import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

from telethon import TelegramClient, errors, utils
from telethon.tl import types

from .time_utils import KST, require_aware


class TelegramUnavailable(Exception):
    pass


class TelegramLimited(Exception):
    def __init__(self, seconds: int):
        self.seconds = max(1, seconds)


@dataclass
class Chat:
    chat_id: str
    title: str
    kind: str
    activity: datetime
    entity: object = None

    def public(self, selected: set[str]):
        return {'chatId': self.chat_id, 'title': self.title, 'type': self.kind, 'selected': self.chat_id in selected}


@dataclass
class Scan:
    messages: list[dict]
    last_id: int
    exhausted: bool
    last_key: tuple | None = None


@dataclass
class MediaDownload:
    label: str
    filename: str
    content_type: str
    inline: bool
    chunks: AsyncIterator[bytes]


def safe_url(value: str) -> str | None:
    from urllib.parse import urlsplit
    try:
        parsed = urlsplit(value)
        return value if parsed.scheme.lower() in ('https', 'http') and parsed.netloc else None
    except ValueError:
        return None


def media_label(message) -> str | None:
    if getattr(message, 'photo', None):
        return '사진'
    if getattr(message, 'video', None):
        return '동영상'
    if getattr(message, 'voice', None):
        return '음성'
    if getattr(message, 'sticker', None):
        return '스티커'
    if getattr(message, 'document', None):
        return '파일'
    if isinstance(getattr(message, 'media', None), types.MessageMediaPoll):
        return '투표'
    if getattr(message, 'media', None) and not isinstance(message.media, types.MessageMediaWebPage):
        return '미디어'
    return None


def attachment_label(message) -> str | None:
    label = media_label(message)
    return label if label and label not in ('투표', '미디어') else None


def serialize_message(message, chat: Chat):
    text = message.message or ''
    sender = getattr(message, 'sender', None)  # only entities already in this response; no extra requests
    sender_name = None
    if sender:
        sender_name = getattr(sender, 'title', None) or ' '.join(filter(None, [getattr(sender, 'first_name', None), getattr(sender, 'last_name', None)])) or None
    links = []
    encoded = text.encode('utf-16-le')
    for entity in message.entities or []:
        url = None
        if isinstance(entity, types.MessageEntityTextUrl):
            url = entity.url
        elif isinstance(entity, types.MessageEntityUrl):
            url = encoded[entity.offset * 2:(entity.offset + entity.length) * 2].decode('utf-16-le', errors='replace')
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
        if url and (valid := safe_url(url)) and valid not in links:
            links.append(valid)
    media = media_label(message)
    attachment = attachment_label(message)
    timestamp = require_aware(message.date).astimezone(KST)
    return {
        'chatId': chat.chat_id, 'chatTitle': chat.title, 'messageId': message.id,
        'sender': sender_name, 'timestamp': timestamp.isoformat(), 'text': text,
        'links': links, 'forwarded': bool(message.fwd_from), 'media': media,
        'attachment': {'label': attachment} if attachment else None,
    }


