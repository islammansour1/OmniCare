from concurrent.futures import ThreadPoolExecutor
from typing import Any

from langgraph.types import interrupt

from ..claims import ClaimNotFoundError, InvalidClaimError
from ..claims.tools import SubmitClaimInput
from ..deps import Deps
from ..observability import log_event
from ..schemas import ClaimDraft
from .llm import LLMUnavailableError
from .retrieval import assess_policy
from .state import (
    AgentState,
    build_response,
    draft_to_payload,
    missing_claim_fields,
    draft_from_payload,
    merge_draft,
    format_missing_fields_prompt,
    first_invalid_field,
)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def build_route_node(deps: Deps) -> Any:
    def _route(state: AgentState) -> dict[str, Any]:
        action = state.get("action")
        if action == "confirm_submit":
            log_event("agent.route", intent="confirm_submit")
            return {"intent": "confirm"}
        if action == "cancel_submit":
            log_event("agent.route", intent="cancel_submit")
            return {"intent": "cancel"}
        intent = deps.lm.classify_intent(state["message"], state.get("history", []))
        log_event("agent.route", intent=intent)
        return {"intent": intent}

    return _route


def compose_coverage_answer(deps: Deps, question: str, analysis: dict, sources: list[dict]) -> str:
    """Presentation cannot change the structured verdict or verified sources."""
    try:
        answer = deps.lm.compose_answer(question, analysis["verdict"], analysis["facts"],
                                        [s["section"] for s in sources])
    except LLMUnavailableError:
        # Wording failures must not discard a successfully verified assessment.
        answer = ("Here is what the policy says: " + " ".join(analysis["facts"]) if analysis["facts"]
                  else "The available policy passages do not establish coverage for this. A policy review is needed.")
    if analysis.get("clarification"):
        answer += " " + analysis["clarification"]
    return answer


def load_policy_dialogue(deps, state):
    messages = deps.db.get_messages(state["user_id"], limit=2)
    for message in reversed(messages):
        if message["role"] == "assistant":
            payload = message.get("data", {})
            return payload.get("data", payload).get("policy_dialogue", {})
    return {}


def assess_turn(deps, state, history):
    previous = load_policy_dialogue(deps, state)
    cached = previous.get("evidence", [])
    if cached:
        # Reuse evidence only while it still matches the active policy exactly.
        current = {c.id: c.section + "\n" + c.text for c in deps.rag.get_chunks()}
        cached = [s for s in cached if current.get(s["id"]) == s["text"]]
    return assess_policy(deps.lm, deps.rag, state["message"], history, initial_sources=cached)


def clarify_or_review(deps, state, analysis, sources):
    previous = {} if analysis.get("starts_new_incident") else load_policy_dialogue(deps, state)
    count = previous.get("questions", 0)
    question = analysis.get("clarification", "").strip()
    # Two questions per unresolved conversation sequence, including across restarts.
    # A terminal review message retains the count; another vague reply cannot reset it.
    if analysis.get("needs_review") or count >= 2 or not question or question.casefold() == previous.get("question", "").casefold():
        cited_sources = [s for s in sources if s['id'] in analysis['cited_ids']]
        # Stop questioning, not explaining: retain the verified policy terms
        # and let the final writer explain the unresolved distinction.
        terminal = {**analysis, "verdict": "uncertain", "clarification": ""}
        answer = compose_coverage_answer(deps, state["message"], terminal, cited_sources)
        return build_response(answer, "coverage_answer", data={"answer": answer, "verdict": "uncertain",
            "policy_dialogue": {"questions": 2, "question": question, "evidence": sources}},
            sources=cited_sources)
    try:
        wording = deps.lm.compose_clarification(state["message"], question, sources, state.get("history", []))
    except LLMUnavailableError:
        wording = "Could you tell me a little more about what happened?"
    return build_response(wording, "clarification", data={"question": wording, "missing_fields": [],
        "policy_dialogue": {"questions": count + 1, "question": question, "evidence": sources}})


