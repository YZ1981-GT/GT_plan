"""ACNR Sheet Labels Generated Check — CI 守卫。

验证已提交的 dSheetLabels.ts 与生成器重新生成的输出一致（禁止手改）。

逻辑：
1. 读取已提交的 dSheetLabels.ts
2. 重新运行生成器逻辑（不写文件）
3. 比较两者内容
4. 不一致 → exit(1)（检测到手动编辑）
5. 一致 → print OK, exit(0)

Requirements: 3.2, 18.1
"""

from __future__ import annotations

import sys
from difflib import unified_diff
from pathlib import Path

# ---------------------------------------------------------------------------
# 路径设置
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_BACKEND_ROOT = _REPO_ROOT / "backend"

# 确保 backend 在 sys.path 以便 import
sys.path.insert(0, str(_BACKEND_ROOT))

_COMMITTED_PATH = (
    _REPO_ROOT
    / "audit-platform"
    / "frontend"
    / "src"
    / "generated"
    / "dSheetLabels.ts"
)
_CATALOG_PATH = _BACKEND_ROOT / "data" / "acnr" / "global_catalog.json"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """执行 sheet labels 生成一致性检查。"""
    # --- Step 1: 读取已提交的文件 ---
    if not _COMMITTED_PATH.exists():
        print(
            f"[check-sheet-labels-generated] ERROR: {_COMMITTED_PATH} 不存在。\n"
            f"请先运行 python backend/scripts/acnr/generate_sheet_labels.py 生成文件。",
            file=sys.stderr,
        )
        return 1

    committed_text = _COMMITTED_PATH.read_text(encoding="utf-8")

    # --- Step 2: 重新生成（不写文件） ---
    from scripts.acnr.generate_sheet_labels import (  # noqa: E402
        generate_ts_content,
        load_d_cycle_sheets,
    )

    if not _CATALOG_PATH.exists():
        print(
            f"[check-sheet-labels-generated] ERROR: {_CATALOG_PATH} 不存在。",
            file=sys.stderr,
        )
        return 1

    sheets = load_d_cycle_sheets(_CATALOG_PATH)
    if not sheets:
        print(
            "[check-sheet-labels-generated] ERROR: catalog 中无 D-cycle sheet 条目。",
            file=sys.stderr,
        )
        return 1

    generated_text = generate_ts_content(sheets)

    # --- Step 3: 比较 ---
    if committed_text == generated_text:
        print(
            "[check-sheet-labels-generated] OK — dSheetLabels.ts 与生成器输出一致，无手动编辑。"
        )
        return 0

    # --- Step 4: 输出 diff 摘要 ---
    print(
        "[check-sheet-labels-generated] FAIL — dSheetLabels.ts 存在手动编辑！",
        file=sys.stderr,
    )
    print("", file=sys.stderr)
    print(
        "此文件由生成器自动产出，禁止手动修改。请运行以下命令重新生成：",
        file=sys.stderr,
    )
    print(
        "  python backend/scripts/acnr/generate_sheet_labels.py",
        file=sys.stderr,
    )
    print("", file=sys.stderr)

    # 生成 unified diff
    committed_lines = committed_text.splitlines(keepends=True)
    generated_lines = generated_text.splitlines(keepends=True)

    diff_lines = list(
        unified_diff(
            committed_lines,
            generated_lines,
            fromfile="committed/dSheetLabels.ts",
            tofile="generated/dSheetLabels.ts",
            lineterm="",
        )
    )

    MAX_DIFF_LINES = 40
    if diff_lines:
        print(f"Diff（前 {MAX_DIFF_LINES} 行）:", file=sys.stderr)
        for line in diff_lines[:MAX_DIFF_LINES]:
            print(line, file=sys.stderr)
        if len(diff_lines) > MAX_DIFF_LINES:
            print(
                f"  ... ({len(diff_lines) - MAX_DIFF_LINES} more lines omitted)",
                file=sys.stderr,
            )

    return 1


if __name__ == "__main__":
    sys.exit(main())
