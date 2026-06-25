"""SQLAlchemy ORM 模型集合（MVP 阶段使用 3 张表）。

表设计参考 groovy-swinging-rain.md，简化：
- policy_sources: 政策源配置
- policies:      原始政策 + 摘要（合一）
- push_logs:     推送记录

后续期会扩展 matches（匹配结果）、consultations（咨询记录）、companies（企业）等表。
"""

from python.models.base import Base, make_engine, AsyncSessionLocal, get_session
from python.models.policy_source import PolicySource
from python.models.policy import Policy
from python.models.push_log import PushLog

__all__ = [
    "Base",
    "make_engine",
    "AsyncSessionLocal",
    "get_session",
    "PolicySource",
    "Policy",
    "PushLog",
]
