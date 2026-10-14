"""Claude als zweite Meinung: Jedes regelbasierte Signal wird vor der Ausführung
an Claude geschickt. Claude antwortet mit APPROVE/REJECT, Konfidenz und
Begründung. Die Regeln bleiben die Basis – Claude kann nur bremsen, nie selbst
Trades erfinden oder Positionsgrößen erhöhen.

Aktiv nur, wenn die Umgebungsvariable ANTHROPIC_API_KEY gesetzt ist.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

import requests

from .config import AIConfig

if TYPE_CHECKING:
    from .broker import PaperBroker
    from .data import Candle
    from .strategy import Signal

log = logging.getLogger("agent.ai")

API_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = """Du bist ein vorsichtiger Risiko-Prüfer für einen Paper-Trading-Agenten \
(Daytrading, BTC und Devisen, 15-Minuten-Kerzen). Ein regelbasiertes System hat ein Signal erzeugt. \
Deine einzige Aufgabe: entscheiden, ob dieses Signal ausgeführt werden soll.

Lehne ab (REJECT), wenn z.B.:
- der Kursverlauf seitwärts/choppy ist und der Crossover vermutlich ein Fehlsignal ist,
- die letzte Kerze ungewöhnlich groß ist (Spike, News-Reaktion) und der Einstieg schlecht wäre,
- der Stop im Verhältnis zur jüngsten Schwankung zu eng oder zu weit wirkt,
- die offenen Positionen bereits stark korreliertes Risiko darstellen (z.B. long EUR/USD und long GBP/USD).
Sonst genehmige (APPROVE). Sei knapp und sachlich.

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt, ohne weiteren Text:
{"decision": "APPROVE" oder "REJECT", "confidence": Zahl zwischen 0 und 1, "reason": "max. 25 Wörter auf Deutsch"}"""


@dataclass
class Review:
    decision: str
    confidence: float
    reason: str
    approved: bool
    error: bool = False


class AIReviewer:
    def __init__(self, cfg: AIConfig, api_key: Optional[str] = None):
        self.cfg = cfg
        self.api_key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY", "")
        self.calls = 0

    @property
    def active(self) -> bool:
        return bool(self.cfg.enabled and self.api_key)

    # ------------------------------------------------------------------
    def build_prompt(self, sig: "Signal", candles: List["Candle"], broker: "PaperBroker") -> str:
        recent = candles[-40:]
        rows = ["zeit_utc,open,high,low,close"]
        for c in recent:
            t = datetime.fromtimestamp(c.ts, tz=timezone.utc).strftime("%m-%d %H:%M")
            rows.append(f"{t},{c.open:.6g},{c.high:.6g},{c.low:.6g},{c.close:.6g}")
        positions = [
            {"symbol": p.symbol, "side": p.side, "entry": round(p.entry, 6), "bars_held": p.bars_held}
            for p in broker.state.positions.values()
        ]
        risk_pct = abs(sig.price - sig.stop) / sig.price * 100
        return (
            f"SIGNAL: {sig.side.upper()} {sig.symbol}\n"
            f"Einstieg ~{sig.price:.6g}, Stop {sig.stop:.6g} ({risk_pct:.2f}% entfernt), "
            f"Ziel {sig.take_profit:.6g}\n"
            f"Begründung der Regel: {sig.reason}\n"
            f"Indikatoren: {json.dumps(sig.indicators)}\n"
            f"Offene Positionen: {json.dumps(positions)}\n"
            f"Kontostand (Paper): {broker.equity():.2f}\n\n"
            f"Letzte {len(recent)} Kerzen (15 min):\n" + "\n".join(rows)
        )

    @staticmethod
    def parse(text: str) -> dict:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise ValueError(f"Kein JSON in Antwort: {text[:200]}")
        data = json.loads(m.group(0))
        decision = str(data.get("decision", "")).upper()
        if decision not in ("APPROVE", "REJECT"):
            raise ValueError(f"Ungültige Entscheidung: {decision}")
        conf = float(data.get("confidence", 0.0))
        return {"decision": decision, "confidence": max(0.0, min(1.0, conf)),
                "reason": str(data.get("reason", ""))[:300]}

    def _fallback(self, err: Exception) -> Review:
        log.warning("Claude-Prüfung fehlgeschlagen (%s) – fail_open=%s", err, self.cfg.fail_open)
        return Review("APPROVE" if self.cfg.fail_open else "REJECT", 0.0,
                      f"KI nicht erreichbar: {err}"[:200], self.cfg.fail_open, error=True)

    def _models(self) -> List[str]:
        seen, out = set(), []
        for m in [getattr(self, "working_model", None), self.cfg.model, *self.cfg.fallback_models]:
            if m and m not in seen:
                seen.add(m)
                out.append(m)
        return out

    def _call(self, prompt: str) -> str:
        last_err: Optional[Exception] = None
        for model in self._models():
            r = requests.post(
                API_URL,
                headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": model, "max_tokens": 300, "system": SYSTEM_PROMPT,
                      "messages": [{"role": "user", "content": prompt}]},
                timeout=self.cfg.timeout_s,
            )
            self.calls += 1
            if r.status_code == 404 or (r.status_code == 400 and "model" in r.text.lower()):
                last_err = RuntimeError(f"Modell {model} nicht verfügbar")
                log.warning("%s – versuche nächstes Modell", last_err)
                continue
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
            self.working_model = model
            return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
        raise last_err or RuntimeError("Kein Modell verfügbar")

    @property
    def model_name(self) -> str:
        return getattr(self, "working_model", None) or self.cfg.model

    def review(self, sig: "Signal", candles: List["Candle"], broker: "PaperBroker") -> Review:
        prompt = self.build_prompt(sig, candles, broker)
        try:
            d = self.parse(self._call(prompt))
        except Exception as e:
            return self._fallback(e)
        approved = d["decision"] == "APPROVE" and d["confidence"] >= self.cfg.min_confidence
        return Review(d["decision"], d["confidence"], d["reason"], approved)
