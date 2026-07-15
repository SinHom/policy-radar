# 河北省+秦皇岛市 政策源站台账

> 最后更新：2026-07-07 | policy-radar 爬虫项目
> 适用版本：v0.2+
> 2026-07-07 刷新：37→60 源有数据，新增 tzgg/zcjd/gs 内容类型子源

---

## 总体概况

| 维度 | 数量 |
|------|------|
| 省级部门 spider 配置 | 37 |
| 秦皇岛市级 spider 配置 | 16 |
| 聚合门户（政府公报/要闻） | 3 |
| 新增内容类型子源（tzgg/zcjd/gs） | 17 |
| **合计** | **73** |
| 已验证有数据 | 44（省级28 + 市级14 + 聚合0 + 内容类型2） |
| 零数据待修 | 29 |

---

## 省级部门（37 源）

### 已验证可用（本地 httpx）

| source_id | 部门 | 列表URL | 列表项 | 状态 |
|-----------|------|---------|--------|------|
| prov_hebei_fgw | 发改委 | hbdrc.hebei.gov.cn/.../tztg_1120/ | 51 | ✅ |
| prov_hebei_czt | 财政厅 | czt.hebei.gov.cn/xwdt/tzgg/ | 34 | ✅ |
| prov_hebei_gxt | 工信厅 | gxt.hebei.gov.cn/.../tzgg83/ | 10 | ✅ |
| prov_hebei_nync | 农业农村厅 | nync.hebei.gov.cn/.../tzgg/ | 54 | ✅ |
| prov_hebei_whly | 文旅厅 | whly.hebei.gov.cn/xwzx/tzgg/ | 47 | ✅ |
| prov_hebei_tyjr | 退役军人厅 | tyjrswt.hebei.gov.cn/.../tzgg/ | 49 | ✅ |
| prov_hebei_scjg | 市监局 | scjg.hebei.gov.cn/node/919 | 19 | ✅ |
| prov_hebei_ylbzj | 医保局 | ylbzj.hebei.gov.cn/category/101 | 20 | ✅ |
| prov_hebei_yjj | 药监局 | yjj.hebei.gov.cn/.../gfxwj/ | 35 | ✅ |
| prov_hebei_gzw | 国资委 | hbsa.hebei.gov.cn/gg.html | 7 | ✅ |
| prov_hebei_zrzy | 自然资源厅 | zrzy.hebei.gov.cn/.../gggs/tz/ | 42 | ✅ (http) |

### 已可本地爬取（原"需服务器端"，现 Playwright 绕过了）

| source_id | 部门 | 状态 | 政策数 |
|-----------|------|------|--------|
| prov_hebei_sthjt | 生态环境厅 | Playwright ✅ | 4 |
| prov_hebei_jtt | 交通运输厅 | Playwright ✅ | 12 |
| prov_hebei_slt | 水利厅 | Playwright ✅ | 1 |
| prov_hebei_rst | 人社厅 | Playwright ✅ (SPA) | 7 |
| prov_hebei_swt | 商务厅 | ⚠️ ok 但 0 数据 | 0 |
| prov_hebei_zfcxjst | 住建厅 | ⚠️ ok 但 0 数据 | 0 |
| prov_hebei_wsjkw | 卫健委 | ⚠️ ok 但 0 数据 | 0 |

### 已验证可用

| source_id | 部门 | 状态 | 政策数 |
|-----------|------|------|--------|
| prov_hebei_rta | 广电局 | ✅ | 10 |
| prov_hebei_lycy | 林业草原局 | ✅ | 10 |
| prov_hebei_sport | 体育局 | ✅ | 10 |
| prov_hebei_tjj | 统计局 | ✅ | 10 |
| prov_hebei_sjt | 审计厅 | ✅ | 10 |
| prov_hebei_minzheng | 民政厅 | ✅ | 3 |
| prov_hebei_mw | 民委 | ✅ | 10 |
| prov_hebei_yjgl | 应急管理厅 | ✅ | 10 |
| prov_hebei_swj_jg | 机关事务管理局 | ✅ | 10 |
| prov_hebei_szj | 数据和政务服务局 | ✅ | 10 |
| prov_hebei_yjs | 政府研究室 | ✅ | 10 |
| prov_hebei_nyj | 能源局 | ✅（挂发改委下） | 1 |

### 仍需修复

