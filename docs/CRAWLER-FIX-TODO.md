# 爬虫源修复清单（剩余待修）

> 上次会话进度：404 已修、系统已固化（禁用 46 源、max_new=10）、12 源可用、其中 7 源能出数据。
> 本文档列**尚未修好**的源 + 通用问题，供下次继续。

## 当前状态总览

DB `policy_sources` 共 58 源，已禁用 46（38 无配置 + 8 重复/下线），**保留 12 源 enabled**：

```
city_bj_gxj  city_sz_fgw  city_sz_gxj  city_sz_hrss  city_sz_kjj
nat_gov_cn   nat_miit     nat_mof      nat_most
prov_gd_kjt  prov_gd_szr  prov_gd_tax
```

**能出数据的 7 源**（已验证 list→detail→去重→入库链路通）：
`city_bj_gxj`、`city_sz_kjj`、`nat_mof`、`nat_most`、`prov_gd_szr`、`prov_gd_tax`、`nat_gov_cn`

> 其中 `city_sz_kjj`/`nat_mof`/`prov_gd_szr` 上次实测入库新政策 9 条；其余 `dup>0` 说明历史已入库、去重正常。

---

## 待修源清单（5 个，list=0 或选择器有问题）

| source_id | 当前状态 | 失败原因 | 修法 | 涉及文件 | 难度 |
|---|---|---|---|---|---|
| city_sz_fgw | Playwright list=0 | Page.goto Timeout 30s | 调大 Playwright timeout；确认 `.news_list li` 选择器；fgw.sz.gov.cn 可能 JS 慢渲染，加大 networkidle 等待 | fetcher.py、city_sz_fgw.json | 中 |
| city_sz_gxj | Playwright list=0 | URL 错（`zfxxgkmlgkml` 重复） | 去 gxj.sz.gov.cn 找正确的政策列表 URL；render_js=true 已设（绕 SSL） | city_sz_gxj.json | 中 |
| city_sz_hrss | httpx 404 | 旧 URL 没改 | 改 list_url 为 `https://hrss.sz.gov.cn/xxgk/zcfgjjd/zcfg/index.html` + render_js=true（JS 渲染）；选择器要看 Playwright 渲染后 DOM 重写 | city_sz_hrss.json | 中高 |
| nat_miit | Playwright list=0 | 纯 JS 搜索 API，URL 是 art 文章页非列表 | 找正确列表页（`/zwgk/zcwj/wjfb/`）；列表靠 JS 调 `/search/search-front-server` API 加载，需逆向 API 或 Playwright 渲染后抓 | nat_miit.json、可能 fetcher/engine | 高 |
| prov_gd_kjt | list=74 太宽泛 | `ul li` 抓到江苏站友情链接 | 看 gdstc.gd.gov.cn 实际 HTML，收窄 item 选择器（限定列表容器 class，排除友情链接区） | prov_gd_kjt.json | 低中 |

### 各源已知信息（agent 调研结果，选择器是推断值，部署前需 curl 实际 HTML 确认）

- **city_sz_fgw**：新 URL `https://fgw.sz.gov.cn/zwgk/zcjzcjd/zc/index.html`，候选选择器 `.news_list li` / `span.date::text`，SSR（但 Playwright 超时，可能实际需 JS 或站点慢）
- **city_sz_gxj**：当前 URL `https://gxj.sz.gov.cn/zwgk/xxgkml/zfxxgkml/zfxxgkmlgkml/index.html` 明显错误（zfxxgkmlgkml 重复），需重找
- **city_sz_hrss**：新 URL `https://hrss.sz.gov.cn/xxgk/zcfgjjd/zcfg/index.html`，agent 确认是 JS 动态渲染（静态 HTML 列表为空，分页 javascript:void(0)），必须 Playwright + 渲染后选择器
- **nat_miit**：列表页 `/zwgk/zcwj/wjfb/` 会 JS 重定向到 `search/wjfb.html`，结果靠 AJAX 调 `/search/search-front-server` 加载；子栏目页用 `unitbuild.js` 从 `/api-gateway/jpaas-publish-server/...` 加载。传统 CSS 选择器抓不到，必须 Playwright 或逆向 API
- **prov_gd_kjt**：URL `http://gdstc.gd.gov.cn/zwgk_n/zcfg/gfwj/index.html` 正确，SSR，httpx 能连；问题是 `ul li` 太宽泛匹配 74 个（含友情链接如 kxjst.jiangsu.gov.cn）

