"""Responsibility-axis safety detectors: prompt injection (ingress) and unsafe content (egress).

The 2026 production consensus is that safety is a *layered stack* of distinct classifiers, not one model:
prompt-injection / jailbreak detection, PII leakage, and unsafe-content moderation are separate failure
modes that need separate defences. These two T0 detectors add the injection and unsafe-content layers next
to the existing PII detector, all on the responsibility axis (they combine via the engine's noisy-OR, so any
one firing raises the axis probability).

Both are deliberately lightweight, specific heuristics with a documented upgrade path -- they are honest T0
signals, not the fine-tuned models they stand in for:

- ``PromptInjectionDetector`` -> Meta **PromptGuard-2** (mDeBERTa) / Llama Firewall's alignment check.
- ``UnsafeContentDetector``   -> **Llama Guard 4** / **ShieldGemma-2** / Qwen3Guard policy classifiers.

Kept specific on purpose so ordinary support-bot / copilot traffic scores 0 and only real attacks or unsafe
generations light the axis up.
"""

from __future__ import annotations

import re

from controlplane.cascade.detectors.base import Detector
from controlplane.core.types import Axis, RequestContext, Tier

# Injection / jailbreak markers. These target the *instruction-override* shape of an attack (telling the model
# to ignore its rules, reveal its system prompt, or exfiltrate) rather than any specific wording, so paraphrases
# still hit while normal questions do not.
_INJECTION = re.compile(
    r"\b(ignore (all |your )?(previous|prior|above) (instructions|prompts?|rules)"
    r"|disregard (the |your )?(above|previous|system)"
    r"|reveal (your |the )?(system|hidden) (prompt|instructions?)"
    r"|what (is|are) your (system prompt|instructions|rules)"
    r"|you are now|act as (an? )?(unrestricted|jailbroken|DAN)"
    r"|developer mode|do anything now"
    r"|print (your |the )?(system prompt|instructions)"
    r"|exfiltrate|leak (the |your )?(secret|api key|credentials?))\b",
    re.IGNORECASE,
)

# Unsafe-content markers grouped by policy category. Intentionally narrow; a real deployment uses a policy
# model. We look for *instructional* unsafe requests/answers ("how to build a bomb"), not mere mention.
_UNSAFE = {
    "weapons": re.compile(
        r"\b(how to (make|build|synthesi[sz]e) (a )?(bomb|explosive|nerve agent|bioweapon))\b", re.I
    ),
    "self_harm": re.compile(
        r"\b(how to (kill|hurt|harm) (myself|yourself)|ways to (commit suicide|self-harm))\b", re.I
    ),
    "illicit": re.compile(
        r"\b(how to (make|cook|synthesi[sz]e) (meth|methamphetamine|fentanyl|heroin))\b", re.I
    ),
    "malware": re.compile(
        r"\b(write (me )?(a )?(ransomware|keylogger|malware|virus)|steal (someone'?s )?password)\b", re.I
    ),
}


class PromptInjectionDetector(Detector):
    """Flag prompt-injection / jailbreak attempts in the incoming prompt (and any tool observations).

    Injection is an ingress attack that leads to the responsibility failures downstream (leaks, unsafe output),
    so it belongs on the responsibility axis. It reads the *prompt* rather than the response -- it is a
    pre-response gate. Upgrade path: PromptGuard-2.
    """

    name = "prompt_injection"
    axis = Axis.RESPONSIBILITY
    tier = Tier.T0
    est_cost_usd = 0.0
    est_latency_ms = 1.0
    informativeness = 0.55

    def assess(self, ctx: RequestContext) -> tuple[float, dict]:
        # Check the prompt plus any tool observations an agent fed back in (indirect injection).
        haystack = " ".join([ctx.prompt or "", *(ctx.retrieved_context or [])])
        hits = _INJECTION.findall(haystack)
        if not hits:
            return 0.0, {"injection": False}
        # Each distinct override phrasing compounds the confidence (capped below 1).
        score = 1.0 - 0.35 ** len(hits)
        return score, {"injection": True, "markers": len(hits)}


class UnsafeContentDetector(Detector):
    """Flag unsafe content (weapons / self-harm / illicit / malware) in the response.

    An egress moderation layer: it reads the candidate *response*. Narrow, category-tagged heuristics stand in
    for a policy model. Upgrade path: Llama Guard 4 / ShieldGemma-2.
    """

    name = "unsafe_content"
    axis = Axis.RESPONSIBILITY
    tier = Tier.T0
    est_cost_usd = 0.0
    est_latency_ms = 1.0
    informativeness = 0.6

    def assess(self, ctx: RequestContext) -> tuple[float, dict]:
        text = " ".join([ctx.response or "", ctx.prompt or ""])
        categories = [name for name, pattern in _UNSAFE.items() if pattern.search(text)]
        if not categories:
            return 0.0, {"unsafe": False}
        # Any unsafe category is high-stakes; multiple categories saturate.
        score = 1.0 - 0.15 ** len(categories)
        return score, {"unsafe": True, "categories": categories}
