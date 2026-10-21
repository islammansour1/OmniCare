"""Pydantic schemas — the single source of truth for API shapes."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Claim
# ---------------------------------------------------------------------------


class Claim(BaseModel):
    claim_id: str
    policy_number: str
    claim_type: str
    status: str
    amount: float


class ClaimDraft(BaseModel):
    """A claim in progress. Fields may be None while unknown."""

    policy_number: str | None = None
    claim_type: str | None = None
    amount: float | None = None
    description: str | None = None


class ClaimDraftInput(BaseModel):
    """Edited draft fields sent by the frontend review card."""

    policy_number: str | None = None
    claim_type: str | None = None
    amount: float | None = None
    description: str | None = None


# ---------------------------------------------------------------------------
# Chat request / response
# ---------------------------------------------------------------------------

MessageAction = Literal["confirm_submit", "cancel_submit"]

# Ordered set of required draft fields for a claim submission.
REQUIRED_CLAIM_FIELDS = ["policy_number", "claim_type", "amount", "description"]

MessageType = Literal[
    "greeting",
    "coverage_answer",
    "claim_status",
    "claim_list",
    "claim_draft",
    "claim_confirmation",
    "clarification",
    "chat",
    "error",
]


class ChatRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = Field(default=None, max_length=128)
    action: MessageAction | None = None
    draft: ClaimDraftInput | None = None
    request_id: str | None = Field(default=None, max_length=128)

    @field_validator("user_id")
    @classmethod
    def _sanitize_user_id(cls, v: str) -> str:
        v = v.strip()
        if not v or any(ch in v for ch in ("\n", "\r", "\t")):
            raise ValueError("invalid user_id")
        return v

    @field_validator("message")
    @classmethod
    def _strip_message(cls, v: str) -> str:
        return v.strip()


class Source(BaseModel):
    id: str
    section: str
    text: str
    score: float


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any | None = None


class ChatResponse(BaseModel):
    response: str
    sources: list[Source] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    message_type: MessageType = "chat"
    data: dict[str, Any] = Field(default_factory=dict)
    request_id: str = ""
    mode: str = "live"


class HealthResponse(BaseModel):
    status: str
    version: str = "1.0.0"
    mode: str = "live"
    providers: dict[str, str] = Field(default_factory=dict)
