"""Strategien (auf abgeschlossenen Kerzen), Auswahl über StrategyConfig.name:

ema_cross (alte Startstrategie, im Spielgeld-Lauf bis 01.11.2026 ohne Vorteil):
  LONG,  wenn EMA9 die EMA21 von unten kreuzt, Kurs über EMA100 liegt und 50 < RSI < 70
  SHORT, wenn EMA9 die EMA21 von oben kreuzt, Kurs unter EMA100 liegt und 30 < RSI < 50
  Ausstieg zusätzlich bei Gegen-Crossover.

breakout (Trendfolge):
  LONG,  wenn der Schlusskurs über dem Hoch der letzten N Kerzen schließt und über EMA100 liegt
  SHORT, wenn er unter dem Tief der letzten N Kerzen schließt und unter EMA100 liegt

pullback (Rücksetzer im Trend):
  LONG,  wenn Kurs über EMA100 und der kurze RSI unter pullback_long_max fällt
  SHORT, wenn Kurs unter EMA100 und der kurze RSI über pullback_short_min steigt

Für alle: Stop = stop_atr x ATR, Ziel = take_profit_atr x ATR, Ausstieg spätestens nach
max_hold_bars Kerzen, Einstiege nur im Zeitfenster session_start_utc–session_end_utc.

Bewusst einfach und transparent – zum Testen, nicht als Gewinnversprechen.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from .config import StrategyConfig
from .data import Candle
from .indicators import atr, ema, rsi


@dataclass
class Signal:
    symbol: str
    side: str            # "long" oder "short"
    price: float
    stop: float
    take_profit: float
    reason: str
    indicators: Dict[str, float] = field(default_factory=dict)


@dataclass
class Snapshot:
    """Indikatorwerte der letzten abgeschlossenen Kerze."""
    close: float
    ema_fast: float
    ema_slow: float
    ema_trend: float
    rsi: float
    atr: float
    cross_up: bool
    cross_down: bool
    dc_high: float = 0.0     # Hoch der letzten N Kerzen vor der aktuellen
    dc_low: float = 0.0
    rsi_fast: float = 50.0
    hour_utc: int = 0

    def as_dict(self) -> Dict[str, float]:
        return {k: round(v, 6) if isinstance(v, float) else v for k, v in self.__dict__.items()}


def min_bars(cfg: StrategyConfig) -> int:
    return max(cfg.ema_trend, cfg.ema_slow, cfg.rsi_period, cfg.atr_period, cfg.breakout_bars,
               cfg.pullback_rsi_period) + 2


def snapshot(candles: List[Candle], cfg: StrategyConfig) -> Optional[Snapshot]:
    if len(candles) < min_bars(cfg):
        return None
    closes = [c.close for c in candles]
    f = ema(closes, cfg.ema_fast)
    s = ema(closes, cfg.ema_slow)
    t = ema(closes, cfg.ema_trend)
    r = rsi(closes, cfg.rsi_period)
    a = atr([c.high for c in candles], [c.low for c in candles], closes, cfg.atr_period)
    rf = rsi(closes, cfg.pullback_rsi_period)
    if None in (f[-1], f[-2], s[-1], s[-2], t[-1], r[-1], a[-1], rf[-1]):
        return None
    prior = candles[-cfg.breakout_bars - 1:-1]
    return Snapshot(
        close=closes[-1], ema_fast=f[-1], ema_slow=s[-1], ema_trend=t[-1],
        rsi=r[-1], atr=a[-1],
        cross_up=f[-2] <= s[-2] and f[-1] > s[-1],
        cross_down=f[-2] >= s[-2] and f[-1] < s[-1],
        dc_high=max(c.high for c in prior), dc_low=min(c.low for c in prior),
        rsi_fast=rf[-1],
        hour_utc=datetime.fromtimestamp(candles[-1].ts, tz=timezone.utc).hour,
    )


def in_session(hour: int, cfg: StrategyConfig) -> bool:
    a, b = cfg.session_start_utc, cfg.session_end_utc
    if a <= 0 and b >= 24:
        return True
    return a <= hour < b if a < b else (hour >= a or hour < b)


def _entry(cfg: StrategyConfig, snap: Snapshot) -> Optional[tuple]:
    """(Seite, Begründung) oder None – je nach gewählter Strategie."""
    p = snap.close
    up, down = p > snap.ema_trend, p < snap.ema_trend
    if cfg.name == "ema_cross":
        if snap.cross_up and up and cfg.rsi_long_min < snap.rsi < cfg.rsi_long_max:
            return "long", f"EMA{cfg.ema_fast} kreuzt EMA{cfg.ema_slow} nach oben, Trend aufwärts, RSI {snap.rsi:.1f}"
        if snap.cross_down and down and cfg.rsi_short_min < snap.rsi < cfg.rsi_short_max:
            return "short", f"EMA{cfg.ema_fast} kreuzt EMA{cfg.ema_slow} nach unten, Trend abwärts, RSI {snap.rsi:.1f}"
    elif cfg.name == "breakout":
        if up and p > snap.dc_high:
            return "long", f"Ausbruch über das {cfg.breakout_bars}-Kerzen-Hoch, Trend aufwärts (über EMA{cfg.ema_trend})"
        if down and p < snap.dc_low:
            return "short", f"Ausbruch unter das {cfg.breakout_bars}-Kerzen-Tief, Trend abwärts (unter EMA{cfg.ema_trend})"
    elif cfg.name == "pullback":
        if up and snap.rsi_fast < cfg.pullback_long_max:
            return "long", f"Rücksetzer im Aufwärtstrend, RSI{cfg.pullback_rsi_period} {snap.rsi_fast:.0f}"
        if down and snap.rsi_fast > cfg.pullback_short_min:
            return "short", f"Rücksetzer im Abwärtstrend, RSI{cfg.pullback_rsi_period} {snap.rsi_fast:.0f}"
    else:
        raise ValueError(f"Unbekannte Strategie: {cfg.name}")
    return None


def generate_signal(symbol: str, candles: List[Candle], cfg: StrategyConfig) -> Optional[Signal]:
    snap = snapshot(candles, cfg)
    if snap is None or snap.atr <= 0 or not in_session(snap.hour_utc, cfg):
        return None
    hit = _entry(cfg, snap)
    if not hit:
        return None
    side, reason = hit
    if side == "short" and not cfg.allow_short:
        return None
    p, a = snap.close, snap.atr
    sgn = 1 if side == "long" else -1
    return Signal(symbol, side, p, p - sgn * cfg.stop_atr * a, p + sgn * cfg.take_profit_atr * a,
                  reason, snap.as_dict())


def opposite_cross(side: str, candles: List[Candle], cfg: StrategyConfig) -> bool:
    """True, wenn die letzte Kerze einen Crossover gegen die offene Position zeigt
    (nur bei ema_cross; die anderen Strategien steigen über Stop, Ziel oder Zeit aus)."""
    if cfg.name != "ema_cross":
        return False
    snap = snapshot(candles, cfg)
    if snap is None:
        return False
    return snap.cross_down if side == "long" else snap.cross_up
