"""存量项目附注对齐 —— 读取 / 执行 / 备份 / 恢复（spec disclosure-note-template-word-realignment Phase 3，design §4）。

调用方管事务：每个项目一个事务。:func:`realign_project` 先锁该项目该年度的附注行再读，计划、备份、执行在同一
事务里；执行后重算计划，动作数必须为 0（幂等），已有行的正文 / 表格哈希必须逐行不变，否则抛错由调用方回滚。

只改树结构与编号，不改正文、表格（表格结构修复待表格口径拍板）、编辑人与更新时间（系统修复不算用户编辑）、
历史留痕表（校验结果、批量写入记录、trace、交付状态 —— 按旧编号记录是事实）。

备份 / 恢复只支持 PostgreSQL：``row_to_json`` / ``json_populate_recordset`` 按库内全部列原样导出导入，
ORM 没声明的列也不丢；恢复 = 删掉该范围的行再按备份原 id 插回（库内无外键引用 ``disclosure_notes``）。
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.models.formula_push_models import FormulaPushState
from app.models.note_trim_models import NoteSectionInstance
from app.models.report_models import DisclosureNote
from app.services.disclosure_engine import DisclosureEngine
from app.services.note_project_realign import NoteRow, RealignPlan, RelatedRow, plan_realignment, plan_related
from app.services.note_section_catalog import normalize_section_code, template_json_path

BACKUP_VERSION = 1
#: 备份范围：表 → 是否按年度过滤（裁剪页章节实例没有年度列，按项目整体备份）
BACKUP_TABLES: dict[str, bool] = {
    "disclosure_notes": True, "formula_push_state": True, "note_section_locks": True, "note_section_instances": False,
}
#: 章节锁表没有 ORM 模型（V046 建表，服务走裸 SQL）；只声明本工具用到的列，查询 / 改写走 Core（类型可移植）
LOCKS = sa.Table(
    "note_section_locks", sa.MetaData(),
    sa.Column("id", sa.Uuid, primary_key=True), sa.Column("project_id", sa.Uuid, nullable=False),
    sa.Column("year", sa.Integer, nullable=False), sa.Column("section_code", sa.String, nullable=False),
    sa.Column("released_at", sa.DateTime(timezone=True)),
)


class RealignError(RuntimeError):
    """对齐无法安全完成（调用方回滚该项目事务）。"""


class RealignSkipped(RealignError):
    """按规则不处理（如项目已删除），不算失败。"""


def _hash(value: Any) -> str:
    raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


def seed_index(template_type: str) -> dict[str, dict[str, Any]]:
    """现行编号 → 原始种子节（``legacy_titles`` / ``scope_titles`` 只在原始种子里）。"""
    data = json.loads(template_json_path(template_type).read_text(encoding="utf-8-sig"))
    return {normalize_section_code(s["section_number"], template_type=template_type): s
            for s in data.get("sections", []) if s.get("section_number")}


async def load_rows(db: AsyncSession, project_id: uuid.UUID, year: int, *, lock: bool = False) -> list[NoteRow]:
    """该项目该年度全部附注行（含软删），Core 查询（不进 ORM 身份映射，执行后再读拿到的是库内现值）。"""
    t = DisclosureNote.__table__
    stmt = sa.select(t.c.id, t.c.note_section, t.c.section_title, t.c.section_id, t.c.parent_section_id, t.c.level,
                     t.c.sort_index, t.c.sort_order, t.c.is_deleted, t.c.text_content, t.c.table_data
                     ).where(t.c.project_id == project_id, t.c.year == year)
    if lock:
        stmt = stmt.with_for_update()
    return [NoteRow(id=str(r.id), note_section=r.note_section, section_title=r.section_title or "",
                    section_id=r.section_id, parent_section_id=r.parent_section_id, level=r.level,
                    sort_index=r.sort_index, sort_order=r.sort_order, is_deleted=bool(r.is_deleted),
                    text_hash=_hash(r.text_content), table_hash=_hash(r.table_data))
            for r in (await db.execute(stmt)).all()]


async def load_related(db: AsyncSession, project_id: uuid.UUID, year: int, codes: set[str]) -> list[RelatedRow]:
    """新旧编号下的关联行：推送状态（编号或 ``note://{编号}/`` 前缀）、裁剪页章节实例、未释放的章节锁。"""
    if not codes:
        return []
    fps = FormulaPushState.__table__
    prefix_hits = [sa.func.substr(fps.c.addr_id, 1, len(f"note://{c}/")) == f"note://{c}/" for c in sorted(codes)]
    out = [RelatedRow("formula_push_state", str(r.id), r.note_section or "", r.addr_id) for r in (await db.execute(
        sa.select(fps.c.id, fps.c.note_section, fps.c.addr_id).where(
            fps.c.project_id == project_id, fps.c.year == year,
            sa.or_(fps.c.note_section.in_(sorted(codes)), *prefix_hits)))).all()]
    nsi = NoteSectionInstance.__table__
    out += [RelatedRow("note_section_instances", str(r.id), r.section_number) for r in (await db.execute(
        sa.select(nsi.c.id, nsi.c.section_number).where(nsi.c.project_id == project_id,
                                                        nsi.c.section_number.in_(sorted(codes))))).all()]
    out += [RelatedRow("note_section_locks", str(r.id), r.section_code) for r in (await db.execute(
        sa.select(LOCKS.c.id, LOCKS.c.section_code).where(
            LOCKS.c.project_id == project_id, LOCKS.c.year == year, LOCKS.c.released_at.is_(None),
            LOCKS.c.section_code.in_(sorted(codes))))).all()]
    return out


