# 政策雷达 (Policy Radar) — Claude 阅读入口

> **状态：🟢 活跃** | 最后更新：2026-07-13 | 版本 v0.3 + Phase A/B(本地分支 `feat/policy-advisor-phase-ab`，未部署)
> 13 MCP Tools · ~40 REST 端点 · 10 张表 · 132 政策源（本地 97 + 上海 52，有数据 58，721 条政策，29% 正文覆盖）
> 服务器：腾讯云 `43.155.161.54`，每日 8/14/20 点定时爬取+回填+导出
> 导出：`data/exports/policies/`（208 .md），`data/exports/feeds/`（OPML + JSON）
> 完整给客户上线路线见 `docs/PRODUCTION-CHECKLIST.md`

---

## 核心约束（不可违反）

1. **LLM 统一用 MiniMax M3**（base_url=`https://api.minimaxi.com/v1`，模型 `MiniMax-M3`）
   - 兼容 OpenAI ChatCompletion 协议，用 `openai` Python SDK
   - API key 从环境变量 `MINIMAX_API_KEY` 读取，**禁止硬编码**
2. **数据库：本地 SQLite，生产可切 PostgreSQL**（通过 `DATABASE_URL` 切换，SQLAlchemy 抽象）
3. **微信 iLink 默认 mock**：`python -m mock` 起在 `0.0.0.0:9999`，推送内容 print + 追加到 `data/pushed_messages.log`；生产前必切真 iLink
4. **本地 Windows 直接跑**（venv + uvicorn），**不强制用 Docker**；Docker Compose 仅备部署

---

## 已落地的能力（v0.2）

- 🕷️ **政策爬虫**：58 源 seed 进 DB，启用 12 实测能出数据 7；`python/crawlers/spiders/*.json` 配置
- 🤖 **AI 摘要**：MiniMax M3（`python/ai/`）
- 🎯 **匹配引擎**：规则预筛（`python/mcp_server/matcher.py`）
- 🔔 **推送通道**：Webhook（飞书/企微/通用 JSON）+ HMAC-SHA256 签名 + 死信重试
- 🛠️ **MCP Server**：13 Tool（`python/mcp_server/server.py`），stdio（Claude Desktop）+ SSE（远程 AI）
- 📊 **管理后台**：Vue 3 SPA（`frontend/`），5 tab：Dashboard / Subscriptions / Policies / Sources / Logs
- 📈 **可观测性**：JSON 结构化日志 + Prometheus `/metrics` + Grafana dashboard
- 🔐 **鉴权**：所有 `/api/*` 端点已挂 `require_admin`（v0.2+）

---

## 目录约定

