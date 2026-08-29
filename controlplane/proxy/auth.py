"""Authentication + multi-tenant workspaces for The Tower.

Enterprises run many AI use cases and (rightly) expect them kept apart: a support-bot's policy, audit log and
P&L must never bleed into a health-copilot's. This module provides the identity half of that:

- **Users** with salted PBKDF2 password hashes (stdlib -- no bcrypt/passlib build dependency).
- **Workspaces** (one per use case) owned by a user; the oversight *state* per workspace is isolated by the
  registry in ``app.py`` (each workspace gets its own :class:`OversightService`).
- **Stateless JWT (HS256)** signed with ``CONTROLPLANE_AUTH_SECRET`` so the static frontend can authenticate
  against the FastAPI backend on Render with no server-side session store.

It is deliberately small and dependency-free so it works identically on a laptop and on the Render deployment.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass

_PBKDF2_ROUNDS = 200_000
_TOKEN_TTL_SECONDS = 7 * 24 * 3600  # a week; re-login after that
_DEFAULT_SECRET = "controlplane-dev-secret-change-me"  # overridden by CONTROLPLANE_AUTH_SECRET in prod


def _secret() -> str:
    return os.environ.get("CONTROLPLANE_AUTH_SECRET", "").strip() or _DEFAULT_SECRET


# ---- password hashing ------------------------------------------------------------------------------
def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ROUNDS).hex()
    return digest, salt


def verify_password(password: str, digest: str, salt: str) -> bool:
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ROUNDS).hex()
    return hmac.compare_digest(candidate, digest)


# ---- stateless JWT (HS256) -------------------------------------------------------------------------
def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(seg: str) -> bytes:
    return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))


def make_token(user_id: str, email: str) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64(json.dumps({"sub": user_id, "email": email, "exp": int(time.time()) + _TOKEN_TTL_SECONDS}).encode())
    signing_input = f"{header}.{payload}"
    sig = _b64(hmac.new(_secret().encode(), signing_input.encode(), hashlib.sha256).digest())
    return f"{signing_input}.{sig}"


def decode_token(token: str) -> dict | None:
    """Return the payload if the token is well-formed, correctly signed and unexpired, else None."""
    try:
        header, payload, sig = token.split(".")
        expected = _b64(hmac.new(_secret().encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, sig):
            return None
        body = json.loads(_b64d(payload))
        if int(body.get("exp", 0)) < int(time.time()):
            return None
        return body
    except Exception:  # noqa: BLE001 - any malformed token is simply unauthenticated
        return None


class AuthError(Exception):
    """Raised for signup/login problems; carries an HTTP-ish status."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class User:
    id: str
    email: str
    name: str


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# The default use cases a brand-new (or demo) account starts with -- one workspace per case, kept apart.
_SEED_WORKSPACES = [
    ("EU Fintech Support", "customer_support"),
    ("US Health Copilot", "internal_copilot"),
    ("Global Agentic Ops", "agentic"),
]


class AuthStore:
    """SQLite-backed users + workspaces. Thread-safe; safe to share across requests."""

    def __init__(self, path: str | None = None) -> None:
        self.path = path or os.environ.get("CONTROLPLANE_AUTH_DB", "controlplane_auth.db")
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT UNIQUE, name TEXT, "
            "pw_hash TEXT, pw_salt TEXT, created REAL)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS workspaces (id TEXT PRIMARY KEY, user_id TEXT, name TEXT, "
            "use_case TEXT, created REAL)"
        )
        self._conn.commit()
        self._seed_demo()

    # -- internal helpers ----------------------------------------------------------------------------
    def _seed_demo(self) -> None:
        """Create a ready-to-use demo account so judges can log in instantly."""
        email = "demo@controlplane.ai"
        with self._lock:
            row = self._conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            if row:
                return
        try:
            self.signup(email, "demo1234", "Demo User")
        except AuthError:
            pass

    def _workspaces_for(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, name, use_case FROM workspaces WHERE user_id=? ORDER BY created", (user_id,)
        ).fetchall()
        return [{"id": r[0], "name": r[1], "use_case": r[2]} for r in rows]

    # -- public API ----------------------------------------------------------------------------------
    def signup(self, email: str, password: str, name: str = "") -> dict:
        email = (email or "").strip().lower()
        name = (name or "").strip() or email.split("@")[0]
        if not _EMAIL_RE.match(email):
            raise AuthError("Enter a valid email address")
        if len(password or "") < 6:
            raise AuthError("Password must be at least 6 characters")
        with self._lock:
            if self._conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
                raise AuthError("An account with that email already exists", status=409)
            user_id = uuid.uuid4().hex[:16]
            digest, salt = hash_password(password)
            self._conn.execute(
                "INSERT INTO users (id, email, name, pw_hash, pw_salt, created) VALUES (?,?,?,?,?,?)",
                (user_id, email, name, digest, salt, time.time()),
            )
            for ws_name, use_case in _SEED_WORKSPACES:
                self._conn.execute(
                    "INSERT INTO workspaces (id, user_id, name, use_case, created) VALUES (?,?,?,?,?)",
                    (uuid.uuid4().hex[:16], user_id, ws_name, use_case, time.time()),
                )
            self._conn.commit()
        return self._session(User(user_id, email, name))

    def login(self, email: str, password: str) -> dict:
        email = (email or "").strip().lower()
        with self._lock:
            row = self._conn.execute(
                "SELECT id, name, pw_hash, pw_salt FROM users WHERE email=?", (email,)
            ).fetchone()
        if not row or not verify_password(password or "", row[2], row[3]):
            raise AuthError("Incorrect email or password", status=401)
        return self._session(User(row[0], email, row[1]))

    def user_for_token(self, token: str) -> User | None:
        body = decode_token(token or "")
        if not body:
            return None
        with self._lock:
            row = self._conn.execute("SELECT id, email, name FROM users WHERE id=?", (body["sub"],)).fetchone()
        return User(row[0], row[1], row[2]) if row else None

    def workspaces(self, user_id: str) -> list[dict]:
        with self._lock:
            return self._workspaces_for(user_id)

    def owns_workspace(self, user_id: str, workspace_id: str) -> bool:
        with self._lock:
            return bool(
                self._conn.execute(
                    "SELECT 1 FROM workspaces WHERE id=? AND user_id=?", (workspace_id, user_id)
                ).fetchone()
            )

    def create_workspace(self, user_id: str, name: str, use_case: str) -> dict:
        name = (name or "").strip()
        if not name:
            raise AuthError("Workspace name is required")
        if use_case not in {"customer_support", "internal_copilot", "decision_support", "agentic"}:
            use_case = "customer_support"
        with self._lock:
            ws_id = uuid.uuid4().hex[:16]
            self._conn.execute(
                "INSERT INTO workspaces (id, user_id, name, use_case, created) VALUES (?,?,?,?,?)",
                (ws_id, user_id, name, use_case, time.time()),
            )
            self._conn.commit()
        return {"id": ws_id, "name": name, "use_case": use_case}

    def delete_workspace(self, user_id: str, workspace_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM workspaces WHERE id=? AND user_id=?", (workspace_id, user_id)
            )
            self._conn.commit()
            return cur.rowcount > 0

    def _session(self, user: User) -> dict:
        return {
            "token": make_token(user.id, user.email),
            "user": {"id": user.id, "email": user.email, "name": user.name},
            "workspaces": self._workspaces_for(user.id),
        }
