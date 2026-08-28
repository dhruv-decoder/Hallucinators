"""Bounded exact + semantic response cache for genuine upstream-call avoidance.

The cache is intentionally conservative: compatibility is enforced by the requested model, use-case,
policy version and retrieved context; semantic similarity is considered only between otherwise compatible
entries. The embedding implementation is optional and lazy so the default/offline service keeps its small
footprint. A cache hit still flows through the normal oversight pipeline, so policy checks and audit receipts
are not bypassed.
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, replace

import numpy as np

from controlplane.proxy.upstream import Generation


@dataclass(frozen=True)
class CacheLookup:
    generation: Generation
    kind: str  # "exact" or "semantic"
    similarity: float


@dataclass
class _Entry:
    generation: Generation
    prompt_norm: str
    context_norm: str
    model: str
    use_case: str
    policy_id: str
    embedding: np.ndarray | None
    created_at: float


class SemanticResponseCache:
    """Thread-safe, bounded response cache with optional sentence-transformer similarity search."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        threshold: float = 0.90,
        max_entries: int = 2048,
        ttl_seconds: float = 3600.0,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        embedding_fn: Callable[[str], np.ndarray] | None = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.threshold = max(0.50, min(float(threshold), 0.9999))
        self.max_entries = max(1, int(max_entries))
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self.model_name = model_name
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._lock = threading.RLock()
        self._embedder = embedding_fn
        self.mode = "semantic" if self.enabled else "exact"

    @staticmethod
    def normalize(text: str | None) -> str:
        return " ".join((text or "").lower().split())

    @classmethod
    def exact_key(
        cls,
        prompt: str,
        model: str | None,
        context: str | None,
        use_case: str | None,
        policy_id: str | None,
    ) -> str:
        payload = "\x1f".join(
            [
                cls.normalize(prompt),
                cls.normalize(model),
                cls.normalize(context),
                cls.normalize(use_case),
                cls.normalize(policy_id),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _get_embedder(self) -> Callable[[str], np.ndarray] | None:
        if not self.enabled:
            return None
        if self._embedder is not None:
            return self._embedder
        try:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(self.model_name)

            def encode(text: str) -> np.ndarray:
                vec = np.asarray(model.encode([text], normalize_embeddings=True)[0], dtype=float)
                return vec

            self._embedder = encode
            return self._embedder
        except Exception:  # noqa: BLE001 - semantic mode degrades safely to exact matching
            self.enabled = False
            self.mode = "exact-fallback"
            return None

    @staticmethod
    def _similarity(a: np.ndarray, b: np.ndarray) -> float:
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom <= 0.0:
            return 0.0
        return float(np.dot(a, b) / denom)

    def _expired(self, entry: _Entry, now: float) -> bool:
        return self.ttl_seconds > 0.0 and (now - entry.created_at) > self.ttl_seconds

    def lookup(
        self,
        *,
        prompt: str,
        model: str | None,
        context: str | None,
        use_case: str | None,
        policy_id: str | None,
    ) -> CacheLookup | None:
        now = time.monotonic()
        model_norm = self.normalize(model)
        context_norm = self.normalize(context)
        use_case_norm = self.normalize(use_case)
        policy_norm = self.normalize(policy_id)
        key = self.exact_key(prompt, model, context, use_case, policy_id)

        with self._lock:
            exact = self._entries.get(key)
            if exact is not None:
                if self._expired(exact, now):
                    self._entries.pop(key, None)
                else:
                    self._entries.move_to_end(key)
                    return CacheLookup(
                        replace(exact.generation, cache_hit=True, cache_similarity=1.0, cache_hit_kind="exact"),
                        "exact", 1.0,
                    )

            embedder = self._get_embedder()
            if embedder is None:
                return None
            query_embedding = embedder(self.normalize(prompt))
            best_key: str | None = None
            best_entry: _Entry | None = None
            best_similarity = 0.0
            for entry_key, entry in list(self._entries.items()):
                if self._expired(entry, now):
                    self._entries.pop(entry_key, None)
                    continue
                if (entry.model, entry.context_norm, entry.use_case, entry.policy_id) != (
                    model_norm, context_norm, use_case_norm, policy_norm
                ):
                    continue
                if entry.embedding is None:
                    continue
                sim = self._similarity(query_embedding, entry.embedding)
                if sim > best_similarity:
                    best_similarity = sim
                    best_key = entry_key
                    best_entry = entry

            if best_entry is not None and best_key is not None and best_similarity >= self.threshold:
                self._entries.move_to_end(best_key)
                generation = replace(
                    best_entry.generation,
                    cache_hit=True,
                    cache_similarity=round(best_similarity, 6),
                    cache_hit_kind="semantic",
                )
                return CacheLookup(generation, "semantic", best_similarity)
        return None

    def store(
        self,
        *,
        prompt: str,
        model: str | None,
        context: str | None,
        use_case: str | None,
        policy_id: str | None,
        generation: Generation,
    ) -> None:
        prompt_norm = self.normalize(prompt)
        context_norm = self.normalize(context)
        model_norm = self.normalize(model)
        use_case_norm = self.normalize(use_case)
        policy_norm = self.normalize(policy_id)
        embedding = None
        embedder = self._get_embedder()
        if embedder is not None:
            embedding = embedder(prompt_norm)

        key = self.exact_key(prompt, model, context, use_case, policy_id)
        entry = _Entry(
            generation=replace(generation, cache_hit=False, cache_similarity=None, cache_hit_kind="miss"),
            prompt_norm=prompt_norm,
            context_norm=context_norm,
            model=model_norm,
            use_case=use_case_norm,
            policy_id=policy_norm,
            embedding=embedding,
            created_at=time.monotonic(),
        )
        with self._lock:
            self._entries[key] = entry
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def stats(self) -> dict:
        with self._lock:
            return {
                "mode": self.mode,
                "enabled": self.enabled,
                "threshold": round(self.threshold, 4),
                "entries": len(self._entries),
                "max_entries": self.max_entries,
                "ttl_seconds": self.ttl_seconds,
                "embedding_model": self.model_name if self.enabled else None,
            }
