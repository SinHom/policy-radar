# 政策雷达 — 安全规范

> **本项目规则**：服务器将放公网，所有开发必须遵守本规范。
> 范围：所有 `/api/*` 端点、admin 后台、MCP 通道、爬虫、推送。
> 维护：每次新功能 PR 必须过本规范 + SECURITY-CHECKLIST.md。

---

## 一、鉴权 & 授权

### 1.1 API 鉴权分层

**当前所有 admin 写操作都已有 `require_admin` 鉴权（v0.2+）**。未来扩展对外 API 时，按下表分层：

| 端点类型 | 鉴权 | 当前状态 | 备注 |
|---|---|---|---|
| `/api/auth/login` | 公开 | ✅ | 失败锁定 10 次/15min |
| `/api/auth/verify`, `/logout` | Bearer token | ✅ | |
| `/api/subscriptions/*` PATCH/POST/DELETE | require_admin | ✅ | |
| `/api/companies/*` POST/PATCH | require_admin | ✅ | |
| `/api/policies/{id}` PATCH/DELETE | require_admin | ✅ | |
| `/api/sources/*` POST/PATCH/DELETE | require_admin | ✅ | |
| `/api/llm/*`, `/api/config/*` | require_admin | ✅ | |
| `/api/audit/*` | require_admin | ✅ | |
| `/api/push-logs`, `/api/dashboard/*` GET | require_admin | ✅ | |
| `/api/crawl/*`, `/api/policies/{id}/push` | require_admin | ✅ | |
| `/admin`, `/`, `/static/*` | 公开（仅 admin 鉴权） | ✅ | admin 单独鉴权 |
| MCP SSE 端点（未来对外） | API key | ❌ 待加 | MCP 接入外部 AI 工具时必加 |

### 1.2 API key 规范

- 格式：`prk_live_<32位随机>` / `prk_test_<32位随机>`
- **永远不要** hardcode 在代码或 .env（除部署时的初始化）
- 存 DB（SystemConfig 或独立 api_keys 表）
- 支持多 key（一公司一个 key，便于独立撤销）
- key 显示时脱敏：前 4 + `...` + 后 4
- key 泄漏后能立即撤销，刷新后无效

### 1.3 Admin 鉴权强化

- 密码强度：≥ 12 位，含大小写+数字+符号
- 默认 `admin / policy-radar-2026` **生产前必改**
- 失败登录 5 次锁定 15 分钟
- 2FA（TOTP）**Phase 2 必加**
- Session/Token TTL：24h → 2h（生产）
- IP 白名单：admin 端点只允许公司 IP
- 审计日志：所有 admin 操作留痕

---

## 二、网络 & 传输

### 2.1 强制 HTTPS

- ❌ **禁止生产用 HTTP**（明文传输 token / API key）
- 用 Let's Encrypt / 阿里云免费证书
- nginx 反代 + SSL termination
- 客户端 `Strict-Transport-Security: max-age=31536000; includeSubDomains`

### 2.2 CORS 白名单

```python
# ❌ 错
allow_origins=["*"]

# ✅ 对
allow_origins=[
    "https://admin.policy-radar.example.com",
    "https://mcp.policy-radar.example.com",
]
```

### 2.3 必加安全头（中间件）

```python
@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response
```

---

## 三、输入验证

### 3.1 通用规则

- **所有**外部输入（query/path/body/header）必须经过 Pydantic 验证
- 类型严格化（int 字段不接受 str）
- 长度限制（字符串 ≤ N 字符）
- 数字范围限制（page ≥ 0, limit ≤ 100）
- 枚举值白名单（push_channel 在 {mock, feishu, ...}）

### 3.2 SQL 注入

- ✅ 已用 SQLAlchemy ORM + 参数化查询
- ❌ **禁止** 拼字符串 SQL（`f"SELECT * WHERE id={user_input}"`）
- ❌ **禁止** 用 `text()` 拼字符串（用绑定参数 `:id`）

### 3.3 XSS

