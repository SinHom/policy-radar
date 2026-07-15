"""MiniMax-VL-01 视觉模型客户端。

MiniMax-VL-01 走 Anthropic Messages API（不是 OpenAI 兼容端点）：
- endpoint: https://api.minimaxi.com/anthropic/v1/messages
- 鉴权：Authorization: Bearer {MINIMAX_API_KEY} + anthropic-version: 2023-06-01
- 请求体：Anthropic messages.content 数组（type=text + type=image+source.base64）

用途：spider 抓到正文配图后，下载 -> base64 -> 调 VL 生成中文 caption，
再把 caption 作为 markdown ``![caption](url)`` 的 alt text，让 WeKnora 的
向量索引能命中图片内容（绕过 WeKnora 内部 VLM 链路对 weknoracloud 的依赖）。

失败降级：API 不可用/超时/报错时返回空串，调用方保留原始图片 URL（无 caption），
不影响抓取主流程。
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

# .env 加载是可选的（本地没装 python-dotenv 也能跑，靠真实环境变量）
try:
    from dotenv import load_dotenv
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

logger = logging.getLogger(__name__)

DEFAULT_VLM_BASE_URL = "https://api.minimaxi.com/anthropic/v1/messages"
DEFAULT_VLM_MODEL = "MiniMax-VL-01"

# 政策文档配图 caption 提示词：要求模型用中文简明描述图片的政策含义或视觉特征，
# 输出纯文本（无拒答套话），便于直接作为 markdown alt text。
_VLM_CAPTION_PROMPT = (
    "你是一个政策文档标注助手。请用 1-2 句简体中文描述这张图的政策含义或视觉特征。"
    "如果是政府公章/机构标识/标题栏，描述机构名称和元素布局。"
    "如果是流程图/示意图/表格/规划图，描述核心要素（标题、关键步骤、结论、金额、时间节点）。"
    "只输出描述内容，不要返回'图片无法识别'或任何拒答套话。"
)

# 单张图最大字节数（防超大图打爆 VLM）
_MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8MB


class VLMClient:
    """MiniMax-VL-01 同步客户端（spider 在同步上下文里调用）。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 60.0,
    ):
        self.api_key = api_key or os.environ.get("MINIMAX_API_KEY", "")
        # VL 用专属 anthropic/v1/messages 端点（默认）
        self.base_url = (
            base_url
            or os.environ.get("MINIMAX_VLM_BASE_URL", DEFAULT_VLM_BASE_URL)
        )
        self.model = model or os.environ.get("MINIMAX_VLM_MODEL", DEFAULT_VLM_MODEL)
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        """是否配置了可用的 API key（决定 spider 是否走 caption 流程）。"""
        return bool(self.api_key)

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(min=2, max=8),
        reraise=False,  # 失败返回空串，不抛
    )
    def caption_image_bytes(self, img_bytes: bytes, media_type: str = "image/jpeg") -> str:
        """对图片字节生成中文 caption。失败返回空串（不抛异常，降级用）。"""
        if not self.enabled:
            return ""
        if not img_bytes or len(img_bytes) > _MAX_IMAGE_BYTES:
            logger.warning("VLM skip: empty or too-large image (%d bytes)", len(img_bytes or b""))
            return ""
        b64 = base64.b64encode(img_bytes).decode("ascii")
        body = {
            "model": self.model,
            "max_tokens": 300,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _VLM_CAPTION_PROMPT},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64,
                            },
                        },
                    ],
                }
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(self.base_url, json=body, headers=headers)
            if resp.status_code != 200:
                logger.warning(
                    "VLM API non-200: status=%s body=%s",
                    resp.status_code,
                    resp.text[:200],
                )
                return ""
            data = resp.json()
            # Anthropic 格式：content[0].text
            blocks = data.get("content") or []
            if blocks and isinstance(blocks[0], dict):
                text = (blocks[0].get("text") or "").strip()
                # 清掉 markdown 噪音（alt text 里不能有 ] ( 等会破坏语法）
                text = text.replace("\n", " ").replace("[", "【").replace("]", "】")[:200]
                return text
            return ""
        except Exception as e:
            logger.warning("VLM caption failed (degraded to empty): %s", e)
            return ""


# 全局默认实例（懒加载）
_default_client: Optional[VLMClient] = None


def get_vlm_client() -> VLMClient:
    """获取全局 VLM 客户端（复用连接配置）。"""
    global _default_client
    if _default_client is None:
        _default_client = VLMClient()
    return _default_client
