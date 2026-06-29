#!/usr/bin/env python3
import json
import os
import re
from pathlib import Path

ROOT = Path(r"C:\Users\Fangyi\OneDrive\文档\Claude\政策收集总结\policy-radar\rsshub_repo\lib\routes\gov")

PATH_RE = re.compile(r"path:\s*['\"`]([^'\"`]+)['\"`]")
EXAMPLE_RE = re.compile(r"example:\s*['\"`]([^'\"`]+)['\"`]")


def main():
    files = sorted(
        (p for p in ROOT.rglob("*.ts") if p.is_file()),
        key=lambda x: str(x.relative_to(ROOT)).lower(),
    )
    results = []
    for fp in files:
        rel = str(fp.relative_to(ROOT)).replace(os.sep, "/")
        src = fp.read_text(encoding="utf-8", errors="ignore")
        mp = PATH_RE.search(src)
        me = EXAMPLE_RE.search(src)
        results.append({
            "file": rel,
            "path": mp.group(1) if mp else None,
            "example": me.group(1) if me else None,
        })
        print(f"  {rel} -> {mp.group(1) if mp else None} | {me.group(1) if me else None}", flush=True)

    out = Path(r"C:\Users\Fangyi\OneDrive\文档\Claude\政策收集总结\policy-radar\rsshub_gov_paths.json")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nTOTAL: {len(results)}")
    print(f"WITH_EXAMPLE: {sum(1 for r in results if r['example'])}")


if __name__ == "__main__":
    main()