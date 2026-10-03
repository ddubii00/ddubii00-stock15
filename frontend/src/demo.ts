import { todayKst } from './api';
import type { Chat, Message, Settings, Hidden } from './types';

// Development-only preview. All names and texts below are invented, never fetched from Telegram.
export function installDemo() {
  const day = todayKst();
  const chats: Chat[] = [
    { chatId: '-1001', title: '오늘의 마켓 노트', type: 'channel', selected: true },
    { chatId: '-1002', title: '테크 인사이트', type: 'channel', selected: true },
    { chatId: '-1003', title: '투자 공부 모임', type: 'group', selected: true },
    { chatId: '-1004', title: '글로벌 경제 브리핑', type: 'channel', selected: true },
    { chatId: '-1005', title: '주말 읽을거리', type: 'channel', selected: false },
    { chatId: '1006', title: '개인 대화 예시', type: 'private', selected: false },
  ];
  let settings: Settings = { selectedChatIds: chats.filter(c => c.selected).map(c => c.chatId), historyStartDate: `${day.slice(0, 8)}01`, hiddenCount: 0, theme: 'light', revision: '0', today: day };
  let hidden: Hidden[] = [];
  const texts = [
    '오늘 시장을 읽는 세 가지 질문\n\n1. 금리의 방향보다 변화 속도를 보고 있나요?\n2. 기업의 성장과 가격에 반영된 기대를 구분하고 있나요?\n3. 단기 뉴스와 장기 투자 가설이 연결되어 있나요?\n\n주말에는 한 주의 기록을 차분하게 돌아보세요. 다음 주를 준비하는 데 좋은 출발점이 됩니다.',
    '기술의 변화는 작은 신호에서 시작됩니다.\n\n이번 주 읽을거리: 반도체 생태계, 데이터센터의 전력 수요, 그리고 새로운 인터페이스. 숫자 하나보다 그 숫자가 만들어지는 과정을 함께 살펴봅니다.\n\n참고 링크: https://telegram.org',
    '이번 주에 읽은 자료 중 가장 흥미로웠던 내용을 공유해 주세요.\n\n결론보다 근거를, 예측보다 관찰을 먼저 적어 보면 서로의 생각을 더 잘 이해할 수 있습니다.',
    '주말 글로벌 경제 체크리스트\n\n• 주요 지표 발표 일정을 확인하기\n• 환율과 원자재 흐름을 함께 보기\n• 관심 기업의 다음 실적 발표일 정리하기\n\n이 카드는 화면 미리보기를 위한 가상의 메시지입니다.',
    '메모를 줄이고, 생각을 남기기\n\n많은 채널을 읽다 보면 같은 이야기를 여러 번 만나게 됩니다. 오늘의 핵심 질문 하나를 정하고, 관련 있는 메시지만 남겨 보세요.',
    '자료 공유드립니다. 첨부 파일은 필요할 때만 Telegram에서 브라우저로 전송됩니다.\n\n이 화면에서는 메시지의 본문과 시간, 대화방을 한눈에 확인할 수 있습니다.',
  ];
  const messages: Message[] = texts.map((text, i) => ({ chatId: chats[i % 4].chatId, chatTitle: chats[i % 4].title, messageId: i + 1, timestamp: `${day}T${['16:42', '16:18', '15:55', '15:30', '14:20', '13:05'][i]}:00+09:00`, text, links: i === 1 ? ['https://telegram.org'] : [], sender: i === 2 ? '참여자 예시' : null, forwarded: i === 3, media: i === 5 ? '파일' : null, attachment: null }));
  const originalFetch = window.fetch;
  window.fetch = async (input, init) => {
    const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, location.origin);
    if (!url.pathname.includes('/api/')) return originalFetch(input, init);
    const path = url.pathname.split('/api/')[1];
    if (path.startsWith('insights/telemoa')) return originalFetch(input, init);
    const body = init?.body ? JSON.parse(String(init.body)) : {};
    let data: unknown = { ok: true };
    if (path.startsWith('auth/')) data = { csrfToken: 'preview-only' };
    else if (path === 'status') data = { telegram: 'connected', selectedCount: settings.selectedChatIds.length, hiddenCount: hidden.length, dbBytes: 32768, messagePersistence: false, timezone: 'Asia/Seoul', today: day };
    else if (path === 'chats') data = chats.map(c => ({ ...c, selected: settings.selectedChatIds.includes(c.chatId) }));
    else if (path === 'settings/chats') { settings.selectedChatIds = body.chatIds; settings.revision = String(Number(settings.revision) + 1); data = settings; }
    else if (path === 'settings/start-date') { settings.historyStartDate = body.date; settings.revision = String(Number(settings.revision) + 1); data = settings; }
    else if (path === 'settings/theme') { settings.theme = body.theme; settings.revision = String(Number(settings.revision) + 1); data = settings; }
    else if (path === 'settings') data = { ...settings, hiddenCount: hidden.length };
    else if (path === 'messages') {
      let items = messages.filter(m => m.timestamp.startsWith(url.searchParams.get('date') || day) && settings.selectedChatIds.includes(m.chatId) && !hidden.some(h => h.chat_id === m.chatId && h.message_id === m.messageId));
      const ids = url.searchParams.getAll('chat_id');
      if (ids.length) items = items.filter(m => ids.includes(m.chatId));
      if (url.searchParams.get('order') === 'asc') items = [...items].reverse();
      data = { messages: items, nextCursor: null, unavailableChatIds: [] };
    } else if (path === 'messages/hide') {
      if (!hidden.some(h => h.chat_id === body.chatId && h.message_id === body.messageId)) hidden.push({ chat_id: body.chatId, message_id: body.messageId, hidden_at: new Date().toISOString() });
      settings = { ...settings, hiddenCount: hidden.length, revision: String(Number(settings.revision) + 1) };
      data = settings;
    }
    else if (path === 'messages/hidden') data = { items: hidden.slice(Number(url.searchParams.get('offset')) || 0, (Number(url.searchParams.get('offset')) || 0) + 100), total: hidden.length };
    else if (path === 'messages/hide-all') { hidden = []; settings.revision = String(Number(settings.revision) + 1); }
    else if (path.startsWith('messages/hide/')) { hidden = hidden.filter(h => `${h.chat_id}/${h.message_id}` !== path.replace('messages/hide/', '')); settings.revision = String(Number(settings.revision) + 1); }
    else if (path === 'settings/records') { hidden = []; settings = { ...settings, selectedChatIds: [], historyStartDate: day }; }
    return new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } });
  };
}
