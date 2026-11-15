import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.ai_reviewer import AIReviewer, Review  # noqa: E402
from agent.backtest import run_backtest  # noqa: E402
from agent.broker import PaperBroker  # noqa: E402
from agent.config import LEGACY_SYMBOLS, AIConfig, Config  # noqa: E402
from agent.data import Candle, synthetic_series  # noqa: E402
from agent.engine import TradingEngine, cost_r  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from agent.indicators import atr, ema, rsi  # noqa: E402
from agent.live import LiveAgent  # noqa: E402
from agent.risk import RiskManager  # noqa: E402
from agent.strategy import generate_signal  # noqa: E402


def cfg_tmp():
    cfg = Config()
    d = tempfile.mkdtemp()
    cfg.state_file = os.path.join(d, "state.json")
    cfg.trades_file = os.path.join(d, "trades.csv")
    cfg.log_file = os.path.join(d, "agent.log")
    cfg.cockpit_file = os.path.join(d, "cockpit.json")
    cfg.control_file = os.path.join(d, "control.json")
    cfg.ai.enabled = False
    cfg.timemachine.enabled = False  # Mechanik-Tests ohne Filter; Time Machine hat eigene Tests
    # Mechanik-Tests laufen weiter mit den früheren vier Märkten und der alten Strategie
    cfg.symbols = list(LEGACY_SYMBOLS)
    cfg.strategy.name = "ema_cross"
    cfg.risk.max_cost_r = 99.0
    # ... und ohne die Schutzregeln (Handelszeiten, Sperrzeiten, Kontobremse, Signal-Alter,
    # Klumpenrisiko); die haben eigene Tests in TestGuards
    cfg.hours.enabled = False
    cfg.news.enabled = False
    cfg.risk.max_total_drawdown_pct = 0.0
    cfg.risk.max_signal_age_min = 10 ** 6
    cfg.risk.max_same_direction = 0
    return cfg


class TestIndicators(unittest.TestCase):
    def test_ema_constant(self):
        self.assertAlmostEqual(ema([5.0] * 30, 10)[-1], 5.0)

    def test_ema_known(self):
        out = ema([1, 2, 3, 4, 5], 3)
        self.assertEqual(out[:2], [None, None])
        self.assertAlmostEqual(out[2], 2.0)
        self.assertAlmostEqual(out[3], 3.0)
        self.assertAlmostEqual(out[4], 4.0)

    def test_rsi_extremes(self):
        self.assertAlmostEqual(rsi(list(range(1, 40)), 14)[-1], 100.0)
        self.assertAlmostEqual(rsi(list(range(40, 1, -1)), 14)[-1], 0.0)

    def test_atr_constant_range(self):
        n = 40
        self.assertAlmostEqual(atr([11.0] * n, [9.0] * n, [10.0] * n, 14)[-1], 2.0)


class TestNewStrategies(unittest.TestCase):
    @staticmethod
    def _cs(closes, start=1_760_000_000, step=3600):
        return [Candle(start + j * step, c, c + 0.2, c - 0.2, c) for j, c in enumerate(closes)]

    def test_breakout_long_in_uptrend(self):
        cfg = Config().strategy
        cfg.name = "breakout"
        closes = [100 + i * 0.05 for i in range(150)] + [107.5 + (0.1 if i % 2 else -0.1) for i in range(25)]
        closes.append(closes[-1] + 1.5)                         # Ausbruch nach oben
        sig = generate_signal("X", self._cs(closes), cfg)
        self.assertIsNotNone(sig)
        self.assertEqual(sig.side, "long")
        self.assertIn("Ausbruch", sig.reason)

    def test_breakout_needs_trend(self):
        cfg = Config().strategy
        cfg.name = "breakout"
        closes = [120 - i * 0.1 for i in range(150)] + [105 + (0.1 if i % 2 else -0.1) for i in range(25)]
        closes.append(closes[-1] + 1.5)                         # Ausbruch nach oben im Abwärtstrend
        sig = generate_signal("X", self._cs(closes), cfg)
        self.assertTrue(sig is None or sig.side != "long")

    def test_pullback_long(self):
        cfg = Config().strategy
        cfg.name = "pullback"
        closes = [100 + i * 0.1 for i in range(180)] + [117.9 - 0.3 * i for i in range(1, 4)]
        sig = generate_signal("X", self._cs(closes), cfg)
        self.assertIsNotNone(sig)
        self.assertEqual(sig.side, "long")

    def test_session_filter(self):
        cfg = Config().strategy
        cfg.name = "pullback"
        closes = [100 + i * 0.1 for i in range(180)] + [117.9 - 0.3 * i for i in range(1, 4)]
        cs = self._cs(closes)
        hour = datetime.fromtimestamp(cs[-1].ts, tz=timezone.utc).hour
        cfg.session_start_utc, cfg.session_end_utc = (hour + 1) % 24, (hour + 2) % 24 or 24
        self.assertIsNone(generate_signal("X", cs, cfg))
        cfg.session_start_utc, cfg.session_end_utc = hour, hour + 1
        self.assertIsNotNone(generate_signal("X", cs, cfg))


