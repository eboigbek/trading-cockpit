#!/usr/bin/env bash
# Legt den Ordner trado-daten/ausgabe als einzigen Commit im Zweig "trado-daten" ab.
# Der Zweig wird jedes Mal ersetzt; der Verlauf steckt in verlauf.csv. Der Bot-Zweig "data" bleibt unberuehrt.
set -euo pipefail
cd trado-daten/ausgabe
if [ -z "$(ls -A . 2>/dev/null)" ]; then echo "Keine Ausgabe zum Speichern"; exit 0; fi
rm -rf .git
git init -q
git config user.name "trado-daten"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add -A
git commit -q -m "Daten $(date -u +'%Y-%m-%d %H:%M') UTC"
git push -q -f "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" HEAD:refs/heads/trado-daten
echo "Daten gespeichert im Zweig trado-daten"
