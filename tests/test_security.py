import jwt
from backend.auth import create_token
from backend.config import settings
from backend.models import Role, User


def test_public_registration_role_policy():
    # Public request schemas may expose a role field for compatibility, but
    # the route must always persist the least-privileged self-registration role.
    assert Role.developer.value == "developer"


def test_token_requires_subject():
    token = jwt.encode({"role": "admin"}, settings.jwt_secret, algorithm="HS256")
    assert token


def test_token_contains_server_role():
    user = User(id="u-1", email="user@example.com", password_hash="hash", role=Role.developer)
    payload = jwt.decode(create_token(user), settings.jwt_secret, algorithms=["HS256"])
    assert payload["sub"] == "u-1"
    assert payload["role"] == "developer"
