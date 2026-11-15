"""Handelszeiten und Sperrzeiten.

Zwei Schutzregeln, wie sie bei Devisen üblich sind:

1. Handelszeiten: Der Devisenmarkt ist von Freitag 22:00 bis Sonntag 22:00 UTC geschlossen.
   Manche Kursquellen (z.B. Kraken) liefern trotzdem dünne Wochenend-Kurse. Dort wird nicht
   eingestiegen, und offene Positionen werden vor dem Wochenende geschlossen (Kurslücken am
   Montag kann kein Stop abfangen). Gilt nur für Kerzen unter einem Tag; bei Tageskerzen
   werden lediglich Samstags- und Sonntagskerzen als Einstieg übersprungen.

2. Sperrzeiten um Termine: Rund um angekündigte Zahlen und Zinsentscheide (kalender.json)
   springen Kurse und Spreads. Von `before_min` davor bis `after_min` danach kein Einstieg.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from .config import HoursConfig


@dataclass
class Event:
    ts: int                 # Unix-Zeit (UTC) des Termins
    name: str
    symbols: List[str]      # leer = gilt für alle Märkte


def _wd_hour(ts: int):
    d = datetime.fromtimestamp(ts, tz=timezone.utc)
    return d.weekday(), d.hour + d.minute / 60.0     # Montag = 0 ... Sonntag = 6


def fx_open(ts: int, h: HoursConfig) -> bool:
    wd, hour = _wd_hour(ts)
    if wd == 5:
        return False
    if wd == 4:
        return hour < h.close_fri_utc
    if wd == 6:
        return hour >= h.open_sun_utc
    return True


def entry_time_ok(bar_ts: int, interval_min: int, h: HoursConfig) -> bool:
    """Darf am Schluss dieser Kerze eingestiegen werden?"""
    if not h.enabled:
        return True
    if interval_min >= 1440:                       # Tageskerzen: keine Wochenend-Kerzen (Tagesmitte zählt)
        return datetime.fromtimestamp(bar_ts + interval_min * 30, tz=timezone.utc).weekday() < 5
    close_ts = bar_ts + interval_min * 60
    # offen, und bis Freitagsschluss bleibt noch genug Zeit
    return fx_open(close_ts, h) and fx_open(close_ts + int(h.no_entry_before_close_h * 3600), h)


def must_flatten(bar_ts: int, interval_min: int, h: HoursConfig) -> bool:
    """Offene Position jetzt schließen, weil das Wochenende beginnt?"""
    if not (h.enabled and h.flat_before_weekend) or interval_min >= 1440:
        return False
    close_ts = bar_ts + interval_min * 60
    return not fx_open(close_ts + interval_min * 60, h)


def to_ts(local: str, tz: str) -> int:
    """'2026-12-09 14:00' in der genannten Zeitzone -> Unix-Zeit."""
    d = datetime.strptime(local, "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(tz))
    return int(d.timestamp())


def load_calendar(path: str) -> List[Event]:
    """Liest kalender.json. Fehlt die Datei oder ist sie kaputt: keine Termine (kein Abbruch)."""
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return sorted((Event(to_ts(e["zeit"], e.get("tz", "UTC")), e["name"], list(e.get("maerkte", [])))
                       for e in raw.get("termine", [])), key=lambda e: e.ts)
    except (ValueError, KeyError, TypeError):
        return []


def blackout(ts: int, symbol: str, events: List[Event], before_min: int, after_min: int) -> Optional[Event]:
    """Liegt `ts` in der Sperrzeit eines Termins, der diesen Markt betrifft?"""
    for e in events:
        if e.symbols and symbol not in e.symbols:
            continue
        if e.ts - before_min * 60 <= ts <= e.ts + after_min * 60:
            return e
    return None


def next_event(ts: int, events: List[Event]) -> Optional[Event]:
    return next((e for e in events if e.ts >= ts), None)
