# Strategie-Test 2026-11-15 01:41 UTC

Echte Kurse (Yahoo), gleiche Engine, Gebühren und Kosten-Filter wie der Bot. Ausgewählt nur auf „Lernen“, bewertet auf „Prüfen“. Vergangene Ergebnisse sind keine Garantie.

**Ergebnis:** Keine Variante hat den Prüf-Teil bestanden (mind. 30 Trades, PF 1.1, t 2.13). Am wenigsten schlecht: Rücksetzer RSI3 20/80, Stop 1.5 / Ziel 3 ATR auf 1d-Kerzen – höchstens zum Beobachten im Spielgeld, kein Beleg für einen Vorteil.

## Prüfliste

- Kein Blick in die Zukunft: Signale nur auf abgeschlossenen Kerzen, Einstieg zum Schlusskurs.
- Kosten drin: Gebühr/Spread je Seite {'EUR/USD': 0.006, 'GBP/USD': 0.008}, Slippage 0.005 % je Order, Kosten-Filter 0.25 R.
- Vorsichtige Ausführung: Stop und Ziel in derselben Kerze = Stop. Kurslücke über den Stop = schlechterer Eröffnungskurs.
- Auswahl und Bewertung getrennt: gewählt auf den ersten 60 %, bewertet auf den letzten 40 %.
- Schutz vor Zufallstreffern: je Zeitrahmen wird nur der Lern-Sieger geprüft; nötiger t-Wert 2.13 (95 % Sicherheit, geteilt durch 3 Zeitrahmen).
- Mindestmenge: 30 Trades im Prüf-Teil, Profit-Faktor mind. 1.1.
- Gleiche Schutzregeln wie im Bot: Handelszeiten, Schließen vor dem Wochenende, Sperrzeiten um Fed-Entscheide und US-Arbeitsmarkt (im Rückblick Näherung), höchstens eine Position je Dollar-Richtung.
- Grenzen: Yahoo-Kurse sind Richtkurse mit einzelnen Ausreißern; echte Spreads schwanken. Ein bestandener Test ist ein Kandidat für den Spielgeld-Lauf, kein Beweis.

## 1d-Kerzen

Lernen 2016-11-14 bis 2022-11-11, Prüfen 2022-11-11 bis 2026-11-13. 6 von 13 Varianten im Prüf-Teil im Plus.

Lern-Sieger: **Rücksetzer RSI3 20/80, Stop 1.5 / Ziel 3 ATR** – Prüfen: 43 Trades, PF 1.17, Ergebnis +515.91, t 0.52 → nicht bestanden

| Variante | Lernen T | PF | t | Prüfen T | PF | Ergebnis | t |
|---|---|---|---|---|---|---|---|
| Rücksetzer RSI3 10/90, Stop 2 / Ziel 4 ATR | 23 | 2.41 | 1.79 | 19 | 1.32 | +379 | 0.59 |
| Rücksetzer RSI3 20/80, Stop 1.5 / Ziel 3 ATR | 68 | 1.4 | 1.3 | 43 | 1.17 | +516 | 0.52 |
| Rücksetzer RSI3 10/90, Stop 2 / Ziel 2 ATR | 24 | 1.71 | 1.22 | 19 | 0.85 | -163 | -0.33 |
| Rücksetzer RSI3 10/90, Stop 1.5 / Ziel 3 ATR | 24 | 1.73 | 1.2 | 19 | 1.44 | +528 | 0.77 |
| Rücksetzer RSI3 20/80, Stop 2 / Ziel 4 ATR | 61 | 1.38 | 1.1 | 36 | 1.04 | +88 | 0.15 |
| Rücksetzer RSI3 20/80, Stop 2 / Ziel 2 ATR | 70 | 1.25 | 0.93 | 39 | 0.85 | -328 | -0.48 |
| EMA-Crossover (alt), Stop 1.5 / Ziel 3 ATR | 55 | 1.22 | 0.67 | 27 | 2.03 | +1272 | 1.64 |
| Ausbruch 50, Stop 1.5 / Ziel 3 ATR | 53 | 0.86 | -0.43 | 30 | 0.23 | -1671 | -3.93 |
| Ausbruch 20, Stop 2 / Ziel 4 ATR | 57 | 0.75 | -0.92 | 38 | 0.86 | -211 | -0.37 |
| Ausbruch 20, Stop 1.5 / Ziel 3 ATR | 63 | 0.74 | -1.01 | 41 | 0.75 | -520 | -0.79 |
| Ausbruch 20, Stop 2 / Ziel 2 ATR | 70 | 0.74 | -1.13 | 46 | 1.03 | +44 | 0.11 |
| Ausbruch 50, Stop 2 / Ziel 4 ATR | 47 | 0.66 | -1.19 | 28 | 0.34 | -994 | -2.56 |
| Ausbruch 50, Stop 2 / Ziel 2 ATR | 57 | 0.62 | -1.66 | 31 | 0.42 | -895 | -2.26 |

