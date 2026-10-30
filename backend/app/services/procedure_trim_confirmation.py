"""粗裁确认当前态投影（spec trim-generation-plan-followup-optimizations R3）。

「某循环保存过粗裁」原先每次请求都扫描本项目全部已消费的粗裁预览凭证（``procedure_operation_previews``
的 ``request_payload_snapshot`` JSON）。现在 ``procedure_trim_cycle_confirmations`` 记每项目每循环的当前态：

- 写：粗裁 apply 消费预览的同一事务内（``consume_and_apply(after_consume=...)``），凭证里出现的每个 scope
  循环 upsert 一行。applied=0 的保存也算确认；只有细裁行的请求不写；同 request_id 重试走幂等分支、不重复写。
- 最新：``(confirmed_at, source_preview_id)`` 最大者，与 V218 回填同一规则、与提交先后无关；
  ``revision_no`` = 含该循环的已消费预览数（每次保存 +1）。
- 读：:func:`load_projection` 只查投影并带出操作人显示名；正常请求不再扫描历史 JSON。
- 校验：:func:`verify_projection` 从凭证重算投影逐字段比对，并与旧扫描结果对拍（运维检查 / 测试用）。

预览凭证仍是不可变的历史真源，投影只是派生数据（R218 删投影即回到按凭证扫描的旧读法）。
条目字段只认 JSON 字符串、循环按「去首尾空格 + 大写」归一 —— 与 V218 回填 SQL 逐字同口径，
:func:`cycle_revision_hash` 与 SQL ``jsonb_agg(...)::text`` 的序列化逐字节一致（PG 测试钉住）。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procedure_models import ProcedureOperationPreview, ProcedureTrimCycleConfirmation

#: 粗裁预览凭证的 operation（``procedure_trim_service`` 从这里导入，只定义一处）。
TRIM_OPERATION = "trim"
_SCOPE_KIND = "scope"
_MAX_CYCLE_LENGTH = 10


def _text(value: Any) -> str:
    """条目字段只认 JSON 字符串；损坏 / 缺失记空串（与 V218 ``jsonb_typeof = 'string'`` 同口径）。"""
    return value if isinstance(value, str) else ""


def _cycle_key(value: Any) -> str | None:
    """循环归一：只认字符串，去首尾空格后大写（与 SQL ``upper(btrim(...))`` 同口径）。

    空值 / 超过 10 个字符返回 None：程序行循环是 VARCHAR(10)，更长的循环不可能对应任何程序行。
    """
    if not isinstance(value, str):
        return None
    stripped = value.strip(" ")
    return stripped.upper() if stripped and len(stripped) <= _MAX_CYCLE_LENGTH else None


def snapshot_entries(snapshot: Any) -> list:
    entries = snapshot.get("entries") if isinstance(snapshot, Mapping) else None
    return entries if isinstance(entries, list) else []


def scope_entries_by_cycle(entries: Iterable[Any]) -> dict[str, list[Mapping]]:
    """把凭证里的 scope 条目按归一循环分组；细裁行 / 非对象 / 无循环的条目忽略。"""
    groups: dict[str, list[Mapping]] = {}
    for entry in entries:
        if not isinstance(entry, Mapping) or entry.get("kind") != _SCOPE_KIND:
            continue
        cycle = _cycle_key(entry.get("cycle"))
        if cycle is not None:
            groups.setdefault(cycle, []).append(entry)
    return groups


def cycle_revision_hash(entries: Iterable[Mapping]) -> str:
    """一个循环一次保存的决定指纹：``[编码, 目标状态, 理由]`` 按码点排序、JSON 序列化后 SHA-256。

    与 V218 回填的 ``jsonb_agg(jsonb_build_array(code,status,reason) ORDER BY ... COLLATE "C")::text``
    逐字节一致：jsonb 数组输出用 ``", "`` 分隔、非 ASCII 原样输出、控制字符转义规则与 ``json.dumps`` 相同。
    """
    triples = sorted(
        [_text(e.get("wp_index_code")), _text(e.get("target_status")), _text(e.get("skip_reason"))]
        for e in entries
    )
    return hashlib.sha256(json.dumps(triples, ensure_ascii=False).encode("utf-8")).hexdigest()


def _dialect_insert(db: AsyncSession):
    name = db.get_bind().dialect.name
    if name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:  # pragma: no cover - 平台只跑 PG（测试库 SQLite）
        raise RuntimeError(f"粗裁确认投影不支持数据库方言：{name}")
    return insert


async def record_confirmations(db: AsyncSession, preview: ProcedureOperationPreview) -> list[str]:
    """粗裁预览消费成功后（同一事务）按凭证里的 scope 循环 upsert 投影；返回写入的循环（细裁行请求 → ``[]``）。

    冲突时 ``revision_no`` 恒 +1；来源 / 时间 / 操作人 / 指纹只在本次 ``(consumed_at, id)`` 更新时覆盖，
    所以并发或时钟偏差下提交先后不同，结果仍与 V218 回填规则一致。只 flush 由调用方 commit。
    """
    if preview.operation != TRIM_OPERATION or preview.consumed_at is None:
        raise ValueError("只有已消费的粗裁预览凭证才能写入粗裁确认")
    groups = scope_entries_by_cycle(snapshot_entries(preview.request_payload_snapshot))
    if not groups:
        return []
    request_id = preview.consumed_request_id or f"legacy:{preview.id}"
    table = ProcedureTrimCycleConfirmation.__table__
    stmt = _dialect_insert(db)(table).values([
        {
            "project_id": preview.project_id,
            "audit_cycle": cycle,
            "source_preview_id": preview.id,
            "confirmed_by": preview.actor_user_id,
            "confirmed_at": preview.consumed_at,
            "request_id": request_id,
            "cycle_revision_hash": cycle_revision_hash(entries),
            "revision_no": 1,
        }
        for cycle, entries in sorted(groups.items())
    ])
    newer = sa.tuple_(stmt.excluded.confirmed_at, stmt.excluded.source_preview_id) > sa.tuple_(
        table.c.confirmed_at, table.c.source_preview_id)

    def _pick(column: str):
        return sa.case((newer, stmt.excluded[column]), else_=table.c[column])

    stmt = stmt.on_conflict_do_update(
        index_elements=[table.c.project_id, table.c.audit_cycle],
        set_={
            **{c: _pick(c) for c in (
                "source_preview_id", "confirmed_by", "confirmed_at", "request_id", "cycle_revision_hash")},
            "revision_no": table.c.revision_no + 1,
            "updated_at": sa.func.now(),
        },
    )
    await db.execute(stmt)
    await db.flush()
    return sorted(groups)


async def load_projection(db: AsyncSession, project_id: UUID) -> dict[str, dict[str, Any]]:
    """各循环当前确认 ``{循环: {confirmed_at, confirmed_by_id, confirmed_by}}``；只查投影 + 操作人显示名。

    显示名：人员档案姓名优先（同一账号多份档案取最早建的那份），没有用登录名，账号不存在为 None。
    """
    from app.models.core import User
    from app.models.staff_models import StaffMember

    t = ProcedureTrimCycleConfirmation
    staff_name = (
        sa.select(StaffMember.name)
        .where(StaffMember.user_id == t.confirmed_by, StaffMember.is_deleted == sa.false(),
               sa.func.coalesce(StaffMember.name, "") != "")
        .order_by(StaffMember.created_at, StaffMember.id)
        .limit(1)
        .correlate(t)
        .scalar_subquery()
    )
    rows = (await db.execute(
        sa.select(t.audit_cycle, t.confirmed_at, t.confirmed_by, staff_name, User.username)
        .select_from(t)
        .outerjoin(User, User.id == t.confirmed_by)
        .where(t.project_id == project_id)
    )).all()
    return {
        cycle: {"confirmed_at": at, "confirmed_by_id": actor, "confirmed_by": name or username or None}
        for cycle, at, actor, name, username in rows
    }


# ---------------------------------------------------------------------------
# 校验：凭证重算 vs 投影；旧扫描 vs 投影
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfirmationRow:
    source_preview_id: UUID
    confirmed_by: UUID
    confirmed_at: datetime
    request_id: str
    cycle_revision_hash: str
    revision_no: int


@dataclass(frozen=True)
class ConsumedPreview:
    id: UUID
    project_id: UUID
    actor_user_id: UUID
    consumed_at: datetime
    consumed_request_id: str | None
    snapshot: Any


def _aware(at: datetime) -> datetime:
    """SQLite 读出来不带时区，按 UTC 补；PG timestamptz 原样。"""
    return at if at.tzinfo else at.replace(tzinfo=timezone.utc)


def expected_projection(previews: Iterable[ConsumedPreview]) -> dict[tuple[UUID, str], ConfirmationRow]:
    """按凭证重算投影（V218 回填 / :func:`record_confirmations` 的同一规则）。"""
    per_cycle: dict[tuple[UUID, str], list[tuple[ConsumedPreview, str]]] = {}
    for p in previews:
        for cycle, entries in scope_entries_by_cycle(snapshot_entries(p.snapshot)).items():
            per_cycle.setdefault((p.project_id, cycle), []).append((p, cycle_revision_hash(entries)))
    out: dict[tuple[UUID, str], ConfirmationRow] = {}
    for key, items in per_cycle.items():
        latest, digest = max(items, key=lambda item: (_aware(item[0].consumed_at), item[0].id))
        out[key] = ConfirmationRow(
            source_preview_id=latest.id, confirmed_by=latest.actor_user_id,
            confirmed_at=_aware(latest.consumed_at),
            request_id=latest.consumed_request_id or f"legacy:{latest.id}",
            cycle_revision_hash=digest, revision_no=len(items),
        )
    return out


def legacy_scan_candidates(previews: Iterable[ConsumedPreview]) -> dict[tuple[UUID, str], set[tuple[datetime, UUID]]]:
    """旧读法（切换前 ``_latest_by_cycle``）可能给出的结果：每循环最新时间上的 ``(时间, 操作人)`` 候选集合。

    旧读法按原始循环字符串分组（不归一），同一最新时间多份凭证时取哪份由库返回顺序决定 —— 所以给候选集合。
    """
    best: dict[tuple[UUID, str], tuple[datetime, set[tuple[datetime, UUID]]]] = {}
    for p in previews:
        at = _aware(p.consumed_at)
        for entry in snapshot_entries(p.snapshot):
            if not isinstance(entry, dict) or entry.get("kind") != _SCOPE_KIND or not entry.get("cycle"):
                continue
            key = (p.project_id, str(entry["cycle"]))
            current = best.get(key)
            if current is None or at > current[0]:
                best[key] = (at, {(at, p.actor_user_id)})
            elif at == current[0]:
                current[1].add((at, p.actor_user_id))
    return {key: candidates for key, (_, candidates) in best.items()}


@dataclass
class ProjectionReport:
    projection_rows: int = 0
    expected_rows: int = 0
    missing: list[tuple[UUID, str]] = field(default_factory=list)
    unexpected: list[tuple[UUID, str]] = field(default_factory=list)
    field_mismatches: list[tuple[UUID, str, str]] = field(default_factory=list)
    legacy_mismatches: list[tuple[UUID, str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.missing or self.unexpected or self.field_mismatches or self.legacy_mismatches)


def compare_projection(
    actual: Mapping[tuple[UUID, str], ConfirmationRow],
    previews: list[ConsumedPreview],
) -> ProjectionReport:
    expected = expected_projection(previews)
    legacy = legacy_scan_candidates(previews)
    report = ProjectionReport(projection_rows=len(actual), expected_rows=len(expected))
    report.missing = sorted(set(expected) - set(actual), key=str)
    report.unexpected = sorted(set(actual) - set(expected), key=str)
    for key in sorted(set(expected) & set(actual), key=str):
        want, got = expected[key], actual[key]
        for name in ConfirmationRow.__dataclass_fields__:
            w, g = getattr(want, name), getattr(got, name)
            if isinstance(g, datetime):
                g = _aware(g)
            if w != g:
                report.field_mismatches.append((*key, f"{name}: 应为 {w!r}，投影 {g!r}"))
    for key in sorted(set(legacy) | set(actual), key=str):
        row = actual.get(key)
        if key not in legacy:
            report.legacy_mismatches.append((*key, "旧读法没有该循环"))
        elif row is None:
            report.legacy_mismatches.append((*key, "投影缺少旧读法确认过的循环"))
        elif (_aware(row.confirmed_at), row.confirmed_by) not in legacy[key]:
            report.legacy_mismatches.append((*key, "确认时间 / 操作人与旧读法不一致"))
    return report


async def load_consumed_previews(db: AsyncSession, project_id: UUID | None = None) -> list[ConsumedPreview]:
    p = ProcedureOperationPreview
    stmt = sa.select(p.id, p.project_id, p.actor_user_id, p.consumed_at, p.consumed_request_id,
                     p.request_payload_snapshot).where(p.operation == TRIM_OPERATION, p.consumed_at.isnot(None))
    if project_id is not None:
        stmt = stmt.where(p.project_id == project_id)
    return [ConsumedPreview(*row) for row in (await db.execute(stmt)).all()]


async def load_projection_rows(
    db: AsyncSession, project_id: UUID | None = None,
) -> dict[tuple[UUID, str], ConfirmationRow]:
    t = ProcedureTrimCycleConfirmation
    stmt = sa.select(t.project_id, t.audit_cycle, t.source_preview_id, t.confirmed_by, t.confirmed_at,
                     t.request_id, t.cycle_revision_hash, t.revision_no)
    if project_id is not None:
        stmt = stmt.where(t.project_id == project_id)
    return {(row[0], row[1]): ConfirmationRow(*row[2:]) for row in (await db.execute(stmt)).all()}


async def verify_projection(db: AsyncSession, project_id: UUID | None = None) -> ProjectionReport:
    """逐项目逐循环比对投影与凭证（只读）；``report.ok`` 为假即不一致，调用方应 fail-closed。"""
    return compare_projection(
        await load_projection_rows(db, project_id),
        await load_consumed_previews(db, project_id),
    )
