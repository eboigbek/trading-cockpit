"""Backtest: spielt historische Kerzen chronologisch über alle Symbole durch –
mit exakt derselben Engine wie im Live-Betrieb (gleiche Regeln, Gebühren,
Risikolimits)."""
from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from .ai_reviewer import AIReviewer
from .broker import PaperBroker, Trade
from .config import Config
from .data import Candle
from .engine import TradingEngine
from .strategy import min_bars

WINDOW = 400  # Kerzen pro Indikatorberechnung (EMA100 ist danach eingeschwungen)


@dataclass
class BacktestResult:
    start_equity: float
    end_equity: float
    trades: List[Trade]
    equity_curve: List[Tuple[int, float]]
    per_symbol: Dict[str, float] = field(default_factory=dict)

    @property
    def total_return_pct(self) -> float:
        return (self.end_equity / self.start_equity - 1) * 100

    @property
    def win_rate(self) -> float:
        return (sum(1 for t in self.trades if t.pnl > 0) / len(self.trades) * 100) if self.trades else 0.0

    @property
    def profit_factor(self) -> float:
        wins = sum(t.pnl for t in self.trades if t.pnl > 0)
        losses = -sum(t.pnl for t in self.trades if t.pnl < 0)
        return wins / losses if losses > 0 else float("inf") if wins > 0 else 0.0

    @property
    def max_drawdown_pct(self) -> float:
        peak, mdd = float("-inf"), 0.0
        for _, eq in self.equity_curve:
            peak = max(peak, eq)
            mdd = max(mdd, (peak - eq) / peak * 100 if peak > 0 else 0)
        return mdd

    @property
    def total_fees(self) -> float:
        return sum(t.fees for t in self.trades)

    def summary(self) -> str:
        lines = [
            f"Startkapital:     {self.start_equity:,.2f}",
            f"Endkapital:       {self.end_equity:,.2f}  ({self.total_return_pct:+.2f}%)",
            f"Trades:           {len(self.trades)}",
            f"Trefferquote:     {self.win_rate:.1f}%",
            f"Profit-Faktor:    {self.profit_factor:.2f}",
            f"Max. Drawdown:    {self.max_drawdown_pct:.2f}%",
            f"Gebühren gesamt:  {self.total_fees:,.2f}",
            "Ergebnis je Symbol:",
        ]
        lines += [f"  {k:<8} {v:+,.2f}" for k, v in sorted(self.per_symbol.items())]
        reasons: Dict[str, int] = {}
        for t in self.trades:
            reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
        lines.append("Ausstiegsgründe:  " + ", ".join(f"{k}={v}" for k, v in sorted(reasons.items())))
        return "\n".join(lines)


def run_backtest(cfg: Config, data: Dict[str, List[Candle]],
                 reviewer: Optional[AIReviewer] = None) -> BacktestResult:
    broker = PaperBroker(cfg, persist=False)
    engine = TradingEngine(cfg, broker, reviewer)
    warmup = min_bars(cfg.strategy)

    index: Dict[str, Dict[int, int]] = {n: {c.ts: i for i, c in enumerate(cs)} for n, cs in data.items()}
    all_ts = sorted({c.ts for cs in data.values() for c in cs})
    curve: List[Tuple[int, float]] = []
    for ts in all_ts:
        for sym in cfg.symbols:
            i = index.get(sym.name, {}).get(ts)
            if i is None or i < warmup:
                continue
            candles = data[sym.name]
            engine.on_bar(sym, candles[max(0, i - WINDOW + 1): i + 1])
        curve.append((ts, broker.equity()))

    # Offene Positionen am Ende zum letzten Kurs schließen
    for name in list(broker.state.positions):
        sym = cfg.symbol(name)
        last = data[name][-1]
        broker.close(sym, last.close, last.ts, "backtest_ende")
    if curve:
        curve.append((curve[-1][0], broker.equity()))

    per_symbol: Dict[str, float] = {}
    for t in broker.state.trades:
        per_symbol[t.symbol] = per_symbol.get(t.symbol, 0.0) + t.pnl
    return BacktestResult(cfg.risk.starting_cash, broker.equity(), broker.state.trades, curve, per_symbol)


