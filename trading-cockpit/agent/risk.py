"""Risikomanagement: Positionsgröße, Tagesverlust-Stopp, Positionslimit."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .broker import PaperBroker, to_account, utc_day
from .config import Config, SymbolConfig


@dataclass
class RiskDecision:
    allowed: bool
    units: float = 0.0
    reason: str = ""


class RiskManager:
    def __init__(self, cfg: Config, broker: PaperBroker):
        self.cfg = cfg
        self.broker = broker

    def roll_day(self, ts: int) -> None:
        """Setzt um 00:00 UTC die Tagesbasis für den Verlust-Stopp neu."""
        day = utc_day(ts)
        st = self.broker.state
        if st.day != day:
            st.day = day
            st.day_start_equity = self.broker.equity()

    def daily_loss_hit(self) -> bool:
        st = self.broker.state
        if st.day_start_equity <= 0:
            return False
        limit = st.day_start_equity * (1 - self.cfg.risk.max_daily_loss_pct / 100.0)
        return self.broker.equity() <= limit

    def drawdown_pct(self) -> float:
        """Rückgang vom Höchststand in Prozent; schreibt den Höchststand fort."""
        st = self.broker.state
        eq = self.broker.equity()
        st.peak_equity = max(st.peak_equity or self.cfg.risk.starting_cash, eq)
        return (st.peak_equity - eq) / st.peak_equity * 100.0 if st.peak_equity > 0 else 0.0

    def brake_active(self) -> bool:
        """Kontobremse: einmal ausgelöst, bleibt sie bis zum Zurücksetzen des Kontos."""
        lim = self.cfg.risk.max_total_drawdown_pct
        st = self.broker.state
        if lim > 0 and not st.flags.get("brake") and self.drawdown_pct() >= lim:
            st.flags["brake"] = "1"
        return lim > 0 and bool(st.flags.get("brake"))

    @staticmethod
    def usd_direction(sym: SymbolConfig, side: str) -> Optional[str]:
        """'long' = setzt auf einen stärkeren Dollar, 'short' = auf einen schwächeren."""
        if sym.quote == "USD":
            return "short" if side == "long" else "long"
        if sym.base == "USD":
            return side
        return None

    def size(self, sym: SymbolConfig, price: float, stop: float, side: Optional[str] = None) -> RiskDecision:
        st = self.broker.state
        if sym.name in st.positions:
            return RiskDecision(False, reason="Position in diesem Symbol bereits offen")
        if len(st.positions) >= self.cfg.risk.max_open_positions:
            return RiskDecision(False, reason="Maximale Anzahl offener Positionen erreicht")
        if self.daily_loss_hit():
            return RiskDecision(False, reason="Tagesverlust-Limit erreicht – Pause bis 00:00 UTC")
        if self.brake_active():
            return RiskDecision(False, reason="Kontobremse aktiv – keine neuen Trades")
        lim = self.cfg.risk.max_same_direction
        want = self.usd_direction(sym, side) if side else None
        if lim > 0 and want:
            same = sum(1 for p in st.positions.values()
                       if self.usd_direction(self.cfg.symbol(p.symbol), p.side) == want)
            if same >= lim:
                return RiskDecision(False, reason="Klumpenrisiko: schon eine Position in dieselbe "
                                                  "Dollar-Richtung offen")

        equity = self.broker.equity()
        if equity <= 0:
            return RiskDecision(False, reason="Kein Kapital")
        stop_dist = abs(price - stop)
        if stop_dist <= 0:
            return RiskDecision(False, reason="Ungültiger Stop")

        risk_amount = equity * self.cfg.risk.risk_per_trade_pct / 100.0
        # Verlust pro Einheit beim Stop, in Kontowährung
        loss_per_unit = to_account(stop_dist, stop, sym, self.cfg.risk.account_currency)
        units = risk_amount / loss_per_unit

        # Hebel-Obergrenze: Nominalwert in Kontowährung begrenzen
        notional_per_unit = to_account(price, price, sym, self.cfg.risk.account_currency)
        max_units = equity * sym.max_leverage / notional_per_unit
        capped = units > max_units
        units = min(units, max_units)
        if units <= 0:
            return RiskDecision(False, reason="Positionsgröße 0")
        note = " (durch Hebel-Limit gekappt)" if capped else ""
        return RiskDecision(True, units=units, reason=f"Risiko {risk_amount:.2f}{note}")
