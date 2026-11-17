import secrets
import hashlib
from datetime import datetime, timezone, timedelta
from passlib.context import CryptContext
import pyotp

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def make_session_id() -> str:
    return secrets.token_urlsafe(32)


def make_token() -> str:
    return secrets.token_urlsafe(32)


def make_challenge() -> str:
    return secrets.token_urlsafe(24)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, email: str, issuer: str = "Regal HMS") -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=window)


def make_backup_codes(n: int = 8) -> list[str]:
    return [secrets.token_hex(4).upper() for _ in range(n)]


def hash_backup_code(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utcnow().isoformat().replace("+00:00", "Z")
