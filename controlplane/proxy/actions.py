"""Applying the oversight decision to the actual response text -- the proxy's action layer.

``cascade/decision.py`` chooses an *action* (pass / annotate / escalate / block) from the calibrated
per-axis probabilities, but it deliberately stops short of ``AUTO_REPAIR`` because a faithful repair needs
a corrective generation -- something only the model/proxy layer has. This module is that layer. It takes the
engine's action plus the real text and retrieved context and produces the bytes that actually go back to the
caller, upgrading to ``AUTO_REPAIR`` only when a *faithful* fix is available:

- **PII redaction** -- if sensitive identifiers are present we can strip them deterministically (no model
  call, no hallucinated substitution), so a redacted copy is always a faithful repair.
- **Grounded correction** -- if a performance failure is contradicted by retrieved context, the honest fix
  is to answer *from the context*. In this offline build the "corrective generation" is a grounded
  substitution built from the retrieved chunk; in production it is a constrained re-generation against the
  same context. We label which one ran so nothing is oversold.

Everything else stays as the engine decided: escalate holds the response for a human (the brief's
"humans in the lead"), block refuses, annotate forwards with a caveat, pass forwards unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from controlplane.cascade.detectors.responsibility import redact_pii
from controlplane.core.types import Action, Axis, CascadeResult, PolicyProfile


@dataclass
class AppliedAction:
    """The outcome of applying oversight to a response: the final text and how it was reached."""

    action: Action
    text: str
    modified: bool
    note: str  # human-readable, goes on the receipt / UI


def _p(result: CascadeResult, axis: Axis) -> float:
    outcome = result.per_axis.get(axis)
    return outcome.p_fail if outcome else 0.0


def _grounded_correction(context: list[str]) -> tuple[str, dict[str, int]] | None:
    """Build a faithful answer from the retrieved context, or None when no faithful answer is available.

    Two conditions have to hold before an answer is rewritten, because a wrong repair is worse than no
    repair: the user is told the corrected text is authoritative, so we only claim that when it is.

    1. **The source must be unambiguous.** With several retrieved passages there is no way to know which one
       governs, and taking the first is arbitrary: on a knowledge base holding both an old and a current
       policy it silently reinstates the outdated one. Ambiguous sources are a decision for a person, so we
       return None and the response escalates instead.
    2. **The correction must be safe to send.** Retrieved context is source data -- a support ticket, a CRM
       record -- and can itself carry identifiers, so it is redacted first. Otherwise repairing a
       hallucination would turn a performance fix into a privacy leak on the very path meant to be safest.
    """
    chunks = [c.strip() for c in context if c and c.strip()]
    if len(chunks) != 1:
        return None  # nothing to ground on, or nothing that can be called authoritative
    return redact_pii(chunks[0])


def apply_action(
    candidate: str,
    result: CascadeResult,
    policy: PolicyProfile,
    retrieved_context: list[str],
) -> AppliedAction:
    """Turn the engine's decision into the response the caller actually receives.

    Priority order mirrors ``decision.py`` (responsibility first, it is the highest-stakes axis), but here we
    can *act on the text*, which is what unlocks ``AUTO_REPAIR``.
    """
    resp_p = _p(result, Axis.RESPONSIBILITY)
    perf_p = _p(result, Axis.PERFORMANCE)
    engine_action = result.action

    # 1. Hard responsibility violation -> do not forward the raw text. Redact so we can say exactly what was
    #    withheld without ever echoing the values, and refuse to serve the sensitive content.
    if resp_p >= policy.block_threshold:
        _, counts = redact_pii(candidate)
        kinds = ", ".join(sorted(counts)) if counts else "sensitive content"
        return AppliedAction(
            action=Action.BLOCK,
            text=(
                "I can't share that. This response was blocked by ControlPlane because it contained "
                f"{kinds}, which policy does not permit disclosing here."
            ),
            modified=True,
            note=f"blocked responsibility leak ({kinds})",
        )

    # 2. Strong performance failure a faithful grounded correction can fix -> AUTO_REPAIR from context.
    #    Only when the model is *probably wrong* (escalate-level), responsibility is clean enough to forward,
    #    and we have context to ground on. Milder uncertainty falls through to ANNOTATE (a caveat, not a
    #    rewrite) -- we only replace an answer when we are confident it is wrong.
    if (
        perf_p >= policy.escalate_threshold
        and resp_p < policy.escalate_threshold
        and engine_action == Action.ESCALATE
    ):
        # No faithful correction available (no source, or sources that disagree) falls through to the
        # engine's action below, which holds the response for a human rather than guessing.
        grounded = _grounded_correction(retrieved_context)
        if grounded is not None:
            correction, redacted = grounded
            note = "auto-repaired: answer replaced with the grounded fact from retrieved context"
            if redacted:
                note += f" ({', '.join(sorted(redacted))} redacted from the source)"
            return AppliedAction(
                action=Action.AUTO_REPAIR,
                text=correction,
                modified=True,
                note=note,
            )

    # 3. Otherwise honour the engine's action against the text.
    if engine_action == Action.BLOCK:
        return AppliedAction(
            action=Action.BLOCK,
            text="I can't share that. This response was blocked by ControlPlane policy.",
            modified=True,
            note="blocked by policy",
        )
    if engine_action == Action.ESCALATE:
        # Held for a human. If any PII is present, redact it in the copy a reviewer sees.
        redacted, counts = redact_pii(candidate)
        safe = redacted if counts else candidate
        return AppliedAction(
            action=Action.ESCALATE,
            text=(
                "This response was flagged for human review by ControlPlane (high-stakes and uncertain) "
                "and is awaiting an agent. — provisional draft below —\n" + safe
            ),
            modified=bool(counts),
            note="escalated to a human reviewer",
        )
    if engine_action == Action.ANNOTATE:
        return AppliedAction(
            action=Action.ANNOTATE,
            text=candidate + "\n\n(Note: ControlPlane flagged some uncertainty in this answer.)",
            modified=True,
            note="annotated with an uncertainty caveat",
        )
    return AppliedAction(action=Action.PASS, text=candidate, modified=False, note="passed unchanged")
