# Trado Daten-Abholer

Holt zweimal je Handelstag Kurse und Kennzahlen für die Beobachtungsliste der Finanzabteilung und legt sie im Zweig `trado-daten` ab. Getrennt vom Trading Pilot: eigener Ordner, eigener Ablauf, eigener Zweig. Kein Schlüssel, kein Konto, kein Geld.

- `liste.json` – welche Werte und Märkte geholt werden. Hier ändern, wenn die Liste wächst.
- `abholer.py` – holt und rechnet. Quelle: Yahoo über das Paket yfinance. Ausweichquellen für Kurse: Yahoo direkt, Stooq, zuletzt die Eckdaten aus den Kennzahlen.
- `test_abholer.py` – Tests ohne Netz, laufen vor jedem Abruf.
- `speichern.sh` – legt die Ausgabe im Zweig `trado-daten` ab.

Ausgabe im Zweig `trado-daten`: `uebersicht.md` (lesbar), `daten.json` (alles), `status.json` (was geklappt hat), `verlauf.csv` (eine Zeile je Wert und Tag).

Von Hand starten: Reiter *Actions* → *Trado Daten-Abholer* → *Run workflow*.

Keine Empfehlung. Die Zahlen stammen aus frei zugänglichen Quellen und können Fehler enthalten.
