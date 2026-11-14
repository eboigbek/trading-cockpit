#!/usr/bin/env python3
"""Strategie-Test auf echten Kursen (läuft auf GitHub Actions, Workflow "Strategie-Test").

Holt historische Kerzen von Yahoo (1 h: ~2 Jahre, 15 min: ~60 Tage) und spielt jede
Kandidaten-Strategie mit derselben Engine wie der Live-Bot durch (gleiche Gebühren,
Slippage, Kosten-Filter, Risikolimits; ohne Time Machine und Claude, weil zu langsam).

Gegen Selbstbetrug: Jede Zeitreihe wird geteilt. Ausgewählt wird nur auf dem ersten Teil
("Lernen", 60 %), bewertet auf dem zweiten, unberührten Teil ("Prüfen", 40 %). Nur wenn der
Lern-Sieger auch im Prüf-Teil besteht, gilt er als Kandidat für den Spielgeld-Lauf.

  python strategie_test.py                 # echte Kurse
  python strategie_test.py --synthetic     # Mechanik-Test ohne Internet
Ergebnis: data/strategie_test.json und data/strategie_test.md
"""
from __future__ import annotations

import argparse
import copy
import itertools
import json
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Dict, List

import requests

from agent.backtest import run_backtest
from agent.config import Config, load_config
from agent.data import HEADERS, Candle, synthetic_series
from agent.gate import t_stat

LEARN_SHARE = 0.6
TIMEFRAMES = {"1h": {"interval": "60m", "range": "730d", "minutes": 60, "max_hold": 24},
              "15m": {"interval": "15m", "range": "60d", "minutes": 15, "max_hold": 96}}
# Prüf-Teil muss das schaffen, damit eine Strategie in den Spielgeld-Lauf darf
# (t ≥ 1,65 ≈ 95 % einseitig: der Gewinn im unberührten Teil ist wahrscheinlich kein Zufall)
PASS_MIN_TRADES = 30
PASS_MIN_PF = 1.1
PASS_MIN_T = 1.65


def fetch_yahoo(ticker: str, interval: str, rng: str) -> List[Candle]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    for attempt in range(3):
        try:
            r = requests.get(url, params={"interval": interval, "range": rng}, headers=HEADERS, timeout=30)
            r.raise_for_status()
            res = r.json()["chart"]["result"][0]
            break
        except Exception as e:  # Rate-Limit, Netz
            if attempt == 2:
                raise
            print(f"  Yahoo {ticker} {interval}: {e} – neuer Versuch", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    q = res["indicators"]["quote"][0]
    out = []
    for i, ts in enumerate(res.get("timestamp", [])):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c) or min(o, h, l, c) <= 0:
            continue
        out.append(Candle(int(ts), float(o), float(max(h, o, c)), float(min(l, o, c)), float(c)))
    return out[:-1]


def candidates() -> List[Dict]:
    out = [{"name": "ema_cross", "stop_atr": 1.5, "take_profit_atr": 3.0}]
    for n, (sl, tp) in itertools.product((20, 50), ((2.0, 4.0), (1.5, 3.0), (2.0, 2.0))):
        out.append({"name": "breakout", "breakout_bars": n, "stop_atr": sl, "take_profit_atr": tp})
    for (lo, hi), (sl, tp) in itertools.product(((10.0, 90.0), (20.0, 80.0)), ((2.0, 2.0), (1.5, 3.0), (2.0, 4.0))):
        out.append({"name": "pullback", "pullback_long_max": lo, "pullback_short_min": hi,
                    "stop_atr": sl, "take_profit_atr": tp})
    # Jede Variante zusätzlich nur während London/New York (07–17 Uhr UTC)
    return out + [{**c, "session_start_utc": 7, "session_end_utc": 17} for c in out]