async def build_plan(db: AsyncSession, project_id: uuid.UUID, year: int, *, lock: bool = False
                     ) -> tuple[RealignPlan, list[NoteRow], dict[str, Any]]:
    deleted = (await db.execute(sa.select(Project.is_deleted).where(Project.id == project_id))).scalar_one_or_none()
    if deleted is None or deleted:
        # 生成链对已删除项目取不到口径（按单体处理），按它对齐会把合并项目改成单体结构
        raise RealignSkipped("项目不存在或已删除（回收站），不处理")
    engine = DisclosureEngine(db)
    template_type = await engine._get_active_template_type(project_id)
    if template_type not in ("soe", "listed"):
        raise RealignError(f"项目模板类型为 {template_type}，只支持国企 / 上市种子")
    report_scope = (await engine._get_project_basic_info(project_id)).get("report_scope")
    templates = await engine._load_templates(project_id, template_type)
    rows = await load_rows(db, project_id, year, lock=lock)
    plan = plan_realignment(rows, templates, template_type=template_type, report_scope=report_scope,
                            seeds=seed_index(template_type))
    changes = plan.code_changes()
    plan_related(plan, await load_related(db, project_id, year, set(changes) | set(changes.values())))
    meta = {"template_type": template_type, "report_scope": report_scope, "templates": len(templates),
            "rows": len(rows), "active_rows": sum(not r.is_deleted for r in rows)}
    return plan, rows, meta


async def apply_plan(db: AsyncSession, project_id: uuid.UUID, year: int, plan: RealignPlan, template_type: str) -> None:
    t = DisclosureNote.__table__

    async def _update(note_id: str, values: dict[str, Any], *, expect_code: str | None = None) -> None:
        where = [t.c.id == uuid.UUID(note_id)]
        if expect_code is not None:
            where.append(t.c.note_section == expect_code)
        result = await db.execute(sa.update(t).where(*where).values(**values))
        if result.rowcount != 1:
            raise RealignError(f"附注行 {note_id} 已变化（期望编号 {expect_code}），本项目回滚")

    for c in (*plan.renames, *plan.rehangs):
        await _update(c["note_id"], {"note_section": c["new"]}, expect_code=c["old"])
    for u in plan.tree_updates:
        await _update(u["note_id"], {f: new for f, (_old, new) in u["changes"].items()})
    for c in plan.child_reparents:
        await _update(c["note_id"], {"parent_section_id": c["new"]})
    for u in plan.related_updates:
        await _apply_related(db, u)
    if plan.inserts:
        created = await DisclosureEngine(db).generate_notes(
            project_id, year, template_type, only_sections=set(plan.inserts), strict=True)
        got = {r["note_section"] for r in created}
        if got != set(plan.inserts):
            raise RealignError(f"补章结果与计划不一致：缺 {sorted(set(plan.inserts) - got)} 多 {sorted(got - set(plan.inserts))}")
    await db.flush()


async def _apply_related(db: AsyncSession, u: dict[str, Any]) -> None:
    rid = uuid.UUID(u["id"])
    if u["table"] == "formula_push_state":
        fps = FormulaPushState.__table__
        values: dict[str, Any] = {"addr_id": u["new_addr_id"]}
        if u["old"]:
            values["note_section"] = u["new"]
        await db.execute(sa.update(fps).where(fps.c.id == rid).values(**values))
    elif u["table"] == "note_section_instances":
        nsi = NoteSectionInstance.__table__
        await db.execute(sa.update(nsi).where(nsi.c.id == rid).values(section_number=u["new"]))
    elif u["table"] == "note_section_locks":
        await db.execute(sa.update(LOCKS).where(LOCKS.c.id == rid).values(section_code=u["new"]))
    else:  # pragma: no cover - 计划只产出上面三类
        raise RealignError(f"未知关联表 {u['table']}")


def _content_digest(rows: list[NoteRow]) -> dict[str, tuple[str, str]]:
    return {r.id: (r.text_hash, r.table_hash) for r in rows}


