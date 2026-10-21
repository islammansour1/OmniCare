import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useChat } from './useChat';
import * as api from '../lib/api';
import type { ChatResponse } from '../lib/types';
vi.mock('../lib/api', () => ({ createConversation: vi.fn(), listConversations: vi.fn(), loadConversation: vi.fn(), streamChat: vi.fn() }));
const reply: ChatResponse = { response: 'Hello', message_type:'chat', data:{}, sources:[], tool_calls:[], request_id:'r', mode:'demo' };
beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear();
  vi.mocked(api.listConversations).mockResolvedValue([{ id:'c1', title:'Saved chat', updated:1 }]);
  vi.mocked(api.loadConversation).mockResolvedValue({ messages:[{ id:'a1', role:'assistant', ...reply }] });
  vi.mocked(api.createConversation).mockResolvedValue({ id:'c2', title:'New conversation', updated:2 });
  vi.mocked(api.streamChat).mockResolvedValue(reply);
});
describe('saved chat journeys', () => {
  it('restores server history and switches to a genuinely new conversation', async () => {
    const { result } = renderHook(() => useChat('u1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.messages).toHaveLength(1);
    vi.mocked(api.loadConversation).mockResolvedValueOnce({ messages:[] });
    await act(async () => { await result.current.clear(); });
    expect(result.current.conversationId).toBe('c2');
    expect(result.current.messages).toHaveLength(0);
    await act(async () => { await result.current.send('Hello'); });
    expect(api.streamChat).toHaveBeenCalledWith(expect.objectContaining({ conversation_id:'c2' }), expect.any(Function), expect.any(Function));
  });
  it('retries the same request ID without duplicating the user message', async () => {
    const { result } = renderHook(() => useChat('u1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    vi.mocked(api.streamChat).mockRejectedValueOnce(new Error('Disconnected'));
    await act(async () => { await result.current.send('Check my claim'); });
    expect(result.current.canRetry).toBe(true);
    const original = vi.mocked(api.streamChat).mock.calls[0][0];
    await act(async () => { await result.current.retry(); });
    expect(vi.mocked(api.streamChat).mock.calls[1][0]).toEqual(original);
    expect(result.current.messages.filter(m => m.role==='user')).toHaveLength(1);
    expect(result.current.canRetry).toBe(false);
  });
});
