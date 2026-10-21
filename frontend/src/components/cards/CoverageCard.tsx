import { Citations } from './Citations';
import type { CoverageAnswerData, Source } from '../../lib/types';

export function CoverageCard({ data, sources }: { data: CoverageAnswerData; sources: Source[] }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-card">
      <p className="text-sm leading-relaxed text-slate-700">{data.answer}</p>
      <div className="mt-3 border-t border-slate-100 pt-3">
        <Citations sources={sources} />
      </div>
    </div>
  );
}
