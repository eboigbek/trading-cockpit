#!/usr/bin/env bash
# Speichert trading-cockpit/data als einzelnen Commit im Zweig "data" (wird jedes Mal ersetzt).
# So wächst das Projekt nicht mit jedem Bot-Lauf, und der Code-Zweig "main" bleibt sauber.
# Aufruf aus dem Projekt-Hauptordner: bash trading-cockpit/save_data.sh "Nachricht"
set -euo pipefail
msg="${1:-Bot-Lauf}"
if [ ! -d trading-cockpit/data ]; then echo "Keine Daten zum Speichern"; exit 0; fi
git config user.name "trading-bot"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
export GIT_INDEX_FILE="$(mktemp -u)"
git add trading-cockpit/data
tree="$(git write-tree)"
old="$(git rev-parse -q --verify 'refs/remotes/origin/data^{tree}' 2>/dev/null || true)"
if [ "$tree" = "$old" ]; then echo "Keine Änderungen"; exit 0; fi
commit="$(echo "$msg $(date -u +'%Y-%m-%d %H:%M') UTC" | git commit-tree "$tree")"
git push -q -f origin "$commit:refs/heads/data"
echo "Daten gespeichert"