def build_coverage_node(deps: Deps) -> Any:
    def _coverage(state: AgentState) -> dict[str, Any]:
        question = state["message"]
        analysis, sources = assess_turn(deps, state, state.get("history", []))
        if analysis["verdict"] == "uncertain":
            return {"result": clarify_or_review(deps, state, analysis, sources)}
        if analysis["verdict"] in ("covered", "conditional") and analysis.get("claim_requested"):
            return build_claim_submit_node(deps, assessment=(analysis, sources))(state)
        verdict = analysis["verdict"]
        facts = analysis["facts"]
        cited_ids = set(analysis["cited_ids"])
        cited_sources = [s for s in sources if s["id"] in cited_ids]
        answer = compose_coverage_answer(deps, question, analysis, cited_sources)

        log_event("agent.coverage", verdict=verdict, source_ids=list(cited_ids))
        return {
            "result": build_response(
                response=answer,
                message_type="coverage_answer",
                data={"answer": answer, "verdict": verdict, "clarification": analysis.get("clarification", "")},
                sources=cited_sources,
            )
        }

    return _coverage


def find_referenced_claim_id(state: AgentState, deps: Deps) -> str | None:
    return deps.lm.resolve_claim_id(state["message"], state.get("history", []))


def build_claim_status_node(deps: Deps) -> Any:
    def _claim_status(state: AgentState) -> dict[str, Any]:
        cid = find_referenced_claim_id(state, deps)
        if not cid:
            query = deps.lm.rewrite_query(state["message"], state.get("history", []))
            candidates = deps.claims.search(query, state["owner_id"], embedder=deps.rag.embedder)
            selected = set(deps.lm.select_claims(query, candidates))
            matches = [c for c in candidates if c['claim_id'] in selected]
            return {"result": build_response(
                response="Here are the matching claims. Select one to see its status." if matches else "I couldn't find a matching claim in this session. Try a different description or a claim ID.",
                message_type="claim_list", data={"claims": matches},
                tool_calls=[{"name": "search_claims", "arguments": {"query": state["message"]},
                             "result": matches}])}
        try:
            claim = deps.claims.get_claim_status(cid, owner_id=state["owner_id"])
        except ClaimNotFoundError:
            return {
                "result": build_response(
                    response=f"I couldn't find a claim with ID {cid}. Please double-check the ID and try again.",
                    message_type="clarification",
                    data={"question": f"Claim {cid} was not found. Please check the ID.", "missing_fields": ["claim_id"]},
                )
            }
        except InvalidClaimError:
            return {
                "result": build_response(
                    response=f"'{cid}' doesn't look like a valid claim ID.",
                    message_type="clarification",
                    data={"question": f"'{cid}' doesn't look like a valid claim ID.", "missing_fields": ["claim_id"]},
                )
            }
        log_event("agent.claim_status", claim_id=cid)
        return {
            "result": build_response(
                response=(
                    f"Claim {claim['claim_id']} is {claim['status'].lower()} — "
                    f"{claim['claim_type']} for {claim['policy_number']} "
                    f"({claim['amount']:.2f})."
                ),
                message_type="claim_status",
                data={"claim": claim},
                tool_calls=[
                    {
                        "name": "get_claim_status",
                        "arguments": {"claim_id": cid},
                        "result": claim,
                    }
                ],
            )
        }

    return _claim_status


def check_coverage_gate(
    deps: Deps, incident: str, history: list[dict[str, str]], assessment=None, state=None
) -> dict[str, Any] | None:
    """Assess whether a described incident is a covered, excluded, or ambiguous
    peril before we let the customer draft a claim for it.

    Entirely LLM-driven: the hosted model reads retrieved policy passages and
    returns a verdict with verified evidence. Excluded, unsupported, and
    uncertain perils short-circuit the draft; covered/conditional ones proceed.
    No keyword rules — the model decides from the policy text.
    """
    analysis, sources = assessment or assess_policy(deps.lm, deps.rag, incident, history)
    verdict = analysis["verdict"]
    if verdict == "uncertain" and state is not None:
        return clarify_or_review(deps, state, analysis, sources)
    if verdict in ("covered", "conditional"):
        return None
    cited = set(analysis["cited_ids"])
    cited_sources = [s for s in sources if s["id"] in cited]
    answer = compose_coverage_answer(deps, incident, analysis, cited_sources)
    log_event("agent.claim_gate", verdict=verdict, source_ids=list(cited))
    return build_response(
        response=answer,
        message_type="coverage_answer",
        data={"answer": answer, "verdict": verdict, "clarification": analysis.get("clarification", "")},
        sources=cited_sources,
    )


