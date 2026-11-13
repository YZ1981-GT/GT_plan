"""受限自动写方逐个接入写入归属判定（spec formula-writer-ownership-and-stale R1b，design §13.4）。

每个受限 writer 至少一条「该字段被拒、其他字段照写」：公式推送 / 底稿披露同步（含 HTML 入口）/ 模板绑定取数 /
报表更新 / 生成合并 / 报表同步 / 公式运行。推送与披露同步走生产引擎（SQLite 真 ORM，E1 → 上市 五、1「货币资金」）；
模板绑定三个入口与报表同步、公式运行用打桩会话，只替换取数与推送状态，判定走生产代码。
"""
from __future__ import annotations

import copy
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.report_models import ContentType, DisclosureNote, SourceTemplate
from app.services import note_write_ownership as own
from app.services import wp_disclosure_sync_service as sync_mod
from app.services.disclosure_engine import DisclosureEngine
from app.services.formula_runtime.adapters.note import NoteMutationAdapter
from app.services.formula_runtime.contracts import CanonicalFormulaTarget, FormulaMutation
from app.services.note_formula_push_guard import OwnedPushCell, PushOwnershipCache
from app.services.note_write_ownership import CELL_PREFIX, OwnershipMatrix
from app.services.report_note_sync_service import LinkTarget, ReportNoteSyncService
from tests._formula_push_env import YEAR, base_entries, make_env

CASH = "货币资金"
COLS = [
    {"key": "label", "flat": True, "label": "项目", "is_label": True},
    {"key": "end_amount", "label": "期末余额", "format": "amount"},
    {"key": "prior_amount", "label": "上年年末余额", "format": "amount"},
]


def _without(entry: tuple[str, str], chapter=("listed", "五、1")) -> OwnershipMatrix:
    """真实矩阵去掉一条条目（模拟矩阵缺行）。"""
    real = own.load_matrix()
    chapters = {k: dict(v) for k, v in real.chapters.items()}
    chapters[chapter].pop(entry)
    return OwnershipMatrix(chapters=chapters, identity=real.identity)


def _workpaper_note() -> dict:
    return {
        "_source": "workpaper", "_last_sync_wp_id": "底稿同步过", "_sub_table_columns": {CASH: COLS},
        "sub_table_data": {CASH: [
            {"label": "库存现金", "end_amount": 1, "prior_amount": 1},
            {"label": "银行存款", "end_amount": 0, "prior_amount": 0},
            {"label": "手工加的行", "end_amount": 5, "prior_amount": 0},
            {"label": "合计", "is_total": True, "end_amount": 6, "prior_amount": 1},
        ]},
    }


def _rows(td: dict) -> dict[str, dict]:
    return {r["label"]: r for r in td["sub_table_data"][CASH]}


# ─── formula_push ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_formula_push_skips_undeclared_field_and_writes_declared_one(monkeypatch):
    async with make_env(monkeypatch) as env:
        await env.seed_entries(base_entries())
        await env.add_note("五、1", _workpaper_note())
        matrix = _without((CASH, CELL_PREFIX + "prior_amount"))
        monkeypatch.setattr(own, "load_matrix", lambda path=None: matrix)
        result = await env.push(skip_note_followup=True)
        rows = _rows((await env.note("五、1")).table_data)
    assert rows["库存现金"]["end_amount"] not in (None, 1), "矩阵声明的期末格照写"
    assert rows["库存现金"]["prior_amount"] == 1 and rows["合计"]["prior_amount"] == 1, "期初格被拒、保持原值"
    blocked = [b for b in result.blocked_writes if b["field"] == CELL_PREFIX + "prior_amount"]
    assert blocked and {(b["writer_id"], b["reason_code"], b["table"]) for b in blocked} == {
        ("formula_push", "unknown_entry", CASH)}
    assert {b["row"] for b in blocked} >= {"库存现金", "合计"}
    assert not any(b["field"] == CELL_PREFIX + "end_amount" for b in result.blocked_writes)
    assert result.blocked_count == len(blocked) and result.summary()["blocked_writes"]
    assert any(i.action == "blocked" for i in result.items) and result.skipped_count >= len(blocked)


