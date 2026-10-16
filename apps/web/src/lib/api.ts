/**
 * Typed fetch wrapper for /v1/*.
 *
 * - credentials: "include" so the session cookie goes along; the SPA runs behind the same
 *   origin as the API (nginx proxy), so the browser attaches it without extra config.
 * - On every mutating request we read the `csrf` cookie and echo it in `X-CSRF-Token`.
 * - 401 bubbles as `ApiError("unauthorized")`; the AuthGuard reacts to it.
 */

const JSON_HEADERS = { "Content-Type": "application/json", Accept: "application/json" };

export type ApiErrorBody = {
  error?: { code?: string; message?: string };
  trace_id?: string;
};

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
    public body: ApiErrorBody | null,
    public retryAfterSeconds?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function readCsrfCookie(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]!) : null;
}

async function parseError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody | null = null;
  try {
    body = (await response.json()) as ApiErrorBody;
  } catch {
    body = null;
  }
  const code = body?.error?.code ?? `http_${response.status}`;
  const message = body?.error?.message ?? response.statusText;
  const retryHeader = response.headers.get("Retry-After");
  const retryAfterSeconds = retryHeader ? Number(retryHeader) : undefined;
  return new ApiError(code, message, response.status, body, retryAfterSeconds);
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  init?: RequestInit,
): Promise<T> {
  const headers = new Headers(init?.headers);
  if (body !== undefined) {
    for (const [key, value] of Object.entries(JSON_HEADERS)) {
      headers.set(key, value);
    }
  } else {
    headers.set("Accept", "application/json");
  }
  if (method !== "GET" && method !== "HEAD") {
    const token = readCsrfCookie();
    if (token !== null) {
      headers.set("X-CSRF-Token", token);
    }
  }
  const response = await fetch(path, {
    method,
    credentials: "include",
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    ...init,
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  if (response.status === 204 || response.status === 205) {
    return undefined as T;
  }
  const contentType = response.headers.get("Content-Type") ?? "";
  if (contentType.startsWith("application/json")) {
    return (await response.json()) as T;
  }
  return (await response.text()) as unknown as T;
}

export const api = {
  get<T>(path: string, init?: RequestInit) {
    return request<T>("GET", path, undefined, init);
  },
  post<T>(path: string, body?: unknown, init?: RequestInit) {
    return request<T>("POST", path, body, init);
  },
  put<T>(path: string, body?: unknown, init?: RequestInit) {
    return request<T>("PUT", path, body, init);
  },
  patch<T>(path: string, body?: unknown, init?: RequestInit) {
    return request<T>("PATCH", path, body, init);
  },
  delete<T>(path: string, body?: unknown, init?: RequestInit) {
    return request<T>("DELETE", path, body, init);
  },
};

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}
