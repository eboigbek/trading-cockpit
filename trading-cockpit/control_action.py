"""Wird vom GitHub-Workflow „Steuerung“ aufgerufen und ändert control.json."""
import os
import sys

from agent.config import load_config
from agent import vault
from agent.control import load_control, save_control

action = sys.argv[1] if len(sys.argv) > 1 else ""
cfg = load_config()
ctl = load_control(cfg.control_file)

if action.startswith("Not-Aus"):
    ctl.stop = True
elif action.startswith("Weiter"):
    ctl.stop = False
elif action.startswith("Echtgeld"):
    ctl.mode = "live"
elif action.startswith("Zurück"):
    ctl.mode = "paper"
elif action.startswith("Spielgeld-Konto zurücksetzen"):
    for p in (cfg.state_file, cfg.trades_file, cfg.cockpit_file):
        vault.remove(p)
    ctl.mode, ctl.stop = "paper", False
else:
    sys.exit(f"Unbekannte Aktion: {action!r}")

save_control(cfg.control_file, ctl)
print("Aktion ausgeführt." if vault.active() else f"Aktion ausgeführt: {action} -> mode={ctl.mode}, stop={ctl.stop}")
