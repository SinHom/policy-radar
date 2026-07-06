import json, os, subprocess, urllib.request

req = urllib.request.Request("http://localhost:8000/api/sources")
with urllib.request.urlopen(req) as resp:
    sources = json.loads(resp.read())

hebei = [s for s in sources if any(kw in s.get("source_id","") for kw in ["hebei","qhd","_pr_"])]
print(f"Found {len(hebei)} Hebei/QHD sources")

outdir = "/opt/policy-radar/spiders_new"
os.makedirs(outdir, exist_ok=True)

for s in hebei:
    sid = s["source_id"]
    cfg = s.get("spider_config", {})
    if not cfg:
        print(f"  SKIP {sid}: empty spider_config")
        continue
    path = os.path.join(outdir, f"{sid}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f"  WROTE {path}")

result = subprocess.run(["docker", "ps", "-q", "-f", "name=policy"], capture_output=True, text=True)
container = result.stdout.strip()
if container:
    subprocess.run(["docker", "cp", outdir + "/.", container + ":/app/python/crawlers/spiders/"])
    print(f"Copied to container {container[:12]}")
else:
    print("No container with 'policy' in name, listing all:")
    subprocess.run(["docker", "ps", "--format", "{{.ID}} {{.Names}}"])