class TelegramReader:
    """History reads only; interactive account authorization belongs to the CLI."""

    def __init__(self, config):
        self.config = config
        self.client = None
        self.semaphore = asyncio.Semaphore(4)
        self.dialog_lock = asyncio.Lock()
        self.connect_lock = asyncio.Lock()
        self.chats: dict[str, Chat] = {}
        self.dialog_time = 0.0
        self.cooldown_until = 0.0
        logger = logging.getLogger('telegram_reader.transport')
        logger.disabled = True  # third-party exception messages can contain account identifiers
        logger.propagate = False
        logger.setLevel(logging.CRITICAL + 1)
        logger.addHandler(logging.NullHandler())  # child loggers cannot fall through to logging.lastResort
        self.logger = logger

    async def close(self):
        if self.client:
            await self.client.disconnect()

    def check_cooldown(self):
        if time.monotonic() < self.cooldown_until:
            raise TelegramLimited(int(self.cooldown_until - time.monotonic()) + 1)

    async def ready(self):
        self.check_cooldown()
        async with self.connect_lock:
            if not self.config.api_id or not self.config.api_hash or not self.config.session_path.is_file():
                raise TelegramUnavailable()
            if self.client is None:
                mode = self.config.session_path.stat().st_mode & 0o777
                if mode != 0o600 or self.config.session_path.stat().st_uid != os.getuid():
                    raise TelegramUnavailable()
                self.client = TelegramClient(
                    str(self.config.session_path), self.config.api_id, self.config.api_hash,
                    receive_updates=False, flood_sleep_threshold=0, request_retries=1,
                    connection_retries=2, raise_last_call_error=True, base_logger=self.logger,
                )
                self.client.session.save_entities = False
            try:
                if not self.client.is_connected():
                    await asyncio.wait_for(self.client.connect(), timeout=15)
                if not await asyncio.wait_for(self.client.is_user_authorized(), timeout=15):
                    raise TelegramUnavailable()
            except errors.FloodWaitError as exc:
                self.cooldown_until = time.monotonic() + exc.seconds
                raise TelegramLimited(exc.seconds) from None
            except (errors.RPCError, OSError, TimeoutError):
                raise TelegramUnavailable() from None

    async def status(self):
        try:
            await self.ready()
            return 'connected'
        except TelegramLimited:
            return 'limited'
        except TelegramUnavailable:
            return 'setup_required'

    async def dialogs(self, force=False):
        await self.ready()
        async with self.dialog_lock:
            if self.chats and not force and time.monotonic() - self.dialog_time < 30:
                return self.chats
            chats = {}
            try:
                async with self.semaphore:
                    self.check_cooldown()
                    async with asyncio.timeout(60):
                        async for dialog in self.client.iter_dialogs(ignore_migrated=True):
                            kind = 'group' if dialog.is_group else 'channel' if dialog.is_channel else 'private'
                            cid = str(dialog.id)
                            activity = require_aware(dialog.date) if dialog.date else datetime.min.replace(tzinfo=timezone.utc)
                            chats[cid] = Chat(cid, dialog.name or '이름 없음', kind, activity, utils.get_input_peer(dialog.entity))
                self.chats, self.dialog_time = chats, time.monotonic()
                return chats
            except errors.FloodWaitError as exc:
                self.cooldown_until = time.monotonic() + exc.seconds
                raise TelegramLimited(exc.seconds) from None
            except (errors.RPCError, OSError, TimeoutError, ValueError):
                raise TelegramUnavailable() from None

    async def scan(self, chat: Chat, start: datetime, end: datetime, order: str, offset: int, limit: int) -> Scan:
        async with self.semaphore:
            self.check_cooldown()
            ascending = order == 'asc'
            # On subsequent pages the ID alone is the exclusive cursor. Dates are always checked again.
            offset_date = None if offset else start - timedelta(seconds=1) if ascending else end
            result, last, count, exited, last_key = [], offset, 0, False, None
            try:
                async with asyncio.timeout(30):
                    async for message in self.client.iter_messages(
                        chat.entity, limit=limit, offset_id=offset, offset_date=offset_date,
                        reverse=ascending, wait_time=1,
                    ):
                        count += 1
                        last = message.id
                        when = require_aware(message.date)
                        last_key = (when, int(chat.chat_id), message.id)
                        if (ascending and when >= end) or (not ascending and when < start):
                            exited = True
                            break
                        if not start <= when < end or getattr(message, 'action', None):
                            continue
                        result.append(serialize_message(message, chat))
                return Scan(result, last, exited or count < limit, last_key)
            except errors.FloodWaitError as exc:
                self.cooldown_until = time.monotonic() + exc.seconds
                raise TelegramLimited(exc.seconds) from None
            except (errors.RPCError, OSError, TimeoutError, ValueError):
                raise TelegramUnavailable() from None

    async def media_stream(self, chat_id: str, message_id: int) -> MediaDownload | None:
        """Read a Telegram attachment into the HTTP response only; never write a file."""
        chats = await self.dialogs()
        chat = chats.get(chat_id)
        if not chat:
            return None
        try:
            async with self.semaphore:
                self.check_cooldown()
                async with asyncio.timeout(30):
                    message = await self.client.get_messages(chat.entity, ids=message_id)
            label = attachment_label(message) if message else None
            if not label:
                return None
            file = message.file
            content_type = getattr(file, 'mime_type', None) or ('image/jpeg' if label == '사진' else 'application/octet-stream')
            extension = getattr(file, 'ext', None) or ('.jpg' if label == '사진' else '')
            filename = getattr(file, 'name', None) or f'telegram-{chat_id}-{message_id}{extension}'
            inline = content_type == 'application/pdf' or content_type.startswith(('image/', 'video/', 'audio/'))

            async def chunks():
                try:
                    async with self.semaphore:
                        async with asyncio.timeout(300):
                            async for chunk in self.client.iter_download(message.media, request_size=64 * 1024):
                                yield chunk
                except errors.FloodWaitError as exc:
                    self.cooldown_until = time.monotonic() + exc.seconds
                    raise TelegramLimited(exc.seconds) from None
                except (errors.RPCError, OSError, TimeoutError, ValueError):
                    raise TelegramUnavailable() from None

            return MediaDownload(label, filename, content_type, inline, chunks())
        except errors.FloodWaitError as exc:
            self.cooldown_until = time.monotonic() + exc.seconds
            raise TelegramLimited(exc.seconds) from None
        except (errors.RPCError, OSError, TimeoutError, ValueError):
            raise TelegramUnavailable() from None
