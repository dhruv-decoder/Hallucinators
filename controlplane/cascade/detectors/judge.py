"""The T2 LLM-as-judge tier -- the expensive check the VoI rule buys only for the uncertain tail.

This is the point of the whole cascade: most responses are resolved by free T0 / cheap T1 signals, and a
real, costly model verification runs only when the value of its information beats its dollar+latency cost --
i.e. on the ~1-3% of responses where cheaper checks left the axis genuinely uncertain. 2026 evidence is that a
well-prompted general LLM judge is competitive with (often better than) fine-tuned detectors, so it is the
right thing to escalate *to*, not to run on everything.

Two backends, auto-detected, so it works both in a real deployment and on a laptop:

- **litellm** -- any hosted provider (OpenAI/Anthropic/Bedrock/…) when a provider key is set.
- **Ollama**  -- a local open-weights model, no API key, when an Ollama server is reachable.

If neither is available the detector is simply absent (the factory does not add it) and the cascade stops at
T1 -- honestly, no fabricated judge. Cost and latency are real and feed both the stopping rule and the P&L.
"""

from __future__ import annotations

import importlib.util
import os
import re
import socket

from controlplane.cascade.detectors.base import Detector
from controlplane.core.types import Axis, RequestContext, Tier
from controlplane.pnl.pricing import Pricing

_NUM = re.compile(r"\d+")


_PROVIDER_KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AZURE_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY")


def _provider_key_present() -> bool:
    return any(os.environ.get(k) for k in _PROVIDER_KEYS)


def _default_judge_model() -> str:
    """Pick a sensible free/cheap judge model from whichever provider key is set (Groq is free & fast)."""
    if os.environ.get("CONTROLPLANE_JUDGE_MODEL"):
        return os.environ["CONTROLPLANE_JUDGE_MODEL"]
    if os.environ.get("GROQ_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        return "groq/llama-3.3-70b-versatile"  # free tier via Groq, litellm-routed
    return "gpt-4o-mini"


def _ollama_host() -> str:
    return os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")


def _ollama_reachable() -> bool:
    host = _ollama_host().replace("http://", "").replace("https://", "")
    hostname, _, port = host.partition(":")
    try:
        with socket.create_connection((hostname or "localhost", int(port or 11434)), timeout=0.2):
            return True
    except OSError:
        return False


class LlmJudgeDetector(Detector):
    """A costly, high-information LLM verification of a response, gated by the VoI stopping rule (T2)."""

    name = "llm_judge"
    axis = Axis.PERFORMANCE
    tier = Tier.T2
    informativeness = 0.9

    def __init__(self, model: str | None = None, backend: str | None = None) -> None:
        self.backend = backend or self._pick_backend()
        if model:
            self.model = model
        elif self.backend == "ollama":
            self.model = os.environ.get("CONTROLPLANE_JUDGE_MODEL", "llama3.1")
        else:
            self.model = _default_judge_model()
        # Real cost/latency the stopping rule weighs. Local (ollama) is ~$0; a hosted judge is priced.
        self.est_cost_usd = 0.0 if self.backend == "ollama" else Pricing().cost(self.model, 400, 30)
        self.est_latency_ms = 500.0

    @staticmethod
    def _pick_backend() -> str:
        forced = os.environ.get("CONTROLPLANE_JUDGE_BACKEND")
        if forced:
            return forced
        if importlib.util.find_spec("litellm") and _provider_key_present():
            return "litellm"
        if _ollama_reachable():
            return "ollama"
        return "none"

    @classmethod
    def available(cls) -> tuple[bool, str]:
        """(usable, backend). Cheap to call -- no model load, only a key check / short socket probe."""
        backend = cls._pick_backend()
        return backend not in ("none", ""), backend

    def _prompt(self, ctx: RequestContext) -> str:
        source = "\n".join(ctx.retrieved_context) if ctx.retrieved_context else "(no source provided)"
        return (
            "You are a strict verification judge. Rate how likely the ANSWER is INCORRECT or UNSUPPORTED "
            "given the SOURCE, from 0 (fully supported/correct) to 100 (clearly wrong/unsupported). "
            "Reply with ONLY the integer.\n\n"
            f"QUESTION: {ctx.prompt}\nSOURCE: {source}\nANSWER: {ctx.response}\nSCORE:"
        )

    def _call_backend(self, prompt: str) -> str:
        """Return the judge model's raw reply. Isolated so tests can monkeypatch it without a network call."""
        if self.backend == "litellm":
            import litellm

            resp = litellm.completion(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=8,
            )
            return resp["choices"][0]["message"]["content"]
        if self.backend == "ollama":
            import httpx

            r = httpx.post(
                f"{_ollama_host()}/api/chat",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"temperature": 0},
                },
                timeout=30.0,
            )
            r.raise_for_status()
            return r.json()["message"]["content"]
        raise RuntimeError("no judge backend available")

    def assess(self, ctx: RequestContext) -> tuple[float, dict]:
        try:
            raw = self._call_backend(self._prompt(ctx))
        except Exception as exc:  # noqa: BLE001 - a judge failure must not break the pipeline
            return 0.0, {"abstained": True, "reason": f"judge unavailable: {exc}", "backend": self.backend}
        match = _NUM.search(raw or "")
        if not match:
            return 0.0, {"abstained": True, "reason": "unparseable judge reply", "raw": (raw or "")[:60]}
        score = max(0.0, min(1.0, int(match.group(0)) / 100.0))
        return score, {"backend": self.backend, "model": self.model, "judge_raw": (raw or "").strip()[:20]}
