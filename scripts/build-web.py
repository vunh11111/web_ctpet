"""Build the browser app against the configured public backend port."""
import os
from pathlib import Path
import subprocess
from dotenv import dotenv_values
root=Path(__file__).resolve().parents[1]
config=dotenv_values(root/'.env')
env=os.environ.copy()
env['VITE_API_PORT']=config.get('API_PORT','8108')
env['VITE_AUTH_MODE']=config.get('AUTH_MODE','password')
if config.get('VITE_API_URL'):env['VITE_API_URL']=config['VITE_API_URL']
subprocess.run(['npm','run','build'],cwd=root/'frontend',env=env,check=True)
