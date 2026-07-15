# 政策雷达 (Policy Radar) · MCP Server

> **v0.2.0** · 13 个 MCP Tools · 10 张表 · ~40 REST 端点
> 让任何 AI 工具（Claude / Cursor / 飞书 / 企微 / 小龙虾）通过 MCP 协议接入政策雷达
> 注：版本号来源不一致 — `python/app/main.py` 报 v0.1.0、`frontend/admin.html` 报 v0.3.0，以本文档为准待统一

---

## 核心能力

- 🕷️ **政策爬虫**：97 个源 seed 进 DB，有数据 60 个，500 条政策（98% 正文覆盖）；含通知公告/政策解读/公示三类子源；Playwright + httpx；详见 `docs/CRAWLER-FIX-TODO.md`
- 🖼️ **正文图片抓取 + VLM caption**：正文 `<img>` 保留进 `raw_content`（非纯文本），相对 src 补全为绝对 URL；MiniMax-VL-01 给每张图生成中文 caption 写入 `![caption](url)`，灌入 WeKnora 后图片内容可向量检索。详见 `docs/HEBEI-QHD-CRAWL-TECHNICAL.md`「正文图片抓取」
- 🤖 **AI 摘要**：MiniMax M3，自动提取政策类型/截止/金额/条件/关键词
- 🎯 **匹配引擎**：规则预筛（类型+地区+关键词）+ 可选 LLM 深度评分
- 🔔 **推送通道**：Webhook 推送（飞书/企微/通用 JSON），HMAC-SHA256 签名
- 🛠️ **MCP Server**：13 个 Tool，stdio（给 Claude Desktop）+ SSE（给远程 AI 工具）
- 📊 **管理后台**：Vue 3 SPA（7 tab：Dashboard/Subscriptions/Policies/Sources/PushLogs/LLMConfig/AuditLogs）
- 🔁 **抗失败**：3 次指数退避重试 + 死信表 + scheduler 周期重发
- 📈 **可观测性**：JSON 结构化日志 + Prometheus 指标 + 健康检查

---

## 快速开始

```bash
cd "C:\Users\\Fangyi\\OneDrive\\文档\\Claude\\政策收集总结\\policy-radar"
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt
playwright install chromium

cp .env.example .env  # 填 MINIMAX_API_KEY
alembic upgrade head
python -m scripts.seed_sources
python -m scripts.seed_policies

# 启 3 个进程（3 个终端）
python -m mock                            # 终端 1: Mock 微信
uvicorn python.app.main:app --port 8000   # 终端 2: FastAPI 管理后台
python -m mcp_server --sse --port 3001    # 终端 3: MCP Server

# 浏览器
start http://localhost:8000               # 触发页
start http://localhost:8000/admin         # Vue 3 管理后台
```

---

## 13 个 MCP Tools

### 注册（3）
- `start_setup` / `complete_setup` / `confirm_setup` — 多轮引导订阅

### 查询（3）
- `search_policies` — 关键词+类型+地区搜索
- `get_matches` — 获取企业匹配政策
- `get_policy_detail` — 单条详情

### 订阅管理（5）
- `list_subscriptions` / `update_subscription` — 列出/修改
- `pause_subscription` / `resume_subscription` — 暂停/恢复
- `delete_subscription` — 级联删除

### 操作（2）
- `trigger_crawl` — 手动爬取
- `push_now` — 立即推送

详见 `docs/superpowers/specs/2026-06-25-mcp-server-design.md`

---

## API 端点（高频 + admin 摘要，完整 ~40 端点见 `python/app/api/`）

