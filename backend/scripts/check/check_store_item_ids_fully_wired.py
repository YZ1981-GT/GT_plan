# -*- coding: utf-8 -*-
"""D4 store item 清单单源门禁 —— 断言 provider 上每一条 store item 声明都进了 `all_store_item_ids()`。

spec: d4-html-to-oo-store-contract-alignment · Task 7 · Requirement 3.3

═══ 这条门禁钉的是什么 ═══

真栈实证过两次「provider 声明了一条 store item，而某个方向的装配代码忘了喂它」——
`D4-35-data` 不在任何清单、`STORE_ITEM_IDS_D413_FIXED` 未被出方向消费，结果 D4-35 切 OO
恒空、D4-13 两段正文写不进 OO。Task 4 把「本 entry 有哪些 store item」收敛成 provider 的
`all_store_item_ids()` 单一口径，出/回两方向都从它取。本门禁守住那个收敛不被再次破坏。

判据（AST，不跑业务、不连库、stdlib-only）：
  1. `phase5_d4_revenue_detail` 里所有形如 `STORE_ITEM_IDS*` 的**模块级 tuple 常量**，其成员
     必须**逐个**出现在运行时 `all_store_item_ids()` 的返回里。
  2. 所有形如 `STORE_ITEM_ID_*_DICT` 的 dict-store 常量（如 `STORE_ITEM_ID_D435_DICT`）也必须
     出现在 `all_store_item_ids()` 里 —— D4-35 缺陷正是这类被漏掉。
  3. `all_store_item_ids()` 自身无重复。

为什么 AST 而不是「import 后读常量」：`STORE_ITEM_IDS_D47_DEDICATED` 是 `if _INCLUDE_*` 条件
定义的，直接读会漏；AST 扫源码能看见**所有**声明（含条件块内），是更强的守卫面。运行时值则
通过 import 一次取到 `all_store_item_ids()` 的真实结果做对照。

🔴 为什么落 `backend/scripts/check/` 而不是只放 pytest：`tests/workpaper_sync/` 有大量与本 spec
无关的既存失败，在那个分母上「pytest 红了」不是可归因信号。本门禁可独立红、可独立归因。

命中即 exit 1，逐条打印缺失项。自测：`backend/tests/scripts/test_check_store_item_ids_fully_wired.py`。
"""
from __future__ import annotations

import argparse
import ast
import json
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
PROVIDER_PATH = (
    _BACKEND / "app" / "services" / "workpaper_sync" / "phase5_d4_revenue_detail.py"
)


def _collect_string_members(node: ast.AST) -> list[str]:
    """从一个 tuple/list 字面量 AST 里抽出直接的字符串成员（忽略 starred/表达式成员）。"""
    out: list[str] = []
    if isinstance(node, (ast.Tuple, ast.List)):
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                out.append(elt.value)
    return out


def _static_declared_items(tree: ast.Module) -> dict[str, list[str]]:
    """AST 扫源码，返回 {声明名: [字面量成员...]}。

    覆盖两类：
      * `STORE_ITEM_IDS*` 赋值为 tuple/list 字面量（抽字面量成员；含 starred 的动态成员抽不到，
        由运行时对照兜底 —— 见下方 runtime 集合）；
      * `STORE_ITEM_ID_*_DICT` 赋值为字符串常量或别名（记名，值走运行时解析）。
    """
    declared: dict[str, list[str]] = {}

    def _handle(name: str, value: ast.AST | None) -> None:
        if name.startswith("STORE_ITEM_IDS"):
            declared.setdefault(name, [])
            if value is not None:
                declared[name].extend(_collect_string_members(value))
        elif name.startswith("STORE_ITEM_ID_") and name.endswith("_DICT"):
            declared.setdefault(name, [])
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                declared[name].append(value.value)

    for stmt in ast.walk(tree):
        # 普通赋值 `NAME = (...)`
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    _handle(target.id, stmt.value)
        # 带类型注解的赋值 `NAME: Final[...] = (...)` —— provider 里 STORE_ITEM_IDS 正是这种
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            _handle(stmt.target.id, stmt.value)
    return declared


