"""Tests ohne Netz: Rechnen, Umformen, Ausgabe. Start: python -m unittest discover -s trado-daten -p "test_*.py" """
import json
import os
import tempfile
import unittest
from datetime import date, timedelta

import abholer as A


def reihe(n=300, start=100.0, schritt=0.5):
    tag0 = date(2025, 9, 1)
    return [((tag0 + timedelta(days=i)).isoformat(), start + i * schritt) for i in range(n)]


class Rechnen(unittest.TestCase):
    def test_veraenderung(self):
        self.assertEqual(A.veraenderung([100, 110], 1), 10.0)
        self.assertIsNone(A.veraenderung([100], 1))
        self.assertIsNone(A.veraenderung([0, 5], 1))

    def test_kurs_kennzahlen(self):
        k = A.kurs_kennzahlen(reihe())
        self.assertEqual(k["schluss"], 249.5)
        self.assertEqual(k["hoch_52w"], 249.5)
        self.assertEqual(k["abstand_hoch_52w"], 0.0)
        self.assertEqual(k["tag"], round((249.5 / 249.0 - 1) * 100, 2))
        self.assertAlmostEqual(k["schnitt_50"], sum(100 + i * 0.5 for i in range(250, 300)) / 50, places=3)
        self.assertGreater(k["abstand_schnitt_200"], 0)
        self.assertIsNotNone(k["seit_jahresbeginn"])
        vorjahr_schluss = [c for d, c in reihe() if d < "2026"][-1]
        self.assertEqual(k["seit_jahresbeginn"], round((249.5 / vorjahr_schluss - 1) * 100, 2))

    def test_kurs_kennzahlen_wenig_daten(self):
        self.assertEqual(A.kurs_kennzahlen([("2026-01-02", 5.0)]), {})
        k = A.kurs_kennzahlen([("2026-01-02", 5.0), ("2026-01-05", 6.0)])
        self.assertEqual(k["tag"], 20.0)
        self.assertIsNone(k["schnitt_200"])
        self.assertIsNone(k["seit_jahresbeginn"])

    def test_luecken_werden_uebersprungen(self):
        k = A.kurs_kennzahlen([("2026-01-02", 5.0), ("2026-01-03", None), ("2026-01-05", 10.0)])
        self.assertEqual(k["tag"], 100.0)


class Umformen(unittest.TestCase):
    def test_chart(self):
        payload = {"chart": {"result": [{"timestamp": [1767312000, 1767398400, 1767484800],
                                         "indicators": {"quote": [{"close": [10.0, None, 12.0]}]}}]}}
        r = A.chart_zu_reihe(payload)
        self.assertEqual(len(r), 2)
        self.assertEqual(r[0], ("2026-01-02", 10.0))

    def test_stooq(self):
        text = "Date,Open,High,Low,Close,Volume\n2026-11-12,1,2,0.5,1.5,100\n2026-11-13,1,2,0.5,N/D,100\n"
        self.assertEqual(A.stooq_zu_reihe(text), [("2026-11-12", 1.5)])
        self.assertEqual(A.stooq_zu_reihe("No data"), [])

    def test_kennzahlen(self):
        kz = A.kennzahlen_aus_info({"trailingPE": 25.3, "forwardPE": {"raw": 17.4, "fmt": "17.40"},
                                    "currency": "USD", "profitMargins": float("nan"), "marketCap": None,
                                    "unbekannt": 1})
        self.assertEqual(kz, {"kgv": 25.3, "kgv_erwartet": 17.4, "waehrung": "USD"})

    def test_paare(self):
        from datetime import datetime
        paare = [(datetime(2026, 11, 12), 10.0), (datetime(2026, 11, 13), float("nan")), (datetime(2026, 11, 16), 12)]
        self.assertEqual(A.paare_zu_reihe(paare), [("2026-11-12", 10.0), ("2026-11-16", 12.0)])

    def test_notkurs_leer(self):
        self.assertEqual(A.notkurs_aus_info({"trailingPE": 5}), {})

    def test_fmt(self):
        self.assertEqual(A.fmt(1234.567, " €", 2), "1.234,57 €")
        self.assertEqual(A.fmt(None), "–")
        self.assertEqual(A.fmt(-3.25, " %"), "-3,2 %")


