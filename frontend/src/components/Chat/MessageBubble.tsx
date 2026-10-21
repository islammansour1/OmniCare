import type { ChatMessage, ClaimDraft } from '../../lib/types';
import { ClaimConfirmationCard } from '../cards/ClaimConfirmationCard';
import { ClaimReviewForm } from '../cards/ClaimReviewForm';
import { ClaimStatusCard } from '../cards/ClaimStatusCard';
import { ClarificationCard } from '../cards/ClarificationCard';
import { CoverageCard } from '../cards/CoverageCard';
import { Citations } from '../cards/Citations';
import { ErrorCard } from '../cards/ErrorCard';
import { GreetingCard } from '../cards/GreetingCard';

export interface MessageBubbleProps {
  message: ChatMessage;
  loading?: boolean;
  onSuggestion: (text: string) => void;
  onConfirmSubmit: (draft: ClaimDraft) => void;
  onCancelSubmit: () => void;
}

export function MessageBubble({
  message,
  loading = false,
  onSuggestion,
  onConfirmSubmit,
  onCancelSubmit,
}: MessageBubbleProps) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-indigo-600 px-4 py-2.5 shadow-sm">
          <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-white">
            {message.text}
          </p>
        </div>
      </div>
    );
  }

  return (
    <AssistantMessage
      message={message}
      loading={loading}
      onSuggestion={onSuggestion}
      onConfirmSubmit={onConfirmSubmit}
      onCancelSubmit={onCancelSubmit}
    />
  );
}

/** Message types whose `response` prose is commentary above the card. */
const PROSE_MESSAGE_TYPES = new Set(['claim_list', 'claim_status', 'claim_draft', 'claim_confirmation', 'chat']);

function AssistantMessage({
  message,
  loading,
  onSuggestion,
  onConfirmSubmit,
  onCancelSubmit,
}: {
  message: Extract<ChatMessage, { role: 'assistant' }>;
  loading: boolean;
  onSuggestion: (text: string) => void;
  onConfirmSubmit: (draft: ClaimDraft) => void;
  onCancelSubmit: () => void;
}) {
  const showProse = PROSE_MESSAGE_TYPES.has(message.message_type);

  return (
    <div className="flex justify-start">
      <div className="flex max-w-[85%] flex-col gap-3">
        {showProse && message.response ? (
          <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-700">
            {message.response}
          </p>
        ) : null}
        <AssistantCard
          message={message}
          loading={loading}
          onSuggestion={onSuggestion}
          onConfirmSubmit={onConfirmSubmit}
          onCancelSubmit={onCancelSubmit}
        />
      </div>
    </div>
  );
}

/**
 * Routes strictly on `message_type` (never on `response` prose).
 */
function AssistantCard({
  message,
  loading,
  onSuggestion,
  onConfirmSubmit,
  onCancelSubmit,
}: {
  message: Extract<ChatMessage, { role: 'assistant' }>;
  loading: boolean;
  onSuggestion: (text: string) => void;
  onConfirmSubmit: (draft: ClaimDraft) => void;
  onCancelSubmit: () => void;
}) {
  switch (message.message_type) {
    case 'greeting':
      return <GreetingCard data={message.data} onSuggestion={onSuggestion} />;
    case 'coverage_answer':
      return <CoverageCard data={message.data} sources={message.sources} />;
    case 'claim_list':
      return <div className="space-y-2">{message.data.claims.map(claim =>
        <button key={claim.claim_id} className="block w-full rounded-xl border border-slate-200 bg-white p-3 text-left text-sm hover:bg-indigo-50"
          onClick={() => onSuggestion(`Check ${claim.claim_id}`)}>
          <span className="font-semibold">{claim.claim_type}</span> · {claim.claim_id}<br />
          <span className="text-slate-500">{claim.status}</span>
        </button>)}</div>;
    case 'claim_status':
      return <ClaimStatusCard claim={message.data.claim} />;
    case 'claim_draft':
      if (!message.data.confirm_required) return <p className="text-xs text-slate-500">Earlier draft — use the latest review card.</p>;
      return (
        <div className="space-y-3">
          <Citations sources={message.sources} />
          <ClaimReviewForm
            data={message.data}
            loading={loading}
            onConfirm={onConfirmSubmit}
            onCancel={onCancelSubmit}
          />
        </div>
      );
    case 'claim_confirmation':
      return <ClaimConfirmationCard data={message.data} />;
    case 'clarification':
      return <ClarificationCard data={message.data} />;
    case 'error':
      return <ErrorCard data={message.data} />;
    case 'chat':
      return null;
    default:
      return null;
  }
}
