import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MessageList } from './MessageList';
import { makeAssistant, makeClaim } from '../../test/factories';

const noop = {
  onSuggestion: vi.fn(),
  onConfirmSubmit: vi.fn(),
  onCancelSubmit: vi.fn(),
};

describe('MessageList', () => {
  it('routes coverage_answer to CoverageCard', () => {
    render(
      <MessageList
        messages={[makeAssistant('coverage_answer', { answer: 'Yes', verdict: 'covered' })]}
        {...noop}
      />,
    );
    expect(screen.getByText('Yes')).toBeInTheDocument();
  });

  it('routes claim_status to ClaimStatusCard', () => {
    render(
      <MessageList
        messages={[makeAssistant('claim_status', { claim: makeClaim() })]}
        {...noop}
      />,
    );
    expect(screen.getByText('CLM-8821')).toBeInTheDocument();
  });

  it('routes claim_draft to ClaimReviewForm', () => {
    render(
      <MessageList
        messages={[
          makeAssistant('claim_draft', {
            draft: { policy_number: 'POL-1', claim_type: null, amount: null, description: null },
            missing_fields: ['claim_type'],
            confirm_required: true,
          }),
        ]}
        {...noop}
      />,
    );
    expect(screen.getByRole('button', { name: /submit claim/i })).toBeInTheDocument();
  });

  it('shows verified citations with the final claim form', () => {
    const message = makeAssistant('claim_draft', {
      draft: { policy_number: null, claim_type: null, amount: null, description: null },
      missing_fields: [], confirm_required: true,
    });
    if (message.role !== 'assistant') throw new Error('Expected assistant fixture');
    message.sources = [{ id: 'sec1', section: 'Policy evidence', text: 'Verified terms.', score: 1 }];
    render(<MessageList messages={[message]} {...noop} />);
    expect(screen.getByText('Citations (1)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /submit claim/i })).toBeInTheDocument();
  });

  it('routes clarification to ClarificationCard', () => {
    render(
      <MessageList
        messages={[
          makeAssistant('clarification', {
            question: 'Which claim would you like to track?',
            missing_fields: ['claim_id'],
          }),
        ]}
        {...noop}
      />,
    );
    expect(screen.getByText('Which claim would you like to track?')).toBeInTheDocument();
  });

  it('routes error to ErrorCard', () => {
    render(
      <MessageList
        messages={[makeAssistant('error', { code: 'NOT_FOUND', detail: 'Claim not found' })]}
        {...noop}
      />,
    );
    expect(screen.getByText('Claim not found')).toBeInTheDocument();
  });

});
