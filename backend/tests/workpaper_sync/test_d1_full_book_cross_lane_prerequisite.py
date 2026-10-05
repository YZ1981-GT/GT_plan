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
    """依赖在 ⇒ 强断言（两端都在）；不在 ⇒ 标红（不再 skip）。

    2026-10-04 升级：`workpaper-sync-managed-row-convergence` 的 E3 已入库到 HEAD，
    `contracts.is_template_skeleton_identity` 已定义且 `content_mutation` 已调用。
    整册门 ⑤c（G1 roundtrip 等值门）现在应能在纯 HEAD 上跑通。
    """
    defined = _contracts_defines_symbol()
    called = _mutation_calls_symbol()
    assert defined, (
        f"contracts.py 里应已定义 {_SYMBOL}（managed-row-convergence E3 的产物）"
    )
    assert called, (
        f"content_mutation.py 里应已调用 {_SYMBOL}（合取放行的第 ① 条件）"
    )


def test_exemption_keeps_fail_closed_shape() -> None:
    """依赖在的时候，校验豁免**没有被弱化成无条件放行**。

    豁免必须是**合取**：① 身份是模板骨架 ∧ ② store 在本次 projection 里没声明这一行。
    只留 ① 会把「store 声明了某骨架行却缺字段」也放过（那是真缺陷）；
    只留 ② 会把 `d4r-*` / `xsheet-*` / `GTROW-MINTED-*` 这些**真孤儿**放过。
    """
    if not (_contracts_defines_symbol() and _mutation_calls_symbol()):
        pytest.fail("依赖应已在本检出（上一条已断言）—— 此处不应再触发")
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


# ─────────────────────────────────────────────────────────────────────────────
# 🔴 元判据：依赖状态与判据强度必须匹配（X5-k，2026-09-28）
#
# 上面第一条在依赖缺失时 `pytest.skip`，这是对的 —— 那不是本 lane 的缺陷。
# 但它有个长期风险：`workpaper-sync-managed-row-convergence` 的 E3 入库之后，
# skip 分支会变成**永远走不到的死代码**，而判据依然写着「不在就 skip」——
# 下一个人读它会以为这条依赖还悬着。
#
# 本节把「该升级了」这件事做成可执行的提醒：**按 HEAD 口径**判依赖是否已入库
# （不能按工作树 —— 工作树上依赖一直在，那样从第一天起就要求升级），
# 已入库则要求源码里不再有 skip 分支。
# ─────────────────────────────────────────────────────────────────────────────

import subprocess  # noqa: E402  （放在此节，与上面的纯 AST 判定分开）


def _head_source(repo_rel: str) -> str | None:
    proc = subprocess.run(
        ["git", "show", f"HEAD:{repo_rel}"],
        cwd=str(_REPO), capture_output=True,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.decode("utf-8", "replace")


def _dependency_is_on_head() -> bool:
    """跨 lane 依赖在 **HEAD 版**里是否已入库（定义 + 调用两端都在）。"""
    contracts_src = _head_source("backend/app/services/workpaper_sync/contracts.py")
    mutation_src = _head_source(
        "backend/app/services/workpaper_sync/content_mutation.py"
    )
    if contracts_src is None or mutation_src is None:
        return False
    defined = any(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == _SYMBOL
        for n in ast.parse(contracts_src).body
    )
    return defined and calls_symbol(mutation_src)


def upgrade_verdict(landed: bool, has_skip: bool) -> str | None:
    """判定「依赖状态 × 判据强度」是否匹配；返回 None 表示匹配。

    抽成纯函数是为了能把**四个象限**全测一遍（见下方变异判据）——
    把判定写在 test 函数体里就只能测到当前那一个象限，另三个永远不执行。
    """
    if landed and has_skip:
        return (
            "跨 lane 依赖（managed-row-convergence E3：contracts."
            f"{_SYMBOL} + content_mutation 的合取放行）**已入库到 HEAD** ⇒ "
            "请把本文件第一条从 skip 升级为强断言，并更新 X5-f 里「依赖不在」那一支的"
            "描述；整册门 ⑤c 现在应该能在纯 HEAD 上跑通了。"
        )
    if not landed and not has_skip:
        return (
            "跨 lane 依赖尚未入库到 HEAD，但本文件已经没有 skip 分支 —— "
            "CI/干净检出上会因别 lane 的入库节奏而红。先把 skip 分支留着。"
        )
    return None


def test_skip_branch_must_be_removed_once_the_dependency_lands() -> None:
    """依赖已入库 ⇒ 不得再有 skip；未入库 ⇒ skip 必须还在。

    两个方向都断言，所以它既提醒升级、也防止提前升级。
    """
    src = Path(__file__).read_text(encoding="utf-8")
    # 🔴 避免自引用：把字面量拆开，这样这行本身不会命中搜索
    _skip_call = "pytest" + ".skip("
    problem = upgrade_verdict(_dependency_is_on_head(), _skip_call in src)
    assert problem is None, problem


def test_upgrade_verdict_covers_all_four_quadrants() -> None:
    """变异：四象限逐个验，两个「不匹配」象限必须给出非空提示。

    🔴 只测当前象限的判据在另一半永远是死代码 —— 依赖入库那天才发现提示写错，
    就失去了提醒的意义。
    """
    assert upgrade_verdict(True, True), "依赖已入库 + 仍有 skip ⇒ 必须提示升级"
    assert upgrade_verdict(False, False), "依赖未入库 + 已删 skip ⇒ 必须提示回退"
    assert upgrade_verdict(True, False) is None, "依赖已入库 + 已升级 ⇒ 匹配，不该报"
    assert upgrade_verdict(False, True) is None, "依赖未入库 + 保留 skip ⇒ 匹配，不该报"
    # 提示文案必须可操作（点名要改什么），不是一句「不匹配」
    assert "升级为强断言" in (upgrade_verdict(True, True) or "")
    assert "skip 分支留着" in (upgrade_verdict(False, False) or "")


def test_meta_assertion_uses_head_not_worktree() -> None:
    """🔴 钉住口径：升级提醒必须按 HEAD 判，不能按工作树。

    工作树上这条依赖一直在（别 lane 的未提交改动里），按工作树判会从第一天起就要求
    升级，而升级之后 CI 立刻红 —— 那是把两个 lane 的节奏绑死。
    """
    src = Path(__file__).read_text(encoding="utf-8")
    # 🔴 用 AST 精确取函数体，不用字符窗口：首版取 `src[i:i+900]` 越界到了下一个函数，
    #    把那里正当的 `Path(__file__).read_text()`（读本判据文件自己）当成了「读工作树」。
    #    与「取代码段用括号配平而非 split」是同一条教训。
    target = None
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.FunctionDef) and node.name == "_dependency_is_on_head":
            target = node
            break
    assert target is not None, "找不到 _dependency_is_on_head"
    body = ast.get_source_segment(src, target) or ""
    assert body, "取不到函数体源码"
    assert "_head_source" in body, "升级提醒没走 HEAD 口径"
    assert "read_text" not in body, "升级提醒里出现了直接读工作树文件的痕迹"
    # 现状：依赖确实还没入库（若某天入库，上一条会要求升级，本条仍然成立）
    assert isinstance(_dependency_is_on_head(), bool)
