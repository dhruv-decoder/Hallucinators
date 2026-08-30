"""Loaders for real, public hallucination benchmarks -- the honest upgrade of the synthetic seed set.

These turn published RAG-hallucination datasets into the harness's ``LabeledExample`` shape so ``make eval``
can report precision/recall on *real* data, not a hand-built seed:

- **HaluEval (QA)** -- 10k open-domain QA items, each with a knowledge passage plus a correct and a
  hallucinated answer. We emit two examples per item: the correct answer (grounded -> performance label False)
  and the hallucinated answer (ungrounded -> performance label True), both grounded against the knowledge.
- **RAGTruth** -- 18k span-level RAG annotations (query + retrieved docs + LLM answer + hallucination label).

They need the optional ``datasets`` library (``pip install datasets``) and a one-time download from the
Hugging Face hub; nothing is bundled, so the repo stays light and license-clean. If the download or library is
unavailable the loader raises a clear error and the caller falls back to the synthetic set.

Sources: HaluEval (arXiv:2305.11747), RAGTruth (arXiv:2401.00396).
"""

from __future__ import annotations

from controlplane.core.types import Axis, RequestContext
from controlplane.eval.dataset import LabeledExample

# Candidate Hugging Face dataset ids, tried in order (mirrors move around; we degrade gracefully).
_HALUEVAL_IDS = ["pminervini/HaluEval", "notrichardren/HaluEval"]
_RAGTRUTH_IDS = ["wandb/RAGTruth-processed", "flowaicom/RAGTruth", "ParticleMedia/RAGTruth"]


def _load_hf(ids: list[str], **kwargs):
    """Try each candidate id until one loads; raise a clear error if none do or ``datasets`` is missing."""
    try:
        from datasets import load_dataset
    except ImportError as exc:  # pragma: no cover
        raise ImportError("Real-data eval needs the 'datasets' library: pip install datasets") from exc
    last: Exception | None = None
    for ds_id in ids:
        try:
            return load_dataset(ds_id, **kwargs)
        except Exception as exc:  # noqa: BLE001 - try the next mirror
            last = exc
    raise RuntimeError(f"could not load any of {ids}: {last}")


def load_halueval_qa(limit: int | None = 500) -> list[LabeledExample]:
    """Load HaluEval QA as paired grounded/hallucinated performance-axis examples."""
    ds = _load_hf(_HALUEVAL_IDS, name="qa", split="data")
    examples: list[LabeledExample] = []
    for i, row in enumerate(ds):
        knowledge = row.get("knowledge") or ""
        question = row.get("question") or ""
        right = (row.get("right_answer") or "").strip()
        halluc = (row.get("hallucinated_answer") or "").strip()
        if not knowledge or not right or not halluc:
            continue
        for suffix, answer, is_fail in (("ok", right, False), ("hallu", halluc, True)):
            examples.append(
                LabeledExample(
                    ctx=RequestContext(
                        request_id=f"halueval-{i}-{suffix}",
                        use_case="rag_qa",
                        prompt=question,
                        response=answer,
                        retrieved_context=[knowledge],
                        model="gpt-4o",
                        input_tokens=len(knowledge.split()),
                        output_tokens=len(answer.split()),
                    ),
                    labels={Axis.PERFORMANCE: is_fail, Axis.RESPONSIBILITY: False},
                )
            )
        if limit and len(examples) >= limit:
            break
    return examples


def load_ragtruth(limit: int | None = 500) -> list[LabeledExample]:
    """Load RAGTruth as performance-axis examples (answer grounded in retrieved context or not)."""
    ds = _load_hf(_RAGTRUTH_IDS, split="test")
    examples: list[LabeledExample] = []
    for i, row in enumerate(ds):
        context = row.get("context") or row.get("source_info") or row.get("prompt") or ""
        answer = (row.get("response") or row.get("answer") or "").strip()
        # A row is a failure if it carries any hallucination annotation/label.
        labels_field = row.get("labels") or row.get("hallucination") or row.get("has_hallucination")
        is_fail = bool(labels_field) if not isinstance(labels_field, list) else len(labels_field) > 0
        if not context or not answer:
            continue
        examples.append(
            LabeledExample(
                ctx=RequestContext(
                    request_id=f"ragtruth-{i}",
                    use_case="rag_qa",
                    prompt=str(row.get("question") or row.get("query") or ""),
                    response=answer,
                    retrieved_context=[str(context)],
                    model="gpt-4o",
                    input_tokens=len(str(context).split()),
                    output_tokens=len(answer.split()),
                ),
                labels={Axis.PERFORMANCE: is_fail, Axis.RESPONSIBILITY: False},
            )
        )
        if limit and len(examples) >= limit:
            break
    return examples


LOADERS = {"halueval": load_halueval_qa, "ragtruth": load_ragtruth}
