"""OpenAI-compatible gateway for ControlPlane.

The gateway is intentionally thin in this first slice: it owns HTTP transport and model
backend selection, while the cascade/policy layers remain pluggable middleware around the
backend call. This keeps the P2/P1 seam explicit.
"""

from controlplane.proxy.app import create_app

__all__ = ["create_app"]
