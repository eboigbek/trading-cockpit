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


# Seit 06.11.2026 nur noch EUR/USD und GBP/USD:
#  - BTC/USD raus: 0,8 % Gebühr je Seite (Kraken Pro, Taker) kosteten im Spielgeld-Lauf ~1,2 R pro
#    Trade – kein Daytrade kann das tragen. Über config.json wieder aufnehmbar.
#  - USD/JPY raus: Kraken-Kurse illiquide (22 von 24 Trades im Stop).
DEFAULT_SYMBOLS: List[SymbolConfig] = [
    SymbolConfig("EUR/USD", "EUR", "USD", "EURUSD", "EURUSD=X", fee_pct=0.006, max_leverage=10.0),
    SymbolConfig("GBP/USD", "GBP", "USD", "GBPUSD", "GBPUSD=X", fee_pct=0.008, max_leverage=10.0),
]


# Frühere Märkte (bis 01.11.2026) – nur noch für Tests und zum Wiederaufnehmen per config.json
LEGACY_SYMBOLS: List[SymbolConfig] = [
    SymbolConfig("BTC/USD", "BTC", "USD", "XBTUSD", "BTC-USD", fee_pct=0.80, max_leverage=1.0),
    *DEFAULT_SYMBOLS,
    SymbolConfig("USD/JPY", "USD", "JPY", "USDJPY", "JPY=X", fee_pct=0.008, max_leverage=10.0),
]


@dataclass
class StrategyConfig:
    # "ema_cross" (alte Startstrategie), "breakout" (Ausbruch über das N-Kerzen-Hoch/-Tief in
    # Trendrichtung) oder "pullback" (Rücksetzer im Trend, kurzer RSI überverkauft/-kauft)
    name: str = "breakout"
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
    breakout_bars: int = 20       # Ausbruch: Hoch/Tief der letzten N Kerzen (ohne die aktuelle)
    pullback_rsi_period: int = 3  # Rücksetzer: kurzer RSI
    pullback_long_max: float = 20.0   # Kauf im Aufwärtstrend, wenn RSI darunter fällt
    pullback_short_min: float = 80.0  # Verkauf im Abwärtstrend, wenn RSI darüber steigt
    session_start_utc: int = 0    # Einstiege nur zwischen diesen Stunden (UTC), 0–24 = immer
    session_end_utc: int = 24


@dataclass
class RiskConfig:
    starting_cash: float = 10_000.0     # Paper-Startkapital in Kontowährung
    account_currency: str = "USD"
    risk_per_trade_pct: float = 1.0     # Max. Verlust pro Trade in % des Kontos
    max_daily_loss_pct: float = 3.0     # Tagesverlust-Stopp: danach keine neuen Trades bis 00:00 UTC
    max_open_positions: int = 3
    slippage_pct: float = 0.005         # Zusätzliche Ausführungsabweichung pro Order (0.005 % ≈ 0,5 Pip EUR/USD)
    # Kosten-Filter: Gebühren + Slippage für Ein- und Ausstieg dürfen höchstens diesen Anteil des
    # riskierten Betrags (1 R) ausmachen. 0,25 = ein Viertel. Darüber wird das Signal ausgelassen.
    max_cost_r: float = 0.25
    # Kontobremse: fällt das Konto so weit unter seinen Höchststand, eröffnet der Bot nichts mehr,
    # bis das Konto zurückgesetzt wird (üblicher Standard bei Handelskonten: 10 %). 0 = aus.
    max_total_drawdown_pct: float = 10.0
    # Kommt ein Lauf später als so viele Minuten nach Kerzenschluss, wird nicht mehr eingestiegen:
    # der Schlusskurs der Kerze wäre am echten Markt dann nicht mehr zu bekommen.
    max_signal_age_min: int = 20
    # EUR/USD und GBP/USD laufen meist gleich. Höchstens so viele Positionen in dieselbe
    # Dollar-Richtung gleichzeitig (Klumpenrisiko). 0 = aus.
    max_same_direction: int = 1


