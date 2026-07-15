"""探测河北 8 个厅局的"政策文件"栏目 URL。

在服务器 (43.155.161.54) 上运行:
  cat /tmp/probe_hebei_8.py | docker exec -i policy-radar-app python

输出: 每个部门的政策栏目 URL + 验证: 前 3 条标题
"""
import urllib.request, re, json, sys

# 8 个厅局
SITES = [
    ("prov_hebei_sgdb", "河北省国动办", "https://sgdb.hebei.gov.cn/", "swj"),
    ("prov_hebei_rta", "河北省广电局", "http://rta.hebei.gov.cn/", "rta"),
    ("prov_hebei_yjgl", "河北省应急管理厅", "https://yjgl.hebei.gov.cn/", "yjgl"),
    ("prov_hebei_yjs", "河北省政府研究室", "https://yjs.hebei.gov.cn/", "yjs"),
    ("prov_hebei_sport", "河北省体育局", "http://sport.hebei.gov.cn/", "sport"),
    ("prov_hebei_swj_jg", "河北省机关事务管理局", "https://swj.hebei.gov.cn/", "swj_jg"),
    ("prov_hebei_mw", "河北省民委", "http://mw.hebei.gov.cn/", "mw"),
    ("prov_hebei_whly", "河北省文旅厅", "https://whly.hebei.gov.cn/", "whly"),
    ("prov_hebei_nync", "河北省农业农村厅", "http://nync.hebei.gov.cn/", "nync"),
]

POLICY_TERMS = ["政策", "法规", "规章", "规范性文件", "厅发文件", "文件", "解读", "制度", "目录", "标准", "细则"]

POLICY_TITLE_KEYWORDS = [
    "通知", "办法", "意见", "条例", "规定", "实施细则", "方案", "细则",
    "决定", "命令", "公告", "标准", "规范", "指南", "规则", "意见", "准则",
    "办法", "规程", "制度", "规范", "条文"
]

NON_POLICY_TITLE_KEYWORDS = [
    "开展", "调研", "召开", "走访", "庆祝", "上线", "揭牌",
    "招标", "采购", "询价", "成交", "中标", "比选",
]


def normalize_url(href, base):
    """补全相对链接"""
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return base.rstrip("/") + href
    return base + href


