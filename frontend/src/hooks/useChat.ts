import { useCallback, useEffect, useRef, useState } from 'react';
import { createConversation, listConversations, loadConversation, streamChat } from '../lib/api';
import { randomId } from '../lib/id';
import type { ChatMessage, ChatRequest, ChatResponse, ClaimDraft, Conversation } from '../lib/types';

export function useChat(userId: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState('Loading conversation');
  const [lastFailedRequest, setLastFailedRequest] = useState<ChatRequest | null>(null);
  const busy = useRef(false);
  const selectVersion = useRef(0);

  const select = useCallback(async (id: string) => {
    if (busy.current) return;
    const version = ++selectVersion.current;
    setIsLoading(true); setProgress('Loading conversation'); setError(null);
    try {
      const result = await loadConversation(id);
      if (version !== selectVersion.current) return;
      setConversationId(id); setMessages(result.messages); setLastFailedRequest(null);
      localStorage.setItem(`omnicare-active-${userId}`, id);
    } catch (err) { if (version === selectVersion.current) setError(String(err)); }
    finally { if (version === selectVersion.current) setIsLoading(false); }
  }, [userId]);

  const clear = useCallback(async () => {
    if (busy.current) return;
    busy.current = true; setIsLoading(true); setError(null);
    try {
      const created = await createConversation();
      setConversations(prev => [created, ...prev]);
      busy.current = false;
      await select(created.id);
    } catch (err) { setError(String(err)); setIsLoading(false); }
    finally { busy.current = false; }
  }, [select]);

  useEffect(() => {
    let cancelled = false;
    listConversations().then(async items => {
      if (cancelled) return;
      setConversations(items);
      const remembered = localStorage.getItem(`omnicare-active-${userId}`);
      const id = items.find(c => c.id === remembered)?.id ?? items[0]?.id;
      if (id) await select(id);
      else await clear();
    }).catch(err => { if (!cancelled) { setError(String(err)); setIsLoading(false); } });
    return () => { cancelled = true; ++selectVersion.current; };
  }, [userId, select, clear]);

  const appendUser = useCallback((text: string) => {
    setMessages(prev => [...prev, { id: randomId('u'), role: 'user', text }]);
  }, []);
  const appendAssistant = useCallback((response: ChatResponse) => {
    setMessages(prev => [...prev, { id: randomId('a'), role: 'assistant', ...response } as ChatMessage]);
    void listConversations().then(setConversations).catch(() => {});
  }, []);

  const submit = useCallback(async (payload: ChatRequest, retry = false) => {
    if (busy.current || !conversationId) return;
    busy.current = true; setIsLoading(true); setError(null); setProgress('Connecting');
    // Action-driven turns (confirm/cancel) are button clicks, not typed messages,
    // so don't inject a synthetic user bubble for them.
    if (!retry && !payload.action) appendUser(payload.message);
    try {
      const response = await streamChat(payload, setProgress);
      if (response.message_type === 'error') throw new Error(response.response);
      appendAssistant(response); setLastFailedRequest(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed.'); setLastFailedRequest(payload);
    } finally { busy.current = false; setIsLoading(false); }
  }, [conversationId, appendUser, appendAssistant]);

  const send = (message: string) => message.trim() ? submit({ user_id: userId, conversation_id: conversationId,
    message: message.trim(), action: null, draft: null, request_id: randomId('req') }) : Promise.resolve();
  const confirmSubmit = (draft: ClaimDraft) => submit({ user_id: userId, conversation_id: conversationId,
    message: 'Confirm claim submission', action: 'confirm_submit', draft, request_id: randomId('req') });
  const cancelSubmit = () => submit({ user_id: userId, conversation_id: conversationId,
    message: 'Cancel claim submission', action: 'cancel_submit', draft: null, request_id: randomId('req') });
  const retry = () => lastFailedRequest ? submit(lastFailedRequest, true) : Promise.resolve();

  // Re-fetch the current conversation (e.g. after a spoken voice turn) without
  // the full select() ceremony.
  const refresh = useCallback(async () => {
    if (!conversationId) return;
    try {
      const result = await loadConversation(conversationId);
      setMessages(result.messages);
    } catch {
      // best-effort — keep the current view if the refresh fails
    }
  }, [conversationId]);

  return { messages, conversations, conversationId, select, isLoading, error, progress, canRetry: !!lastFailedRequest,
    send, confirmSubmit, cancelSubmit, retry, refresh, appendUser, appendAssistant, clear };
}
