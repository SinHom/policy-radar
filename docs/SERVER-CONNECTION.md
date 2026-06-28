# 服务器连接模板（通用版）

> **用途**：在任何 Claude Code 会话窗口，只需让 Claude 读这份文档 + 配套 `SERVER-CONNECTION.local.md`，就能 SSH 连上你的服务器去**部署 / 运维任何项目**，不用每次重新说明。
>
> 本文件是**通用模板**（占位符），可入 git。
> 真实 IP / 私钥路径在 `docs/SERVER-CONNECTION.local.md`（不入 git）。

---

## 文件关系

```
docs/
├── SERVER-CONNECTION.md          ← 你正在看（通用模板，占位符）
├── SERVER-CONNECTION.local.md   ← 真实配置（不入 git，被 .gitignore 忽略）
└── .bashrc.template              ← Shell 别名模板（占位符，可入 git）
```

新项目使用时：
1. 复制 `SERVER-CONNECTION.local.md` 到 `docs/`（或新项目根的 `docs/`）
2. 填真实 IP / 私钥 / 用户
3. 让 Claude 读这两个文件即可

---

## 字段清单（复制 `SERVER-CONNECTION.local.md` 后要填的）

| 字段 | 占位符 | 说明 | 示例 |
|---|---|---|---|
| `{{SERVER_IP}}` | 公网 IP | 阿里云 / 腾讯云控制台看 | `43.155.161.54` |
| `{{SSH_PORT}}` | SSH 端口 | 默认 22，改过就写实际 | `22` |
| `{{SSH_USER}}` | SSH 用户 | 1Panel 默认 root | `root` |
| `{{KEY_NAME}}` | 私钥文件名 | 在 `~/.ssh/` 下 | `policy-radar-key` |
| `{{KEY_TYPE}}` | 私钥类型 | ED25519 / RSA / ECDSA | `ED25519` |
| `{{KEY_FINGERPRINT}}` | 私钥指纹 | `ssh-keygen -lf xxx.pub` | `SHA256:xxx` |
| `{{HAS_PASSPHRASE}}` | 是否有密码 | 是 / 否 | `否` |
| `{{SERVER_OS}}` | 操作系统 | Ubuntu / CentOS / Debian | `Ubuntu 22.04` |
| `{{SERVER_PROVIDER}}` | 云厂商 | 阿里云 / 腾讯云 / AWS | `阿里云轻量` |
| `{{PANEL_URL}}` | 1Panel / 宝塔 地址 | 1Panel 默认 10086 | `https://{{SERVER_IP}}:10086/1panel` |
| `{{PANEL_PORT}}` | 面板端口 | 1Panel 默认 10086 | `10086` |
| `{{PROJECTS_DIR}}` | 项目部署目录 | 1Panel 应用通常在 | `/opt` 或 `/www/wwwroot` |
| `{{ALIAS}}` | SSH 别名 | 你想给服务器起的短名 | `radar` / `aliyun` / `prod` |

---

## 给新会话 Claude 的最小启动指令

在任意 Claude Code 窗口粘贴：

```
读 {{PATH_TO_LOCAL_FILE}}（通常是 docs/SERVER-CONNECTION.local.md），
按 §"启动流程" 先 touch ~/.hushlogin 屏蔽 banner，然后按 §"常用操作" 跑一次连通性 + 资源检查，
只汇报服务器状态（系统 / 磁盘 / Docker），不改任何东西。
```

Claude 会：
1. 读真实配置
2. SSH 连上建 `.hushlogin`
3. 跑 `uname -a` / `df -h` / `docker ps` / `free -h`
4. 汇报：「服务器在线 / 系统 / 磁盘剩余 / Docker 已装/未装」

---

## 通用操作清单（Claude 复制即用）

> 替换 `{{ALIAS}}` 为你的 SSH 别名（或保留长形式 `ssh -i ~/.ssh/{{KEY_NAME}} ...`）。

### 连通性测试

