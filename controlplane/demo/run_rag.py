"""A tiny but genuinely functional RAG app, overseen by ControlPlane (P1.1).

The point is integration realism, not application complexity: a small policy corpus, a keyword retriever, a
model behind the ControlPlane proxy, and oversight checking each answer against the *retrieved* context. It
shows the two cases that matter in production RAG:

- a question supported by the corpus -> grounded answer -> ControlPlane PASS;
- a question where the model states a confident but unsupported fact -> ControlPlane catches the ungrounded
  claim and auto-repairs it back to the retrieved source, with a signed receipt.

By default it runs against the offline simulator so the hallucination (and its repair) is *deterministic* and
reproducible every run with no API key. Pass ``--live`` to route the same flow through the real Groq model.

Run with ``make rag`` or ``python -m controlplane.demo.run_rag [--live]``.
"""

from __future__ import annotations

import re
import sys

from controlplane.runtime import load_dotenv

# A small, self-contained policy corpus (what a support knowledge base might hold).
CORPUS = [
    "Refunds are available within 30 days of purchase, with a valid receipt.",
    "Support is available 9am to 6pm, Monday to Friday.",
    "To reset your password, click 'Forgot Password' on the login page.",
    "The warranty covers parts and labour for two years from the date of purchase.",
    "Orders are shipped within 3 to 5 business days via standard delivery.",
]

_WORD = re.compile(r"[a-z0-9']+")
_STOP = {"the", "a", "an", "is", "are", "of", "to", "and", "what", "how", "do", "i", "my", "your", "for"}


def _stem(word: str) -> str:
    """A deliberately tiny stemmer so 'refund' matches 'refunds' and 'hours' matches 'hour'."""
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _terms(text: str) -> set[str]:
    return {_stem(w) for w in _WORD.findall(text.lower()) if w not in _STOP}


def retrieve(query: str, k: int = 1) -> list[str]:
    """Keyword retriever: rank corpus chunks by stemmed term overlap (empty if nothing overlaps)."""
    q = _terms(query)
    scored = sorted(((len(q & _terms(c)), c) for c in CORPUS), reverse=True)
    return [c for score, c in scored[:k] if score > 0]


def main() -> None:
    load_dotenv()
    live = "--live" in sys.argv
    from fastapi.testclient import TestClient

    from controlplane.proxy.app import create_app

    client = TestClient(create_app(recorder_path=None, force_simulated=not live))

    # One question the corpus supports, and one where the model over-claims (the sim confidently says the
    # refund window is 180 days -- ControlPlane must catch that against the retrieved 30-day policy).
    queries = ["What are the customer support hours?", "What is the refund window?"]
    print(f"Tiny RAG app + ControlPlane oversight  (upstream: {'live Groq' if live else 'simulator'})")
    print("=" * 74)
    for q in queries:
        context = retrieve(q)
        r = client.post(
            "/v1/oversight/playground",
            json={"prompt": q, "context": "\n".join(context) or None, "model": "gpt-4o"},
        ).json()
        cp = r["controlplane"]
        print(f"\nQ: {q}")
        print(f"  retrieved:  {context[0] if context else '(nothing relevant)'}")
        print(f"  model said: {r['candidate'][:90]}")
        print(f"  ControlPlane -> {cp['action'].upper()}  "
              f"(groundedness p_fail = {cp['per_axis_p_fail'].get('performance', 0):.2f})")
        if r["modified"]:
            print(f"  repaired to: {r['final'][:90]}")
        print(f"  receipt: {cp['receipt_id']}  (hash-chained: {bool(r['receipt']['hash_self'])})")
    print("\nThe RAG app retrieves; ControlPlane oversees each answer against the retrieved context,")
    print("passing the grounded one and repairing the ungrounded one -- every step on a signed receipt.")


if __name__ == "__main__":
    main()
