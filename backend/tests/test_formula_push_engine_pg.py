"""公式推送底稿级 SAVEPOINT 的真实 PostgreSQL 守卫。

SQLite 能验证回滚结果，但不能证明 SQL 失败后事务不会保持 aborted。本测试使用临时 schema，
第一张底稿在真实保存点内执行不存在的 SQL，第二张底稿继续走真实 CAS 写入、状态保存和提交。
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import engine
from app.models.formula_push_models import FormulaPushState
from app.services.formula_push import engine as push
from app.services.formula_push.bindings.e1 import WorkpaperTarget
from app.services.formula_push.rules import PushRule, PushSource, PushTarget

_BACKEND = Path(__file__).resolve().parents[1]
_V169 = _BACKEND / "migrations" / "V169__formula_push_engine.sql"


async def _run_sql_file(conn, path: Path) -> None:
    from app.core.migration_runner import MigrationRunner

    for statement in MigrationRunner._split_sql_statements(path.read_text(encoding="utf-8")):
        await conn.exec_driver_sql(statement)


async def _scenario(monkeypatch) -> dict:
    assert engine.dialect.name == "postgresql", f"需要 PostgreSQL，实际 {engine.dialect.name}"
    schema = f"tmp_formula_push_isolation_{uuid.uuid4().hex[:10]}"
    f1, f2 = uuid.uuid4(), uuid.uuid4()
    project_id = uuid.uuid4()
    rules = tuple(
        PushRule(
            rule_id=f"{code}.value", page_key=f"workpaper:{code}", stage="source", policy="system",
            target=PushTarget(domain="workpaper", wp_code=code, sheet_code=code,
                              item_id=f"{code}-value", fields=("value",)),
            source=PushSource(kind="derivation", name="test"), triggers=("manual",), description="PG 隔离守卫",
        )
        for code in ("F1", "F2")
    )

    class Binding:
        def __init__(self, code: str):
            self.wp_code = code
            self.account_prefixes = ("999",)
            self.derivations = frozenset()

        async def load_sources(self, db, project_id, year, wp_id):
            if self.wp_code == "F1":
                await db.execute(sa.text("SELECT * FROM formula_push_missing_probe"))
            return SimpleNamespace(warnings=[], template_type=None)

        def workpaper_targets(self, rule, entries, sources):
            item_id = f"{self.wp_code}-value"
            return [WorkpaperTarget(
                rule_id=rule.rule_id, policy=rule.policy,
                addr_id=f"{self.wp_code}/{self.wp_code}/{item_id}", item_id=item_id,
                formula_value=f"{self.wp_code}-new", current_value=entries.get(item_id),
            )], []

        @staticmethod
        def apply(entries, target, value):
            value = str(value)
            changed = entries.get(target.item_id) != value
            entries[target.item_id] = value
            return changed

        @staticmethod
        def entry_warnings(entries):
            return []

    bindings = {code: Binding(code) for code in ("F1", "F2")}
    papers = {"F1": push._Paper(f1, "draft"), "F2": push._Paper(f2, "draft")}
    monkeypatch.setattr(push, "_project_audit_year", lambda db, project_id: _audit_year())
    monkeypatch.setattr(push, "load_push_rules", lambda: rules)
    monkeypatch.setattr(push, "supported_wp_codes", lambda: ("F1", "F2"))
    monkeypatch.setattr(push, "get_binding", lambda code: bindings[code])
    monkeypatch.setattr(push, "rules_for", lambda all_rules, *, wp_code, trigger: tuple(
        rule for rule in all_rules if rule.wp_code == wp_code and trigger in rule.triggers
    ))

    async def find_workpapers(db, project_id, wp_code):
        return [papers[wp_code]]

    monkeypatch.setattr(push, "_find_workpapers", find_workpapers)

    async with engine.begin() as admin:
        await admin.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    try:
        async with engine.connect() as conn:
            await conn.execute(sa.text(f'SET search_path TO "{schema}", public'))
            await conn.exec_driver_sql(
                "CREATE TABLE projects (id UUID PRIMARY KEY)"
            )
            await conn.exec_driver_sql(
                "CREATE TABLE working_paper (id UUID PRIMARY KEY, project_id UUID NOT NULL REFERENCES projects(id))"
            )
            await conn.exec_driver_sql(
                "CREATE TABLE checklist_responses ("
                "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), project_id UUID NOT NULL, "
                "wp_id UUID NOT NULL REFERENCES working_paper(id), item_id VARCHAR(256) NOT NULL, "
                "remark TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "content_version INTEGER NOT NULL DEFAULT 1, UNIQUE (wp_id, item_id))"
            )
            await _run_sql_file(conn, _V169)
            await conn.execute(sa.text("INSERT INTO projects (id) VALUES (:p)"), {"p": project_id})
            await conn.execute(sa.text(
                "INSERT INTO working_paper (id, project_id) VALUES (:w, :p), (:w2, :p)"
            ), {"w": f1, "w2": f2, "p": project_id})
            await conn.execute(sa.text(
                "INSERT INTO checklist_responses (project_id, wp_id, item_id, remark) "
                "VALUES (:p, :w1, 'F1-value', 'F1-old'), (:p, :w2, 'F2-value', 'F2-old')"
            ), {"p": project_id, "w1": f1, "w2": f2})
            await conn.commit()

            session = AsyncSession(bind=conn, expire_on_commit=False)
            try:
                result = await push.run_and_commit(
                    session, project_id=project_id, year=2025, trigger="manual",
                )
                rows = (await conn.execute(sa.text(
                    "SELECT wp_id, item_id, remark FROM checklist_responses ORDER BY item_id"
                ))).all()
                run = (await conn.execute(sa.text(
                    "SELECT status, detail FROM formula_push_run"
                ))).one()
                states = (await session.execute(sa.select(FormulaPushState))).scalars().all()
                return {
                    "result": result,
                    "rows": [(str(row[0]), row[1], row[2]) for row in rows],
                    "run": (run[0], run[1]),
                    "states": [(state.addr_id, state.last_run_id) for state in states],
                }
            finally:
                await session.close()
                await conn.rollback()
    finally:
        async with engine.begin() as admin:
            await admin.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


async def _audit_year() -> tuple[bool, int]:
    return True, 2025


def test_formula_push_continues_after_sql_failure_on_real_postgres(monkeypatch):
    snap = asyncio.run(_scenario(monkeypatch))
    result = snap["result"]

    assert result.status == "partial"
    assert [paper["status"] for paper in result.workpapers] == ["failed", "pushed"]
    assert "formula_push_missing_probe" in result.workpapers[0]["reason"]
    assert snap["rows"] == [
        (str(uuid.UUID(snap["rows"][0][0])), "F1-value", "F1-old"),
        (str(uuid.UUID(snap["rows"][1][0])), "F2-value", "F2-new"),
    ]
    assert snap["run"][0] == "partial"
    assert snap["run"][1]["wp"][0]["status"] == "failed"
    assert snap["run"][1]["wp"][1]["status"] == "pushed"
    assert snap["states"] == [("F2/F2/F2-value", snap["states"][0][1])]




# 多册保存点隔离同 Task 4 的 F1/F2 双 binding 机制（同一段 begin_nested/rollback 代码路径），
# SQLite 双册测试已在 test_formula_push_engine.py 覆盖地址重映射 + 缺册跳过 + 首册失败隔离。
# 全局 asyncpg engine 在 pytest-asyncio 跨测试函数的事件循环复用上有已知限制，不为重复验证写额外脚手架。
