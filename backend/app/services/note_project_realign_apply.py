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
#: 公式推送还会写底稿条目（无年度列，按项目整体）：推送前的备份带上它（``include_workpapers``），恢复时一并原样恢复。
#: 库内无外键指向 ``checklist_responses``，删后按原 id 插回不会连带删别的表
WORKPAPER_TABLES: dict[str, bool] = {"checklist_responses": False}
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
    stmt = sa.select(t.c.id, t.c.note_section, t.c.section_title, t.c.account_name, t.c.section_id, t.c.parent_section_id, t.c.level,
                     t.c.sort_index, t.c.sort_order, t.c.is_deleted, t.c.text_content, t.c.table_data
                     ).where(t.c.project_id == project_id, t.c.year == year)
    if lock:
        stmt = stmt.with_for_update()
    return [NoteRow(id=str(r.id), note_section=r.note_section, section_title=r.section_title or "",
                    account_name=r.account_name, section_id=r.section_id, parent_section_id=r.parent_section_id, level=r.level,
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


# ── 表格结构搬值（Task 12，design §4.2）──────────────────────────────────────
#
# 独立于上面的「改编号 / 树字段」对齐：那条链刻意不碰表格（design：Task 12 搬值待口径定）。表格口径既定后
# （= 现行种子表 = 底稿 xlsx），把库内表值搬进现行种子表结构：每节深拷贝种子 ``tables`` 当新结构，旧值按
# （规范化行标签，列 key / 表头文字）搬入，搬不进的进 ``table_data._realign_orphans``。两条硬断言（逐节非空值
# 多重集合不变、正文哈希逐行不变）由本模块保证，破坏即回滚。


async def _active_sections(db: AsyncSession, project_id: uuid.UUID, year: int, *, lock: bool = False
                           ) -> list[tuple[str, str, Any, Any]]:
    """活动节 ``(note_id, note_section, table_data, text_content)``；``lock`` 时 FOR UPDATE。"""
    t = DisclosureNote.__table__
    stmt = sa.select(t.c.id, t.c.note_section, t.c.table_data, t.c.text_content).where(
        t.c.project_id == project_id, t.c.year == year, t.c.is_deleted == sa.false())
    if lock:
        stmt = stmt.with_for_update()
    return [(str(r.id), r.note_section, r.table_data, r.text_content) for r in (await db.execute(stmt)).all()]


async def _seed_tables_by_code(db: AsyncSession, project_id: uuid.UUID) -> dict[str, list[dict[str, Any]]]:
    """生成链同口径的现行模板：现行编号 → 该节 ``tables``（口径过滤、编号已归一）。"""
    engine = DisclosureEngine(db)
    template_type = await engine._get_active_template_type(project_id)
    if template_type not in ("soe", "listed"):
        raise RealignError(f"项目模板类型为 {template_type}，只支持国企 / 上市种子")
    templates = await engine._load_templates(project_id, template_type)
    return {t["note_section"]: (t.get("tables") or []) for t in templates}


async def plan_table_realignment(db: AsyncSession, project_id: uuid.UUID, year: int) -> dict[str, Any]:
    """dry-run：逐活动节预演搬值（只读），不写库。安全性（multiset 恒等）与孤儿进报告，不抛错。"""
    from app.services.note_project_table_realign import plan_section

    deleted = (await db.execute(sa.select(Project.is_deleted).where(Project.id == project_id))).scalar_one_or_none()
    if deleted is None or deleted:
        raise RealignSkipped("项目不存在或已删除（回收站），不处理")
    seed_tables = await _seed_tables_by_code(db, project_id)
    sections = await _active_sections(db, project_id, year)
    plans: list[dict[str, Any]] = []
    for _nid, code, td, _text in sections:
        seed = seed_tables.get(code)
        if seed is None or not (seed or td):
            continue  # 编号不在现行模板，或两侧都无表 ⇒ 无需搬
        plans.append(plan_section(code, td, seed))
    changed = [p for p in plans if p.get("changed")]
    unsafe = [p for p in plans if not p.get("safe")]
    with_orphans = [p for p in plans if p.get("orphan_values")]
    return {"project_id": str(project_id), "year": year, "compared_sections": len(plans),
            "changed_sections": len(changed), "unsafe_sections": len(unsafe),
            "orphan_sections": len(with_orphans), "orphan_values": sum(p.get("orphan_values", 0) for p in plans),
            "unsafe": [{"note_section": p["note_section"], "error": p.get("error")} for p in unsafe],
            "orphans": [{"note_section": p["note_section"], "orphan_values": p["orphan_values"],
                         "detail": p["orphans"]} for p in with_orphans],
            "sections": plans}


async def apply_table_realignment(db: AsyncSession, project_id: uuid.UUID, year: int, *,
                                  backup_path: Path | None = None, allow_orphans: bool = True) -> dict[str, Any]:
    """搬值写库：锁行 → 备份 → 逐节搬值写回 → 每节非空值多重集合不变 + 每行正文哈希不变，否则抛错回滚。

    ``allow_orphans=False`` 时，任一节产生孤儿即拒绝（整项目回滚）——给「要求零孤儿才落库」的项目用。
    """
    deleted = (await db.execute(sa.select(Project.is_deleted).where(Project.id == project_id))).scalar_one_or_none()
    if deleted is None or deleted:
        raise RealignSkipped("项目不存在或已删除（回收站），不处理")
    from app.services.note_project_table_realign import TableRealignError, realign_section_tables

    seed_tables = await _seed_tables_by_code(db, project_id)
    sections = await _active_sections(db, project_id, year, lock=True)
    text_before = {nid: _hash(text) for nid, _c, _td, text in sections}
    t = DisclosureNote.__table__
    written = 0
    orphan_total = 0
    if backup_path is not None:
        await write_backup(db, project_id, year, backup_path)
    for nid, code, td, _text in sections:
        seed = seed_tables.get(code)
        if seed is None or not (seed or td):
            continue
        try:
            new_td = realign_section_tables(td, seed)
        except TableRealignError as err:
            raise RealignError(f"节 {code} 搬值破坏非空值多重集合：{err}") from err
        orphans = new_td.get("_realign_orphans") or []
        if orphans and not allow_orphans:
            raise RealignError(f"节 {code} 产生 {len(orphans)} 条孤儿，allow_orphans=False 拒绝落库")
        orphan_total += sum(len(o.get("values") or []) for o in orphans)
        if _hash(new_td) == _hash(td):
            continue  # 结构与值都没变（含孤儿恒无）⇒ 不写
        await db.execute(sa.update(t).where(t.c.id == uuid.UUID(nid)).values(table_data=new_td))
        written += 1
    await db.flush()
    # 正文哈希逐行不变（搬值只碰 table_data）
    after = await _active_sections(db, project_id, year)
    for nid, _c, _td, text in after:
        if text_before.get(nid) != _hash(text):
            raise RealignError(f"节行 {nid} 正文被改动（搬值只应改表格）")
    return {"project_id": str(project_id), "year": year, "written_sections": written,
            "orphan_values": orphan_total, "backup": str(backup_path) if backup_path else None}


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


#: 判「无业务实值」时忽略的结构键 / 明确占位值。100 只在比例字段中视为模板合计占位。
_DROP_META_KEYS = frozenset({"label", "is_total", "row_type", "_cell_meta", "_cell_modes", "row_key"})
_DROP_EMPTY_VALUES = frozenset({None, "", 0, 0.0, "0", "/", "-", "—", 100})
_RATIO_KEYS = ("ratio", "rate", "percent", "比例", "比率", "率")


def _is_empty_sample(key: str, value: Any) -> bool:
    if isinstance(value, (dict, list, tuple, set)):
        return not value
    if value == 100:
        return any(token in key.lower() for token in _RATIO_KEYS)
    try:
        return value in (_DROP_EMPTY_VALUES - {100})
    except TypeError:  # 自定义 JSON 解码对象等不可哈希值，一律按业务值保守处理
        return False


def _protected_cell_payload(value: Any, row_mode: Any) -> tuple[Any, str]:
    """返回单元格业务值与保护模式；无显式值的元数据对象按空壳处理。"""
    mode = str(row_mode or "").strip().lower()
    if not isinstance(value, dict):
        return value, mode
    mode = str(value.get("mode") or mode).strip().lower()
    if "value" in value:
        return value.get("value"), mode
    if "manual_value" in value:
        return value.get("manual_value"), mode
    return None, mode


def _is_protected_zero(value: Any, mode: str) -> bool:
    """人工确认的零是业务事实；自动零仍是可清理的模板样值。"""
    if mode not in {"manual", "locked"} or isinstance(value, bool):
        return False
    return value in (0, 0.0, "0")


def _drop_protection_reasons(table_data: Any) -> list[str]:
    """破坏性软删的独立保护证据；普通结构元数据不构成阻断。"""
    if not isinstance(table_data, dict):
        return []
    reasons: list[str] = []
    if table_data.get("_manual_override") is True:
        reasons.append("manual_override:top")
    sub = table_data.get("sub_table_data")
    if isinstance(sub, dict) and sub.get("_manual_override") is True:
        reasons.append("manual_override:sub_table_data")
    orphans = table_data.get("_realign_orphans")
    if orphans:
        size = len(orphans) if isinstance(orphans, list) else "malformed"
        reasons.append(f"realign_orphans:{size}")
    return reasons


def _business_values(table_data: Any) -> list[tuple[str, Any]]:
    """附注 table_data 中的非空业务值；兼容旧顶层表、多表和 sub_table_data。"""
    out: list[tuple[str, Any]] = []
    if not isinstance(table_data, dict):
        return out

    def scan_rows(name: str, rows: Any) -> None:
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            label = row.get("label")
            values = row.get("values")
            if isinstance(values, list):
                modes = row.get("_cell_modes") if isinstance(row.get("_cell_modes"), dict) else {}
                for ci, raw_value in enumerate(values):
                    value, mode = _protected_cell_payload(raw_value, modes.get(str(ci)))
                    if _is_protected_zero(value, mode) or not _is_empty_sample(str(ci), value):
                        out.append((f"{name}.{label}.{ci}", value))
            for key, value in row.items():
                if key in _DROP_META_KEYS or key in {"values", "cells"}:
                    continue
                if not _is_empty_sample(key, value):
                    out.append((f"{name}.{label}.{key}", value))

    sub = table_data.get("sub_table_data") or {}
    if isinstance(sub, dict):
        for name, rows in sub.items():
            scan_rows(str(name), rows)
    tables = table_data.get("_tables")
    if isinstance(tables, list) and tables:
        for idx, table in enumerate(tables):
            if isinstance(table, dict):
                scan_rows(str(table.get("name") or idx), table.get("rows") or [])
    else:  # 旧格式单表；多表时顶层是首表镜像，不能重复计数
        scan_rows(str(table_data.get("name") or "table"), table_data.get("rows") or [])
    return out


def _has_text(value: Any) -> bool:
    """正文 / 指引是否含用户可见内容；HTML 空壳不算。"""
    import re

    text = re.sub(r"<[^>]+>", "", str(value or ""))
    return bool(text.replace("&nbsp;", " ").strip())


async def drop_duplicate_sections(
    db: AsyncSession, project_id: uuid.UUID, year: int, sections: list[str], *,
    apply: bool = False, backup_dir: Path | None = None, stamp: str = "",
) -> dict[str, Any]:
    """软删「跨准则同步进来的重复编号行」—— 四道硬门全过才删（spec Phase 8，宜宾 五、5 / 五、15）。

    判据（任一不满足即拒绝该行，不删）：
      1. 编号原文不属本项目准则（``note_section`` 不在本准则种子的 ``section_number`` ∪ ``legacy_section_numbers``；
         五、N 是上市编号，国企项目现行编号是 八、N —— **不归一**，归一会把 五、N 映成 八、N 而误判成「属于本项目」）；
      2. 表格由**另一准则**底稿同步写入（``_source`` 以 workpaper 开头且 ``_current_standard`` 与项目模板准则不符）；
      3. 无业务实值（:func:`_business_values` 为空）；
      4. 现行模板里有同标题的未软删行（删掉这行不丢任何信息）。

    ``--apply``：锁行 → 只备份本操作会改的附注域 → 全部请求项过门后统一置 ``is_deleted=true`` →
    复核目标已软删且同标题活动行仍在。表无 ``deleted_at`` / ``deleted_by`` 列，只写 ``is_deleted``。
    调用方管事务（提交 / 回滚）。
    """
    deleted = (await db.execute(sa.select(Project.is_deleted).where(Project.id == project_id))).scalar_one_or_none()
    if deleted is None or deleted:
        raise RealignSkipped("项目不存在或已删除（回收站），不处理")
    engine = DisclosureEngine(db)
    template_type = await engine._get_active_template_type(project_id)
    if template_type not in ("soe", "listed"):
        raise RealignError(f"项目模板类型为 {template_type}，只支持国企 / 上市种子")
    seeds = seed_index(template_type)
    # 本准则现行编号原文集合（含别名）：判「编号不属于本项目准则」用——不归一（五、N 是 listed 编号，
    # 归一会把它映成国企 八、N 而误判成「属于本项目」）
    native_codes = {s.get("section_number") for s in seeds.values()}
    native_codes |= {alias for s in seeds.values() for alias in (s.get("legacy_section_numbers") or [])}
    rows = await load_rows(db, project_id, year, lock=apply)
    by_id = {r.id: r for r in rows}
    from app.services.note_section_matcher import normalize_for_match

    # 标题按同一规范化口径比较；候选本身不算另一条承载。
    live_titles: dict[str, list[tuple[str, str]]] = {}
    for r in rows:
        if not r.is_deleted:
            live_titles.setdefault(normalize_for_match(r.section_title), []).append((r.id, r.note_section))

    content_by_id = {str(x["id"]): x for x in await _full_rows(db, project_id, year)}
    matches_by_code: dict[str, list[NoteRow]] = {
        code: [r for r in rows if r.note_section == code and not r.is_deleted]
        for code in sections
    }
    candidates: dict[str, dict[str, Any]] = {}
    ambiguous: dict[str, list[str]] = {}
    for code, matched in matches_by_code.items():
        if len(matched) > 1:
            ambiguous[code] = [r.id for r in matched]
            continue
        if not matched:
            continue
        r = matched[0]
        content = content_by_id.get(str(r.id)) or {}
        td = content.get("table_data") or {}
        source = str((td.get("_source") or "")) if isinstance(td, dict) else ""
        cur_std = (td.get("_current_standard") if isinstance(td, dict) else None) or ""
        title_key = normalize_for_match(r.section_title)
        same_title_live = [other_code for other_id, other_code in live_titles.get(title_key, []) if other_id != r.id]
        business_values = _business_values(td)
        protection_reasons = _drop_protection_reasons(td)
        gates = {
            "编号不属本准则": r.note_section not in native_codes,
            "另一准则底稿同步": source.startswith("workpaper") and bool(cur_std) and not cur_std.startswith(template_type),
            "无正文指引和业务实值": not business_values
                and not protection_reasons
                and not _has_text(content.get("text_content"))
                and not _has_text(content.get("guidance_text")),
            "现行有同标题行": bool(same_title_live),
        }
        candidates[code] = {
            "note_id": r.id, "section_title": r.section_title, "current_standard": cur_std, "source": source,
            "business_values": business_values[:10], "protection_reasons": protection_reasons,
            "same_title_live": same_title_live,
            "gates": gates, "droppable": all(gates.values()),
        }

    missing = [code for code in sections if not matches_by_code.get(code)]
    report: dict[str, Any] = {
        "project_id": str(project_id), "year": year, "template_type": template_type,
        "requested": sections, "candidates": candidates, "missing": missing, "ambiguous": ambiguous,
    }
    droppable = [c["note_id"] for c in candidates.values() if c["droppable"]]
    blockers = [code for code, c in candidates.items() if not c["droppable"]]
    report["droppable_count"] = len(droppable)
    report["blocked"] = blockers
    if not apply:
        return report
    # apply 是项目级原子操作：请求项必须全部恰好命中一行并通过全部门，禁止静默部分删除。
    if missing or ambiguous or blockers or len(droppable) != len(sections):
        raise RealignError(
            f"重复行软删未通过全部安全门：missing={missing} ambiguous={ambiguous} blocked={blockers}"
        )
    if not droppable:
        return report

    report["backup"] = await write_backup(
        db, project_id, year, (backup_dir or Path(".")) / f"note_drop_{project_id}_{year}_{stamp}.json",
    )
    t = DisclosureNote.__table__
    await db.execute(sa.update(t).where(t.c.id.in_([uuid.UUID(nid) for nid in droppable])).values(is_deleted=True))
    await db.flush()
    # 复核：目标行已软删，且其同标题现行行仍在（删对了、没误删唯一承载）
    after = {r.id: r for r in await load_rows(db, project_id, year)}
    problems: list[str] = []
    for nid in droppable:
        row = after.get(nid)
        if not row or not row.is_deleted:
            problems.append(f"{by_id[nid].note_section} 未软删")
        title = by_id[nid].section_title or ""
        title_key = normalize_for_match(title)
        if not any(
            not x.is_deleted and normalize_for_match(x.section_title) == title_key and x.id != nid
            for x in after.values()
        ):
            problems.append(f"{by_id[nid].note_section}「{title}」软删后已无现行同标题行")
    if problems:
        raise RealignError("软删复核不通过：" + "；".join(problems))
    report["dropped"] = [by_id[nid].note_section for nid in droppable]
    return report


async def _full_rows(db: AsyncSession, project_id: uuid.UUID, year: int) -> list[dict[str, Any]]:
    """该项目该年度活动附注的内容字段（Core，拿库内 JSONB / 正文现值）。"""
    t = DisclosureNote.__table__
    stmt = sa.select(t.c.id, t.c.table_data, t.c.text_content, t.c.guidance_text).where(
        t.c.project_id == project_id, t.c.year == year, t.c.is_deleted == sa.false())
    return [
        {"id": r.id, "table_data": r.table_data, "text_content": r.text_content, "guidance_text": r.guidance_text}
        for r in (await db.execute(stmt)).all()
    ]


def _backup_tables(include_workpapers: bool) -> dict[str, bool]:
    return {**BACKUP_TABLES, **(WORKPAPER_TABLES if include_workpapers else {})}


async def export_rows(db: AsyncSession, project_id: uuid.UUID, year: int, *,
                      include_workpapers: bool = False) -> dict[str, list[dict[str, Any]]]:
    """表 → ``[{"id", "row": row_to_json 原文, "json_null": [值为 JSON null 的 jsonb 列]}]``，按 id 排序。"""
    out: dict[str, list[dict[str, Any]]] = {}
    for table, by_year in _backup_tables(include_workpapers).items():
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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """先写临时文件再替换：补记后像时改写的是已有备份，写到一半中断不能毁掉备份本身。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


async def begin_snapshot(db: AsyncSession) -> None:
    """本事务改用 REPEATABLE READ（须在事务第一条查询前调用）：备份、执行、后像读同一快照。

    读已提交时，备份之后、提交之前别人提交的改动会进后像却不在备份里，按备份恢复就会悄悄抹掉它们；
    同一快照下这类改动要么与本事务写同一行而让本事务报串行化失败回滚，要么留在快照外、恢复时被后像围栏拦下。
    """
    _require_pg(db)
    await db.execute(sa.text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
    level = (await db.execute(sa.text("SELECT current_setting('transaction_isolation')"))).scalar_one()
    if level != "repeatable read":
        raise RealignError(f"事务隔离级别没有切到 REPEATABLE READ（实际 {level}），不执行")


async def write_backup(db: AsyncSession, project_id: uuid.UUID, year: int, path: Path, *,
                       include_workpapers: bool = False) -> dict[str, Any]:
    _require_pg(db)
    tables = await export_rows(db, project_id, year, include_workpapers=include_workpapers)
    payload = {"version": BACKUP_VERSION, "project_id": str(project_id), "year": year,
               "created_at": datetime.now(timezone.utc).isoformat(), "tables": tables}
    _write_json(path, payload)
    return {"path": str(path), "counts": {k: len(v) for k, v in tables.items()}}


def _load_backup(path: Path) -> tuple[dict[str, Any], uuid.UUID, int, bool]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    names = set(payload.get("tables", {}))
    with_wp = names == set(_backup_tables(True))
    if payload.get("version") != BACKUP_VERSION or not (with_wp or names == set(BACKUP_TABLES)):
        raise RealignError(f"备份格式不符：{path}")
    return payload, uuid.UUID(payload["project_id"]), int(payload["year"]), with_wp


def _row_digests(entries: list[dict[str, Any]]) -> dict[str, str]:
    return {e["id"]: _hash([e["row"], sorted(e["json_null"])]) for e in entries}


async def record_postimage(db: AsyncSession, path: Path) -> dict[str, Any]:
    """提交前把本次操作后的逐行摘要补记进备份（恢复围栏），须与操作在同一事务、提交之前调用。

    恢复时现状须与这份后像逐行一致才放行：不一致说明操作提交后又有人改过这些表，原样恢复会连别人的改动一起抹掉。
    """
    _require_pg(db)
    payload, pid, year, with_wp = _load_backup(path)
    rows = await export_rows(db, pid, year, include_workpapers=with_wp)
    payload["postimage"] = {"recorded_at": datetime.now(timezone.utc).isoformat(),
                            "rows": {table: _row_digests(entries) for table, entries in rows.items()}}
    _write_json(path, payload)
    return {"counts": {k: len(v) for k, v in rows.items()}}


async def plan_restore(db: AsyncSession, path: Path) -> dict[str, Any]:
    """只读：按备份恢复会删 / 插 / 改多少行，以及后像围栏的判定。

    ``fence``：``ok`` 现状与后像一致 · ``mismatch`` 操作后有改动（``drift`` 列出行 id）· ``unfenced`` 备份没有后像
    （旧备份或操作未提交）· ``already_restored`` 现状已与备份一致（无需恢复）。
    """
    _require_pg(db)
    payload, pid, year, with_wp = _load_backup(path)
    current = await export_rows(db, pid, year, include_workpapers=with_wp)
    delta: dict[str, dict[str, int]] = {}
    for table, entries in current.items():
        now, then = _row_digests(entries), _row_digests(payload["tables"][table])
        delta[table] = {"delete": len(now.keys() - then.keys()), "insert": len(then.keys() - now.keys()),
                        "change": sum(now[i] != then[i] for i in now.keys() & then.keys())}
    post = payload.get("postimage")
    drift: dict[str, list[str]] = {}
    if current == payload["tables"]:
        fence = "already_restored"
    elif not isinstance(post, dict) or not isinstance(post.get("rows"), dict):
        fence = "unfenced"
    else:
        for table, entries in current.items():
            expected, actual = post["rows"].get(table) or {}, _row_digests(entries)
            moved = (expected.keys() ^ actual.keys()) | {i for i in expected.keys() & actual.keys()
                                                         if expected[i] != actual[i]}
            if moved:
                drift[table] = sorted(moved)
        fence = "mismatch" if drift else "ok"
    return {"project_id": str(pid), "year": year, "fence": fence, "drift": drift, "delta": delta,
            "postimage_recorded_at": post.get("recorded_at") if isinstance(post, dict) else None}


async def restore_backup(db: AsyncSession, path: Path, *, force: bool = False) -> dict[str, Any]:
    """按备份原样恢复（删范围内现有行 → 按原 id 插回 → 补回 JSON null）；恢复后再导出须与备份逐字相等。

    先过后像围栏（:func:`plan_restore`）：现状须与备份补记的操作后像逐行一致；``unfenced`` / ``mismatch`` 只有
    ``force`` 才继续（调用方须先 dry-run 看过 ``drift`` 与 ``delta``）。现状已与备份一致时不写。
    """
    plan = await plan_restore(db, path)
    if plan["fence"] == "already_restored":
        return {**plan, "restored": False, "counts": {}}
    if plan["fence"] != "ok" and not force:
        detail = {t: ids[:5] for t, ids in plan["drift"].items()}
        raise RealignError(f"后像围栏不放行（{plan['fence']}）：{detail or '备份没有后像'}；"
                           "按备份恢复会覆盖这些改动，确认后用 --force-restore")
    payload, pid, year, with_wp = _load_backup(path)
    for table, by_year in _backup_tables(with_wp).items():
        await db.execute(sa.text(f"DELETE {_scope_sql(table, by_year)}"), {"p": pid, "y": year})
        entries = payload["tables"][table]
        if not entries:
            continue
        await db.execute(sa.text(f"INSERT INTO {table} SELECT * FROM json_populate_recordset(NULL::{table}, "
                                 "CAST(:rows AS json))"), {"rows": "[" + ",".join(e["row"] for e in entries) + "]"})
        for col in sorted({c for e in entries for c in e["json_null"]}):
            ids = [uuid.UUID(e["id"]) for e in entries if col in e["json_null"]]
            await db.execute(sa.text(f"UPDATE {table} SET {col} = 'null'::jsonb WHERE id = ANY(:ids)"), {"ids": ids})
    restored = await export_rows(db, pid, year, include_workpapers=with_wp)
    for table in restored:
        if restored[table] != payload["tables"][table]:
            raise RealignError(f"恢复后 {table} 与备份不一致")
    return {**plan, "restored": True, "forced": plan["fence"] != "ok",
            "counts": {k: len(v) for k, v in restored.items()}}
