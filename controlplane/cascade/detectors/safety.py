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

from controlplane.cascade.detectors.abstention import is_abstention
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


# Phrases that only appear when a model has actually disclosed its own configuration.
_DISCLOSURE = re.compile(
    r"\b(my (system )?(prompt|instructions) (is|are)"
    # A support assistant naming the underlying model identity has disclosed its configuration; this is
    # the shape a leaked system prompt almost always opens with.
    r"|(you|i) (are|am) (chatgpt|claude|gemini|an ai (language )?model|a large language model)"
    r"|developer mode (is )?(enabled|activated|on)"
    r"|here (is|are) my (system )?(prompt|instructions))\b",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[A-Za-z_]{5,}")


def _payload_echo(response: str, injected: str, legitimate: str) -> list[str]:
    """Distinctive terms the attacker asked for that the response repeated back.

    The reliable tell for a successful injection is not that the model said something unsafe, it is that the
    model echoed the attacker's payload: a canary token, a demanded phrase, wording that exists nowhere in
    the legitimate passages. Comparing against the clean context is what keeps ordinary vocabulary out.
    """
    clean = {w.lower() for w in _WORD_RE.findall(legitimate)}
    said = {w.lower() for w in _WORD_RE.findall(response)}
    asked = {w.lower() for w in _WORD_RE.findall(injected)}
    # Terms unique to the injected span, ignoring the instruction verbs any such note would contain.
    boilerplate = {"ignore", "previous", "instructions", "system", "note", "assistant", "important",
                   "disregard", "above", "instead", "reply", "answer", "your", "append", "text", "words"}
    distinctive = (asked - clean - boilerplate)
    return sorted(distinctive & said)


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
        # A poisoned passage usually hides *inside* a genuine document, so the split has to be finer than
        # per-document: only the lines carrying an override marker are the attacker's, and the rest of that
        # same document is still legitimate source text.
        sources: list[tuple[str, str]] = [("user_prompt", ctx.prompt or "")]
        sources += [("retrieved_document", c or "") for c in (ctx.retrieved_context or [])]

        attacker_lines: list[str] = []
        clean_lines: list[str] = []
        vectors: set[str] = set()
        hits = 0
        for where, text in sources:
            # An injected note runs on for several lines and is appended after the genuine content, so once
            # a line in a passage is tainted the rest of that passage is treated as the attacker's too.
            # Otherwise the demanded payload, which sits on the line *after* the override phrase, would be
            # counted as legitimate source text and the echo would go unnoticed.
            tainted_from_here = False
            for line in re.split(r"[\n.]+", text):
                if not line.strip():
                    continue
                found = len(_INJECTION.findall(line))
                if found:
                    hits += found
                    tainted_from_here = True
                    vectors.add(where)
                (attacker_lines if tainted_from_here else clean_lines).append(line)
        if not hits:
            return 0.0, {"injection": False}

        detail = {
            "injection": True,
            "markers": hits,
            "vector": "user_prompt" if "user_prompt" in vectors else "retrieved_document",
        }
        confidence = 1.0 - 0.35 ** hits  # each distinct override phrasing compounds the confidence

        # An attempt is not an outcome. The axis measures whether *this response* is a responsibility
        # failure, and the two safe outcomes look very different: the model may refuse outright, or it may
        # quietly ignore the injected instruction and answer the real question. Both are correct behaviour,
        # and blocking either replaces a good answer with a scare notice. The attempt stays on the receipt
        # as evidence in every case, which is what the audit trail is for.
        response = (ctx.response or "").strip()
        if not response:
            detail["outcome"] = "pre_response_gate"  # ingress check, before there is a response to judge
            return confidence, detail

        if is_abstention(response):
            detail["outcome"] = "refused"
            detail["note"] = "the model declined, so the response is safe to forward"
            return 0.0, detail

        # Did the model carry out the injected instruction? The tell is an echo of the attacker's payload:
        # wording demanded by the poisoned lines that appears nowhere in the legitimate ones.
        echoed = _payload_echo(response, " ".join(attacker_lines), " ".join(clean_lines))
        disclosed = bool(_DISCLOSURE.search(response))
        if not echoed and not disclosed:
            detail["outcome"] = "ignored"
            detail["note"] = "the model answered the real question and did not act on the injected instruction"
            return 0.0, detail

        # Direct evidence that the attack landed outweighs how many override phrases were counted: one
        # clean injection that the model obeyed is a confirmed responsibility failure, not a maybe.
        detail["outcome"] = "complied"
        if echoed:
            detail["echoed_payload"] = echoed[:5]
        if disclosed:
            detail["disclosed_configuration"] = True
        return max(confidence, 0.95), detail


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
