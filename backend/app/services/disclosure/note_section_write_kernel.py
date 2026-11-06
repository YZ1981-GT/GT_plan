"""附注章节原子写入内核：一次 advisory lock + 一次 deepcopy + 一次写。

C2/C3 收口骨架（spec: `platform-heavy-jobs-and-capacity-closure`）：
    现有写入方（``disclosure_engine.update_note`` / `note_followup` /
    `consol_note_subtree_reaggregate` / etc.）各自保留业务 mutator，但共用本内核的
    三件事：

      1. ``pg_advisory_xact_lock(namespace, hashtext(key))``：
         同 (project_id, year, section_id) 串行，不同章节天然并行；
         非 PG 环境自动降级为 no-op。
      2. ``SELECT ... FOR UPDATE``（仅 PG）：避免并发 ORM 从外部漂进内核。
      3. ``copy.deepcopy(table_data)``：业务 mutator 只碰 workspace；
         结束时按稳定序列化比较差集，不变则不写、不触发 UPDATE。

不改契约：
    - 返回的 ``DisclosureNote`` 原样挂在当前 session；
    - 调用方仍负责 commit / rollback / 事件派发。
    - 任何写入方愿意接入本内核时按 ``mutate_note_section(...)`` 单入口调用即可；
      本模块不读 ``disclosure_notes`` 之外的任何表，不派发事件、不写 stale。

真实 PG 并发 barrier（C2/C3 `[ ]*` 的那部分）仍属专用环境验收。
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable, Optional
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified


__all__ = [
    "SectionMutateResult",
    "mutate_note_section",
    "stable_hash",
]


# 独立 namespace，避免和 `report_provenance:pg_advisory_xact_lock(hashtextextended(...))`
# / `workpaper_sync._ADVISORY_NAMESPACE=0x7770` / other advisory 锁冲突。
_ADVISORY_NAMESPACE = 0x6E6F7465  # b"note" 字面


@dataclass
class SectionMutateResult:
    note_id: UUID
    changed: bool
    before_hash: str
    after_hash: str


async def mutate_note_section(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    section_id: str,
    mutator: Callable[[Any, dict[str, Any]], None],
) -> Optional[SectionMutateResult]:
    """用统一内核对单个附注章节做原子 mutator 写入。

    参数：
        db:
            当前 AsyncSession；内核只做 ``flush()``，不 commit / rollback。
        project_id / year / section_id:
            定位 ``disclosure_notes`` 唯一活跃章节（``is_deleted=false``）。
        mutator:
            接收 ``(note, workspace)``，直接改 ``workspace``（``note.table_data`` 的
            deepcopy）；返回值被忽略。非 ``table_data`` 字段可直接改 ``note``。

    返回 ``None`` 当章节不存在（软删或未创建）；否则返回带 ``changed`` / hashes
    的结果；``changed=False`` 时内核**不触发** ``flag_modified`` 也不发 UPDATE。

    PG：
        - ``pg_advisory_xact_lock(_ADVISORY_NAMESPACE, hashtext(key))``
        - ``SELECT ... FOR UPDATE``
    其他方言：
        - advisory 锁跳过（本进程串行即可，适合单元测试）
        - 不加 ``FOR UPDATE``
    """
    from app.models.report_models import DisclosureNote  # 延迟 import 避免循环

    await _acquire_section_lock(db, project_id, year, section_id)

    is_pg = db.bind is not None and db.bind.dialect.name == "postgresql"
    stmt = sa.select(DisclosureNote).where(
        DisclosureNote.project_id == project_id,
        DisclosureNote.year == year,
        DisclosureNote.note_section == section_id,
        DisclosureNote.is_deleted == sa.false(),
    )
    if is_pg:
        stmt = stmt.with_for_update()
    note = (await db.execute(stmt)).scalar_one_or_none()
    if note is None:
        return None

    workspace: dict[str, Any] = copy.deepcopy(note.table_data) if note.table_data is not None else {}
    before = stable_hash(workspace)

    mutator(note, workspace)

    after = stable_hash(workspace)
    changed = before != after

    if changed:
        note.table_data = workspace
        flag_modified(note, "table_data")
    # 无条件 flush：mutator 允许直接改 note 的非 table_data 字段（text_content /
    # status / guidance_text 等），内核不追踪这些字段，但退出前必须让它们落盘。
    # changed=False 时也只有一次 flush：如果 mutator 什么都没改，flush 即 no-op；
    # 否则按真实 dirty set 发 UPDATE。
    await db.flush()

    return SectionMutateResult(
        note_id=note.id,
        changed=changed,
        before_hash=before,
        after_hash=after,
    )


async def _acquire_section_lock(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    section_id: str,
) -> None:
    """PG 事务级 advisory 锁；非 PG 环境 no-op。

    事务级（``pg_advisory_xact_lock``）即可：commit / rollback 自动释放，
    不需要本内核再手工释放；跨章节天然并行。
    """
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    key = f"note_section:{project_id}:{year}:{section_id}"
    await db.execute(
        sa.text("SELECT pg_advisory_xact_lock(:ns, hashtext(:key))"),
        {"ns": _ADVISORY_NAMESPACE, "key": key},
    )


def stable_hash(value: Any) -> str:
    """稳定 hash：按 JSON canonical 比较（``sort_keys=True, ensure_ascii=False``）。

    不可 JSON 序列化的对象（如 Decimal / datetime）按 ``default=str`` 回退，
    仍保持确定性；真正不可序列化的落到 ``repr`` 兜底（过于敏感，但保证单调）。
    """
    try:
        serialized = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        serialized = repr(value)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
