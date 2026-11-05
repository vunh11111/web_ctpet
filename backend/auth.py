"""One demo account, hashed password, expiring signed bearer sessions."""
from collections import defaultdict, deque
import hashlib
import secrets
import threading
import time
import re
from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel, Field
from .config import get_settings

settings = get_settings()
attempts = defaultdict(deque)
lock = threading.Lock()


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


def password_hash(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600000).hex()
    return f"pbkdf2_sha256$600000${salt}${digest}"


def password_matches(password, encoded):
    try:
        name, rounds, salt, expected = encoded.split("$")
        if name != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds)).hex()
        return secrets.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def serializer():
    return URLSafeTimedSerializer(settings.auth_signing_secret.get_secret_value(), salt="pet-demo-session-v1")


def validate_configuration():
    if settings.auth_enabled and (len(settings.auth_signing_secret.get_secret_value()) < 32 or (settings.auth_mode == "password" and not settings.auth_password_hash.get_secret_value().startswith("pbkdf2_sha256$"))):
        raise RuntimeError("Run scripts/setup-auth.py before enabling authenticated API")


def authenticate(request: Request):
    if not settings.auth_enabled:
        return "local-demo"
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(401, "Vui lòng đăng nhập để tiếp tục.")
    try:
        data = serializer().loads(header[7:], max_age=settings.auth_ttl_seconds)
        if settings.auth_mode == "guest" and data.get("role") == "guest" and re.fullmatch(r"guest:[a-f0-9]{32}", data.get("sub", "")):
            return data["sub"]
        if data.get("sub") != settings.auth_username:
            raise BadSignature("Unknown account")
        return data["sub"]
    except (BadSignature, SignatureExpired, TypeError):
        raise HTTPException(401, "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.")


def guest_session(request: Request):
    if settings.auth_mode != "guest":
        raise HTTPException(404, "Chế độ truy cập trực tiếp chưa được bật.")
    principal = "guest:" + secrets.token_hex(16)
    header = request.headers.get("authorization", "")
    if header.startswith("Bearer "):
        try:
            # Renew the same browser identity for up to 30 days of inactivity.
            previous = serializer().loads(header[7:], max_age=30 * 86400)
            if previous.get("role") == "guest" and re.fullmatch(r"guest:[a-f0-9]{32}", previous.get("sub", "")):
                principal = previous["sub"]
        except (BadSignature, SignatureExpired, TypeError):
            pass
    return {"access_token": serializer().dumps({"sub": principal, "role": "guest"}), "expires_in": settings.auth_ttl_seconds}


def can_access(owner, principal):
    return not settings.auth_enabled or principal == settings.auth_username or (owner is not None and owner == principal)


def login(request: Request, payload: Login):
    now = time.monotonic()
    key = request.client.host if request.client else "unknown"
    with lock:
        # Bound the rate-limit state; it contains no passwords or tokens.
        for old in list(attempts):
            if not attempts[old] or attempts[old][-1] < now - 60:
                del attempts[old]
        bucket = attempts[key]
        while bucket and bucket[0] < now - 60:
            bucket.popleft()
        if len(bucket) >= 10:
            raise HTTPException(429, "Đăng nhập quá nhiều lần. Vui lòng đợi một phút.")
        bucket.append(now)
    valid = password_matches(payload.password, settings.auth_password_hash.get_secret_value())
    if not secrets.compare_digest(payload.username, settings.auth_username) or not valid:
        raise HTTPException(401, "Tên đăng nhập hoặc mật khẩu chưa đúng.")
    return {"access_token": serializer().dumps({"sub": settings.auth_username}), "token_type": "bearer", "expires_in": settings.auth_ttl_seconds}
