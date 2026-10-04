import { describe, expect, it, vi } from 'vitest';
import { api, apiUrl, todayKst, httpUrl, openExternalWindow } from '../src/api';

describe('subpath and message links', () => {
  it('keeps APIs inside the configured Vite base path', () => { vi.stubEnv('BASE_URL', '/stock15-7/'); expect(apiUrl('messages?date=2026-10-03')).toBe('/stock15-7/api/messages?date=2026-10-03'); vi.unstubAllEnvs(); });
  it('rejects executable and unexpected link schemes', () => { expect(httpUrl('javascript:alert(1)')).toBe(null); expect(httpUrl('data:text/html,a')).toBe(null); expect(httpUrl('https://telegram.org')).toBe('https://telegram.org/'); });
  it('requests a separate popup window for links', () => { const popup = { opener: true }; const open = vi.fn(() => popup); vi.stubGlobal('window', { open }); openExternalWindow('https://telegram.org/'); expect(open).toHaveBeenCalledWith('https://telegram.org/', '_blank', 'popup=yes,width=1100,height=800,noopener,noreferrer'); expect(popup.opener).toBe(null); vi.unstubAllGlobals(); });
  it('uses KST at UTC midnight boundaries', () => { vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-02T15:01:00Z')); expect(todayKst()).toBe('2026-10-03'); vi.useRealTimers(); });
  it('turns browser connection errors into a useful message', async () => { vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))); await expect(api('settings')).rejects.toMatchObject({ status: 0, message: '서버와 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.' }); vi.unstubAllGlobals(); });
});
