"""Steuerdatei control.json – wird über den GitHub-Knopf „Steuerung“ geändert.

  {"mode": "paper" | "live", "stop": false}

stop = true  -> Not-Aus: offene Positionen werden geschlossen, keine neuen Trades.
mode = live  -> Echtgeld angefordert. Wird nur wirksam, wenn die Freischalt-
                Bedingungen erfüllt sind UND eine Börsenanbindung eingerichtet ist.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass
class Control:
    mode: str = "paper"
    stop: bool = False


def load_control(path: str) -> Control:
    if not os.path.exists(path):
        return Control()
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        # Kaputte Datei: sicherer Zustand
        return Control(mode="paper", stop=True)
    mode = raw.get("mode", "paper")
    return Control(mode=mode if mode in ("paper", "live") else "paper", stop=bool(raw.get("stop", False)))


def save_control(path: str, ctl: Control) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"mode": ctl.mode, "stop": ctl.stop}, f, indent=2)
        f.write("\n")
