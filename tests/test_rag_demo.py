"""Tests for the tiny RAG app (P1.1): the retriever picks the right chunk, and ControlPlane oversees the
answer against it -- passing a grounded reply and repairing an ungrounded one, deterministically offline."""

from __future__ import annotations

from fastapi.testclient import TestClient

from controlplane.demo.run_rag import retrieve
from controlplane.proxy.app import create_app


def test_retriever_stems_and_ranks() -> None:
    # "refund" must match the "Refunds ..." chunk despite the plural, and beat the unrelated chunks.
    assert "Refunds are available within 30 days" in retrieve("What is the refund window?")[0]
    assert "9am to 6pm" in retrieve("customer support hours")[0]
    # A query with no corpus support retrieves nothing rather than a spurious chunk.
    assert retrieve("What is the CEO's mobile number?") == []


def test_rag_grounded_passes_and_hallucination_is_repaired() -> None:
    client = TestClient(create_app(recorder_path=None, force_simulated=True))

    grounded = client.post("/v1/oversight/playground", json={
        "prompt": "What are the customer support hours?",
        "context": retrieve("What are the customer support hours?")[0],
        "model": "gpt-4o",
    }).json()
    assert grounded["controlplane"]["action"] == "pass"

    hallucinated = client.post("/v1/oversight/playground", json={
        "prompt": "What is the refund window?",
        "context": retrieve("What is the refund window?")[0],
        "model": "gpt-4o",
    }).json()
    cp = hallucinated["controlplane"]
    assert cp["action"] == "auto_repair"
    # The delivered answer is grounded in the retrieved policy, not the 180-day over-claim.
    assert "30 days" in hallucinated["final"] and "180" not in hallucinated["final"]
    assert hallucinated["receipt"]["hash_self"]