def label(c: Dict) -> str:
    if c["name"] == "breakout":
        s = f"Ausbruch {c['breakout_bars']}"
    elif c["name"] == "pullback":
        s = f"Rücksetzer RSI3 {c['pullback_long_max']:.0f}/{c['pullback_short_min']:.0f}"
    else:
        s = "EMA-Crossover (alt)"
    s += f", Stop {c['stop_atr']:g} / Ziel {c['take_profit_atr']:g} ATR"
    if c.get("session_start_utc"):
        s += ", nur 07–17 UTC"
    return s


def segment_stats(trades, curve, start_ts: int, end_ts: int) -> Dict:
    ts_ = [t for t in trades if start_ts <= t.closed_ts < end_ts]
    wins = sum(t.pnl for t in ts_ if t.pnl > 0)
    losses = -sum(t.pnl for t in ts_ if t.pnl < 0)
    pf = wins / losses if losses > 0 else (99.0 if wins > 0 else 0.0)
    peak, mdd = None, 0.0
    for ts, eq in curve:
        if start_ts <= ts < end_ts:
            peak = eq if peak is None else max(peak, eq)
            mdd = max(mdd, (peak - eq) / peak * 100 if peak else 0.0)
    net = sum(t.pnl for t in ts_)
    return {"trades": len(ts_), "net": round(net, 2), "pf": round(min(pf, 99.0), 2),
            "win_rate": round(sum(t.pnl > 0 for t in ts_) / len(ts_) * 100, 1) if ts_ else 0.0,
            "t": round(t_stat(ts_), 2), "max_dd_pct": round(mdd, 2),
            "fees": round(sum(t.fees for t in ts_), 2)}


def run_timeframe(base: Config, tf: str, data: Dict[str, List[Candle]]) -> Dict:
    spec = TIMEFRAMES[tf]
    all_ts = sorted({c.ts for cs in data.values() for c in cs})
    first, last = all_ts[0], all_ts[-1] + 1
    split = all_ts[int(len(all_ts) * LEARN_SHARE)]
    rows = []
    for cand in candidates():
        cfg = copy.deepcopy(base)
        cfg.interval_min = spec["minutes"]
        cfg.ai.enabled = False
        cfg.timemachine.enabled = False
        cfg.strategy.max_hold_bars = spec["max_hold"]
        for k, v in cand.items():
            setattr(cfg.strategy, k, v)
        t0 = time.time()
        res = run_backtest(cfg, data)
        learn = segment_stats(res.trades, res.equity_curve, first, split)
        test = segment_stats(res.trades, res.equity_curve, split, last)
        rows.append({"label": label(cand), "strategy": cand, "learn": learn, "test": test})
        print(f"  {tf:>3} {label(cand):<60} Lernen {learn['trades']:>4} T, PF {learn['pf']:>5.2f}, "
              f"t {learn['t']:>5.2f} | Prüfen {test['trades']:>4} T, PF {test['pf']:>5.2f} "
              f"({time.time() - t0:.1f}s)", flush=True)
    eligible = [r for r in rows if r["learn"]["trades"] >= 30]
    best = max(eligible, key=lambda r: r["learn"]["t"]) if eligible else None
    passed = bool(best and best["test"]["trades"] >= PASS_MIN_TRADES and best["test"]["pf"] >= PASS_MIN_PF
                  and best["test"]["net"] > 0 and best["learn"]["net"] > 0 and best["test"]["t"] >= PASS_MIN_T)
    d = lambda ts: datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    return {"timeframe": tf, "bars": {k: len(v) for k, v in data.items()},
            "learn_period": [d(first), d(split)], "test_period": [d(split), d(last)],
            "rows": rows, "best": best, "passed": passed,
            "test_positive": sum(1 for r in rows if r["test"]["net"] > 0), "candidates": len(rows)}


