import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.ai_reviewer import AIReviewer, Review  # noqa: E402
from agent.backtest import run_backtest  # noqa: E402
from agent.broker import PaperBroker  # noqa: E402
from agent.config import AIConfig, Config  # noqa: E402
from agent.data import Candle, synthetic_series  # noqa: E402
from agent.engine import TradingEngine  # noqa: E402
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


class TestStrategy(unittest.TestCase):
    def test_long_signal_on_cross_in_uptrend(self):
        cfg = Config().strategy
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
        trades = [mk_trade(30) for _ in range(30)] + [mk_trade(-20) for _ in range(25)]  # PF 1.8
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
