"""逐 workbook/sheet 语义 preflight（Task 6）。

Spec: custom-workpaper-template-ingestion-and-sync-closure
Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7

## 与 package scanner 的边界

* Task 5 是包/安全门；本模块是语义门。
* 安全门 BLOCKER（损坏/加密/路径穿越/zip bomb）→ **不**打开 openpyxl，
  不进入语义扫描（Requirement 5.1）。
* 能力矩阵 BLOCKER（VBA/外链等）仍可做只读语义扫描，便于上传者看到结构；
  但 overall verdict 仍 BLOCKED，不得 finalize。
* 公式只作文本与依赖 token 收集，**不计算**（``data_only=False``）。
* ``keep_links=False``：不跟随外部链接目标（禁网）。

## 空报告永不 valid（Requirement 5.7）

``SemanticPreflightResult.valid`` 只能由 findings 派生；空 findings → BLOCKED。
"""
from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from app.services.custom_template_ingestion.package_scanner import (
    FINDING_CORRUPT,
    FINDING_ENCRYPTED,
    FINDING_PASSWORD,
    FINDING_TIMEOUT,
    PackageScanResult,
    SCANNER_BUILD_ID,
    scan_package_bytes,
)
from app.services.custom_template_ingestion.policy import (
    FINDING_EMPTY_REPORT,
    POLICY_V1,
    CustomTemplateIngestionPolicy,
    Finding,
    PreflightResult,
    Severity,
    Verdict,
    derive_verdict,
)

#: 九段 key（与 G-C0 GuidanceSectionKey 对齐，本模块只产 candidate，不 confirmed）。
GUIDANCE_SECTION_KEYS: tuple[str, ...] = (
    "purpose",
    "materials",
    "data_sources",
    "steps",
    "formulas",
    "judgments",
    "evidence",
    "common_errors",
    "completion",
)

FINDING_SEMANTIC_COMPLETE: str = "SEMANTIC.scan_complete"
FINDING_PACKAGE_GATE: str = "SEMANTIC.package_gate_blocked"
FINDING_OPEN_FAILED: str = "SEMANTIC.open_failed"
FINDING_SHEET_LIMIT: str = "SEMANTIC.sheet_count_exceeded"
FINDING_CELL_LIMIT: str = "SEMANTIC.non_empty_cells_exceeded"
FINDING_NO_SHEETS: str = "SEMANTIC.no_sheets"

#: 跨 sheet 引用粗匹配（``Sheet1!A1`` / ``'My Sheet'!A1``）。
_CROSS_SHEET_REF_RE = re.compile(
    r"(?:'([^']+)'|([A-Za-z_][\w.]*))!",
)

#: 安全门 finding code 前缀 / 精确码 —— 命中则禁止打开 workbook。
_SECURITY_GATE_CODES: frozenset[str] = frozenset({
    FINDING_CORRUPT,
    FINDING_ENCRYPTED,
    FINDING_PASSWORD,
    FINDING_TIMEOUT,
    FINDING_EMPTY_REPORT,
})


class ProjectionRecommendation(str, Enum):
    """Requirement 5.7：总体建议只能是这四个派生结论。"""

    EDITABLE_GRID = "editable_grid"
    READ_ONLY_HTML = "read_only_html"
    ONLYOFFICE_ONLY = "onlyoffice_only"
    BLOCKED = "BLOCKED"


class IdentityCarrierKind(str, Enum):
    DEFINED_NAME = "defined_name"
    HIDDEN_META_CELL = "hidden_meta_cell"
    CUSTOM_DOC_PROP = "custom_doc_prop"
    TABLE_COLUMN = "table_column"


@dataclass(frozen=True, slots=True)
class IdentityCarrier:
    kind: IdentityCarrierKind
    key: str
    locator: str
    instrumentable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "key": self.key,
            "locator": self.locator,
            "instrumentable": self.instrumentable,
        }


@dataclass(frozen=True, slots=True)
class GuidanceCandidateSection:
    key: str
    title: str
    content: str
    status: str  # always custom_candidate / review_pending 语义

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "content": self.content,
            "extractionSource": "custom_candidate",
            "completionStatus": "review_pending",
        }


