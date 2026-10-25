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
from types import SimpleNamespace

import pytest
import pytest_asyncio
import sqlalchemy as sa

from app.models.report_models import DisclosureNote, NoteStatus
from app.services.formula_push import engine as push
from app.services.formula_push import panel
from app.services.formula_push.bindings import e1_calc, register_binding
from app.services.formula_push.bindings.e1 import E1Binding, TargetSkip, WorkpaperTarget
from app.services.formula_push.rules import PushRule, PushSource, PushTarget
from tests._formula_push_env import (
    CASH_OPENING, TB_ENDING, YEAR, Env, base_entries, by_addr, cash_rows, make_env, make_sources,
)


@pytest_asyncio.fixture
async def env(monkeypatch):
    async with make_env(monkeypatch) as e:
        yield e


async def _add_workpaper(env: Env, wp_code: str) -> uuid.UUID:
    """在共享 SQLite 夹具中增加一张编码底稿，供底稿级隔离测试使用。"""
    idx_id, wp_id = uuid.uuid4(), uuid.uuid4()
    async with env.factory() as db:
        await db.execute(sa.text(
            "INSERT INTO wp_index (id, project_id, wp_code) VALUES (:i, :p, :c)"
        ), {"i": str(idx_id), "p": str(env.pid), "c": wp_code})
        await db.execute(sa.text(
            "INSERT INTO working_paper (id, project_id, wp_index_id) VALUES (:w, :p, :i)"
        ), {"w": str(wp_id), "p": str(env.pid), "i": str(idx_id)})
        await db.commit()
    return wp_id


async def _workpaper_item_count(env: Env, wp_id: uuid.UUID) -> int:
    async with env.factory() as db:
        return int((await db.execute(sa.text(
            "SELECT COUNT(*) FROM checklist_responses WHERE wp_id = :w"
        ), {"w": str(wp_id)})).scalar_one())


async def _install_isolation_plan(env: Env, monkeypatch, *, failing_code: str | None = None,
                                  with_note: bool = False) -> dict[str, uuid.UUID]:
    """安装两个真实底稿 + 临时 binding，专门验证底稿保存点隔离。"""
    codes = ("F1", "F2")
    wp_ids = {code: await _add_workpaper(env, code) for code in codes}
    async with env.factory() as db:
        for code in codes:
            await db.execute(sa.text(
                "INSERT INTO checklist_responses "
                "(id, project_id, wp_id, item_id, remark, updated_at) "
                "VALUES (:id, :p, :w, :i, :r, :t)"
            ), {
                "id": str(uuid.uuid4()), "p": str(env.pid), "w": str(wp_ids[code]),
                "i": f"{code}-value", "r": f"{code}-old",
                "t": "2026-09-01 08:00:00.000000+00:00",
            })
        await db.commit()

    class _Binding:
        def __init__(self, code: str):
            self.wp_code = code
            self.account_prefixes = ("999",)
            self.derivations = frozenset()

        async def load_sources(self, db, project_id, year, wp_id):
            if self.wp_code == failing_code:
                await db.execute(sa.text(
                    "UPDATE checklist_responses SET remark = :r WHERE wp_id = :w AND item_id = :i"
                ), {"r": f"{self.wp_code}-poison", "w": str(wp_id), "i": f"{self.wp_code}-value"})
                await db.flush()
                raise RuntimeError(f"{self.wp_code} 取数失败")
            return SimpleNamespace(warnings=[], template_type=None)

        def workpaper_targets(self, rule, entries, sources):
            item_id = f"{self.wp_code}-value"
            return [WorkpaperTarget(
                rule_id=rule.rule_id, policy=rule.policy,
                addr_id=f"{self.wp_code}/{self.wp_code}/{item_id}", item_id=item_id,
                formula_value=f"{self.wp_code}-new", current_value=entries.get(item_id),
            )], []

        def apply(self, entries, target, value):
            value = str(value)
            changed = entries.get(target.item_id) != value
            entries[target.item_id] = value
            return changed

        def entry_warnings(self, entries):
            return []

    bindings = {code: _Binding(code) for code in codes}
    rules = []
    for code in codes:
        rules.append(PushRule(
            rule_id=f"{code}.value", page_key=f"workpaper:{code}", stage="source", policy="system",
            target=PushTarget(domain="workpaper", wp_code=code, sheet_code=code,
                              item_id=f"{code}-value", fields=("value",)),
            source=PushSource(kind="derivation", name="fake"), triggers=("manual",), description="隔离测试",
        ))
        if with_note:
            rules.append(PushRule(
                rule_id=f"{code}.note", page_key=f"workpaper:{code}", stage="note", policy="editable",
                target=PushTarget(domain="note", section_by_template=(("listed", "五、1"),), table="测试表"),
                source=PushSource(kind="derivation", name="fake"), triggers=("manual",), description="隔离测试附注",
            ))

    monkeypatch.setattr(push, "supported_wp_codes", lambda: codes)
    monkeypatch.setattr(push, "load_push_rules", lambda: tuple(rules))
    monkeypatch.setattr(push, "get_binding", lambda code: bindings[code])

    async def find_workpapers(db, project_id, wp_code):
        return [push._Paper(id=wp_ids[wp_code], status="draft")]

    monkeypatch.setattr(push, "_find_workpapers", find_workpapers)
    return wp_ids



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

    async def read_then_user_saves(db, wp_id, wp_code, **kwargs):
        snap = await real_read(db, wp_id, wp_code, **kwargs)
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


