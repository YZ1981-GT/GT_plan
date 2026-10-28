# -*- coding: utf-8 -*-
"""程序表行级编辑隔离：保存合并口径 + ``/save`` 接线（spec procedure-trim-generation-delegation-chain 需求 7）。

用户裁决：程序执行人能看整张程序表，只有派给自己的行能编辑。服务端按自己推导的行归属合并，不信客户端：
受限用户的本人行只收执行状态与执行说明（裁剪 / 恢复只走细裁接口），其余一律保留服务端已存内容，并回报
没有生效的程序号。行归属判定（真库）见 ``procedure_delegation_visibility/test_program_row_trim_and_access.py``。
"""
from __future__ import annotations

import copy
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.wp_visibility import program_row_guard
from app.services.wp_visibility.program_row_guard import RowAccess, merge_program_sheet
from tests.test_wp_html_save import _WP_ID, _FakeWorkingPaper, _make_app, _patched_lane

SHEET = "应收账款实质性程序表D2A"
OWN_1 = RowAccess(full_power=False, can_trim=False, own_program_nos=frozenset({"1"}))

_SERVER = {
    "programs": [
        {"id": "row-1", "program_no": 1, "program_desc": "函证", "status": "pending", "execution_summary": ""},
        {"id": "row-2", "program_no": 2, "program_desc": "截止测试", "status": "pending"},
        {"id": "row-3", "program_no": 3, "program_desc": "分析", "status": "not_applicable", "trim_reason": "裁"},
    ],
    "signatures": {"preparer": "张三"},
    "trim_decisions": [{"program_no": 3, "reason": "裁"}],
    "conclusion": "服务端结论",
}


def _client_edit() -> dict:
    data = copy.deepcopy(_SERVER)
    rows = data["programs"]
    rows[0].update(status="completed", execution_summary="已函证", program_desc="改了描述")
    rows[1].update(status="completed", execution_summary="替别人填")
    rows[2].update(status="pending")
    rows.append({"id": "custom-1", "program_no": 4, "program_desc": "自加", "status": "pending"})
    data["signatures"] = {"preparer": "李四"}
    data["trim_decisions"] = []
    data["conclusion"] = "客户端结论"
    return data


# ---------------------------------------------------------------------------
# 合并口径
# ---------------------------------------------------------------------------
def test_delegator_and_non_program_sheets_pass_through():
    edit = _client_edit()
    assert merge_program_sheet(_SERVER, edit, RowAccess(full_power=True, can_trim=True)) == (edit, [])
    plain = {"rows": [{"cell": "B17", "value": 1}]}
    assert merge_program_sheet(None, plain, OWN_1) == (plain, [])


def test_lead_edits_every_row_but_applicability_stays_with_delegator():
    lead = RowAccess(full_power=True, can_trim=False)
    edit = _client_edit()
    edit["programs"][1].update(status="not_applicable", trim_reason="主编想裁")
    merged, ignored = merge_program_sheet(_SERVER, edit, lead)
    rows = merged["programs"]
    assert (rows[0]["status"], rows[0]["execution_summary"], rows[0]["program_desc"]) == ("completed", "已函证", "改了描述")
    assert rows[1]["status"] == "pending" and "trim_reason" not in rows[1] and rows[1]["execution_summary"] == "替别人填"
    assert (rows[2]["status"], rows[2]["trim_reason"]) == ("not_applicable", "裁"), "恢复也只归委派人"
    assert rows[3]["id"] == "custom-1" and merged["conclusion"] == "客户端结论", "其余照收"
    assert merged["trim_decisions"] == _SERVER["trim_decisions"]
    assert ignored == ["2", "3"]
    assert merge_program_sheet(None, edit, lead) == (edit, []), "服务端还没存过：分不清模板默认，照收（残余风险）"


def test_restricted_save_keeps_server_copy_except_own_status_and_summary():
    merged, ignored = merge_program_sheet(_SERVER, _client_edit(), OWN_1)
    expected = copy.deepcopy(_SERVER)
    expected["programs"][0].update(status="completed", execution_summary="已函证")
    assert merged == expected, "本人行只收执行状态与说明；别人的行、自加行、签字、裁剪决定、结论都保留服务端"
    assert ignored == ["2", "3", "4"]
    assert _SERVER["programs"][0]["status"] == "pending", "不改写传入的服务端数据"


