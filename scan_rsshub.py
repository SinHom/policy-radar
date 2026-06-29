#!/usr/bin/env python3
"""Scan RSSHub lib/routes/gov via GitHub Tree API (1 call) + raw.githubusercontent (no rate limit)."""
import base64
import json
import re
import urllib.request

TREE_API = "https://api.github.com/repos/DIYgod/RSSHub/git/trees/main?recursive=1"
RAW = "https://raw.githubusercontent.com/DIYgod/RSSHub/main/"

PATH_RE = re.compile(r"path:\s*['\"`]([^'\"`]+)['\"`]")
EXAMPLE_RE = re.compile(r"example:\s*['\"`]([^'\"`]+)['\"`]")


def gh_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "scanner"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def fetch_raw(path):
    url = RAW + path
    req = urllib.request.Request(url, headers={"User-Agent": "scanner"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="ignore")


def main():
    tree = gh_get(TREE_API)
    files = [
        t["path"]
        for t in tree.get("tree", [])
        if t["path"].startswith("lib/routes/gov/")
        and t["path"].endswith(".ts")
        and t["type"] == "blob"
    ]
    files.sort(key=str.lower)
    print(f"files: {len(files)}", flush=True)

    results = []
    for p in files:
        try:
            src = fetch_raw(p)
        except Exception as e:
            print(f"  ERR {p}: {e}", flush=True)
            continue
        mp = PATH_RE.search(src)
        me = EXAMPLE_RE.search(src)
        rel = p[len("lib/routes/gov/"):]
        rec = {
            "file": rel,
            "path": mp.group(1) if mp else None,
            "example": me.group(1) if me else None,
        }
        results.append(rec)
        print(f"  {rel} -> {rec['path']} | {rec['example']}", flush=True)

    with open("rsshub_gov_paths.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nTOTAL: {len(results)}")
    print(f"WITH_EXAMPLE: {sum(1 for r in results if r['example'])}")


if __name__ == "__main__":
    main()