@pytest.mark.asyncio
async def test_formula_push_title_fallback_into_undeclared_chapter_is_blocked(monkeypatch):
    """章节号对不上、按标题改投到别的章节：矩阵没有那一章的推送条目 ⇒ 不写（原来照写）。"""
    async with make_env(monkeypatch) as env:
        await env.seed_entries(base_entries())
        await env.add_note("五、1", _workpaper_note(), title="政府补助")
        await env.add_note("五、3", _workpaper_note(), title=CASH)
        result = await env.push(skip_note_followup=True)
        moved = _rows((await env.note("五、3")).table_data)
    assert moved["库存现金"]["end_amount"] == 1, "改投的章节一格不写"
    assert result.blocked_writes and {b["section"] for b in result.blocked_writes} == {"五、3"}
    assert {b["reason_code"] for b in result.blocked_writes} == {"unknown_entry"}


def test_blocked_push_items_count_as_skipped_in_the_run_record():
    """该格没写：运行记录的跳过数含归属拒写（健康度 total = 写入 + 未变 + 保留 + 跳过 = 项数）。"""
    from app.services.formula_push.results import BLOCKED, PushItem, RunResult

    result = RunResult(project_id=uuid.uuid4(), year=YEAR, trigger="manual", status="succeeded")
    result.items.append(PushItem("r", "note", "note", "note://x", BLOCKED, reason="写入归属矩阵没有这一格"))
    result.blocked_writes.append({"section": "五、1", "reason_code": "unknown_entry"})
    assert (result.skipped_count, result.blocked_count) == (1, 1)
    assert result.summary()["blocked_count"] == 1
    assert result.detail()["blocked_writes"] == [{"section": "五、1", "reason_code": "unknown_entry"}]


# ─── workpaper_sync / workpaper_html_sync ────────────────────────────────────


async def _pushed_env(monkeypatch):
    env_cm = make_env(monkeypatch)
    env = await env_cm.__aenter__()
    await env.seed_entries(base_entries())
    await env.add_note("五、1", _workpaper_note())
    await env.push()
    env.pushed = _rows((await env.note("五、1")).table_data)
    env.cm = env_cm
    return env


async def _sync(env, rows: list[dict], section="五、1", **kw) -> dict:
    async with env.factory() as db:
        return await sync_mod.sync_from_workpaper(
            db, env.pid, wp_id=env.wp_id, sheet_name="附注披露信息(上市公司)", section_id=section,
            sub_table_data={CASH: rows}, current_standard="listed_standalone",
            user=SimpleNamespace(id=uuid.uuid4()), year=YEAR, sub_table_columns={CASH: COLS}, **kw,
        )


def _stale(env) -> list[dict]:
    return [
        {"label": "库存现金", "end_amount": 999, "prior_amount": env.pushed["库存现金"]["prior_amount"]},
        {"label": "银行存款", "end_amount": env.pushed["银行存款"]["end_amount"],
         "prior_amount": env.pushed["银行存款"]["prior_amount"]},
        {"label": "手工加的行", "end_amount": 7, "prior_amount": 0},
        {"label": "合计", "is_total": True, "end_amount": 1500, "prior_amount": 0},
    ]


@pytest.mark.asyncio
async def test_workpaper_sync_keeps_pushed_cell_and_writes_other_fields(monkeypatch):
    env = await _pushed_env(monkeypatch)
    try:
        result = await _sync(env, _stale(env))
        rows = _rows((await env.note("五、1")).table_data)
    finally:
        await env.cm.__aexit__(None, None, None)
    pushed = env.pushed["库存现金"]["end_amount"]
    assert rows["库存现金"]["end_amount"] == pushed, "推送写定的期末格被拒，保持审定数"
    assert rows["手工加的行"]["end_amount"] == 7, "其他字段照写"
    blocked = {(b["row"], b["field"]): b for b in result["blocked_writes"]}
    cell = blocked[("库存现金", CELL_PREFIX + "end_amount")]
    assert (cell["writer_id"], cell["owner_id"], cell["reason_code"]) == ("workpaper_sync", "formula_push", "pushed_cell")
    assert (cell["incoming"], cell["kept"]) == (999, pushed), "运行时对拍：底稿值与保留的推送值"
    assert ("合计", CELL_PREFIX + "end_amount") in blocked
    assert len(result["blocked_writes"]) == len(result["push_kept"])


