"""语义 preflight 守卫。

Feature: custom-workpaper-template-ingestion-and-sync-closure
Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7
"""
from __future__ import annotations

import io
from zipfile import ZipFile

from openpyxl import Workbook

from app.services.custom_template_ingestion.package_scanner import scan_package_bytes
from app.services.custom_template_ingestion.policy import (
    FINDING_EMPTY_REPORT,
    Severity,
    Verdict,
)
from app.services.custom_template_ingestion.semantic_preflight import (
    FINDING_PACKAGE_GATE,
    FINDING_SEMANTIC_COMPLETE,
    GUIDANCE_SECTION_KEYS,
    ProjectionRecommendation,
    SemanticPreflightResult,
    _finish,
    package_blocks_semantic_open,
    run_semantic_preflight,
)


def _xlsx_bytes(*, sheets: dict[str, list[tuple[str, object]]] | None = None,
                defined_names: dict[str, str] | None = None) -> bytes:
    wb = Workbook()
    # 删掉默认 Sheet，按调用方重建
    default = wb.active
    wb.remove(default)
    if not sheets:
        sheets = {"Sheet1": [("A1", 1), ("A2", "=B1+1")]}
    for name, cells in sheets.items():
        ws = wb.create_sheet(name)
        for coord, value in cells:
            ws[coord] = value
    if defined_names:
        from openpyxl.workbook.defined_name import DefinedName
        for name, attr in defined_names.items():
            wb.defined_names.add(DefinedName(name=name, attr_text=attr))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_clean_workbook_is_preflight_ready() -> None:
    payload = _xlsx_bytes(defined_names={"RowKey": "Sheet1!$A$1"})
    result = run_semantic_preflight(payload, filename_hint="ok.xlsx")
    assert result.is_valid is True
    assert result.verdict is Verdict.PREFLIGHT_READY
    assert result.semantic_opened is True
    assert result.workbook is not None
    assert result.workbook.sheet_count == 1
    assert FINDING_SEMANTIC_COMPLETE in {f.code for f in result.findings}


def test_package_security_blocker_skips_semantic_open() -> None:
    result = run_semantic_preflight(b"not-a-zip", filename_hint="bad.xlsx")
    assert result.semantic_opened is False
    assert result.is_valid is False
    assert FINDING_PACKAGE_GATE in {f.code for f in result.findings}
    assert result.projection_recommendation is ProjectionRecommendation.BLOCKED


def test_path_traversal_package_blocks_semantic() -> None:
    buf = io.BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("xl/../evil.xml", "<a/>")
        zf.writestr("[Content_Types].xml", "<Types/>")
    pkg = scan_package_bytes(buf.getvalue())
    assert package_blocks_semantic_open(pkg) is True


def test_workbook_report_has_digests_and_sheets() -> None:
    payload = _xlsx_bytes(sheets={
        "A": [("A1", "title"), ("B1", "=Sheet2!A1")],
        "Sheet2": [("A1", 10)],
    })
    result = run_semantic_preflight(payload)
    assert result.workbook is not None
    assert len(result.workbook.artifact_sha256) == 64
    assert result.workbook.policy_version
    assert result.workbook.scanner_build_id
    assert result.workbook.sheet_count == 2
    assert any("Sheet2!" in f or "Sheet2" in f for f in result.workbook.cross_sheet_formulas) or any(
        s.cross_sheet_formula_count > 0 for s in result.workbook.sheets
    )


def test_sheet_report_covers_required_observations() -> None:
    payload = _xlsx_bytes(sheets={"Main": [
        ("A1", "hdr"), ("A2", 1), ("B2", "=A2*2"),
    ]}, defined_names={"MainKey": "Main!$A$2"})
    result = run_semantic_preflight(payload)
    sheet = result.workbook.sheets[0]
    # 🔴 sheet_uid 供 `unified_child_entry_id` 拼 entry_id，而该函数用冒号作分隔符
    # 并**明确拒绝**含冒号的 uid。曾用 `sheet:{order}:{token}` 使 preflight 产出的
    # uid 无法建册（两个模块约定不一致）。现为 `sheet-{order}-{token}`。
    assert sheet.sheet_uid.startswith("sheet-")
    assert ":" not in sheet.sheet_uid, "sheet_uid 不得含冒号（保留作 entry 分隔符）"
    assert sheet.sheet_name == "Main"
    assert sheet.order == 0
    # 顺序 + 名称摘要 ⇒ 同名不同序仍是不同 uid，同序同名稳定不变
    assert sheet.sheet_uid == f"sheet-0-{sheet.sheet_uid.rsplit('-', 1)[-1]}"
    assert sheet.non_empty_cells >= 3
    assert sheet.formula_count >= 1
    assert sheet.used_range
    assert sheet.projection_recommendation in set(ProjectionRecommendation)


