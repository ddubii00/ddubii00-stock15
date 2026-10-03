import hashlib
import hmac
import secrets
import time
from collections import deque

from fastapi import HTTPException, Request


class Auth:
    def __init__(self, config, db):
        self.config, self.db = config, db
        self.salt = secrets.token_bytes(16)
        self.digest = self._digest(config.app_password)
        self.attempts: dict[str, deque] = {}

    def _digest(self, password: str):
        return hashlib.scrypt(password.encode(), salt=self.salt, n=16384, r=8, p=1)

    def verify_origin(self, request: Request):
        if request.headers.get('origin') != self.config.origin:
            raise HTTPException(403, '허용되지 않은 요청 출처입니다.')

    def login(self, request: Request, password: str):
        self.verify_origin(request)
        ip = request.client.host if request.client else 'unknown'
        now = time.monotonic()
        self.attempts = {key: q for key, q in self.attempts.items() if q and q[-1] > now - 300}
        q = self.attempts.setdefault(ip, deque())
        while q and q[0] <= now - 300:
            q.popleft()
        if len(q) >= 5 or sum(len(v) for v in self.attempts.values()) >= 50:
            raise HTTPException(429, '로그인 요청이 많습니다. 잠시 후 다시 시도해 주세요.', headers={'Retry-After': '300'})
        q.append(now)
        if not hmac.compare_digest(self._digest(password), self.digest):
            raise HTTPException(401, '비밀번호를 확인해 주세요.')
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.db.create_session(token, csrf, self.config.session_seconds)
        return token, csrf

    def require(self, request: Request):
        token = request.cookies.get('reader_session', '')
        session = self.db.session(token) if token else None
        if not session:
            raise HTTPException(401, '로그인이 필요합니다.')
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            self.verify_origin(request)
            if not hmac.compare_digest(request.headers.get('x-csrf-token', ''), session['csrf_token']):
                raise HTTPException(403, '인증 토큰을 확인해 주세요.')
        return session