class TestCostFilter(unittest.TestCase):
    def test_cost_r(self):
        # BTC: 0,8 % je Seite + 0,005 % Slippage, Stop 0,5 % entfernt -> ~3,2 R Kosten
        self.assertAlmostEqual(cost_r(100.0, 99.5, 0.8, 0.005), 3.22, places=2)
        # EUR/USD: 0,006 % + 0,005 %, Stop 0,2 % -> 0,11 R
        self.assertAlmostEqual(cost_r(1.0, 0.998, 0.006, 0.005), 0.11, places=2)

    def test_engine_skips_expensive_trade(self):
        cfg = cfg_tmp()
        cfg.risk.max_cost_r = 0.25
        cfg.symbols = [s for s in LEGACY_SYMBOLS if s.name == "BTC/USD"]
        series = synthetic_series("BTC/USD", 1500, seed=3)
        b = PaperBroker(cfg)
        e = TradingEngine(cfg, b)
        kinds = set()
        for i in range(150, len(series)):
            r = e.on_bar(cfg.symbols[0], series[: i + 1])
            if r.signal:
                kinds.add(r.skip_kind)
        self.assertIn("cost", kinds)
        self.assertEqual(len(b.state.trades), 0)


class TestTStat(unittest.TestCase):
    def test_t_stat(self):
        from agent.gate import t_stat
        self.assertEqual(t_stat([]), 0.0)
        ts = t_stat([mk_trade(30)] * 60 + [mk_trade(-20)] * 60)
        self.assertGreater(ts, 2.0)
        self.assertLess(t_stat([mk_trade(30)] * 5 + [mk_trade(-25)] * 5), 2.0)


class TestStrategy(unittest.TestCase):
    def test_long_signal_on_cross_in_uptrend(self):
        cfg = Config().strategy
        cfg.name = "ema_cross"
        closes = [100 + i * 0.5 for i in range(150)]          # Aufwärtstrend
        for _ in range(15):                                     # Rücksetzer -> EMA9 unter EMA21
            closes.append(closes[-1] - 0.6)
        for i in range(40):                                     # Wiederaufnahme im Zickzack (RSI < 70)
            closes.append(closes[-1] + (1.0 if i % 2 == 0 else -0.4))
        sig = None
        for i in range(120, len(closes)):
            cs = [Candle(j, c, c + 0.3, c - 0.3, c) for j, c in enumerate(closes[: i + 1])]
            sig = generate_signal("X", cs, cfg)
            if sig:
                break
        self.assertIsNotNone(sig)
        self.assertEqual(sig.side, "long")
        self.assertLess(sig.stop, sig.price)
        self.assertGreater(sig.take_profit, sig.price)
        self.assertAlmostEqual((sig.take_profit - sig.price) / (sig.price - sig.stop), 2.0)


class TestBrokerAndRisk(unittest.TestCase):
    def test_position_size_risks_one_percent(self):
        cfg = cfg_tmp()
        b = PaperBroker(cfg, persist=False)
        rm = RiskManager(cfg, b)
        eur = cfg.symbol("EUR/USD")
        d = rm.size(eur, 1.1000, 1.0980)  # 20 Pips Stop
        self.assertTrue(d.allowed)
        self.assertAlmostEqual(d.units * 0.0020, 100.0, places=6)  # 1% von 10.000

    def test_leverage_cap_btc(self):
        cfg = cfg_tmp()
        b = PaperBroker(cfg, persist=False)
        d = RiskManager(cfg, b).size(cfg.symbol("BTC/USD"), 60_000, 59_990)  # sehr enger Stop
        self.assertLessEqual(d.units * 60_000, 10_000 + 1e-6)  # max. 1x Hebel

    def test_usdjpy_pnl_converted_to_usd(self):
        cfg = cfg_tmp()
        cfg.risk.slippage_pct = 0
        jpy = cfg.symbol("USD/JPY")
        jpy.fee_pct = 0
        b = PaperBroker(cfg, persist=False)
        b.open(jpy, "long", 10_000, 150.0, 149.0, 152.0, 0)
        t = b.close(jpy, 151.5, 1, "test")
        self.assertAlmostEqual(t.pnl, 10_000 * 1.5 / 151.5, places=6)

    def test_stop_loss_and_fees(self):
        cfg = cfg_tmp()
        cfg.risk.slippage_pct = 0
        eur = cfg.symbol("EUR/USD")
        b = PaperBroker(cfg, persist=False)
        b.open(eur, "short", 50_000, 1.1000, 1.1020, 1.0960, 0)
        t = b.check_stops(eur, high=1.1025, low=1.0950, ts=1)  # beides berührt -> Stop zählt
        self.assertEqual(t.exit_reason, "stop_loss")
        expected_fees = (50_000 * 1.1000 + 50_000 * 1.1020) * eur.fee_pct / 100
        self.assertAlmostEqual(t.fees, expected_fees, places=6)
        self.assertAlmostEqual(t.pnl, -50_000 * 0.0020 - expected_fees, places=6)
        self.assertAlmostEqual(b.state.cash, 10_000 + t.pnl, places=6)

    def test_daily_loss_blocks_new_trades(self):
        cfg = cfg_tmp()
        b = PaperBroker(cfg, persist=False)
        rm = RiskManager(cfg, b)
        rm.roll_day(0)
        b.state.cash -= 400  # -4 % am Tag
        self.assertFalse(rm.size(cfg.symbol("EUR/USD"), 1.1, 1.09).allowed)
        rm.roll_day(86_400)  # neuer Tag
        self.assertTrue(rm.size(cfg.symbol("EUR/USD"), 1.1, 1.09).allowed)

    def test_state_persists(self):
        cfg = cfg_tmp()
        b = PaperBroker(cfg)
        b.open(cfg.symbol("EUR/USD"), "long", 1000, 1.1, 1.09, 1.12, 0, "test")
        b.save()
        b2 = PaperBroker(cfg)
        self.assertIn("EUR/USD", b2.state.positions)
        self.assertAlmostEqual(b2.state.cash, b.state.cash)


