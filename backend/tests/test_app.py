import asyncio
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.time_utils import date_bounds, require_aware
from backend.app.telegram import TelegramLimited, TelegramReader, TelegramUnavailable
from .conftest import FakeTelegram, sign_in

PREFIX = '/stock15-7/api'


@pytest.mark.parametrize('method,path,body', [
    ('GET', '/status', None), ('GET', '/chats', None), ('GET', '/messages?date=2026-10-03', None),
    ('GET', '/settings', None), ('GET', '/messages/hidden', None), ('GET', '/insights/telemoa', None),
    ('PUT', '/settings/chats', {'chatIds': []}), ('PUT', '/settings/start-date', {'date': '2026-10-01'}),
    ('POST', '/messages/hide', {'chatId': '-1001', 'messageId': 2}),
    ('DELETE', '/messages/hide/-1001/2', None), ('DELETE', '/messages/hide-all', None), ('DELETE', '/settings/records', None),
])
def test_all_private_endpoints_block_anonymous(rig, method, path, body):
    _, client, _, _, _ = rig
    result = client.request(method, PREFIX + path, json=body)
    assert result.status_code == 401
    assert result.headers['Cache-Control'] == 'no-store'


def test_cookie_password_and_csrf(rig):
    _, client, password, _, _ = rig
    assert client.post(PREFIX + '/auth/login', json={'password': password}).status_code == 403
    assert client.post(PREFIX + '/auth/login', json={'password': password}, headers={'Origin': 'https://attacker.test'}).status_code == 403
    result = client.post(PREFIX + '/auth/login', json={'password': password}, headers={'Origin': 'https://reader.test'})
    cookie = result.headers['set-cookie'].lower()
    assert all(item in cookie for item in ('httponly', 'secure', 'samesite=strict', 'path=/stock15-7/'))
    assert client.get(PREFIX + '/settings').status_code == 200
    assert client.put(PREFIX + '/settings/chats', json={'chatIds': []}, headers={'Origin': 'https://reader.test'}).status_code == 403
    assert client.put(PREFIX + '/settings/chats', json={'chatIds': []}, headers={'Origin': 'https://attacker.test', 'X-CSRF-Token': result.json()['csrfToken']}).status_code == 403


def test_login_rate_limit_and_validation_do_not_echo_password(rig):
    _, client, _, _, _ = rig
    assert client.post(PREFIX + '/auth/login', json={'password': []}, headers={'Origin': 'https://reader.test'}).json() == {'detail': '요청 형식을 확인해 주세요.'}
    for _ in range(5):
        assert client.post(PREFIX + '/auth/login', json={'password': os.urandom(12).hex()}, headers={'Origin': 'https://reader.test'}).status_code == 401
    response = client.post(PREFIX + '/auth/login', json={'password': os.urandom(12).hex()}, headers={'Origin': 'https://reader.test'})
    assert response.status_code == 429 and response.headers['retry-after'] == '300'


def test_status_and_dialog_conversion(authenticated):
    _, client, headers, _, _ = authenticated
    assert client.put(PREFIX + '/settings/chats', json={'chatIds': ['-1002']}, headers=headers).status_code == 200
    chats = client.get(PREFIX + '/chats').json()
    assert chats[0]['chatId'] == '-1002' and chats[0]['selected']
    assert {c['type'] for c in chats} == {'channel', 'group', 'private'}
    status = client.get(PREFIX + '/status').json()
    assert status['telegram'] == 'connected'
    assert status['selectedCount'] == 1 and status['dbBytes'] > 0
    assert not status['messagePersistence']


def test_multidevice_selection_and_hidden_state(authenticated, rig):
    app, client, headers, _, _ = authenticated
    other = TestClient(app, base_url='https://reader.test')  # same service, a different browser cookie jar
    other_headers = sign_in(other, rig[2])
    chosen = ['-1001', '-1002']
    client.put(PREFIX + '/settings/chats', json={'chatIds': chosen}, headers=headers)
    assert other.get(PREFIX + '/settings').json()['selectedChatIds'] == chosen
    assert other.get(PREFIX + '/messages?date=2026-10-03').json()['messages']
    client.post(PREFIX + '/messages/hide', json={'chatId': '-1001', 'messageId': 3}, headers=headers)
    result = other.get(PREFIX + '/messages?date=2026-10-03').json()['messages']
    assert not any(m['chatId'] == '-1001' and m['messageId'] == 3 for m in result)
    assert other.get(PREFIX + '/settings').json()['hiddenCount'] == 1
    assert other.delete(PREFIX + '/messages/hide/-1001/3', headers=other_headers).status_code == 200
    assert client.get(PREFIX + '/settings').json()['hiddenCount'] == 0


