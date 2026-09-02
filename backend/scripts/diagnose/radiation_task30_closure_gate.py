# -*- coding: utf-8 -*-
"""Task 30 改动的辐射面（AST 引用实扫，不用裸词搜）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 2 Task 30

═══ 为什么不能用裸词搜 ═══

本 spec 的 docstring 里大量**逐字引用**类名与文件名（例如注释里写
「`workpaper_writer_inventory.json`」只是在解释判据），裸词搜会把这些说明文字算成引用，
辐射面被撑大到没法跑。所以这里分两条通道：

* **代码符号**：`ast` 走 `Import` / `ImportFrom` / `Call` / `Attribute`，只收真引用；
* **数据/脚本产物**（JSON、生成器、门脚本、tasks.md）：这些是被**字符串路径**引用的，
  没有 import 可查，所以按**字符串常量**（`ast.Constant` 里的 str，**不含** docstring）
  匹配 —— docstring 与注释在 AST 里可区分，因此说明文字不会被算进来。

用法（仓库根）::

    py -3 backend/scripts/diagnose/radiation_task30_closure_gate.py --json radiation.json
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[3]
_TEST_ROOT = _REPO / "backend" / "tests"

#: 本任务改动的产物 → 归属说明。**唯一真源**：辐射面按它推导。
CHANGED: dict[str, str] = {
    "backend/tests/workpaper_sync/test_task21_room_service.py": "修好契约数值单一真源判据",
    "backend/tests/workpaper_sync/test_task22_callback_claim.py": "修好 token 解码单一实现判据",
    "backend/tests/workpaper_sync/test_task30_closure_gate.py": "新增：关门离线判据",
    "backend/tests/workpaper_sync/test_task30_closure_gate_pg.py": "新增：关门集成判据",
    "backend/scripts/gen/generate_workpaper_resolver_migration_matrix.py": "POLICY 补记阻塞",
    "backend/data/workpaper_resolver_migration_matrix.json": "重新生成（含新阻塞登记）",
    "backend/data/workpaper_writer_inventory.json": "重新生成（Task 28 之后行号漂移）",
    ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/tasks.md": (
        "修正 Task 20 「不再评估」措辞"
    ),
}

#: 被字符串路径引用的产物（无 import 可查）。
_PATH_TOKENS = (
    "workpaper_resolver_migration_matrix",
    "workpaper_writer_inventory",
    "generate_workpaper_resolver_migration_matrix",
    "generate_workpaper_writer_inventory",
    "check_workpaper_writer_revision_gate",
    "tasks.md",
)

#: 被 import 的模块名（本任务改动的生产模块为空 —— 本轮**没有**改生产代码，
#: 但变异检验注入过的生产模块仍要进辐射面，因为判据是「它们被谁消费」）。
_MODULE_TOKENS = (
    "app.services.workpaper_sync.models",
    "app.services.workpaper_sync.repository",
    "app.services.workpaper_sync.callback_delivery",
    "app.services.workpaper_sync.close_intent",
    "app.services.workpaper_sync.rooms",
    "app.services.workpaper_sync.oo_contract",
)


def _string_constants(tree: ast.AST) -> set[str]:
    """模块里的字符串常量，**剔除 docstring**（说明文字不算引用）。"""
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body:
            first = body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstrings.add(id(first.value))
    out: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
        ):
            out.add(node.value)
    return out


def _imported_modules(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out.update(f"{node.module}.{alias.name}" for alias in node.names)
    return out


def scan() -> dict[str, Any]:
    hits: dict[str, list[str]] = {}
    scanned = 0
    unparsable: list[str] = []
    for path in sorted(_TEST_ROOT.rglob("test_*.py")):
        rel = path.relative_to(_REPO).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        except SyntaxError as exc:
            unparsable.append(f"{rel}: {exc}")
            continue
        scanned += 1
        reasons: list[str] = []
        strings = _string_constants(tree)
        modules = _imported_modules(tree)
        for token in _PATH_TOKENS:
            if any(token in s for s in strings):
                reasons.append(f"path:{token}")
        for token in _MODULE_TOKENS:
            if any(m == token or m.startswith(token + ".") for m in modules):
                reasons.append(f"import:{token}")
        if rel in CHANGED:
            reasons.append("changed-itself")
        if reasons:
            hits[rel] = sorted(set(reasons))
    if scanned < 100:
        raise SystemExit(f"只扫到 {scanned} 个测试文件 —— 辐射面分母塌了")
    return {
        "changed": CHANGED,
        "scanned_test_files": scanned,
        "unparsable": unparsable,
        "radiated": hits,
        "radiated_count": len(hits),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", metavar="PATH", help="落盘 JSON")
    args = ap.parse_args()
    try:
        for stream in (sys.stdout, sys.stderr):
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    report = scan()
    print(f"扫描测试文件 {report['scanned_test_files']} 个，辐射 {report['radiated_count']} 个")
    for rel, reasons in report["radiated"].items():
        print(f"  {rel}\n      {', '.join(reasons)}")
    if report["unparsable"]:
        print(f"\n无法 parse（不计入分母）：{len(report['unparsable'])} 个")
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n报告已写入 {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