def _load_runtime() -> tuple[tuple[str, ...], dict[str, tuple[str, ...]], dict[str, str]]:
    """import provider，取运行时 all_store_item_ids() 及各 STORE_ITEM_IDS*/DICT 的实际值。"""
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    import os

    os.environ.setdefault("DB_DISABLE_SSL", "True")
    from app.services.workpaper_sync import phase5_d4_revenue_detail as P

    all_ids = tuple(P.all_store_item_ids())
    id_lists: dict[str, tuple[str, ...]] = {}
    dict_consts: dict[str, str] = {}
    for name in dir(P):
        if name.startswith("STORE_ITEM_IDS"):
            val = getattr(P, name)
            if isinstance(val, (tuple, list)):
                id_lists[name] = tuple(str(v) for v in val)
        elif name.startswith("STORE_ITEM_ID_") and name.endswith("_DICT"):
            val = getattr(P, name)
            if isinstance(val, str):
                dict_consts[name] = val
    return all_ids, id_lists, dict_consts


def run() -> dict[str, Any]:
    tree = ast.parse(PROVIDER_PATH.read_text(encoding="utf-8"))
    static_declared = _static_declared_items(tree)
    all_ids, runtime_id_lists, runtime_dict_consts = _load_runtime()
    all_ids_set = set(all_ids)

    missing: list[dict[str, str]] = []

    # 1+2. 每条 STORE_ITEM_IDS* / *_DICT 声明的成员都要进 all_store_item_ids()。
    #      静态成员（AST）与运行时成员（import）取并集，两边都查——AST 抓条件块内声明，
    #      运行时抓 starred/派生成员。
    for name, members in static_declared.items():
        runtime_members = list(runtime_id_lists.get(name, ()))
        runtime_members += (
            [runtime_dict_consts[name]] if name in runtime_dict_consts else []
        )
        for item in set(members) | set(runtime_members):
            if item and item not in all_ids_set:
                missing.append({"declaration": name, "item_id": item})

    # 运行时还可能有 AST 没扫到的 *_DICT（别名赋值）——一并查。
    for name, item in runtime_dict_consts.items():
        if item and item not in all_ids_set:
            missing.append({"declaration": name, "item_id": item})

    # 🔴 import 进本模块的 `STORE_ITEM_IDS*`（如从 policy_check / erp_check 引入的
    #    D45_FIXED / D413_FIXED）AST 扫不到（不在本文件定义），但它们是 provider 命名空间的
    #    一部分、也必须进 all_store_item_ids()。用运行时 dir(P) 的 tuple 成员兜住这个盲区
    #    —— D4-13 缺陷正属此类（fixed 项从别处 import 却漏接）。
    for name, members in runtime_id_lists.items():
        if name in static_declared:
            continue  # AST 已覆盖（含条件块），上面已查
        for item in members:
            if item and item not in all_ids_set:
                missing.append({"declaration": name, "item_id": item})

    # 3. all_store_item_ids() 无重复。
    dupes = sorted({x for x in all_ids if all_ids.count(x) > 1})

    ok = not missing and not dupes
    return {
        "ok": ok,
        "provider": str(PROVIDER_PATH.relative_to(_REPO)),
        "all_store_item_ids_count": len(all_ids),
        "declarations_scanned": sorted(static_declared.keys()),
        "missing": sorted(missing, key=lambda m: (m["declaration"], m["item_id"])),
        "duplicates": dupes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=str, default=None, help="把报告写到该路径")
    args = parser.parse_args()

    report = run()
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if report["ok"]:
        print(
            f"✅ store item 清单单源门禁通过："
            f"{report['all_store_item_ids_count']} 个 item 全部经 all_store_item_ids() 收敛，"
            f"覆盖声明 {report['declarations_scanned']}"
        )
        return 0

    print("❌ store item 清单未完全接入 all_store_item_ids()：")
    for m in report["missing"]:
        print(f"   [漏项] {m['declaration']} 的成员 {m['item_id']!r} 不在 all_store_item_ids()")
    for d in report["duplicates"]:
        print(f"   [重复] all_store_item_ids() 里 {d!r} 出现多次")
    print(
        "\n根因通常是：新声明了一条 store item 却没接进 provider.all_store_item_ids() —— "
        "那样它在出方向（store_projection_response）或回方向（oo_to_html）会被漏喂，"
        "重演 D4-35 / D4-13 的缺陷 C。请把它并进 all_store_item_ids() 的并集。"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