@dataclass(frozen=True, slots=True)
class SheetReport:
    sheet_uid: str
    sheet_name: str
    order: int
    state: str  # visible / hidden / veryHidden
    used_range: str | None
    non_empty_cells: int
    freeze_panes: str | None
    protection: bool
    merge_count: int
    hidden_rows: int
    hidden_cols: int
    formula_count: int
    cross_sheet_formula_count: int
    table_count: int
    data_validation_count: int
    conditional_formatting_count: int
    comment_count: int
    identity_carriers: tuple[IdentityCarrier, ...]
    identity_risks: tuple[str, ...]
    guidance_candidates: tuple[GuidanceCandidateSection, ...]
    projection_recommendation: ProjectionRecommendation
    sample_formulas: tuple[str, ...]
    cell_type_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sheetUid": self.sheet_uid,
            "sheetName": self.sheet_name,
            "order": self.order,
            "state": self.state,
            "usedRange": self.used_range,
            "nonEmptyCells": self.non_empty_cells,
            "freezePanes": self.freeze_panes,
            "protection": self.protection,
            "mergeCount": self.merge_count,
            "hiddenRows": self.hidden_rows,
            "hiddenCols": self.hidden_cols,
            "formulaCount": self.formula_count,
            "crossSheetFormulaCount": self.cross_sheet_formula_count,
            "tableCount": self.table_count,
            "dataValidationCount": self.data_validation_count,
            "conditionalFormattingCount": self.conditional_formatting_count,
            "commentCount": self.comment_count,
            "identityCarriers": [c.to_dict() for c in self.identity_carriers],
            "identityRisks": list(self.identity_risks),
            "guidanceCandidates": [g.to_dict() for g in self.guidance_candidates],
            "projectionRecommendation": self.projection_recommendation.value,
            "sampleFormulas": list(self.sample_formulas),
            "cellTypeCounts": dict(self.cell_type_counts),
        }


@dataclass(frozen=True, slots=True)
class WorkbookReport:
    artifact_sha256: str
    policy_version: str
    scanner_build_id: str
    sheet_count: int
    defined_names: tuple[str, ...]
    cross_sheet_formulas: tuple[str, ...]
    preservation_inventory: tuple[str, ...]
    sheets: tuple[SheetReport, ...]
    relationships: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifactSha256": self.artifact_sha256,
            "policyVersion": self.policy_version,
            "scannerBuildId": self.scanner_build_id,
            "sheetCount": self.sheet_count,
            "definedNames": list(self.defined_names),
            "crossSheetFormulas": list(self.cross_sheet_formulas),
            "preservationInventory": list(self.preservation_inventory),
            "sheets": [s.to_dict() for s in self.sheets],
            "relationships": self.relationships,
        }


@dataclass(frozen=True, slots=True)
class SemanticPreflightResult:
    package: PackageScanResult
    workbook: WorkbookReport | None
    findings: tuple[Finding, ...]
    verdict: Verdict
    projection_recommendation: ProjectionRecommendation
    semantic_opened: bool

    @property
    def is_valid(self) -> bool:
        return self.verdict is Verdict.PREFLIGHT_READY

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.is_valid,
            "verdict": self.verdict.value,
            "projectionRecommendation": self.projection_recommendation.value,
            "semanticOpened": self.semantic_opened,
            "findings": [f.to_dict() for f in self.findings],
            "workbook": self.workbook.to_dict() if self.workbook else None,
            "package": self.package.to_dict(),
        }


def package_blocks_semantic_open(package: PackageScanResult) -> bool:
    """安全门 BLOCKER 是否禁止打开 workbook（Requirement 5.1）。"""
    for finding in package.preflight.findings:
        if finding.severity is not Severity.BLOCKER:
            continue
        if finding.code in _SECURITY_GATE_CODES:
            return True
        if finding.code.startswith("PACKAGE.path_"):
            return True
        if finding.code.startswith("POLICY.") and finding.code.endswith("_exceeded"):
            return True
        if finding.code.startswith("PACKAGE.xml_"):
            return True
    return False


