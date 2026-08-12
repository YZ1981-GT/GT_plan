"""程序裁剪 → 附注章节「本期不适用」反向联动（procedure-trimming-and-delegation-intelligence Task 21）。

## 为什么不新建"不适用"字段

附注侧**已有**完整的"本期不适用"机制，本模块只是给它加一个新的触发来源：

- 持久化真源 = ``disclosure_notes.is_empty``（bool 列）
- 判定真源 = ``note_content_utils.note_has_data``（与 ``NoteWordExporter._has_content``
  收敛的共享 helper，归档 spec ``disclosure-notes-selective-generation`` Req2）
- 呈现 = ``disclosure_engine.get_notes_tree`` 按 ``is_empty`` 产出 ``status: "not_applicable"``；
  Word 导出按同一 helper 跳过

⇒ 本模块**只写 ``is_empty``**，判定**只调**上述共享 helper。新建第二套字段或判定逻辑
会让「附注树标记」与「Word 导出结果」漂移（那正是 Req2 当初收敛掉的问题）。

## 与 ``note_trim_service`` 的区别（名字近，做的事完全不同）

``note_trim_service`` 是**附注侧**的章节裁剪向导，判据是试算表科目余额全 0。它写三个
**与本模块无关**的地方，后续会话不得把本联动接到其中任何一个上：

1. ``NoteSectionInstance.status = 'not_applicable'`` —— 另一张表的另一个状态列
2. ``DisclosureNote.is_deleted = True``（``auto_trim_v2`` 段落级）—— **删章节**，与
   R13.2「不删除章节或模板结构」直接冲突
3. ``table_data['_render_as'] = 'no_business_paragraph'``（表格级）—— 改写业务载荷，
   与 R13.2 的可恢复性冲突

本模块的判据是**程序裁剪结果**，只写 ``disclosure_notes.is_empty``。两者是不同触发源、
不同承载列、不同可恢复性语义，不可互相复用。

## 判定规则（两个必须同时成立的合取项）

1. **该章节的全部 owner 底稿都已被粗裁**（``procedure_instances.status ∈ {skip, not_applicable}``）
2. **这些 owner 所属循环各自都被整体裁剪**（该循环下每一条 ``procedure_instances`` 都已裁）

第 1 条不可省：registry 实测有 8 个章节 owner 数 > 1，且**跨循环**
（``五、42 → [K3, M1]``、``五、8 → [G2, G3, K1]``）。只看循环会把「K 循环整体裁掉」
误判成「M1 owner 的章节也不适用」，从而隐藏一段本应披露的内容。

第 2 条不可省：R13.1 的触发条件是「某科目**循环**的程序被**整体**裁剪」。只看
owner 会让「裁掉 G2/G3/K1 三张底稿而 G 循环仍在做」也触发标注 —— 比准则要求宽。
误标"本期不适用"会让一段应披露内容从交付件里消失，故此处取**更保守**的一侧。

## 映射真源

``note_workpaper_sync_registry.json``，经**唯一访问器**
``note_readiness_service.section_workpaper_map()``（``section → [wp_code]``）读取。
本模块**不自己读该 JSON 文件**：正反两个方向都由这一个访问器派生（反向由正向 invert
得到），故两个方向不可能漂移。

⚠️ 已知既有缺口（**不在本 spec 范围内修**）：该访问器只读 ``listed`` / ``soe`` 两个
单数键，registry 里 G1 / G10 另有 ``listed_sections`` / ``soe_sections`` 复数键
（衍生工具章节 五、3 / 五、35）。``disclosure_stale_marker.sections_for_wp_code``
有同一缺口。扩它会改变 stale 标记的既有行为面 ⇒ 非加法式，另议。

## 撤销（R13.3）与 provenance

撤销必须只撤**本联动自己标的**那些章节 —— 否则会把审计师经
``PATCH /sections/{section}`` 手工标的"不适用"一并清掉。而**判定字段仍只有
``is_empty``**，故需要一条只记"谁标的"的面包屑：``template_lineage`` 的
``procedure_trim_not_applicable`` 键。

🔴 该面包屑**不是**第二套不适用字段，判据是结构性的：模块内任何"是否不适用"的
判断都不读它，它只决定"本联动是否有权撤销这一条"。守卫按此断言，并有一条变异
（把它变成判定输入）必须打红。

平台先例：``note_trim_service`` 已在 ``template_lineage`` 写
``deletion_reason`` / ``deletion_at``（注释原话「无独立列，避免 schema 改动」）；
``stale_source`` 亦是"给某个 flag 记来源"的同款做法。本模块因此**零迁移**。

Spec: .kiro/specs/procedure-trimming-and-delegation-intelligence/
Requirements: 13.1 13.2 13.3 13.4 13.5 13.6 13.7
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Literal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

__all__ = [
    "LINEAGE_KEY",
    "TRIMMED_SCOPE_STATUSES",
    "ScopeRow",
    "SectionVerdict",
    "LinkagePlan",
    "resolve_linkage_plan",
    "note_has_manual_content",
    "was_marked_by_linkage",
    "preview_note_linkage",
    "apply_note_linkage",
]

# ``template_lineage`` 内记录"本联动标注过该章节"的键。**只作 provenance**，
# 不参与任何"是否不适用"的判定（见模块 docstring）。
LINEAGE_KEY = "procedure_trim_not_applicable"

# 粗裁后视为"已裁"的 ``procedure_instances.status`` 取值。
#
# 🔴 与 ``ProcedureTrimService.is_scope_trimmed`` / ``_trimmed_scopes()`` 同口径。
#    此处若少一个取值，「被 skip 的底稿」就不算裁 ⇒ 章节永不被标注；多一个取值
#    （如把 ``execute`` 算进来）则会把在做的底稿当成已裁 ⇒ 隐藏应披露内容。
TRIMMED_SCOPE_STATUSES = frozenset({"skip", "not_applicable"})


# ---------------------------------------------------------------------------
# 纯函数层（零 IO，可直接单测与变异检验）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScopeRow:
    """一条粗裁范围快照（来自 ``procedure_instances``）。"""

    cycle: str
    wp_code: str
    status: str

    @property
    def trimmed(self) -> bool:
        return (self.status or "").strip() in TRIMMED_SCOPE_STATUSES


@dataclass(frozen=True)
class SectionVerdict:
    """某附注章节在本次联动下的目标态。"""

    note_section: str
    verdict: Literal["not_applicable", "applicable"]
    owners: tuple[str, ...]
    cycles: tuple[str, ...]
    narrative: str


@dataclass
class LinkagePlan:
    """联动计划（纯派生，无 IO）。"""

    verdicts: list[SectionVerdict] = field(default_factory=list)
    cycles_fully_trimmed: list[str] = field(default_factory=list)
    #: 有 owner 映射但 owner 一个都不在 ``procedure_instances`` 里 → 无判据可依，跳过
    skipped_no_scope: list[str] = field(default_factory=list)

    def by_verdict(self, verdict: str) -> list[SectionVerdict]:
        return [v for v in self.verdicts if v.verdict == verdict]


def resolve_linkage_plan(
    *,
    scopes: list[ScopeRow],
    section_wp_map: dict[str, list[str]],
) -> LinkagePlan:
    """按粗裁快照 + section→wp 映射派生每个章节的目标态（纯函数）。

    Args:
        scopes: ``procedure_instances`` 的 ``(audit_cycle, wp_code, status)`` 快照。
        section_wp_map: ``note_readiness_service.section_workpaper_map()`` 的输出。

    Returns:
        :class:`LinkagePlan`。``verdict == "not_applicable"`` 的章节是**标注候选**
        （仍要过"有无内容"这道闸，见 :func:`note_has_manual_content`）；
        ``verdict == "applicable"`` 的是**撤销候选**（仅撤销本联动标过的）。
    """
    present: dict[str, ScopeRow] = {}
    cycle_rows: dict[str, list[ScopeRow]] = {}
    for row in scopes:
        code = (row.wp_code or "").strip()
        cycle = (row.cycle or "").strip()
        if cycle:
            cycle_rows.setdefault(cycle, []).append(row)
        if not code:
            continue
        # 同一 wp_code 可能有多条 procedure_instances（多条程序）⇒ 只要有一条未裁
        # 就不算该底稿已裁。故按"最不利"合并：trimmed 取 AND。
        prev = present.get(code)
        if prev is None or (prev.trimmed and not row.trimmed):
            present[code] = row

    fully_trimmed_cycles = {
        cycle
        for cycle, rows in cycle_rows.items()
        if rows and all(r.trimmed for r in rows)
    }

    plan = LinkagePlan(cycles_fully_trimmed=sorted(fully_trimmed_cycles))

    for section in sorted(section_wp_map):
        owners = [str(c).strip() for c in (section_wp_map.get(section) or []) if str(c).strip()]
        if not owners:
            continue
        owners_present = [c for c in owners if c in present]
        if not owners_present:
            plan.skipped_no_scope.append(section)
            continue

        rows = [present[c] for c in owners_present]
        cycles = sorted({r.cycle for r in rows if r.cycle})
        all_owners_trimmed = all(r.trimmed for r in rows)
        all_cycles_fully_trimmed = bool(cycles) and all(
            c in fully_trimmed_cycles for c in cycles
        )

        if all_owners_trimmed and all_cycles_fully_trimmed:
            plan.verdicts.append(
                SectionVerdict(
                    note_section=section,
                    verdict="not_applicable",
                    owners=tuple(owners_present),
                    cycles=tuple(cycles),
                    narrative=(
                        f"对应底稿 {'、'.join(owners_present)} 已全部裁剪为不适用，"
                        f"且 {'、'.join(cycles)} 循环程序已整体裁剪"
                    ),
                )
            )
            continue

        if all_owners_trimmed:
            why = (
                f"对应底稿 {'、'.join(owners_present)} 已裁剪，但 "
                f"{'、'.join(c for c in cycles if c not in fully_trimmed_cycles)} "
                "循环仍有程序在执行，未达「整体裁剪」"
            )
        else:
            live = [r.wp_code for r in rows if not r.trimmed]
            why = f"对应底稿 {'、'.join(live)} 本期仍需执行"
        plan.verdicts.append(
            SectionVerdict(
                note_section=section,
                verdict="applicable",
                owners=tuple(owners_present),
                cycles=tuple(cycles),
                narrative=why,
            )
        )

    return plan


def note_has_manual_content(note: Any) -> bool:
    """该章节是否已有内容（R13.4：有内容时只提示，不自动标注）。

    🔴 判定**只调**共享 helper ``note_content_utils.note_has_data``，不自己遍历
    ``table_data``。但必须绕开它的 ``is_empty`` 短路：该 helper 第一句就是
    ``if note.is_empty: return False``（Req2.4 的正确行为，供附注树用），若直接传
    真实 note，**已被本联动标过**的章节恒返 False ⇒ 「标注后审计师又录了内容」这一
    情形永远发现不了，下一轮联动会继续把它标成不适用、把内容压在导出之外。

    故传一个 ``is_empty=False`` 的投影再调同一 helper：判定逻辑仍是唯一那份，
    只是把"我自己上一轮的标注"从输入里剔除，使本判据幂等且与标注状态无关。
    """
    from app.services.note_content_utils import note_has_data

    probe = SimpleNamespace(
        is_empty=False,
        text_content=getattr(note, "text_content", None),
        table_data=getattr(note, "table_data", None),
    )
    return bool(note_has_data(probe))


def was_marked_by_linkage(note: Any) -> bool:
    """本联动是否标过这一条（**provenance**，不是不适用判据）。

    只用于决定"是否有权撤销"。任何"该章节是否不适用"的判断都不得读它 ——
    那个判断的唯一依据是 ``is_empty``。
    """
    lineage = getattr(note, "template_lineage", None)
    return isinstance(lineage, dict) and isinstance(lineage.get(LINEAGE_KEY), dict)


def _lineage_with_mark(
    lineage: Any, *, verdict: SectionVerdict, actor_user_id: UUID | None, at: datetime
) -> dict:
    """构造带面包屑的新 lineage（深拷贝，JSONB 需整体赋新对象才标脏）。"""
    base = dict(lineage) if isinstance(lineage, dict) else {}
    base[LINEAGE_KEY] = {
        "at": at.isoformat(),
        "by": str(actor_user_id) if actor_user_id else None,
        "cycles": list(verdict.cycles),
        "wp_codes": list(verdict.owners),
    }
    return base


def _lineage_without_mark(lineage: Any) -> dict | None:
    base = dict(lineage) if isinstance(lineage, dict) else {}
    base.pop(LINEAGE_KEY, None)
    return base or None


# ---------------------------------------------------------------------------
# 取数 + 分类（preview 与 apply 共用同一份，防两条路径漂移）
# ---------------------------------------------------------------------------


async def _load_scopes(db: AsyncSession, project_id: UUID) -> list[ScopeRow]:
    """读 ``procedure_instances`` 的粗裁快照。

    ``ProcedureInstance`` **没有 year 列**（实测），故不按年过滤；附注侧才按年定位。
    """
    rows = (
        await db.execute(
            sa.text(
                "SELECT audit_cycle, wp_code, status FROM procedure_instances "
                "WHERE project_id = CAST(:pid AS uuid) AND is_deleted = false"
            ),
            {"pid": str(project_id)},
        )
    ).fetchall()
    return [
        ScopeRow(
            cycle=str(r[0] or "").strip(),
            wp_code=str(r[1] or "").strip(),
            status=str(r[2] or "").strip(),
        )
        for r in rows
    ]


@dataclass
class _Classification:
    to_mark: list[dict] = field(default_factory=list)
    already_marked: list[dict] = field(default_factory=list)
    #: 候选但有内容 → 只提示不标注（R13.4）
    conflicts: list[dict] = field(default_factory=list)
    to_revoke: list[dict] = field(default_factory=list)
    #: 候选但附注侧定位不到章节 → 跳过并记录（R13.6）
    unlocatable: list[dict] = field(default_factory=list)
    skipped_foreign_mark: list[dict] = field(default_factory=list)
    degradations: list[dict] = field(default_factory=list)
    cycles_fully_trimmed: list[str] = field(default_factory=list)


async def _classify(
    db: AsyncSession, project_id: UUID, year: int
) -> tuple[_Classification, dict[str, Any]]:
    """派生分类 + 返回命中的 note ORM 对象（apply 用；preview 不写）。"""
    out = _Classification()

    try:
        from app.services.note_readiness_service import section_workpaper_map

        section_wp_map = section_workpaper_map()
    except Exception as exc:  # noqa: BLE001 — registry 不可用 → 降级为空计划
        logger.warning("procedure_trim_note_linkage: registry unavailable: %s", exc)
        out.degradations.append({"stage": "registry", "reason": str(exc)})
        return out, {}
    if not section_wp_map:
        out.degradations.append(
            {"stage": "registry", "reason": "section→wp 映射为空，无法定位任何附注章节"}
        )
        return out, {}

    scopes = await _load_scopes(db, project_id)
    plan = resolve_linkage_plan(scopes=scopes, section_wp_map=section_wp_map)
    out.cycles_fully_trimmed = plan.cycles_fully_trimmed

    sections = [v.note_section for v in plan.verdicts]
    notes: dict[str, Any] = {}
    if sections:
        from app.models.report_models import DisclosureNote

        rows = (
            (
                await db.execute(
                    sa.select(DisclosureNote).where(
                        DisclosureNote.project_id == project_id,
                        DisclosureNote.year == year,
                        DisclosureNote.note_section.in_(sections),
                        DisclosureNote.is_deleted == sa.false(),
                    )
                )
            )
            .scalars()
            .all()
        )
        notes = {n.note_section: n for n in rows}

    for v in plan.verdicts:
        note = notes.get(v.note_section)
        item = {
            "note_section": v.note_section,
            "owners": list(v.owners),
            "cycles": list(v.cycles),
            "narrative": v.narrative,
            "section_title": getattr(note, "section_title", None),
        }
        if v.verdict == "not_applicable":
            if note is None:
                # R13.6：定位不到就跳过并记录，绝不报错阻断裁剪保存
                out.unlocatable.append({**item, "reason": "no_disclosure_note_row"})
                continue
            if note_has_manual_content(note):
                # R13.4：有内容时只提示。**两个方向都不自动动** —— 已标过的也不自动
                # 撤销，因为撤销同样是自动动作；交由审计师在附注侧决定。
                out.conflicts.append(
                    {
                        **item,
                        "currently_marked": bool(note.is_empty),
                        "reason": "has_content",
                    }
                )
                continue
            if note.is_empty:
                out.already_marked.append(item)
            else:
                out.to_mark.append(item)
            continue

        # verdict == applicable → 撤销候选
        if note is None or not note.is_empty:
            continue
        if not was_marked_by_linkage(note):
            # 审计师手工标的"不适用"不属本联动的撤销范围
            out.skipped_foreign_mark.append({**item, "reason": "marked_by_user"})
            continue
        out.to_revoke.append(item)

    return out, notes


def _as_payload(c: _Classification) -> dict:
    return {
        "to_mark": c.to_mark,
        "already_marked": c.already_marked,
        "conflicts": c.conflicts,
        "to_revoke": c.to_revoke,
        "unlocatable": c.unlocatable,
        "skipped_foreign_mark": c.skipped_foreign_mark,
        "degradations": c.degradations,
        "cycles_fully_trimmed": c.cycles_fully_trimmed,
        "summary": {
            "to_mark": len(c.to_mark),
            "already_marked": len(c.already_marked),
            "conflicts": len(c.conflicts),
            "to_revoke": len(c.to_revoke),
            "unlocatable": len(c.unlocatable),
        },
    }


async def preview_note_linkage(db: AsyncSession, project_id: UUID, year: int) -> dict:
    """只读预览：本次联动会标注 / 撤销 / 只提示哪些附注章节。

    不写任何字段（供裁剪页在应用前展示，也供复核追溯）。
    """
    classification, _ = await _classify(db, project_id, year)
    return _as_payload(classification)


async def apply_note_linkage(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    actor_user_id: UUID | None = None,
) -> dict:
    """应用联动：只写 ``is_empty`` + provenance 面包屑（service 只 flush）。

    - **不删除**章节、不动 ``table_data`` / ``text_content``（R13.2 可恢复性）
    - 有内容的章节只进 ``conflicts``，两个方向都不自动动（R13.4）
    - 定位不到的章节进 ``unlocatable``，不抛（R13.6）
    - 幂等：重复调用对已处于目标态的章节零写入
    """
    classification, notes = await _classify(db, project_id, year)
    from sqlalchemy.orm.attributes import flag_modified

    now = datetime.now(timezone.utc)
    marked = 0
    revoked = 0

    verdict_by_section = {
        item["note_section"]: SectionVerdict(
            note_section=item["note_section"],
            verdict="not_applicable",
            owners=tuple(item["owners"]),
            cycles=tuple(item["cycles"]),
            narrative=item["narrative"],
        )
        for item in classification.to_mark
    }

    for item in classification.to_mark:
        section = item["note_section"]
        note = notes.get(section)
        if note is None:  # pragma: no cover — _classify 已保证存在
            continue
        try:
            note.is_empty = True
            note.template_lineage = _lineage_with_mark(
                note.template_lineage,
                verdict=verdict_by_section[section],
                actor_user_id=actor_user_id,
                at=now,
            )
            flag_modified(note, "template_lineage")
            marked += 1
        except Exception as exc:  # noqa: BLE001 — 单章节失败不阻断其余
            logger.warning("procedure_trim_note_linkage: mark %s failed: %s", section, exc)
            classification.degradations.append(
                {"stage": "mark", "note_section": section, "reason": str(exc)}
            )

    for item in classification.to_revoke:
        section = item["note_section"]
        note = notes.get(section)
        if note is None:  # pragma: no cover
            continue
        try:
            note.is_empty = False
            note.template_lineage = _lineage_without_mark(note.template_lineage)
            flag_modified(note, "template_lineage")
            revoked += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("procedure_trim_note_linkage: revoke %s failed: %s", section, exc)
            classification.degradations.append(
                {"stage": "revoke", "note_section": section, "reason": str(exc)}
            )

    if marked or revoked:
        await db.flush()

    payload = _as_payload(classification)
    payload["marked"] = marked
    payload["revoked"] = revoked
    return payload