def build_claim_submit_node(deps: Deps, assessment=None, interactive: bool = True) -> Any:
    def _claim_submit(state: AgentState) -> dict[str, Any]:
        user_id = state["user_id"]
        existing = deps.db.load_draft(user_id) or ClaimDraft()
        # Assess the original message even if extraction misses fields. The
        # extracted draft is context, never a replacement for the user's facts.
        context = list(state.get("history", []))
        if existing.description:
            context.append({"role": "assistant", "content": "Existing draft description (may be corrected by latest message): " + existing.description})

        def _extract() -> dict[str, Any]:
            return deps.lm.extract_claim_fields(state["message"], state.get("history", []))

        if assessment is not None:
            # The coverage node already computed the assessment; only extraction
            # remains, so there is nothing to overlap.
            extracted = _extract()
            checked = assessment
        else:
            # Field extraction and coverage assessment are independent of each
            # other (assessment reads history + existing draft, never the
            # extracted fields). Run them concurrently to save one LLM round-trip.
            with ThreadPoolExecutor(max_workers=2) as pool:
                f_extract = pool.submit(_extract)
                f_assess = pool.submit(lambda: assess_turn(deps, state, context))
                extracted = f_extract.result()
                checked = f_assess.result()

        merged = merge_draft(existing, extracted)
        gate = check_coverage_gate(deps, state["message"], context, assessment=checked, state=state)
        if gate is not None:
            deps.db.save_draft(user_id, merged)
            return {"result": gate}
        deps.db.save_draft(user_id, merged)
        missing = missing_claim_fields(merged)
        analysis, sources = checked
        cited_sources = [s for s in sources if s['id'] in analysis['cited_ids']]
        response = compose_coverage_answer(deps, state["message"], analysis, cited_sources)
        response += " You can complete and review the claim details below. Submitting a claim does not guarantee payment."
        log_event("agent.claim_draft", missing=missing)
        draft_result = build_response(
            response=response,
            message_type="claim_draft",
            data={
                "draft": draft_to_payload(merged),
                "missing_fields": missing,
                "confirm_required": True,
            },
            sources=cited_sources,
        )

        if not interactive:
            # Stateless path (voice): surface the draft without pausing for a
            # human confirmation round-trip (voice has no confirm action).
            return {"result": draft_result}

        # Human-in-the-loop: pause and surface the draft for explicit
        # confirmation, then resume into the confirm/cancel node.
        decision = interrupt(draft_result)
        if decision.get("action") == "cancel_submit":
            return {"intent": "cancel"}
        return {"intent": "confirm", "draft_input": decision.get("draft") or {}}

    return _claim_submit


