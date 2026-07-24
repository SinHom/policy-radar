# 部署指南

## 云服务器部署（阿里云轻量 2C4G / 腾讯云 / 华为云）

### 1. 服务器初始化

```bash
# Ubuntu 22.04
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl

# 安装 Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# 验证
docker --version
docker compose version
```

### 2. 拉取代码

```bash
# 把本地项目 push 到 GitHub（首次）
cd /path/to/policy-radar
git init && git add -A && git commit -m "init"
git remote add origin https://github.com/yourname/policy-radar.git
git push -u origin main

# 服务器上 clone
git clone https://github.com/yourname/policy-radar.git
cd policy-radar
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入真实的 MINIMAX_API_KEY（119 元全模态套餐同时支持 M3 文本 + VL-01 视觉）
nano .env
```

> **VLM（正文图片 caption）**：复用同一个 `MINIMAX_API_KEY`。spider 抓到正文配图时调 MiniMax-VL-01 生成中文 caption 注入 markdown。`MINIMAX_VLM_MODEL` 默认 `MiniMax-VL-01`（已在 `.env.example`）。未配 `MINIMAX_API_KEY` 时 caption 流程静默降级（保留原图无 caption，不影响抓取）。详见 `docs/HEBEI-QHD-CRAWL-TECHNICAL.md`「正文图片抓取」。

> **改 `.env` / 轮换 API key**：编辑 `.env` 后必须 `docker compose up -d`（**不是** `docker restart`）才重读 env_file；`restart` 不重读 env，旧 key 仍生效。轮换流程：`sed -i 's|^MINIMAX_API_KEY=.*|MINIMAX_API_KEY=<new>|' .env`（服务器+本地都改，key 只在 shell 变量不进文件内容）-> `docker compose up -d app` -> 验证 `curl -X POST .../advisor-qhd/analyze` 跑一次真实 LLM 调用确认 key 有效。**安全红线**：key 永不在对话/commit/memory 明文出现；曾在对话暴露的 key 应去控制台废弃重生。
>
> ⚠ **已知泄漏（待修）**：`.env.production` 未被 `.gitignore` 覆盖且**已被 git 跟踪**，真实 MINIMAX_API_KEY 已进 PUBLIC 仓库 `SinHom/policy-radar` 历史。修前**勿再编辑 `.env.production`**；新 key 只写 `.env`（已 gitignore）。修复需 `git rm --cached .env.production` + 补 `.gitignore`（`.env*` + `!.env.example`）+ BFG/filter-repo 清历史 + force push，且先在 MiniMax 控制台废弃已泄漏 key。

### 4. 启动

```bash
docker compose build
docker compose up -d
docker compose logs -f app
```

### 5. 初始化数据

```bash
# 进容器跑一次性脚本
docker compose exec app python -m scripts.seed_sources
docker compose exec app python -m scripts.seed_policies
docker compose exec app python -m ai --limit 5
```

### 6. 绑定域名

阿里云 DNS 解析：`admin.your-domain.com` → 服务器 IP
Nginx 反向代理 8000 端口 → 加 HTTPS（certbot 自动）

## 本地开发（Windows）

```bash
# 激活虚拟环境
cd "C:\Users\Fangyi\OneDrive\文档\Claude\政策收集总结\policy-radar"
source .venv/Scripts/activate

# 启 mock 微信
python -m mock

# 启 FastAPI（另一个终端）
uvicorn python.app.main:app --reload --port 8000

# 浏览器打开
start http://localhost:8000
```

## 常见问题

### SQLite + Docker volume
必须把 `data/` 挂载到 host，否则容器重启数据丢。当前 docker-compose.yml 已挂载。
**重要**：`data/exports/policies/` 是 host 容器共享挂载点，RSSHub 端点的 .md 从这里读。

### Playwright 在 Docker 中需要系统依赖
Dockerfile 用 `python:3.11-slim`（debian），已 apt-get install 所有依赖。
**不要**用 `python:3.11-alpine`（musl 库不兼容）。

### 时区
容器默认 UTC。日志时间会偏 8 小时。在 `docker-compose.yml` 加：
```yaml
environment:
  - TZ=Asia/Shanghai
```

### 反爬失败
政府网站对云服务器 IP 段可能也有限制。如反复失败：
- 加代理（HTTP_PROXY 环境变量）
- 减少爬取频率（`CRAWLER_REQUEST_INTERVAL_MIN=10`）

## 定时任务（v0.3 新增）

```bash
# 1. 服务器 5am cron（爬取+导出）
# 文件: /etc/cron.d/policy-radar-5am
# 内容: 0 5 * * * root /opt/policy-radar/cron_5am.sh
# 脚本流程: docker exec policy-radar-app python -m crawlers --all
#        → backfill_content → export_policies_md
#        → docker restart policy-radar-app（加载新代码）

# 2. 已有 8/14/20 点 cron（不变）
# 文件: /etc/cron.d/policy-radar
```

## RSSHub 端点验证

```bash
# 服务器启动后验证（确保 8000 端口可访问）
curl -s http://43.155.161.54:8000/policy-radar/feed?limit=3 | head -30
curl -s http://43.155.161.54:8000/policy-radar/markdown/1 | head -20
curl -s http://43.155.161.54:8000/policy-radar/opml | head -10
```

## Windows 本地每日同步

```powershell
# 1. 配置 SSH 免密（一次性，详见 ~/.claude/.../memory/policy-radar-ssh-and-waf.md）
# 2. 复制 sync_from_server.ps1 到 OneDrive 根目录
# 3. 注册 Windows Task Scheduler 任务：
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
  -Argument '-ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\Users\Fangyi\OneDrive\文档\Claude\政策收集总结\sync_from_server.ps1"'
$trigger = New-ScheduledTaskTrigger -Daily -At '06:00'
Register-ScheduledTask -TaskName 'PolicyRadar-DailySync' `
  -Action $action -Trigger $trigger

# 验证
Get-ScheduledTask -TaskName 'PolicyRadar-DailySync'
```