| 路径 | 说明 |
|------|------|
| `/` | 触发页（Alpine.js MVP） |
| `/admin` | Vue 3 管理后台 |
| `/health` | 健康检查 + 统计 |
| `/metrics` | Prometheus 指标 |
| `/version` | 服务版本 |
| `/api/auth/login` | admin 登录（限流 5 次/分/IP） |
| `/api/auth/verify`, `/logout`, `/me` | token 验证/登出/当前用户 |
| `/api/sources` | 政策源列表 |
| `/api/crawl/all` | 爬取所有源 |
| `/api/crawl/{source_id}` | 爬取单源 |
| `/api/policies` | 政策列表 |
| `/api/policies/search` | 政策搜索 |
| `/api/policies/{id}/summarize` | 摘要 |
| `/api/policies/{id}/push` | 推送 |
| `/api/policies/{id}/content` | 政策正文 |
| `/api/policies/{id}/pdf` | 政策 markdown（飞书 webview 用） |
| `/api/subscriptions` | 订阅 CRUD（含 pause/resume/push/test/weekly-report） |
| `/api/companies` | 企业 CRUD |
| `/api/llm/usage`, `/api/config/llm` | LLM 统计 + 配置（admin） |
| `/api/audit/logs`, `/api/audit/stats` | 审计日志（admin） |
| `/api/push-logs`, `/api/dashboard/funnel`, `/api/dashboard/companies`, `/api/push-history` | 运营分析 |

---

## 数据库表（10 张）

| 表 | 说明 |
|---|------|
| `policy_sources` | 政策源配置 |
| `policies` | 原始政策 + AI 摘要 |
| `push_logs` | 推送记录 |
| `companies` | 企业档案 |
| `subscriptions` | 订阅规则（含 webhook + secret） |
| `matches` | 匹配结果 |
| `push_dead_letters` | 死信（重试失败入队） |
| `audit_logs` | admin 操作审计（v0.2 新增） |
| `llm_usage_logs` | LLM token 消耗统计（v0.2 新增） |
| `system_configs` | 系统配置（LLM API key 存这里，不入 .env） |

---

## Claude Desktop 配置

`%APPDATA%\\Claude\\claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "policy-radar": {
      "command": "python",
      "args": ["-m", "mcp_server", "--stdio"],
      "cwd": "C:\\\\Users\\\\Fangyi\\\\OneDrive\\\\文档\\\\Claude\\\\政策收集总结\\\\policy-radar",
      "env": {
        "PYTHONPATH": "python",
        "PYTHONIOENCODING": "utf-8",
        "MINIMAX_API_KEY": "sk-xxx"
      }
    }
  }
}
```

---

## 端到端测试

```bash
# 业务流（mcp_e2e）
rm -f data/policy_radar.db
alembic upgrade head
python -m scripts.mcp_e2e
# → 4 matches / 4 pushed / webhook received

# 协议层（stdio_smoke）
python -m scripts.stdio_smoke
# → 13 tools registered, 10 tested

# Webhook HMAC 签名
python -m scripts.verify_hmac
# → signature match = True

# 运营端点
uvicorn python.app.main:app --port 8000 &
curl http://localhost:8000/health
curl http://localhost:8000/metrics
curl http://localhost:8000/api/dashboard/funnel
```

---

## Webhook HMAC 签名

```python
import hmac, hashlib
expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
# 接收方 header: X-Policy-Radar-Signature: sha256=...
```

---

## 部署

详见 `docs/DEPLOY.md`：Ubuntu 22.04 + Docker Compose，3 个 service。

---

## 成本

| 项目 | 费用 |
|------|------|
| 云服务器 2C4G | ~¥60/月 |
| MiniMax API | ~¥15/月 |
| 域名 | ~¥5/月 |
| **合计** | **~¥80/月** |

---

## 项目结构

```
python/
├── app/            FastAPI 业务层（main / api / web / logging_config）
├── ai/             LLM 层（MiniMax M3 客户端 + 摘要）
├── crawlers/       爬虫引擎
├── mcp_server/     MCP Server（13 Tool + matcher + scheduler + webhook）
├── models/         SQLAlchemy ORM（10 张表）
├── mock/           iLink mock
├── wechat/         真实 iLink 适配器
└── scripts/        seed_* / e2e / stdio_smoke / verify_hmac
```
