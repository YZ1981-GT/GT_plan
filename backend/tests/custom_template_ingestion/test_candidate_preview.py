"""Task 9 守卫：immutable candidate 静态预览 + candidate guidance。

Feature: custom-workpaper-template-ingestion-and-sync-closure
Validates: Requirements 6.2, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6

判据一律行为/结构级：
  * sanitizer 用真实危险载荷验证转义 + 无可执行 sink（不是「函数存在」）；
  * no-OO-config 用 AST 扫描本模块 + 允许 kind 集合封闭（结构性保证）；
  * digest 变化 / candidate 非可预览态 → token stale（行为断言）；
  * guidance 预览 by-reference 消费 G-C0 candidate handoff，拒绝 finalized/confirmed。
"""
from __future__ import annotations

import ast
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.guidance_gid import StableSheetIdentity

from app.services.custom_template_ingestion.identity import (
    IdentityCarrierKind,
    StableFieldIdentity,
)
from app.services.custom_template_ingestion.lifecycles import (
    FakeClock,
    MappingDraft,
    freeze_candidate,
)
from app.services.custom_template_ingestion.mapping import (
    CustomProjectionManifest,
    FieldMapping,
    PreservationDecision,
    ProjectionMode,
    RegionKind,
    RegionMapping,
)
from app.services.custom_template_ingestion import candidate_preview as cp
from app.services.custom_template_ingestion.candidate_preview import (
    ALLOWED_PREVIEW_SURFACE_KINDS,
    FORBIDDEN_PRODUCTION_SINKS,
    CandidatePreviewService,
    PreviewError,
    PreviewSurfaceKind,
    SheetPreviewInput,
    sanitize_cell_text,
)
from app.services.custom_template_ingestion import candidate_guidance as cg
from app.services.custom_template_ingestion.candidate_guidance import (
    CandidateGuidanceError,
    build_candidate_guidance_preview,
)


FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "data" / "guidance" / "contracts" / "gc0" / "fixtures"
)
MODULE_PATH = Path(cp.__file__)


# ─────────────────────────────────────────────────────────────────────────────
# fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _clock() -> FakeClock:
    return FakeClock(datetime(2026, 9, 8, tzinfo=timezone.utc))


def _sheet_identity() -> StableSheetIdentity:
    return StableSheetIdentity(
        template_lineage_id="lin-1",
        template_version_id="ver-1",
        wp_code="D5",
        sheet_uid="sheet:0:abc",
        sheet_code="D5",
    )


def _manifest(mode: ProjectionMode = ProjectionMode.EDITABLE_GRID) -> CustomProjectionManifest:
    ident = StableFieldIdentity(
        sheet=_sheet_identity(),
        carrier_kind=IdentityCarrierKind.DEFINED_NAME,
        carrier_key="amount_row",
        locator="sheet/definedName/amount_row",
        instrumented=False,
    )
    managed = mode is ProjectionMode.EDITABLE_GRID
    fields = (
        FieldMapping(
            field_id="f1",
            identity=ident,
            region_id="r1",
            managed=managed,
            value_type="number",
        ),
    ) if mode is not ProjectionMode.ONLYOFFICE_ONLY else ()
    return CustomProjectionManifest(
        manifest_version="man-v1",
        workbook_lineage_id="lin-1",
        sheet_uid="sheet:0:abc",
        projection_mode=mode,
        regions=(RegionMapping(
            region_id="r1", kind=RegionKind.DATA, a1_range="A1:B2",
            read_only=not managed, dynamic=False,
        ),) if mode is not ProjectionMode.ONLYOFFICE_ONLY else (),
        fields=fields,
        row_identity=None,
        column_identity=None,
        formula_boundary_version="fb-1",
        preservation_decisions=(
            PreservationDecision(feature="external_link", decision="block"),
        ),
        adapter_id="ad-1" if managed else None,
        adapter_version="1.0" if managed else None,
    )


def _candidate(clock: FakeClock, *, guidance_digest: str = "g" * 8):
    draft = MappingDraft(
        draft_id="draft-1",
        organization_id="org-1",
        artifact_id="up-1",
        revision=1,
        mapping={"sheets": ["s1"]},
        guidance_revision="g-1",
        updated_at=clock.now(),
    )
    return freeze_candidate(
        draft,
        artifact_sha256="a" * 64,
        policy_digest="p" * 16,
        scanner_digest="s" * 16,
        guidance_digest=guidance_digest,
        adapter_digest="d" * 16,
        clock=clock,
    )


