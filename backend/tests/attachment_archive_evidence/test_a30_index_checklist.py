"""A30 电子底稿归档检查表（spec attachment-archive-and-a-class-evidence 需求 8，ADR-AE-11）。

回归背景：A30 不在两份 xlsx 列映射里，``parse_checklist_xlsx`` 抛错，页面是空模板；三个核对表入口各写一遍
「xlsx → docx」分派。
"""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio

from app.routers import completion_phase
from app.services import checklist_template_loader
from app.services.checklist_index_parser import (
    checklist_item_codes,
    get_index_checklist_template,
    is_index_checklist,
    parse_index_checklist,
    template_path,
)
from tests.attachment_security_baseline._world import add_wp, sqlite_attachment_world

#: 真模板现读（2026-10-27）：第 5~207 行 203 个编码，A17-2 出现两次，名称带 * 的 51 项
EXPECTED_SECTION_COUNTS = {
    "A": 69, "B": 21, "C": 22, "S": 2, "D": 8, "E": 2, "F": 6, "G": 15, "H": 11, "I": 6, "J": 3, "K": 14,
    "L": 9, "M": 10, "N": 5,
}


@pytest.fixture(scope="module")
def parsed():
    path = template_path("A30")
    assert path is not None and path.name == "A30 电子底稿归档检查表.xlsx"
    return parse_index_checklist(path, "A30")


def test_structure_from_real_template(parsed):
    assert parsed["wp_code"] == "A30" and parsed["conclusion_mode"] == "completion"
    counts = {s["title"][0]: len(s["items"]) for s in parsed["sections"]}
    assert counts == EXPECTED_SECTION_COUNTS
    assert [s["title"] for s in parsed["sections"]][:4] == ["A 完成阶段", "B 控制了解", "C 控制测试", "S 专项"]
    assert parsed["stats"]["total_actionable"] == sum(EXPECTED_SECTION_COUNTS.values()) == 203
    assert parsed["stats"]["total_required"] == 51
    assert [t["id"] for t in parsed["toc"]] == [s["id"] for s in parsed["sections"]]


def test_items_codes_ids_and_required(parsed):
    items = [i for s in parsed["sections"] for i in s["items"]]
    ids = [i["id"] for i in items]
    assert len(set(ids)) == len(ids)
    first = items[0]
    assert (first["id"], first["standard_ref"], first["content"], first["required"]) == (
        "A30-A1", "A1", "财务报告（必备）", True)
    by_id = {i["id"]: i for i in items}
    assert by_id["A30-A1-11"]["standard_ref"] == "A1-11"  # 「A 1-11」去空白
    assert "A30-A17-2" in by_id and "A30-A17-2-2" in by_id  # 重复编码第二次加后缀
    assert by_id["A30-N5"]["content"] == "所得税费用" and by_id["A30-N5"]["required"] is False
    assert all(i["preset_wp_ref"] == i["standard_ref"] for i in items)
    # 页脚「项目合伙人：」「填表说明：」及其后的说明行不成项
    assert not any(i["content"].startswith(("项目合伙人", "填表说明", "1、")) for i in items)
    assert Counter(checklist_item_codes(parsed).values())["A17-2"] == 2


async def test_loader_dispatches_a30_to_index_parser():
    assert is_index_checklist("A30") and not is_index_checklist("A30-1") and not is_index_checklist("A3")
    via_loader = await checklist_template_loader.load_checklist_template("A30")
    assert via_loader is await get_index_checklist_template("A30")  # 同一缓存结果
    assert via_loader["stats"]["total_actionable"] == 203


@pytest_asyncio.fixture
async def world(monkeypatch):
    async with sqlite_attachment_world(monkeypatch) as w:
        yield w


def _url(project_id, wp_id):
    return f"/api/projects/{project_id}/workpapers/{wp_id}/archive-checklist/suggestions"


def _plain_app():
    """只挂路由本身与它的路由级依赖（项目成员只读及以上），不附加注册时的底稿统一门 ``dedicated_wp_gate``：
    SQLite 世界没有可见性相关表，统一门恒拒（同 ``attachment_evidence_intake._helpers.evidence_app``）。"""
    from fastapi import FastAPI

    api = FastAPI()
    api.include_router(completion_phase.router)
    return api


async def test_suggestions_follow_project_workpapers(world):
    a30 = await add_wp(world, world.target, wp_code="A30")
    await add_wp(world, world.target, wp_code="D2")
    await add_wp(world, world.target, wp_code="A1-11")
    gone = await add_wp(world, world.target, wp_code="E1")
    gone.is_deleted = True
    await world.db.flush()
    who = await world.readonly_member()
    async with world.client_for_app(_plain_app(), user=who.user) as c:
        resp = await c.get(_url(world.target.id, a30.id))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    sug = body["suggestions"]
    assert (sug["A30-D2"], sug["A30-A1-11"], sug["A30-A30"]) == ("是", "是", "是")
    assert sug["A30-E1"] == "否"  # 已删除的底稿不算
    assert sug["A30-A1"] == "否"
    assert body["total"] == 203 and body["present"] == 3


