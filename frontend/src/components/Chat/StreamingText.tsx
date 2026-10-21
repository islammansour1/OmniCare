/** Streamed assistant prose shown while the final card is still being assembled. */
export function StreamingText({ text }: { text: string }) {
  return (
    <div className="flex justify-start" role="status" aria-label="Assistant is responding">
      <div className="max-w-[85%] rounded-2xl rounded-bl-md bg-slate-100 px-4 py-2.5 shadow-sm">
        <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-slate-700">
          {text}
          <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-slate-400 align-text-bottom" aria-hidden="true" />
        </p>
      </div>
    </div>
  );
}
