# 河北/秦皇岛政策爬虫技术总结

> **项目**: policy-radar v0.3
> **时间**: 2026-07-06 ~ 2026-07-09 (12 轮)
> **服务器**: 腾讯云 43.155.161.54 (Ubuntu 22.04 + Docker)
> **目标**: 补全河北省/秦皇岛市所有政府委办局的政策、公告、通知爬取
> **最终成果**: 415 启用源，771 条政策入库，617 篇真政策 .md（仅 2026 年至今）

---

## 一、整体架构

```
                    ┌──────────────────────────────────────────┐
                    │  腾讯云 43.155.161.54                     │
                    │                                          │
  ┌──────────┐      │  ┌─────────────────────┐                 │
  │  cron    │──────┼─▶│  policy-radar-app   │                 │
  │ 8/14/20  │      │  │  (Python 爬虫)       │                 │
  └──────────┘      │  └──────────┬──────────┘                 │
                    │             │                             │
                    │             │ QHD 域                     │
                    │             ▼                             │
                    │  ┌─────────────────────┐                 │
                    │  │  policy-radar-rsshub│  172.18.0.4    │
                    │  │  (Node 代理)        │  8888 端口    │
                    │  └──────────┬──────────┘                 │
                    │             │                             │
                    └─────────────┼─────────────────────────────┘
                                  │
                                  ▼
                  ┌─────────────────────────────┐
                  │  qhd.gov.cn / hebei.gov.cn   │
                  │  (政府站)                    │
                  └─────────────────────────────┘
```

- **policy-radar-app**: 主爬虫容器，跑 Playwright + httpx 抓取
- **policy-radar-rsshub**: 原本是 RSSHub 镜像（但实际 gov 路由空），后被复用为**HTTP 代理服务器**（172.18.0.4:8888）
- **cron**: 8/14/20 点自动跑全部 enabled 源
- **DB**: SQLite (`/app/data/policy_radar.db`)，表 `policy_sources` + `policies`
- **本地导出**: `data/exports/policies/{region}/{department}/{year}/`

---

## 二、爬虫 fetcher 的 5 个核心机制

`python/crawlers/fetcher.py` 是所有抓取的核心，按以下顺序处理：

### 1. IPv4 强制解析
容器默认走 IPv6 优先（happy-eyeballs），但 IPv6 不可达会卡 60s。强制 IPv4：
```python
infos = socket.getaddrinfo(host, p.port or 80, socket.AF_INET, socket.SOCK_STREAM)
if infos:
    ip = infos[0][4][0]
    url_to_fetch = f"{p.scheme}://{ip}{p.path}"
    headers["Host"] = host
```

### 2. QHD/河北域代理转发
`*.qhd.gov.cn / *.hebei.gov.cn` 走 RSSHub 容器内 Node HTTP 代理：
```python
from urllib.parse import urlparse as _up
_host = _up(url).hostname or ''
if _host.endswith('qhd.gov.cn') or _host.endswith('hebei.gov.cn') or \
   _host.endswith('hebaudit.gov.cn') or _host.endswith('chinatax.gov.cn'):
    import urllib.parse as _u
    actual_url = f"http://172.18.0.4:8888/fetch?url={_u.quote(url, safe='')}"
```

**为什么必须走代理**：腾讯云 IP 段被政府站防火墙白名单直接拒连，连 RSSHub 容器的 IP 段**不在**黑名单里（实测 RSSHub 容器能访问 qhd/hebei 站）。

### 3. 完整 Chrome 指纹头（绕 NWAF WAF）
```python
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://www.baidu.com/",  # 注意: 用百度,不用 google, 政府站拒 google referer
    "Cache-Control": "max-age=0",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}
```

**关键点**：
- Referer 用 **baidu.com** 而非 google.com（政府站拒 google referer）
- 完整 Sec-Ch-Ua* 头（Chromium 120 真实头）
- 这个头让 qhd 站把请求当作"真实 Chrome 浏览器"处理

### 4. Playwright 代理（v5/v6 最终方案）
最初用 `browser.new_context(proxy={...})`，但容器内**不生效**。最终改用：
```python
# 直接让 Playwright 访问代理 URL（而不是访问真实 URL + 走代理）
_pw_url = url
if _h3.endswith("qhd.gov.cn") or _h3.endswith("hebei.gov.cn"):
    import urllib.parse as _u4
    _pw_url = f"http://172.18.0.4:8888/fetch?url={_u4.quote(url, safe='')}"
resp = await page.goto(_pw_url, wait_until="commit", timeout=...)
```

配合 `final_url = url`（用原始 URL 而非代理 URL，让 `urljoin` 拼接详情页用对的域名）。

