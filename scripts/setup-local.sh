#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"
MODEL_PYTHON="${MODEL_PYTHON:-/mnt/disk1/aiotlab/quanghv/.venvs/roi-totalsegmentator/bin/python}"
if [[ ! -x "$MODEL_PYTHON" ]]; then echo 'Set MODEL_PYTHON to a Python environment with PyTorch, nibabel, SimpleITK, scipy, pydicom and Pillow.' >&2; exit 1; fi
uv venv --python "$MODEL_PYTHON" .venv --allow-existing
uv pip install --python .venv/bin/python -r backend/requirements.lock.txt pytest
MODEL_SITE=$("$MODEL_PYTHON" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
.venv/bin/python - "$MODEL_SITE" <<'PY'
from pathlib import Path
import sys,sysconfig,secrets,socket
Path(sysconfig.get_paths()['purelib'],'workspace_model_environment.pth').write_text(sys.argv[1]+'\n')
path=Path('.env')
if not path.exists():
    value=Path('.env.example').read_text().replace('CHANGE_ME',secrets.token_urlsafe(28))
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.connect(('192.168.1.1',9)); address=sock.getsockname()[0]
        if not address.startswith('127.'):
            value=value.replace('CORS_ORIGINS=http://localhost:3108,http://127.0.0.1:3108','CORS_ORIGINS=http://localhost:3108,http://127.0.0.1:3108,http://'+address+':3108')
    except OSError: pass
    path.write_text(value);path.chmod(0o600)
PY
.venv/bin/python -c 'import torch, nibabel, SimpleITK, scipy, pydicom, PIL'
.venv/bin/python scripts/setup-auth.py
npm --prefix frontend ci
.venv/bin/python scripts/build-web.py
echo 'Prepared. Review .env, then run: bash scripts/run-local.sh'
