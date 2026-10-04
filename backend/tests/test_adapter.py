import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from telethon import errors
from telethon.tl import types

from backend.app.telegram import Chat, TelegramLimited, TelegramReader, serialize_message
from backend.app.time_utils import date_bounds
from datetime import date


def message(mid, when, text='synthetic caption', entities=None):
    media = types.MessageMediaPhoto(photo=types.PhotoEmpty(id=mid))
    return SimpleNamespace(id=mid, date=datetime.fromisoformat(when), message=text, sender=SimpleNamespace(first_name='합성', last_name='작성자'), entities=entities, fwd_from=object(), photo=object(), action=None, media=media)


def test_serialization_kst_caption_forward_and_safe_links():
    chat = Chat('-1001', '합성 방', 'channel', datetime.now(timezone.utc))
    text = '😀 https://telegram.org'
    msg = message(1, '2026-10-02T15:01:00+00:00', text, [types.MessageEntityUrl(offset=3, length=20), types.MessageEntityTextUrl(offset=0, length=2, url='javascript:alert(1)')])
    result = serialize_message(msg, chat)
    assert result['timestamp'] == '2026-10-03T00:01:00+09:00'
    assert result['text'] == text and result['media'] == '사진' and result['forwarded']
    assert result['attachment'] == {'kind': 'photo', 'label': '사진'}
    assert result['sender'] == '합성 작성자'
    assert result['links'] == ['https://telegram.org']


def test_only_photo_pdf_and_video_receive_attachment_buttons():
    chat = Chat('-1001', '합성 방', 'channel', datetime.now(timezone.utc))
    pdf = message(2, '2026-10-02T15:01:00+00:00')
    pdf.photo, pdf.document, pdf.file = None, object(), SimpleNamespace(mime_type='application/pdf')
    pdf.media = types.MessageMediaDocument(document=SimpleNamespace(mime_type='application/pdf'))
    video = message(3, '2026-10-02T15:01:00+00:00')
    video.photo, video.video = None, object()
    video.media = types.MessageMediaDocument(document=object())
    generic = message(4, '2026-10-02T15:01:00+00:00')
    generic.photo, generic.document, generic.file = None, object(), SimpleNamespace(mime_type='application/zip')
    generic.media = types.MessageMediaDocument(document=SimpleNamespace(mime_type='application/zip'))
    assert serialize_message(pdf, chat)['attachment'] == {'kind': 'pdf', 'label': 'PDF'}
    assert serialize_message(video, chat)['attachment'] == {'kind': 'video', 'label': '동영상'}
    assert serialize_message(generic, chat)['attachment'] is None


def test_link_preview_thumbnail_does_not_receive_a_photo_button():
    chat = Chat('-1001', '합성 방', 'channel', datetime.now(timezone.utc))
    preview = message(5, '2026-10-02T15:01:00+00:00', 'https://example.com')
    preview.media = types.MessageMediaWebPage(webpage=object())
    preview.photo = object()  # Telethon exposes webpage thumbnails through Message.photo.
    assert serialize_message(preview, chat)['attachment'] is None


@pytest.mark.parametrize('order', ['asc', 'desc'])
def test_real_adapter_exclusive_offsets_date_bounds_and_floodwait(rig, order):
    reader = TelegramReader(rig[4])
    calls = []
    ascending = order == 'asc'
    all_messages = [message(i, when) for i, when in [(1, '2026-10-02T14:59:59+00:00'), (2, '2026-10-02T15:00:00+00:00'), (3, '2026-10-02T15:01:00+00:00'), (4, '2026-10-03T14:59:00+00:00'), (5, '2026-10-03T15:00:00+00:00')]]
    class Client:
        async def iter_messages(self, entity, **kwargs):
            calls.append(kwargs)
            for msg in sorted(all_messages, key=lambda m: m.id, reverse=not ascending):
                offset = kwargs['offset_id']
                boundary = kwargs['offset_date']
                if offset and (msg.id <= offset if ascending else msg.id >= offset): continue
                if boundary and (msg.date <= boundary if ascending else msg.date >= boundary): continue
                yield msg
    reader.client = Client()
    start, end = date_bounds(date(2026, 10, 3))
    chat = Chat('-1001', '합성 방', 'channel', start, object())
    result = asyncio.run(reader.scan(chat, start, end, order, 0, 10))
    assert {m['messageId'] for m in result.messages} == {2, 3, 4}
    assert calls[0]['reverse'] == ascending
    assert calls[0]['offset_date'].tzinfo is not None
    asyncio.run(reader.scan(chat, start, end, order, 3, 10))
    assert calls[-1]['offset_id'] == 3 and calls[-1]['offset_date'] is None
    class Limited:
        async def iter_messages(self, *args, **kwargs):
            raise errors.FloodWaitError(request=None, capture=9)
            yield
    reader.client = Limited()
    with pytest.raises(TelegramLimited) as info: asyncio.run(reader.scan(chat, start, end, order, 0, 10))
    assert info.value.seconds == 9
    with pytest.raises(TelegramLimited): reader.check_cooldown()
