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
    expect(screen.getByLabelText(/claim type/i)).toHaveValue('Equipment malfunction');
    expect(screen.getByDisplayValue('3500')).toBeInTheDocument();
    expect(screen.getByDisplayValue('A pipe burst in my kitchen')).toBeInTheDocument();
    expect(screen.getByText(/Still needed: amount/)).toBeInTheDocument();
    expect(screen.getByText('Required')).toBeInTheDocument();
  });

  it('shows field errors and does not confirm when submitted incomplete', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();

    render(
      <ClaimReviewForm
        data={makeData({ policy_number: null, claim_type: null, amount: null, description: null })}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('button', { name: /submit claim/i }));

    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.getByText(/Enter your policy number/)).toBeInTheDocument();
    expect(screen.getByText(/Choose a claim type/)).toBeInTheDocument();
    expect(screen.getByText(/Enter the estimated amount/)).toBeInTheDocument();
    expect(screen.getByText(/Briefly describe what happened/)).toBeInTheDocument();
  });

  it('confirms the edited draft when valid', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();

    render(
      <ClaimReviewForm
        data={makeData({ policy_number: null, claim_type: null, amount: null, description: null })}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );

    await user.type(screen.getByLabelText(/policy number/i), 'POL-1');
    await user.selectOptions(screen.getByLabelText(/claim type/i), 'Water Damage');
    await user.type(screen.getByLabelText(/estimated amount/i), '3500');
    await user.type(screen.getByLabelText(/what happened/i), 'A pipe burst');
    await user.click(screen.getByRole('button', { name: /submit claim/i }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onConfirm).toHaveBeenCalledWith({
      policy_number: 'POL-1',
      claim_type: 'Water Damage',
      amount: 3500,
      description: 'A pipe burst',
    });
  });

  it('tolerates $ and commas in the amount', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();

    render(
      <ClaimReviewForm
        data={makeData({
          policy_number: 'POL-1',
          claim_type: 'Water Damage',
          amount: null,
          description: 'A pipe burst',
        })}
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );

    await user.type(screen.getByLabelText(/estimated amount/i), '$3,500');
    await user.click(screen.getByRole('button', { name: /submit claim/i }));

    expect(onConfirm).toHaveBeenCalledWith(
      expect.objectContaining({ amount: 3500 }),
    );
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

  it('does not confirm while loading', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();

    render(
      <ClaimReviewForm
        data={makeData({
          policy_number: 'POL-1',
          claim_type: 'Water Damage',
          amount: 3500,
          description: 'A pipe burst',
        })}
        loading
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('button', { name: /submit claim/i }));
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