```
policy-radar/
├── python/
│   ├── app/         FastAPI 业务层（main / api / web / logging_config）
│   ├── ai/          LLM 层（llm_client / summarizer / prompts）
│   ├── crawlers/    爬虫引擎（engine / fetcher / parser / dedup / spiders/*.json / **tagger.py 标签分类器**）
│   ├── mcp_server/  MCP Server（server 13 Tool + matcher + scheduler + webhook）
│   ├── models/      SQLAlchemy ORM（10 张表）
│   ├── mock/        iLink mock
│   ├── wechat/      真实 iLink 适配器
│   └── scripts/     seed_* / e2e / mcp_e2e / stdio_smoke / verify_hmac / backfill_content / backfill_httpx / probe_content_types / fix_zero_sources / generate_opml / export_policies_md / seed_shanghai_sources
├── frontend/        Vue 3 管理后台（npm 项目）
├── alembic/         数据库迁移
├── data/            运行时数据（SQLite、推送日志，不入 git）
├── docs/            文档（DEPLOY / SECURITY / CI / MVP / PRODUCTION / ...）
├── rsshub_repo/     内嵌 RSSHub（Git submodule，含 AGENTS.md）
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## 已完成（原"不在 MVP 范围内"清单全部兑现）

- ✅ 定时调度（APScheduler，mcp_server scheduler）
- ✅ 匹配引擎（规则预筛 + 可选 LLM 深度评分）
- ✅ 日报 + 周报自动推送
- ✅ Vue 3 + Node.js 管理后台
- ✅ 推送设置 / 关键词配置 / 顾问名片
- ✅ MCP Server 13 Tool + stdio/SSE 双模
- ✅ 批量正文回填（backfill_content.py，Playwright 抓取 + 多选择器 fallback）
- ✅ 通知公告/政策解读/公示三类子源（probe_content_types.py 自动探测 + 创建 config）
- ✅ 零数据源批量修复（fix_zero_sources.py，首页→通知公告 + render_js 修复）
- ✅ OPML/JSON 信源订阅导出（generate_opml.py，可导入 Feedly/Inoreader）
- ✅ 上海市 50 信源（34 委办局 + 16 区，`*.sh.gov.cn` + Playwright，seed_shanghai_sources.py）
- ✅ 服务器定时部署（cron 8/14/20 点，cron_run.sh）
- ✅ **v0.3 RSSHub 订阅源链路**（2026-07-09）：4 个 FastAPI 端点（feed/article/markdown/opml）+ 5 个 RSSHub Node 路由 + 5am 服务器 cron + 6am Windows 同步
- ✅ **18 个国家级 spider 新增**（含 国务院公报、惠企助企、省/市文旅、省知产 + 14 个部委）
- ✅ **server SSH 免密登录**（`ssh radar` 一键登，详见 [[policy-radar-ssh-and-waf]]）
- ✅ **Phase A/B 信源补网 + 标签分类器**（2026-07-13，本地分支 `feat/policy-advisor-phase-ab`，**未部署**）：
  - 9 新 spider：`nat_mct`(文旅部) / `nat_forestry`(林草局) / `city_qhd_tyj`(市体育局) / `city_qhd_shg·bdh·fn·ql·cl·ll`(6 区县)。审计修正：河北省级 5 个文旅相关部门早已存在，非新增
  - `python/crawlers/tagger.py` `classify_tags(title)` 纯函数关键字分类（14 标签：文旅_规划/申报/非遗/文物/广电/体育/政策 + 通用公文 + 新闻动态）
  - 接入 `policy_radar.py` RSS item：`tags = parse_tags(src.tags) + classify_tags(pol.title)` 去重 merge，**实时算不落库、不加 Policy.tags 列**
  - **?tag= 过滤重排**：从 SQL 层（按 PolicySource.tags 源级）改为 item 构建后 Python 层按 merged tags AND 过滤，使 `?tag=文旅_规划` 等标题级标签可过滤
  - `parse_tags` 加 `isinstance(result, list)` 防护（防 json.loads 返回 str/dict 时全端点 500）
  - 待服务器：A5 city_qhd_lyj(probe code+WAF) / A12 验证已有 11 信源 / A13 全量抓取导出
- ✅ **正文图片抓取 + VLM caption 增强**（2026-07-14，本地分支，**未部署**）：
  - `python/crawlers/parser.py` 新增 `extract_content_html(soup, selector, base_url, caption_images=True)`：取代 `extract_by_selector` 抓正文。返回**带 `<img>` 的 HTML 片段**（非纯文本），补全相对 src 为绝对 URL，删 script/style/nav/footer
  - `python/ai/vlm_client.py` 新增 `VLMClient`：调 MiniMax-VL-01 via `https://api.minimaxi.com/anthropic/v1/messages`（Anthropic Messages API，**非** OpenAI 兼容端点）。`caption_image_bytes(img_bytes, media_type) -> str`，失败降级返回空串
  - `extract_content_html` 内 `_caption_images(node, base_url)`：下载正文每张绝对 URL 图（带 Referer 绕 gov 防盗链，限 5 张/页）-> VLM 生成中文 caption -> 写 `<img alt=caption>`。markdownify 后成 `![caption](url)`，caption 进 chunk 文本被向量检索
  - 复用 `MINIMAX_API_KEY`（119 元全模态套餐含 VL），新增 `MINIMAX_VLM_MODEL`（默认 `MiniMax-VL-01`）+ 可选 `MINIMAX_VLM_BASE_URL`
  - `engine.py` 第 206 行已改调 `extract_content_html`。raw_content 现存带 img + caption 的 HTML（向后兼容：旧纯文本数据不受影响，导出 markdownify 自动转 `![](url)`）
  - **WeKnora 集成**：上传这种 md 到配齐 `embedding_model_id`+`summary_model_id`+`chunking_config` 的 KB，caption 被向量化，检索"国徽"/"文化和旅游部官网"可命中图片内容

