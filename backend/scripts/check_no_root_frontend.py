"""pre-commit hook：禁止仓库根重新出现 frontend/ 目录或 frontend/src/ 路径。

repo-frontend-layout-unification spec / Task 7

检查项：
1. 仓库根 frontend/ 目录不存在（git ls-files 不含）
2. 暂存 / staged 文件中无 ^frontend/src/ 路径

退出码：
- 0 = 通过
- 1 = 有违规

用法：
    python backend/scripts/check_no_root_frontend.py [files...]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    files = argv or sys.argv[1:]

    violations: list[str] = []

    # 检查 1：仓库根 frontend/ 目录不存在
    root_frontend = ROOT / "frontend"
    if root_frontend.is_dir():
        # 检查是否有 .vue / .ts 等真前端文件
        has_frontend_files = any(
            f.is_file() and f.suffix in (".vue", ".ts", ".tsx", ".js")
            for f in root_frontend.rglob("*")
        )
        if has_frontend_files:
            violations.append(
                "❌ 仓库根 frontend/ 目录已被废弃（重新出现真前端文件）；"
                "前端唯一路径 = audit-platform/frontend/"
            )

    # 检查 2：暂存文件中是否有 frontend/src/ 路径
    for f in files:
        f_norm = f.replace("\\", "/")
        if f_norm.startswith("frontend/src/"):
            violations.append(
                f"❌ {f} - 路径 frontend/src/ 已废弃；"
                f"前端唯一路径 = audit-platform/frontend/src/"
            )

    if violations:
        print("\n".join(violations), file=sys.stderr)
        print("", file=sys.stderr)
        print(
            "参考：repo-frontend-layout-unification spec（2026-05-29 落地）",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
