#!/usr/bin/env python3
"""Run interactively on Oracle, as telegram-reader, while the web service is stopped."""
import argparse
import asyncio
import getpass
import logging
import os
import sys
from pathlib import Path

from dotenv import dotenv_values
from telethon import TelegramClient, errors


async def login():
    parser = argparse.ArgumentParser(description='Telegram 터미널 최초 인증')
    parser.add_argument('--env-file', type=Path, help='현재 사용자 또는 root 소유의 권한 600 환경변수 파일')
    args = parser.parse_args()
    os.umask(0o077)
    if not sys.stdin.isatty():
        raise RuntimeError('대화형 터미널에서 실행해 주세요.')
    if args.env_file:
        info = args.env_file.stat()
        if info.st_mode & 0o777 != 0o600 or info.st_uid not in (0, os.getuid()):
            raise RuntimeError('환경변수 파일의 소유자와 권한 600을 확인해 주세요.')
        for key, value in dotenv_values(args.env_file).items():
            if value is not None:
                os.environ[key] = value
    required = ('TELEGRAM_API_ID', 'TELEGRAM_API_HASH', 'TELEGRAM_PHONE')
    if any(not os.environ.get(name) for name in required):
        raise RuntimeError('필수 Telegram 환경변수를 Oracle에서 입력해 주세요.')
    path = Path(os.getenv('TELEGRAM_SESSION_PATH') or '/var/lib/telegram-reader/session/telegram.session')
    if not path.is_absolute() or path.suffix != '.session':
        raise RuntimeError('TELEGRAM_SESSION_PATH는 절대 경로의 .session 파일이어야 합니다.')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists() and path.stat().st_uid != os.getuid():
        raise RuntimeError('세션 파일 소유자와 실행 사용자가 같아야 합니다.')
    logger = logging.getLogger('telegram_reader.login')
    logger.disabled = True
    logger.propagate = False
    logger.setLevel(logging.CRITICAL + 1)
    logger.addHandler(logging.NullHandler())
    client = TelegramClient(str(path), int(os.environ['TELEGRAM_API_ID']), os.environ['TELEGRAM_API_HASH'], receive_updates=False, flood_sleep_threshold=0, request_retries=1, connection_retries=2, base_logger=logger)
    client.session.save_entities = False
    try:
        await client.connect()
        if not await client.is_user_authorized():
            phone = os.environ['TELEGRAM_PHONE']
            sent = await client.send_code_request(phone)
            code = getpass.getpass('Telegram 인증코드 (화면에 표시되지 않음): ')
            try:
                await client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
            except errors.SessionPasswordNeededError:
                password = getpass.getpass('Telegram 2FA password: ')
                try:
                    await client.sign_in(password=password)
                finally:
                    password = None
            finally:
                code = None
        if not await client.is_user_authorized():
            raise RuntimeError('Telegram 인증을 완료하지 못했습니다.')
        print('Telegram 인증이 완료되었습니다. 계정 정보는 출력하지 않습니다.')
    finally:
        await client.disconnect()
        if path.exists():
            path.chmod(0o600)


if __name__ == '__main__':
    try:
        asyncio.run(login())
    except KeyboardInterrupt:
        print('인증을 중단했습니다.', file=sys.stderr)
        sys.exit(1)
    except Exception:
        # Never print third-party exception text, phone, codes, hash, or passwords.
        print('인증 실패: 환경변수, 인증코드, 2FA와 파일 권한을 확인한 뒤 다시 실행해 주세요.', file=sys.stderr)
        sys.exit(1)
