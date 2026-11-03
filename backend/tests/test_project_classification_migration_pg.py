"""V219 / R219 质控业务分类与专项场景拆分的真实 PostgreSQL 契约（follow-up R4.2 / R4.6）。

- 迁移矩阵：旧场景值搬到场景列、小写 / 空白码规范化、空串清空、干净行不动；改动行逐行备份；CHECK 生效、默认值去掉；
- 未登记分类 / 旧值与场景冲突 / 未登记场景 ⇒ fail-closed，整份迁移回滚（数据、备份表、约束都不留）；
- R219 只恢复现值仍等于迁移结果的行（迁移后人工改过的保持现值），恢复默认值、删备份表，可重复执行；
- 约束是否已存在按本表判断：另一个 schema 已有同名约束时本 schema 照样建上；
- 迁移前后 ``project_classification.resolve`` 判定逐行一致；共享库 projects 分类列只读复制进临时 schema 做 dry-run。
所有建表 / 写入都在随机临时 schema 内，finally 删除；共享 public 只读。
"""
from __future__ import annotations

from pathlib import Path
import sys
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))

from app.services import project_classification as pc  # noqa: E402
from tests.pg_temp_schema import (  # noqa: E402
    MIGRATIONS,
    constraint_names,
    run_sql_file,
    sqlstate,
    table_names,
    temporary_schema,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.pg_only]

_V219 = MIGRATIONS / "V219__project_category_scenario_split.sql"
_R219 = MIGRATIONS / "R219__rollback_project_category_scenario_split.sql"
_BACKUP = "project_classification_v219_backup"
_CHECKS = {"ck_projects_business_category_registered", "ck_projects_scenario_registered"}

#: 与共享库 projects 三列同定义（V219 前：分类默认 'C'、可空；场景非空默认 normal），见 test_parent_mirrors_shared_columns。
_PROJECTS_DDL = """
    CREATE TABLE projects (
        id UUID PRIMARY KEY,
        business_category VARCHAR(20) DEFAULT 'C',
        scenario VARCHAR(20) NOT NULL DEFAULT 'normal',
        template_type VARCHAR(20)
    )
"""

#: (键, 原分类, 原场景, 报表模板, 迁移后分类, 迁移后场景, 是否备份)
_MATRIX = [
    ("legacy_ipo", "IPO", "normal", "soe", None, "ipo", True),
    ("legacy_refi_spaced", " refinancing ", "normal", None, None, "refinancing", True),
    ("legacy_ipo_same_scenario", "ipo", "ipo", "listed", None, "ipo", True),
    ("lower_code", "a1", "normal", "soe", "A1", "normal", True),
    ("spaced_code", " C ", "listed", None, "C", "listed", True),
    ("blank", "", "normal", None, None, "normal", True),
    ("null", None, "normal", "listed", None, "normal", False),
    ("clean", "B2", "transfer", "soe", "B2", "transfer", False),
]


def _pid(key: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"v219/{key}")


async def _seed(conn: AsyncConnection, rows) -> None:
    await conn.exec_driver_sql(_PROJECTS_DDL)
    for key, category, scenario, template_type, *_ in rows:
        await conn.execute(
            sa.text("INSERT INTO projects (id, business_category, scenario, template_type) VALUES (:id, :c, :s, :t)"),
            {"id": _pid(key), "c": category, "s": scenario, "t": template_type},
        )


async def _values(conn: AsyncConnection) -> dict[uuid.UUID, tuple[str | None, str]]:
    rows = await conn.execute(sa.text("SELECT id, business_category, scenario FROM projects"))
    return {row[0]: (row[1], row[2]) for row in rows}


async def _default(conn: AsyncConnection) -> str | None:
    return await conn.scalar(sa.text("""
        SELECT column_default FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'projects' AND column_name = 'business_category'
    """))


