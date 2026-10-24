import os
from datetime import datetime, timedelta, timezone
import jwt
from pwdlib import PasswordHash
from dotenv import load_dotenv

load_dotenv()
password_hash = PasswordHash.recommended()

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")
)

if JWT_ALGORITHM != "HS256":
    raise RuntimeError(
        "Unsupported JWT_ALGORITHM. This application requires HS256."
    )

if not JWT_SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY is missing. Configure it in the backend .env file."
    )

def hash_password(password: str) -> str:
    """Return a secure password hash."""
    return password_hash.hash(password)

def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against its stored hash."""
    return password_hash.verify(password, stored_hash)

def create_access_token(employee_id: int, employee_code: str) -> str:
    """Create a signed JWT for an authenticated employee."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": str(employee_id),
        "employee_code": employee_code,
        "iat": now,
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )

def decode_access_token(token: str) -> dict:
    """Validate a JWT signature and expiration."""
    return jwt.decode(
        token,
        JWT_SECRET_KEY,
        algorithms=[JWT_ALGORITHM],
        options={"require": ["sub", "exp", "iat"]},
    )
