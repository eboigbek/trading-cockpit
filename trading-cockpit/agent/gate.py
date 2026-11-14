"""Echtgeld-Freischaltung: prüft, ob der Spielgeld-Lauf die vereinbarten
Bedingungen erfüllt (Laufzeit, Anzahl Trades, Profit-Faktor, Drawdown, Gewinn
nach Gebühren). Erst wenn ALLE erfüllt sind, gilt Echtgeld als freigeschaltet."""
from __future__ import annotations

from typing import Dict, List

from .broker import AccountState, Trade
from .config import GateConfig


def profit_factor(trades: List[Trade]) -> float:
    wins = sum(t.pnl for t in trades if t.pnl > 0)
    losses = -sum(t.pnl for t in trades if t.pnl < 0)
    if losses > 0:
        return wins / losses
    return 99.0 if wins > 0 else 0.0


def max_drawdown_pct(history: List[List[float]], start: float) -> float:
    peak, mdd = start, 0.0
    for _, eq in history:
        peak = max(peak, eq)
        if peak > 0:
            mdd = max(mdd, (peak - eq) / peak * 100)
    return mdd


def t_stat(trades: List[Trade]) -> float:
    """Ø-Ergebnis pro Trade geteilt durch seinen Standardfehler. Ab ~2 ist ein Gewinn mit
    rund 95 % Sicherheit kein reiner Zufall (vereinfachter t-Test, Trades als unabhängig)."""
    n = len(trades)
    if n < 2:
        return 0.0
    xs = [t.pnl for t in trades]
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    if var <= 0:
        return 0.0
    return m / (var ** 0.5 / n ** 0.5)


def progress(state: AccountState, gate: GateConfig, starting_cash: float, now_ts: int) -> Dict:
    days = (now_ts - state.paper_start_ts) / 86_400 if state.paper_start_ts else 0.0
    trades = state.trades
    pf = profit_factor(trades)
    net = sum(t.pnl for t in trades)
    dd = max_drawdown_pct(state.equity_history, starting_cash)

    def item(key, label, value, target, ok, pct, fmt):
        return {"key": key, "label": label, "value": value, "target": target, "ok": bool(ok),
                "pct": max(0.0, min(1.0, pct)), "display": fmt}

    items = [
        item("days", "Laufzeit Spielgeld", round(days, 1), gate.min_days, days >= gate.min_days,
             days / gate.min_days if gate.min_days else 1, f"{days:.1f} / {gate.min_days} Tage"),
        item("trades", "Abgeschlossene Trades", len(trades), gate.min_trades, len(trades) >= gate.min_trades,
             len(trades) / gate.min_trades if gate.min_trades else 1, f"{len(trades)} / {gate.min_trades}"),
        item("pf", "Profit-Faktor (nach Gebühren)", round(pf, 2), gate.min_profit_factor,
             len(trades) > 0 and pf >= gate.min_profit_factor,
             pf / gate.min_profit_factor if gate.min_profit_factor else 1,
             f"{pf:.2f} / mind. {gate.min_profit_factor:.2f}" if trades else "noch keine Trades"),
        item("dd", "Größter Rückgang", round(dd, 2), gate.max_drawdown_pct, dd <= gate.max_drawdown_pct,
             1 - dd / gate.max_drawdown_pct if gate.max_drawdown_pct else 1,
             f"{dd:.1f} % / max. {gate.max_drawdown_pct:.0f} %"),
    ]
    if gate.min_t_stat > 0:
        ts = t_stat(trades)
        items.append(item("tstat", "Zufallstest (t-Wert)", round(ts, 2), gate.min_t_stat,
                          len(trades) >= 2 and ts >= gate.min_t_stat,
                          ts / gate.min_t_stat if gate.min_t_stat else 1,
                          f"{ts:.2f} / mind. {gate.min_t_stat:.1f}" if len(trades) >= 2 else "noch zu wenige Trades"))
    if gate.require_net_profit:
        items.append(item("net", "Ergebnis nach Gebühren", round(net, 2), 0, net > 0,
                          1.0 if net > 0 else 0.0, f"{net:+,.2f}"))
    return {"unlocked": all(i["ok"] for i in items), "items": items}