def run_semantic_preflight(
    payload: bytes,
    *,
    package: PackageScanResult | None = None,
    policy: CustomTemplateIngestionPolicy = POLICY_V1,
    filename_hint: str | None = None,
) -> SemanticPreflightResult:
    """先包门、再语义。永不返回空 findings / valid=true 的空报告。"""
    pkg = package or scan_package_bytes(
        payload, policy=policy, filename_hint=filename_hint,
    )
    findings: list[Finding] = list(pkg.preflight.findings)
    artifact_sha = hashlib.sha256(payload).hexdigest()

    if package_blocks_semantic_open(pkg):
        findings.append(Finding(
            code=FINDING_PACKAGE_GATE,
            severity=Severity.BLOCKER,
            locator="package",
            policy_decision="安全门 BLOCKER，禁止进入语义扫描/可执行预览",
            remediation="先修复包级安全 finding 后重试",
        ))
        return _finish(
            pkg, None, findings, ProjectionRecommendation.BLOCKED, opened=False,
        )

    try:
        workbook_report, sheet_findings = _scan_workbook(
            payload, artifact_sha, pkg, policy,
        )
    except Exception as exc:  # noqa: BLE001 — 结构化失败，禁止空成功
        findings.append(Finding(
            code=FINDING_OPEN_FAILED,
            severity=Severity.BLOCKER,
            locator="workbook",
            policy_decision=f"openpyxl 打开失败: {type(exc).__name__}",
            remediation="文件可能损坏或超预算；不得返回空报告",
        ))
        return _finish(
            pkg, None, findings, ProjectionRecommendation.BLOCKED, opened=False,
        )

    findings.extend(sheet_findings)
    overall = _derive_projection(workbook_report, findings, pkg)
    return _finish(pkg, workbook_report, findings, overall, opened=True)


def _scan_workbook(
    payload: bytes,
    artifact_sha: str,
    package: PackageScanResult,
    policy: CustomTemplateIngestionPolicy,
) -> tuple[WorkbookReport, list[Finding]]:
    from openpyxl import load_workbook

    findings: list[Finding] = []
    bio = io.BytesIO(payload)
    # data_only=False：公式当文本；keep_links=False：不解析外链目标。
    wb = load_workbook(bio, read_only=False, data_only=False, keep_links=False)

    try:
        if len(wb.sheetnames) > policy.max_sheets:
            findings.append(Finding(
                code=FINDING_SHEET_LIMIT,
                severity=Severity.BLOCKER,
                locator="workbook.sheets",
                policy_decision=f"sheets={len(wb.sheetnames)} > {policy.max_sheets}",
                remediation="减少 sheet 数",
                observed=len(wb.sheetnames),
                limit=policy.max_sheets,
            ))

        defined_names = _collect_defined_names(wb)
        sheet_reports: list[SheetReport] = []
        all_cross: list[str] = []
        total_non_empty = 0

        for order, name in enumerate(wb.sheetnames):
            ws = wb[name]
            report, cross, non_empty = _scan_sheet(
                ws, order=order, defined_names=defined_names, policy=policy,
            )
            sheet_reports.append(report)
            all_cross.extend(cross)
            total_non_empty += non_empty

        if total_non_empty > policy.max_non_empty_cells:
            findings.append(Finding(
                code=FINDING_CELL_LIMIT,
                severity=Severity.BLOCKER,
                locator="workbook.cells",
                policy_decision=(
                    f"non_empty_cells={total_non_empty} > {policy.max_non_empty_cells}"
                ),
                remediation="缩小工作簿",
                observed=total_non_empty,
                limit=policy.max_non_empty_cells,
            ))

        if not sheet_reports:
            findings.append(Finding(
                code=FINDING_NO_SHEETS,
                severity=Severity.BLOCKER,
                locator="workbook.sheets",
                policy_decision="工作簿无 sheet",
                remediation="至少包含一个 worksheet",
            ))

        # 重复 defined name / 空 name 风险
        name_keys = [n.split("!")[-1] if "!" in n else n for n in defined_names]
        seen: set[str] = set()
        for key in name_keys:
            folded = key.casefold()
            if folded in seen:
                findings.append(Finding(
                    code="SEMANTIC.defined_name_duplicate",
                    severity=Severity.WARNING,
                    locator=key,
                    policy_decision="defined name 重复（casefold）",
                    remediation="合并或重命名，避免 identity drift",
                ))
            seen.add(folded)

        report = WorkbookReport(
            artifact_sha256=artifact_sha,
            policy_version=policy.version,
            scanner_build_id=SCANNER_BUILD_ID,
            sheet_count=len(sheet_reports),
            defined_names=tuple(defined_names),
            cross_sheet_formulas=tuple(dict.fromkeys(all_cross)),
            preservation_inventory=tuple(package.preflight.preservation_inventory),
            sheets=tuple(sheet_reports),
            relationships=package.relationships,
        )
        return report, findings
    finally:
        wb.close()


