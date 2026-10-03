import asyncio
import time
from datetime import datetime
from urllib.parse import quote

import httpx

from .time_utils import KST


class TelemoaUnavailable(Exception):
    pass


def rows(payload):
    if not isinstance(payload, dict) or payload.get('code') != '0000':
        raise TelemoaUnavailable()
    data = payload.get('data')
    if not isinstance(data, dict) or not isinstance(data.get('list'), list):
        raise TelemoaUnavailable()
    if any(not isinstance(row, dict) for row in data['list']):
        raise TelemoaUnavailable()
    return data


def normalize_stocks(payload):
    data = rows(payload)
    result = []
    for row in data['list']:
        if row.get('recommend') or not row.get('isu_kor_abbrv'):
            continue
        code = str(row.get('isu_srt_cd', ''))
        channels = [name for name in str(row.get('channels', '')).split('$!$') if name]
        result.append({'rank': len(result) + 1, 'name': str(row['isu_kor_abbrv'])[:100], 'code': code[:20], 'channels': channels[:3], 'channelCount': int(row.get('cnt', len(channels))), 'url': 'https://telemoa.com/stock/' + quote(code, safe='')})
    return result[:6], (data.get('param') or {}).get('yyyymmdd')


def normalize_blogs(payload, mode):
    result = []
    for row in rows(payload)['list']:
        if row.get('recommend') or not row.get('blog_id'):
            continue
        blog_id = quote(str(row['blog_id']), safe='')
        path = blog_id if mode == 'cumulative' else blog_id + '/' + quote(str(row.get('scrap_id', '')), safe='')
        title = row.get('nickname') if mode == 'cumulative' else row.get('title')
        # Titles and counts only; full article content stays at the publisher.
        result.append({'rank': len(result) + 1, 'title': str(title or '블로그')[:250], 'mentions': int(row.get('scrap_cnt' if mode == 'cumulative' else 'cnt', 0)), 'url': 'https://blog.naver.com/' + path})
    return result[:6]


class Telemoa:
    def __init__(self):
        self.cache = {}
        self.lock = asyncio.Lock()

    def clear(self):
        self.cache.clear()

    async def get(self, mode='latest'):
        async with self.lock:
            cached = self.cache.get(mode)
            if cached and time.monotonic() - cached[0] < 60:
                return cached[1]
            try:
                async with httpx.AsyncClient(timeout=10, follow_redirects=False, headers={'User-Agent': 'TelegramReader/1.0 (personal reader)', 'Accept': 'application/json'}) as client:
                    responses = await asyncio.gather(*(
                        client.get('https://telemoa.com/api/' + endpoint, params={'curPage': 1, 'rowPerPage': 6, 'service_type': 'ST'})
                        for endpoint in ('message/popular', 'blog/' + mode)
                    ))
                    for response in responses:
                        response.raise_for_status()
                    stocks, as_of = normalize_stocks(responses[0].json())
                    blogs = normalize_blogs(responses[1].json(), mode)
                result = {'stocks': stocks, 'blogs': blogs, 'blogMode': mode, 'sourceUrl': 'https://telemoa.com/', 'dataDate': as_of, 'fetchedAt': datetime.now(KST).isoformat()}
                self.cache[mode] = (time.monotonic(), result)
                return result
            except (httpx.HTTPError, ValueError, TypeError, KeyError):
                raise TelemoaUnavailable() from None
