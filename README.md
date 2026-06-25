# 政策雷达 (Policy Radar)

> 第一期 MVP：政策采集 → AI 摘要 → 推送

将 Demo 中的政策雷达从静态原型变为可运行系统。MVP 范围：**5 条 mock 政策 + LLM 摘要 + Mock 微信推送**。完整 4 期方案见 `C:\Users\Fangyi\.claude\plans\groovy-swinging-rain.md`。

## ⚠️ 重要说明（第一期 MVP）

由于本地公司网络 + 政府网站反爬，**第一期 MVP 用 mock 政策验证端到端链路**。爬虫代码已就绪（`python/crawlers/`），部署到云服务器（无代理拦截）后即可启用真实爬取。

## 本地开发（Windows 4 步）

```bash
# 1. 激活虚拟环境
cd "C:\Users\Fangyi\OneDrive\文档\Claude\政策收集总结\policy-radar"
source .venv/Scripts/activate

# 2. 启 mock 微信（终端 1）
python -m mock

# 3. 启 FastAPI（终端 2）
uvicorn python.app.main:app --reload --port 8000

# 4. 浏览器打开
start http://localhost:8000
```

页面提供 4 个按钮：**爬取 / 刷新 / 推送日志 / Mock 心跳**，列表展示已摘要政策，点「推送」即发到 Mock 微信。

## 一键端到端测试

```bash
# 清库重建后跑全链路
rm -f data/policy_radar.db data/pushed_messages.log
alembic upgrade head
python -m scripts.e2e
```

预期输出：
```
e2e PASS
  sources:    3
  policies:   5
  summarized: 5/5
  push:       OK
  elapsed:    ~70s
```

## 云服务器部署（3 步）

```bash
# 1. 装 Docker（Ubuntu 22.04）
curl -fsSL https://get.docker.com | sh

# 2. clone + 配置
git clone <repo> policy-radar && cd policy-radar
cp .env.example .env && nano .env  # 填 MINIMAX_API_KEY

# 3. 启动
docker compose build && docker compose up -d
```

详见 `docs/DEPLOY.md`。

## 目录结构

```
policy-radar/
├── python/
│   ├── app/          FastAPI 业务层（main / api / web）
│   ├── ai/           LLM 层（MiniMax M3 客户端 + 摘要）
│   ├── crawlers/     爬虫引擎（fetcher / parser / engine / spiders/*.json）
│   ├── models/       SQLAlchemy 模型（policy_sources / policies / push_logs）
│   ├── mock/         Mock 微信 iLink 服务
│   └── scripts/      seed_sources / seed_policies / e2e
├── data/             运行时（SQLite、推送日志，不入 git）
├── docs/             DEPLOY.md 等
├── alembic/          数据库迁移
├── Dockerfile
├── docker-compose.yml
├── .env.example      环境变量模板
├── CLAUDE.md         项目说明（给 Claude 读）
└── requirements.txt
```

## 关键命令

| 命令 | 说明 |
|------|------|
| `python -m mock` | 启 Mock 微信（端口 9999） |
| `uvicorn python.app.main:app --reload` | 启 FastAPI（端口 8000） |
| `python -m crawlers --source sz_gxj` | 跑单个爬虫源 |
| `python -m crawlers --all` | 跑所有 enabled 爬虫源 |
| `python -m ai --limit 5` | 摘要 5 条未摘要政策 |
| `python -m ai --health-check` | 验证 LLM API 可用 |
| `python -m scripts.seed_sources` | 预置 3 个政策源 |
| `python -m scripts.seed_policies` | 预置 5 条 mock 政策 |
| `python -m scripts.e2e` | 端到端测试 |
| `alembic upgrade head` | 应用数据库迁移 |
| `alembic revision --autogenerate -m "msg"` | 生成新迁移 |

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 触发页（demo 风格） |
| GET | `/api/sources` | 列出政策源 |
| POST | `/api/crawl/all` | 爬取所有源 |
| POST | `/api/crawl/{source_id}` | 爬取单个源 |
| GET | `/api/policies?limit=50` | 列出已摘要政策 |
| POST | `/api/policies/{id}/summarize` | 摘要单条 |
| POST | `/api/policies/{id}/push` | 推送到 Mock 微信 |
| GET | `/api/push-logs?limit=30` | 推送历史 |

## FAQ

**Q: 为什么 mock 政策而不是真实爬取？**
A: 本地公司网络代理拦截政府网站 SSL，3 个源全部不可达。爬虫代码已就绪，部署到云服务器后即可启用。

**Q: MiniMax M3 是什么？**
A: MiniMax 自研的中文 LLM（`https://api.minimaxi.com/v1`），兼容 OpenAI ChatCompletion 协议，base_url 用 `https://api.minimaxi.com/v1`（注意不是 `platform.minimaxi.com`）。

**Q: 推送到真实微信怎么切？**
A: 把 `MOCK_WECHAT_URL` 改为真实 iLink 网关地址，把 `mock_wechat.py` 删掉，FastAPI 的 `/api/policies/{id}/push` 端点不变。

**Q: 跑 e2e 报 "summarized 0/5"？**
A: 之前已经摘要过了。清库重建：`rm data/policy_radar.db && alembic upgrade head && python -m scripts.e2e`。

## 成本

| 项目 | 费用 |
|------|------|
| 云服务器 2C4G | ~¥60/月 |
| MiniMax API | ~¥15/月（日均 50 条摘要 + 少量匹配） |
| 域名 | ~¥5/月 |
| **合计** | **~¥80/月** |
