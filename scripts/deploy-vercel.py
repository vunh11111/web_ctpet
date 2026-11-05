"""Deploy connected frontend only to the already recorded Vercel project."""
import json
from pathlib import Path
import subprocess
import sys
import httpx
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]
plan_path=ROOT/'artifacts/vercel-deployment.json'
plan=json.loads(plan_path.read_text())
public=json.loads((ROOT/'artifacts/public-preview.json').read_text())
config=dotenv_values(ROOT/'.env')
if config.get('AUTH_ENABLED','').lower()!='true':
    raise SystemExit('Authentication must be enabled before deploying a connected public frontend.')
with httpx.Client(timeout=30,trust_env=False) as client:
    response=client.get(public['backend_url']+'/models')
    if response.status_code!=401:
        raise SystemExit('Public API must be reachable and reject anonymous data requests.')
subprocess.run([sys.executable,str(ROOT/'scripts/stage-vercel.py')],check=True)
stage=ROOT/'deploy/vercel-frontend'
for path in stage.rglob('*'):
    if path.is_file() and (path.name.startswith('.env') or path.suffix in ['.pt','.npy','.nii','.dcm']):
        raise SystemExit('Staging contains a non-frontend or private file.')
args=['npx','--yes','vercel','deploy','--project',plan['project_name'],'--create-if-missing','--prod','--yes',
      '--build-env','VITE_API_URL='+public['backend_url'],'--build-env','VITE_PUBLIC_PREVIEW=false',
      '--build-env','VITE_AUTH_MODE='+config.get('AUTH_MODE','password'),
      '--env','VITE_API_URL='+public['backend_url'],'--env','VITE_PUBLIC_PREVIEW=false','--json']
result_path=ROOT/'artifacts/vercel-deploy-result.json'
with result_path.open('w') as out,(ROOT/'logs/vercel-deploy.log').open('w') as log:
    subprocess.run(args,cwd=stage,stdout=out,stderr=log,check=True)
result=json.loads(result_path.read_text())['deployment']
plan.update(frontend_url=result['productionUrl'],backend_url=public['backend_url'],deployment_id=result['id'],status=result['readyState'],mode='connected')
plan_path.write_text(json.dumps(plan,indent=2))
print('Connected frontend deployed:',plan['frontend_url'])