def test_guidance_candidates_are_nine_sections_review_pending() -> None:
    payload = _xlsx_bytes()
    result = run_semantic_preflight(payload)
    sheet = result.workbook.sheets[0]
    keys = [g.key for g in sheet.guidance_candidates]
    assert keys == list(GUIDANCE_SECTION_KEYS)
    for g in sheet.guidance_candidates:
        d = g.to_dict()
        assert d["extractionSource"] == "custom_candidate"
        assert d["completionStatus"] == "review_pending"
        assert "confirmed" not in d


def test_no_carrier_recommends_read_only_or_oo_not_editable() -> None:
    payload = _xlsx_bytes(sheets={"Bare": [("A1", "x"), ("A2", 1)]})
    result = run_semantic_preflight(payload)
    sheet = result.workbook.sheets[0]
    assert sheet.projection_recommendation in {
        ProjectionRecommendation.READ_ONLY_HTML,
        ProjectionRecommendation.ONLYOFFICE_ONLY,
    }
    assert sheet.projection_recommendation is not ProjectionRecommendation.EDITABLE_GRID
    assert "no_existing_stable_carrier" in sheet.identity_risks


def test_defined_name_carrier_allows_editable_grid_recommendation() -> None:
    payload = _xlsx_bytes(
        sheets={"Main": [("A1", 1), ("A2", 2)]},
        defined_names={"StableRow": "Main!$A$1"},
    )
    result = run_semantic_preflight(payload)
    sheet = result.workbook.sheets[0]
    assert any(c.kind.value == "defined_name" for c in sheet.identity_carriers)
    assert sheet.projection_recommendation is ProjectionRecommendation.EDITABLE_GRID


def test_empty_findings_path_never_valid() -> None:
    pkg = scan_package_bytes(_xlsx_bytes(), filename_hint="ok.xlsx")
    # 人为造一个「空 findings」收尾路径
    result = _finish(pkg, None, [], ProjectionRecommendation.EDITABLE_GRID, opened=False)
    assert result.is_valid is False
    assert any(f.code == FINDING_EMPTY_REPORT for f in result.findings)
    assert result.projection_recommendation is ProjectionRecommendation.BLOCKED


def test_formulas_not_evaluated() -> None:
    """公式格保留表达式文本，不出现求值后的数字替代。"""
    payload = _xlsx_bytes(sheets={"S": [("A1", 2), ("A2", "=A1*10")]})
    result = run_semantic_preflight(payload)
    samples = result.workbook.sheets[0].sample_formulas
    assert any(s.startswith("=A1") for s in samples)


def test_finding_shape_has_code_severity_locator_remediation() -> None:
    result = run_semantic_preflight(b"", filename_hint="x.xlsx")
    assert result.findings
    for f in result.findings:
        d = f.to_dict()
        assert "code" in d and "severity" in d
        assert "locator" in d and "remediation" in d
        assert "policyDecision" in d


def test_vba_feature_still_opens_semantic_but_not_valid() -> None:
    """能力矩阵 BLOCKER 不等于安全门：仍可读结构，但 overall 不可 valid。"""
    # 最小 xlsx + vbaProject.bin 部件
    base = _xlsx_bytes()
    buf = io.BytesIO()
    with ZipFile(io.BytesIO(base), "r") as src, ZipFile(buf, "w") as dst:
        for info in src.infolist():
            dst.writestr(info, src.read(info.filename))
        dst.writestr("xl/vbaProject.bin", b"MZ")
    result = run_semantic_preflight(buf.getvalue(), filename_hint="m.xlsx")
    # 包门未拦路径/加密 → 可打开语义；但 VBA BLOCKER 使 verdict BLOCKED
    assert result.semantic_opened is True
    assert result.is_valid is False
    assert result.projection_recommendation is ProjectionRecommendation.BLOCKED


