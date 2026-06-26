# 政策雷达 — 上线 Checklist

> 状态：v0.2 demo 完成，距离正式给客户使用还差关键能力
> 评估时间：2026-06-27
> 完整度：~40%

---

## 🔴 阻塞上线（没这些不能给真用户用）

- [ ] **真 iLink bot_token 接入** — 现在所有推送走 mock，需要真实微信通道
  - [ ] 申请腾讯 iLink 平台 bot_token
  - [ ] 申请目标企业微信群 ID
  - [ ] 替换 `python/mock/mock_wechat.py` 为真实 iLink 客户端
  - [ ] E2E 测试：政策 → iLink → 群消息
- [ ] **HTTPS + 域名 + ICP 备案**
  - [ ] 申请域名（如 policy-radar.example.com）
  - [ ] 申请 ICP 备案（阿里云/腾讯云，约 7-15 工作日）
  - [ ] 配置 SSL 证书（Let's Encrypt / 阿里云免费证书）
  - [ ] nginx 反代到 8000 端口，加 HSTS
- [ ] **MCP server 端到端真测**
  - [ ] Claude Desktop 加载本 MCP server 跑一轮
  - [ ] Cursor 加载跑一轮
  - [ ] 飞书 / 企微 机器人 加载跑一轮
  - [ ] 13 个工具每个都至少被调用 1 次
  - [ ] 验证 tools/list 和 tools/call JSON schema 兼容
- [ ] **API 鉴权 + 速率限制**
  - [ ] 加 API key 机制（除 admin 外所有 `/api/*` 需要 key）
  - [ ] 加 rate limit（per-IP + per-key，每分钟/小时配额）
  - [ ] 加 audit log（谁在什么时候调了什么）
  - [ ] 限流触发时返回 429 + Retry-After

---

## 🟡 上线 1 周内必须补（不补会有运营风险）

- [ ] **法务合规**
  - [ ] 用户协议（terms of service）
  - [ ] 隐私政策（privacy policy）— 涉及企业数据 + 微信通道
  - [ ] 数据使用授权书
  - [ ] 客服/投诉渠道
- [ ] **数据备份**
  - [ ] 每日 SQLite 自动备份到 OSS / S3
  - [ ] 备份保留 30 天滚动
  - [ ] 备份可恢复性 E2E 测试
- [ ] **LLM 失败兜底**
  - [ ] Key 失效自动切换备用 key
  - [ ] LLM 超时降级（用历史摘要 + 标记未摘要）
  - [ ] 错误日志清晰可查
- [ ] **监控告警**
  - [ ] healthcheck 失败 → 飞书/企微 webhook 告警
  - [ ] 5xx 错误率超过 1% 告警
  - [ ] LLM 调用失败率超过 10% 告警
  - [ ] 爬虫失败率超过 30% 告警
  - [ ] 磁盘使用 > 80% 告警
- [ ] **LLM 摘要质量**
  - [ ] 人工抽检机制（每周抽 10 条，人工 review）
  - [ ] 高风险政策 flag（金额 > 100 万 / 截止日期 < 7 天）人工确认
  - [ ] 用户可标记"摘要不准确"反馈
- [ ] **文档**
  - [ ] 用户使用手册（如何订阅、查收、取消）
  - [ ] API 文档（OpenAPI 文档站，自动生成）
  - [ ] 接入指南（如何接入自己的系统）
  - [ ] 故障排查 FAQ

---

## 🟢 锦上添花（运营起来才需要）

- [ ] **多租户隔离**
  - [ ] 加 `org_id` 字段到所有表
  - [ ] 跨租户访问鉴权
  - [ ] 租户级 quota 管理
- [ ] **推送通道多元**
  - [ ] 飞书机器人（已有 webhook 框架，扩展即可）
  - [ ] 企微机器人
  - [ ] 邮件（SMTP）
  - [ ] 短信（阿里云/腾讯云短信）
- [ ] **实时推送**
  - [ ] 爬虫入库 → 立即推送给匹配订阅（不等到 schedule 时间）
  - [ ] 用户可订阅"突发政策"分类
- [ ] **运营数据看板**
  - [ ] 注册→订阅→收到推送→咨询转化漏斗
  - [ ] 客户活跃度（DAU / WAU / MAU）
  - [ ] 推送打开率 / 点击率（需要埋点）
  - [ ] 收入/订阅数据
- [ ] **生产级工程**
  - [ ] staging 环境（预发布验证）
  - [ ] E2E 自动化测试
  - [ ] 结构化 JSON 日志（带 request_id）
  - [ ] 性能压测报告
  - [ ] 多 uvicorn worker / gunicorn
  - [ ] Prometheus + Grafana 完善（已有基础）

---

## 📊 当前已有能力（✅）

### 核心
- 5 个政策源已 seed 完毕（58 个官方源：国家级 20 / 省级 21 / 市级 11 / 区级 6）
- 爬虫引擎（httpx + Playwright，支持反爬）
- LLM 摘要（MiniMax M3，可热切换其他模型）
- 政策库（SQLite，已建表，支持 PATCH/DELETE 编辑）
- 推送通道（mock 已通，可手动触发）

### MCP
- 13 个 MCP 工具已注册（setup / query / manage / admin / push）
- 7 个核心 + 5 个管理 + 1 个推送
- iLink mock 长轮询 + 消息路由

### 管理后台
- 7 个 tab：概览 / MCP 用户 / 订阅 / 政策库 / 政策源 / 推送历史 / LLM & 统计
- 登录鉴权（admin/admin_token）
- 订阅/公司/政策的完整 CRUD
- 手动推送测试
- 政策源启用/停用 + 标签筛选
- LLM token 消耗统计（按天/按模型/按用途）
- LLM 配置热切换（不重启）

### DevOps
- GitHub Actions 自动部署到 1Panel
- Docker Compose（5 服务）
- 阿里云 / 腾讯云镜像源
- 1Panel 管理（宝塔替代品）

---

## 🎯 推荐上线路线

### 阶段 1：MVP 商业化（2-3 周）
1. 真 iLink 接入（1-2 天）
2. 域名 + HTTPS + ICP（1 周，等审核）
3. MCP 端到端真测（1-2 天）
4. API 鉴权 + 限流（1-2 天）
5. 用户协议 / 隐私政策（半天）
6. 数据备份（半天）
7. LLM 兜底（1 天）

### 阶段 2：产品化（4-6 周）
- 多推送通道
- 实时推送
- 运营看板
- 多租户

### 阶段 3：规模化（持续）
- 数据驱动迭代
- 客户成功
- 商业化（按订阅收费）

---

## 📝 备注

- 当前所有数据存 SQLite，单机部署，够 1-10 客户用
- 客户 > 50 需切 PostgreSQL + 多实例
- 政策源 URL 列表见 `python/scripts/seed_official_sources.py`，可继续扩展
- LLM 用 MiniMax M3，可换其他（OpenAI/Claude/DeepSeek），已支持热切换
