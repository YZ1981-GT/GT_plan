"""公式推送引擎 run：判定 → 写底稿（CAS）→ 写附注 → 状态 / 运行记录（SQLite 真 ORM + 真 SQL）。

spec: chain-closure-phase2-formula-push-engine · 任务 10 · 需求 2.4~2.6 / 3.1~3.5 / 4.6

取数层（四表叶子 / 试算表 / 大厅调整 / 附注模板类型）由 binding 测试与双侧夹具守卫，本文件把
``E1Binding.load_sources`` 换成固定源，其余全走真实代码：真规则清单、真 binding、真写入适配器
（``@raw`` UPSERT + CAS）、真附注写入、真 ORM 状态表。

🔴 SQLite 下 uuid 存储形态：ORM（``PG_UUID``）写 32 位 hex，裸 SQL 传 ``str(uuid)`` 是带横线形态，
两者互不命中（探针实测）。生产代码对 ``working_paper`` / ``checklist_responses`` 走裸 SQL（与写入适配器
同口径），故本文件对这两张表也用裸 SQL 造数；``projects`` / ``disclosure_notes`` / 推送状态走 ORM。
PG 原生 uuid 无此差异（适配器真 PG 行为见 ``test_workpaper_adapter_pg.py``）。
"""
from __future__ import annotations

import json
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.models.report_models import DisclosureNote, NoteStatus
from app.services.formula_push import engine as push
from app.services.formula_push import panel
from app.services.formula_push.bindings import e1_calc
from app.services.formula_push.bindings.e1 import E1Binding
from tests._formula_push_env import (
    CASH_OPENING, TB_ENDING, YEAR, Env, base_entries, by_addr, cash_rows, make_env, make_sources,
)


@pytest_asyncio.fixture
async def env(monkeypatch):
    async with make_env(monkeypatch) as e:
        yield e



# ── 首推：系统值 / 派生值写入，来源不明的可编辑值待确认 ──────────────────────


@pytest.mark.asyncio
async def test_first_push_writes_system_and_derived_values_and_holds_unknown_editable_values(env):
    await env.seed_entries(base_entries())
    result = await env.push()
    items = by_addr(result)
    saved = await env.entries()

    # 系统值：试算平衡表数 = 试算表审定数合计；大厅已确认调整
    assert saved["E1-adj-tb-amount-ending"] == "606.73" and saved["E1-adj-tb-amount-opening"] == "386.73"
    assert saved["E1-hall-adj-cash-ending"] == "100"
    # 派生：审定合计 = 未审（落库的现金合计 290）+ 大厅已确认调整 100
    assert saved["E1-adj-total-1001"] == "390" and saved["E1-adj-total-1001-opening"] == "203"
    assert saved["E1-bank-detail-principal-total-unaudited"] == "120"
    # 语义槽三值全 0 ⇒ 保持空白，不写 0（「无此科目」≠「余额为 0」）
    assert "E1-adj-slot-digital" not in saved

    # 四表带入行：与四表相同 ⇒ 静默采纳；不同且来源不明（从未推送）⇒ 待确认，不覆盖
    assert items[CASH_OPENING].action == "keep_pending" and items[CASH_OPENING].state == "pending_confirm"
    assert items[CASH_OPENING.replace("opening", "increase")].action == "unchanged"
    assert json.loads(saved[e1_calc.CASH_ROWS_KEY])[0]["opening"] == 200
    assert saved[e1_calc.CASH_ROWS_KEY] == cash_rows(), "未决定写入的行 JSON 必须逐字不变"

    assert (result.written_count, result.unchanged_count, result.kept_count) == (20, 11, 2)
    assert result.status == "succeeded" and result.stages == ["derived", "source"]
    assert "E1-cash-detail-rows" not in result.changed_items

    states = await env.states()
    assert states[CASH_OPENING].state == "pending_confirm" and states[CASH_OPENING].last_pushed_value is None
    assert states[TB_ENDING].last_pushed_value == 606.73 and states[TB_ENDING].state == "auto"
    [run] = await env.runs()
    assert (run.status, run.written_count, run.kept_count) == ("succeeded", 20, 2)
    assert run.detail["items"] and run.detail["wp"][0]["status"] == "pushed"
    [(event, payload)] = env.broadcasts
    assert event == "formula.pushed" and payload["run_id"] == str(run.id)
    assert payload["stages"] == ["derived", "source"] and payload["written_count"] == 20