async def test_suggestions_auth_and_scope(world, monkeypatch):
    from app.services.wp_visibility.denial import DenialResponder

    a30 = await add_wp(world, world.target, wp_code="A30")
    other_wp = await add_wp(world, world.target, wp_code="D2")
    outsider = await world.non_member()
    manager = await world.edit_member()
    # 统一门拒绝会用全局引擎另开会话写安全审计 outbox：截住，不写开发库（否则还会把绑在本用例事件循环上的连接
    # 留在全局连接池里，后面用全局引擎的用例报 Event loop is closed）
    denials: list[str | None] = []

    async def _capture(_self, **fields):
        denials.append(fields.get("reason"))

    monkeypatch.setattr(DenialResponder, "_write_outbox", _capture)
    async with world.client_for_app(_plain_app(), user=outsider.user) as c:
        assert (await c.get(_url(world.target.id, a30.id))).status_code == 403
    async with world.client(completion_phase.router, user=manager.user) as c:
        # 按生产注册挂载：底稿统一门在（SQLite 世界恒拒 ⇒ 404「资源不存在或不可访问」），证明新路由也受统一门保护
        assert (await c.get(_url(world.target.id, a30.id))).status_code == 404
    assert len(denials) == 1 and denials[0]
    async with world.client_for_app(_plain_app(), user=manager.user) as c:
        assert (await c.get(_url(world.target.id, other_wp.id))).status_code == 404  # 不是 A30
        other = await world.other_project()
        assert (await c.get(_url(other.id, a30.id))).status_code in (403, 404)


class _InsertOnlyDb:
    """只接住核对表 UPSERT 的假库：验证结论白名单（``_do_batch_save`` 在写库前逐条校验）。"""

    def __init__(self):
        self.saved: list[tuple[str, str | None]] = []

    async def execute(self, statement, params):
        assert "INSERT INTO checklist_responses" in str(statement)
        self.saved.append((params["item_id"], params["conclusion"]))
        row = SimpleNamespace(id=uuid.uuid4(), item_id=params["item_id"], conclusion=params["conclusion"], remark=None,
                              wp_ref=None, updated_by=None, updated_at=datetime.now(timezone.utc))
        return SimpleNamespace(fetchone=lambda: row)

    async def flush(self):
        return None


async def _save(pairs):
    from app.routers.checklist_responses import BatchSaveRequest, ChecklistResponseItem, _do_batch_save

    db = _InsertOnlyDb()
    body = BatchSaveRequest(items=[ChecklistResponseItem(item_id=i, conclusion=c) for i, c in pairs])
    await _do_batch_save(db, uuid.uuid4(), body, SimpleNamespace(id=uuid.uuid4()), datetime.now(timezone.utc),
                         uuid.uuid4(), {})
    return db.saved


async def test_completion_conclusions_are_saved():
    """建议填入的「是 / 否」、人工选的「不适用」都要能存（走查实测：原先落到默认白名单 Y/N/X/I/X/W/N/A ⇒ 恒 422）。"""
    pairs = [("A30-D2", "是"), ("A30-E1", "否"), ("A30-A1", "不适用"), ("A30-A2", None),
             ("A17-5-1-001", "是"), ("A17-5-1-002", "X/W")]
    assert await _save(pairs) == pairs


@pytest.mark.parametrize(("item_id", "value"), [("A30-D2", "Y"), ("A30-D2", "N/A"), ("A17-5-1-001", "完成")])
async def test_values_outside_options_still_rejected(item_id, value):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as raised:
        await _save([(item_id, value)])
    assert raised.value.status_code == 422 and value in str(raised.value.detail)


def test_footer_stops_parsing_even_if_code_like_rows_follow(tmp_path):
    """页脚之后的行一律不成项：即使说明里写了像编码的内容（如「A30 表由项目经理签字」）。"""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    rows = [("致同会计师事务所",), ("电子底稿归档检查表",), (None,), ("索引号", "电子工作底稿名称", None, "有或无"),
            ("A 1", "财务报告 *"), ("D2", "营业收入"), ("项目合伙人：",), ("A30", "表由项目经理签字"), ("B1", "不该进来")]
    for r in rows:
        ws.append(list(r))
    path = tmp_path / "A30 测试.xlsx"
    wb.save(path)
    parsed = parse_index_checklist(path, "A30")
    ids = [i["id"] for s in parsed["sections"] for i in s["items"]]
    assert ids == ["A30-A1", "A30-D2"]
