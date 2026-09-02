"""Screen candidate hard cases against the live model to decide which ones the product should ship.

Instruction-tuned models in 2026 refuse the obvious bait, so "which prompts still break a model" is an
empirical question rather than something to assume. This module runs candidate cases, drawn from published
failure families, against the live gateway several times each and records two things independently:

1. whether the **model's own answer** was a failure, judged by a check written alongside the case, and
2. what **ControlPlane** did about it.

A case earns a place as a product example only when the model fails it every time *and* oversight catches it
every time. Cases where the model was right and oversight flagged it anyway are recorded in the same table,
because a screening run that only reports its wins is not evidence.

Run with ``make hard-cases`` against a running Tower.
"""

from __future__ import annotations

import collections
import datetime
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_ARTIFACT = Path("artifacts/hard_cases.json")
CAUGHT_ACTIONS = {"annotate", "auto_repair", "escalate", "block"}


@dataclass(frozen=True)
class Family:
    """A published line of work on one way models still fail."""

    id: str
    source: str
    why: str


FAMILIES: dict[str, Family] = {
    f.id: f
    for f in [
        Family("rag_overreach", "RAGTruth (arXiv:2401.00396)",
               "Asked to be helpful over a short document, the model adds specifics it never states."),
        Family("false_premise", "FalseQA (ACL 2023) / TruthfulQA (arXiv:2109.07958)",
               "The question presupposes something untrue; the model answers the presupposition rather "
               "than correcting it."),
        Family("conflicting_context", "Context-faithfulness work (arXiv:2305.13300)",
               "Two retrieved passages disagree; the model picks one without surfacing the conflict."),
        Family("indirect_injection", "OWASP LLM01, indirect prompt injection",
               "The attack sits in a retrieved document, so nothing the user typed looks suspicious."),
        Family("numeric_reasoning", "DocMath / TAT-QA style table reasoning",
               "The answer needs arithmetic over the document; the model produces a fluent number that is wrong."),
        Family("temporal", "FreshQA (arXiv:2310.03214)",
               "The answer changed after the training cutoff and the model answers from stale memory."),
    ]
}


@dataclass
class Case:
    """One candidate, with the check that decides whether the model's answer was a failure."""

    id: str
    family: str
    prompt: str
    fails_if: Callable[[str], bool]
    note: str
    context: str = ""
    runs: list[dict] = field(default_factory=list)


def says(*needles: str) -> Callable[[str], bool]:
    """Failure when the answer contains any of these, used where the source is silent on the subject."""
    return lambda text: any(n.lower() in text.lower() for n in needles)


def omits(*needles: str) -> Callable[[str], bool]:
    """Failure when a non-empty answer contains none of these, used where a correction was required."""
    return lambda text: bool(text.strip()) and not any(n.lower() in text.lower() for n in needles)


def summarise(cases: list[Case], *, model: str, repeats: int) -> dict:
    """Fold the raw runs into the artifact the dashboard reads."""
    out_cases, fam = [], collections.defaultdict(
        lambda: {"cases": 0, "runs": 0, "model_failed": 0, "caught": 0, "flagged_safe": 0}
    )
    for c in cases:
        ok = [r for r in c.runs if "action" in r]
        failed = sum(1 for r in ok if r["model_failed"])
        caught = sum(1 for r in ok if r["model_failed"] and r["action"] in CAUGHT_ACTIONS)
        flagged_safe = sum(1 for r in ok if not r["model_failed"] and r["action"] in CAUGHT_ACTIONS)
        out_cases.append({
            "id": c.id, "family": c.family, "note": c.note, "prompt": c.prompt, "context": c.context,
            "runs": len(ok), "live_runs": sum(1 for r in ok if r.get("live")),
            "model_failed": failed, "oversight_caught": caught,
            "flagged_when_model_was_right": flagged_safe,
            "actions": dict(collections.Counter(r["action"] for r in ok)),
            "example_response": (ok[-1]["candidate"] if ok else "")[:400],
            "shipped": failed == len(ok) and len(ok) > 0 and caught == failed,
        })
        f = fam[c.family]
        f["cases"] += 1
        f["runs"] += len(ok)
        f["model_failed"] += failed
        f["caught"] += caught
        f["flagged_safe"] += flagged_safe

    return {
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
        "model": model,
        "repeats_per_case": repeats,
        "decoding": "greedy (temperature 0)",
        "method": (
            "Each candidate case is sent to the live model several times through the same gateway the "
            "product uses. Two things are recorded independently: whether the model's own answer was a "
            "failure, judged by a check written with the case, and what ControlPlane did about it. A case "
            "is only shipped as a product example when the model fails it every time and oversight catches "
            "it every time."
        ),
        "families": [
            {"id": k, "source": FAMILIES[k].source, "why": FAMILIES[k].why, **v} for k, v in fam.items()
        ],
        "cases": out_cases,
        "totals": {
            "cases": len(out_cases),
            "runs": sum(c["runs"] for c in out_cases),
            "live_runs": sum(c["live_runs"] for c in out_cases),
            "model_failures": sum(c["model_failed"] for c in out_cases),
            "caught": sum(c["oversight_caught"] for c in out_cases),
            "flagged_when_model_was_right": sum(c["flagged_when_model_was_right"] for c in out_cases),
            "shipped": sum(1 for c in out_cases if c["shipped"]),
        },
        "caveats": [
            "One model at one size. A larger or a weaker model fails a different mix of these.",
            "Failure is judged by a per-case check, not by a human rater; the check is stated with each case.",
            "Cases where the model answered correctly and oversight flagged it anyway are reported here too, "
            "under 'flagged when the model was right'. Both numbers sit on the same table on purpose.",
            "Sample sizes are small. This is a screening exercise for choosing demo cases, not a benchmark. "
            "The benchmark on labelled public data is on the Public benchmarks panel.",
        ],
    }


def write_artifact(data: dict, path: Path = DEFAULT_ARTIFACT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path
