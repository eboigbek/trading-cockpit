"""Zentrale Einstellungen des Trading-Agenten.

Alle Werte lassen sich über eine config.json im Projektordner überschreiben
(siehe config.example.json). Nichts hier ist eine Anlageempfehlung – es sind
Startwerte für einen Paper-Trading-Test.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, List


@dataclass
class SymbolConfig:
    name: str            # Anzeigename, z.B. "BTC/USD"
    base: str            # Basiswährung, z.B. "BTC"
    quote: str           # Kurswährung, z.B. "USD"
    kraken: str          # Kraken-Paarname, z.B. "XBTUSD"
    yahoo: str           # Yahoo-Ticker als Fallback, z.B. "BTC-USD"
    fee_pct: float       # Kosten pro Seite (Gebühr + halber Spread) in Prozent des Nominalwerts
    max_leverage: float  # Max. Nominalwert / Kontostand für dieses Instrument


DEFAULT_SYMBOLS: List[SymbolConfig] = [
    SymbolConfig("BTC/USD", "BTC", "USD", "XBTUSD", "BTC-USD", fee_pct=0.80, max_leverage=1.0),
    SymbolConfig("EUR/USD", "EUR", "USD", "EURUSD", "EURUSD=X", fee_pct=0.006, max_leverage=10.0),
    SymbolConfig("GBP/USD", "GBP", "USD", "GBPUSD", "GBPUSD=X", fee_pct=0.008, max_leverage=10.0),
    SymbolConfig("USD/JPY", "USD", "JPY", "USDJPY", "JPY=X", fee_pct=0.008, max_leverage=10.0),
]


@dataclass
class StrategyConfig:
    ema_fast: int = 9
    ema_slow: int = 21
    ema_trend: int = 100
    rsi_period: int = 14
    atr_period: int = 14
    rsi_long_min: float = 50.0
    rsi_long_max: float = 70.0
    rsi_short_min: float = 30.0
    rsi_short_max: float = 50.0
    stop_atr: float = 1.5        # Stop-Loss-Abstand in ATR
    take_profit_atr: float = 3.0  # Take-Profit-Abstand in ATR (=> Chance/Risiko 1:2)
    max_hold_bars: int = 96       # Daytrading: nach 96 x 15 min = 24 h wird geschlossen
    allow_short: bool = True


@dataclass
class RiskConfig:
    starting_cash: float = 10_000.0     # Paper-Startkapital in Kontowährung
    account_currency: str = "USD"
    risk_per_trade_pct: float = 1.0     # Max. Verlust pro Trade in % des Kontos
    max_daily_loss_pct: float = 3.0     # Tagesverlust-Stopp: danach keine neuen Trades bis 00:00 UTC
    max_open_positions: int = 3
    slippage_pct: float = 0.005         # Zusätzliche Ausführungsabweichung pro Order (0.005 % ≈ 0,5 Pip EUR/USD)


@dataclass
class AIConfig:
    enabled: bool = True          # Wird nur aktiv, wenn ANTHROPIC_API_KEY gesetzt ist
    model: str = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
    # Falls ein Modellname nicht (mehr) existiert, werden diese der Reihe nach probiert
    fallback_models: List[str] = field(default_factory=lambda: ["claude-sonnet-5", "claude-sonnet-4-5"])
    fail_open: bool = True        # Bei API-Fehler: Signal trotzdem ausführen (True) oder verwerfen (False)
    min_confidence: float = 0.55  # Unter diesem Wert wird ein APPROVE wie REJECT behandelt
    timeout_s: int = 30


@dataclass
class GateConfig:
    """Bedingungen, die der Spielgeld-Lauf erfüllen muss, bevor Echtgeld freigeschaltet wird."""
    min_days: int = 42                 # 6 Wochen
    min_trades: int = 50
    min_profit_factor: float = 1.2
    max_drawdown_pct: float = 15.0
    require_net_profit: bool = True    # Ergebnis nach Gebühren im Plus


@dataclass
class LiveConfig:
    """Harte Grenzen für den Echtgeld-Betrieb."""
    max_capital: float = 200.0         # Höchstbetrag in EUR, den der Bot überhaupt nutzen darf
    currency: str = "EUR"
    risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 3.0
    max_total_loss_pct: float = 15.0   # Gesamt-Notbremse: danach automatisch zurück auf Spielgeld
    max_open_positions: int = 1
    symbols: List[str] = field(default_factory=lambda: ["BTC/EUR"])
    long_only: bool = True
    leverage: float = 1.0
    withdrawals_allowed: bool = False  # Börsen-Schlüssel darf nur handeln


@dataclass
class Config:
    symbols: List[SymbolConfig] = field(default_factory=lambda: list(DEFAULT_SYMBOLS))
    interval_min: int = 15
    poll_seconds: int = 60
    data_source: str = "kraken"   # "kraken" (mit Yahoo-Fallback), "yahoo" oder "synthetic"
    state_file: str = "data/state.json"
    trades_file: str = "data/trades.csv"
    log_file: str = "data/agent.log"
    cockpit_file: str = "data/cockpit.json"
    control_file: str = "control.json"
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    ai: AIConfig = field(default_factory=AIConfig)
    gate: GateConfig = field(default_factory=GateConfig)
    live: LiveConfig = field(default_factory=LiveConfig)

    def symbol(self, name: str) -> SymbolConfig:
        for s in self.symbols:
            if s.name == name:
                return s
        raise KeyError(name)

    def to_dict(self) -> Dict:
        return asdict(self)


def load_config(path: str = "config.json") -> Config:
    cfg = Config()
    if not os.path.exists(path):
        return cfg
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    for key in ("interval_min", "poll_seconds", "data_source", "state_file", "trades_file", "log_file",
                "cockpit_file", "control_file"):
        if key in raw:
            setattr(cfg, key, raw[key])
    for section, cls in (("strategy", StrategyConfig), ("risk", RiskConfig), ("ai", AIConfig),
                         ("gate", GateConfig), ("live", LiveConfig)):
        if section in raw:
            current = asdict(getattr(cfg, section))
            current.update(raw[section])
            setattr(cfg, section, cls(**current))
    if "symbols" in raw:
        cfg.symbols = [SymbolConfig(**s) for s in raw["symbols"]]
    return cfg