### 5. 内容质量过滤（`export_policies_md.py`）
```python
_MIN_CONTENT_LENGTH = 100  # 字符
_MIN_CHINESE_RATIO = 0.15   # 中文占比
_GARBAGE_PATTERNS = ["403 Forbidden", "404 Not Found", "云防护", "拒绝执行", ...]
```

### 6. 正文图片抓取 + VLM caption（`parser.py` / `engine.py`，2026-07-15）

详情页正文提取从 `extract_by_selector`（纯文本，img 全丢）改为 `extract_content_html`，保留 `<img>` HTML 进 `raw_content`，让下游 markdownify 转成 `![](url)` 供 WeKnora 图片索引：

```python
# engine.py:206 详情抓取
detail_content = extract_content_html(
    detail_soup, detail_selectors.get("content", "body"),
    base_url=detail.final_url or url,   # 补全相对 src 为绝对 URL
    caption_images=True,                 # 调 MiniMax-VL 生成 caption
)
```

**`extract_content_html` 流程**：
1. CSS 选择器定位正文容器（支持逗号分隔备选），找不到回退 `body`
2. 删 `script/style/nav/footer/header/form/button`
3. 相对路径图片补全为绝对 URL（政府站多 `../../../images/x`）
4. `_caption_images`：下载每张绝对 URL 图（httpx，带 Referer 绕 gov 防盗链，限 5 张/页）-> 调 MiniMax-VL-01 生成中文 caption -> 写 `<img alt=caption>`

**MiniMax-VL-01 调用**（`python/ai/vlm_client.py`）：
- 端点 `https://api.minimaxi.com/anthropic/v1/messages`（**Anthropic Messages API，非 OpenAI 兼容端点**，OpenAI 兼容的 `/v1/chat/completions` 报 unknown model）
- 复用 `MINIMAX_API_KEY`，新增 `MINIMAX_VLM_MODEL`（默认 `MiniMax-VL-01`）+ 可选 `MINIMAX_VLM_BASE_URL`
- 失败降级返回空串（不阻塞抓取，保留原 src 无 caption）
- 无 `MINIMAX_API_KEY` 时整个 caption 流程 no-op

**为什么走应用层 VLM 而非 WeKnora 内部 VLM**：WeKnora 租户 10000 的 VLM 模型是 weknoracloud 内部服务（无 credentials），image_resolver.go 的 `ResolveRemoteImages` 跳过 http(s) 图片不下载。应用层把 caption 注入 markdown alt text，灌入 WeKnora 后 caption 进 chunk 文本被向量索引，绕过 WeKnora 内部 VLM 链路。WeKnora 部署与配置细节见项目根 `CLAUDE.md`「正文图片抓取 + VLM caption 增强」段。

---

## 三、RSSHub 容器内的 HTTP 代理

`policy-radar-rsshub` 容器原本是 RSSHub 镜像，但 gov 路由是空的（`/api/routes` 报 NotFoundError）。**复用为 HTTP 代理**：

文件：`/tmp/universal_proxy.mjs`（部署在 RSSHub 容器内）

```javascript
import http from 'node:http';
import { URL } from 'node:url';

const PORT = 8888;

const server = http.createServer(async (req, res) => {
    const reqUrl = new URL(req.url, `http://localhost:${PORT}`);
    
    let targetUrl = null;
    if (reqUrl.pathname === '/fetch') {
        targetUrl = reqUrl.searchParams.get('url');
    } else if (reqUrl.pathname.startsWith('/proxy/')) {
        targetUrl = decodeURIComponent(reqUrl.pathname.substring(7));
    }
    
    if (!targetUrl) {
        res.writeHead(404, {'Content-Type': 'text/plain'});
        res.end('Not Found. Use /fetch?url=<url>');
        return;
    }
    
    try {
        const resp = await fetch(targetUrl, {
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Referer': 'https://www.baidu.com/',
                'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                // ... 完整 Chrome 120 指纹
            },
            signal: AbortSignal.timeout(25000),
        });
        const text = await resp.text();
        res.writeHead(200, {
            'Content-Type': 'text/html; charset=utf-8',
            'X-Proxy-Status': String(resp.status),
            'X-Proxy-Elapsed': String(Date.now() - startTime),
            'X-Proxy-Size': String(text.length),
        });
        res.end(text);
    } catch (e) {
        res.writeHead(502, {'Content-Type': 'text/plain'});
        res.end(`Proxy error: ${e.message}`);
    }
});

