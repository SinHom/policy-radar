"""统计抚顺政策库真实数据，用于驾驶舱页 OVERVIEW 更新。"""
import sqlite3, json, sys

db_path = sys.argv[1] if len(sys.argv) > 1 else 'data/policy_radar.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# 1. 抚顺政策总数
cur.execute("""SELECT COUNT(*) as cnt FROM policies p
JOIN policy_sources ps ON p.source_id = ps.id
WHERE ps.region LIKE '%抚顺%'""")
total = cur.fetchone()['cnt']
print(f"抚顺政策总数: {total}")

# 2. 本月新增
cur.execute("""SELECT COUNT(*) as cnt FROM policies p
JOIN policy_sources ps ON p.source_id = ps.id
WHERE ps.region LIKE '%抚顺%'
  AND p.published_at >= '2026-07-01'""")
new_m = cur.fetchone()['cnt']
print(f"本月新增: {new_m}")

# 3. 部门分布
cur.execute("""SELECT ps.department as dept, COUNT(*) as cnt FROM policies p
JOIN policy_sources ps ON p.source_id = ps.id
WHERE ps.region LIKE '%抚顺%'
  AND ps.department IS NOT NULL AND ps.department != ''
GROUP BY ps.department ORDER BY cnt DESC""")
dept_rows = cur.fetchall()
print(f"覆盖部门: {len(dept_rows)}")
departments = []
for r in dept_rows:
    print(f"  {r['dept']}: {r['cnt']}")
    departments.append({"name": r['dept'], "count": r['cnt']})

# 4. 辽宁省级
cur.execute("""SELECT COUNT(*) as cnt FROM policies p
JOIN policy_sources ps ON p.source_id = ps.id
WHERE ps.region LIKE '%辽宁%' AND ps.region NOT LIKE '%抚顺%'""")
ln = cur.fetchone()['cnt']
print(f"辽宁省级(不含抚顺): {ln}")

# 5. 国家级
cur.execute("""SELECT COUNT(*) as cnt FROM policies p
JOIN policy_sources ps ON p.source_id = ps.id
WHERE (ps.region LIKE '%全国%' OR ps.region LIKE '%国家%')
  AND ps.region NOT LIKE '%辽宁%'""")
nat = cur.fetchone()['cnt']
print(f"国家级: {nat}")

# 6. 抚顺+辽宁+国家级 合计（与 advisor_fushun RAG region_cond 一致）
cur.execute("""SELECT COUNT(*) as cnt FROM policies p
JOIN policy_sources ps ON p.source_id = ps.id
WHERE ps.region LIKE '%抚顺%'
   OR ps.region LIKE '%辽宁%'
   OR ps.category = '国家级'""")
full_scope = cur.fetchone()['cnt']
print(f"抚顺+辽宁+国家级(advisor检索范围): {full_scope}")

# 7. 按数据源
cur.execute("""SELECT ps.name, COUNT(*) as cnt FROM policies p
JOIN policy_sources ps ON p.source_id = ps.id
WHERE ps.region LIKE '%抚顺%'
GROUP BY ps.name ORDER BY cnt DESC""")
print("\n按数据源:")
for r in cur.fetchall():
    print(f"  {r['name']}: {r['cnt']}")

# 8. 按 spider config
cur.execute("""SELECT ps.spider_config, COUNT(*) as cnt FROM policies p
JOIN policy_sources ps ON p.source_id = ps.id
WHERE ps.region LIKE '%抚顺%'
GROUP BY ps.spider_config ORDER BY cnt DESC""")
print("\n按spider:")
for r in cur.fetchall():
    print(f"  {r['spider_config']}: {r['cnt']}")

# 9. 最近 20 条（用于 timeline）
cur.execute("""SELECT p.id, p.title, p.published_at, ps.department, ps.region
FROM policies p
JOIN policy_sources ps ON p.source_id = ps.id
WHERE ps.region LIKE '%抚顺%'
ORDER BY p.published_at DESC LIMIT 20""")
print("\n最近20条(用于timeline):")
timeline = []
for r in cur.fetchall():
    d = r['published_at'][:10] if r['published_at'] else '?'
    print(f"  {d} | id={r['id']} | {r['department']} | {r['title'][:60]}")
    timeline.append({
        "id": r['id'],
        "title": r['title'],
        "date": d,
        "department": r['department']
    })

# 10. 所有标题（用于主题分类统计）
cur.execute("""SELECT p.title, ps.department FROM policies p
JOIN policy_sources ps ON p.source_id = ps.id
WHERE ps.region LIKE '%抚顺%'""")
all_titles = [(r['title'], r['department']) for r in cur.fetchall()]
print(f"\n全部 {len(all_titles)} 条标题:")
for t, d in all_titles:
    print(f"  [{d}] {t}")

conn.close()
