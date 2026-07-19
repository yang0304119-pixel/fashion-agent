"""JWT访问令牌的签发与校验。"""

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass

from app.core.config import settings


logger = logging.getLogger(__name__)
JWT_ALGORITHM = "HS256"


class TokenError(ValueError):
    """令牌缺失、损坏、过期或声明不合法。"""


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: int
    tenant_id: int
    role: str


def create_access_token(*, user_id: int, tenant_id: int, role: str) -> str:
    """为已通过密码校验的用户签发短期访问令牌。"""
    now = int(time.time())
    expires_at = now + settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    payload = {
        "sub": str(user_id),
        "tenant_id": tenant_id,
        "role": role,
        "iss": settings.JWT_ISSUER,
        "iat": now,
        "exp": expires_at,
    }
    signing_input = (
        f"{_encode_json(header)}.{_encode_json(payload)}"
    )
    signature = hmac.new(
        _get_signing_secret(),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{_b64encode(signature)}"


def decode_access_token(token: str) -> AccessTokenClaims:
    """验证签名、签发方和过期时间，并返回可信身份声明。"""
    try:
        header_part, payload_part, signature_part = token.split(".")
        header = json.loads(_b64decode(header_part))
        payload = json.loads(_b64decode(payload_part))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TokenError("访问令牌格式无效") from error

    if header != {"alg": JWT_ALGORITHM, "typ": "JWT"}:
        raise TokenError("访问令牌算法无效")

    signing_input = f"{header_part}.{payload_part}"
    expected_signature = hmac.new(
        _get_signing_secret(),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    try:
        actual_signature = _b64decode(signature_part)
    except (ValueError, UnicodeDecodeError) as error:
        raise TokenError("访问令牌签名无效") from error

    if not hmac.compare_digest(actual_signature, expected_signature):
        raise TokenError("访问令牌签名无效")

    now = int(time.time())
    try:
        user_id = int(payload["sub"])
        tenant_id = int(payload["tenant_id"])
        role = str(payload["role"])
        expires_at = int(payload["exp"])
        issued_at = int(payload["iat"])
        issuer = str(payload["iss"])
    except (KeyError, TypeError, ValueError) as error:
        raise TokenError("访问令牌声明无效") from error

    if issuer != settings.JWT_ISSUER:
        raise TokenError("访问令牌签发方无效")
    if expires_at <= now:
        raise TokenError("访问令牌已过期")
    if issued_at > now + 60:
        raise TokenError("访问令牌签发时间无效")
    if user_id <= 0 or tenant_id <= 0 or role not in {"customer", "admin"}:
        raise TokenError("访问令牌身份无效")

    return AccessTokenClaims(
        user_id=user_id,
        tenant_id=tenant_id,
        role=role,
    )


def _get_signing_secret() -> bytes:
    configured = settings.JWT_SECRET_KEY.strip()
    if configured:
        if len(configured) < 32:
            raise RuntimeError("JWT_SECRET_KEY 长度必须不少于 32 个字符")
        return configured.encode("utf-8")

    if settings.ENVIRONMENT.lower() == "production":
        raise RuntimeError("生产环境必须配置 JWT_SECRET_KEY")

    secret_path = settings.PROJECT_ROOT / "data" / ".jwt_secret"
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        secret = secret_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        secret = secrets.token_urlsafe(48)
        try:
            with secret_path.open("x", encoding="utf-8") as file:
                file.write(secret)
        except FileExistsError:
            secret = secret_path.read_text(encoding="utf-8").strip()
        try:
            os.chmod(secret_path, 0o600)
        except OSError:
            pass
        logger.warning(
            "JWT_SECRET_KEY 未配置，已生成仅供开发使用的本机密钥: %s",
            secret_path,
        )

    if len(secret) < 32:
        raise RuntimeError("开发JWT密钥文件无效")
    return secret.encode("utf-8")


def _encode_json(value: dict) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _b64encode(raw)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
