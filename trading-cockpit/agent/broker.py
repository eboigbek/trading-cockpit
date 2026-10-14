"""Paper-Broker: simuliertes Konto mit Gebühren, Spread/Slippage, Stop-Loss und
Take-Profit. Es wird KEIN echtes Geld bewegt und keine echte Order gesendet.

Kontomodell (wie ein Margin-/CFD-Konto): Positionen binden kein Bargeld, aber
Gewinne/Verluste und Gebühren werden in Kontowährung verbucht. Die Positions-
größe wird vom Risikomanager begrenzt.
"""
from __future__ import annotations

import csv
import io
import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from . import vault
from .config import Config, SymbolConfig


@dataclass
class Position:
    symbol: str
    side: str
    units: float          # Einheiten der Basiswährung (z.B. BTC oder EUR)
    entry: float
    stop: float
    take_profit: float
    opened_ts: int
    bars_held: int = 0
    reason: str = ""
    ai_note: str = ""


@dataclass
class Trade:
    symbol: str
    side: str
    units: float
    entry: float
    exit: float
    opened_ts: int
    closed_ts: int
    pnl: float            # netto, nach Gebühren, in Kontowährung
    fees: float
    exit_reason: str
    entry_reason: str = ""
    ai_note: str = ""
    gross_pnl: float = 0.0   # vor Gebühren, in Kontowährung
    turnover: float = 0.0    # gehandelter Nominalwert Ein- + Ausstieg, in Kontowährung (Basis der Gebühren)


@dataclass
class AccountState:
    cash: float
    positions: Dict[str, Position] = field(default_factory=dict)
    trades: List[Trade] = field(default_factory=list)
    day: str = ""
    day_start_equity: float = 0.0
    last_bar_ts: Dict[str, int] = field(default_factory=dict)
    last_prices: Dict[str, float] = field(default_factory=dict)
    paper_start_ts: int = 0
    equity_history: List[List[float]] = field(default_factory=list)   # [ts, equity]
    events: List[Dict] = field(default_factory=list)                  # {ts, kind, text}
    flags: Dict[str, str] = field(default_factory=dict)               # z.B. zuletzt gemeldeter Modus-Status


def to_account(amount_quote: float, price: float, sym: SymbolConfig, account_ccy: str) -> float:
    """Betrag in Kurswährung -> Kontowährung (unterstützt XXX/USD und USD/XXX)."""
    if sym.quote == account_ccy:
        return amount_quote
    if sym.base == account_ccy:
        return amount_quote / price
    raise ValueError(f"{sym.name}: Umrechnung nach {account_ccy} nicht unterstützt")


