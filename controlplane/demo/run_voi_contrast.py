"""Show the VoI rule deciding *how much* to verify (``make voi-contrast``).

Two responses, one engine, one policy. A safe response gets waved through after the cheap checks; an
uncertain one triggers the purchase of the expensive check. This is the centerpiece proof that ControlPlane's
oversight is adaptive, not a fixed pipeline. Deterministic and offline -- no API key or model download.

    python -m controlplane.demo.run_voi_contrast
"""

from __future__ import annotations

from controlplane.cascade.voi_contrast import voi_contrast


def _print_case(title: str, case: dict) -> None:
    verb = "BOUGHT an extra check" if case["bought_a_check"] else "SKIPPED the extra check"
    print(f"\n  {title}: {verb}")
    print(f"    prompt   : {case['prompt']}")
    print(f"    response : {case['response']}")
    print(f"    P(fail) after cheap checks: {case['p_fail_after_t0']:.3f}  ->  final: {case['final_p_fail']:.3f}")
    for s in case["expensive_checks"]:
        decision = "RAN " if s["ran"] else "SKIP"
        print(
            f"    [{decision}] {s['detector']:<18} tier {s['tier']}  "
            f"VoI={s['voi']:.5f}  cost={s['check_cost']:.5f}  ({s['reason']})"
        )
    print(f"    action   : {case['action']}")


def main() -> None:
    data = voi_contrast()
    print("=" * 84)
    print(f"  VoI contrast — same engine, same detectors, same policy ({data['policy_id']})")
    print("=" * 84)
    _print_case("SAFE response      ", data["safe"])
    _print_case("UNCERTAIN response ", data["uncertain"])
    print(f"\n  {data['note']}")


if __name__ == "__main__":
    main()