@pytest.mark.asyncio
async def test_second_push_without_changes_is_idempotent(env):
    await env.seed_entries(base_entries())
    await env.push()
    before = await env.entries()
    result = await env.push()
    assert result.written_count == 0 and result.kept_count == 2
    assert await env.entries() == before


# ── 可编辑值三态：采用 → 跟随四表；用户改过 → 保留；锁定 → 保留 ─────────────


@pytest.mark.asyncio
async def test_adopt_then_follow_four_table_until_user_edits(env):
    await env.seed_entries(base_entries())
    await env.push()
    # 采用公式值：写入**当前重新算出**的公式值并转 auto
    async with env.factory() as db:
        adopted = await panel.adopt(db, project_id=env.pid, year=YEAR, addr_ids=[CASH_OPENING], user_id=None)
    assert by_addr(adopted)[CASH_OPENING].action == "write"
    row = json.loads((await env.entries())[e1_calc.CASH_ROWS_KEY])[0]
    assert row["opening"] == 286.73 and row["note"] == "四表取数 1001.01", "只改目标字段，用户字段保留"
    assert (await env.entries())["E1-cash-detail-opening-unaudited"] == "289.73", "派生值同次运行读到新行"
    states = await env.states()
    assert states[CASH_OPENING].state == "auto" and states[CASH_OPENING].last_pushed_value == 286.73

    # 四表重新导入（期初变了）：当前值 == 上次推送值 ⇒ 视为自动，跟随新值
    env.sources = make_sources(cash_opening=300)
    result = await env.push("TRIAL_BALANCE_UPDATED")
    assert by_addr(result)[CASH_OPENING].action == "write"
    assert json.loads((await env.entries())[e1_calc.CASH_ROWS_KEY])[0]["opening"] == 300

    # 用户在底稿里改了期初 ⇒ 下次推送判人工修改，保留并记差异
    await _user_saves(env, e1_calc.CASH_ROWS_KEY, cash_rows(opening=321))
    env.sources = make_sources(cash_opening=310)
    result = await env.push("TRIAL_BALANCE_UPDATED")
    item = by_addr(result)[CASH_OPENING]
    assert (item.action, item.state, item.current, item.formula) == ("keep_manual", "manual", 321.0, 310)
    assert json.loads((await env.entries())[e1_calc.CASH_ROWS_KEY])[0]["opening"] == 321
    assert (await env.states())[CASH_OPENING].last_pushed_value == 300, "保留时不动上次推送值"


async def _user_saves(env: Env, item: str, remark: str) -> None:
    """模拟用户保存（checklist 路由同效果：改 remark、推进版本与 updated_at）。"""
    async with env.factory() as db:
        await db.execute(sa.text(
            "UPDATE checklist_responses SET remark = :r, updated_at = :t, content_version = content_version + 1 "
            "WHERE wp_id = :w AND item_id = :i"
        ), {"r": remark, "t": "2026-09-30 09:00:00.000000+00:00", "w": str(env.wp_id), "i": item})
        await db.commit()


@pytest.mark.asyncio
async def test_locked_target_is_never_overwritten_and_unlock_goes_pending(env):
    await env.seed_entries(base_entries())
    await env.push()
    async with env.factory() as db:
        await panel.adopt(db, project_id=env.pid, year=YEAR, addr_ids=[CASH_OPENING], user_id=None)
    async with env.factory() as db:
        [row] = await panel.set_locked(db, project_id=env.pid, year=YEAR, addr_ids=[CASH_OPENING],
                                      locked=True, user_id=None)
        await db.commit()
    assert row.state == "locked"
    env.sources = make_sources(cash_opening=999)
    result = await env.push("TRIAL_BALANCE_UPDATED")
    assert by_addr(result)[CASH_OPENING].action == "keep_locked"
    assert json.loads((await env.entries())[e1_calc.CASH_ROWS_KEY])[0]["opening"] == 286.73
    async with env.factory() as db:
        [row] = await panel.set_locked(db, project_id=env.pid, year=YEAR, addr_ids=[CASH_OPENING],
                                      locked=False, user_id=None)
        await db.commit()
    assert row.state == "pending_confirm", "解锁不直接覆盖，下次推送重新判定"


