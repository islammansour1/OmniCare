import { ChevronDownIcon } from '../ui/icons';
import type { Source } from '../../lib/types';

export function Citations({ sources }: { sources: Source[] }) {
  if (!sources || sources.length === 0) return null;

  return (
    <details className="group">
      <summary className="flex cursor-pointer list-none items-center gap-1 text-xs font-medium text-indigo-600 hover:text-indigo-700">
        <ChevronDownIcon className="h-3.5 w-3.5 transition-transform group-open:rotate-180" />
        Citations ({sources.length})
      </summary>
      <ul className="mt-2 space-y-2">
        {sources.map((source) => (
          <li
            key={source.id}
            className="rounded-lg border border-slate-100 bg-slate-50 p-3"
          >
            <div className="flex items-start justify-between gap-2">
              <span className="text-xs font-semibold text-slate-700">{source.section}</span>

            </div>
            <p className="mt-1 text-xs leading-relaxed text-slate-500">{source.text}</p>
          </li>
        ))}
      </ul>
    </details>
  );
}
