#!/usr/bin/env python3
"""Inspect source and Git index without printing potentially sensitive file contents."""
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'.git', 'node_modules', 'dist', '.venv', 'venv', '__pycache__', '.pytest_cache', 'test-results'}
FORBIDDEN = ('.env', '.env.*', '*.session', '*.session-*', '*.sqlite', '*.sqlite3', '*.sqlite-*', '*.sqlite3-*', '*.pem', '*.key')
REQUIRED = ['.env', '.env.*', '*.session', '*.session-journal', '*.sqlite', '*.sqlite3', 'data/', 'secrets/']


def source_files():
    # Do not descend into third-party modules or build artifacts.
    import os
    for current, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for name in files:
            yield Path(current) / name


def forbidden(path):
    p = Path(path)
    return p.name != '.env.example' and (any(fnmatch.fnmatch(p.name, pat) for pat in FORBIDDEN) or any(part in ('data', 'secrets') for part in p.parts))


def check():
    errors = []
    ignore = (ROOT / '.gitignore').read_text().splitlines()
    for pattern in REQUIRED:
        if pattern not in ignore: errors.append('Missing gitignore pattern: ' + pattern)
    example = (ROOT / '.env.example').read_text().splitlines()
    if any(line.strip() and not re.fullmatch(r'[A-Z_]+=', line.strip()) for line in example):
        errors.append('.env.example contains a value or unexpected content')
    paths = list(source_files())
    for path in paths:
        rel = path.relative_to(ROOT)
        if forbidden(rel): errors.append('Private file found in source tree: ' + str(rel)); continue
        try: text = path.read_text()
        except (UnicodeDecodeError, OSError): continue
        # Detect literal secret assignments. References and empty placeholders are allowed.
        for name in ('TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 'TELEGRAM_PHONE', 'APP_PASSWORD'):
            patterns = [rf'(?m)^[ \t]*{name}[ \t]*=[ \t]*[^\s\n]', rf'''(?i)\b{name}\b[ \t]*[:=][ \t]*["'][^"'\n]+["']''']
            if any(re.search(pat, text) for pat in patterns): errors.append('Possible literal credential: ' + str(rel))
        if re.search(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', text): errors.append('Private key: ' + str(rel))
    result = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True)
    if result.returncode == 0:
        tracked = result.stdout.decode().split('\0')
        errors.extend('Forbidden Git tracked file: ' + name for name in tracked if name and forbidden(name))
        samples = ['.env', '.env.production', 'telegram.session', 'telegram.session-journal', 'app.sqlite3', 'app.sqlite3-wal', 'data/message.json', 'secrets/key']
        ignored = subprocess.run(['git', 'check-ignore', '--stdin'], input='\n'.join(samples) + '\n', cwd=ROOT, text=True, capture_output=True)
        errors.extend('Not gitignored: ' + name for name in samples if name not in ignored.stdout.splitlines())
    backend = list((ROOT / 'backend' / 'app').glob('*.py'))
    write_calls = re.compile(r'\.(?:send_message|edit_message|delete_messages|forward_messages|send_read_acknowledge|download_media)\s*\(')
    for path in backend:
        if write_calls.search(path.read_text()): errors.append('Forbidden Telegram write/media method: ' + path.name)
    frontend = (ROOT / 'frontend' / 'src')
    for path in frontend.glob('*'):
        if path.suffix in ('.ts', '.tsx') and re.search(r'\b(?:localStorage|sessionStorage|indexedDB)\b', path.read_text()):
            errors.append('Browser persistence API found: ' + path.name)
    if errors:
        print('\n'.join(sorted(set(errors))), file=sys.stderr)
        return 1
    print(f'Security source scan passed ({len(paths)} files); no literal credentials, private files, Telegram write calls, or browser storage APIs detected.')
    print('This is a source/index check, not proof that arbitrary historical or external files contain no secrets.')
    return 0


if __name__ == '__main__':
    sys.exit(check())
