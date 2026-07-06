# 河北省+秦皇岛市 政策源站台账

> 最后更新：2026-07-06 | policy-radar 爬虫项目
> 适用版本：v0.2+

---

## 总体概况

| 维度 | 数量 |
|------|------|
| 省级部门 spider 配置 | 37 |
| 秦皇岛市级 spider 配置 | 16 |
| 聚合门户（政府公报/要闻） | 3 |
| **合计** | **56** |
| 本地验证通过 | 11（httpx） + 4（Playwright可尝试） |
| 需服务器端爬取 | 约 25（封锁非大陆IP/SSL） |

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

### 需服务器端爬取（本地被墙/SSL/JS）

| source_id | 部门 | 原因 |
|-----------|------|------|
| prov_hebei_sthjt | 生态环境厅 | 503 封锁 |
| prov_hebei_jtt | 交通运输厅 | 503 封锁 |
| prov_hebei_slt | 水利厅 | 503 封锁 |
| prov_hebei_swt | 商务厅 | 本地 httpx 被墙，需 Playwright |
| prov_hebei_zfcxjst | 住建厅 | 412 封锁，需 Playwright |
| prov_hebei_wsjkw | 卫健委 | 403 封锁，需 Playwright |
| prov_hebei_rst | 人社厅 | SPA JS渲染，必须 Playwright |

### 需确认列表 URL

| source_id | 部门 | 问题 |
|-----------|------|------|
| prov_hebei_rta | 广电局 | 404, URL 需更新 |
| prov_hebei_hebwb | 外办 | 400, 参数需调整 |
| prov_hebei_lycy | 林业草原局 | 404, URL 需更新 |
| prov_hebei_sport | 体育局 | 410 Gone, URL 已失效 |
| prov_hebei_tjj | 统计局 | 404, URL 需更新 |
| prov_hebei_sjt | 审计厅 | 需验证 |
| prov_hebei_jyt | 教育厅 | 需验证 |
| prov_hebei_minzheng | 民政厅 | 需验证 |
| prov_hebei_sft | 司法厅 | 需验证 |
| prov_hebei_gat | 公安厅 | 需验证 |
| prov_hebei_mw | 民委 | 需验证 |
| prov_hebei_yjgl | 应急管理厅 | 需验证 |
| prov_hebei_swj_jg | 机关事务管理局 | 需验证 |
| prov_hebei_szj | 数据和政务服务局 | 需验证 |
| prov_hebei_yjs | 政府研究室 | 需验证 |
| prov_hebei_wenwu | 文物局 | 需验证 |
| prov_hebei_nyj | 能源局 | 挂发改委下 |

### 聚合门户

| source_id | 说明 | 模式 |
|-----------|------|------|
| pr_hebei_yw | 河北省政府·要闻 | Playwright |
| pr_hebei_zfgb | 河北省政府公报 | Playwright |
| prov_hebei_gov | 省政府·政策文件 | html |

---

## 秦皇岛市级（16 源）

> ⚠️ 全部 QHD 站点封锁非中国大陆 IP，需从服务器（阿里云北京）爬取。
> QHD 站点使用统一 JSP/Servlet CMS，URL 参数为 Base64 编码。

| source_id | 部门 | 域名 | 备注 |
|-----------|------|------|------|
| city_qhd_gov | 市政府门户 | www.qhd.gov.cn | JSP, 端口81聚合所有部门 |
| city_qhd_fgw | 发改委 | fgw.qhd.gov.cn | 自签SSL |
| city_qhd_gxj | 工信局 | gxj.qhd.gov.cn | 自签SSL |
| city_qhd_kjj | 科技局 | kjj.qhd.gov.cn | 自签SSL |
| city_qhd_czj | 财政局 | czj.qhd.gov.cn | 自签SSL |
| city_qhd_rsj | 人社局 | rsj.qhd.gov.cn | ✅ 唯一本地可访问的QHD站 |
| city_qhd_zjj | 住建局 | zjj.qhd.gov.cn | 自签SSL |
| city_qhd_sthjj | 生态环境局 | sthjj.qhd.gov.cn | 自签SSL |
| city_qhd_zyghj | 自然资源局 | zyghj.qhd.gov.cn | 域名zyghj非zrzyj，静态HTML分页 |
| city_qhd_jtj | 交通局 | jtj.qhd.gov.cn | 自签SSL |
| city_qhd_nyncj | 农业农村局 | nyncj.qhd.gov.cn | 自签SSL |
| city_qhd_lywgj | 文旅局 | lywgj.qhd.gov.cn | 域名lywgj非whlyj |
| city_qhd_swj_water | 水务局 | swj.qhd.gov.cn | 与商务局域名冲突 |
| city_qhd_swj | 商务局(外事和商务局) | swj.qhd.gov.cn | 已更名,可能无独立站 |
| city_qhd_wjw | 卫健委 | wjw.qhd.gov.cn | 自签SSL |
| city_qhd_scjg | 市监局 | scjg.qhd.gov.cn | 自签SSL |

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
- [ ] 从服务器端测试 QHD 站点（国内IP）
- [ ] 修复 6 个失效 URL 的 spider 配置
- [ ] 测试 Playwright 模式的 4 个封锁站点
- [ ] 完成全量爬取（max_new 调大，覆盖过去2年）
- [ ] 配置每日定时爬取（scheduler 添加 crawl job）
- [ ] MD 文件上传到服务器 `/opt/policy-radar/data/exports/`
