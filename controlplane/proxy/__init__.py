"""The Tower -- ControlPlane's OpenAI-compatible proxy layer.

This is the inline placement of the oversight engine: an enterprise points its existing OpenAI client at
this gateway with a one-line ``base_url`` swap, and every response is run through the VoI cascade before it
reaches the user. Nothing about the caller's code changes.

Owned by P2 in the plan; built here against the frozen contracts in ``controlplane/core/types.py`` so the
engine (P1) and UI (P3) plug in unchanged. The proxy runs fully offline by default via a simulated
failure-injecting upstream (no API keys, no model downloads); a real multi-provider path via ``litellm``
turns on automatically when a provider key is present.
"""

from controlplane.proxy.app import create_app

__all__ = ["create_app"]
