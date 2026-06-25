"""预置 5 条未摘要的政策样本到 DB。

由于本地公司网络 + 政府网站反爬，第一期 MVP 跳过真实爬取
（Step 3 爬虫代码已就绪，部署到云服务器后即可运行）。

5 条 mock 政策用于验证端到端链路：
    seed → summarize (LLM) → push (Mock 微信)

样本结构：title / url(UNIQUE) / raw_content(完整文本) / published_at
注意：url 用 file:// 形式或带 source 标识的占位 URL，避免与未来真实爬取冲突。
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import date

from sqlalchemy import select

from python.models import Policy, PolicySource
from python.models.base import get_session, init_session_factory, make_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("seed_policies")


# 5 条 mock 政策样本（贴近真实政府政策格式）
POLICIES = [
    {
        "source_id": "sz_gxj",
        "url": "mock://sz_gxj/2026-001",
        "title": "深圳市关于支持专精特新中小企业发展的若干措施",
        "published_at": date(2026, 6, 15),
        "raw_content": """深圳市工业和信息化局关于支持专精特新中小企业发展的若干措施

为深入贯彻党中央、国务院关于促进中小企业专精特新发展的决策部署，加快培育一批具有创新能力的专精特新中小企业，结合我市实际，制定如下措施。

一、认定奖励
对新认定的国家级专精特新"小巨人"企业，给予一次性奖励 50 万元；
对认定的省级"专精特新"中小企业，给予一次性奖励 20 万元。

二、研发支持
专精特新企业研发费用加计扣除比例提高至 120%，单个企业年度最高支持 500 万元。

三、贷款贴息
对专精特新企业获得的商业银行贷款，按贷款利息的 30% 给予贴息支持，
单户企业年度贴息最高 100 万元，贴息期限不超过 2 年。

四、人才补贴
专精特新企业引进的高层次人才，享受我市人才安居政策，
按层次给予每月 5000-20000 元生活补贴。

五、申报条件
1. 在深圳市行政区域内依法注册登记，具有独立法人资格
2. 符合工业和信息化部发布的专精特新中小企业认定标准
3. 企业信用良好，无重大违法违规记录
4. 上年度营业收入 1000 万元以上

六、申报材料
1. 企业营业执照副本复印件
2. 经审计的上一年度财务报告
3. 研发投入证明材料
4. 知识产权证书、获奖证书等证明材料

七、申报时间
本措施自发布之日起实施，2026 年度申报截止时间为 2026 年 7 月 31 日。
""",
    },
    {
        "source_id": "sz_gxj",
        "url": "mock://sz_gxj/2026-002",
        "title": "深圳市科技型中小企业创新贷款贴息实施细则",
        "published_at": date(2026, 6, 18),
        "raw_content": """深圳市科技型中小企业创新贷款贴息实施细则

为缓解科技型中小企业融资难融资贵问题，根据《深圳市科技计划项目管理办法》，
制定本实施细则。

一、支持对象
在深圳市注册的科技型中小企业，且满足以下条件：
1. 通过科技型中小企业评价入库
2. 上年度营业收入不超过 2 亿元
3. 研发费用占营业收入比例不低于 5%

二、贷款额度与贴息
单户企业年度贴息贷款额度最高 500 万元，贴息比例不超过实际支付利息的 50%，
单户企业年度贴息金额最高 100 万元。

三、申请流程
1. 企业向合作银行申请"创新贷"产品
2. 银行审核通过后放款
3. 企业每季度向市科创委申报贴息
4. 审核通过后贴息资金拨付至企业

四、申报材料
1. 创新贷贴息申请表
2. 贷款合同及放款凭证
3. 利息支付凭证
4. 科技型中小企业入库登记编号

五、申报时间
常年受理，分批审核。本年度贴息资金申报截止时间为 2026 年 8 月 15 日。
""",
    },
    {
        "source_id": "gd_kjt",
        "url": "mock://gd_kjt/2026-001",
        "title": "广东省高新技术企业税收优惠申报指南",
        "published_at": date(2026, 6, 20),
        "raw_content": """广东省高新技术企业税收优惠申报指南（2026 年版）

根据《中华人民共和国企业所得税法》及实施条例、《高新技术企业认定管理办法》，
为帮助企业准确享受高新技术企业所得税优惠（税率 15%），制定本指南。

一、优惠内容
高新技术企业适用企业所得税税率 15%（一般企业为 25%），同时研发费用可加计扣除。

二、认定条件
1. 企业须在广东省行政区域内注册成立一年以上
2. 企业拥有核心自主知识产权
3. 企业从事研究开发活动技术领域属于《国家重点支持的高新技术领域》
4. 科技人员占企业当年职工总数的比例不低于 10%
5. 研究开发费用占销售收入比例符合要求（最近一年销售收入 5000 万元以上的，比例不低于 3%）
6. 高新技术产品（服务）收入占企业当年总收入的比例不低于 60%

