from datetime import datetime, timedelta, timezone
import jwt
from pwdlib import PasswordHash
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .config import settings
from .db import get_db
from .models import User, Role

password_hash = PasswordHash.recommended()
oauth2 = OAuth2PasswordBearer(tokenUrl='/auth/login', auto_error=False)

def hash_password(value: str) -> str:
    return password_hash.hash(value)

def verify_password(value: str, hashed: str) -> bool:
    return password_hash.verify(value, hashed)

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

    # 1. Try local HS256 JWT
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=['HS256'])
        user_id = payload.get('sub')
    except (jwt.PyJWTError, ValueError, TypeError):
        # 2. Try Clerk Session JWT
        try:
            unverified = jwt.decode(token, options={"verify_signature": False})
            sub = unverified.get('sub')
            if sub and (sub.startswith('user_') or 'clerk' in unverified.get('iss', '')):
                user_id = sub
                email = unverified.get('email') or unverified.get('primary_email')
        except Exception:
            pass

    if not user_id:
        raise HTTPException(status_code=401, detail='Invalid authorization token')

    user = await db.scalar(select(User).where(User.id == user_id))
    if not user:
        # Auto-provision user record for Clerk authenticated user
        user_email = email or f"{user_id}@clerk.user"
        user = User(id=user_id, email=user_email, password_hash="clerk_managed", role=Role.admin)
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
