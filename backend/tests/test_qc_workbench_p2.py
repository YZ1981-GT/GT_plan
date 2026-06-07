"""
test_qc_workbench_p2.py — P2 质控闭环 + EQCR + 问题类型库 集成测试

验证：
1. P2-1: QC 工作台聚合、问题关联、状态流转、关闭依据
2. P2-2: EQCR 聚合、批注区分、checklist、签出
3. P2-3: 问题类型配置、归类、统计、导出
4. Facade 扩展: qc/eqcr 角色 section 隔离
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services.qc_workbench_service import (
    QCIssue,
    QCIssueCloseRequest,
    QCIssueCreate,
    QCIssueLink,
    QCIssueLinkType,
    QCIssueStatus,
    QCIssueTransition,
    QCWorkbenchService,
    can_transition,
    validate_close_requirements,
)
from app.services.eqcr_review_workbench import (
    AnnotationType,
    EQCR_CHECKLIST_TEMPLATE,
    EqcrReviewWorkbenchService,
)
from app.services.quality_issue_type_service import QualityIssueTypeService
from app.services.role_workbench_facade import (
    RoleWorkbenchFacade,
    ROLE_SECTION_REGISTRY,
)
from app.schemas.evidence_ref import EvidenceRef, EvidenceType


# ─── Mock DB ──────────────────────────────────────────────────────────────────

def _make_mock_db():
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
    mock_result.scalar.return_value = 0
    mock_result.one.return_value = MagicMock(total=0, completed=0)
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result
    db.get.return_value = None
    return db


# ═══════════════════════════════════════════════════════════════════════════════
# P2-1: 质控闭环工作台
# ═══════════════════════════════════════════════════════════════════════════════


class TestQCIssueStateMachine:
    """P2-1.3: 问题状态流转 identified → assigned → responded → verified → closed"""

    def test_valid_transitions(self):
        """所有合法流转路径。"""
        assert can_transition(QCIssueStatus.identified, QCIssueStatus.assigned)
        assert can_transition(QCIssueStatus.assigned, QCIssueStatus.responded)
        assert can_transition(QCIssueStatus.responded, QCIssueStatus.verified)
        assert can_transition(QCIssueStatus.verified, QCIssueStatus.closed)

    def test_invalid_transitions(self):
        """禁止跳跃流转。"""
        assert not can_transition(QCIssueStatus.identified, QCIssueStatus.closed)
        assert not can_transition(QCIssueStatus.identified, QCIssueStatus.verified)
        assert not can_transition(QCIssueStatus.assigned, QCIssueStatus.closed)
        assert not can_transition(QCIssueStatus.responded, QCIssueStatus.closed)

    def test_closed_is_terminal(self):
        """closed 是终态，不可再流转。"""
        for target in QCIssueStatus:
            assert not can_transition(QCIssueStatus.closed, target)

    def test_rollback_transitions(self):
        """允许退回：assigned→identified, responded→assigned, verified→assigned"""
        assert can_transition(QCIssueStatus.assigned, QCIssueStatus.identified)
        assert can_transition(QCIssueStatus.responded, QCIssueStatus.assigned)
        assert can_transition(QCIssueStatus.verified, QCIssueStatus.assigned)

    def test_full_happy_path(self):
        """完整正向流转路径。"""
        db = _make_mock_db()
        svc = QCWorkbenchService(db)

        issue = QCIssue(project_id="proj-1", title="测试问题")
        assert issue.status == QCIssueStatus.identified

        # identified → assigned
        ok, err = svc.transition_issue(issue, QCIssueTransition(
            target_status=QCIssueStatus.assigned, assignee_id="user-1"
        ))
        assert ok
        assert issue.status == QCIssueStatus.assigned
        assert issue.assignee_id == "user-1"

        # assigned → responded
        ok, err = svc.transition_issue(issue, QCIssueTransition(
            target_status=QCIssueStatus.responded
        ))
        assert ok
        assert issue.status == QCIssueStatus.responded

        # responded → verified
        ok, err = svc.transition_issue(issue, QCIssueTransition(
            target_status=QCIssueStatus.verified
        ))
        assert ok
        assert issue.status == QCIssueStatus.verified

        # verified → closed (需要依据)
        ok, err = svc.transition_issue(issue, QCIssueTransition(
            target_status=QCIssueStatus.closed,
            justification="问题已修正，附件已补充",
        ))
        assert ok
        assert issue.status == QCIssueStatus.closed
        assert issue.closed_at is not None


class TestQCIssueCloseRequirement:
    """P2-1.4: 关闭问题必须填写依据或 EvidenceRef (Property 4)"""

    def test_close_without_evidence_fails(self):
        """无依据关闭 → 验证失败。"""
        issue = QCIssue(project_id="p1", title="t1")
        valid, err = validate_close_requirements(issue)
        assert not valid
        assert "evidence_ref" in err or "justification" in err

    def test_close_with_justification_passes(self):
        """有文字依据 → 通过。"""
        issue = QCIssue(project_id="p1", title="t1")
        valid, err = validate_close_requirements(issue, justification="已修复")
        assert valid

    def test_close_with_evidence_ref_passes(self):
        """有 EvidenceRef → 通过。"""
        ref = EvidenceRef(
            evidence_type=EvidenceType.attachment,
            evidence_id="att-123",
            project_id="p1",
        )
        issue = QCIssue(project_id="p1", title="t1")
        valid, err = validate_close_requirements(issue, evidence_ref=ref)
        assert valid

    def test_close_request_schema_validation(self):
        """Pydantic schema 级别验证：两者都缺则报错。"""
        with pytest.raises(ValueError, match="evidence_ref.*justification|justification.*evidence_ref"):
            QCIssueCloseRequest()

    def test_close_request_with_justification(self):
        """schema 带 justification → 合法。"""
        req = QCIssueCloseRequest(justification="已修复并附证据")
        assert req.justification == "已修复并附证据"

    def test_close_only_from_verified(self):
        """只有 verified 状态可以调用 close_issue。"""
        db = _make_mock_db()
        svc = QCWorkbenchService(db)
        issue = QCIssue(project_id="p1", title="t1", status=QCIssueStatus.assigned)
        close_req = QCIssueCloseRequest(justification="fixed")

        ok, err = svc.close_issue(issue, close_req)
        assert not ok
        assert "verified" in err

    def test_close_from_verified_with_evidence(self):
        """verified 状态 + 有依据 → 成功关闭。"""
        db = _make_mock_db()
        svc = QCWorkbenchService(db)
        issue = QCIssue(project_id="p1", title="t1", status=QCIssueStatus.verified)
        ref = EvidenceRef(
            evidence_type=EvidenceType.workpaper_cell,
            evidence_id="cell-001",
            project_id="p1",
        )
        close_req = QCIssueCloseRequest(evidence_ref=ref)

        ok, err = svc.close_issue(issue, close_req)
        assert ok
        assert issue.status == QCIssueStatus.closed
        assert issue.evidence_ref is not None


class TestQCIssueLinks:
    """P2-1.2: QC 问题关联底稿、单元格、附件、复核记录"""

    def test_build_links_workpaper(self):
        db = _make_mock_db()
        svc = QCWorkbenchService(db)
        links = svc.build_issue_links("proj-1", workpaper_id="wp-123")
        assert len(links) == 1
        assert links[0]["link_type"] == "workpaper"
        assert "/workpapers/wp-123/edit" in links[0]["route"]

    def test_build_links_all_types(self):
        db = _make_mock_db()
        svc = QCWorkbenchService(db)
        links = svc.build_issue_links(
            "proj-1",
            workpaper_id="wp-1",
            cell_ref="B5",
            attachment_id="att-1",
            review_record_id="rr-1",
        )
        assert len(links) == 4
        types = {l["link_type"] for l in links}
        assert types == {"workpaper", "cell", "attachment", "review_record"}

    def test_create_issue_with_links(self):
        db = _make_mock_db()
        svc = QCWorkbenchService(db)
        req = QCIssueCreate(
            project_id="p1",
            title="金额不一致",
            links=[
                QCIssueLink(link_type=QCIssueLinkType.workpaper, target_id="wp-1"),
                QCIssueLink(link_type=QCIssueLinkType.cell, target_id="C3"),
            ],
        )
        issue = svc.create_issue(req, creator_id="user-1")
        assert len(issue.links) == 2
        assert issue.creator_id == "user-1"


# ═══════════════════════════════════════════════════════════════════════════════
# P2-2: EQCR 独立复核工作台
# ═══════════════════════════════════════════════════════════════════════════════


class TestEqcrDimensions:
    """P2-2.1: 聚合 KAM、重大估计、持续经营、关联方、集团范围、重大调整"""

    def test_default_dimensions_has_6_items(self):
        db = _make_mock_db()
        svc = EqcrReviewWorkbenchService(db)
        dims = svc._default_dimensions()
        assert len(dims) == 6
        ids = {d["id"] for d in dims}
        assert ids == {"kam", "estimate", "going_concern", "related_party", "group_scope", "material_adjustment"}

    def test_all_dimensions_have_route_suffix(self):
        db = _make_mock_db()
        svc = EqcrReviewWorkbenchService(db)
        for dim in svc._default_dimensions():
            assert dim["route_suffix"].startswith("/eqcr/")


class TestEqcrAnnotationTypes:
    """P2-2.2: 区分普通复核与 EQCR 批注"""

    def test_classify_eqcr_annotation(self):
        db = _make_mock_db()
        svc = EqcrReviewWorkbenchService(db)
        assert svc.classify_annotation(AnnotationType.EQCR_INDEPENDENT) == "eqcr"
        assert svc.classify_annotation(AnnotationType.NORMAL_REVIEW) == "normal"

    def test_create_eqcr_annotation_type(self):
        db = _make_mock_db()
        svc = EqcrReviewWorkbenchService(db)
        ann = svc.create_eqcr_annotation(
            project_id="p1",
            category="kam",
            content="KAM 识别恰当",
            author_id="eqcr-user-1",
        )
        assert ann.annotation_type == AnnotationType.EQCR_INDEPENDENT
        assert ann.category == "kam"
        assert ann.id is not None


class TestEqcrChecklist:
    """P2-2.3 / P2-2.4: EQCR checklist + 签出要求"""

    def test_checklist_template_not_empty(self):
        assert len(EQCR_CHECKLIST_TEMPLATE) > 0

    def test_checklist_has_all_categories(self):
        categories = {t["category"] for t in EQCR_CHECKLIST_TEMPLATE}
        expected = {"kam", "estimate", "going_concern", "related_party", "group_scope", "material_adjustment"}
        assert expected == categories

    def test_empty_checklist_cannot_sign_off(self):
        db = _make_mock_db()
        svc = EqcrReviewWorkbenchService(db)
        status = svc.get_checklist_status(uuid4(), completed_items=[])
        assert not svc.can_sign_off(status)

    def test_all_required_done_can_sign_off(self):
        db = _make_mock_db()
        svc = EqcrReviewWorkbenchService(db)
        required_ids = [t["id"] for t in EQCR_CHECKLIST_TEMPLATE if t.get("required", True)]
        status = svc.get_checklist_status(uuid4(), completed_items=required_ids)
        assert svc.can_sign_off(status)
        assert status["all_required_done"]

    def test_partial_completion_cannot_sign_off(self):
        db = _make_mock_db()
        svc = EqcrReviewWorkbenchService(db)
        # 只完成一半
        required_ids = [t["id"] for t in EQCR_CHECKLIST_TEMPLATE if t.get("required", True)]
        half = required_ids[:len(required_ids) // 2]
        status = svc.get_checklist_status(uuid4(), completed_items=half)
        assert not svc.can_sign_off(status)

    def test_attempt_sign_off_failure_message(self):
        db = _make_mock_db()
        svc = EqcrReviewWorkbenchService(db)
        status = svc.get_checklist_status(uuid4(), completed_items=[])
        ok, msg = svc.attempt_sign_off(status)
        assert not ok
        assert "未完成" in msg

    def test_attempt_sign_off_success(self):
        db = _make_mock_db()
        svc = EqcrReviewWorkbenchService(db)
        all_ids = [t["id"] for t in EQCR_CHECKLIST_TEMPLATE]
        status = svc.get_checklist_status(uuid4(), completed_items=all_ids)
        ok, msg = svc.attempt_sign_off(status)
        assert ok


# ═══════════════════════════════════════════════════════════════════════════════
# P2-3: 质量问题类型库
# ═══════════════════════════════════════════════════════════════════════════════


class TestQualityIssueTypeConfig:
    """P2-3.5: 问题类型配置"""

    def test_get_all_types_not_empty(self):
        svc = QualityIssueTypeService()
        types = svc.get_all_types()
        assert len(types) >= 8  # 至少 8 种类型

    def test_required_type_codes_exist(self):
        """验证设计文档要求的 4 种核心类型。"""
        svc = QualityIssueTypeService()
        codes = {t["code"] for t in svc.get_all_types()}
        assert "procedure_omission" in codes
        assert "insufficient_evidence" in codes
        assert "amount_inconsistency" in codes
        assert "inadequate_response" in codes

    def test_type_structure(self):
        svc = QualityIssueTypeService()
        for t in svc.get_all_types():
            assert "code" in t
            assert "name_zh" in t
            assert "category" in t
            assert "severity_default" in t
            assert "description" in t

    def test_get_type_by_code(self):
        svc = QualityIssueTypeService()
        t = svc.get_type_by_code("procedure_omission")
        assert t is not None
        assert t["name_zh"] == "程序遗漏"

    def test_get_type_by_invalid_code(self):
        svc = QualityIssueTypeService()
        assert svc.get_type_by_code("nonexistent_code") is None


class TestQualityIssueClassification:
    """P2-3.6: 复核/QC 问题支持归类"""

    def test_classify_valid_code(self):
        svc = QualityIssueTypeService()
        result = svc.classify_issue("insufficient_evidence")
        assert result is not None
        assert result["code"] == "insufficient_evidence"
        assert result["name_zh"] == "证据不足"

    def test_classify_invalid_code_returns_none(self):
        svc = QualityIssueTypeService()
        assert svc.classify_issue("invalid") is None

    def test_validate_type_code(self):
        svc = QualityIssueTypeService()
        assert svc.validate_type_code("amount_inconsistency")
        assert not svc.validate_type_code("fake_code")


class TestRepeatedIssueStats:
    """P2-3.7: 统计重复问题"""

    def test_count_by_type(self):
        svc = QualityIssueTypeService()
        issues = [
            {"issue_type_code": "procedure_omission"},
            {"issue_type_code": "procedure_omission"},
            {"issue_type_code": "insufficient_evidence"},
            {"issue_type_code": "procedure_omission"},
        ]
        counts = svc.count_by_type(issues)
        assert counts["procedure_omission"] == 3
        assert counts["insufficient_evidence"] == 1

    def test_find_repeated_issues(self):
        svc = QualityIssueTypeService()
        issues = [
            {"issue_type_code": "procedure_omission"},
            {"issue_type_code": "procedure_omission"},
            {"issue_type_code": "procedure_omission"},
            {"issue_type_code": "insufficient_evidence"},
            {"issue_type_code": "insufficient_evidence"},
            {"issue_type_code": "amount_inconsistency"},
        ]
        repeated = svc.find_repeated_issues(issues, threshold=2)
        assert len(repeated) == 2
        assert repeated[0]["code"] == "procedure_omission"
        assert repeated[0]["count"] == 3

    def test_no_repeated_below_threshold(self):
        svc = QualityIssueTypeService()
        issues = [
            {"issue_type_code": "procedure_omission"},
            {"issue_type_code": "insufficient_evidence"},
        ]
        repeated = svc.find_repeated_issues(issues, threshold=2)
        assert len(repeated) == 0


class TestTrainingExport:
    """P2-3.8: 导出培训材料候选清单"""

    def test_export_training_candidates(self):
        svc = QualityIssueTypeService()
        issues = [
            {"issue_type_code": "amount_inconsistency"},
            {"issue_type_code": "amount_inconsistency"},
            {"issue_type_code": "amount_inconsistency"},
            {"issue_type_code": "procedure_omission"},
            {"issue_type_code": "procedure_omission"},
            {"issue_type_code": "inadequate_response"},
        ]
        candidates = svc.export_training_candidates(issues, min_occurrences=2)
        assert len(candidates) >= 2
        # amount_inconsistency = critical(4) * 3 = 12
        # procedure_omission = high(3) * 2 = 6
        assert candidates[0]["code"] == "amount_inconsistency"
        assert candidates[0]["priority_score"] == 12

    def test_export_includes_examples(self):
        svc = QualityIssueTypeService()
        issues = [
            {"issue_type_code": "insufficient_evidence"},
            {"issue_type_code": "insufficient_evidence"},
        ]
        candidates = svc.export_training_candidates(issues, min_occurrences=2)
        assert len(candidates) == 1
        assert len(candidates[0]["examples"]) > 0
        assert candidates[0]["training_hint"] != ""


# ═══════════════════════════════════════════════════════════════════════════════
# Facade 扩展: qc/eqcr 角色 section 隔离
# ═══════════════════════════════════════════════════════════════════════════════


class TestFacadeQCEqcrRoles:
    """验证 facade 支持 qc 和 eqcr 角色。"""

    def test_qc_role_registered(self):
        assert "qc" in ROLE_SECTION_REGISTRY
        assert "qc_rule_hits" in ROLE_SECTION_REGISTRY["qc"]

    def test_eqcr_role_registered(self):
        assert "eqcr" in ROLE_SECTION_REGISTRY
        assert "eqcr_dimensions" in ROLE_SECTION_REGISTRY["eqcr"]

    @pytest.mark.asyncio
    async def test_qc_workbench_returns_sections(self):
        db = _make_mock_db()
        facade = RoleWorkbenchFacade(db=db, project_id=uuid4(), user_id=uuid4())
        result = await facade.get_workbench("qc")
        section_ids = [s["id"] for s in result["sections"]]
        assert section_ids == ["qc_rule_hits", "issue_rectification", "quality_trend", "cycle_matrix"]

    @pytest.mark.asyncio
    async def test_eqcr_workbench_returns_sections(self):
        db = _make_mock_db()
        facade = RoleWorkbenchFacade(db=db, project_id=uuid4(), user_id=uuid4())
        result = await facade.get_workbench("eqcr")
        section_ids = [s["id"] for s in result["sections"]]
        assert section_ids == ["eqcr_dimensions", "eqcr_checklist", "eqcr_annotations"]

    @pytest.mark.asyncio
    async def test_five_roles_all_different(self):
        """Property 1: 5 类角色 section 集合互不相同。"""
        db = _make_mock_db()
        pid = uuid4()
        uid = uuid4()

        results = {}
        for role in ["auditor", "manager", "partner", "qc", "eqcr"]:
            facade = RoleWorkbenchFacade(db=db, project_id=pid, user_id=uid)
            result = await facade.get_workbench(role)
            results[role] = set(s["id"] for s in result["sections"])

        # 任意两个角色 section 集合不同
        roles = list(results.keys())
        for i in range(len(roles)):
            for j in range(i + 1, len(roles)):
                assert results[roles[i]] != results[roles[j]], (
                    f"{roles[i]} and {roles[j]} have same sections"
                )

    @pytest.mark.asyncio
    async def test_all_items_have_route_or_missing_reason(self):
        """Property 2: 每个 item 有 route 或 missing_reason。"""
        db = _make_mock_db()
        for role in ["qc", "eqcr"]:
            facade = RoleWorkbenchFacade(db=db, project_id=uuid4(), user_id=uuid4())
            result = await facade.get_workbench(role)
            for section in result["sections"]:
                for item in section["items"]:
                    has_route = "route" in item and item["route"]
                    has_missing = "missing_reason" in item and item["missing_reason"]
                    assert has_route or has_missing, (
                        f"Item '{item.get('id')}' in section '{section['id']}' "
                        f"for role '{role}' has neither route nor missing_reason"
                    )
