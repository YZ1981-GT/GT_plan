"""ACNR Catalog Drift Check — CI 守卫。

验证已提交的 global_catalog.json 与生成器重新生成的输出字节一致（无漂移）。

逻辑：
1. 读取 global_catalog.json → 提取 registry_version
2. 运行 generate_catalog(offline=True, registry_version=existing_version)
3. 用 _deterministic_json 序列化并比较
4. 不一致 → 打印 diff 摘要, exit(1)
5. 一致 → print OK, exit(0)

Requirements: 18.3
"""

from __future__ import annotations

import json
import sys
from difflib import unified_diff
from pathlib import Path

# ---------------------------------------------------------------------------
# 路径设置
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_BACKEND_ROOT = _REPO_ROOT / "backend"
_ACNR_DATA_DIR = _BACKEND_ROOT / "data" / "acnr"
_CATALOG_PATH = _ACNR_DATA_DIR / "global_catalog.json"

# 确保 backend 在 sys.path 以便 import
sys.path.insert(0, str(_BACKEND_ROOT))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """执行 drift 检查。"""
    # --- Step 1: 读取已提交的 catalog 文件 ---
    if not _CATALOG_PATH.exists():
        print(
            f"[ACNR drift] ERROR: {_CATALOG_PATH} 不存在。"
            f"请先运行 generate_catalog.py 生成 catalog。",
            file=sys.stderr,
        )
        return 1

    committed_text = _CATALOG_PATH.read_text(encoding="utf-8")

    try:
        committed_data = json.loads(committed_text)
    except json.JSONDecodeError as e:
        print(
            f"[ACNR drift] ERROR: global_catalog.json 解析失败: {e}",
            file=sys.stderr,
        )
        return 1

    # 提取 registry_version
    registry_version = committed_data.get("registry_version")
    if not registry_version:
        print(
            "[ACNR drift] ERROR: global_catalog.json 缺少 registry_version 字段。",
            file=sys.stderr,
        )
        return 1

    # --- Step 2: 重新生成 catalog（使用相同 registry_version） ---
    from scripts.acnr.generate_catalog import (  # noqa: E402
        _deterministic_json,
        generate_catalog,
    )

    try:
        catalog_data, _report_data, _manifest_blocked = generate_catalog(
            offline=True,
            registry_version=registry_version,
        )
    except FileNotFoundError as e:
        print(f"[ACNR drift] ERROR: 生成 catalog 失败: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[ACNR drift] ERROR: 生成 catalog 异常: {e}", file=sys.stderr)
        return 1

    # --- Step 3: 确定性序列化并比较 ---
    generated_text = _deterministic_json(catalog_data)

    if committed_text == generated_text:
        print("[ACNR drift] OK — global_catalog.json 与生成器输出一致，无漂移。")
        return 0

    # --- Step 4: 输出 diff 摘要 ---
    print(
        "[ACNR drift] FAIL — global_catalog.json 与生成器输出不一致！",
        file=sys.stderr,
    )
    print("", file=sys.stderr)
    print("请运行以下命令更新 catalog：", file=sys.stderr)
    print(
        f"  python backend/scripts/acnr/generate_catalog.py "
        f"--offline --registry-version {registry_version}",
        file=sys.stderr,
    )
    print("", file=sys.stderr)

    # 生成 unified diff（限制输出行数避免 CI 日志过长）
    committed_lines = committed_text.splitlines(keepends=True)
    generated_lines = generated_text.splitlines(keepends=True)

    diff_lines = list(
        unified_diff(
            committed_lines,
            generated_lines,
            fromfile="committed/global_catalog.json",
            tofile="generated/global_catalog.json",
            lineterm="",
        )
    )

    MAX_DIFF_LINES = 80
    if diff_lines:
        print(f"Diff（前 {MAX_DIFF_LINES} 行）:", file=sys.stderr)
        for line in diff_lines[:MAX_DIFF_LINES]:
            print(line, file=sys.stderr)
        if len(diff_lines) > MAX_DIFF_LINES:
            print(
                f"  ... ({len(diff_lines) - MAX_DIFF_LINES} more lines omitted)",
                file=sys.stderr,
            )
    else:
        # 文本不同但 diff 为空（不应该发生，防御性处理）
        print(
            "  (无可显示 diff — 可能存在尾部空白/换行符差异)",
            file=sys.stderr,
        )

    return 1


if __name__ == "__main__":
    sys.exit(main())
