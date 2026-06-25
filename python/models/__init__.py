"""SQLAlchemy ORM 模型集合。

表设计：
- policy_sources:    政策源配置
- policies:          原始政策 + 摘要（合一）
- push_logs:         推送记录（mock 微信推送用）
- companies:         企业档案（MCP 化后新增）
- subscriptions:     订阅规则（每企业一条，含推送设置）
- matches:           匹配结果（subscription × policy 命中）
- push_dead_letters: 推送死信（重试失败后入队，scheduler 周期重发）
"""

from python.models.base import Base, make_engine, AsyncSessionLocal, get_session
from python.models.policy_source import PolicySource
from python.models.policy import Policy
from python.models.push_log import PushLog
from python.models.company import Company
from python.models.subscription import Subscription
from python.models.match import Match
from python.models.push_dead_letter import PushDeadLetter

__all__ = [
    "Base",
    "make_engine",
    "AsyncSessionLocal",
    "get_session",
    "PolicySource",
    "Policy",
    "PushLog",
    "Company",
    "Subscription",
    "Match",
    "PushDeadLetter",
]
