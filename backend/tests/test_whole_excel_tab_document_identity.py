# -*- coding: utf-8 -*-
"""「完整Excel」页签的源文档身份守卫。

改动前的缺陷（本文件 `test_the_defect_being_fixed_*` 两条把它实证冻结）：
整册模式沿用 `find_template_file_any(wp_code)`，那是**主模板**口径（「审定 > 常规程序」
优先级阶梯），D4 上返回 ``D4-1至D4-4 …审定表明细表…xlsx`` —— 只有 10 张 sheet。于是标着
「完整Excel」的页签打开的根本不是整本：D4-26 等 36 张 sheet 在那份文件里**不存在**。

修后口径：整册模式取该 wp_code 的**整本工作簿**（D4/F2 是合并本），并在候选里挑**已净化**
那份（无 ``<externalReference>``）。D4 因此与 sync 契约 ``d4.revenue_detail`` 钉住的
``D/D4 收入底稿.xlsx`` 收敛到同一份文档 —— 平台只有一个「D4 整册」身份。

无整册合并本的 wp_code（D2 只有范围式拆分包）行为逐字不变，本改动是纯加法。
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

from app.routers.wp_onlyoffice_router import (
    _has_external_references,
    _resolve_whole_workbook_template,
    _whole_workbook_template_or_primary,
)
from app.services import wp_template_finder as finder

_BACKEND = Path(__file__).resolve().parents[1]
_TEMPLATES = _BACKEND / "wp_templates"

#: sheet 名尾部的底稿编码（`销售退货检查表 D4-20` → `D4-20`）。
_SHEET_CODE_RE = re.compile(r"([A-Z]\d+(?:-\d+)?[A-Z]?)\s*$")


def _sheets(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("xl/workbook.xml").decode("utf-8")
    return re.findall(r'<sheet[^>]*\bname="([^"]*)"', xml)


def _require(path: Path | None) -> Path:
    if path is None or not path.is_file():
        pytest.skip(f"模板不在工作树: {path}")
    return path


# ═══════════════════════════════════════════════════════════════════════════
# 1. 被修的缺陷（反向实证：不冻结它，就说不清"修好了什么"）
# ═══════════════════════════════════════════════════════════════════════════


def test_the_defect_being_fixed_primary_template_is_only_a_subset() -> None:
    """主模板口径下 D4 只有 10 张 sheet，且不含 D4-26 —— 那不叫「完整Excel」。"""
    primary = _require(finder.find_template_file_any("D4"))
    names = _sheets(primary)
    assert "审定表" in primary.name
    assert len(names) == 10
    assert "境外销售收入检查D4-26" not in names


def test_the_defect_being_fixed_unsanitized_twin_carries_external_links() -> None:
    """D4 目录有净化前后两份整册本；未净化那份带外部引用，不能给 OO 开。"""
    unsanitized = _require(_TEMPLATES / "D" / "D4收入底稿.xlsx")
    sanitized = _require(_TEMPLATES / "D" / "D4 收入底稿.xlsx")
    assert _has_external_references(unsanitized) is True
    assert _has_external_references(sanitized) is False
    # 两份 sheet 名序列相同 ⇒ 差别只在净化，不在内容范围
    assert _sheets(unsanitized) == _sheets(sanitized)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 修后口径
# ═══════════════════════════════════════════════════════════════════════════


def test_d4_whole_tab_resolves_to_the_merged_workbook() -> None:
    picked = _require(_whole_workbook_template_or_primary("D4"))
    names = _sheets(picked)
    assert picked.name == "D4 收入底稿.xlsx"
    assert len(names) == 46
    assert "境外销售收入检查D4-26" in names
    assert _has_external_references(picked) is False


def test_sanitized_candidate_wins_over_unsanitized() -> None:
    """候选里同时有净化前后两份时，必须选净化那份（否则一打开就是刷新提示 + #REF!）。"""
    candidates = finder.find_whole_workbook_templates("D4")
    assert len(candidates) >= 2, f"D4 整册候选只有 {[c.name for c in candidates]}，判据会空转"
    assert any(_has_external_references(c) for c in candidates), "没有未净化候选 ⇒ 判据空转"
    picked = _require(_resolve_whole_workbook_template("D4"))
    assert _has_external_references(picked) is False


def test_f2_whole_tab_gets_the_full_inventory_workbook() -> None:
    picked = _require(_whole_workbook_template_or_primary("F2"))
    primary = _require(finder.find_template_file_any("F2"))
    assert picked.name == "F2存货.xlsx"
    assert len(_sheets(picked)) > len(_sheets(primary))


