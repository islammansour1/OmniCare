"""Claim tools exposed to the agent.

Validation is deterministic Pydantic — never delegated to the LLM. Business
operations (status lookup, submission, idempotency) are pure code.
"""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .store import ClaimsStore, ClaimNotFoundError, InvalidClaimError, claims_store

_CLAIM_ID_RE = re.compile(r"^[A-Za-z0-9-]{3,32}$")
_POLICY_RE = re.compile(r"^[A-Za-z0-9-]{3,32}$")


class SubmitClaimInput(BaseModel):
    policy_number: str = Field(min_length=3, max_length=32)
    claim_type: str = Field(min_length=2, max_length=64)
    amount: float
    description: str = Field(min_length=3, max_length=2000)

    @field_validator("policy_number")
    @classmethod
    def _policy(cls, v: str) -> str:
        v = v.strip()
        if not _POLICY_RE.match(v):
            raise ValueError("policy number must be alphanumeric (e.g. POL-1092)")
        return v

    @field_validator("claim_type", "description")
    @classmethod
    def _no_control(cls, v: str) -> str:
        v = v.strip()
        if any(ch in v for ch in ("\n", "\r", "\t")) or not v:
            raise ValueError("must not be empty or contain control characters")
        return v

    @field_validator("amount")
    @classmethod
    def _positive(cls, v: float) -> float:
        import math

        if not math.isfinite(v) or v <= 0:
            raise ValueError("amount must be a positive number")
        if v > 10_000_000:
            raise ValueError("amount is unreasonably large")
        return round(float(v), 2)


def get_claim_status(claim_id: str, owner_id: str) -> dict[str, Any]:
    """Return the claim for ``claim_id`` or raise ClaimNotFoundError."""
    if not _CLAIM_ID_RE.match(claim_id or ""):
        raise InvalidClaimError(f"invalid claim id: {claim_id!r}")
    return claims_store.get_claim_status(claim_id, owner_id)


def submit_claim(
    policy_number: str,
    claim_type: str,
    amount: float,
    description: str,
    owner_id: str,
) -> dict[str, Any]:
    """Validate and append a claim, returning the persisted record.

    Idempotent: identical inputs always return the same claim (never duplicates).
    """
    validated = SubmitClaimInput(
        policy_number=policy_number,
        claim_type=claim_type,
        amount=amount,
        description=description,
    )
    return claims_store.submit_claim(
        validated.policy_number,
        validated.claim_type,
        validated.amount,
        validated.description,
        owner_id,
    )


# Re-export for convenience.
__all__ = [
    "SubmitClaimInput",
    "get_claim_status",
    "submit_claim",
    "ClaimNotFoundError",
    "InvalidClaimError",
    "ClaimsStore",
    "claims_store",
]
