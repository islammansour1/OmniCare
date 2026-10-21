import { useCallback, useEffect, useRef, useState } from 'react';
import type { ChatResponse } from '../lib/types';

/**
 * Client-side voice state. Extends the server states with a client-only
 * `error` state for microphone / websocket failures.
 */
export type VoiceState = 'idle' | 'listening' | 'processing' | 'speaking' | 'error';

export interface VoiceController {
  state: VoiceState;
  transcript: string;
  isFinal: boolean;
  error: string | null;
  isSupported: boolean;
  isActive: boolean;
  start: () => Promise<void>;
  stop: () => void;
  toggle: () => void;
}

interface UseVoiceOptions {
  userId: string;
  conversationId: string;
  /** Append a final assistant turn (ChatResponse) to the shared chat state. */
  onAssistantMessage: (message: ChatResponse) => void;
  /** Append the user's finalized spoken transcript to the chat state. */
  onUserTranscript: (text: string) => void;
}

type ServerVoiceState = 'listening' | 'processing' | 'speaking' | 'idle';

type ServerMessage =
  | { type: 'state'; state: ServerVoiceState }
  | { type: 'transcript'; text: string; final: boolean }
  | { type: 'message'; message: ChatResponse }
  | { type: 'error'; detail: string };

const VOICE_STATES: ReadonlyArray<string> = ['listening', 'processing', 'speaking', 'idle'];

function parseServerMessage(raw: string): ServerMessage | null {
  let obj: unknown;
  try {
    obj = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof obj !== 'object' || obj === null) return null;
  const record = obj as Record<string, unknown>;
  switch (record.type) {
    case 'state':
      if (typeof record.state === 'string' && VOICE_STATES.includes(record.state)) {
        return { type: 'state', state: record.state as ServerVoiceState };
      }
      return null;
    case 'transcript':
      return {
        type: 'transcript',
        text: typeof record.text === 'string' ? record.text : '',
        final: record.final === true,
      };
    case 'message':
      if (typeof record.message === 'object' && record.message !== null) {
        return { type: 'message', message: record.message as ChatResponse };
      }
      return null;
    case 'error':
      return {
        type: 'error',
        detail: typeof record.detail === 'string' ? record.detail : 'Voice error',
      };
    default:
      return null;
  }
}

function buildVoiceUrl(userId: string, conversationId: string): string {
  const override = import.meta.env.VITE_WS_BASE;
  const base = override
    ? override
    : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;
  return `${base.replace(/\/+$/, '')}/api/v1/voice?user_id=${encodeURIComponent(userId)}&conversation_id=${encodeURIComponent(conversationId)}`;
}

