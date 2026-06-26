"""安全中间件：安全头 + 限流 + 请求大小限制。

部署到生产前必须启用（main.py 会自动包含）。
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Deque

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