@dataclass
class HoursConfig:
    """Handelszeiten für Devisen (siehe agent/session.py). Stunden in UTC."""
    enabled: bool = True
    close_fri_utc: float = 22.0            # Marktschluss am Freitag
    open_sun_utc: float = 22.0             # Öffnung am Sonntag
    no_entry_before_close_h: float = 3.0   # so lange vor Freitagsschluss kein neuer Einstieg
    flat_before_weekend: bool = True       # offene Positionen vor dem Wochenende schließen


@dataclass
class NewsConfig:
    """Sperrzeiten um Termine aus kalender.json (Zinsentscheide, Arbeitsmarkt, Inflation)."""
    enabled: bool = True
    file: str = "kalender.json"
    before_min: int = 30
    after_min: int = 60


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
class TimeMachineConfig:
    """Monte-Carlo-Prüfung vor jedem Trade (siehe agent/montecarlo.py)."""
    enabled: bool = True
    paths: int = 10_000
    lookback_bars: int = 500
    # Die Simulation unterstellt bewusst KEINEN Vorteil (Trend herausgerechnet). Ohne Kosten
    # läge der Erwartungswert also bei ~0 R. Die Schwelle prüft daher, ob Kosten und
    # unrealistische Ziele zu viel vom Risiko auffressen: Kosten dürfen höchstens ein Viertel
    # des riskierten Betrags verschlingen (schlechter als -0,25 R -> auslassen).
    min_ev_r: float = -0.25


@dataclass
class DataQualityConfig:
    """Wächter gegen unzuverlässige Kursdaten (z.B. illiquide Märkte)."""
    window_bars: int = 96
    max_unchanged_share: float = 0.25   # mehr als 25 % Kerzen ohne Kursänderung = verdächtig


@dataclass
class GateConfig:
    """Bedingungen, die der Spielgeld-Lauf erfüllen muss, bevor Echtgeld freigeschaltet wird."""
    min_days: int = 42                 # 6 Wochen
    # 200 Trades: erst ab dieser Größenordnung lässt sich ein Vorteil von ~0,2 R pro Trade
    # statistisch von Glück unterscheiden (bei 50 Trades kann PF 1,2 reiner Zufall sein).
    min_trades: int = 200
    min_profit_factor: float = 1.2
    max_drawdown_pct: float = 15.0
    require_net_profit: bool = True    # Ergebnis nach Gebühren im Plus
    min_t_stat: float = 2.0            # Zufallstest: Ø-Ergebnis / Standardfehler (≈ 95 % Sicherheit)


@dataclass
class LiveConfig:
    """Harte Grenzen für den Echtgeld-Betrieb."""
    max_capital: float = 200.0         # Höchstbetrag in EUR, den der Bot überhaupt nutzen darf
    currency: str = "EUR"
    risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 3.0
    max_total_loss_pct: float = 15.0   # Gesamt-Notbremse: danach automatisch zurück auf Spielgeld
    max_open_positions: int = 1
    symbols: List[str] = field(default_factory=lambda: ["EUR/USD", "GBP/USD"])
    long_only: bool = False
    # Devisen-Stops liegen oft nur 0,1–0,3 % entfernt; 1 % Risiko geht dann nur mit Hebel.
    leverage: float = 10.0
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
    timemachine: TimeMachineConfig = field(default_factory=TimeMachineConfig)
    quality: DataQualityConfig = field(default_factory=DataQualityConfig)
    hours: HoursConfig = field(default_factory=HoursConfig)
    news: NewsConfig = field(default_factory=NewsConfig)
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
                         ("gate", GateConfig), ("live", LiveConfig),
                         ("timemachine", TimeMachineConfig), ("quality", DataQualityConfig),
                         ("hours", HoursConfig), ("news", NewsConfig)):
        if section in raw:
            current = asdict(getattr(cfg, section))
            current.update(raw[section])
            setattr(cfg, section, cls(**current))
    if "symbols" in raw:
        cfg.symbols = [SymbolConfig(**s) for s in raw["symbols"]]
    return cfg