- admin.html 用 Vue 3 + `{{ }}` 文本插值（自动转义）
- ❌ **禁止** 用 `v-html`（除非内容是 100% 可信）
- ❌ **禁止** 后端返回 HTML 字符串（用纯数据，让前端渲染）

### 3.4 文件 / 路径

- ❌ **禁止** 接受用户输入拼文件路径
- 上传文件大小限制（≤ 10MB）
- 文件类型白名单（不是黑名单）

### 3.5 Request size

- 默认 FastAPI 无 body size 限制
- **加中间件**限制 body ≤ 1MB（admin 上传除外）

---

## 四、密钥 & 敏感数据

### 4.1 存储

- ✅ LLM API key 存 DB（SystemConfig），不写 .env
- ✅ Webhook secret 存 Subscription.push_config
- ❌ **禁止** 把 key 写 commit / 日志 / 错误消息
- ❌ **禁止** 在 API 响应里返回完整 key（脱敏后只显示前 4 后 4）

### 4.2 传输

- LLM key 走 HTTPS（不能明文）
- Webhook 接收方验证 HMAC 签名（防伪造）

### 4.3 日志脱敏

```python
def mask_key(k: str) -> str:
    if not k or len(k) < 8:
        return "***"
    return f"{k[:4]}...{k[-4:]}"

# ❌ 错
logger.info(f"using key: {api_key}")

# ✅ 对
logger.info(f"using key: {mask_key(api_key)}")
```

---

## 五、限流 & 防滥用

### 5.1 Rate Limit（每端点）

| 端点类型 | 限制 |
|---|---|
| `/api/auth/login` | 5 次 / 分钟 / IP |
| `/api/*` 写操作 | 60 次 / 分钟 / API key |
| `/api/*` 读操作 | 300 次 / 分钟 / API key |
| 爬虫触发 `/crawl/*` | 10 次 / 小时 / API key |
| `/api/llm/usage` | 60 次 / 分钟 / API key |

### 5.2 失败限流

- 登录失败 5 次 → 锁定该 IP 15 分钟
- API 错误率 > 50% → 临时降速

### 5.3 实现

- 用 `slowapi` 或自实现 token bucket
- 内存 LRU + Redis（生产）
- 429 响应带 `Retry-After: <秒数>`

---

## 六、日志 & 审计

### 6.1 必记日志

- 所有 admin 操作（login/logout/edit/delete/crawl/push）
- 所有 API key 使用（key_id + endpoint）
- 所有鉴权失败（IP + 路径 + 原因）
- 所有 5xx 错误（带 stack trace）

### 6.2 禁记日志

- 完整 API key
- 用户密码
- 用户手机号 / 身份证
- 公司商业机密

### 6.3 结构化日志

```json
{
  "ts": "2026-06-27T01:00:00Z",
  "level": "INFO",
  "event": "admin.login.success",
  "actor": "admin",
  "ip": "1.2.3.4",
  "ua": "Mozilla/5.0...",
  "request_id": "uuid"
}
```

### 6.4 审计日志

- 单独表 `audit_logs`（不与业务日志混）
- 至少保留 90 天
- 含 actor / action / target / before / after / ip / ua

---

## 七、依赖 & 镜像安全

### 7.1 依赖

- ✅ requirements.txt 已 pin 主要版本
- ❌ **禁止** 用 `*` 或 unpinned
- 每季度跑 `pip-audit` 检查 CVE
- CI 加 Dependabot 自动 PR

### 7.2 Docker 镜像

- 用官方 `python:3.11-slim`（已用）
- ❌ **禁止** 用 `latest` tag（必须 pin 版本）
- 加 `.dockerignore` 防 .env / data 被打入
- 非 root 用户运行（加 `USER` 到 Dockerfile）
- 加 `HEALTHCHECK`（已加）

### 7.3 .dockerignore 必含

```
.env
.env.*
data/
.git/
__pycache__/
*.pyc
*.log
.DS_Store
```

---

## 八、数据保护

