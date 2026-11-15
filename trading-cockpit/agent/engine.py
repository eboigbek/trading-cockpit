"""Gemeinsamer Kern für Live-Agent und Backtest: verarbeitet je Symbol eine neue
abgeschlossene Kerze (Stops prüfen -> Ausstiege -> neues Signal -> Risiko ->
KI-Prüfung -> Order)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from .ai_reviewer import AIReviewer, Review
from .broker import PaperBroker, Trade
from .config import Config, SymbolConfig
from .data import Candle
from .risk import RiskManager
from .montecarlo import describe, seed_for, simulate
from .session import blackout, entry_time_ok, is_fx, load_calendar, must_flatten
from .strategy import Signal, generate_signal, opposite_cross

log = logging.getLogger("agent.engine")


@dataclass
class BarResult:
    symbol: str
    closed: List[Trade] = field(default_factory=list)
    signal: Optional[Signal] = None
    review: Optional[Review] = None
    opened: bool = False
    skipped_reason: str = ""
    mc: Optional[dict] = None
    skip_kind: str = ""          # "late", "news", "quality", "cost", "timemachine", "risk", "ai"


def cost_r(price: float, stop: float, fee_pct: float, slippage_pct: float) -> float:
    """Kosten für Ein- und Ausstieg (Gebühr + Slippage) als Anteil des Risikos bis zum Stop."""
    dist = abs(price - stop)
    if dist <= 0:
        return float("inf")
    return 2 * (fee_pct + slippage_pct) / 100.0 * price / dist


def unchanged_share(candles: List[Candle], window: int) -> float:
    """Anteil der Kerzen ohne jede Kursänderung – hoch bei illiquiden/eingefrorenen Daten."""
    w = candles[-window:]
    if len(w) < 2:
        return 0.0
    same = sum(1 for a, b in zip(w, w[1:]) if b.close == a.close and b.high == b.low)
    return same / (len(w) - 1)


class TradingEngine:
    def __init__(self, cfg: Config, broker: PaperBroker, reviewer: Optional[AIReviewer] = None):
        self.cfg = cfg
        self.broker = broker
        self.risk = RiskManager(cfg, broker)
        self.reviewer = reviewer
        self.events = load_calendar(cfg.news.file) if cfg.news.enabled else []

    def on_bar(self, sym: SymbolConfig, candles: List[Candle], allow_entry: bool = True,
               stale_reason: str = "") -> BarResult:
        """`candles` = alle bisher abgeschlossenen Kerzen; die letzte ist neu.
        allow_entry=False: nur Ausstiege prüfen (z.B. beim Nachholen verpasster Kerzen).
        stale_reason: der Lauf kam zu spät – ein Signal wird nur noch protokolliert."""
        res = BarResult(sym.name)
        bar = candles[-1]
        st = self.broker.state
        iv = self.cfg.interval_min
        fx = is_fx(sym)
        self.risk.roll_day(bar.ts)

        # 1) Offene Position: Stop/Target innerhalb der Kerze, dann Zeit-/Signal-Ausstieg
        pos = st.positions.get(sym.name)
        if pos:
            pos.bars_held += 1
            t = self.broker.check_stops(sym, bar.high, bar.low, bar.ts, bar.open)
            if t:
                res.closed.append(t)
            elif fx and must_flatten(bar.ts, iv, self.cfg.hours):
                res.closed.append(self.broker.close(sym, bar.close, bar.ts, "wochenende"))
            elif pos.bars_held >= self.cfg.strategy.max_hold_bars:
                res.closed.append(self.broker.close(sym, bar.close, bar.ts, "max_haltedauer"))
            elif opposite_cross(pos.side, candles, self.cfg.strategy):
                res.closed.append(self.broker.close(sym, bar.close, bar.ts, "gegensignal"))
        self.broker.mark(sym, bar.close)
        self.risk.drawdown_pct()   # Höchststand fortschreiben

        # 2) Neues Signal nur, wenn flach, Markt offen und Kontobremse nicht ausgelöst
        if sym.name in st.positions or not (allow_entry or stale_reason):
            return res
        if self.risk.brake_active() or (fx and not entry_time_ok(bar.ts, iv, self.cfg.hours)):
            return res
        sig = generate_signal(sym.name, candles, self.cfg.strategy)
        if not sig:
            return res
        res.signal = sig

        # 2·) Lauf kam zu spät: der Kerzenschlusskurs ist nicht mehr zu bekommen
        if stale_reason:
            st.late_skipped += 1
            res.skip_kind, res.skipped_reason = "late", stale_reason
            return res

        # 2··) Sperrzeit um einen angekündigten Termin
        ev = blackout(bar.ts + iv * 60, sym.name, self.events, self.cfg.news.before_min,
                      self.cfg.news.after_min) if self.cfg.news.enabled else None
        if ev:
            res.skip_kind, res.skipped_reason = "news", f"Sperrzeit um „{ev.name}“ – kein Einstieg"
            return res

        # 2a) Datenqualität: bei eingefrorenen/illiquiden Kursen nicht handeln
        share = unchanged_share(candles, self.cfg.quality.window_bars)
        if share > self.cfg.quality.max_unchanged_share:
            res.skip_kind = "quality"
            res.skipped_reason = (f"Kursdaten unzuverlässig ({share * 100:.0f} % der letzten Kerzen ohne "
                                  f"Kursänderung) – kein Handel")
            return res

        # 2b) Kosten-Filter: fressen Gebühren + Slippage zu viel vom Risiko, ist der Trade chancenlos
        c_r = cost_r(sig.price, sig.stop, sym.fee_pct, self.cfg.risk.slippage_pct)
        sig.indicators["kosten_r"] = round(c_r, 3)
        if c_r > self.cfg.risk.max_cost_r:
            res.skip_kind = "cost"
            res.skipped_reason = (f"Kosten {c_r:.2f} R – mehr als {self.cfg.risk.max_cost_r:.2f} R erlaubt "
                                  f"(Stop zu nah für die Gebühren)")
            return res

        decision = self.risk.size(sym, sig.price, sig.stop, sig.side)
        if not decision.allowed:
            res.skip_kind = "risk"
            res.skipped_reason = decision.reason
            log.info("%s %s-Signal verworfen: %s", sym.name, sig.side, decision.reason)
            return res

        # 2c) Time Machine: 10.000 Pfade durchspielen, Erwartungswert nach Kosten
        mc_dict = None
        tm = self.cfg.timemachine
        if tm.enabled:
            try:
                r = simulate(candles, sig.side, sig.price, sig.stop, sig.take_profit, sym.fee_pct,
                             self.cfg.risk.slippage_pct, self.cfg.strategy.max_hold_bars,
                             paths=tm.paths, lookback=tm.lookback_bars, seed=seed_for(sym.name, bar.ts))
                mc_dict = r.as_dict()
                res.mc = mc_dict
                approved = r.ev_r >= tm.min_ev_r
                st.last_mc = {**mc_dict, "symbol": sym.name, "side": sig.side,
                              "ts": bar.ts + self.cfg.interval_min * 60, "approved": approved}
                if not approved:
                    st.mc_skipped += 1
                    res.skip_kind = "timemachine"
                    res.skipped_reason = f"Time Machine: {describe(mc_dict)} – Kosten zu hoch für den möglichen Gewinn, Trade ausgelassen"
                    return res
                sig.indicators["time_machine"] = describe(mc_dict)
            except ValueError as e:
                log.warning("Time Machine übersprungen: %s", e)

        # 3) Optionale KI-Prüfung durch Claude
        ai_note = ""
        if self.reviewer and self.reviewer.active:
            review = self.reviewer.review(sig, candles, self.broker)
            res.review = review
            ai_note = f"{review.decision} ({review.confidence:.2f}): {review.reason}"
            if not review.approved:
                res.skip_kind = "ai"
                res.skipped_reason = f"KI abgelehnt: {review.reason}"
                log.info("%s %s-Signal von Claude abgelehnt: %s", sym.name, sig.side, review.reason)
                return res

        self.broker.open(sym, sig.side, decision.units, sig.price, sig.stop, sig.take_profit,
                         bar.ts, sig.reason, ai_note, mc_dict)
        res.opened = True
        return res
