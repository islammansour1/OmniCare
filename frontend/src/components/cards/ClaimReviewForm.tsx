import { useMemo, useState, type FormEvent } from 'react';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { Select } from '../ui/Select';
import { Textarea } from '../ui/Textarea';
import type { ClaimDraft, ClaimDraftData } from '../../lib/types';

const CLAIM_TYPES = [
  'Water Damage',
  'Personal Property',
  'Fire',
  'Theft',
  'Storm/Wind',
  'Vandalism',
];

const POLICY_RE = /^[A-Za-z0-9-]{3,32}$/;

const LABELS: Record<string, string> = {
  policy_number: 'policy number',
  claim_type: 'claim type',
  amount: 'amount',
  description: 'description',
};

function labelFor(field: string): string {
  return LABELS[field] ?? field;
}

/** Parse a typed amount, tolerating $, commas and surrounding whitespace. */
function parseAmount(raw: string): number | null {
  const cleaned = raw.replace(/[$,\s]/g, '');
  if (cleaned === '') return null;
  const value = Number(cleaned);
  return Number.isFinite(value) ? value : null;
}

interface FormState {
  policyNumber: string;
  claimType: string;
  amount: string;
  description: string;
}

type FormErrors = Partial<Record<keyof FormState, string>>;

function toFormState(draft: ClaimDraft): FormState {
  return {
    policyNumber: draft.policy_number ?? '',
    claimType: draft.claim_type ?? '',
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

export function ClaimReviewForm({
  data,
  loading = false,
  onConfirm,
  onCancel,
}: ClaimReviewFormProps) {
  const [form, setForm] = useState<FormState>(() => toFormState(data.draft));
  const [attempted, setAttempted] = useState(false);
  const missing = useMemo(() => new Set(data.missing_fields ?? []), [data.missing_fields]);

  // Keep an extracted claim type selectable even when it isn't in the curated list.
  const claimTypeOptions = useMemo(() => {
    const current = form.claimType.trim();
    const options = [...CLAIM_TYPES];
    if (current && !options.some((o) => o.toLowerCase() === current.toLowerCase())) {
      options.push(current);
    }
    return options;
  }, [form.claimType]);

  const amountValue = parseAmount(form.amount);

  const errors: FormErrors = {};
  if (form.policyNumber.trim() === '') {
    errors.policyNumber = 'Enter your policy number.';
  } else if (!POLICY_RE.test(form.policyNumber.trim())) {
    errors.policyNumber = 'Policy numbers are letters, numbers and dashes (e.g. POL-1092).';
  }
  if (form.claimType.trim() === '') {
    errors.claimType = 'Choose a claim type.';
  }
  if (amountValue === null || amountValue <= 0) {
    errors.amount =
      form.amount.trim() === '' ? 'Enter the estimated amount.' : 'Enter a valid amount (e.g. 3500).';
  }
  if (form.description.trim() === '') {
    errors.description = 'Briefly describe what happened.';
  }

  const isValid = Object.keys(errors).length === 0;
  const showErrors = attempted && !isValid;
  const missingList = (data.missing_fields ?? []).map(labelFor);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAttempted(true);
    if (!isValid || loading) return;
    onConfirm({
      policy_number: form.policyNumber.trim(),
      claim_type: form.claimType.trim(),
      amount: amountValue as number,
      description: form.description.trim(),
    });
  }

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-card"
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">Confirm your claim details</h3>
          <p className="text-xs text-slate-500">
            Review what I understood and fill in anything missing.
          </p>
        </div>
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
          error={showErrors ? errors.policyNumber : undefined}
        >
          <Input
            id="claim-policy-number"
            value={form.policyNumber}
            onChange={(e) => setForm((f) => ({ ...f, policyNumber: e.target.value }))}
            placeholder="e.g. POL-1092"
            aria-invalid={showErrors && !!errors.policyNumber}
            autoComplete="off"
          />
        </Field>

        <Field
          label="Claim type"
          htmlFor="claim-type"
          required={missing.has('claim_type')}
          error={showErrors ? errors.claimType : undefined}
        >
          <Select
            id="claim-type"
            value={form.claimType}
            onChange={(e) => setForm((f) => ({ ...f, claimType: e.target.value }))}
            aria-invalid={showErrors && !!errors.claimType}
          >
            <option value="">Select a type…</option>
            {claimTypeOptions.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </Select>
        </Field>

        <Field
          label="Estimated amount (USD)"
          htmlFor="claim-amount"
          required={missing.has('amount')}
          error={showErrors ? errors.amount : undefined}
        >
          <div className="relative">
            <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-slate-400">
              $
            </span>
            <Input
              id="claim-amount"
              value={form.amount}
              onChange={(e) => setForm((f) => ({ ...f, amount: e.target.value }))}
              placeholder="3500"
              inputMode="decimal"
              className="pl-6"
              aria-invalid={showErrors && !!errors.amount}
              autoComplete="off"
            />
          </div>
        </Field>

        <Field
          label="What happened"
          htmlFor="claim-description"
          required={missing.has('description')}
          error={showErrors ? errors.description : undefined}
        >
          <Textarea
            id="claim-description"
            value={form.description}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            placeholder="Briefly describe what happened"
            rows={3}
            aria-invalid={showErrors && !!errors.description}
          />
        </Field>
      </div>

      <div className="flex items-center gap-2">
        <Button type="submit" loading={loading} disabled={loading}>
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
  error,
  children,
}: {
  label: string;
  htmlFor: string;
  required: boolean;
  error?: string;
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
      {error ? (
        <p role="alert" className="mt-1 text-xs text-rose-600">
          {error}
        </p>
      ) : null}
    </div>
  );
}