class FakeReviewer(AIReviewer):
    def __init__(self, approve):
        super().__init__(AIConfig(enabled=True), api_key="x")
        self.approve, self.seen = approve, 0

    def review(self, sig, candles, broker):
        self.seen += 1
        return Review("APPROVE" if self.approve else "REJECT", 0.9, "test", self.approve)


class TestAIReviewer(unittest.TestCase):
    def test_parse(self):
        d = AIReviewer.parse('Hier: {"decision": "reject", "confidence": 1.4, "reason": "choppy"}')
        self.assertEqual(d["decision"], "REJECT")
        self.assertEqual(d["confidence"], 1.0)

    def test_inactive_without_key(self):
        self.assertFalse(AIReviewer(AIConfig(enabled=True), api_key="").active)

    def test_fail_open_on_network_error(self):
        r = AIReviewer(AIConfig(enabled=True, fail_open=False, timeout_s=1), api_key="x")
        r.review.__func__  # existiert
        rev = r._fallback(RuntimeError("down"))
        self.assertFalse(rev.approved)

    def test_reject_blocks_all_entries(self):
        cfg = cfg_tmp()
        data = {s.name: synthetic_series(s.name, 1500, seed=3) for s in cfg.symbols}
        rej = FakeReviewer(False)
        res = run_backtest(cfg, data, rej)
        self.assertGreater(rej.seen, 0)
        self.assertEqual(len(res.trades), 0)

    def test_prompt_contains_signal(self):
        cfg = cfg_tmp()
        b = PaperBroker(cfg, persist=False)
        cs = synthetic_series("EUR/USD", 300)
        from agent.strategy import Signal
        sig = Signal("EUR/USD", "long", 1.1, 1.09, 1.12, "Test", {"rsi": 55})
        p = AIReviewer(AIConfig(), api_key="x").build_prompt(sig, cs, b)
        self.assertIn("LONG EUR/USD", p)
        self.assertIn("zeit_utc,open,high,low,close", p)


class TestEndToEnd(unittest.TestCase):
    def test_backtest_runs_and_accounting_balances(self):
        cfg = cfg_tmp()
        data = {s.name: synthetic_series(s.name, 3000, seed=11) for s in cfg.symbols}
        res = run_backtest(cfg, data)
        self.assertGreater(len(res.trades), 10)
        self.assertAlmostEqual(res.end_equity, cfg.risk.starting_cash + sum(t.pnl for t in res.trades), places=4)
        # Kein Einzeltrade verliert deutlich mehr als ~1 % Risiko (+ Gebühren/Slippage/Gaps)
        worst = min(t.pnl for t in res.trades)
        self.assertGreater(worst, -cfg.risk.starting_cash * 0.03)

    def test_live_agent_processes_new_bars_and_resumes(self):
        cfg = cfg_tmp()
        cfg.symbols = cfg.symbols[:2]
        series = {s.name: synthetic_series(s.name, 800, seed=5) for s in cfg.symbols}
        pos = {"n": 300}
        fetch = lambda sym, iv: series[sym.name][: pos["n"]]  # noqa: E731
        a = LiveAgent(cfg, fetcher=fetch)
        self.assertEqual(a.cycle(), 0)  # erster Lauf = Aufwärmen
        pos["n"] += 3
        self.assertEqual(a.cycle(), 6)  # 3 neue Kerzen x 2 Symbole
        self.assertEqual(a.cycle(), 0)  # nichts Neues
        for _ in range(400):
            pos["n"] += 1
            a.cycle()
        a2 = LiveAgent(cfg, fetcher=fetch)  # Neustart setzt fort
        self.assertEqual(a2.broker.state.last_bar_ts, a.broker.state.last_bar_ts)
        self.assertEqual(len(a2.broker.state.trades), len(a.broker.state.trades))




