#!/usr/bin/env bash
# Holt den letzten Datenstand aus dem Zweig "data". Gibt es ihn noch nicht, startet ein neues Konto.
# Aufruf aus dem Projekt-Hauptordner: bash trading-cockpit/load_data.sh
set -euo pipefail
rm -rf trading-cockpit/data
if git fetch -q --depth=1 origin "+refs/heads/data:refs/remotes/origin/data" 2>/dev/null; then
  git checkout refs/remotes/origin/data -- trading-cockpit/data
  git reset -q -- trading-cockpit/data
  echo "Daten geladen"
else
  echo "Noch keine Daten – neues Spielgeld-Konto"
fi