def test_to_dict_roundtrip_keys() -> None:
    result = run_semantic_preflight(_xlsx_bytes(defined_names={"K": "Sheet1!$A$1"}))
    d = result.to_dict()
    assert d["valid"] is True
    assert d["workbook"]["sheetCount"] == 1
    assert isinstance(d["findings"], list)


# ---------------------------------------------------------------------------
# 逐 region 确认：amount region 候选推导（2026-11-24，平台技术债清偿）
#
# 背景：unit-authority 的 manifest.regions 此前由客户端自造（没有任何候选来源），
# 「逐 amount region 确认 UI」无从谈起。现在 preflight 报告按列统计产出候选，
# 前端按候选清单让用户逐 region 裁决（kind / unit / divisor），scanner 不猜单位。
#
# 判据：
# 1. 金额列形态（首 3 行有文本表头 + 数值格数达阈值）必须出现在候选里；
# 2. 表头文字带进候选（用户能看到列名再裁决单位）；
# 3. 纯文本列 / 数值格不足阈值的列不产候选（不把什么都当金额列）；
# 4. stable_id 同结构重跑稳定（幂等）；
# 5. 反向：无任何数值的 workbook 候选为空（分母非空对照）。
# ---------------------------------------------------------------------------


def _money_sheet_bytes() -> bytes:
    """一张典型金额表：A 列科目名（文本），B 列金额（数值），首行表头。"""
    cells: list[tuple[str, object]] = [
        ("A1", "科目名称"), ("B1", "期末余额"),
        ("A2", "货币资金"), ("B2", 1234.5),
        ("A3", "应收账款"), ("B3", 2234.5),
        ("A4", "存货"), ("B4", 3234.5),
        ("A5", "固定资产"), ("B5", 4234.5),
        ("A6", "合计"), ("B6", "=SUM(B2:B5)"),
    ]
    return _xlsx_bytes(sheets={"余额表": cells})


def test_amount_region_candidates_found_for_money_column() -> None:
    result = run_semantic_preflight(_money_sheet_bytes(), filename_hint="money.xlsx")
    assert result.workbook is not None
    sheet = result.workbook.sheets[0]
    cand = sheet.amount_region_candidates
    assert cand, "金额表必须有 region 候选（分母非空）"
    letters = {c.column_letter for c in cand}
    assert "B" in letters, f"B 列（期末余额）应在候选里，实际 {sorted(letters)}"
    # A 列是纯文本科目名，不是金额列
    assert "A" not in letters


def test_amount_region_candidate_carries_header() -> None:
    result = run_semantic_preflight(_money_sheet_bytes(), filename_hint="money.xlsx")
    sheet = result.workbook.sheets[0]
    cand = {c.column_letter: c for c in sheet.amount_region_candidates}
    assert cand["B"].header == "期末余额"


def test_amount_region_stable_id_is_deterministic() -> None:
    """同结构重跑 preflight，stable_id 必须稳定（幂等）。"""
    r1 = run_semantic_preflight(_money_sheet_bytes(), filename_hint="m.xlsx")
    r2 = run_semantic_preflight(_money_sheet_bytes(), filename_hint="m.xlsx")
    s1 = [c.stable_id for c in r1.workbook.sheets[0].amount_region_candidates]
    s2 = [c.stable_id for c in r2.workbook.sheets[0].amount_region_candidates]
    assert s1 == s2
    assert s1, "候选非空（反向对照：两次都空也可能是推导恒失败）"


def test_amount_region_empty_for_text_only_sheet() -> None:
    """纯文本 sheet（无数值列）候选为空 —— 不把文本列当金额列。"""
    cells = [("A1", "名称"), ("A2", "备注一"), ("A3", "备注二")]
    result = run_semantic_preflight(_xlsx_bytes(sheets={"说明": cells}), filename_hint="t.xlsx")
    assert result.workbook is not None
    assert list(result.workbook.sheets[0].amount_region_candidates) == []


def test_amount_region_to_dict_shape() -> None:
    """to_dict 给 camelCase（前端直接消费），字段齐。"""
    result = run_semantic_preflight(_money_sheet_bytes(), filename_hint="m.xlsx")
    raw = result.workbook.sheets[0].to_dict()
    cands = raw["amountRegionCandidates"]
    assert cands, "to_dict 必须带候选（前端读的就是这个键）"
    for c in cands:
        assert {"stableId", "columnLetter", "header", "numericCells", "firstNumericRow"} <= set(c)
