import type { ChatRequest, ChatResponse, HealthResponse, Conversation, ChatMessage } from './types';

const DEFAULT_BASE = '/api/v1';

function getBase(): string {
  return import.meta.env.VITE_API_BASE ?? DEFAULT_BASE;
}

/** Typed error carrying the HTTP status and FastAPI `detail` message. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${getBase()}${path}`, {
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
      ...init,
    });
  } catch (err) {
    throw new ApiError(0, err instanceof Error ? err.message : 'Network error');
  }

  if (!res.ok) {
    let detail = `Request failed with status ${res.status}`;
    try {
      const body: unknown = await res.json();
      if (
        typeof body === 'object' &&
        body !== null &&
        typeof (body as { detail?: unknown }).detail === 'string'
      ) {
        detail = (body as { detail: string }).detail;
      }
    } catch {
      // non-JSON error body — fall back to the generic message
    }
    throw new ApiError(res.status, detail);
  }

  return (await res.json()) as T;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health');
}

export function postChat(payload: ChatRequest): Promise<ChatResponse> {
  return request<ChatResponse>('/chat', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}


let sessionPromise: Promise<{ user_id: string }> | null = null;
export function getSession(): Promise<{ user_id: string }> {
  if (!sessionPromise) sessionPromise = request<{ user_id: string }>('/session', { method: 'POST' })
    .catch((err) => { sessionPromise = null; throw err; });
  return sessionPromise;
}
export const listConversations = () => request<Conversation[]>('/conversations');
export const createConversation = () => request<Conversation>('/conversations', { method: 'POST' });
export const loadConversation = (id: string) => request<{ messages: ChatMessage[] }>(`/conversations/${encodeURIComponent(id)}`);

/** LiveKit voice: fetch a signed access token for the user's voice room. */
export function getVoiceToken(
  userId: string,
  conversationId?: string,
): Promise<{ url: string; token: string; room: string }> {
  const params = new URLSearchParams({ user_id: userId });
  if (conversationId) params.set('conversation_id', conversationId);
  return request<{ url: string; token: string; room: string }>(
    `/voice/token?${params.toString()}`,
    { method: 'POST' },
  );
}

/** Stream real server progress; the completed response is one atomic card. */
export async function streamChat(payload: ChatRequest, progress: (label: string) => void): Promise<ChatResponse> {
  const res = await fetch(`${getBase()}/chat/stream`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
  if (!res.ok) throw new ApiError(res.status, res.status === 401 ? 'Your session expired. Reload the page.' : 'Unable to send. Please retry.');
  const reader = res.body?.getReader();
  if (!reader) throw new Error('Streaming is unavailable. Please retry.');
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let end: number;
      while ((end = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, end); buffer = buffer.slice(end + 2);
        const data = frame.split('\n').filter((l) => l.startsWith('data:')).map((l) => l.slice(5).trim()).join('\n');
        if (!data) continue;
        const event = JSON.parse(data);
        if (event.type === 'progress') progress(event.label);
        if (event.type === 'result') return event.response as ChatResponse;
        if (event.type === 'error') throw new Error(event.detail);
      }
      if (done) throw new Error('Connection interrupted. Retry to recover the response.');
    }
  } finally { await reader.cancel(); reader.releaseLock(); }
}
