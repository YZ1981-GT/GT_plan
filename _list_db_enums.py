"""列出所有 create_type=False 的 PG 枚举（需 DB 侧预先创建），
并与 dev1.0 库现有枚举对比，生成缺失清单。
"""
import re
from pathlib import Path

ROOT = Path(r"D:\zaqcwrok\GT_plan_sw\backend\app")

pat = re.compile(
    r"sa\.Enum\(\s*(\w+)\s*,\s*name=[\"'](\w+)[\"'][^)]*create_type\s*=\s*False",
    re.S,
)
pat2 = re.compile(
    r"Enum\(\s*(\w+)\s*,\s*name=[\"'](\w+)[\"'][^)]*create_type\s*=\s*False",
    re.S,
)

found = {}
for f in ROOT.rglob("*.py"):
    try:
        t = f.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    for m in list(pat.finditer(t)) + list(pat2.finditer(t)):
        py_enum, pg_name = m.group(1), m.group(2)
        found.setdefault(pg_name, set()).add(f"{py_enum} @ {f.relative_to(ROOT)}")

print("create_type=False 的 PG 枚举共", len(found), "个:")
for name in sorted(found):
    print(" ", name)
    for src in sorted(found[name]):
        print("      ", src)
