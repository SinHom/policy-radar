"""MiniMax M3 LLM 客户端。

MiniMax Text-01 / M3 兼容 OpenAI ChatCompletion 协议：
- base_url: https://platform.minimaxi.com/v1
- 鉴权：Authorization: Bearer {MINIMAX_API_KEY}
- 用 openai Python SDK 即可
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

# 启动时自动加载 .env（项目根 / .env）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://platform.minimaxi.com/v1"
DEFAULT_MODEL = "MiniMax-M3"


class LLMClient:
    """MiniMax M3 客户端封装。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 60.0,
    ):
        self.api_key = api_key or os.environ.get("MINIMAX_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "MINIMAX_API_KEY not set. 请设置环境变量或在 .env 中配置。"
            )
        self.base_url = base_url or os.environ.get("MINIMAX_BASE_URL", DEFAULT_BASE_URL)
        self.model = model or os.environ.get("MINIMAX_MODEL", DEFAULT_MODEL)
        self.timeout = timeout
        self._client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=2, max=15),
        reraise=True,
    )
    async def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 1500,
        json_mode: bool = False,
    ) -> str:
        """发一次 chat 请求，返回 assistant content 字符串。"""
        kwargs = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = await self._client.chat.completions.create(**kwargs)
        if not resp.choices:
            raise RuntimeError("LLM returned no choices")
        return resp.choices[0].message.content or ""

    async def chat_json(self, system: str, user: str) -> dict:
        """发请求并解析返回为 dict。"""
        text = await self.chat(system, user, json_mode=True)
        return _safe_parse_json(text)

    async def health_check(self) -> bool:
        """快速验证 API 可用：发最小请求。"""
        try:
            text = await self.chat(
                "You are a helpful assistant.",
                "Reply with the single word: ok",
                temperature=0,
                max_tokens=10,
            )
            return bool(text)
        except Exception as e:
            logger.exception("health_check failed: %s", e)
            return False


def _safe_parse_json(text: str) -> dict:
    """LLM 偶发返回 ```json ... ``` 围栏，先剥再解析。

    MiniMax M3 等带思考的模型会在 answer 前面输出 <think>...</think>，
    也要剥掉。
    """
    if not text:
        raise ValueError("Empty LLM response")
    s = text.strip()
    # 剥 <think>...</think> 块（包括多行）
    s = re.sub(r"<think>.*?</think>", "", s, flags=re.DOTALL).strip()
    # 剥 ```json ... ``` 围栏
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, re.DOTALL)
    if m:
        s = m.group(1)
    # 找到第一个 { 和最后一个 }
    first = s.find("{")
    last = s.rfind("}")
    if first != -1 and last != -1 and last > first:
        s = s[first : last + 1]
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM response not valid JSON: {e}; raw head: {text[:300]}")


# 全局默认实例（懒加载）
_default_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    global _default_client
    if _default_client is None:
        _default_client = LLMClient()
    return _default_client