@pytest.mark.asyncio
async def test_workpaper_sync_follows_matrix_when_push_entry_is_missing(monkeypatch):
    env = await _pushed_env(monkeypatch)
    try:
        matrix = _without((CASH, CELL_PREFIX + "end_amount"))
        monkeypatch.setattr(own, "load_matrix", lambda path=None: matrix)
        result = await _sync(env, _stale(env))
        rows = _rows((await env.note("五、1")).table_data)
    finally:
        await env.cm.__aexit__(None, None, None)
    assert rows["库存现金"]["end_amount"] == 999, "矩阵没声明期末格归推送 ⇒ 归底稿披露同步"
    assert not any(b["field"] == CELL_PREFIX + "end_amount" for b in result["blocked_writes"])


@pytest.mark.asyncio
async def test_workpaper_sync_does_not_take_over_never_synced_chapter_with_manual_values(monkeypatch):
    manual = {"name": CASH, "headers": ["项目", "期末余额", "期初余额"],
              "rows": [{"label": "库存现金", "values": [12.0, 3.0], "_cell_modes": {"0": "manual"}}]}
    td = {"_tables": [manual], "rows": copy.deepcopy(manual["rows"]), "headers": list(manual["headers"])}
    rows = [{"label": "库存现金", "end_amount": 40, "prior_amount": 4}]
    async with make_env(monkeypatch) as env:
        await env.add_note("五、1", copy.deepcopy(td))
        await env.add_note("五、99", copy.deepcopy(td), title="域外章节")
        result = await _sync(env, rows)
        stored = (await env.note("五、1")).table_data
        outside = await _sync(env, rows, section="五、99")
        outside_td = (await env.note("五、99")).table_data
    assert (result["skipped"], result["reason"], result["rows_synced"]) == (True, "manual_values_never_synced", 0)
    assert stored == td, "整节一格不写"
    assert [(b["writer_id"], b["owner_id"], b["table"], b["reason_code"]) for b in result["blocked_writes"]] == [
        ("workpaper_sync", "manual_editor", CASH, "manual_values_never_synced")]
    assert not outside.get("skipped") and outside_td["sub_table_data"][CASH][0]["end_amount"] == 40, \
        "域外章节沿用前端同步现状"


def _html_service(monkeypatch, section="五、1") -> sync_mod.WpDisclosureSyncService:
    service = sync_mod.WpDisclosureSyncService()

    async def mapping(db, wp_id, sheet):
        return {"section_id": section}

    async def no_audit(*args, **kwargs):
        return None

    monkeypatch.setattr(service, "_get_section_mapping", mapping)
    monkeypatch.setattr(service, "_write_audit_log", no_audit)
    monkeypatch.setattr(service, "_broadcast_synced", lambda *a, **k: None)
    return service


def _never_synced_manual_td() -> dict:
    manual = {"name": CASH, "headers": ["项目", "期末余额", "期初余额"],
              "rows": [{"label": "库存现金", "values": [12.0, 3.0], "_cell_modes": {"0": "manual"}}]}
    return {"_tables": [manual], "rows": copy.deepcopy(manual["rows"]), "headers": list(manual["headers"])}