# ── 冻结 / 并发 / 试跑 ─────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["review_passed", "archived", "review_level1_passed", "review_level2_passed"])
async def test_frozen_workpaper_is_not_touched(env, status):
    await env.seed_entries(base_entries())
    await env.set_wp_status(status)
    before = await env.entries()
    result = await env.push()
    assert await env.entries() == before
    assert result.written_count == 0 and result.workpapers[0]["status"] == "frozen"
    assert any(i.action == "skipped" and "不改写" in (i.reason or "") for i in result.items)
    assert await env.states() == {}, "冻结底稿不产生推送状态"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["draft", "edit_complete", "under_review", "revision_required"])
async def test_editable_workpaper_statuses_are_pushed(env, status):
    await env.seed_entries(base_entries())
    await env.set_wp_status(status)
    assert (await env.push()).written_count > 0


@pytest.mark.asyncio
async def test_concurrent_save_rolls_back_whole_workpaper_and_skips_note(env, monkeypatch):
    """读快照之后、写入之前用户保存了一个条目 ⇒ 该底稿一个条目都不写，附注也不推，记「并发修改」。"""
    await env.seed_entries({**base_entries(), "E1-adj-total-1001": "1"})
    await env.add_note("五、1", _f2_note())
    real_read = push._read_entries

    async def read_then_user_saves(db, wp_id, wp_code):
        snap = await real_read(db, wp_id, wp_code)
        # 同一连接内改版本号，等价于「快照读取后另一个请求已提交」（改的是本次要写的条目）
        await db.execute(sa.text(
            "UPDATE checklist_responses SET updated_at = '2026-09-30 10:00:00.000000+00:00' "
            "WHERE wp_id = :w AND item_id = 'E1-adj-total-1001'"
        ), {"w": str(wp_id)})
        return snap

    monkeypatch.setattr(push, "_read_entries", read_then_user_saves)
    before = await env.entries()
    result = await env.push()
    assert result.status == "partial" and result.written_count == 0
    conflicts = [i for i in result.items if i.action == "conflict"]
    assert conflicts and all("E1-adj-total-1001" in i.reason for i in conflicts)
    after = await env.entries()
    # 按条目名排序先写的「试算平衡表数」已进保存点，冲突后必须一并回滚
    assert "E1-adj-tb-amount-ending" not in after, "冲突底稿的其它条目也不得落库（保存点回滚）"
    assert after == before
    assert (await env.note("五、1")).table_data == _f2_note(), "底稿冲突时附注不推"
    assert await env.states() == {}, "冲突项不写推送状态"
    [run] = await env.runs()
    assert run.status == "partial" and run.detail["wp"][0]["status"] == "conflict"


@pytest.mark.asyncio
async def test_dry_run_reports_without_leaving_any_trace(env):
    await env.seed_entries(base_entries())
    await env.add_note("五、1", _f2_note())
    before = await env.entries()
    result = await env.push(dry_run=True)
    assert result.dry_run and result.run_id is None
    writes = [i for i in result.items if i.action == "write"]
    # 底稿 20 项 + 附注 6 项（库存现金 / 银行存款 / 合计 × 期末期初）：试跑照常报告「将写入」
    assert sum(i.domain == "workpaper" for i in writes) == 20 and sum(i.domain == "note" for i in writes) == 6
    assert by_addr(result)[CASH_OPENING].action == "keep_pending" and result.note_sections == ["五、1"]
    assert await env.entries() == before
    assert (await env.note("五、1")).table_data == _f2_note()
    assert await env.states() == {} and await env.runs() == [] and env.broadcasts == []


# ── 附注 ───────────────────────────────────────────────────────────────────

NOTE_COLS = [
    {"key": "label", "flat": True, "label": "项目", "is_label": True},
    {"key": "end_amount", "label": "期末余额", "format": "amount"},
    {"key": "prior_amount", "label": "上年年末余额", "format": "amount"},
]


