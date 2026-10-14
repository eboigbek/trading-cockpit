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


class TradingEngine:
    def __init__(self, cfg: Config, broker: PaperBroker, reviewer: Optional[AIReviewer] = None):
        self.cfg = cfg
        self.broker = broker
        self.risk = RiskManager(cfg, broker)
        self.reviewer = reviewer

    def on_bar(self, sym: SymbolConfig, candles: List[Candle], allow_entry: bool = True) -> BarResult:
        """`candles` = alle bisher abgeschlossenen Kerzen; die letzte ist neu.
        allow_entry=False: nur Ausstiege prüfen (z.B. beim Nachholen verpasster Kerzen)."""
        res = BarResult(sym.name)
        bar = candles[-1]
        st = self.broker.state
        self.risk.roll_day(bar.ts)

        # 1) Offene Position: Stop/Target innerhalb der Kerze, dann Zeit-/Signal-Ausstieg
        pos = st.positions.get(sym.name)
        if pos:
            pos.bars_held += 1
            t = self.broker.check_stops(sym, bar.high, bar.low, bar.ts)
            if t:
                res.closed.append(t)
            elif pos.bars_held >= self.cfg.strategy.max_hold_bars:
                res.closed.append(self.broker.close(sym, bar.close, bar.ts, "max_haltedauer"))
            elif opposite_cross(pos.side, candles, self.cfg.strategy):
                res.closed.append(self.broker.close(sym, bar.close, bar.ts, "gegensignal"))
        self.broker.mark(sym, bar.close)

        # 2) Neues Signal nur, wenn flach
        if sym.name in st.positions or not allow_entry:
            return res
        sig = generate_signal(sym.name, candles, self.cfg.strategy)
        if not sig:
            return res
        res.signal = sig

        decision = self.risk.size(sym, sig.price, sig.stop)
        if not decision.allowed:
            res.skipped_reason = decision.reason
            log.info("%s %s-Signal verworfen: %s", sym.name, sig.side, decision.reason)
            return res

        # 3) Optionale KI-Prüfung durch Claude
        ai_note = ""
        if self.reviewer and self.reviewer.active:
            review = self.reviewer.review(sig, candles, self.broker)
            res.review = review
            ai_note = f"{review.decision} ({review.confidence:.2f}): {review.reason}"
            if not review.approved:
                res.skipped_reason = f"KI abgelehnt: {review.reason}"
                log.info("%s %s-Signal von Claude abgelehnt: %s", sym.name, sig.side, review.reason)
                return res

        self.broker.open(sym, sig.side, decision.units, sig.price, sig.stop, sig.take_profit,
                         bar.ts, sig.reason, ai_note)
        res.opened = True
        return res
