# 安全检查清单（每 PR / 发布前必过）

> 配合 [SECURITY.md](SECURITY.md) 用。每次发版前按此清单打勾。
> ✅ = 已检查并通过 / ⚠️ = 有问题需修复 / ➖ = 不适用

---

## 1️⃣ 鉴权 & 授权

- [ ] 所有 `/api/*` 写操作（POST/PUT/PATCH/DELETE）都有鉴权
- [ ] `/api/auth/login` 有失败锁定（5 次/15 分钟）
- [ ] Admin 密码已改默认（`policy-radar-2026` → 强密码）
- [ ] API key 用 `prk_live_*` / `prk_test_*` 格式
- [ ] API key 存 DB（不写 .env / commit）
- [ ] API key 响应里脱敏（前 4 + ... + 后 4）
- [ ] Token TTL 合理（admin 2h, API key 24h）
- [ ] 失败鉴权返回 401 + WWW-Authenticate 头

## 2️⃣ 网络 & 传输

- [ ] HTTPS 已部署（Let's Encrypt / 云厂商证书）
- [ ] HTTP 自动跳转 HTTPS
- [ ] HSTS 头开启（`max-age=31536000`）
- [ ] CORS 白名单（不是 `*`）
- [ ] 防火墙只开 80/443 + 必要管理端口
- [ ] SSH 改端口 + 禁用密码登录
- [ ] TLS 1.2+（禁 TLS 1.0/1.1）

## 3️⃣ 安全头

- [ ] `X-Content-Type-Options: nosniff`
- [ ] `X-Frame-Options: DENY`
- [ ] `X-XSS-Protection: 1; mode=block`
- [ ] `Referrer-Policy: strict-origin-when-cross-origin`
- [ ] `Content-Security-Policy` 合理（admin 用 inline script，需 `unsafe-inline` 或 nonce）
- [ ] `Strict-Transport-Security`（HTTPS 强制）

## 4️⃣ 输入验证

- [ ] 所有外部输入用 Pydantic 验证
- [ ] 字符串长度限制
- [ ] 数字范围限制
- [ ] 枚举值白名单
- [ ] 文件上传大小限制（≤ 10MB）
- [ ] 无 SQL 字符串拼接（用 ORM）
- [ ] 无 `v-html`（admin.html）
- [ ] 无 `dangerouslyAllowBrowser` 误用（前端 SDK）

## 5️⃣ 密钥 & 敏感数据

- [ ] `.env` 不入 git（已配 .gitignore）
- [ ] `.env.example` 列出所有变量但值留空
- [ ] LLM API key 存 SystemConfig
- [ ] Webhook secret 存 Subscription.push_config
- [ ] 响应里不返完整 key（脱敏）
- [ ] 日志里不打印 key
- [ ] 错误消息不泄露内部信息（DB 错误、stack trace）

## 6️⃣ 限流

- [ ] `/api/auth/login` ≤ 5 次/分钟/IP
- [ ] 写操作 ≤ 60 次/分钟/key
- [ ] 读操作 ≤ 300 次/分钟/key
- [ ] 爬虫触发 ≤ 10 次/小时/key
- [ ] 429 响应带 `Retry-After`
- [ ] IP 异常（>1000 次/小时）临时封禁

## 7️⃣ 日志 & 审计

- [ ] 所有 admin 操作记 audit log
- [ ] 所有鉴权失败记日志
- [ ] 所有 5xx 带 stack trace
- [ ] 日志不含 PII / 密码 / 完整 key
- [ ] 日志结构化（JSON）
- [ ] 审计日志保留 ≥ 90 天
- [ ] 日志不在前端展示

## 8️⃣ 依赖

- [ ] requirements.txt 全 pin 版本
- [ ] `pip-audit` 无高危 CVE
- [ ] Docker 镜像用 pinned tag（不用 `latest`）
- [ ] `.dockerignore` 排除 .env / data
- [ ] Dockerfile 加 `USER`（非 root）
- [ ] 无 unused dev 依赖

## 9️⃣ 数据保护

- [ ] 备份加密（OSS 服务端加密 / S3 SSE）
- [ ] 备份保留 30 天滚动
- [ ] 推送日志 90 天后清理
- [ ] 软删除 → 硬删除策略
- [ ] DB 不放公网（内网或限制访问）
- [ ] 敏感字段考虑加密存储

## 🔟 运维

- [ ] 服务器自动安全更新
- [ ] 磁盘 / 内存 / CPU 监控
- [ ] Docker 加 `--memory` / `--cpus` 限制
- [ ] Docker 加 `--cap-drop=ALL`
- [ ] Docker 加 `--security-opt=no-new-privileges`
- [ ] fail2ban / 防火墙防爆破
- [ ] 备份定期演练恢复

## 1️⃣1️⃣ 合规

- [ ] ICP 备案完成
- [ ] 网安备案（如需要）
- [ ] 用户协议 + 隐私政策上线
- [ ] 客服 / 投诉渠道
- [ ] 第三方 LLM 数据使用合规
- [ ] 数据保留 / 删除策略文档

## 1️⃣2️⃣ Admin 后台

- [ ] 改默认 admin 密码
- [ ] Admin 端点加 IP 白名单
- [ ] Session / Token 2h 过期
- [ ] 操作留 audit log
- [ ] 失败登录锁定
- [ ] 2FA（Phase 2）

## 1️⃣3️⃣ MCP 通道

- [ ] MCP 端点加 API key 鉴权
- [ ] MCP 错误不泄露内部信息
- [ ] 飞书 webhook 启用签名校验
- [ ] 通用 webhook 启用 HMAC 签名
- [ ] iLink（生产）bot_token 不入代码

## 1️⃣4️⃣ 爬虫

- [ ] 爬虫请求加 User-Agent
- [ ] 爬虫 IP 不暴露
- [ ] 反爬策略（UA/代理/限速）
- [ ] 爬虫只爬授权数据源
- [ ] 爬虫 robots.txt 遵守

## 1️⃣5️⃣ 部署

- [ ] 部署前过本清单全部 ✅
- [ ] 部署后 smoke test（curl /health）
- [ ] 部署日志归档
- [ ] 旧版本镜像保留 7 天可回滚
- [ ] 数据库迁移备份

---

## 严重级别判定

- ❌ **阻断上线**：1️⃣2️⃣3️⃣4️⃣5️⃣7️⃣ 任一 ⚠️
- ⚠️ **限期修**：6️⃣8️⃣9️⃣10️⃣ 任一 ⚠️（1 周内）
- 📋 **可优化**：1️⃣1️⃣1️⃣2️⃣1️⃣3️⃣1️⃣4️⃣1️⃣5️⃣（持续）

---

## 应急联系

- 安全事件：立即通知 Fangyi
- 渠道：飞书群 / 邮件
- 流程：发现 → 通知 → 评估 → 处置 → 复盘

---

> 维护：Fangyi / 每次发版前 review