---

## 通用待修项（影响多个源）

### 1. detail timeout 调优（优先级高）
- **现象**：Playwright `Page.goto Timeout 30000ms` + httpx `ReadTimeout`，导致 `city_sz_kjj` 9 个 detail 失败、`prov_gd_szr` 5 个失败
- **修法**：fetcher.py 调大 Playwright timeout（`self.timeout`，当前 Page.goto 用 `self.timeout*1000`）+ httpx timeout；或 detail 失败时跳过不阻塞
- **涉及**：`python/crawlers/fetcher.py`（_fetch_playwright 的 timeout、_fetch_httpx 的 timeout）、`python/app/config.py`（crawler timeout 配置）
- **难度**：低

### 2. 选择器收窄（抓到错链接）
- **现象**：`prov_gd_szr`/`prov_gd_kjt` 的 `ul li` 太宽泛，detail 抓到 `hrss.tj.gov.cn`（天津）、`kxjst.jiangsu.gov.cn`（江苏）等友情链接
- **修法**：逐源 curl 实际 list HTML，用更精确的 item 选择器（限定列表容器 class，排除导航/友情链接区）
- **涉及**：各 spider json 的 `list_selectors.item`
- **难度**：低中

### 3. 重复源文件残留（清理项，非功能）
- **现象**：服务器容器 `/app/python/crawlers/spiders/` 残留 `national_*.json`（4 个，旧选择器全 0），DB 的 `national_*` source 已禁用，文件无害但冗余
- **修法**：删 `national_gov_cn/miit/mof/most.json`（删文件需用户确认，红线）
- **涉及**：服务器 `/opt/policy-radar/python/crawlers/spiders/` + 容器内同路径

---

## 已完成的修复（背景，别重做）

1. **404 修复**：`python/app/web/admin.html` 的爬取按钮（1436 行 crawlAll、1459 行 crawlOne）请求路径补 `/api` 前缀（baseURL 为空，原路径漏前缀 → 404）
2. **命名对齐**：`national_{gov_cn,miit,mof,most}.json` 重命名为 `nat_*` 对齐 DB seed 的 `nat_` 前缀（seed_official_sources.py 用 `nat_`，spider 文件原用 `national_`）
3. **SSL 方案**：httpx 改 SSL context（CERT_NONE+SECLEVEL=0）**无效**（BAD_ECPOINT 是 OpenSSL3 椭圆曲线问题，非证书）；改用 Playwright `ignore_https_errors=True` 绕过。`city_sz_gxj/sz_gxj/fgw/kjj` 已切 `render_js=true`
4. **禁用 46 源**：38 无配置 + 8 重复/下线（`city_sz_tax` 下线、`gov_cn`/`sz_gxj`/`gd_kjt`/`national_*` 重复），DB `UPDATE policy_sources SET enabled=0`
5. **max_new 50→10**：`python/crawlers/engine.py:208` `run_crawler` 默认 `max_new_per_source`，提速 crawl/all
6. **agent 调研的新 URL/选择器已写入**：`city_sz_fgw/kjj`、`prov_gd_szr/tax`、`city_bj_gxj`、`prov_gd_kjt`、`gd_kjt`、`nat_gov_cn/mof/most`（部分选择器是推断值，见上）

---

## 关键文件 + 命令速查

### 文件
- 爬虫引擎：`python/crawlers/engine.py`（crawl_source / run_crawler / load_spider_config）
- 获取层：`python/crawlers/fetcher.py`（_fetch_httpx / _fetch_playwright，SSL_CONTEXT 已加但无效）
- spider 配置：`python/crawlers/spiders/*.json`（list_url + list_selectors + render_js）
- 爬取接口：`python/app/api/routes.py`（POST /api/crawl/all、/api/crawl/{source_id}）
- 前端按钮：`python/app/web/admin.html:1436`（crawlAll）

