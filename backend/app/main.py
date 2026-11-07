"""MAQSAT web MVP API. Owner-scoped data access throughout.

This is a tested starter, not a security audit or finished SaaS release.
"""
from pathlib import Path
import os
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from .db import get_db
from .models import User, LoginSession
from .security import (public_user, hash_password, verify_password, current_user, csrf_protected,
                       admin_user, check_origin, guard_login, failed_login, successful_login,
                       attach_session, token_digest, csrf_token, COOKIE_NAME)

app = FastAPI(title='MAQSAT API', version='0.3.0', docs_url=None, redoc_url=None)

@app.middleware('http')
async def security_headers(request: Request, call_next):
    try:
        check_origin(request)
    except HTTPException as exc:
        return JSONResponse({'detail': exc.detail}, status_code=exc.status_code)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    return response

@app.get('/healthz')
def health(db: Session = Depends(get_db)):
    db.execute(text('SELECT 1'))
    return {'status': 'ok'}

class LoginIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=256)

class UserCreate(BaseModel):
    username: str = Field(pattern=r'^[a-z0-9_\-]{3,32}$')
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=10, max_length=256)

class PasswordChange(BaseModel):
    old_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)

@app.post('/api/v1/auth/login')
def login(payload: LoginIn, response: Response, request: Request, db: Session = Depends(get_db)):
    # Never trust forwarded IP headers; an in-memory limiter is a first-line MVP precaution only.
    ip = request.client.host if request.client else 'unknown'
    guard_login(ip)
    username = payload.username.strip().lower()
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(payload.password, user.password_hash):
        failed_login(ip)
        raise HTTPException(401, 'Неверный логин или пароль')
    successful_login(ip)
    csrf = attach_session(response, db, user)
    return {'user': public_user(user), 'csrf': csrf}

@app.get('/api/v1/auth/me')
def me(request: Request, user: User = Depends(current_user)):
    return {'user': public_user(user), 'csrf': csrf_token(request.cookies[COOKIE_NAME])}

@app.post('/api/v1/auth/logout')
def logout(request: Request, response: Response, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME)
    session = db.scalar(select(LoginSession).where(LoginSession.token_hash == token_digest(token)))
    if session:
        db.delete(session); db.commit()
    response.delete_cookie(COOKIE_NAME, path='/', samesite='lax')
    return {'ok': True}

@app.patch('/api/v1/auth/password')
def password_change(payload: PasswordChange, request: Request, response: Response, user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    if not verify_password(payload.old_password, user.password_hash):
        raise HTTPException(400, 'Текущий пароль неверный')
    user.password_hash = hash_password(payload.new_password)
    # Invalidate all OTHER sessions to prevent continued access from old sessions.
    current = token_digest(request.cookies[COOKIE_NAME])
    db.query(LoginSession).filter(LoginSession.user_id == user.id, LoginSession.token_hash != current).delete(synchronize_session=False)
    db.commit()
    return {'ok': True}

@app.get('/api/v1/admin/users')
def admin_list(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.is_admin: raise HTTPException(403, 'Недостаточно прав')
    return [public_user(x) for x in db.scalars(select(User).order_by(User.created_at)).all()]

@app.post('/api/v1/admin/users', status_code=201)
def admin_create(payload: UserCreate, user: User = Depends(admin_user), db: Session = Depends(get_db)):
    username = payload.username.lower()
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(409, 'Логин уже занят')
    if not payload.display_name.strip(): raise HTTPException(422, 'Укажите имя')
    new_user = User(username=username, display_name=payload.display_name.strip(),
                    password_hash=hash_password(payload.password), is_admin=False)
    db.add(new_user)
    db.commit()
    return public_user(new_user)

# Domain routes are deliberately separate from authentication and static serving.
from .routers import planning, calendar, finance, health, overview
for module in (planning, calendar, finance, health, overview):
    app.include_router(module.router)

from fastapi.exceptions import RequestValidationError
@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Do not return submitted passwords or whole request bodies in validation errors.
    return JSONResponse(status_code=422, content={'detail': 'Проверьте заполнение полей',
        'fields': [str(error['loc'][-1]) for error in exc.errors()]})

# For production the Docker image includes the Vite dist directory, served on
# the SAME ORIGIN as the API. This avoids exposing cookies across app domains.
WEB_DIR = Path(os.getenv('WEB_DIST_DIR', str(Path(__file__).resolve().parents[2] / 'web_dist')))
if WEB_DIR.exists():
    assets = WEB_DIR / 'assets'
    if assets.exists(): app.mount('/assets', StaticFiles(directory=str(assets)), name='assets')
    @app.get('/{full_path:path}', include_in_schema=False)
    def spa_fallback(full_path: str):
        # Serve index.html for valid SPA routes, not for non-existing API endpoints.
        if full_path.startswith(('api/', 'healthz')):
            raise HTTPException(404)
        file = (WEB_DIR / full_path).resolve()
        if WEB_DIR.resolve() in file.parents and file.is_file():
            return FileResponse(file)
        return FileResponse(WEB_DIR / 'index.html')
