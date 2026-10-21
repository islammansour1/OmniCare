import { cn } from '../ui/cn';
import { MicIcon } from '../ui/icons';
import type { VoiceController, VoiceState } from '../../hooks/useVoice';

const STATE_LABEL: Record<VoiceState, string> = {
  idle: 'Tap to talk',
  listening: 'Listening…',
  processing: 'Processing…',
  speaking: 'Speaking…',
  error: 'Voice unavailable',
};

const MIC_CLASSES: Record<VoiceState, string> = {
  idle:
    'border border-slate-300 bg-white text-slate-600 hover:bg-slate-50',
  listening:
    'bg-rose-600 text-white ring-4 ring-rose-200 hover:bg-rose-700',
  processing: 'bg-amber-500 text-white ring-4 ring-amber-100',
  speaking: 'bg-indigo-600 text-white ring-4 ring-indigo-100',
  error: 'border border-rose-300 bg-white text-rose-600',
};

const LABEL_CLASSES: Record<VoiceState, string> = {
  idle: 'text-slate-500',
  listening: 'text-rose-600',
  processing: 'text-amber-600',
  speaking: 'text-indigo-600',
  error: 'text-rose-600',
};

export function VoiceControls({ voice }: { voice: VoiceController }) {
  if (!voice.isSupported) return null;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={voice.toggle}
          aria-pressed={voice.isActive}
          aria-label={voice.isActive ? 'Stop voice input' : 'Start voice input'}
          className={cn(
            'flex h-9 w-9 items-center justify-center rounded-full transition-colors',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2',
            MIC_CLASSES[voice.state],
          )}
        >
          <MicIcon className="h-4 w-4" />
        </button>
        <span className={cn('text-xs font-medium', LABEL_CLASSES[voice.state])}>
          {STATE_LABEL[voice.state]}
        </span>
      </div>

      {voice.error ? (
        <p role="alert" className="text-xs text-rose-600">
          {voice.error}
        </p>
      ) : null}

      {voice.transcript ? (
        <p
          aria-live="polite"
          className={cn(
            'text-xs',
            voice.isFinal ? 'text-slate-600' : 'italic text-slate-400',
          )}
        >
          “{voice.transcript}”
        </p>
      ) : null}
    </div>
  );
}
