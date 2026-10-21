import { afterEach, describe, expect, it, vi } from 'vitest';
import { streamChat } from './api';
const payload = { user_id: 'u1', message: 'hello', action: null, draft: null, request_id: 'r1' };
afterEach(() => vi.unstubAllGlobals());
function response(parts: string[]) {
  return new Response(new ReadableStream({ start(controller) {
    parts.forEach(part => controller.enqueue(new TextEncoder().encode(part))); controller.close();
  } }), { status: 200 });
}
describe('stream transport', () => {
  it('handles split frames, heartbeat and completed response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response([
      'data: {"type":"prog', 'ress","label":"Checking evidence"}\n\n: keepalive\n\n',
      'data: {"type":"result","response":{"response":"Done"}}\n\n',
    ])));
    const progress = vi.fn();
    expect((await streamChat(payload, progress)).response).toBe('Done');
    expect(progress).toHaveBeenCalledWith('Checking evidence');
  });
  it('does not treat a disconnected stream as success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(['data: {"type":"progress","label":"Checking"}\n\n'])));
    await expect(streamChat(payload, vi.fn())).rejects.toThrow('Connection interrupted');
  });
});
