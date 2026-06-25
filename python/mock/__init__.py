"""Mock 微信 iLink 服务：模拟 iLink 协议端点，把推送内容 print + 落盘。"""

from python.mock.mock_wechat import app, start_server, PENDING_MESSAGES

__all__ = ["app", "start_server", "PENDING_MESSAGES"]
