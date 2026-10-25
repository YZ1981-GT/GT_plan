"""K2 审定表族 canary：真实 PostgreSQL 取数、写入与状态链路。

spec: formula-push-balance-adj-batch-c · 任务 4 · 需求 C4

本测试使用独立临时 schema，避免污染业务项目：

* ``load_tb_audited`` 从真实 PostgreSQL ``trial_balance`` 按 1901 前缀汇总；
* ``load_hall_adjustments`` 从真实 ``adjustments`` + ``adjustment_entries`` 汇总，
  只纳入 approved 且排除 origin=workpaper；
* K2 引擎真实执行公式、动态行派生、CAS upsert、formula_push_run/state；
* 首次提交后检查写入结果，第二次提交检查幂等；最后删除临时 schema。

项目年度解析、模板类型和 SSE 是本 canary 的外围副作用，分别使用固定年度、空模板类型
和空广播隔离；数据库取数与公式推送写入不 mock。
"""
from __future__ import annotations

import asyncio
import json
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
from app.services.formula_push import engine as push
from app.services.formula_push import bindings as bindings_registry
from app.services.formula_push import sources as push_sources

_BACKEND = Path(__file__).resolve().parents[1]
_V169 = _BACKEND / "migrations" / "V169__formula_push_engine.sql"
_YEAR = 2025


def _dynamic_rows_json(*row_ids: str) -> str:
    return json.dumps(
        [{"rowId": row_id, "label": f"项目{index}"} for index, row_id in enumerate(row_ids, 1)],
        ensure_ascii=False,
        separators=(",", ":"),
    )


async def _run_sql_file(conn, path: Path) -> None:
    from app.core.migration_runner import MigrationRunner

    for statement in MigrationRunner._split_sql_statements(path.read_text(encoding="utf-8")):
        await conn.exec_driver_sql(statement)


