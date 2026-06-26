"""管理后台鉴权：简易 token 机制（生产用 JWT）。

设计：
- 登录 /api/auth/login 验证 user/pass，返回随机 token
- token 存内存 dict（重启失效；适合单实例）
- 受保护端点用 require_admin dependency 检查 Authorization: Bearer <token>
- 登出 /api/auth/logout 删除 token
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from python.app.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])  # 路径前缀由 main.py include_router 时统一加 /api

# 内存 token 存储：{token_hash: {"user": str, "expires_at": float}}
_TOKENS: dict[str, dict] = {}
_TOKEN_TTL = 86400  # 24 小时


def _hash_token(token: str) -> str:
    """只存 token 的 hash（不存原值，避免泄露）。"""
    return hashlib.sha256(token.encode()).hexdigest()


def _is_valid(token: str) -> Optional[dict]:
    """检查 token 是否有效且未过期。"""
    h = _hash_token(token)
    info = _TOKENS.get(h)
    if not info:
        return None
    if time.time() > info["expires_at"]:
        _TOKENS.pop(h, None)
        return None
    return info


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    expires_in: int
    user: str


class MeResponse(BaseModel):
    user: str


@router.post("/api/auth/login", response_model=LoginResponse)
async def login(req: LoginRequest) -> LoginResponse:
    """登录：验证 user/pass，返回 token。"""
    settings = get_settings()
    # 用 constant-time compare 防时序攻击
    user_ok = hmac.compare_digest(req.username, settings.admin_user)
    pass_ok = hmac.compare_digest(req.password, settings.admin_password)
    if not (user_ok and pass_ok):
        # 避免用户名枚举，加固定 sleep
        time.sleep(0.5)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # 生成 token
    token = secrets.token_urlsafe(32)
    expires_at = time.time() + _TOKEN_TTL
    _TOKENS[_hash_token(token)] = {
        "user": req.username,
        "expires_at": expires_at,
    }
    logger.info("admin login: user=%s", req.username)
    return LoginResponse(token=token, expires_in=_TOKEN_TTL, user=req.username)


@router.post("/api/auth/logout")
async def logout(authorization: Optional[str] = Header(None)) -> dict:
    """登出：删除 token。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        return {"ok": True}  # 幂等
    token = authorization.split(" ", 1)[1]
    h = _hash_token(token)
    _TOKENS.pop(h, None)
    return {"ok": True}


@router.get("/api/auth/me", response_model=MeResponse)
async def me(user: str = Depends(lambda: None)) -> MeResponse:  # 占位
    raise HTTPException(status_code=501, detail="use /verify instead")


async def require_admin(
    authorization: Optional[str] = Header(None),
) -> str:
    """FastAPI dependency：受保护端点用 Depends(require_admin)。"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    token = parts[1]
    info = _is_valid(token)
    if info is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return info["user"]


@router.get("/api/auth/verify")
async def verify(user: str = Depends(require_admin)) -> dict:
    """verify endpoint（用于前端 axios 拦截器检查 token 是否还有效）。"""
    return {"ok": True, "user": user}
