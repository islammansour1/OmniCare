import { useMemo, useState, type FormEvent } from 'react';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { Textarea } from '../ui/Textarea';
import type { ClaimDraft, ClaimDraftData } from '../../lib/types';


const LABELS: Record<string, string> = {
  policy_number: 'policy number',
  claim_type: 'claim type',
  amount: 'amount',
  description: 'description',
};

function labelFor(field: string): string {
  return LABELS[field] ?? field;
}

interface FormState {
  policyNumber: string;
  claimType: string;
  amount: string;
  description: string;
}

function toFormState(draft: ClaimDraft): FormState {
  const type = draft.claim_type ?? '';
  return {
    policyNumber: draft.policy_number ?? '',
    claimType: type,
    amount: draft.amount != null ? String(draft.amount) : '',
    description: draft.description ?? '',
  };
}

export interface ClaimReviewFormProps {
  data: ClaimDraftData;
  loading?: boolean;
  onConfirm: (draft: ClaimDraft) => void;
  onCancel: () => void;
}

export function ClaimReviewForm({ data, loading = false, onConfirm, onCancel }: ClaimReviewFormProps) {
  const [form, setForm] = useState<FormState>(() => toFormState(data.draft));
  const missing = useMemo(() => new Set(data.missing_fields ?? []), [data.missing_fields]);

  const effectiveType = form.claimType.trim();

  const amountValue = form.amount.trim() === '' ? null : Number(form.amount);
  const amountValid = amountValue !== null && Number.isFinite(amountValue) && amountValue > 0;

  const isComplete =
    form.policyNumber.trim() !== '' &&
    effectiveType !== '' &&
    amountValid &&
    form.description.trim() !== '';

  const missingList = (data.missing_fields ?? []).map(labelFor);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!isComplete || loading) return;
    onConfirm({
      policy_number: form.policyNumber.trim(),
      claim_type: effectiveType,
      amount: amountValue as number,
      description: form.description.trim(),
    });
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-card"
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-900">Review your claim</h3>
        {data.confirm_required ? <Badge tone="amber">Review required</Badge> : null}
      </div>

      {missingList.length > 0 ? (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
          Still needed: {missingList.join(', ')}
        </p>
      ) : null}

      <div className="space-y-3">
        <Field
          label="Policy number"
          htmlFor="claim-policy-number"
          required={missing.has('policy_number')}
        >
          <Input
            id="claim-policy-number"
            value={form.policyNumber}
            onChange={(e) => setForm((f) => ({ ...f, policyNumber: e.target.value }))}
            placeholder="e.g. POL-1092"
            aria-invalid={missing.has('policy_number')}
            autoComplete="off"
          />
        </Field>

        <Field
          label="Claim type"
          htmlFor="claim-type"
          required={missing.has('claim_type')}
        >
          <Input
            id="claim-type"
            value={form.claimType}
            onChange={(e) => setForm((f) => ({ ...f, claimType: e.target.value }))}
            maxLength={64}
            placeholder="Type of incident or loss"
            aria-invalid={missing.has('claim_type')}
          />
        </Field>

        <Field label="Amount (USD)" htmlFor="claim-amount" required={missing.has('amount')}>
          <Input
            id="claim-amount"
            value={form.amount}
            onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))}
            placeholder="e.g. 3500"
            inputMode="decimal"
            aria-invalid={missing.has('amount') || (form.amount.trim() !== '' && !amountValid)}
            autoComplete="off"
          />
        </Field>

        <Field
          label="Description"
          htmlFor="claim-description"
          required={missing.has('description')}
        >
          <Textarea
            id="claim-description"
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            placeholder="Briefly describe what happened"
            rows={3}
            aria-invalid={missing.has('description')}
          />
        </Field>
      </div>

      <div className="flex items-center gap-2">
        <Button type="submit" disabled={!isComplete} loading={loading}>
          Submit claim
        </Button>
        <Button type="button" variant="secondary" onClick={onCancel} disabled={loading}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

function Field({
  label,
  htmlFor,
  required,
  children,
}: {
  label: string;
  htmlFor: string;
  required: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label
        htmlFor={htmlFor}
        className="mb-1 flex items-center gap-2 text-xs font-medium text-slate-600"
      >
        {label}
        {required ? (
          <span className="rounded bg-rose-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-rose-600">
            Required
          </span>
        ) : null}
      </label>
      {children}
    </div>
  );
}