server.listen(PORT, '0.0.0.0', () => {
    console.log(`[universal-proxy] listening on 0.0.0.0:${PORT}`);
});
```

**启动**（RSSHub 容器内）：
```bash
# RSSHub 容器镜像里 node 是 node24, 无 pkill/disown
for p in /proc/[0-9]*/cmdline; do
  c=$(cat $p 2>/dev/null | tr "\0" " ")
  if echo "$c" | grep -q "node /tmp/universal_proxy"; then
    pid=$(basename $(dirname $p))
    kill -9 $pid 2>/dev/null
  fi
done
sleep 2
(nohup node /tmp/universal_proxy.mjs > /tmp/proxy.log 2>&1 &)
sleep 3
cat /tmp/proxy.log
```

**关键技巧**：`for p in /proc` 是因为容器里**没有 pkill/disown/ps 命令**，只能用 `/proc` 遍历找 node 进程。

---

## 四、56 个信源完整清单

### 4.1 秦皇岛（35 个 source_id）

| source_id | 部门 | 状态 | 政策数 | list_url | 关键点 |
|---|---|---|---|---|---|
| `city_qhd_lywgj` | 文旅局 | ✅ 成功 | 12 | `http://lywgj.qhd.gov.cn/home/list?code=MTA2&pcode=MTA0` | 政策文件 (base64 code=MTA2) |
| `city_qhd_lywgj_zcjd` | 文旅局·政策解读 | ✅ 成功 | 5 | `http://lywgj.qhd.gov.cn/home/list?code=MTA1&pcode=MTA0` | 政策解读 (MTA1) |
| `city_qhd_jtj` | 交通局 | ✅ 成功 | 6 | `http://jtj.qhd.gov.cn/home/list?pcode=emNmZw&code=emNmZ183` | 法律法规 (emNmZ183) |
| `city_qhd_jtj_tzgg` | 交通局·通知公告 | ✅ 成功 | 3 | `http://jtj.qhd.gov.cn/home/list?pcode=enc&code=endfMQ` | 通知公告 (endfMQ) |
| `city_qhd_gxj` | 工信局 | ✅ 成功 | 5 | `http://gxj.qhd.gov.cn/home/list/?code=NDg0NjI2MTYwOTE4&pcode=MDE3NjMxOTgyNTE2` | 政策法规 (NDg0...) |
| `city_qhd_swj` | 商务局 | ✅ 成功 | 3 | `http://swj.qhd.gov.cn/home/list/?code=MjE&pcode=MTAx` | 政策法规 |
| `city_qhd_fgw` | 发改委 | ✅ 成功 | 2 | `http://fgw.qhd.gov.cn/home/list/?code=Njc2MTAyMjc0NzM2&pcode=MDE3NTkzNDM3MjA2` | 发改委政策栏目 |
| `city_qhd_zjj` | 住建局 | ✅ 成功 | 1 | `http://zjj.qhd.gov.cn/home/xzzfgstablist?code=NTM5&pcode=NTc2` | 行政规范性文件 |
| `city_qhd_jyj` | 教育局 | ✅ 成功 | 1 | `http://jyj.qhd.gov.cn/home/list/?code=NjA0&pcode=MDE3NjMxOTgyNTE2` | 政策解读栏目 |
| `city_qhd_xzspj` | 数据和政务服务局 | ⚠️ 启用但 0 | 0 | `http://xzspj.qhd.gov.cn/home/list/?code=NjI5&pcode=MDE3NjMxOTgyNTE2` | 走代理后仍 0，可能有 WAF 漏 |
| `city_qhd_wjw` | 卫健委 | ❌ 禁用 | 0 | `http://wjw.qhd.gov.cn/` | 死站 + JS 反爬严，Playwright 0 链接 |
| `city_qhd_zyghj` | 自然资源局 | ❌ 禁用 | 0 | `http://zyghj.qhd.gov.cn/` | DNS 解析失败（域名不存在） |
| `city_qhd_czj` | 财政局 | ❌ 禁用 | 0 | `http://czj.qhd.gov.cn/home/list/?code=NTk5&pcode=MDE3NjMxOTgyNTE2` | DNS 解析失败 |
| `city_qhd_scjg` | 市监局 | ❌ 禁用 | 0 | `http://scjg.qhd.gov.cn/home/list/?code=NjE1&pcode=MDE3NjMxOTgyNTE2` | DNS 解析失败 |
| `city_qhd_sthjj` | 生态环境局 | ❌ 禁用 | 0 | `http://sthjj.qhd.gov.cn/home/list/?code=NjA2&pcode=MDE3NjMxOTgyNTE2` | DNS 解析失败 |
| `city_qhd_kjj` | 科技局 | ❌ 禁用 | 0 | `http://kjj.qhd.gov.cn/home/list/?code=NjA5&pcode=MDE3NjMxOTgyNTE2` | 列表页 JS 渲染后无 `/home/details` 链接 |
| `city_qhd_nyncj` | 农业农村局 | ⚠️ 启用但 0 | 0 | `http://nyncj.qhd.gov.cn/home/list/?code=MTA1&pcode=MDE3NjMxOTgyNTE2` | 待抓取 |
| `city_qhd_mzj` | 民政局 | ⚠️ 启用但 0 | 0 | `http://mzj.qhd.gov.cn/home/list/?code=NjAz&pcode=MDE3NjMxOTgyNTE2` | 待抓取 |
| `city_qhd_sfj` | 司法局 | ⚠️ 启用但 0 | 0 | `http://sfj.qhd.gov.cn/home/list/?code=NjEx&pcode=MDE3NjMxOTgyNTE2` | 待抓取 |
| `city_qhd_yjglj` | 应急管理局 | ⚠️ 启用但 0 | 0 | `http://yjglj.qhd.gov.cn/home/list/?code=NjEy&pcode=MDE3NjMxOTgyNTE2` | 待抓取 |
| `city_qhd_czj_gk` | 财政局(信息公开) | ⚠️ 启用但 0 | 0 | `http://www.qhd.gov.cn:81/list.jsp?deptid=132&code=340` | 待抓取 |
| `city_qhd_rsj` | 人社局 | ⚠️ 启用但 0 | 0 | `http://rsj.qhd.gov.cn/` | 早前配置，可能需重抓 |
| `city_qhd_rsj_gs` | 人社局·公示 | ⚠️ 启用但 0 | 0 | (rsj 拆分) | 待抓取 |
| `city_qhd_rsj_tzgg` | 人社局·通知公告 | ⚠️ 启用但 0 | 0 | (rsj 拆分) | 待抓取 |
| `city_qhd_rsj_zcjd` | 人社局·政策解读 | ⚠️ 启用但 0 | 0 | (rsj 拆分) | 待抓取 |
| `city_qhd_bdhxq` | 北戴河新区 | ⚠️ 启用但 0 | 0 | `http://www.bdhxq.gov.cn/` | 早前配置，待抓取 |
| `city_qhd_hgq` | 海港区 | ⚠️ 启用但 0 | 0 | `https://www.qhdhgq.gov.cn/` | 早前配置，待抓取 |
| `city_qhd_kfq` | 开发区 | ⚠️ 启用但 0 | 0 | `https://qetdz.gov.cn/Content/browse/cid/303` | 早前配置，待抓取 |
| `city_qhd_gov` | 市政府 | ⚠️ 启用但 0 | 0 | `http://www.qhd.gov.cn/tzgg/` | 早前配置，待抓取 |
| `city_qhd_gov_gfxwj` | 市政府·规范性文件 | ⚠️ 启用但 0 | 0 | `http://www.qhd.gov.cn:81/info/list.jsp?deptid=58&code=293` | 早前配置，待抓取 |
| `city_qhd_gov_zc` | 市政府·政策文件专栏 | ⚠️ 启用但 0 | 0 | `http://www.qhd.gov.cn/list_gz.jsp?code=342&type=zc` | 早前配置，待抓取 |

