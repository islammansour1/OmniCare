import type { ChatMessage, ChatResponse, Claim, MessageType, Source } from '../lib/types';

export function makeClaim(overrides: Partial<Claim> = {}): Claim {
  return {
    claim_id: 'CLM-8821',
    policy_number: 'POL-1092',
    claim_type: 'Water Damage',
    status: 'Approved',
    amount: 3500,
    ...overrides,
  };
}

export function makeSources(): Source[] {
  return [
    {
      id: 'sec1',
      section: 'Section 1 — Home Water Damage Coverage',
      text: 'Water damage caused by sudden pipe bursts is covered up to $25,000 with a $500 deductible.',
      score: 0.91,
    },
  ];
}

export function makeAssistant<K extends MessageType>(
  message_type: K,
  data: Extract<ChatResponse, { message_type: K }>['data'],
): ChatMessage {
  return {
    id: 'a1',
    role: 'assistant',
    response: 'Here you go.',
    sources: [],
    tool_calls: [],
    request_id: null,
    mode: 'demo',
    message_type,
    data,
  } as ChatMessage;
}
