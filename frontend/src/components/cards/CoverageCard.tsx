import { Badge, type BadgeTone } from '../ui/Badge';
import { Citations } from './Citations';
import type { CoverageAnswerData, Source, Verdict } from '../../lib/types';

const verdictMeta: Record<Verdict, { label: string; tone: BadgeTone }> = {
  covered: { label: 'Covered', tone: 'emerald' },
  excluded: { label: 'Excluded', tone: 'rose' },
  conditional: { label: 'Conditional', tone: 'amber' },
  uncertain: { label: 'More information needed', tone: 'amber' },
  unsupported: { label: 'Unsupported', tone: 'slate' },
};

export function CoverageCard({ data, sources }: { data: CoverageAnswerData; sources: Source[] }) {
  const meta = verdictMeta[data.verdict] ?? { label: data.verdict, tone: 'slate' as const };

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-card">
      <div className="mb-2">
        <Badge tone={meta.tone}>{meta.label}</Badge>
      </div>
      <p className="text-sm leading-relaxed text-slate-700">{data.answer}</p>
      <div className="mt-3 border-t border-slate-100 pt-3">
        <Citations sources={sources} />
      </div>
    </div>
  );
}