### 4.2 河北省级（24 个 source_id）

| source_id | 部门 | 状态 | 政策数 | list_url | 关键点 |
|---|---|---|---|---|---|
| `prov_hebei_sport` | 体育局 | ✅ 成功 | 22 | `http://sport.hebei.gov.cn/faguichanye/zcfg/` | 政策法规 (faguichanye/zcfg) |
| `prov_hebei_swj_jg` | 机关事务管理局 | ✅ 成功 | 36 | `https://swj.hebei.gov.cn/zcfg/` | 政策法规 (首页) |
| `prov_hebei_mw` | 民委 | ✅ 成功 | 35 | `http://mw.hebei.gov.cn/xxgk/` | 信息公开 (xxgk) |
| `prov_hebei_whly` | 文旅厅 | ✅ 成功 | 14 | `https://whly.hebei.gov.cn/zwwj/flfg/` | 法律法规规章 (zwwj/flfg) |
| `prov_hebei_nync` | 农业农村厅 | ✅ 成功 | 6 | `http://nync.hebei.gov.cn/html/www//xxgkzl/zhengcfg/index.html` | 政策文件 |
| `prov_hebei_sgdb` | 国动办 | ✅ 成功 | 1 | `https://sgdb.hebei.gov.cn/zcfg/` | 政策法规 (走代理通了) |
| `prov_hebei_rta` | 广电局 | ✅ 成功 | 4 | `http://rta.hebei.gov.cn/lists/3/0/32.html` | 通知公告 |
| `prov_hebei_yjgl` | 应急管理厅 | ✅ 成功 | 1 | `https://yjgl.hebei.gov.cn/zwgk/zcfg/` | 政务公开/政策法规 (走代理通了) |
| `prov_hebei_yjs` | 政府研究室 | ✅ 成功 | 1 | `https://yjs.hebei.gov.cn/zcfg/` | 政策法规 (走代理通了) |
| `prov_hebei_slt` | 水利厅 | ✅ 成功 | 18 | `http://slt.hebei.gov.cn/a/zc/` | 政策 |
| `prov_hebei_scjg` | 市监局 | ✅ 成功 | 20 | `https://scjg.hebei.gov.cn/node/919` | 通知公告 (早前配置) |
| `prov_hebei_sjt` | 审计厅 | ✅ 成功 | 21 | `http://sjt.hebei.gov.cn/` | 早前配置 |
| `prov_hebei_fgw2` | 发改委 | ❌ 禁用 | 0 | `http://hbdrc.hebei.gov.cn/ndjh_1231/` | **IP 段封锁** 121.29.48.87 |
| `prov_hebei_jtt2` | 交通厅 | ❌ 禁用 | 0 | `https://jtt.hebei.gov.cn/jtyst/zwgk/jcxxgk/xxgkzn/` | **IP 段封锁** 121.29.49.195 |
| `prov_hebei_kjt2` | 科技厅 | ❌ 禁用 | 0 | `https://kjt.hebei.gov.cn/` | **IP 段封锁** 124.239.213.29 |
| `prov_hebei_zrzy2` | 自然资源厅 | ❌ 禁用 | 0 | `https://zrzy.hebei.gov.cn/heb/gongk/gkml/zcwj/` | **IP 段封锁** 121.29.48.192 |
| `prov_hebei_sthjt` | 生态环境厅 | ❌ 禁用 | 0 | `https://hbepb.hebei.gov.cn/hbhjt/zwgk/fdzdgknr/tongzhigonggao/` | **IP 段封锁** 36.144.10.42 |
| `prov_hebei_minzheng2` | 民政厅 | ❌ 禁用 | 0 | `https://minzheng.hebei.gov.cn/` | **IP 段封锁** 218.11.12.4 |
| `prov_hebei_tax` | 税务局 | ⚠️ 启用但 0 | 0 | `https://hebei.chinatax.gov.cn/` | SSL 证书不匹配 |
| `prov_hebei_gov_zk` | 省政府·政策文件总库 | ⚠️ 启用但 0 | 0 | `https://www.hebei.gov.cn/columns/49f13cc2-db03-4d0c-b4fe-2f3f659d3b6e/index.html` | Playwright 60s 超时 |
| `prov_hebei_gov_jd` | 省政府·政策解读 | ⚠️ 启用但 0 | 0 | `https://www.hebei.gov.cn/columns/b4515201-74c2-4866-ba74-70199fee1a67/index.html` | 同上 |
| `prov_hebei_gov` | 省政府门户 | ⚠️ 启用但 0 | 0 | `https://www.hebei.gov.cn/` | 同上 |
| `prov_hebei_jrb` | 金融办 | ⚠️ 启用但 0 | 0 | `https://www.hebswjrb.gov.cn/` | 待抓取 |

