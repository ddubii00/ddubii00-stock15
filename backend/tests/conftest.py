import secrets
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Config
from backend.app.main import create_app
from backend.app.telegram import Chat, MediaDownload, Scan, byte_range


class FakeTelegram:
    """Synthetic transport double. Contains no real account or credentials."""
    def __init__(self):
        self.chats = {
            '-1001': Chat('-1001', '채널 예시', 'channel', datetime(2026, 10, 3, tzinfo=timezone.utc)),
            '-1002': Chat('-1002', '그룹 예시', 'group', datetime(2026, 10, 2, tzinfo=timezone.utc)),
            '1003': Chat('1003', '개인대화 예시', 'private', datetime(2026, 10, 1, tzinfo=timezone.utc)),
        }
        self.dialog_time = 0
        self.calls = []
        self.messages = {'-1001': [
            self.message('-1001', 1, '2026-10-02T14:59:59+00:00'),
            self.message('-1001', 2, '2026-10-02T15:00:00+00:00'),
            self.message('-1001', 3, '2026-10-02T15:01:00+00:00'),
            self.message('-1001', 4, '2026-10-03T14:59:00+00:00'),
            self.message('-1001', 5, '2026-10-03T15:00:00+00:00'),
        ], '-1002': [self.message('-1002', 10, '2026-10-03T10:00:00+00:00')]}

    @staticmethod
    def message(cid, mid, when):
        return {'chatId': cid, 'chatTitle': '합성 대화방', 'messageId': mid, 'timestamp': when, 'text': 'SYNTHETIC_BODY_NEVER_PERSIST_' + str(mid), 'sender': 'SYNTHETIC_SENDER_NEVER_PERSIST', 'links': [], 'media': '파일', 'attachment': {'kind': 'pdf', 'label': 'PDF'}, 'forwarded': False}

    async def close(self):
        pass

    async def status(self):
        return 'connected'

    async def dialogs(self, force=False):
        return self.chats

    async def scan(self, chat, start, end, order, offset, limit):
        self.calls.append((chat.chat_id, start, end, offset, limit))
        items = sorted(self.messages.get(chat.chat_id, []), key=lambda m: (datetime.fromisoformat(m['timestamp']), m['messageId']), reverse=order == 'desc')
        if offset:
            items = [m for m in items if m['messageId'] > offset] if order == 'asc' else [m for m in items if m['messageId'] < offset]
        else:
            items = [m for m in items if datetime.fromisoformat(m['timestamp']) >= start] if order == 'asc' else [m for m in items if datetime.fromisoformat(m['timestamp']) < end]
        raw = items[:limit]
        valid = []
        exited = False
        last = offset
        last_key = None
        for m in raw:
            last = m['messageId']
            when = datetime.fromisoformat(m['timestamp'])
            last_key = (when, int(chat.chat_id), last)
            if order == 'asc' and when >= end or order == 'desc' and when < start:
                exited = True
                break
            if start <= when < end:
                valid.append(m)
        return Scan(valid, last, exited or len(raw) < limit, last_key)

    async def media_stream(self, chat_id, message_id, range_header=None):
        if chat_id not in self.chats or not any(item['messageId'] == message_id for item in self.messages.get(chat_id, [])):
            return None
        data = b'%PDF-synthetic-attachment'
        requested = byte_range(range_header, len(data))
        start, end = requested or (0, len(data) - 1)

        async def chunks():
            yield data[start:end + 1]

        return MediaDownload('PDF', 'synthetic.pdf', 'application/pdf', chunks(), len(data), start, end, requested is not None)


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr('backend.app.main.today_kst', lambda: date(2026, 10, 3))
    password = secrets.token_urlsafe(24)  # generated at runtime, never a real credential
    config = Config(app_password=password, db_path=tmp_path / 'app.sqlite3', session_path=tmp_path / 'telegram.session', origin='https://reader.test')
    telegram = FakeTelegram()
    app = create_app(config, telegram)
    app.state.db.set_start_date('2026-09-01')
    with TestClient(app, base_url='https://reader.test') as client:
        yield app, client, password, telegram, config


def sign_in(client, password):
    response = client.post('/stock15-7/api/auth/login', json={'password': password}, headers={'Origin': 'https://reader.test'})
    assert response.status_code == 200
    return {'Origin': 'https://reader.test', 'X-CSRF-Token': response.json()['csrfToken']}


@pytest.fixture
def authenticated(rig):
    app, client, password, telegram, config = rig
    headers = sign_in(client, password)
    return app, client, headers, telegram, config
