import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent, MouseEvent as ReactMouseEvent, ReactNode } from 'react';
import { CalendarDays, Check, ChevronLeft, ChevronRight, CircleHelp, Download, Hash, LayoutGrid, List, LoaderCircle, LockKeyhole, LogOut, MessageCircle, Radio, RefreshCw, Search, Send, Settings2, ShieldCheck, Trash2, Users, X } from 'lucide-react';
import { api, apiUrl, ApiError, httpUrl, openExternalWindow, setCsrf, todayKst } from './api';
import type { Chat, Hidden, Message, Page, Settings, Status } from './types';
import TelemoaPanel from './TelemoaPanel';

const typeLabel = { channel: '채널', group: '그룹', private: '개인대화' };
const timeLabel = (date: string) => new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(date));
const dateLabel = (date: string) => new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', month: 'long', day: 'numeric', weekday: 'long' }).format(new Date(`${date}T12:00:00+09:00`));
const keyOf = (m: Message) => `${m.chatId}:${m.messageId}`;

function Modal({ title, close, children, wide = false, error = '' }: { title: string; close: () => void; children: ReactNode; wide?: boolean; error?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    ref.current?.querySelector<HTMLElement>('button, input')?.focus();
    const handle = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close();
      if (event.key === 'Tab') {
        const elements = Array.from(ref.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input, select, a[href], [tabindex="0"]') ?? []);
        const first = elements[0], last = elements.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    document.addEventListener('keydown', handle);
    return () => { document.removeEventListener('keydown', handle); previous?.focus(); };
  }, [close]);
  return <div className="overlay"><div ref={ref} role="dialog" aria-modal="true" aria-label={title} className={`modal ${wide ? 'wide' : ''}`}><div className="modal-head"><h2>{title}</h2><button className="icon-button" onClick={close} aria-label="닫기"><X size={20} /></button></div>{error && <div className="alert error" role="alert">{error}</div>}{children}</div></div>;
}

function openInWindow(event: ReactMouseEvent<HTMLAnchorElement>) {
  event.preventDefault();
  openExternalWindow(event.currentTarget.href);
}

function MessageText({ text, links }: { text: string; links: string[] }) {
  const inlineLinks = text.match(/https?:\/\/[^\s<>]+/g) || [];
  const previewLink = [...inlineLinks, ...links].map(httpUrl).find((link): link is string => Boolean(link));
  return <><div className="message-text">{text.split(/(https?:\/\/[^\s<>]+)/g).map((part, i) => {
    const url = httpUrl(part);
    return url ? <a key={i} href={url} onClick={openInWindow}>{part}</a> : part;
  })}{links.filter(link => !text.includes(link) && httpUrl(link)).map(link => <span key={link}><br /><a href={httpUrl(link)!} onClick={openInWindow}>{link}</a></span>)}</div>{previewLink && <LinkPreview url={previewLink} />}</>;
}

type Preview = { url: string; title: string | null; description: string | null; image: string | null };

function youtubeId(url: string) {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.replace(/^www\./, '');
    const parts = parsed.pathname.split('/').filter(Boolean);
    const value = host === 'youtu.be' ? parts[0] : host.endsWith('youtube.com') ? parsed.searchParams.get('v') || (['shorts', 'embed', 'live'].includes(parts[0]) ? parts[1] : null) : null;
    return value && /^[A-Za-z0-9_-]{11}$/.test(value) ? value : null;
  } catch { return null; }
}

function LinkPreview({ url }: { url: string }) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const videoId = youtubeId(url);
  useEffect(() => {
    const controller = new AbortController();
    api<Preview | Record<string, never>>(`link-preview?url=${encodeURIComponent(url)}`, 'GET', undefined, controller.signal).then(data => {
      if ('url' in data && typeof data.url === 'string') setPreview(data as Preview);
    }).catch(() => {});
    return () => controller.abort();
  }, [url]);
  if (!preview && !videoId) return null;
  return <div className="link-preview">{videoId ? <iframe title={preview?.title || 'YouTube 미리보기'} src={`https://www.youtube-nocookie.com/embed/${videoId}?rel=0`} loading="lazy" referrerPolicy="no-referrer" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowFullScreen /> : preview?.image && <img src={preview.image} alt="" loading="lazy" referrerPolicy="no-referrer" />}<a href={url} onClick={openInWindow} className="link-preview-copy"><strong>{preview?.title || new URL(url).hostname}</strong>{preview?.description && <span>{preview.description}</span>}<small>{new URL(url).hostname}</small></a></div>;
}

