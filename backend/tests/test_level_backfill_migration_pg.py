"""级别回填迁移的性质测试与执行语义（真 PG）（partner-manager-edit-permission 任务 7.2~7.5；需求 4.1~4.7、4.9~4.11、12.7；
design Property 3、4、5，§5.2、§8.3、§8.5 变异③）。

被测：级别回填迁移 ``V<n>__partner_manager_edit_level_backfill.sql`` 与配对回滚脚本
``R<n>__rollback_partner_manager_edit_level_backfill.sql``（``n`` 按文件名后缀现找，不写死；回滚见 Property 5）。每个样例一个提交型
临时 schema：造数、取全表快照，经运行时迁移执行器 ``MigrationRunner(...).run_pending()`` 正向执行一次（与启动同一入口），
再取一次快照，最后删掉该 schema。隔离与驱动方式见 ``tests/level_backfill_world.py`` 的模块说明；全部用例 ``pg_only``。

- Property 3（``test_property_3_backfill_matches_row_model``）：执行一次后，每个成员行的（项目角色，级别）等于由迁移前数据
  逐行推导的期望；被改动行集合 = 回填记录的 ``project_user_id`` 集合，每条记录的迁移前值 = 改动前快照、目标值与 ``rule`` =
  模型；成员行其余 11 列逐行不变、id 集合不变（不增删、不补建）；``users`` / ``projects`` / ``staff_members`` /
  ``project_assignments`` / ``disclosure_notes`` 全表逐行不变；执行器恰执行本版本、无失败，临时 schema 的 ``schema_version``
  登记了本版本（checksum 与执行器扫描同口径），``schema_migration_failures`` 为空。
- 固定样例（``test_property_3_fixed_examples``）：期望按需求原文逐行写死在 ``Row.expect``；先核对模型，再跑同一组断言。
- Property 4（``test_property_4_backfill_is_idempotent``，任务 7.3）：同一个世界执行一次（快照 A）后，删掉临时 schema
  ``schema_version`` 中本版本那一行，经同一个 ``run_pending()`` 再执行一次（快照 B），两次之间不写其他任何表：第一次仍满足
  Property 3 的全部断言；第二次执行器恰执行本版本、无失败；B 与 A 的成员行（id 集合与全部列）、回填记录（含 ``recorded_at``）
  与其余五张表逐值相同。固定样例 ``test_property_4_fixed_examples`` 复用 f1~f9。
- 需求 4.5（``test_requirement_4_5_existing_records_not_overwritten``，不是 Property 4 本体）：两次执行之间直接改成员行，第一次的
  回填记录不被第二次的新值覆盖；期望写死在 ``_R45_STEPS``，先与模型核对。
- Property 5（``test_property_5_backfill_roundtrip``，任务 7.4）：同一个世界正向执行一次或两次（第二次同 Property 4），再把任选
  的成员行经原生 UPDATE 改成任意（项目角色，级别）（他途改动），最后经执行器的运维回滚入口 ``rollback_to(n − 1)`` 执行 R 副本
  （``_run_backup`` 换成只记录调用的替身）：回滚后每个成员行的（项目角色，级别）等于按需求 4.9 原文推导的值（有回填记录且回滚前
  仍等于记录的目标值 ⇒ 记录的迁移前值，其余保持回滚前的现值），其余列与 id 集合同迁移前；回填记录表不存在；其余五张表同迁移前；
  临时 ``schema_version`` 不再含本版本；``_run_backup`` 替身恰被调用 1 次；没有他途改动时全部成员行回到迁移前（需求 4.6）。
  固定样例 ``test_property_5_fixed_examples`` 复用 f1~f9（正向一次与两次，没有他途改动），``test_requirement_4_9_rollback_branches``
  覆盖 4.9 各分支（期望写死在 ``_R49_STEPS``，先与模型核对）。

- 执行语义（任务 7.5）：需求 4.1 的「两个脚本重复执行都不报错」中正向两次即 Property 4 与需求 4.5 用例，回滚两次见
  ``test_requirement_4_1_rollback_twice``；回滚在没有回填记录时、正向从未执行时成功且不改动成员行；需求 4.10 正向失败（预建不兼容的
  同名表）不登记、记失败、重试时 ``attempt_count`` 递增，回滚失败（回填记录表有依赖视图）整体回滚、版本保持已应用。冲突一律由测试
  数据制造，不改写迁移副本；``rollback_to`` 走不到 R 脚本的两种状态下按执行器同口径直接执行 R 副本（见夹具模块说明「六」）。
- 需求 12.7（``test_requirement_12_7_backfill_matches_role_map``，任务 7.5）：每个合伙人 / 经理与 EQCR 别名（取自期望表）一个世界，
  正向所得级别 == 生产 ``ROLE_MAP`` 的级别，合伙人 / 经理别名的项目角色也相等——SQL 别名字面量与 ``ROLE_MAP`` 的一致性约束。

模型、生成器、``@example`` 世界、固定样例与需求 4.5 / 4.9 用例的数据在 ``tests/level_backfill_cases.py``（任务 7.4 起由本文件
原样挪入），模型口径与生成维度（需求 4.6）见其模块说明。
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import hypothesis
import pytest
from hypothesis import example, given, settings
from sqlalchemy.exc import DBAPIError, ProgrammingError

from app.services.assignment_service import ROLE_MAP
from tests.level_backfill_cases import (
    _BLOCK_DROP,
    _CONFLICT_ERROR,
    _CONFLICT_ID,
    _CONFLICT_NOTE,
    _CONFLICTING_BACKFILL,
    _DEPENDENT_VIEW,
    _DROP_ERROR,
    _E1,
    _E2,
    _FIRST,
    _FIXED,
    _R41_MIXED,
    _R41_NOOP,
    _R45,
    _R45_STEPS,
    _R49,
    _R49_STEPS,
    _RECONCILE_ALIASES,
    Overrides,
    RoundTripCase,
    _model,
    _original,
    _r45_from_model,
    _r49_steps,
    _reconcile_world,
    _rollback_model,
    _roundtrip_cases,
    _worlds,
)
from tests.level_backfill_world import (
    BackfillMigrations,
    ForwardRun,
    Outcome,
    Pair,
    RepeatRun,
    RollbackAttempt,
    RoundTrip,
    RowKey,
    Snapshot,
    World,
    copy_backfill_migrations,
    run_forward_failure,
    run_forward_once,
    run_forward_twice,
    run_rollback_failure,
    run_rollback_only,
    run_rollback_twice,
    run_roundtrip,
)
from tests.role_map_expected import EXPECTED_EQCR_ALIASES

pytestmark = pytest.mark.pg_only


# ─── 断言 ────────────────────────────────────────────────────────────────────

_MEMBER_TABLE = "project_users"
_OTHER_TABLES = ("users", "projects", "staff_members", "project_assignments", "disclosure_notes")
_PAIR_COLUMNS = ("role", "permission_level")


def _pair(row: dict[str, Any]) -> Pair:
    return (row["role"], row["permission_level"])


def _label(world: World, key: RowKey) -> str:
    pi, ri = key
    person = world.people[pi]
    row = person.rows[ri]
    deleted = "，已删除" if row.deleted else ""
    return f"用户{pi}（全局 {person.global_role}）在 {row.project} 的成员行{ri}（{row.role}, {row.level}{deleted}）"


def _check_executor(tag: str, run: ForwardRun, migrations: BackfillMigrations) -> None:
    """经执行器正向执行了本版本、只作用于临时 schema；执行前临时 schema 里没有回填记录表与本版本登记。"""
    assert run.search_path == (run.schema,), f"{tag}：世界连接的 search_path 应只含临时 schema，实际 {run.search_path}"
    assert (run.before.backfill, run.before.schema_version, run.before.failures) == (None, (), None), (
        f"{tag}：执行前临时 schema 里不应已有回填记录表、版本登记或失败表")
    assert (run.result.executed, run.result.failed) == ([migrations.version], []), (
        f"{tag}：执行器应恰执行版本 {migrations.version} 且无失败，实际 executed={run.result.executed}，"
        f"failed={run.result.failed}")
    assert run.backfill_in_schema, f"{tag}：回填记录表应建在临时 schema {run.schema} 里"
    registered = {"version": migrations.version, "filename": migrations.forward.name,
                  "checksum": migrations.forward_checksum(), "operator": None, "rollback_note": None}
    assert run.after.schema_version == (registered,), (
        f"{tag}：schema_version 应恰登记本版本，实际 {run.after.schema_version}")
    assert run.after.failures == (), f"{tag}：schema_migration_failures 应为空，实际 {run.after.failures}"


def _check_member_rows(world: World, expected: dict[RowKey, Outcome | None], run: ForwardRun) -> None:
    """成员行取值等于逐行推导；改动行即记录行；记录的迁移前值、目标值与 rule；其余列与 id 集合不变。"""
    tag = world.name or "生成样例"
    ids = run.seeded.row_ids
    key_of = {row_id: key for key, row_id in ids.items()}
    before, after = run.before.tables[_MEMBER_TABLE], run.after.tables[_MEMBER_TABLE]
    assert set(before) == set(key_of), f"{tag}：建世界后的成员行与造数不符"
    assert set(after) == set(before), f"{tag}：迁移增删了成员行：新增 {set(after) - set(before)}，消失 {set(before) - set(after)}"
    wrong, drift = [], []
    for key, row_id in ids.items():
        outcome = expected[key]
        want = outcome[:2] if outcome is not None else _pair(before[row_id])
        if _pair(after[row_id]) != want:
            wrong.append(f"{_label(world, key)}：迁移后 {_pair(after[row_id])}，逐行推导 {want}")
        rest_before = {column: value for column, value in before[row_id].items() if column not in _PAIR_COLUMNS}
        rest_after = {column: value for column, value in after[row_id].items() if column not in _PAIR_COLUMNS}
        if rest_after != rest_before:
            changed_columns = sorted(c for c in rest_before if rest_before[c] != rest_after.get(c))
            drift.append(f"{_label(world, key)}：其余列被改动 {changed_columns}")
    assert not wrong, f"{tag}：成员行取值与逐行推导不一致：\n" + "\n".join(wrong)
    assert not drift, f"{tag}：迁移改动了成员行的其余列：\n" + "\n".join(drift)

    changed = {row_id for row_id in before if _pair(before[row_id]) != _pair(after[row_id])}
    records = run.after.backfill if run.after.backfill is not None else {}

    def labels(row_ids: set[str]) -> list[str]:
        return sorted(_label(world, key_of[row_id]) if row_id in key_of else row_id for row_id in row_ids)

    assert set(records) == changed, (
        f"{tag}：被改动行与回填记录不一致：改动而无记录 {labels(changed - set(records))}，"
        f"有记录而未改动 {labels(set(records) - changed)}")
    assert changed == {ids[key] for key, outcome in expected.items() if outcome is not None}, (
        f"{tag}：被改动行集合与逐行推导不一致")
    bad = []
    for row_id, record in records.items():
        key = key_of[row_id]
        got = ((record["prior_role"], record["prior_permission_level"]),
               (record["target_role"], record["target_permission_level"], record["rule"]))
        want_record = (_pair(before[row_id]), expected[key])
        if got != want_record or record["recorded_at"] is None:
            bad.append(f"{_label(world, key)}：记录（迁移前值，目标值与 rule）为 {got}，应为 {want_record}")
    assert not bad, f"{tag}：回填记录内容不对：\n" + "\n".join(bad)


def _check_other_tables(tag: str, run: ForwardRun) -> None:
    """迁移不碰委派、人员、用户与项目（4.4）：其余五张表逐行全列不变。"""
    changed = [table for table in _OTHER_TABLES if run.after.tables[table] != run.before.tables[table]]
    assert not changed, f"{tag}：迁移改动了 {changed}"


def _check_forward_once(world: World, expected: dict[RowKey, Outcome | None], migrations: BackfillMigrations) -> ForwardRun:
    """Property 3 的全部断言（每个样例一个新临时 schema，正向执行一次）。"""
    tag = world.name or "生成样例"
    run = run_forward_once(world, migrations)
    _check_executor(tag, run, migrations)
    _check_member_rows(world, expected, run)
    _check_other_tables(tag, run)
    return run


@pytest.fixture(scope="module")
def backfill_migrations(tmp_path_factory: pytest.TempPathFactory) -> BackfillMigrations:
    """只含 V<n> / R<n> 两个逐字节副本的临时迁移目录（执行器在空 schema 里只扫得到它们）。"""
    return copy_backfill_migrations(tmp_path_factory.mktemp("level_backfill_migrations"))


# ─── Property 3 ──────────────────────────────────────────────────────────────


@settings(max_examples=5, deadline=None)
@given(world=_worlds())
@example(world=_E1)
@example(world=_E2)
def test_property_3_backfill_matches_row_model(world: World, backfill_migrations: BackfillMigrations) -> None:
    # Feature: partner-manager-edit-permission, Property 3: 回填结果等于逐行推导，改动行即记录行
    expected = _model(world)
    rules = [outcome[2] for outcome in expected.values() if outcome is not None]
    hypothesis.event(f"成员行 {len(expected)} 条")  # 只进 --hypothesis-show-statistics 的统计，不参与判定
    hypothesis.event(f"被改动行：需求 4.2 {rules.count('partner_manager')} 条，需求 4.3 {rules.count('eqcr')} 条")
    _check_forward_once(world, expected, backfill_migrations)


@pytest.mark.parametrize("world", [pytest.param(world, id=world.name) for world in _FIXED])
def test_property_3_fixed_examples(world: World, backfill_migrations: BackfillMigrations) -> None:
    """固定样例：期望按需求 4.2~4.4 原文逐行写死在 ``Row.expect``；先核对模型，再跑 Property 3 的全部断言。"""
    written = {key: world.people[key[0]].rows[key[1]].expect for key in world.row_keys()}
    assert _model(world) == written, f"{world.name}：模型与需求原文不一致"
    _check_forward_once(world, written, backfill_migrations)


# ─── Property 4：执行两次 == 执行一次（任务 7.3） ───────────────────────────


def _written(world: World) -> dict[RowKey, Outcome | None]:
    """固定样例写死在 ``Row.expect`` 里的第一次执行期望。"""
    return {key: world.people[key[0]].rows[key[1]].expect for key in world.row_keys()}


def _rest(row: dict[str, Any]) -> dict[str, Any]:
    """成员行除（项目角色，级别）两列之外的其余列。"""
    return {column: value for column, value in row.items() if column not in _PAIR_COLUMNS}


def _diff(old: dict[str, Any], new: dict[str, Any]) -> dict[str, tuple[Any, Any]]:
    """取值不同的列 →（旧值，新值）。"""
    return {column: (old.get(column), new.get(column)) for column in sorted(old.keys() | new.keys())
            if old.get(column) != new.get(column)}


def _check_second_run(tag: str, run: RepeatRun, migrations: BackfillMigrations) -> None:
    """第二次也经执行器执行了本版本：先删掉的登记恰 1 行；``executed == [n]``、无失败、没有失败记录；重新登记的内容同第一次。"""
    assert run.forgotten == 1, f"{tag}：第二次执行前应恰删掉 1 行本版本登记，实际 {run.forgotten}"
    assert (run.second.executed, run.second.failed) == ([migrations.version], []), (
        f"{tag}：第二次执行器应恰执行版本 {migrations.version} 且无失败，实际 executed={run.second.executed}，"
        f"failed={run.second.failed}")
    assert run.again.failures == (), f"{tag}：第二次执行后 schema_migration_failures 应为空，实际 {run.again.failures}"
    assert run.again.schema_version == run.first.after.schema_version, (
        f"{tag}：第二次执行后的 schema_version 应与第一次后相同，实际 {run.again.schema_version}")


def _check_idempotent(world: World, run: RepeatRun) -> None:
    """快照 B == 快照 A：第二次不改成员行（id 集合与全部列），不加、不删、不覆盖回填记录（含 recorded_at），其余五张表不变。"""
    tag = world.name or "生成样例"
    key_of = {row_id: key for key, row_id in run.first.seeded.row_ids.items()}
    a, b = run.first.after, run.again

    def labels(row_ids: Iterable[str]) -> list[str]:
        return [_label(world, key_of[row_id]) if row_id in key_of else row_id for row_id in sorted(row_ids)]

    rows_a, rows_b = a.tables[_MEMBER_TABLE], b.tables[_MEMBER_TABLE]
    assert set(rows_b) == set(rows_a), (
        f"{tag}：第二次执行增删了成员行：新增 {labels(set(rows_b) - set(rows_a))}，消失 {labels(set(rows_a) - set(rows_b))}")
    moved = [f"{labels([i])[0]}：{_diff(rows_a[i], rows_b[i])}" for i in sorted(rows_a) if rows_b[i] != rows_a[i]]
    assert not moved, f"{tag}：第二次执行改动了成员行（列 →（第一次后，第二次后））：\n" + "\n".join(moved)
    records_a = a.backfill or {}
    assert b.backfill is not None, f"{tag}：第二次执行后回填记录表不存在"
    assert set(b.backfill) <= set(records_a), f"{tag}：第二次执行新增了回填记录 {labels(set(b.backfill) - set(records_a))}"
    assert set(records_a) <= set(b.backfill), (
        f"{tag}：第二次执行后第一次的回填记录消失 {labels(set(records_a) - set(b.backfill))}")
    rewritten = [f"{labels([i])[0]}：{_diff(records_a[i], b.backfill[i])}"
                 for i in sorted(records_a) if b.backfill[i] != records_a[i]]
    assert not rewritten, f"{tag}：第二次执行覆盖了第一次的回填记录（列 →（第一次后，第二次后））：\n" + "\n".join(rewritten)
    other = [table for table in _OTHER_TABLES if b.tables[table] != a.tables[table]]
    assert not other, f"{tag}：第二次执行改动了 {other}"


def _check_twice(world: World, expected: dict[RowKey, Outcome | None], migrations: BackfillMigrations) -> RepeatRun:
    """Property 4 的全部断言：第一次满足 Property 3；两次之间没有写入；第二次经执行器执行，快照 B == 快照 A。"""
    tag = world.name or "生成样例"
    run = run_forward_twice(world, migrations)
    _check_executor(tag, run.first, migrations)
    _check_member_rows(world, expected, run.first)
    _check_other_tables(tag, run.first)
    assert run.missed == () and run.between == run.first.after, f"{tag}：两次执行之间不应有任何写入"
    _check_second_run(tag, run, migrations)
    _check_idempotent(world, run)
    return run


@settings(max_examples=5, deadline=None)
@given(world=_worlds())
@example(world=_E1)
@example(world=_E2)
def test_property_4_backfill_is_idempotent(world: World, backfill_migrations: BackfillMigrations) -> None:
    # Feature: partner-manager-edit-permission, Property 4: 回填幂等
    expected = _model(world)
    rules = [outcome[2] for outcome in expected.values() if outcome is not None]
    hypothesis.event(  # 只进 --hypothesis-show-statistics 的统计，不参与判定
        f"第一次被改动行 {len(rules)} 条（需求 4.2 {rules.count('partner_manager')} 条，需求 4.3 {rules.count('eqcr')} 条）")
    _check_twice(world, expected, backfill_migrations)


@pytest.mark.parametrize("world", [pytest.param(world, id=world.name) for world in _FIXED])
def test_property_4_fixed_examples(world: World, backfill_migrations: BackfillMigrations) -> None:
    """固定样例：复用 Property 3 的 f1~f9（含被需求 4.2、4.3 改动的行）跑「执行两次 == 执行一次」；先核对模型与写死的期望。"""
    written = _written(world)
    assert _model(world) == written, f"{world.name}：模型与需求原文不一致"
    _check_twice(world, written, backfill_migrations)


# ─── 需求 4.5：两次执行之间有他途改动（不是 Property 4 本体） ────────────────


def test_requirement_4_5_existing_records_not_overwritten(backfill_migrations: BackfillMigrations) -> None:
    """需求 4.5「该行已有回填记录时保留原记录，不用新值覆盖」：两次执行之间有他途改动，属 4.5 的语义，不是 Property 4 本体。

    第一次执行后直接在临时 schema 里把 8 条成员行的（项目角色，级别）改成非目标值（``_R45_STEPS`` 第一列），再按 Property 4 的
    同一方式执行第二次。期望：被他途改动的 4.2 / 4.3 行再次改为第二次执行时的目标值；第一次的 7 条回填记录逐值不变（迁移前值、
    目标值、rule、``recorded_at``），不被第二次的新值覆盖；第一次已等于目标值、被他途改成非目标值的行由第二次改动并新增一条记录
    （迁移前值为第二次执行前的值）；其余行与记录不变，其余五张表不变。"""
    world, steps = _R45, _R45_STEPS
    written = _written(world)
    assert _model(world) == written, f"{world.name}：第一次：模型与需求原文不一致"
    assert set(steps) == set(world.row_keys()) and _r45_from_model(world, steps) == steps, (
        f"{world.name}：第二次：模型与需求原文不一致")
    run = run_forward_twice(world, backfill_migrations, {key: step[0] for key, step in steps.items() if step[0]})
    tag, ids = world.name, run.first.seeded.row_ids
    _check_executor(tag, run.first, backfill_migrations)
    _check_member_rows(world, written, run.first)
    _check_other_tables(tag, run.first)
    a, mid, b = run.first.after, run.between, run.again
    rows_a, rows_mid, rows_b = (snap.tables[_MEMBER_TABLE] for snap in (a, mid, b))
    # 他途改动本身：恰改了指定行的两列，其余数据不变
    assert run.missed == (), f"{tag}：他途改动没有改到成员行 {run.missed}"
    assert {i: _pair(row) for i, row in rows_mid.items()} == {
        ids[key]: step[0] or _pair(rows_a[ids[key]]) for key, step in steps.items()}, f"{tag}：他途改动后的成员行不对"
    assert ({i: _rest(row) for i, row in rows_mid.items()}, mid.backfill, mid.schema_version, mid.failures) == (
        {i: _rest(row) for i, row in rows_a.items()}, a.backfill, a.schema_version, a.failures), (
        f"{tag}：他途改动不应碰两列之外的数据")
    _check_second_run(tag, run, backfill_migrations)
    got = {key: _pair(rows_b[ids[key]]) for key in steps}
    assert got == {key: step[1] for key, step in steps.items()}, f"{tag}：第二次执行后的成员行不对：{got}"
    assert set(rows_b) == set(rows_a) and all(_rest(rows_b[i]) == _rest(rows_a[i]) for i in rows_a), (
        f"{tag}：第二次执行增删了成员行，或改了两列之外的列")
    records, records_a = b.backfill if b.backfill is not None else {}, a.backfill or {}
    key_of = {row_id: key for key, row_id in ids.items()}
    want_ids = {ids[key] for key, step in steps.items() if step[2] is not None}
    assert set(records) == want_ids, (
        f"{tag}：第二次执行后回填记录覆盖的行不对：缺少 {sorted(_label(world, key_of[i]) for i in want_ids - set(records))}，"
        f"多出 {sorted(_label(world, key_of[i]) if i in key_of else i for i in set(records) - want_ids)}")
    wrong = []
    for row_id in sorted(want_ids):
        key = key_of[row_id]
        want, record = steps[key][2], records[row_id]
        if want == _FIRST:
            if record != records_a.get(row_id):
                wrong.append(f"{_label(world, key)}：第一次的记录被改写 {_diff(records_a.get(row_id, {}), record)}")
            continue
        got_record = ((record["prior_role"], record["prior_permission_level"]),
                      (record["target_role"], record["target_permission_level"], record["rule"]))
        if got_record != want or record["recorded_at"] is None:
            wrong.append(f"{_label(world, key)}：第二次新增的记录为 {got_record}，应为 {want}")
    assert not wrong, f"{tag}：回填记录不对（需求 4.5）：\n" + "\n".join(wrong)
    other = [table for table in _OTHER_TABLES if b.tables[table] != a.tables[table]]
    assert not other, f"{tag}：第二次执行改动了 {other}"


# ─── Property 5：回填往返（任务 7.4） ───────────────────────────────────────


def _check_roundtrip(world: World, forward: dict[RowKey, Outcome | None], run: RoundTrip, migrations: BackfillMigrations,
                     steps: tuple[Overrides, ...], expected: dict[RowKey, Pair]) -> None:
    """Property 5 的全部断言：正向部分同 Property 3（执行两次时另同 Property 4）；他途改动恰改到指定行的两列；``rollback_to(n − 1)``
    恰回滚本版本、``_run_backup`` 替身恰 1 次；回滚后成员行（项目角色，级别）== ``expected``，其余列与 id 集合同迁移前，回填记录表
    不存在，其余五张表同迁移前，临时 ``schema_version`` 不再含本版本；没有他途改动时全部成员行（全部列）回到迁移前（需求 4.6）。"""
    tag = world.name or "生成样例"
    ids, before = run.first.seeded.row_ids, run.first.before
    _check_executor(tag, run.first, migrations)
    _check_member_rows(world, forward, run.first)
    _check_other_tables(tag, run.first)
    if run.repeat is not None:
        assert run.repeat.missed == () and run.repeat.between == run.first.after, f"{tag}：两次正向执行之间不应有任何写入"
        _check_second_run(tag, run.repeat, migrations)
        _check_idempotent(world, run.repeat)
    # 他途改动：恰改到指定行的（项目角色，级别），其余数据不变
    fwd, ovr = run.forward, run.overridden
    current = {key: _pair(fwd.tables[_MEMBER_TABLE][row_id]) for key, row_id in ids.items()}
    for step in steps:
        current.update(step)
    assert run.missed == (), f"{tag}：他途改动没有改到成员行 {run.missed}"
    assert {key: _pair(ovr.tables[_MEMBER_TABLE][row_id]) for key, row_id in ids.items()} == current, (
        f"{tag}：他途改动后的成员行不对")
    assert ({i: _rest(row) for i, row in ovr.tables[_MEMBER_TABLE].items()}, ovr.backfill, ovr.schema_version, ovr.failures) == (
        {i: _rest(row) for i, row in fwd.tables[_MEMBER_TABLE].items()}, fwd.backfill, fwd.schema_version, fwd.failures), (
        f"{tag}：他途改动不应碰两列之外的数据")
    # 回滚：经 rollback_to 执行了 R 副本
    assert (run.target, run.rolled_back) == (str(int(migrations.version) - 1), [migrations.version]), (
        f"{tag}：rollback_to({run.target}) 应恰回滚版本 {migrations.version}，实际 {run.rolled_back}")
    assert run.backups == ((migrations.version, run.target),), f"{tag}：_run_backup 替身应恰被调用 1 次，实际 {run.backups}"
    assert (run.backfill_in_schema, run.after.backfill) == (False, None), f"{tag}：回滚后回填记录表应不存在"
    assert (run.after.schema_version, run.after.failures) == ((), ()), (
        f"{tag}：回滚后临时 schema_version 不应再含本版本、失败表应为空，实际 {run.after.schema_version}，{run.after.failures}")
    rows_before, rows_after = before.tables[_MEMBER_TABLE], run.after.tables[_MEMBER_TABLE]
    assert set(rows_after) == set(rows_before), f"{tag}：回滚增删了成员行"
    wrong = [f"{_label(world, key)}：回滚前 {current[key]}，回滚后 {_pair(rows_after[row_id])}，按需求 4.9 应为 {expected[key]}"
             for key, row_id in ids.items() if _pair(rows_after[row_id]) != expected[key]]
    assert not wrong, f"{tag}：回滚后成员行取值不对：\n" + "\n".join(wrong)
    drift = [_label(world, key) for key, row_id in ids.items() if _rest(rows_after[row_id]) != _rest(rows_before[row_id])]
    assert not drift, f"{tag}：回滚改动了成员行的其余列 {drift}"
    other = [table for table in _OTHER_TABLES if run.after.tables[table] != before.tables[table]]
    assert not other, f"{tag}：回滚后 {other} 与迁移前不同"
    if not any(steps):  # 需求 4.6 往返性质本体：不经模型，直接与迁移前快照逐行全列比
        back = [f"{_label(world, key)}：{_diff(rows_before[row_id], rows_after[row_id])}"
                for key, row_id in ids.items() if rows_after[row_id] != rows_before[row_id]]
        assert not back and run.after.tables == before.tables, (
            f"{tag}：没有他途改动，回滚后应全部回到迁移前（列 →（迁移前，回滚后））：\n" + "\n".join(back))


@settings(max_examples=5, deadline=None)
@given(case=_roundtrip_cases())
@example(case=RoundTripCase(_E1, 1, {}))
@example(case=RoundTripCase(_E2, 2, {}))
def test_property_5_backfill_roundtrip(case: RoundTripCase, backfill_migrations: BackfillMigrations) -> None:
    # Feature: partner-manager-edit-permission, Property 5: 回填往返
    world, steps = case.world, (case.overrides,)
    forward, expected = _model(world), _rollback_model(world, steps)
    recorded = {key: outcome[:2] for key, outcome in forward.items() if outcome is not None}
    restored = sum(case.overrides.get(key, target) == target for key, target in recorded.items())
    hypothesis.event(f"正向执行 {case.runs} 次")  # 三个事件只进 --hypothesis-show-statistics 的统计，不参与判定
    hypothesis.event(f"他途改动 {len(case.overrides)} 行，其中有回填记录 {len(recorded.keys() & case.overrides.keys())} 行")
    hypothesis.event(f"回填记录 {len(recorded)} 条，回滚时仍为目标值（恢复）{restored} 条")
    run = run_roundtrip(world, backfill_migrations, case.runs, steps)
    _check_roundtrip(world, forward, run, backfill_migrations, steps, expected)


@pytest.mark.parametrize("runs", [pytest.param(1, id="once"), pytest.param(2, id="twice")])
@pytest.mark.parametrize("world", [pytest.param(world, id=world.name) for world in _FIXED])
def test_property_5_fixed_examples(world: World, runs: int, backfill_migrations: BackfillMigrations) -> None:
    """固定样例：f1~f9（含被需求 4.2、4.3 改动的行）正向执行一次与两次、没有他途改动，回滚后全部成员行回到迁移前值（需求 4.6）；
    先核对两个模型与写死的期望。"""
    written, original = _written(world), _original(world)
    assert _model(world) == written, f"{world.name}：模型与需求原文不一致"
    assert _rollback_model(world, ()) == original, f"{world.name}：往返模型与需求 4.6 不一致"
    run = run_roundtrip(world, backfill_migrations, runs)
    _check_roundtrip(world, written, run, backfill_migrations, (), original)


@pytest.mark.parametrize("runs", [pytest.param(1, id="once"), pytest.param(2, id="twice")])
def test_requirement_4_9_rollback_branches(runs: int, backfill_migrations: BackfillMigrations) -> None:
    """需求 4.9 各分支（Property 5 的显式样例）：有记录且仍为目标值、被改成非目标值、被改走后又改回目标值、只差一列（两种）、
    没有记录的行被他途改动（含已删除行）、需求 4.3 的行被改动与未被改动各一。期望写死在 ``_R49_STEPS``，先核对第一次正向与回滚两个
    模型，再跑 Property 5 的全部断言。"""
    world, steps = _R49, _r49_steps()
    written, expected = _written(world), {key: after for key, (_, after) in _R49_STEPS.items()}
    assert _model(world) == written, f"{world.name}：正向：模型与需求原文不一致"
    assert set(_R49_STEPS) == set(world.row_keys()) and _rollback_model(world, steps) == expected, (
        f"{world.name}：回滚：模型与需求 4.9 原文不一致")
    run = run_roundtrip(world, backfill_migrations, runs, steps)
    _check_roundtrip(world, written, run, backfill_migrations, steps, expected)


# ─── 需求 4.1、4.10：执行语义（任务 7.5） ──────────────────────────────────


_REFUSED = "schema_version 表为空，无法回滚"  # 执行器 rollback_to 在临时 schema_version 为空时的报错原文（现读）


def _check_refused(tag: str, attempt: RollbackAttempt) -> None:
    """``rollback_to(n − 1)`` 走不到 R 脚本：临时 schema_version 为空 ⇒ RuntimeError，``_run_backup`` 替身未被调用。"""
    assert (type(attempt.error), str(attempt.error), attempt.rolled_back, attempt.backups) == (
        RuntimeError, _REFUSED, None, ()), f"{tag}：rollback_to 应因 schema_version 为空而拒绝执行，实际 {attempt}"


def _check_same_data(tag: str, what: str, old: Snapshot, new: Snapshot) -> None:
    """``new`` 与 ``old`` 的六张表逐行全列、回填记录、版本登记与失败表都相同；不同时列出不同的部分。"""
    tables = [name for name in old.tables if new.tables[name] != old.tables[name]]
    others = [name for name in ("backfill", "schema_version", "failures") if getattr(new, name) != getattr(old, name)]
    assert not tables and not others, f"{tag}：{what}改动了 {tables + others}"


def test_requirement_4_1_rollback_twice(backfill_migrations: BackfillMigrations) -> None:
    """需求 4.1「两个脚本在同一库上重复执行都不报错」的回滚一半（正向两次即 Property 4 与需求 4.5 用例）：正向一次后经
    ``rollback_to(n − 1)`` 回滚一次，再按执行器同口径（``_execute_rollback_script``，``rollback_to`` 执行 R 脚本所用的同一函数）
    执行一次 R 副本——此时本版本登记已删，``rollback_to`` 走不到 R 脚本（另断言其拒绝执行、不改数据）。期望：第一次回滚后全部数据
    回到迁移前；第二次执行不报错，六张表、版本登记与失败表都与第一次回滚后相同，回填记录表不存在。"""
    world, n = _R41_MIXED, backfill_migrations.version
    written = _written(world)
    assert _model(world) == written and any(written.values()), f"{world.name}：模型与需求原文不一致，或没有被改动的行"
    run = run_rollback_twice(world, backfill_migrations)
    tag = world.name
    _check_executor(tag, run.first, backfill_migrations)
    _check_member_rows(world, written, run.first)
    _check_other_tables(tag, run.first)
    first = run.rollback
    assert (first.error, first.rolled_back, first.backups) == (None, [n], ((n, first.target),)), (
        f"{tag}：第一次回滚应经 rollback_to 恰回滚版本 {n}，实际 {first}")
    assert (run.exists_once, run.once.backfill, run.once.schema_version, run.once.failures) == (False, None, (), ()), (
        f"{tag}：第一次回滚后回填记录表应不存在、版本登记与失败表应为空")
    assert run.once.tables == run.first.before.tables, f"{tag}：第一次回滚后六张表应全部回到迁移前"
    _check_refused(tag, run.refused)
    _check_same_data(tag, "被拒绝的 rollback_to ", run.once, run.mid)
    assert run.second_error is None, f"{tag}：第二次执行 R 副本报错：{run.second_error!r}"
    assert run.exists_twice is False, f"{tag}：第二次执行 R 副本后回填记录表应不存在"
    _check_same_data(tag, "第二次执行 R 副本", run.once, run.twice)


def test_requirement_4_1_rollback_without_backfill_records(backfill_migrations: BackfillMigrations) -> None:
    """需求 4.1「配对回滚脚本在没有回填记录时执行成功，且不改动任何成员行」：正向执行一次后没有任何行被改动（回填记录表建出且为空；
    其中 4 行持合伙人 / 经理或 EQCR 别名委派、已在目标值上），再经 ``rollback_to(n − 1)`` 回滚：成功，成员行与其余表逐行全列同
    迁移前，回填记录表不存在（其余断言同 Property 5）。"""
    world = _R41_NOOP
    written = _written(world)
    assert _model(world) == written and not any(written.values()), f"{world.name}：模型应给出「没有被改动的行」"
    run = run_roundtrip(world, backfill_migrations, 1)
    tag = world.name
    assert (run.first.backfill_in_schema, run.first.after.backfill) == (True, {}), (
        f"{tag}：正向执行后回填记录表应存在且为空，实际 {run.first.after.backfill}")
    assert run.first.after.tables == run.first.before.tables, f"{tag}：正向执行不应改动任何表"
    _check_roundtrip(world, written, run, backfill_migrations, (), _original(world))


def test_requirement_4_1_rollback_when_forward_never_ran(backfill_migrations: BackfillMigrations) -> None:
    """需求 4.1「没有回填记录时（包括正向迁移从未执行）执行成功，且不改动任何成员行」的后一种：临时 schema 里没有回填记录表、没有
    本版本登记、没有失败表。执行器的运维入口 ``rollback_to(n − 1)`` 此时走不到 R 脚本（schema_version 为空即拒绝，另断言），所以
    按执行器同口径直接执行 R 副本（``_execute_rollback_script``，即 ``rollback_to`` 执行 R 脚本所用的同一函数）。期望：不报错；
    成员行（含正向会改动的、已在目标值上的）与其余表逐行全列不变；回填记录表不存在；版本登记仍为空，失败表仍不存在。"""
    world = _R41_MIXED
    assert any(_model(world).values()), f"{world.name}：应含正向会改动的行（R 不得按正向的逻辑反推改动）"
    run = run_rollback_only(world, backfill_migrations)
    tag = f"{world.name}（正向从未执行）"
    assert run.search_path == (run.schema,), f"{tag}：世界连接的 search_path 应只含临时 schema，实际 {run.search_path}"
    assert (run.exists_before, run.before.backfill, run.before.schema_version, run.before.failures) == (
        False, None, (), None), f"{tag}：执行前不应有回填记录表、本版本登记或失败表"
    _check_refused(tag, run.refused)
    _check_same_data(tag, "被拒绝的 rollback_to ", run.before, run.mid)
    assert run.error is None, f"{tag}：执行 R 副本报错：{run.error!r}"
    assert run.exists_after is False, f"{tag}：执行 R 副本后回填记录表应不存在"
    _check_same_data(tag, "执行 R 副本", run.before, run.after)


def test_requirement_4_10_forward_failure_is_not_registered(backfill_migrations: BackfillMigrations) -> None:
    """需求 4.10 正向一半：执行前在临时 schema 里预建与回填记录表同名、结构不同的表（含一行；测试数据，不改写迁移副本），V 副本的建表
    语句因 ``IF NOT EXISTS`` 跳过，随后的数据修改语句列名解析失败。经 ``run_pending()`` 正向执行：``executed`` 为空、``failed`` 恰为
    本版本（类型与信息同预期）；版本 n 不登记；失败表有本版本一条记录、``attempt_count`` 为 1；六张表逐行全列不变（含正向会改动的
    行）；预建的表内容不变（没有被写入）。再执行一次 ``run_pending()``（下次启动的重试）：同样失败、不登记，``attempt_count`` 为 2。"""
    world, n, filename = _R41_MIXED, backfill_migrations.version, backfill_migrations.forward.name
    assert any(_model(world).values()), f"{world.name}：应含正向会改动的行"
    run = run_forward_failure(world, backfill_migrations, _CONFLICTING_BACKFILL)
    tag = f"{world.name}（预建不兼容的同名表）"
    conflict = {_CONFLICT_ID: {"project_user_id": _CONFLICT_ID, "note": _CONFLICT_NOTE}}
    assert run.search_path == (run.schema,), f"{tag}：世界连接的 search_path 应只含临时 schema，实际 {run.search_path}"
    assert (run.before.backfill, run.before.schema_version, run.before.failures) == (conflict, (), None), (
        f"{tag}：执行前应只有预建的同名表、没有本版本登记与失败表")
    for label, result, snap, attempts in (("第一次", run.first, run.after, 1), ("重试", run.second, run.again, 2)):
        records = [(record.version, record.filename, record.error_type) for record in result.failed]
        assert (result.executed, records) == ([], [(n, filename, ProgrammingError.__name__)]), (
            f"{tag}：{label}正向执行应恰失败于版本 {n}，实际 executed={result.executed}，failed={result.failed}")
        message = result.failed[0].error_message
        assert all(fragment in message for fragment in _CONFLICT_ERROR), f"{tag}：{label}失败信息不是预期的列名解析错误：{message}"
        assert snap.failures == ({"version": n, "filename": filename, "error_type": ProgrammingError.__name__,
                                  "error_message": message, "attempt_count": attempts},), (
            f"{tag}：{label}后失败表应恰有本版本一条记录、attempt_count={attempts}，实际 {snap.failures}")
        assert snap.schema_version == (), f"{tag}：{label}后版本 {n} 不应登记为已应用，实际 {snap.schema_version}"
        assert snap.backfill == conflict, f"{tag}：{label}后预建的同名表被改动：{snap.backfill}"
        tables = [name for name in snap.tables if snap.tables[name] != run.before.tables[name]]
        assert not tables, f"{tag}：{label}正向执行失败后 {tables} 与执行前不同"


def test_requirement_4_10_rollback_failure_keeps_version_applied(backfill_migrations: BackfillMigrations) -> None:
    """需求 4.10 回滚一半：正向成功后给回填记录表建一个依赖视图（测试数据），再经 ``rollback_to(n − 1)`` 回滚：R 副本的 UPDATE 先在
    事务内恢复成员行，其后的 DROP TABLE（不带 CASCADE）报错 ⇒ ``rollback_to`` 抛出（断言类型与信息）；R 整个脚本在一个事务里回滚：
    六张表（成员行仍为正向后的值）、回填记录与版本登记都与回滚前相同，版本 n 保持已应用；``_run_backup`` 替身在执行 R 之前恰被调用
    1 次。"""
    world, n = _R41_MIXED, backfill_migrations.version
    written = _written(world)
    assert _model(world) == written and any(written.values()), f"{world.name}：模型与需求原文不一致，或没有被改动的行"
    run = run_rollback_failure(world, backfill_migrations, _BLOCK_DROP, _DEPENDENT_VIEW)
    tag = f"{world.name}（回填记录表有依赖视图）"
    _check_executor(tag, run.first, backfill_migrations)
    _check_member_rows(world, written, run.first)
    _check_other_tables(tag, run.first)
    _check_same_data(tag, "建依赖视图", run.first.after, run.before)
    attempt = run.attempt
    assert (attempt.rolled_back, attempt.backups) == (None, ((n, attempt.target),)), (
        f"{tag}：rollback_to 应在执行 R 副本时失败（_run_backup 替身先被调用 1 次），实际 {attempt}")
    assert type(attempt.error) is DBAPIError and all(fragment in str(attempt.error) for fragment in _DROP_ERROR), (
        f"{tag}：rollback_to 应抛出「删表被依赖对象阻止」的错误，实际 {attempt.error!r}")
    _check_same_data(tag, "失败的回滚", run.before, run.after)
    assert run.after.schema_version == run.first.after.schema_version != (), f"{tag}：回滚失败后版本 {n} 应保持已应用"
    assert (run.exists_after, run.probe_after) == (True, True), f"{tag}：回滚失败后回填记录表与依赖视图都应还在"


# ─── 需求 12.7：回填与角色映射对账（任务 7.5） ──────────────────────────────


@pytest.mark.parametrize("alias", [pytest.param(alias, id=alias) for alias in _RECONCILE_ALIASES])
def test_requirement_12_7_backfill_matches_role_map(alias: str, backfill_migrations: BackfillMigrations) -> None:
    """需求 12.7 回填与角色映射对账：迁移脚本引用不了 Python，合伙人 / 经理与 EQCR 别名只能以字面量写在 V 的 SQL 里；本用例是这些
    SQL 字面量与生产 ``ROLE_MAP`` 之间的一致性约束——``ROLE_MAP`` 改值而 SQL 不改（或反之）即打红（design §8.5 变异③）。别名取需求
    2.5 期望表，不从生产代码推导；每个别名一个世界：一名用户、一条人员库记录、该别名一条现行委派、一条 (auditor, readonly) 成员行，
    经执行器正向执行一次。所得级别 == ``ROLE_MAP[别名]`` 的级别；合伙人 / 经理别名的项目角色 == ``ROLE_MAP[别名]`` 的项目角色；
    EQCR 别名的项目角色按需求 4.3 保持迁移前的 auditor（按需求原文写死，不读 ``ROLE_MAP``）。"""
    world = _reconcile_world(alias)
    run = run_forward_once(world, backfill_migrations)
    _check_executor(world.name, run, backfill_migrations)
    role, level = _pair(run.after.tables[_MEMBER_TABLE][run.seeded.row_ids[(0, 0)]])
    mapped_role, mapped_level = ROLE_MAP[alias]
    assert level == mapped_level.value, (
        f"{world.name}：迁移所得级别 {level} 与 ROLE_MAP[{alias!r}] 的级别 {mapped_level.value} 不一致")
    if alias in EXPECTED_EQCR_ALIASES:
        assert role == "auditor", f"{world.name}：EQCR 别名的项目角色按需求 4.3 应保持迁移前的 auditor，实际 {role}"
    else:
        assert role == mapped_role.value, (
            f"{world.name}：迁移所得项目角色 {role} 与 ROLE_MAP[{alias!r}] 的项目角色 {mapped_role.value} 不一致")
