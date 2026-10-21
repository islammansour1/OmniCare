import { Badge } from '../ui/Badge';
import { CheckIcon } from '../ui/icons';
import { formatCurrency } from '../../lib/format';
import type { ClaimConfirmationData } from '../../lib/types';

export function ClaimConfirmationCard({ data }: { data: ClaimConfirmationData }) {
  const { claim } = data;

  return (
    <div className="overflow-hidden rounded-xl border border-emerald-200 bg-white shadow-card">
      <div className="flex items-center gap-3 border-b border-emerald-100 bg-emerald-50 px-4 py-3">
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-600 text-white">
          <CheckIcon className="h-4 w-4" />
        </span>
        <div>
          <p className="text-sm font-semibold text-emerald-900">Claim submitted</p>
          <p className="text-xs text-emerald-700">Your claim has been received and is being reviewed.</p>
        </div>
        <div className="ml-auto">
          <Badge tone="indigo">Submitted</Badge>
        </div>
      </div>
      <dl className="divide-y divide-slate-100 px-4">
        <Row label="Claim ID" value={claim.claim_id} />
        <Row label="Policy" value={claim.policy_number} />
        <Row label="Type" value={claim.claim_type} />
        <Row label="Amount" value={formatCurrency(claim.amount)} />
      </dl>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5">
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="text-right text-sm font-semibold text-slate-900">{value}</dd>
    </div>
  );
}
