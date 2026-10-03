import hashlib
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .time_utils import today_kst

SCHEMA = '''
CREATE TABLE IF NOT EXISTS selected_chats (
    chat_id TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS hidden_messages (
    chat_id TEXT NOT NULL,
    message_id INTEGER NOT NULL CHECK(message_id > 0),
    hidden_at TEXT NOT NULL,
    PRIMARY KEY (chat_id, message_id)
);
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS web_sessions (
    token_hash TEXT PRIMARY KEY,
    csrf_token TEXT NOT NULL,
    expires_at INTEGER NOT NULL
);
'''


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Database:
    """Metadata only. Never pass a Telegram message object or message text here."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        os.chmod(path, 0o600)
        with self.connection() as db:
            db.executescript(SCHEMA)
            db.execute('INSERT OR IGNORE INTO app_settings VALUES (?, ?)', ('history_start_date', today_kst().isoformat()))
            db.execute('INSERT OR IGNORE INTO app_settings VALUES (?, ?)', ('state_revision', '0'))

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA secure_delete=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def settings(self):
        with self.connection() as db:
            day = db.execute('SELECT value FROM app_settings WHERE key=?', ('history_start_date',)).fetchone()[0]
            ids = [r[0] for r in db.execute('SELECT chat_id FROM selected_chats WHERE enabled=1 ORDER BY sort_order, chat_id')]
            count = db.execute('SELECT COUNT(*) FROM hidden_messages').fetchone()[0]
            revision = db.execute('SELECT value FROM app_settings WHERE key=?', ('state_revision',)).fetchone()[0]
        return {'historyStartDate': day, 'selectedChatIds': ids, 'hiddenCount': count, 'revision': revision}

    @staticmethod
    def bump(db):
        db.execute("UPDATE app_settings SET value=CAST(value AS INTEGER)+1 WHERE key='state_revision'")

    def select_chats(self, chat_ids: list[str]):
        with self.connection() as db:
            db.execute('DELETE FROM selected_chats')
            db.executemany('INSERT INTO selected_chats VALUES (?, 1, ?, ?)', [(cid, i, stamp()) for i, cid in enumerate(chat_ids)])
            self.bump(db)

    def set_start_date(self, day: str):
        with self.connection() as db:
            db.execute('UPDATE app_settings SET value=? WHERE key=?', (day, 'history_start_date'))
            self.bump(db)

    def hide(self, chat_id: str, message_id: int):
        with self.connection() as db:
            db.execute('INSERT OR IGNORE INTO hidden_messages VALUES (?, ?, ?)', (chat_id, message_id, stamp()))
            self.bump(db)

    def unhide(self, chat_id: str, message_id: int):
        with self.connection() as db:
            db.execute('DELETE FROM hidden_messages WHERE chat_id=? AND message_id=?', (chat_id, message_id))
            self.bump(db)

    def reset_hidden(self):
        with self.connection() as db:
            db.execute('DELETE FROM hidden_messages')
            self.bump(db)

    def delete_records(self):
        # Delete only application metadata. Never unlink Telegram's separate authentication session.
        with self.connection() as db:
            for table in ('selected_chats', 'hidden_messages', 'app_settings', 'web_sessions'):
                db.execute(f'DELETE FROM {table}')
            db.execute('INSERT INTO app_settings VALUES (?, ?)', ('history_start_date', today_kst().isoformat()))
            db.execute('INSERT INTO app_settings VALUES (?, ?)', ('state_revision', '0'))
        with self.connection() as db:
            db.execute('VACUUM')

    def hidden_pairs(self, pairs: list[tuple[str, int]]) -> set[tuple[str, int]]:
        found = set()
        with self.connection() as db:
            for start in range(0, len(pairs), 300):
                chunk = pairs[start:start + 300]
                sql = 'SELECT chat_id, message_id FROM hidden_messages WHERE (chat_id, message_id) IN (' + ','.join('(?,?)' for _ in chunk) + ')'
                found.update(tuple(r) for r in db.execute(sql, [v for p in chunk for v in p]))
        return found

    def hidden_page(self, offset: int, limit: int = 100):
        with self.connection() as db:
            return [dict(r) for r in db.execute('SELECT * FROM hidden_messages ORDER BY hidden_at DESC, chat_id, message_id LIMIT ? OFFSET ?', (limit, offset))]

    def create_session(self, token: str, csrf: str, seconds: int):
        with self.connection() as db:
            db.execute('DELETE FROM web_sessions WHERE expires_at<=?', (int(time.time()),))
            db.execute('INSERT INTO web_sessions VALUES (?, ?, ?)', (token_hash(token), csrf, int(time.time()) + seconds))

    def session(self, token: str):
        with self.connection() as db:
            row = db.execute('SELECT csrf_token, expires_at FROM web_sessions WHERE token_hash=? AND expires_at>?', (token_hash(token), int(time.time()))).fetchone()
            return dict(row) if row else None

    def delete_session(self, token: str):
        with self.connection() as db:
            db.execute('DELETE FROM web_sessions WHERE token_hash=?', (token_hash(token),))

    def clear_sessions(self):
        with self.connection() as db:
            db.execute('DELETE FROM web_sessions')

    def size(self):
        return sum(p.stat().st_size for p in (self.path, Path(str(self.path) + '-wal'), Path(str(self.path) + '-shm')) if p.exists())
