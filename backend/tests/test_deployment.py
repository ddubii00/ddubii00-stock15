import secrets
from pathlib import Path

import pytest

from backend.app.config import Config
from scripts.deployment_check import FILES, ROOT, check


def test_deployment_templates_match_oracle():
    assert check() == []


@pytest.mark.parametrize('name,old,new', [
    ('deploy/nginx-telegram-reader.conf', 'location ^~ /stock15-7/assets/', 'location /stock15-7/assets/'),
    ('deploy/nginx-telegram-reader.conf', 'alias /var/www/stock15-7/frontend/dist/assets/;', 'alias /var/www/stock15-7/frontend/dist/assets;'),
    ('deploy/webapp-stock15-7.service', 'WorkingDirectory=/var/www/stock15-7', 'WorkingDirectory=/var/www/old-reader'),
    ('backend/app/config.py', 'len(self.app_password) < 4', 'len(self.app_password) < 12'),
])
def test_deployment_check_catches_known_regressions(tmp_path, name, old, new):
    for filename in (*FILES, '.env.example'):
        target = tmp_path / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((ROOT / filename).read_text())
    target = tmp_path / name
    target.write_text(target.read_text().replace(old, new))
    assert check(tmp_path)


def test_config_environment_defaults_preserve_oracle_paths_and_four_characters(monkeypatch):
    for name in ('APP_PASSWORD', 'APP_ORIGIN', 'APP_BASE_PATH', 'APP_DB_PATH', 'TELEGRAM_SESSION_PATH', 'TELEGRAM_API_ID', 'TELEGRAM_API_HASH'):
        monkeypatch.delenv(name, raising=False)
    password = secrets.token_hex(2)  # four synthetic characters, never a real credential
    monkeypatch.setenv('APP_PASSWORD', password)
    config = Config.from_env()
    assert config.app_password == password
    assert config.base_path == '/stock15-7'
    assert config.db_path == Path('/var/lib/stock15-7/app.sqlite3')
    assert config.session_path == Path('/var/lib/stock15-7/session/telegram.session')
    with pytest.raises(ValueError):
        Config(app_password=password[:3])