### 8.1 PII 处理

- 公司名 / 行业 / 地区：可存
- webhook URL + secret：可存（用户自填）
- LLM API key：存 DB（脱敏显示）
- 推送内容（公司名）：可出现在推送内容里（用户授权）
- 联系方式（手机/邮箱）：**Phase 2 才加**（不在 MVP）

### 8.2 备份加密

- DB 备份到 OSS / S3，开启服务端加密
- 备份保留 30 天滚动
- 备份文件命名带日期 + 加密后缀

### 8.3 数据保留

- 推送日志保留 90 天后自动清理
- 公司订阅删除后 30 天软删除 → 永久删除
- 政策数据长期保留（合规需求）

---

## 九、运维安全

### 9.1 SSH

- ✅ 用 SSH key（已用）
- ❌ **禁止** 密码登录
- 改默认端口 22 → 高位端口
- fail2ban 防爆破

### 9.2 服务器加固

- 防火墙只开 80/443（前端）+ 必要管理端口
- 自动安全更新（unattended-upgrades）
- 磁盘满监控
- SSH 白名单 IP（公司 IP）

### 9.3 Docker

- 不使用 `--privileged`
- 加 `--read-only`（除必要目录）
- 加 `--cap-drop=ALL` + 必要 cap
- 加 `--security-opt=no-new-privileges`
- 加资源限制：`--memory=512m --cpus=1`

### 9.4 密钥管理

- 生产密钥不写 .env
- 用云厂商 KMS / Vault
- 定期轮换（季度）

---

## 十、API 设计安全

### 10.1 错误信息

```python
# ❌ 错：泄露内部信息
raise HTTPException(500, detail=f"DB error: {e}")

# ✅ 对：客户端只看到通用错误，详细只进日志
logger.exception("DB error: %s", e)
raise HTTPException(500, detail="internal server error")
```

### 10.2 状态码语义

- 401 = 未鉴权（不是 403，403 是已鉴权但无权限）
- 403 = 已鉴权但资源不可访问
- 404 = 资源不存在（**不要**用 404 替代 403，避免暴露资源存在性）
- 409 = 冲突（重复创建）
- 422 = 验证错误（Pydantic 422 默认）

### 10.3 HTTP 方法

- GET = 读（幂等，无副作用）
- POST = 创建
- PUT = 全量替换
- PATCH = 部分更新
- DELETE = 删除
- **GET 不能有副作用**（如不能 GET /api/sources/crawl）

### 10.4 CORS Preflight

- OPTIONS 必须返回正确 CORS 头
- 复杂请求（带自定义 header）必须支持 preflight

---

## 十一、合规要求（参考）

### 11.1 中国合规

- **ICP 备案**（公网域名必须）
- **网安备案**（涉及数据收集）
- **等保 2.0 三级**（如果涉及大量 PII）
- **用户协议 + 隐私政策**（必须有）
- **数据出境合规**（如用海外 LLM）

### 11.2 行业合规（参考）

- 数据安全法
- 个人信息保护法（PIPL）
- 网络安全法

---

## 十二、强制检查清单（每 PR / 发布）

详见 [SECURITY-CHECKLIST.md](SECURITY-CHECKLIST.md)

---

## 附录 A：密码强度策略

- admin 密码：≥ 12 位，含大小写+数字+符号
- API key：32 字符随机（base62）
- LLM API key：用户自管，我们不校验
- Webhook secret：用户自管

## 附录 B：应急响应

1. **发现 key 泄漏**：
   - 立即 revoke（更新 SystemConfig）
   - 改密钥（去 LLM 平台改）
   - 查 push_logs 看有没有异常推送
   - 通知用户

2. **发现越权访问**：
   - 查 audit_logs 找源头
   - 封 IP
   - 补鉴权漏洞

3. **DDoS**：
   - 启用 cloudflare / 阿里云高防
   - rate limit 收紧
   - 静态资源走 CDN

---

> 维护：Fangyi / 每次新功能 PR review
