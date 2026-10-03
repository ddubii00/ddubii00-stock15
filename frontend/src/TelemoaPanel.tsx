import { useCallback, useEffect, useState } from 'react';
import { ArrowUpRight, BookOpen, ChevronUp, ChevronDown, RefreshCw, TrendingUp } from 'lucide-react';
import { api, httpUrl, openExternalWindow } from './api';

type Insights = {
  stocks: { rank: number; name: string; code: string; channels: string[]; channelCount: number; url: string }[];
  blogs: { rank: number; title: string; mentions: number; url: string }[];
  blogMode: string; sourceUrl: string; dataDate: string | null; fetchedAt: string;
};

export default function TelemoaPanel() {
  const [mode, setMode] = useState<'latest' | 'cumulative'>('latest');
  const [data, setData] = useState<Insights | null>(null), [error, setError] = useState(''), [loading, setLoading] = useState(false), [expanded, setExpanded] = useState(true);
  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true); setError('');
    try { const next = await api<Insights>(`insights/telemoa?mode=${mode}`, 'GET', undefined, signal); if (!signal?.aborted) setData(next); }
    catch (cause) { if (!signal?.aborted) setError(cause instanceof Error ? cause.message : 'Telemoa 연결을 확인해 주세요.'); }
    finally { if (!signal?.aborted) setLoading(false); }
  }, [mode]);
  useEffect(() => { const controller = new AbortController(); void load(controller.signal); return () => controller.abort(); }, [load]);
  return <section className="insights-section" aria-label="Telemoa 인기 종목 및 핵심 블로그">
    <div className="insights-title"><div><span className="insights-eyebrow">MARKET RADAR</span><h2>시장의 관심, 한눈에</h2></div><div><a href="https://telemoa.com/" onClick={event => { event.preventDefault(); openExternalWindow(event.currentTarget.href); }}>Telemoa <ArrowUpRight size={13} /></a><button className="icon-button" disabled={loading} aria-label="Telemoa 새로고침" onClick={() => void load()}><RefreshCw size={14} className={loading ? 'spin' : ''} /></button><button className="icon-button" onClick={() => setExpanded(value => !value)} aria-label={expanded ? 'Telemoa 섹션 접기' : 'Telemoa 섹션 펼치기'}>{expanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}</button></div></div>
    {expanded && <><div className="insight-grid"><div className="insight-card"><div className="insight-card-head"><h3><TrendingUp size={17} />인기 종목</h3><span>최근 24시간 언급</span></div><div className="stock-table-head"><span>순위</span><span>종목명</span><span>언급 채널</span></div>{data?.stocks.map(stock => <a className="stock-row" href={httpUrl(stock.url) || 'https://telemoa.com/stock'} onClick={event => { event.preventDefault(); openExternalWindow(event.currentTarget.href); }} key={stock.code}><span className={`rank ${stock.rank <= 3 ? 'top' : ''}`}>{stock.rank}</span><strong>{stock.name}</strong><div><span title={stock.channels.join(', ')}>{stock.channels.slice(0, 2).join(', ')}</span><b>{stock.channelCount}개</b></div></a>)}{!data && <p className="insight-placeholder">{loading ? '인기 종목 불러오는 중…' : '원문에서 인기 종목을 확인해 주세요.'}</p>}<a className="insight-more" href="https://telemoa.com/stock" onClick={event => { event.preventDefault(); openExternalWindow(event.currentTarget.href); }}>인기 종목 전체 보기<ArrowUpRight size={13} /></a></div>
    <div className="insight-card"><div className="insight-card-head"><h3><BookOpen size={17} />핵심 블로그</h3><div className="blog-tabs"><button className={mode === 'latest' ? 'active' : ''} onClick={() => { if (mode !== 'latest') { setData(null); setMode('latest'); } }}>최신</button><span>|</span><button className={mode === 'cumulative' ? 'active' : ''} onClick={() => { if (mode !== 'cumulative') { setData(null); setMode('cumulative'); } }}>누적</button></div></div><div className="blog-table-head"><span>순위</span><span>{mode === 'latest' ? '글 제목' : '블로그'}</span><span>{mode === 'latest' ? '언급' : '스크랩'}</span></div>{data?.blogs.map(blog => <a className="blog-row" key={blog.url} href={httpUrl(blog.url) || 'https://telemoa.com/blog'} onClick={event => { event.preventDefault(); openExternalWindow(event.currentTarget.href); }}><span className={`rank ${blog.rank <= 3 ? 'top' : ''}`}>{blog.rank}</span><strong title={blog.title}>{blog.title}</strong><span className="mention-count">{blog.mentions.toLocaleString()}</span></a>)}{!data && <p className="insight-placeholder">{loading ? '핵심 블로그 불러오는 중…' : '원문에서 인기 종목을 확인해 주세요.'}</p>}<a className="insight-more" href="https://telemoa.com/blog" onClick={event => { event.preventDefault(); openExternalWindow(event.currentTarget.href); }}>핵심 블로그 전체 보기<ArrowUpRight size={13} /></a></div></div>{error && <p className="insight-error" role="alert">{error}</p>}<div className="insight-source"><span>출처: Telemoa · 제목을 누르면 원문을 새 창으로 엽니다.</span><span>{data ? `${new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(data.fetchedAt))} 조회 · KST` : '공개 데이터 · 내 Telegram 선택과 별도'}</span></div></>}
  </section>;
}
