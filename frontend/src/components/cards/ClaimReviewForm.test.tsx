import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ClaimReviewForm } from './ClaimReviewForm';
import type { ClaimDraftData } from '../../lib/types';

function makeData(draft: ClaimDraftData['draft'], missing_fields: string[] = []): ClaimDraftData {
  return { draft, missing_fields, confirm_required: true };
}

describe('ClaimReviewForm', () => {
  it('renders a prefilled draft and highlights missing fields', () => {
    render(
      <ClaimReviewForm
        data={makeData(
          {
            policy_number: 'POL-1092',
            claim_type: 'Equipment malfunction',
            amount: 3500,
            description: 'A pipe burst in my kitchen',
          },
          ['amount'],
        )}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    expect(screen.getByDisplayValue('POL-1092')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Equipment malfunction')).toBeInTheDocument();
    expect(screen.getByDisplayValue('3500')).toBeInTheDocument();
    expect(screen.getByDisplayValue('A pipe burst in my kitchen')).toBeInTheDocument();
    expect(screen.getByText(/Still needed: amount/)).toBeInTheDocument();
    expect(screen.getByText('Required')).toBeInTheDocument();
  });

  it('disables submit until all required fields are filled, then confirms the edited draft', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();

    render(
      <ClaimReviewForm
        data={makeData(
          { policy_number: null, claim_type: null, amount: null, description: null },
          ['policy_number', 'claim_type', 'amount', 'description'],
        )}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );

    const submit = screen.getByRole('button', { name: /submit claim/i });
    expect(submit).toBeDisabled();

    await user.type(screen.getByLabelText(/policy number/i), 'POL-1');
    await user.type(screen.getByLabelText(/claim type/i), 'Equipment malfunction');
    await user.type(screen.getByLabelText(/amount/i), '3500');
    await user.type(screen.getByLabelText(/description/i), 'A pipe burst');

    expect(submit).toBeEnabled();
    await user.click(submit);

    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm).toHaveBeenCalledWith({
      policy_number: 'POL-1',
      claim_type: 'Equipment malfunction',
      amount: 3500,
      description: 'A pipe burst',
    });
  });

  it('calls onCancel when the cancel button is clicked', async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();

    render(
      <ClaimReviewForm
        data={makeData({ policy_number: 'POL-1', claim_type: null, amount: null, description: null })}
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />,
    );

    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('does not call onConfirm while loading or when incomplete', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();

    render(
      <ClaimReviewForm
        data={makeData(
          { policy_number: null, claim_type: null, amount: null, description: null },
          ['policy_number', 'claim_type', 'amount', 'description'],
        )}
        loading
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );

    const submit = screen.getByRole('button', { name: /submit claim/i });
    expect(submit).toBeDisabled();
    await user.click(submit);
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
