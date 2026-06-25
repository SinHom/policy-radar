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
# 编辑 .env，填入真实的 MINIMAX_API_KEY
nano .env
```

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