@pytest.mark.asyncio
async def test_single_field_note_rule_only_writes_declared_column(env, monkeypatch):
    """规则只声明 end_amount 时，附注 prior_amount 必须保持原值（守卫引擎遍历 rule.target.fields）。"""
    await env.seed_entries(base_entries())
    await env.add_note("五、1", _f2_note())
    # 临时把附注规则的 fields 改为只含 end_amount
    real_load = push.load_push_rules

    def patched_rules():
        rules = list(real_load())
        patched = []
        for r in rules:
            if r.rule_id == "E1.note.main_rows":
                from app.services.formula_push.rules import PushRule, PushTarget
                new_target = PushTarget(
                    domain=r.target.domain, rows=r.target.rows,
                    fields=("end_amount",),
                    section_by_template=r.target.section_by_template,
                    table=r.target.table,
                )
                r = PushRule(
                    rule_id=r.rule_id, page_key=r.page_key, stage=r.stage, policy=r.policy,
                    target=new_target, source=r.source, triggers=r.triggers, description=r.description,
                )
            patched.append(r)
        return tuple(patched)

    monkeypatch.setattr(push, "load_push_rules", patched_rules)
    result = await env.push()
    rows = _main((await env.note("五、1")).table_data)
    # end_amount 被推送更新
    assert rows["库存现金"]["end_amount"] == 390
    # prior_amount 保持原值（_f2_note 初始值 = 1）
    assert rows["库存现金"]["prior_amount"] == 1, (
        "单字段规则不声明 prior_amount，附注期初列必须保持原值"
    )
    # 合计行也只更新 end_amount
    assert rows["合计"]["end_amount"] == 390 + 120 + 0 + 0 + 5
    assert rows["合计"]["prior_amount"] == 1, "合计行的 prior_amount 也必须保持原值"
    # 确认 items 中无 prior 期间的记录
    note_items = [i for i in result.items if i.domain == "note"]
    assert all(".prior" not in (i.addr_id or "") for i in note_items), (
        "单字段规则不应产生 prior 期间的推送记录"
    )


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
async def test_workpaper_failure_isolated_and_later_workpaper_commits(env, monkeypatch):
    wp_ids = await _install_isolation_plan(env, monkeypatch, failing_code="F1")
    result = await env.push()

    assert result.status == "partial"
    assert result.workpapers[0]["status"] == "failed"
    assert "F1 取数失败" in result.workpapers[0]["reason"]
    assert any("已回滚本底稿写入" in warning for warning in result.warnings)
    assert result.wp_ids == [str(wp_ids["F2"])]
    assert [item.addr_id for item in result.items] == ["F2/F2/F2-value"]
    async with env.factory() as db:
        rows = (await db.execute(sa.text(
            "SELECT wp_id, item_id, remark FROM checklist_responses ORDER BY wp_id"
        ))).all()
    assert {(str(wp), item, remark) for wp, item, remark in rows} == {
        (str(wp_ids["F1"]), "F1-value", "F1-old"),
        (str(wp_ids["F2"]), "F2-value", "F2-new"),
    }
    states = await env.states()
    assert set(states) == {"F2/F2/F2-value"}
    [run] = await env.runs()
    assert run.status == "partial"
    assert run.detail["wp"] == result.workpapers
    assert [event for event, _ in env.broadcasts] == ["formula.pushed"]


