"""安全工具模块 — JWT 编解码、密码哈希"""

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


def create_access_token(data: dict) -> str:
    """创建 access token（默认 2h 过期）。

    JWT payload 包含:
      - sub: 用户 ID（字符串）
      - exp: 过期时间
      - type: "access"
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """创建 refresh token（默认 7d 过期）。

    JWT payload 包含:
      - sub: 用户 ID（字符串）
      - exp: 过期时间
      - type: "refresh"
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """解码并验证 JWT token。

    Returns:
        解码后的 payload 字典。

    Raises:
        JWTError: token 无效或已过期。
    """
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def hash_password(password: str) -> str:
    """使用 bcrypt 哈希密码（cost factor = 12）。"""
    # bcrypt 限制密码长度为 72 字节
    password_bytes = password.encode('utf-8')[:72]
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain: str, hashed: str) -> bool:
    """验证明文密码与哈希值是否匹配。"""
    plain_bytes = plain.encode('utf-8')[:72]
    hashed_bytes = hashed.encode('utf-8')
    return bcrypt.checkpw(plain_bytes, hashed_bytes)
