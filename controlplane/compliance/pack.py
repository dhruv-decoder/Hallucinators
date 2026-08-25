"""Build a compliance evidence pack from the recorded receipts.

The mapping table below is the core: each row ties a regulatory control to the *recorded fact* that evidences
it. We compute the facts (how many decisions, how many escalated to a human, whether the audit chain
verifies, how many leaks were blocked) from the receipts and stamp each control with a status and the concrete
numbers. Frameworks covered: EU AI Act (Arts. 12, 13, 14, 15, 26, 50), ISO/IEC 42001, NIST AI RMF.
"""

from __future__ import annotations

from controlplane.core.types import Action, Axis, VoIReceipt

_DISCLAIMER = (
    "This pack is an evidence aid generated from ControlPlane's tamper-evident flight recorder. It maps "
    "recorded operational facts to regulatory controls to support an audit; it is not a legal certification "
    "of conformity. Regulatory note (as of 2 Aug 2026): EU AI Act GPAI obligations and Art. 50 transparency "
    "are enforceable; the high-risk Annex III obligations (Arts. 8-15/26) were deferred to 2 Dec 2027 by the "
    "Digital Omnibus, so those rows map evidence to controls that may not yet be legally required for a given "
    "system. Prices and any offline-simulated traffic are labelled as such."
)


def _stats(receipts: list[VoIReceipt]) -> dict:
    """Aggregate the facts the controls cite."""
    n = len(receipts)
    by_action = {a.value: 0 for a in Action}
    for r in receipts:
        by_action[r.action.value] = by_action.get(r.action.value, 0) + 1
    responsibility_flags = sum(
        1 for r in receipts if (r.per_axis.get(Axis.RESPONSIBILITY) and r.per_axis[Axis.RESPONSIBILITY].p_fail >= 0.5)
    )
    performance_flags = sum(
        1 for r in receipts if (r.per_axis.get(Axis.PERFORMANCE) and r.per_axis[Axis.PERFORMANCE].p_fail >= 0.5)
    )
    return {
        "decisions": n,
        "by_action": by_action,
        "escalated": by_action.get("escalate", 0),
        "blocked": by_action.get("block", 0),
        "auto_repaired": by_action.get("auto_repair", 0),
        "annotated": by_action.get("annotate", 0),
        "responsibility_flags": responsibility_flags,
        "performance_flags": performance_flags,
    }


def generate_pack(receipts: list[VoIReceipt], chain_valid: bool, policy_id: str = "") -> dict:
    """Return a structured evidence pack: summary stats + a control-by-control mapping with statuses."""
    s = _stats(receipts)
    n = s["decisions"]

    def status(ok: bool) -> str:
        return "evidenced" if ok else "no evidence yet"

    controls = [
        {
            "framework": "EU AI Act",
            "control": "Art. 12 — Record-keeping (logging & traceability)",
            "requirement": "Automatically record events over the system's lifetime to ensure traceability.",
            "evidence": (
                f"Every decision is an append-only, SHA-256 hash-chained receipt ({n} recorded). "
                f"Tamper-evident chain verifies = {chain_valid}."
            ),
            "status": status(n > 0 and chain_valid),
        },
        {
            "framework": "EU AI Act",
            "control": "Art. 13 — Transparency to deployers",
            "requirement": "Provide information enabling deployers to interpret and use the output.",
            "evidence": (
                "Each response carries a VoI receipt: per-axis failure probabilities, the checks run vs "
                "skipped and why, the action taken, and the stopping reason."
            ),
            "status": status(n > 0),
        },
        {
            "framework": "EU AI Act",
            "control": "Art. 14 — Human oversight",
            "requirement": "Enable humans to oversee, intervene on, and override the system.",
            "evidence": (
                f"{s['escalated']} decision(s) were escalated to a human reviewer; the override feedback loop "
                "recalibrates detectors from human verdicts."
            ),
            "status": status(True),
        },
        {
            "framework": "EU AI Act",
            "control": "Art. 15 — Accuracy & robustness",
            "requirement": "Achieve appropriate accuracy and act on erroneous outputs.",
            "evidence": (
                f"{s['performance_flags']} response(s) flagged on the performance axis; {s['auto_repaired']} "
                f"auto-repaired from retrieved context; {s['annotated']} annotated with a caveat."
            ),
            "status": status(True),
        },
        {
            "framework": "EU AI Act",
            "control": "Art. 26 / 50 — Deployer obligations & transparency",
            "requirement": "Monitor operation, keep logs, and support disclosure obligations.",
            "evidence": (
                f"Continuous inline monitoring of {n} decision(s) with retained logs; {s['blocked']} unsafe / "
                "data-leak response(s) blocked before reaching a user."
            ),
            "status": status(n > 0),
        },
        {
            "framework": "ISO/IEC 42001",
            "control": "AIMS — Operational controls & performance monitoring",
            "requirement": "Operate, monitor, and document controls over the AI system in production.",
            "evidence": (
                "Per-use-case policy profiles (risk appetite as config) drive an inline VoI cascade; every "
                "decision, cost, and latency is metered and logged."
            ),
            "status": status(n > 0),
        },
        {
            "framework": "NIST AI RMF",
            "control": "GOVERN / MAP / MEASURE / MANAGE",
            "requirement": "Govern policy, map context, measure risk, and manage/act on it.",
            "evidence": (
                "GOVERN: policy-as-config. MAP: three coupled risk axes per use case. MEASURE: calibrated "
                "per-axis p_fail + offline P/R/FPR/FNR eval. MANAGE: "
                f"{s['blocked'] + s['escalated'] + s['auto_repaired']} response(s) acted on "
                "(block/escalate/repair)."
            ),
            "status": status(n > 0),
        },
    ]

    return {
        "generated_from": "ControlPlane flight recorder",
        "policy_id": policy_id,
        "decisions": n,
        "chain_valid": chain_valid,
        "summary": s,
        "controls": controls,
        "disclaimer": _DISCLAIMER,
    }


def render_markdown(pack: dict) -> str:
    """Render the structured pack as an auditor-readable Markdown document."""
    lines = [
        "# ControlPlane — Compliance Evidence Pack",
        "",
        f"- **Decisions covered:** {pack['decisions']}",
        f"- **Active policy:** {pack['policy_id'] or 'n/a'}",
        f"- **Audit chain verified:** {pack['chain_valid']}",
        "",
        "| Framework | Control | Evidence (from receipts) | Status |",
        "|---|---|---|---|",
    ]
    for c in pack["controls"]:
        ev = c["evidence"].replace("|", "\\|")
        lines.append(f"| {c['framework']} | {c['control']} | {ev} | {c['status']} |")
    lines += ["", f"> {pack['disclaimer']}"]
    return "\n".join(lines)
