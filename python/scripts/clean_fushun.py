import sqlite3, sys

db_path = sys.argv[1] if len(sys.argv) > 1 else '/app/data/policy_radar.db'
conn = sqlite3.connect(db_path)
cur = conn.cursor()

# 8 WeChat articles + 1 TOC page
bad_ids = [3029, 3031, 3035, 3036, 3037, 3038, 3041, 3062, 3094]

for pid in bad_ids:
    cur.execute('SELECT title FROM policies WHERE id = ?', (pid,))
    r = cur.fetchone()
    if r:
        cur.execute('DELETE FROM policies WHERE id = ?', (pid,))
        title = (r[0] or '')[:60]
        print(f'DELETED id={pid}: {title}')
    else:
        print(f'NOT FOUND id={pid}')

conn.commit()

cur.execute("""SELECT COUNT(*) FROM policies p
JOIN policy_sources ps ON p.source_id = ps.id
WHERE ps.region LIKE '%抚顺%'""")
new_total = cur.fetchone()[0]
print(f'\n清理后抚顺政策总数: {new_total}')

# Re-run stats by department
cur.execute("""SELECT ps.department, COUNT(*) as cnt FROM policies p
JOIN policy_sources ps ON p.source_id = ps.id
WHERE ps.region LIKE '%抚顺%'
  AND ps.department IS NOT NULL AND ps.department != ''
GROUP BY ps.department ORDER BY cnt DESC""")
print('\n部门分布:')
for r in cur.fetchall():
    print(f'  {r["department"]}: {r["cnt"]}')

conn.close()