async def realign_project(db: AsyncSession, project_id: uuid.UUID, year: int, *, apply: bool = False,
                          backup_path: Path | None = None) -> dict[str, Any]:
    """一个项目一个年度：dry-run 只出计划；``apply`` 时锁行 → 备份 → 执行 → 重算计划须为空 → 内容哈希逐行不变。"""
    plan, rows, meta = await build_plan(db, project_id, year, lock=apply)
    report: dict[str, Any] = {"project_id": str(project_id), "year": year, **meta, "plan": plan.to_dict()}
    if not apply or plan.action_count() == 0:
        return report
    if backup_path is not None:
        report["backup"] = await write_backup(db, project_id, year, backup_path)
    await apply_plan(db, project_id, year, plan, meta["template_type"])
    after, after_rows, _ = await build_plan(db, project_id, year)
    if after.action_count():
        raise RealignError(f"执行后仍有 {after.action_count()} 项待办（不幂等）：{after.counts()}")
    before_digest, after_digest = _content_digest(rows), _content_digest(after_rows)
    changed = sorted(i for i, d in before_digest.items() if after_digest.get(i) != d)
    if changed:
        raise RealignError(f"{len(changed)} 行正文或表格被改动（对齐只应改编号与树字段）：{changed[:5]}")
    report["after"] = after.counts()
    report["rows_after"] = len(after_rows)
    return report


# ── 备份 / 恢复（PostgreSQL）───────────────────────────────────────────────
#
# 每行存 PostgreSQL 自己输出的 ``row_to_json`` 文本，不经 Python 解析：``json.loads`` 会把 jsonb 里的数字转成浮点
# （``1.10`` 变 ``1.1``、超 17 位有效数字丢精度）。``row_to_json`` 把 SQL NULL 与 jsonb 的 JSON ``null`` 都写成
# ``null``，而真库纯文字章节的 ``table_data`` 全是 JSON null、推送状态「推送过空值」也是 JSON null ⇒ 另记
# ``json_null`` 列名，恢复后补回，否则恢复会把它们静默改成 SQL NULL。


def _scope_sql(table: str, by_year: bool) -> str:
    return f"FROM {table} WHERE project_id = :p" + (" AND year = :y" if by_year else "")


async def _jsonb_columns(db: AsyncSession, table: str) -> list[str]:
    return list((await db.execute(sa.text(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() "
        "AND table_name = :t AND data_type = 'jsonb' ORDER BY column_name"), {"t": table})).scalars().all())


async def export_rows(db: AsyncSession, project_id: uuid.UUID, year: int) -> dict[str, list[dict[str, Any]]]:
    """表 → ``[{"id", "row": row_to_json 原文, "json_null": [值为 JSON null 的 jsonb 列]}]``，按 id 排序。"""
    out: dict[str, list[dict[str, Any]]] = {}
    for table, by_year in BACKUP_TABLES.items():
        cols = await _jsonb_columns(db, table)
        nulls = ", ".join(f"CASE WHEN jsonb_typeof(x.{c}) = 'null' THEN '{c}' END" for c in cols)
        null_expr = f"array_remove(ARRAY[{nulls}]::text[], NULL)" if cols else "ARRAY[]::text[]"
        rows = (await db.execute(sa.text(
            f"SELECT x.id::text, row_to_json(x)::text, {null_expr} FROM (SELECT * {_scope_sql(table, by_year)}) x "
            "ORDER BY x.id"), {"p": project_id, "y": year})).all()
        out[table] = [{"id": rid, "row": raw, "json_null": list(jn)} for rid, raw, jn in rows]
    return out


def _require_pg(db: AsyncSession) -> None:
    if db.get_bind().dialect.name != "postgresql":
        raise RealignError("备份 / 恢复只支持 PostgreSQL")


async def write_backup(db: AsyncSession, project_id: uuid.UUID, year: int, path: Path) -> dict[str, Any]:
    _require_pg(db)
    tables = await export_rows(db, project_id, year)
    payload = {"version": BACKUP_VERSION, "project_id": str(project_id), "year": year,
               "created_at": datetime.now(timezone.utc).isoformat(), "tables": tables}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"path": str(path), "counts": {k: len(v) for k, v in tables.items()}}


async def restore_backup(db: AsyncSession, path: Path) -> dict[str, Any]:
    """按备份原样恢复（删范围内现有行 → 按原 id 插回 → 补回 JSON null）；恢复后再导出须与备份逐字相等。"""
    _require_pg(db)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != BACKUP_VERSION or set(payload.get("tables", {})) != set(BACKUP_TABLES):
        raise RealignError(f"备份格式不符：{path}")
    pid, year = uuid.UUID(payload["project_id"]), int(payload["year"])
    for table, by_year in BACKUP_TABLES.items():
        await db.execute(sa.text(f"DELETE {_scope_sql(table, by_year)}"), {"p": pid, "y": year})
        entries = payload["tables"][table]
        if not entries:
            continue
        await db.execute(sa.text(f"INSERT INTO {table} SELECT * FROM json_populate_recordset(NULL::{table}, "
                                 "CAST(:rows AS json))"), {"rows": "[" + ",".join(e["row"] for e in entries) + "]"})
        for col in sorted({c for e in entries for c in e["json_null"]}):
            ids = [uuid.UUID(e["id"]) for e in entries if col in e["json_null"]]
            await db.execute(sa.text(f"UPDATE {table} SET {col} = 'null'::jsonb WHERE id = ANY(:ids)"), {"ids": ids})
    restored = await export_rows(db, pid, year)
    for table in BACKUP_TABLES:
        if restored[table] != payload["tables"][table]:
            raise RealignError(f"恢复后 {table} 与备份不一致")
    return {"project_id": str(pid), "year": year, "counts": {k: len(v) for k, v in restored.items()}}
