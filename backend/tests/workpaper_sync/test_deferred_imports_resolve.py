# -*- coding: utf-8 -*-
"""平台级守卫：`workpaper_sync` 生产代码里 **import 的名字必须真的存在**。

spec: `h2-h6-h10-pilot-cross-reference-lanes`（H 收口时连续撞到三例同类缺陷）

═══ 这条判据为什么必须存在 ═══════════════════════════════════════════════════════

本会话在 H 收口时实测到**三例**同一形态的缺陷：

1. `neutralize_oo_crash_if_formulas` —— 注册表 21 条声明里 20 条运行时
   `getattr(..., None)` 取不到，OO 加载期崩溃中性化**从未执行**（本轮已修，见
   `oo_crash_neutralization.py`）。
2. G7 的同一个函数，其定义模块 docstring 自己记着：「函数本体**从未随任何 commit 落地**
   ⇒ HEAD 上 G7 的整条 materialize/verify 路径带着一个 `ImportError` 在跑」。
3. `static_sheet_payload_for_adjudication` —— `phase5_d{5,6,7}_expansion` 三个模块
   **函数内延迟 import** 它，而 `phase5_adjudication_sheet` 从来没有这个名字。

共性是**同一个机制**：
  · 延迟 import（函数体内）或 `getattr(..., None)`，让缺失符号不在 import 期暴露；
  · 藏在灰度开关（`if not _INCLUDE_X: return ()`）后面，日常测试永远走不到；
  · 于是「写了但没落地」与「这条路本来就不走」在观测面上**长得一模一样**。

⇒ 静态可判的那一半（名字存在性）必须有判据。本文件就是。

═══ 为什么带基线清单，以及为什么它不是豁免名单 ═══════════════════════════════════

现算 16 处待修（3 处审定表 payload 生成器 + 13 处 F 循环未交付的 sheet 子模块）。
判据**双向锁死**：
  · 出现清单外的缺失 ⇒ 打红（不得新增）；
  · 清单里的某条**已经修好** ⇒ 也打红，要求把它从清单删掉
    （否则清单会慢慢变成永久豁免，缺陷重新有了藏身处）。

🔴 所以「往清单里加一行」不能让红变绿地蒙混过去：加进去的那一条会被 `.. note` 要求写明
   归属 lane，而修好之后不删又会立刻再红。
"""
from __future__ import annotations

import ast
import importlib
import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_PKG = "app.services.workpaper_sync"
_SRC = _BACKEND / "app" / "services" / "workpaper_sync"

#: 已知待修的「import 了但目标未导出」——  `(源文件相对路径, 目标模块尾段, 名字)`。
#:
#: 🔴 **append-only 欠账清单，不是豁免名单**：修好必须删，见模块 docstring。
#:    每条都注明归属 lane，便于 lane 收口时一并清掉。
_KNOWN_MISSING: frozenset[tuple[str, str, str]] = frozenset(
    {
        # ── 审定表 payload 生成器：`AdjudicationSheetSpec` 数据类**存在**，
        #    但把它变成契约 sheet payload 的那个函数从未落地 ⇒ 审定表族真正的前置门。
        #    （并发会话 commit `ad7941e02` 记的是「AdjudicationSheetSpec 未落地」，
        #     实测该数据类在 `f1ec1c67d` 就已引入、在 `ad7941e02` 与 HEAD 都存在 ——
        #     缺的是 payload 生成器与 store 投影/merge 引擎，不是类型本身。）
        #    归属：`g-cycle-adjudication-sheets-coverage` / 审定表引擎 spec
        (
            "phase5_d5_expansion.py",
            "phase5_adjudication_sheet",
            "static_sheet_payload_for_adjudication",
        ),
        (
            "phase5_d6_expansion.py",
            "phase5_adjudication_sheet",
            "static_sheet_payload_for_adjudication",
        ),
        (
            "phase5_d7_expansion.py",
            "phase5_adjudication_sheet",
            "static_sheet_payload_for_adjudication",
        ),
        # ── F 循环：lane 在 entry 模块里按灰度开关延迟 import per-sheet 子模块，
        #    而那些子模块文件尚未交付。归属：f3/f4/f5 lane spec。
        ("phase5_f3_notes_payable.py", _PKG, "phase5_f3_02_detail"),
        ("phase5_f3_notes_payable.py", _PKG, "phase5_f3_04_interest"),
        ("phase5_f3_notes_payable.py", _PKG, "phase5_f3_01_adjudication"),
        ("phase5_f4_accounts_payable.py", _PKG, "phase5_f4_05_long_outstanding"),
        ("phase5_f4_accounts_payable.py", _PKG, "phase5_f4_08_voucher_check"),
        ("phase5_f4_accounts_payable.py", _PKG, "phase5_f4_07_unrecorded"),
        ("phase5_f4_accounts_payable.py", _PKG, "phase5_f4_02_detail"),
        ("phase5_f4_accounts_payable.py", _PKG, "phase5_f4_09_supplier_financing"),
        ("phase5_f4_accounts_payable.py", _PKG, "phase5_f4_01_adjudication"),
        ("phase5_f5_cost_of_sales.py", _PKG, "phase5_f5_05_comparison"),
        ("phase5_f5_cost_of_sales.py", _PKG, "phase5_f5_03_other_cost"),
        ("phase5_f5_cost_of_sales.py", _PKG, "phase5_f5_02_monthly_detail"),
        ("phase5_f5_cost_of_sales.py", _PKG, "phase5_f5_07_cost_rollforward"),
    }
)


