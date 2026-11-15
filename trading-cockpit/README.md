# Trading-Cockpit: Paper-Trading-Bot für Devisen (EUR/USD, GBP/USD)

**Cockpit:** https://eboigbek.github.io/trading-cockpit/

Der Bot läuft automatisch über GitHub Actions (Start alle 5 Minuten, Handel auf 1-Stunden-Kerzen), auch wenn kein Computer an ist. Er handelt mit Spielgeld (10.000 USD), berücksichtigt Gebühren und Spreads und schreibt nach jedem Lauf seine Daten nach `data/`. Das Cockpit zeigt Kontostand, Märkte, Positionen, Gebühren, die Echtgeld-Freischaltung und das Protokoll.

## Wo die Daten liegen

Der Code liegt im Zweig `main`. Kontostand, Trades und Cockpit-Daten liegen im Zweig `data`, der bei jedem Speichern durch einen einzigen neuen Commit ersetzt wird (`load_data.sh` / `save_data.sh`). So wächst das Projekt nicht mit jedem Bot-Lauf. Der Bot startet alle 5 Minuten; neue Daten entstehen nach jedem Kerzenschluss, dazwischen wird nur alle 15 Minuten ein Lebenszeichen geschrieben.

## Bedienung über GitHub

- **Not-Aus / Steuerung:** Reiter *Actions* → *Steuerung* → *Run workflow* → Aktion wählen. Geht auch in der GitHub-App am Handy.
- **Claude-Prüfung einschalten:** *Settings* → *Secrets and variables* → *Actions* → *New repository secret*, Name `ANTHROPIC_API_KEY`, Wert = API-Key von console.anthropic.com. Wird separat abgerechnet, nicht über das Claude-Abo.
- **Bot-Läufe ansehen:** Reiter *Actions* → *Trading-Bot*.

## Strategie (seit 06.11.2026)

Die alte EMA-Crossover-Strategie auf 15-Minuten-Kerzen hatte im Spielgeld-Lauf keinen Vorteil (17,8 Tage, −41 %, 71 Trades, Profit-Faktor 0,11). Gründe: BTC-Gebühren von 0,8 % je Seite kosteten ~1,2 R pro Trade, USD/JPY-Kurse von Kraken waren unzuverlässig, und bei EUR/USD und GBP/USD lag die Trefferquote mit 21 % weit unter den nötigen 37 %.

Jetzt:
- **Märkte:** nur EUR/USD und GBP/USD (BTC und USD/JPY lassen sich per `config.json` wieder aufnehmen).
- **Strategie** wählbar in `config.json` → `strategy.name`: `breakout` (Ausbruch über das N-Kerzen-Hoch/-Tief in Trendrichtung), `pullback` (Rücksetzer im Trend, RSI3) oder `ema_cross` (alt). Optional nur Einstiege zwischen `session_start_utc` und `session_end_utc`.
- **Kosten-Filter:** Ein Signal wird ausgelassen, wenn Gebühren und Slippage für Ein- und Ausstieg mehr als 0,25 R kosten würden (`risk.max_cost_r`).
- **Strategie-Test:** Workflow *Strategie-Test* (von Hand starten) spielt alle Kandidaten auf ~10 Jahren Tageskerzen, ~2 Jahren 1-h-Kerzen und 60 Tagen 15-min-Kerzen durch, mit denselben Schutzregeln wie der Bot. Ausgewählt wird nur auf den ersten 60 % („Lernen“), bewertet auf den letzten 40 % („Prüfen“). Bericht: `trading-cockpit/data/strategie_test.md` im Zweig `data` und in der Zusammenfassung des Laufs.

## Schutzregeln (seit 15.11.2026)

Vor jedem Einstieg prüft der Bot zusätzlich (Stand und nächster Termin stehen im Cockpit unter „Schutzregeln“):

- **Handelszeiten:** Der Devisenmarkt ist von Freitag 22:00 bis Sonntag 22:00 UTC geschlossen. In dieser Zeit und in den letzten 3 Stunden davor wird nicht eingestiegen; offene Positionen werden vor dem Wochenende geschlossen. Bei Tageskerzen werden nur Samstags- und Sonntagskerzen übersprungen. Einstellungen: `hours` in `config.json`.
- **Sperrzeiten um Termine:** Von 30 Minuten vor bis 60 Minuten nach einem Termin aus `kalender.json` (Zinsentscheide, Arbeitsmarkt, Inflation) kein Einstieg. Die Liste kommt von Trado und muss nachgepflegt werden; sind keine Termine mehr eingetragen, zeigt das Cockpit das an. Einstellungen: `news`.
- **Zu späte Läufe:** GitHub startet geplante Läufe unpünktlich (werktags etwa stündlich, am Wochenende seltener). Kommt ein Lauf mehr als 20 Minuten nach Kerzenschluss (bei Tageskerzen: 10 % der Kerzenlänge), wird ein Signal nur protokolliert, nicht ausgeführt – der Schlusskurs wäre am echten Markt nicht mehr zu bekommen. `risk.max_signal_age_min`.
- **Kurslücken:** Eröffnet eine Kerze schon jenseits des Stops, zählt der schlechtere Eröffnungskurs, nicht der Stop.
- **Klumpenrisiko:** EUR/USD und GBP/USD laufen meist gleich. Höchstens eine Position in dieselbe Dollar-Richtung. `risk.max_same_direction`.
- **Kontobremse:** Fällt das Konto 10 % unter seinen Höchststand, eröffnet der Bot nichts mehr, bis das Konto über *Steuerung* zurückgesetzt wird. `risk.max_total_drawdown_pct`.