def test_own_row_cannot_trim_or_restore_or_change_reason():
    server = copy.deepcopy(_SERVER)
    access = RowAccess(full_power=False, can_trim=False, own_program_nos=frozenset({"1", "3"}))
    edit = copy.deepcopy(server)
    edit["programs"][0].update(status="not_applicable", execution_summary="写了说明")
    edit["programs"][2].update(status="pending", trim_reason="")
    merged, ignored = merge_program_sheet(server, edit, access)
    assert merged["programs"][0]["status"] == "pending" and merged["programs"][0]["execution_summary"] == "写了说明"
    assert merged["programs"][2]["status"] == "not_applicable" and merged["programs"][2]["trim_reason"] == "裁"
    assert ignored == ["1", "3"]


def test_removed_row_is_kept_and_reported():
    edit = copy.deepcopy(_SERVER)
    del edit["programs"][1]
    merged, ignored = merge_program_sheet(_SERVER, edit, OWN_1)
    assert merged == _SERVER and ignored == ["2"]


@pytest.mark.parametrize("server", [None, {"programs": []}])
def test_first_save_resets_non_own_rows_to_template_state(server):
    edit = _client_edit()
    edit["programs"][2]["status"] = "not_applicable"
    merged, ignored = merge_program_sheet(server, edit, OWN_1)
    rows = merged["programs"]
    assert [r["id"] for r in rows] == ["row-1", "row-2", "row-3"], "自加行丢弃"
    assert (rows[0]["status"], rows[0]["execution_summary"]) == ("completed", "已函证")
    assert rows[1]["status"] == "pending" and "execution_summary" not in rows[1]
    assert rows[2]["status"] == "not_applicable", "模板原样的状态（待执行 / 不适用）照收 —— 已知残余风险，见 design"
    assert "signatures" not in merged and merged["trim_decisions"] == []
    assert ignored == ["2", "4"]


# ---------------------------------------------------------------------------
# /save 接线（路由层替身，同 test_wp_html_save；真实 commit 语义另有真库用例）
# ---------------------------------------------------------------------------
def _mock_db(fake_wp):
    mock_db = AsyncMock(spec=AsyncSession)

    def _execute(*args, **kwargs):
        result = MagicMock()
        scalars = MagicMock()
        scalars.first.return_value = fake_wp
        result.scalars.return_value = scalars
        return result

    mock_db.execute.side_effect = _execute
    mock_db.commit = AsyncMock()
    return mock_db


async def _save(access_side_effect, html_data):
    app = _make_app()
    fake_wp = _FakeWorkingPaper(parsed_data={"schema_version": "v2025-R5", "html_data": {SHEET: copy.deepcopy(_SERVER)}})
    mock_db = _mock_db(fake_wp)

    async def _db():
        yield mock_db

    app.dependency_overrides[get_db] = _db
    resolver = AsyncMock(side_effect=access_side_effect)
    with (
        patch.object(program_row_guard, "resolve_row_access", resolver),
        patch("app.routers.wp_html_save.cross_ref_service") as crs,
        _patched_lane(fake_wp) as (lane, _outbox),
    ):
        crs.get_wp_code_for_wp_id = AsyncMock(return_value="D2")
        crs.detect_changes.return_value = []
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(f"/api/workpapers/{_WP_ID}/save", json={
                "sheet_name": SHEET, "html_data": html_data, "schema_version": "v2025-R5",
            })
    return resp, lane, fake_wp, resolver


@pytest.mark.asyncio
async def test_save_merges_restricted_program_sheet_before_commit():
    resp, lane, fake_wp, resolver = await _save([OWN_1], _client_edit())
    assert resp.status_code == 200
    assert resp.json()["ignored_program_nos"] == ["2", "3", "4"]
    expected = copy.deepcopy(_SERVER)
    expected["programs"][0].update(status="completed", execution_summary="已函证")
    assert lane.staged_calls[0][1] == expected, "落盘的是合并后的数据"
    assert fake_wp.parsed_data["html_data"][SHEET] == expected
    assert resolver.await_args.args[3] == SHEET


@pytest.mark.asyncio
async def test_save_passes_full_power_edit_through():
    edit = _client_edit()
    resp, lane, _wp, _r = await _save([RowAccess(full_power=True, can_trim=True)], edit)
    assert resp.status_code == 200 and resp.json()["ignored_program_nos"] == []
    assert lane.staged_calls[0][1] == edit


@pytest.mark.asyncio
async def test_save_fails_closed_when_row_ownership_unreadable():
    resp, lane, fake_wp, _r = await _save(RuntimeError("归属查询失败"), _client_edit())
    assert resp.status_code == 503
    assert lane.staged_calls == [] and lane.commit_calls == []
    assert fake_wp.parsed_data["html_data"][SHEET] == _SERVER, "读不到归属不得落盘"
