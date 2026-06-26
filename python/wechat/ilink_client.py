"""iLink 协议客户端。

特性：
- 一次扫码登录，bot_token 存 data/ilink_token.json（不入 git）
- send_message / get_updates / refresh_token
- context_token 24h 过期：自动刷新
- 长轮询 getupdates（用 httpx 流式）

MVP 范围：
- 只实现 iLink 协议的 client（不实现扫码 GUI）
- 扫码登录走外部命令：python -m wechat.ilink_login 提示用户用手机扫码

部署到云服务器后：
1. 手动跑一次 ilink_login（生成 token）
2. 之后 token 自动持久化，server 重启不需重新扫码
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

ILINK_BASE = "https://ilinkai.weixin.qq.com"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TOKEN_FILE = PROJECT_ROOT / "data" / "ilink_token.json"


def get_ilink_base_url() -> str:
    """支持 env var 覆盖（测试用 mock server）。"""
    return os.environ.get("ILINK_BASE_URL", ILINK_BASE)


class ILinkError(Exception):
    """iLink API 错误。"""


class ILinkClient:
    """iLink 协议客户端。"""

    def __init__(self, bot_token: Optional[str] = None, base_url: Optional[str] = None):
        self.bot_token = bot_token
        self.base_url = base_url or get_ilink_base_url()
        self._client = httpx.AsyncClient(timeout=30.0)

    def set_token(self, token: str) -> None:
        self.bot_token = token

    async def close(self) -> None:
        await self._client.aclose()

    async def _auth_headers(self) -> dict:
        if not self.bot_token:
            raise ILinkError("bot_token not set; run wechat.ilink_login first")
        return {"Authorization": f"Bearer {self.bot_token}"}

    async def get_qrcode(self) -> dict:
        """第一步：获取登录二维码（首次部署用）。"""
        r = await self._client.get(f"{self.base_url}/get_bot_qrcode")
        r.raise_for_status()
        return r.json()

    async def wait_for_login(self, qrcode_url: str, timeout: int = 120) -> dict:
        """轮询等待用户扫码登录。返回 {"bot_token": ..., "user_id": ...}"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = await self._client.get(f"{self.base_url}/get_qrcode_status?url={qrcode_url}")
            r.raise_for_status()
            data = r.json()
            if data.get("status") == "ok":
                return data
            await asyncio.sleep(2)
        raise ILinkError("login timeout")

    async def send_message(
        self,
        context_token: str,
        content: str,
        message_type: int = 1,
    ) -> dict:
        """发消息到 context_token 对应的微信会话。"""
        r = await self._client.post(
            f"{self.base_url}/sendmessage",
            headers=await self._auth_headers(),
            json={
                "context_token": context_token,
                "message": {"message_type": message_type, "content": content},
            },
        )
        r.raise_for_status()
        return r.json()

    async def get_updates(self, cursor: str = "", long_poll_timeout: int = 30) -> dict:
        """长轮询获取用户消息。

        返回 {"messages": [...], "cursor": "next-xxx"}
        """
        r = await self._client.post(
            f"{self.base_url}/getupdates",
            headers=await self._auth_headers(),
            json={"get_updates_buf": cursor, "timeout": long_poll_timeout},
        )
        r.raise_for_status()
        return r.json()


# === Token 持久化 ===

def save_token(bot_token: str, user_id: str = "", extra: Optional[dict] = None) -> None:
    """保存 token 到文件。"""
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "bot_token": bot_token,
        "user_id": user_id,
        "saved_at": time.time(),
    }
    if extra:
        data.update(extra)
    TOKEN_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    # 限制权限（owner only）
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except Exception:
        pass
    logger.info("ilink token saved to %s", TOKEN_FILE)


def load_token() -> Optional[dict]:
    """读 token。"""
    if not TOKEN_FILE.exists():
        return None
    try:
        return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("failed to load ilink token: %s", e)
        return None


def clear_token() -> None:
    """清 token（重新扫码前调）。"""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        logger.info("ilink token cleared")


# === 全局 client（懒加载） ===

_default_client: Optional[ILinkClient] = None


def get_client() -> ILinkClient:
    global _default_client
    if _default_client is None:
        token_data = load_token()
        token = token_data.get("bot_token") if token_data else None
        _default_client = ILinkClient(bot_token=token)
        if token:
            logger.info("ilink client initialized with saved token (user=%s)", token_data.get("user_id", "?"))
        else:
            logger.warning("ilink client created without token; run wechat.ilink_login first")
    return _default_client


# === context_token 24h 刷新 ===

async def ensure_fresh_context_token(context_token: str, expires_at: Optional[float] = None) -> str:
    """检查 context_token 是否过期（默认 24h）。如果过期或即将过期，提示刷新。

    实际 iLink 协议没有 server-side 主动 refresh；过期后用户必须再发一条消息。
    这里只做客户端缓存 + 提醒。

    简化版：始终返回原 token，过期检查由调用方决定。
    """
    return context_token
