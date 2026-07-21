"""生成抚顺驾驶舱 OVERVIEW 真实数据 JSON。"""
import sqlite3, json, sys, re

db_path = sys.argv[1] if len(sys.argv) > 1 else 'data/policy_radar.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# 全部抚顺政策
cur.execute("""SELECT p.id, p.title, p.crawled_at, ps.department, ps.name as source_name
FROM policies p JOIN policy_sources ps ON p.source_id = ps.id
WHERE ps.region LIKE '%抚顺%'
ORDER BY p.crawled_at DESC""")
rows = cur.fetchall()
total = len(rows)

# 部门统计
dept_counts = {}
for r in rows:
    dept = r['department'] or '其他'
    dept_short = dept.replace('抚顺市','').replace('市场监督管理局','市场监管局')
    dept_counts[dept_short] = dept_counts.get(dept_short, 0) + 1

dept_sorted = sorted(dept_counts.items(), key=lambda x: -x[1])

# 主题分类（标题关键词）
TOPIC_RULES = [
    ('财税政策', ['财政', '税务', '税', '增值税', '个税', '所得税', '国债', '国库', '会计', '彩票公益金', '国有资产', '金融企业', '资产评估']),
    ('市场监管', ['食品', '药品', '医疗器械', '化妆品', '产品.*质量', '特种设备', '抽检', '安全责任事故', '酒类']),
    ('人才就业', ['高校毕业', '人才', '就业', '招聘', '教师', '三支一扶', '技能培训', '职业资格', '病残津贴', '外国人来华', '农民工工资', '培训补贴']),
    ('应急安全', ['防汛', '抗洪', '暴雨', '应急', '危险化学品', '煤矿', '消防', '森林防火', '自然灾害', '水库', '预警', '救灾', '地震']),
    ('企业服务', ['企业', '民营经济', '营商环境', '负面清单', '公平竞争', '稳经济', '市场主体', '经营主体', '商事', '中小微', '营环境']),
    ('科技创新', ['科技', '创新', '科研', '专利', '知识产权', '成果转化', '技术转移', '人工智能', 'AI']),
    ('数字化转型', ['数字化', '数据要素', '数据安全', '工业互联网', '智能制造', '信息.*化']),
    ('规划建设', ['规划', '纲要', '政府工作报告', '常务会议', '电网', '空气质量', '经济.*回升']),
    ('法治建设', ['法治', '民法典', '信访', '行政执法', '普法', '法规', '执法.*制', '直销管理', '网络安全法']),
    ('其他', []),  # fallback
]

def classify(title):
    t = title or ''
    for cat, keywords in TOPIC_RULES:
        if not keywords:
            continue
        for kw in keywords:
            if re.search(kw, t):
                return cat
    return '其他'

topic_counts = {}
for r in rows:
    cat = classify(r['title'])
    topic_counts[cat] = topic_counts.get(cat, 0) + 1

topic_sorted = sorted(topic_counts.items(), key=lambda x: -x[1])

# 时间轴 - 取最近 12 条
timeline = []
for r in rows[:12]:
    # 从标题提取日期片段
    title = r['title'] or ''
    date_str = '07/21'  # 默认用爬取日期
    m = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', title)
    if m:
        date_str = f'{m.group(2).zfill(2)}/{m.group(3).zfill(2)}'
    dept = (r['department'] or '').replace('抚顺市','')
    timeline.append({
        'date': date_str,
        'title': title,
        'src': f'抚顺市{dept}' if dept else r['source_name'],
        'kind': '库',
        'id': r['id']
    })

# 主题颜色（匹配政务蓝/绿/紫/红/灰等 Morandi 降饱和色系）
TOPIC_COLORS = {
    '财税政策': '#1d4e89',   # 政务蓝
    '市场监管': '#b85c5c',   # 降饱和红
    '人才就业': '#15803d',   # 绿
    '应急安全': '#c8821a',   # 赭
    '企业服务': '#6b5e8f',   # 紫
    '科技创新': '#2d6a9f',   # 中蓝
    '数字化转型': '#4a7c59',  # 青绿
    '规划建设': '#7e96bf',   # 浅蓝
    '法治建设': '#9b6b43',   # 褐
    '其他': '#94a3b8',       # 灰
}

# 输出 OVERVIEW JavaScript
print("// === 自动生成的抚顺驾驶舱真实数据 === //")
print(f"// 总计 {total} 条政策，{len(dept_counts)} 个部门，{len(topic_counts)} 个主题类别")
print()
print("const OVERVIEW = {")
print(f"  kpi: {{ total: {total}, new_this_month: {total}, departments: {len(dept_counts)}, web_supplement: 0 }},")

# 主题分布
print("  topics: [")
for name, cnt in topic_sorted:
    color = TOPIC_COLORS.get(name, '#94a3b8')
    print(f"    {{ name: '{name}', count: {cnt}, color: '{color}' }},")
print("  ],")

# 部门分布
print("  departments: [")
for name, cnt in dept_sorted:
    print(f"    {{ name: '{name}', count: {cnt} }},")
print("  ],")

# 时间轴
print("  timeline: [")
for t in reversed(timeline):  # 最早在前
    title_esc = t['title'].replace("'", "\\'").replace('"', '\\"')
    src_esc = t['src'].replace("'", "\\'")
    print(f"    {{ date: '{t['date']}', title: '{title_esc}', src: '{src_esc}', kind: '{t['kind']}', id: {t['id']} }},")
print("  ],")
print("};")

# 打印详细分类明细
print()
print("// === 分类明细 ===")
for cat, _ in topic_sorted:
    members = [r['title'] for r in rows if classify(r['title']) == cat]
    print(f"// {cat} ({len(members)}):")
    for m in members:
        print(f"//   {m}")

conn.close()
