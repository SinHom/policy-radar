"""iLink 扫码登录（一次性）。

用法：
    python -m wechat.ilink_login
    → 显示二维码 URL
    → 用手机微信扫码
    → 等待登录成功，token 自动保存到 data/ilink_token.json
"""

from __future__ import annotations

import asyncio
import logging
import sys

from python.wechat.ilink_client import ILinkClient, save_token

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ilink_login")


async def main() -> int:
    client = ILinkClient()
    try:
        # 1. 拿二维码
        logger.info("Fetching login QR code...")
        qr = await client.get_qrcode()
        qrcode_url = qr.get("qrcode_url", "")
        bot_token = qr.get("bot_token", "")
        print()
        print("=" * 60)
        print("请用手机微信扫描以下二维码完成登录：")
        print()
        print(f"  {qrcode_url}")
        print()
        print("=" * 60)
        print("等待扫码中（超时 120s）...")

        # 2. 等登录
        result = await client.wait_for_login(qrcode_url, timeout=120)
        token = result.get("bot_token") or bot_token
        user_id = result.get("user_id", "")
        if not token:
            logger.error("login response missing bot_token: %s", result)
            return 1

        # 3. 保存
        save_token(token, user_id)
        print()
        print("✅ 登录成功！")
        print(f"  user_id: {user_id}")
        print(f"  token 保存到: data/ilink_token.json")
        print()
        print("现在可以启 MCP Server，会自动用这个 token 推送：")
        print("  python -m mcp_server --sse --port 3001")
        return 0
    finally:
        await client.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
