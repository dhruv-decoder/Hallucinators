"""YAML-backed policy profiles with validation and hot reload."""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from controlplane.core.types import PolicyProfile


class PolicyDocument(BaseModel):
    """Validated on-disk policy document."""

    version: int = 1
    profiles: list[PolicyProfile] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_profiles(self) -> "PolicyDocument":
        ids = [profile.id for profile in self.profiles]
        if len(ids) != len(set(ids)):
            raise ValueError("policy profile ids must be unique")
        if "default@balanced" not in ids:
            raise ValueError("policy document must define default@balanced")
        return self


class PolicyManager:
    """Load, validate, select and hot-reload policy profiles.

    Selection is exact ``use_case × geography × risk_appetite``, then wildcard geography, then the
    required default profile.  The file is checked on each lookup; only a changed mtime triggers parsing.
    """

    def __init__(self, path: str | Path = "policies/policies.yaml") -> None:
        self.path = Path(path)
        self._lock = RLock()
        self._mtime_ns: int | None = None
        self._profiles: dict[str, PolicyProfile] = {}
        self.reload(force=True)

    def reload(self, *, force: bool = False) -> bool:
        with self._lock:
            if not self.path.exists():
                raise FileNotFoundError(f"policy file not found: {self.path}")
            mtime_ns = self.path.stat().st_mtime_ns
            if not force and self._mtime_ns == mtime_ns:
                return False
            try:
                raw = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
                document = PolicyDocument.model_validate(raw)
            except (ValidationError, yaml.YAMLError, OSError) as exc:
                raise ValueError(f"invalid policy file {self.path}: {exc}") from exc
            self._profiles = {profile.id: profile for profile in document.profiles}
            self._mtime_ns = mtime_ns
            return True

    def maybe_reload(self) -> bool:
        return self.reload(force=False)

    def profiles(self) -> list[PolicyProfile]:
        self.maybe_reload()
        with self._lock:
            return list(self._profiles.values())

    def get(self, policy_id: str) -> PolicyProfile:
        self.maybe_reload()
        with self._lock:
            try:
                return self._profiles[policy_id]
            except KeyError as exc:
                raise KeyError(f"unknown policy profile: {policy_id}") from exc

    def resolve(
        self,
        *,
        use_case: str = "default",
        geography: str = "*",
        risk_appetite: str = "balanced",
    ) -> PolicyProfile:
        self.maybe_reload()
        use_case = use_case or "default"
        geography = geography or "*"
        risk_appetite = risk_appetite or "balanced"
        with self._lock:
            exact = [
                p for p in self._profiles.values()
                if p.use_case == use_case and p.geography == geography and p.risk_appetite == risk_appetite
            ]
            if exact:
                return exact[0]
            wildcard = [
                p for p in self._profiles.values()
                if p.use_case == use_case and p.geography == "*" and p.risk_appetite == risk_appetite
            ]
            if wildcard:
                return wildcard[0]
            return self._profiles["default@balanced"]

    def snapshot(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "profiles": [profile.model_dump(mode="json") for profile in self.profiles()],
        }
