/**
 * OmniCare AI — API contract types.
 *
 * Single source of truth mirroring docs/CONTRACTS.md exactly.
 * The frontend renders strictly off `message_type` + `data` (and top-level
 * `sources` / `tool_calls`). It must never parse `response` prose.
 */

export type MessageType =
  | 'greeting'
  | 'coverage_answer'
  | 'claim_list'
  | 'claim_status'
  | 'claim_draft'
  | 'claim_confirmation'
  | 'clarification'
  | 'chat'
  | 'error';

export type Verdict = 'covered' | 'excluded' | 'conditional' | 'uncertain' | 'unsupported';

export type Action = 'confirm_submit' | 'cancel_submit';

/** States reported by the voice WebSocket server (`state` message). */
export type VoiceServerState = 'listening' | 'processing' | 'speaking' | 'idle';

export interface Source {
  id: string;
  section: string;
  text: string;
  score: number;
}

export interface ToolCall {
  name: string;
  arguments: Record<string, unknown>;
  result?: unknown;
}

export interface Claim {
  claim_id: string;
  policy_number: string;
  claim_type: string;
  status: string;
  amount: number;
}

export interface ClaimDraft {
  policy_number: string | null;
  claim_type: string | null;
  amount: number | null;
  description: string | null;
}

export interface ChatRequest {
  user_id: string;
  conversation_id?: string;
  message: string;
  action: Action | null;
  draft: ClaimDraft | null;
  request_id: string | null;
}

// --- `data` payloads, keyed by `message_type` -----------------------------

export interface GreetingData {
  text: string;
  suggestions: string[];
}

export interface CoverageAnswerData {
  answer: string;
  verdict: Verdict;
}

export interface ClaimStatusData {
  claim: Claim;
}

export interface ClaimDraftData {
  draft: ClaimDraft;
  missing_fields: string[];
  confirm_required: boolean;
}

export interface ClaimConfirmationData {
  claim: Claim;
  idempotency_key: string;
}

export interface ClarificationData {
  question: string;
  missing_fields: string[];
}

export interface ChatData {
  draft_cancelled?: boolean;
}

export interface ErrorData {
  code: string;
  detail: string;
}

export type MessageData =
  | GreetingData
  | CoverageAnswerData
  | ClaimStatusData
  | ClaimDraftData
  | ClaimConfirmationData
  | ClarificationData
  | ChatData
  | ErrorData;

interface BaseResponse {
  response: string;
  sources: Source[];
  tool_calls: ToolCall[];
  request_id: string | null;
  mode: string;
}

export type ChatResponse = BaseResponse &
  (
    | { message_type: 'greeting'; data: GreetingData }
    | { message_type: 'coverage_answer'; data: CoverageAnswerData }
    | { message_type: 'claim_list'; data: { claims: Claim[] } }
    | { message_type: 'claim_status'; data: ClaimStatusData }
    | { message_type: 'claim_draft'; data: ClaimDraftData }
    | { message_type: 'claim_confirmation'; data: ClaimConfirmationData }
    | { message_type: 'clarification'; data: ClarificationData }
    | { message_type: 'chat'; data: ChatData }
    | { message_type: 'error'; data: ErrorData }
  );

export interface HealthResponse {
  status: string;
  version: string;
  mode: string;
  providers: Record<string, string>;
}

/**
 * Client-side chat message: a `ChatResponse` with a client `id` and `role`,
 * plus user turns (which only carry text).
 */
export type ChatMessage =
  | { id: string; role: 'user'; text: string }
  | ({ id: string; role: 'assistant' } & ChatResponse);

export interface Conversation { id: string; title: string; updated: number }
