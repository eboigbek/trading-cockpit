"""Startstrategie: EMA-Crossover mit Trend- und RSI-Filter, ATR-basierte Stops.

Regeln (auf abgeschlossenen Kerzen):
  LONG,  wenn EMA9 die EMA21 von unten kreuzt, Kurs über EMA100 liegt und 50 < RSI < 70
  SHORT, wenn EMA9 die EMA21 von oben kreuzt, Kurs unter EMA100 liegt und 30 < RSI < 50
  Stop-Loss   = Einstieg -/+ 1.5 x ATR
  Take-Profit = Einstieg +/- 3.0 x ATR   (Chance/Risiko 1:2)
  Ausstieg zusätzlich bei Gegen-Crossover oder nach max_hold_bars Kerzen.

Bewusst einfach und transparent – zum Lernen und Testen, nicht als
Gewinnversprechen.
"""
from __future__ import annotations

from dataclasses import dataclass, field
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

    def as_dict(self) -> Dict[str, float]:
        return {k: round(v, 6) if isinstance(v, float) else v for k, v in self.__dict__.items()}


def min_bars(cfg: StrategyConfig) -> int:
    return max(cfg.ema_trend, cfg.ema_slow, cfg.rsi_period, cfg.atr_period) + 2


def snapshot(candles: List[Candle], cfg: StrategyConfig) -> Optional[Snapshot]:
    if len(candles) < min_bars(cfg):
        return None
    closes = [c.close for c in candles]
    f = ema(closes, cfg.ema_fast)
    s = ema(closes, cfg.ema_slow)
    t = ema(closes, cfg.ema_trend)
    r = rsi(closes, cfg.rsi_period)
    a = atr([c.high for c in candles], [c.low for c in candles], closes, cfg.atr_period)
    if None in (f[-1], f[-2], s[-1], s[-2], t[-1], r[-1], a[-1]):
        return None
    return Snapshot(
        close=closes[-1], ema_fast=f[-1], ema_slow=s[-1], ema_trend=t[-1],
        rsi=r[-1], atr=a[-1],
        cross_up=f[-2] <= s[-2] and f[-1] > s[-1],
        cross_down=f[-2] >= s[-2] and f[-1] < s[-1],
    )


def generate_signal(symbol: str, candles: List[Candle], cfg: StrategyConfig) -> Optional[Signal]:
    snap = snapshot(candles, cfg)
    if snap is None or snap.atr <= 0:
        return None
    p, a = snap.close, snap.atr
    if snap.cross_up and p > snap.ema_trend and cfg.rsi_long_min < snap.rsi < cfg.rsi_long_max:
        return Signal(symbol, "long", p, p - cfg.stop_atr * a, p + cfg.take_profit_atr * a,
                      f"EMA{cfg.ema_fast} kreuzt EMA{cfg.ema_slow} nach oben, Trend aufwärts, RSI {snap.rsi:.1f}",
                      snap.as_dict())
    if cfg.allow_short and snap.cross_down and p < snap.ema_trend \
            and cfg.rsi_short_min < snap.rsi < cfg.rsi_short_max:
        return Signal(symbol, "short", p, p + cfg.stop_atr * a, p - cfg.take_profit_atr * a,
                      f"EMA{cfg.ema_fast} kreuzt EMA{cfg.ema_slow} nach unten, Trend abwärts, RSI {snap.rsi:.1f}",
                      snap.as_dict())
    return None


def opposite_cross(side: str, candles: List[Candle], cfg: StrategyConfig) -> bool:
    """True, wenn die letzte Kerze einen Crossover gegen die offene Position zeigt."""
    snap = snapshot(candles, cfg)
    if snap is None:
        return False
    return snap.cross_down if side == "long" else snap.cross_up
