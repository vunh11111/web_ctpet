"""Stage frontend files only; exclude all datasets, model files and server secrets."""
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'frontend'
target=ROOT/'deploy/vercel-frontend'
target.mkdir(parents=True,exist_ok=True)
for name in ['index.html','package.json','package-lock.json','tsconfig.json','vite.config.ts','vercel.json']:
    shutil.copy2(source/name,target/name)
shutil.copytree(source/'src',target/'src',dirs_exist_ok=True)
if (source/'public').exists():shutil.copytree(source/'public',target/'public',dirs_exist_ok=True)
(target/'.vercelignore').write_text('.env*\nnode_modules\ndist\n*.log\n')
print('Staged frontend only:',target)