# ---------------------------------------------------------------------------
# Freischaltung, Steuerung, Cockpit-Export
# ---------------------------------------------------------------------------
import json  # noqa: E402

from agent.broker import AccountState, Trade  # noqa: E402
from agent.config import GateConfig  # noqa: E402
from agent.control import Control, load_control, save_control  # noqa: E402
from agent.export import fee_scenarios  # noqa: E402
from agent.gate import progress  # noqa: E402


def mk_trade(pnl, symbol="EUR/USD", gross=None, turnover=0.0):
    return Trade(symbol, "long", 1, 1, 1, 0, 1, pnl, 0.0, "x", gross_pnl=pnl if gross is None else gross,
                 turnover=turnover)


class TestGate(unittest.TestCase):
    def test_locked_when_new(self):
        st = AccountState(cash=10_000, paper_start_ts=0)
        g = progress(st, GateConfig(), 10_000, 1_000)
        self.assertFalse(g["unlocked"])

    def test_unlocks_only_when_all_met(self):
        day = 86_400
        trades = ([mk_trade(30) for _ in range(30)] + [mk_trade(-20) for _ in range(25)]) * 4  # PF 1.8, 220 Trades
        st = AccountState(cash=10_000, trades=trades, paper_start_ts=1,
                          equity_history=[[0, 10_000], [1, 9_500], [2, 10_400]])
        self.assertTrue(progress(st, GateConfig(), 10_000, 43 * day)["unlocked"])
        self.assertFalse(progress(st, GateConfig(), 10_000, 41 * day)["unlocked"])  # zu kurz
        st.equity_history.append([3, 8_000])  # Drawdown > 15 %
        self.assertFalse(progress(st, GateConfig(), 10_000, 43 * day)["unlocked"])

    def test_low_profit_factor_blocks(self):
        trades = [mk_trade(10) for _ in range(30)] + [mk_trade(-10) for _ in range(25)]  # PF 1.2 knapp
        st = AccountState(cash=10_000, trades=trades, paper_start_ts=1, equity_history=[[0, 10_000]])
        items = {i["key"]: i for i in progress(st, GateConfig(min_profit_factor=1.3), 10_000, 50 * 86_400)["items"]}
        self.assertFalse(items["pf"]["ok"])


class TestControlAndExport(unittest.TestCase):
    def test_broken_control_file_means_stop(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "c.json")
        open(p, "w").write("{kaputt")
        self.assertTrue(load_control(p).stop)
        save_control(p, Control("live", False))
        c = load_control(p)
        self.assertEqual((c.mode, c.stop), ("live", False))

    def test_fee_scenarios(self):
        cfg = cfg_tmp()
        trades = [mk_trade(-5, "BTC/USD", gross=10, turnover=10_000), mk_trade(3)]
        sc = {s["fee_pct"]: s["net"] for s in fee_scenarios(cfg, trades)}
        self.assertAlmostEqual(sc[0.10], 3 + 10 - 10)
        self.assertAlmostEqual(sc[0.80], 3 + 10 - 80)

    def _agent(self, cfg, n0=300):
        series = {s.name: synthetic_series(s.name, 1500, seed=9) for s in cfg.symbols}
        pos = {"n": n0}
        clock = lambda: series[cfg.symbols[0].name][pos["n"] - 1].ts + 120  # noqa: E731
        a = LiveAgent(cfg, fetcher=lambda sym, iv: series[sym.name][: pos["n"]], clock=clock)
        return a, pos

    def test_stop_closes_positions_and_blocks_entries(self):
        cfg = cfg_tmp()
        a, pos = self._agent(cfg)
        a.cycle()
        while not a.broker.state.positions:
            pos["n"] += 1
            a.cycle()
        save_control(cfg.control_file, Control("paper", True))
        pos["n"] += 1
        a.cycle()
        self.assertEqual(a.broker.state.positions, {})
        self.assertEqual(a.broker.state.trades[-1].exit_reason, "not_aus")
        for _ in range(300):
            pos["n"] += 1
            a.cycle()
        self.assertEqual(a.broker.state.positions, {})
        self.assertEqual(sum(t.exit_reason != "not_aus" and t.closed_ts > 0 for t in a.broker.state.trades[-1:]), 0)

    def test_live_request_stays_paper_and_export_complete(self):
        cfg = cfg_tmp()
        save_control(cfg.control_file, Control("live", False))
        a, pos = self._agent(cfg)
        for _ in range(400):
            a.cycle()
            pos["n"] += 1
        data = json.load(open(cfg.cockpit_file))
        self.assertEqual(data["mode"]["effective"], "paper")
        self.assertEqual(data["mode"]["requested"], "live")
        self.assertIn("gesperrt", data["mode"]["note"])
        self.assertFalse(data["gate"]["unlocked"])
        self.assertEqual(len(data["markets"]), 4)
        self.assertEqual(len(data["markets"][0]["closes"]), 96)
        self.assertGreater(len(data["equity_curve"]), 50)
        self.assertEqual(data["account"]["trades"], len(a.broker.state.trades))
        self.assertAlmostEqual(data["account"]["fees_total"], sum(t.fees for t in a.broker.state.trades), places=1)
        self.assertTrue(any(e["kind"] == "warn" and "gesperrt" in e["text"] for e in data["events"]))
        # Ereignis "gesperrt" nur einmal, nicht bei jedem Lauf
        self.assertEqual(sum("gesperrt" in e["text"] for e in a.broker.state.events), 1)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# Tresor-Modus (Verschlüsselung)
