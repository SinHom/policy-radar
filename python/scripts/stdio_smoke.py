"""MCP 协议层 stdio 联调：通过 ClientSession 连 stdio server，调 7 个核心 Tool。

不直接 import handler —— 真的走 MCP 协议层（stdio transport + JSON-RPC）。

模拟 Claude Desktop 的使用方式。

运行：
    python -m scripts.stdio_smoke
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("stdio_smoke")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SERVER_CMD = "python"
SERVER_ARGS = ["-m", "mcp_server", "--stdio", "--no-scheduler"]


async def main() -> int:
    # 强制子进程 stdout 为 UTF-8（Windows 默认 GBK 会让 mcp client 读崩溃）
    import os as _os
    sub_env = {
        "PYTHONPATH": "python",
        "PATH": sys.executable + "/../.." + ":" + _os.environ.get("PATH", ""),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }
    server_params = StdioServerParameters(
        command=SERVER_CMD,
        args=SERVER_ARGS,
        env=sub_env,
        cwd=str(PROJECT_ROOT),
    )

    logger.info("Connecting to MCP server via stdio...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # 1. initialize
            init_result = await session.initialize()
            logger.info("server info: %s", init_result.serverInfo.name)

            # 2. list tools
            tools_result = await session.list_tools()
            tool_names = [t.name for t in tools_result.tools]
            logger.info("tools: %d -> %s", len(tool_names), tool_names)
            assert "start_setup" in tool_names
            assert "trigger_crawl" in tool_names
            assert "push_now" in tool_names
            assert "get_matches" in tool_names

            # 3. 调 start_setup
            logger.info("call start_setup")
            r1 = await session.call_tool("start_setup", {"company_name": "stdio测试公司"})
            data1 = json.loads(r1.content[0].text)
            logger.info("start_setup: status=%s", data1.get("status"))
            assert data1["status"] == "need_more_info"

            # 4. complete_setup
            logger.info("call complete_setup")
            r2 = await session.call_tool("complete_setup", {
                "company_name": "stdio测试公司",
                "industry": "科技",
                "region": "深圳",
                "policy_types": ["补贴"],
                "regions": ["深圳"],
                "keywords": [],
                "push_schedule": "manual",
            })
            data2 = json.loads(r2.content[0].text)
            assert data2["status"] == "ready_to_confirm"

            # 5. confirm_setup
            logger.info("call confirm_setup")
            r3 = await session.call_tool("confirm_setup", {"setup_data": data2["summary"]})
            data3 = json.loads(r3.content[0].text)
            logger.info("confirm_setup: company_id=%s", data3.get("company_id"))
            assert data3["status"] == "ok"
            company_id = data3["company_id"]

            # 6. list_subscriptions
            logger.info("call list_subscriptions")
            r4 = await session.call_tool("list_subscriptions", {})
            data4 = json.loads(r4.content[0].text)
            logger.info("list_subscriptions: %d subs", data4.get("count"))
            assert data4["count"] >= 1

            # 7. search_policies
            logger.info("call search_policies")
            r5 = await session.call_tool("search_policies", {"query": "专精特新", "limit": 3})
            data5 = json.loads(r5.content[0].text)
            logger.info("search_policies: %d results", data5.get("count"))

            # 8. pause + resume
            logger.info("call pause_subscription")
            r6 = await session.call_tool("pause_subscription", {"company_id": company_id})
            data6 = json.loads(r6.content[0].text)
            assert data6["status"] == "ok"
            assert data6["enabled"] is False

            logger.info("call resume_subscription")
            r7 = await session.call_tool("resume_subscription", {"company_id": company_id})
            data7 = json.loads(r7.content[0].text)
            assert data7["status"] == "ok"
            assert data7["enabled"] is True

            # 9. push_now (manual subscription, no webhook → skipped)
            logger.info("call push_now")
            r8 = await session.call_tool("push_now", {"company_id": company_id})
            data8 = json.loads(r8.content[0].text)
            logger.info("push_now: status=%s msg=%s", data8.get("status"), data8.get("message", ""))
            assert data8["status"] in ("ok", "skipped")  # manual schedule → skipped 或 no matches

            # 10. delete
            logger.info("call delete_subscription")
            r9 = await session.call_tool("delete_subscription", {"company_id": company_id})
            data9 = json.loads(r9.content[0].text)
            assert data9["status"] == "ok"

    print("\n" + "=" * 60)
    print("STDIO SMOKE: PASS")
    print(f"  tools registered: {len(tool_names)}")
    print(f"  tested tools: 10 (start_setup/complete_setup/confirm_setup/list_subscriptions/search_policies/pause/resume/push_now/delete_subscription)")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
