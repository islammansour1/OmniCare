import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { cn } from '../ui/cn';
import { Button } from '../ui/Button';
import { SendIcon } from '../ui/icons';

const MAX_LENGTH = 4000;

export interface ComposerProps {
  onSend: (text: string) => void;
  disabled?: boolean;
}

export function Composer({ onSend, disabled = false }: ComposerProps) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const resize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, []);

  useEffect(() => {
    resize();
  }, [value, resize]);

  const submit = useCallback(() => {
    const text = value.trim();
    if (!text || disabled) return;
    onSend(text);
    setValue('');
  }, [value, disabled, onSend]);

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  const canSend = !disabled && value.trim().length > 0;

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-sm transition-shadow focus-within:border-indigo-400 focus-within:ring-2 focus-within:ring-indigo-100">
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={handleKeyDown}
        rows={1}
        maxLength={MAX_LENGTH}
        placeholder="Message OmniCare AI…"
        aria-label="Message"
        className="block w-full resize-none bg-transparent px-4 pb-1 pt-3 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none"
      />
      <div className="flex items-center justify-between px-3 pb-2">
        <span
          className={cn(
            'text-xs',
            value.length > MAX_LENGTH - 400 ? 'text-amber-600' : 'text-slate-400',
          )}
        >
          {value.length > MAX_LENGTH - 800
            ? `${value.length}/${MAX_LENGTH}`
            : 'Enter to send · Shift+Enter for a new line'}
        </span>
        <Button
          type="button"
          size="sm"
          onClick={submit}
          disabled={!canSend}
          loading={disabled}
          aria-label="Send message"
        >
          <SendIcon className="h-4 w-4" />
          Send
        </Button>
      </div>
    </div>
  );
}
