"""QC-17 按证据声明判定（spec attachment-archive-and-a-class-evidence 需求 6，ADR-AE-09）。

回归背景：QC-17 原按「底稿挂了几份整稿关联附件」计数 —— 没挂附件就阻断、挂一份无关附件就放行，
行级证据与函证回函都不算，与附件抽屉「应收集证据」是两套口径。
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from app.models.attachment_models import AttachmentWorkingPaper
from app.models.wp_optimization_models import EvidenceLink
from app.services import confirmation_evidence_status
from app.services.attachment_service import AttachmentService
from app.services.attachment_wp_view import evaluate_wp_evidence_requirements
from app.services.qc_engine import AttachmentSufficiencyRule, QCContext
from tests.attachment_security_baseline._world import add_attachment, add_wp, sqlite_attachment_world


@pytest_asyncio.fixture
async def world(monkeypatch):
    async with sqlite_attachment_world(monkeypatch) as w:
        yield w


async def _qc17(world, wp):
    return [f.to_dict() for f in await AttachmentSufficiencyRule().check(QCContext(world.db, wp))]


def test_engine_registers_declaration_based_qc17():
    """QC 引擎里的 QC-17 就是这条按声明判定的规则（整引擎用例 test_wopi_working_paper_qc_review 走无声明的 B1-1）。"""
    from app.services.qc_engine import QCEngine

    rules = [r for r in QCEngine().rules if r.rule_id == "QC-17"]
    assert len(rules) == 1 and type(rules[0]) is AttachmentSufficiencyRule and rules[0].severity == "blocking"


async def test_undeclared_workpaper_no_requirements_no_finding(world):
    wp = await add_wp(world, world.target, wp_code="B1-1")
    assert await evaluate_wp_evidence_requirements(world.db, wp.id) is None
    assert await _qc17(world, wp) == []


async def test_declared_unsatisfied_lists_missing_type(world):
    wp = await add_wp(world, world.target, wp_code="F3-5")
    # 挂一份无关类型的整稿附件：改造前计数即放行，现在仍缺「票据影像」
    other = await add_attachment(world, world.target, file_name="无关.pdf", attachment_type="evidence")
    await world._add(AttachmentWorkingPaper(attachment_id=other.id, wp_id=wp.id, association_type="evidence"))
    reqs = await evaluate_wp_evidence_requirements(world.db, wp.id)
    assert reqs == [{"type": "note", "label": "票据影像", "satisfied": False}]
    found = await _qc17(world, wp)
    assert [(f["rule_id"], f["severity"], f["message"]) for f in found] == [
        ("QC-17", "blocking", "应收集证据未齐：票据影像"),
    ]
    assert (found[0]["expected_value"], found[0]["actual_value"]) == (["note"], [])


async def test_row_level_evidence_satisfies(world):
    who = await world.edit_member()
    wp = await add_wp(world, world.target, wp_code="F3-5")
    note = await add_attachment(world, world.target, file_name="票据.pdf", attachment_type="note")
    await world._add(EvidenceLink(wp_id=wp.id, attachment_id=note.id, sheet_name="F3-5", cell_ref="row:1",
                                  evidence_type="note", created_by=who.user.id))
    view = await AttachmentService(world.db).get_wp_attachments(wp.id)
    reqs = await evaluate_wp_evidence_requirements(world.db, wp.id)
    # 与抽屉同一判定
    assert reqs == view["evidence_requirements"] == [{"type": "note", "label": "票据影像", "satisfied": True}]
    assert await _qc17(world, wp) == []


async def test_signed_copy_satisfies_a16(world):
    wp = await add_wp(world, world.target, wp_code="A16")
    assert (await _qc17(world, wp))[0]["message"] == "应收集证据未齐：管理层声明书签字件"
    signed = await add_attachment(world, world.target, file_name="声明书签字件.pdf", attachment_type="signed")
    await world._add(AttachmentWorkingPaper(attachment_id=signed.id, wp_id=wp.id, association_type="evidence"))
    assert await _qc17(world, wp) == []
    # A16-1 是变体：不继承 A16 的精确声明
    variant = await add_wp(world, world.target, wp_code="A16-1")
    assert await evaluate_wp_evidence_requirements(world.db, variant.id) is None


@pytest.mark.parametrize(("missing", "expect_finding"), [(2, True), (0, False)])
async def test_confirmation_breakdown_decides(world, monkeypatch, missing, expect_finding):
    wp = await add_wp(world, world.target, wp_code="D0")
    reply = await add_attachment(world, world.target, file_name="回函.pdf", attachment_type="confirmation")
    await world._add(AttachmentWorkingPaper(attachment_id=reply.id, wp_id=wp.id, association_type="confirmation"))

    async def fake_breakdown(db, project_id, wp_code):
        return {"total": 3, "replied": 3 - missing, "alternative": 0, "missing": missing, "missing_items": []}

    monkeypatch.setattr(confirmation_evidence_status, "confirmation_breakdown", fake_breakdown)
    reqs = await evaluate_wp_evidence_requirements(world.db, wp.id)
    assert reqs[0]["satisfied"] is (missing == 0)
    assert reqs[0]["breakdown"]["missing"] == missing
    found = await _qc17(world, wp)
    if expect_finding:
        assert found[0]["message"] == "应收集证据未齐：函证回函件（2 笔未回函且无替代程序）"
    else:
        # 整稿挂了回函件 ⇒ 改造前也放行；逐笔判定全部回函 ⇒ 仍放行
        assert found == []


async def test_evaluation_failure_is_fail_open(world, monkeypatch):
    wp = await add_wp(world, world.target, wp_code="F3-5")

    async def boom(db, wp_id):
        raise RuntimeError("db down")

    import app.services.attachment_wp_view as view_mod
    monkeypatch.setattr(view_mod, "evaluate_wp_evidence_requirements", boom)
    assert await _qc17(world, wp) == []