def test_kst_exact_date_bounds_and_no_naive_datetime():
    start, end = date_bounds(date(2026, 10, 3))
    assert start == datetime(2026, 10, 2, 15, tzinfo=timezone.utc)
    assert end == datetime(2026, 10, 3, 15, tzinfo=timezone.utc)
    assert start <= datetime(2026, 10, 2, 15, 1, tzinfo=timezone.utc) < end
    assert start <= datetime(2026, 10, 3, 14, 59, tzinfo=timezone.utc) < end
    with pytest.raises(ValueError):
        require_aware(datetime(2026, 10, 3))


@pytest.mark.parametrize('order', ['asc', 'desc'])
def test_date_filter_and_pagination_have_no_gaps(authenticated, order):
    _, client, headers, _, _ = authenticated
    client.put(PREFIX + '/settings/chats', json={'chatIds': ['-1001', '-1002']}, headers=headers)
    result = []
    cursor = None
    for _ in range(20):
        params = {'date': '2026-10-03', 'limit': 2, 'order': order}
        if cursor: params['cursor'] = cursor
        page = client.get(PREFIX + '/messages', params=params)
        assert page.status_code == 200, page.text
        result += page.json()['messages']
        cursor = page.json()['nextCursor']
        if not cursor: break
    assert cursor is None
    pairs = [(m['chatId'], m['messageId']) for m in result]
    assert len(pairs) == len(set(pairs)) == 4
    assert set(pairs) == {('-1001', 2), ('-1001', 3), ('-1001', 4), ('-1002', 10)}
    stamps = [datetime.fromisoformat(m['timestamp']) for m in result]
    assert stamps == sorted(stamps, reverse=order == 'desc')


@pytest.mark.parametrize('order', ['asc', 'desc'])
def test_dense_hidden_batches_keep_global_order_and_advance(authenticated, order):
    app, client, headers, fake, _ = authenticated
    start, _ = date_bounds(date(2026, 10, 3))
    fake.messages = {
        '-1001': [FakeTelegram.message('-1001', i, (start + timedelta(minutes=i)).isoformat()) for i in range(1, 25)],
        '-1002': [FakeTelegram.message('-1002', i, (start + timedelta(minutes=i * 2)).isoformat()) for i in range(1, 13)],
    }
    app.state.db.select_chats(['-1001', '-1002'])
    for i in range(2, 24): app.state.db.hide('-1001', i)
    result, cursor = [], None
    for _ in range(50):
        params = {'date': '2026-10-03', 'limit': 2, 'order': order}
        if cursor: params['cursor'] = cursor
        page = client.get(PREFIX + '/messages', params=params)
        assert page.status_code == 200
        result += page.json()['messages']
        cursor = page.json()['nextCursor']
        if not cursor: break
    assert cursor is None and len(result) == 14
    stamps = [(datetime.fromisoformat(m['timestamp']), int(m['chatId']), m['messageId']) for m in result]
    assert stamps == sorted(stamps, reverse=order == 'desc')


def test_start_date_and_unselected_chat_are_enforced_on_server(authenticated):
    _, client, headers, fake, _ = authenticated
    client.put(PREFIX + '/settings/chats', json={'chatIds': ['-1001']}, headers=headers)
    client.put(PREFIX + '/settings/start-date', json={'date': '2026-10-03'}, headers=headers)
    before = len(fake.calls)
    assert client.get(PREFIX + '/messages?date=2026-10-02').status_code == 400
    assert len(fake.calls) == before
    assert client.get(PREFIX + '/messages?date=2026-10-03&chat_id=-1002').status_code == 403
    assert client.put(PREFIX + '/settings/chats', json={'chatIds': ['99999']}, headers=headers).status_code == 400
    assert client.put(PREFIX + '/settings/start-date', json={'date': '2026-10-04'}, headers=headers).status_code == 400


