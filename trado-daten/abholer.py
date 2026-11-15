"""Trado Daten-Abholer: holt Kurse und Kennzahlen fuer die Beobachtungsliste.

Laeuft auf GitHub Actions (dort sind die Datenquellen erreichbar), braucht keinen
Schluessel und bewegt kein Geld. Quellen: Yahoo (Kurse ueber die Chart-Schnittstelle,
Kennzahlen ueber yfinance), Stooq als Ausweichquelle fuer Kurse.

Ausgabe im Ordner ausgabe/: daten.json (alles), uebersicht.md (lesbar),
status.json (was hat geklappt, was nicht), verlauf.csv (eine Zeile je Wert und Tag).
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import requests

KOPF = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0 Safari/537.36"}
AUSGABE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ausgabe")

KENNZAHLEN = {  # Feld bei Yahoo -> Name in unserer Datei
    "marketCap": "boersenwert", "currency": "waehrung", "sector": "branche",
    "trailingPE": "kgv", "forwardPE": "kgv_erwartet",
    "priceToSalesTrailing12Months": "kurs_umsatz", "enterpriseToEbitda": "ev_ebitda",
    "priceToBook": "kurs_buchwert", "profitMargins": "nettomarge",
    "operatingMargins": "operative_marge", "revenueGrowth": "umsatzwachstum",
    "earningsGrowth": "gewinnwachstum", "returnOnEquity": "eigenkapitalrendite",
    "debtToEquity": "schulden_zu_eigenkapital", "freeCashflow": "freier_mittelzufluss",
    "totalRevenue": "umsatz", "dividendYield": "dividendenrendite",
    "trailingEps": "gewinn_je_aktie", "forwardEps": "gewinn_je_aktie_erwartet",
    "targetMeanPrice": "kursziel_schnitt", "numberOfAnalystOpinions": "analysten",
    "recommendationKey": "analysten_urteil",
}


# ---------- Rechnen (ohne Netz, wird getestet) ----------

def zahl(x) -> Optional[float]:
    """Macht aus beliebigen Eingaben eine endliche Zahl oder None."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def veraenderung(kurse: List[float], tage: int) -> Optional[float]:
    """Prozentuale Veraenderung gegenueber dem Schluss vor `tage` Handelstagen."""
    if len(kurse) <= tage or kurse[-1 - tage] <= 0:
        return None
    return round((kurse[-1] / kurse[-1 - tage] - 1) * 100, 2)


def schnitt(kurse: List[float], tage: int) -> Optional[float]:
    if len(kurse) < tage:
        return None
    return sum(kurse[-tage:]) / tage


def kurs_kennzahlen(reihe: List[Tuple[str, float]]) -> Dict:
    """reihe: Liste aus (Datum JJJJ-MM-TT, Schlusskurs), aelteste zuerst."""
    reihe = [(d, c) for d, c in reihe if zahl(c) is not None and c > 0]
    if len(reihe) < 2:
        return {}
    daten, kurse = [d for d, _ in reihe], [c for _, c in reihe]
    letzter, jahr = kurse[-1], daten[-1][:4]
    vorjahr = [c for d, c in reihe if d[:4] < jahr]
    fenster = kurse[-252:]
    hoch, tief = max(fenster), min(fenster)
    s50, s200 = schnitt(kurse, 50), schnitt(kurse, 200)
    aenderungen = [math.log(kurse[i] / kurse[i - 1]) for i in range(max(1, len(kurse) - 30), len(kurse))]
    schwankung = None
    if len(aenderungen) >= 10:
        m = sum(aenderungen) / len(aenderungen)
        var = sum((a - m) ** 2 for a in aenderungen) / (len(aenderungen) - 1)
        schwankung = round(math.sqrt(var) * math.sqrt(252) * 100, 1)
    return {
        "schluss": round(letzter, 4), "datum": daten[-1], "handelstage": len(kurse),
        "tag": veraenderung(kurse, 1), "woche": veraenderung(kurse, 5),
        "monat": veraenderung(kurse, 21), "quartal": veraenderung(kurse, 63),
        "jahr": veraenderung(kurse, 252),
        "seit_jahresbeginn": round((letzter / vorjahr[-1] - 1) * 100, 2) if vorjahr else None,
        "hoch_52w": round(hoch, 4), "tief_52w": round(tief, 4),
        "abstand_hoch_52w": round((letzter / hoch - 1) * 100, 2),
        "abstand_tief_52w": round((letzter / tief - 1) * 100, 2),
        "schnitt_50": round(s50, 4) if s50 else None,
        "schnitt_200": round(s200, 4) if s200 else None,
        "abstand_schnitt_200": round((letzter / s200 - 1) * 100, 2) if s200 else None,
        "schwankung_30t": schwankung,
    }


def kennzahlen_aus_info(info: Dict) -> Dict:
    aus = {}
    for quelle, ziel in KENNZAHLEN.items():
        wert = info.get(quelle)
        if isinstance(wert, dict):  # Rohformat der Yahoo-Schnittstelle: {"raw": .., "fmt": ..}
            wert = wert.get("raw")
        if isinstance(wert, str):
            aus[ziel] = wert
        else:
            v = zahl(wert)
            if v is not None:
                aus[ziel] = round(v, 4)
    return aus