def test_whole_workbook_covers_every_coded_sheet_of_every_split_package() -> None:
    """「完整」的实质判据：拆分包里每一张**带编码**的 sheet 都在整册本里。

    只比 sheet 数量证不出完整性（数量多不代表包含），所以逐张按编码核。
    """
    for wp_code in ("D4", "F2"):
        whole = _require(_whole_workbook_template_or_primary(wp_code))
        whole_names = set(_sheets(whole))
        packages = [
            p for p in finder.find_all_template_files(wp_code)
            if p.suffix.lower() in (".xlsx", ".xlsm") and p.is_file()
        ]
        assert packages, f"{wp_code} 一个拆分包都没解析到 —— 判据会空转"
        checked = 0
        for pkg in packages:
            for name in _sheets(pkg):
                if not _SHEET_CODE_RE.search(name):
                    continue  # 目录页 / GT_Custom / 示例页不参与编码覆盖判据
                assert name in whole_names, (
                    f"{wp_code} 整册本 {whole.name!r} 缺 {pkg.name!r} 的 {name!r} "
                    f"—— 「完整Excel」并不完整"
                )
                checked += 1
        assert checked >= 20, f"{wp_code} 只核了 {checked} 张带编码 sheet，覆盖面不足"


def test_d4_whole_tab_and_sync_contract_point_at_the_same_document() -> None:
    """平台只有一个「D4 整册」身份：完整页签与双模式 artifact 同源。

    不同源意味着同一份底稿有两个整册真相，用户在完整页签改的 sheet 与双模式里看到的
    可能来自不同模板。
    """
    from app.services.workpaper_sync.contracts import load_contract

    contract = load_contract("d4.revenue_detail")
    picked = _require(_whole_workbook_template_or_primary("D4"))
    assert picked.relative_to(_TEMPLATES).as_posix() == str(
        contract.template.relative_path
    )


def test_wp_codes_without_a_merged_book_are_unchanged() -> None:
    """纯加法：没有整册合并本的 wp_code 仍走主模板口径，行为逐字不变。"""
    for wp_code in ("D2",):
        assert _resolve_whole_workbook_template(wp_code) is None
        assert _whole_workbook_template_or_primary(wp_code) == finder.find_template_file_any(
            wp_code
        )


def test_split_package_names_are_never_taken_as_whole_books() -> None:
    """反向自检：范围式拆分包不得被认成整册本（否则"整册"退化成随便一个包）。"""
    for name in (
        "D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx",
        "D4-22至D4-32营业收入-IPO 上市 新三板 重组 舞弊应对.xlsx",
        "F2-1至F2-14 存货及跌价准备-审定明细表类（Leap-常规程序）.xlsx",
        "D4-5 营业收入-会计政策（Leap-常规程序）.xlsx",
    ):
        assert not finder._is_whole_excel_template_name(name), name
    for name in ("D4收入底稿.xlsx", "D4 收入底稿.xlsx", "F2存货.xlsx"):
        assert finder._is_whole_excel_template_name(name), name


# ═══════════════════════════════════════════════════════════════════════════
# 3. 读写同码（整册模式 config/WOPI 读 `{wp_code}.xlsx`，callback 必须写同一处）
# ═══════════════════════════════════════════════════════════════════════════
#
# 改动前 callback **完全不知道** whole 模式：它只能从 `sheet_name` 反推编码，而整册模式
# 前端传的是「首个业务 sheet 名」（如 `营业收入审计程序表D4A`）⇒ 反推出 `D4A` ⇒ 整册编辑
# 被写进 `D4A.xlsx`，而 config/WOPI 读的是 `D4.xlsx`。读写异地 = 保存后再打开就没了。

import ast  # noqa: E402

_ROUTER_PY = _BACKEND / "app" / "routers" / "wp_onlyoffice_router.py"


def _func(tree: ast.Module, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"找不到函数 {name!r}")


def _config_appends_whole_flag(tree: ast.Module) -> bool:
    """config 在整册模式下把 `whole=1` 拼进 callbackUrl。"""
    src = ast.unparse(_func(tree, "get_sheet_onlyoffice_config"))
    return "?whole=1" in src and "callback_url" in src


def _callback_honors_whole_flag(tree: ast.Module) -> bool:
    """callback 读 `whole` query，并据此跳过按 sheet 名反推子码。"""
    fn = _func(tree, "post_sheet_onlyoffice_callback")
    src = ast.unparse(fn)
    if 'query_params.get(\'whole\')' not in src and 'query_params.get("whole")' not in src:
        return False
    # 该判据必须真的**门控**子码推导，而不是读完不用
    return any(
        "_save_is_whole" in ast.unparse(node.test)
        for node in ast.walk(fn)
        if isinstance(node, ast.If)
    )


