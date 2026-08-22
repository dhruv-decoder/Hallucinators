"""Adaptive Oversight Thermostat demo.

Runs a stream that is calm, then hit by a burst of risky answers, then calm again, and shows the
thermostat raising scrutiny during the burst and relaxing afterwards. Higher scrutiny makes the VoI
stopping rule willing to run more (paid) checks precisely when the environment is risky, without slowing
the safe majority.

Run with ``make thermostat`` or ``python -m controlplane.demo.run_thermostat``.
"""

from __future__ import annotations

from controlplane.cascade.thermostat import Thermostat, risk_score
from controlplane.core.types import PolicyProfile, RequestContext
from controlplane.demo.run_demo import build_engine


def _ctx(
    rid: str, prompt: str, response: str, context: list[str], samples: list[str] | None = None
) -> RequestContext:
    return RequestContext(
        request_id=rid,
        use_case="support_bot",
        prompt=prompt,
        response=response,
        retrieved_context=context,
        samples=samples or [],
        model="gpt-4o",
        input_tokens=200,
        output_tokens=300,
    )


def stream() -> list[RequestContext]:
    """Calm -> risky burst -> calm."""
    calm = [
        _ctx(
            f"calm-{i}",
            "What are your support hours?",
            "Support is available 9am to 6pm, Monday to Friday.",
            ["Support is available from 9am to 6pm, Monday through Friday."],
        )
        for i in range(4)
    ]
    burst = [
        _ctx(
            f"risky-{i}",
            "What is the refund window?",
            "You can absolutely get a refund within 180 days, guaranteed, without a doubt.",
            ["Refunds are available within 30 days of purchase."],
            samples=["Yes, 180 days.", "Definitely 180 days."],  # makes the T1 check applicable
        )
        for i in range(5)
    ]
    calm_again = [
        _ctx(
            f"calm2-{i}",
            "What are your support hours?",
            "Support is available 9am to 6pm, Monday to Friday.",
            ["Support is available from 9am to 6pm, Monday through Friday."],
        )
        for i in range(4)
    ]
    return calm + burst + calm_again


def main() -> None:
    engine = build_engine(PolicyProfile(id="support_bot@IN@balanced"))
    thermostat = Thermostat()

    print("Adaptive Oversight Thermostat -- calm, then a risky burst, then calm")
    print("=" * 72)
    print(f"{'request':10s} {'scrutiny':>8s}  {'risk':>5s}  paid-checks  action")
    for ctx in stream():
        s = thermostat.recommend()
        result = engine.run(ctx, scrutiny=s)
        risk = risk_score(result)
        thermostat.observe(risk)

        paid_checks = sum(1 for step in result.trace if step.ran and step.tier > 0)
        bar = "#" * int(round((s - 0.5) / 2.5 * 20))  # scale [0.5, 3.0] -> [0, 20]
        print(
            f"{ctx.request_id:10s} {s:7.2f}x  {risk:5.2f}  {paid_checks:^11d}  {result.action.value}"
            f"   |{bar}"
        )

    print("=" * 72)
    print("Scrutiny climbs as the burst raises recent risk, then decays once calm returns.")


if __name__ == "__main__":
    main()