async def test_v219_matrix_backup_and_r219_restores_only_untouched_rows():
    async with temporary_schema("tgfo_v219") as (engine, _schema):
        async with engine.begin() as conn:
            await _seed(conn, _MATRIX)
            before = await _values(conn)
            await run_sql_file(conn, _V219)

        async with engine.begin() as conn:
            after = await _values(conn)
            for key, _c, _s, template_type, expected_c, expected_s, _b in _MATRIX:
                assert after[_pid(key)] == (expected_c, expected_s), key
                # 迁移前后判定逐行一致（resolver 认得旧值）
                assert pc.resolve(*before[_pid(key)], template_type) == pc.resolve(*after[_pid(key)], template_type), key
            backups = {row[0]: (row[1], row[2]) for row in await conn.execute(
                sa.text(f"SELECT project_id, old_business_category, old_scenario FROM {_BACKUP}"))}
            assert backups == {_pid(k): (c, s) for k, c, s, _t, _ec, _es, backed in _MATRIX if backed}
            assert _CHECKS <= await constraint_names(conn, "projects")
            assert await _default(conn) is None, "未填写 = NULL：库默认值 'C' 会让漏写列的裸 SQL 伪填 C 类"
            fresh = uuid.uuid4()
            await conn.execute(sa.text("INSERT INTO projects (id) VALUES (:id)"), {"id": fresh})
            assert (await _values(conn))[fresh] == (None, "normal")

        for bad in ({"c": "IPO", "s": "normal"}, {"c": "a1", "s": "normal"}, {"c": None, "s": "integrated"}):
            async with engine.connect() as conn:
                with pytest.raises(sa.exc.DBAPIError) as caught:
                    await conn.execute(sa.text(
                        "INSERT INTO projects (id, business_category, scenario) VALUES (:id, :c, :s)"),
                        {"id": uuid.uuid4(), **bad})
                assert sqlstate(caught.value) == "23514", bad
                await conn.rollback()

        # 迁移后人工确认：旧 IPO 项目定为 A2；规范化过的 A1 项目改场景 ⇒ R219 不得覆盖
        async with engine.begin() as conn:
            await conn.execute(sa.text("UPDATE projects SET business_category = 'A2' WHERE id = :id"),
                               {"id": _pid("legacy_ipo")})
            await conn.execute(sa.text("UPDATE projects SET scenario = 'listed' WHERE id = :id"),
                               {"id": _pid("lower_code")})
            await run_sql_file(conn, _R219)

        async with engine.begin() as conn:
            restored = await _values(conn)
            expected = {_pid(k): (c, s) for k, c, s, *_ in _MATRIX}
            expected[_pid("legacy_ipo")] = ("A2", "ipo")
            expected[_pid("lower_code")] = ("A1", "listed")
            expected[fresh] = (None, "normal")
            assert restored == expected
            assert _BACKUP not in await table_names(conn)
            assert not (_CHECKS & await constraint_names(conn, "projects"))
            assert await _default(conn) == "'C'::character varying"
            await run_sql_file(conn, _R219)  # 备份表已删：重复执行不报错、不改数据
            assert await _values(conn) == expected


@pytest.mark.parametrize(
    ("category", "scenario"),
    [("D9", "normal"), ("上市公司", "normal"), ("IPO", "listed"), ("refinancing", "ipo"), ("C", "integrated"),
     ("C", "IPO"), ("\tA1", "normal")],
    ids=["unregistered", "chinese_alias", "ipo_vs_listed", "refi_vs_ipo", "bad_scenario", "scenario_case", "tab"],
)
async def test_v219_fails_closed_and_rolls_back_everything(category, scenario):
    async with temporary_schema("tgfo_v219f") as (engine, _schema):
        async with engine.begin() as conn:
            await _seed(conn, [("bad", category, scenario, None), ("legacy", "IPO", "normal", None)])
            before = await _values(conn)
        with pytest.raises(sa.exc.DBAPIError) as caught:
            async with engine.begin() as conn:  # 与 MigrationRunner 同：一份迁移一个事务
                await run_sql_file(conn, _V219)
        assert sqlstate(caught.value) == "P0001"
        assert "V219:" in str(caught.value)
        async with engine.connect() as conn:
            assert await _values(conn) == before, "失败的迁移不得留下部分改动（旧 IPO 行也不搬）"
            assert _BACKUP not in await table_names(conn)
            assert not (_CHECKS & await constraint_names(conn, "projects"))
            assert await _default(conn) == "'C'::character varying"


