import asyncio
import httpx
import pytest

from backend.app.telemoa import Telemoa, TelemoaUnavailable, normalize_blogs, normalize_stocks


def payload(rows):
    return {'code': '0000', 'data': {'param': {'yyyymmdd': '20261003'}, 'list': rows}}


def test_public_data_conversions():
    stocks, day = normalize_stocks(payload([{'isu_kor_abbrv': '예시 종목', 'isu_srt_cd': '000000', 'channels': '채널 A$!$채널 B', 'cnt': 2}]))
    assert day == '20261003' and stocks[0]['channelCount'] == 2
    assert stocks[0]['channels'] == ['채널 A', '채널 B']
    latest = normalize_blogs(payload([{'blog_id': 'example', 'scrap_id': 1, 'title': '합성 블로그 글', 'cnt': 3}]), 'latest')
    assert latest[0]['url'] == 'https://blog.naver.com/example/1'
    cumulative = normalize_blogs(payload([{'blog_id': 'example', 'nickname': '예시 저자', 'description': 'DO_NOT_COPY_FULL_DESCRIPTION', 'scrap_cnt': 4}]), 'cumulative')
    assert cumulative[0]['title'] == '예시 저자'
    assert cumulative[0]['url'] == 'https://blog.naver.com/example'
    assert 'DO_NOT_COPY' not in str(cumulative)


def test_provider_cache_fixed_paths_and_failure(monkeypatch):
    requests = []
    fail = False
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, url, params):
            requests.append((url, params))
            if fail: raise httpx.ConnectError('synthetic upstream failure')
            return httpx.Response(200, json=payload([]), request=httpx.Request('GET', url))
    monkeypatch.setattr('backend.app.telemoa.httpx.AsyncClient', Client)
    async def exercise():
        nonlocal fail
        provider = Telemoa()
        assert (await provider.get())['blogMode'] == 'latest'
        await provider.get()
        assert len(requests) == 2
        assert all(url.startswith('https://telemoa.com/api/') for url, _ in requests)
        provider.clear()
        fail = True
        with pytest.raises(TelemoaUnavailable): await provider.get()
    asyncio.run(exercise())
