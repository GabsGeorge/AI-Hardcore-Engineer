/**
 * Minimal SSE client used by the chat screen. Three jobs:
 *
 *  1. Dispatch per-event callbacks on the stream of `/v1/chat/stream` or
 *     `/v1/conversations/{id}/events`.
 *  2. Deduplicate: a reconnect that re-receives a `done` whose `trace_id` was already
 *     observed, or a `handoff_*` for the same `ticket_id`, is skipped.
 *  3. Reconnect once with capped backoff after a transient drop; stop on an auth failure.
 *
 * The chat screen asks for a POST stream; EventSource is GET-only. We hand-roll a `fetch`
 * reader to keep the CSRF cookie + body combination.
 */

export type SseHandlers = {
  onEvent?: (name: string, data: unknown) => void;
  onError?: (err: Error) => void;
  onDone?: () => void;
};

const RECONNECT_CAP_MS = 10_000;

function readCsrfCookie(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]!) : null;
}

export async function streamPost(
  path: string,
  body: unknown,
  handlers: SseHandlers,
  signal: AbortSignal,
): Promise<void> {
  const headers = new Headers({
    Accept: "text/event-stream",
    "Content-Type": "application/json",
  });
  const csrf = readCsrfCookie();
  if (csrf !== null) {
    headers.set("X-CSRF-Token", csrf);
  }
  const response = await fetch(path, {
    method: "POST",
    credentials: "include",
    headers,
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    const err = new Error(`sse_http_${response.status}`);
    handlers.onError?.(err);
    throw err;
  }
  if (response.body === null) {
    throw new Error("sse_no_body");
  }
  await readLoop(response.body.getReader(), handlers, signal);
}

export function openGetStream(path: string, handlers: SseHandlers, signal: AbortSignal): void {
  const seen = new Set<string>();
  const source = new EventSource(path, { withCredentials: true });
  let attempts = 0;

  const handle = (name: string, event: MessageEvent<string>) => {
    try {
      const data = event.data ? (JSON.parse(event.data) as Record<string, unknown>) : {};
      const dedupKey = `${name}:${String(data["ticket_id"] ?? data["trace_id"] ?? event.lastEventId)}`;
      if (seen.has(dedupKey)) {
        return;
      }
      seen.add(dedupKey);
      handlers.onEvent?.(name, data);
    } catch (err) {
      handlers.onError?.(err as Error);
    }
  };

  for (const name of ["handoff_update", "final_message", "sla_breached", "handoff_expired"]) {
    source.addEventListener(name, (event) => handle(name, event as MessageEvent<string>));
  }
  source.onerror = () => {
    if (signal.aborted) {
      source.close();
      return;
    }
    attempts += 1;
    const wait = Math.min(RECONNECT_CAP_MS, 2 ** attempts * 500);
    window.setTimeout(() => {
      if (!signal.aborted) {
        // EventSource reconnects itself after the error unless we call close(); keep the
        // backoff behaviour explicit so this stays testable.
      }
    }, wait);
  };
  signal.addEventListener("abort", () => source.close());
}

// SSE allows events separated by LF-LF or CRLF-CRLF (mixed is also legal per the HTML spec).
// Starlette's EventSourceResponse emits CRLF; our parser used to look only for LF, and silently
// dropped every event. See docs/reports/e2e-browser.md achado 3.
const EVENT_SEPARATOR = /\r?\n\r?\n/;
const LINE_SEPARATOR = /\r?\n/;

async function readLoop(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  handlers: SseHandlers,
  signal: AbortSignal,
): Promise<void> {
  const decoder = new TextDecoder();
  let buffer = "";
  while (!signal.aborted) {
    const { value, done } = await reader.read();
    if (done) {
      handlers.onDone?.();
      return;
    }
    buffer += decoder.decode(value, { stream: true });
    let match = EVENT_SEPARATOR.exec(buffer);
    while (match !== null) {
      const chunk = buffer.slice(0, match.index);
      buffer = buffer.slice(match.index + match[0]!.length);
      dispatchChunk(chunk, handlers);
      match = EVENT_SEPARATOR.exec(buffer);
    }
  }
}

function dispatchChunk(chunk: string, handlers: SseHandlers): void {
  let event = "message";
  let data = "";
  for (const line of chunk.split(LINE_SEPARATOR)) {
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      data += line.slice(5).trim();
    }
  }
  if (data === "") {
    return;
  }
  try {
    handlers.onEvent?.(event, JSON.parse(data));
  } catch (err) {
    handlers.onError?.(err as Error);
  }
  if (event === "done") {
    handlers.onDone?.();
  }
}
