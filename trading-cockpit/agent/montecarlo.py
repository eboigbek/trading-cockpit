"""Time Machine: spielt vor jedem Trade die nächsten Stunden 10.000-mal durch.

Verfahren (Bootstrap-Monte-Carlo):
  1. Aus den letzten ~500 echten 15-Minuten-Kerzen wird für jede Kerze die
     Bewegung relativ zum vorherigen Schlusskurs genommen: Schluss, Hoch, Tief.
  2. Der durchschnittliche Trend wird herausgerechnet (kein eingebauter
     Optimismus, nur die typische Schwankung bleibt).
  3. Für jeden der 10.000 Pfade werden zufällig echte Kerzen hintereinander-
     gesetzt, bis Stop-Loss, Gewinnziel oder die maximale Haltedauer erreicht ist.
     Berühren Stop und Ziel dieselbe Kerze, zählt konservativ der Stop.
  4. Ergebnis: Wahrscheinlichkeit für Ziel / Stop / Zeitablauf und der
     durchschnittliche Ertrag NACH Gebühren und Slippage – in Prozent und in
     „R“ (Vielfachen des riskierten Betrags).

Wichtig: Das ist keine Vorhersage. Es zeigt nur, wie der Plan bei der bisher
typischen Schwankung ausgeht. Überraschende Nachrichten bildet es nicht ab.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass, asdict
from typing import Dict, List

import numpy as np

from .data import Candle


@dataclass
class MCResult:
    paths: int
    p_tp: float
    p_sl: float
    p_timeout: float
    ev_pct: float        # durchschnittlicher Ertrag in % des Einstiegs, nach Kosten
    ev_r: float          # durchschnittlicher Ertrag in R (1 R = Verlust beim Stop)
    median_bars: float
    cost_pct: float      # angesetzte Kosten hin und zurück in %

    def as_dict(self) -> Dict:
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def simulate(candles: List[Candle], side: str, entry: float, stop: float, take_profit: float,
             fee_pct: float, slippage_pct: float, horizon: int, paths: int = 10_000,
             lookback: int = 500, seed: int = 0) -> MCResult:
    hist = candles[-(lookback + 1):]
    if len(hist) < 60:
        raise ValueError("zu wenig Kerzen für die Simulation")
    prev = np.array([c.close for c in hist[:-1]], dtype=float)
    close = np.array([c.close for c in hist[1:]], dtype=float) / prev
    high = np.array([c.high for c in hist[1:]], dtype=float) / prev
    low = np.array([c.low for c in hist[1:]], dtype=float) / prev
    # Trend herausrechnen: mittlere Log-Rendite auf 0 setzen
    drift = np.exp(np.mean(np.log(close)))
    close, high, low = close / drift, high / drift, low / drift
    high = np.maximum(high, np.maximum(close, 1.0))
    low = np.minimum(low, np.minimum(close, 1.0))

    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(close), size=(paths, horizon))
    path_close = entry * np.cumprod(close[idx], axis=1)
    start = np.concatenate([np.full((paths, 1), entry), path_close[:, :-1]], axis=1)
    path_high = start * high[idx]
    path_low = start * low[idx]

    if side == "long":
        hit_sl, hit_tp = path_low <= stop, path_high >= take_profit
    else:
        hit_sl, hit_tp = path_high >= stop, path_low <= take_profit
    never = horizon + 1
    first_sl = np.where(hit_sl.any(axis=1), hit_sl.argmax(axis=1), never)
    first_tp = np.where(hit_tp.any(axis=1), hit_tp.argmax(axis=1), never)

    is_sl = (first_sl <= first_tp) & (first_sl < never)
    is_tp = (first_tp < first_sl) & (first_tp < never)
    is_to = ~(is_sl | is_tp)
    exit_price = np.where(is_sl, stop, np.where(is_tp, take_profit, path_close[:, -1]))
    direction = 1.0 if side == "long" else -1.0
    gross = direction * (exit_price / entry - 1.0)
    cost = 2.0 * (fee_pct + slippage_pct) / 100.0
    net = gross - cost
    risk = abs(entry - stop) / entry
    bars = np.where(is_sl, first_sl, np.where(is_tp, first_tp, horizon - 1)) + 1

    return MCResult(
        paths=paths,
        p_tp=float(is_tp.mean()), p_sl=float(is_sl.mean()), p_timeout=float(is_to.mean()),
        ev_pct=float(net.mean() * 100), ev_r=float(net.mean() / risk) if risk > 0 else 0.0,
        median_bars=float(np.median(bars)), cost_pct=cost * 100,
    )


def seed_for(symbol: str, ts: int) -> int:
    """Reproduzierbar: gleiche Kerze + gleiches Symbol = gleiches Ergebnis."""
    return zlib.crc32(f"{symbol}-{ts}".encode())


def describe(r: Dict) -> str:
    return (f"Ziel {r['p_tp'] * 100:.0f} % · Stop {r['p_sl'] * 100:.0f} % · Zeitablauf {r['p_timeout'] * 100:.0f} % · "
            f"Ø {r['ev_r']:+.2f} R ({r['ev_pct']:+.3f} %) nach {r['cost_pct']:.2f} % Kosten")
