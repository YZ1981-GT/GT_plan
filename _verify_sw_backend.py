"""验证 sw worktree 的后端依赖是否可用（直接 import，不看日志）。"""
import importlib
import sys

CORE = [
    "fastapi", "uvicorn", "sqlalchemy", "asyncpg", "pydantic",
    "pydantic_settings", "redis", "jose", "passlib", "openpyxl",
    "docx", "alembic", "httpx", "pytest",
]

print("python:", sys.version.split()[0])
print("exe:", sys.executable)
print()

missing = []
for name in CORE:
    try:
        m = importlib.import_module(name)
        v = getattr(m, "__version__", "")
        print(f"  OK   {name:20} {v}")
    except Exception as e:
        missing.append(name)
        print(f"  MISS {name:20} {type(e).__name__}: {e}")

print()
print("missing count:", len(missing))
print("RESULT:", "后端依赖可用" if not missing else f"缺失: {missing}")