def _collect_defined_names(wb: Any) -> list[str]:
    names: list[str] = []
    try:
        dns = wb.defined_names
    except Exception:  # noqa: BLE001
        return names
    # openpyxl 3.x：DefinedNameDict 可迭代
    try:
        for dn in dns.values():
            attr_name = getattr(dn, "name", None) or str(dn)
            names.append(str(attr_name))
    except Exception:  # noqa: BLE001
        try:
            for key in dns:
                names.append(str(key))
        except Exception:  # noqa: BLE001
            return names
    return sorted(set(names))


def _scan_sheet(
    ws: Any,
    *,
    order: int,
    defined_names: list[str],
    policy: CustomTemplateIngestionPolicy,
) -> tuple[SheetReport, list[str], int]:
    del policy  # 单元格上限在 workbook 级核算
    sheet_name = str(ws.title)
    sheet_uid = f"sheet:{order}:{_stable_sheet_token(sheet_name)}"
    state = _sheet_state(ws)

    non_empty = 0
    formula_count = 0
    cross_count = 0
    cross_samples: list[str] = []
    sample_formulas: list[str] = []
    type_counts: dict[str, int] = {
        "n": 0, "s": 0, "b": 0, "f": 0, "e": 0, "inlineStr": 0, "other": 0,
    }
    hidden_rows = 0
    hidden_cols = 0
    comment_count = 0

    # 声明范围（稀疏炸弹信号）
    dim = getattr(ws, "dimensions", None) or getattr(ws, "calculate_dimension", lambda: None)()
    used_range = str(dim) if dim else None

    max_row = ws.max_row or 0
    max_col = ws.max_column or 0
    # 有界扫描：避免对空声明范围全表爆炸；仍计数非空。
    for row in ws.iter_rows(min_row=1, max_row=max_row, max_col=max_col):
        for cell in row:
            value = cell.value
            if value is None:
                continue
            non_empty += 1
            if isinstance(value, str) and value.startswith("="):
                formula_count += 1
                type_counts["f"] += 1
                if len(sample_formulas) < 20:
                    sample_formulas.append(value[:200])
                if _CROSS_SHEET_REF_RE.search(value):
                    cross_count += 1
                    if len(cross_samples) < 50:
                        cross_samples.append(f"{sheet_name}!{cell.coordinate}:{value[:120]}")
            elif isinstance(value, bool):
                type_counts["b"] += 1
            elif isinstance(value, (int, float)):
                type_counts["n"] += 1
            elif isinstance(value, str):
                type_counts["s"] += 1
            else:
                type_counts["other"] += 1

    for idx in range(1, max_row + 1):
        if ws.row_dimensions[idx].hidden:
            hidden_rows += 1
    for idx in range(1, max_col + 1):
        letter = ws.cell(row=1, column=idx).column_letter
        if ws.column_dimensions[letter].hidden:
            hidden_cols += 1

    merge_count = len(getattr(ws, "merged_cells", {}).ranges) if hasattr(ws, "merged_cells") else 0
    try:
        merge_count = len(list(ws.merged_cells.ranges))
    except Exception:  # noqa: BLE001
        pass

    freeze = None
    fp = getattr(ws, "freeze_panes", None)
    if fp:
        freeze = str(fp)

    protection = False
    try:
        protection = bool(ws.protection.sheet)
    except Exception:  # noqa: BLE001
        protection = False

    table_count = 0
    try:
        table_count = len(ws.tables)
    except Exception:  # noqa: BLE001
        table_count = 0

    dv_count = 0
    try:
        dv_count = len(ws.data_validations.dataValidation)
    except Exception:  # noqa: BLE001
        dv_count = 0

    cf_count = 0
    try:
        cf_count = len(ws.conditional_formatting._cf_rules)  # noqa: SLF001
    except Exception:  # noqa: BLE001
        try:
            cf_count = len(list(ws.conditional_formatting))
        except Exception:  # noqa: BLE001
            cf_count = 0

    try:
        comments = getattr(ws, "_comments", None)
        if comments is not None:
            comment_count = len(comments)
    except Exception:  # noqa: BLE001
        comment_count = 0

    carriers, risks = _identity_for_sheet(
        sheet_name=sheet_name,
        sheet_uid=sheet_uid,
        defined_names=defined_names,
        table_count=table_count,
        non_empty=non_empty,
    )
    guidance = _guidance_candidates(sheet_name, formula_count, carriers)
    projection = _sheet_projection(
        carriers=carriers,
        risks=risks,
        formula_count=formula_count,
        table_count=table_count,
        non_empty=non_empty,
        state=state,
    )

    report = SheetReport(
        sheet_uid=sheet_uid,
        sheet_name=sheet_name,
        order=order,
        state=state,
        used_range=used_range,
        non_empty_cells=non_empty,
        freeze_panes=freeze,
        protection=protection,
        merge_count=merge_count,
        hidden_rows=hidden_rows,
        hidden_cols=hidden_cols,
        formula_count=formula_count,
        cross_sheet_formula_count=cross_count,
        table_count=table_count,
        data_validation_count=dv_count,
        conditional_formatting_count=cf_count,
        comment_count=comment_count,
        identity_carriers=tuple(carriers),
        identity_risks=tuple(risks),
        guidance_candidates=tuple(guidance),
        projection_recommendation=projection,
        sample_formulas=tuple(sample_formulas),
        cell_type_counts=type_counts,
    )
    return report, cross_samples, non_empty


