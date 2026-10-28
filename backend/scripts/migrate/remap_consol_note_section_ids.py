"""已保存的合并附注数据随种子章节号重对齐迁移（spec consol-note-header-library-and-node-reaggregate R7.6 / design §16.6）。

对照：``backend/data/consol_note_section_realign_r7.json`` 的 ``sources``（按口径：新章节号 → 旧章节号列表，第一个是种子
里留下的条目，其余是并掉的重复条目）。存合并附注章节号的表逐张迁（``SPECS``）：

- 项目级的表按项目口径（``resolve_note_template_type``）取对照；模板级的表按口径列（``template_type`` / 全局公式 ``scope``）。
- 同一新号、同一唯一键下有多个旧号的行：留有数的那行（都有数 / 都没数时留对照里排在前面的旧号），其余备份后删除。
- 先把要改的行都改成临时号再改成新号：新旧号区间重叠（五-22-1 → 五-21-1、五-23-1 → 五-22-1 …），一步改会撞唯一索引。
- 合并附注公式的种子行（``source`` = seed / seed_sub、未删除）是派生数据：备份后删除，读公式时 ``ensure_seeded`` 按新种子
  重种；人工公式与人工删除记录随章节迁移。
- 公式模板层 / 模板版本快照里的合并附注公式位只报告不改（快照是历史）；有就拒绝 ``--apply``，请人工处理。
- 明细映射规则 / 绑定的来源结构指纹含章节号（``compute_source_structure_hash``），迁移后需在页面上重新确认。
- 新旧号同一区间，迁过的数据再迁一次会再错一节：迁完在 ``logs`` 记一条（``object_type`` = ``TAG``；全量迁移
  ``object_id`` 为空，指定项目时逐项目一条），已迁过的跳过；恢复时再记一条 restore。

默认只读演练（逐表报告）；``--apply``：涉及的行逐列原值备份到 ``--backup-dir``（默认 ``backend/backups/``，不入库）后在一个
事务里改完提交；``--restore <备份>`` 原样恢复。不指定 ``--project`` = 全部项目 + 模板级的表；指定时只迁这些项目的项目级表。
部署时随新种子立即全量跑一次（新种子上线后新存的数据已是新号）。

用法：python scripts/migrate/remap_consol_note_section_ids.py [--project <uuid> ...] [--apply | --restore <备份>]
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import pkgutil
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Awaitable, Callable

import sqlalchemy as sa

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

import app.models  # noqa: E402

# 与应用启动一致：导入全部模型子模块（外键目标表要在 metadata 里，否则 flush 排表时解析不到）
for _m in pkgutil.walk_packages(app.models.__path__, "app.models."):
    importlib.import_module(_m.name)

from app.models.account_note_mapping_models import AccountNoteMapping  # noqa: E402
from app.models.consol_note_data_models import ConsolNoteData  # noqa: E402
from app.models.consol_note_mapping_models import (  # noqa: E402
    ConsolNoteDetailTemplate,
    ConsolNoteMappingBinding,
    ConsolNoteMappingRule,
    ConsolNoteTemplateBinding,
)
from app.models.consol_push_models import ConsolNoteFormula  # noqa: E402
from app.models.core import Log  # noqa: E402
from app.models.formula_setting_models import FormulaSetting, FormulaSyncItem, FormulaTemplateVersion  # noqa: E402

RECORD = BACKEND / "data" / "consol_note_section_realign_r7.json"
DEFAULT_BACKUP_DIR = BACKEND / "backups"
TAG = "consol_note_section_realign_r7"
TEMP = "~r7~"
SEED_SOURCES = frozenset({"seed", "seed_sub"})
CONSOL_DOMAIN = "consol_note"
_ALWAYS: Callable[[Any], bool] = lambda _row: True  # noqa: E731


@dataclass(frozen=True)
class Spec:
    """一张存章节号的表：章节号列、口径来源、唯一键其余列、参与唯一索引的行、派生行。"""

    name: str
    model: Any
    unique: tuple[str, ...]
    column: str = "section_id"
    project_attr: str | None = "project_id"  # 项目级：按该列项目的口径；None = 模板级
    std_attr: str | None = None  # 模板级：口径列
    active: Callable[[Any], bool] = _ALWAYS  # 部分唯一索引的 WHERE
    derived: Callable[[Any], bool] = lambda _row: False  # 派生行：删（重种），不迁
    where: Callable[[Any], list] = lambda _m: []  # 额外筛选
    slot: bool = False  # 列值是「章节号|行|列」公式位


SPECS: tuple[Spec, ...] = (
    Spec("consol_note_data", ConsolNoteData, ("project_id", "year", "node_key")),
    Spec("consol_note_formula", ConsolNoteFormula, ("template_type", "row_index", "col_index"), project_attr=None,
         std_attr="template_type", active=lambda r: not r.is_deleted,
         derived=lambda r: r.source in SEED_SOURCES and not r.is_deleted),
    Spec("consol_note_detail_template", ConsolNoteDetailTemplate, ("template_type", "created_by"), project_attr=None,
         std_attr="template_type", active=lambda r: not r.is_deleted),
    # V202 的规则模板库 / 值确认 / 结构锁三表已退役（V208 删表，spec note-pull-followup-closure R16）；
    # 2026-10-23 的 R7 迁移备份里这三表 0 个动作，--restore 不受影响
    Spec("consol_note_mapping_rule", ConsolNoteMappingRule,
         ("project_id", "template_version_id", "source_structure_hash", "version_number"), active=lambda r: r.is_active),
    Spec("consol_note_mapping_binding", ConsolNoteMappingBinding, ("project_id", "entity_node_key")),
    Spec("consol_note_template_binding", ConsolNoteTemplateBinding, ("project_id",)),
    Spec("account_note_mapping", AccountNoteMapping, ("project_id", "account_name", "row_name")),
    Spec("formula_setting(global)", FormulaSetting, ("domain", "scope"), column="slot_key", slot=True, project_attr=None,
         std_attr="scope", active=lambda r: not r.is_deleted,
         where=lambda m: [m.domain == CONSOL_DOMAIN, m.layer == "global"]),
    Spec("formula_setting(project)", FormulaSetting, ("domain", "project_id"), column="slot_key", slot=True,
         active=lambda r: not r.is_deleted, where=lambda m: [m.domain == CONSOL_DOMAIN, m.layer == "project"]),
    Spec("formula_sync_item", FormulaSyncItem, ("project_id", "domain"), column="slot_key", slot=True,
         active=lambda r: r.status == "pending", where=lambda m: [m.domain == CONSOL_DOMAIN]),
)
_BY_NAME = {s.name: s for s in SPECS}


@dataclass
class Action:
    spec: str
    row_id: Any
    kind: str  # move / merge_drop / derived_drop
    old: str
    new: str | None
    project_id: Any = None
    std: str = ""
    note: str = ""


def load_record(path: Path = RECORD) -> dict[str, dict[str, tuple[str, int]]]:
    """旧章节号 → (新章节号, 在该新号来源里的序号)，按口径。"""
    sources = json.loads(path.read_bytes().decode("utf-8"))["sources"]
    out: dict[str, dict[str, tuple[str, int]]] = {}
    for std, mapping in sources.items():
        for new, olds in mapping.items():
            for rank, old in enumerate(olds):
                if out.setdefault(std, {}).setdefault(old, (new, rank)) != (new, rank):
                    raise ValueError(f"{std} 旧章节号 {old} 在对照里出现两次")
    return out


async def platform_std(db, project_id) -> str | None:
    from app.services.consol_note_formula_service import NoteFormulaError, resolve_note_template_type

    try:
        return await resolve_note_template_type(db, project_id)
    except (NoteFormulaError, ValueError, LookupError):
        return None


def _split(spec: Spec, value: str) -> tuple[str, str]:
    """列值 → (章节号, 公式位其余部分)。"""
    if not spec.slot:
        return value, ""
    sid, _, rest = value.partition("|")
    return sid, rest


def _join(spec: Spec, sid: str, rest: str) -> str:
    return f"{sid}|{rest}" if spec.slot else sid


def _filled(cell: Any) -> bool:
    """格子有数：非零数（「——」占位、模板里嵌的表头文字不算）。"""
    text = str(cell if cell is not None else "").strip().replace(",", "").rstrip("%")
    try:
        return Decimal(text) != 0
    except ArithmeticError:
        return False


def _has_values(row: Any) -> bool:
    """合并附注数据行有没有数（表格里标签列以外的格子、手工格 / 锁定格）。"""
    data = getattr(row, "data", None)
    if not isinstance(data, dict):
        return False
    if data.get("manual_cells") or getattr(row, "locked_cells", None):
        return True
    return any(_filled(c) for r in data.get("rows") or [] if isinstance(r, list) for c in r[1:])


async def build_plan(db, record: dict, *, projects: list[uuid.UUID] | None = None,
                     resolve_std: Callable[[Any, Any], Awaitable[str | None]] = platform_std) -> tuple[list[Action], list[str]]:
    """逐表算动作（只读）。返回 (动作, 提示)；已迁过的（``logs`` 有记录）跳过。"""
    actions: list[Action] = []
    notes: list[str] = []
    stds: dict[Any, str | None] = {}
    olds_all = sorted({old for mapping in record.values() for old in mapping})
    everything_done, done = await migrated(db)
    if everything_done:
        return [], ["已全量迁过（logs 有记录），无需再迁"]
    skipped: set = set()
    for spec in SPECS:
        if spec.project_attr is None and projects is not None:
            notes.append(f"{spec.name} 是模板级的表（各项目共用），指定 --project 时不迁")
            continue
        model, col = spec.model, getattr(spec.model, spec.column)
        stmt = sa.select(model).where(*spec.where(model))
        if not spec.slot:
            stmt = stmt.where(col.in_(olds_all))
        if projects is not None:
            stmt = stmt.where(getattr(model, spec.project_attr).in_(projects))
        groups: dict[tuple, list[tuple[int, Any, str, str, Any, str]]] = defaultdict(list)
        for row in (await db.execute(stmt)).scalars().all():
            sid, rest = _split(spec, getattr(row, spec.column))
            if spec.project_attr is not None:
                pid = getattr(row, spec.project_attr)
                if pid in done:
                    skipped.add(pid)
                    continue
                if pid not in stds:
                    stds[pid] = await resolve_std(db, pid)
                std = stds[pid]
            else:
                pid, std = None, getattr(row, spec.std_attr)
            if not std or sid not in record.get(std, {}):
                continue
            new, rank = record[std][sid]
            if spec.derived(row):
                actions.append(Action(spec.name, row.id, "derived_drop", getattr(row, spec.column), None, pid, std,
                                      "种子是派生数据，ensure_seeded 按新种子重种"))
                continue
            key = (std, *(getattr(row, c) for c in spec.unique), rest, new) if spec.active(row) else (row.id,)
            groups[key].append((rank, row, sid, new, pid, std))
        for members in groups.values():
            # 留有数的那行；都有 / 都没有时留对照里排在前面的旧号
            members.sort(key=lambda m: (not _has_values(m[1]), m[0]))
            for i, (_rank, row, sid, new, pid, std) in enumerate(members):
                value = getattr(row, spec.column)
                if i == 0:
                    if sid != new:
                        actions.append(Action(spec.name, row.id, "move", value, _join(spec, new, _split(spec, value)[1]),
                                              pid, std))
                    continue
                note = "两行都有数，留排在前面的那行，本行只在备份里" if _has_values(row) else ""
                actions.append(Action(spec.name, row.id, "merge_drop", value, None, pid, std, note))
    notes += [f"项目 {pid} 合并附注口径无法确定，未迁" for pid, std in stds.items() if not std]
    notes += [f"项目 {pid} 已迁过（logs 有记录），跳过" for pid in sorted(skipped, key=str)]
    if any(a.spec.startswith("consol_note_mapping") for a in actions):
        notes.append("明细映射规则 / 绑定的来源结构指纹含章节号：迁移后在页面上重新确认这些章节的映射")
    notes += await _template_layer_refs(db, record)
    return actions, notes


async def migrated(db) -> tuple[bool, set]:
    """已迁过的：(全量迁过, 迁过的项目)。按每个对象最后一条记录（apply / restore）判。"""
    last: dict[Any, str] = {}
    for log in (await db.execute(sa.select(Log).where(Log.object_type == TAG).order_by(Log.created_at, Log.id))).scalars():
        last[log.object_id] = log.action_type
    return last.get(None) == "apply", {k for k, v in last.items() if k is not None and v == "apply"}


async def mark(db, action: str, projects: list | None, detail: dict) -> None:
    """在 ``logs`` 记一条迁移 / 恢复：全量（``projects`` 为 None）记一条 object_id 为空的，否则逐项目一条。"""
    now = datetime.now(timezone.utc)
    for pid in (projects if projects is not None else [None]):
        db.add(Log(action_type=action, object_type=TAG, object_id=pid, new_value=detail, created_at=now))
    await db.flush()


async def _template_layer_refs(db, record: dict) -> list[str]:
    """公式模板层 / 模板版本快照里引用了要迁章节的合并附注公式位（只报告）。"""
    olds = {old for mapping in record.values() for old in mapping}
    hits = [r.slot_key for r in (await db.execute(sa.select(FormulaSetting).where(
        FormulaSetting.domain == CONSOL_DOMAIN, FormulaSetting.layer == "template"))).scalars().all()
        if r.slot_key.partition("|")[0] in olds]
    for v in (await db.execute(sa.select(FormulaTemplateVersion))).scalars().all():
        hits += [k for k in ((v.snapshot or {}).get(CONSOL_DOMAIN) or {}) if str(k).partition("|")[0] in olds]
    return [f"BLOCK 公式模板里有 {len(hits)} 个合并附注公式位引用了要迁的章节号（{', '.join(sorted(set(hits))[:5])}…），请人工处理"] if hits else []


def _plain(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return {"__uuid__": str(value)}
    if isinstance(value, datetime):
        return {"__dt__": value.isoformat()}
    if isinstance(value, date):
        return {"__date__": value.isoformat()}
    if isinstance(value, Decimal):
        return {"__dec__": str(value)}
    return value


def _typed(value: Any) -> Any:
    if isinstance(value, dict) and len(value) == 1:
        (tag, text), = value.items()
        conv = {"__uuid__": uuid.UUID, "__dt__": datetime.fromisoformat, "__date__": date.fromisoformat, "__dec__": Decimal}
        if tag in conv:
            return conv[tag](text)
    return value


def _row_payload(row: Any) -> dict:
    return {a.key: _plain(getattr(row, a.key)) for a in sa.inspect(row).mapper.column_attrs}


async def apply_plan(db, actions: list[Action]) -> list[dict]:
    """执行（只 flush，调用方提交）：备份 → 删并掉的 / 派生的 → 移的先改临时号再改新号。返回备份。"""
    rows = {}
    for a in actions:
        rows[(a.spec, a.row_id)] = await db.get(_BY_NAME[a.spec].model, a.row_id)
    backup = [{"spec": a.spec, "kind": a.kind, "old": a.old, "new": a.new, "row": _row_payload(rows[(a.spec, a.row_id)])}
              for a in actions]
    for a in actions:
        if a.kind != "move":
            await db.delete(rows[(a.spec, a.row_id)])
    await db.flush()
    moves = [a for a in actions if a.kind == "move"]
    for a in moves:
        setattr(rows[(a.spec, a.row_id)], _BY_NAME[a.spec].column, TEMP + a.old)
    await db.flush()
    for a in moves:
        row, spec = rows[(a.spec, a.row_id)], _BY_NAME[a.spec]
        setattr(row, spec.column, a.new)
        if spec.slot and getattr(row, "slot_label", None) == a.old:
            row.slot_label = a.new
    await db.flush()
    return backup


async def restore(db, doc: dict) -> int:
    """按备份原样恢复（只 flush）：移过的先改临时号再改回旧号，删掉的原样插回；``logs`` 记一条 restore。"""
    backup = doc["actions"]
    moved = [(b, await db.get(_BY_NAME[b["spec"]].model, _typed(b["row"]["id"]))) for b in backup if b["kind"] == "move"]
    for b, row in moved:
        setattr(row, _BY_NAME[b["spec"]].column, TEMP + b["old"])
    await db.flush()
    for b in backup:
        if b["kind"] != "move":
            db.add(_BY_NAME[b["spec"]].model(**{k: _typed(v) for k, v in b["row"].items()}))
    await db.flush()
    for b, row in moved:
        for key, value in b["row"].items():
            setattr(row, key, _typed(value))
    await db.flush()
    projects = doc.get("projects")
    await mark(db, "restore", [uuid.UUID(p) for p in projects] if projects else None, {"rows": len(backup)})
    return len(backup)


def summarize(actions: list[Action], notes: list[str]) -> str:
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for a in actions:
        counts[(a.spec, a.kind)] += 1
    lines = [f"  {spec}: {kind} {n}" for (spec, kind), n in sorted(counts.items())] or ["  无需迁移"]
    lines += [f"  ⚠ {a.spec} {a.old} 删除（{a.note}）" for a in actions if a.kind == "merge_drop" and a.note]
    return "\n".join(lines + [f"  ⚠ {n}" for n in notes])


async def main() -> int:
    parser = argparse.ArgumentParser(description="合并附注已保存数据随章节号重对齐迁移（默认只读演练）")
    parser.add_argument("--project", action="append", type=uuid.UUID, help="只迁这些项目的项目级表（可多次）")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="备份后执行")
    mode.add_argument("--restore", type=Path, help="按备份文件恢复")
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    args = parser.parse_args()

    from app.core.database import async_session

    async with async_session() as db:
        if args.restore:
            n = await restore(db, json.loads(args.restore.read_bytes().decode("utf-8")))
            await db.commit()
            print(f"已恢复 {n} 行（{args.restore}）")
            return 0
        actions, notes = await build_plan(db, load_record(), projects=args.project)
        print(("执行" if args.apply else "演练（只读）") + f"：{len(actions)} 个动作\n" + summarize(actions, notes))
        if not args.apply or any(n.startswith("已全量迁过") for n in notes):
            await db.rollback()
            return 0
        if any(n.startswith("BLOCK") for n in notes):
            await db.rollback()
            print("有需人工处理的公式模板引用，未执行")
            return 2
        backup = await apply_plan(db, actions)
        args.backup_dir.mkdir(parents=True, exist_ok=True)
        path = args.backup_dir / f"consol_note_remap_r7_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        path.write_text(json.dumps({"record": str(RECORD), "projects": [str(p) for p in args.project or []] or None,
                                    "actions": backup}, ensure_ascii=False, default=str), encoding="utf-8")
        await mark(db, "apply", args.project, {"actions": len(actions), "backup": str(path)})
        await db.commit()
        print(f"已提交；备份 {path}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