@pytest.mark.asyncio
async def test_successful_workpaper_remains_when_later_workpaper_fails(env, monkeypatch):
    wp_ids = await _install_isolation_plan(env, monkeypatch, failing_code="F2")
    result = await env.push()

    assert result.status == "partial"
    assert [paper["status"] for paper in result.workpapers] == ["pushed", "failed"]
    async with env.factory() as db:
        rows = (await db.execute(sa.text(
            "SELECT wp_id, item_id, remark FROM checklist_responses ORDER BY wp_id"
        ))).all()
    assert {(str(wp), item, remark) for wp, item, remark in rows} == {
        (str(wp_ids["F1"]), "F1-value", "F1-new"),
        (str(wp_ids["F2"]), "F2-value", "F2-old"),
    }
    assert set(await env.states()) == {"F1/F1/F1-value"}
    assert result.changed_items == ["F1-value"]


@pytest.mark.asyncio
async def test_partial_failure_dry_run_leaves_no_persistence_or_broadcast(env, monkeypatch):
    await _install_isolation_plan(env, monkeypatch, failing_code="F1")
    before = await env.entries()
    result = await env.push(dry_run=True)

    assert result.dry_run and result.run_id is None and result.status == "partial"
    assert any(paper["status"] == "failed" for paper in result.workpapers)
    assert await env.entries() == before
    assert await env.states() == {} and await env.runs() == [] and env.broadcasts == []


@pytest.mark.asyncio
async def test_note_failure_rolls_back_workpaper_cas_write(env, monkeypatch):
    """附注阶段失败时，已完成的底稿 CAS 写入也必须随底稿保存点回滚。"""
    await env.seed_entries(base_entries())
    await env.add_note("五、1", _f2_note())
    before = await env.entries()
    original_write_cell = push.note_writer.write_cell

    def write_then_fail(*args, **kwargs):
        original_write_cell(*args, **kwargs)
        raise RuntimeError("附注写入失败")

    monkeypatch.setattr(push.note_writer, "write_cell", write_then_fail)
    result = await env.push()

    assert result.status == "partial"
    assert result.workpapers[0]["status"] == "failed"
    assert "附注写入失败" in result.workpapers[0]["reason"]
    assert await env.entries() == before
    assert (await env.note("五、1")).table_data == _f2_note()
    assert await env.states() == {}


@pytest.mark.asyncio
async def test_failure_rolls_back_and_records_partial_run(env):
    await env.seed_entries(base_entries())
    before = await env.entries()

    async def boom(db, project_id, year, wp):
        raise RuntimeError("四表取数失败")

    env_sources = E1Binding.load_sources
    try:
        E1Binding.load_sources = staticmethod(boom)
        result = await env.push()
    finally:
        E1Binding.load_sources = env_sources

    assert result.status == "partial"
    assert await env.entries() == before, "取数失败不得拿「失败的空」推送"
    assert result.workpapers[0]["status"] == "failed"
    assert "四表取数失败" in result.workpapers[0]["reason"]
    [run] = await env.runs()
    assert run.status == "partial"
    assert run.detail["wp"][0]["status"] == "failed"
    assert "四表取数失败" in run.detail["wp"][0]["reason"]
    assert env.broadcasts == [("formula.pushed", result.summary())]


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