def _whole_reads_use_the_whole_resolver(tree: ast.Module) -> bool:
    """三条整册读侧（config / WOPI contents / 降级 grid）都走整册解析器。"""
    return all(
        "_whole_workbook_template_or_primary" in ast.unparse(_func(tree, name))
        for name in (
            "get_sheet_onlyoffice_config",
            "get_sheet_wopi_contents",
            "get_whole_excel_grid",
        )
    )


def _assigned_source(fn: ast.AST, target_name: str) -> str:
    """`fn` 体内所有 `target_name = <expr>` 的右侧源码拼接（没有则空串）。

    🔴 判「回写目标真的用了整册 stem」不能只看函数体里有没有出现这个名字：callback 里
    另有一处 `_probe_stem` 也提到它，于是「掐断保存目标」后判据仍绿（反向自检第一次跑
    就抓到了这点）。必须落到**赋值语句的右侧**。
    """
    out: list[str] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if isinstance(tgt, ast.Name) and tgt.id == target_name:
                out.append(ast.unparse(node.value))
    return "\n".join(out)


def _whole_paths_share_one_cache_stem(tree: ast.Module) -> bool:
    """整册的三条读侧 + 回写侧都用 `_whole_cache_stem` 定位工作副本。

    整册源文档是整册本、单 sheet 是主模板 —— **两份不同的文档**，共用
    `{wp_code}.xlsx` 会让整册永久复用旧文档；而只有部分路径用新 stem，则读写异地。
    """
    reads_ok = all(
        "_whole_cache_stem" in ast.unparse(_func(tree, name))
        for name in (
            "get_sheet_onlyoffice_config",
            "get_sheet_wopi_contents",
            "get_whole_excel_grid",
        )
    )
    cb = _func(tree, "post_sheet_onlyoffice_callback")
    stem_from_whole = "_whole_cache_stem" in _assigned_source(cb, "_save_stem")
    target_uses_stem = "_save_stem" in _assigned_source(cb, "target")
    return reads_ok and stem_from_whole and target_uses_stem


_WIRING = (
    ("config 给 callbackUrl 带 whole=1", _config_appends_whole_flag),
    ("callback 按 whole 门控子码推导", _callback_honors_whole_flag),
    ("三条整册读侧走同一解析器", _whole_reads_use_the_whole_resolver),
    ("整册读写共用一个 cache stem", _whole_paths_share_one_cache_stem),
)

_MUTATIONS = (
    ('callback_url += "?whole=1"', "pass"),
    ('_save_is_whole = str(request.query_params.get("whole") or "") == "1"',
     "_save_is_whole = False"),
    ("_whole_workbook_template_or_primary(_sheet_wp_code)\n        if whole_workbook",
     "find_template_file_any(_sheet_wp_code)\n        if whole_workbook"),
    ("_whole_cache_stem(_save_wp_code) if _save_is_whole else _save_wp_code\n            )",
     "_save_wp_code\n            )"),
)


def test_whole_cache_stem_is_distinct_from_the_per_code_working_copy() -> None:
    """整册工作副本的文件名必须与 `{wp_code}` 那份不同（否则修了不生效、且不敢自愈）。"""
    from app.routers.wp_onlyoffice_router import _whole_cache_stem

    assert _whole_cache_stem("D4") != "D4"
    assert _whole_cache_stem("D4").startswith("D4")
    assert _whole_cache_stem("D4") == _whole_cache_stem("D4")  # 确定性


@pytest.mark.parametrize("label,predicate", _WIRING, ids=lambda v: str(v)[:40])
def test_whole_mode_read_and_write_are_wired_to_the_same_code(label, predicate) -> None:
    assert predicate(ast.parse(_ROUTER_PY.read_text(encoding="utf-8"))), f"接线断在：{label}"


def test_selfcheck_wiring_guards_are_load_bearing() -> None:
    """反向自检：掐断任一环，必须至少一条判据打红。"""
    text = _ROUTER_PY.read_text(encoding="utf-8")
    for needle, replacement in _MUTATIONS:
        assert needle in text, f"变异锚点未命中（源码已改形）: {needle!r}"
        mutated = ast.parse(text.replace(needle, replacement, 1))
        assert any(not p(mutated) for _l, p in _WIRING), f"掐断 {needle!r} 后判据仍全绿"
