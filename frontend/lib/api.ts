"use client";

/**
 * Browser API client. Requests go to /api/v1 on the frontend origin (proxied to FastAPI),
 * so httpOnly auth cookies are first-party. A 401 triggers one silent refresh + retry.
 */

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
  }
}

type Options = Omit<RequestInit, "body"> & { json?: unknown; body?: BodyInit; retry?: boolean };

const NO_REFRESH = ["/auth/refresh", "/auth/login", "/auth/signup", "/auth/logout"];
let refreshing: Promise<boolean> | null = null;

export function refreshSession(): Promise<boolean> {
  refreshing ??= fetch("/api/v1/auth/refresh", { method: "POST", credentials: "include" })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => setTimeout(() => (refreshing = null), 0));
  return refreshing;
}

async function parseError(res: Response): Promise<ApiError> {
  let detail = res.statusText || "Request failed";
  try {
    const body = await res.json();
    if (typeof body.detail === "string") detail = body.detail;
    else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join(", ");
  } catch {
    /* non-JSON error */
  }
  return new ApiError(res.status, detail);
}

export async function api<T = unknown>(path: string, opts: Options = {}): Promise<T> {
  const { json, retry = true, headers, ...init } = opts;
  const res = await fetch(`/api/v1${path}`, {
    credentials: "include",
    ...init,
    headers: { ...(json !== undefined ? { "Content-Type": "application/json" } : {}), ...headers },
    body: json !== undefined ? JSON.stringify(json) : init.body,
  });

  if (res.status === 401 && retry && !NO_REFRESH.some((p) => path.startsWith(p))) {
    if (await refreshSession()) return api<T>(path, { ...opts, retry: false });
  }
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Fire-and-forget POST that survives page unload (used for final playback heartbeat). */
export function beacon(path: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data)], { type: "application/json" });
  if (!navigator.sendBeacon?.(`/api/v1${path}`, blob)) {
    void fetch(`/api/v1${path}`, { method: "POST", body: blob, credentials: "include", keepalive: true });
  }
}
