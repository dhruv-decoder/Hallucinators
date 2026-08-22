"""Demo: the model-backed PII detector catches leaks the regex heuristic cannot.

Sends the same response -- one that leaks a person's name and location but no structured identifier --
through two engines: the default (regex PII only) and one with the Presidio NER detector added. The regex
engine sees nothing and forwards the leak; the model-backed engine flags it and escalates.

Requires the ``[ml]`` extra and the spaCy model (see pyproject / README). Run with
``python -m controlplane.demo.run_ml_pii``.
"""

from __future__ import annotations

from controlplane.cascade.detectors import (
    GroundednessHeuristicDetector,
    ModelOverkillDetector,
    OverconfidenceDetector,
    RegexPiiDetector,
    SelfConsistencyDetector,
    SemanticCacheDetector,
)
from controlplane.cascade.detectors.responsibility_ml import PresidioPiiDetector
from controlplane.cascade.engine import CascadeEngine
from controlplane.core.types import Axis, PolicyProfile, RequestContext


def _engine(with_ml: bool) -> CascadeEngine:
    detectors = [
        OverconfidenceDetector(),
        GroundednessHeuristicDetector(),
        SelfConsistencyDetector(),
        RegexPiiDetector(),
    ]
    if with_ml:
        detectors.append(PresidioPiiDetector())
    cost = [ModelOverkillDetector(), SemanticCacheDetector()]
    return CascadeEngine(detectors, cost, PolicyProfile(id="support_bot@IN@balanced"))


def main() -> None:
    ctx = RequestContext(
        request_id="pii-freetext",
        use_case="support_bot",
        prompt="Who filed the complaint and where are they based?",
        response="The complaint was filed by Sarah Chen, who lives in Mumbai.",
        model="gpt-4o",
        input_tokens=40,
        output_tokens=20,
    )

    print("Model-backed PII detector vs regex heuristic")
    print("=" * 60)
    print(f"Response under review: {ctx.response!r}\n")
    for label, with_ml in [("regex only (default)", False), ("+ Presidio NER (ml)", True)]:
        result = _engine(with_ml).run(ctx)
        resp = result.per_axis.get(Axis.RESPONSIBILITY)
        p = resp.p_fail if resp else 0.0
        entities = {}
        for sig in result.signals:
            if sig.axis == Axis.RESPONSIBILITY:
                entities.update(sig.detail.get("entities", {}))
        print(f"  {label:22s} -> responsibility p_fail={p:.3f}  action={result.action.value}")
        print(f"  {'':22s}    entities found: {entities or 'none'}")
    print("\nThe name and location are free-text PII: the regex detector is blind to them,")
    print("so without the model the leak is forwarded. The NER detector catches and escalates it.")


if __name__ == "__main__":
    main()