def _f2_note(**cash) -> dict:
    """上市 五、1 F2（真库重药形态：底稿同步写入的业务键行 + 合计 + 其中行 + 受限表）。"""
    rows = [
        {"label": "库存现金", "end_amount": 1, "prior_amount": 1, **cash},
        {"label": "银行存款", "end_amount": 0, "prior_amount": 0},
        {"label": "存放财务公司款项", "end_amount": 0, "prior_amount": 0},
        {"label": "其他货币资金", "end_amount": 0, "prior_amount": 0},
        {"label": "手工加的行", "end_amount": 5, "prior_amount": 0},
        {"label": "合计", "is_total": True, "end_amount": 6, "prior_amount": 1},
        {"label": "其中：存放在境外的款项总额", "end_amount": 7, "prior_amount": 0},
    ]
    return {
        "_source": "workpaper", "_last_sync_wp_id": "旧底稿同步",
        "_sub_table_columns": {"货币资金": NOTE_COLS},
        "sub_table_data": {"货币资金": rows, "受限制的货币资金明细": [{"label": "保证金", "end_amount": 9}]},
    }


def _main(td: dict) -> dict[str, dict]:
    return {r["label"]: r for r in td["sub_table_data"]["货币资金"]}


@pytest.mark.asyncio
async def test_note_rows_follow_disclosure_and_total_is_recomputed_from_actual_rows(env):
    await env.seed_entries(base_entries())
    await env.add_note("五、1", _f2_note())
    result = await env.push()
    note = await env.note("五、1")
    rows = _main(note.table_data)
    # 底稿来源章节、单元格无人工标记 ⇒ 与「同步到附注」同效，跟随披露数（需求 3.5：底稿同步写入不视为人工修改）
    assert rows["库存现金"]["end_amount"] == 390 and rows["库存现金"]["prior_amount"] == 203
    assert rows["银行存款"]["end_amount"] == 120 and rows["银行存款"]["prior_amount"] == 100
    # 底稿取不到的行（存放财务公司款项：语义槽空）保持附注原值，不写 0
    assert by_addr(result)["note://五、1/货币资金/存放财务公司款项.end"].action == "skipped"
    # 合计 = 合计行之前各行（含手工行 5，保留）；「其中：」行不动
    assert rows["合计"]["end_amount"] == 390 + 120 + 0 + 0 + 5 and rows["合计"]["prior_amount"] == 303
    assert rows["手工加的行"]["end_amount"] == 5
    assert rows["其中：存放在境外的款项总额"]["end_amount"] == 7
    assert note.table_data["sub_table_data"]["受限制的货币资金明细"] == [{"label": "保证金", "end_amount": 9}]
    # 同步指纹 + 来源（pull-from-workpapers 据 _last_sync_wp_id 认定已同步）
    assert note.table_data["_last_sync_wp_id"] == str(env.wp_id)
    assert (note.last_sync_source, note.last_sync_wp_id) == ("formula_push", env.wp_id)
    assert result.note_sections == ["五、1"] and "note" in result.stages

    # 大厅调整变化 ⇒ 附注跟随；整节人工覆盖（_manual_override）⇒ 整节保留
    env.sources = make_sources(hall_1001="200")
    await env.push("TRIAL_BALANCE_UPDATED")
    assert _main((await env.note("五、1")).table_data)["库存现金"]["end_amount"] == 490
    async with env.factory() as db:
        note = await db.get(DisclosureNote, (await env.note("五、1")).id)
        note.table_data = {**json.loads(json.dumps(note.table_data)), "_manual_override": True}
        await db.commit()
    env.sources = make_sources(hall_1001="300")
    result = await env.push("TRIAL_BALANCE_UPDATED")
    assert by_addr(result)["note://五、1/货币资金/库存现金.end"].action == "keep_locked"
    assert _main((await env.note("五、1")).table_data)["库存现金"]["end_amount"] == 490

    assert "整节人工覆盖" in by_addr(result)["note://五、1/货币资金/库存现金.end"].reason
    # 附注目标以附注自身标记为准：公式管理面板不提供采用 / 锁定（否则两处各有一套「人工」口径）
    addr = "note://五、1/货币资金/库存现金.end"
    for action in ("adopt", "lock"):
        async with env.factory() as db:
            with pytest.raises(push.PushActionError, match="附注模块"):
                if action == "adopt":
                    await panel.adopt(db, project_id=env.pid, year=YEAR, addr_ids=[addr], user_id=None)
                else:
                    await panel.set_locked(db, project_id=env.pid, year=YEAR, addr_ids=[addr], locked=True,
                                          user_id=None)



