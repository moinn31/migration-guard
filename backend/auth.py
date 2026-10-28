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

password_hash = PasswordHash.recommended(); oauth2 = OAuth2PasswordBearer(tokenUrl='/auth/login', auto_error=False)
def hash_password(value: str) -> str: return password_hash.hash(value)
def verify_password(value: str, hashed: str) -> bool: return password_hash.verify(value, hashed)
def create_token(user: User) -> str:
    return jwt.encode({'sub': user.id, 'role': user.role.value, 'exp': datetime.now(timezone.utc)+timedelta(minutes=settings.jwt_expire_minutes)}, settings.jwt_secret, algorithm='HS256')
async def current_user(token: str | None = Depends(oauth2), query_token: str | None = Query(None, alias='token'), db: AsyncSession = Depends(get_db)) -> User:
    token = token or query_token
    try:
        if not token:
            raise ValueError('missing token')
        payload = jwt.decode(token, settings.jwt_secret, algorithms=['HS256'])
        user_id = payload.get('sub')
        if not isinstance(user_id, str) or not user_id:
            raise ValueError('missing subject')
    except (jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail='Invalid token')
    user=await db.scalar(select(User).where(User.id==user_id))
    if not user: raise HTTPException(status_code=401, detail='User not found')
    return user
def require_roles(*roles: Role):
    async def checker(user: User = Depends(current_user)):
        if user.role not in roles: raise HTTPException(status_code=403, detail='Insufficient role')
        return user
    return checker
