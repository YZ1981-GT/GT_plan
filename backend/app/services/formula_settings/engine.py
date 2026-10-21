"""「上游变化」执行器：把同步内核的效果落到存储、待确认事项与审计（design §4 / §6）。

全局发布、模板发布新版本、订阅、退订共用：调用方先算好每个（项目, 公式位）的
旧上游 / 新上游 / 本项目状态（:class:`PlanItem`），这里统一分类、决策、写入。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.formula_settings.audit import change_entry
from app.services.formula_settings.definitions import display_formula, same_exec
from app.services.formula_settings.pending import close_pending, upsert_pending
from app.services.formula_settings.projects import ProjectInfo
from app.services.formula_settings.stores import DomainStore, SlotRecord
from app.services.formula_settings.sync import (
    CATEGORY_LABELS,
    Action,
    Category,
    ConflictChoice,
    Effect,
    ProjectChoice,
    classify,
    decide,
)

#: 全局发布时，本项目行来自订阅模板（模板层优先）——不受本次全局变化影响
TEMPLATE_SKIPPED = "template"


# ── 锁 ────────────────────────────────────────────────────────────────────────


def _is_pg(db: AsyncSession) -> bool:
    bind = db.get_bind()
    return bind is not None and bind.dialect.name == "postgresql"


async def lock_domain(db: AsyncSession, domain: str, *, shared: bool = False) -> None:
    """域级咨询事务锁：发布取排他，项目侧写取共享（与发布互斥、彼此并行）。SQLite 跳过。"""
    if not _is_pg(db):
        return
    fn = "pg_advisory_xact_lock_shared" if shared else "pg_advisory_xact_lock"
    await db.execute(sa.text(f"SELECT {fn}(hashtextextended(:k, 0))"), {"k": f"formula_settings:{domain}"})


async def lock_project(db: AsyncSession, domain: str, project_id: uuid.UUID) -> None:
    """项目侧写：先取域共享锁，再取本项目排他锁。"""
    await lock_domain(db, domain, shared=True)
    if _is_pg(db):
        await db.execute(sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
                         {"k": f"formula_settings:{domain}:{project_id}"})


# ── 计划项 ────────────────────────────────────────────────────────────────────


@dataclass
class PlanItem:
    project: ProjectInfo
    slot_key: str
    label: str
    old_up: dict | None
    old_version: int | None
    old_origin: str
    new_up: dict | None
    new_version: int | None
    new_origin: str
    local: SlotRecord | None
    structure: dict = field(default_factory=dict)
    old_template_id: uuid.UUID | None = None
    new_template_id: uuid.UUID | None = None
    #: 新上游来自全局且写入定义与之相同时删除本项目行（模板退场 → 回到继承）
    retire_same: bool = False
    #: 新上游为模板：无本项目行也要写（物化）
    materialize: bool = False
    #: 新上游的版本来自本次写入的哪个公式位（发布写全局后回填真实版本）
    version_from_change: bool = False
    category: Category | None = None
    skipped: str | None = None

    @property
    def key(self) -> str:
        return f"{self.project.id}|{self.slot_key}"

    def classify(self, domain: str) -> Category:
        self.category = classify(domain, new_upstream=self.new_up,
                                 local=self.local.local_state() if self.local else None,
                                 frozen=self.project.frozen)
        return self.category

    def to_dict(self, domain: str) -> dict[str, Any]:
        lo = self.local
        cat = self.skipped or (self.category.value if self.category else "")
        return {
            "key": self.key,
            "project_id": str(self.project.id),
            "project_name": self.project.name,
            "project_status": self.project.status,
            "frozen": self.project.frozen,
            "slot_key": self.slot_key,
            "label": self.label,
            "category": cat,
            "category_label": "模板覆盖（不受影响）" if cat == TEMPLATE_SKIPPED else CATEGORY_LABELS.get(cat, cat),
            "base_definition": _plain(lo.base_definition) if lo else None,
            "old_upstream": _plain(self.old_up),
            "new_upstream": _plain(self.new_up),
            "local_definition": _plain(lo.definition) if lo else None,
            "base_formula": display_formula(domain, lo.base_definition) if lo else "",
            "old_formula": display_formula(domain, self.old_up),
            "new_formula": display_formula(domain, self.new_up) if self.new_up is not None else "（已删除）",
            "local_formula": display_formula(domain, lo.definition) if lo else "",
            "local_version": lo.version if lo else None,
            "new_origin": self.new_origin,
            "pinned": bool(lo.pinned) if lo else False,
        }


def _plain(definition: Mapping[str, Any] | None) -> dict | None:
    if definition is None:
        return None
    return {k: v for k, v in dict(definition).items() if k != "_structure"}


@dataclass
class Decisions:
    """管理员（或项目成员）对计划的决策：项目级「应用 / 暂缓」+ 冲突级「采用 / 保留 / 交项目确认」。"""

    project_choices: dict[str, ProjectChoice] = field(default_factory=dict)
    conflict_choices: dict[str, ConflictChoice] = field(default_factory=dict)
    default_conflict: ConflictChoice = ConflictChoice.ASK

    def __post_init__(self) -> None:
        # 内核按枚举身份判断（``is``）：传进来的字符串一律转成枚举，免得「keep」被当成采用
        self.project_choices = {str(k): ProjectChoice(v) for k, v in self.project_choices.items()}
        self.conflict_choices = {str(k): ConflictChoice(v) for k, v in self.conflict_choices.items()}
        self.default_conflict = ConflictChoice(self.default_conflict)

    @classmethod
    def parse(cls, raw: Mapping[str, Any] | None) -> "Decisions":
        raw = raw or {}
        return cls(
            project_choices={str(k): ProjectChoice(v) for k, v in (raw.get("project_choices") or {}).items()},
            conflict_choices={str(k): ConflictChoice(v) for k, v in (raw.get("conflict_choices") or {}).items()},
            default_conflict=ConflictChoice(raw.get("default_conflict") or ConflictChoice.ASK.value),
        )

    def project(self, project_id: uuid.UUID) -> ProjectChoice:
        return self.project_choices.get(str(project_id), ProjectChoice.APPLY)

    def conflict(self, item: PlanItem) -> ConflictChoice:
        return self.conflict_choices.get(item.key, self.default_conflict)


# ── 落地 ──────────────────────────────────────────────────────────────────────


@dataclass
class ApplyOutcome:
    effect: Effect
    audit: dict[str, Any] | None
    pending: bool


def decide_item(domain: str, item: PlanItem, decisions: Decisions) -> Effect:
    assert item.category is not None
    return decide(domain, item.category, old_upstream=item.old_up, old_version=item.old_version,
                  new_upstream=item.new_up, new_version=item.new_version, local=item.local.local_state()
                  if item.local else None, project_choice=decisions.project(item.project.id),
                  conflict_choice=decisions.conflict(item), materialize=item.materialize)


async def apply_effect(db: AsyncSession, store: DomainStore, item: PlanItem, effect: Effect, *,
                       publish_id: uuid.UUID | None, user_id: uuid.UUID | None) -> ApplyOutcome:
    """按效果写本项目层与待确认事项；返回审计条目（无需留痕时为 ``None``）。"""
    domain, pid, slot, local = store.domain, item.project.id, item.slot_key, item.local
    action = effect.action
    common = dict(user_id=user_id, label=item.label, structure=item.structure or None)
    effective_before = local.definition if local else item.old_up
    effective_after = effective_before
    if action is Action.SET_LOCAL:
        if item.retire_same and same_exec(domain, effect.local_definition, item.new_up):
            if local is not None:
                await store.delete_project(db, pid, slot)
        else:
            await store.write_project(db, pid, slot, definition=dict(effect.local_definition or {}),
                                      base_definition=effect.base_definition, base_version=effect.base_version,
                                      pinned=False, base_origin=item.new_origin,
                                      base_template_id=item.new_template_id, **common)
        effective_after = effect.local_definition
    elif action is Action.DELETE_LOCAL:
        if local is not None:
            await store.delete_project(db, pid, slot)
        effective_after = item.new_up
    elif action is Action.REBASE:
        await store.write_project(db, pid, slot,
                                  definition=dict(effect.local_definition or (local.definition if local else {})),
                                  base_definition=effect.base_definition, base_version=effect.base_version,
                                  pinned=False, base_origin=item.new_origin,
                                  base_template_id=item.new_template_id, **common)
    elif action is Action.PIN:
        # 新上游是模板（订阅项目暂缓 / 冻结）：固定行记为模板层，全局发布跳过它（模板层优先）
        template_pin = local is None and item.new_origin == "template"
        origin = (local.base_origin if local else None) or ("template" if template_pin else item.old_origin)
        tpl = local.base_template_id if local else (item.new_template_id if template_pin else item.old_template_id)
        await store.write_project(db, pid, slot, definition=dict(effect.local_definition or {}),
                                  base_definition=effect.base_definition, base_version=effect.base_version,
                                  pinned=True, base_origin=origin, base_template_id=tpl, **common)
    elif action is Action.NONE and effect.effective_changed:
        effective_after = item.new_up

    pending = bool(effect.pending_reason)
    if pending:
        await upsert_pending(
            db, project_id=pid, domain=domain, slot_key=slot, slot_label=item.label,
            reason=effect.pending_reason or "conflict",
            base_definition=local.base_definition if local else item.old_up,
            upstream_definition=item.new_up, upstream_version=item.new_version,
            local_definition=local.definition if local else effect.local_definition,
            publish_id=publish_id, upstream_origin=item.new_origin, upstream_template_id=item.new_template_id,
        )
    elif action in (Action.SET_LOCAL, Action.DELETE_LOCAL, Action.REBASE):
        await close_pending(db, pid, domain, [slot])

    record = not (action is Action.NONE and not effect.effective_changed)
    if action is Action.REBASE and item.category is Category.SAME:
        record = False
    audit = None
    if record:
        audit = change_entry(domain, slot, effective_before, effective_after,
                             category=item.category.value if item.category else None,
                             effect=("pending" if pending else action.value),
                             upstream_formula=display_formula(domain, item.new_up) if pending else None,
                             config_id=local.row_id if local else None)
    return ApplyOutcome(effect, audit, pending)


# ── 汇总 ──────────────────────────────────────────────────────────────────────


def empty_counts() -> dict[str, int]:
    return {c.value: 0 for c in Category} | {TEMPLATE_SKIPPED: 0}


def summarize(items: Iterable[PlanItem], projects: Iterable[ProjectInfo],
              outcomes: Mapping[str, ApplyOutcome] | None = None) -> dict[str, Any]:
    counts = empty_counts()
    per: dict[uuid.UUID, dict[str, Any]] = {}
    for p in projects:
        per[p.id] = {"project_id": str(p.id), "name": p.name, "status": p.status, "frozen": p.frozen,
                     "counts": empty_counts(), "pending": 0, "changed": False}
    for it in items:
        cat = it.skipped or (it.category.value if it.category else "")
        counts[cat] = counts.get(cat, 0) + 1
        row = per.setdefault(it.project.id, {"project_id": str(it.project.id), "name": it.project.name,
                                             "status": it.project.status, "frozen": it.project.frozen,
                                             "counts": empty_counts(), "pending": 0, "changed": False})
        row["counts"][cat] = row["counts"].get(cat, 0) + 1
        out = (outcomes or {}).get(it.key)
        if out is not None:
            row["pending"] += int(out.pending)
            row["changed"] = row["changed"] or (out.effect.effective_changed and not it.project.frozen)
    affected = [r for r in per.values() if any(v for k, v in r["counts"].items() if k != TEMPLATE_SKIPPED)]
    return {
        "counts": counts,
        "projects": sorted(per.values(), key=lambda r: r["name"]),
        "affected_project_count": len(affected),
        "conflict_count": counts.get(Category.CONFLICT.value, 0),
        "pending_total": sum(r["pending"] for r in per.values()),
        "changed_projects": [r["project_id"] for r in per.values() if r["changed"]],
    }


def changed_slots(items: Iterable[PlanItem], outcomes: Mapping[str, ApplyOutcome]) -> dict[uuid.UUID, list[str]]:
    """每个项目有效定义发生变化的公式位（传播事件用）。"""
    out: dict[uuid.UUID, list[str]] = {}
    for it in items:
        o = outcomes.get(it.key)
        if o is not None and o.effect.effective_changed and not it.project.frozen:
            out.setdefault(it.project.id, []).append(it.slot_key)
    return out
