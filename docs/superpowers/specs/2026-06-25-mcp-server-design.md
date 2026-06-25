# 政策雷达 MCP Server 设计文档

## 概述

将政策雷达从"自有 FastAPI + Mock 微信"架构转变为 **MCP Server + REST/Webhook 双模** 架构。MCP Server 是政策雷达的"大脑"，负责爬取、摘要、订阅管理、匹配推送。任何 AI 工具（Claude Desktop、Cursor、飞书机器人、企微机器人、小龙虾、Hermes 等）都可以通过 MCP 协议或 Webhook 调用。

## 核心设计决策

| 决策 | 结论 |
|------|------|
| 协议 | MCP 协议（stdio/SSE）+ REST/Webhook 双模 |
| 用户类型 | C 端自助（通过 AI 工具订阅）+ B 端运营（Web 后台管理） |
| 推送模式 | Pull（AI 工具主动调 `get_matches`）+ Push（Server 定时 POST webhook） |
| 迁移策略 | 保留现有代码（crawlers/ai/models），新增 MCP 层 |
| 爬虫调度 | 全量爬取 + 后匹配（爬虫不感知用户，匹配引擎按订阅规则筛选） |
| 注册交互 | Tool 返回"还缺什么字段"，AI 工具自己追问用户（MCP Server 无状态） |

## 架构图

```
                              ┌──────────────────────────────┐
   Claude Desktop ──stdio──→  │                              │
   Cursor ──stdio──→          │   MCP Server 进程             │
   远程 AI ──SSE/HTTP──→      │   (python -m mcp_server)     │
                              │                              │
   飞书 Webhook ←── push ──── │   Components:                │
   企微 Webhook ←── push ──── │   ├── Tool registry (7 tools)│
   通用 Webhook ←── push ──── │   ├── Matcher (规则预筛)      │
                              │   ├── Scheduler (APScheduler) │
                              │   └── Webhook pusher         │
                              │                              │
                              └──────────┬───────────────────┘
                                         │
                                    共享 DB (SQLite/PG)
                                         │
                              ┌──────────┴───────────────────┐
                              │   现有 FastAPI 保留           │
                              │   (管理后台 + 触发页)         │
                              │   端口 8000                  │
                              └──────────────────────────────┘
                                         │
                              ┌──────────┴───────────────────┐
                              │   现有模块（不改动）           │
                              │   ├── crawlers/engine.py      │
                              │   ├── ai/summarizer.py        │
                              │   └── models/*.py             │
                              └──────────────────────────────┘
```

## MCP Tools 定义

### 注册类（多轮引导流程）

#### `start_setup`

发起订阅注册。传入已知信息，返回缺失字段及选项。

```json
{
  "name": "start_setup",
  "description": "发起政策监控订阅。传入已知的企业信息，返回还需要补充的字段。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "company_name": {"type": "string", "description": "企业名称"},
      "industry": {"type": "string", "description": "所属行业"},
      "region": {"type": "string", "description": "企业注册地"},
      "scale": {"type": "string", "description": "企业规模"},
      "tags": {"type": "array", "items": {"type": "string"}, "description": "资质标签"},
      "policy_types": {"type": "array", "items": {"type": "string"}, "description": "关注的政策类型"},
      "regions": {"type": "array", "items": {"type": "string"}, "description": "关注的政策地区"},
      "keywords": {"type": "array", "items": {"type": "string"}, "description": "关键词增强"},
      "push_schedule": {"type": "string", "description": "推送频率: realtime/daily/weekly/manual"},
      "webhook_url": {"type": "string", "description": "推送 Webhook URL（可选）"},
      "platform_hint": {"type": "string", "description": "平台提示: feishu/wecom/generic"}
    },
    "required": ["company_name"]
  }
}
```

**返回值**：

```json
{
  "status": "need_more_info",
  "filled": {"company_name": "优智科技"},
  "missing": [
    {
      "field": "industry",
      "question": "贵公司所属行业？",
      "options": ["科技/互联网", "制造业", "生物医药", "新能源", "金融", "其他"],
      "required": true
    },
    {
      "field": "region",
      "question": "企业注册地？",
      "options": ["深圳", "广州", "北京", "上海", "其他"],
      "required": true
    },
    {
      "field": "policy_types",
      "question": "关注哪些类型的政策？（可多选）",
      "options": ["补贴", "贷款", "税收优惠", "人才引进", "产业扶持", "知识产权", "科技项目"],
      "required": true
    },
    {
      "field": "push_schedule",
      "question": "希望多久推送一次？",
      "options": ["realtime (新政策立即推)", "daily (每日早间汇总)", "weekly (每周五)", "manual (不主动推，我自己查)"],
      "required": true
    }
  ]
}
```

或者，如果信息已齐：

```json
{
  "status": "ready_to_confirm",
  "summary": {
    "company_name": "优智科技",
    "industry": "科技/互联网",
    "region": "深圳",
    "policy_types": ["补贴", "贷款"],
    "regions": ["深圳"],
    "push_schedule": "daily",
    "webhook_url": "https://open.feishu.cn/xxx"
  },
  "confirm_prompt": "请确认以上信息。确认后我将开始为您监控深圳地区的补贴和贷款政策，每天 08:30 推送到您的飞书群。"
}
```

