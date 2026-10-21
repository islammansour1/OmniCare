# API contracts

All paths start with `/api/v1`. Health is public. Session creation returns
`{"user_id":"usr_..."}` and an HttpOnly `omnicare_session` cookie. Subsequent calls
require that cookie (or an equivalent bearer session token). Cross-origin browser
requests require a configured allowed origin. Caller-supplied user IDs must match
the authenticated session.

| Method | Path | Behavior |
|---|---|---|
| POST | `/session` | Resume or create a 30-day prototype browser session |
| GET | `/health` | Status, mode, and per-provider availability (`unavailable` when a key is missing) |
| GET | `/conversations` | Owned conversations: id, title, updated |
| POST | `/conversations` | Create an empty conversation |
| GET | `/conversations/{id}` | Owned messages with full cards/citations plus current draft |
| POST | `/chat` | Complete response |
| POST | `/chat/stream` | SSE progress events and one terminal result/error |
| WS | `/voice?user_id=...&conversation_id=...` | Cookie-authenticated voice in the same conversation |

Chat input:

```json
{
  "user_id": "SESSION_USER_ID",
  "conversation_id": "OPTIONAL_OWNED_CONVERSATION_ID",
  "message": "Is water damage covered?",
  "request_id": "UNIQUE_TURN_ID",
  "action": null,
  "draft": null
}
```

Omitting conversation_id selects a legacy single-chat scope within the authenticated
session. `action` is null, `confirm_submit`, or `cancel_submit`. The edited draft
contains policy_number, claim_type, amount, description. An LLM-driven coverage gate
flags excluded, unsupported, or uncertain perils before a draft is presented. Only
structured confirmation can write a claim. New claim IDs/idempotency keys include
the owner.

Responses contain response, sources, tool_calls, message_type, data, request_id, mode.
Types: greeting, coverage_answer, claim_list, claim_status, claim_draft,
claim_confirmation, clarification, chat, error. Coverage verdicts: covered, excluded,
conditional, uncertain, unsupported. Missing incident facts return `clarification`
with a short `data.question`, without displayed citations or a verdict card.
After two consecutive replies without useful new facts, unresolved cases return
`coverage_answer` with an uncertain verdict. An explicit inability to answer, a
repeated question without progress, or missing document evidence can end questioning
earlier. Useful partial answers reset the stalled-reply count rather than exhausting
a fixed two-question limit. `data.policy_dialogue` stores the server's total question
count, `stalled_turns`, terminal `stopped` flag, and verified evidence for subsequent
turns; clients do not render this metadata. Final `claim_draft` responses may include policy sources and an
explanation above the form. Confirmation remains an explicit action.
`claim_list.data.claims` contains owned matches or explicitly public sample records.
`chat.data.draft_cancelled=true` retires a cancelled draft card.

SSE frames use `data: JSON` followed by a blank line:

```json
{"type":"progress","label":"Processing your request"}
{"type":"token","delta":"A pipe"}
{"type":"token","delta":" burst is covered."}
{"type":"result","response":{"response":"...","message_type":"coverage_answer","data":{},"sources":[],"tool_calls":[],"request_id":"...","mode":"live"}}
```

`token` frames stream the final answer text incrementally before the terminal
`result`; clients that ignore them still receive the complete atomic card.

A terminal transport error has type=error and detail. A terminal response whose
message_type=error is also retryable. The frontend retains the original request
body and ID when retrying. Completed requests replay without appending messages;
a different body with the same ID returns 409 on the non-streaming endpoint.
Clients must not treat a disconnected stream as a successful response.

Unauthorized sessions return 401, mismatched user IDs 403, and inaccessible
conversations 404. Schema validation returns 422. Public sample claims are
CLM-8821 and CLM-9014. No real policyholder identity or policy ownership is inferred.