async def test_v219_is_idempotent_and_checks_constraints_on_this_table_only():
    async with temporary_schema("tgfo_v219a") as (engine_a, _a):
        async with engine_a.begin() as conn:
            await _seed(conn, _MATRIX)
            await run_sql_file(conn, _V219)
        # 另一个 schema 已有同名约束：只按名字查全库目录会误判「已存在」而漏建
        async with temporary_schema("tgfo_v219b") as (engine_b, _b):
            async with engine_b.begin() as conn:
                await _seed(conn, _MATRIX)
                await run_sql_file(conn, _V219)
                assert _CHECKS <= await constraint_names(conn, "projects")
        async with engine_a.begin() as conn:
            once = await _values(conn)
            backups = await conn.scalar(sa.text(f"SELECT count(*) FROM {_BACKUP}"))
            await run_sql_file(conn, _V219)
            assert await _values(conn) == once
            assert await conn.scalar(sa.text(f"SELECT count(*) FROM {_BACKUP}")) == backups


async def test_parent_mirrors_shared_columns_and_dry_run_on_shared_copy():
    """共享库 projects 分类列只读复制进临时 schema 跑 V219：不 fail-closed，改动行与判定逐行可预期。"""
    async with temporary_schema("tgfo_v219s") as (engine, _schema):
        async with engine.begin() as conn:
            await conn.exec_driver_sql(_PROJECTS_DDL)
            shape_sql = sa.text("""
                SELECT column_name, data_type, character_maximum_length, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_schema = :schema AND table_name = 'projects'
                  AND column_name IN ('business_category', 'scenario', 'template_type')
                ORDER BY column_name
            """)
            mine = [tuple(r) for r in await conn.execute(shape_sql, {"schema": _schema})]
            shared = [tuple(r) for r in await conn.execute(shape_sql, {"schema": "public"})]
            shared_has_v219 = await conn.scalar(sa.text("""
                SELECT count(*) FROM pg_constraint WHERE conrelid = 'public.projects'::regclass
                  AND conname = 'ck_projects_business_category_registered'
            """))
            if shared_has_v219:  # 共享库已跑过 V219：只有分类默认值不同
                mine = [r if r[0] != "business_category" else (*r[:4], None) for r in mine]
            assert mine == shared, "临时父表与共享库 projects 列定义不一致，矩阵用例的前提失效"

            await conn.exec_driver_sql("""
                INSERT INTO projects (id, business_category, scenario, template_type)
                SELECT id, business_category, scenario, template_type FROM public.projects
            """)
            source = {r[0]: (r[1], r[2], r[3]) for r in await conn.execute(
                sa.text("SELECT id, business_category, scenario, template_type FROM projects"))}
            assert source, "共享库没有项目，dry-run 空转"
            await run_sql_file(conn, _V219)
            after = await _values(conn)
            changed = {pid for pid, (c, s, _t) in source.items() if after[pid] != (c, s)}
            backed = {r[0] for r in await conn.execute(sa.text(f"SELECT project_id FROM {_BACKUP}"))}
            assert changed <= backed, "改了值却没备份的行，R219 无法恢复"
            for pid, (category, scenario, template_type) in source.items():
                assert pc.resolve(category, scenario, template_type) == pc.resolve(*after[pid], template_type), pid
                if category is not None and category.strip(" ").upper() in pc.LEGACY_SCENARIO_CATEGORIES:
                    assert after[pid] == (None, pc.LEGACY_SCENARIO_CATEGORIES[category.strip(" ").upper()])