---

## 五、QHD 站 URL 模式与 base64 code 规律

秦皇岛各委办局用统一平台 `*.qhd.gov.cn`，列表页 URL 模式：

```
/home/list?code={base64_int_or_str}&pcode={base64_int_or_str}
/home/xzzfgstablist?code={base64}&pcode={base64}  (住建局特殊)
/home/tablist?code={base64}&pcode={base64}  (住建局特殊)
```

**code 是 base64 编码的栏目 ID**：
- `MTA2` = base64('106') = 政策法规（文旅局）
- `MTA1` = base64('105') = 政策解读（文旅局）
- `OTc` = base64('97') = 通知公告（文旅局）
- `emNmZw%ce%b3%ce%b3` = base64('r6g') + GBK 编码（住建局）

**如何找到正确 code**：
1. 抓首页 → 找栏目链接（href 含 `/home/list?code=...`）
2. 用 Python 解析后**直接 base64 解码**看是什么栏目
3. 用 `ntuser` 探测：`node fetch` 拿到内容后，正则提取 `code` 参数

---

## 六、hebei.gov.cn 域名的 4 种 URL 模式

| 模式 | 例子 | 说明 |
|---|---|---|
| UUID 栏目页 | `https://www.hebei.gov.cn/columns/{uuid}/index.html` | 政策文件总库/解读栏目 |
| 厅级子站 | `https://{dept}.hebei.gov.cn/{path}` | 厅局自建子站 |
| 特殊子域 | `https://hbdrc.hebei.gov.cn/` (发改委) | 域名特殊 |
| 独立域 | `https://www.hebaudit.gov.cn/` (审计) | 独立域 |