```bash
ssh -i ~/.ssh/{{KEY_NAME}} -o ConnectTimeout=5 {{SSH_USER}}@{{SERVER_IP}} "echo connected && uname -a && cat /etc/os-release | head -3"
```

### 看资源

```bash
ssh -i ~/.ssh/{{KEY_NAME}} -o LogLevel=ERROR {{SSH_USER}}@{{SERVER_IP}} "df -h / && free -h && nproc && uptime"
```

### 看 Docker

```bash
ssh -i ~/.ssh/{{KEY_NAME}} -o LogLevel=ERROR {{SSH_USER}}@{{SERVER_IP}} "docker --version && docker compose version && docker ps -a"
```

### 看端口监听

```bash
ssh -i ~/.ssh/{{KEY_NAME}} -o LogLevel=ERROR {{SSH_USER}}@{{SERVER_IP}} "ss -tlnp 2>/dev/null || netstat -tlnp"
```

### 屏蔽 banner（**首次必做**，省 token）

```bash
ssh -i ~/.ssh/{{KEY_NAME}} -o ConnectTimeout=5 {{SSH_USER}}@{{SERVER_IP}} "touch ~/.hushlogin && echo done"
```

### 上传文件

```bash
scp -i ~/.ssh/{{KEY_NAME}} ./localfile {{SSH_USER}}@{{SERVER_IP}}:/tmp/
```

### 部署项目（通用 5 步）

```bash
# 1. 装基础工具（如果没有）
ssh ... "which git docker docker-compose || (apt update && apt install -y git curl)"

# 2. 装 Docker（如未装）
ssh ... "command -v docker >/dev/null || (curl -fsSL https://get.docker.com | sh)"

# 3. 拉代码
ssh ... "cd {{PROJECTS_DIR}} && git clone https://github.com/{{USER}}/{{PROJECT}}.git"

# 4. 起服务（具体看项目 docker-compose.yml）
ssh ... "cd {{PROJECTS_DIR}}/{{PROJECT}} && docker compose up -d --build"

# 5. 验证
ssh ... "curl -sf http://127.0.0.1:{{PORT}}/health"
```

### 看任意日志

```bash
ssh -i ~/.ssh/{{KEY_NAME}} -o LogLevel=ERROR {{SSH_USER}}@{{SERVER_IP}} "docker logs {{CONTAINER_NAME}} --tail 80 -t 2>&1" | grep -vE "^[█ *]+$|WeChat|qrcode"
```

---

## 安全红线

1. **真实配置绝不入 git** — `docs/SERVER-CONNECTION.local.md` 必须被 `.gitignore` 忽略
2. **私钥永不写入任何文档/commit/聊天** — 只写**路径**（如 `~/.ssh/{{KEY_NAME}}`）
3. **生产密钥**（API key / DB 密码 / 1Panel 登录密码）**不入日志**
4. **危险命令**（`docker volume rm` / `rm -rf` / `reboot` / `git reset --hard` / `git push --force`）必须先跟用户确认

---

## 关联文件

- `docs/SERVER-CONNECTION.local.md` — **真实配置**（不入 git，必备）
- `docs/.bashrc.template` — Shell 别名模板（可选，本地用）
- `docs/TOKEN-OPTIMIZATION.md` — SSH / Docker 操作 token 节省规则（项目内）

---

## 故障速查

| 现象 | 排查 |
|------|------|
| `Permission denied (publickey)` | `chmod 600 ~/.ssh/{{KEY_NAME}}`；私钥路径对吗 |
| 连接超时 | 阿里云安全组 → 入站 22 端口；1Panel 防火墙 → 放行 SSH |
| Banner 刷屏 | 服务器 `touch ~/.hushlogin`（见上） |
| Docker 命令找不到 | 服务器没装 Docker（先 `curl -fsSL https://get.docker.com \| sh`） |
| 磁盘满 | `df -h /` + `du -sh {{PROJECTS_DIR}}/* | sort -h | tail` |
| SSH 突然连不上 | 1Panel → 主机 → 控制台 / 救援模式 |