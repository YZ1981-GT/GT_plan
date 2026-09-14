"""附注模板回流：把模板升级后的结构差异补进既有项目（本文件只做**只读差异计算**）。

**为什么需要**（2026-07-29 实证）：改 `note_template_*.json` 与改前端同步载荷代码，
对既有项目**一律不生效** ——

- `guidance` 只经 `disclosure_engine._carry_seed_table_guidance` 在 **seed 路径**生效；
  给 F2 存货 14 张表补齐 guidance 后，拉真实后端投影结果仍全为 0 字
- `_sub_table_columns` 是上次同步写入的旧值；给「存货跌价准备…（续）」补 `flat` 后，
  既有项目 `_column_groups` 仍是 `None`（会回退前缀推断）
- 模板新增表（如「确认为存货的数据资源」）在既有项目的附注里根本不出现

差异分五类：

| 类别 | 含义 | 回流动作（Task 6，不在本文件） |
|------|------|------|
| `missing` | 模板有、附注无 | 新增空骨架 + 列头 |
| `renamed` | 疑似改名（列结构同构） | 迁移而非新建，避免孤儿空表 |
| `column_drift` | 列头与模板不一致 | 更新 `_sub_table_columns`，**行数据不动** |
| `guidance_missing` | 模板有 guidance、附注表没有 | 补 guidance |
| `extra` | 附注有、模板无 | **只报告不删**（可能是项目自定义表） |

纯读：本模块任何函数都不写库。

Spec: .kiro/specs/disclosure-note-follow-actual-content/ R2 / Task 2
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

__all__ = [
    "ColumnDrift",
    "RenameCandidate",
    "SectionDiff",
    "ReflowResult",
    "diff_tables",
    "diff_section",
    "diff_project",
    "apply_reflow_tables",
    "apply_reflow_section",
]


# ════════════════════════════════════════════════════════════════════
# 数据结构
# ════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ColumnDrift:
    """某表列头与模板不一致。"""

    table: str
    reason: str
    """`count` 列数不同 / `label` 列名不同 / `group_or_flat` 分组声明不同"""
    template_labels: tuple[str, ...]
    note_labels: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "table": self.table,
            "reason": self.reason,
            "template_labels": list(self.template_labels),
            "note_labels": list(self.note_labels),
        }


@dataclass(frozen=True)
class RenameCandidate:
    """疑似改名：附注侧 `note_name` ↔ 模板侧候选名（可能多个 → 需人工选）。"""

    note_name: str
    template_candidates: tuple[str, ...]
    basis: str
    """`declared` = 模板 `_renamed_from` 显式声明；`structural` = 列结构同构推断"""

    @property
    def is_ambiguous(self) -> bool:
        return len(self.template_candidates) != 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "note_name": self.note_name,
            "template_candidates": list(self.template_candidates),
            "basis": self.basis,
            "ambiguous": self.is_ambiguous,
        }


@dataclass(frozen=True)
class SectionDiff:
    note_id: str
    note_section: str
    section_title: str
    missing: tuple[str, ...] = ()
    renamed: tuple[RenameCandidate, ...] = ()
    column_drift: tuple[ColumnDrift, ...] = ()
    guidance_missing: tuple[str, ...] = ()
    extra: tuple[str, ...] = ()
    is_local_override: bool = False
    has_legacy_snapshot: bool = False
    """`sub_table_data` 为空但存在 legacy `rows`/`_tables` → 需先跑迁移脚本（Task 3/8）"""
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_changes(self) -> bool:
        return bool(
            self.missing or self.renamed or self.column_drift or self.guidance_missing
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "note_id": self.note_id,
            "note_section": self.note_section,
            "section_title": self.section_title,
            "missing": list(self.missing),
            "renamed": [r.to_dict() for r in self.renamed],
            "column_drift": [c.to_dict() for c in self.column_drift],
            "guidance_missing": list(self.guidance_missing),
            "extra": list(self.extra),
            "is_local_override": self.is_local_override,
            "has_legacy_snapshot": self.has_legacy_snapshot,
            "has_changes": self.has_changes,
            "notes": list(self.notes),
        }


# ════════════════════════════════════════════════════════════════════
# 纯函数 diff（不碰 DB，便于单测）
# ════════════════════════════════════════════════════════════════════


def _labels_of(columns: Any) -> tuple[str, ...]:
    return tuple(
        str(c.get("label") or "") for c in (columns or []) if isinstance(c, dict)
    )


def _group_signature(columns: Any) -> tuple[Any, ...]:
    """列的分组/单级声明签名：用于判断 `group`/`flat` 声明是否漂移。"""
    sig: list[Any] = []
    for c in columns or []:
        if not isinstance(c, dict):
            continue
        sig.append((str(c.get("group") or ""), bool(c.get("flat"))))
    return tuple(sig)


def _is_meta_key(k: Any) -> bool:
    return str(k).startswith("_")


def _structurally_same(a: Any, b: Any) -> bool:
    """列结构同构：列数相同且列名逐位相同（用于改名推断）。"""
    la, lb = _labels_of(a), _labels_of(b)
    return bool(la) and la == lb


def diff_tables(
    template_tables: list[dict[str, Any]],
    note_sub_table_data: dict[str, Any] | None,
    note_columns_map: dict[str, Any] | None,
) -> dict[str, Any]:
    """纯函数：比对模板表集合与附注现有表集合。

    Args:
        template_tables: 模板 section 的 `tables`（每项含 `name`/`columns`/`guidance`）
        note_sub_table_data: 附注 `table_data.sub_table_data`
        note_columns_map: 附注 `table_data._sub_table_columns`

    Returns:
        `{"missing", "renamed", "column_drift", "guidance_missing", "extra"}`
    """
    tpl_by_name: dict[str, dict[str, Any]] = {}
    tpl_order: list[str] = []
    for t in template_tables or []:
        if not isinstance(t, dict):
            continue
        name = str(t.get("name") or "")
        if not name:
            continue
        tpl_by_name[name] = t
        tpl_order.append(name)

    note_names = [
        str(k) for k in (note_sub_table_data or {}).keys() if not _is_meta_key(k)
    ]
    note_set = set(note_names)
    cols_map = note_columns_map if isinstance(note_columns_map, dict) else {}

    missing = [n for n in tpl_order if n not in note_set]
    extra = [n for n in note_names if n not in tpl_by_name]

    # ── 改名判定 ────────────────────────────────────────────────────
    renamed: list[RenameCandidate] = []
    consumed_missing: set[str] = set()
    consumed_extra: set[str] = set()

    # 1) 模板显式声明 `_renamed_from`
    for new_name in missing:
        declared = tpl_by_name[new_name].get("_renamed_from")
        olds = [declared] if isinstance(declared, str) else list(declared or [])
        hits = [o for o in olds if isinstance(o, str) and o in note_set]
        if hits:
            renamed.append(
                RenameCandidate(
                    note_name=hits[0], template_candidates=(new_name,), basis="declared",
                )
            )
            consumed_missing.add(new_name)
            consumed_extra.add(hits[0])

    # 2) 列结构同构推断（只在 preview 展示，需人工确认）
    for old_name in extra:
        if old_name in consumed_extra:
            continue
        cands = [
            n
            for n in missing
            if n not in consumed_missing
            and _structurally_same(tpl_by_name[n].get("columns"), cols_map.get(old_name))
        ]
        if cands:
            renamed.append(
                RenameCandidate(
                    note_name=old_name,
                    template_candidates=tuple(cands),
                    basis="structural",
                )
            )
            consumed_extra.add(old_name)
            if len(cands) == 1:
                consumed_missing.add(cands[0])

    # ── 列头漂移 + guidance 缺失（只看两侧都存在的表）──────────────
    column_drift: list[ColumnDrift] = []
    guidance_missing: list[str] = []
    for name in tpl_order:
        if name not in note_set:
            continue
        tpl = tpl_by_name[name]
        tpl_cols = tpl.get("columns")
        note_cols = cols_map.get(name)
        tl, nl = _labels_of(tpl_cols), _labels_of(note_cols)
        if tpl_cols and not note_cols:
            column_drift.append(ColumnDrift(name, "count", tl, nl))
        elif tl and nl and len(tl) != len(nl):
            column_drift.append(ColumnDrift(name, "count", tl, nl))
        elif tl and nl and tl != nl:
            column_drift.append(ColumnDrift(name, "label", tl, nl))
        elif tpl_cols and note_cols and _group_signature(tpl_cols) != _group_signature(note_cols):
            # 列名一致但 group/flat 声明不同 → 影响两级表头与前缀推断
            column_drift.append(ColumnDrift(name, "group_or_flat", tl, nl))

        if str(tpl.get("guidance") or "").strip():
            # guidance 存放在两处：note 的 `_sub_table_guidance`（若已支持）或表级
            has = _note_guidance_of(note_columns_map, note_sub_table_data, name)
            if not has:
                guidance_missing.append(name)

    return {
        "missing": [n for n in missing if n not in consumed_missing],
        "renamed": renamed,
        "column_drift": column_drift,
        "guidance_missing": guidance_missing,
        "extra": [n for n in extra if n not in consumed_extra],
    }


def _note_guidance_of(
    cols_map: Any, sub: Any, table_name: str,
) -> str:
    """附注侧该表现有 guidance（同步路径目前不落 guidance → 恒为空）。"""
    if isinstance(cols_map, dict):
        g = cols_map.get("_guidance")
        if isinstance(g, dict) and str(g.get(table_name) or "").strip():
            return str(g[table_name])
    if isinstance(sub, dict):
        g2 = sub.get("_guidance")
        if isinstance(g2, dict) and str(g2.get(table_name) or "").strip():
            return str(g2[table_name])
    return ""


# ════════════════════════════════════════════════════════════════════
# DB 层薄封装（只读）
# ════════════════════════════════════════════════════════════════════


async def _load_template_sections(
    db: AsyncSession, project_id: UUID,
) -> tuple[list[dict[str, Any]], str]:
    """复用 `DisclosureEngine._load_templates`（含 custom 模板合并 + section 归一）。

    🔴 不要自己读 `note_template_*.json`：会漏掉项目级自定义模板合并与
    `normalize_section_code` 归一，导致 diff 把自定义章节误报为 extra。
    """
    from app.services.disclosure_engine import DisclosureEngine

    engine = DisclosureEngine(db)
    template_type = await engine._get_active_template_type(project_id)
    sections = await engine._load_templates(project_id, template_type)
    return sections, template_type


def _pick_template_section(
    sections: list[dict[str, Any]], note_section: str, section_title: str,
) -> dict[str, Any] | None:
    """按 `note_section` 定位；退化时按 `section_title` 兜底。"""
    for s in sections:
        if str(s.get("note_section") or "") == str(note_section):
            return s
    if section_title:
        hits = [
            s for s in sections
            if str(s.get("section_title") or "") == str(section_title)
            and (s.get("tables") or [])
        ]
        if len(hits) == 1:
            return hits[0]
    return None


async def diff_section(db: AsyncSession, note_id: str | UUID) -> SectionDiff:
    """计算单个附注章节与模板的结构差异（只读）。"""
    row = (
        await db.execute(
            sa.text(
                "SELECT id, project_id, note_section, section_title, table_data, "
                "       is_local_override "
                "FROM disclosure_notes WHERE id = :id AND is_deleted = false"
            ),
            {"id": str(note_id)},
        )
    ).mappings().first()
    if not row:
        raise ValueError(f"disclosure_note not found: {note_id}")

    td = row["table_data"] if isinstance(row["table_data"], dict) else {}
    sub = td.get("sub_table_data") if isinstance(td.get("sub_table_data"), dict) else {}
    cols_map = (
        td.get("_sub_table_columns")
        if isinstance(td.get("_sub_table_columns"), dict)
        else {}
    )
    has_legacy = (not sub) and bool(td.get("rows") or td.get("_tables"))

    sections, _tt = await _load_template_sections(db, row["project_id"])
    tpl = _pick_template_section(
        sections, str(row["note_section"] or ""), str(row["section_title"] or ""),
    )

    notes: list[str] = []
    if tpl is None:
        notes.append("模板中未找到对应章节（可能是项目自定义章节）→ 跳过回流")
        return SectionDiff(
            note_id=str(row["id"]),
            note_section=str(row["note_section"] or ""),
            section_title=str(row["section_title"] or ""),
            extra=tuple(str(k) for k in sub.keys() if not _is_meta_key(k)),
            is_local_override=bool(row["is_local_override"]),
            has_legacy_snapshot=has_legacy,
            notes=tuple(notes),
        )

    if has_legacy:
        notes.append(
            "该章节仍是 legacy 快照（sub_table_data 为空但存在 rows/_tables）"
            "→ 请先跑 migrate_legacy_note_snapshots.py，否则回流会把整章当空章节处理"
        )

    d = diff_tables(tpl.get("tables") or [], sub, cols_map)
    return SectionDiff(
        note_id=str(row["id"]),
        note_section=str(row["note_section"] or ""),
        section_title=str(row["section_title"] or ""),
        missing=tuple(d["missing"]),
        renamed=tuple(d["renamed"]),
        column_drift=tuple(d["column_drift"]),
        guidance_missing=tuple(d["guidance_missing"]),
        extra=tuple(d["extra"]),
        is_local_override=bool(row["is_local_override"]),
        has_legacy_snapshot=has_legacy,
        notes=tuple(notes),
    )


@dataclass(frozen=True)
class ReflowResult:
    """apply_reflow 的返回结果。"""

    note_id: str
    note_section: str
    added_tables: tuple[str, ...] = ()
    renamed_tables: tuple[tuple[str, str], ...] = ()  # (old_name, new_name)
    columns_updated: tuple[str, ...] = ()
    skipped_reason: str | None = None

    @property
    def has_changes(self) -> bool:
        return bool(self.added_tables or self.renamed_tables or self.columns_updated)

    def to_dict(self) -> dict[str, Any]:
        return {
            "note_id": self.note_id,
            "note_section": self.note_section,
            "added_tables": list(self.added_tables),
            "renamed_tables": [list(pair) for pair in self.renamed_tables],
            "columns_updated": list(self.columns_updated),
            "skipped_reason": self.skipped_reason,
            "has_changes": self.has_changes,
        }


# ════════════════════════════════════════════════════════════════════
# 纯函数 apply（不碰 DB，便于单测）
# ════════════════════════════════════════════════════════════════════


def apply_reflow_tables(
    template_tables: list[dict[str, Any]],
    sub_table_data: dict[str, Any],
    columns_map: dict[str, Any],
    *,
    include_renamed: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """纯函数：把模板差异就地补进 sub_table_data 与 columns_map。

    **只加不覆盖**：
    - 新增表 → 写空骨架行 + 列头（从模板 `rows`/`columns` 复制）
    - 列头漂移 → 更新 columns_map（行数据不动）
    - 确认改名 → 把旧键迁移到新键（行数据保留、列头取模板）
    - 已有表的行数据**绝不触碰**

    Args:
        template_tables: 模板 section 的 `tables`
        sub_table_data: 附注的 sub_table_data（会就地修改）
        columns_map: 附注的 _sub_table_columns（会就地修改）
        include_renamed: 用户确认的改名对 `[(old_name, new_name)]`；
                         None 时自动执行非歧义的 declared 改名

    Returns:
        `{"added": [...], "renamed": [...], "columns_updated": [...]}`
    """
    tpl_by_name: dict[str, dict[str, Any]] = {}
    for t in template_tables or []:
        if not isinstance(t, dict):
            continue
        name = str(t.get("name") or "")
        if name:
            tpl_by_name[name] = t

    note_keys = set(str(k) for k in sub_table_data.keys() if not _is_meta_key(k))
    added: list[str] = []
    renamed: list[tuple[str, str]] = []
    columns_updated: list[str] = []

    # ── 改名（只执行确认的、非歧义的） ──────────────────────────────
    rename_pairs = include_renamed or []
    if not rename_pairs:
        # 自动执行模板 _renamed_from 声明的非歧义改名
        for name, tpl in tpl_by_name.items():
            if name in note_keys:
                continue
            declared = tpl.get("_renamed_from")
            olds = [declared] if isinstance(declared, str) else list(declared or [])
            hits = [o for o in olds if isinstance(o, str) and o in note_keys]
            if len(hits) == 1:
                rename_pairs.append((hits[0], name))

    for old_name, new_name in rename_pairs:
        if old_name not in sub_table_data:
            continue
        if new_name in sub_table_data:
            continue  # 新名已存在 → 跳过，不覆盖
        # 迁移行数据
        sub_table_data[new_name] = sub_table_data.pop(old_name)
        # 迁移列头或用模板列头
        if old_name in columns_map:
            columns_map.pop(old_name)
        tpl = tpl_by_name.get(new_name)
        if tpl and tpl.get("columns"):
            columns_map[new_name] = tpl["columns"]
        renamed.append((old_name, new_name))
        note_keys.discard(old_name)
        note_keys.add(new_name)

    # ── 补齐缺失表 ─────────────────────────────────────────────────
    for name, tpl in tpl_by_name.items():
        if name in note_keys:
            continue
        # 空骨架行（模板的 rows 去除 header_label）
        rows = []
        for row in tpl.get("rows") or []:
            if isinstance(row, dict) and row.get("row_type") == "header_label":
                continue
            rows.append(dict(row) if isinstance(row, dict) else row)
        sub_table_data[name] = rows
        # 列头
        if tpl.get("columns"):
            columns_map[name] = tpl["columns"]
        added.append(name)

    # ── 修正列头漂移 ───────────────────────────────────────────────
    for name in note_keys:
        tpl = tpl_by_name.get(name)
        if not tpl or not tpl.get("columns"):
            continue
        tpl_cols = tpl["columns"]
        note_cols = columns_map.get(name)
        # 只在模板有列定义且与附注不同时更新
        if not note_cols:
            columns_map[name] = tpl_cols
            columns_updated.append(name)
        elif _labels_of(tpl_cols) != _labels_of(note_cols):
            columns_map[name] = tpl_cols
            columns_updated.append(name)
        elif _group_signature(tpl_cols) != _group_signature(note_cols):
            columns_map[name] = tpl_cols
            columns_updated.append(name)

    return {
        "added": added,
        "renamed": renamed,
        "columns_updated": columns_updated,
    }


# ════════════════════════════════════════════════════════════════════
# DB 层写入（apply_reflow_section）
# ════════════════════════════════════════════════════════════════════


async def apply_reflow_section(
    db: AsyncSession,
    note_id: str | UUID,
    *,
    include_local_override: bool = False,
    include_renamed: list[tuple[str, str]] | None = None,
    commit: bool = True,
) -> ReflowResult:
    """对单个附注章节执行模板回流（写入）。

    - 只加不覆盖：新增表写空骨架 + 列头；已有表只在列头漂移时更新列头
    - `is_local_override` 默认跳过
    - 执行前后记 `template_lineage._reflow_history`

    Spec: disclosure-note-follow-actual-content Task 6
    """
    row = (
        await db.execute(
            sa.text(
                "SELECT id, project_id, note_section, section_title, table_data, "
                "       is_local_override "
                "FROM disclosure_notes WHERE id = :id AND is_deleted = false"
            ),
            {"id": str(note_id)},
        )
    ).mappings().first()
    if not row:
        raise ValueError(f"disclosure_note not found: {note_id}")

    note_section = str(row["note_section"] or "")
    section_title = str(row["section_title"] or "")

    # is_local_override 守卫
    if row["is_local_override"] and not include_local_override:
        return ReflowResult(
            note_id=str(row["id"]),
            note_section=note_section,
            skipped_reason="is_local_override=true（跳过，需显式包含）",
        )

    td = dict(row["table_data"]) if isinstance(row["table_data"], dict) else {}
    sub = dict(td.get("sub_table_data") or {}) if isinstance(td.get("sub_table_data"), dict) else {}
    cols_map = dict(td.get("_sub_table_columns") or {}) if isinstance(td.get("_sub_table_columns"), dict) else {}

    # legacy 快照警告：仍有 rows/_tables 但无 sub_table_data
    if not sub and (td.get("rows") or td.get("_tables")):
        return ReflowResult(
            note_id=str(row["id"]),
            note_section=note_section,
            skipped_reason="legacy 快照未迁移（sub_table_data 为空），请先跑迁移脚本",
        )

    # 加载模板
    sections, _tt = await _load_template_sections(db, row["project_id"])
    tpl = _pick_template_section(sections, note_section, section_title)
    if tpl is None:
        return ReflowResult(
            note_id=str(row["id"]),
            note_section=note_section,
            skipped_reason="模板中未找到对应章节",
        )

    # 执行纯函数回流
    result = apply_reflow_tables(
        tpl.get("tables") or [],
        sub,
        cols_map,
        include_renamed=include_renamed,
    )

    if not result["added"] and not result["renamed"] and not result["columns_updated"]:
        return ReflowResult(
            note_id=str(row["id"]),
            note_section=note_section,
        )

    # 写回 table_data
    td["sub_table_data"] = sub
    td["_sub_table_columns"] = cols_map

    # template_lineage 记账
    lineage = dict(td.get("_template_lineage") or {}) if isinstance(td.get("_template_lineage"), dict) else {}
    history = list(lineage.get("_reflow_history") or [])
    history.append({
        "at": datetime.now(timezone.utc).isoformat(),
        "added": result["added"],
        "renamed": [(o, n) for o, n in result["renamed"]],
        "columns_updated": result["columns_updated"],
    })
    lineage["_reflow_history"] = history
    td["_template_lineage"] = lineage

    # 更新 DB
    # 🔴 JSONB 绑定必须 `CAST(:td AS jsonb)` + json.dumps 字符串：
    # `sa.type_coerce(td, sa.JSON)` 配 `sa.text()` 在 asyncpg 下抛
    # `Neither 'TypeCoerce' object nor 'Comparator' object has an attribute 'encode'`
    # （type_coerce 是 SQL 表达式构造器、不是可绑定值）。原写法对真实库 100% 失败，
    # 单测因用替身 session 未暴露；与 migrate_legacy_note_snapshots 同批修复。
    await db.execute(
        sa.text(
            "UPDATE disclosure_notes SET table_data = CAST(:td AS jsonb), updated_at = :now "
            "WHERE id = :id"
        ),
        {
            "id": str(row["id"]),
            "td": json.dumps(td, ensure_ascii=False, default=str),
            "now": datetime.now(timezone.utc),
        },
    )
    if commit:
        await db.commit()

    return ReflowResult(
        note_id=str(row["id"]),
        note_section=note_section,
        added_tables=tuple(result["added"]),
        renamed_tables=tuple(result["renamed"]),
        columns_updated=tuple(result["columns_updated"]),
    )


async def diff_project(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    only_with_changes: bool = False,
) -> list[SectionDiff]:
    """批量：某项目某年度全部附注章节的差异（只读，供预览）。

    预览与执行（Task 6）共用本函数，保证「看到的」等于「将执行的」。
    """
    rows = (
        await db.execute(
            sa.text(
                "SELECT id FROM disclosure_notes "
                "WHERE project_id = :pid AND year = :year AND is_deleted = false "
                "ORDER BY sort_index, sort_order, note_section"
            ),
            {"pid": str(project_id), "year": year},
        )
    ).mappings().all()

    out: list[SectionDiff] = []
    for r in rows:
        try:
            d = await diff_section(db, r["id"])
        except Exception as exc:  # noqa: BLE001 — 单章节失败不阻断整批预览
            logger.warning("diff_section failed for %s: %s", r["id"], exc)
            continue
        if only_with_changes and not d.has_changes:
            continue
        out.append(d)
    return out
