import type { ReactNode } from 'react';
import { FileTextIcon, SearchIcon, ShieldIcon, SparklesIcon } from '../ui/icons';

interface Starter {
  label: string;
  message: string;
  icon: ReactNode;
}

const STARTERS: Starter[] = [
  {
    label: 'Ask about coverage',
    message: 'Does my policy cover burst pipes?',
    icon: <SparklesIcon className="h-5 w-5" />,
  },
  {
    label: 'Track a claim',
    message: "What's the status of my claim?",
    icon: <SearchIcon className="h-5 w-5" />,
  },
  {
    label: 'File a claim',
    message: 'I want to file a claim for water damage.',
    icon: <FileTextIcon className="h-5 w-5" />,
  },
];

export function WelcomeScreen({ onSelect }: { onSelect: (text: string) => void }) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center py-10 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-600 text-white shadow-lg shadow-indigo-600/25">
        <ShieldIcon className="h-7 w-7" />
      </span>
      <h2 className="mt-5 text-2xl font-semibold tracking-tight text-slate-900">
        How can I help today?
      </h2>
      <p className="mt-2 max-w-md text-sm leading-relaxed text-slate-500">
        Ask about your coverage, check on a claim, or file a new one — I&apos;ll guide you
        through every step.
      </p>

      <div className="mt-8 w-full max-w-md space-y-3">
        {STARTERS.map((starter) => (
          <button
            key={starter.label}
            type="button"
            onClick={() => onSelect(starter.message)}
            className="flex w-full items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-left shadow-card transition-colors hover:border-indigo-300 hover:bg-indigo-50/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
          >
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
              {starter.icon}
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-slate-900">{starter.label}</span>
              <span className="block truncate text-xs text-slate-500">{starter.message}</span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
