import { Badge } from '../ui/Badge';
import type { ClarificationData } from '../../lib/types';

const LABELS: Record<string, string> = {
  policy_number: 'policy number',
  claim_type: 'claim type',
  amount: 'amount',
  description: 'description',
  claim_id: 'claim ID',
};

function labelFor(field: string): string {
  return LABELS[field] ?? field;
}

export function ClarificationCard({ data }: { data: ClarificationData }) {
  const missing = data.missing_fields ?? [];

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-card">
      <p className="text-sm leading-relaxed text-slate-700">{data.question}</p>
      {missing.length > 0 ? (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-medium text-slate-500">Still needed:</span>
          {missing.map((field) => (
            <Badge key={field} tone="amber">
              {labelFor(field)}
            </Badge>
          ))}
        </div>
      ) : null}
    </div>
  );
}
