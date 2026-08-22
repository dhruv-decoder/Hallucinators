"""The one-line ``base_url`` swap, demonstrated.

This is a plain OpenAI-style client that talks to a *running* Tower (``make serve`` in another terminal).
It sends the scripted demo prompts to ``/v1/chat/completions`` exactly as any app would, and prints what
oversight did to each response -- the point being that the caller changed nothing but the ``base_url``.

Run with ``make traffic`` (or ``python -m controlplane.proxy.traffic``). Uses only ``httpx`` so there is no
dependency on the OpenAI SDK; the request/response shape is the standard Chat Completions contract.
"""

from __future__ import annotations

import os
import sys

import httpx

from controlplane.proxy.workload import demo_prompts

BASE_URL = os.environ.get("CONTROLPLANE_BASE_URL", "http://127.0.0.1:8000/v1")

_BADGE = {
    "pass": "\033[92mPASS\033[0m",
    "annotate": "\033[96mANNOTATE\033[0m",
    "auto_repair": "\033[95mAUTO-REPAIR\033[0m",
    "escalate": "\033[93mESCALATE\033[0m",
    "block": "\033[91mBLOCK\033[0m",
}


def main() -> None:
    print(f"Pointing an OpenAI client at {BASE_URL} (one-line base_url swap)\n" + "=" * 70)
    try:
        client = httpx.Client(base_url=BASE_URL, timeout=30.0)
        client.get("/models").raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"Could not reach The Tower at {BASE_URL}. Start it first with `make serve`.\n  ({exc})")
        sys.exit(1)

    for p in demo_prompts():
        resp = client.post(
            "/chat/completions",
            json={
                "model": p.get("model", "controlplane-sim"),
                "use_case": p.get("use_case"),
                "messages": [{"role": "user", "content": p["prompt"]}],
            },
        ).json()
        cp = resp["controlplane"]
        text = resp["choices"][0]["message"]["content"].replace("\n", " ")
        badge = _BADGE.get(cp["action"], cp["action"].upper())
        p_fail = " ".join(f"{ax[:4]}={v:.2f}" for ax, v in cp["per_axis_p_fail"].items())
        print(f"\n[{badge}]  {p['prompt']}")
        print(
            f"   axes: {p_fail}   net: ${cp['net_usd']:.5f}   "
            f"+{cp['added_latency_ms']:.1f}ms   receipt {cp['receipt_id']}"
        )
        print(f"   → {text[:96]}")

    summary = client.get("/oversight/summary").json()
    print("\n" + "=" * 70)
    print(
        f"Oversight P&L: saved ${summary['cost_saved_usd']:.5f}  spend ${summary['safety_spend_usd']:.5f}  "
        f"net ${summary['net_usd']:.5f}  " + ("(self-funding)" if summary["self_funding"] else "")
    )
    print(f"cleared @T0: {summary['cleared_at_t0_pct']}%   chain valid: {summary['chain_valid']}")
    print("\nOpen the Control-Tower dashboard at", BASE_URL.replace("/v1", "/"))


if __name__ == "__main__":
    main()