/** Downsample a Float32 mono buffer to 16-bit little-endian PCM at 16 kHz. */
function downsampleToPcm16(
  input: Float32Array,
  inputSampleRate: number,
  outputSampleRate: number,
): Int16Array {
  const ratio = inputSampleRate / outputSampleRate;
  const length = Math.max(1, Math.round(input.length / ratio));
  const out = new Int16Array(length);
  for (let i = 0; i < length; i++) {
    const pos = i * ratio;
    const idx = Math.floor(pos);
    const frac = pos - idx;
    const a = input[idx] ?? 0;
    const b = input[idx + 1] ?? a;
    const sample = Math.max(-1, Math.min(1, a + (b - a) * frac));
    out[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return out;
}

export function useVoice({ userId, conversationId, onAssistantMessage, onUserTranscript }: UseVoiceOptions): VoiceController {
  const [state, setState] = useState<VoiceState>('idle');
  const [transcript, setTranscript] = useState('');
  const [isFinal, setIsFinal] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeRef = useRef(false);
  const wsRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const audioElRef = useRef<HTMLAudioElement | null>(null);

  // Keep the latest callbacks without re-creating handlers.
  const onAssistantRef = useRef(onAssistantMessage);
  const onTranscriptRef = useRef(onUserTranscript);
  useEffect(() => {
    onAssistantRef.current = onAssistantMessage;
    onTranscriptRef.current = onUserTranscript;
  });

  const isSupported =
    typeof window !== 'undefined' &&
    typeof window.WebSocket !== 'undefined' &&
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === 'function';

  const teardownAudio = useCallback(() => {
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current.onaudioprocess = null;
      processorRef.current = null;
    }
    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (audioCtxRef.current) {
      void audioCtxRef.current.close().catch(() => undefined);
      audioCtxRef.current = null;
    }
  }, []);

  const closeSocket = useCallback(() => {
    const ws = wsRef.current;
    wsRef.current = null;
    if (ws) {
      ws.onopen = null;
      ws.onmessage = null;
      ws.onerror = null;
      ws.onclose = null;
      try {
        ws.close();
      } catch {
        // already closing/closed
      }
    }
  }, []);

  const reset = useCallback(() => {
    activeRef.current = false;
    teardownAudio();
    closeSocket();
  }, [teardownAudio, closeSocket]);

  const playAudio = useCallback((data: Blob | ArrayBuffer) => {
    const blob = data instanceof Blob ? data : new Blob([data], { type: 'audio/mp3' });
    const url = URL.createObjectURL(blob);
    const audio = audioElRef.current ?? new Audio();
    audioElRef.current = audio;
    audio.src = url;
    setState('speaking');
    void audio.play().catch(() => undefined);
    audio.onended = () => {
      URL.revokeObjectURL(url);
      audioElRef.current = null;
      setState((prev) => (prev === 'speaking' ? 'idle' : prev));
    };
  }, []);

  const handleServerMessage = useCallback(
    (raw: string) => {
      const msg = parseServerMessage(raw);
      if (!msg) return;
      switch (msg.type) {
        case 'state':
          setState(msg.state);
          if (msg.state === 'idle') {
            reset();
          }
          break;
        case 'transcript':
          setTranscript(msg.text);
          setIsFinal(msg.final);
          if (msg.final && msg.text.trim()) {
            onTranscriptRef.current(msg.text);
          }
          break;
        case 'message':
          onAssistantRef.current(msg.message);
          break;
        case 'error':
          setError(msg.detail);
          setState('error');
          break;
      }
    },
    [reset],
  );

  const start = useCallback(async () => {
    if (activeRef.current) return;
    if (!isSupported) {
      setError('Voice input is not supported in this browser.');
      setState('error');
      return;
    }

    setError(null);
    setTranscript('');
    setIsFinal(false);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: 16000,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      streamRef.current = stream;

      const Ctor: typeof AudioContext | undefined =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!Ctor) {
        throw new Error('AudioContext is not supported');
      }
      const audioCtx = new Ctor({ sampleRate: 16000 });
      audioCtxRef.current = audioCtx;

      const source = audioCtx.createMediaStreamSource(stream);
      const processor = audioCtx.createScriptProcessor(4096, 1, 1);
      sourceRef.current = source;
      processorRef.current = processor;

      const ws = new WebSocket(buildVoiceUrl(userId, conversationId));
      wsRef.current = ws;
      ws.binaryType = 'arraybuffer';

      processor.onaudioprocess = (event: AudioProcessingEvent) => {
        const currentWs = wsRef.current;
        if (currentWs && currentWs.readyState === WebSocket.OPEN) {
          const pcm = downsampleToPcm16(
            event.inputBuffer.getChannelData(0),
            event.inputBuffer.sampleRate,
            16000,
          );
          currentWs.send(pcm.buffer);
        }
      };

      source.connect(processor);
      processor.connect(audioCtx.destination);

      ws.onopen = () => {
        activeRef.current = true;
        ws.send(JSON.stringify({ type: 'start' }));
        setState('listening');
      };
      ws.onmessage = (event: MessageEvent) => {
        if (typeof event.data === 'string') {
          handleServerMessage(event.data);
        } else {
          playAudio(event.data as Blob | ArrayBuffer);
        }
      };
      ws.onerror = () => {
        setError('Voice connection failed. Please try again.');
        setState('error');
        reset();
      };
      ws.onclose = () => {
        if (activeRef.current) {
          reset();
          setState((prev) => (prev === 'error' ? prev : 'idle'));
        }
      };
    } catch (err) {
      const name = err instanceof DOMException ? err.name : '';
      const message =
        name === 'NotAllowedError'
          ? 'Microphone access was denied. Enable it in your browser settings to use voice.'
          : name === 'NotFoundError'
            ? 'No microphone was found.'
            : 'Could not access the microphone.';
      setError(message);
      setState('error');
      reset();
    }
  }, [userId, conversationId, isSupported, handleServerMessage, playAudio, reset]);

  const stop = useCallback(() => {
    if (!activeRef.current) return;
    activeRef.current = false;

    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      reset();
      setState('idle');
      return;
    }

    try {
      ws.send(JSON.stringify({ type: 'stop' }));
    } catch {
      // ignore — socket teardown will follow
    }

    // Stop capturing immediately; keep the socket open to receive the reply.
    teardownAudio();
    setState((prev) => (prev === 'error' ? prev : 'processing'));
  }, [teardownAudio, reset]);

  const toggle = useCallback(() => {
    if (activeRef.current) {
      stop();
    } else {
      void start();
    }
  }, [start, stop]);

  // Clean up on unmount.
  useEffect(() => {
    return () => {
      reset();
    };
  }, [reset]);

  const isActive = state === 'listening' || state === 'processing' || state === 'speaking';

  return {
    state,
    transcript,
    isFinal,
    error,
    isSupported,
    isActive,
    start,
    stop,
    toggle,
  };
}