## 1h-Kerzen

Lernen 2024-01-29 bis 2025-09-30, Prüfen 2025-09-30 bis 2026-11-13. 0 von 26 Varianten im Prüf-Teil im Plus.

Lern-Sieger: **Rücksetzer RSI3 10/90, Stop 2 / Ziel 4 ATR, nur 07–17 UTC** – Prüfen: 58 Trades, PF 0.62, Ergebnis -1444.82, t -1.66 → nicht bestanden

Sperrzeiten beim Lern-Sieger (ganzer Zeitraum): mit 168 Trades, Ergebnis -1424; ohne 170 Trades, Ergebnis -1523.

| Variante | Lernen T | PF | t | Prüfen T | PF | Ergebnis | t |
|---|---|---|---|---|---|---|---|
| Rücksetzer RSI3 10/90, Stop 2 / Ziel 4 ATR, nur 07–17 UTC | 110 | 1.0 | 0.07 | 58 | 0.62 | -1445 | -1.66 |
| Rücksetzer RSI3 10/90, Stop 2 / Ziel 4 ATR | 181 | 0.98 | -0.03 | 103 | 0.85 | -970 | -0.71 |
| Rücksetzer RSI3 10/90, Stop 2 / Ziel 2 ATR | 188 | 0.97 | -0.13 | 106 | 0.74 | -1454 | -1.47 |
| Rücksetzer RSI3 10/90, Stop 2 / Ziel 2 ATR, nur 07–17 UTC | 113 | 0.86 | -0.71 | 59 | 0.68 | -1002 | -1.43 |
| Rücksetzer RSI3 10/90, Stop 1.5 / Ziel 3 ATR | 192 | 0.86 | -0.85 | 107 | 0.98 | -120 | -0.05 |
| Rücksetzer RSI3 10/90, Stop 1.5 / Ziel 3 ATR, nur 07–17 UTC | 119 | 0.81 | -0.94 | 64 | 0.88 | -473 | -0.45 |
| EMA-Crossover (alt), Stop 1.5 / Ziel 3 ATR, nur 07–17 UTC | 246 | 0.85 | -0.95 | 159 | 0.87 | -954 | -0.72 |
| Ausbruch 20, Stop 1.5 / Ziel 3 ATR, nur 07–17 UTC | 497 | 0.88 | -1.09 | 310 | 0.91 | -1091 | -0.59 |
| Rücksetzer RSI3 20/80, Stop 2 / Ziel 4 ATR, nur 07–17 UTC | 259 | 0.83 | -1.21 | 180 | 0.73 | -2262 | -2.07 |
| Ausbruch 20, Stop 2 / Ziel 4 ATR | 547 | 0.86 | -1.28 | 356 | 0.76 | -2730 | -2.18 |
| Ausbruch 20, Stop 2 / Ziel 4 ATR, nur 07–17 UTC | 448 | 0.84 | -1.38 | 279 | 0.85 | -1437 | -1.04 |
| Rücksetzer RSI3 20/80, Stop 2 / Ziel 4 ATR | 393 | 0.83 | -1.47 | 264 | 0.84 | -1609 | -1.28 |
| Rücksetzer RSI3 20/80, Stop 2 / Ziel 2 ATR, nur 07–17 UTC | 277 | 0.82 | -1.47 | 193 | 0.76 | -1792 | -1.86 |
| Ausbruch 50, Stop 2 / Ziel 4 ATR | 380 | 0.81 | -1.57 | 246 | 0.77 | -2066 | -1.82 |
| Rücksetzer RSI3 20/80, Stop 1.5 / Ziel 3 ATR, nur 07–17 UTC | 296 | 0.78 | -1.78 | 192 | 0.69 | -2479 | -2.65 |
| Ausbruch 20, Stop 1.5 / Ziel 3 ATR | 622 | 0.82 | -1.98 | 411 | 0.76 | -2381 | -2.36 |
| Ausbruch 20, Stop 2 / Ziel 2 ATR, nur 07–17 UTC | 574 | 0.81 | -2.11 | 348 | 0.68 | -2679 | -3.25 |
| Rücksetzer RSI3 20/80, Stop 1.5 / Ziel 3 ATR | 465 | 0.78 | -2.17 | 293 | 0.73 | -2486 | -2.97 |
| EMA-Crossover (alt), Stop 1.5 / Ziel 3 ATR | 372 | 0.73 | -2.36 | 240 | 0.73 | -1741 | -1.98 |
| Rücksetzer RSI3 20/80, Stop 2 / Ziel 2 ATR | 438 | 0.78 | -2.41 | 291 | 0.78 | -1878 | -2.23 |
| Ausbruch 50, Stop 1.5 / Ziel 3 ATR, nur 07–17 UTC | 341 | 0.73 | -2.48 | 202 | 0.87 | -910 | -0.86 |
| Ausbruch 50, Stop 1.5 / Ziel 3 ATR | 441 | 0.75 | -2.54 | 273 | 0.86 | -1098 | -1.07 |
| Ausbruch 50, Stop 2 / Ziel 2 ATR | 509 | 0.75 | -2.79 | 325 | 0.7 | -2274 | -3.12 |
| Ausbruch 50, Stop 2 / Ziel 2 ATR, nur 07–17 UTC | 390 | 0.73 | -2.83 | 231 | 0.62 | -2289 | -3.43 |
| Ausbruch 50, Stop 2 / Ziel 4 ATR, nur 07–17 UTC | 313 | 0.68 | -2.97 | 184 | 0.75 | -1336 | -1.65 |
| Ausbruch 20, Stop 2 / Ziel 2 ATR | 726 | 0.77 | -2.99 | 475 | 0.69 | -2471 | -3.77 |