def utc_day(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


class PaperBroker:
    def __init__(self, cfg: Config, persist: bool = True):
        self.cfg = cfg
        self.persist = persist
        self.state = self._load() if persist else AccountState(cash=cfg.risk.starting_cash)

    # ---------------- Persistenz ----------------
    def _load(self) -> AccountState:
        text = vault.read_text(self.cfg.state_file)
        if text is None:
            return AccountState(cash=self.cfg.risk.starting_cash)
        raw = json.loads(text)
        return AccountState(
            cash=raw["cash"],
            positions={k: Position(**v) for k, v in raw.get("positions", {}).items()},
            trades=[Trade(**t) for t in raw.get("trades", [])],
            day=raw.get("day", ""),
            day_start_equity=raw.get("day_start_equity", 0.0),
            last_bar_ts=raw.get("last_bar_ts", {}),
            last_prices=raw.get("last_prices", {}),
            paper_start_ts=raw.get("paper_start_ts", 0),
            equity_history=raw.get("equity_history", []),
            events=raw.get("events", []),
            flags=raw.get("flags", {}),
        )

    def save(self) -> None:
        if not self.persist:
            return
        vault.write_text(self.cfg.state_file, json.dumps(asdict(self.state), indent=1))

    def _append_trade_csv(self, t: Trade) -> None:
        if not self.persist:
            return
        path = self.cfg.trades_file
        existing = vault.read_text(path) or ""
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(asdict(t).keys()), lineterminator="\n")
        if not existing:
            w.writeheader()
        w.writerow(asdict(t))
        vault.write_text(path, existing + buf.getvalue())

    # ---------------- Protokoll & Verlauf ----------------
    MAX_EVENTS = 300
    MAX_HISTORY = 6000

    def event(self, ts: int, kind: str, text: str) -> None:
        self.state.events.append({"ts": int(ts), "kind": kind, "text": text})
        if len(self.state.events) > self.MAX_EVENTS:
            del self.state.events[: len(self.state.events) - self.MAX_EVENTS]

    def snapshot(self, ts: int, min_gap_s: int = 900) -> None:
        """Equity-Punkt für die Kurve speichern (höchstens alle 15 Minuten)."""
        h = self.state.equity_history
        if h and ts - h[-1][0] < min_gap_s:
            h[-1] = [int(ts), round(self.equity(), 4)]
            return
        h.append([int(ts), round(self.equity(), 4)])
        if len(h) > self.MAX_HISTORY:
            # ältere Hälfte ausdünnen statt abschneiden
            old, new = h[: len(h) // 2], h[len(h) // 2:]
            self.state.equity_history = old[::2] + new

    # ---------------- Bewertung ----------------
    def unrealized(self, sym: SymbolConfig, price: float) -> float:
        pos = self.state.positions.get(sym.name)
        if not pos:
            return 0.0
        direction = 1 if pos.side == "long" else -1
        return to_account((price - pos.entry) * pos.units * direction, price, sym,
                          self.cfg.risk.account_currency)

    def equity(self) -> float:
        eq = self.state.cash
        for name, pos in self.state.positions.items():
            price = self.state.last_prices.get(name, pos.entry)
            eq += self.unrealized(self.cfg.symbol(name), price)
        return eq

    def mark(self, sym: SymbolConfig, price: float) -> None:
        self.state.last_prices[sym.name] = price

    # ---------------- Ausführung ----------------
    def _fee(self, sym: SymbolConfig, units: float, price: float) -> float:
        notional_quote = units * price
        return to_account(notional_quote * sym.fee_pct / 100.0, price, sym,
                          self.cfg.risk.account_currency)

    def _slip(self, price: float, side: str, opening: bool) -> float:
        s = self.cfg.risk.slippage_pct / 100.0
        buying = (side == "long") == opening
        return price * (1 + s) if buying else price * (1 - s)

    def open(self, sym: SymbolConfig, side: str, units: float, price: float, stop: float,
             take_profit: float, ts: int, reason: str = "", ai_note: str = "") -> Position:
        if sym.name in self.state.positions:
            raise RuntimeError(f"{sym.name}: Position bereits offen")
        fill = self._slip(price, side, opening=True)
        self.state.cash -= self._fee(sym, units, fill)
        pos = Position(sym.name, side, units, fill, stop, take_profit, ts, 0, reason, ai_note)
        self.state.positions[sym.name] = pos
        self.mark(sym, price)
        return pos

    def close(self, sym: SymbolConfig, price: float, ts: int, exit_reason: str,
              already_slipped: bool = False) -> Trade:
        pos = self.state.positions.pop(sym.name)
        fill = price if already_slipped else self._slip(price, pos.side, opening=False)
        direction = 1 if pos.side == "long" else -1
        gross = to_account((fill - pos.entry) * pos.units * direction, fill, sym,
                           self.cfg.risk.account_currency)
        entry_fee = self._fee(sym, pos.units, pos.entry)
        exit_fee = self._fee(sym, pos.units, fill)
        self.state.cash += gross - exit_fee
        ccy = self.cfg.risk.account_currency
        turnover = (to_account(pos.units * pos.entry, pos.entry, sym, ccy)
                    + to_account(pos.units * fill, fill, sym, ccy))
        t = Trade(sym.name, pos.side, pos.units, pos.entry, fill, pos.opened_ts, ts,
                  round(gross - exit_fee - entry_fee, 6), round(entry_fee + exit_fee, 6),
                  exit_reason, pos.reason, pos.ai_note, round(gross, 6), round(turnover, 4))
        self.state.trades.append(t)
        self.mark(sym, price)
        self._append_trade_csv(t)
        return t

    def check_stops(self, sym: SymbolConfig, high: float, low: float, ts: int) -> Optional[Trade]:
        """Prüft, ob die Kerze Stop-Loss oder Take-Profit erreicht hat.
        Werden beide in derselben Kerze berührt, wird konservativ der Stop angenommen."""
        pos = self.state.positions.get(sym.name)
        if not pos:
            return None
        if pos.side == "long":
            hit_sl, hit_tp = low <= pos.stop, high >= pos.take_profit
        else:
            hit_sl, hit_tp = high >= pos.stop, low <= pos.take_profit
        if hit_sl:
            return self.close(sym, pos.stop, ts, "stop_loss")
        if hit_tp:
            return self.close(sym, pos.take_profit, ts, "take_profit")
        return None
