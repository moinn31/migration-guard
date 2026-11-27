from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import jwt
import pytest
from fastapi import HTTPException

from backend import auth
from backend.config import settings
from backend.models import Role

@pytest.mark.asyncio
async def test_forged_clerk_token_cannot_provision_admin(monkeypatch):
    monkeypatch.setattr(settings, 'clerk_issuer', None)
    monkeypatch.setattr(settings, 'next_public_clerk_publishable_key', None)
    token = jwt.encode({'sub': 'user_attacker', 'iss': 'https://clerk.attacker', 'exp': datetime.now(timezone.utc) + timedelta(hours=1)}, 'attacker-controlled-secret-of-32-bytes', algorithm='HS256')
    db = AsyncMock()
    with pytest.raises(HTTPException) as error:
        await auth.current_user(token, None, db)
    assert error.value.status_code == 401
    db.scalar.assert_not_called()

def test_clerk_verification_checks_signature_expiry_issuer_and_party(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import rsa
    from types import SimpleNamespace
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer = 'https://trusted.clerk.accounts.dev'
    monkeypatch.setattr(settings, 'clerk_issuer', issuer)
    monkeypatch.setattr(settings, 'clerk_audience', 'migrationguard')
    monkeypatch.setattr(settings, 'clerk_authorized_parties', ['https://app.example.com'])
    monkeypatch.setattr(auth, 'clerk_keys', lambda _: SimpleNamespace(get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key())))
    claims = {'sub': 'user_verified', 'iss': issuer, 'aud': 'migrationguard', 'azp': 'https://app.example.com', 'iat': datetime.now(timezone.utc), 'exp': datetime.now(timezone.utc) + timedelta(minutes=5)}
    assert auth.verify_clerk_token(jwt.encode(claims, key, algorithm='RS256'))['sub'] == 'user_verified'
    for change in ({'iss': 'https://attacker'}, {'exp': datetime.now(timezone.utc) - timedelta(seconds=1)}, {'azp': 'https://attacker'}, {'aud': 'other'}):
        with pytest.raises(jwt.InvalidTokenError):
            auth.verify_clerk_token(jwt.encode({**claims, **change}, key, algorithm='RS256'))
    wrong_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(jwt.InvalidTokenError):
        auth.verify_clerk_token(jwt.encode(claims, wrong_key, algorithm='RS256'))

@pytest.mark.asyncio
async def test_verified_clerk_user_gets_developer_role(monkeypatch):
    monkeypatch.setattr(auth, 'verify_clerk_token', lambda _: {'sub': 'user_verified'})
    db = AsyncMock()
    db.scalar.return_value = None
    from unittest.mock import Mock
    db.add = Mock()
    user = await auth.current_user('clerk-token', None, db)
    assert user.role == Role.developer

@pytest.mark.asyncio
async def test_unknown_local_identity_is_not_auto_provisioned():
    db = AsyncMock()
    db.scalar.return_value = None
    token = jwt.encode({'sub': 'unknown', 'exp': datetime.now(timezone.utc) + timedelta(minutes=5)}, settings.jwt_secret, algorithm='HS256')
    with pytest.raises(HTTPException) as error:
        await auth.current_user(token, None, db)
    assert error.value.status_code == 401
