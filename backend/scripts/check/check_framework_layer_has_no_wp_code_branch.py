# -*- coding: utf-8 -*-
r"""框架层零 wp_code / adapter_id / contract_id 分支门禁（P9 / D1-P9）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 2（红判据先行）/ Task 20（转绿）
Requirements 7.1 / 7.4

═══ 这条门禁钉的是什么 ═══

`oo_to_html.py` 现有 111 处 D4 提及 + 9 分支 `elif adapter_id ==` 链 + 9 处 `hasattr(bridge, …)`
试探，是「通用回写层被单个循环特化污染」的活样本。光删一次不够——下一个接底稿的人会照原样
再加一个 elif。因此把「框架层不感知具体 wp_code」做成机器守的卡点：

判据（AST，不跑业务、不连库、stdlib-only）：
  在框架层模块里，任何形如 `<name> == "<adapter/wp 字面量>"` 的**比较分支**即命中。
  * `<name>` ∈ {adapter_id, contract_id, wp_code, entry_id} 或以它们结尾的属性访问
  * `<字面量>` 匹配 adapter_id 形态 `^[a-z]\d?\.\w+$`（如 `d4.revenue_detail` / `b60.hour_budget`）
    或 wp_code 形态 `^[A-Z]\d+(-\d+)?[A-Z]?$`（如 `D4`, `D1-3`, `D4-35`）

  同时检测 `hasattr(bridge, "STORE_ITEM_ID_D4xx_DICT")` 式 per-adapter 试探（Requirement 3.2）。

白名单（显式登记，两类）：
  * 注册表模块本身（`store_item_registry` / `transposed_registry`）—— 它们的职责就是持有映射，
    但**注册表用 dict key 存 adapter_id 是合法的**，不是分支；这里只豁免"字面量比较"检测。
  * 错误消息文案里的 adapter_id（`f"adapter {adapter_id!r} 未注册…"`）—— 那不是分支。

现状（Task 2）：**必红**（oo_to_html 9 elif + 9 hasattr）。抽取后（Task 20）：**必绿**。
命中即 exit 1，逐条打印 `模块:行号  命中形态`。
自测：`backend/tests/scripts/test_check_framework_layer_has_no_wp_code_branch.py`。
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        pass

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_SYNC = _BACKEND / "app" / "services" / "workpaper_sync"

#: 框架层（全平台唯一实现）模块 —— 这些文件里不得出现 per-adapter 字面量分支。
FRAMEWORK_MODULES: tuple[str, ...] = (
    "oo_to_html.py",
    "merge.py",
    "excel_extract.py",
    "excel_materialize.py",
    "store_projection_response.py",
    "adapters/excel.py",
)

#: 显式白名单：注册表模块（持有映射是其职责，字面量作 dict key 合法）。
WHITELIST_MODULES: frozenset[str] = frozenset({
    "store_item_registry.py",
    "transposed_registry.py",
})

#: 触发比较分支检测的标识符名（或以其结尾的属性访问）。
_BRANCH_NAMES: frozenset[str] = frozenset({"adapter_id", "contract_id", "wp_code", "entry_id"})

_ADAPTER_LITERAL = re.compile(r"^[a-z]\d?\.\w+$")           # d4.revenue_detail / b60.hour_budget
_WP_CODE_LITERAL = re.compile(r"^[A-Z]\d+(-\d+)?[A-Z]?$")   # D4 / D1-3 / D4-35 / D1N

_HASATTR_DICT = re.compile(r"^STORE_ITEM_ID_\w+_DICT$")


def _is_branch_name(node: ast.AST) -> bool:
    """节点是否 `adapter_id` / `x.adapter_id` 之类可触发分支检测的名字。"""
    if isinstance(node, ast.Name):
        return node.id in _BRANCH_NAMES
    if isinstance(node, ast.Attribute):
        return node.attr in _BRANCH_NAMES
    return False


def _is_adapter_or_wp_literal(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        s = node.value
        if _ADAPTER_LITERAL.match(s) or _WP_CODE_LITERAL.match(s):
            return s
    return None


def _scan_module(path: Path) -> list[dict[str, Any]]:
    """返回该模块的命中列表。"""
    hits: list[dict[str, Any]] = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    try:
        rel = path.relative_to(_SYNC).as_posix()
    except ValueError:
        rel = path.name

    for node in ast.walk(tree):
        # A. 比较分支：<branch_name> == "<adapter/wp literal>"（或反向）
        if isinstance(node, ast.Compare):
            left = node.left
            comparators = node.comparators
            # 只关心 == / !=
            if all(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
                # 判定：一侧是 branch name，另一侧是 adapter/wp 字面量
                name_side = _is_branch_name(left) or any(_is_branch_name(c) for c in comparators)
                lit = _is_adapter_or_wp_literal(left)
                for c in comparators:
                    lit = lit or _is_adapter_or_wp_literal(c)
                if name_side and lit:
                    hits.append({
                        "module": rel,
                        "line": node.lineno,
                        "kind": "literal_branch",
                        "detail": f"分支比较命中 adapter/wp 字面量 {lit!r}",
                    })
        # B. hasattr(bridge, "STORE_ITEM_ID_*_DICT") 式 per-adapter 试探
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "hasattr":
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                attr = node.args[1].value
                if isinstance(attr, str) and _HASATTR_DICT.match(attr):
                    hits.append({
                        "module": rel,
                        "line": node.lineno,
                        "kind": "hasattr_probe",
                        "detail": f"per-adapter hasattr 试探 {attr!r}",
                    })
    return hits


def run() -> dict[str, Any]:
    all_hits: list[dict[str, Any]] = []
    scanned: list[str] = []
    for rel in FRAMEWORK_MODULES:
        path = _SYNC / rel
        if not path.exists():
            continue
        if path.name in WHITELIST_MODULES:
            continue
        scanned.append(rel)
        all_hits.extend(_scan_module(path))
    return {
        "ok": not all_hits,
        "scanned_modules": scanned,
        "whitelist": sorted(WHITELIST_MODULES),
        "hit_count": len(all_hits),
        "hits": sorted(all_hits, key=lambda h: (h["module"], h["line"])),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=str, default=None)
    args = parser.parse_args()

    report = run()
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if report["ok"]:
        print(f"✅ 框架层零 wp_code/adapter_id 分支：扫描 {len(report['scanned_modules'])} 模块，"
              f"白名单 {report['whitelist']}")
        return 0

    print(f"❌ 框架层含 {report['hit_count']} 处 per-adapter 特化分支（通用层被单循环污染）：")
    for h in report["hits"]:
        print(f"   {h['module']}:{h['line']}  [{h['kind']}] {h['detail']}")
    print("\n应改走注册表查表（O(1) dict）而非字面量分支/hasattr 试探 —— 见 spec 需求 3.1/3.2。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
