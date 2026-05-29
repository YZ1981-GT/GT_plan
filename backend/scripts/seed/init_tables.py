"""一次性建表脚本 — 自动扫描所有模型文件，无需手动维护导入列表"""
import sys, os, importlib, pathlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import create_engine, text
from app.models.base import Base

# 自动扫描 app/models/ 下所有 Python 模块并导入（触发 ORM 注册到 Base.metadata）
models_dir = pathlib.Path(__file__).parent.parent / "app" / "models"
loaded, skipped = [], []
for f in sorted(models_dir.glob("*.py")):
    mod_name = f.stem
    if mod_name.startswith("_"):
        continue
    full_name = f"app.models.{mod_name}"
    try:
        importlib.import_module(full_name)
        loaded.append(mod_name)
    except Exception as e:
        skipped.append((mod_name, str(e)))
        print(f"skip {mod_name}: {e}")

print(f"\nLoaded {len(loaded)} model modules, skipped {len(skipped)}")

# 从 .env 读取数据库连接，自动转为同步驱动
from dotenv import load_dotenv
load_dotenv(models_dir.parent.parent / ".env")
DB_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/audit_platform")
# asyncpg → psycopg2（同步建表需要同步驱动）
DB_URL = DB_URL.replace("+asyncpg", "+psycopg2")
engine = create_engine(DB_URL)
Base.metadata.create_all(engine)
tables = sorted(Base.metadata.tables.keys())
print(f"\nCreated {len(tables)} tables:")
for t in tables:
    print(f"  {t}")

# ── 自动加载种子数据 ──
# 通用规则：建表后调用后端所有 /seed 端点（它们本身是幂等的）
# 这样种子数据的加载逻辑只维护在各服务层一处，脚本不重复硬编码
import json, urllib.request, urllib.error

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:9980")

def _call_seed(path: str, token: str | None = None):
    """调用一个 seed 端点，返回 (成功, 消息)"""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{API_BASE}{path}", data=b"{}", headers=headers, method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=30)
        body = json.loads(r.read().decode())
        msg = body.get("data", {}).get("message", "") if isinstance(body.get("data"), dict) else str(body.get("data", ""))
        return True, msg or "ok"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except Exception as e:
        return False, str(e)

# 先尝试登录拿 token（后端运行中才能加载种子数据）
token = None
try:
    login_req = urllib.request.Request(
        f"{API_BASE}/api/auth/login",
        data=json.dumps({"username": "admin", "password": "admin123"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    login_resp = urllib.request.urlopen(login_req, timeout=5)
    login_data = json.loads(login_resp.read().decode())
    token = (login_data.get("data") or login_data).get("access_token") or (login_data.get("data") or login_data).get("token")
except Exception:
    print("\n⚠ 后端未运行，跳过种子数据加载（建表已完成，启动后端后可手动调用 seed 端点）")
    engine.dispose()
    sys.exit(0)

# 所有已知的 seed 端点（幂等，可重复调用）
SEED_ENDPOINTS = [
    "/api/report-config/seed",
    "/api/gt-coding/seed",
    "/api/ai-models/seed",
    "/api/ai-plugins/seed",
    "/api/accounting-standards/seed",
    "/api/template-sets/seed",
]

print("\n── 加载种子数据 ──")
for ep in SEED_ENDPOINTS:
    ok, msg = _call_seed(ep, token)
    status = "✓" if ok else "✗"
    print(f"  {status} {ep}: {msg}")

engine.dispose()
