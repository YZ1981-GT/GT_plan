"""离屏执行器的写入照样受四层人工保护与推送 ownership 重放约束（spec note-disclosure-pull-regression-and-headless-backend
任务 13 / R4.5，design §5.4）。

离屏执行器（Node）只经现有端点写入（写请求名单见 ``tools/headless-disclosure/entry.ts`` 的 ``headlessWriteAllowlist``，
前端用例 ``executor.spec.ts`` 钉住）。本文件拿**执行器真实产出的载荷**（``fixtures/headless_disclosure/d2_listed_payload.json``：
【测试】公式同步甲 D2，与浏览器附注页逐字节相同）走这些端点背后的生产服务，逐层断言保护仍然生效：

- 整章 ``_manual_override``：同步被拦下，表格一格不动，留冲突待调解；
- 正文 ``is_local_override``：表格照常随底稿刷新，正文不被底稿叙述覆盖（对照：不带标记时会被覆盖 ⇒ 判据不空转）；
- 推送 ownership 重放：公式推送拥有的格同步后恢复推送值并逐格回报 ``push_kept``；
- 格级 ``_cell_modes`` manual / locked：执行器最后一步调的重算端点（全部 / 单章节）都以 ``skip_manual=True`` 重算
  （重算本身跳过人工格由 ``services/test_note_manual_protect_pbt.py`` 覆盖）。
- 首次同步保护（从未由底稿同步、已有人工填写的章节不写）在执行器侧，见前端 ``executor.spec.ts``。

SQLite 真 ORM（``_formula_push_env``），不打桩同步服务本身。
"""
from __future__ import annotations

import copy
import json
import uuid
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.models.audit_log_models import AuditChainHead, AuditLogEntry
from app.models.formula_push_models import FormulaPushState
from app.models.report_models import DisclosureNote
from app.models.v3_refinement_models import CrossModuleConflict
from app.services import wp_disclosure_sync_service as sync_mod
from tests._formula_push_env import YEAR, make_env

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "headless_disclosure" / "d2_listed_payload.json"
SECTION = "五、5"
AGING = "按账龄披露"


def _payload() -> dict:
    body = json.loads(FIXTURE.read_text(encoding="utf-8"))["body"]
    assert body["section_id"] == SECTION and body["current_standard"] == "listed_standalone", "夹具是上市 D2 载荷"
    assert AGING in body["sub_table_data"] and len(body["sub_table_data"]) >= 10, "夹具是执行器整份载荷（不是手写片段）"
    return body


def _existing_table_data() -> dict:
    """附注里已有的披露表：账龄表 1 年以内期末 100（载荷里是 0，被覆盖即看得出）。"""
    return {
        "_source": "workpaper", "_last_sync_wp_id": "底稿同步过",
        "sub_table_data": {AGING: [{"label": "1年以内", "end_amount": 100, "prior_amount": 80},
                                   {"label": "合计", "is_total": True, "end_amount": 100, "prior_amount": 80}]},
    }


@pytest_asyncio.fixture
async def env(monkeypatch):
    async with make_env(monkeypatch, extra_tables=(
        CrossModuleConflict.__table__, AuditChainHead.__table__, AuditLogEntry.__table__,
    )) as e:
        yield e


async def _add_note(env, table_data: dict, **cols) -> None:
    async with env.factory() as db:
        db.add(DisclosureNote(project_id=env.pid, year=YEAR, note_section=SECTION, section_title="应收账款",
                              table_data=table_data, **cols))
        await db.commit()


async def _sync(env, body: dict) -> dict:
    """与 ``sync-from-workpaper`` 端点同一调用（端点把请求体原样转给这个服务函数）。"""
    async with env.factory() as db:
        return await sync_mod.sync_from_workpaper(
            db, env.pid, wp_id=uuid.UUID(body["wp_id"]), sheet_name=body["sheet_name"], section_id=body["section_id"],
            sub_table_data=body["sub_table_data"], current_standard=body["current_standard"],
            user=SimpleNamespace(id=uuid.uuid4()), year=YEAR, sub_table_columns=body.get("columns"),
        )


def _aging_first(note: DisclosureNote) -> dict:
    return note.table_data["sub_table_data"][AGING][0]


