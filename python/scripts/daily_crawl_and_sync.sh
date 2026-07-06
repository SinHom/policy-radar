#!/bin/bash
# Daily crawl for Hebei/QHD sources + sync to server
# Usage: bash python/scripts/daily_crawl_and_sync.sh
# Must be run from policy-radar project root
# Requires: venv activated, SSH key at ~/.ssh/policy-radar-key

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

SERVER="root@43.155.161.54"
SSH_KEY="$HOME/.ssh/policy-radar-key"

echo "=== $(date) Starting daily Hebei/QHD crawl ==="

# Activate venv
source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate 2>/dev/null

# Crawl all Hebei/QHD sources
PYTHONPATH=. python -m python.crawlers \
  --source prov_hebei_fgw --source prov_hebei_gov --source prov_hebei_czt \
  --source prov_hebei_kjt --source prov_hebei_gxt --source prov_hebei_scjg \
  --source prov_hebei_zfcxjst --source prov_hebei_sthjt --source prov_hebei_zrzy \
  --source prov_hebei_jtt --source prov_hebei_slt --source prov_hebei_swt \
  --source prov_hebei_nync --source prov_hebei_wsjkw --source prov_hebei_jyt \
  --source prov_hebei_rst --source prov_hebei_whly --source prov_hebei_minzheng \
  --source prov_hebei_sjt --source prov_hebei_tjj --source prov_hebei_sport \
  --source prov_hebei_gat --source prov_hebei_sft --source prov_hebei_swj_jg \
  --source prov_hebei_sgdb --source prov_hebei_lswz --source prov_hebei_tyjr \
  --source prov_hebei_yjgl --source prov_hebei_ylbzj --source prov_hebei_wenwu \
  --source prov_hebei_rta --source prov_hebei_hebwb --source prov_hebei_lycy \
  --source prov_hebei_mw --source prov_hebei_nyj --source prov_hebei_gzw \
  --source prov_hebei_yjj --source prov_hebei_yjs --source prov_hebei_szj \
  --source city_qhd_gov --source city_qhd_fgw --source city_qhd_czj \
  --source city_qhd_kjj --source city_qhd_gxj --source city_qhd_scjg \
  --source city_qhd_zjj --source city_qhd_jtj --source city_qhd_sthjj \
  --source city_qhd_nyncj --source city_qhd_rsj --source city_qhd_wjw \
  --source city_qhd_lywgj --source city_qhd_swj --source city_qhd_swj_water \
  --source city_qhd_zyghj \
  --max-new 10

# Export MD files
echo ""
echo "=== Exporting MD files ==="
PYTHONPATH=. python python/scripts/export_policies_md.py \
  --region hebei --days 730 --output data/exports/policies

# Sync to server
echo ""
echo "=== Syncing to server ==="
scp -i "$SSH_KEY" data/policy_radar.db "$SERVER:/opt/policy-radar/data/policy_radar.db"
scp -i "$SSH_KEY" -r data/exports/policies/ "$SERVER:/opt/policy-radar/data/exports/"

# Restart container
ssh -i "$SSH_KEY" "$SERVER" "docker restart policy-radar-app"

echo ""
echo "=== $(date) Daily crawl complete ==="