@pytest.mark.asyncio
@pytest.mark.parametrize("case, fragment", [
    ("missing", "尚未生成"),
    ("other_title", "政府补助"),
    ("confirmed", "已确认"),
    ("f1", "模板取数维护"),
])
async def test_note_section_is_skipped_with_reason(env, case, fragment):
    await env.seed_entries(base_entries())
    if case == "other_title":
        await env.add_note("五、1", _f2_note(), title="政府补助")
    elif case == "confirmed":
        await env.add_note("五、1", _f2_note(), status=NoteStatus.confirmed)
    elif case == "f1":
        # 真库和平药房 / 首汽形态：顶层 rows，由模板按试算表取数维护
        await env.add_note("五、1", {"rows": [{"label": "库存现金", "values": [1, 1]}], "headers": ["项目"]})
    result = await env.push()
    [skip] = [i for i in result.items if i.stage == "note"]
    assert skip.action == "skipped" and fragment in skip.reason
    assert result.note_sections == []
    if case != "missing":
        note = await env.note("五、1")
        assert "_last_sync_wp_id" not in (note.table_data or {}) or note.table_data["_last_sync_wp_id"] == "旧底稿同步"
        assert note.last_sync_source is None


@pytest.mark.asyncio
async def test_soe_template_picks_section_8_and_falls_back_to_workpaper_label(env):
    """国企 八、1：附注行标签优先附注字面「库存现金」，退回底稿字面「现金」（真库宜宾历史同步）。"""
    env.sources = make_sources(template_type="soe")
    await env.seed_entries(base_entries())
    td = _f2_note()
    _main(td)["库存现金"]["label"] = "现金"
    td["sub_table_data"]["货币资金"][0] = {"label": "现金", "end_amount": None, "prior_amount": None}
    await env.add_note("八、1", td)
    await env.add_note("五、1", _f2_note())
    result = await env.push()
    rows = _main((await env.note("八、1")).table_data)
    assert rows["现金"]["end_amount"] == 390 and rows["现金"]["prior_amount"] == 203, "空单元格直接写入"
    assert "note://八、1/货币资金/库存现金.end" in by_addr(result)
    assert (await env.note("五、1")).table_data == _f2_note(), "国企项目不碰上市章节"


@pytest.mark.asyncio
async def test_f3_cell_modes_and_section_override_are_respected_even_on_adopt(env):
    await env.seed_entries(base_entries())
    td = _f2_note()
    for r in td["sub_table_data"]["货币资金"]:
        r["values"] = [r.pop("end_amount"), r.pop("prior_amount")]
    _main(td)["银行存款"]["_cell_modes"] = {"0": "manual", "1": "locked"}
    await env.add_note("五、1", td)
    result = await env.push()
    rows = _main((await env.note("五、1")).table_data)
    assert rows["库存现金"]["values"] == [390, 203], "无标记单元格按列序写 values"
    assert rows["银行存款"]["values"] == [0, 0], "附注单元格人工 / 锁定模式保留"
    assert rows["合计"]["values"] == [390 + 0 + 0 + 0 + 5, 203], "合计按附注实际行重算"
    end, prior = (by_addr(result)[f"note://五、1/货币资金/银行存款.{p}"] for p in ("end", "prior"))
    assert (end.action, prior.action) == ("keep_manual", "keep_locked")
    assert "人工填写" in end.reason and "锁定" in prior.reason
    # 去掉附注标记后下次推送即跟随（推送状态里记下的 manual / locked 不冒充附注标记）
    async with env.factory() as db:
        note = await db.get(DisclosureNote, (await env.note("五、1")).id)
        td = json.loads(json.dumps(note.table_data))
        _main(td)["银行存款"]["_cell_modes"] = {}
        note.table_data = td
        await db.commit()
    await env.push("WORKPAPER_SAVED", wp_id=env.wp_id)
    assert _main((await env.note("五、1")).table_data)["银行存款"]["values"] == [120, 100]



# ── 年度 / 触发范围 / 失败留痕 / 防回环 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_non_audit_year_is_refused(env):
    """底稿 / 附注只属于项目审计年度；上年试算表（比较数导入）的重算事件不得推进本年底稿。"""
    await env.seed_entries(base_entries())
    before = await env.entries()
    async with env.factory() as db:
        with pytest.raises(push.PushActionError, match="审计年度"):
            await push.run_and_commit(db, project_id=env.pid, year=YEAR - 1, trigger="manual")
        result = await push.run_and_commit(db, project_id=env.pid, year=YEAR - 1, trigger="TRIAL_BALANCE_UPDATED")
    assert result.run_id is None and "审计年度" in result.warnings[0]
    assert await env.entries() == before and await env.runs() == [] and env.broadcasts == []