export default function App({ demo }: { demo: boolean }) {
  const [ready, setReady] = useState(false), [logged, setLogged] = useState(false), [theme, setTheme] = useState<'light' | 'dark'>('light');
  const [password, setPassword] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [settings, setSettings] = useState<Settings | null>(null), [status, setStatus] = useState<Status | null>(null), [chats, setChats] = useState<Chat[]>([]);
  const [day, setDay] = useState(todayKst()), [view, setView] = useState<'feed' | 'chat'>('feed'), [filters, setFilters] = useState<string[] | null>(null);
  const [messages, setMessages] = useState<Message[]>([]), [cursor, setCursor] = useState<string | null>(null), [loading, setLoading] = useState(false), [lastUpdated, setLastUpdated] = useState('');
  const [loadedDay, setLoadedDay] = useState(''), [hiddenKeys, setHiddenKeys] = useState(new Set<string>()), [refreshRevision, setRefreshRevision] = useState(0);
  const [modal, setModal] = useState<'chats' | 'settings' | 'delete' | null>(null);
  const [draftIds, setDraftIds] = useState<string[]>([]), [search, setSearch] = useState(''), [kind, setKind] = useState('public');
  const [draftStart, setDraftStart] = useState(''), [hidden, setHidden] = useState<Hidden[]>([]), [hiddenTotal, setHiddenTotal] = useState(0), [showHidden, setShowHidden] = useState(false);
  const [retryUntil, setRetryUntil] = useState(0), [notice, setNotice] = useState('');
  const requestRef = useRef<AbortController | null>(null);
  const currentDayRef = useRef(day);
  currentDayRef.current = day;
  const settingsRef = useRef<Settings | null>(null);
  const hiddenRef = useRef(new Set<string>()), pendingHides = useRef(new Set<string>());
  const cooldownRef = useRef(0);
  const today = settings?.today || todayKst();
  const selected = settings?.selectedChatIds || [];
  const selectedChats = chats.filter(c => selected.includes(c.chatId));
  const activeIds = selected.filter(id => filters === null || filters.includes(id));
  const selectionKey = JSON.stringify(selected), filterKey = JSON.stringify(activeIds);
  const fingerprint = settings ? JSON.stringify([settings.historyStartDate, selected]) : '';

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    return () => { delete document.documentElement.dataset.theme; };
  }, [theme]);

  const fail = useCallback((cause: unknown) => {
    if (cause instanceof DOMException && cause.name === 'AbortError') return;
    if (cause instanceof ApiError && cause.status === 401) { setLogged(false); setMessages([]); setSettings(null); settingsRef.current = null; setCsrf(''); setError('로그인 시간이 만료되었습니다. 비밀번호를 다시 입력해 주세요.'); return; }
    if (cause instanceof ApiError && cause.retryAfter) { cooldownRef.current = Date.now() + cause.retryAfter * 1000; setRetryUntil(cooldownRef.current); }
    if (cause instanceof ApiError && cause.status === 403 && cause.message === '인증 토큰을 확인해 주세요.') { setError('로그인 보안 확인에 실패했습니다. 페이지를 새로고침한 뒤 다시 시도해 주세요.'); return; }
    setError(cause instanceof Error ? cause.message : '요청 중 오류가 발생했습니다.');
  }, []);

  useEffect(() => { api<{ csrfToken: string }>('auth/session').then(data => { setCsrf(data.csrfToken); setLogged(true); }).catch(() => {}).finally(() => setReady(true)); }, []);
  useEffect(() => {
    if (!retryUntil) return;
    const timer = window.setTimeout(() => { cooldownRef.current = 0; setRetryUntil(0); }, Math.min(2147483647, Math.max(1, retryUntil - Date.now())));
    return () => clearTimeout(timer);
  }, [retryUntil]);

  const acceptSettings = useCallback((next: Settings, ownHide = false) => {
    const previous = settingsRef.current;
    // A slower metadata request must not overwrite a newer hide acknowledgement.
    if (previous?.revision && next.revision && Number(next.revision) < Number(previous.revision)) return;
    const changed = previous && (previous.historyStartDate !== next.historyStartDate || previous.hiddenCount !== next.hiddenCount || JSON.stringify(previous.selectedChatIds) !== JSON.stringify(next.selectedChatIds));
    const onlyOwnHide = ownHide && previous && next.revision !== undefined && Number(next.revision) === Number(previous.revision) + 1;
    if (changed && !onlyOwnHide) {
      hiddenRef.current = new Set(pendingHides.current);
      setHiddenKeys(new Set(hiddenRef.current));
      setRefreshRevision(value => value + 1);
    }
    settingsRef.current = next;
    setTheme(next.theme);
    setSettings(previousState => JSON.stringify(previousState) === JSON.stringify(next) ? previousState : next);
  }, []);

  const metadata = useCallback(async (quiet = false) => {
    try { acceptSettings(await api<Settings>('settings')); }
    catch (cause) { if (!quiet || cause instanceof ApiError && cause.status === 401) fail(cause); }
  }, [acceptSettings, fail]);

  useEffect(() => {
    if (!logged) return;
    void metadata();
    api<Status>('status').then(setStatus).catch(fail);
    api<Chat[]>('chats').then(setChats).catch(fail);
    const focus = () => { void metadata(true); };
    window.addEventListener('focus', focus);
    return () => { window.removeEventListener('focus', focus); requestRef.current?.abort(); };
  }, [logged, metadata, fail]);

  const load = useCallback(async (nextCursor?: string) => {
    if (!logged || !settings || Date.now() < cooldownRef.current) return;
    requestRef.current?.abort();
    if (!activeIds.length) { setMessages([]); setCursor(null); setLoading(false); return; }
    const controller = new AbortController(); requestRef.current = controller;
    setLoading(true); setError('');
    if (!nextCursor) setCursor(null);
    const query = new URLSearchParams({ date: day, order: 'desc' });
    activeIds.forEach(id => query.append('chat_id', id));
    if (nextCursor) query.set('cursor', nextCursor);
    try {
      const page = await api<Page>(`messages?${query}`, 'GET', undefined, controller.signal);
      if (controller.signal.aborted) return;
      const items = page.messages.filter(m => !hiddenRef.current.has(keyOf(m)));
      setMessages(previous => nextCursor ? [...new Map([...previous, ...items].map(m => [keyOf(m), m])).values()] : items);
      setLoadedDay(day);
      setCursor(page.nextCursor); setLastUpdated(new Date().toISOString());
      setNotice(page.unavailableChatIds.length ? '일부 대화방에 접근할 수 없습니다. 대화방 선택을 확인해 주세요.' : '');
    } catch (cause) { if (!controller.signal.aborted) fail(cause); }
    finally { if (!controller.signal.aborted) setLoading(false); }
  }, [logged, fingerprint, day, filterKey, refreshRevision, fail]);

  useEffect(() => {
    if (settings && day < settings.historyStartDate) { setDay(settings.historyStartDate); return; }
    void load();
    return () => requestRef.current?.abort();
  }, [load]);

  useEffect(() => {
    setFilters(previous => previous === null ? null : previous.filter(id => selected.includes(id)));
  }, [selectionKey]);

  useEffect(() => {
    if (!logged) {
      hiddenRef.current.clear(); pendingHides.current.clear();
      setHiddenKeys(new Set()); setFilters(null); settingsRef.current = null;
    }
  }, [logged]);

  const login = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError('');
    const entered = password; setPassword('');
    try { const data = await api<{ csrfToken: string }>('auth/login', 'POST', { password: entered }); setCsrf(data.csrfToken); setLogged(true); }
    catch (cause) { fail(cause); } finally { setBusy(false); }
  };
  const logout = async () => {
    try { await api('auth/logout', 'POST'); setLogged(false); setMessages([]); setSettings(null); setStatus(null); setCsrf(''); } catch (cause) { fail(cause); }
  };
  const closeModal = useCallback(() => setModal(null), []);
  const openChats = async () => {
    setDraftIds([...selected]); setSearch(''); setKind('public'); setModal('chats'); setBusy(true);
    try { setChats(await api<Chat[]>('chats')); } catch (cause) { fail(cause); } finally { setBusy(false); }
  };
  const saveChats = async () => {
    setBusy(true);
    try { acceptSettings(await api<Settings>('settings/chats', 'PUT', { chatIds: draftIds })); setModal(null); } catch (cause) { fail(cause); } finally { setBusy(false); }
  };
  const hide = async (m: Message) => {
    const key = keyOf(m);
    const hideDay = day;
    if (pendingHides.current.has(key)) return;
    pendingHides.current.add(key); hiddenRef.current.add(key);
    setHiddenKeys(new Set(hiddenRef.current));
    try {
      const next = await api<Settings>('messages/hide', 'POST', { chatId: m.chatId, messageId: m.messageId });
      setMessages(previous => previous.filter(item => keyOf(item) !== key));
      acceptSettings(next, true);
    } catch (cause) {
      hiddenRef.current.delete(key); setHiddenKeys(new Set(hiddenRef.current));
      if (currentDayRef.current === hideDay) setMessages(previous => previous.some(item => keyOf(item) === key) ? previous : [...previous, m]);
      fail(cause);
    } finally { pendingHides.current.delete(key); }
  };
  const hiddenPage = async (offset = 0) => {
    try { const result = await api<{ items: Hidden[]; total: number }>(`messages/hidden?offset=${offset}`); setHidden(previous => offset ? [...previous, ...result.items] : result.items); setHiddenTotal(result.total); setShowHidden(true); } catch (cause) { fail(cause); }
  };
  const restore = async (h: Hidden) => {
    try { await api(`messages/hide/${h.chat_id}/${h.message_id}`, 'DELETE'); await hiddenPage(); void metadata(); } catch (cause) { fail(cause); }
  };
  const clearHidden = async () => {
    if (!window.confirm('숨김 기록을 모두 초기화할까요? 숨긴 메시지가 다시 표시됩니다.')) return;
    try { await api('messages/hide-all', 'DELETE'); await hiddenPage(); void metadata(); } catch (cause) { fail(cause); }
  };
  const saveStart = async () => {
    setBusy(true);
    try { acceptSettings(await api<Settings>('settings/start-date', 'PUT', { date: draftStart })); setNotice('조회 시작일을 저장했습니다. 모든 기기에 적용됩니다.'); } catch (cause) { fail(cause); } finally { setBusy(false); }
  };
  const saveTheme = async (nextTheme: 'light' | 'dark') => {
    const previousTheme = theme;
    setTheme(nextTheme);
    try {
      acceptSettings(await api<Settings>('settings/theme', 'PUT', { theme: nextTheme }));
      setNotice(`${nextTheme === 'dark' ? '어두운' : '밝은'} 화면 설정을 모든 기기에 저장했습니다.`);
    } catch (cause) {
      setTheme(previousTheme);
      fail(cause);
    }
  };
  const deleteRecords = async () => {
    setBusy(true);
    try { await api('settings/records', 'DELETE'); setModal(null); setMessages([]); setSettings(null); setStatus(null); setLogged(false); setCsrf(''); setNotice('웹앱 기록을 삭제했습니다. 다시 로그인해 주세요.'); } catch (cause) { fail(cause); } finally { setBusy(false); }
  };
  const moveDay = (amount: number) => { const d = new Date(`${day}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + amount); setDay(d.toISOString().slice(0, 10)); };
  const visibleChats = chats.filter(c => c.title.toLocaleLowerCase().includes(search.toLocaleLowerCase()) && (kind === 'all' || kind === 'public' && c.type !== 'private' || c.type === kind));
  const toggleChat = (id: string) => setFilters(previous => previous === null ? [id] : previous.includes(id) ? previous.filter(item => item !== id) : [...previous, id]);
  const visibleMessages = (loadedDay === day ? messages : []).filter(m => activeIds.includes(m.chatId) && !hiddenKeys.has(keyOf(m))).sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp) || b.messageId - a.messageId || a.chatId.localeCompare(b.chatId));
  const initialLoading = loading && loadedDay !== day;
  const grouped = new Map<string, Message[]>();
  visibleMessages.forEach(m => grouped.set(m.chatId, [...(grouped.get(m.chatId) || []), m]));
  const chatGroups = [...grouped].sort((a, b) => a[1][0].chatTitle.localeCompare(b[1][0].chatTitle, 'ko', { numeric: true }) || a[0].localeCompare(b[0]));
  const mediaUrl = (m: Message) => apiUrl(`media/${encodeURIComponent(m.chatId)}/${m.messageId}`);
  const card = (m: Message) => <article className="message-card" key={keyOf(m)} onDoubleClickCapture={() => void hide(m)}><div className="message-top"><span className={`avatar tone-${Math.abs(Number(m.chatId)) % 4}`}><Hash size={18} /></span><div className="message-origin"><strong>{m.chatTitle}</strong><span>{m.sender || '채널 메시지'}<i>·</i><time dateTime={m.timestamp}>{timeLabel(m.timestamp)}</time></span></div><button className="hide-button" aria-label={`${m.chatTitle} 메시지 숨기기`} title="이 웹앱에서 숨기기" onClick={() => void hide(m)}><X size={17} /></button></div>{m.attachment?.kind === 'photo' && <a className="attachment-photo" href={mediaUrl(m)} onClick={openInWindow}><img src={mediaUrl(m)} alt={`${m.chatTitle} 사진 첨부`} loading="lazy" /></a>}<MessageText text={m.text} links={m.links} />{m.attachment && <div className="message-tags"><a className="attachment-button" href={mediaUrl(m)} onClick={openInWindow}><Download size={13} />{m.attachment.label}</a></div>}</article>;

  if (!ready) return <div className="loading-screen"><LoaderCircle className="spin" />불러오는 중</div>;
  if (!logged) return <div className="login-page"><div className="login-card"><div className="brand-icon"><Send size={27} /></div><h1>Telegram Reader</h1><p>나의 대화, 한곳에서 차분하게.</p><form onSubmit={event => void login(event)}><label htmlFor="password">웹앱 비밀번호</label><div className="password-field"><LockKeyhole size={18} /><input id="password" type="password" value={password} autoComplete="current-password" autoFocus required maxLength={1024} onChange={event => setPassword(event.target.value)} placeholder="비밀번호를 입력하세요" /></div><button className="primary full" disabled={busy || !!retryUntil}>{busy ? '확인 중…' : '로그인'}</button></form>{error && <p className="error" role="alert">{error}</p>}{notice && <p className="hint">{notice}</p>}<div className="login-footer"><ShieldCheck size={16} />개인 계정 전용 · 메시지 영구저장 없음</div>{demo && <p className="hint">예시 데이터 미리보기 · 아무 텍스트로 로그인할 수 있습니다.</p>}</div></div>;
  return <div className="app-shell">
    {demo && <div className="demo-banner"><span className="demo-dot" />미리보기<span>Telegram은 예시 메시지 · Telemoa는 실제 공개 데이터 · Oracle 미연결</span></div>}
    <header className="header"><a className="brand" href={import.meta.env.BASE_URL}><span className="brand-icon"><Send size={23} /></span><span>Telegram<span className="brand-light"> Reader</span></span></a><nav><button onClick={() => void openChats()}><MessageCircle size={17} />대화방<span className="nav-count">{selected.length}</span></button><label className="header-date"><CalendarDays size={17} /><span>날짜</span><input aria-label="헤더 날짜 선택" type="date" value={day} min={settings?.historyStartDate} max={today} onChange={e => e.target.value && setDay(e.target.value)} /></label><button onClick={() => { setDraftStart(settings?.historyStartDate || today); setShowHidden(false); setModal('settings'); }}><Settings2 size={17} />설정</button></nav><div className="header-right"><span className={`connection-dot ${status?.telegram === 'connected' ? '' : 'offline'}`} /><span className="connection-label">{status?.telegram === 'connected' ? '연결됨' : status?.telegram === 'limited' ? '요청 제한' : '인증 필요'}</span><span className="header-divider" /><button className="icon-button" onClick={() => void logout()} aria-label="로그아웃" title="로그아웃"><LogOut size={18} /></button></div></header>
    <div className="body-layout"><aside className="sidebar"><div className="sidebar-title">내 워크스페이스</div><button className={`side-button ${filters === null ? 'active' : ''}`} aria-pressed={filters === null} onClick={() => setFilters(null)}><LayoutGrid size={18} />전체 피드<span>{selected.length}</span></button><div className="side-section"><span>선택한 대화방</span><button onClick={() => void openChats()} aria-label="대화방 선택 관리">+</button></div><div className="side-chats">{selectedChats.map(c => <button className={`side-button ${activeIds.includes(c.chatId) ? 'active' : ''}`} aria-pressed={activeIds.includes(c.chatId)} key={c.chatId} onClick={() => toggleChat(c.chatId)}>{c.type === 'group' ? <Users size={17} /> : c.type === 'private' ? <MessageCircle size={17} /> : <Hash size={17} />}<span className="chat-name">{c.title}</span>{activeIds.includes(c.chatId) && <Check size={14} />}</button>)}{!selected.length && <p className="sidebar-empty">대화방을 선택하고<br />나만의 피드를 만들어 보세요.</p>}</div><button className="add-chat" onClick={() => void openChats()}>+ 대화방 선택하기</button><div className="sidebar-bottom"><div className="privacy-note"><ShieldCheck size={20} /><strong>내 대화는, 내 계정에서</strong><p>메시지는 필요할 때만 읽고<br />서버에 영구 저장하지 않습니다.</p><span>READ ONLY</span></div><button className="delete-records" onClick={() => setModal('delete')}><Trash2 size={15} />기록삭제</button><div className="side-foot">TELEGRAM READER <span>v1.0</span></div></div></aside>
    <main><div className="page-heading"><div><div className="eyebrow">YOUR DAILY READING SPACE</div><h1>{filters === null ? '전체 피드' : activeIds.length === 1 ? selectedChats.find(c => c.chatId === activeIds[0])?.title || '대화방' : `선택한 대화방 ${activeIds.length}개`}<span className="heading-dot" /></h1><p>흩어진 대화를 모아, 필요한 정보에 집중하세요.</p></div><div className="heading-actions"><div className="segmented theme-toggle" aria-label="화면 밝기"><button className={theme === 'light' ? 'selected' : ''} aria-pressed={theme === 'light'} onClick={() => void saveTheme('light')}>밝음</button><button className={theme === 'dark' ? 'selected' : ''} aria-pressed={theme === 'dark'} onClick={() => void saveTheme('dark')}>어두움</button></div><div className="heading-meta"><span><ShieldCheck size={14} />읽기 전용</span><span>Asia/Seoul · KST</span></div></div></div>
    <TelemoaPanel />
    <div className="mobile-chat-filters" aria-label="표시할 대화방"><button className={filters === null ? 'active' : ''} aria-pressed={filters === null} onClick={() => setFilters(null)}>전체 피드</button>{selectedChats.map(c => <button key={c.chatId} className={activeIds.includes(c.chatId) ? 'active' : ''} aria-pressed={activeIds.includes(c.chatId)} onClick={() => toggleChat(c.chatId)}>{activeIds.includes(c.chatId) && <Check size={12} />}{c.title}</button>)}</div>
    <div className="toolbar"><div className="date-control"><button className="icon-button" disabled={day <= (settings?.historyStartDate || day)} onClick={() => moveDay(-1)} aria-label="이전 날짜"><ChevronLeft size={17} /></button><label><CalendarDays size={17} /><strong>{day === today ? '오늘' : day}</strong><span>{dateLabel(day)}</span><input type="date" aria-label="날짜 선택" value={day} min={settings?.historyStartDate} max={today} onChange={e => e.target.value && setDay(e.target.value)} /></label><button className="icon-button" disabled={day >= today} onClick={() => moveDay(1)} aria-label="다음 날짜"><ChevronRight size={17} /></button></div><div className="toolbar-right"><div className="segmented" aria-label="메시지 정렬"><button className={view === 'feed' ? 'selected' : ''} aria-pressed={view === 'feed'} onClick={() => setView('feed')}><List size={16} />시간순</button><button className={view === 'chat' ? 'selected' : ''} aria-pressed={view === 'chat'} onClick={() => setView('chat')}><LayoutGrid size={15} />대화방순</button></div>{day === today && <button className="refresh-button" disabled={loading || !!retryUntil} onClick={() => void load()}><RefreshCw size={16} className={loading ? 'spin' : ''} />새로고침</button>}</div></div>
    <div className="feed-caption"><div><span className="small-dot" />{activeIds.length}개 대화방<span className="caption-divider">/</span>{visibleMessages.length}개 메시지{loading && <LoaderCircle size={13} className="spin" />}</div><div>{lastUpdated && <span className="updated">{timeLabel(lastUpdated)} 업데이트</span>}</div></div>
    {error && <div className="alert error" role="alert"><CircleHelp size={17} /><span>{error}</span><button className="icon-button" aria-label="알림 닫기" onClick={() => setError('')}><X size={15} /></button></div>}{notice && <div className="alert">{notice}</div>}
    <section className="feed" aria-label="메시지 피드" aria-busy={loading}>{view === 'feed' ? visibleMessages.map(card) : chatGroups.map(([cid, items]) => <section className="chat-group" key={cid}><h2><Hash size={17} />{items[0].chatTitle}<span>{items.length}</span></h2>{items.map(card)}</section>)}{!visibleMessages.length && <div className="empty-state">{initialLoading ? <LoaderCircle size={32} className="spin" /> : <MessageCircle size={38} />}<h2>{!activeIds.length && selected.length ? '표시할 대화방을 선택해 주세요' : initialLoading ? '대화를 불러오고 있어요' : selected.length ? '표시할 메시지가 없습니다' : '읽고 싶은 대화방을 골라보세요'}</h2><p>{!activeIds.length && selected.length ? '대화방을 클릭해 선택하거나 전체 피드를 눌러주세요.' : initialLoading ? 'Telegram에서 선택한 날짜의 메시지를 조회합니다.' : selected.length ? '다른 날짜를 확인하거나 숨김 기록을 관리해 보세요.' : '채널과 그룹을 선택하면 이곳에 함께 표시됩니다.'}</p>{!selected.length && <button className="primary" onClick={() => void openChats()}>대화방 선택</button>}</div>}</section>
    {cursor && <div className="more-row"><button className="secondary" disabled={loading || !!retryUntil} onClick={() => void load(cursor)}>{loading ? '불러오는 중…' : '더 보기'}<ChevronRight size={16} /></button></div>}
    {visibleMessages.length > 0 && !cursor && !loading && <div className="feed-end"><span />선택한 날짜의 메시지를 모두 읽었습니다<span /></div>}
    <footer className="main-footer"><span><LockKeyhole size={12} />메시지 영구저장 없음</span><span>X는 이 웹앱에서 숨기기 · Telegram 원본은 그대로</span></footer></main></div>
    {modal === 'chats' && <Modal title="대화방 선택" close={closeModal} error={error} wide><p className="modal-description">내 계정의 채널과 대화방을 선택하세요. 모든 기기에 동기화됩니다.</p><div className="search-field"><Search size={17} /><input autoComplete="off" placeholder="대화방 검색" aria-label="대화방 검색" value={search} onChange={e => setSearch(e.target.value)} /></div><div className="filter-tabs">{[['public', '채널·그룹'], ['channel', '채널'], ['group', '그룹'], ['private', '개인대화'], ['all', '전체']].map(([id, label]) => <button key={id} className={kind === id ? 'active' : ''} onClick={() => setKind(id)}>{label}</button>)}</div><div className="selection-tools"><span>{draftIds.length}개 선택</span><button onClick={() => setDraftIds([...new Set([...draftIds, ...visibleChats.map(c => c.chatId)])])}>전체 선택</button><button onClick={() => setDraftIds([])}>전체 해제</button></div><div className="chat-picker">{busy && <p className="hint">대화방 목록을 불러오는 중…</p>}{visibleChats.map(c => <label className="chat-picker-row" key={c.chatId}><input type="checkbox" checked={draftIds.includes(c.chatId)} onChange={e => setDraftIds(ids => e.target.checked ? [...ids, c.chatId] : ids.filter(id => id !== c.chatId))} /><span className="picker-icon">{c.type === 'group' ? <Users size={18} /> : c.type === 'private' ? <MessageCircle size={18} /> : <Radio size={18} />}</span><strong>{c.title}</strong><span>{typeLabel[c.type]}</span></label>)}{!visibleChats.length && !busy && <p className="hint">표시할 대화방이 없습니다.</p>}</div><div className="modal-footer"><button className="secondary" onClick={closeModal}>취소</button><button className="primary" disabled={busy} onClick={() => void saveChats()}><Check size={16} />적용</button></div></Modal>}
    {modal === 'settings' && <Modal title="설정" close={closeModal} error={error} wide><section className="settings-section"><h3>대화 조회 시작일</h3><p>이 날짜 이후의 메시지만 조회합니다. 모든 기기에 적용됩니다.</p><div className="start-date"><input type="date" aria-label="대화 조회 시작일" value={draftStart} max={today} onChange={e => setDraftStart(e.target.value)} /><button className="primary" disabled={busy || !draftStart} onClick={() => void saveStart()}>저장</button></div></section><section className="settings-section"><h3>서버 상태</h3><div className="status-grid"><span>Telegram 연결</span><strong>{status?.telegram === 'connected' ? '정상' : '인증 또는 연결 확인 필요'}</strong><span>선택 대화방</span><strong>{selected.length}개</strong><span>숨긴 메시지 ID</span><strong>{settings?.hiddenCount || 0}개</strong><span>DB 크기</span><strong>{((status?.dbBytes || 0) / 1024).toFixed(1)} KB</strong><span>메시지 영구저장</span><strong className="teal-text">사용 안 함</strong></div></section><section className="settings-section"><button className="section-toggle" onClick={() => void hiddenPage()}><h3>숨긴 메시지 관리</h3><ChevronRight size={17} /></button><p>본문 없이 대화방 ID·메시지 ID·숨긴 시간만 저장됩니다.</p>{showHidden && <><div className="hidden-list">{hidden.map(h => <div className="hidden-row" key={`${h.chat_id}:${h.message_id}`}><span><code>{h.chat_id} / {h.message_id}</code><small>{new Date(h.hidden_at).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })}</small></span><button className="secondary" onClick={() => void restore(h)}>복원</button></div>)}{!hidden.length && <p className="hint">숨긴 메시지가 없습니다.</p>}</div>{hidden.length < hiddenTotal && <button className="secondary" onClick={() => void hiddenPage(hidden.length)}>더 보기</button>}<button className="text-danger" onClick={() => void clearHidden()} disabled={!hiddenTotal}>숨김 기록 전체 초기화</button></>}</section><section className="settings-section"><button className="secondary" onClick={() => { closeModal(); void logout(); }}><LogOut size={15} />로그아웃</button></section><section className="settings-section danger-zone"><h3>기록삭제</h3><p>Oracle에 저장된 웹앱 기록을 초기화합니다.</p><button className="danger" onClick={() => setModal('delete')}><Trash2 size={15} />기록삭제</button></section></Modal>}
    {modal === 'delete' && <Modal title="웹앱 기록을 삭제할까요?" close={closeModal} error={error}><div className="delete-warning"><Trash2 size={30} /><p>선택한 대화방, 숨긴 메시지 ID, 설정과 웹 로그인 세션을 Oracle에서 삭제합니다.</p><p>Telegram 인증 파일은 유지됩니다. Telegram 원본 메시지는 변경되지 않습니다.</p><strong>{demo ? '미리보기에서는 예시 데이터만 초기화합니다.' : '삭제 후 로그아웃됩니다. 이 작업은 되돌릴 수 없습니다.'}</strong></div><div className="modal-footer"><button className="secondary" disabled={busy} onClick={closeModal}>취소</button><button className="danger" disabled={busy} onClick={() => void deleteRecords()}>{busy ? '삭제 중…' : '기록 삭제 확인'}</button></div></Modal>}
  </div>;
}
