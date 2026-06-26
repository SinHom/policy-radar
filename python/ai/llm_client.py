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
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

# 启动时自动加载 .env（项目根 / .env）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.minimaxi.com/v1"
DEFAULT_MODEL = "MiniMax-M3"


async def _log_usage(model: str, input_tokens: int, output_tokens: int,
                     purpose: str, policy_id: int, duration_ms: int,
                     status: str = "success", error_msg: str = "") -> None:
    """异步记录 LLM 调用日志到 DB（不阻塞主流程）。"""
    try:
        from python.models.base import get_session
        from python.models.llm_usage_log import LLMUsageLog
        async with get_session() as session:
            session.add(LLMUsageLog(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                purpose=purpose,
                policy_id=policy_id,
                status=status,
                error_msg=error_msg[:500] if error_msg else "",
                duration_ms=duration_ms,
            ))
            await session.commit()
    except Exception as e:
        # 日志失败不影响主流程
        logger.warning("failed to log LLM usage: %s", e)


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
        purpose: str = "summarize",
        policy_id: int = 0,
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
        start = time.time()
        try:
            resp = await self._client.chat.completions.create(**kwargs)
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            await _log_usage(self.model, 0, 0, purpose, policy_id, duration_ms,
                             status="failed", error_msg=str(e))
            raise
        if not resp.choices:
            raise RuntimeError("LLM returned no choices")
        # 提取 token 使用
        in_tok = getattr(resp.usage, "prompt_tokens", 0) or 0
        out_tok = getattr(resp.usage, "completion_tokens", 0) or 0
        duration_ms = int((time.time() - start) * 1000)
        await _log_usage(self.model, in_tok, out_tok, purpose, policy_id, duration_ms)
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


# 全局默认实例（懒加载，从 SystemConfig 热切换）
_default_client: Optional[LLMClient] = None


async def _load_config_from_db() -> dict:
    """从 DB 读 LLM 配置，env 兜底。"""
    import os as _os
    cfg = {}
    try:
        from python.models.base import get_session
        from python.models.system_config import SystemConfig
        async with get_session() as session:
            cfg = await SystemConfig.get(session, "llm", default={}) or {}
    except Exception:
        cfg = {}
    return {
        "api_key": cfg.get("api_key") or _os.environ.get("MINIMAX_API_KEY", ""),
        "base_url": cfg.get("base_url") or _os.environ.get("MINIMAX_BASE_URL", DEFAULT_BASE_URL),
        "model": cfg.get("model") or _os.environ.get("MINIMAX_MODEL", DEFAULT_MODEL),
    }


async def get_llm_client() -> LLMClient:
    """从 DB 读最新配置，每次新建 client（支持热切换 model/key/url）。"""
    global _default_client
    cfg = await _load_config_from_db()
    _default_client = LLMClient(
        api_key=cfg["api_key"],
        base_url=cfg["base_url"],
        model=cfg["model"],
    )
    return _default_client