class Ausgabe(unittest.TestCase):
    def daten(self):
        return {"erzeugt_utc": "2026-11-15 06:23",
                "werte": [{"name": "Test AG", "yahoo": "TST.DE", "kurs": A.kurs_kennzahlen(reihe()),
                           "kennzahlen": {"kgv": 20.0, "kgv_erwartet": 15.5, "waehrung": "EUR",
                                          "nettomarge": 0.123, "umsatzwachstum": -0.05},
                           "naechste_zahlen": "2027-02-03"},
                          {"name": "Leer AG", "yahoo": "LEER.DE", "kurs": {}, "kennzahlen": {}}],
                "maerkte": [{"name": "EUR/USD", "yahoo": "EURUSD=X", "kurs": A.kurs_kennzahlen(reihe(30, 1.05, 0.001))}]}

    def test_uebersicht(self):
        md = A.uebersicht_md(self.daten())
        self.assertIn("| Test AG | 249,50 EUR |", md)
        self.assertIn("12,3 %", md)
        self.assertIn("-5,0 %", md)
        self.assertIn("| Leer AG | – |", md)
        self.assertIn("| EUR/USD | 1,0790 |", md)

    def test_verlauf_haengt_an_und_doppelt_nicht(self):
        with tempfile.TemporaryDirectory() as tmp:
            alt, A.AUSGABE = A.AUSGABE, tmp
            try:
                A.schreibe_verlauf(self.daten())
                A.schreibe_verlauf(self.daten())
                zeilen = open(os.path.join(tmp, "verlauf.csv"), encoding="utf-8").read().strip().splitlines()
            finally:
                A.AUSGABE = alt
        self.assertEqual(len(zeilen), 3)  # Kopf + 2 Werte mit Kurs, Leer AG fehlt
        self.assertTrue(zeilen[0].startswith("datum,symbol,schluss"))

    def lauf(self, **ersatz):
        """Startet main() mit ersetzten Holern in einem leeren Ordner."""
        namen = ("hole_kurse_yfinance", "hole_kurse_yahoo", "hole_kurse_stooq", "hole_angaben")

        def kaputt(sym):
            raise RuntimeError("kein Netz")

        with tempfile.TemporaryDirectory() as tmp:
            alt = {n: getattr(A, n) for n in namen}
            alt_ausgabe, alt_sleep = A.AUSGABE, A.time.sleep
            A.AUSGABE, A.time.sleep = tmp, lambda s: None
            for n in namen:
                setattr(A, n, ersatz.get(n, kaputt))
            try:
                code = A.main()
                status = json.load(open(os.path.join(tmp, "status.json"), encoding="utf-8"))
                pfad = os.path.join(tmp, "daten.json")
                daten = json.load(open(pfad, encoding="utf-8")) if os.path.exists(pfad) else None
            finally:
                A.AUSGABE, A.time.sleep = alt_ausgabe, alt_sleep
                for n in namen:
                    setattr(A, n, alt[n])
        return code, status, daten

    def test_hauptlauf_ohne_netz_schreibt_status(self):
        code, status, daten = self.lauf()
        self.assertEqual(code, 1)
        self.assertEqual(status["ergebnis"], "fehlgeschlagen")
        self.assertEqual(status["kurse_ok"], 0)
        self.assertIsNone(daten)

    def test_hauptlauf_normalfall(self):
        code, status, daten = self.lauf(
            hole_kurse_yfinance=lambda sym: reihe(),
            hole_angaben=lambda sym: ({"trailingPE": 11.0, "currency": "EUR"}, "2027-01-01"))
        self.assertEqual(code, 0)
        self.assertEqual(status["ergebnis"], "ok")
        self.assertEqual(daten["werte"][0]["kursquelle"], "yfinance")
        self.assertEqual(daten["werte"][0]["kennzahlen"], {"kgv": 11.0, "waehrung": "EUR"})
        self.assertEqual(daten["werte"][0]["naechste_zahlen"], "2027-01-01")
        self.assertNotIn("kennzahlen", daten["maerkte"][0])

    def test_hauptlauf_mit_ausweichquelle(self):
        code, status, daten = self.lauf(
            hole_kurse_stooq=lambda sym: reihe(),
            hole_angaben=lambda sym: ({"trailingPE": 11.0, "currency": "EUR"}, "2027-01-01"))
        self.assertEqual(code, 0)
        self.assertEqual(status["ergebnis"], "ok")
        self.assertEqual(daten["werte"][0]["kursquelle"], "Stooq")
        self.assertEqual(status["kurse_ok"], status["kurse_gesamt"])
        erster = next(iter(status["einzeln"].values()))
        self.assertIn("kurse_fehler_yfinance", erster)

    def test_hauptlauf_nur_eckdaten(self):
        """Keine Kursreihe zu bekommen: Kennzahlen und Eckdaten werden trotzdem gespeichert."""
        info = {"trailingPE": 30.0, "currency": "USD", "regularMarketPrice": 90.0,
                "regularMarketPreviousClose": 100.0, "fiftyTwoWeekHigh": 120.0, "fiftyTwoWeekLow": 60.0,
                "twoHundredDayAverage": 80.0, "regularMarketTime": 1767312000}
        code, status, daten = self.lauf(hole_angaben=lambda sym: (info, None))
        self.assertEqual(code, 0)
        self.assertEqual(status["ergebnis"], "teilweise")
        self.assertEqual(status["kursreihen_ok"], 0)
        w = daten["werte"][0]
        self.assertEqual(w["kursquelle"], "Yahoo-Eckdaten")
        self.assertEqual(w["kurs"]["schluss"], 90.0)
        self.assertEqual(w["kurs"]["tag"], -10.0)
        self.assertEqual(w["kurs"]["abstand_hoch_52w"], -25.0)
        self.assertEqual(w["kurs"]["abstand_schnitt_200"], 12.5)
        self.assertEqual(w["kurs"]["datum"], "2026-01-02")
        self.assertIsNone(w["kurs"]["monat"])
        self.assertEqual(daten["maerkte"][0]["kursquelle"], "Yahoo-Eckdaten")


if __name__ == "__main__":
    unittest.main()
