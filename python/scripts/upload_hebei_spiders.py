"""Upload all Hebei/QHD spider configs to server via HTTP API (through proxy).

Usage: python upload_hebei_spiders.py
Stdlib only — no pip install needed.
"""
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

API_BASE = "http://43.155.161.54:8000"
PROXY = "http://127.0.0.1:10808"
SPIDERS_DIR = Path(__file__).resolve().parent.parent / "crawlers" / "spiders"


def _setup_proxy():
    """Set system proxy for urllib."""
    ph = urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
    opener = urllib.request.build_opener(ph)
    urllib.request.install_opener(opener)


def _api(method: str, path: str, token: str | None = None, body: dict | None = None) -> dict:
    """Make an API call, return (status, response_body_dict)."""
    url = API_BASE + path
    data = json.dumps(body).encode("utf-8") if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"detail": raw}


def login() -> str:
    """Login and return bearer token."""
    status, data = _api("POST", "/api/auth/login",
                        body={"username": "admin", "password": "policy-radar-2026"})
    if status != 200:
        raise RuntimeError(f"Login failed: {status} {data}")
    token = data["token"]
    print(f"[LOGIN] token={token[:8]}...")
    return token


def list_sources(token: str) -> list[dict]:
    """Get all sources from server."""
    status, data = _api("GET", "/api/sources", token=token)
    if status != 200:
        raise RuntimeError(f"List sources failed: {status}")
    return data if isinstance(data, list) else []


def upload_or_update(token: str, spider_json: dict, existing_map: dict[str, dict]) -> bool:
    """Upload a single spider config. Update if exists."""
    source_id = spider_json["source_id"]
    body = {
        "source_id": source_id,
        "name": spider_json["name"],
        "url": spider_json.get("list_url", spider_json.get("url", "")),
        "category": spider_json.get("category", ""),
        "region": spider_json.get("region", ""),
        "department": spider_json.get("department", ""),
        "tags": [spider_json["mode"]] if spider_json.get("mode") else [],
        "spider_config": spider_json,
        "frequency": spider_json.get("frequency", "daily"),
        "enabled": True,
    }

    if source_id in existing_map:
        db_id = existing_map[source_id]["id"]
        status, data = _api("PATCH", f"/api/sources/{db_id}", token=token, body={
            "name": body["name"], "url": body["url"],
            "category": body["category"], "region": body["region"],
            "department": body["department"], "tags": body["tags"],
            "spider_config": body["spider_config"],
            "frequency": body["frequency"], "enabled": True,
        })
        if 200 <= status < 300:
            print(f"  [UPDATED] {source_id}")
            return True
        else:
            print(f"  [UPDATE ERR {status}] {source_id}: {data}")
            return False
    else:
        status, data = _api("POST", "/api/sources", token=token, body=body)
        if 200 <= status < 300:
            print(f"  [CREATED] {source_id}")
            return True
        else:
            detail = data.get("detail", str(data))
            print(f"  [ERROR {status}] {source_id}: {detail[:150]}")
            return False


def main():
    _setup_proxy()

    # Find all hebei/qhd spider files
    spider_files = sorted(
        f for f in SPIDERS_DIR.glob("*.json")
        if any(kw in f.stem for kw in ["hebei", "qhd"])
    )
    print(f"Found {len(spider_files)} spider configs to upload\n")

    # Login
    try:
        token = login()
    except Exception as e:
        print(f"Login failed via proxy: {e}")
        print("Trying direct...")
        # Try without proxy
        urllib.request.install_opener(urllib.request.build_opener())
        try:
            token = login()
        except Exception as e2:
            print(f"Login also failed direct: {e2}")
            sys.exit(1)

    # Get existing sources for conflict detection
    print("Fetching existing sources...")
    try:
        existing = {s["source_id"]: s for s in list_sources(token)}
    except Exception as e:
        print(f"Warning: could not list sources: {e}")
        existing = {}
    print(f"  {len(existing)} sources already in DB\n")

    # Upload each spider
    ok, fail, skip = 0, 0, 0
    for f in spider_files:
        try:
            cfg = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [SKIP] {f.name}: {e}")
            skip += 1
            continue

        success = upload_or_update(token, cfg, existing)
        if success:
            ok += 1
        else:
            fail += 1
        time.sleep(0.2)

    print(f"\n--- Done: {ok} OK, {fail} failed, {skip} skipped (of {len(spider_files)}) ---")


if __name__ == "__main__":
    main()
