"""LLM 摘要模块：调用 MiniMax M3 对政策全文生成结构化 JSON 摘要。"""

from python.ai.llm_client import LLMClient, get_llm_client
from python.ai.summarizer import summarize_pending, summarize_one

__all__ = ["LLMClient", "get_llm_client", "summarize_pending", "summarize_one"]
