let csrfToken = '';
export function setCsrf(value: string) { csrfToken = value; }
export function apiUrl(path: string) { return `${import.meta.env.BASE_URL}api/${path.replace(/^\//, '')}`; }

export class ApiError extends Error {
  constructor(public status: number, message: string, public retryAfter = 0) { super(message); }
}

export async function api<T>(path: string, method = 'GET', body?: unknown, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      method, credentials: 'same-origin', cache: 'no-store', signal,
      headers: { ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(method !== 'GET' ? { 'X-CSRF-Token': csrfToken } : {}) },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
    throw new ApiError(0, '서버와 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.');
  }
  let data: unknown;
  try { data = await response.json(); }
  catch { throw new ApiError(response.status, '서버 응답을 읽을 수 없습니다. 잠시 후 다시 시도해 주세요.'); }
  const detail = typeof data === 'object' && data !== null && 'detail' in data && typeof data.detail === 'string' ? data.detail : '요청을 처리할 수 없습니다.';
  if (!response.ok) throw new ApiError(response.status, detail, Number(response.headers.get('Retry-After')) || 0);
  return data as T;
}

export function todayKst() {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  return ['year', 'month', 'day'].map(kind => parts.find(part => part.type === kind)?.value).join('-');
}

export function httpUrl(value: string): string | null {
  try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : null; } catch { return null; }
}

export function openExternalWindow(url: string) {
  const popup = window.open(url, '_blank', 'popup=yes,width=1100,height=800,noopener,noreferrer');
  if (popup) popup.opener = null;
}
