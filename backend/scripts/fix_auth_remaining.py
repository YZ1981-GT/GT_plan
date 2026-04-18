"""修复剩余缺认证的路由文件"""
import re
from pathlib import Path

ROUTER_DIR = Path(__file__).parent.parent / "app" / "routers"

# 需要修复的文件
FILES = [
    "ledger_penetration.py",
    "formula.py",
    "continuous_audit.py",
    "private_storage.py",
    "task_center.py",
    "ai_plugins.py",
    "ai_models.py",
    "note_templates.py",
    "signatures.py",
    "t_accounts.py",
    "gt_coding.py",
    "custom_templates.py",
    "regulatory.py",
    "audit_types.py",
    "i18n.py",
    "ai_unified.py",
    "metabase.py",
    "accounting_standards.py",
]

def fix_file(filename: str):
    filepath = ROUTER_DIR / filename
    if not filepath.exists():
        print(f"  SKIP {filename}")
        return

    content = filepath.read_text(encoding="utf-8")
    if "get_current_user" in content or "require_project_access" in content:
        print(f"  OK {filename} (already has auth)")
        return

    # Add imports
    if "from app.core.database import get_db" in content:
        content = content.replace(
            "from app.core.database import get_db",
            "from app.core.database import get_db\nfrom app.deps import get_current_user\nfrom app.models.core import User",
        )
    elif "from app.core.database" not in content:
        # Find first import line and add after
        lines = content.split("\n")
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("from ") or line.startswith("import "):
                insert_idx = i + 1
        lines.insert(insert_idx, "from app.deps import get_current_user")
        lines.insert(insert_idx + 1, "from app.models.core import User")
        content = "\n".join(lines)

    # Add auth to endpoints missing it
    lines = content.split("\n")
    new_lines = []
    fixed = 0
    for i, line in enumerate(lines):
        new_lines.append(line)
        if "Depends(get_db)" in line and "current_user" not in line and "user=" not in line:
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line.startswith(")") or next_line.startswith("->"):
                    indent = len(line) - len(line.lstrip())
                    if not new_lines[-1].rstrip().endswith(","):
                        new_lines[-1] = new_lines[-1].rstrip() + ","
                    new_lines.append(" " * indent + "current_user: User = Depends(get_current_user),")
                    fixed += 1

    if fixed > 0:
        filepath.write_text("\n".join(new_lines), encoding="utf-8")
        print(f"  FIXED {filename}: {fixed} endpoints")
    else:
        print(f"  NO CHANGE {filename}")

if __name__ == "__main__":
    print("=== 修复剩余路由认证 ===\n")
    for f in FILES:
        fix_file(f)
    print("\nDone!")