---

## 七、3 类硬性技术限制（无法在 Server 上解决）

### 1. hebei.gov.cn IP 段封锁
- **症状**：TCP 80/443 全 timeout，DNS 解析得到 IP 但连不上
- **证据**：
  ```
  $ socket.getaddrinfo("hbdrc.hebei.gov.cn", 80) → 121.29.48.87
  $ curl http://121.29.48.87/ --max-time 15 → Connection timed out
  ```
- **6 个站 IP 段**：121.29.48.87, 121.29.49.195, 124.239.213.29, 121.29.48.192, 36.144.10.42, 218.11.12.4
- **根因**：腾讯云 IP 段在政府防火墙白名单外
- **解法**：**换 Server 出口 IP**（如家用宽带代理 / 国外代理 / 在 RSSHub 容器配代理出口）

### 2. QHD 部分域名 DNS 不存在
- **症状**：`Name or service not known`，连代理也 fetch failed
- **3 个站**：`czj.qhd.gov.cn`, `scjg.qhd.gov.cn`, `sthjj.qhd.gov.cn`
- **根因**：可能域名已下线/改名/NS 未配置

### 3. kjj 列表页 JS 渲染后无详情
- **症状**：Playwright 渲染后页面有内容但**只有栏目导航链接**，无 `/home/details` 详情链接
- **可能**：列表是 JS 动态加载但网络层不返回详情（API 限流）

---

## 八、关键文件位置

```
C:\Users\Fangyi\OneDrive\文档\Claude\政策收集总结\policy-radar\
├── python\
│   ├── crawlers\
│   │   ├── fetcher.py         ← 核心: IPv4+代理+Chrome指纹
│   │   ├── engine.py          ← 爬取主流程
│   │   ├── parser.py          ← 列表/详情解析
│   │   └── spiders\
│   │       ├── city_qhd_*.json  ← 31 个 QHD 配置
│   │       └── prov_hebei_*.json ← 87 个河北配置
│   └── scripts\
│       ├── export_policies_md.py  ← MD 导出 (有质量过滤)
│       ├── seed_*.py              ← 批量创建信源
│       ├── probe_*.py             ← URL 探测脚本
│       └── fix_*.py               ← 信源修复脚本
├── data\
│   ├── policy_radar.db        ← SQLite
│   ├── policy_radar.db.bak_2026-07-08  ← R9 前备份
│   └── exports\
│       └── policies\
│           ├── 河北\              ← 128 篇
│           └── 秦皇岛\            ← 6 篇
└── docs\
    ├── SERVER-CONNECTION.md   ← 服务器连接说明
    └── HEBEI-QHD-CRAWL-TECHNICAL.md  ← 本文档
```

服务器端：
```
/opt/policy-radar/  (或 /app/ 在容器内)
├── python/crawlers/...
├── data/policy_radar.db
├── data/exports/policies/...
└── /tmp/universal_proxy.mjs  (RSSHub 容器内)
```

---

## 九、9 轮工作历程

| 轮 | 目标 | 关键产出 | 累计入库 |
|---|---|---|---|
| 1 | 初探：找 lywgj/wjw/zyghj/jtj 真实栏目 | 发现 base64 code 模式 | ~36 |
| 2 | 修河北 5 个厅局（sport/swj_jg/mw/whly/nync）| selector 改 `/xxgk/` 等 | 36 |
| 3 | 修 QHD 已 enable 的源（xzspj/czj 等）| 部分走代理后通 | 36 |
| 4-6 | 探查更多厅局+调选择器 | 新增 18 源，禁用 8 死站 | 36 |
| 7 | **突破 WAF**：部署 RSSHub 容器 Node 代理 + 改 fetcher | 启用 21 源 | 209 (+173) |
| 8 | 修 fgw + 跑全量 | +59 条 | 268 |
| 9 | 收尾：禁用 9 死源 + 放宽过滤 + 清理 52 非政策 | -52 净清理 | 216 |

---

## 十、关键经验与最佳实践

### ✅ 应该做的
1. **必须走代理**：腾讯云 IP 被政府站 WAF 白名单拒，**必须**通过 RSSHub 容器（172.18.0.4）的 IP 段才能访问
2. **完整 Chrome 指纹**：`Sec-Ch-Ua*` 头是 NWAF WAF 识别的关键
3. **Referer 用 baidu**：政府站拒 google referer，但接受 baidu
4. **`final_url` 还原原始**：用代理时 final_url 会被替换成代理 URL，必须手动还原才能让 `urljoin` 正确拼接详情页
5. **多轮探测**：从首页 → 列表 → 详情逐级探测