def _stable_sheet_token(name: str) -> str:
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]
    return digest


def _sheet_state(ws: Any) -> str:
    try:
        state = ws.sheet_state
        return str(state)
    except Exception:  # noqa: BLE001
        return "visible"


def _identity_for_sheet(
    *,
    sheet_name: str,
    sheet_uid: str,
    defined_names: list[str],
    table_count: int,
    non_empty: int,
) -> tuple[list[IdentityCarrier], list[str]]:
    carriers: list[IdentityCarrier] = []
    risks: list[str] = []
    for dn in defined_names:
        # 本地名 ``Sheet!Name`` 或全局
        local = dn
        scoped = False
        if "!" in dn:
            scope, local = dn.split("!", 1)
            scoped = scope.casefold() == sheet_name.casefold()
        if scoped or "!" not in dn:
            carriers.append(IdentityCarrier(
                kind=IdentityCarrierKind.DEFINED_NAME,
                key=local,
                locator=f"{sheet_uid}/definedName/{local}",
                instrumentable=False,
            ))
    if table_count:
        carriers.append(IdentityCarrier(
            kind=IdentityCarrierKind.TABLE_COLUMN,
            key=f"tables:{table_count}",
            locator=f"{sheet_uid}/tables",
            instrumentable=True,
        ))
    if not carriers and non_empty > 0:
        risks.append("no_existing_stable_carrier")
        risks.append("editable_grid_requires_instrumentation")
    if non_empty == 0:
        risks.append("empty_sheet")
    return carriers, risks


