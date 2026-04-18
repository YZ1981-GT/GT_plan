"""批量给缺认证的路由文件加上 get_current_user 依赖

对 /api/projects/{project_id}/ 前缀的路由用 require_project_access
对其他路由用 get_current_user
"""
import re
from pathlib import Path

ROUTER_DIR = Path(__file__).parent.parent / "app" / "routers"

# 需要修复的文件及其权限级别
FILES_TO_FIX = {
    # project-scoped routes → require_project_access
    "drilldown.py": "readonly",
    "cfs_worksheet.py": "mixed",  # GET=readonly, POST/PUT/DELETE=edit
    "disclosure_notes.py": "mixed",
    "materiality.py": "partial",  # 部分已有
    # non-project-scoped routes → get_current_user
    "report_config.py": "user",
    "audit_report.py": "user",
    "export.py": "user",
}


def fix_file(filename: str, mode: str):
    filepath = ROUTER_DIR / filename
    if not filepath.exists():
        print(f"  SKIP {filename} (not found)")
        return

    content = filepath.read_text(encoding="utf-8")

    # Check if already has auth imports
    has_get_current_user = "get_current_user" in content
    has_require_project = "require_project_access" in content
    has_user_import = "from app.models.core import User" in content

    # Add imports if needed
    if mode in ("readonly", "mixed"):
        if not has_require_project:
            content = content.replace(
                "from app.core.database import get_db",
                "from app.core.database import get_db\nfrom app.deps import get_current_user, require_project_access\nfrom app.models.core import User",
            )
        elif not has_user_import:
            content = content.replace(
                "from app.core.database import get_db",
                "from app.core.database import get_db\nfrom app.models.core import User",
            )
    elif mode == "user":
        if not has_get_current_user:
            content = content.replace(
                "from app.core.database import get_db",
                "from app.core.database import get_db\nfrom app.deps import get_current_user\nfrom app.models.core import User",
            )
        elif not has_user_import:
            content = content.replace(
                "from app.core.database import get_db",
                "from app.core.database import get_db\nfrom app.models.core import User",
            )

    # Find all endpoint functions and add auth if missing
    # Pattern: db: AsyncSession = Depends(get_db),\n) or db: AsyncSession = Depends(get_db)\n)
    # We need to add current_user parameter after db parameter

    lines = content.split("\n")
    new_lines = []
    i = 0
    fixed_count = 0

    while i < len(lines):
        line = lines[i]
        new_lines.append(line)

        # Check if this line has db = Depends(get_db) and the next line closes the function signature
        if "Depends(get_db)" in line and "current_user" not in line and "user=" not in line and "user =" not in line:
            # Check if next line is ) or ): or ) -> or has no more params
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line.startswith(")") or next_line.startswith("->"):
                    # This endpoint is missing auth - add it
                    indent = len(line) - len(line.lstrip())
                    indent_str = " " * indent

                    # Determine which auth to use
                    if mode == "user":
                        auth_line = f"{indent_str}current_user: User = Depends(get_current_user),"
                    elif mode == "readonly":
                        auth_line = f'{indent_str}current_user: User = Depends(require_project_access("readonly")),'
                    elif mode == "mixed":
                        # Look back to find the HTTP method
                        method = "get"
                        for j in range(max(0, i - 10), i):
                            if "@router.get" in lines[j]:
                                method = "get"
                                break
                            elif "@router.post" in lines[j]:
                                method = "post"
                                break
                            elif "@router.put" in lines[j]:
                                method = "put"
                                break
                            elif "@router.delete" in lines[j]:
                                method = "delete"
                                break

                        if method == "get":
                            auth_line = f'{indent_str}current_user: User = Depends(require_project_access("readonly")),'
                        else:
                            auth_line = f'{indent_str}current_user: User = Depends(require_project_access("edit")),'
                    else:
                        auth_line = f"{indent_str}current_user: User = Depends(get_current_user),"

                    # Make sure the db line ends with comma
                    if not new_lines[-1].rstrip().endswith(","):
                        new_lines[-1] = new_lines[-1].rstrip() + ","

                    new_lines.append(auth_line)
                    fixed_count += 1

        i += 1

    if fixed_count > 0:
        filepath.write_text("\n".join(new_lines), encoding="utf-8")
        print(f"  FIXED {filename}: {fixed_count} endpoints")
    else:
        print(f"  OK {filename}: no changes needed")


if __name__ == "__main__":
    print("=== 批量修复路由认证 ===\n")
    for fname, mode in FILES_TO_FIX.items():
        print(f"Processing {fname} (mode={mode})...")
        fix_file(fname, mode)
    print("\nDone!")
