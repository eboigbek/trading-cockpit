# Trading-Cockpit: Paper-Trading-Bot für BTC und Devisen

**Cockpit:** https://eboigbek.github.io/trading-cockpit/

Der Bot läuft automatisch alle 15 Minuten über GitHub Actions, auch wenn kein Computer an ist. Er handelt mit Spielgeld (10.000 USD), berücksichtigt Gebühren und Spreads und schreibt nach jedem Lauf seine Daten nach `data/`. Das Cockpit zeigt Kontostand, Märkte, Positionen, Gebühren, die Echtgeld-Freischaltung und das Protokoll.

## Bedienung über GitHub

- **Not-Aus / Steuerung:** Reiter *Actions* → *Steuerung* → *Run workflow* → Aktion wählen. Geht auch in der GitHub-App am Handy.
- **Claude-Prüfung einschalten:** *Settings* → *Secrets and variables* → *Actions* → *New repository secret*, Name `ANTHROPIC_API_KEY`, Wert = API-Key von console.anthropic.com. Wird separat abgerechnet, nicht über das Claude-Abo.
- **Bot-Läufe ansehen:** Reiter *Actions* → *Trading-Bot*.

## Tresor-Modus (Verschlüsselung)

Ist bei GitHub das Secret `COCKPIT_PASSWORT` hinterlegt (*Settings* → *Secrets and variables* → *Actions*), speichert der Bot Kontostand, Trades und Cockpit-Daten nur noch verschlüsselt (`data/*.enc`, AES-256-GCM, Schlüssel per PBKDF2-SHA256 aus dem Passwort). In den öffentlichen GitHub-Logs stehen dann keine Beträge mehr. Das Cockpit fragt einmal pro Gerät nach dem Passwort und entschlüsselt die Daten direkt im Browser. Ohne Passwort oder mit falschem Passwort bricht der Bot ab, statt Daten zu überschreiben. **Passwort vergessen = Daten nicht wiederherstellbar** (dann über *Steuerung* das Konto zurücksetzen).

## Echtgeld-Freischaltung

Der Echtgeld-Modus wird erst frei, wenn der Spielgeld-Lauf ALLE Bedingungen erfüllt: mindestens 42 Tage (6 Wochen), mindestens 50 Trades, Profit-Faktor nach Gebühren mindestens 1,2, größter Rückgang höchstens 15 %, Ergebnis nach Gebühren im Plus. Grenzen im Echtgeld-Betrieb: höchstens 200 €, 1 % Risiko pro Trade, 3 % Tagesverlust-Limit, Notbremse bei 15 % Gesamtverlust (automatisch zurück auf Spielgeld), 1 Position, nur BTC/EUR, nur Kauf, kein Hebel, Börsen-Schlüssel ohne Auszahlungsrecht. Die Börsenanbindung wird eingerichtet, sobald ein Börsenkonto existiert. Vor Echtgeld wird dieses Projekt auf privat gestellt.

Alle Werte stehen in `agent/config.py` (Abschnitte `GateConfig` und `LiveConfig`).

---

## Lokal ausführen (optional)

Ein Daytrading-Agent, der BTC/USD, EUR/USD, GBP/USD und USD/JPY rund um die Uhr auf 15-Minuten-Kerzen beobachtet, nach festen Regeln Trades eröffnet und schließt und jedes Signal vor der Ausführung von Claude gegenprüfen lässt. **Er handelt ausschließlich mit Spielgeld (Paper-Trading).** Es wird kein Konto benötigt, keine echte Order gesendet und kein echtes Geld bewegt.

> Kein Finanzrat. Die eingebaute Strategie ist ein transparenter Lern- und Teststand, kein Gewinnversprechen. Die allermeisten Daytrader verlieren Geld, vor allem wegen Gebühren und Spreads.

## So funktioniert der Agent

Alle 60 Sekunden holt der Agent öffentliche Kursdaten von Kraken (ohne API-Key; Yahoo Finance als Ausweichquelle). Sobald eine 15-Minuten-Kerze abgeschlossen ist, passiert für jedes Symbol Folgendes:

1. **Offene Position prüfen:** Wurde Stop-Loss oder Take-Profit in der Kerze berührt? Gibt es ein Gegensignal? Ist die maximale Haltedauer (24 h) erreicht? Dann wird geschlossen.
2. **Signal suchen** (nur wenn keine Position offen ist):
   - LONG: EMA 9 kreuzt EMA 21 nach oben, Kurs über EMA 100, RSI zwischen 50 und 70
   - SHORT: EMA 9 kreuzt EMA 21 nach unten, Kurs unter EMA 100, RSI zwischen 30 und 50
   - Stop-Loss 1,5 × ATR, Take-Profit 3 × ATR (Chance/Risiko 1:2)
3. **Risiko prüfen:** Positionsgröße so, dass ein Stop-Loss maximal 1 % des Kontos kostet; höchstens 3 Positionen gleichzeitig; Hebel-Limit (BTC 1×, Devisen 10×); nach 3 % Tagesverlust Pause bis 00:00 UTC.
4. **Claude fragen** (optional): Claude sieht das Signal, die letzten 40 Kerzen und die offenen Positionen und antwortet mit Genehmigen/Ablehnen plus Begründung. Claude kann Trades nur verhindern, nie selbst erfinden oder vergrößern.
5. **Ausführen und protokollieren:** Simulierte Order inklusive Gebühren und Slippage, Zustand wird gespeichert, jeder Trade landet in `data/trades.csv`.

Wenn du den Agent beendest und neu startest, macht er dort weiter, wo er aufgehört hat.

## Einrichtung (ca. 10 Minuten, am Computer)

