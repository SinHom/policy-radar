"""服务器端种子脚本：将上海 spider config 写入 policy_sources 表。"""
import json, os, asyncio, sys
sys.path.insert(0, '/app/python')

from sqlalchemy import select
from python.models import PolicySource
from python.models.base import get_session, init_session_factory, make_engine

async def seed():
    engine = make_engine()
    init_session_factory(engine)
    async with get_session() as session:
        result = await session.execute(select(PolicySource.source_id))
        existing = set(result.scalars().all())

    spiders_dir = '/app/python/crawlers/spiders/'
    new_ids = []
    for f in sorted(os.listdir(spiders_dir)):
        if f.startswith('sh_') and f.endswith('.json') and not f.startswith('rss_sh_'):
            sid = f.replace('.json', '')
            if sid not in existing:
                new_ids.append(sid)

    print(f'To seed: {len(new_ids)} sources')
    for sid in new_ids:
        path = os.path.join(spiders_dir, f'{sid}.json')
        with open(path, encoding='utf-8') as fp:
            cfg = json.load(fp)
        async with get_session() as session:
            src = PolicySource(
                source_id=sid, name=cfg.get('name', sid),
                url=cfg.get('list_url', ''), category=cfg.get('category', '市级'),
                department=cfg.get('department', ''), region='上海',
                spider_config=cfg, frequency='daily', enabled=True, last_status='pending',
            )
            session.add(src)
            await session.commit()
        print(f'  + {sid}')

    print(f'Done. Seeded {len(new_ids)} sources.')
    return len(new_ids)

if __name__ == '__main__':
    n = asyncio.run(seed())
    print(f'Result: {n}')
