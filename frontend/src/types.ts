export type Chat = { chatId: string; title: string; type: 'channel' | 'group' | 'private'; selected: boolean };
export type Message = { chatId: string; chatTitle: string; messageId: number; sender: string | null; timestamp: string; text: string; links: string[]; forwarded: boolean; media: string | null; attachment: { kind: 'photo' | 'pdf' | 'video'; label: '사진' | 'PDF' | '동영상' } | null };
export type Settings = { historyStartDate: string; selectedChatIds: string[]; hiddenCount: number; theme: 'light' | 'dark'; revision?: string; today?: string };
export type Status = { telegram: 'connected' | 'limited' | 'setup_required'; selectedCount: number; hiddenCount: number; dbBytes: number; messagePersistence: false; timezone: string; today: string };
export type Page = { messages: Message[]; nextCursor: string | null; unavailableChatIds: string[] };
export type Hidden = { chat_id: string; message_id: number; hidden_at: string };
