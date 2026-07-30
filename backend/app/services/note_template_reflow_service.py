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

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

__all__ = [
    "ColumnDrift",
    "RenameCandidate",
    "SectionDiff",
    "diff_tables",
    "diff_section",
    "diff_project",
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