### 服务器
- SSH：`ssh -i ~/.ssh/policy-radar-key root@43.155.161.54`（已 `~/.hushlogin`）
- 项目目录：`/opt/policy-radar`
- 容器：`policy-radar-app`（docker compose，volumes 只挂 `./data`，源码改动要 `docker compose up -d --build app`）

### 验证命令（下次直接用）

```bash
# 单源快速验证选择器匹配数（不抓 detail，快）—— 最先跑这个定位问题
ssh -i ~/.ssh/policy-radar-key root@43.155.161.54 'docker exec -i policy-radar-app python' <<'PYEOF'
import asyncio,json,glob
from python.crawlers.fetcher import get_fetcher
from python.crawlers.parser import parse_html,extract_all
async def m():
    f=get_fetcher()
    for sid in ["city_sz_fgw","city_sz_gxj","city_sz_hrss","nat_miit","prov_gd_kjt"]:
        d=json.load(open(f'/app/python/crawlers/spiders/{sid}.json'))
        try:
            r=await f.fetch(d['list_url'],render_js=d.get('render_js',False))
            n=len(extract_all(parse_html(r.html),d.get('list_selectors',{}).get('item','')))
            print(f"{sid:16} items={n}")
        except Exception as e:
            print(f"{sid:16} ERR={str(e)[:60]}")
asyncio.run(m())
PYEOF

# 单源真入库验证（max_new=2，快）
ssh -i ~/.ssh/policy-radar-key root@43.155.161.54 'docker exec -i policy-radar-app python' <<'PYEOF'
import asyncio
from python.crawlers.engine import run_crawler
async def m():
    for r in await run_crawler(["city_sz_fgw"], max_new_per_source=2):
        print(r.source_id, "L=",r.total_listed,"new=",r.new_crawled,"err=",r.errors, r.error_messages[:1])
asyncio.run(m())
PYEOF

# 看某源实际 HTML 结构（精调选择器用）
ssh -i ~/.ssh/policy-radar-key root@43.155.161.54 'docker exec -i policy-radar-app python' <<'PYEOF'
import asyncio
from python.crawlers.fetcher import get_fetcher
async def m():
    r=await get_fetcher().fetch("http://gdstc.gd.gov.cn/zwgk_n/zcfg/gfwj/index.html", render_js=False)
    print(r.html[:3000])  # 看列表区 HTML，找精确 item class
asyncio.run(m())
PYEOF

# 改 spider json 后热更容器（json 是 read_text 动态读，不用 rebuild）
scp -i ~/.ssh/policy-radar-key python/crawlers/spiders/XXX.json root@43.155.161.54:/opt/policy-radar/python/crawlers/spiders/
ssh -i ~/.ssh/policy-radar-key root@43.155.161.54 "docker cp /opt/policy-radar/python/crawlers/spiders/XXX.json policy-radar-app:/app/python/crawlers/spiders/"

# 改 fetcher.py/engine.py（代码，要 rebuild）
scp -i ~/.ssh/policy-radar-key python/crawlers/fetcher.py root@43.155.161.54:/opt/policy-radar/python/crawlers/
ssh -i ~/.ssh/policy-radar-key root@43.155.161.54 "cd /opt/policy-radar && docker compose up -d --build app"
```

---

## 下次继续的建议顺序

1. **detail timeout 调优**（低难度、影响多源 detail 成功率）—— 先做这个，city_sz_kjj 等的 detail 失败能减
2. **prov_gd_kjt 选择器收窄**（低中，URL 已对，只差精确 item）—— curl 看 HTML 调选择器
3. **city_sz_hrss**（改新 URL + render_js=true + 渲染后选择器）
4. **city_sz_gxj**（找正确 URL）
5. **city_sz_fgw**（timeout 调大后看是否还超时）
6. **nat_miit**（最难，逆向 JS API，放最后，不成可禁用）

每改一个 spider json → docker cp 热更 → 单源验证（上面命令）→ 确认 new>0 再下一个。
代码改动（fetcher/engine）→ scp + rebuild。
