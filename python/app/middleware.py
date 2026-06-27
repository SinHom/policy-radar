"""安全中间件：安全头 + 限流 + 请求大小限制 + 自动审计。

部署到生产前必须启用（main.py 会自动包含）。
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict, deque
from typing import Deque, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


# ============================================================
# 安全头
# ============================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """加标准安全响应头。"""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # 浏览器侧的 XSS / MIME 嗅探 / 点击劫持防护
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        # HTTPS 强制
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


# ============================================================
# 请求大小限制
# ============================================================

class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """限制请求 body 大小（防 OOM / 慢攻击）。"""

    def __init__(self, app, max_bytes: int = 1 * 1024 * 1024):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > self.max_bytes:
            return JSONResponse(
                status_code=413,
                content={"detail": f"request body too large (>{self.max_bytes // 1024}KB)"},
            )
        return await call_next(request)


# ============================================================
# 简易内存 rate limit（per IP）
# ============================================================

class RateLimitMiddleware(BaseHTTPMiddleware):
    """滑动窗口限流。

    配置：
    - /api/auth/login: 5/min/IP
    - 其他: 60/min/IP（写）/ 300/min/IP（读）

    生产建议换成 Redis（共享状态 + 跨实例）。
    """

    # { ip+key: deque[timestamps] }
    _buckets: dict[str, Deque[float]] = defaultdict(deque)

    # 端点特殊规则
    RULES = {
        "/api/auth/login": (5, 60),     # 5 次/60秒
        "/api/auth/logout": (10, 60),
    }
    DEFAULT_WRITE_LIMIT = (60, 60)
    DEFAULT_READ_LIMIT = (300, 60)

    async def dispatch(self, request: Request, call_next):
        ip = request.client.host if request.client else "unknown"
        path = request.url.path
        method = request.method.upper()

        # 选规则
        if path in self.RULES:
            limit, window = self.RULES[path]
        elif method in ("POST", "PUT", "PATCH", "DELETE"):
            limit, window = self.DEFAULT_WRITE_LIMIT
        else:
            limit, window = self.DEFAULT_READ_LIMIT

        # 滑动窗口
        key = f"{ip}:{path}"
        now = time.time()
        bucket = self._buckets[key]
        # 清过期
        while bucket and bucket[0] < now - window:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = int(window - (now - bucket[0])) + 1
            return JSONResponse(
                status_code=429,
                content={"detail": f"rate limit exceeded ({limit}/{window}s)"},
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)

        # 清理空 bucket（避免内存泄漏）
        if len(bucket) == 0:
            self._buckets.pop(key, None)

        return await call_next(request)


# ============================================================
# 全局异常处理（防信息泄露）
# ============================================================

class SafeErrorMiddleware(BaseHTTPMiddleware):
    """5xx 错误只返通用消息，详细进日志。"""

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as e:
            logger.exception("unhandled error on %s %s: %s",
                             request.method, request.url.path, e)
            return JSONResponse(
                status_code=500,
                content={"detail": "internal server error"},
            )


# ============================================================
# 自动审计中间件
# ============================================================

def _extract_token_user(authorization: Optional[str]) -> str:
    """从 Authorization header 提取 admin username（失败返 anonymous）。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        return "anonymous"
    try:
        token = authorization.split(" ", 1)[1]
        from python.app.api.auth import _TOKENS, _hash_token
        info = _TOKENS.get(_hash_token(token))
        if info:
            return info.get("user", "anonymous")
    except Exception:
        pass
    return "anonymous"


def _extract_target_id(path: str) -> str:
    """从 URL path 提取资源 ID（最后一段数字）。"""
    parts = [p for p in path.split("/") if p]
    # 例如 /api/subscriptions/123 → "123"
    if len(parts) >= 2 and parts[-1].isdigit():
        return parts[-1]
    return ""


def _path_to_target_type(path: str) -> str:
    """从 path 提取资源类型。"""
    if "auth" in path:
        return "auth"
    if "subscriptions" in path:
        return "subscription"
    if "companies" in path:
        return "company"
    if "policies" in path:
        return "policy"
    if "sources" in path:
        return "source"
    if "llm" in path or "config" in path:
        return "llm_config"
    if "crawl" in path:
        return "crawler"
    if "push-logs" in path:
        return "push_log"
    return "other"


class AuditMiddleware(BaseHTTPMiddleware):
    """自动审计中间件：所有 /api/* 写操作（成功 + 部分失败）写 audit_log。

    自动捕获：actor（从 Bearer token 解析）/ action（method）/ target_type / target_id / ip / ua。
    body 大小限制内会截取（防过大）。
    """

    # 排除不需要审计的路径（高频轮询/日志读）
    SKIP_PATHS = {
        "/api/auth/verify",  # 心跳
        "/api/audit/logs",    # 读 audit 自己
        "/api/audit/stats",
        "/health",
    }

    async def dispatch(self, request: Request, call_next):
        method = request.method.upper()
        path = request.url.path

        # 只审计 /api/* 的写操作
        if (
            not path.startswith("/api/")
            or method not in ("POST", "PUT", "PATCH", "DELETE")
            or path in self.SKIP_PATHS
        ):
            return await call_next(request)

        response = await call_next(request)

        # 只记成功 + 业务失败（4xx），不记 5xx（已记日志）
        if response.status_code >= 500:
            return response

        # 提取上下文
        actor = _extract_token_user(request.headers.get("authorization"))
        ip = request.client.host if request.client else ""
        ua = request.headers.get("user-agent", "")
        target_type = _path_to_target_type(path)
        target_id = _extract_target_id(path)
        status = "success" if 200 <= response.status_code < 300 else "failed"
        # 详细：method + path + status
        detail = f"{method} {path} → {response.status_code}"

        # 异步写 audit（不阻塞响应）
        import asyncio
        asyncio.create_task(self._write(actor, method, target_type, target_id, detail, ip, ua, status))

        return response

    @staticmethod
    async def _write(actor, action, target_type, target_id, detail, ip, ua, status):
        try:
            from python.models.audit_log import write_audit
            await write_audit(actor, action.lower(), target_type, target_id, detail, ip, ua, status)
        except Exception as e:
            logger.warning("audit write failed: %s", e)