@pytest.mark.asyncio
async def test_workpaper_saved_runs_only_its_rules_and_only_that_workpaper(env):
    await env.seed_entries(base_entries())
    result = await env.push("WORKPAPER_SAVED", wp_id=env.wp_id)
    rules = {i.rule_id for i in result.items}
    # 源值规则只挂在 TRIAL_BALANCE_UPDATED / manual：底稿保存只重算派生与附注
    assert not any(r.startswith(("E1.cash_rows", "E1.tb_amount", "E1.hall_adj")) for r in rules)
    assert "E1-adj-total-1001" in result.changed_items
    other = await env.push("WORKPAPER_SAVED", wp_id=uuid.uuid4())
    assert other.run_id is None and other.items == [], "事件指向别的底稿：不跑、不留运行记录"


@pytest.mark.asyncio
async def test_failure_rolls_back_and_leaves_a_failed_run(env):
    await env.seed_entries(base_entries())
    before = await env.entries()

    async def boom(db, project_id, year, wp):
        raise RuntimeError("四表取数失败")

    env_sources = E1Binding.load_sources
    try:
        E1Binding.load_sources = staticmethod(boom)
        with pytest.raises(RuntimeError, match="四表取数失败"):
            await env.push()
    finally:
        E1Binding.load_sources = env_sources
    assert await env.entries() == before, "取数失败不得拿「失败的空」推送"
    [run] = await env.runs()
    assert run.status == "failed" and "四表取数失败" in run.detail["error"]
    assert env.broadcasts == []


@pytest.mark.asyncio
async def test_engine_writes_never_publish_workpaper_saved(env, monkeypatch):
    """防回环：引擎写入只广播 formula.pushed，不发 WORKPAPER_SAVED（否则保存事件 → 推送 → 保存事件……）。"""
    from app.services.event_bus import event_bus

    published: list = []

    async def record(payload):
        published.append(payload)

    monkeypatch.setattr(event_bus, "publish", record)
    monkeypatch.setattr(event_bus, "publish_immediate", record)
    await env.seed_entries(base_entries())
    await env.add_note("五、1", _f2_note())
    result = await env.push()
    assert result.written_count > 0 and result.note_sections == ["五、1"]
    assert published == [] and [e for e, _ in env.broadcasts] == ["formula.pushed"]



@pytest.mark.asyncio
async def test_placeholder_row_zero_to_zero_is_not_a_write(env):
    """composable 占位行（全 0、无备注）金额视为空 ⇒ 判定为写；但四表也是 0 时存储值不变：
    不落库、不推进版本、不进「后台已更新」（否则每次推送都让打开底稿的用户看到假提示条）。"""
    placeholder = json.dumps([{"id": "fixed-rmb", "currency": "人民币", "opening": 0, "increase": 0,
                               "decrease": 0, "fxRate": 1, "adjustment": 0, "note": ""}],
                             ensure_ascii=False, separators=(",", ":"))
    await env.seed_entries({e1_calc.CASH_ROWS_KEY: placeholder})
    leaf = env.sources.four_table_prefill["cash"][0]
    leaf.update(opening=0, increase=0, decrease=0, ending=0)
    result = await env.push()
    row_items = [i for i in result.items if i.addr_id and "E1-cash-detail-rows[" in i.addr_id]
    assert [i.action for i in row_items] == ["unchanged"] * 3
    assert e1_calc.CASH_ROWS_KEY not in result.changed_items
    async with env.factory() as db:
        version = (await db.execute(sa.text(
            "SELECT content_version FROM checklist_responses WHERE item_id = :i"
        ), {"i": e1_calc.CASH_ROWS_KEY})).scalar_one()
    assert version == 1 and (await env.entries())[e1_calc.CASH_ROWS_KEY] == placeholder
    # 反向：四表非 0 时同一占位行照常写入（占位行不是用户数据）
    leaf.update(opening=5)
    result = await env.push()
    assert by_addr(result)[CASH_OPENING].action == "write"
    assert e1_calc.CASH_ROWS_KEY in result.changed_items
