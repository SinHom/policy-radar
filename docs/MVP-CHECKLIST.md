# 第一期 MVP 验收清单

## Step 0 — 脚手架 + CLAUDE.md

- [x] `policy-radar/` 目录创建
- [x] `.gitignore` 写好（忽略 `.venv/`、`data/*.db`、`.env`）
- [x] `CLAUDE.md` 写好（核心约束、目录约定、不在 MVP 范围）
- [x] `.env.example` 写好
- [x] `.venv/` 创建（Python 3.14.4）
- [x] 首次 git commit

**验收**：`git log` 看到 `step0: scaffold project structure`

## Step 1 — 依赖安装 + 环境验证

- [x] `requirements.txt` 写好（不锁版本，让 pip 选 3.14 兼容）
- [x] 用清华源 + `PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1` 装好所有依赖
- [x] Playwright Chromium 装好（`playwright install chromium`）
- [x] Playwright 启动验证 OK（访问 baidu.com）

**验收**：
```bash
python -c "import fastapi, sqlalchemy, playwright, openai, httpx; print('OK')"
```

## Step 2 — 数据库 Schema + Alembic

- [x] `python/models/` 3 张表（policy_sources, policies, push_logs）
- [x] `alembic init` + env.py 配置（读 DATABASE_URL）
- [x] `alembic upgrade head` 创建表
- [x] 表结构验证 OK

**验收**：
```bash
alembic upgrade head
sqlite3 data/policy_radar.db ".tables"  # 看到 alembic_version policies policy_sources push_logs
```

## Step 3 — 爬虫引擎骨架

- [x] `fetcher.py`（httpx + Playwright）
- [x] `parser.py`（BS4 + lxml）
- [x] `dedup.py`（URL 去重）
- [x] `engine.py`（主流程）
- [x] `__main__.py`（CLI 入口）
- [x] 3 个 JSON 配置文件（sz_gxj / gd_kjt / gov_cn）
- [x] fetcher Playwright 加 `ignore_https_errors=True`（绕过公司代理 SSL）

**验收**：
```bash
python -m crawlers --source sz_gxj   # 受网络限制可能 timeout/404
```

## Step 4（调整）— 预置 5 条 mock 政策

- [x] `python/scripts/seed_policies.py` 写好
- [x] 5 条政策入库（sz_gxj×2, gd_kjt×2, gov_cn×1）
- [x] 3 个爬虫源预置到 DB

**验收**：
```bash
python -m scripts.seed_sources
python -m scripts.seed_policies
sqlite3 data/policy_radar.db "select count(*) from policies"  # = 5
```

## Step 5 — MiniMax M3 摘要接入

- [x] `ai/llm_client.py`（OpenAI 协议）
- [x] `ai/summarizer.py`（政策摘要）
- [x] `ai/prompts/summary.txt`（prompt 模板）
- [x] `ai/__main__.py`（CLI）
- [x] 修正 base_url 为 `https://api.minimaxi.com/v1`
- [x] JSON 解析兼容 M3 的 <think> 围栏
- [x] 5/5 摘要成功

**验收**：
```bash
python -m ai --health-check   # OK
python -m ai --limit 5        # 5/5 成功
```

## Step 6 — Mock 微信 iLink 服务

- [x] `mock/mock_wechat.py`（FastAPI on 9999）
- [x] 4 个端点：`/get_bot_qrcode`, `/getupdates`, `/sendmessage`, `/_inject`
- [x] sendmessage 把内容 print + 追加到 `data/pushed_messages.log`
- [x] emoji 容错（避免 Windows console GBK 错误）

**验收**：
```bash
python -m mock &
curl http://localhost:9999/   # 返回 service 描述
cat data/pushed_messages.log   # 看到推送记录
```

## Step 7 — FastAPI + 触发页面

- [x] `app/main.py`（FastAPI 入口 + lifespan）
- [x] `app/api/routes.py`（5 个端点：sources / crawl / policies / push / push-logs）
- [x] `app/web/routes.py`（返回静态 HTML）
- [x] `app/web/templates/index.html`（demo 风格的触发页，Tailwind + Alpine）

**验收**：
```bash
uvicorn python.app.main:app --reload
# 浏览器 http://localhost:8000 看到触发页
```

## Step 8 — 端到端联调

- [x] `python/scripts/e2e.py`（4 步：seed_sources → seed_policies → summarize → push）
- [x] `e2e PASS`：3 sources / 5 policies / 5 summarized / push OK

**验收**：
```bash
rm -f data/policy_radar.db
alembic upgrade head
python -m scripts.e2e
# 输出: e2e PASS / sources: 3 / policies: 5 / summarized: 5/5 / push: OK
```

## Step 9 — Docker Compose 部署方案

- [x] `Dockerfile`（`python:3.11-slim` + Playwright `--with-deps` + 系统依赖）
- [x] `docker-compose.yml`（app + mock_wechat 两个服务，data volume 挂载）
- [x] `docs/DEPLOY.md`（Ubuntu 22.04 + Docker 一键部署）

## Step 10 — README + 验收清单

- [x] `README.md`（本地 4 步 + 部署 3 步 + FAQ + 成本）
- [x] `docs/MVP-CHECKLIST.md`（本文件）

## 全局验收

```bash
# 1. 清库重建
cd "C:\Users\Fangyi\OneDrive\文档\Claude\政策收集总结\policy-radar"
rm -f data/policy_radar.db data/pushed_messages.log
alembic upgrade head

# 2. 启两个服务（两个终端）
python -m mock                                       # 终端 1
uvicorn python.app.main:app --port 8000              # 终端 2

# 3. 跑 e2e
python -m scripts.e2e
# 预期: e2e PASS

# 4. 浏览器访问
start http://localhost:8000
# 点击 "爬取所有源" / "推送" 等按钮，验证交互
```