#### `complete_setup`

补齐信息后调用，返回确认摘要。参数同 `start_setup`，但此时必须有所有 required 字段。

#### `confirm_setup`

用户确认后调用，落库。

```json
{
  "name": "confirm_setup",
  "inputSchema": {
    "type": "object",
    "properties": {
      "setup_data": {"type": "object", "description": "complete_setup 返回的 summary 对象"}
    },
    "required": ["setup_data"]
  }
}
```

返回：`{"status": "ok", "company_id": 1, "subscription_id": 1, "message": "注册成功，已开始监控。"}`

### 查询类

#### `search_policies`

```json
{
  "name": "search_policies",
  "description": "搜索政策库。可按关键词、类型、地区、时间范围筛选。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "搜索关键词"},
      "types": {"type": "array", "items": {"type": "string"}},
      "region": {"type": "string"},
      "days_back": {"type": "integer", "default": 30},
      "limit": {"type": "integer", "default": 10}
    }
  }
}
```

#### `get_matches`

```json
{
  "name": "get_matches",
  "description": "获取某企业的最新匹配政策（已按订阅规则筛选）。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "company_id": {"type": "integer"},
      "limit": {"type": "integer", "default": 10},
      "unpushed_only": {"type": "boolean", "default": true}
    },
    "required": ["company_id"]
  }
}
```

#### `get_policy_detail`

```json
{
  "name": "get_policy_detail",
  "description": "获取单条政策详情，含 AI 摘要、申报条件、截止日期等。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "policy_id": {"type": "integer"}
    },
    "required": ["policy_id"]
  }
}
```

### 管理类

#### `trigger_crawl`

```json
{
  "name": "trigger_crawl",
  "description": "手动触发一次政策爬取。不传 source_id 则爬取所有启用的源。",
  "inputSchema": {
    "type": "object",
    "properties": {
      "source_id": {"type": "string", "description": "政策源 ID，如 sz_gxj"}
    }
  }
}
```

## 新增 DB Schema

在现有 3 张表基础上新增 3 张表（通过 Alembic 迁移）。

### `companies` 表

```sql
CREATE TABLE companies (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  name          TEXT NOT NULL,
  industry      TEXT,
  region        TEXT,
  scale         TEXT,
  tags          JSON,          -- ["高新技术", "专精特新", ...]
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### `subscriptions` 表

```sql
CREATE TABLE subscriptions (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  company_id    INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  types         JSON NOT NULL,  -- ["补贴", "贷款"]
  regions       JSON NOT NULL,  -- ["深圳", "广东"]
  keywords      JSON,           -- ["专精特新", "研发补贴"]
  push_schedule TEXT NOT NULL DEFAULT 'daily',  -- realtime/daily/weekly/manual
  push_time     TEXT DEFAULT '08:30',
  webhook_url   TEXT,           -- 为空则只支持 pull
  platform_hint TEXT,           -- feishu/wecom/generic
  enabled       BOOLEAN DEFAULT TRUE,
  last_push_at  DATETIME,
  created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(company_id)
);
```

### `matches` 表

```sql
CREATE TABLE matches (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  subscription_id INTEGER NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
  policy_id       INTEGER NOT NULL REFERENCES policies(id) ON DELETE CASCADE,
  score           INTEGER DEFAULT 0,     -- 0-100 匹配分
  reasons         JSON,                  -- ["地区匹配", "类型匹配:补贴"]
  pushed          BOOLEAN DEFAULT FALSE,
  pushed_at       DATETIME,
  created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(subscription_id, policy_id)
);
```

### 现有表不改动

- `policy_sources`：不动
- `policies`：不动
- `push_logs`：保留，Webhook push 也写一条日志

## 匹配引擎

### 规则预筛流程

```
for each enabled subscription:
    for each policy in last N days (未匹配过的):
        score = 0
        if policy.summary_type in subscription.types:
            score += 40
        if policy 地区 matches any of subscription.regions:
            score += 30
        if any(kw in policy.keywords for kw in subscription.keywords):
            score += 30
        if score >= 30:
            insert into matches(subscription_id, policy_id, score, reasons)
```

MVP 阶段不引入 LLM 深度匹配（groovy-swinging-rain.md 第二期），纯规则预筛。

### 定时调度

```python
# APScheduler
scheduler.add_job(run_daily_match, 'cron', hour=7, minute=0)   # 07:00 跑匹配
scheduler.add_job(run_daily_push,  'cron', hour=8, minute=30)  # 08:30 推送
scheduler.add_job(run_weekly_push, 'cron', day_of_week='fri', hour=8, minute=30)
```

### Webhook Push

```python
async def push_to_webhook(subscription, matches):
    if not subscription.webhook_url:
        return  # pull-only, skip
    payload = format_payload(subscription.platform_hint, matches)
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(subscription.webhook_url, json=payload)
        r.raise_for_status()
    # 标记 matches 为已推送
    for m in matches:
        m.pushed = True
        m.pushed_at = datetime.utcnow()
