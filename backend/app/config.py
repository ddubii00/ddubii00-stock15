import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Config:
    app_password: str = field(repr=False)
    db_path: Path = Path('/var/lib/telegram-reader/app.sqlite3')
    session_path: Path = Path('/var/lib/telegram-reader/session/telegram.session')
    api_id: int | None = field(default=None, repr=False)
    api_hash: str | None = field(default=None, repr=False)
    origin: str = 'https://localhost'
    base_path: str = '/telegram-7'
    session_seconds: int = 43200

    def __post_init__(self):
        if len(self.app_password) < 4:
            raise ValueError('APP_PASSWORD must contain at least 4 characters')
        if not self.db_path.is_absolute() or not self.session_path.is_absolute():
            raise ValueError('Database and Telegram session paths must be absolute')
        parsed = urlsplit(self.origin)
        if parsed.scheme != 'https' or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
            raise ValueError('APP_ORIGIN must be an HTTPS origin with no path')
        if self.base_path and (not self.base_path.startswith('/') or self.base_path.endswith('/') or '..' in self.base_path):
            raise ValueError('APP_BASE_PATH must start with / and have no trailing slash')

    @classmethod
    def from_env(cls):
        api_id = os.getenv('TELEGRAM_API_ID', '')
        try:
            parsed_id = int(api_id) if api_id else None
        except ValueError:
            raise ValueError('TELEGRAM_API_ID must be numeric') from None
        return cls(
            app_password=os.getenv('APP_PASSWORD', ''),
            db_path=Path(os.getenv('APP_DB_PATH') or '/var/lib/telegram-reader/app.sqlite3'),
            session_path=Path(os.getenv('TELEGRAM_SESSION_PATH') or '/var/lib/telegram-reader/session/telegram.session'),
            api_id=parsed_id,
            api_hash=os.getenv('TELEGRAM_API_HASH') or None,
            origin=os.getenv('APP_ORIGIN') or 'https://localhost',
            base_path=os.getenv('APP_BASE_PATH', '/telegram-7').rstrip('/'),
        )
