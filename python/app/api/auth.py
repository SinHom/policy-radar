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
import json
import logging
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel

from python.app.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])  # 完整路径前缀在 router 自身定好，main.py 不再加 /api

# 内存 token 存储 + 持久化到 data/admin_tokens.json(防止容器重启丢失)
_TOKENS: dict[str, dict] = {}
_TOKENS_LOCK = threading.Lock()
_TOKENS_FILE = Path("/app/data/admin_tokens.json") if Path("/app").exists() else Path("data/admin_tokens.json")


def _load_tokens_from_disk() -> None:
    """启动时加载已持久化的 tokens。"""
    if _TOKENS_FILE.exists():
        try:
            data = json.loads(_TOKENS_FILE.read_text(encoding="utf-8"))
            now = time.time()
            for h, info in data.items():
                if info.get("expires_at", 0) > now:
                    _TOKENS[h] = info
            logger.info("loaded %d admin tokens from disk", len(_TOKENS))
        except Exception as e:
            logger.warning("load tokens from disk failed: %s", e)


def _save_tokens_to_disk() -> None:
    """持久化 tokens 到文件。"""
    try:
        _TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TOKENS_FILE.write_text(
            json.dumps(_TOKENS, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("save tokens to disk failed: %s", e)


# 启动加载
_load_tokens_from_disk()
# TTL：默认 7 天(604800s)。通过环境变量 ADMIN_TOKEN_TTL 覆盖。
_TOKEN_TTL = int(os.environ.get("ADMIN_TOKEN_TTL", str(7 * 24 * 3600)))  # 默认 7 天
COOKIE_NAME = "admin_token"
_MAX_TOKENS_PER_USER = 5  # 同一用户最多 5 个有效 token，防滥用
# 失败计数（按用户名）— 超过阈值要锁定
_FAIL_COUNT: dict[str, int] = {}
_FAIL_LOCKED_UNTIL: dict[str, float] = {}  # {user: ts}
_FAIL_THRESHOLD = 10  # 同一用户失败 10 次 → 锁定 15 分钟
_FAIL_LOCK_WINDOW = 15 * 60  # 15 分钟


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
        _save_tokens_to_disk()
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


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, request: Request, response: Response) -> LoginResponse:
    """登录：验证 user/pass，返回 token。

    同时把 token 设到 HttpOnly Cookie(7 天)—— 前端无需存 localStorage,
    浏览器每次请求自动带上,由 require_admin 解析 Cookie 或 Authorization header。
    """
    settings = get_settings()
    ip = request.client.host if request.client else ""
    # 用 constant-time compare 防时序攻击
    user_ok = hmac.compare_digest(req.username, settings.admin_user)
    pass_ok = hmac.compare_digest(req.password, settings.admin_password)
    if not (user_ok and pass_ok):
        # 记录失败（IP-based 限流在 middleware 层）
        _FAIL_COUNT[req.username] = _FAIL_COUNT.get(req.username, 0) + 1
        # 超阈值 → 锁定
        locked = False
        if _FAIL_COUNT[req.username] >= _FAIL_THRESHOLD:
            _FAIL_LOCKED_UNTIL[req.username] = time.time() + _FAIL_LOCK_WINDOW
            locked = True
            logger.warning("admin login LOCKED: user=%s fail_count=%d lock_until=%s",
                           req.username, _FAIL_COUNT[req.username],
                           _FAIL_LOCKED_UNTIL[req.username])
        else:
            logger.warning("admin login failed: user=%s fail_count=%d",
                           req.username, _FAIL_COUNT[req.username])
        # 写 audit（登录失败）
        from python.models.audit_log import write_audit
        await write_audit(
            req.username, "login_fail", "auth", req.username,
            detail=f"fail_count={_FAIL_COUNT[req.username]} locked={locked}",
            ip=ip, status="failed",
        )
        # 避免用户名枚举，加固定 sleep
        time.sleep(0.5)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # 成功 → 清失败计数 + 解锁
    _FAIL_COUNT.pop(req.username, None)
    _FAIL_LOCKED_UNTIL.pop(req.username, None)
    # 写 audit（登录成功）
    from python.models.audit_log import write_audit
    await write_audit(
        req.username, "login", "auth", req.username,
        detail=f"login success from {ip}", ip=ip, status="success",
    )

    # 限同用户 token 数（防 token 洪水）
    with _TOKENS_LOCK:
        user_tokens = [(k, v) for k, v in _TOKENS.items() if v.get("user") == req.username]
        while len(user_tokens) >= _MAX_TOKENS_PER_USER:
            # 删最早过期的
            oldest = min(user_tokens, key=lambda x: x[1]["expires_at"])
            _TOKENS.pop(oldest[0], None)
            user_tokens = user_tokens[:-1]

        # 生成 token
        token = secrets.token_urlsafe(32)
        expires_at = time.time() + _TOKEN_TTL
        _TOKENS[_hash_token(token)] = {
            "user": req.username,
            "expires_at": expires_at,
        }
        _save_tokens_to_disk()
    # 设 HttpOnly Cookie(浏览器自动管理过期与同源策略)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=_TOKEN_TTL,
        httponly=True,
        secure=False,  # 上线后用 https 必须改 True
        samesite="lax",
        path="/",
    )
    logger.info("admin login success: user=%s ttl=%d cookie=%s",
                req.username, _TOKEN_TTL, COOKIE_NAME)
    return LoginResponse(token=token, expires_in=_TOKEN_TTL, user=req.username)


async def require_admin(
    request: Request,
    authorization: Optional[str] = Header(None),
) -> str:
    """FastAPI dependency:受保护端点用 Depends(require_admin)。

    支持两种鉴权:
    1. HttpOnly Cookie(浏览器自动带)— 用 cookie_name 取
    2. Authorization: Bearer <token>(兼容 CLI/外部调用)
    """
    token: Optional[str] = None
    # 1) Cookie(优先,浏览器场景)
    if COOKIE_NAME in request.cookies:
        token = request.cookies[COOKIE_NAME]
    # 2) Authorization header(API 调用)
    elif authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
    if not token:
        raise HTTPException(status_code=401, detail="Missing auth (cookie or Authorization header)")
    info = _is_valid(token)
    if info is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return info["user"]


@router.post("/logout")
async def logout(request: Request, response: Response, authorization: Optional[str] = Header(None)) -> dict:
    """登出:删除 token + 清除 Cookie。"""
    token: Optional[str] = None
    if COOKIE_NAME in request.cookies:
        token = request.cookies[COOKIE_NAME]
    elif authorization:
        parts = authorization.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
    if token:
        with _TOKENS_LOCK:
            _TOKENS.pop(_hash_token(token), None)
            _save_tokens_to_disk()
    # 清 Cookie
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
async def me(user: str = Depends(require_admin)) -> MeResponse:
    """当前登录用户(用于前端初始化身份)。"""
    return MeResponse(user=user)


@router.get("/verify")
async def verify(user: str = Depends(require_admin)) -> dict:
    """verify endpoint(用于前端 axios 拦截器检查 token 是否还有效)。"""
    return {"ok": True, "user": user}
