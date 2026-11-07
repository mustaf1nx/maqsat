"""Session-cookie auth and per-request CSRF checks."""
import hashlib
import hmac
import os
import re
import secrets
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from .db import get_db
from .models import LoginSession, User

ENV = os.getenv('APP_ENV', 'development')
PRODUCTION = ENV == 'production'
SECRET = os.getenv('APP_SECRET', '')
if PRODUCTION and len(SECRET) < 32:
    raise RuntimeError('APP_SECRET must contain >=32 random characters in production')
if not SECRET:
    SECRET = 'dev-only-unsafe-secret-not-for-deployment-change-me'
APP_ORIGIN = os.getenv('APP_ORIGIN', '').rstrip('/')
if PRODUCTION and (not APP_ORIGIN.startswith('https://')):
    raise RuntimeError('APP_ORIGIN must be an HTTPS URL in production')
COOKIE_NAME = 'maqsat_session'
HASHER = PasswordHasher(time_cost=2, memory_cost=32768, parallelism=2)
USERNAME_RE = re.compile(r'^[a-z0-9_\-]{3,32}$')
# In-memory limiter is intended for a single-instance MVP; add Redis at scale.
FAILED_LOGINS = defaultdict(deque)

def verify_password(password: str, stored: str) -> bool:
    try:
        return HASHER.verify(stored, password)
    except (VerifyMismatchError, VerificationError):
        return False

def hash_password(password: str) -> str:
    if not 10 <= len(password) <= 256:
        raise HTTPException(422, 'Пароль должен содержать от 10 до 256 символов')
    return HASHER.hash(password)

def public_user(user: User) -> dict:
    return {'id': user.id, 'username': user.username, 'display_name': user.display_name, 'is_admin': user.is_admin, 'timezone': user.timezone}

def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def csrf_token(raw_token: str) -> str:
    return hmac.new(SECRET.encode(), (raw_token + ':csrf').encode(), hashlib.sha256).hexdigest()

def attach_session(response: Response, db: Session, user: User) -> str:
    token = secrets.token_urlsafe(48)
    db.add(LoginSession(user_id=user.id, token_hash=token_digest(token), expires_at=datetime.now(timezone.utc) + timedelta(days=7)))
    db.commit()
    response.set_cookie(COOKIE_NAME, token, httponly=True, secure=PRODUCTION, samesite='lax', max_age=604800, path='/')
    return csrf_token(token)

def _get_token(request: Request) -> str:
    token = request.cookies.get(COOKIE_NAME)
    if not token or len(token) > 256:
        raise HTTPException(401, 'Нужно войти в аккаунт')
    return token

def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _get_token(request)
    session = db.scalar(select(LoginSession).where(LoginSession.token_hash == token_digest(token)))
    if not session:
        raise HTTPException(401, 'Сессия недействительна')
    expiry = session.expires_at.replace(tzinfo=timezone.utc) if session.expires_at.tzinfo is None else session.expires_at
    if expiry <= datetime.now(timezone.utc):
        db.delete(session); db.commit()
        raise HTTPException(401, 'Сессия истекла')
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(401, 'Пользователь не найден')
    return user

def csrf_protected(request: Request, user: User = Depends(current_user)) -> User:
    token = _get_token(request)
    supplied = request.headers.get('X-CSRF-Token', '')
    if not hmac.compare_digest(supplied, csrf_token(token)):
        raise HTTPException(403, 'Проверка безопасности запроса не пройдена')
    return user

def admin_user(user: User = Depends(csrf_protected)) -> User:
    if not user.is_admin:
        raise HTTPException(403, 'Недостаточно прав')
    return user

def check_origin(request: Request):
    """Extra check against cross-origin cookie requests (including login CSRF)."""
    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        origin = request.headers.get('origin')
        if origin:
            host = APP_ORIGIN or f'{request.url.scheme}://{request.headers.get("host", "")}'
            allowed = {host}
            if not PRODUCTION:
                allowed.update({'http://localhost:5173', 'http://127.0.0.1:5173', 'http://localhost:8000', 'http://127.0.0.1:8000'})
            if origin not in allowed:
                raise HTTPException(403, 'Запрос с другого источника запрещён')
        if request.headers.get('sec-fetch-site') == 'cross-site':
            raise HTTPException(403, 'Межсайтовый запрос запрещён')

def guard_login(ip: str):
    now = datetime.now(timezone.utc).timestamp()
    failures = FAILED_LOGINS[ip]
    while failures and failures[0] < now - 600:
        failures.popleft()
    if len(failures) >= 6:
        raise HTTPException(429, 'Слишком много попыток. Попробуйте позже.')

def failed_login(ip: str):
    FAILED_LOGINS[ip].append(datetime.now(timezone.utc).timestamp())

def successful_login(ip: str):
    FAILED_LOGINS.pop(ip, None)
