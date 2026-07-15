"""探测秦皇岛市各部门网站的政策文件栏目URL和选择器。

在服务器上运行（需要中国大陆IP）:
  docker exec policy-radar-app python -m scripts.probe_qhd_fix

输出可直接用于更新 spider config 的 JSON。
"""
import asyncio, json, re, sys, os
from playwright.async_api import async_playwright

# 需要修复的QHD部门
TARGETS = [
    {
        "source_id": "city_qhd_lywgj",
        "name": "秦皇岛市文旅局",
        "homepage": "http://lywgj.qhd.gov.cn/",
    },
    {
        "source_id": "city_qhd_wjw",
        "name": "秦皇岛市卫健委",
        "homepage": "http://wjw.qhd.gov.cn/",
    },
    {
        "source_id": "city_qhd_zyghj",
        "name": "秦皇岛市自然资源和规划局",
        "homepage": "http://zyghj.qhd.gov.cn/",
    },
    {
        "source_id": "city_qhd_jtj",
        "name": "秦皇岛市交通局",
        "homepage": "http://jtj.qhd.gov.cn/",
    },
]

# 已知有效的政策栏目关键词
POLICY_KEYWORDS = [
    "政策文件", "政策法规", "政策", "规范性文件", "通知公告",
    "政务公开", "信息公开", "政府信息公开", "公告公示",
    "部门文件", "法规文件", "法规规章",
]

# 已知有效的 list URL 模式
LIST_PATTERNS = [
    r'/home/list/\?code=',        # QHD 统一平台
    r'/home/xzzfgstablist\?code=', # 住建局特例
    r'/list\.jsp\?',               # 老平台
    r'/info/list\.jsp\?',          # 规范性文件
    r'/tzgg/',                     # 通知公告
    r'/zwgk/',                     # 政务公开
    r'/zcwj/',                     # 政策文件
    r'/zcfg/',                     # 政策法规
]


async def probe_one(browser, target):
    """探一个部门网站，找到政策列表页URL"""
    sid = target["source_id"]
    homepage = target["homepage"]
    print(f"\n{'='*60}")
    print(f"探测: {target['name']} ({sid})")
    print(f"首页: {homepage}")

    page = await browser.new_page()
    result = {
        "source_id": sid,
        "homepage": homepage,
        "policy_list_urls": [],
        "best_url": None,
        "best_reason": "",
        "error": None,
    }

    try:
        await page.goto(homepage, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        # 获取页面所有链接
        links = await page.evaluate('''() => {
            const links = Array.from(document.querySelectorAll('a[href]'));
            return links.map(a => ({
                text: (a.textContent || '').trim(),
                href: a.href || '',
                innerText: (a.innerText || '').trim(),
            })).filter(l => l.href && !l.href.startsWith('javascript:') && !l.href.startsWith('#'));
        }''')

        # 分类链接
        policy_links = []
        list_links = []
        detail_links = []
        nav_links = []

        for link in links:
            text = link['text'] + link['innerText']
            href = link['href']

            # 导航类
            if any(kw in text for kw in ['首页', '机构', '领导', '互动', '留言', '咨询', '投诉', '服务', '办事', '省情', '概况']):
                if len(text) < 10:
                    nav_links.append(link)
                    continue

            # 政策列表页
            is_list = False
            for pat in LIST_PATTERNS:
                if re.search(pat, href):
                    is_list = True
                    break
            if is_list:
                list_links.append(link)
                continue

            # 政策栏目关键词
            if any(kw in text for kw in POLICY_KEYWORDS):
                policy_links.append(link)
                continue

            # 详情页
            if '/home/details' in href or '/info/' in href or '/content/' in href:
                detail_links.append(link)

        print(f"  找到 {len(policy_links)} 个政策栏目链接, {len(list_links)} 个列表页链接, {len(detail_links)} 个详情链接")

        # 优先选择 list 模式的链接
        best = None
        for link in list_links:
            text = link['text'] + link['innerText']
            href = link['href']
            # 优先匹配包含政策关键词的
            score = 0
            if any(kw in text for kw in ['政策文件', '政策法规', '规范性文件']):
                score = 10
            elif any(kw in text for kw in ['通知公告', '公告公示']):
                score = 5
            elif any(kw in text for kw in ['政务公开', '信息公开']):
                score = 3

            if '/home/list/' in href:
                score += 5  # QHD统一平台优先
            if '/tzgg/' in href:
                score += 3

            if best is None or score > best.get('score', 0):
                best = {"url": href, "text": text, "score": score}

        if best:
            result["best_url"] = best["url"]
            result["best_reason"] = f"列表页: {best['text']} (score={best['score']})"
            result["policy_list_urls"] = [l['href'] for l in list_links[:5]]
            print(f"  => 最佳: {best['url']}")
            print(f"     原因: {best['text']}")

            # 进一步探测：打开列表页确认有有效链接
            try:
                await page.goto(best["url"], wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2000)
                detail_links_on_list = await page.evaluate('''() => {
                    return Array.from(document.querySelectorAll('a[href*="/home/details"], a[href*="/info/"], a[href*="/content/"]'))
                        .slice(0, 5)
                        .map(a => ({
                            text: (a.textContent || '').trim().substring(0, 80),
                            href: a.href
                        }));
                }''')
                result["sample_details"] = detail_links_on_list
                print(f"  列表页含 {len(detail_links_on_list)} 条详情链接:")
                for d in detail_links_on_list:
                    print(f"    - {d['text'][:60]}")
            except Exception as e:
                print(f"  列表页探测失败: {e}")
        else:
            # 没找到list模式，尝试policy链接
            for link in policy_links:
                text = link['text'] + link['innerText']
                href = link['href']
                print(f"  候选: [{text[:40]}] {href[:100]}")

            # 尝试常见子路径
            domain = homepage.rstrip('/')
            candidates = [
                f"{domain}/home/list/?code=",  # QHD统一平台需要code
                f"{domain}/tzgg/",
                f"{domain}/zwgk/",
                f"{domain}/zcwj/",
            ]
            print(f"  无明确列表页，尝试常见路径...")
            for c in candidates:
                print(f"  需手动验证: {c}")

    except Exception as e:
        result["error"] = str(e)
        print(f"  ERROR: {e}")
    finally:
        await page.close()

    return result


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        results = []
        for target in TARGETS:
            result = await probe_one(browser, target)
            results.append(result)

        await browser.close()

    print(f"\n{'='*60}")
    print("修复建议汇总")
    print(f"{'='*60}")
    for r in results:
        print(f"\n{r['source_id']}:")
        if r['error']:
            print(f"  ERROR: {r['error']}")
        elif r['best_url']:
            print(f"  list_url: {r['best_url']}")
            print(f"  item_selector: a[href*='/home/details']")
            print(f"  原因: {r['best_reason']}")
            if 'sample_details' in r:
                print(f"  样本: {len(r['sample_details'])} 条")
        else:
            print(f"  未找到合适的列表页URL，需手动查找")

    # 输出JSON供后续使用
    print(f"\n\n=== JSON OUTPUT ===")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
