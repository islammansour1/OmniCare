import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, postChat } from './api';

const CHAT_PAYLOAD = {
  user_id: 'usr_1',
  message: 'hello',
  action: null,
  draft: null,
  request_id: null,
} as const;

const OK_CHAT = {
  response: 'hi',
  sources: [],
  tool_calls: [],
  message_type: 'chat',
  data: {},
  request_id: 'req_1',
  mode: 'demo',
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('postChat', () => {
  it('builds the correct request and parses the response', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => OK_CHAT,
    });
    vi.stubGlobal('fetch', fetchMock);

    const res = await postChat({ ...CHAT_PAYLOAD });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/v1/chat');
    expect(init.method).toBe('POST');
    expect(init.headers).toMatchObject({ 'Content-Type': 'application/json' });
    expect(JSON.parse(init.body as string)).toEqual({ ...CHAT_PAYLOAD });
    expect(res.message_type).toBe('chat');
    expect(res.response).toBe('hi');
  });

  it('throws ApiError carrying the FastAPI detail on non-2xx', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({ detail: 'Validation failed' }),
      }),
    );

    const promise = postChat({ ...CHAT_PAYLOAD });
    await expect(promise).rejects.toBeInstanceOf(ApiError);
    await expect(promise).rejects.toMatchObject({
      name: 'ApiError',
      status: 422,
      detail: 'Validation failed',
    });
  });

  it('falls back to a generic message when the error body has no detail', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ not: 'detail' }),
      }),
    );

    await expect(postChat({ ...CHAT_PAYLOAD })).rejects.toThrow(
      'Request failed with status 500',
    );
  });
});
