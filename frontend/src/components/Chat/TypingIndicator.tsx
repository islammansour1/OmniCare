export function TypingIndicator({ label = 'Thinking…' }: { label?: string }) {
  return (
    <div
      className="flex items-center gap-1.5"
      role="status"
      aria-label="Assistant is thinking"
    >
      <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.3s]" />
      <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400 [animation-delay:-0.15s]" />
      <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400" />
      <span className="ml-2 text-xs text-slate-500">{label}</span>
    </div>
  );
}