### ❌ 不要做的
1. **不要用 `a[href]` 太宽的 selector**（如 `ul li`）：会命中导航/推荐链接
2. **不要尝试 Node http2 代理**：根因是 IP 段封锁，HTTP 协议层改不动
3. **不要用 Playwright launch proxy 参数**（容器内不生效）
4. **不要给 `localhost:1200` 访问 RSSHub**（容器外不通，必须用 RSSHub 容器 IP `172.18.0.4`）
5. **不要在新表里硬编码 list_url 推断栏目**——栏目名称可能与 URL 路径不符，必须实际探测

### ⚠️ 已知坑
1. RSSHub 容器**无 pkill/disown/ps**，杀 node 进程用 `/proc/[0-9]*/cmdline` 遍历
2. Spider JSON 注释里 GBK 编码字符串在 Windows Python3 读取会失败——读时必须 `encoding='utf-8'`
3. fetcher 的 IP 替换对代理 URL **不生效**（虽然条件有判断但因 url_to_fetch 被改 actual_url 覆盖）
4. 列表页 200 KB+ 大页面（gxj 1.3 MB）会触发 IP 替换逻辑后变慢
5. crontab 跑全量时单个源 60s 超时是 httpx 客户端默认，要让源稳定 < 30s

---

## 十一、cron 自动化

`/etc/cron.d/policy-radar`:
```cron
0 8,14,20 * * * root cd /opt/policy-radar && /usr/bin/docker exec policy-radar-app bash /opt/cron_run.sh >> /var/log/policy-radar-cron.log 2>&1
```

`cron_run.sh` 流程:
1. `python -m crawlers --all` （跑所有 enabled 源）
2. `python -m scripts.backfill_content` （回填缺失的 raw_content）
3. `python -m scripts.export_policies_md --days 730` （导出 MD）
4. 失败源会记录 `last_status='fetch_failed'`

---

## 十二、监控与诊断命令

```bash
# 查某源状态
docker exec policy-radar-app python -c "
import sqlite3
c = sqlite3.connect('/app/data/policy_radar.db')
r = c.execute('SELECT source_id, enabled, last_status, last_crawl_at FROM policy_sources WHERE source_id=?', ('city_qhd_lywgj',)).fetchone()
print(dict(r))
"

# 单源抓取测试
docker exec policy-radar-app python -m crawlers --source city_qhd_lywgj --max-new 3 -v

# 看 RSSHub 代理日志
docker exec policy-radar-rsshub tail -30 /tmp/proxy.log

# 看 policy-radar-app 日志
docker logs policy-radar-app --tail 100

# 立即触发全量
docker exec policy-radar-app python -m crawlers --all --max-new 5

# 看某源入库数
docker exec policy-radar-app python -c "
import sqlite3
c = sqlite3.connect('/app/data/policy_radar.db')
for sid in ['city_qhd_lywgj','prov_hebei_swj_jg','prov_hebei_mw']:
    n = c.execute('SELECT COUNT(*) FROM policies p JOIN policy_sources ps ON p.source_id=ps.id WHERE ps.source_id=?', (sid,)).fetchone()[0]
    print(f'  {sid}: {n}')
"
```

---

## 十三、下一轮要做的事（如果用户允许继续）

1. **换 Server 出口 IP**（最关键）：在 RSSHub 容器里挂代理出口，绕 IP 封锁
2. **手动给禁用源配新 URL**（9 个启用但 0 数据的源）：用户可访问站点看新版面
3. **重启用 czj/scjg/sthjj**：测试新域名（`ssczj` / `amr` / `sthjj`）的官方新地址
4. **kjj API 探测**：用浏览器开发者工具抓真实 API 端点，跳过 HTML 列表
5. **完善 RSSHub 路由**：写真正的 RSSHub Route.js（需重 build RSSHub 镜像）

---

## 十四、关键 SQL 维护命令

```sql
-- 1. 看某源状态
SELECT source_id, name, enabled, last_status, last_crawl_at 
FROM policy_sources 
WHERE source_id IN ('city_qhd_lywgj','city_qhd_lywgj_zcjd');

-- 2. 禁用某源
UPDATE policy_sources 
SET enabled=0, last_status='disabled', 
    spider_config = json_set(spider_config, '$.disabled_reason', '原因')
WHERE source_id='xxx';

-- 3. 启用某源
UPDATE policy_sources 
SET enabled=1, last_status='re_enabled', 
    spider_config = json_remove(spider_config, '$.disabled_reason')
WHERE source_id='xxx';

-- 4. 重新 seed（同步 spider JSON 到 DB）
docker exec policy-radar-app python -m scripts.seed_sources

-- 5. 看 cron 跑了多少条
SELECT ps.source_id, ps.name, COUNT(p.id) as cnt
FROM policy_sources ps
LEFT JOIN policies p ON p.source_id = ps.id
WHERE ps.region IN ('河北','秦皇岛')
GROUP BY ps.id
ORDER BY cnt DESC;
```