@pytest.mark.asyncio
async def test_batch_sync_strict_mode_rolls_back_with_the_chinese_reason(monkeypatch):
    """批量严格模式整批回滚；对外原因写中文（原因代码只在 reason 字段里）。"""
    td = _never_synced_manual_td()
    item = {"section_id": "五、1", "sheet_name": "附注披露信息(上市公司)", "columns": {CASH: COLS},
            "sub_table_data": {CASH: [{"label": "库存现金", "end_amount": 40, "prior_amount": 4}]}}
    async with make_env(monkeypatch) as env:
        await env.add_note("五、1", copy.deepcopy(td))
        async with env.factory() as db:
            with pytest.raises(ValueError) as exc:
                await sync_mod.sync_batch_from_workpaper(
                    db, env.pid, wp_id=env.wp_id, current_standard="listed_standalone", items=[item],
                    user=SimpleNamespace(id=uuid.uuid4()), year=YEAR, require_all_applied=True)
        stored = (await env.note("五、1")).table_data
    assert str(exc.value) == f"附注 五、1 未同步：{own.reason_text(own.Verdict(False, 'manual_values_never_synced'), 'x')}"
    assert own.MANUAL_TAKEOVER_ADVICE in str(exc.value) and "manual_values_never_synced" not in str(exc.value)
    assert stored == td


@pytest.mark.asyncio
async def test_html_sync_does_not_take_over_never_synced_chapter_with_manual_values(monkeypatch):
    """HTML 入口与底稿披露同步同一 manual 策略；章节没记准则 ⇒ 按项目准则（上市）判交接域。"""
    td = _never_synced_manual_td()
    async with make_env(monkeypatch) as env:
        await env.add_note("五、1", copy.deepcopy(td))
        async with env.factory() as db:
            result = await _html_service(monkeypatch).sync_from_html(
                db, env.wp_id, "附注披露信息(上市公司)", {CASH: [{"label": "库存现金", "end_amount": 40}]},
                project_id=env.pid, user=SimpleNamespace(id=uuid.uuid4()), sub_table_columns={CASH: COLS},
                force=True)
        stored = (await env.note("五、1")).table_data
    assert (result["skipped"], result["reason"], result["synced"]) == (True, "manual_values_never_synced", False)
    assert stored == td, "整节一格不写"
    assert [(b["writer_id"], b["reason_code"], b["template_type"]) for b in result["blocked_writes"]] == [
        ("workpaper_html_sync", "manual_values_never_synced", "listed")]


@pytest.mark.asyncio
async def test_html_sync_keeps_pushed_cell_and_reports_it(monkeypatch):
    env = await _pushed_env(monkeypatch)
    try:
        service = _html_service(monkeypatch)
        async with env.factory() as db:
            result = await service.sync_from_html(
                db, env.wp_id, "附注披露信息(上市公司)", {CASH: _stale(env)}, project_id=env.pid,
                user=SimpleNamespace(id=uuid.uuid4()), sub_table_columns={CASH: COLS}, force=True)
        rows = _rows((await env.note("五、1")).table_data)
    finally:
        await env.cm.__aexit__(None, None, None)
    assert rows["库存现金"]["end_amount"] == env.pushed["库存现金"]["end_amount"]
    assert rows["手工加的行"]["end_amount"] == 7
    assert {(b["writer_id"], b["reason_code"]) for b in result["blocked_writes"]} == {
        ("workpaper_html_sync", "pushed_cell")}


# ─── 模板绑定取数三个入口 ─────────────────────────────────────────────────────

TB_END = {"source": "trial_balance", "field": "audited", "account_codes": ["1001"], "mode": "auto"}
TB_OPEN = {"source": "trial_balance", "field": "opening", "account_codes": ["1001"], "mode": "auto"}
BINDING = {"tables": [{
    "header_normalize": [{"semantic": "row_label"}, {"semantic": "closing_balance"}, {"semantic": "opening_balance"}],
    "rows": {"库存现金": {"binding": {"closing_balance": TB_END, "opening_balance": TB_OPEN}}},
}]}
PUSHED = {
    (0, 0, 0): OwnedPushCell(table=CASH, field="end_amount", label="库存现金", pushed=100.0),
    (0, 1, 0): OwnedPushCell(table=CASH, field="end_amount", label="合计", pushed=150.0),
}