Du brauchst Python 3.9 oder neuer ([python.org/downloads](https://www.python.org/downloads/); unter Windows bei der Installation „Add Python to PATH“ anhaken).

```bash
# 1. In den entpackten Ordner wechseln
cd trading_agent

# 2. Einzige Abhängigkeit installieren
pip install -r requirements.txt

# 3. Selbsttest (sollte "OK" ausgeben)
python -m unittest discover tests

# 4. Backtest auf den letzten ~7 Tagen echter Kurse
python run.py backtest
#    -> Bericht öffnen: data/backtest_report.html

# 5. Agent starten (läuft, bis du Strg+C drückst)
python run.py live
```

Unter macOS/Linux ggf. `python3` und `pip3` statt `python` und `pip` verwenden.

### Claude als Prüfer aktivieren

Ohne Schlüssel läuft der Agent rein regelbasiert. Für die Claude-Prüfung:

1. Unter [console.anthropic.com](https://console.anthropic.com) einen API-Key erstellen und etwas Guthaben aufladen. Pro geprüftem Signal fällt nur eine kleine Gebühr an (ein Aufruf mit rund 1.500 Tokens), und Signale kommen nur ein paar Mal am Tag.
2. Den Schlüssel als Umgebungsvariable setzen, bevor du den Agent startest:

```bash
# macOS / Linux
export ANTHROPIC_API_KEY="sk-ant-..."
# Windows (PowerShell)
$env:ANTHROPIC_API_KEY="sk-ant-..."
```

3. Optional ein anderes Modell wählen: `CLAUDE_MODEL` setzen (Standard: `claude-sonnet-4-5`). Die aktuellen Modellnamen stehen unter [docs.claude.com/en/docs/about-claude/models](https://docs.claude.com/en/docs/about-claude/models).

Beim Start zeigt das Log „Claude-Prüfung AKTIV“. Jede Entscheidung samt Begründung steht im Log und in der Trade-Liste.

## Befehle

| Befehl | Was er tut |
|---|---|
| `python run.py live` | Paper-Trading mit Live-Kursen, läuft dauerhaft |
| `python run.py live --once` | Ein einzelner Durchlauf (für Aufgabenplanung/Cron) |
| `python run.py live --no-ai` | Ohne Claude-Prüfung |
| `python run.py status` | Kontostand, offene Positionen, letzte Trades |
| `python run.py backtest` | Backtest auf echten Kursen der letzten Tage |
| `python run.py backtest --ai` | Backtest mit Claude-Prüfung (verbraucht API-Guthaben) |
| `python run.py backtest --synthetic` | Offline-Backtest auf simulierten Kursen |
| `python run.py demo` | Schnelldemo mit simulierten Kursen, ohne Internet |
| `python run.py reset` | Paper-Konto auf Startkapital zurücksetzen |

## Einstellungen anpassen

`config.example.json` nach `config.json` kopieren und Werte ändern, z.B. Startkapital, Risiko pro Trade, Indikator-Perioden, Symbole oder Gebühren. Nicht angegebene Werte behalten ihren Standard.

Die Gebühren (`fee_pct`, pro Seite inklusive halbem Spread) sind Schätzwerte. Trage die echten Kosten des Brokers ein, den du später nutzen würdest, sonst sind die Ergebnisse zu optimistisch.

## Den Agent dauerhaft laufen lassen

Der Agent handelt nur, solange das Programm läuft. Möglichkeiten:

- **Eigener PC/Laptop:** Einfach `python run.py live` offen lassen (Energiesparmodus aus).
- **Kleiner Cloud-Server oder Raspberry Pi:** Zuverlässiger für 24/7. Zum Beispiel mit `nohup python3 run.py live &` oder als systemd-Dienst starten.
- **Aufgabenplanung:** `python run.py live --once` alle 15 Minuten per Windows-Aufgabenplanung oder Cron. Der Zustand wird zwischen den Läufen gespeichert.

## Dateien

```
run.py                 Befehlszeile
agent/config.py        Alle Einstellungen und Standardwerte
agent/data.py          Kursdaten (Kraken, Yahoo, simuliert)
agent/indicators.py    EMA, RSI, ATR
agent/strategy.py      Handelsregeln
agent/risk.py          Positionsgröße und Limits
agent/broker.py        Paper-Konto (Gebühren, Stops, Speicherung)
agent/ai_reviewer.py   Claude-Signalprüfung
agent/engine.py        Ablauf pro Kerze (gemeinsam für Live und Backtest)
agent/live.py          Dauerschleife
agent/backtest.py      Backtest und HTML-Bericht
tests/                 Automatische Tests
data/                  Zustand, Trades, Logs (wird automatisch angelegt)
```

## Ehrliche Einordnung

Im Offline-Test mit zufälligen Kursen landete die Strategie bei vier verschiedenen Zufallsreihen zwischen −55 % und +2 %, meist knapp unter null, und die Gebühren fraßen jeweils 25–40 % des Startkapitals (`--seed` ändert die Reihe). Das ist bei Zufallsdaten zu erwarten: Ohne echten Vorteil bleibt nur der Kostenblock plus Glück oder Pech. Der Test zeigt also, dass die Mechanik korrekt rechnet, und wie stark Kosten beim Daytrading ins Gewicht fallen. Ob die Regeln an echten Märkten einen Vorteil haben, zeigt erst ein längerer Paper-Lauf über Wochen mit vielen Trades. Ein paar Tage oder eine Handvoll Trades sagen fast nichts aus.

Echtes Geld ist bewusst nicht eingebaut. Falls du später darüber nachdenkst: Erst nach mehreren Wochen stabiler Paper-Ergebnisse, nur bei einem regulierten Broker, mit kleinen Beträgen, deren Verlust du verkraften kannst, und mit Beachtung der steuerlichen Pflichten (Krypto- und Devisengewinne sind in Deutschland steuerpflichtig).
