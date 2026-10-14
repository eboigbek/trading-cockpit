"""Live-Paper-Trading: verarbeitet jede neue abgeschlossene Kerze, beachtet die
Steuerdatei (Not-Aus, Modus), protokolliert Ereignisse und schreibt die Daten
fürs Cockpit. Läuft entweder dauerhaft (`run`) oder als einzelner Durchlauf
(`cycle`, z.B. alle 15 Minuten über GitHub Actions)."""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from . import export
from .ai_reviewer import AIReviewer
from .broker import PaperBroker
from .config import Config, SymbolConfig
from .control import load_control
from .data import Candle, SyntheticFeed, fetch_candles
from .engine import TradingEngine
from .gate import progress

log = logging.getLogger("agent.live")


def setup_logging(cfg: Config) -> None:
    os.makedirs(os.path.dirname(cfg.log_file) or ".", exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    for h in (logging.StreamHandler(), logging.FileHandler(cfg.log_file, encoding="utf-8")):
        h.setFormatter(fmt)
        root.addHandler(h)


def fmt_ts(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def p6(x: float) -> str:
    return f"{x:.6g}"


class LiveAgent:
    def __init__(self, cfg: Config, fetcher: Optional[Callable[[SymbolConfig, int], List[Candle]]] = None,
                 reviewer: Optional[AIReviewer] = None, clock: Optional[Callable[[], int]] = None):
        self.cfg = cfg
        self.broker = PaperBroker(cfg)
        self.reviewer = reviewer if reviewer is not None else AIReviewer(cfg.ai)
        self.engine = TradingEngine(cfg, self.broker, self.reviewer)
        self.clock = clock or (lambda: int(time.time()))
        self.feed: Optional[SyntheticFeed] = None
        if fetcher is not None:
            self.fetch = fetcher
        elif cfg.data_source == "synthetic":
            self.feed = SyntheticFeed([s.name for s in cfg.symbols], cfg.interval_min)
            self.fetch = self.feed.fetch
        else:
            self.fetch = lambda sym, iv: fetch_candles(sym, iv, cfg.data_source)

    # ------------------------------------------------------------------
    def _once(self, key: str, value: str, ts: int, kind: str, text: str) -> None:
        """Ereignis nur protokollieren, wenn sich ein Zustand geändert hat (kein Spam)."""
        if self.broker.state.flags.get(key) != value:
            self.broker.state.flags[key] = value
            if text:
                self.broker.event(ts, kind, text)
                log.info(text)

    def cycle(self) -> int:
        """Ein Durchlauf über alle Symbole. Gibt die Anzahl verarbeiteter neuer Kerzen zurück."""
        st = self.broker.state
        now = self.clock()
        ctl = load_control(self.cfg.control_file)
        if not st.paper_start_ts:
            st.paper_start_ts = now
            self.broker.event(now, "info", f"Spielgeld-Konto gestartet mit {self.cfg.risk.starting_cash:,.0f} "
                                           f"{self.cfg.risk.account_currency}")

        self._once("stop", str(ctl.stop), now, "warn" if ctl.stop else "info",
                   "NOT-AUS aktiv: keine neuen Trades, offene Positionen werden geschlossen" if ctl.stop
                   else ("Not-Aus aufgehoben – Bot handelt wieder" if "stop" in st.flags else ""))

        processed = 0
        markets: Dict[str, List[Candle]] = {}
        for sym in self.cfg.symbols:
            try:
                candles = self.fetch(sym, self.cfg.interval_min)
                self._once(f"data:{sym.name}", "ok", now, "info",
                           f"{sym.name}: Kursdaten wieder verfügbar" if f"data:{sym.name}" in st.flags else "")
            except Exception as e:
                log.error("%s: Daten nicht verfügbar – %s", sym.name, e)
                self._once(f"data:{sym.name}", "err", now, "warn", f"{sym.name}: Kursdaten nicht verfügbar")
                continue
            if not candles:
                continue
            markets[sym.name] = candles
            last = st.last_bar_ts.get(sym.name)
            if last is None:
                # Erster Start: Historie nur als Aufwärmphase, keine Trades auf alten Kerzen
                st.last_bar_ts[sym.name] = candles[-1].ts
                self.broker.mark(sym, candles[-1].close)
                log.info("%s: %d Kerzen geladen, letzter Kurs %s (%s).", sym.name, len(candles),
                         p6(candles[-1].close), fmt_ts(candles[-1].ts))
                continue
            new_idx = [i for i, c in enumerate(candles) if c.ts > last]
            for n, i in enumerate(new_idx):
                newest = n == len(new_idx) - 1
                res = self.engine.on_bar(sym, candles[: i + 1], allow_entry=newest and not ctl.stop)
                processed += 1
                self._report(sym, candles[i], res)
            if new_idx:
                st.last_bar_ts[sym.name] = candles[new_idx[-1]].ts
            else:
                self.broker.mark(sym, candles[-1].close)

        if ctl.stop:
            for name in list(st.positions):
                sym = self.cfg.symbol(name)
                price = st.last_prices.get(name, st.positions[name].entry)
                t = self.broker.close(sym, price, now, "not_aus")
                self.broker.event(now, "close", f"Not-Aus: {t.symbol} {t.side} geschlossen @ {p6(t.exit)}, "
                                                f"Ergebnis {t.pnl:+.2f} (Gebühren {t.fees:.2f})")

        mode_note = self._mode_note(ctl.mode, now)
        self.broker.snapshot(now)
        prev = export.read(self.cfg.cockpit_file)
        data = export.build(self.cfg, self.broker, now, markets, self.reviewer.active,
                            self.reviewer.model_name, ctl.mode, ctl.stop, mode_note, prev)
        export.write(self.cfg.cockpit_file, data)
        self.broker.save()
        return processed

    def _mode_note(self, requested: str, now: int) -> str:
        if requested != "live":
            note = "Spielgeld-Modus"
            self._once("mode", note, now, "info", "Spielgeld-Modus aktiv" if "mode" in self.broker.state.flags else "")
            return note
        gate = progress(self.broker.state, self.cfg.gate, self.cfg.risk.starting_cash, now)
        if not gate["unlocked"]:
            missing = ", ".join(i["label"] for i in gate["items"] if not i["ok"])
            note = f"Echtgeld angefordert, aber gesperrt. Noch offen: {missing}"
        else:
            note = ("Alle Bedingungen erfüllt – Börsenanbindung ist noch nicht eingerichtet. "
                    "Bot bleibt im Spielgeld-Modus.")
        self._once("mode", note, now, "warn", note)
        return note

    def _report(self, sym: SymbolConfig, bar: Candle, res) -> None:
        ts = bar.ts + self.cfg.interval_min * 60  # Zeitpunkt des Kerzenschlusses
        for t in res.closed:
            reason = {"stop_loss": "Stop-Loss", "take_profit": "Gewinnziel", "gegensignal": "Gegensignal",
                      "max_haltedauer": "max. Haltedauer"}.get(t.exit_reason, t.exit_reason)
            text = (f"{t.symbol} {t.side.upper()} geschlossen @ {p6(t.exit)} ({reason}): "
                    f"{t.pnl:+.2f} {self.cfg.risk.account_currency} nach {t.fees:.2f} Gebühren")
            self.broker.event(ts, "close", text)
            log.info(text)
        if res.opened:
            p = self.broker.state.positions[sym.name]
            text = (f"{p.symbol} {p.side.upper()} eröffnet @ {p6(p.entry)} | Stop {p6(p.stop)} | "
                    f"Ziel {p6(p.take_profit)} | {p.reason}")
            self.broker.event(ts, "open", text)
            if p.ai_note:
                self.broker.event(ts, "ai", f"Claude zu {p.symbol}: {p.ai_note}")
            log.info(text)
        elif res.signal and res.skipped_reason:
            kind = "ai" if res.review is not None and not res.review.approved else "skip"
            text = f"{sym.name} {res.signal.side.upper()}-Signal nicht ausgeführt: {res.skipped_reason}"
            self.broker.event(ts, kind, text)
            log.info(text)

    def status_line(self) -> str:
        st = self.broker.state
        eq = self.broker.equity()
        start = self.cfg.risk.starting_cash
        pos = ", ".join(f"{p.symbol} {p.side}" for p in st.positions.values()) or "keine"
        return (f"Equity {eq:,.2f} {self.cfg.risk.account_currency} ({(eq / start - 1) * 100:+.2f}%) | "
                f"Trades {len(st.trades)} | offen: {pos}")

    def run(self, max_cycles: Optional[int] = None) -> None:
        mode = "Claude-Prüfung AKTIV" if self.reviewer.active else "nur Regeln (kein ANTHROPIC_API_KEY)"
        log.info("Paper-Trading-Agent gestartet | Quelle: %s | %s | %s",
                 self.cfg.data_source, mode, ", ".join(s.name for s in self.cfg.symbols))
        log.info("ACHTUNG: Simulation – es wird kein echtes Geld gehandelt.")
        cycles = 0
        try:
            while max_cycles is None or cycles < max_cycles:
                if self.cycle():
                    log.info(self.status_line())
                cycles += 1
                if self.feed:
                    self.feed.advance()
                elif max_cycles is None or cycles < max_cycles:
                    time.sleep(self.cfg.poll_seconds)
        except KeyboardInterrupt:
            log.info("Beendet durch Benutzer.")
        finally:
            self.broker.save()
            log.info(self.status_line())
