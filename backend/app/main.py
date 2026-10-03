import os
import secrets
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .auth import Auth
from .config import Config
from .db import Database
from .feed import Feed
from .telegram import TelegramLimited, TelegramReader, TelegramUnavailable
from .time_utils import today_kst
from .telemoa import Telemoa, TelemoaUnavailable

FRONTEND = Path(__file__).resolve().parents[2] / 'frontend' / 'dist'
ChatId = Annotated[str, Field(pattern=r'^-?[0-9]{1,20}$')]


class LoginBody(BaseModel):
    password: str = Field(min_length=1, max_length=1024, repr=False)


class ChatsBody(BaseModel):
    chatIds: list[ChatId] = Field(max_length=200)


class StartDateBody(BaseModel):
    date: date


class HideBody(BaseModel):
    chatId: ChatId
    messageId: int = Field(gt=0, le=2147483647)


class ThemeBody(BaseModel):
    theme: Literal['light', 'dark']


def create_app(config: Config | None = None, telegram=None):
    os.umask(0o077)
    config = config or Config.from_env()
    db = Database(config.db_path)
    reader = telegram if telegram is not None else TelegramReader(config)
    auth, feed = Auth(config, db), Feed(db, reader)
    telemoa = Telemoa()

    @asynccontextmanager
    async def lifespan(app):
        db.clear_sessions()  # changing APP_PASSWORD or restarting invalidates existing browser logins
        yield
        await reader.close()

    app = FastAPI(title='Telegram Reader', docs_url=None, redoc_url=None, openapi_url=None, root_path=config.base_path, lifespan=lifespan)
    app.state.db, app.state.telegram, app.state.feed = db, reader, feed
    app.state.telemoa = telemoa

    @app.middleware('http')
    async def privacy_headers(request, call_next):
        if request.headers.get('content-length', '').isdigit() and int(request.headers['content-length']) > 65536:
            response = JSONResponse({'detail': '요청이 너무 큽니다.'}, status_code=413)
        else:
            response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Pragma'] = 'no-cache'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse({'detail': '요청 형식을 확인해 주세요.'}, status_code=422)

    @app.exception_handler(TelegramUnavailable)
    async def telegram_error(request, exc):
        return JSONResponse({'detail': 'Telegram 연결을 확인해 주세요. 최초 인증은 Oracle 터미널에서 실행합니다.'}, status_code=503)

    @app.exception_handler(TelegramLimited)
    async def telegram_limited(request, exc):
        return JSONResponse({'detail': 'Telegram 요청 제한으로 잠시 후 다시 시도합니다.', 'retryAfter': exc.seconds}, status_code=429, headers={'Retry-After': str(exc.seconds)})

    async def require_auth(request: Request):
        return auth.require(request)

    secured = [Depends(require_auth)]

    @app.exception_handler(TelemoaUnavailable)
    async def telemoa_error(request, exc):
        return JSONResponse({'detail': 'Telemoa 정보를 불러올 수 없습니다. 원문 사이트를 확인해 주세요.'}, status_code=502)

    @app.get('/api/insights/telemoa', dependencies=secured)
    async def insights(mode: Literal['latest', 'cumulative'] = 'latest'):
        return await telemoa.get(mode)

    @app.post('/api/auth/login')
    async def login(body: LoginBody, request: Request, response: Response):
        token, csrf = auth.login(request, body.password)
        response.set_cookie('reader_session', token, httponly=True, secure=True, samesite='strict', path=config.base_path + '/', max_age=config.session_seconds)
        return {'csrfToken': csrf}

    @app.get('/api/auth/session', dependencies=secured)
    async def web_session(request: Request):
        return {'csrfToken': auth.require(request)['csrf_token']}

    @app.post('/api/auth/logout', dependencies=secured)
    async def logout(request: Request, response: Response):
        db.delete_session(request.cookies.get('reader_session', ''))
        response.delete_cookie('reader_session', path=config.base_path + '/', secure=True, httponly=True, samesite='strict')
        return {'ok': True}

    @app.get('/api/status', dependencies=secured)
    async def status():
        settings = db.settings()
        return {'telegram': await reader.status(), 'selectedCount': len(settings['selectedChatIds']), 'hiddenCount': settings['hiddenCount'], 'dbBytes': db.size(), 'messagePersistence': False, 'timezone': 'Asia/Seoul', 'today': today_kst().isoformat()}

    @app.get('/api/chats', dependencies=secured)
    async def chats():
        dialogs = await reader.dialogs(force=True)
        selected = set(db.settings()['selectedChatIds'])
        ordered = sorted(dialogs.values(), key=lambda c: (c.chat_id not in selected, -c.activity.timestamp(), c.title.casefold()))
        return [c.public(selected) for c in ordered]

    @app.get('/api/settings', dependencies=secured)
    async def settings():
        return {**db.settings(), 'today': today_kst().isoformat()}

    @app.put('/api/settings/chats', dependencies=secured)
    async def set_chats(body: ChatsBody, request: Request):
        ids = list(dict.fromkeys(body.chatIds))
        if ids:
            available = await reader.dialogs()
            if any(cid not in available for cid in ids):
                raise HTTPException(400, '접근 가능한 대화방만 선택할 수 있습니다.')
        auth.require(request)  # account records may have been reset during the upstream await
        db.select_chats(ids)
        return db.settings()

    @app.put('/api/settings/start-date', dependencies=secured)
    async def set_start_date(body: StartDateBody):
        if body.date > today_kst():
            raise HTTPException(400, '시작일은 오늘보다 늦을 수 없습니다.')
        db.set_start_date(body.date.isoformat())
        return db.settings()

    @app.put('/api/settings/theme', dependencies=secured)
    async def set_theme(body: ThemeBody):
        db.set_theme(body.theme)
        return db.settings()

    @app.delete('/api/settings/records', dependencies=secured)
    async def delete_records(response: Response, request: Request):
        async with feed.lock:
            auth.require(request)
            db.delete_records()
            feed.key = secrets.token_bytes(32)
            telemoa.clear()
            reader.chats.clear()
            reader.dialog_time = 0.0
        response.delete_cookie('reader_session', path=config.base_path + '/', secure=True, httponly=True, samesite='strict')
        return {'ok': True, 'telegramSessionPreserved': True}

    @app.get('/api/messages', dependencies=secured)
    async def messages(date: date, order: Literal['asc', 'desc'] = 'desc', chat_id: Annotated[list[ChatId] | None, Query(max_length=200)] = None, cursor: Annotated[str | None, Query(max_length=20000)] = None, limit: Annotated[int, Query(ge=1, le=100)] = 50):
        if date > today_kst():
            raise HTTPException(400, '미래 날짜는 조회할 수 없습니다.')
        return await feed.page(date, order, chat_id, cursor, limit)

    @app.get('/api/media/{chat_id}/{message_id}', dependencies=secured)
    async def media(chat_id: ChatId, message_id: Annotated[int, Field(gt=0, le=2147483647)], disposition: Literal['inline', 'attachment'] = 'inline'):
        if chat_id not in db.settings()['selectedChatIds']:
            raise HTTPException(403, '선택된 대화방의 첨부 파일만 열 수 있습니다.')
        download = await reader.media_stream(chat_id, message_id)
        if not download:
            raise HTTPException(404, '첨부 파일을 찾을 수 없습니다.')
        from urllib.parse import quote
        mode = 'inline' if disposition == 'inline' and download.inline else 'attachment'
        filename = quote(download.filename.replace('/', '_').replace('\\', '_'), safe='')
        return StreamingResponse(download.chunks, media_type=download.content_type, headers={'Content-Disposition': f"{mode}; filename*=UTF-8''{filename}"})

    @app.post('/api/messages/hide', dependencies=secured)
    async def hide(body: HideBody):
        if body.chatId not in db.settings()['selectedChatIds']:
            raise HTTPException(403, '선택된 대화방만 숨길 수 있습니다.')
        db.hide(body.chatId, body.messageId)
        return {**db.settings(), 'today': today_kst().isoformat()}

    @app.get('/api/messages/hidden', dependencies=secured)
    async def hidden(offset: Annotated[int, Query(ge=0)] = 0):
        return {'items': db.hidden_page(offset), 'total': db.settings()['hiddenCount']}

    @app.delete('/api/messages/hide-all', dependencies=secured)
    async def reset_hidden():
        db.reset_hidden()
        return {'ok': True}

    @app.delete('/api/messages/hide/{chat_id}/{message_id}', dependencies=secured)
    async def unhide(chat_id: ChatId, message_id: Annotated[int, Field(gt=0)]):
        db.unhide(chat_id, message_id)
        return {'ok': True}

    if (FRONTEND / 'assets').is_dir():
        app.mount('/assets', StaticFiles(directory=FRONTEND / 'assets'), name='assets')

    @app.get('/')
    async def index():
        if not (FRONTEND / 'index.html').is_file():
            raise HTTPException(503, '먼저 frontend를 build해 주세요.')
        return FileResponse(FRONTEND / 'index.html')

    @app.get('/favicon.svg')
    async def favicon():
        return FileResponse(FRONTEND / 'favicon.svg')

    return app
