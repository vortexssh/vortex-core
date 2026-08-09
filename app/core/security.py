from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext
import pyotp
import secrets

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def hash_secret(raw: str) -> str:
    """Hash API keys / agent secrets (same bcrypt stack)."""
    return pwd_context.hash(raw)


def verify_secret(raw: str, secret_hash: str) -> bool:
    return pwd_context.verify(raw, secret_hash)


def generate_api_key() -> str:
    return f"vxk_{secrets.token_urlsafe(32)}"


def generate_agent_secret() -> str:
    return f"vxa_{secrets.token_urlsafe(32)}"


def generate_plugin_token() -> str:
    """Daemon token for out-of-process plugin installs (vxp_…)."""
    return f"vxp_{secrets.token_urlsafe(32)}"


def create_access_token(
    *,
    subject: UUID,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    settings = get_settings()
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise ValueError("Invalid token") from exc
    if payload.get("type") != "access":
        raise ValueError("Invalid token type")
    return payload


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def build_totp_uri(*, secret: str, email: str) -> str:
    settings = get_settings()
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=settings.app_name)


def verify_totp(secret: str, code: str) -> bool:
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)
