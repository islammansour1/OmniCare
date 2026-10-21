import { useEffect, useRef } from 'react';
import type { ChatMessage, ClaimDraft } from '../../lib/types';
import { MessageBubble } from './MessageBubble';
import { StreamingText } from './StreamingText';
import { TypingIndicator } from './TypingIndicator';

function latestDraftIndex(messages: ChatMessage[]): number {
  return messages.reduce((last, m, i) => m.role === 'assistant' &&
    (m.message_type === 'claim_draft' || m.message_type === 'claim_confirmation' ||
     (m.message_type === 'chat' && m.data.draft_cancelled)) ? i : last, -1);
}

export interface MessageListProps {
  messages: ChatMessage[];
  isLoading?: boolean;
  progress?: string;
  streamText?: string;
  onSuggestion: (text: string) => void;
  onConfirmSubmit: (draft: ClaimDraft) => void;
  onCancelSubmit: () => void;
}

export function MessageList({
  messages,
  isLoading = false,
  progress = 'Thinking…',
  streamText = '',
  onSuggestion,
  onConfirmSubmit,
  onCancelSubmit,
}: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages.length, isLoading]);

  // Follow the streamed text without the smooth-scroll easing (which would lag
  // behind rapid token updates).
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' });
  }, [streamText.length]);

  const lastAction = latestDraftIndex(messages);
  return (
    <div className="space-y-5 py-6" role="log" aria-live="polite" aria-label="Conversation">
      {messages.map((message, index) => (
        <MessageBubble
          key={message.id}
          message={message.role === 'assistant' && message.message_type === 'claim_draft' && (index !== lastAction || isLoading)
            ? { ...message, data: { ...message.data, confirm_required: false } } : message}
          loading={isLoading}
          onSuggestion={onSuggestion}
          onConfirmSubmit={onConfirmSubmit}
          onCancelSubmit={onCancelSubmit}
        />
      ))}
      {isLoading && streamText ? <StreamingText text={streamText} /> : isLoading ? <TypingIndicator label={progress} /> : null}
      <div ref={endRef} />
    </div>
  );
}
