# 爬虫源状态（2026-07-09 更新 v0.3）

> v0.1 "404 已修、12 源可用" → v0.2 "97 源、60 有数据、500 条政策" → **v0.3 "415 启用源、153 有数据、771 条政策、617 .md"**

## 当前状态总览（v0.3）

| 维度 | 数量 |
|------|------|
| DB 政策总数 | 771 |
| 正文覆盖率 | ~93%（garbage filter 漏网 215 条） |
| 启用信源（policy_sources.enabled=1） | 415 |
| 有数据信源 | 153 |
| 零数据信源 | 262 |
| 导出 .md 文件 | 617（`../policies_md/`，仅 2026 年至今） |
| 标签分类 | 政策文件(127) + 通知(78) + 公告(52) + 文旅(43) + 惠企(9) + 解读(5) |
| v0.3 新增 spider | 18 个国家级（含 gongbao/惠企/省文旅/秦文旅/省知产 + 14 部委） |

## v0.3 重要更新

- **RSSHub 订阅源链路已上线**：4 个 FastAPI 端点（`/feed`/`/article`/`/markdown`/`/opml`），可直接当 RSS 源订阅
- **每日 5am 服务器 cron** + **每日 6am Windows 同步**（见 DEPLOY.md）
- **64 个源 region 回填** + **322 个 published_at 回填**（2026 年至今）
- **export_policies_md.py 优化**：去除 sitemap/留言须知等过严 garbage 规则；新增"首页/无标题"过滤；正文阈值从 100 字符降至 50
- **engine.py 优化**：跳过 javascript:void(0) URL；跳过 list/index/col 等列表页 URL
- **nat_mee 修复**：列表选择器从 `.list li` 改为 `a[href*='t20']`，加 `xxgk01` 子路径

## 零数据源处理（v0.3 进展）

v0.2 提到的 37 个零数据源，在 v0.3 中有部分已修复（通过新选择器 + dedup 逻辑）：
- ✅ 河北省：公安厅(gat)、政府·政策文件(gov_zk) — 改 list_url 后有数据
- ✅ 河北省发改委(fgw) — 已运行
- ⚠️ 河北省：卫健委、商务厅、住建厅、教育厅、文物局、科技厅 — 仍需定制 selector
- ⚠️ 秦皇岛市：交通局、住建局、农业农村局、发改委、市监局、政府、生态环境局、科技局、财政局
- ⚠️ 深圳：科创委、税务局

具体待修清单（v0.3 仍然零数据）：
- 河北省：卫健委(jyt)、商务厅(swj)、住建厅(zfcxjst)、教育厅(jyt 不通)、文物局、生态环境厅(sthjt 站点已下线)
- 秦皇岛市：交通局(jtj，部分 OK)、住建局、农业农村局、发改委、市监局、政府、生态环境局、科技局、财政局

## 推荐修复路径（v0.3）

### 短期（投入产出比最高）
1. **修 18 个新增 spider 的 list_url**：v0.3 新增的 18 个国家级 spider 实际产出依赖 list_url 正确性
2. **每个新 spider 跑一次 `python -m crawlers --source <sid> --max-new 20`** 验证
3. **导出时 garbage filter 调严**：v0.3 还有 215 条被过滤（占 27%），可减少过严规则

### 长期
- 262 个零数据源逐个定制 CSS selector（工作量 ~50 小时）
- 或全部切到 RSSHub 模式（`rsshub_repo/` 已有 200+ 路由）

## 关键脚本（v0.3）

| 脚本 | 用途 |
|------|------|
| `backfill_content.py` | Playwright 批量回填空正文，多选择器 fallback |
| `backfill_httpx.py` | httpx 轻量回填（服务器用，但 403 多） |
| `probe_content_types.py` | 自动探测通知公告/政策解读/公示子页面 |
| `fix_zero_sources.py` | 批量修复：创建缺失 config + 首页→通知公告 + render_js |
| `generate_opml.py` | 生成 OPML + JSON 信源索引（导入 RSS 阅读器） |
| `export_policies_md.py` | 政策原文导出为 Markdown（v0.3 含首页过滤） |
| `auto_tag.py` (新) | 标题关键字自动打标签（惠企/文旅/政策文件/公告/通知/解读） |

## 关键命令（v0.3）

```bash
# 爬取全部启用源
python -m crawlers --all

# 爬取单个源
python -m crawlers --source <source_id> --max-new 20

# 回填空正文
python -m scripts.backfill_content --limit 100

# 导出全部政策为 .md (v0.3 已修首页/无标题过滤)
python -m scripts.export_policies_md --output ../policies_md

# 生成 RSS 订阅文件
python -m scripts.generate_opml --output ../feeds

# 自动打标签
python -m scripts.auto_tag

# 探测内容类型子页面
python -m scripts.probe_content_types --dry-run

# RSSHub 端点验证（服务器 8000 端口）
curl -s http://43.155.161.54:8000/policy-radar/feed?limit=3
```