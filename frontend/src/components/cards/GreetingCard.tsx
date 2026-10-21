import type { GreetingData } from '../../lib/types';

export function GreetingCard({
  data,
  onSuggestion,
}: {
  data: GreetingData;
  onSuggestion?: (text: string) => void;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-card">
      <p className="text-sm leading-relaxed text-slate-700">{data.text}</p>
      {data.suggestions && data.suggestions.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {data.suggestions.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              onClick={() => onSuggestion?.(suggestion)}
              className="rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-medium text-indigo-700 transition-colors hover:bg-indigo-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
            >
              {suggestion}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
