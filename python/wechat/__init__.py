"""微信 iLink 适配器（生产化）。

替代 mock_wechat.py：
- 一次扫码登录 → bot_token 持久化到 data/ilink_token.json
- send_message 调真实 iLink API
- long_poll 接收用户消息
- 解决 context_token 24h 过期：提供 refresh 接口 + 心跳任务

iLink API:
  GET  https://ilinkai.weixin.qq.com/get_bot_qrcode
  POST https://ilinkai.weixin.qq.com/sendmessage
  POST https://ilinkai.weixin.qq.com/getupdates
"""

from python.wechat.ilink_client import (
    ILinkClient,
    ILinkError,
    get_client,
    save_token,
    load_token,
)

__all__ = [
    "ILinkClient",
    "ILinkError",
    "get_client",
    "save_token",
    "load_token",
]