def _name_resolves(module_path: str, name: str) -> bool:
    """`from module_path import name` 是否真的能解析。

    🔴 两条都要试：`from pkg import submodule` 在子模块未被导入时 `hasattr` 为假，
    那**不是**缺陷 —— 漏了这一支会产出一大批假红（首版探针实测 60+ 条全是这类）。
    """
    try:
        mod = importlib.import_module(module_path)
    except Exception:  # noqa: BLE001 —— 模块本身 import 失败另有判据
        return False
    if hasattr(mod, name):
        return True
    try:
        importlib.import_module(f"{module_path}.{name}")
        return True
    except Exception:  # noqa: BLE001
        return False


def _scan() -> set[tuple[str, str, str]]:
    """现算全部「import 了但目标未导出」的 `(文件名, 目标模块, 名字)`。

    🔴 用 `ast` 而不是正则：延迟 import 在函数体里、常带括号续行，正则会漏。
    🔴 键里**不含行号**：行号会随任何编辑漂移，把它写进基线等于制造伪失败。
    """
    found: set[tuple[str, str, str]] = set()
    for path in sorted(_SRC.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            if not node.module.startswith(_PKG):
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                if not _name_resolves(node.module, alias.name):
                    found.add((path.name, node.module, alias.name))
    return found


def _short(entry: tuple[str, str, str]) -> tuple[str, str, str]:
    """把目标模块压成尾段，便于与基线（写尾段）比对。"""
    src, mod, name = entry
    return (src, mod if mod == _PKG else mod.rsplit(".", 1)[-1], name)


@pytest.fixture(scope="module")
def scanned() -> set[tuple[str, str, str]]:
    return {_short(e) for e in _scan()}


def test_the_scan_finds_something_to_compare(scanned: set) -> None:
    """自检前提：扫描器真的在工作。

    扫描器若因路径/解析问题产出空集，下面两条会双双空转变成永久绿。
    """
    assert _SRC.is_dir(), f"源目录不存在 {_SRC}"
    assert len(list(_SRC.rglob("*.py"))) > 100, "生产模块数异常少，扫描范围可能算错了"
    # 空集是合法终态（全部修完），但那时基线也必须是空的 —— 由下一条守
    assert scanned == scanned  # 形式自检，真正的判据在下面两条


def _extra_over_baseline(
    scanned: set[tuple[str, str, str]], baseline: frozenset[tuple[str, str, str]]
) -> list[tuple[str, str, str]]:
    """现算里超出基线的部分（= 新增缺陷）。抽成函数供变异判据复用。"""
    return sorted(scanned - baseline)


def _baseline_entries_already_fixed(
    scanned: set[tuple[str, str, str]], baseline: frozenset[tuple[str, str, str]]
) -> list[tuple[str, str, str]]:
    """基线里已经修好的部分（= 清单该删的行）。抽成函数供变异判据复用。"""
    return sorted(baseline - scanned)


def test_no_new_unresolved_imports(scanned: set) -> None:
    """🔴 不得新增「import 了但目标不存在」。"""
    extra = _extra_over_baseline(scanned, _KNOWN_MISSING)
    assert not extra, (
        "出现基线外的未解析 import —— 这类缺陷会藏在延迟 import + 灰度开关后面，"
        "第一次真正走到那条路才炸：\n"
        + "\n".join(f"  {src}: from {mod} import {name}" for src, mod, name in extra)
    )


def test_baseline_entries_are_still_really_missing(scanned: set) -> None:
    """🔴 反向：基线里**已修好**的条目必须从基线删掉。

    这条是「清单不得变成豁免名单」的实现 —— 修好不删就打红。
    """
    fixed = _baseline_entries_already_fixed(scanned, _KNOWN_MISSING)
    assert not fixed, (
        "以下条目已经能解析了，请从 `_KNOWN_MISSING` 里删掉（否则清单会退化成永久豁免）：\n"
        + "\n".join(f"  {src}: from {mod} import {name}" for src, mod, name in fixed)
    )


def test_scan_really_detects_the_known_defects(scanned: set) -> None:
    """🔴 正向对照：扫描器必须**真的**命中那三条审定表 payload 生成器缺失。

    不是「基线与现算相等」那种自证 —— 这里直接点名断言，扫描器若坏成空集会当场红。
    """
    for src in ("phase5_d5_expansion.py", "phase5_d6_expansion.py", "phase5_d7_expansion.py"):
        assert (
            src,
            "phase5_adjudication_sheet",
            "static_sheet_payload_for_adjudication",
        ) in scanned, f"{src} 的 payload 生成器缺失未被扫到 —— 扫描器失效"


def test_dropping_a_baseline_entry_would_red(scanned: set) -> None:
    """🔴 变异判据①：基线少一条 ⇒ 「不得新增」必须报出那一条。

    证明 `test_no_new_unresolved_imports` 真的在承重，而不是恒空比较。
    """
    victim = next(iter(_KNOWN_MISSING))
    weakened = frozenset(_KNOWN_MISSING - {victim})
    assert _extra_over_baseline(scanned, weakened) == [victim]


def test_adding_a_phantom_baseline_entry_would_red(scanned: set) -> None:
    """🔴 变异判据②：往基线塞一条**其实不缺**的 ⇒ 「清单不得变豁免名单」必须报出它。

    这条钉住的是：想靠往 `_KNOWN_MISSING` 加行把红改绿的人，会被这一侧当场抓住。
    """
    phantom = ("phase5_row_table_sheet.py", _PKG, "phase5_adjudication_sheet")
    assert phantom not in scanned, "选的哨兵条目本身就缺失，换一个真实存在的目标"
    inflated = frozenset(_KNOWN_MISSING | {phantom})
    assert _baseline_entries_already_fixed(scanned, inflated) == [phantom]


def test_adjudication_sheet_spec_type_itself_does_exist() -> None:
    """🔴 钉死一条**被误判过**的事实：`AdjudicationSheetSpec` 数据类是**存在**的。

    并发会话 commit `ad7941e02` 的结论是「AdjudicationSheetSpec … 当前 HEAD 不存在」，
    据此把 13 张审定表的 Task 2~11 全部标成阻塞。实测：该数据类由 `f1ec1c67d` 引入，
    在 `ad7941e02` 与 HEAD 都在，且已有 6 个声明实例（D1-1/D3-1/D5-1/D6-1/D7-1/F1-1）。

    审定表族真正的前置门是**另外两件**：
      · 契约 payload 生成器 `static_sheet_payload_for_adjudication` 不存在（见基线 3 条）；
      · 没有消费 `AdjudicationSheetSpec` 的 store 投影 / merge 引擎
        （行表那边是 `phase5_row_table_sheet.build_store_projection`，审定表这边没有对位物）。

    把「类型不存在」当阻塞理由会让后来人去重建一个已经存在的类型。
    """
    from app.services.workpaper_sync import phase5_adjudication_sheet as A

    assert hasattr(A, "AdjudicationSheetSpec")
    assert hasattr(A, "AdjudicationRowMode")
    assert hasattr(A, "AdjudicationSection")
    assert hasattr(A, "AdjudicationValueSource")
    # 已有声明实例 —— 数量现算，只断言「不得归零」（新交付会让它增长）
    declared = [
        m
        for m in (
            "phase5_d1_01_adjudication",
            "phase5_d3_01_adjudication",
            "phase5_d5_01_adjudication",
            "phase5_d6_01_adjudication",
            "phase5_d7_01_adjudication",
            "phase5_f1_01_adjudication",
        )
        if (_SRC / f"{m}.py").exists()
    ]
    assert declared, "6 个审定表声明实例一个都不在了 —— 前置门事实已变，须重新核查"

    # 🔴 引擎缺口现算断言：没有任何生产模块导出「消费 AdjudicationSheetSpec 的投影函数」。
    #    修好之后这条会打红，届时把它翻面成「引擎已就位」。
    assert not hasattr(A, "static_sheet_payload_for_adjudication"), (
        "payload 生成器已落地 —— 请同时从 `_KNOWN_MISSING` 删掉那 3 条，"
        "并把本断言翻面成「引擎已就位」"
    )
