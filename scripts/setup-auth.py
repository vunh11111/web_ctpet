"""Create the initial demo login without printing credentials or secrets."""
import argparse
from pathlib import Path
import secrets
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.auth import password_hash
from dotenv import dotenv_values

parser = argparse.ArgumentParser()
parser.add_argument("--rotate", action="store_true")
args = parser.parse_args()
path = ROOT / ".env"
existing = dotenv_values(path)
if existing.get("AUTH_PASSWORD_HASH") and not args.rotate:
    print("Authentication already configured; credentials retained.")
    sys.exit(0)
password = secrets.token_urlsafe(18)
values = {"AUTH_ENABLED": "true", "AUTH_USERNAME": "demo", "AUTH_PASSWORD_HASH": password_hash(password), "AUTH_SIGNING_SECRET": secrets.token_urlsafe(48)}
lines = [line for line in path.read_text().splitlines() if line.split("=", 1)[0] not in values]
path.write_text("\n".join(lines) + "\n" + "\n".join(f"{k}='{v}'" for k, v in values.items()) + "\n")
path.chmod(0o600)
target = ROOT / "data" / "demo-login.txt"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(f"Username: demo\nPassword: {password}\n")
target.chmod(0o600)
print("Authentication configured. Initial login saved privately to data/demo-login.txt.")
