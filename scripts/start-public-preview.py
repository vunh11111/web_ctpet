"""Temporary authenticated HTTPS preview; no DNS or Cloudflare account needed."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import time
from urllib.parse import urlparse
import httpx
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]
config=dotenv_values(ROOT/'.env')
api_port=config.get('API_PORT','8108');web_port=config.get('WEB_PORT','3108')
if config.get('AUTH_ENABLED','').lower()!='true' or not config.get('AUTH_PASSWORD_HASH'):
    raise SystemExit('Configure authentication before exposing this demo.')
with httpx.Client(timeout=10,trust_env=False) as client:
    response=client.get(f'http://127.0.0.1:{api_port}/api/models')
    if response.status_code!=401:
        raise SystemExit('API must reject anonymous requests before opening a public tunnel.')
session='dienbien_pet_demo_tunnel'
log=ROOT/'logs/public-tunnel.log'
if subprocess.run(['tmux','has-session','-t',session],capture_output=True).returncode:
    log.write_text('')
    command=f"exec {shlex.quote(str(Path.home()/'bin/cloudflared'))} tunnel --no-autoupdate --protocol http2 --url http://127.0.0.1:{web_port} > {shlex.quote(str(log))} 2>&1"
    subprocess.run(['tmux','new-session','-d','-s',session,command],check=True)
url=None
for _ in range(40):
    matches=re.findall(r'https://[a-z0-9-]+\.trycloudflare\.com',log.read_text())
    if matches:
        url=matches[-1];break
    time.sleep(1)
if not url:
    raise SystemExit('Tunnel URL not available yet; inspect logs/public-tunnel.log.')
host=urlparse(url).hostname
env=ROOT/'.env'
lines=[line for line in env.read_text().splitlines() if not line.startswith('PUBLIC_WEB_HOST=')]
env.write_text('\n'.join(lines)+f'\nPUBLIC_WEB_HOST={host}\n')
subprocess.run(['tmux','kill-session','-t','dienbien_pet_demo_frontend'],capture_output=True)
command=f'cd {shlex.quote(str(ROOT))} && bash scripts/service-local.sh frontend >> logs/frontend.log 2>&1'
subprocess.run(['tmux','new-session','-d','-s','dienbien_pet_demo_frontend',command],check=True)
result={'frontend_url':url,'backend_url':url+'/api','temporary':True,'authentication_required':True,'note':'Quick Tunnel URL changes if the tunnel process is recreated; no uptime guarantee.'}
(ROOT/'artifacts/public-preview.json').write_text(json.dumps(result,indent=2))
print('Temporary HTTPS frontend:',url,flush=True)
print('API:',url+'/api',flush=True)
