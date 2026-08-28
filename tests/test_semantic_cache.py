"""Tests for genuine semantic response-cache bypass and compatibility guards."""

from __future__ import annotations

import numpy as np

from controlplane.proxy.semantic_cache import SemanticResponseCache
from controlplane.proxy.upstream import Generation


def _gen(text: str = "answer") -> Generation:
    return Generation(text=text, model="gpt-4o", input_tokens=10, output_tokens=5, use_case="support_bot")


def test_compatible_semantic_hit_returns_cached_generation_without_generation_logic() -> None:
    cache = SemanticResponseCache(enabled=True, threshold=0.9, embedding_fn=lambda _: np.array([1.0, 0.0]))
    first = _gen("cached")
    cache.store(prompt="What are support hours?", model="gpt-4o", context="9-6", use_case="support_bot", policy_id="support@balanced", generation=first)

    hit = cache.lookup(prompt="Can you tell me the support hours?", model="gpt-4o", context="9-6", use_case="support_bot", policy_id="support@balanced")
    assert hit is not None
    assert hit.kind == "semantic"
    assert hit.generation.cache_hit is True
    assert hit.generation.text == "cached"


def test_model_context_use_case_or_policy_mismatch_is_a_miss() -> None:
    cache = SemanticResponseCache(enabled=True, threshold=0.9, embedding_fn=lambda _: np.array([1.0, 0.0]))
    cache.store(prompt="refund policy", model="gpt-4o", context="A", use_case="support_bot", policy_id="support@balanced", generation=_gen())
    assert cache.lookup(prompt="refund policy", model="gpt-4o-mini", context="A", use_case="support_bot", policy_id="support@balanced") is None
    assert cache.lookup(prompt="refund policy", model="gpt-4o", context="B", use_case="support_bot", policy_id="support@balanced") is None
    assert cache.lookup(prompt="refund policy", model="gpt-4o", context="A", use_case="internal_copilot", policy_id="support@balanced") is None
    assert cache.lookup(prompt="refund policy", model="gpt-4o", context="A", use_case="support_bot", policy_id="support@strict") is None


def test_exact_mode_does_not_require_embedding_backend() -> None:
    cache = SemanticResponseCache(enabled=False)
    cache.store(prompt="Hello", model="gpt-4o", context=None, use_case="support_bot", policy_id="p", generation=_gen())
    hit = cache.lookup(prompt="hello", model="gpt-4o", context=None, use_case="support_bot", policy_id="p")
    assert hit is not None and hit.kind == "exact"
