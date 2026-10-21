import { useEffect, useState } from 'react';
import { useChat } from '../../hooks/useChat';
import { useVoice } from '../../hooks/useVoice';
import { getHealth } from '../../lib/api';
import type { HealthResponse } from '../../lib/types';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { PlusIcon, ShieldIcon } from '../ui/icons';
import { VoiceControls } from '../voice/VoiceControls';
import { Composer } from './Composer';
import { MessageList } from './MessageList';
import { WelcomeScreen } from './WelcomeScreen';

export function ChatShell({ userId }: { userId: string }) {
  const chat = useChat(userId);
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((result) => {
        if (!cancelled) setHealth(result);
      })
      .catch(() => {
        // The mode badge is best-effort; the chat still works without it.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const voice = useVoice({
    userId,
    conversationId: chat.conversationId,
    onAssistantMessage: chat.appendAssistant,
    onUserTranscript: chat.appendUser,
  });

  return (
    <div className="flex h-full flex-col">
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/80 backdrop-blur">
        <div className="mx-auto flex w-full max-w-[760px] items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-600 text-white shadow-sm">
              <ShieldIcon className="h-5 w-5" />
            </span>
            <div className="leading-tight">
              <h1 className="text-sm font-semibold text-slate-900">OmniCare AI</h1>
              <p className="text-xs text-slate-500">Your insurance assistant</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {health ? (
              <Badge tone={health.mode === 'live' ? 'emerald' : 'amber'}>
                {health.mode === 'live' ? 'Live' : 'Demo'}
              </Badge>
            ) : null}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void chat.clear()}
              disabled={chat.isLoading || voice.isActive}
              aria-label="Start a new chat"
            >
              <PlusIcon className="h-4 w-4" />
              New chat
            </Button>
          </div>
        </div>
      </header>

      <nav aria-label="Saved conversations" className="mx-auto flex w-full max-w-[760px] items-center gap-3 px-4 py-2">
        <label htmlFor="saved-chats" className="text-xs text-slate-500">Conversations</label>
        <select id="saved-chats" value={chat.conversationId} disabled={chat.isLoading || voice.isActive}
          onChange={e => void chat.select(e.target.value)} className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white p-2 text-sm">
          {!chat.conversationId && <option value="">Select a conversation</option>}
          {chat.conversations.map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
        </select>
      </nav>
      <main className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[760px] px-4">
          {chat.messages.length === 0 && !chat.isLoading ? (
            <WelcomeScreen onSelect={(text) => void chat.send(text)} />
          ) : (
            <MessageList
              messages={chat.messages}
              isLoading={chat.isLoading || voice.isActive}
              progress={chat.progress}
              onSuggestion={(text) => void chat.send(text)}
              onConfirmSubmit={(draft) => void chat.confirmSubmit(draft)}
              onCancelSubmit={() => void chat.cancelSubmit()}
            />
          )}
        </div>
      </main>

      <footer className="border-t border-slate-200 bg-white/60">
        <div className="mx-auto w-full max-w-[760px] space-y-2 px-4 py-3">
          {chat.error ? (
            <p role="alert" className="text-xs font-medium text-rose-600">
              {chat.error}
              {chat.canRetry && <button className="ml-3 underline" disabled={chat.isLoading} onClick={() => void chat.retry()}>Retry</button>}
            </p>
          ) : null}
          {!chat.isLoading && chat.conversationId && <VoiceControls voice={voice} />}
          <Composer onSend={(text) => void chat.send(text)} disabled={chat.isLoading || voice.isActive || !chat.conversationId || chat.canRetry} />
        </div>
      </footer>
    </div>
  );
}
