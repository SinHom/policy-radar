"""MCP Server 入口：注册 7 个 Tool，分发到 handlers。

启动方式：
    python -m mcp_server --stdio          # 给 Claude Desktop
    python -m mcp_server --sse --port 3001  # 给远程 AI 工具 / Webhook 调用方
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from python.mcp_server.tools.setup import (
    handle_complete_setup,
    handle_confirm_setup,
    handle_start_setup,
)
from python.mcp_server.tools.query import (
    handle_get_matches,
    handle_get_policy_detail,
    handle_search_policies,
)
from python.mcp_server.tools.admin import handle_trigger_crawl
from python.mcp_server.tools.manage import (
    handle_delete_subscription,
    handle_list_subscriptions,
    handle_pause_subscription,
    handle_resume_subscription,
    handle_update_subscription,
)
from python.mcp_server.tools.push import handle_push_now

logger = logging.getLogger(__name__)

server = Server("policy-radar")


# === Tool 注册 ===

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        # ----- 注册类 -----
        Tool(
            name="start_setup",
            description=(
                "发起政策监控订阅。传入已知的企业信息（至少 company_name），"
                "返回还需要补充哪些字段，每个字段给出推荐选项。"
                "AI 工具应根据返回的 missing 列表用自然语言追问用户。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "company_name": {"type": "string", "description": "企业名称（必填）"},
                    "industry": {"type": "string"},
                    "region": {"type": "string"},
                    "policy_types": {"type": "array", "items": {"type": "string"}},
                    "regions": {"type": "array", "items": {"type": "string"}},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "push_schedule": {"type": "string"},
                    "webhook_url": {"type": "string"},
                    "platform_hint": {"type": "string"},
                },
                "required": ["company_name"],
            },
        ),
        Tool(
            name="complete_setup",
            description=(
                "在用户填完所有缺失字段后调用此 Tool。"
                "如果信息齐全返回 ready_to_confirm + 摘要 + 确认提示；"
                "如果还有缺失字段返回 need_more_info + missing 列表。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "company_name": {"type": "string"},
                    "industry": {"type": "string"},
                    "region": {"type": "string"},
                    "policy_types": {"type": "array", "items": {"type": "string"}},
                    "regions": {"type": "array", "items": {"type": "string"}},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "push_schedule": {"type": "string"},
                    "webhook_url": {"type": "string"},
                    "platform_hint": {"type": "string"},
                },
                "required": ["company_name"],
            },
        ),
        Tool(
            name="confirm_setup",
            description="用户确认订阅信息后调用，落库并返回 company_id / subscription_id。",
            inputSchema={
                "type": "object",
                "properties": {
                    "setup_data": {
                        "type": "object",
                        "description": "complete_setup 返回的 summary 对象（或等价 dict）",
                    }
                },
                "required": ["setup_data"],
            },
        ),
        # ----- 查询类 -----
        Tool(
            name="search_policies",
            description=(
                "在政策库里搜索。可按关键词、类型、地区、时间范围筛选。"
                "返回最近 days_back 天内、已生成 AI 摘要的政策列表。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词（匹配 title/summary）"},
                    "types": {"type": "array", "items": {"type": "string"}, "description": "政策类型筛选"},
                    "region": {"type": "string", "description": "地区筛选"},
                    "days_back": {"type": "integer", "default": 30},
                    "limit": {"type": "integer", "default": 20},
                },
            },
        ),
        Tool(
            name="get_matches",
            description=(
                "获取某企业的最新匹配政策（已按订阅规则筛好、已打分）。"
                "unpushed_only=true 时只返回尚未推送给 webhook 的。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "company_id": {"type": "integer"},
                    "limit": {"type": "integer", "default": 10},
                    "unpushed_only": {"type": "boolean", "default": False},
                },
                "required": ["company_id"],
            },
        ),
        Tool(
            name="get_policy_detail",
            description="获取单条政策的完整详情，含 AI 摘要、申报条件、截止日期、URL。",
            inputSchema={
                "type": "object",
                "properties": {
                    "policy_id": {"type": "integer"},
                },
                "required": ["policy_id"],
            },
        ),
        # ----- 管理类 -----
        Tool(
            name="trigger_crawl",
            description=(
                "手动触发一次政策爬取。source_id 留空则爬所有启用的源。"
                "返回每个源的爬取结果（new_crawled / skipped_duplicate / errors）。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "source_id": {"type": "string", "description": "如 sz_gxj；留空爬所有"},
                },
            },
        ),
        # ----- 订阅管理类 -----
        Tool(
            name="list_subscriptions",
            description="列出所有订阅（含 company_name / enabled / webhook_url）。可选 enabled_only=true 只看启用的。",
            inputSchema={
                "type": "object",
                "properties": {
                    "enabled_only": {"type": "boolean", "default": False},
                },
            },
        ),
        Tool(
            name="update_subscription",
            description=(
                "部分更新订阅字段。可改：types / regions / keywords / push_schedule / "
                "push_time / webhook_url / platform_hint。只传要改的字段即可。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "company_id": {"type": "integer"},
                    "subscription_id": {"type": "integer"},
                    "types": {"type": "array", "items": {"type": "string"}},
                    "regions": {"type": "array", "items": {"type": "string"}},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "push_schedule": {"type": "string"},
                    "push_time": {"type": "string"},
                    "webhook_url": {"type": "string"},
                    "platform_hint": {"type": "string"},
                },
            },
        ),
        Tool(
            name="pause_subscription",
            description="暂停订阅。定时推送会跳过，但 get_matches 仍可查。",
            inputSchema={
                "type": "object",
                "properties": {
                    "company_id": {"type": "integer"},
                    "subscription_id": {"type": "integer"},
                },
            },
        ),
        Tool(
            name="resume_subscription",
            description="恢复被暂停的订阅。",
            inputSchema={
                "type": "object",
                "properties": {
                    "company_id": {"type": "integer"},
                    "subscription_id": {"type": "integer"},
                },
            },
        ),
        Tool(
            name="delete_subscription",
            description=(
                "彻底删除公司 + 订阅 + 匹配记录。级联删除：company → subscription → matches。"
                "push_logs 不删（独立审计）。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "company_id": {"type": "integer"},
                    "subscription_id": {"type": "integer"},
                },
            },
        ),
        Tool(
            name="push_now",
            description=(
                "立即把未推送的 matches 推到 subscription.webhook_url（不等定时）。"
                "match_ids 留空则推该 company 全部未推送 matches；指定则只推指定 ID。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "company_id": {"type": "integer", "description": "必填"},
                    "match_ids": {"type": "array", "items": {"type": "integer"}, "description": "可选"},
                },
                "required": ["company_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """分发 Tool 调用。"""
    logger.info("call_tool: name=%s args=%s", name, json.dumps(arguments, ensure_ascii=False)[:200])
    try:
        if name == "start_setup":
            return await handle_start_setup(arguments)
        if name == "complete_setup":
            return await handle_complete_setup(arguments)
        if name == "confirm_setup":
            return await handle_confirm_setup(arguments)
        if name == "search_policies":
            return await handle_search_policies(arguments)
        if name == "get_matches":
            return await handle_get_matches(arguments)
        if name == "get_policy_detail":
            return await handle_get_policy_detail(arguments)
        if name == "trigger_crawl":
            return await handle_trigger_crawl(arguments)
        if name == "list_subscriptions":
            return await handle_list_subscriptions(arguments)
        if name == "update_subscription":
            return await handle_update_subscription(arguments)
        if name == "pause_subscription":
            return await handle_pause_subscription(arguments)
        if name == "resume_subscription":
            return await handle_resume_subscription(arguments)
        if name == "delete_subscription":
            return await handle_delete_subscription(arguments)
        if name == "push_now":
            return await handle_push_now(arguments)
        return [TextContent(type="text", text=json.dumps(
            {"status": "error", "error": f"Unknown tool: {name}"}, ensure_ascii=False
        ))]
    except Exception as e:
        logger.exception("call_tool %s failed: %s", name, e)
        return [TextContent(type="text", text=json.dumps(
            {"status": "error", "error": str(e)}, ensure_ascii=False
        ))]


def make_server() -> Server:
    return server
