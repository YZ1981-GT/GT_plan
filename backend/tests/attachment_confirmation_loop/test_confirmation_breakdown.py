"""函证底稿「函证」证据声明逐笔判定（spec attachment-confirmation-evidence-loop 需求 6，ADR-ACE-07）。

改造前：底稿下只要有任意一份函证附件就判「满足」，看不出哪几笔缺回函、哪几笔做了替代程序。
真库行（SQLite 世界）+ 生产 service；接口用例经 HTTP 真发请求（生产门禁）。
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from app.models.attachment_models import AttachmentWorkingPaper
from app.models.confirmation_models import Confirmation, ConfirmationAttachmentLink
from app.models.wp_optimization_models import EvidenceLink
from app.routers.attachments import router as attachments_router
from app.services import confirmation_evidence_status as status_module
from app.services.attachment_service import AttachmentService
from app.services.confirmation_evidence_status import (
    REASON_NO_EVIDENCE,
    REASON_NOT_SENT,
    confirmation_breakdown,
    workbook_code_of,
)
from tests.attachment_security_baseline._world import add_attachment, add_wp, sqlite_attachment_world


@pytest_asyncio.fixture
async def world(monkeypatch):
    async with sqlite_attachment_world(monkeypatch) as w:
        yield w


async def _conf(world, wp, counterparty, *, status="sent", index=None, confirm_type="receivable", project=None):
    project = project or world.target
    return await world._add(Confirmation(
        project_id=project.id, confirm_type=confirm_type, counterparty=counterparty, status=status,
        wp_id=wp.id, account_code=index, book_amount=100,
    ))


async def _letter(world, conf, role, *, deleted=False):
    att = await add_attachment(world, world.target, file_name=f"{conf.counterparty}-{role}.pdf",
                               attachment_type="confirmation", is_deleted=deleted)
    await world._add(ConfirmationAttachmentLink(
        confirmation_id=conf.id, attachment_id=att.id, role=role, match_status="manual",
    ))
    return att


def _company(name, index, *row_ids):
    """替代程序页的一家公司：第一个行 id 放第一区块，其余放第三区块（各区块的行都算）。"""
    return {
        "entity_name": name, "confirm_index": index,
        "block1_rows": [{"_row_id": rid, "voucher_amount": 10} for rid in row_ids[:1]],
        "block3_rows": [{"_row_id": rid} for rid in row_ids[1:]],
    }


async def _alternative_page(world, wp, companies, *, sheet="D0-5"):
    wp.parsed_data = {"html_data": {
        sheet: {"_format": "alternative-d05-v1", "companies": companies},
        "D0-1": {"rows": [{"_row_id": "不是替代程序页的行"}]},
    }}
    await world.db.flush()


async def _row_evidence(world, wp, row_id, *, creator, deleted=False):
    att = await add_attachment(world, world.target, file_name=f"替代-{row_id}.pdf", is_deleted=deleted)
    await world._add(EvidenceLink(
        wp_id=wp.id, attachment_id=att.id, sheet_name="D0-5", cell_ref=f"row:{row_id}",
        evidence_type="voucher", created_by=creator,
    ))


async def _whole_wp_reply(world, wp):
    """整稿挂一份函证类附件：原判定据此即判满足。"""
    att = await add_attachment(world, world.target, file_name="整稿回函.pdf", attachment_type="confirmation")
    await world._add(AttachmentWorkingPaper(attachment_id=att.id, wp_id=wp.id, association_type="evidence"))


def _reasons(result) -> dict[str, str]:
    return {item["counterparty"]: item["reason"] for item in result["missing_items"]}


def _data(resp) -> dict:
    body = resp.json()
    return body.get("data", body) if isinstance(body, dict) and "items" not in body else body


@pytest.mark.parametrize(("code", "book"), [
    ("D0-5", "D0"), ("D0-4b", "D0"), ("D0", "D0"), ("E1-1", "E1"), ("A12-1", "A12"), (None, ""),
])
def test_workbook_code(code, book):
    assert workbook_code_of(code) == book


async def test_each_confirmation_is_classified(world):
    who = await world.edit_member()
    wp = await add_wp(world, world.target, wp_code="D0")  # 整册一张底稿的形态
    replied = await _conf(world, wp, "甲公司", index="D0-1-001")
    await _letter(world, replied, "outbound")
    await _letter(world, replied, "inbound")
    await _conf(world, wp, "乙公司", status="matched")  # 状态已相符、回函件未挂 ⇒ 仍算已回函
    by_index = await _conf(world, wp, "丙公司", index="D0-1-003")
    await _letter(world, by_index, "outbound")
    by_name = await _conf(world, wp, "丁公司(北京)")
    await _letter(world, by_name, "outbound")
    await _conf(world, wp, "戊公司", status="pending")
    sent_only = await _conf(world, wp, "己公司", index="D0-1-006")
    await _letter(world, sent_only, "outbound")
    await _conf(world, wp, "庚公司", index="D0-1-007")
    pending_with_letter = await _conf(world, wp, "辛公司", status="pending")
    await _letter(world, pending_with_letter, "outbound")
    await _alternative_page(world, wp, [
        _company("丙公司（另一写法）", "D0-1-003", "r-c1", "r-c2"),  # 按索引号对上
        _company(" 丁公司（北京） ", None, "r-d1"),                  # 按名称对上（空白、全角括号）
        _company("庚公司", "D0-1-007", "r-g1"),                      # 有行但行上没有附件
    ])
    await _row_evidence(world, wp, "r-c2", creator=who.user.id)  # 第三区块的行
    await _row_evidence(world, wp, "r-d1", creator=who.user.id)

    result = await confirmation_breakdown(world.db, world.target.id, "D0")

    assert (result["total"], result["replied"], result["alternative"], result["missing"]) == (8, 2, 2, 4)
    assert _reasons(result) == {
        "戊公司": REASON_NOT_SENT,
        "己公司": REASON_NO_EVIDENCE,   # 已发函不等于已回函
        "庚公司": REASON_NO_EVIDENCE,   # 替代程序要看行上的附件，有行不算
        "辛公司": REASON_NO_EVIDENCE,   # 状态待发函但发函件已挂 ⇒ 不是「未发函」
    }


async def test_deleted_attachments_do_not_count(world):
    who = await world.edit_member()
    wp = await add_wp(world, world.target, wp_code="D0")
    reply_gone = await _conf(world, wp, "甲公司")
    await _letter(world, reply_gone, "inbound", deleted=True)
    await _conf(world, wp, "乙公司", index="D0-1-002")
    letter_gone = await _conf(world, wp, "丙公司", status="pending")
    await _letter(world, letter_gone, "outbound", deleted=True)
    await _alternative_page(world, wp, [_company("乙公司", "D0-1-002", "r-b1")])
    await _row_evidence(world, wp, "r-b1", creator=who.user.id, deleted=True)

    result = await confirmation_breakdown(world.db, world.target.id, "D0")

    assert (result["replied"], result["alternative"], result["missing"]) == (0, 0, 3)
    assert _reasons(result) == {"甲公司": REASON_NO_EVIDENCE, "乙公司": REASON_NO_EVIDENCE, "丙公司": REASON_NOT_SENT}


async def test_split_workbook_view_counts_the_whole_family(world):
    """拆成 D0-1 … D0-8 的形态：函证登记在汇总表 D0-1 上，替代程序在 D0-5；在 D0-5 的附件抽屉看。

    读者用系统管理员：底稿可见性门对成员要求委派 + 循环范围（另有 procedure_delegation_visibility 套件），
    这里只观测响应内容，门禁照常执行。
    """
    who = await world.edit_member()
    reader = (await world.admin_non_member()).user
    summary = await add_wp(world, world.target, wp_code="D0-1")
    alt = await add_wp(world, world.target, wp_code="D0-5")
    by_alt = await _conf(world, summary, "甲公司", index="D0-1-001")
    await _letter(world, by_alt, "outbound")
    pending_id = str((await _conf(world, summary, "乙公司", status="pending")).id)
    await _alternative_page(world, alt, [_company("甲公司", "D0-1-001", "r-a1")])
    await _row_evidence(world, alt, "r-a1", creator=who.user.id)
    await _whole_wp_reply(world, alt)  # 原判定会据此判满足
    other = await world.other_project()  # 别的项目同编码族的函证不算
    await _conf(world, await add_wp(world, other, wp_code="D0-1"), "外项目", status="pending", project=other)

    async with world.client(attachments_router, user=reader) as client:
        resp = await client.get(f"/api/working-papers/{alt.id}/attachments")

    assert resp.status_code == 200, resp.text
    (req,) = [r for r in _data(resp)["evidence_requirements"] if r["type"] == "confirmation"]
    assert req["satisfied"] is False
    assert req["breakdown"] == {
        "total": 2, "replied": 0, "alternative": 1, "missing": 1,
        "missing_items": [{"confirmation_id": pending_id, "counterparty": "乙公司", "confirm_type": "receivable",
                           "reason": REASON_NOT_SENT}],
    }


async def test_family_without_confirmations_keeps_original_rule(world):
    wp = await add_wp(world, world.target, wp_code="D0")
    await _whole_wp_reply(world, wp)
    await _conf(world, await add_wp(world, world.target, wp_code="E0-1"), "某银行", status="pending", confirm_type="bank")

    assert await confirmation_breakdown(world.db, world.target.id, "D0") is None
    view = await AttachmentService(world.db).get_wp_attachments(wp.id)
    assert view["evidence_requirements"] == [{"type": "confirmation", "label": "函证回函件", "satisfied": True}]


async def test_breakdown_failure_keeps_original_rule(world, monkeypatch):
    wp = await add_wp(world, world.target, wp_code="D0")
    await _whole_wp_reply(world, wp)
    await _conf(world, wp, "甲公司", status="pending")
    normal = await AttachmentService(world.db).get_wp_attachments(wp.id)
    assert normal["evidence_requirements"][0]["satisfied"] is False  # 逐笔判定生效

    async def boom(*_args, **_kwargs):
        raise RuntimeError("模拟查询失败")

    monkeypatch.setattr(status_module, "confirmation_breakdown", boom)
    view = await AttachmentService(world.db).get_wp_attachments(wp.id)
    assert view["evidence_requirements"] == [{"type": "confirmation", "label": "函证回函件", "satisfied": True}]
    assert len(view["items"]) == 1  # 其余部分照常返回


async def test_a12_1_legal_letter(world):
    wp = await add_wp(world, world.target, wp_code="A12-1")
    letter = await _conf(world, wp, "某律师事务所", confirm_type="legal")
    letter_id = str(letter.id)
    await _letter(world, letter, "outbound")

    view = await AttachmentService(world.db).get_wp_attachments(wp.id)
    (req,) = view["evidence_requirements"]
    assert (req["type"], req["label"], req["satisfied"]) == ("confirmation", "律师询证函回函", False)
    assert req["breakdown"]["missing_items"] == [
        {"confirmation_id": letter_id, "counterparty": "某律师事务所", "confirm_type": "legal", "reason": REASON_NO_EVIDENCE},
    ]

    await _letter(world, letter, "inbound")
    view = await AttachmentService(world.db).get_wp_attachments(wp.id)
    assert view["evidence_requirements"][0]["satisfied"] is True
    assert view["evidence_requirements"][0]["breakdown"]["replied"] == 1
