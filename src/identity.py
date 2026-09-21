"""Identity layer for the cap-table reconciler (SYSTEM_SPEC §3.2).

Abstract IdentityProvider + role enum + permission tables. The real Qapita
SSO provider is Evelyn-blocked (we need their SSO endpoints + token format).
This module ships:

  - The role enum and the permission table the engine enforces.
  - An abstract IdentityProvider ABC that production Qapita SSO will
    implement.
  - A StubSSOProvider for local dev (returns a fixed test user).
  - A StaticUserProvider for tests (lets tests inject a user list).

Authentication is the provider's responsibility; authorisation (role -> what
they can do) is enforced inside this module via `can(user, action, ...)`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Role(str, Enum):
    analyst = "analyst"
    reviewer = "reviewer"
    partner = "partner"
    read_only_auditor = "read_only_auditor"


@dataclass(frozen=True)
class User:
    id: str
    email: str
    role: Role
    display_name: str


# ---- Permission matrix ------------------------------------------------------
# SYSTEM_SPEC §3.2 lists the role-based access rules. Codified here.

_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.analyst: frozenset(
        {
            "engagement.create",
            "engagement.read",
            "engagement.upload_cap_table",
            "engagement.add_snapshot",
            "engagement.resolve_finding",
            "engagement.generate_memo_draft",
            "engagement.transition_open_to_review",
            "export.json",
            "export.xlsx",
            "export.memo_pdf",
        }
    ),
    Role.reviewer: frozenset(
        {
            "engagement.read",
            "engagement.add_snapshot",
            "engagement.resolve_finding",
            "engagement.generate_memo_draft",
            "engagement.add_reviewer_note",
            "engagement.transition_review_to_signed",
            "export.json",
            "export.xlsx",
            "export.memo_pdf",
        }
    ),
    Role.partner: frozenset(
        {
            "engagement.read",
            "engagement.add_snapshot",
            "engagement.resolve_finding",
            "engagement.add_reviewer_note",
            "engagement.transition_review_to_signed",
            "engagement.transition_signed_to_review",  # GAP-29 reopen
            "engagement.transition_review_to_open",  # SD-AUD-M3 reopen back to analyst work
            "engagement.transition_to_archived",
            "engagement.restore_archived",  # W8.10 restore within 90d window
            "engagement.revoke_auditor_token",  # GAP-39
            "engagement.pii_redact",  # GAP-03
            "export.json",
            "export.xlsx",
            "export.memo_pdf",
        }
    ),
    Role.read_only_auditor: frozenset(
        {
            "engagement.read",
            "export.memo_pdf",
        }
    ),
}


def can(user: User, action: str) -> bool:
    """Return True if `user` is allowed to perform `action`."""
    return action in _PERMISSIONS.get(user.role, frozenset())


def actions_for(role: Role) -> frozenset[str]:
    return _PERMISSIONS.get(role, frozenset())


# ---- IdentityProvider abstraction -------------------------------------------


class IdentityProvider(ABC):
    """Subclass to integrate with a concrete SSO."""

    @abstractmethod
    def authenticate(self, token: str) -> Optional[User]:
        """Validate an opaque session token from the wire and return the user."""

    @abstractmethod
    def lookup_user(self, user_id: str) -> Optional[User]:
        """Look up a user by their stable ID (for audit-log display)."""


class StubSSOProvider(IdentityProvider):
    """Local-dev placeholder. Returns a fixed analyst user for any token.

    EVELYN-BLOCKED: replace with a real QapitaSSOProvider that calls Qapita's
    OIDC endpoint and maps the JWT's role claim to our Role enum.

    W8.2: refuses to mount in non-TESTING unless the operator explicitly
    sets ALLOW_STUB_SSO=1 in the environment. Without this, a careless
    prod deploy would accept any non-empty token as an analyst — the
    audit's "demo surface in production" footgun.
    """

    _STUB_USER = User(
        id="stub-analyst",
        email="dev-analyst@example.invalid",
        role=Role.analyst,
        display_name="Dev Analyst (stub)",
    )

    def __init__(self, *, allow_in_prod: bool = False):
        import os
        if not allow_in_prod and os.environ.get("ALLOW_STUB_SSO") != "1":
            # Test apps that set Flask's TESTING flag still construct the
            # stub directly; the guard fires only when nothing has opted in.
            # The boolean param exists so callers in app.py can route the
            # decision via config rather than env-only.
            if os.environ.get("FLASK_TESTING") != "1" and not _running_in_test():
                raise RuntimeError(
                    "StubSSOProvider refused to start: set ALLOW_STUB_SSO=1 "
                    "or pass allow_in_prod=True for the demo/dev path. "
                    "Prod deploys must use a real IdentityProvider."
                )

    def authenticate(self, token: str) -> Optional[User]:
        if not token:
            return None
        return self._STUB_USER

    def lookup_user(self, user_id: str) -> Optional[User]:
        if user_id == self._STUB_USER.id:
            return self._STUB_USER
        return None


def _running_in_test() -> bool:
    """True if the process looks like pytest. Used to keep the test fixture
    apps that instantiate StubSSOProvider directly from breaking — they
    already gate themselves with `app.config["TESTING"] = True`, which
    isn't visible at construct-time."""
    import sys
    return "pytest" in sys.modules


class StaticUserProvider(IdentityProvider):
    """Test fixture: a dict of token -> User."""

    def __init__(self, users: dict[str, User]):
        self._users = users

    def authenticate(self, token: str) -> Optional[User]:
        return self._users.get(token)

    def lookup_user(self, user_id: str) -> Optional[User]:
        for u in self._users.values():
            if u.id == user_id:
                return u
        return None