def _template_td() -> dict:
    table = {"name": CASH, "headers": ["项目", "期末余额", "期初余额"], "rows": [
        {"label": "库存现金", "values": [100.0, 7.0], "_cell_modes": {"0": "auto", "1": "auto"},
         "_cell_meta": {"0": {"semantic": "closing_balance"}, "1": {"semantic": "opening_balance"}}},
        {"label": "合计", "values": [150.0, 7.0], "is_total": True, "row_type": "total"},
    ]}
    return {"_tables": [table], "headers": list(table["headers"]), "rows": copy.deepcopy(table["rows"]),
            "name": CASH}


def _note(td: dict, section="五、1") -> MagicMock:
    note = MagicMock(spec=DisclosureNote)
    note.note_section, note.content_type, note.table_data = section, ContentType.table, td
    note.source_template, note.is_local_override, note.is_deleted = SourceTemplate.listed, False, False
    return note


def _db(note) -> MagicMock:
    db = MagicMock()
    db.flush, db.rollback, db.add = AsyncMock(), AsyncMock(), MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [note]
    result.scalar_one_or_none.return_value = note
    db.execute = AsyncMock(return_value=result)
    return db


async def _owned(self, section, td):
    return dict(PUSHED) if section == "五、1" else {}


@pytest.mark.asyncio
async def test_binding_refill_skips_pushed_cells_and_refills_the_rest():
    td = _template_td()
    eng = DisclosureEngine(_db(_note(td)))

    async def dispatch(cell, ctx):
        return 999.0 if cell is TB_END else 888.0

    with (patch.object(eng, "_preload_data_for_notes", new_callable=AsyncMock),
          patch.object(eng, "_get_active_template_type", new=AsyncMock(return_value="listed")),
          patch.object(PushOwnershipCache, "cells", _owned),
          patch("app.services.note_template_bindings_loader.get_binding_for_section", return_value=BINDING),
          patch("app.services.note_source_resolvers.dispatch_resolver", side_effect=dispatch),
          patch("sqlalchemy.orm.attributes.flag_modified")):
        report = await eng.refill_sections(uuid.uuid4(), YEAR, ["五、1"], skip_manual=True)
    rows = td["_tables"][0]["rows"]
    assert rows[0]["values"] == [100.0, 888.0], "推送写定的期末格不刷，期初格照刷"
    assert rows[1]["values"] == [150.0, 888.0], "推送兜底写入的合计格不按明细重算，另一列照算"
    assert report.cells_updated == 1 and "五、1" in report.recomputed_sections
    got = {(b["row"], b["reason_code"], b["incoming"], b["kept"]) for b in report.blocked_writes}
    assert got == {("库存现金", "pushed_cell", 999.0, 100.0), ("合计", "pushed_cell", 100.0, 150.0)}
    assert {b["writer_id"] for b in report.blocked_writes} == {"binding_refill"}


@pytest.mark.asyncio
async def test_binding_refill_does_not_write_shadowed_template_tables():
    td = {**_template_td(), "_source": "workpaper", "_sub_table_columns": {CASH: COLS},
          "sub_table_data": {CASH: [{"label": "库存现金", "end_amount": 1, "prior_amount": 1}]}}
    before = copy.deepcopy(td)
    eng = DisclosureEngine(_db(_note(td)))
    with (patch.object(eng, "_preload_data_for_notes", new_callable=AsyncMock),
          patch.object(eng, "_get_active_template_type", new=AsyncMock(return_value="listed")),
          patch("app.services.note_template_bindings_loader.get_binding_for_section", return_value=BINDING),
          patch("app.services.note_source_resolvers.dispatch_resolver", new=AsyncMock(return_value=999.0)),
          patch("sqlalchemy.orm.attributes.flag_modified")):
        report = await eng.refill_sections(uuid.uuid4(), YEAR, ["五、1"], skip_manual=True)
    assert td == before and report.cells_updated == 0 and report.changed_sections == []
    assert [(b["reason_code"], b["owner_id"]) for b in report.blocked_writes] == [("inactive_container", "workpaper_sync")]


def _new_td() -> dict:
    td = _template_td()
    for table_rows in (td["_tables"][0]["rows"], td["rows"]):
        table_rows[0]["values"] = [111.0, 55.0]
        table_rows[1]["values"] = [222.0, 66.0]
    return td


