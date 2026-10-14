"""Marktdaten: öffentliche Kerzen von Kraken (ohne API-Key), Yahoo als Fallback,
sowie synthetische Kurse für Offline-Tests.

Es werden nur ABGESCHLOSSENE Kerzen zurückgegeben – die laufende Kerze wird
verworfen, damit Signale nicht "nachmalen".
"""
from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests

from .config import SymbolConfig

log = logging.getLogger("agent.data")

HEADERS = {"User-Agent": "Mozilla/5.0 (paper-trading-agent)"}


@dataclass
class Candle:
    ts: int        # Unix-Zeit (Sekunden) des Kerzenbeginns
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class DataError(RuntimeError):
    pass


def fetch_kraken(sym: SymbolConfig, interval_min: int) -> List[Candle]:
    url = "https://api.kraken.com/0/public/OHLC"
    r = requests.get(url, params={"pair": sym.kraken, "interval": interval_min},
                     headers=HEADERS, timeout=15)
    r.raise_for_status()
    payload = r.json()
    if payload.get("error"):
        raise DataError(f"Kraken {sym.kraken}: {payload['error']}")
    result = payload["result"]
    key = next(k for k in result if k != "last")
    rows = result[key]
    candles = [Candle(int(row[0]), float(row[1]), float(row[2]), float(row[3]),
                      float(row[4]), float(row[6])) for row in rows]
    return candles[:-1]  # letzte Kerze läuft noch


def fetch_yahoo(sym: SymbolConfig, interval_min: int) -> List[Candle]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym.yahoo}"
    rng = "5d" if interval_min <= 15 else "1mo"
    r = requests.get(url, params={"interval": f"{interval_min}m", "range": rng},
                     headers=HEADERS, timeout=15)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    candles = []
    for i, ts in enumerate(res.get("timestamp", [])):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        candles.append(Candle(int(ts), float(o), float(h), float(l), float(c),
                              float(q.get("volume", [0] * (i + 1))[i] or 0)))
    return candles[:-1]


def fetch_candles(sym: SymbolConfig, interval_min: int, source: str = "kraken") -> List[Candle]:
    """Holt Kerzen mit automatischem Fallback Kraken -> Yahoo."""
    order = {"kraken": [fetch_kraken, fetch_yahoo], "yahoo": [fetch_yahoo, fetch_kraken]}[source]
    last_err: Optional[Exception] = None
    for fn in order:
        try:
            candles = fn(sym, interval_min)
            if len(candles) >= 50:
                return candles
            last_err = DataError(f"{fn.__name__}: nur {len(candles)} Kerzen für {sym.name}")
        except Exception as e:  # Netzwerk, Format, Rate-Limit ...
            last_err = e
            log.warning("Datenquelle %s für %s fehlgeschlagen: %s", fn.__name__, sym.name, e)
    raise DataError(f"Keine Daten für {sym.name}: {last_err}")


# --------------------------------------------------------------------------
# Synthetische Daten (für Tests, Backtests ohne Internet und den Demo-Modus)
# --------------------------------------------------------------------------

START_PRICES = {"BTC/USD": 65_000.0, "EUR/USD": 1.09, "GBP/USD": 1.27, "USD/JPY": 148.0}
VOLS = {"BTC/USD": 0.0045, "EUR/USD": 0.0006, "GBP/USD": 0.0008, "USD/JPY": 0.0008}


def synthetic_series(name: str, n: int, interval_min: int = 15, seed: int = 42,
                     start_ts: int = 1_760_000_000) -> List[Candle]:
    """Geometrische Brownsche Bewegung mit wechselnden Trendphasen.
    Nur zum Testen der Mechanik – sagt NICHTS über echte Profitabilität aus."""
    rng = random.Random(f"{name}-{seed}")
    price = START_PRICES.get(name, 100.0)
    vol = VOLS.get(name, 0.002)
    drift, regime_left = 0.0, 0
    candles = []
    for i in range(n):
        if regime_left <= 0:
            drift = rng.choice([-1, 0, 0, 1]) * vol * rng.uniform(0.05, 0.25)
            regime_left = rng.randint(40, 200)
        regime_left -= 1
        o = price
        steps = [o]
        for _ in range(4):
            steps.append(steps[-1] * math.exp(drift / 4 + vol / 2 * rng.gauss(0, 1)))
        c = steps[-1]
        h = max(steps) * (1 + abs(rng.gauss(0, vol / 4)))
        l = min(steps) * (1 - abs(rng.gauss(0, vol / 4)))
        candles.append(Candle(start_ts + i * interval_min * 60, o, h, l, c, rng.uniform(1, 100)))
        price = c
    return candles


class SyntheticFeed:
    """Simulierter Live-Feed: jeder Aufruf liefert eine neue abgeschlossene Kerze."""

    def __init__(self, names: List[str], interval_min: int, history: int = 300,
                 total: int = 5000, seed: int = 7):
        self.series: Dict[str, List[Candle]] = {
            n: synthetic_series(n, total, interval_min, seed) for n in names}
        self.pos = history

    def fetch(self, sym: SymbolConfig, interval_min: int) -> List[Candle]:
        return self.series[sym.name][: self.pos]

    def advance(self) -> None:
        self.pos += 1


def load_csv(path: str) -> List[Candle]:
    """CSV mit Spalten ts,open,high,low,close[,volume] laden (z.B. eigene Exporte)."""
    import csv
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out.append(Candle(int(float(row["ts"])), float(row["open"]), float(row["high"]),
                              float(row["low"]), float(row["close"]), float(row.get("volume") or 0)))
    return out