def verdict(results: List[Dict], base: Config) -> Dict:
    passed = [r for r in results if r["passed"]]
    pool = passed or [r for r in results if r["best"]]
    if not pool:
        return {"passed": False, "config": None, "text": "Zu wenige Trades für eine Auswahl."}
    win = max(pool, key=lambda r: r["best"]["test"]["t"])
    spec = TIMEFRAMES[win["timeframe"]]
    strat = {**win["best"]["strategy"], "max_hold_bars": spec["max_hold"]}
    cfg = {"interval_min": spec["minutes"], "strategy": strat}
    name = f"{win['best']['label']} auf {win['timeframe']}-Kerzen"
    if passed:
        return {"passed": True, "timeframe": win["timeframe"], "label": win["best"]["label"], "config": cfg,
                "text": f"Bestanden: {name}. Kandidat für den Spielgeld-Lauf."}
    return {"passed": False, "timeframe": win["timeframe"], "label": win["best"]["label"], "config": cfg,
            "text": f"Keine Variante hat den Prüf-Teil bestanden (mind. {PASS_MIN_TRADES} Trades, PF "
                    f"{PASS_MIN_PF}, t {PASS_MIN_T}). Am wenigsten schlecht: {name} – höchstens zum "
                    f"Beobachten im Spielgeld, kein Beleg für einen Vorteil."}


def write_md(path: str, out: Dict) -> None:
    L = [f"# Strategie-Test {out['generated']}", "",
         "Echte Kurse (Yahoo), gleiche Engine, Gebühren und Kosten-Filter wie der Bot. "
         "Ausgewählt nur auf „Lernen“, bewertet auf „Prüfen“. Vergangene Ergebnisse sind keine Garantie.", "",
         f"**Ergebnis:** {out['verdict']['text']}", ""]
    for r in out["results"]:
        L += [f"## {r['timeframe']}-Kerzen", "",
              f"Lernen {r['learn_period'][0]} bis {r['learn_period'][1]}, Prüfen {r['test_period'][0]} bis "
              f"{r['test_period'][1]}. {r['test_positive']} von {r['candidates']} Varianten im Prüf-Teil im Plus.", ""]
        if r["best"]:
            b = r["best"]
            L.append(f"Lern-Sieger: **{b['label']}** – Prüfen: {b['test']['trades']} Trades, PF {b['test']['pf']}, "
                     f"Ergebnis {b['test']['net']:+.2f}, t {b['test']['t']} → {'bestanden' if r['passed'] else 'nicht bestanden'}")
        L += ["", "| Variante | Lernen T | PF | t | Prüfen T | PF | Ergebnis | t |", "|---|---|---|---|---|---|---|---|"]
        for x in sorted(r["rows"], key=lambda x: -x["learn"]["t"]):
            a, b = x["learn"], x["test"]
            L.append(f"| {x['label']} | {a['trades']} | {a['pf']} | {a['t']} | {b['trades']} | {b['pf']} | "
                     f"{b['net']:+.0f} | {b['t']} |")
        L.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--timeframes", default="1h,15m")
    args = ap.parse_args()
    base = load_config()
    os.makedirs("data", exist_ok=True)
    results = []
    for tf in args.timeframes.split(","):
        spec = TIMEFRAMES[tf]
        data = {}
        for s in base.symbols:
            if args.synthetic:
                data[s.name] = synthetic_series(s.name, 3000, spec["minutes"], seed=5)
            else:
                data[s.name] = fetch_yahoo(s.yahoo, spec["interval"], spec["range"])
            print(f"{tf} {s.name}: {len(data[s.name])} Kerzen", flush=True)
        results.append(run_timeframe(base, tf, data))
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
           "source": "synthetic" if args.synthetic else "yahoo",
           "symbols": [s.name for s in base.symbols],
           "costs": {s.name: s.fee_pct for s in base.symbols}, "slippage_pct": base.risk.slippage_pct,
           "max_cost_r": base.risk.max_cost_r, "results": results}
    out["verdict"] = verdict(results, base)
    with open("data/strategie_test.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    write_md("data/strategie_test.md", out)
    print(out["verdict"]["text"])


if __name__ == "__main__":
    main()