```

### Webhook 消息格式

**通用 JSON**（generic）：

```json
{
  "event_type": "policy_matches",
  "company": {"id": 1, "name": "优智科技"},
  "matches": [
    {
      "policy_id": 42,
      "title": "深圳专精特新认定",
      "type": "补贴",
      "summary": "对认定的专精特新企业给予最高50万元奖励",
      "amount": "最高50万",
      "deadline": "2026-07-31",
      "score": 92,
      "reasons": ["地区匹配:深圳", "类型匹配:补贴", "关键词:专精特新"]
    }
  ],
  "generated_at": "2026-06-25T08:30:00"
}
```

**飞书卡片**（feishu）：

```json
{
  "msg_type": "interactive",
  "card": {
    "header": {"title": {"tag": "plain_text", "content": "📡 政策雷达 · 今日匹配 3 条"}},
    "elements": [
      {"tag": "div", "text": {"tag": "lark_md", "content": "**🟢 92% | 补贴**\n深圳专精特新认定\n💰 最高50万 ⏰ 截止 07-31"}},
      {"tag": "hr"},
      ...
    ]
  }
}
```

**企微 Markdown**（wecom）：

```json
{
  "msgtype": "markdown",
  "markdown": {
    "content": "## 📡 政策雷达 · 今日匹配\n> **92% | 补贴** 深圳专精特新认定\n> 💰 最高50万 ⏰ 截止 07-31"
  }
}
```

## 新增文件结构

```
python/
├── mcp_server/                     # 新增
│   ├── __init__.py
│   ├── __main__.py                 # 入口 (--stdio / --sse --port 3001)
│   ├── server.py                   # MCP Server + Tool 注册
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── setup.py                # start_setup / complete_setup / confirm_setup
│   │   ├── query.py                # search_policies / get_matches / get_policy_detail
│   │   └── admin.py                # trigger_crawl
│   ├── matcher.py                  # 规则预筛
│   ├── scheduler.py                # APScheduler 定时任务
│   └── webhook.py                  # Webhook 推送 + 平台 adapter
├── models/                         # 修改
│   ├── company.py                  # 新增
│   ├── subscription.py             # 新增
│   ├── match.py                    # 新增
│   └── ...现有不动
├── app/                            # 不动（保留 FastAPI 管理后台）
├── ai/                             # 不动
├── crawlers/                       # 不动
├── mock/                           # 不动
└── scripts/                        # 不动
```

## 部署

### 本地开发

```bash
# 终端 1: MCP Server (stdio 模式给 Claude Desktop)
python -m mcp_server --stdio

# 终端 2: MCP Server (SSE 模式给远程 AI 工具)
python -m mcp_server --sse --port 3001

# 终端 3: FastAPI 管理后台
uvicorn python.app.main:app --port 8000

# 终端 4: Mock 微信（如果还需要）
python -m mock
```

### Claude Desktop 配置

```json
{
  "mcpServers": {
    "policy-radar": {
      "command": "python",
      "args": ["-m", "mcp_server", "--stdio"],
      "cwd": "C:\\Users\\Fangyi\\OneDrive\\文档\\Claude\\政策收集总结\\policy-radar",
      "env": {
        "PYTHONPATH": "python",
        "MINIMAX_API_KEY": "sk-xxx"
      }
    }
  }
}
```

### Docker Compose（更新）

```yaml
services:
  app:
    # 现有 FastAPI，不变
  mcp-server:
    build: .
    command: ["python", "-m", "mcp_server", "--sse", "--port", "3001"]
    ports: ["3001:3001"]
    env_file: .env
    volumes: ["./data:/app/data"]
    restart: unless-stopped
```

## 验证方式

1. **MCP 协议验证**：用 `mcp` CLI 或 Claude Desktop 连接 stdio 模式，调 `start_setup` → `complete_setup` → `confirm_setup` 完成注册
2. **Webhook Push 验证**：设一个 webhook.site 临时 URL 作为 webhook_url，触发 `trigger_crawl` 后等匹配 + 推送
3. **飞书集成验证**：创建飞书群机器人 → 拿 webhook URL → 用 `set_webhook(platform_hint="feishu")` 设好 → 等定时推送
4. **Pull 模式验证**：不设 webhook，只调 `get_matches(company_id=1)` 验证返回匹配结果

## 范围控制

### 本次做

- MCP Server 7 个 Tool（3 注册 + 3 查询 + 1 管理）
- 3 张新表（companies / subscriptions / matches）+ Alembic 迁移
- 规则预筛匹配引擎
- APScheduler 定时爬取 + 匹配 + 推送
- Webhook pusher（generic + feishu adapter）
- Claude Desktop 配置验证

### 不做

- LLM 深度匹配（Qwen 打分）——留后续
- Vue 3 管理后台改造——保留现有触发页
- 小龙虾 iLink 真实集成——保留 mock
- 消息回复处理（用户发"1"查详情）——留后续
- 多租户隔离——单 DB 即可