def write_report(res: BacktestResult, path: str, title: str = "Backtest") -> None:
    """Einfacher HTML-Bericht mit Equity-Kurve (inline SVG) und Trade-Liste."""
    pts = res.equity_curve[:: max(1, len(res.equity_curve) // 600)] or [(0, res.start_equity)]
    lo = min(e for _, e in pts)
    hi = max(e for _, e in pts)
    span = (hi - lo) or 1.0
    w, h = 800, 260
    coords = " ".join(f"{i / max(1, len(pts) - 1) * w:.1f},{h - (e - lo) / span * (h - 20) - 10:.1f}"
                      for i, (_, e) in enumerate(pts))
    base_y = h - (res.start_equity - lo) / span * (h - 20) - 10

    def d(ts: int) -> str:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%m-%d %H:%M")

    rows = "".join(
        f"<tr><td>{html.escape(t.symbol)}</td><td>{t.side}</td><td>{d(t.opened_ts)}</td>"
        f"<td>{d(t.closed_ts)}</td><td>{t.entry:.6g}</td><td>{t.exit:.6g}</td>"
        f"<td class='{'pos' if t.pnl > 0 else 'neg'}'>{t.pnl:+.2f}</td><td>{html.escape(t.exit_reason)}</td></tr>"
        for t in res.trades[-200:])
    stats = "".join(f"<div class='stat'><span>{k}</span><b>{v}</b></div>" for k, v in [
        ("Rendite", f"{res.total_return_pct:+.2f}%"), ("Trades", len(res.trades)),
        ("Trefferquote", f"{res.win_rate:.1f}%"), ("Profit-Faktor", f"{res.profit_factor:.2f}"),
        ("Max. Drawdown", f"{res.max_drawdown_pct:.2f}%"), ("Gebühren", f"{res.total_fees:,.2f}")])
    doc = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>
:root{{--bg:#fafaf9;--fg:#1c1917;--muted:#78716c;--line:#2563eb;--card:#fff;--border:#e7e5e4;--pos:#15803d;--neg:#b91c1c}}
@media (prefers-color-scheme:dark){{:root{{--bg:#1c1917;--fg:#f5f5f4;--muted:#a8a29e;--line:#60a5fa;--card:#292524;--border:#44403c;--pos:#4ade80;--neg:#f87171}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;margin:0;padding:16px;max-width:900px;margin-inline:auto}}
h1{{font-size:20px;margin:0 0 4px}} p.note{{color:var(--muted);font-size:13px;margin:0 0 16px}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin-bottom:16px}}
.stat{{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:10px}}
.stat span{{display:block;color:var(--muted);font-size:12px}} .stat b{{font-size:18px;font-variant-numeric:tabular-nums}}
svg{{width:100%;height:auto;background:var(--card);border:1px solid var(--border);border-radius:8px}}
.wrap{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums;margin-top:16px}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--border);white-space:nowrap}} th{{color:var(--muted);font-weight:500}}
.pos{{color:var(--pos)}} .neg{{color:var(--neg)}}
</style></head><body>
<h1>{html.escape(title)}</h1>
<p class="note">Paper-Trading-Simulation. Vergangene oder simulierte Ergebnisse sind keine Garantie für zukünftige Gewinne.</p>
<div class="stats">{stats}</div>
<svg viewBox="0 0 {w} {h}" role="img" aria-label="Equity-Kurve">
<line x1="0" x2="{w}" y1="{base_y:.1f}" y2="{base_y:.1f}" stroke="currentColor" stroke-opacity=".25" stroke-dasharray="4 4"/>
<polyline fill="none" stroke="var(--line)" stroke-width="2" points="{coords}"/></svg>
<div class="wrap"><table><thead><tr><th>Symbol</th><th>Seite</th><th>Eröffnet</th><th>Geschlossen</th>
<th>Einstieg</th><th>Ausstieg</th><th>PnL</th><th>Grund</th></tr></thead><tbody>{rows}</tbody></table></div>
</body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
