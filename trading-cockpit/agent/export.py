"""Erzeugt data/cockpit.json – alles, was die Cockpit-Webseite anzeigt."""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

from .broker import PaperBroker, Trade
from .config import Config
from .data import Candle
from .gate import max_drawdown_pct, profit_factor, progress
from .indicators import ema, rsi

# Gebühren-Szenarien für BTC (pro Kauf bzw. Verkauf). 0,80 % = Kraken Pro Einstiegsstufe mit Market-Order.
BTC_FEE_SCENARIOS = [0.10, 0.25, 0.40, 0.80]


def _downsample(points: List, n: int) -> List:
    if len(points) <= n:
        return points
    step = len(points) / n
    out = [points[int(i * step)] for i in range(n)]
    out[-1] = points[-1]
    return out


def _trade_dict(t: Trade) -> Dict:
    return {"symbol": t.symbol, "side": t.side, "units": t.units, "entry": t.entry, "exit": t.exit,
            "opened": t.opened_ts, "closed": t.closed_ts, "pnl": round(t.pnl, 2), "fees": round(t.fees, 2),
            "gross": round(t.gross_pnl, 2), "reason": t.exit_reason, "entry_reason": t.entry_reason,
            "ai": t.ai_note}


def fee_scenarios(cfg: Config, trades: List[Trade]) -> List[Dict]:
    """Was wäre das Gesamtergebnis, wenn BTC-Trades andere Gebühren hätten?"""
    out = []
    try:
        current = cfg.symbol("BTC/USD").fee_pct
    except KeyError:
        return out
    btc = [t for t in trades if t.symbol == "BTC/USD" and t.turnover > 0]
    other = sum(t.pnl for t in trades if t.symbol != "BTC/USD")
    for f in BTC_FEE_SCENARIOS:
        btc_net = sum(t.gross_pnl - t.turnover * f / 100 for t in btc)
        out.append({"fee_pct": f, "net": round(other + btc_net, 2), "current": abs(f - current) < 1e-9})
    return out


def market_info(name: str, candles: List[Candle]) -> Dict:
    closes = [c.close for c in candles]
    last = closes[-1]
    day_ago = closes[-97] if len(closes) > 96 else closes[0]
    r = rsi(closes, 14)[-1]
    e = ema(closes, 100)[-1]
    return {
        "symbol": name, "price": last, "ts": candles[-1].ts,
        "change_24h_pct": round((last / day_ago - 1) * 100, 3) if day_ago else 0.0,
        "closes": [round(c, 6) for c in closes[-96:]],
        "rsi": round(r, 1) if r is not None else None,
        "trend": None if e is None else ("auf" if last > e else "ab"),
    }


def build(cfg: Config, broker: PaperBroker, now_ts: int, markets: Dict[str, List[Candle]],
          ai_active: bool, ai_model: str, mode_requested: str, stop: bool,
          mode_note: str, prev: Optional[Dict] = None) -> Dict:
    st = broker.state
    start = cfg.risk.starting_cash
    eq = broker.equity()
    trades = st.trades
    wins = [t for t in trades if t.pnl > 0]
    positions = []
    for p in st.positions.values():
        price = st.last_prices.get(p.symbol, p.entry)
        positions.append({"symbol": p.symbol, "side": p.side, "units": p.units, "entry": p.entry,
                          "stop": p.stop, "tp": p.take_profit, "price": price, "opened": p.opened_ts,
                          "unrealized": round(broker.unrealized(cfg.symbol(p.symbol), price), 2),
                          "reason": p.reason, "ai": p.ai_note})
    mk = []
    prev_markets = {m["symbol"]: m for m in (prev or {}).get("markets", [])}
    for s in cfg.symbols:
        if s.name in markets and markets[s.name]:
            mk.append(market_info(s.name, markets[s.name]))
        elif s.name in prev_markets:  # Datenquelle kurz weg: letzten Stand behalten
            mk.append({**prev_markets[s.name], "stale": True})
    return {
        "version": 1,
        "generated_at": now_ts,
        "interval_min": cfg.interval_min,
        "mode": {"effective": "paper", "requested": mode_requested, "stop": stop, "note": mode_note},
        "ai": {"active": ai_active, "model": ai_model if ai_active else None},
        "account": {
            "currency": cfg.risk.account_currency, "start": start, "equity": round(eq, 2),
            "cash": round(st.cash, 2), "pnl": round(eq - start, 2), "pnl_pct": round((eq / start - 1) * 100, 3),
            "fees_total": round(sum(t.fees for t in trades), 2), "trades": len(trades),
            "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else None,
            "profit_factor": round(profit_factor(trades), 2) if trades else None,
            "max_drawdown_pct": round(max_drawdown_pct(st.equity_history, start), 2),
            "paper_start": st.paper_start_ts,
        },
        "fee_scenarios": fee_scenarios(cfg, trades),
        "fees_config": [{"symbol": s.name, "fee_pct": s.fee_pct} for s in cfg.symbols],
        "positions": positions,
        "markets": mk,
        "equity_curve": _downsample(st.equity_history, 400),
        "trades": [_trade_dict(t) for t in reversed(trades[-150:])],
        "events": list(reversed(st.events[-80:])),
        "gate": progress(st, cfg.gate, start, now_ts),
        "limits": {
            "paper": {"risk_per_trade_pct": cfg.risk.risk_per_trade_pct,
                      "max_daily_loss_pct": cfg.risk.max_daily_loss_pct,
                      "max_open_positions": cfg.risk.max_open_positions},
            "live": {"max_capital": cfg.live.max_capital, "currency": cfg.live.currency,
                     "risk_per_trade_pct": cfg.live.risk_per_trade_pct,
                     "max_daily_loss_pct": cfg.live.max_daily_loss_pct,
                     "max_total_loss_pct": cfg.live.max_total_loss_pct,
                     "max_open_positions": cfg.live.max_open_positions,
                     "symbols": cfg.live.symbols, "long_only": cfg.live.long_only,
                     "leverage": cfg.live.leverage, "withdrawals_allowed": cfg.live.withdrawals_allowed},
        },
    }


def write(path: str, data: Dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
    os.replace(tmp, path)


def read(path: str) -> Optional[Dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