---

## 十五、文件 / 命令索引

| 用途 | 文件 / 命令 |
|---|---|
| 看 list URL 模板 | `python/crawlers/spiders/{source_id}.json` |
| 改 fetch 逻辑 | `python/crawlers/fetcher.py` |
| 改质量过滤 | `python/scripts/export_policies_md.py` |
| DB 操作 | `python/scripts/seed_sources.py`, `python/scripts/fix_*.py` |
| 探测新站 | `python/scripts/probe_*.py` (通用), `python/scripts/probe_qhd_fix.py` (QHD) |
| 跑全量 | `python -m crawlers --all` |
| 跑单源 | `python -m crawlers --source {id} --max-new N` |
| 导出 | `python -m scripts.export_policies_md --source-ids ...` |
| 看 cron 状态 | `docker logs policy-radar-app --tail 100` |

---

## 抚顺市抓取对比参考（2026-07-21 增）

**结论**: 抚顺站对比秦皇岛**无 WAF / 无封禁**（本地 + 服务器都通），11 源 spider 首批 6 源成功入库 99 条。

| 维度 | 秦皇岛 (qhd) | 抚顺 (fushun) |
|---|---|---|
| 主机位置 | 河北秦皇岛 | 辽宁抚顺 |
| WAF/封禁 | **严重**（sub-sites 14 OK / 5 DNS-fail / 3 TCP 封禁 / 6 :81 端口挡）| **几乎无**（11 源全可达）|
| 抓取 403 率 | 高（部分子域 UA 拦截）| 极低（仅 2 源 403 WAF）|
| CMS 模板 | webBuilder（`.TRS_Editor`、`#UCAP-CONTENT` 等老模板）| 国务院政务公开平台（`#TDContent`、`.ewb-article-bd`）|
| list item class | 多种（site-dependent）| **统一 `.ewb-info-item`**（11 站同模板）|
| render_js | 多数 false，少数 true（qhd 主站 JS 渲染）| **全部 false**（HTML 直接含列表）|
| 详情页结构 | 不统一 | **统一**：`#TDContent` / `.ewb-article-bd` |
| URL 模式 | 多种（`front_pcsec.do?tid=`、`/home/list/?code=`）| **统一**：`/{栏目段}/{YYYYMMDD}/{uuid}.html` |
| 列表外链 | 少 | **30-50%** 是微信公众号外链（mp.weixin.qq.com）|
| PDF 直链 | 少 | **多**（财政局/人社局/市场监管局部分项就是 .pdf 直链）|
| 抓取经验 | 单站单测 selector | 批量同模板，selector 高度复用 |
| 部署成果 | 36 源（v0.3）| 11 源 + 99 条入库（2026-07-21）|

**选择器统一范式（抚顺 11 源通用）**:
```json
{
  "list_selectors": {
    "item": ".ewb-info-item, .sec-right-item, li.ewb-info-item.clearfix, li.module-list.clearfix",
    "title": "a::text",
    "href": "a::attr(href)",
    "date": ".ewb-date::text, .sec-right-time::text"
  },
  "detail_selectors": {
    "title": "h3, .ewb-article-hd h3",
    "content": "#TDContent, .ewb-article-bd, .post-content",
    "date": "meta[name=PubDate], .post-mark"
  },
  "render_js": false
}
```

**5 源 0 抓取待二期**：minzheng/wenhua(403 WAF)、shangwu(超时)、weisheng(URL 重测)、shichangjiandu(PDF 附件)。详见 `CRAWLER-FIX-TODO.md` 抚顺段。

**总结**：抚顺抓取比秦皇岛**简单一档**，无 WAF + 统一 CMS，未来类似地级市（用同 CMS 模板的）都可直接套这套配置。详见 `../政府站-验证矩阵.md` Round 6。

---

**最后更新**: 2026-07-21
**维护**: Fangyi / Claude Code
**相关文档**:
- `docs/SERVER-CONNECTION.md` - 服务器连接
- `docs/PRODUCTION-CHECKLIST.md` - 上线路线
- `docs/DEPLOY.md` - 部署
- `../政府站-验证矩阵.md` Round 6 - 抚顺站点详细验证
- `CRAWLER-FIX-TODO.md` 抚顺段 - 5 源 0 抓取待修