def chart_zu_reihe(payload: Dict) -> List[Tuple[str, float]]:
    res = payload["chart"]["result"][0]
    schluss = res["indicators"]["quote"][0]["close"]
    reihe = []
    for ts, c in zip(res.get("timestamp", []), schluss):
        if c is None:
            continue
        reihe.append((datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%d"), float(c)))
    return reihe


def stooq_zu_reihe(text: str) -> List[Tuple[str, float]]:
    reihe = []
    for zeile in csv.DictReader(io.StringIO(text)):
        c = zahl(zeile.get("Close"))
        if zeile.get("Date") and c:
            reihe.append((zeile["Date"], c))
    return reihe


def fmt(v, einheit="", stellen=1) -> str:
    if v is None or v == "":
        return "–"
    if isinstance(v, str):
        return v
    return f"{v:,.{stellen}f}".replace(",", "X").replace(".", ",").replace("X", ".") + einheit


def uebersicht_md(daten: Dict) -> str:
    z = [f"# Trado Daten – Stand {daten['erzeugt_utc']} UTC", "",
         "Quelle: Yahoo, Ausweichquelle Stooq. Keine Empfehlung, nur Zahlen.", "",
         "## Beobachtungsliste", "",
         "| Wert | Schluss | Datum | Woche | Monat | Seit Jahresbeginn | Abstand 52-W-Hoch | KGV | KGV erwartet | Nettomarge | Umsatzwachstum | Nächste Zahlen |",
         "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for w in daten["werte"]:
        k, f = w.get("kurs", {}), w.get("kennzahlen", {})
        marge = f.get("nettomarge")
        wachs = f.get("umsatzwachstum")
        z.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            w["name"], fmt(k.get("schluss"), " " + f.get("waehrung", ""), 2), k.get("datum", "–"),
            fmt(k.get("woche"), " %"), fmt(k.get("monat"), " %"), fmt(k.get("seit_jahresbeginn"), " %"),
            fmt(k.get("abstand_hoch_52w"), " %"), fmt(f.get("kgv")), fmt(f.get("kgv_erwartet")),
            fmt(marge * 100 if marge is not None else None, " %"),
            fmt(wachs * 100 if wachs is not None else None, " %"), w.get("naechste_zahlen") or "–"))
    z += ["", "## Märkte", "", "| Markt | Stand | Datum | Tag | Woche | Monat | Seit Jahresbeginn |",
          "|---|---:|---|---:|---:|---:|---:|"]
    for m in daten["maerkte"]:
        k = m.get("kurs", {})
        z.append("| {} | {} | {} | {} | {} | {} | {} |".format(
            m["name"], fmt(k.get("schluss"), "", 4 if (k.get("schluss") or 0) < 10 else 2), k.get("datum", "–"),
            fmt(k.get("tag"), " %"), fmt(k.get("woche"), " %"), fmt(k.get("monat"), " %"),
            fmt(k.get("seit_jahresbeginn"), " %")))
    return "\n".join(z) + "\n"


# ---------- Holen (mit Netz) ----------

def hole_kurse_yahoo(symbol: str) -> List[Tuple[str, float]]:
    letzter_fehler = None
    for host in ("query1", "query2"):
        try:
            r = requests.get(f"https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}",
                             params={"range": "2y", "interval": "1d"}, headers=KOPF, timeout=20)
            r.raise_for_status()
            return chart_zu_reihe(r.json())
        except Exception as e:  # noqa: BLE001 - jede Stoerung soll zur Ausweichquelle fuehren
            letzter_fehler = e
            time.sleep(1.5)
    raise RuntimeError(f"Yahoo-Kurse: {letzter_fehler}")


def hole_kurse_stooq(symbol: str) -> List[Tuple[str, float]]:
    r = requests.get("https://stooq.com/q/d/l/", params={"s": symbol, "i": "d"}, headers=KOPF, timeout=20)
    r.raise_for_status()
    reihe = stooq_zu_reihe(r.text)
    if len(reihe) < 2:
        raise RuntimeError(f"Stooq lieferte keine Kurse ({r.text[:60]!r})")
    return reihe[-520:]


def hole_kennzahlen(symbol: str) -> Tuple[Dict, Optional[str]]:
    """Gibt (Kennzahlen, Termin der naechsten Zahlen) zurueck. Braucht yfinance."""
    import yfinance as yf  # erst hier, damit Tests ohne das Paket laufen

    t = yf.Ticker(symbol)
    info = t.info or {}
    termin = None
    try:
        kal = t.calendar or {}
        tage = kal.get("Earnings Date") if isinstance(kal, dict) else None
        if tage:
            erster = tage[0] if isinstance(tage, (list, tuple)) else tage
            termin = str(erster)[:10]
    except Exception:  # noqa: BLE001 - Termin ist Beiwerk
        termin = None
    kz = kennzahlen_aus_info(info)
    if not kz:
        raise RuntimeError("Yahoo lieferte keine Kennzahlen")
    return kz, termin


def bearbeite(eintrag: Dict, mit_kennzahlen: bool, status: Dict) -> Dict:
    aus = dict(eintrag)
    sym, protokoll = eintrag["yahoo"], {}
    try:
        aus["kurs"] = kurs_kennzahlen(hole_kurse_yahoo(sym))
        aus["kursquelle"] = "Yahoo"
        protokoll["kurse"] = "ok (Yahoo)"
    except Exception as e:  # noqa: BLE001
        protokoll["kurse_yahoo_fehler"] = str(e)[:200]
        try:
            aus["kurs"] = kurs_kennzahlen(hole_kurse_stooq(eintrag["stooq"]))
            aus["kursquelle"] = "Stooq"
            protokoll["kurse"] = "ok (Stooq)"
        except Exception as e2:  # noqa: BLE001
            aus["kurs"] = {}
            protokoll["kurse"] = "FEHLER"
            protokoll["kurse_stooq_fehler"] = str(e2)[:200]
    if mit_kennzahlen:
        for versuch in range(2):
            try:
                aus["kennzahlen"], aus["naechste_zahlen"] = hole_kennzahlen(sym)
                protokoll["kennzahlen"] = "ok"
                break
            except Exception as e:  # noqa: BLE001
                aus["kennzahlen"], aus["naechste_zahlen"] = {}, None
                protokoll["kennzahlen"] = "FEHLER"
                protokoll["kennzahlen_fehler"] = f"{type(e).__name__}: {str(e)[:200]}"
                time.sleep(3)
    status["einzeln"][sym] = protokoll
    time.sleep(0.8)
    return aus


def schreibe_verlauf(daten: Dict) -> None:
    pfad = os.path.join(AUSGABE, "verlauf.csv")
    kopf = ["datum", "symbol", "schluss", "kgv", "kgv_erwartet", "kursziel_schnitt"]
    alt = []
    if os.path.exists(pfad):
        with open(pfad, newline="", encoding="utf-8") as f:
            alt = [z for z in csv.DictReader(f)]
    schon = {(z["datum"], z["symbol"]) for z in alt}
    for w in daten["werte"] + daten["maerkte"]:
        k, f = w.get("kurs", {}), w.get("kennzahlen", {})
        if not k.get("datum") or (k["datum"], w["yahoo"]) in schon:
            continue
        alt.append({"datum": k["datum"], "symbol": w["yahoo"], "schluss": k.get("schluss"),
                    "kgv": f.get("kgv", ""), "kgv_erwartet": f.get("kgv_erwartet", ""),
                    "kursziel_schnitt": f.get("kursziel_schnitt", "")})
    alt.sort(key=lambda z: (z["datum"], z["symbol"]))
    with open(pfad, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=kopf)
        w.writeheader()
        w.writerows(alt)


def main() -> int:
    os.makedirs(AUSGABE, exist_ok=True)
    jetzt = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    status = {"erzeugt_utc": jetzt, "einzeln": {}, "lauf": os.environ.get("GITHUB_RUN_ID", "lokal")}
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "liste.json"), encoding="utf-8") as f:
            liste = json.load(f)
        daten = {"erzeugt_utc": jetzt,
                 "werte": [bearbeite(e, True, status) for e in liste["werte"]],
                 "maerkte": [bearbeite(e, False, status) for e in liste["maerkte"]]}
        alle = daten["werte"] + daten["maerkte"]
        status["kurse_ok"] = sum(1 for w in alle if w.get("kurs"))
        status["kurse_gesamt"] = len(alle)
        status["kennzahlen_ok"] = sum(1 for w in daten["werte"] if w.get("kennzahlen"))
        status["kennzahlen_gesamt"] = len(daten["werte"])
        if status["kurse_ok"]:
            with open(os.path.join(AUSGABE, "daten.json"), "w", encoding="utf-8") as f:
                json.dump(daten, f, ensure_ascii=False, indent=1)
            with open(os.path.join(AUSGABE, "uebersicht.md"), "w", encoding="utf-8") as f:
                f.write(uebersicht_md(daten))
            schreibe_verlauf(daten)
        status["ergebnis"] = "ok" if status["kurse_ok"] == status["kurse_gesamt"] and \
            status["kennzahlen_ok"] == status["kennzahlen_gesamt"] else \
            ("teilweise" if status["kurse_ok"] else "fehlgeschlagen")
    except Exception as e:  # noqa: BLE001 - Status soll immer geschrieben werden
        status["ergebnis"] = "abgebrochen"
        status["abbruch"] = f"{type(e).__name__}: {str(e)[:300]}"
    with open(os.path.join(AUSGABE, "status.json"), "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in status.items() if k != "einzeln"}, ensure_ascii=False))
    return 0 if status["ergebnis"] in ("ok", "teilweise") else 1


if __name__ == "__main__":
    sys.exit(main())
