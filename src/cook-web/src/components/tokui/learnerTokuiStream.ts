import { SSE } from 'sse.js';
import { getResolvedBaseURL } from '@/c-utils/envUtils';
import { attachSseBusinessResponseFallback } from '@/lib/request';
import { buildTraceHeaders } from '@/lib/request-trace';
import { useUserStore } from '@/store/useUserStore';

export type LearnerTokuiStreamEvent =
  | { type: 'start' }
  | { type: 'chunk'; tokui?: string }
  | { type: 'status'; status?: string }
  | { type: 'reset' }
  | { type: 'final'; artifact?: unknown }
  | { type: 'error'; message?: string };

type StreamLearnerTokuiParams = {
  shifuBid: string;
  outlineBid: string;
  forceRegenerate?: boolean;
  onEvent: (event: LearnerTokuiStreamEvent) => void;
  onError?: (error: unknown) => void;
  onDone?: () => void;
};

export type LearnerTokuiStreamHandle = {
  close: () => void;
};

const dispatchSseBusinessError = (
  source: { dispatchEvent: (event: Event) => void },
  error: { message: string; code?: number },
) => {
  source.dispatchEvent(
    new MessageEvent('error', {
      data: JSON.stringify({
        type: 'error',
        message: error.message,
        code: error.code,
      }),
    }),
  );
};

export const streamLearnerTokui = ({
  shifuBid,
  outlineBid,
  forceRegenerate = false,
  onEvent,
  onError,
  onDone,
}: StreamLearnerTokuiParams): LearnerTokuiStreamHandle => {
  const token = useUserStore.getState().getToken();
  const baseURL = getResolvedBaseURL();
  const url = `${baseURL}/api/learn/shifu/${shifuBid}/outlines/${outlineBid}/tokui/stream`;
  const traceHeaders = buildTraceHeaders({
    'Content-Type': 'application/json',
    ...(token
      ? {
          Authorization: `Bearer ${token}`,
          Token: token,
        }
      : {}),
  });
  const source = new SSE(url, {
    headers: traceHeaders.headers,
    payload: JSON.stringify({ force_regenerate: forceRegenerate }),
    method: 'POST',
  });

  source.addEventListener('message', event => {
    const data = (event as MessageEvent).data;
    if (data === '[DONE]') {
      source.close();
      onDone?.();
      return;
    }
    try {
      onEvent(JSON.parse(data) as LearnerTokuiStreamEvent);
    } catch {
      // Ignore malformed partial frames; valid TokUI chunks are JSON-wrapped.
    }
  });

  source.addEventListener('error', error => {
    onError?.(error);
  });

  attachSseBusinessResponseFallback(source, {
    requestToken: token || '',
    meta: {
      url,
      method: 'POST',
      requestToken: token || '',
      requestId: traceHeaders.requestId,
      harnessRunId: traceHeaders.harnessRunId,
    },
    onHandled: error => {
      dispatchSseBusinessError(source, error);
    },
  });

  source.stream();
  return {
    close: () => source.close(),
  };
};
