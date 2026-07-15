# 上海市 政策源站台账

> 创建：2026-07-08 | policy-radar 爬虫项目
> 适用版本：v0.2+

## 关键发现

1. **域名模式**：上海政府站使用 `*.sh.gov.cn`（**非** `*.shanghai.gov.cn`）
2. **访问限制**：全部需要 Playwright（httpx 返回 403），**且需国内 IP**
3. **选择器问题**：`ul li` 模板不匹配上海站 HTML 结构（div 布局为主），需后续逐个定制

## 委办局（34 源）

| source_id | 部门 | host | 通知公告 URL |
|-----------|------|------|-------------|
| sh_fgw | 发改委 | fgw.sh.gov.cn | /tzgg/ |
| sh_jxw | 经信委 | sheitc.sh.gov.cn | /tzgg/ |
| sh_sww | 商务委 | sww.sh.gov.cn | /tzgg/ |
| sh_edu | 教委 | edu.sh.gov.cn | /tzgg/ |
| sh_kw | 科委 | stcsm.sh.gov.cn | /tzgg/ |
| sh_gaj | 公安局 | gaj.sh.gov.cn | /tzgg/ |
| sh_mzj | 民政局 | mzj.sh.gov.cn | /tzgg/ |
| sh_sfj | 司法局 | sfj.sh.gov.cn | /tzgg/ |
| sh_czj | 财政局 | czj.sh.gov.cn | /tzgg/ |
| sh_rsj | 人社局 | rsj.sh.gov.cn | /tzgg/ |
| sh_zjw | 住建委 | zjw.sh.gov.cn | /tzgg/ |
| sh_jtw | 交通委 | jtw.sh.gov.cn | /tzgg/ |
| sh_nyncw | 农业农村委 | nyncw.sh.gov.cn | /tzgg/ |
| sh_sthj | 生态环境局 | sthj.sh.gov.cn | /tzgg/ |
| sh_ghzyj | 规自局 | ghzyj.sh.gov.cn | /tzgg/ |
| sh_swj | 水务局 | swj.sh.gov.cn | /tzgg/ |
| sh_wsjkw | 卫健委 | wsjkw.sh.gov.cn | /tzgg/ |
| sh_sjj | 审计局 | sjj.sh.gov.cn | /tzgg/ |
| sh_gzw | 国资委 | gzw.sh.gov.cn | /tzgg/ |
| sh_tjj | 统计局 | tjj.sh.gov.cn | /tzgg/ |
| sh_tyj | 体育局 | tyj.sh.gov.cn | /tzgg/ |
| sh_lhsr | 绿化市容局 | lhsr.sh.gov.cn | /tzgg/ |
| sh_yjglj | 应急管理局 | yjglj.sh.gov.cn | /tzgg/ |
| sh_jgswj | 机关事务管理局 | jgswj.sh.gov.cn | /tzgg/ |
| sh_jrj | 金融局 | jrj.sh.gov.cn | /tzgg/ |
| sh_ybj | 医保局 | ybj.sh.gov.cn | /tzgg/ |
| sh_whlyj | 文旅局 | whlyj.sh.gov.cn | /tzgg/ |
| sh_scjgj | 市监局 | scjgj.sh.gov.cn | /tzgg/ |
| sh_mzzjj | 民宗局 | mzzjj.sh.gov.cn | /tzgg/ |
| sh_wsb | 外办 | wsb.sh.gov.cn | /tzgg/ |
| sh_hzjl | 合作交流办 | hzjl.sh.gov.cn | /tzgg/ |
| sh_jyj | 监狱管理局 | jyj.sh.gov.cn | /tzgg/ |
| sh_dsj | 数据局 | dsj.sh.gov.cn | /tzgg/ |
| sh_zhengce | 市政府·政策发布 | www.shanghai.gov.cn | /zhengce/list |

## 区级（16 源）

| source_id | 区 | Domain |
|-----------|-----|--------|
| sh_pudong | 浦东新区 | www.pudong.gov.cn |
| sh_huangpu | 黄浦区 | www.shhuangpu.gov.cn |
| sh_xuhui | 徐汇区 | www.xuhui.gov.cn |
| sh_changning | 长宁区 | www.shcn.gov.cn |
| sh_jingan | 静安区 | www.jingan.gov.cn |
| sh_putuo | 普陀区 | www.shpt.gov.cn |
| sh_hongkou | 虹口区 | www.shhk.gov.cn |
| sh_yangpu | 杨浦区 | www.shyp.gov.cn |
| sh_minhang | 闵行区 | www.shmh.gov.cn |
| sh_baoshan | 宝山区 | www.shbs.gov.cn |
| sh_jiading | 嘉定区 | www.jiading.gov.cn |
| sh_jinshan | 金山区 | www.jinshan.gov.cn |
| sh_songjiang | 松江区 | www.songjiang.gov.cn |
| sh_qingpu | 青浦区 | www.shqp.gov.cn |
| sh_fengxian | 奉贤区 | www.fengxian.gov.cn |
| sh_chongming | 崇明区 | www.shcm.gov.cn |

## 部署方式

- Config 文件：`python/crawlers/spiders/sh_*.json`（50 个）
- 生成脚本：`python/scripts/seed_shanghai_sources.py`（本地）+ `seed_sh_server.py`（服务器）
- 来源页面：`https://www.shanghai.gov.cn/bmjs-17-32994/index.html`
- 爬取要求：Playwright + 国内 IP（已部署到腾讯云服务器 43.155.161.54）

## 待办

- [ ] 逐个确认 50 个域名的实际可达性（部分子域名可能不存在，如 gzw.sh.gov.cn DNS 失败）
- [ ] 为上海站定制 CSS selector（替代 `ul li` 模板）
- [ ] 通过 RSSHub 容器（`policy-radar-rsshub`）获取结构化数据
- [ ] 确认 16 个区站的 `/tzgg/` 路径是否正确
