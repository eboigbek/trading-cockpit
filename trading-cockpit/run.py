#!/usr/bin/env python3
"""Steuerung des Paper-Trading-Agenten.

  python run.py live                 # Paper-Trading mit echten Live-Kursen (Kraken/Yahoo), läuft dauerhaft
  python run.py live --once          # Nur ein Durchlauf (z.B. für Cron / Aufgabenplanung)
  python run.py demo                 # Schnelldemo mit simulierten Kursen, ohne Internet
  python run.py backtest             # Backtest auf den letzten ~7 Tagen echter 15-min-Kerzen
  python run.py backtest --synthetic # Backtest auf simulierten Kursen (offline)
  python run.py status               # Kontostand, offene Positionen, letzte Trades
  python run.py reset                # Paper-Konto zurücksetzen
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

from agent.ai_reviewer import AIReviewer
from agent.backtest import run_backtest, write_report
from agent.broker import PaperBroker
from agent.config import load_config
from agent.data import fetch_candles, load_csv, synthetic_series
from agent.live import LiveAgent, setup_logging


def cmd_live(cfg, args):
    if args.no_ai:
        cfg.ai.enabled = False
    setup_logging(cfg)
    LiveAgent(cfg).run(max_cycles=1 if args.once else None)


def cmd_demo(cfg, args):
    cfg.data_source = "synthetic"
    cfg.state_file, cfg.trades_file, cfg.log_file = "data/demo_state.json", "data/demo_trades.csv", "data/demo.log"
    cfg.cockpit_file, cfg.control_file = "data/demo_cockpit.json", "data/demo_control.json"
    for p in (cfg.state_file, cfg.trades_file, cfg.cockpit_file):
        if os.path.exists(p):
            os.remove(p)
    if args.no_ai:
        cfg.ai.enabled = False
    setup_logging(cfg)
    LiveAgent(cfg).run(max_cycles=args.bars)


def cmd_backtest(cfg, args):
    data = {}
    if args.synthetic:
        data = {s.name: synthetic_series(s.name, args.bars, cfg.interval_min, seed=args.seed) for s in cfg.symbols}
    elif args.csv:
        sym = cfg.symbols[0]
        cfg.symbols = [sym]
        data = {sym.name: load_csv(args.csv)}
    else:
        for s in cfg.symbols:
            try:
                data[s.name] = fetch_candles(s, cfg.interval_min, cfg.data_source)
                print(f"{s.name}: {len(data[s.name])} Kerzen geladen")
            except Exception as e:
                print(f"{s.name}: übersprungen ({e})")
        cfg.symbols = [s for s in cfg.symbols if s.name in data]
        if not data:
            sys.exit("Keine Marktdaten erreichbar. Tipp: --synthetic für einen Offline-Test.")
    reviewer = AIReviewer(cfg.ai) if args.ai else None
    if reviewer and reviewer.active:
        print("Claude-Prüfung im Backtest aktiv (verursacht API-Kosten pro Signal).")
    res = run_backtest(cfg, data, reviewer)
    print("\n=== BACKTEST", "(simulierte Kurse)" if args.synthetic else "", "===")
    print(res.summary())
    os.makedirs("data", exist_ok=True)
    out = args.report or "data/backtest_report.html"
    write_report(res, out, "Backtest – simulierte Kurse" if args.synthetic else "Backtest – echte Kurse")
    print(f"\nBericht: {out}")


def cmd_status(cfg, args):
    b = PaperBroker(cfg)
    st = b.state
    eq = b.equity()
    print(f"Equity: {eq:,.2f} {cfg.risk.account_currency} "
          f"({(eq / cfg.risk.starting_cash - 1) * 100:+.2f}% seit Start) | Cash: {st.cash:,.2f}")
    print(f"Offene Positionen ({len(st.positions)}):")
    for p in st.positions.values():
        u = b.unrealized(cfg.symbol(p.symbol), st.last_prices.get(p.symbol, p.entry))
        print(f"  {p.symbol} {p.side.upper()} {p.units:.6g} @ {p.entry:.6g} | SL {p.stop:.6g} "
              f"| TP {p.take_profit:.6g} | unrealisiert {u:+.2f}")
    print(f"Abgeschlossene Trades: {len(st.trades)}")
    for t in st.trades[-10:]:
        when = datetime.fromtimestamp(t.closed_ts, tz=timezone.utc).strftime("%m-%d %H:%M")
        print(f"  {when} {t.symbol} {t.side} {t.pnl:+.2f} ({t.exit_reason})")


def cmd_reset(cfg, args):
    for p in (cfg.state_file, cfg.trades_file, cfg.cockpit_file):
        if os.path.exists(p):
            os.remove(p)
    print("Paper-Konto zurückgesetzt.")


def main():
    ap = argparse.ArgumentParser(description="Paper-Trading-Agent für BTC und Devisen")
    ap.add_argument("--config", default="config.json")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("live", help="Paper-Trading mit Live-Kursen")
    p.add_argument("--once", action="store_true", help="nur ein Durchlauf")
    p.add_argument("--no-ai", action="store_true", help="Claude-Prüfung deaktivieren")
    p.set_defaults(fn=cmd_live)

    p = sub.add_parser("demo", help="Schnelldemo mit simulierten Kursen")
    p.add_argument("--bars", type=int, default=500)
    p.add_argument("--no-ai", action="store_true")
    p.set_defaults(fn=cmd_demo)

    p = sub.add_parser("backtest", help="Backtest")
    p.add_argument("--synthetic", action="store_true")
    p.add_argument("--csv", help="CSV mit ts,open,high,low,close (für das erste Symbol)")
    p.add_argument("--bars", type=int, default=3000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--ai", action="store_true", help="Claude-Prüfung auch im Backtest (kostet API-Guthaben)")
    p.add_argument("--report")
    p.set_defaults(fn=cmd_backtest)

    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("reset").set_defaults(fn=cmd_reset)

    args = ap.parse_args()
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    args.fn(load_config(args.config), args)


if __name__ == "__main__":
    main()