| source_id | 部门 | 问题 |
|-----------|------|------|
| prov_hebei_jyt | 教育厅 | `ul li` 抓到导航，需定制 selector |
| prov_hebei_sft | 司法厅 | 同上 |
| prov_hebei_gat | 公安厅 | 同上 |
| prov_hebei_wenwu | 文物局 | 同上 |
| prov_hebei_hebwb | 外办 | 400，URL 参数需调整 |
| prov_hebei_swt | 商务厅 | ok 但 0 产出，需查列表页 |
| prov_hebei_zfcxjst | 住建厅 | ok 但 0 产出 |
| prov_hebei_wsjkw | 卫健委 | ok 但 0 产出 |

### 聚合门户

| source_id | 说明 | 模式 |
|-----------|------|------|
| pr_hebei_yw | 河北省政府·要闻 | Playwright |
| pr_hebei_zfgb | 河北省政府公报 | Playwright |
| prov_hebei_gov | 省政府·政策文件 | html |

---

## 秦皇岛市级（16 源）

> ⚠️ 大部分 QHD 站点封锁非中国大陆 IP。本地 Playwright 可部分绕过。
> QHD 站点使用统一 JSP/Servlet CMS，URL 参数为 Base64 编码。

### 已有数据（6 源）

| source_id | 部门 | 政策数 | 备注 |
|-----------|------|--------|------|
| city_qhd_rsj | 人社局 | 18 | ✅ 本地可访问 |
| city_qhd_wjw | 卫健委 | 10 | Playwright |
| city_qhd_lywgj | 文旅局 | 10 | Playwright |
| city_qhd_swj | 商务局 | 10 | Playwright |
| city_qhd_zyghj | 自然资源局 | 10 | Playwright，含 tzgg/gs 子源 |
| city_qhd_swj_water | 水务局 | 5 | Playwright |
| city_qhd_gxj | 工信局 | 3 | Playwright（有噪声） |

### 零数据（10 源，需定制 selector）

| source_id | 部门 | 问题 |
|-----------|------|------|
| city_qhd_gov | 市政府门户 | `ul li` 抓到导航 |
| city_qhd_fgw | 发改委 | 同上 |
| city_qhd_kjj | 科技局 | 同上 |
| city_qhd_czj | 财政局 | 同上 |
| city_qhd_zjj | 住建局 | 同上 |
| city_qhd_sthjj | 生态环境局 | 同上 |
| city_qhd_jtj | 交通局 | 同上 |
| city_qhd_nyncj | 农业农村局 | 同上 |
| city_qhd_scjg | 市监局 | 同上 |

---

## 域名变更对照表

| 旧域名（常见但已失效） | 新域名 | 部门 |
|-------------------------|--------|------|
| fgw.hebei.gov.cn | hbdrc.hebei.gov.cn | 发改委 |
| gzw.hebei.gov.cn | hbsa.hebei.gov.cn | 国资委 |
| gdj.hebei.gov.cn | rta.hebei.gov.cn | 广电局 |
| swb.hebei.gov.cn | hebwb.hebei.gov.cn | 外办 |
| lcj.hebei.gov.cn | lycy.hebei.gov.cn | 林业草原局 |
| lsj.hebei.gov.cn | lswz.hebei.gov.cn | 粮食局 |
| gdb.hebei.gov.cn | sgdb.hebei.gov.cn | 国动办 |
| jgswj.hebei.gov.cn | swj.hebei.gov.cn | 机关事务管理局 |
| jrgj.hebei.gov.cn | (已拆分) | 金融监管→NFRA+金融委 |
| nyj.hebei.gov.cn | (无独立站) | 能源局挂靠发改委 |
| zscqj.hebei.gov.cn | scjg.hebei.gov.cn | 知识产权局挂靠市监局 |

---

## 待办事项

- [ ] 恢复服务器 SSH 访问（端口22 被 HTTP 代理拦截）
- [ ] 从服务器端测试 QHD 站点（国内IP）—— 9 个零数据 QHD 源
- [x] 修复失效 URL 的 spider 配置 —— 大部分已自动修复（首页→/tzgg/）
- [x] 测试 Playwright 模式的封锁站点 —— 已通过批量回填验证
- [x] 完成全量爬取 —— 500 条政策，98% 正文覆盖
- [ ] 配置每日定时爬取（scheduler 添加 crawl job）
- [ ] 本地部署 RSSHub 替代手写 spider config
- [ ] MD 文件上传到服务器 `/opt/policy-radar/data/exports/`
- [ ] 为 37 个零数据源逐个定制 CSS selector（或全部切 RSSHub）
