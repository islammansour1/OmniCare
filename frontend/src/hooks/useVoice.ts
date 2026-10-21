import { useCallback, useEffect, useRef, useState } from 'react';
import { Room, RoomEvent, Track, type RemoteTrack } from 'livekit-client';
import { getVoiceToken } from '../lib/api';

/**
 * LiveKit real-time voice state. The agent worker (backend) performs STT and
 * turn-taking; the browser only streams its mic and plays the agent's audio.
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

export interface UseVoiceOptions {
  userId: string;
  /** Active conversation, so spoken and typed turns share one thread. */
  conversationId: string;
  /** Fired when the agent finishes a spoken turn (used to refresh the chat). */
  onTurnComplete: () => void;
}

/** Key LiveKit Agents uses to publish the agent's state as participant attributes. */
const AGENT_STATE_KEY = 'lk.agent.state';

function agentStateToVoiceState(agentState: string): VoiceState {
  switch (agentState) {
    case 'listening':
      return 'listening';
    case 'thinking':
      return 'processing';
    case 'speaking':
      return 'speaking';
    default:
      return 'listening';
  }
}

export function useVoice({ userId, conversationId, onTurnComplete }: UseVoiceOptions): VoiceController {
  const [state, setState] = useState<VoiceState>('idle');
  const [error, setError] = useState<string | null>(null);
  const roomRef = useRef<Room | null>(null);
  const activeRef = useRef(false);
  const audioEls = useRef<HTMLMediaElement[]>([]);

  // Keep the latest values without re-creating the room event handlers.
  const conversationIdRef = useRef(conversationId);
  const onTurnCompleteRef = useRef(onTurnComplete);
  const lastAgentStateRef = useRef<string | null>(null);
  useEffect(() => {
    conversationIdRef.current = conversationId;
    onTurnCompleteRef.current = onTurnComplete;
  });

  const isSupported =
    typeof window !== 'undefined' &&
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices &&
    typeof navigator.mediaDevices.getUserMedia === 'function';

  const cleanupAudio = useCallback(() => {
    audioEls.current.forEach((el) => {
      el.srcObject = null;
      el.remove();
    });
    audioEls.current = [];
  }, []);

  const disconnect = useCallback(() => {
    const room = roomRef.current;
    roomRef.current = null;
    activeRef.current = false;
    if (room) {
      try {
        void room.disconnect();
      } catch {
        // already disconnected
      }
    }
    cleanupAudio();
  }, [cleanupAudio]);

  const start = useCallback(async () => {
    if (activeRef.current) return;
    if (!isSupported) {
      setError('Voice input is not supported in this browser.');
      setState('error');
      return;
    }

    setError(null);
    lastAgentStateRef.current = null;

    try {
      const { url, token } = await getVoiceToken(userId, conversationIdRef.current);

      const room = new Room({ adaptiveStream: true, dynacast: true });
      roomRef.current = room;

      room
        .on(RoomEvent.Connected, () => {
          activeRef.current = true;
          setState('listening');
          // Publish the microphone.
          void room.localParticipant.setMicrophoneEnabled(true).catch(() => undefined);
        })
        .on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
          if (track.kind === Track.Kind.Audio) {
            const el = track.attach();
            el.autoplay = true;
            document.body.appendChild(el);
            audioEls.current.push(el);
          }
        })
        .on(RoomEvent.ParticipantAttributesChanged, (attributes: Record<string, string>) => {
          const agentState = attributes[AGENT_STATE_KEY];
          if (!agentState) return;
          const previous = lastAgentStateRef.current;
          lastAgentStateRef.current = agentState;
          setState(agentStateToVoiceState(agentState));
          // A turn ended when the agent stops speaking/thinking and returns to
          // listening — refresh the chat so spoken turns appear in the thread.
          if (
            (previous === 'speaking' || previous === 'thinking') &&
            (agentState === 'listening' || agentState === 'idle')
          ) {
            onTurnCompleteRef.current();
          }
        })
        .on(RoomEvent.Disconnected, () => {
          cleanupAudio();
          activeRef.current = false;
          setState((prev) => (prev === 'error' ? prev : 'idle'));
        });

      await room.connect(url, token);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Voice connection failed.');
      setState('error');
      disconnect();
    }
  }, [userId, isSupported, disconnect, cleanupAudio]);

  const stop = useCallback(() => {
    disconnect();
    setState('idle');
  }, [disconnect]);

  const toggle = useCallback(() => {
    if (activeRef.current) stop();
    else void start();
  }, [start, stop]);

  // Clean up on unmount.
  useEffect(() => () => disconnect(), [disconnect]);

  const isActive = state === 'listening' || state === 'processing' || state === 'speaking';

  return {
    state,
    transcript: '',
    isFinal: false,
    error,
    isSupported,
    isActive,
    start,
    stop,
    toggle,
  };
}
