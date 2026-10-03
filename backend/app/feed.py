import asyncio
import base64
import hmac
import json
import secrets
import time
from datetime import date, datetime

from fastapi import HTTPException

from .time_utils import date_bounds


class Feed:
    def __init__(self, db, telegram):
        self.db, self.telegram = db, telegram
        self.key = secrets.token_bytes(32)
        self.lock = asyncio.Lock()  # serialize feed requests across browsers; semaphore still bounds chat reads

    def encode(self, payload):
        raw = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode()
        return base64.urlsafe_b64encode(raw + hmac.digest(self.key, raw, 'sha256')).decode()

    def decode(self, cursor):
        try:
            raw = base64.b64decode(cursor, altchars=b'-_', validate=True)
            body, signature = raw[:-32], raw[-32:]
            if not hmac.compare_digest(signature, hmac.digest(self.key, body, 'sha256')):
                raise ValueError()
            payload = json.loads(body)
            if not isinstance(payload, dict) or payload.get('exp', 0) < time.time():
                raise ValueError()
            return payload
        except (ValueError, TypeError, KeyError):
            raise HTTPException(400, '조회 페이지가 만료되었습니다. 날짜를 다시 조회해 주세요.') from None

    async def page(self, day: date, order: str, chat_id: list[str] | None, cursor: str | None, limit: int):
        async with self.lock:
            settings = self.db.settings()
            if day < date.fromisoformat(settings['historyStartDate']):
                raise HTTPException(400, '대화 조회 시작일보다 이전 날짜는 조회할 수 없습니다.')
            selected = settings['selectedChatIds']
            if chat_id:
                if any(cid not in selected for cid in chat_id):
                    raise HTTPException(403, '선택된 대화방만 조회할 수 있습니다.')
                selected = [cid for cid in selected if cid in chat_id]
            context = {'date': day.isoformat(), 'order': order, 'ids': selected, 'start': settings['historyStartDate']}
            previous = self.decode(cursor) if cursor else None
            if previous and previous.get('context') != context:
                raise HTTPException(409, '다른 기기에서 설정이 변경되었습니다. 다시 조회해 주세요.')
            offsets = previous.get('offsets', {}) if previous else {}
            done = set(previous.get('done', [])) if previous else set()
            if not selected:
                return {'messages': [], 'nextCursor': None, 'unavailableChatIds': []}
            chats = await self.telegram.dialogs()
            unavailable = [cid for cid in selected if cid not in chats]
            active = [cid for cid in selected if cid in chats and cid not in done]
            start, end = date_bounds(day)
            # At most 101 raw messages per chat per request; no whole-history reads.
            tasks = [asyncio.create_task(self.telegram.scan(chats[cid], start, end, order, offsets.get(cid, 0), limit + 1)) for cid in active]
            try:
                scans = await asyncio.gather(*tasks)
            except BaseException:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise
            pairs = [(m['chatId'], m['messageId']) for scan in scans for m in scan.messages]
            hidden = self.db.hidden_pairs(pairs)
            visible_by_chat = {cid: [m for m in scan.messages if (cid, m['messageId']) not in hidden] for cid, scan in zip(active, scans)}
            merged = [m for messages in visible_by_chat.values() for m in messages]
            message_key = lambda m: (datetime.fromisoformat(m['timestamp']), int(m['chatId']), m['messageId'])
            merged.sort(key=message_key, reverse=order == 'desc')
            frontiers = [scan.last_key for scan in scans if not scan.exhausted and scan.last_key is not None]
            if frontiers:
                boundary = max(frontiers) if order == 'desc' else min(frontiers)
                # Hidden-only batches must advance before older/newer items in other chats can be emitted.
                merged = [m for m in merged if message_key(m) >= boundary] if order == 'desc' else [m for m in merged if message_key(m) <= boundary]
            emitted = merged[:limit]
            used = {(m['chatId'], m['messageId']) for m in emitted}
            for cid, scan in zip(active, scans):
                visible = visible_by_chat[cid]
                consumed = [m for m in visible if (cid, m['messageId']) in used]
                if len(consumed) == len(visible):
                    offsets[cid] = scan.last_id
                    if scan.exhausted:
                        done.add(cid)
                elif consumed:
                    offsets[cid] = consumed[-1]['messageId']
            done.update(unavailable)
            more = any(cid not in done for cid in selected)
            # A hidden-only page advances scan cursors. The UI keeps a usable More button.
            next_cursor = self.encode({'context': context, 'offsets': offsets, 'done': sorted(done), 'exp': int(time.time()) + 3600}) if more else None
            # Do not return data from an outdated selection changed while Telegram was being queried.
            current = self.db.settings()
            if current['selectedChatIds'] != settings['selectedChatIds'] or current['historyStartDate'] != settings['historyStartDate']:
                raise HTTPException(409, '다른 기기에서 설정이 변경되었습니다. 다시 조회해 주세요.')
            hidden_now = self.db.hidden_pairs([(m['chatId'], m['messageId']) for m in emitted])
            return {'messages': [m for m in emitted if (m['chatId'], m['messageId']) not in hidden_now], 'nextCursor': next_cursor, 'unavailableChatIds': unavailable}