@pytest.mark.asyncio
@pytest.mark.parametrize("codes, expected", [
    (frozenset({"E1"}), ["E1"]),
    (frozenset({"K1"}), ["K1"]),
    (frozenset({"E1", "K1"}), ["E1", "K1"]),
    (None, ["E1", "K1"]),
    (frozenset(), []),
    (frozenset({"Z9"}), []),
], ids=["e1-only", "k1-only", "both", "all", "empty", "unknown"])
async def test_execute_filters_plan_to_explicit_codes(monkeypatch, codes, expected):
    """显式 codes 只允许命中的 binding 进入执行计划；None 仍保留旧的全量语义。"""
    seen: list[str] = []

    class FakeDb:
        def add(self, value):
            self.run_row = value

        async def flush(self):
            return None

        async def begin_nested(self):
            class Savepoint:
                async def commit(self):
                    return None

                async def rollback(self):
                    return None

            return Savepoint()

    async def fake_find_workpapers(db, project_id, wp_code):
        return [push._Paper(id=uuid.uuid4(), status="draft")]

    async def fake_push_workpaper(ctx, *, wp_code, binding, rules, paper, push_note=True):
        seen.append(wp_code)

    async def resolved_audit_year(db, project_id):
        return True, 2025

    async def load_states(db, project_id, year):
        return {}

    async def save_states(ctx, run_id):
        return None

    monkeypatch.setattr(push, "_project_audit_year", resolved_audit_year)
    monkeypatch.setattr(push, "load_push_rules", lambda: ())
    monkeypatch.setattr(push, "supported_wp_codes", lambda: ("E1", "K1"))
    monkeypatch.setattr(push, "rules_for", lambda rules, *, wp_code, trigger: (wp_code,))
    monkeypatch.setattr(push, "_find_workpapers", fake_find_workpapers)
    monkeypatch.setattr(push, "get_binding", lambda wp_code: wp_code)
    monkeypatch.setattr(push, "_load_states", load_states)
    monkeypatch.setattr(push, "_save_states", save_states)
    monkeypatch.setattr(push, "_push_workpaper", fake_push_workpaper)

    db = FakeDb()
    await push._execute(
        db,
        project_id=uuid.uuid4(),
        year=2025,
        trigger="TRIAL_BALANCE_UPDATED",
        triggered_by=None,
        wp_id=None,
        codes=codes,
        force=frozenset(),
    )
    assert seen == expected



# ── 多册隔离（Task 5：Z9 声明 ("Z9","Z9-1") 两册、缺册跳过、owner note、adopt 分册隔离）─


async def _install_multi_paper_plan(
    env: Env, monkeypatch, *, missing_subcode: bool = False, failing_code: str | None = None,
) -> dict[str, uuid.UUID]:
    """安装 Z9 双册底稿 + binding + 规则，验证多册隔离。

    两册都有同名条目 ``Z9-value``（按 wp_id 各自读取），一条规则写该条目；
    地址重映射后主册地址 ``Z9/Z9/Z9-value``、分册地址 ``Z9-1/Z9/Z9-value``，状态不串。
    """
    main, sub = "Z9", "Z9-1"
    codes = (main,) if missing_subcode else (main, sub)
    wp_ids = {code: await _add_workpaper(env, code) for code in codes}
    async with env.factory() as db:
        for code in codes:
            await db.execute(sa.text(
                "INSERT INTO checklist_responses "
                "(id, project_id, wp_id, item_id, remark, updated_at) "
                "VALUES (:id, :p, :w, :i, :r, :t)"
            ), {
                "id": str(uuid.uuid4()), "p": str(env.pid), "w": str(wp_ids[code]),
                "i": "Z9-value", "r": f"{code}-old",
                "t": "2026-09-01 08:00:00.000000+00:00",
            })
        await db.commit()

    class _Z9Binding:
        wp_code = main
        account_prefixes = ("9901",)
        derivations = frozenset()
        four_table_slots = frozenset()
        tb_columns = frozenset({"期末余额"})
        paper_codes = (main, sub)

        async def load_sources(self, db, project_id, year, wp_id):
            if failing_code and any(
                str(wp_ids.get(c)) == str(wp_id) for c in [failing_code] if c in wp_ids
            ):
                raise RuntimeError(f"{failing_code} 取数失败")
            return SimpleNamespace(warnings=[], template_type=None)

        def workpaper_targets(self, rule, entries, sources):
            item_id = rule.target.item_id
            current = entries.get(item_id)
            return [WorkpaperTarget(
                rule_id=rule.rule_id, policy=rule.policy,
                addr_id=f"{main}/{main}/{item_id}", item_id=item_id,
                formula_value=f"{item_id}-new", current_value=current,
            )], []

        def apply(self, entries, target, value):
            changed = entries.get(target.item_id) != str(value)
            entries[target.item_id] = str(value)
            return changed

        def note_rows(self, entries, template_type, rule):
            return []

        def entry_warnings(self, entries):
            return []

    binding = _Z9Binding()
    rules = [PushRule(
        rule_id=f"Z9.value", page_key=f"workpaper:{main}", stage="source", policy="system",
        target=PushTarget(domain="workpaper", wp_code=main, sheet_code=main,
                          item_id="Z9-value", fields=("value",)),
        source=PushSource(kind="derivation", name="fake"), triggers=("manual",),
        description="多册隔离测试",
    )]

    monkeypatch.setattr(push, "supported_wp_codes", lambda: (main,))
    monkeypatch.setattr(push, "load_push_rules", lambda: tuple(rules))
    monkeypatch.setattr(push, "get_binding", lambda code: binding)

    return wp_ids


