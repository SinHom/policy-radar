# 政策雷达 — 项目说明（给 Claude 读）

> 第一期 MVP：脚手架 + 3 个政策源爬虫 + MiniMax M3 摘要 + Mock 微信推送
> 完整 4 期方案见 `C:\Users\Fangyi\.claude\plans\groovy-swinging-rain.md`

## 核心约束（不可违反）

1. **LLM 统一用 MiniMax M3**（base_url=`https://platform.minimaxi.com/v1`，模型 `MiniMax-M3`）
   - 兼容 OpenAI ChatCompletion 协议，用 `openai` Python SDK
   - API key 从环境变量 `MINIMAX_API_KEY` 读取，**禁止硬编码**
2. **数据库：本地 SQLite，生产可切 PostgreSQL**（通过 `DATABASE_URL` 切换，SQLAlchemy 抽象）
3. **微信 iLink 用 mock**：`python -m mock` 起在 `0.0.0.0:9999`，推送内容 print + 追加到 `data/pushed_messages.log`
4. **本地 Windows 直接跑**（venv + uvicorn），**不强制用 Docker**；Docker Compose 仅备部署

## 目录约定

```
python/
├── app/         FastAPI 业务层（main.py, config.py, api/, web/）
├── ai/          LLM 层（llm_client.py, summarizer.py, prompts/）
├── crawlers/    爬虫（engine.py, fetcher.py, parser.py, dedup.py, spiders/*.json）
├── models/      SQLAlchemy 模型
├── mock/        iLink mock 服务
└── scripts/     一次性脚本（seed_sources.py, e2e.py）
data/            运行时数据（SQLite、推送日志，不入 git）
docs/            文档和 HTML 样本
alembic/         数据库迁移
```

## 不在 MVP 范围内（第二期再做）

- ❌ 定时调度（APScheduler）— 第二期
- ❌ 匹配引擎（Qwen 深度匹配）— 第二期
- ❌ 日报自动推送 — 第二期
- ❌ 完整 Vue 3 + Node.js 管理后台 — 第三期
- ❌ 推送设置 / 关键词配置 / 顾问名片 — 第三期
- ❌ 咨询引流 / 二维码 / 转化漏斗 — 第四期
- ❌ PyMuPDF PDF 解析 — 第二期（MVP 仅识别 PDF URL）

## 触发页面 UI 风格

参考 `../政策雷达-demo.html`：
- 浅色商务风（类似 Linear / Notion / 飞书）
- Tailwind CDN + Alpine.js（不是 Vue）
- Noto Sans SC + DM Sans
- 主色 `brand` 蓝（#3b82f6 系），强调 `accent` 琥珀
- 圆角统一 `rounded-xl` 卡片、`rounded-full` 标签
- 极轻阴影 + hover-lift 浮起

**MVP 触发页面范围控制**：只做"4 个按钮 + 1 个列表 + 推送日志面板"，不要扩到搜索/筛选/分页（第二期再加）。

## 命名约定

- Python 文件/目录：`snake_case`
- 类：`PascalCase`
- 函数/变量：`snake_case`
- 常量：`UPPER_SNAKE_CASE`
- 配置文件：`kebab-case.env.example` 用 `UPPER_SNAKE_CASE`
- 数据库表名：`snake_case` 复数（`policies`、`push_logs`）

## 关键命令速查

```bash
# 激活虚拟环境（Windows Git Bash）
source .venv/Scripts/activate

# 启 mock 微信
python -m mock

# 启 FastAPI（开发模式）
uvicorn app.main:app --reload --port 8000

# 跑爬虫
python -m crawlers --source sz_gxj

# 跑摘要
python -m ai --limit 5

# 端到端联调
python -m scripts.e2e

# 跑迁移
alembic upgrade head
alembic revision --autogenerate -m "msg"
```

## ⚠️ Token 消耗优化（强制规则）

**每次操作前必读：[docs/TOKEN-OPTIMIZATION.md](docs/TOKEN-OPTIMIZATION.md)**

核心 3 条：
1. **屏蔽 SSH banner** — 远程服务器 `touch ~/.hushlogin` 一次
2. **Edit 不用 Read+Edit** — grep 定位直接改
3. **输出最小化** — `tail -N` + `grep -vE` 过滤 + `-o /dev/null`

不遵守会让 token 浪费 5-10 倍，本项目大，必须严格执行。

## 安全红线

- 绝不能 commit `.env`（含真实 API Key）
- commit 前必跑 `git diff --staged` 检查
- `MINIMAX_API_KEY` 只从 `os.environ` 读
- 真实微信 bot_token 不进代码、不进 commit、不进日志