---

## 命名约定

- Python 文件/目录：`snake_case`
- 类：`PascalCase`
- 函数/变量：`snake_case`
- 常量：`UPPER_SNAKE_CASE`
- 配置文件：`kebab-case.env.example` 用 `UPPER_SNAKE_CASE`
- 数据库表名：`snake_case` 复数（`policies`、`push_logs`）

---

## 关键命令速查

```bash
# 激活虚拟环境（Windows Git Bash）
source .venv/Scripts/activate

# 启 mock 微信
python -m mock

# 启 FastAPI（开发模式，端口 8000）
uvicorn python.app.main:app --reload --port 8000

# 启 MCP Server（stdio 给 Claude Desktop）
python -m mcp_server --stdio

# 启 MCP Server（SSE 给远程 AI 工具）
python -m mcp_server --sse --port 3001

# 跑爬虫
python -m crawlers --source sz_gxj

# 跑摘要
python -m ai --limit 5

# 端到端联调（MCP 业务流）
python -m scripts.mcp_e2e

# 端到端联调（旧 REST 流，仍可用）
python -m scripts.e2e

# MCP 协议层冒烟（13 tool 注册 + 10 tested）
python -m scripts.stdio_smoke

# Webhook HMAC 验证
python -m scripts.verify_hmac

# 跑迁移
alembic upgrade head
alembic revision --autogenerate -m "msg"
```

---

## RSSHub 订阅源端点（v0.3 核心）

服务器 `43.155.161.54:8000`：

| 端点 | 说明 |
|---|---|
| `GET /policy-radar/feed[/{region}[/{dept}]]` | RSS 2.0 列表（带 region/dept/tag/from/to/limit/full 筛选） |
| `GET /policy-radar/article/{id}` | 单篇 RSS 包装 markdown |
| `GET /policy-radar/markdown/{id}` | 纯 .md + YAML frontmatter（知识库直接抓） |
| `GET /policy-radar/opml` | 所有源 OPML 订阅列表 |

筛选参数：`?tag=惠企_政策,解读&from=2026-01-01&to=2026-07-09&limit=50&full=1`

**标签体系**（Phase A/B 新增）：每条政策 `tags = 源级(PolicySource.tags) + 标题级(classify_tags 实时算)`，去重 merge，**不落库不加列**。标题级标签：`文旅_规划` `文旅_申报` `文旅_非遗` `文旅_文物` `文旅_广电` `文旅_体育` `文旅_政策` + 通用(`政策文件`/`通知`/`公告`/`解读`/`公文`/`法规`/`会议`/`新闻动态`)。`?tag=` 过滤在 item 构建后 Python 层 AND 匹配（tags 非空时全量取回再截断），可过滤标题级标签如 `?tag=文旅_规划`。分类器在 `python/crawlers/tagger.py`。

详细文档见根目录 `RSSHub订阅源文档.md`。

---

## 服务器定时任务（v0.3 新增）