async def _scenario(monkeypatch) -> dict:
    if engine.dialect.name != "postgresql":
        pytest.skip(f"K2 canary 需要 PostgreSQL，当前方言为 {engine.dialect.name}")

    schema = f"tmp_formula_push_k2_{uuid.uuid4().hex[:10]}"
    project_id = uuid.uuid4()
    wp_index_id = uuid.uuid4()
    wp_id = uuid.uuid4()

    # 只隔离项目年度 / 附注模板 / SSE；K2 binding.load_sources 保持生产实现，
    # 因而 trial_balance 与 adjustment_entries 查询仍走真实 PostgreSQL。
    async def fixed_audit_year(db, pid):
        assert pid == project_id
        return True, _YEAR

    async def no_template_type(db, pid):
        assert pid == project_id
        return None

    monkeypatch.setattr(push, "_project_audit_year", fixed_audit_year)
    monkeypatch.setattr(bindings_registry, "_load_template_type", no_template_type, raising=False)
    # _load_template_type 是 balance_adj 模块的全局符号，需在定义它的模块上替换。
    from app.services.formula_push.bindings import balance_adj

    monkeypatch.setattr(balance_adj, "_load_template_type", no_template_type)
    monkeypatch.setattr(push, "_broadcast", lambda result: None)

    async with engine.begin() as admin:
        await admin.execute(sa.text(f'CREATE SCHEMA "{schema}"'))

    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text(f'SET search_path TO "{schema}", public'))
            db_identity = (await conn.execute(sa.text(
                "SELECT current_database(), current_user, current_schema(), version()"
            ))).one()

            # 只建真实调用链需要的最小表。字段名与生产 ORM / 迁移一致；
            # 不用 ORM create_all，避免把 public schema 的其他表带进临时 schema。
            await conn.exec_driver_sql(
                "CREATE TABLE projects (id UUID PRIMARY KEY)"
            )
            await conn.exec_driver_sql(
                "CREATE TABLE wp_index ("
                "id UUID PRIMARY KEY, project_id UUID NOT NULL REFERENCES projects(id), "
                "wp_code VARCHAR(50) NOT NULL, is_deleted BOOLEAN NOT NULL DEFAULT false)"
            )
            await conn.exec_driver_sql(
                "CREATE TABLE working_paper ("
                "id UUID PRIMARY KEY, project_id UUID NOT NULL REFERENCES projects(id), "
                "wp_index_id UUID NOT NULL REFERENCES wp_index(id), "
                "status VARCHAR(50) NOT NULL DEFAULT 'draft', "
                "is_deleted BOOLEAN NOT NULL DEFAULT false)"
            )
            await conn.exec_driver_sql(
                "CREATE TABLE checklist_responses ("
                "id UUID PRIMARY KEY, project_id UUID NOT NULL REFERENCES projects(id), "
                "wp_id UUID NOT NULL REFERENCES working_paper(id), "
                "item_id VARCHAR(256) NOT NULL, remark TEXT, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "content_version INTEGER NOT NULL DEFAULT 1, "
                "UNIQUE (wp_id, item_id))"
            )
            await conn.exec_driver_sql(
                "CREATE TYPE account_category AS ENUM "
                "('asset', 'liability', 'equity', 'revenue', 'expense')"
            )
            await conn.exec_driver_sql(
                "CREATE TYPE adjustment_type AS ENUM ('aje', 'rje')"
            )
            await conn.exec_driver_sql(
                "CREATE TYPE review_status AS ENUM "
                "('draft', 'pending_review', 'approved', 'rejected')"
            )
            await conn.exec_driver_sql(
                "CREATE TABLE trial_balance ("
                "id UUID PRIMARY KEY, project_id UUID NOT NULL REFERENCES projects(id), "
                "year INTEGER NOT NULL, company_code VARCHAR(50) NOT NULL, "
                "standard_account_code VARCHAR(50) NOT NULL, account_name TEXT, "
                "account_category account_category NOT NULL, unadjusted_amount NUMERIC(20,2), "
                "rje_adjustment NUMERIC(20,2) NOT NULL DEFAULT 0, "
                "aje_adjustment NUMERIC(20,2) NOT NULL DEFAULT 0, "
                "audited_amount NUMERIC(20,2), opening_balance NUMERIC(20,2), "
                "is_deleted BOOLEAN NOT NULL DEFAULT false)"
            )
            await conn.exec_driver_sql(
                "CREATE TABLE adjustments ("
                "id UUID PRIMARY KEY, project_id UUID NOT NULL REFERENCES projects(id), "
                "year INTEGER NOT NULL, adjustment_type adjustment_type NOT NULL, "
                "review_status review_status NOT NULL DEFAULT 'draft', "
                "origin VARCHAR(20) NOT NULL DEFAULT 'manual', "
                "is_deleted BOOLEAN NOT NULL DEFAULT false)"
            )
            await conn.exec_driver_sql(
                "CREATE TABLE adjustment_entries ("
                "id UUID PRIMARY KEY, adjustment_id UUID NOT NULL REFERENCES adjustments(id), "
                "standard_account_code VARCHAR(50) NOT NULL, account_name TEXT, "
                "debit_amount NUMERIC(20,2) NOT NULL DEFAULT 0, "
                "credit_amount NUMERIC(20,2) NOT NULL DEFAULT 0, "
                "is_deleted BOOLEAN NOT NULL DEFAULT false)"
            )
            await _run_sql_file(conn, _V169)

            # 项目与 K2 底稿。
            await conn.execute(sa.text("INSERT INTO projects (id) VALUES (:p)"), {"p": project_id})
            await conn.execute(sa.text(
                "INSERT INTO wp_index (id, project_id, wp_code) VALUES (:i, :p, 'K2')"
            ), {"i": wp_index_id, "p": project_id})
            await conn.execute(sa.text(
                "INSERT INTO working_paper (id, project_id, wp_index_id) VALUES (:w, :p, :i)"
            ), {"w": wp_id, "p": project_id, "i": wp_index_id})

            # 两条 1901 前缀试算表行：load_tb_audited 必须汇总本级 + 子级。
            await conn.execute(sa.text(
                "INSERT INTO trial_balance "
                "(id, project_id, year, company_code, standard_account_code, account_name, "
                " account_category, unadjusted_amount, audited_amount, opening_balance) "
                "VALUES (:id, :p, :y, '001', :code, :name, 'asset', :unadj, :audited, :opening)"
            ), [
                {
                    "id": uuid.uuid4(), "p": project_id, "y": _YEAR, "code": "1901",
                    "name": "其他流动资产", "unadj": Decimal("90000"),
                    "audited": Decimal("100000"), "opening": Decimal("60000"),
                },
                {
                    "id": uuid.uuid4(), "p": project_id, "y": _YEAR, "code": "190101",
                    "name": "其他流动资产明细", "unadj": Decimal("20000"),
                    "audited": Decimal("25000"), "opening": Decimal("15000"),
                },
                {
                    "id": uuid.uuid4(), "p": project_id, "y": _YEAR, "code": "1701",
                    "name": "无形资产", "unadj": Decimal("1"),
                    "audited": Decimal("999"), "opening": Decimal("100"),
                },
            ])

            # 大厅调整：approved + 非 workpaper 的 1901 本级/子级计入；draft 与
            # origin=workpaper 必须排除。预期 ADJ('1901','aje_net') = 3500 + 500 = 4000。
            adjustments = [
                (Decimal("3500"), "approved", "manual", "1901"),
                (Decimal("500"), "approved", "manual", "190101"),
                (Decimal("900"), "draft", "manual", "1901"),
                (Decimal("700"), "approved", "workpaper", "1901"),
            ]
            for debit, status, origin, code in adjustments:
                adjustment_id = uuid.uuid4()
                await conn.execute(sa.text(
                    "INSERT INTO adjustments "
                    "(id, project_id, year, adjustment_type, review_status, origin) "
                    "VALUES (:id, :p, :y, 'aje', :status, :origin)"
                ), {
                    "id": adjustment_id, "p": project_id, "y": _YEAR,
                    "status": status, "origin": origin,
                })
                await conn.execute(sa.text(
                    "INSERT INTO adjustment_entries "
                    "(id, adjustment_id, standard_account_code, account_name, debit_amount, credit_amount) "
                    "VALUES (:id, :a, :code, :name, :debit, 0)"
                ), {
                    "id": uuid.uuid4(), "a": adjustment_id, "code": code,
                    "name": "其他流动资产", "debit": debit,
                })

            # 动态审定表行：50000+1000 + 30000+500 + 20000 = 101500。
            k2_entries = {
                "K2-1-rows": _dynamic_rows_json("contract-cost", "prepayment", "other"),
                "K2-1-contract-cost-unadj": "50000",
                "K2-1-contract-cost-aje": "1000",
                "K2-1-contract-cost-rje": "0",
                "K2-1-prepayment-unadj": "30000",
                "K2-1-prepayment-aje": "0",
                "K2-1-prepayment-rje": "500",
                "K2-1-other-unadj": "20000",
                "K2-1-other-aje": "0",
                "K2-1-other-rje": "0",
            }
            for item_id, remark in k2_entries.items():
                await conn.execute(sa.text(
                    "INSERT INTO checklist_responses "
                    "(id, project_id, wp_id, item_id, remark) "
                    "VALUES (:id, :p, :w, :item, :remark)"
                ), {
                    "id": uuid.uuid4(), "p": project_id, "w": wp_id,
                    "item": item_id, "remark": remark,
                })
            await conn.commit()

            session = AsyncSession(bind=conn, expire_on_commit=False)
            try:
                # 显式读取两条真实 PG source，给 canary 留下可检查的取数证据。
                tb_snapshot = await push_sources.load_tb_audited(
                    session, project_id, _YEAR, ("1901",)
                )
                hall_snapshot = await push_sources.load_hall_adjustments(
                    session, project_id, _YEAR, ("1901",)
                )

                first = await push.run_and_commit(
                    session,
                    project_id=project_id,
                    year=_YEAR,
                    trigger="manual",
                    codes=("K2",),
                )
                rows_after_first = (await session.execute(sa.text(
                    "SELECT item_id, remark FROM checklist_responses "
                    "WHERE wp_id = :w ORDER BY item_id"
                ), {"w": wp_id})).all()
                states_after_first = (await session.execute(sa.text(
                    "SELECT addr_id, rule_id, state FROM formula_push_state "
                    "WHERE project_id = :p AND year = :y ORDER BY addr_id"
                ), {"p": project_id, "y": _YEAR})).all()
                run_after_first = (await session.execute(sa.text(
                    "SELECT status, detail FROM formula_push_run "
                    "WHERE project_id = :p AND year = :y ORDER BY started_at DESC LIMIT 1"
                ), {"p": project_id, "y": _YEAR})).one()

                second = await push.run_and_commit(
                    session,
                    project_id=project_id,
                    year=_YEAR,
                    trigger="manual",
                    codes=("K2",),
                )
                rows_after_second = (await session.execute(sa.text(
                    "SELECT item_id, remark FROM checklist_responses "
                    "WHERE wp_id = :w ORDER BY item_id"
                ), {"w": wp_id})).all()
                run_count = (await session.execute(sa.text(
                    "SELECT count(*) FROM formula_push_run WHERE project_id = :p AND year = :y"
                ), {"p": project_id, "y": _YEAR})).scalar_one()
            finally:
                await session.close()

            # 结束当前连接事务，确保 DROP SCHEMA 不受查询事务持锁影响。
            await conn.rollback()

            return {
                "db_identity": tuple(db_identity),
                "tb_available": tb_snapshot.available,
                "tb_company_codes": tb_snapshot.company_codes,
                "tb_1901_ending": tb_snapshot.tb_data["1901"]["期末余额"],
                "tb_1901_opening": tb_snapshot.tb_data["1901"]["年初余额"],
                "tb_1901_occurrence": tb_snapshot.tb_data["1901"]["本期发生额"],
                "hall_1901_aje": hall_snapshot["1901"]["aje_net"],
                "first": first,
                "second": second,
                "rows_after_first": {row[0]: row[1] for row in rows_after_first},
                "rows_after_second": {row[0]: row[1] for row in rows_after_second},
                "states_after_first": [tuple(row) for row in states_after_first],
                "run_status": run_after_first[0],
                "run_detail": run_after_first[1],
                "run_count": run_count,
            }
    finally:
        async with engine.begin() as admin:
            await admin.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


