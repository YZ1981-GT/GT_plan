"""真实 PostgreSQL 守卫（Task 56，NFR-2~5）：V187 真跑 + ORM 对账 + 约束语义 + 可见性 / 幂等 / 零部分写入 + 样本容量。

═══ 为什么必须真库 ═══

SQLite 测试库由 ORM metadata 建表：V187 的部分唯一索引、CHECK、不可延迟外键、ON DELETE RESTRICT 从来没有按迁移
原文在 PostgreSQL 上执行过，而生产库恰恰是 V187 建出来的。迁移与 ORM 任一层写错，SQLite 全绿。

═══ 隔离 ═══

- scratch schema（``tmp_v187_*``），``search_path`` 只含自己；V187 原文用 MigrationRunner **同一个分句器**切分后逐句执行；
  users / projects / disclosure_notes / staff_members / project_assignments 为去外键副本（V187 只引用前两者主键）。
- public **只读**：只查 information_schema / pg_catalog、三张表行数（前后各一次，必须相等）和真实项目快照体量。
- 结束 ``DROP SCHEMA CASCADE`` 并复查 schema 已不存在。``DATABASE_URL`` 非 PostgreSQL 时直接失败不 skip。

═══ 已知：V187 外键补建判断不限 schema ═══

V187 的 DO 块用 ``pg_constraint WHERE conname = 'fk_nct_current_version'`` 判断外键是否已建，不限定 schema。
同库别的 schema 已有同名约束（这里是 public）时会**跳过**补建。生产只有 public，不受影响；V187 已应用、不能改
（改了会触发 checksum 漂移）。守卫如实记录跳过，再执行 V187 自己的那条 ALTER 补齐，后续语义判据才完整。
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

YEAR = 2025
V187 = _BACKEND / "migrations" / "V187__note_content_templates_and_batch_apply.sql"
TABLES = ("note_content_templates", "note_content_template_versions", "note_text_batch_applications")


def _fk_free_copy(table: sa.Table, metadata: sa.MetaData) -> sa.Table:
    from sqlalchemy.dialects import postgresql

    def _type(column: sa.Column):
        t = column.type
        if isinstance(t, sa.Enum) and t.name:
            return postgresql.ENUM(*t.enums, name=t.name, create_type=False)
        return t

    return sa.Table(table.name, metadata, *[
        sa.Column(c.name, _type(c), primary_key=c.primary_key, nullable=c.nullable, server_default=c.server_default)
        for c in table.columns
    ])


def _enum_ddl(*tables: sa.Table) -> list[str]:
    seen = {c.type.name: list(c.type.enums) for t in tables for c in t.columns
            if isinstance(c.type, sa.Enum) and c.type.name}
    return [f"CREATE TYPE {name} AS ENUM ({', '.join(repr(v) for v in labels)})" for name, labels in sorted(seen.items())]


_COLUMNS_SQL = """
SELECT c.relname AS table_name, a.attname AS column_name, format_type(a.atttypid, a.atttypmod) AS type,
       a.attnotnull AS not_null, (ad.adbin IS NOT NULL) AS has_default
FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_attrdef ad ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
WHERE n.nspname = :schema AND c.relname::text = ANY(:tables) AND a.attnum > 0 AND NOT a.attisdropped
"""
_CONSTRAINTS_SQL = """
SELECT c.relname AS table_name, con.conname AS name, con.contype::text AS kind,
       pg_get_constraintdef(con.oid) AS definition, con.condeferrable AS deferrable
FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = :schema AND c.relname::text = ANY(:tables)
"""
_INDEXES_SQL = """
SELECT tablename AS table_name, indexname AS name, indexdef AS definition
FROM pg_indexes WHERE schemaname = :schema AND tablename::text = ANY(:tables)
"""


async def _catalog(conn, schema: str) -> dict[str, Any]:
    """三张表的列 / 约束 / 索引。必须用 search_path 指向该 schema 的连接查：外键定义里的表名才不带 schema 前缀。"""
    out: dict[str, Any] = {"columns": {}, "constraints": {}, "indexes": {}}
    params = {"schema": schema, "tables": list(TABLES)}
    for r in (await conn.execute(sa.text(_COLUMNS_SQL), params)).mappings():
        out["columns"].setdefault(r["table_name"], {})[r["column_name"]] = [r["type"], r["not_null"], r["has_default"]]
    for r in (await conn.execute(sa.text(_CONSTRAINTS_SQL), params)).mappings():
        out["constraints"].setdefault(r["table_name"], {})[r["name"]] = [r["kind"], r["definition"], r["deferrable"]]
    for r in (await conn.execute(sa.text(_INDEXES_SQL), params)).mappings():
        out["indexes"].setdefault(r["table_name"], {})[r["name"]] = r["definition"].replace(f" ON {schema}.", " ON ")
    return out


def _sqlstate(exc: BaseException) -> str:
    """``SQLSTATE:约束名``（asyncpg 原始异常上才有约束名）；判据要钉到具体约束，不能只看「报错了」。"""
    for e in (getattr(getattr(exc, "orig", None), "__cause__", None), getattr(exc, "orig", None), exc.__cause__):
        code = getattr(e, "sqlstate", None) or getattr(e, "pgcode", None)
        if code:
            name = getattr(e, "constraint_name", None)
            return f"{code}:{name}" if name else str(code)
    return type(exc).__name__


async def _probe(engine, statements: list[tuple[str, dict]]) -> str:
    """每个约束探针独立事务（失败会让事务 aborted）：返回首个失败语句的 SQLSTATE，全部成功为 accepted；一律回滚。"""
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            for sql, params in statements:
                await conn.execute(sa.text(sql), params)
            return "accepted"
        except sa.exc.DBAPIError as exc:
            return _sqlstate(exc)
        finally:
            await trans.rollback()


_VERSION_COLS = ("template_id, version_no, source_project_id, source_year, source_project_name, template_type, "
                 "report_scope, content_hash, byte_size")
_APP_COLS = ("source_kind, template_version_id, target_project_id, target_year, mutation_id, request_fingerprint, "
             "preview_digest, applied_count")


def _probes(ids: dict[str, Any]) -> dict[str, tuple[list[tuple[str, dict]], str]]:
    """约束探针：名称 → (语句, 期望「SQLSTATE:约束名」或 accepted)。多个 CHECK 同时违反时 PG 按约束名字母序报第一个。"""
    me, p, a, t1, v1, h1 = ids["me"], ids["P"], ids["A"], ids["t1"], ids["v1"], ids["h1"]

    def tpl(name: str, scope: str = "personal", deleted: bool = False, **over: Any) -> tuple[str, dict]:
        owner = {"personal": (me, None), "group": (None, p)}[scope]
        row = {"n": name, "s": scope, "u": owner[0], "g": owner[1], "d": deleted, **over}
        return ("INSERT INTO note_content_templates (name, owner_scope, owner_user_id, owner_group_project_id, "
                "is_deleted) VALUES (:n, :s, :u, :g, :d)", row)

    def ver(no: int, h: str) -> tuple[str, dict]:
        return (f"INSERT INTO note_content_template_versions ({_VERSION_COLS}) "
                "VALUES (:t, :no, :a, 2025, '子甲', 'soe', 'standalone', :h, 1)", {"t": t1, "no": no, "a": a, "h": h})

    def app(kind: str = "upload", version: Any = None, mutation: str = "probe-1", fp: str = "f" * 64,
            status: str = "succeeded") -> tuple[str, dict]:
        return (f"INSERT INTO note_text_batch_applications ({_APP_COLS}, status) "
                "VALUES (:k, :v, :a, 2025, :m, :fp, :pd, 1, :st)",
                {"k": kind, "v": version, "a": a, "m": mutation, "fp": fp, "pd": "d" * 64, "st": status})

    return {
        "ck_nct_owner_scope": ([tpl("探针", s="public")], "23514:ck_nct_owner_scope"),
        "ck_nct_owner_shape": ([tpl("探针", g=p)], "23514:ck_nct_owner_shape"),
        "ux_nct_personal_active_name": ([tpl("Dup"), tpl("DUP")], "23505:ux_nct_personal_active_name"),
        "personal_name_reusable_after_soft_delete": ([tpl("Gone", deleted=True), tpl("GONE")], "accepted"),
        "ux_nct_group_active_name": ([tpl("G1", "group"), tpl("g1", "group")], "23505:ux_nct_group_active_name"),
        "personal_and_group_same_name_coexist": ([tpl("Same"), tpl("same", "group")], "accepted"),
        "ux_nctv_template_version": ([ver(1, "b" * 64)], "23505:ux_nctv_template_version"),
        "ux_nctv_template_hash": ([ver(99, h1)], "23505:ux_nctv_template_hash"),
        "ck_nctv_hash_length": ([ver(98, "abc")], "23514:ck_nctv_hash_length"),
        "ck_nctv_version_positive": ([ver(0, "c" * 64)], "23514:ck_nctv_version_positive"),
        # 不可延迟：同一事务里先改指针、后落版本也不行 ⇒ 服务必须先 flush 版本再改 current_version_id
        "fk_nct_current_version_immediate": (
            [("UPDATE note_content_templates SET current_version_id = :x WHERE id = :t", {"x": uuid.uuid4(), "t": t1})],
            "23503:fk_nct_current_version"),
        "versions_block_template_delete": ([("DELETE FROM note_content_templates WHERE id = :t", {"t": t1})],
                                           "23503:note_content_template_versions_template_id_fkey"),
        "applications_block_version_delete": (
            [app("content_template", v1, "probe-del"),
             ("DELETE FROM note_content_template_versions WHERE id = :v", {"v": v1})],
            "23503:note_text_batch_applications_template_version_id_fkey"),
        "app_template_requires_version": ([app("content_template")], "23514:ck_ntba_source_template"),
        "app_non_template_forbids_version": ([app("upload", v1)], "23514:ck_ntba_source_template"),
        "ck_ntba_source_kind": ([app("email")], "23514:ck_ntba_source_kind"),
        "ck_ntba_status": ([app(status="failed")], "23514:ck_ntba_status"),
        "ck_ntba_request_hash": ([app(fp="short")], "23514:ck_ntba_request_hash"),
        "ux_ntba_project_mutation": ([app(mutation="dup-1"), app(mutation="dup-1")], "23505:ux_ntba_project_mutation"),
    }


async def _public_counts(conn) -> dict[str, int]:
    return {t: int(await conn.scalar(sa.text(f"SELECT count(*) FROM public.{t}"))) for t in TABLES}


async def _run_v187(engine, schema: str, snap: dict[str, Any]) -> None:
    """按 MigrationRunner 同一分句器逐句执行 V187 原文；外键若被不限 schema 的 DO 块跳过，执行 V187 自己那条 ALTER 补齐。"""
    from app.core.migration_runner import MigrationRunner

    text = V187.read_text(encoding="utf-8")
    statements = MigrationRunner._split_sql_statements(text)
    snap["v187_statements"] = len(statements)
    count_fk = ("SELECT count(*) FROM pg_constraint WHERE conname = 'fk_nct_current_version' "
                f"AND connamespace {{op}} '{schema}'::regnamespace")  # schema 名由本守卫生成（hex），非外部输入
    async with engine.begin() as conn:
        for stmt in statements:
            await conn.exec_driver_sql(stmt)
        snap["fk_after_v187"] = int(await conn.scalar(sa.text(count_fk.format(op="="))))
        snap["fk_in_other_schemas"] = int(await conn.scalar(sa.text(count_fk.format(op="<>"))))
        if snap["fk_after_v187"] == 0:
            alter = re.search(r"ALTER TABLE note_content_templates\s+ADD CONSTRAINT fk_nct_current_version.*?;",
                              text, flags=re.S)
            assert alter, "V187 里找不到 fk_nct_current_version 的 ALTER 语句"
            await conn.exec_driver_sql(alter.group(0).rstrip(";"))


async def _seed(Session, ids: dict[str, Any]) -> None:
    from app.models.base import ProjectStatus, UserRole
    from app.models.core import Project, User
    from app.models.report_models import DisclosureNote
    from app.models.staff_models import ProjectAssignment, StaffMember

    async with Session() as s:
        for key in ("me", "boss", "other"):
            s.add(User(id=ids[key], username=f"{key}_login", email=f"{key}@example.com", hashed_password="x",
                       role=UserRole.auditor))
        for key, name in (("P", "集团"), ("Q", "异组")):
            s.add(Project(id=ids[key], name=name, client_name=f"{name}公司", template_type="soe",
                          report_scope="standalone", status=ProjectStatus.execution))
        await s.flush()
        for key, name, parent in (("A", "子甲", "P"), ("B", "子乙", "P"), ("C", "异组子", "Q")):
            s.add(Project(id=ids[key], name=name, client_name=f"{name}公司", template_type="soe",
                          report_scope="standalone", status=ProjectStatus.execution, parent_project_id=ids[parent]))
        staff = StaffMember(name="经理甲", user_id=ids["boss"])
        s.add(staff)
        await s.flush()
        s.add(ProjectAssignment(project_id=ids["P"], staff_id=staff.id, role="manager"))
        for key, pid, code, title, html in (
            ("a_basic", "A", "一、1", "公司基本情况", "<p>子甲公司成立于2001年。</p>"),
            ("a_period", "A", "四、会计期间", "会计期间", "<p>会计年度自1月1日起至12月31日止。</p>"),
            ("b_basic", "B", "一、1", "公司基本情况", "<p>旧基本情况</p>"),
            ("b_period", "B", "四、会计期间", "会计期间", None),
        ):
            s.add(DisclosureNote(id=ids[key], project_id=ids[pid], year=YEAR, note_section=code, section_title=title,
                                 text_content=html, sort_index=1 if code == "一、1" else 2))
        await s.commit()


async def _service_scenarios(Session, ids: dict[str, Any], snap: dict[str, Any]) -> None:
    """真服务跑在 V187 建出的表上：兄弟可见 / 异组不可见、同 hash 复用版本、保存人姓名与最近引用版本。"""
    from app.models.note_content_template_models import NoteContentTemplate, NoteTextBatchApplication
    from app.models.report_models import DisclosureNote
    from app.services.note_content_template_snapshot import (
        get_template_detail,
        list_templates,
        save_snapshot,
        snapshot_preview,
    )

    def user(key: str) -> SimpleNamespace:
        return SimpleNamespace(id=ids[key], role="auditor")

    async def save(who: str, scope: str, name: str) -> dict[str, Any]:
        async with Session() as db:
            digest = (await snapshot_preview(db, ids["A"], YEAR, user=user(who), owner_scope=scope))["snapshot_digest"]
            result = await save_snapshot(db, project_id=ids["A"], year=YEAR, name=name, description=None,
                                         owner_scope=scope, snapshot_digest=digest, user=user(who))
            await db.commit()
            return result

    async def set_text(key: str, html: str) -> None:
        async with Session() as db:
            (await db.get(DisclosureNote, ids[key])).text_content = html
            await db.commit()

    async def names(project: str, who: str) -> list[str]:
        async with Session() as db:
            return sorted(i["name"] for i in (await list_templates(db, project_id=ids[project], user=user(who)))["items"])

    group = await save("boss", "group", "集团模板")
    mine = await save("me", "personal", "我的模板")
    ids.update(t1=uuid.UUID(mine["template_id"]), v1=uuid.UUID(mine["version_id"]), h1=mine["content_hash"])
    snap["visibility"] = {f"{who}@{p}": await names(p, who) for who in ("me", "other") for p in ("B", "C")}
    async with Session() as db:
        snap["visibility"]["group_detail@C"] = await get_template_detail(
            db, uuid.UUID(group["template_id"]), project_id=ids["C"], user=user("me")) is not None

    same = await save("boss", "group", "集团模板")
    await set_text("a_basic", "<p>子甲公司 2025 年完成改制。</p>")
    changed = await save("boss", "group", "集团模板")
    await set_text("a_basic", "<p>子甲公司成立于2001年。</p>")
    back = await save("boss", "group", "集团模板")
    async with Session() as db:
        tpl = await db.get(NoteContentTemplate, uuid.UUID(group["template_id"]))
        nos = sorted((await db.execute(sa.text("SELECT version_no FROM note_content_template_versions "
                                               "WHERE template_id = :t"), {"t": tpl.id})).scalars())
    first_id = group["version_id"]
    snap["idempotent"] = {
        "first": [group["version_no"], group["reused"]],
        "same": [same["version_no"], same["reused"], same["version_id"] == first_id],
        "changed": [changed["version_no"], changed["reused"]],
        "reverted": [back["version_no"], back["reused"], back["version_id"] == first_id],
        "current_is_v1": str(tpl.current_version_id) == first_id, "version_nos": nos,
    }
    async with Session() as db:  # 兄弟项目 B 引用过 v2，之后模板内容回退 ⇒ 当前 v1 与已引用 v2 不同
        db.add(NoteTextBatchApplication(
            source_kind="content_template", template_version_id=uuid.UUID(changed["version_id"]),
            target_project_id=ids["B"], target_year=YEAR, mutation_id="svc-applied", request_fingerprint="a" * 64,
            preview_digest="b" * 64, applied_count=1))
        await db.commit()
    async with Session() as db:
        item = {i["name"]: i for i in (await list_templates(db, project_id=ids["B"], user=user("boss"),
                                                            year=YEAR))["items"]}["集团模板"]
    snap["listing"] = {"created_by_name": item["current_version"]["created_by_name"],
                       "current_no": item["current_version"]["version_no"],
                       "last_applied_no": (item["last_applied"] or {}).get("version_no")}


async def _stale_scenario(Session, ids: dict[str, Any], snap: dict[str, Any]) -> None:
    """预览后他人改了两章中的一章：整批 409、两章都不写、无应用记录；对照组重新预览后同两章整批写入。"""
    from app.models.report_models import DisclosureNote
    from app.services.note_document_parser import ParsedSection
    from app.services.note_text_batch_apply import ApplyError, apply_batch, lock_target_notes
    from app.services.note_text_batch_service import build_preview, load_target_sections, locate_sources

    sources = [ParsedSection(source_id="s1", title="公司基本情况", html="<p>新基本情况</p>"),
               ParsedSection(source_id="s2", title="会计期间", html="<p>会计期间正文</p>")]
    mapping = {"s1": ids["b_basic"], "s2": ids["b_period"]}

    async def preview(db) -> dict[str, Any]:
        targets = await load_target_sections(db, ids["B"], YEAR, scope="narrative", include_content=True)
        # 映射全部手工指定（本场景只测并发 stale）；上传来源按章节树定位见 phase4 / 第 23 组
        located, matches, structural = locate_sources(sources, targets, manual_mappings=mapping)
        return build_preview(located, targets, matches, source_identity={"kind": "upload"}, structural_ids=structural)

    def selections(pv: dict[str, Any]) -> list[dict[str, Any]]:
        return [{"source_id": i["source_id"], "target_note_id": uuid.UUID(i["target_note_id"]), "mode": "replace",
                 "before_hash": i["before_hash"], "proposed_hash": i["proposed_hash"], "expected_updated_at": None,
                 "revoked_replacement_ids": []} for i in pv["items"] if i["target_note_id"]]

    async def apply(pv: dict[str, Any], mutation: str) -> dict[str, Any]:
        async with Session() as db:
            sels = selections(pv)
            locked = await lock_target_notes(db, ids["B"], YEAR, [s["target_note_id"] for s in sels])
            try:
                result = await apply_batch(
                    db, project_id=ids["B"], year=YEAR, locked_notes=locked, preview=await preview(db),
                    request_digest=pv["preview_digest"], selections=sels, source_kind="upload",
                    template_version_id=None, template_content_hash=None, source_metadata={"file_hash": "f" * 64},
                    mutation_id=mutation, request_fingerprint="e" * 64, user_id=ids["me"])
            except ApplyError as err:
                await db.rollback()
                return {"ok": False, "code": err.code, "stale": err.stale_notes}
            await db.commit()
            return {"ok": True, "applied": result["applied_count"]}

    async def state() -> dict[str, Any]:
        async with Session() as db:
            notes = {k: (await db.get(DisclosureNote, ids[k])).text_content for k in ("b_basic", "b_period")}
            apps = await db.scalar(sa.text("SELECT count(*) FROM note_text_batch_applications "
                                           "WHERE target_project_id = :p AND mutation_id LIKE 'stale-%'"), {"p": ids["B"]})
        return {**notes, "apps": int(apps)}

    async with Session() as db:
        stale_pv = await preview(db)
    async with Session() as db:
        (await db.get(DisclosureNote, ids["b_basic"])).text_content = "<p>他人刚保存</p>"
        await db.commit()
    stale = await apply(stale_pv, "stale-1")
    after_stale = await state()
    async with Session() as db:
        fresh_pv = await preview(db)
    fresh = await apply(fresh_pv, "stale-2")
    old, new = selections(stale_pv), selections(fresh_pv)
    snap["stale"] = {"items": len(old), "before_hash_changed": old[0]["before_hash"] != new[0]["before_hash"],
                     "result": stale, "after": after_stale, "fresh": fresh, "after_fresh": await state()}


async def _real_snapshot_sizes(db) -> list[dict[str, Any]]:
    """真库每个（项目, 年度）的快照体量（只读，生成快照不落库）：对照 design §11.2 冻结的硬上限。"""
    from app.services.note_content_template_snapshot import TemplateError, generate_snapshot

    pairs = (await db.execute(sa.text("SELECT DISTINCT project_id, year FROM public.disclosure_notes "
                                      "WHERE NOT is_deleted ORDER BY 1, 2"))).all()
    out = []
    for pid, year in pairs:
        try:
            snap = await generate_snapshot(db, pid, year)
        except TemplateError as err:  # 孤儿章节（项目已不存在）：如实记录，不当成样本
            out.append({"project_id": str(pid), "year": year, "error": err.code})
            continue
        out.append({"project_id": str(pid), "year": year, "byte_size": snap["byte_size"],
                    "sections": len(snap["sections_data"])})
    return out


async def _collect() -> dict[str, Any]:  # noqa: C901 - 单次采集覆盖全部场景
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.core.config import settings
    from app.models.core import Project, User
    from app.models.report_models import DisclosureNote
    from app.models.staff_models import ProjectAssignment, StaffMember

    snap: dict[str, Any] = {"harness_errors": [], "probes": {}}
    if not str(settings.DATABASE_URL).startswith("postgresql"):
        snap["harness_errors"].append("本守卫的判据是 PostgreSQL 约束与锁语义，必须真实 PostgreSQL")
        return snap
    ssl_off = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    admin = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, connect_args=dict(ssl_off))
    schema = f"tmp_v187_{uuid.uuid4().hex[:10]}"
    ids: dict[str, Any] = {k: uuid.uuid4() for k in (
        "me", "boss", "other", "P", "Q", "A", "B", "C", "a_basic", "a_period", "b_basic", "b_period")}
    prereq = (User.__table__, Project.__table__, DisclosureNote.__table__, StaffMember.__table__,
              ProjectAssignment.__table__)
    engine = None
    try:
        async with admin.connect() as conn:
            snap["public_before"] = await _public_counts(conn)
            snap["public_catalog"] = await _catalog(conn, "public")
        async with async_sessionmaker(admin, expire_on_commit=False)() as db:
            snap["real_snapshots"] = await _real_snapshot_sizes(db)
            await db.rollback()
        async with admin.begin() as conn:
            await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool,
                                     connect_args={**ssl_off, "server_settings": {"search_path": schema}})
        md = sa.MetaData()
        for table in prereq:
            _fk_free_copy(table, md)
        async with engine.begin() as conn:
            for ddl in _enum_ddl(*prereq):
                await conn.exec_driver_sql(ddl)
            await conn.run_sync(md.create_all)
        await _run_v187(engine, schema, snap)
        async with engine.connect() as conn:
            snap["scratch_catalog"] = await _catalog(conn, schema)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        await _seed(Session, ids)
        await _service_scenarios(Session, ids, snap)
        await _stale_scenario(Session, ids, snap)
        for name, (statements, _expected) in _probes(ids).items():
            snap["probes"][name] = await _probe(engine, statements)
        async with admin.connect() as conn:
            snap["public_after"] = await _public_counts(conn)
    except Exception as exc:  # noqa: BLE001 - 采集失败必须让守卫红
        snap["harness_errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        if engine is not None:
            await engine.dispose()
        try:
            async with admin.begin() as conn:
                await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            async with admin.connect() as conn:
                snap["schema_left"] = int(await conn.scalar(
                    sa.text("SELECT count(*) FROM pg_namespace WHERE nspname = :s"), {"s": schema}))
        except Exception as exc:  # noqa: BLE001
            snap["harness_errors"].append(f"cleanup: {type(exc).__name__}: {exc}")
        await admin.dispose()
    return snap


@pytest.fixture(scope="module")
def snapshot() -> dict[str, Any]:
    return asyncio.run(_collect())


def _dummy_ids() -> dict[str, Any]:
    return {**{k: uuid.uuid4() for k in ("me", "P", "A", "t1", "v1")}, "h1": "h" * 64}


# ── 采集本身 ────────────────────────────────────────────────────────────────


def test_harness_ran_without_errors(snapshot: dict[str, Any]) -> None:
    assert snapshot["harness_errors"] == []
    assert snapshot["v187_statements"] >= 15
    assert set(snapshot["probes"]) == set(_probes(_dummy_ids()))


def test_public_untouched_and_scratch_dropped(snapshot: dict[str, Any]) -> None:
    """public 只读：三张表前后行数一致；scratch schema 结束后不存在（无遗留模板或应用记录）。"""
    assert snapshot["public_after"] == snapshot["public_before"]
    assert snapshot["schema_left"] == 0


# ── V187 ↔ 生产库 ↔ ORM ─────────────────────────────────────────────────────


def test_v187_in_scratch_matches_production_catalog(snapshot: dict[str, Any]) -> None:
    """生产库（public）由 V187 建出：scratch 里按原文真跑 V187 后，列 / 约束 / 索引须与 public 逐项一致。"""
    pub, scr = snapshot["public_catalog"], snapshot["scratch_catalog"]
    assert set(pub["columns"]) == set(TABLES), "public 缺表：V187 未应用"
    for part in ("columns", "constraints", "indexes"):
        assert scr[part] == pub[part], part


def test_current_version_fk_present_and_not_deferrable(snapshot: dict[str, Any]) -> None:
    """服务「先落版本、再改指针」的前提：外键存在且不可延迟（可延迟时首版的错误顺序在 PG 上也会通过）。"""
    for catalog in (snapshot["public_catalog"], snapshot["scratch_catalog"]):
        kind, definition, deferrable = catalog["constraints"]["note_content_templates"]["fk_nct_current_version"]
        assert (kind, deferrable) == ("f", False)
        assert definition == ("FOREIGN KEY (current_version_id) REFERENCES note_content_template_versions(id) "
                              "ON DELETE SET NULL")


def _orm_tables() -> dict[str, sa.Table]:
    from app.models.note_content_template_models import (
        NoteContentTemplate,
        NoteContentTemplateVersion,
        NoteTextBatchApplication,
    )

    return {m.__table__.name: m.__table__ for m in (NoteContentTemplate, NoteContentTemplateVersion,
                                                     NoteTextBatchApplication)}


_PG_TYPE = {"VARCHAR": "character varying", "TIMESTAMP WITH TIME ZONE": "timestamp with time zone",
            "TIMESTAMP WITHOUT TIME ZONE": "timestamp without time zone", "TIMESTAMP": "timestamp without time zone",
            "INTEGER": "integer", "BOOLEAN": "boolean", "UUID": "uuid", "TEXT": "text", "JSONB": "jsonb"}
_FK_RE = re.compile(r"FOREIGN KEY \((\w+)\) REFERENCES (\w+)\((\w+)\)(?: ON DELETE (SET NULL|RESTRICT|CASCADE))?")


def _orm_type(column: sa.Column) -> str:
    from sqlalchemy.dialects import postgresql

    compiled = column.type.compile(dialect=postgresql.dialect())
    m = re.fullmatch(r"([A-Z ]+?)(\(\d+\))?", compiled)
    assert m, compiled
    return _PG_TYPE.get(m.group(1), m.group(1).lower()) + (m.group(2) or "")


@pytest.mark.parametrize("table", TABLES)
def test_orm_columns_match_v187(snapshot: dict[str, Any], table: str) -> None:
    """NFR-2「迁移 ↔ ORM」：列集合、类型、可空性逐列一致（ORM 多一列 ⇒ 运行期 UndefinedColumn）。"""
    db_cols = snapshot["scratch_catalog"]["columns"][table]
    orm = _orm_tables()[table]
    assert set(db_cols) == set(orm.columns.keys())
    drift = {c.name: {"orm": [_orm_type(c), not c.nullable], "v187": db_cols[c.name][:2]} for c in orm.columns
             if [_orm_type(c), not c.nullable] != db_cols[c.name][:2]}
    assert drift == {}


@pytest.mark.parametrize("table", TABLES)
def test_orm_declares_every_v187_check_index_and_fk(snapshot: dict[str, Any], table: str) -> None:
    """CHECK 名、索引名与唯一性、外键（列 → 表.列 + ON DELETE）三项与 V187 逐一对上（SQLite 测试库按 ORM 建表）。"""
    cons, idx = snapshot["scratch_catalog"]["constraints"][table], snapshot["scratch_catalog"]["indexes"][table]
    orm = _orm_tables()[table]
    assert {c.name for c in orm.constraints if isinstance(c, sa.CheckConstraint)} == {
        n for n, (kind, _d, _x) in cons.items() if kind == "c"}
    assert {i.name: bool(i.unique) for i in orm.indexes} == {
        n: d.startswith("CREATE UNIQUE INDEX") for n, d in idx.items() if not n.endswith("_pkey")}
    db_fks = set()
    for kind, definition, _x in cons.values():
        if kind == "f":
            m = _FK_RE.fullmatch(definition)
            assert m, definition
            db_fks.add((m.group(1), m.group(2), m.group(3), m.group(4) or "NO ACTION"))
    assert {(fk.parent.name, fk.column.table.name, fk.column.name, (fk.ondelete or "NO ACTION").upper())
            for fk in orm.foreign_keys} == db_fks


# ── 约束语义（V187 原文建出的表）──────────────────────────────────────────


@pytest.mark.parametrize("name", sorted(_probes(_dummy_ids())))
def test_constraint_semantics_on_real_pg(snapshot: dict[str, Any], name: str) -> None:
    assert snapshot["probes"][name] == _probes(_dummy_ids())[name][1]


# ── 真服务跑在 V187 表上 ───────────────────────────────────────────────────


def test_sibling_visible_other_group_invisible(snapshot: dict[str, Any]) -> None:
    """AC-8.1：同集团兄弟项目可见集团模板；异集团不可见（详情直接按 ID 也拿不到）；个人模板只本人可见。"""
    assert snapshot["visibility"] == {
        "me@B": ["我的模板", "集团模板"], "me@C": ["我的模板"],
        "other@B": ["集团模板"], "other@C": [],
        "group_detail@C": False,
    }


def test_same_hash_reuses_version_and_revert_points_back(snapshot: dict[str, Any]) -> None:
    """AC-7.4：内容不变 ⇒ 复用原版本不增版本号；改内容 ⇒ v2；改回去 ⇒ 复用 v1 且当前版本指回 v1。"""
    assert snapshot["idempotent"] == {
        "first": [1, False], "same": [1, True, True], "changed": [2, False], "reverted": [1, True, True],
        "current_is_v1": True, "version_nos": [1, 2],
    }


def test_listing_saver_name_and_last_applied_on_real_pg(snapshot: dict[str, Any]) -> None:
    """第 10 组新增的两条查询在真 PG 上带数据执行：保存人取人员档案姓名；最近引用 v2、当前 v1（内容回退）。"""
    assert snapshot["listing"] == {"created_by_name": "经理甲", "current_no": 1, "last_applied_no": 2}


def test_stale_preview_writes_nothing(snapshot: dict[str, Any]) -> None:
    """AC-4.3：预览后两章中的一章被他人改过 ⇒ 整批 409，两章都不写、无应用记录；重新预览后同两章整批写入。"""
    s = snapshot["stale"]
    assert s["items"] == 2 and s["before_hash_changed"] is True, "夹具没有制造出过期预览，下面的判据空转"
    assert s["result"] == {"ok": False, "code": "NOTE_BATCH_STALE_PREVIEW", "stale": ["一、1"]}
    assert s["after"] == {"b_basic": "<p>他人刚保存</p>", "b_period": None, "apps": 0}
    assert s["fresh"] == {"ok": True, "applied": 2}
    assert s["after_fresh"] == {"b_basic": "<p>新基本情况</p>", "b_period": "<p>会计期间正文</p>", "apps": 1}


# ── 样本容量（NFR-5）─────────────────────────────────────────────────────────


def test_real_project_snapshots_within_frozen_hard_caps(snapshot: dict[str, Any]) -> None:
    """真库每个项目年度的全套快照都在 design §11.2 冻结硬上限内：超了就保存不了模板（413）。"""
    from app.services.note_content_template_snapshot import _MAX_SECTIONS_DATA_BYTES
    from app.services.note_document_parser import MAX_SECTIONS

    samples = [s for s in snapshot["real_snapshots"] if "byte_size" in s]
    assert samples, "真库没有任何附注章节：样本为空时本判据不成立"
    assert max(s["byte_size"] for s in samples) <= _MAX_SECTIONS_DATA_BYTES
    assert max(s["sections"] for s in samples) <= MAX_SECTIONS