```cron
# /etc/cron.d/policy-radar-5am (新增) - 凌晨 5 点
0 5 * * * root /opt/policy-radar/cron_5am.sh

# /etc/cron.d/policy-radar (原有) - 8/14/20 点
0 8,14,20 * * * root cd /opt/policy-radar && /usr/bin/docker exec policy-radar-app bash /opt/cron_run.sh
```

Windows 本地同步：Task Scheduler `PolicyRadar-DailySync` 每天 06:00 触发 `sync_from_server.ps1`。

服务器路径、SSH 免密、密码安全规范见 `~/.claude/projects/.../memory/policy-radar-ssh-and-waf.md`。

---

## 触发页面 UI 风格

参考 `../政策雷达-demo.html`：
- 浅色商务风（类似 Linear / Notion / 飞书）
- Tailwind CDN + Alpine.js（不是 Vue）
- Noto Sans SC + DM Sans
- 主色 `brand` 蓝（#3b82f6 系），强调 `accent` 琥珀
- 圆角统一 `rounded-xl` 卡片、`rounded-full` 标签
- 极轻阴影 + hover-lift 浮起

**MVP 触发页面范围控制**：只做"4 个按钮 + 1 个列表 + 推送日志面板"，不要扩到搜索/筛选/分页（第二期再加）。

---

## MCP Server 设计

详见 [`docs/superpowers/specs/2026-06-25-mcp-server-design.md`](docs/superpowers/specs/2026-06-25-mcp-server-design.md)

Claude Desktop 配置 (`%APPDATA%\Claude\claude_desktop_config.json`)：
```json
{
  "mcpServers": {
    "policy-radar": {
      "command": "python",
      "args": ["-m", "mcp_server", "--stdio"],
      "cwd": "C:\\Users\\Fangyi\\OneDrive\\文档\\Claude\\政策收集总结\\policy-radar",
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

## ⚠️ Token 消耗优化（强制规则）

**每次操作前必读：[docs/TOKEN-OPTIMIZATION.md](docs/TOKEN-OPTIMIZATION.md)**

核心 3 条：
1. **屏蔽 SSH banner** — 远程服务器 `touch ~/.hushlogin` 一次
2. **Edit 不用 Read+Edit** — grep 定位直接改
3. **输出最小化** — `tail -N` + `grep -vE` 过滤 + `-o /dev/null`

不遵守会让 token 浪费 5-10 倍，本项目大，必须严格执行。

---

## 🔒 安全规范（强制规则）

**每次开发前必读：[docs/SECURITY.md](docs/SECURITY.md) + [docs/SECURITY-CHECKLIST.md](docs/SECURITY-CHECKLIST.md)**

10 维度：鉴权/网络/输入/密钥/限流/日志/依赖/数据/运维/API。

**代码层底线（缺一不可）：**
- 所有 `/api/*` 写操作必须鉴权（`Depends(require_admin)`，已落地）
- API key 不写代码/commit，存 DB（`SystemConfig` 表）
- 响应里 API key 脱敏（前 4 + ... + 后 4）
- 日志不打印完整 key / 密码
- 错误信息不泄露内部细节
- SQL 用 ORM，不拼字符串
- 外部输入全过 Pydantic

**发布前必查清单**（15 维 ~80 项）— 见 SECURITY-CHECKLIST.md。

## 安全红线

- 绝不能 commit `.env`（含真实 API Key）
- commit 前必跑 `git diff --staged` 检查
- `MINIMAX_API_KEY` 只从 `os.environ` 读
- 真实微信 bot_token 不进代码、不进 commit、不进日志

---

## 上线路线参考

- [docs/PRODUCTION-CHECKLIST.md](docs/PRODUCTION-CHECKLIST.md) — 阻塞项 / 限期项 / 锦上添花 三档清单
- [docs/DEPLOY.md](docs/DEPLOY.md) — Ubuntu 22.04 + Docker Compose 部署
- [docs/CRAWLER-FIX-TODO.md](docs/CRAWLER-FIX-TODO.md) — 爬虫源剩余待修清单（5 源待修）