## 15m-Kerzen

Lernen 2026-08-24 bis 2026-10-13, Prüfen 2026-10-13 bis 2026-11-13. 2 von 26 Varianten im Prüf-Teil im Plus.

Lern-Sieger: **Ausbruch 20, Stop 2 / Ziel 4 ATR** – Prüfen: 46 Trades, PF 0.68, Ergebnis -831.21, t -1.21 → nicht bestanden

Sperrzeiten beim Lern-Sieger (ganzer Zeitraum): mit 87 Trades, Ergebnis -3143; ohne 93 Trades, Ergebnis -2919.

| Variante | Lernen T | PF | t | Prüfen T | PF | Ergebnis | t |
|---|---|---|---|---|---|---|---|
| Rücksetzer RSI3 10/90, Stop 2 / Ziel 2 ATR | 9 | 2.26 | 1.18 | 13 | 0.94 | -35 | -0.02 |
| Rücksetzer RSI3 20/80, Stop 2 / Ziel 2 ATR, nur 07–17 UTC | 18 | 1.34 | 0.63 | 28 | 0.65 | -642 | -1.01 |
| Rücksetzer RSI3 10/90, Stop 2 / Ziel 2 ATR, nur 07–17 UTC | 7 | 1.65 | 0.62 | 8 | 0.97 | -13 | 0.02 |
| Rücksetzer RSI3 20/80, Stop 2 / Ziel 2 ATR | 23 | 1.03 | 0.12 | 39 | 0.61 | -961 | -1.38 |
| EMA-Crossover (alt), Stop 1.5 / Ziel 3 ATR, nur 07–17 UTC | 1 | 0.0 | 0.0 | 6 | 0.73 | -130 | -0.39 |
| Rücksetzer RSI3 20/80, Stop 2 / Ziel 4 ATR, nur 07–17 UTC | 16 | 0.93 | -0.11 | 24 | 0.44 | -1175 | -1.85 |
| Rücksetzer RSI3 10/90, Stop 2 / Ziel 4 ATR, nur 07–17 UTC | 6 | 0.87 | -0.14 | 8 | 0.66 | -207 | -0.5 |
| Rücksetzer RSI3 20/80, Stop 1.5 / Ziel 3 ATR, nur 07–17 UTC | 8 | 0.81 | -0.18 | 8 | 0.46 | -402 | -1.06 |
| Rücksetzer RSI3 10/90, Stop 1.5 / Ziel 3 ATR | 3 | 0.58 | -0.37 | 3 | 0.0 | -351 | -319.76 |
| Rücksetzer RSI3 10/90, Stop 1.5 / Ziel 3 ATR, nur 07–17 UTC | 3 | 0.58 | -0.37 | 1 | 0.0 | -120 | 0.0 |
| Ausbruch 20, Stop 1.5 / Ziel 3 ATR, nur 07–17 UTC | 14 | 0.66 | -0.64 | 12 | 0.96 | -31 | 0.01 |
| Rücksetzer RSI3 20/80, Stop 1.5 / Ziel 3 ATR | 10 | 0.59 | -0.7 | 11 | 0.31 | -723 | -1.9 |
| Rücksetzer RSI3 10/90, Stop 2 / Ziel 4 ATR | 8 | 0.55 | -0.77 | 13 | 1.06 | +51 | 0.15 |
| Rücksetzer RSI3 20/80, Stop 2 / Ziel 4 ATR | 21 | 0.63 | -1.05 | 31 | 0.59 | -937 | -1.3 |
| Ausbruch 50, Stop 1.5 / Ziel 3 ATR, nur 07–17 UTC | 11 | 0.45 | -1.19 | 12 | 0.97 | -26 | 0.01 |
| Ausbruch 20, Stop 1.5 / Ziel 3 ATR | 17 | 0.51 | -1.2 | 18 | 0.85 | -176 | -0.21 |
| Ausbruch 50, Stop 1.5 / Ziel 3 ATR | 14 | 0.34 | -1.86 | 16 | 1.05 | +45 | 0.19 |
| EMA-Crossover (alt), Stop 1.5 / Ziel 3 ATR | 2 | 0.0 | -2.06 | 8 | 0.51 | -334 | -0.95 |
| Ausbruch 20, Stop 2 / Ziel 4 ATR | 41 | 0.34 | -3.36 | 46 | 0.68 | -831 | -1.21 |
| Ausbruch 50, Stop 2 / Ziel 4 ATR | 34 | 0.3 | -3.47 | 36 | 0.95 | -102 | -0.15 |
| Ausbruch 20, Stop 2 / Ziel 4 ATR, nur 07–17 UTC | 38 | 0.32 | -3.47 | 35 | 0.74 | -520 | -0.83 |
| Ausbruch 50, Stop 2 / Ziel 4 ATR, nur 07–17 UTC | 31 | 0.27 | -3.64 | 29 | 0.91 | -146 | -0.24 |
| Ausbruch 20, Stop 2 / Ziel 2 ATR | 50 | 0.31 | -3.99 | 66 | 0.69 | -848 | -1.46 |
| Ausbruch 20, Stop 2 / Ziel 2 ATR, nur 07–17 UTC | 48 | 0.3 | -4.02 | 50 | 0.76 | -463 | -0.9 |
| Ausbruch 50, Stop 2 / Ziel 2 ATR | 39 | 0.18 | -5.41 | 52 | 0.76 | -488 | -0.94 |
| Ausbruch 50, Stop 2 / Ziel 2 ATR, nur 07–17 UTC | 37 | 0.17 | -5.57 | 43 | 0.82 | -292 | -0.61 |
