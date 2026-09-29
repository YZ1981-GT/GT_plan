# -*- coding: utf-8 -*-
"""整册门 ⑤c（G1 roundtrip 等值门）的**跨 lane 前置依赖**声明。

spec: d1-sync-row-table-engine-and-d1-coverage · X5-f
Requirements 7.4

═══ 这条判据存在的理由 ═══

2026-09-28 实测：把 `excel_materialize.py` / `content_mutation.py` 临时换成 HEAD 版后
（本 lane 在这两个文件里的 hunk 已全部入库，剩下的是别 lane 的未提交改动），
整册门 `verify_d1_full_book_real_stack.py` 卡在第 ⑤c 步：

    RoundtripEquivalenceError: staged representation 反读出未提交的受管字段
    ['bad_debt_individual_rows/GTROW-D14INDIVIDUAL-0013/item',
     'bad_debt_portfolio_rows/GTROW-D14PORTFOLIO-0018/item',
     'category_detail_rows/GTROW-D12-0011/note_type', ...]（共 18 个）

前 5 步全部正常（受管区 18 / materialize OK size=136386 / extract 360 值 18 表 /
反读覆盖 18/18），只有等值门红。

根因**不在本 lane**：D1 模板在受管区内自带非空业务值（与 D4 同型 —— D4 权威模板有
466 个 editable 非空字段），store 只声明「有业务数据的行」，所以模板骨架行不在
`intended.row_keys` 里是常态；extract 把模板自带的值反读出来 ⇒ 它们恒为 `extra`。

豁免逻辑（`contracts.is_template_skeleton_identity` + `content_mutation` 里按
「① 身份是模板骨架 ∧ ② store 在本次 projection 里完全没声明这一行」合取放行）属
**`workpaper-sync-managed-row-convergence` lane 的 E3**，其改动尚未入库。

⇒ 结论如实记：本 lane 的改动已全部入库（干净检出上 6 道 Gate + 7 份自测全绿），
  但整册门这个真栈 E2E 要在纯 HEAD 上跑通，**还需 managed-row-convergence 的 E3 入库**。
  整册门不在 CI 内（需真 PG + storage），所以这不构成 CI 红。

本判据把这条依赖写成可执行的东西：依赖在 ⇒ 校验它的形状没被弱化；依赖不在 ⇒ skip
并把那个难读的 `RoundtripEquivalenceError` 翻译成一句结论，省得后来者对着它猜半天。
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SYNC = _REPO / "backend" / "app" / "services" / "workpaper_sync"
_CONTRACTS = _SYNC / "contracts.py"
_MUTATION = _SYNC / "content_mutation.py"

_SYMBOL = "is_template_skeleton_identity"


def _contracts_defines_symbol() -> bool:
    tree = ast.parse(_CONTRACTS.read_text(encoding="utf-8"))
    return any(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == _SYMBOL
        for n in tree.body
    )


def calls_symbol(source: str) -> bool:
    """🔴 用 AST 判「真的调用了」，不用文本 `in` —— 后者会被注释/docstring 骗过

    （铁律㉖；本轮已经在 hook 的 `--staged` 上踩过一次同型的坑：用
    `'--staged' in text` 判断 hook 装好了没，命中的是我自己写的注释）。

    做成接受 source 的纯函数，才能用内联样本做双向变异（见文件末两条判据）。
    """
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id == _SYMBOL:
                return True
            if isinstance(fn, ast.Attribute) and fn.attr == _SYMBOL:
                return True
    return False


def _mutation_calls_symbol() -> bool:
    return calls_symbol(_MUTATION.read_text(encoding="utf-8"))


def test_cross_lane_prerequisite_is_present_or_explained() -> None:
    """依赖在 ⇒ 过；不在 ⇒ skip 并说清整册门 ⑤c 会怎么红、根因归谁。"""
    defined = _contracts_defines_symbol()
    called = _mutation_calls_symbol()
    if defined and called:
        return
    pytest.skip(
        "整册门 ⑤c（G1 roundtrip 等值门）的跨 lane 前置依赖不在本检出：\n"
        f"  contracts.{_SYMBOL} 已定义={defined} / content_mutation 已调用={called}\n"
        "⇒ 跑 verify_d1_full_book_real_stack.py 会在第 ⑤c 步报\n"
        "   `RoundtripEquivalenceError: staged representation 反读出未提交的受管字段`\n"
        "   （18 个，形如 `*/GTROW-D14INDIVIDUAL-0013/item`、`*/GTROW-D12-0011/note_type`）。\n"
        "   前五步全部正常。根因是 D1 模板在受管区内自带非空业务值、而 store 只声明\n"
        "   有业务数据的行 ⇒ 模板骨架行恒为 extra；豁免属 "
        "`workpaper-sync-managed-row-convergence` 的 E3，与本 spec 无关。\n"
        "   整册门不在 CI 内（需真 PG + storage），故这不构成 CI 红。"
    )


def test_exemption_keeps_fail_closed_shape() -> None:
    """依赖在的时候，校验豁免**没有被弱化成无条件放行**。

    豁免必须是**合取**：① 身份是模板骨架 ∧ ② store 在本次 projection 里没声明这一行。
    只留 ① 会把「store 声明了某骨架行却缺字段」也放过（那是真缺陷）；
    只留 ② 会把 `d4r-*` / `xsheet-*` / `GTROW-MINTED-*` 这些**真孤儿**放过。
    """
    if not (_contracts_defines_symbol() and _mutation_calls_symbol()):
        pytest.skip("依赖不在本检出（上一条已说明）")
    src = _MUTATION.read_text(encoding="utf-8")
    i = src.find(_SYMBOL, src.find("def "))
    # 取调用点附近的代码（不含前面那一大段说明注释）
    call_idx = -1
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call):
            fn = node.func
            if (isinstance(fn, ast.Name) and fn.id == _SYMBOL) or (
                isinstance(fn, ast.Attribute) and fn.attr == _SYMBOL
            ):
                call_idx = node.lineno
                break
    assert call_idx > 0, "找不到调用点的行号"
    lines = src.split("\n")
    window = "\n".join(lines[max(0, call_idx - 12) : call_idx + 3])
    # ② 的形态：与「store 声明集」比对（declared / row_keys 任一出现即可）
    assert "declared" in window or "row_keys" in window, (
        "豁免条件里看不到「store 未声明这一行」这一半 —— 可能被弱化成无条件放行：\n"
        f"{window}"
    )
    assert " and " in window or "if " in window, (
        f"豁免看起来不是合取条件：\n{window}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 检测器本身的双向变异（不改真文件 —— 用内联样本）
# ─────────────────────────────────────────────────────────────────────────────


def test_detector_is_not_fooled_by_comments_or_docstrings() -> None:
    """只在注释/docstring/字符串里出现符号名 ⇒ 必须判「没调用」。

    这是本轮踩过的坑的正面判据：`'X' in text` 会把注释当成实现。
    """
    fooling = f'''
"""这个 docstring 提到 {_SYMBOL} 但没调用它。"""
# 注释里也写了 {_SYMBOL}
MSG = "字符串里同样写了 {_SYMBOL}"


def f(extra):
    return extra  # 这里本该调用 {_SYMBOL} 却没有
'''
    assert not calls_symbol(fooling), (
        "注释/docstring/字符串里的符号名被当成了调用 —— 检测器退回文本匹配了"
    )


def test_detector_finds_real_calls_in_both_forms() -> None:
    """裸调用与属性调用两种形态都要认出来（反向变异：干净样本必须命中）。"""
    bare = f"def f(i):\n    return {_SYMBOL}(i)\n"
    attr = f"import contracts\n\ndef f(i):\n    return contracts.{_SYMBOL}(i)\n"
    assert calls_symbol(bare), "裸调用没认出来"
    assert calls_symbol(attr), "属性调用没认出来（真源就是 `from ... import` 后裸调用，"
    "但别人改成模块前缀调用时不能漏）"
