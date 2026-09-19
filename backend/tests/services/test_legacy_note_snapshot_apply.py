"""legacy 快照迁移**写入路径**的纯函数契约（Task 8.4）。

被测函数（全部纯函数，无 IO）：
- `build_migrated_table_data`：legacy `table_data` → `sub_table_data` 形态
- `build_rollback_table_data`：从 `_template_lineage._legacy_backup` 逆变换
- `_already_migrated` / `allowed_kinds` / `select_migratable`：幂等探针与安全闸

三消费者视角：迁移结果必须能被 `note_sub_table_projector.project_sub_tables()`
投影出与计划一致的表（漏 `_source` 会让整章渲染为空 = 比迁移前更糟）。

Spec: .kiro/specs/disclosure-note-follow-actual-content/ R3 / Task 8
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.note_sub_table_projector import project_sub_tables

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "fix" / "migrate_legacy_note_snapshots.py"
)
_spec = importlib.util.spec_from_file_location("_legacy_migrate_apply", _SCRIPT)
assert _spec and _spec.loader
mod = importlib.util.module_from_spec(_spec)
# 与 test_legacy_note_snapshot_plan 同理：@dataclass 需要模块已注册到 sys.modules
sys.modules["_legacy_migrate_apply"] = mod
_spec.loader.exec_module(mod)


# ════════════════════════════════════════════════════════════════════
# fixtures
# ════════════════════════════════════════════════════════════════════


def _cols(*labels: str) -> list[dict[str, Any]]:
    defs = [{"key": "label", "label": labels[0], "is_label": True, "flat": True}]
    defs += [{"key": f"c{i}", "label": lab, "flat": True} for i, lab in enumerate(labels[1:])]
    return defs


def _tpl(*names: str, with_columns: bool = True) -> list[dict[str, Any]]:
    return [
        {"name": n, "columns": _cols("项目", "期末余额") if with_columns else None}
        for n in names
    ]


def _legacy_table(name: str, n_rows: int, *, header_label_rows: int = 0) -> dict[str, Any]:
    rows: list[dict[str, Any]] = [
        {"label": f"{name}-r{i}", "c0": i} for i in range(n_rows)
    ]
    for _ in range(header_label_rows):
        rows.insert(0, {"label": "表头行", "row_type": "header_label"})
    return {"name": name, "headers": ["项目", "期末余额"], "rows": rows}


def _plan(table_data: dict[str, Any], template: list[dict[str, Any]] | None) -> Any:
    return mod.build_note_plan(
        note_id="n1",
        project="P",
        note_section="五、9",
        section_title="存货",
        table_data=table_data,
        template_tables=template,
    )


def _legacy_two_tables() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    td = {"_tables": [_legacy_table("存货分类", 3), _legacy_table("开发成本", 2)]}
    return td, _tpl("存货分类", "开发成本")


# ════════════════════════════════════════════════════════════════════
# 1~5：迁移结果形态
# ════════════════════════════════════════════════════════════════════


def test_sub_table_data_keyed_by_target_name_with_row_counts():
    """契约 1：`sub_table_data` 按目标表名建键，行数与计划一致。"""
    td, tpl = _legacy_two_tables()
    plan = _plan(td, tpl)
    new = mod.build_migrated_table_data(td, plan, tpl)

    assert list(new["sub_table_data"].keys()) == ["存货分类", "开发成本"]
    assert [len(v) for v in new["sub_table_data"].values()] == [3, 2]
    assert [t.row_count for t in plan.tables] == [3, 2]


def test_sub_table_columns_filled_from_template():
    """契约 2：`_sub_table_columns` 取自模板表的 `columns`。"""
    td, tpl = _legacy_two_tables()
    new = mod.build_migrated_table_data(td, _plan(td, tpl), tpl)

    assert set(new["_sub_table_columns"]) == {"存货分类", "开发成本"}
    assert new["_sub_table_columns"]["存货分类"] == _cols("项目", "期末余额")


def test_source_is_set_to_workpaper():
    """契约 3：`_source` 必须置 workpaper，否则投影器返回 None、整章渲染为空。"""
    td, tpl = _legacy_two_tables()
    new = mod.build_migrated_table_data(td, _plan(td, tpl), tpl)
    assert new["_source"] == "workpaper"


def test_legacy_backup_holds_original_rows_and_tables():
    """契约 4：备份完整保留原 `rows` + `_tables`。"""
    td = {
        "rows": [{"label": "top-a"}],
        "_tables": [_legacy_table("唯一表", 1)],
    }
    tpl = _tpl("唯一表")
    new = mod.build_migrated_table_data(td, _plan(td, tpl), tpl)

    backup = new["_template_lineage"]["_legacy_backup"]
    assert backup["rows"] == [{"label": "top-a"}]
    assert backup["_tables"] == [_legacy_table("唯一表", 1)]
    assert backup["kind"] == "by_name"
    assert backup["at"]


def test_top_level_rows_and_tables_removed():
    """契约 5：Task 8.3 —— 顶层 `rows` / `_tables` 删除。"""
    td, tpl = _legacy_two_tables()
    td["rows"] = [{"label": "x"}]
    new = mod.build_migrated_table_data(td, _plan(td, tpl), tpl)

    assert "rows" not in new
    assert "_tables" not in new


# ════════════════════════════════════════════════════════════════════
# 6：其余顶层键必须保留
# ════════════════════════════════════════════════════════════════════


def test_other_top_level_keys_preserved():
    """契约 6：只删 rows/_tables，`_note_texts` 等其余顶层键原样保留。"""
    td, tpl = _legacy_two_tables()
    td["_note_texts"] = [{"section": "s1", "title": "分类说明", "text": "略"}]
    td["_last_sync_at"] = "2026-01-01T00:00:00+00:00"
    td["_custom_marker"] = {"deep": [1, 2, 3]}

    new = mod.build_migrated_table_data(td, _plan(td, tpl), tpl)

    assert new["_note_texts"] == [{"section": "s1", "title": "分类说明", "text": "略"}]
    assert new["_last_sync_at"] == "2026-01-01T00:00:00+00:00"
    assert new["_custom_marker"] == {"deep": [1, 2, 3]}


# ════════════════════════════════════════════════════════════════════
# 7：幂等
# ════════════════════════════════════════════════════════════════════


def test_migration_is_idempotent_and_backup_not_double_wrapped():
    """契约 7：二次迁移不覆盖备份 —— 备份里仍是**最初**的 legacy 数据。"""
    td, tpl = _legacy_two_tables()
    plan = _plan(td, tpl)

    once = mod.build_migrated_table_data(td, plan, tpl)
    assert mod._already_migrated(once) is True

    twice = mod.build_migrated_table_data(once, plan, tpl)
    b1 = once["_template_lineage"]["_legacy_backup"]
    b2 = twice["_template_lineage"]["_legacy_backup"]
    assert b2 == b1
    assert b2["_tables"] is not None  # 不是迁移后形态（迁移后已无 _tables）
    assert len(b2["_tables"]) == 2


def test_already_migrated_probe_negative_cases():
    assert mod._already_migrated({}) is False
    assert mod._already_migrated({"_template_lineage": {}}) is False
    assert mod._already_migrated({"_template_lineage": {"_reflow_history": []}}) is False
    assert mod._already_migrated(None) is False


# ════════════════════════════════════════════════════════════════════
# 8：header_label 假数据行
# ════════════════════════════════════════════════════════════════════


def test_header_label_rows_stripped_from_migrated_rows():
    """契约 8：`header_label` 是 md 重建残留的假数据行，迁移时必删。"""
    td = {"_tables": [_legacy_table("存货分类", 3, header_label_rows=2)]}
    tpl = _tpl("存货分类")
    new = mod.build_migrated_table_data(td, _plan(td, tpl), tpl)

    rows = new["sub_table_data"]["存货分类"]
    assert len(rows) == 3
    assert all(r.get("row_type") != "header_label" for r in rows)
    # 备份里仍保有完整原始行（含假行），回滚后可完全复原
    assert len(new["_template_lineage"]["_legacy_backup"]["_tables"][0]["rows"]) == 5


# ════════════════════════════════════════════════════════════════════
# 9~10：回滚
# ════════════════════════════════════════════════════════════════════


def test_rollback_round_trip_deep_equals_original():
    """契约 9（关键性质）：migrate → rollback 后与原 `table_data` 深度相等。"""
    td = {
        "_tables": [_legacy_table("存货分类", 3, header_label_rows=1), _legacy_table("开发成本", 2)],
        "_note_texts": [{"section": "s", "title": "说明", "text": "t"}],
        "_last_sync_at": "2026-01-01T00:00:00+00:00",
    }
    tpl = _tpl("存货分类", "开发成本")
    original = mod.copy.deepcopy(td)

    migrated = mod.build_migrated_table_data(td, _plan(td, tpl), tpl)
    back = mod.build_rollback_table_data(migrated)

    assert back == original


def test_rollback_round_trip_for_single_row_shape():
    """只有顶层 rows 的形态同样可逆。"""
    td = {"rows": [{"label": "a", "c0": 1}, {"label": "b", "c0": 2}]}
    tpl = _tpl("唯一表")
    original = mod.copy.deepcopy(td)

    migrated = mod.build_migrated_table_data(td, _plan(td, tpl), tpl)
    assert migrated["sub_table_data"]["唯一表"] == td["rows"]
    assert mod.build_rollback_table_data(migrated) == original


def test_rollback_returns_none_without_backup():
    """契约 10：没有备份 → None，调用方跳过（绝不瞎猜原形态）。"""
    assert mod.build_rollback_table_data({}) is None
    assert mod.build_rollback_table_data({"_template_lineage": {}}) is None
    assert mod.build_rollback_table_data({"_template_lineage": {"_reflow_history": []}}) is None
    assert mod.build_rollback_table_data(None) is None
    assert mod.build_rollback_table_data("oops") is None


def test_rollback_keeps_other_lineage_entries():
    """`_reflow_history` 等同级记账不能被回滚顺手删掉。"""
    td = {"_tables": [_legacy_table("A", 1)], "_template_lineage": {"_reflow_history": [{"at": "x"}]}}
    tpl = _tpl("A")
    migrated = mod.build_migrated_table_data(td, _plan(td, tpl), tpl)
    back = mod.build_rollback_table_data(migrated)

    assert back["_template_lineage"] == {"_reflow_history": [{"at": "x"}]}
    assert "_legacy_backup" not in back["_template_lineage"]


# ════════════════════════════════════════════════════════════════════
# 11：三消费者一致 —— 投影器
# ════════════════════════════════════════════════════════════════════


def test_projector_parity_after_migration():
    """契约 11：迁移结果能被投影器投出与计划一致的表（`_source` 缺失即为 None）。"""
    td, tpl = _legacy_two_tables()
    plan = _plan(td, tpl)
    new = mod.build_migrated_table_data(td, plan, tpl)

    projected = project_sub_tables(new)
    assert projected is not None
    assert [t["name"] for t in projected] == [t.target_name for t in plan.tables]
    assert [len(t["rows"]) for t in projected] == [t.row_count for t in plan.tables]
    # 有模板 columns → 不降级
    assert all(not t.get("_needs_columns") for t in projected)
    assert projected[0]["headers"] == ["项目", "期末余额"]


def test_projector_degrades_when_template_has_no_columns():
    """反向自检：模板无 columns 时投影会降级 —— 这正是 --require-columns 要拦的情况。"""
    td = {"_tables": [_legacy_table("A", 2)]}
    tpl = _tpl("A", with_columns=False)
    new = mod.build_migrated_table_data(td, _plan(td, tpl), tpl)

    assert "_sub_table_columns" not in new
    projected = project_sub_tables(new)
    assert projected is not None
    assert projected[0]["_needs_columns"] is True


def test_projector_returns_none_without_source():
    """反向自检：去掉 `_source` 投影器返回 None（整章渲染为空）。"""
    td, tpl = _legacy_two_tables()
    new = mod.build_migrated_table_data(td, _plan(td, tpl), tpl)
    del new["_source"]
    assert project_sub_tables(new) is None


# ════════════════════════════════════════════════════════════════════
# 12：纯度
# ════════════════════════════════════════════════════════════════════


def test_build_migrated_table_data_does_not_mutate_input():
    """契约 12：入参 dict 及其嵌套结构均不被修改。"""
    td, tpl = _legacy_two_tables()
    td["_note_texts"] = [{"section": "s"}]
    snapshot = mod.copy.deepcopy(td)
    tpl_snapshot = mod.copy.deepcopy(tpl)

    new = mod.build_migrated_table_data(td, _plan(td, tpl), tpl)
    # 改动产物不应回渗入参
    new["sub_table_data"]["存货分类"].append({"label": "injected"})
    new["_sub_table_columns"]["存货分类"].append({"key": "zzz"})

    assert td == snapshot
    assert tpl == tpl_snapshot


def test_build_rollback_table_data_does_not_mutate_input():
    td, tpl = _legacy_two_tables()
    migrated = mod.build_migrated_table_data(td, _plan(td, tpl), tpl)
    snapshot = mod.copy.deepcopy(migrated)

    back = mod.build_rollback_table_data(migrated)
    back["_tables"].append({"name": "injected"})

    assert migrated == snapshot


# ════════════════════════════════════════════════════════════════════
# 安全闸：类别白名单 + 列头闸
# ════════════════════════════════════════════════════════════════════


def test_allowed_kinds_excludes_positional_by_default():
    assert mod.allowed_kinds(include_positional=False) == ("by_name", "single_row")
    assert "positional" in mod.allowed_kinds(include_positional=True)


def _fake_plan(kind: str, *, columns: bool = True, actionable: bool = True) -> Any:
    p = mod.NotePlan(
        note_id=f"id-{kind}-{columns}-{actionable}",
        project="P",
        note_section="五、1",
        section_title="T",
        kind=kind,
    )
    if actionable:
        p.tables = [mod.TablePlan("表A", 0, 1, 0, columns)]
    return p


def test_select_migratable_default_gates():
    plans = [
        _fake_plan("by_name"),
        _fake_plan("single_row"),
        _fake_plan("positional"),
        _fake_plan("by_name", columns=False),
        _fake_plan("manual", actionable=False),
    ]
    picked, c = mod.select_migratable(
        plans, kinds=mod.allowed_kinds(include_positional=False), require_columns=True
    )
    assert [p.kind for p in picked] == ["by_name", "single_row"]
    assert c["skipped_kind"] == 1
    assert c["skipped_no_columns"] == 1
    assert c["skipped_manual"] == 1
    assert c["selected"] == 2


def test_select_migratable_with_opt_ins():
    plans = [_fake_plan("positional"), _fake_plan("by_name", columns=False)]
    picked, c = mod.select_migratable(
        plans, kinds=mod.allowed_kinds(include_positional=True), require_columns=False
    )
    assert len(picked) == 2
    assert c["skipped_no_columns"] == 0
    assert c["skipped_kind"] == 0


def test_require_columns_gate_needs_all_tables_covered():
    """任一张表缺模板 columns 就整节拦下（部分降级也不接受）。"""
    p = _fake_plan("by_name")
    p.tables = [mod.TablePlan("A", 0, 1, 0, True), mod.TablePlan("B", 1, 1, 0, False)]
    picked, c = mod.select_migratable(
        [p], kinds=mod.allowed_kinds(include_positional=False), require_columns=True
    )
    assert picked == []
    assert c["skipped_no_columns"] == 1


# ════════════════════════════════════════════════════════════════════
# PBT：任意 legacy 形态下 migrate → rollback 保持行标签序列
# ════════════════════════════════════════════════════════════════════

_label = st.text(alphabet="abcXY存货一二", min_size=1, max_size=4)
_row = st.builds(lambda lab, v: {"label": lab, "c0": v}, _label, st.integers(-5, 5))
_table_rows = st.lists(_row, min_size=0, max_size=4)


@settings(max_examples=5, deadline=None)
@given(st.lists(_table_rows, min_size=1, max_size=3))
def test_pbt_migrate_rollback_preserves_row_labels(tables_rows: list[list[dict[str, Any]]]):
    names = [f"表{i}" for i in range(len(tables_rows))]
    td: dict[str, Any] = {
        "_tables": [
            {"name": n, "headers": ["项目", "期末余额"], "rows": rows}
            for n, rows in zip(names, tables_rows)
        ]
    }
    tpl = _tpl(*names)
    original = mod.copy.deepcopy(td)

    plan = _plan(td, tpl)
    assert plan.kind == "by_name"

    migrated = mod.build_migrated_table_data(td, plan, tpl)
    # 迁移后每张表的行标签序列与源表一致
    for n, rows in zip(names, tables_rows):
        assert [r["label"] for r in migrated["sub_table_data"][n]] == [r["label"] for r in rows]

    back = mod.build_rollback_table_data(migrated)
    assert back == original
    assert [
        [r["label"] for r in t["rows"]] for t in back["_tables"]
    ] == [[r["label"] for r in rows] for rows in tables_rows]


@pytest.mark.parametrize("bad", [None, "oops", 123, []])
def test_migrated_table_data_tolerates_non_dict_input(bad: Any):
    plan = mod.NotePlan(
        note_id="x", project="P", note_section="五、1", section_title="T", kind="by_name"
    )
    out = mod.build_migrated_table_data(bad, plan, None)
    assert out["_source"] == "workpaper"
    assert out["sub_table_data"] == {}


# ════════════════════════════════════════════════════════════════════
# _apply 写入编排：per-note savepoint 隔离 / 幂等跳过 / 单次外层 commit
# ════════════════════════════════════════════════════════════════════


class _FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def mappings(self) -> "_FakeResult":
        return self

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return self._rows


class _FakeSavepoint:
    def __init__(self, db: "_FakeDb") -> None:
        self.db = db

    async def __aenter__(self) -> "_FakeSavepoint":
        self.db.savepoints += 1
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if exc_type is not None:
            self.db.savepoint_rollbacks += 1
        return False  # 不吞异常，交给 _apply 的 per-note try


class _FakeDb:
    """最小可用的 AsyncSession 替身：区分 SELECT / UPDATE，可注入写失败。"""

    def __init__(self, notes: dict[str, dict[str, Any]], fail_ids: tuple[str, ...] = ()) -> None:
        self.notes = notes
        self.fail_ids = fail_ids
        self.writes: list[dict[str, Any]] = []
        self.commits = 0
        self.savepoints = 0
        self.savepoint_rollbacks = 0

    async def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> _FakeResult:
        sql = str(stmt).strip()
        params = params or {}
        if sql.upper().startswith("SELECT"):
            row = self.notes.get(str(params.get("id")))
            return _FakeResult([row] if row else [])
        if sql.upper().startswith("UPDATE"):
            if str(params.get("id")) in self.fail_ids:
                raise RuntimeError("模拟写库失败")
            self.writes.append(params)
            return _FakeResult([])
        raise AssertionError(f"未预期的 SQL: {sql}")

    def begin_nested(self) -> _FakeSavepoint:
        return _FakeSavepoint(self)

    async def commit(self) -> None:
        self.commits += 1


def _apply_args(**over: Any) -> Any:
    import argparse

    base = dict(require_columns=True, include_positional=False)
    base.update(over)
    return argparse.Namespace(**base)


def _note_row(note_id: str, td: dict[str, Any]) -> dict[str, Any]:
    return {"id": note_id, "project_id": "proj-1", "table_data": td}


def _unwrap_td(bound: Any) -> dict[str, Any]:
    """取回写入的 table_data。

    绑定形态是 `json.dumps` 字符串（`CAST(:td AS jsonb)`）—— 不是 dict、也不是
    `sa.type_coerce` 对象。后两种形态在 asyncpg 下会写库失败，这里只接受字符串，
    形态一旦退回去本 helper 立刻炸（等于多一道守卫）。
    """
    import json

    assert isinstance(bound, str), (
        f"table_data 绑定值应为 json.dumps 字符串，实得 {type(bound).__name__}"
    )
    return json.loads(bound)


@pytest.fixture()
def _patched_template(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """让 `_apply` 内部的模板加载返回固定的两表章节。"""
    import app.services.note_template_reflow_service as reflow

    tables = _tpl("存货分类", "开发成本")

    async def _fake_load(db: Any, project_id: Any) -> tuple[list[dict[str, Any]], Any]:
        return [{"section_number": "五、9", "section_title": "存货", "tables": tables}], None

    monkeypatch.setattr(reflow, "_load_template_sections", _fake_load)
    monkeypatch.setattr(
        reflow, "_pick_template_section", lambda sections, num, title: sections[0]
    )
    return tables


@pytest.mark.asyncio
async def test_apply_writes_selected_notes_and_commits_once(_patched_template: Any):
    td, tpl = _legacy_two_tables()
    plan = _plan(td, tpl)
    plan.note_id = "n-1"
    db = _FakeDb({"n-1": _note_row("n-1", td)})

    stats = await mod._apply(db, [plan], _apply_args())

    assert stats["migrated"] == 1
    assert stats["failed"] == 0
    assert db.commits == 1  # 外层只 commit 一次
    assert db.savepoints == 1  # 每个章节一个 savepoint
    payload = _unwrap_td(db.writes[0]["td"])
    assert payload["_source"] == "workpaper"
    assert set(payload["sub_table_data"]) == {"存货分类", "开发成本"}
    assert "_tables" not in payload and "rows" not in payload
    assert payload["_template_lineage"]["_legacy_backup"]["_tables"] is not None


@pytest.mark.asyncio
async def test_apply_isolates_failure_per_note(_patched_template: Any):
    """一个章节写失败只回滚它自己的 savepoint，其余照常提交。"""
    td, tpl = _legacy_two_tables()
    plans = []
    notes = {}
    for i in range(3):
        p = _plan(td, tpl)
        p.note_id = f"n-{i}"
        plans.append(p)
        notes[p.note_id] = _note_row(p.note_id, mod.copy.deepcopy(td))

    db = _FakeDb(notes, fail_ids=("n-1",))
    stats = await mod._apply(db, plans, _apply_args())

    assert stats["migrated"] == 2
    assert stats["failed"] == 1
    assert [f[0] for f in stats["failures"]] == ["n-1"]
    assert "模拟写库失败" in stats["failures"][0][2]
    assert db.savepoint_rollbacks == 1
    assert db.commits == 1
    assert [w["id"] for w in db.writes] == ["n-0", "n-2"]


@pytest.mark.asyncio
async def test_apply_skips_already_migrated(_patched_template: Any):
    """幂等重跑：已有 _legacy_backup 的章节不再写。"""
    td, tpl = _legacy_two_tables()
    plan = _plan(td, tpl)
    plan.note_id = "n-1"
    migrated = mod.build_migrated_table_data(td, plan, tpl)

    db = _FakeDb({"n-1": _note_row("n-1", migrated)})
    stats = await mod._apply(db, [plan], _apply_args())

    assert stats["skipped_already"] == 1
    assert stats["migrated"] == 0
    assert db.writes == []


@pytest.mark.asyncio
async def test_apply_respects_gates(_patched_template: Any):
    """positional 与「模板缺 columns」默认被闸拦下，一行都不写。"""
    td = {"_tables": [_legacy_table("项  目", 2), _legacy_table("项  目", 2)]}
    tpl = _tpl("存货分类", "开发成本")
    plan = _plan(td, tpl)
    assert plan.kind == "positional"
    plan.note_id = "n-1"

    db = _FakeDb({"n-1": _note_row("n-1", td)})
    stats = await mod._apply(db, [plan], _apply_args())
    assert stats["skipped_kind"] == 1
    assert db.writes == []

    db2 = _FakeDb({"n-1": _note_row("n-1", td)})
    stats2 = await mod._apply(db2, [plan], _apply_args(include_positional=True))
    assert stats2["migrated"] == 1


@pytest.mark.asyncio
async def test_apply_skips_missing_note(_patched_template: Any):
    """记录已被软删/不存在 → 计入 skipped_missing，不算失败。"""
    td, tpl = _legacy_two_tables()
    plan = _plan(td, tpl)
    plan.note_id = "gone"
    db = _FakeDb({})
    stats = await mod._apply(db, [plan], _apply_args())
    assert stats["skipped_missing"] == 1
    assert stats["failed"] == 0
    assert db.writes == []


# ════════════════════════════════════════════════════════════════════
# JSONB 绑定形态守卫（实测踩坑：38/38 章节写库全失败）
# ════════════════════════════════════════════════════════════════════
#
# `sa.type_coerce(td, sa.JSON)` 配 `sa.text()` 在 asyncpg 下抛
# `Neither 'TypeCoerce' object nor 'Comparator' object has an attribute 'encode'`
# —— type_coerce 是 SQL 表达式构造器、不是可绑定的值，asyncpg 直接拿它去 encode。
# 替身 session 测试**查不出**这个（替身不做真实参数编码），只有真实库能暴露。
# 故这里改为源码级断言：SQL 必须用 CAST(:td AS jsonb)，参数必须是 json.dumps 字符串。


def _script_source() -> str:
    return _SCRIPT.read_text(encoding="utf-8")


def _reflow_source() -> str:
    p = (
        Path(__file__).resolve().parents[2]
        / "app" / "services" / "note_template_reflow_service.py"
    )
    return p.read_text(encoding="utf-8")


def _strip_comments(src: str) -> str:
    """去掉 # 注释与三引号块，避免把「说明为什么不能这么写」的文字数成真实代码。"""
    import re

    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    return "\n".join(line.split("#", 1)[0] for line in src.splitlines())


