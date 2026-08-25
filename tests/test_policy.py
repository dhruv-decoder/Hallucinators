from __future__ import annotations

from pathlib import Path

import yaml

from controlplane.core.types import Axis, PolicyProfile, Tier
from controlplane.policy import PolicyManager


def test_policy_manager_selects_exact_and_fallback(tmp_path: Path) -> None:
    path = tmp_path / "policies.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "profiles": [
                    PolicyProfile().model_dump(mode="json"),
                    PolicyProfile(
                        id="support_bot@IN@balanced",
                        use_case="support_bot",
                        geography="IN",
                        risk_appetite="balanced",
                        tier_ceilings={Axis.PERFORMANCE: Tier.T1, Axis.COST: Tier.T0, Axis.RESPONSIBILITY: Tier.T1},
                    ).model_dump(mode="json"),
                ],
            }
        ),
        encoding="utf-8",
    )
    manager = PolicyManager(path)
    exact = manager.resolve(use_case="support_bot", geography="IN", risk_appetite="balanced")
    assert exact.id == "support_bot@IN@balanced"
    assert exact.tier_ceilings[Axis.PERFORMANCE] == Tier.T1
    fallback = manager.resolve(use_case="unknown", geography="US", risk_appetite="balanced")
    assert fallback.id == "default@balanced"


def test_policy_manager_hot_reloads(tmp_path: Path) -> None:
    path = tmp_path / "policies.yaml"
    base = {
        "version": 1,
        "profiles": [PolicyProfile().model_dump(mode="json")],
    }
    path.write_text(yaml.safe_dump(base), encoding="utf-8")
    manager = PolicyManager(path)
    assert manager.get("default@balanced").block_threshold == 0.85

    updated = {
        "version": 1,
        "profiles": [PolicyProfile(block_threshold=0.70).model_dump(mode="json")],
    }
    path.write_text(yaml.safe_dump(updated), encoding="utf-8")
    # Ensure the filesystem timestamp resolution cannot hide the mutation.
    path.touch()
    assert manager.get("default@balanced").block_threshold == 0.70