三、申报材料
1. 高新技术企业认定申请书
2. 企业营业执照副本、税务登记证
3. 知识产权证书、科研项目立项证明
4. 经审计的近三个会计年度财务报告
5. 研究开发费用及高新技术产品（服务）收入专项审计报告
6. 职工和科技人员情况说明

四、申报时间
本年度集中受理时间：2026 年 7 月 1 日至 9 月 30 日。
预计节税：营业收入 1 亿元的高新技术企业，年节税额约 100-300 万元。

五、有效期
高新技术企业资格有效期为三年，到期前三个月内重新申请认定。
""",
    },
    {
        "source_id": "gd_kjt",
        "url": "mock://gd_kjt/2026-002",
        "title": "广东省瞪羚企业认定与扶持办法",
        "published_at": date(2026, 6, 22),
        "raw_content": """广东省瞪羚企业认定与扶持办法

为支持高成长中小企业跨越发展，培育一批瞪羚企业、独角兽企业，
根据《广东省培育前沿新材料产业集群行动计划》等文件精神，制定本办法。

一、认定标准
瞪羚企业须同时满足以下条件：
1. 在广东省内注册，具有独立法人资格
2. 属有效期内的高新技术企业或科技型中小企业
3. 上年度营业收入在 1000 万元至 5 亿元之间
4. 营业收入或净利润近三年复合增长率不低于 20%
5. 研发投入占营业收入比例不低于 5%

二、扶持措施
1. 资金奖励：首次认定瞪羚企业，给予一次性奖励 30 万元
2. 贷款支持：联合合作银行提供最高 1000 万元信用贷款
3. 研发补贴：年度研发投入的 10% 给予后补助，最高 200 万元
4. 人才政策：核心高管享受省级高层次人才待遇
5. 空间保障：优先安排入驻省市共建的科技企业孵化器

三、申报程序
1. 企业注册登录"广东省科技业务管理阳光政务平台"在线申报
2. 区科技主管部门初审
3. 省科技厅组织专家评审
4. 公示无异议后发布认定名单

四、申报材料
1. 瞪羚企业认定申请书
2. 企业营业执照、近三年财务审计报告
3. 知识产权清单、研发投入明细
4. 营业收入增长率说明材料

五、申报时间
本年度申报截止时间为 2026 年 8 月 30 日，逾期不予受理。
""",
    },
    {
        "source_id": "gov_cn",
        "url": "mock://gov_cn/2026-001",
        "title": "国务院关于深化新一轮财税体制改革的意见",
        "published_at": date(2026, 6, 10),
        "raw_content": """国务院关于深化新一轮财税体制改革的意见

财税体制改革是经济体制改革的重要组成部分。为深入贯彻党的二十大精神，
深化新一轮财税体制改革，现提出如下意见。

一、总体要求
以习近平新时代中国特色社会主义思想为指导，坚持稳中求进工作总基调，
健全现代预算制度，完善税收制度，调整中央与地方财政关系，
建立权责清晰、财力协调、区域均衡的中央和地方财政关系。

二、建立现代预算制度
1. 增强重大战略任务财力保障
2. 健全预算约束机制
3. 推进支出标准体系建设
4. 加强财政资源统筹

三、完善税收制度
1. 健全增值税制度
2. 完善消费税制度
3. 推进个人所得税改革
4. 健全地方税体系
5. 培育地方税源

四、调整中央与地方财政关系
1. 完善中央与地方收入划分
2. 优化转移支付制度
3. 健全省以下财政体制
4. 推进基本公共服务均等化

五、保障措施
1. 加强组织领导
2. 强化协同配合
3. 抓好督查落实
4. 做好宣传引导

本意见自发布之日起施行。各地区各部门要结合实际认真贯彻落实。
""",
    },
]


async def seed() -> int:
    engine = make_engine()
    init_session_factory(engine)

    count = 0
    async with get_session() as session:
        # 取 source_id → PolicySource.id 映射
        stmt = select(PolicySource)
        rows = (await session.execute(stmt)).scalars().all()
        source_map = {s.source_id: s.id for s in rows}
        if not source_map:
            logger.error("No PolicySource found; run seed_sources first")
            return 0

        for p in POLICIES:
            db_source_id = source_map.get(p["source_id"])
            if db_source_id is None:
                logger.warning("Unknown source_id %s, skip", p["source_id"])
                continue

            # 检查是否已存在（按 url）
            existing_stmt = select(Policy).where(Policy.url == p["url"])
            existing = (await session.execute(existing_stmt)).scalar_one_or_none()
            if existing:
                logger.info("Skip (exists): %s", p["url"])
                continue

            session.add(Policy(
                source_id=db_source_id,
                url=p["url"],
                title=p["title"],
                raw_content=p["raw_content"],
                published_at=p["published_at"],
            ))
            count += 1
            logger.info("Inserted: %s", p["title"][:50])

    logger.info("Seeded %d policies", count)
    return count


def main() -> int:
    return asyncio.run(seed())


if __name__ == "__main__":
    sys.exit(main())