@pytest.mark.parametrize(
    "loader,label",
    [(_script_source, "migrate_legacy_note_snapshots.py"),
     (_reflow_source, "note_template_reflow_service.py")],
)
def test_jsonb_update_uses_cast_not_type_coerce(loader: Any, label: str):
    """两处写 table_data 的 SQL 都必须走 CAST(:td AS jsonb)，且不得残留 type_coerce。"""
    raw = loader()
    code = _strip_comments(raw)

    # 反向自检：注释里确实提到了 type_coerce（否则 _strip_comments 可能失效、断言空转）
    assert "type_coerce" in raw, f"{label}: 期望注释里保留 type_coerce 的踩坑说明"

    assert "CAST(:td AS jsonb)" in code, f"{label}: table_data 更新未用 CAST(:td AS jsonb)"
    assert "type_coerce" not in code, (
        f"{label}: 代码里仍有 type_coerce —— asyncpg 下会 100% 写库失败"
    )
    assert "json.dumps" in code, f"{label}: 未用 json.dumps 序列化 JSONB 参数"


def test_json_param_serializes_chinese_without_escaping():
    """`ensure_ascii=False`：中文原样，不变成 \\uXXXX（便于日志与人工核对）。"""
    out = mod._json_param({"表名": "存货分类", "n": 1})
    assert "存货分类" in out
    assert "\\u" not in out


def test_json_param_tolerates_non_serializable_via_default_str():
    """`default=str` 兜底：datetime 等非原生 JSON 类型不炸（备份里有 ISO 时间戳）。"""
    from datetime import datetime as _dt

    out = mod._json_param({"at": _dt(2026, 8, 1, 12, 0, 0)})
    assert "2026-08-01" in out
