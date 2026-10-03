let csrfToken = '';
export function setCsrf(value: string) { csrfToken = value; }
export function apiUrl(path: string) { return `${import.meta.env.BASE_URL}api/${path.replace(/^\//, '')}`; }

export class ApiError extends Error {
  constructor(public status: number, message: string, public retryAfter = 0) { super(message); }
}

export async function api<T>(path: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(apiUrl(path), {
    method, credentials: 'same-origin', cache: 'no-store', signal,
    headers: { ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(method !== 'GET' ? { 'X-CSRF-Token': csrfToken } : {}) },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
  const data = await response.json();
  if (!response.ok) throw new ApiError(response.status, typeof data.detail === 'string' ? data.detail : '요청을 처리할 수 없습니다.', Number(response.headers.get('Retry-After')) || 0);
  return data as T;
}

export function todayKst() {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  return ['year', 'month', 'day'].map(kind => parts.find(part => part.type === kind)?.value).join('-');
}

export function httpUrl(value: string): string | null {
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : null; } catch { return null; }
}