TEMPLATE = {"note_section": "五、1", "section_title": CASH, "content_type": "table", "sort_order": 1,
            "table_template": {"rows": [{"label": "库存现金", "account_codes": ["1001"]}]}}


@pytest.mark.asyncio
async def test_update_note_values_holds_pushed_cells_and_merges_the_rest():
    note = _note(_template_td())
    eng = DisclosureEngine(_db(note))
    with (patch.object(eng, "_get_active_template_type", new=AsyncMock(return_value="listed")),
          patch.object(eng, "_load_templates", new=AsyncMock(return_value=[TEMPLATE])),
          patch.object(eng, "_build_section_table_data", new=AsyncMock(return_value=_new_td())),
          patch.object(PushOwnershipCache, "cells", _owned),
          patch("sqlalchemy.orm.attributes.flag_modified")):
        assert await eng.update_note_values(uuid.uuid4(), YEAR) == 1
    rows = note.table_data["_tables"][0]["rows"]
    # 推送写定格保留；明细期初照合并取新值；合计期初按合并后的明细重算（note_cell_merge：明细里有保留值时合计的自动格按
    # 明细重算 —— 推送写定格在合并里按 locked 语义保留，同样适用；新模板的合计 66 是按不含保留值的明细算的）
    assert [r["values"] for r in rows] == [[100.0, 55.0], [150.0, 55.0]], "推送写定格保留，其余照合并"
    assert note.table_data["rows"] == rows
    assert {(b["writer_id"], b["row"], b["incoming"], b["kept"]) for b in eng.blocked_writes} == {
        ("update_note_values", "库存现金", 111.0, 100.0), ("update_note_values", "合计", 222.0, 150.0)}


@pytest.mark.asyncio
async def test_generate_notes_merge_holds_pushed_cells_and_merges_the_rest():
    note = _note(_template_td())
    eng = DisclosureEngine(_db(note))
    with (patch.object(eng, "_load_templates", new=AsyncMock(return_value=[TEMPLATE])),
          patch.object(eng, "_preload_data_for_notes", new_callable=AsyncMock),
          patch.object(eng, "_build_section_table_data", new=AsyncMock(return_value=_new_td())),
          patch("app.services.note_formula_gray_service.is_note_formula_enabled", new=AsyncMock(return_value=False)),
          patch.object(PushOwnershipCache, "cells", _owned),
          patch("sqlalchemy.orm.attributes.flag_modified")):
        await eng.generate_notes(uuid.uuid4(), YEAR, "listed")
    rows = note.table_data["_tables"][0]["rows"]
    assert [r["values"] for r in rows] == [[100.0, 55.0], [150.0, 55.0]], "同报表更新：合计期初按合并后的明细重算"
    assert {(b["writer_id"], b["reason_code"]) for b in eng.blocked_writes} == {("generate_notes", "pushed_cell")}


# ─── report_sync ─────────────────────────────────────────────────────────────


def _report_note(section: str, values: list) -> MagicMock:
    td = {"headers": ["项目", "期末余额", "期初余额"], "name": CASH,
          "rows": [{"label": "合计", "values": list(values), "_cell_modes": {}}]}
    return _note(td, section=section)


@pytest.mark.asyncio
async def test_report_sync_is_rejected_in_handoff_chapters_and_writes_elsewhere():
    governed, outside = _report_note("五、1", [1.0, 2.0]), _report_note("五、99", [1.0, 2.0])
    report_row = SimpleNamespace(row_code="BS-001", current_period_amount=500)
    db = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(rowcount=1))  # 清过期（stale_state 一条 UPDATE）
    svc = ReportNoteSyncService(db)
    target = [LinkTarget(note_section="五、1", table_index=0, row_idx=0, col_idx=0, row_code="BS-001", origin="binding")]
    with (patch("app.services.report_note_sync_service.ReportNoteLinkage") as linkage,
          patch("app.services.note_validation_engine.NoteValidationEngine") as validator):
        linkage.return_value.report_targets_in_note.return_value = target
        validator.return_value.validate_all = AsyncMock(return_value={})
        result = await svc._sync_real(uuid.uuid4(), YEAR, [report_row], [governed, outside])
    assert governed.table_data["rows"][0]["values"] == [1.0, 2.0], "交接章节报表同步不改"
    assert outside.table_data["rows"][0]["values"] == [500.0, 2.0], "域外章节照写"
    assert result["cells_updated"] == 1
    assert [(b["section"], b["writer_id"], b["owner_id"], b["reason_code"]) for b in result["blocked_writes"]] == [
        ("五、1", "report_sync", "binding_refill", "owner_mismatch")]