def test_cursor_tampering_context_changes_and_future_date(authenticated):
    _, client, headers, _, _ = authenticated
    client.put(PREFIX + '/settings/chats', json={'chatIds': ['-1001']}, headers=headers)
    cursor = client.get(PREFIX + '/messages?date=2026-10-03&limit=1').json()['nextCursor']
    assert cursor
    assert client.get(PREFIX + '/messages', params={'date': '2026-10-03', 'cursor': cursor[:-4] + 'AAAA'}).status_code == 400
    assert client.get(PREFIX + '/messages', params={'date': '2026-10-03', 'cursor': cursor, 'order': 'asc'}).status_code == 409
    client.put(PREFIX + '/settings/chats', json={'chatIds': []}, headers=headers)
    assert client.get(PREFIX + '/messages', params={'date': '2026-10-03', 'cursor': cursor}).status_code == 409
    assert client.get(PREFIX + '/messages?date=2026-10-04').status_code == 400


def test_database_schema_and_bytes_never_contain_message_text(authenticated):
    app, client, headers, _, config = authenticated
    app.state.db.select_chats(['-1001'])
    assert client.get(PREFIX + '/messages?date=2026-10-03').status_code == 200
    client.post(PREFIX + '/messages/hide', json={'chatId': '-1001', 'messageId': 3}, headers=headers)
    with sqlite3.connect(config.db_path) as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == {'selected_chats', 'hidden_messages', 'app_settings', 'web_sessions'}
        assert [r[1] for r in db.execute('PRAGMA table_info(hidden_messages)')] == ['chat_id', 'message_id', 'hidden_at']
        dump = '\n'.join(db.iterdump())
        assert not any(word in dump for word in ('SYNTHETIC_BODY', 'SYNTHETIC_SENDER', '합성 대화방'))
    assert b'SYNTHETIC_BODY' not in config.db_path.read_bytes()
    assert config.db_path.stat().st_mode & 0o777 == 0o600


def test_record_delete_revokes_all_browsers_preserves_telegram_auth(authenticated, rig):
    app, client, headers, _, config = authenticated
    other = TestClient(app, base_url='https://reader.test')
    sign_in(other, rig[2])
    app.state.db.select_chats(['-1001'])
    app.state.db.hide('-1001', 3)
    config.session_path.write_bytes(b'not-a-real-session-test-marker')
    assert client.delete(PREFIX + '/settings/records').status_code == 403
    assert client.delete(PREFIX + '/settings/records', headers=headers).status_code == 200
    assert config.session_path.read_bytes() == b'not-a-real-session-test-marker'
    assert client.get(PREFIX + '/settings').status_code == 401
    assert other.get(PREFIX + '/settings').status_code == 401
    assert app.state.db.settings()['selectedChatIds'] == []
    assert app.state.db.settings()['hiddenCount'] == 0
    assert app.state.db.hidden_page(0) == []
    assert b'-1001' not in config.db_path.read_bytes()


def test_floodwait_is_bounded_and_no_store(authenticated, monkeypatch):
    app, client, _, fake, _ = authenticated
    app.state.db.select_chats(['-1001'])
    async def limited(*args, **kwargs): raise TelegramLimited(45)
    monkeypatch.setattr(fake, 'dialogs', limited)
    result = client.get(PREFIX + '/messages?date=2026-10-03')
    assert result.status_code == 429
    assert result.headers['Retry-After'] == '45'
    assert result.headers['Cache-Control'] == 'no-store'


def test_missing_real_telegram_auth_has_safe_status(rig):
    config = rig[4]
    reader = TelegramReader(config)
    assert asyncio.run(reader.status()) == 'setup_required'
    with pytest.raises(TelegramUnavailable): asyncio.run(reader.ready())


def test_subpath_assets_auth_gate_and_security_headers(authenticated):
    _, client, _, _, _ = authenticated
    index = client.get('/stock15-7/')
    assert index.status_code == 200
    assert '/stock15-7/assets/' in index.text
    assert "frame-ancestors 'none'" in index.headers['content-security-policy']
    assert index.headers['cache-control'] == 'no-store'
    assert client.get('/stock15-7/api/auth/session').status_code == 200
    assert client.get('/stock15-7/api/does-not-exist').status_code == 404