def test_k2_canary_real_postgres(monkeypatch):
    """K2 真 PG canary：真实来源、推送值、状态记录与二次幂等均成立。"""
    snap = asyncio.run(_scenario(monkeypatch))

    # 连接确实落在 PostgreSQL 的临时 schema；不能用 SQLite 结果替代。
    database, user, schema, version = snap["db_identity"]
    assert database == "audit_platform"
    assert user
    assert schema.startswith("tmp_formula_push_k2_")
    assert version.startswith("PostgreSQL")

    # 真实 load_tb_audited：1901 本级 100000 + 190101 子级 25000。
    assert snap["tb_available"] is True
    assert snap["tb_company_codes"] == ("001",)
    assert snap["tb_1901_ending"] == Decimal("125000.00")
    assert snap["tb_1901_opening"] == Decimal("75000.00")
    assert snap["tb_1901_occurrence"] == Decimal("50000.00")

    # 真实 load_hall_adjustments：只纳入 approved、排除 workpaper，并按前缀吞子级。
    assert snap["hall_1901_aje"] == Decimal("4000.00")

    first = snap["first"]
    assert first.status == "succeeded"
    assert first.workpapers[0]["wp_code"] == "K2"
    assert first.workpapers[0]["status"] == "pushed"

    first_rows = snap["rows_after_first"]
    assert first_rows["K2-1-tb-amount"] == "125000"
    assert first_rows["K2-1-hall-adj-ending"] == "4000"
    assert first_rows["K2-1-audited-receivable"] == "101500"
    assert first_rows["K2-1-audited-net"] == "101500"
    assert "K2-1-audited-baddebt" not in first_rows

    # 真 PG formula_push_state：K2 两个 source + 两个 derived 目标。
    state_rows = snap["states_after_first"]
    assert len(state_rows) == 4
    assert {row[1] for row in state_rows} == {
        "K2.tb_amount",
        "K2.hall_adj.ending",
        "K2.audited_total.receivable",
        "K2.audited_total.net",
    }
    assert {row[2] for row in state_rows} == {"auto"}

    # 真 PG formula_push_run：首轮成功且明细含 K2。
    assert snap["run_status"] == "succeeded"
    assert any(item["wp_code"] == "K2" for item in snap["run_detail"]["wp"])

    # 第二次仍走真实 PG 事务，值不变且运行记录新增一行。
    assert snap["rows_after_second"] == first_rows
    assert snap["second"].status == "succeeded"
    changed_rules = {
        item.rule_id: item.action
        for item in snap["second"].items
        if item.rule_id in {
            "K2.tb_amount",
            "K2.hall_adj.ending",
            "K2.audited_total.receivable",
            "K2.audited_total.net",
        }
    }
    assert changed_rules == {
        "K2.tb_amount": "unchanged",
        "K2.hall_adj.ending": "unchanged",
        "K2.audited_total.receivable": "unchanged",
        "K2.audited_total.net": "unchanged",
    }
    assert snap["run_count"] == 2