def probe_list(url, timeout=12):
    """访问列表页，提取 (title, url) 列表"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36"})
        html = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", errors="replace")
    except Exception as e:
        return None, str(e)

    # 抓所有 a 链接
    items = re.findall(r'href="([^"]+)"[^>]*>([^<]{4,100})</a>', html)
    result = []
    seen = set()
    for href, text in items:
        text = text.strip()
        href = href.strip()
        if not text or len(text) < 4:
            continue
        if href in seen:
            continue
        seen.add(href)
        if href.startswith("javascript:") or href.startswith("#"):
            continue
        result.append((text, href))
    return result, html


def score_listing(items, list_url):
    """给列表页打分"""
    if not items:
        return -1, []
    # 跳过导航/首页/联系我们/网站声明
    SKIP = ["首页", "联系我们", "网站声明", "网站地图", "站点地图",
            "信息公开指南", "公开年报", "依申请公开", "RSS", "无障碍"]
    real_items = [(t, h) for t, h in items if not any(s in t for s in SKIP) and "/home/" not in h and "/list" not in h.lower()]
    if not real_items:
        return 0, []

    # 计算政策关键词命中
    policy_hits = 0
    non_policy_hits = 0
    for t, h in real_items[:20]:
        if any(kw in t for kw in POLICY_TITLE_KEYWORDS):
            policy_hits += 1
        if any(kw in t for kw in NON_POLICY_TITLE_KEYWORDS):
            non_policy_hits += 1

    # URL path 命中
    path_bonus = 0
    for path in ["/zcwj/", "/zcfg/", "/zwgk/", "/tzgg/", "/xxgk/", "/zfgb/", "/fgwj/"]:
        if path in list_url:
            path_bonus = 3
            break

    # 栏目名匹配
    cat_bonus = 0
    for term in POLICY_TERMS:
        if term in list_url:
            cat_bonus = 2
            break

    score = policy_hits * 2 - non_policy_hits * 3 + path_bonus + cat_bonus
    return score, real_items[:5]


def main():
    print("=" * 80)
    print("河北 8 个厅局 政策栏目探测")
    print("=" * 80)

    results = []
    for source_id, name, base_url, _ in SITES:
        print(f"\n{'─' * 70}")
        print(f"### {name} ({source_id})")
        print(f"   首页: {base_url}")

        # 1. 抓首页
        items, html_or_err = probe_list(base_url)
        if not items:
            print(f"  [X] 首页抓取失败: {html_or_err}")
            results.append({"source_id": source_id, "name": name, "best_url": None, "error": html_or_err})
            continue

        # 2. 提取首页中含政策关键词的链接
        policy_candidates = []
        for text, href in items:
            if any(term in text for term in POLICY_TERMS) and not any(s in text for s in ["首页", "联系我们", "网站声明"]):
                full = normalize_url(href, base_url)
                if "hebei.gov.cn" in full or full.startswith(base_url):
                    policy_candidates.append((text, full))

        print(f"  首页 {len(items)} 个链接, {len(policy_candidates)} 个含政策关键词")
        for text, url in policy_candidates[:8]:
            print(f"    候选: [{text}] {url[:80]}")

        # 3. 对每个候选栏目评分
        best = None
        best_score = -1
        all_candidates = []
        for text, url in policy_candidates:
            # 跳过 .css .js .png
            if any(url.endswith(ext) for ext in [".css", ".js", ".png", ".jpg", ".gif"]):
                continue
            # 跳过纯链接
            if url.rstrip("/") == base_url.rstrip("/"):
                continue
            items, err = probe_list(url)
            if not items:
                print(f"    [X] {url} 抓取失败: {err}")
                continue
            score, real_items = score_listing(items, url)
            print(f"    [{score:>3}] {url[:70]}")
            if real_items:
                titles = [t for t, h in real_items[:3]]
                print(f"         前3条: {titles}")
            all_candidates.append({"text": text, "url": url, "score": score, "sample_titles": [t for t, h in real_items[:3]] if real_items else []})
            if score > best_score:
                best_score = score
                best = {"text": text, "url": url, "score": score, "sample_titles": [t for t, h in real_items[:3]] if real_items else []}

        # 4. 兜底：尝试常见路径
        common_paths = [
            "/zwgk/zcwj/", "/zwgk/zcfg/", "/zwgk/zfgb/",
            "/zcwj/", "/zcfg/", "/zfgb/",
            "/xxgk/zcwj/", "/xxgk/zcfg/",
            "/tzgg/", "/xwzx/zcwj/", "/xwzx/zcfg/",
            "/zcjd/",  # 政策解读
        ]
        for path in common_paths:
            test_url = base_url.rstrip("/") + path
            items, err = probe_list(test_url)
            if not items:
                continue
            score, real_items = score_listing(items, test_url)
            if score > best_score:
                best_score = score
                best = {"text": path, "url": test_url, "score": score, "sample_titles": [t for t, h in real_items[:3]] if real_items else []}
                print(f"    兜底命中: {test_url} (score={score})")

        if best:
            print(f"\n  ✓ 最佳: {best['url']}")
            print(f"    栏目: {best['text']}")
            print(f"    评分: {best['score']}")
            print(f"    前3条: {best['sample_titles']}")
        else:
            print(f"\n  ✗ 未找到合适的政策栏目")

        results.append({
            "source_id": source_id,
            "name": name,
            "best_url": best["url"] if best else None,
            "best_text": best["text"] if best else None,
            "best_score": best["score"] if best else None,
            "sample_titles": best["sample_titles"] if best else [],
            "candidates": all_candidates,
        })

    print(f"\n{'=' * 80}")
    print("探测结果 JSON (供后续自动更新 spider config 使用)")
    print(f"{'=' * 80}")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
