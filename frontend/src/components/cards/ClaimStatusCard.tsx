import { Badge, type BadgeTone } from '../ui/Badge';
import { formatCurrency } from '../../lib/format';
import type { Claim } from '../../lib/types';

function statusMeta(status: string): { label: string; tone: BadgeTone } {
  const normalized = status.trim().toLowerCase();
  if (normalized === 'approved') return { label: 'Approved', tone: 'emerald' };
  if (normalized === 'under review') return { label: 'Under Review', tone: 'amber' };
  if (normalized === 'submitted') return { label: 'Submitted', tone: 'indigo' };
  return { label: status, tone: 'slate' };
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2">
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="text-right text-sm font-medium text-slate-900">{value}</dd>
    </div>
  );
}

export function ClaimStatusCard({ claim }: { claim: Claim }) {
  const meta = statusMeta(claim.status);

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-card">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-900">Claim status</h3>
        <Badge tone={meta.tone}>{meta.label}</Badge>
      </div>
      <dl className="divide-y divide-slate-100">
        <Row label="Claim ID" value={claim.claim_id} />
        <Row label="Policy" value={claim.policy_number} />
        <Row label="Type" value={claim.claim_type} />
        <Row label="Amount" value={formatCurrency(claim.amount)} />
      </dl>
    </div>
  );
}