def test_report_sync_gate_keeps_locked_cell_silently_and_writes_auto_cell():
    note = _report_note("五、99", [1.0, 2.0])
    note.table_data["rows"][0]["_cell_modes"] = {"0": "locked"}
    gate = own.WriteGate("report_sync", "listed", "五、99", note.table_data)
    targets = [LinkTarget(note_section="五、99", table_index=0, row_idx=0, col_idx=0, row_code="A", origin="binding"),
               LinkTarget(note_section="五、99", table_index=0, row_idx=0, col_idx=1, row_code="B", origin="binding")]
    td, written, matched = ReportNoteSyncService._apply_report_values(note, targets, {"A": 5.0, "B": 6.0}, gate=gate)
    assert td["rows"][0]["values"] == [1.0, 6.0] and written == 1 and matched == {"A", "B"}
    assert gate.blocked_writes == [], "锁定格保留不进回报"


# ─── formula_runtime_apply ───────────────────────────────────────────────────


def _mutation(section: str, row: str, column: str, after) -> FormulaMutation:
    target = CanonicalFormulaTarget(domain="note", project_id=PROJECT, year=YEAR, addr_id=f"note:{section}!{row}:{column}",
                                    locator={"section": section, "row": row, "column": column, "cell_type": "auto"})
    return FormulaMutation(target=target, before_value=None, after_value=after, expected_version=None)


PROJECT = uuid.uuid4()


def _runtime_session(note) -> MagicMock:
    session = MagicMock()
    session.flush = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = note
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_formula_runtime_skips_locked_target_and_applies_the_other():
    td = {"rows": {"r1": {"end": 1, "_cell_modes": {"end": "locked"}}, "r2": {"end": 2}}}
    note = SimpleNamespace(table_data=td, source_template=SourceTemplate.listed, updated_at=None)
    adapter = NoteMutationAdapter(_runtime_session(note))
    applied = await adapter.apply_many([_mutation("五、99", "r1", "end", 10), _mutation("五、99", "r2", "end", 20)])
    assert [a.target.locator["row"] for a in applied] == ["r2"]
    assert note.table_data["rows"]["r1"]["end"] == 1 and note.table_data["rows"]["r2"]["end"] == 20
    assert adapter.blocked_writes == []


@pytest.mark.asyncio
async def test_formula_runtime_is_rejected_in_handoff_chapter():
    td = {"rows": {"r1": {"end": 1}}}
    note = SimpleNamespace(table_data=td, source_template=SourceTemplate.listed, updated_at=None)
    adapter = NoteMutationAdapter(_runtime_session(note))
    applied = await adapter.apply_many([_mutation("五、1", "r1", "end", 10)])
    assert applied == [] and note.table_data == td
    assert [(b["writer_id"], b["owner_id"], b["reason_code"], b["addr_id"]) for b in adapter.blocked_writes] == [
        ("formula_runtime_apply", "binding_refill", "owner_mismatch", "note:五、1!r1:end")]


def test_template_type_mutation_guard_uses_the_note_own_template():
    """报表同步 / 公式运行按附注自己的准则判（``_current_standard`` 优先、``source_template`` 兜底）。"""
    note = SimpleNamespace(table_data={"_current_standard": "soe_standalone"}, source_template=SourceTemplate.listed)
    assert own.note_template_type(note) == "soe"
    assert own.note_template_type(replace_ns(note, table_data={})) == "listed"


def replace_ns(ns: SimpleNamespace, **kw) -> SimpleNamespace:
    return SimpleNamespace(**{**vars(ns), **kw})