@pytest.mark.asyncio
async def test_dual_paper_both_pushed_with_isolated_state_addresses(env, monkeypatch):
    """Z9 声明 ("Z9","Z9-1") ⇒ 两张底稿都推；状态地址首段按实际册码隔离。"""
    wp_ids = await _install_multi_paper_plan(env, monkeypatch)
    result = await env.push()

    assert result.status == "succeeded"
    assert len(result.workpapers) == 2
    assert {p["paper_code"] for p in result.workpapers} == {"Z9", "Z9-1"}
    assert all(p["status"] == "pushed" for p in result.workpapers)
    # 同一条规则在两册各写一次
    assert result.written_count == 2
    assert set(result.wp_ids) == {str(wp_ids["Z9"]), str(wp_ids["Z9-1"])}

    states = await env.states()
    # 地址首段按实际册码隔离
    assert "Z9/Z9/Z9-value" in states
    assert "Z9-1/Z9/Z9-value" in states
    assert states["Z9/Z9/Z9-value"].wp_id == wp_ids["Z9"]
    assert states["Z9-1/Z9/Z9-value"].wp_id == wp_ids["Z9-1"]

    # CAS 真实落库：两册各自有 "Z9-value"-new
    async with env.factory() as db:
        rows = (await db.execute(sa.text(
            "SELECT wp_id, remark FROM checklist_responses WHERE item_id = 'Z9-value' ORDER BY wp_id"
        ))).all()
    assert {str(r[0]): r[1] for r in rows} == {
        str(wp_ids["Z9"]): "Z9-value-new",
        str(wp_ids["Z9-1"]): "Z9-value-new",
    }


@pytest.mark.asyncio
async def test_missing_subcode_is_skipped_with_reason(env, monkeypatch):
    """声明了分册 Z9-1 但该底稿不存在 ⇒ 跳过并说明，不报错。"""
    wp_ids = await _install_multi_paper_plan(env, monkeypatch, missing_subcode=True)
    result = await env.push()

    assert result.status == "succeeded"
    assert len(result.workpapers) == 1
    assert result.workpapers[0]["paper_code"] == "Z9"
    skips = [i for i in result.items if i.action == "skipped" and "Z9-1" in (i.reason or "")]
    assert len(skips) == 1 and "不存在" in skips[0].reason


@pytest.mark.asyncio
async def test_first_paper_failure_does_not_break_second_paper(env, monkeypatch):
    """双册中首张取数失败 ⇒ 该册零写入，第二册照常。"""
    wp_ids = await _install_multi_paper_plan(env, monkeypatch, failing_code="Z9")
    result = await env.push()

    assert result.status == "partial"
    assert result.workpapers[0]["status"] == "failed"
    assert result.workpapers[1]["status"] == "pushed"
    assert result.wp_ids == [str(wp_ids["Z9-1"])]
    states = await env.states()
    assert "Z9/Z9/Z9-value" not in states, "失败底稿不写状态"
    assert "Z9-1/Z9/Z9-value" in states



@pytest.mark.asyncio
async def test_dual_paper_frozen_owner_skips_note_but_second_paper_pushes(env, monkeypatch):
    """Z9 双册首册（owner）frozen ⇒ 附注不推，第二册底稿照常。"""
    wp_ids = await _install_multi_paper_plan(env, monkeypatch)
    # 把首册改成 frozen
    async with env.factory() as db:
        await db.execute(sa.text(
            "UPDATE working_paper SET status = 'review_passed' WHERE id = :w"
        ), {"w": str(wp_ids["Z9"])})
        await db.commit()
    result = await env.push()

    assert result.status == "succeeded"
    wp_statuses = {p["paper_code"]: p["status"] for p in result.workpapers}
    assert wp_statuses == {"Z9": "frozen", "Z9-1": "pushed"}
    # 首册 frozen 跳过：零写入
    assert result.wp_ids == [str(wp_ids["Z9-1"])]
    states = await env.states()
    assert "Z9/Z9/Z9-value" not in states, "frozen 底稿不产生状态"
    assert "Z9-1/Z9/Z9-value" in states
    # 附注不推（owner = papers[0] = frozen）
    assert result.note_sections == []