Jeder Trade wird außerdem in **R** gemessen (1 R = der riskierte Betrag). Cockpit und Echtgeld-Tor rechnen den Zufallstest auf diesen R-Werten, damit die Kontogröße das Ergebnis nicht verzerrt.

## Time Machine (Monte-Carlo-Prüfung)

Vor jedem Trade spielt der Bot 10.000 mögliche Kursverläufe durch, zusammengesetzt aus den letzten 500 echten Kerzen. Der Trend wird dabei herausgerechnet, die Simulation unterstellt also bewusst keinen Vorteil. Ergebnis: Wahrscheinlichkeit für Ziel, Stop und Zeitablauf sowie der durchschnittliche Ertrag nach Gebühren in R (1 R = Verlust beim Stop). Fressen die Kosten mehr als ein Viertel des riskierten Betrags (schlechter als −0,25 R), wird der Trade ausgelassen. Das Cockpit vergleicht außerdem die vorhergesagte mit der tatsächlichen Trefferquote. Einstellungen: `TimeMachineConfig` in `agent/config.py`.

## Datenqualitäts-Wächter

Sind mehr als 25 % der letzten 96 Kerzen eines Marktes völlig unverändert (typisch für illiquide Kursquellen), handelt der Bot dort nicht und das Cockpit markiert den Markt als „Daten unzuverlässig“.

## Tresor-Modus (Verschlüsselung)

Ist bei GitHub das Secret `COCKPIT_PASSWORT` hinterlegt (*Settings* → *Secrets and variables* → *Actions*), speichert der Bot Kontostand, Trades und Cockpit-Daten nur noch verschlüsselt (`data/*.enc`, AES-256-GCM, Schlüssel per PBKDF2-SHA256 aus dem Passwort). In den öffentlichen GitHub-Logs stehen dann keine Beträge mehr. Das Cockpit fragt einmal pro Gerät nach dem Passwort und entschlüsselt die Daten direkt im Browser. Ohne Passwort oder mit falschem Passwort bricht der Bot ab, statt Daten zu überschreiben. **Passwort vergessen = Daten nicht wiederherstellbar** (dann über *Steuerung* das Konto zurücksetzen).

## Echtgeld-Freischaltung

Der Echtgeld-Modus wird erst frei, wenn der Spielgeld-Lauf ALLE Bedingungen erfüllt: mindestens 42 Tage (6 Wochen), mindestens 200 Trades, Profit-Faktor nach Gebühren mindestens 1,2, Zufallstest (t-Wert) mindestens 2, größter Rückgang höchstens 15 %, Ergebnis nach Gebühren im Plus. 200 Trades, weil sich erst ab dieser Größenordnung ein Vorteil von etwa 0,2 R pro Trade von Glück unterscheiden lässt. Grenzen im Echtgeld-Betrieb: höchstens 200 €, 1 % Risiko pro Trade, 3 % Tagesverlust-Limit, Notbremse bei 15 % Gesamtverlust (automatisch zurück auf Spielgeld), 1 Position, EUR/USD und GBP/USD, Hebel höchstens 10×, Broker-Schlüssel ohne Auszahlungsrecht. Eine Broker-Anbindung ist nicht gebaut. Vor Echtgeld wird dieses Projekt auf privat gestellt.

Alle Werte stehen in `agent/config.py` (Abschnitte `GateConfig` und `LiveConfig`).

---

## Lokal ausführen (optional)

Ein Trading-Agent, der EUR/USD und GBP/USD rund um die Uhr beobachtet, nach festen Regeln Trades eröffnet und schließt und jedes Signal vor der Ausführung von Claude gegenprüfen lässt. **Er handelt ausschließlich mit Spielgeld (Paper-Trading).** Es wird kein Konto benötigt, keine echte Order gesendet und kein echtes Geld bewegt.

> Kein Finanzrat. Die eingebaute Strategie ist ein transparenter Lern- und Teststand, kein Gewinnversprechen. Die allermeisten Daytrader verlieren Geld, vor allem wegen Gebühren und Spreads.

## So funktioniert der Agent

Bei jedem Lauf holt der Agent öffentliche Kursdaten von Kraken (ohne API-Key; Yahoo Finance als Ausweichquelle). Sobald eine Kerze abgeschlossen ist, passiert für jedes Symbol Folgendes (Beispiel: frühere Startstrategie `ema_cross`; die aktuelle steht oben unter „Strategie“):

1. **Offene Position prüfen:** Wurde Stop-Loss oder Take-Profit in der Kerze berührt? Gibt es ein Gegensignal? Ist die maximale Haltedauer (24 h) erreicht? Dann wird geschlossen.
2. **Signal suchen** (nur wenn keine Position offen ist):
   - LONG: EMA 9 kreuzt EMA 21 nach oben, Kurs über EMA 100, RSI zwischen 50 und 70
   - SHORT: EMA 9 kreuzt EMA 21 nach unten, Kurs unter EMA 100, RSI zwischen 30 und 50
   - Stop-Loss 1,5 × ATR, Take-Profit 3 × ATR (Chance/Risiko 1:2)
3. **Risiko prüfen:** Positionsgröße so, dass ein Stop-Loss maximal 1 % des Kontos kostet; höchstens 3 Positionen gleichzeitig; Hebel-Limit (Devisen 10×); Kosten-Filter 0,25 R; nach 3 % Tagesverlust Pause bis 00:00 UTC.
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
