"""Leakage-safe deterministic splits for paired public hallucination datasets."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from controlplane.eval.dataset import LabeledExample


def source_group(request_id: str) -> str:
    """Group paired HaluEval rows (``...-ok`` / ``...-hallu``) into one source item."""
    rid = str(request_id or "")
    if rid.startswith("halueval-"):
        parts = rid.split("-")
        if len(parts) >= 3:
            return "-".join(parts[:2])
    return rid


def grouped_split(
    dataset: Sequence[LabeledExample], fractions: tuple[float, float, float] = (0.6, 0.2, 0.2)
) -> tuple[list[LabeledExample], list[LabeledExample], list[LabeledExample]]:
    """Deterministically split by source group so paired examples never cross partitions."""
    if len(fractions) != 3 or abs(sum(fractions) - 1.0) > 1e-9:
        raise ValueError("fractions must contain three values summing to 1")
    groups: dict[str, list[LabeledExample]] = defaultdict(list)
    for ex in dataset:
        groups[source_group(ex.ctx.request_id)].append(ex)
    ordered = sorted(groups.items(), key=lambda kv: kv[0])
    n_groups = len(ordered)
    n_first = int(n_groups * fractions[0])
    n_second = int(n_groups * (fractions[0] + fractions[1]))
    first = [ex for _, rows in ordered[:n_first] for ex in rows]
    second = [ex for _, rows in ordered[n_first:n_second] for ex in rows]
    third = [ex for _, rows in ordered[n_second:] for ex in rows]
    return first, second, third
