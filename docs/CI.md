# CI 文档

## GitHub Actions 配置

`.github/workflows/ci.yml` 在以下情况自动跑测试：
- `push` 到 `main` 分支
- 任何 `pull_request` 到 `main`

## 测试矩阵

| 步骤 | 命令 | 用途 |
|------|------|------|
| Lint | `python -m compileall -q python/` | 编译检查（捕捉语法错） |
| Init | `alembic upgrade head` + `seed_*` | 建库 + 数据 |
| HMAC | `python -m scripts.verify_hmac` | Webhook 签名验证 |
| E2E | `python -m scripts.mcp_e2e` | 业务流：爬→摘要→匹配→推送 |
| Stdio | `python -m scripts.stdio_smoke` | MCP 协议层 13 个 Tool |
| HTTP | curl `/health` `/metrics` `/version` `/api/dashboard/funnel` | FastAPI 端点 |

## 配置 Secret

在 GitHub repo → Settings → Secrets and variables → Actions → New repository secret：

| Secret 名 | 值 |
|-----------|-----|
| `MINIMAX_API_KEY` | 你的 MiniMax API key（`sk-cp-xxx`） |

## 本地模拟 CI

```bash
# 模拟 CI 流程
rm -f data/policy_radar.db
export PYTHONIOENCODING=utf-8
export PYTHONPATH=python
alembic upgrade head
python -m scripts.seed_sources
python -m scripts.seed_policies
python -m scripts.verify_hmac    # HMAC
python -m scripts.mcp_e2e        # 业务流
python -m scripts.stdio_smoke    # 协议层

# HTTP
uvicorn python.app.main:app --port 8000 &
sleep 4
curl http://localhost:8000/health
curl http://localhost:8000/metrics
curl http://localhost:8000/api/dashboard/funnel
kill %1
```

## 状态徽章

在 README 顶部加：
```markdown
![CI](https://github.com/SinHom/policy-radar/workflows/CI/badge.svg)
```

第一次 push 后 GitHub 会显示 pass/fail。
