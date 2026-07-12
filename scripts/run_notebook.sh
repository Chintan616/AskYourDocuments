#!/usr/bin/env bash
set -euo pipefail

python3 -m venv .venv
source .venv/bin/activate

install_requirements() {
  local mode="$1"
  case "$mode" in
    proxy)
      python -m pip install --upgrade pip
      python -m pip install -r requirements.txt
      ;;
    direct)
      env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
        python -m pip install --upgrade pip
      env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
        python -m pip install -r requirements.txt
      ;;
    custom-index)
      if [[ -z "${PIP_INDEX_URL:-}" ]]; then
        return 1
      fi
      python -m pip install --upgrade pip
      python -m pip install -r requirements.txt --index-url "$PIP_INDEX_URL" ${PIP_EXTRA_INDEX_URL:+--extra-index-url "$PIP_EXTRA_INDEX_URL"}
      ;;
    *)
      return 1
      ;;
  esac
}

echo "[setup] Installing dependencies..."
if install_requirements proxy; then
  echo "[setup] Dependency install succeeded (proxy mode)."
elif install_requirements direct; then
  echo "[setup] Dependency install succeeded (direct mode)."
elif install_requirements custom-index; then
  echo "[setup] Dependency install succeeded (custom index mode)."
else
  echo "[error] Could not install Python dependencies."
  echo "[hint] Proxy/index is blocking package resolution."
  echo "[hint] Set one of the following and rerun:"
  echo "       export PIP_INDEX_URL=<reachable_simple_index>"
  echo "       export PIP_EXTRA_INDEX_URL=<optional_secondary_index>"
  echo "[hint] Or run this notebook in Google Colab where base deps/network are typically available."
  exit 2
fi

export AUTO_START_FLASK=${AUTO_START_FLASK:-0}
python - <<'PY'
import os
from nbclient import NotebookClient
import nbformat

path = "AskYourDocuments.ipynb"
nb = nbformat.read(path, as_version=4)
client = NotebookClient(nb, timeout=1800, kernel_name="python3")
client.execute()
out_path = "AskYourDocuments.executed.ipynb"
nbformat.write(nb, out_path)
print(f"Notebook executed successfully: {out_path}")
print(f"AUTO_START_FLASK={os.getenv('AUTO_START_FLASK')}")
PY
