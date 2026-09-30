// Thin fetch wrapper for billing-service. The dashboard token lives in sessionStorage (cleared with the tab).

const BASE = ((import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8001').replace(/\/$/, '');
const TOKEN_KEY = 'dashboardToken';

export class ApiError extends Error {
  readonly status: number;
  /** True for finance-only endpoints: a 401 there means "your token is fine but not a finance token". */
  readonly financeOnly: boolean;
  constructor(status: number, message: string, financeOnly = false) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.financeOnly = financeOnly;
  }
}

export const tokenStore = {
  get(): string { try { return sessionStorage.getItem(TOKEN_KEY) ?? ''; } catch { return ''; } },
  set(value: string): void { try { sessionStorage.setItem(TOKEN_KEY, value); } catch { /* storage unavailable */ } },
  clear(): void { try { sessionStorage.removeItem(TOKEN_KEY); } catch { /* storage unavailable */ } },
};

const authListeners = new Set<() => void>();
/** Called when the server rejects the token (401 on a non-finance-only endpoint). Returns an unsubscribe fn. */
export function onAuthFailure(listener: () => void): () => void {
  authListeners.add(listener);
  return () => { authListeners.delete(listener); };
}

type Params = Record<string, string | number | undefined>;
export interface RequestOptions { method?: 'GET' | 'POST' | 'DELETE'; params?: Params; signal?: AbortSignal; financeOnly?: boolean }

function describe(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return 'The request was not valid.';
  }
  return fallback;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(options.params ?? {})) if (value !== undefined) query.set(key, String(value));
  const qs = query.toString();
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}${qs ? `?${qs}` : ''}`, {
      method: options.method ?? 'GET',
      headers: { 'X-Dashboard-Token': tokenStore.get() },
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError(0, 'Cannot reach the billing service. Check that it is running.');
  }
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    if (response.status === 401 && !options.financeOnly) authListeners.forEach((listener) => listener());
    throw new ApiError(response.status, describe(body, `Request failed (${response.status})`), Boolean(options.financeOnly));
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string, params?: Params, options: Omit<RequestOptions, 'method' | 'params'> = {}) => request<T>(path, { ...options, params }),
  post: <T>(path: string, params?: Params) => request<T>(path, { method: 'POST', params }),
  del: (path: string, params?: Params) => request<void>(path, { method: 'DELETE', params }),
};
