"""The T2 LLM-as-judge tier -- the expensive check the VoI rule buys only for the uncertain tail.

This is the point of the whole cascade: most responses are resolved by free T0 / cheap T1 signals, and a
real, costly model verification runs only when the value of its information beats its dollar+latency cost --
i.e. on the ~1-3% of responses where cheaper checks left the axis genuinely uncertain. 2026 evidence is that a
well-prompted general LLM judge is competitive with (often better than) fine-tuned detectors, so it is the
right thing to escalate *to*, not to run on everything.

Backends are OpenAI-compatible and called directly over httpx (no heavy SDK):

- **Groq** -- free tier, OpenAI-compatible, very fast. Default judge model ``openai/gpt-oss-120b`` (verified
  ~0.7s and correct on the verification prompt). Set ``GROQ_API_KEY`` (a local ``.env`` is auto-loaded).
- **OpenAI** -- any GPT model when ``OPENAI_API_KEY`` is set.
- **Ollama** -- a local open-weights model (default ``llama3.1:8b``) when an Ollama server is reachable.

If none is available the detector is simply absent (the factory does not add it) and the cascade stops at
T1 -- honestly, no fabricated judge. Cost and latency are real and feed both the stopping rule and the P&L.
"""

from __future__ import annotations

import os
import re
import socket

from controlplane.cascade.detectors.abstention import split_abstention
from controlplane.cascade.detectors.base import Detector
from controlplane.core.types import Axis, RequestContext, Tier
from controlplane.pnl.pricing import Pricing

_NUM = re.compile(r"\d+")

# backend -> (base_url, api-key env var, default model). OpenAI-compatible /chat/completions.
_HTTP_BACKENDS: dict[str, tuple[str, str, str]] = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY", "openai/gpt-oss-120b"),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY", "gpt-4o-mini"),
}


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


def _pick_backend() -> str:
    """Choose a judge backend: forced override, then Groq/OpenAI by key, then a local Ollama, else none."""
    forced = os.environ.get("CONTROLPLANE_JUDGE_BACKEND")
    if forced:
        return forced
    for name, (_base, keyvar, _model) in _HTTP_BACKENDS.items():
        if os.environ.get(keyvar):
            return name
    if _ollama_reachable():
        return "ollama"
    return "none"


class LlmJudgeDetector(Detector):
    """A costly, high-information LLM verification of a response, gated by the VoI stopping rule (T2)."""

    name = "llm_judge"
    axis = Axis.PERFORMANCE
    tier = Tier.T2
    informativeness = 0.9
    construct = "groundedness"  # asks the same question as the groundedness tiers, with the best evidence

    def __init__(self, model: str | None = None, backend: str | None = None) -> None:
        self.backend = backend or _pick_backend()
        if model:
            self.model = model
        elif os.environ.get("CONTROLPLANE_JUDGE_MODEL"):
            self.model = os.environ["CONTROLPLANE_JUDGE_MODEL"]
        elif self.backend in _HTTP_BACKENDS:
            self.model = _HTTP_BACKENDS[self.backend][2]
        else:
            self.model = "llama3.1:8b"
        # Real cost the stopping rule weighs: Groq free tier and local Ollama are ~$0; OpenAI is priced.
        self.est_cost_usd = Pricing().cost(self.model, 400, 30) if self.backend == "openai" else 0.0
        self.est_latency_ms = 800.0

    @classmethod
    def available(cls) -> tuple[bool, str]:
        """(usable, backend). Cheap -- a key check / short socket probe, no model load."""
        backend = _pick_backend()
        return backend not in ("none", ""), backend

    def _prompt(self, ctx: RequestContext, answer: str | None = None) -> str:
        source = "\n".join(ctx.retrieved_context) if ctx.retrieved_context else "(no source provided)"
        answer = ctx.response if answer is None else answer
        return (
            "You are a strict verification judge. Score ONLY the factual claims the ANSWER actually makes, "
            "against the SOURCE. Reply with ONLY an integer from 0 to 100.\n"
            "0 = every claim it makes is supported by the SOURCE.\n"
            "100 = it states something the SOURCE contradicts, or a specific fact the SOURCE does not "
            "contain.\n"
            "Score LOW (near 0) when the answer is merely incomplete, declines to answer, says the "
            "information is not available, or corrects a false premise in the QUESTION -- none of those is "
            "a factual error. Judge accuracy, not helpfulness.\n\n"
            f"QUESTION: {ctx.prompt}\nSOURCE: {source}\nANSWER: {answer}\nSCORE:"
        )

    def _call_backend(self, prompt: str) -> str:
        """Return the judge model's raw reply. Isolated so tests can monkeypatch it without a network call."""
        import httpx

        if self.backend in _HTTP_BACKENDS:
            base, keyvar, _ = _HTTP_BACKENDS[self.backend]
            r = httpx.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {os.environ.get(keyvar, '')}"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1024,
                    "temperature": 0,
                },
                timeout=30.0,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"].get("content") or ""
        if self.backend == "ollama":
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
        # The judge is the top tier of the *groundedness* construct, so it follows the same rule as the
        # tiers below it: a response that declines to answer makes no claim, and "unsupported" is not the
        # same as "wrong". Without this the judge scores a correct refusal ~0.95 and, because it supersedes
        # the cheaper tiers, single-handedly turns the safest possible behaviour into an auto-repair.
        claim, declined = split_abstention(ctx.response or "")
        if declined and not claim:
            return 0.0, {"abstained": True, "reason": "response declined to answer; nothing to verify"}
        try:
            raw = self._call_backend(self._prompt(ctx, answer=claim or ctx.response))
        except Exception as exc:  # noqa: BLE001 - a judge failure must not break the pipeline
            return 0.0, {"abstained": True, "unavailable": True,
                         "reason": f"judge unavailable: {exc}", "backend": self.backend}
        match = _NUM.search(raw or "")
        if not match:
            return 0.0, {"abstained": True, "reason": "unparseable judge reply", "raw": (raw or "")[:60]}
        score = max(0.0, min(1.0, int(match.group(0)) / 100.0))
        return score, {"backend": self.backend, "model": self.model, "judge_raw": (raw or "").strip()[:20]}