# ---------------------------------------------------------------------------
from unittest import mock  # noqa: E402

from agent import vault  # noqa: E402


class TestVault(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(vault, "ITERATIONS", 2000)  # Tests schnell halten
        p.start()
        self.addCleanup(p.stop)

    def test_roundtrip_and_wrong_password(self):
        blob = vault.encrypt("geheim 123 €", "richtiges-passwort")
        self.assertNotIn("geheim", blob)
        self.assertEqual(vault.decrypt(blob, "richtiges-passwort"), "geheim 123 €")
        with self.assertRaises(vault.VaultError):
            vault.decrypt(blob, "falsch")

    def test_agent_migrates_to_encrypted_and_leaves_no_plaintext(self):
        cfg = cfg_tmp()
        series = {s.name: synthetic_series(s.name, 1200, seed=4) for s in cfg.symbols}
        pos = {"n": 300}
        clock = lambda: series["BTC/USD"][pos["n"] - 1].ts + 120  # noqa: E731
        mk = lambda: LiveAgent(cfg, fetcher=lambda s, iv: series[s.name][: pos["n"]], clock=clock)  # noqa: E731
        a = mk()
        for _ in range(50):  # erst Klartext
            a.cycle(); pos["n"] += 1
        self.assertTrue(os.path.exists(cfg.state_file))
        with mock.patch.dict(os.environ, {vault.ENV: "testpasswort-123"}):
            a = mk()  # liest Klartext, schreibt verschlüsselt
            trades_before = len(a.broker.state.trades)
            for _ in range(400):
                a.cycle(); pos["n"] += 1
            self.assertGreater(len(a.broker.state.trades), trades_before)
            for p in (cfg.state_file, cfg.trades_file, cfg.cockpit_file):
                self.assertFalse(os.path.exists(p), p)
                self.assertTrue(os.path.exists(p + ".enc"), p)
                with open(p + ".enc") as f:
                    env = json.load(f)  # nur der Umschlag, keine Klartext-Felder
                self.assertEqual(set(env), {"v", "alg", "kdf", "iter", "salt", "iv", "ct"})
                self.assertNotIn('"symbol"', env["ct"])
            b = mk()  # Neustart mit Passwort setzt fort
            self.assertEqual(len(b.broker.state.trades), len(a.broker.state.trades))
            csv_text = vault.read_text(cfg.trades_file)
            self.assertEqual(csv_text.count("\n"), len(a.broker.state.trades) + 1)
        # Ohne Passwort: harter Abbruch statt leerem Konto
        with mock.patch.dict(os.environ, {vault.ENV: ""}):
            with self.assertRaises(vault.VaultError):
                mk()
        with mock.patch.dict(os.environ, {vault.ENV: "falsches-passwort"}):
            with self.assertRaises(vault.VaultError):
                mk()


# ---------------------------------------------------------------------------
# Time Machine (Monte Carlo) und Datenqualitäts-Wächter
# ---------------------------------------------------------------------------
import math  # noqa: E402
import random  # noqa: E402

from agent.engine import TradingEngine as _TE, unchanged_share  # noqa: E402
from agent.montecarlo import simulate  # noqa: E402


def random_walk(n=600, vol=0.001, seed=1):
    rng, p, cs = random.Random(seed), 100.0, []
    for i in range(n):
        o = p
        p = p * math.exp(rng.gauss(0, vol))
        cs.append(Candle(i * 900, o, max(o, p), min(o, p), p))
    return cs


class TestTimeMachine(unittest.TestCase):
    def test_matches_theory_for_random_walk(self):
        # Ohne Trend und ohne Kosten: Ziel bei +2R vor Stop bei -1R in ~1/3 der Fälle
        r = simulate(random_walk(), "long", 100, 99, 102, 0, 0, horizon=5000, paths=10000)
        self.assertAlmostEqual(r.p_tp, 1 / 3, delta=0.03)
        self.assertAlmostEqual(r.ev_r, 0.0, delta=0.12)

    def test_costs_make_expectation_negative(self):
        cs = random_walk()
        r = simulate(cs, "short", 100, 100.5, 99, 0.8, 0.005, horizon=96)
        self.assertLess(r.ev_r, -1.0)  # 1,6 % Kosten bei 0,5 % Risiko
        self.assertAlmostEqual(r.p_tp + r.p_sl + r.p_timeout, 1.0, places=6)

    def test_reproducible(self):
        cs = random_walk()
        a = simulate(cs, "long", 100, 99, 102, 0.1, 0, horizon=96, seed=7)
        b = simulate(cs, "long", 100, 99, 102, 0.1, 0, horizon=96, seed=7)
        self.assertEqual(a, b)

    def test_engine_skips_negative_expectation_and_records_it(self):
        cfg = cfg_tmp()
        cfg.timemachine.enabled = True
        cfg.timemachine.paths = 2000
        data = {s.name: synthetic_series(s.name, 2000, seed=11) for s in cfg.symbols}
        res = run_backtest(cfg, data)
        st_trades = res.trades
        self.assertTrue(all(t.mc_p_tp >= 0 for t in st_trades if t.exit_reason != "backtest_ende" or True))
        # Bei 0,8 % BTC-Gebühren rechnet sich auf Zufallsdaten kein BTC-Trade
        self.assertEqual([t for t in st_trades if t.symbol == "BTC/USD"], [])

    def test_export_has_time_machine_and_calibration(self):
        cfg = cfg_tmp()
        cfg.timemachine.enabled = True
        cfg.timemachine.paths = 1000
        cfg.timemachine.min_ev_r = -99  # alles durchlassen, damit Trades mit Vorhersage entstehen
        series = {s.name: synthetic_series(s.name, 1200, seed=5) for s in cfg.symbols}
        pos = {"n": 300}
        clock = lambda: series["BTC/USD"][pos["n"] - 1].ts + 120  # noqa: E731
        a = LiveAgent(cfg, fetcher=lambda s, iv: series[s.name][: pos["n"]], clock=clock)
        for _ in range(800):
            a.cycle(); pos["n"] += 1
        with open(cfg.cockpit_file) as f:
            d = json.load(f)
        tmi = d["time_machine"]
        self.assertTrue(tmi["enabled"])
        self.assertIsNotNone(tmi["last"])
        self.assertGreater(tmi["calibration"]["n"], 0)
        self.assertTrue(0 <= tmi["calibration"]["predicted_tp"] <= 1)
        self.assertTrue(any(e["kind"] == "tm" for e in d["events"]))


class TestDataQuality(unittest.TestCase):
    def test_frozen_market_is_not_traded(self):
        cs = random_walk(300)
        frozen = cs[:200] + [Candle(c.ts, cs[199].close, cs[199].close, cs[199].close, cs[199].close)
                             for c in cs[200:]]
        self.assertGreater(unchanged_share(frozen, 96), 0.9)
        self.assertLess(unchanged_share(cs, 96), 0.05)
        cfg = cfg_tmp()
        eng = _TE(cfg, PaperBroker(cfg, persist=False))
        sym = cfg.symbol("EUR/USD")
        import agent.engine as E
        orig = E.generate_signal
        E.generate_signal = lambda name, c, scfg: __import__("agent.strategy", fromlist=["Signal"]).Signal(
            name, "long", c[-1].close, c[-1].close * 0.99, c[-1].close * 1.02, "test")
        try:
            r = eng.on_bar(sym, frozen)
        finally:
            E.generate_signal = orig
        self.assertFalse(r.opened)
        self.assertEqual(r.skip_kind, "quality")


class TestQuietRuns(unittest.TestCase):
    def test_no_write_without_news_but_heartbeat_every_15_min(self):
        cfg = cfg_tmp()
        series = {s.name: synthetic_series(s.name, 600, seed=8) for s in cfg.symbols}
        pos = {"n": 300}
        t = {"now": series["BTC/USD"][299].ts + 960}
        a = LiveAgent(cfg, fetcher=lambda s, iv: series[s.name][: pos["n"]], clock=lambda: t["now"])
        a.cycle()
        m1 = os.path.getmtime(cfg.cockpit_file)
        gen1 = json.load(open(cfg.cockpit_file))["generated_at"]
        t["now"] += 300  # 5 Minuten später, keine neue Kerze
        a.cycle()
        self.assertEqual(json.load(open(cfg.cockpit_file))["generated_at"], gen1)
        t["now"] += 600  # nach 15 Minuten: Lebenszeichen wird geschrieben
        a.cycle()
        self.assertGreater(json.load(open(cfg.cockpit_file))["generated_at"], gen1)
        gen2 = json.load(open(cfg.cockpit_file))["generated_at"]
        pos["n"] += 1  # neue Kerze -> sofort schreiben
        t["now"] += 60
        a.cycle()
        self.assertGreater(json.load(open(cfg.cockpit_file))["generated_at"], gen2)
        self.assertGreater(m1, 0)


# ---------------------------------------------------------------------------
# Schutzregeln: Handelszeiten, Sperrzeiten, Kontobremse, Kurslücken, R-Kennzahlen
# ---------------------------------------------------------------------------
from agent.config import HoursConfig  # noqa: E402
from agent.gate import pro_stats  # noqa: E402
from agent.session import (Event, blackout, entry_time_ok, fx_open, load_calendar,  # noqa: E402
                           must_flatten, to_ts)


def utc(y, m, d, h=0, mi=0):
    return int(datetime(y, m, d, h, mi, tzinfo=timezone.utc).timestamp())


def cfg_guards():
    cfg = cfg_tmp()
    cfg.hours.enabled = True
    cfg.news.enabled = True
    cfg.risk.max_total_drawdown_pct = 10.0
    cfg.risk.max_same_direction = 1
    return cfg


def forced_signal(side="long"):
    """Ersetzt die Strategie durch ein festes Signal (für Tests der Regeln davor/danach)."""
    import agent.engine as E
    from agent.strategy import Signal
    orig = E.generate_signal
    k = 0.99 if side == "long" else 1.01
    E.generate_signal = lambda name, c, scfg: Signal(name, side, c[-1].close, c[-1].close * k,
                                                     c[-1].close * (2 - k) ** 2, "test")
    return lambda: setattr(E, "generate_signal", orig)


def hourly(start_ts, n, price=1.1):
    return [Candle(start_ts + i * 3600, price, price * 1.0005, price * 0.9995, price * (1 + 0.0001 * (i % 3)))
            for i in range(n)]


class TestGuards(unittest.TestCase):
    def test_fx_hours(self):
        h = HoursConfig()
        self.assertTrue(fx_open(utc(2026, 11, 13, 21, 59), h))    # Freitag kurz vor Schluss
        self.assertFalse(fx_open(utc(2026, 11, 13, 22, 0), h))
        self.assertFalse(fx_open(utc(2026, 11, 14, 12, 0), h))    # Samstag
        self.assertFalse(fx_open(utc(2026, 11, 15, 21, 59), h))   # Sonntag vor Öffnung
        self.assertTrue(fx_open(utc(2026, 11, 15, 22, 0), h))
        # Stundenkerze, die Freitag 18:00 schließt: Einstieg erlaubt; 19:00: zu nah am Schluss
        self.assertTrue(entry_time_ok(utc(2026, 11, 13, 17), 60, h))
        self.assertFalse(entry_time_ok(utc(2026, 11, 13, 18), 60, h))
        self.assertFalse(must_flatten(utc(2026, 11, 13, 19), 60, h))
        self.assertTrue(must_flatten(utc(2026, 11, 13, 20), 60, h))  # schließt 21:00, nächste wäre zu
        # Tageskerzen: nur Wochenend-Kerzen überspringen, nie zwangsschließen
        self.assertTrue(entry_time_ok(utc(2026, 11, 13), 1440, h))
        self.assertFalse(entry_time_ok(utc(2026, 11, 14), 1440, h))
        self.assertFalse(must_flatten(utc(2026, 11, 13), 1440, h))

    def test_calendar_times_and_blackout(self):
        self.assertEqual(to_ts("2026-12-09 14:00", "America/New_York"), utc(2026, 12, 9, 19))  # Winterzeit
        self.assertEqual(to_ts("2026-07-29 14:00", "America/New_York"), utc(2026, 7, 29, 18))  # Sommerzeit
        ev = [Event(utc(2026, 12, 17, 13, 15), "EZB", ["EUR/USD"])]
        self.assertIsNotNone(blackout(utc(2026, 12, 17, 12, 46), "EUR/USD", ev, 30, 60))
        self.assertIsNone(blackout(utc(2026, 12, 17, 12, 44), "EUR/USD", ev, 30, 60))
        self.assertIsNone(blackout(utc(2026, 12, 17, 13, 15), "GBP/USD", ev, 30, 60))
        self.assertIsNone(blackout(utc(2026, 12, 17, 14, 16), "EUR/USD", ev, 30, 60))
        here = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "kalender.json")
        cal = load_calendar(here)
        self.assertGreaterEqual(len(cal), 9)
        self.assertEqual(cal, sorted(cal, key=lambda e: e.ts))
        self.assertEqual(load_calendar("gibt-es-nicht.json"), [])

    def test_gap_fills_at_open_and_r_multiple(self):
        cfg = cfg_tmp()
        b = PaperBroker(cfg, persist=False)
        eur = cfg.symbol("EUR/USD")
        b.open(eur, "long", 50_000, 1.1000, 1.0980, 1.1040, ts=0)
        t = b.check_stops(eur, high=1.0960, low=1.0940, ts=1, open_=1.0950)   # Lücke unter den Stop
        self.assertEqual(t.exit_reason, "stop_loss")
        self.assertLess(t.exit, 1.0951)
        self.assertLess(t.r, -2.0)                       # Verlust größer als geplant (1 R)
        b.open(eur, "long", 50_000, 1.1000, 1.0980, 1.1040, ts=2)
        t2 = b.check_stops(eur, high=1.1005, low=1.0975, ts=3, open_=1.1000)  # normaler Stop
        self.assertAlmostEqual(t2.r, -1.0, delta=0.15)

    def test_account_brake_latches(self):
        cfg = cfg_guards()
        b = PaperBroker(cfg, persist=False)
        rm = RiskManager(cfg, b)
        eur = cfg.symbol("EUR/USD")
        self.assertFalse(rm.brake_active())
        self.assertTrue(rm.size(eur, 1.1, 1.09, "long").allowed)
        b.state.cash = 8_990.0                            # -10,1 % vom Höchststand
        self.assertTrue(rm.brake_active())
        self.assertFalse(rm.size(eur, 1.1, 1.09, "long").allowed)
        b.state.cash = 9_900.0                            # Erholung löst die Bremse nicht
        self.assertTrue(rm.brake_active())

    def test_same_dollar_direction_limit(self):
        cfg = cfg_guards()
        b = PaperBroker(cfg, persist=False)
        rm = RiskManager(cfg, b)
        b.open(cfg.symbol("EUR/USD"), "long", 10_000, 1.1, 1.09, 1.12, ts=0)
        gbp = cfg.symbol("GBP/USD")
        self.assertFalse(rm.size(gbp, 1.3, 1.29, "long").allowed)     # wieder gegen den Dollar
        self.assertTrue(rm.size(gbp, 1.3, 1.31, "short").allowed)
        self.assertFalse(rm.size(cfg.symbol("USD/JPY"), 150, 151, "short").allowed)  # auch gegen den Dollar

    def test_engine_weekend_news_and_late(self):
        cfg = cfg_guards()
        cfg.interval_min = 60
        eur = cfg.symbol("EUR/USD")
        restore = forced_signal("long")
        try:
            # Mittwoch: Einstieg; Sperrzeit: kein Einstieg; zu spät: kein Einstieg, wird gezählt
            wed = hourly(utc(2026, 11, 11, 0), 12)
            eng = TradingEngine(cfg, PaperBroker(cfg, persist=False))
            self.assertTrue(eng.on_bar(eur, wed).opened)
            eng = TradingEngine(cfg, PaperBroker(cfg, persist=False))
            eng.events = [Event(wed[-1].ts + 3600 + 600, "Test-Termin", [])]
            r = eng.on_bar(eur, wed)
            self.assertEqual((r.opened, r.skip_kind), (False, "news"))
            eng = TradingEngine(cfg, PaperBroker(cfg, persist=False))
            r = eng.on_bar(eur, wed, allow_entry=False, stale_reason="zu spät")
            self.assertEqual((r.opened, r.skip_kind, eng.broker.state.late_skipped), (False, "late", 1))
            # Freitag: Einstieg um 15:00 erlaubt, Position wird mit der Kerze bis 21:00 geschlossen
            fri = hourly(utc(2026, 11, 13, 0), 21)       # letzte Kerze 20:00–21:00
            eng = TradingEngine(cfg, PaperBroker(cfg, persist=False))
            self.assertTrue(eng.on_bar(eur, fri[:15]).opened)
            reasons = []
            for i in range(16, 22):
                reasons += [t.exit_reason for t in eng.on_bar(eur, fri[:i]).closed]
            self.assertEqual(reasons, ["wochenende"])
            self.assertFalse(eng.on_bar(eur, fri).opened)  # und kein neuer Einstieg mehr
            # Samstag (dünne Kurse mancher Quellen): gar kein Signal
            sat = hourly(utc(2026, 11, 14, 0), 12)
            eng = TradingEngine(cfg, PaperBroker(cfg, persist=False))
            self.assertIsNone(eng.on_bar(eur, sat).signal)
        finally:
            restore()

    def test_pro_stats(self):
        ts = []
        for r in [2.0, -1.0, -1.0, 2.0, -1.0, -1.0]:
            t = mk_trade(100 * r)
            t.r = r
            ts.append(t)
        s = pro_stats(ts)
        self.assertEqual(s["n"], 6)
        self.assertAlmostEqual(s["expectancy_r"], 0.0)
        self.assertAlmostEqual(s["payoff"], 2.0)
        self.assertAlmostEqual(s["kelly"], 1 / 3 - (2 / 3) / 2.0, places=3)   # = 0: kein Vorteil
        self.assertEqual(pro_stats([mk_trade(5)]), {"n": 0})