def _candidate_handoff() -> dict:
    return json.loads((FIXTURES / "handoff_candidate.json").read_text(encoding="utf-8"))


def _finalized_handoff() -> dict:
    return json.loads((FIXTURES / "handoff_finalized.json").read_text(encoding="utf-8"))


def _sheet_input(mode: ProjectionMode = ProjectionMode.EDITABLE_GRID) -> SheetPreviewInput:
    return SheetPreviewInput(
        sheet_uid="sheet:0:abc",
        manifest=_manifest(mode),
        cell_texts=("hello", "=SUM(A1:A2)"),
        formulas=("=cmd|'/c calc'!A1", "=DDE(server,topic,item)"),
        comments=("<script>alert(1)</script>",),
        defined_names=("amount_row",),
        properties={"author": "<b>evil</b>", "title": "T&Co"},
        structure={"rows": 2, "note": "<i>x</i>"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 9.2 — sanitizer with REAL dangerous payloads
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("payload", [
    "=cmd|'/c calc'!A1",
    "=DDE(server,topic,item)",
    "<script>alert(1)</script>",
    "@SUM(1)",
    "+1+1",
    "-2-2",
    "javascript:alert(1)",
    "http://evil.example/x?a=<b>",
])
def test_sanitizer_escapes_and_never_yields_executable_sink(payload: str) -> None:
    """公式/DDE/script/外链一律转义成文本，输出无未转义可执行 sink。"""
    out = sanitize_cell_text(payload)
    # 无未转义标签 —— 去掉转义实体后不得残留裸 < >。
    stripped = out.replace("&lt;", "").replace("&gt;", "").replace("&amp;", "")
    assert "<" not in stripped
    assert ">" not in stripped
    # script 标签必须被转义
    assert "<script" not in out.lower()
    # 单引号被转义（避免属性逃逸）
    if "'" in payload:
        assert "'" not in out


def test_static_html_surface_contains_no_executable_markup() -> None:
    svc = CandidatePreviewService(clock=_clock())
    clock = _clock()
    cand = _candidate(clock)
    preview = svc.build_preview(
        candidate=cand,
        sheets=[_sheet_input()],
        guidance_handoff=_candidate_handoff(),
    )
    html_surfaces = [
        s for sh in preview.sheets for s in sh.surfaces
        if s.kind is PreviewSurfaceKind.STATIC_HTML
    ]
    assert html_surfaces
    for s in html_surfaces:
        low = s.content.lower()
        assert "<script" not in low
        assert "<iframe" not in low
        assert "javascript:" not in low
        # DDE/formula payloads present only as escaped text, never raw.
        assert "&lt;script&gt;" in low  # the comment payload got escaped


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 9.1 — static only; NO production OO/WOPI config (structural)
# ─────────────────────────────────────────────────────────────────────────────


def test_preview_surface_kinds_are_closed_to_static_only() -> None:
    """允许的预览面 kind 集合封闭为三种静态形态；无 OO/WOPI/iframe 成员。"""
    assert ALLOWED_PREVIEW_SURFACE_KINDS == {
        "static_html", "nonexecutable_image", "structure_json",
    }
    kinds = {k.value for k in PreviewSurfaceKind}
    assert kinds == ALLOWED_PREVIEW_SURFACE_KINDS
    forbidden = {"onlyoffice_config", "wopi_url", "editable_iframe", "document_key"}
    assert not (kinds & forbidden)


def test_module_source_has_no_production_oo_wopi_sink() -> None:
    """结构性保证：本模块源码不含任何生产 OO/WOPI/可执行 sink 字面量。

    读磁盘真实源码（去注释/docstring 后），扫描 FORBIDDEN_PRODUCTION_SINKS。
    出现任意一条即说明本模块能产出生产 config —— RED。
    """
    src = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    # 去掉 docstring：只看真实运行代码字符串常量 + 标识符。
    code_strings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            code_strings.append(node.value.lower())
        if isinstance(node, ast.Name):
            code_strings.append(node.id.lower())
        if isinstance(node, ast.Attribute):
            code_strings.append(node.attr.lower())
    # docstring 节点单独排除（module/func/class 的首个表达式常量）。
    doc_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                doc_nodes.add(doc.lower())
    scan = [c for c in code_strings if c not in doc_nodes]
    blob = "\n".join(scan)
    # FORBIDDEN_PRODUCTION_SINKS 本身是黑名单常量的一部分（tuple 元素），
    # 会作为 Constant 出现；排除掉「定义黑名单」这个合法用途：黑名单元素本身
    # 出现次数应恰为 1（即定义处）。任何 >1 说明有真实使用点。
    for sink in FORBIDDEN_PRODUCTION_SINKS:
        occurrences = blob.count(sink)
        assert occurrences <= 1, (
            f"生产 sink {sink!r} 在本模块出现 {occurrences} 次（>1 = 有真实使用点）"
        )


def test_module_defines_no_config_emitting_function() -> None:
    """本模块无任何函数名暗示产出 OO/WOPI/editor config。"""
    src = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    banned = re.compile(r"(wopi|onlyoffice|editor_config|document_key|iframe)", re.I)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert not banned.search(node.name), (
                f"函数 {node.name!r} 名称暗示产出生产 config"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 9.3 — mapping preview shows managed/unmanaged/mode/identity/risk
# ─────────────────────────────────────────────────────────────────────────────


def test_mapping_preview_separates_managed_editable_mode_identity_risk() -> None:
    svc = CandidatePreviewService(clock=_clock())
    cand = _candidate(_clock())
    preview = svc.build_preview(
        candidate=cand,
        sheets=[_sheet_input(ProjectionMode.EDITABLE_GRID)],
        guidance_handoff=_candidate_handoff(),
    )
    m = preview.sheets[0].mapping
    assert m.projection_mode == "editable_grid"
    assert m.editable is True
    assert "f1" in m.managed_field_ids
    assert m.stable_identities  # 有稳定身份
    assert any("external_link" in r for r in m.preservation_risks)


def test_read_only_mapping_preview_is_not_editable() -> None:
    svc = CandidatePreviewService(clock=_clock())
    cand = _candidate(_clock())
    preview = svc.build_preview(
        candidate=cand,
        sheets=[_sheet_input(ProjectionMode.READ_ONLY_HTML)],
        guidance_handoff=_candidate_handoff(),
    )
    m = preview.sheets[0].mapping
    assert m.editable is False
    assert not m.managed_field_ids


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 9.4 — guidance uses G-C0 candidate handoff; no finalized/confirmed
# ─────────────────────────────────────────────────────────────────────────────


def test_guidance_preview_accepts_candidate_handoff() -> None:
    out = build_candidate_guidance_preview(_candidate_handoff())
    assert out["phase"] == "candidate"
    assert out["confirmed"] is False
    assert out["completionStatus"] == "review_pending"
    assert len(out["sections"]) == 9
    # 每段都不 confirmed
    assert all(s["completionStatus"] == "review_pending" for s in out["sections"])


def test_guidance_preview_rejects_finalized_handoff() -> None:
    with pytest.raises(CandidateGuidanceError):
        build_candidate_guidance_preview(_finalized_handoff())


def test_guidance_preview_rejects_finalized_phase_even_without_finalized_fields() -> None:
    """隔离 phase gate：把 candidate handoff 只改 top-level phase=finalized，
    不加任何 finalized-only 字段 —— 只有 phase gate 能拦。"""
    h = _candidate_handoff()
    h["phase"] = "finalized"
    with pytest.raises(CandidateGuidanceError):
        build_candidate_guidance_preview(h)


def test_guidance_preview_rejects_finalized_authority_phase_only() -> None:
    """隔离 authority phase gate：只把 authority.phase 改成 finalized，
    top-level phase 仍 candidate、无 finalized-only 字段 —— 只有 authority
    phase gate 能拦。"""
    h = _candidate_handoff()
    h["authority"]["phase"] = "finalized"
    with pytest.raises(CandidateGuidanceError):
        build_candidate_guidance_preview(h)


def test_guidance_preview_rejects_candidate_with_forged_finalization_field() -> None:
    h = _candidate_handoff()
    h["finalizationId"] = "fin-forged"
    with pytest.raises(CandidateGuidanceError):
        build_candidate_guidance_preview(h)


def test_guidance_preview_rejects_authority_forged_finalization_field() -> None:
    h = _candidate_handoff()
    h["authority"]["finalizationId"] = "fin-forged"
    with pytest.raises(CandidateGuidanceError):
        build_candidate_guidance_preview(h)


def test_guidance_preview_rejects_bad_contract_version() -> None:
    h = _candidate_handoff()
    h["contractVersion"] = "9.0"  # unknown major → BLOCKED
    with pytest.raises(CandidateGuidanceError):
        build_candidate_guidance_preview(h)


def test_guidance_preview_never_emits_custom_confirmed() -> None:
    """预览输出（含嵌套）不得出现 custom_confirmed / confirmed=True。"""
    out = build_candidate_guidance_preview(_candidate_handoff())
    blob = json.dumps(out).lower()
    assert "custom_confirmed" not in blob
    assert "\"confirmed\": true" not in blob
    assert "confirmedby" not in blob


def test_guidance_module_does_not_redefine_gc0_schema() -> None:
    """by-reference：本模块不本地定义任何 C0 top-level 类型/接口。"""
    from app.services.guidance_gc0_contract import GC0_TOP_LEVEL_TYPES
    src = Path(cg.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    defined = {
        n.name for n in ast.walk(tree)
        if isinstance(n, (ast.ClassDef, ast.FunctionDef))
    }
    for sym in GC0_TOP_LEVEL_TYPES:
        assert sym not in defined, f"本地重定义了 C0 类型 {sym!r}（by-reference 违规）"


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 9.5 — any digest change → preview/evidence stale; token invalid
# ─────────────────────────────────────────────────────────────────────────────


def test_token_valid_for_unchanged_candidate() -> None:
    clock = _clock()
    svc = CandidatePreviewService(clock=clock)
    cand = _candidate(clock)
    token = svc.issue_token(cand)
    assert not svc.is_preview_stale(
        token=token, candidate=cand, candidate_active_or_pending=True,
    )


def test_guidance_digest_change_makes_preview_stale() -> None:
    """candidate 的 guidance digest 变了 → 旧 token 对新 candidate stale。"""
    clock = _clock()
    svc = CandidatePreviewService(clock=clock)
    cand = _candidate(clock, guidance_digest="g" * 8)
    token = svc.issue_token(cand)
    # 用不同 guidance_digest 冻结出新的 candidate（同 candidate_id 场景由 fingerprint 捕获）
    cand2_clock = _clock()
    cand2 = _candidate(cand2_clock, guidance_digest="h" * 8)
    # 直接构造一个 candidate_id 相同但 digest 不同的对象来验证 fingerprint 门。
    import dataclasses
    cand_mut = dataclasses.replace(cand, guidance_digest="h" * 8)
    assert svc.is_preview_stale(
        token=token, candidate=cand_mut, candidate_active_or_pending=True,
    )


@pytest.mark.parametrize("field_name", [
    "artifact_sha256", "policy_digest", "scanner_digest",
    "mapping_digest", "adapter_digest",
])
def test_any_input_digest_change_makes_preview_stale(field_name: str) -> None:
    import dataclasses
    clock = _clock()
    svc = CandidatePreviewService(clock=clock)
    cand = _candidate(clock)
    token = svc.issue_token(cand)
    mutated = dataclasses.replace(cand, **{field_name: "z" * 16})
    assert svc.is_preview_stale(
        token=token, candidate=mutated, candidate_active_or_pending=True,
    ), f"{field_name} 变化应使预览 stale"


def test_expired_token_is_stale() -> None:
    clock = _clock()
    svc = CandidatePreviewService(clock=clock)
    cand = _candidate(clock)
    token = svc.issue_token(cand)
    clock.advance(cp.PREVIEW_TOKEN_TTL_SECONDS + 1)
    assert svc.is_preview_stale(
        token=token, candidate=cand, candidate_active_or_pending=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Requirement 9.6 — expired/rejected/superseded → token invalid AND discover=0
# ─────────────────────────────────────────────────────────────────────────────


def test_non_previewable_candidate_blocks_preview_generation() -> None:
    clock = _clock()
    svc = CandidatePreviewService(clock=clock)
    cand = _candidate(clock)
    with pytest.raises(PreviewError):
        svc.build_preview(
            candidate=cand,
            sheets=[_sheet_input()],
            guidance_handoff=_candidate_handoff(),
            candidate_active_or_pending=False,
        )


def test_token_invalid_when_candidate_not_active_or_pending() -> None:
    clock = _clock()
    svc = CandidatePreviewService(clock=clock)
    cand = _candidate(clock)
    token = svc.issue_token(cand)
    # rejected/superseded/expired → not active_or_pending → stale
    assert svc.is_preview_stale(
        token=token, candidate=cand, candidate_active_or_pending=False,
    )


def test_token_bound_to_specific_candidate_id() -> None:
    clock = _clock()
    svc = CandidatePreviewService(clock=clock)
    cand = _candidate(clock)
    other = _candidate(_clock())
    token = svc.issue_token(cand)
    # 换成别的 candidate（不同 id）→ stale
    assert svc.is_preview_stale(
        token=token, candidate=other, candidate_active_or_pending=True,
    )
