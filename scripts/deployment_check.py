#!/usr/bin/env python3
"""Check repository templates only. Never reads Oracle secrets or runtime data."""
import ast
import configparser
import re
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD_PATHS = ('/telegram-7', '/var/www/telegram-reader', '/etc/telegram-reader.env', '/var/lib/telegram-reader')
FILES = ('README.md', 'frontend/vite.config.ts', 'backend/app/config.py', 'deploy/webapp-stock15-7.service', 'deploy/nginx-telegram-reader.conf')


def check(root=ROOT):
    errors = []
    sources = {}

    def require(condition, detail):
        if not condition:
            errors.append(detail)

    for name in FILES:
        path = root / name
        if not path.is_file():
            errors.append('Missing deployment file: ' + name)
            continue
        sources[name] = path.read_text()
        for old in OLD_PATHS:
            require(old not in sources[name], 'Old deployment path in ' + name + ': ' + old)
    if len(sources) != len(FILES):
        return errors

    vite = sources['frontend/vite.config.ts']
    require(bool(re.search(r"base\s*:\s*['\"]/stock15-7/['\"]", vite)), 'Vite base must be /stock15-7/')

    config = ast.parse(sources['backend/app/config.py'])
    constants = [node.value for node in ast.walk(config) if isinstance(node, ast.Constant)]
    require(constants.count('/stock15-7') >= 2, 'Backend base path default and environment fallback must be /stock15-7')
    for path in ('/var/lib/stock15-7/app.sqlite3', '/var/lib/stock15-7/session/telegram.session'):
        require(constants.count(path) >= 2, 'Backend default and environment fallback must use ' + path)
    expected = ast.dump(ast.parse('len(self.app_password) < 4', mode='eval').body)
    require(any(isinstance(node, ast.If) and ast.dump(node.test) == expected for node in ast.walk(config)), 'Backend must accept passwords of at least 4 characters')

    services = sorted(path.name for path in (root / 'deploy').glob('*.service'))
    require(services == ['webapp-stock15-7.service'], 'Provide only deploy/webapp-stock15-7.service')
    service = configparser.ConfigParser(interpolation=None)
    service.read_string(sources['deploy/webapp-stock15-7.service'])
    for section, key, value in (
        ('Unit', 'Description', 'Stock15-7 Personal Telegram Reader'),
        ('Service', 'User', 'telegram-reader'), ('Service', 'Group', 'telegram-reader'),
        ('Service', 'WorkingDirectory', '/var/www/stock15-7'),
        ('Service', 'EnvironmentFile', '/etc/stock15-7.env'),
        ('Service', 'StateDirectory', 'stock15-7'), ('Service', 'StateDirectoryMode', '0700'),
        ('Service', 'ReadWritePaths', '/var/lib/stock15-7'), ('Service', 'UMask', '0077'),
        ('Service', 'Environment', 'PYTHONDONTWRITEBYTECODE=1'),
        ('Service', 'ProtectSystem', 'strict'), ('Service', 'ProtectHome', 'true'),
        ('Service', 'PrivateTmp', 'true'), ('Service', 'NoNewPrivileges', 'true'),
        ('Service', 'LimitCORE', '0'), ('Install', 'WantedBy', 'multi-user.target'),
    ):
        require(service.get(section, key, fallback=None) == value, 'systemd mismatch: ' + key)
    expected_command = '/var/www/stock15-7/.venv/bin/uvicorn backend.app.main:create_app --factory --host 127.0.0.1 --port 8017 --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-access-log --log-level warning'
    require(shlex.split(service.get('Service', 'ExecStart', fallback='')) == shlex.split(expected_command), 'systemd ExecStart must use stock15-7 venv, localhost:8017 and one worker')

    nginx = sources['deploy/nginx-telegram-reader.conf']
    assets = re.search(r'location\s+\^~\s+/stock15-7/assets/\s*\{([^{}]*)\}', nginx)
    require(assets is not None, 'nginx requires location ^~ /stock15-7/assets/')
    if assets:
        require(bool(re.search(r'alias\s+/var/www/stock15-7/frontend/dist/assets/\s*;', assets[1])), 'nginx assets alias must use stock15-7 dist/assets with trailing /')
        require('proxy_pass' not in assets[1], 'nginx must serve Vite assets directly')
        require('access_log off;' in assets[1] and 'add_header Cache-Control "no-store" always;' in assets[1], 'nginx assets require no-store and access_log off')
    proxy = re.search(r'location\s+/stock15-7/\s*\{([^{}]*)\}', nginx)
    require(proxy is not None, 'nginx requires /stock15-7/ proxy')
    if proxy:
        for directive in ('proxy_pass http://127.0.0.1:8017/;', 'proxy_cache off;', 'proxy_buffering off;', 'proxy_request_buffering off;', 'proxy_max_temp_file_size 0;', 'access_log off;', 'add_header Cache-Control "no-store" always;'):
            require(directive in proxy[1], 'nginx proxy missing: ' + directive)
    require(bool(re.search(r'location\s+=\s+/stock15-7\s*\{\s*return\s+308\s+/stock15-7/;', nginx)), 'nginx requires canonical trailing-slash redirect')

    readme = sources['README.md']
    require('## A. 최초 Oracle 설치' in readme and '## B. 기존 Oracle 서버 업데이트' in readme, 'README must separate initial install and existing-server update')
    update = readme.split('## B. 기존 Oracle 서버 업데이트', 1)[-1].split('## SQLite schema', 1)[0]
    commands = '\n'.join(re.findall(r'```bash\n(.*?)```', update, re.S))
    for command in ('cd /var/www/stock15-7', 'git fetch origin', 'git reset --hard origin/main', '.venv/bin/pip install -r requirements.txt', 'npm ci', 'npm run build', 'find frontend/dist -type d -exec chmod 755 {} \\;', 'find frontend/dist -type f -exec chmod 644 {} \\;', 'sudo systemctl restart webapp-stock15-7.service', 'sudo nginx -t', 'sudo systemctl reload nginx'):
        require(command in commands, 'README update missing: ' + command)
    require(not re.search(r'(?m)^\s*(?:sudo\s+)?(?:cp|install|tee|nano)\b|telegram_login\.py', commands), 'README normal update must not install configs, edit secrets or reauthenticate Telegram')
    example = root / '.env.example'
    names = ('TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 'TELEGRAM_PHONE', 'APP_PASSWORD', 'TELEGRAM_SESSION_PATH', 'APP_DB_PATH', 'APP_ORIGIN', 'APP_BASE_PATH', 'TZ')
    require(example.is_file() and example.read_text().splitlines() == [name + '=' for name in names], '.env.example must contain only the nine empty variables')
    return errors


if __name__ == '__main__':
    try:
        errors = check()
    except (SyntaxError, configparser.Error, ValueError) as error:
        errors = ['Deployment template parse error: ' + type(error).__name__]
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        sys.exit(1)
    print('Deployment consistency passed: stock15-7 paths, 4-character minimum, systemd, nginx direct assets and safe update instructions.')