@pytest.mark.asyncio
async def test_unprotected_sync_writes_the_executor_payload(env) -> None:
    """对照（判据不空转）：没有任何保护时，执行器载荷照写 —— 下面各条「不动」才有意义。"""
    await _add_note(env, _existing_table_data())
    result = await _sync(env, _payload())
    note = await env.note(SECTION)
    assert result["blocked_by_manual_override"] is False and result["push_kept"] == []
    assert _aging_first(note)["end_amount"] == 0, "载荷里的 0 覆盖了附注里的 100"
    assert set(_payload()["columns"]) <= set(note.table_data["sub_table_data"]), "整份载荷的表都写进来了"


@pytest.mark.asyncio
async def test_whole_section_manual_override_blocks_the_executor_payload(env) -> None:
    before = {**_existing_table_data(), "_manual_override": True}
    await _add_note(env, copy.deepcopy(before))
    result = await _sync(env, _payload())
    note = await env.note(SECTION)
    assert result["blocked_by_manual_override"] is True and result["rows_synced"] == 0
    assert note.table_data == before, "整章人工覆盖：表格一格不动"
    async with env.factory() as db:
        conflicts = (await db.execute(sa.select(CrossModuleConflict))).scalars().all()
    assert len(conflicts) == 1 and conflicts[0].target_id == note.id, "拦下的同步留一条冲突待调解"


@pytest.mark.asyncio
@pytest.mark.parametrize("local_override", [True, False])
async def test_local_override_keeps_text_while_tables_follow_the_workpaper(env, local_override) -> None:
    body = _payload()
    body["sub_table_data"]["_note_texts"] = [{"section": "d2-aging", "title": "账龄说明", "text": "底稿里的说明"}]
    await _add_note(env, _existing_table_data(), text_content="审计师编制的正文", is_local_override=local_override)
    await _sync(env, body)
    note = await env.note(SECTION)
    assert _aging_first(note)["end_amount"] == 0, "表格照常随底稿刷新"
    if local_override:
        assert note.text_content == "审计师编制的正文", "正文受 is_local_override 保护"
    else:
        assert note.text_content == "【账龄说明】\n底稿里的说明", "对照：不带标记时正文随底稿（判据不空转）"


@pytest.mark.asyncio
async def test_pushed_cells_are_replayed_over_the_executor_payload(env) -> None:
    await _add_note(env, _existing_table_data())
    async with env.factory() as db:
        db.add(FormulaPushState(
            project_id=env.pid, year=YEAR, domain="note", note_section=SECTION, rule_id="D2.note.main",
            addr_id=f"note://{SECTION}/{AGING}/1年以内.end", state="auto", last_pushed_value=12345.67,
        ))
        await db.commit()
    result = await _sync(env, _payload())
    note = await env.note(SECTION)
    assert Decimal(str(_aging_first(note)["end_amount"])) == Decimal("12345.67"), "推送拥有的格保持试算表审定数"
    kept = [k for k in result["push_kept"] if k["kind"] == "cell"]
    assert [(k["table"], k["row"], k["period"]) for k in kept] == [(AGING, "1年以内", "end")]
    assert kept[0]["incoming"] == 0, "回报的是执行器载荷里被顶掉的值"


@pytest.mark.asyncio
async def test_refresh_steps_called_by_the_executor_skip_manual_cells(env, monkeypatch) -> None:
    """执行器最后一步：全部刷新调 ``refresh-from-workpapers``，单章节调 ``…/{章节}/refresh-from-workpaper``。"""
    from app.services import disclosure_engine, note_wp_mapping_service
    from app.services.note_wp_mapping_service import NoteWpMappingService

    calls: list[dict] = []

    async def refill(self, project_id, year, sections, **kw):
        calls.append({"sections": list(sections), **kw})
        # 用真实报告类型（字段随 RefillReport 走，如写入归属的 blocked_writes；spec formula-writer-ownership-and-stale §13）
        return disclosure_engine.RefillReport(requested_sections=list(sections))

    async def finalize(db, project_id, year, report):  # 收尾（附注公式）与本判据无关
        return {}

    monkeypatch.setattr(disclosure_engine.DisclosureEngine, "refill_sections", refill)
    monkeypatch.setattr(note_wp_mapping_service, "_finalize_refill_report", finalize)
    await _add_note(env, _existing_table_data())
    async with env.factory() as db:
        svc = NoteWpMappingService(db)
        await svc.refresh_from_workpapers(env.pid, YEAR)
        await svc.refresh_section_from_workpapers(env.pid, YEAR, SECTION)
    assert len(calls) == 2 and calls[1]["sections"] == [SECTION], "两条重算路径都走到了 refill_sections"
    assert all(c.get("skip_manual") is True for c in calls), f"重算必须跳过人工 / 锁定格：{calls}"
