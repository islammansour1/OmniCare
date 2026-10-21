from typing import Any, NotRequired, TypedDict

from ..schemas import REQUIRED_CLAIM_FIELDS, ClaimDraft


class AgentState(TypedDict, total=False):
    user_id: str
    owner_id: str
    message: str
    action: str | None
    draft_input: dict[str, Any] | None
    history: list[dict[str, str]]
    intent: str
    result: dict[str, Any]
    # Internal channels shared by the ``coverage`` and ``claim_submit``
    # subgraphs. They are computed mid-turn and never supplied by a caller
    # (``AgentInput`` below excludes them, so Studio's input form ignores them).
    assessment: dict[str, Any] | None
    sources: list[dict[str, Any]]
    context: list[dict[str, str]]
    existing: dict[str, Any] | None
    extracted: dict[str, Any] | None


class AgentInput(TypedDict):
    """Fields a caller must supply to run the agent.

    This is the schema LangGraph Studio surfaces as its input form. ``intent``
    and ``result`` are deliberately absent — they are computed by the graph
    (the ``route`` node and the leaf nodes), never supplied by the caller.
    """

    user_id: str
    message: str
    owner_id: NotRequired[str]
    action: NotRequired[str | None]
    draft_input: NotRequired[dict[str, Any] | None]
    history: NotRequired[list[dict[str, str]]]


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------


def build_response(
    response: str,
    message_type: str,
    data: dict[str, Any] | None = None,
    sources: list[dict[str, Any]] | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "response": response,
        "sources": sources or [],
        "tool_calls": tool_calls or [],
        "message_type": message_type,
        "data": data or {},
    }


def draft_to_payload(d: ClaimDraft) -> dict[str, Any]:
    return {
        "policy_number": d.policy_number,
        "claim_type": d.claim_type,
        "amount": d.amount,
        "description": d.description,
    }


def missing_claim_fields(d: ClaimDraft) -> list[str]:
    return [f for f in REQUIRED_CLAIM_FIELDS if getattr(d, f) is None]


def draft_from_payload(edits: dict[str, Any]) -> ClaimDraft:
    return ClaimDraft(
        policy_number=edits.get("policy_number"),
        claim_type=edits.get("claim_type"),
        amount=edits.get("amount"),
        description=edits.get("description"),
    )


def merge_draft(base: ClaimDraft, updates: dict[str, Any]) -> ClaimDraft:
    merged = ClaimDraft(
        policy_number=base.policy_number,
        claim_type=base.claim_type,
        amount=base.amount,
        description=base.description,
    )
    if updates.get("policy_number"):
        merged.policy_number = str(updates["policy_number"]).strip()
    if updates.get("claim_type"):
        merged.claim_type = str(updates["claim_type"]).strip()
    if updates.get("amount") is not None:
        try:
            merged.amount = float(updates["amount"])
        except (TypeError, ValueError):
            pass
    if updates.get("description"):
        merged.description = str(updates["description"]).strip()
    return merged


def format_missing_fields_prompt(missing: list[str]) -> str:
    names = {
        "policy_number": "your policy number (e.g. POL-1092)",
        "claim_type": "the type of incident or loss",
        "amount": "the estimated damage amount",
        "description": "a short description of what happened",
    }
    return "I still need " + ", ".join(names[f] for f in missing) + "."


def first_invalid_field(exc: Exception) -> str:
    try:
        errors = exc.errors()  # pydantic ValidationError
        loc = errors[0]["loc"]
        return str(loc[0]) if loc else "invalid input"
    except Exception:  # noqa: BLE001
        return "invalid input"