def _guidance_candidates(
    sheet_name: str,
    formula_count: int,
    carriers: list[IdentityCarrier],
) -> list[GuidanceCandidateSection]:
    """九段 extraction candidate；状态恒为 custom_candidate/review_pending。"""
    titles = {
        "purpose": "编制目的",
        "materials": "所需资料",
        "data_sources": "数据来源",
        "steps": "编制步骤",
        "formulas": "公式与勾稽",
        "judgments": "职业判断",
        "evidence": "审计证据",
        "common_errors": "常见错误",
        "completion": "完成标准",
    }
    stubs = {
        "purpose": f"候选：说明「{sheet_name}」在项目中的编制目的（待审核）。",
        "materials": "候选：列出完成本表所需资料（待审核）。",
        "data_sources": "候选：列出来源底稿/系统（待审核）。",
        "steps": "候选：逐步编制说明（待审核）。",
        "formulas": (
            f"候选：本表观测到 {formula_count} 条公式；"
            f"稳定载体 {len(carriers)} 个（待审核，不得自动 confirmed）。"
        ),
        "judgments": "候选：需职业判断的事项（待审核）。",
        "evidence": "候选：应归档的证据类型（待审核）。",
        "common_errors": "候选：常见错漏（待审核）。",
        "completion": "候选：完成/复核标准（待审核）。",
    }
    return [
        GuidanceCandidateSection(
            key=key,
            title=titles[key],
            content=stubs[key],
            status="review_pending",
        )
        for key in GUIDANCE_SECTION_KEYS
    ]


def _sheet_projection(
    *,
    carriers: list[IdentityCarrier],
    risks: list[str],
    formula_count: int,
    table_count: int,
    non_empty: int,
    state: str,
) -> ProjectionRecommendation:
    if non_empty == 0 or state == "veryHidden":
        return ProjectionRecommendation.ONLYOFFICE_ONLY
    if "no_existing_stable_carrier" in risks:
        # 无载体不可选 editable_grid（Requirement 8.3）；可降 read_only_html
        if formula_count > 200 or table_count > 10:
            return ProjectionRecommendation.ONLYOFFICE_ONLY
        return ProjectionRecommendation.READ_ONLY_HTML  # no-carrier degrade
    if carriers:
        return ProjectionRecommendation.EDITABLE_GRID
    return ProjectionRecommendation.READ_ONLY_HTML


def _derive_projection(
    workbook: WorkbookReport,
    findings: list[Finding],
    package: PackageScanResult,
) -> ProjectionRecommendation:
    if any(f.severity is Severity.BLOCKER for f in findings):
        return ProjectionRecommendation.BLOCKED
    if package.finalize_blocked:
        return ProjectionRecommendation.BLOCKED
    if not workbook.sheets:
        return ProjectionRecommendation.BLOCKED
    recs = {s.projection_recommendation for s in workbook.sheets}
    if ProjectionRecommendation.BLOCKED in recs:
        return ProjectionRecommendation.BLOCKED
    if recs == {ProjectionRecommendation.EDITABLE_GRID}:
        return ProjectionRecommendation.EDITABLE_GRID
    if ProjectionRecommendation.EDITABLE_GRID in recs:
        # 混合：保守降为 read_only_html（个别 sheet 仍可在 mapping 阶段分别选）
        return ProjectionRecommendation.READ_ONLY_HTML
    if ProjectionRecommendation.READ_ONLY_HTML in recs:
        return ProjectionRecommendation.READ_ONLY_HTML
    return ProjectionRecommendation.ONLYOFFICE_ONLY


def _finish(
    package: PackageScanResult,
    workbook: WorkbookReport | None,
    findings: list[Finding],
    projection: ProjectionRecommendation,
    *,
    opened: bool,
) -> SemanticPreflightResult:
    if not findings:
        findings.append(Finding(
            code=FINDING_EMPTY_REPORT,
            severity=Severity.BLOCKER,
            locator="semantic",
            policy_decision="semantic preflight 未产生任何 finding",
            remediation="禁止返回空报告（Requirement 5.7）",
        ))
        projection = ProjectionRecommendation.BLOCKED
    elif not any(f.severity is Severity.BLOCKER for f in findings):
        findings.append(Finding(
            code=FINDING_SEMANTIC_COMPLETE,
            severity=Severity.INFO,
            locator="semantic",
            policy_decision="语义 preflight 完成且无 BLOCKER",
            remediation="无需处理",
        ))

    verdict = derive_verdict(tuple(findings))
    if verdict is not Verdict.PREFLIGHT_READY:
        projection = ProjectionRecommendation.BLOCKED

    return SemanticPreflightResult(
        package=package,
        workbook=workbook,
        findings=tuple(findings),
        verdict=verdict,
        projection_recommendation=projection,
        semantic_opened=opened,
    )
