# -*- coding: utf-8 -*-
"""`check_framework_layer_has_no_wp_code_branch.py` 门禁自测（P9 / D1-P9）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 2（红判据先行）

覆盖：
  1. 现状**必红**（抽取前 oo_to_html 有 9 elif + 6 hasattr_probe）—— 这是 P9「先打红」的意义，
     没有这条红，Task 20 的转绿不可归因。
  2. 命中里确实含 literal_branch（adapter_id 字面量比较）与 hasattr_probe 两类。
  3. 变异反证（正向）：构造一份「干净」源（无 adapter 分支）⇒ _scan_module 命中 0。
  4. 变异反证（反向）：往干净源里塞一个 `if adapter_id == "d1.notes_receivable_detail":`
     ⇒ 必被检出。
  5. 白名单模块（注册表）被跳过。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))

_CHECK_PATH = _BACKEND / "scripts" / "check" / "check_framework_layer_has_no_wp_code_branch.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "_check_framework_layer_no_wp_branch", _CHECK_PATH
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_oo_to_html_elif_chain_is_gone() -> None:
    """Task 13 转绿的**可归因断言**：`oo_to_html` 里 9 分支 elif adapter_id 链已删。

    ═══ 红→绿的归因链（本判据是它的落点）═══

    Task 2 落判据时实测 **17 处**命中（11 literal_branch：oo_to_html 9 个 elif adapter_id
    分支 + adapters/excel 2 个 g7 分支；6 hasattr_probe）。Task 13 把 elif 链改为
    `store_item_registry` 查表后，`oo_to_html` 的 literal_branch 应**归零**。

    🔴 本判据只钉 `oo_to_html` 的 literal_branch 归零（Task 13 的作业面），不断言全局 ok ——
    剩余两类如实登记在 `test_remaining_hits_are_declared_scope`：
      * `adapters/excel.py` 的 2 个 g7 分支（extract 侧，非本 task 作业面）
      * `oo_to_html` 的 6 个 D4 dict-store hasattr 试探（在 `_mirror_d4_dual_stores` 专用门面内，
        改它须动 D4 dict-store 分派；spec 需求 2.5 明令不重构 D4 的 26 个 per-sheet 模块）
    """
    report = _load_module().run()
    oo_literal = [
        h for h in report["hits"]
        if h["module"] == "oo_to_html.py" and h["kind"] == "literal_branch"
    ]
    assert oo_literal == [], (
        f"oo_to_html 仍有 {len(oo_literal)} 个 adapter_id 字面量分支 —— "
        f"Task 13 的注册表化未完成：{oo_literal}"
    )


def test_remaining_hits_are_declared_scope() -> None:
    """P9 现已全部转绿（Task 13 完整收敛）：`adapters/excel.py` 的 2 个 g7 分支已改注册表声明
    `oo_crash_neutralization_fn`；`oo_to_html` 的 6 个 D4 dict hasattr 试探已改注册表声明
    `dedicated_items`。命中集合现应为空 —— 任何新出现的命中都是回归，必须打红。
    """
    report = _load_module().run()
    assert report["hits"] == [], f"框架层出现新的 per-adapter 分支/hasattr 试探：{report['hits']}"


def test_detector_covers_both_kinds(tmp_path: Path) -> None:
    """检测器两类形态都有效。

    🔴 2026-09-26 改法变更：原判据靠「生产代码现状恰好留有 hasattr 命中」证明检测器有效
    ——这条证据来源随 Task 13 收敛（`oo_to_html` 6 处 hasattr 试探已改注册表分派）而消失，
    但检测器本身的能力没有变化。改为独立样例源码驱动，不再依赖生产代码现状：
    检测器有效性的证明应该独立于「今天生产代码里恰好还留了几个 bug」这件事，
    否则每修一个就要重新构造"证据"，这正是本次教训要修的耦合。
    """
    mod = _load_module()
    sample = tmp_path / "sample_with_hasattr_probe.py"
    sample.write_text(
        'if hasattr(bridge, "STORE_ITEM_ID_D999_DICT"):\n'
        "    pass\n",
        encoding="utf-8",
    )
    hits = mod._scan_module(sample)
    kinds = {h["kind"] for h in hits}
    assert "hasattr_probe" in kinds, "hasattr 检测失效（用独立样例源码驱动，不依赖生产代码现状）"
    # literal_branch 检测有效性由 test_mutation_injected_branch_is_detected 的注入变异证明


def test_clean_source_has_no_hit(tmp_path: Path) -> None:
    mod = _load_module()
    clean = tmp_path / "clean.py"
    clean.write_text(
        "def f(plan):\n"
        "    return plan.merge_fn(x)\n",
        encoding="utf-8",
    )
    hits = mod._scan_module(clean)
    # _scan_module 用相对 _SYNC 的路径，这里用绝对 tmp 会抛；改为直接扫 AST 逻辑等价：
    # 复用 run 无法指向 tmp，故此处仅断言无 adapter 分支源不产命中。
    assert hits == []


def test_mutation_injected_branch_is_detected(tmp_path: Path) -> None:
    """反向变异：塞一个 adapter_id 字面量分支 ⇒ 必被检出。"""
    mod = _load_module()
    dirty = tmp_path / "dirty.py"
    dirty.write_text(
        "def f(adapter_id):\n"
        "    if adapter_id == 'd1.notes_receivable_detail':\n"
        "        return 1\n"
        "    if hasattr(bridge, 'STORE_ITEM_ID_D435_DICT'):\n"
        "        return 2\n"
        "    return 0\n",
        encoding="utf-8",
    )
    hits = mod._scan_module(dirty)
    kinds = {h["kind"] for h in hits}
    assert "literal_branch" in kinds, "adapter_id 字面量分支未被检出"
    assert "hasattr_probe" in kinds, "hasattr 试探未被检出"


def test_whitelist_registry_modules_skipped() -> None:
    report = _load_module().run()
    scanned = set(report["scanned_modules"])
    assert "store_item_registry.py" not in scanned
    assert "transposed_registry.py" not in scanned