def build_confirm_node(deps: Deps) -> Any:
    """Policy preflight followed by deterministic validation and persistence."""

    def submit_confirmed_claim(merged: ClaimDraft, owner_id: str) -> dict[str, Any]:
        claim = deps.claims.submit_claim(
            merged.policy_number,
            merged.claim_type,
            merged.amount,
            merged.description,
            owner_id=owner_id,
        )
        idem = deps.claims.idempotency_key(
            merged.policy_number, merged.claim_type, merged.amount, merged.description, owner_id
        )
        log_event("agent.confirmed", claim_id=claim["claim_id"])
        return build_response(
            response=(
                f"Your claim has been submitted. Confirmation ID: {claim['claim_id']}. "
                f"Status: {claim['status']}."
            ),
            message_type="claim_confirmation",
            data={"claim": claim, "idempotency_key": idem},
            tool_calls=[
                {
                    "name": "submit_claim",
                    "arguments": {
                        "policy_number": merged.policy_number,
                        "claim_type": merged.claim_type,
                        "amount": merged.amount,
                        "description": merged.description,
                    },
                    "result": claim,
                }
            ],
        )

    def replay_existing_claim(edits: dict[str, Any], owner_id: str) -> dict[str, Any] | None:
        """Recover a confirmation for an already-submitted claim (retry/refresh)."""
        merged = draft_from_payload(edits)
        if missing_claim_fields(merged):
            return None
        try:
            SubmitClaimInput(
                policy_number=merged.policy_number,
                claim_type=merged.claim_type,
                amount=merged.amount,
                description=merged.description,
            )
        except Exception:  # noqa: BLE001
            return None
        idem = deps.claims.idempotency_key(
            merged.policy_number, merged.claim_type, merged.amount, merged.description, owner_id
        )
        existing = deps.claims.find_by_idempotency_key(idem)
        if existing is not None:
            log_event("agent.confirm_replay", claim_id=existing["claim_id"])
            return submit_confirmed_claim(merged, owner_id)
        return None

    def _confirm(state: AgentState) -> dict[str, Any]:
        user_id = state["user_id"]
        owner_id = state["owner_id"]
        draft = deps.db.load_draft(user_id)
        edits = state.get("draft_input") or {}

        if draft is None:
            # Retry/refresh after a successful submit: replay the existing claim.
            replay = replay_existing_claim(edits, owner_id)
            if replay is not None:
                return {"result": replay}
            return {
                "result": build_response(
                    response="There's no claim draft to submit. Start by describing your claim.",
                    message_type="clarification",
                    data={"question": "No claim draft to submit."},
                )
            }

        # Apply any edits from the review card.
        merged = merge_draft(draft, edits)
        missing = missing_claim_fields(merged)
        if missing:
            deps.db.save_draft(user_id, merged)
            return {
                "result": build_response(
                    response="I still need: " + format_missing_fields_prompt(missing),
                    message_type="claim_draft",
                    data={
                        "draft": draft_to_payload(merged),
                        "missing_fields": missing,
                        "confirm_required": True,
                    },
                )
            }
        try:
            SubmitClaimInput(
                policy_number=merged.policy_number,
                claim_type=merged.claim_type,
                amount=merged.amount,
                description=merged.description,
            )
        except Exception as exc:  # pydantic.ValidationError
            field = first_invalid_field(exc)
            return {
                "result": build_response(
                    response=f"I couldn't submit that: {field}. Please correct the draft and try again.",
                    message_type="claim_draft",
                    data={
                        "draft": draft_to_payload(merged),
                        "missing_fields": [],
                        "confirm_required": True,
                        "error": str(exc),
                    },
                )
            }
        # Reassess the reviewed incident: edits must not bypass the policy check.
        gate = check_coverage_gate(deps, merged.description, state.get("history", []), state=state)
        if gate is not None:
            deps.db.save_draft(user_id, merged)
            return {"result": gate}
        result = submit_confirmed_claim(merged, owner_id)
        deps.db.delete_draft(user_id)
        return {"result": result}

    return _confirm


def build_cancel_node(deps: Deps) -> Any:
    def _cancel(state: AgentState) -> dict[str, Any]:
        deps.db.delete_draft(state["user_id"])
        return {
            "result": build_response(
                response="Claim draft cancelled. Let me know if you'd like to start over.",
                message_type="chat", data={"draft_cancelled": True},
            )
        }

    return _cancel


def build_chitchat_node(deps: Deps) -> Any:
    def _chitchat(state: AgentState) -> dict[str, Any]:
        if not state.get("history"):
            return {
                "result": build_response(
                    response=(
                        "Hi, I'm OmniCare's assistant. I can answer questions about your "
                        "policy, track a claim, or help you file a new claim. How can I help?"
                    ),
                    message_type="greeting",
                    data={
                        "text": "How can I help you today?",
                        "suggestions": ["Ask about coverage", "Track a claim", "File a claim"],
                    },
                )
            }
        return {
            "result": build_response(
                response="Happy to help. Ask me about coverage, tracking a claim, or filing a new claim.",
                message_type="chat",
            )
        }

    return _chitchat
