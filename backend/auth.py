from datetime import datetime, timedelta, timezone
import asyncio
import base64
from functools import lru_cache
import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .config import settings
from .db import get_db
from .models import User, Role

password_hash = PasswordHash.recommended()
oauth2 = OAuth2PasswordBearer(tokenUrl='/auth/login', auto_error=False)

@lru_cache(maxsize=4)
def clerk_keys(issuer: str):
    return jwt.PyJWKClient(issuer.rstrip('/') + '/.well-known/jwks.json')

def verify_clerk_token(token: str) -> dict:
    issuer = settings.clerk_issuer
    if not issuer and settings.next_public_clerk_publishable_key:
        # This key comes from trusted server configuration, never from JWT claims.
        encoded = settings.next_public_clerk_publishable_key.split('_', 2)[-1]
        try:
            domain = base64.b64decode(encoded + '=' * (-len(encoded) % 4)).decode().rstrip('$')
            import re
            if re.fullmatch(r'[A-Za-z0-9.-]+', domain):
                issuer = 'https://' + domain
        except (ValueError, UnicodeError):
            pass
    if not issuer or not issuer.startswith('https://'):
        raise jwt.InvalidTokenError('Clerk issuer is not configured')
    key = clerk_keys(issuer).get_signing_key_from_jwt(token)
    payload = jwt.decode(token, key.key, algorithms=['RS256'], issuer=issuer,
        audience=settings.clerk_audience,
        options={'require': ['sub', 'exp', 'iat', 'iss'], 'verify_aud': bool(settings.clerk_audience)})
    if settings.clerk_authorized_parties and payload.get('azp') not in settings.clerk_authorized_parties:
        raise jwt.InvalidTokenError('Unauthorized token party')
    if not str(payload['sub']).startswith('user_'):
        raise jwt.InvalidTokenError('Invalid Clerk subject')
    return payload

def hash_password(value: str) -> str:
    return password_hash.hash(value)

def verify_password(value: str, hashed: str) -> bool:
    try:
        return password_hash.verify(value, hashed)
    except (ValueError, UnknownHashError):
        return False

def create_token(user: User) -> str:
    return jwt.encode(
        {'sub': user.id, 'role': user.role.value, 'exp': datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)},
        settings.jwt_secret,
        algorithm='HS256',
    )

async def current_user(
    token: str | None = Depends(oauth2),
    query_token: str | None = Query(None, alias='token'),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = token or query_token
    if not token:
        raise HTTPException(status_code=401, detail='Missing authorization token')

    user_id: str | None = None
    email: str | None = None
    clerk_identity = False

    # 1. Try local HS256 JWT
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=['HS256'], options={'require': ['sub', 'exp']})
        user_id = payload.get('sub')
    except (jwt.PyJWTError, ValueError, TypeError):
        # 2. Try Clerk Session JWT
        try:
            payload = await asyncio.to_thread(verify_clerk_token, token)
            user_id = payload['sub']
            email = payload.get('email') or payload.get('primary_email')
            clerk_identity = True
        except Exception:
            pass

    if not user_id:
        raise HTTPException(status_code=401, detail='Invalid authorization token')

    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        if not clerk_identity:
            raise HTTPException(status_code=401, detail='Unknown user')
        # Auto-provision user record for Clerk authenticated user
        user_email = email or f"{user_id}@clerk.user"
        user = User(id=user_id, email=user_email, password_hash="clerk_managed", role=Role.developer)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return user

def require_roles(*roles: Role):
    async def checker(user: User = Depends(current_user)):
        if user.role not in roles:
            raise HTTPException(status_code=403, detail='Insufficient role')
        return user
    return checker
