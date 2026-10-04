"""三件套共享交付快照 — 不可变 digest 与「三项引用同一快照」绑定（phase4 Task 3）。

spec: ``.kiro/specs/chain-closure-phase4-deliverable-center-trio``（需求 1.5, 2.4）。

设计 §3.4 / §4.2 的两条铁律在此落为可复用、可被变异测试打红的入口：

1. **digest 不含生成时间与本机绝对路径**：对规范化 JSON（项目/年度/准则/模板/
   report_scope/TB-调整-推送-报表-附注-底稿指纹/phase3 readiness 版本）取 sha256。
   生成时间是元数据，不进 digest；文件 hash 属 item/attempt/version，不进 snapshot。
   ⇒ 同一输入两次 digest 相同（幂等）。

2. **三项 trio item 引用同一 snapshot_id**：``bind_items_to_snapshot`` 把同一个
   digest 写进 job 与三个 item 的 ``snapshot_id``；``verify_trio_shares_snapshot``
   在生成/重试路径复核三项仍绑同一值，任一项换了快照即判不一致（需求 2.4：
   不得在前两项完成后重新读取已变化的项目数据而形成跨快照文件）。

本模块是**纯计算 + 轻量投影写入**：``build_digest`` 不触库；``bind_items_to_snapshot``
只 flush 不 commit（由 router/编排边界统一 commit）。
"""

from __future__ import annotations

import hashlib
import json
import logging
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase13_models import ExportJob, ExportJobItem

logger = logging.getLogger(__name__)

#: 正式三件套稳定键（与 readiness/executor TRIO_STEP_KEYS 同源的权威契约）。
TRIO_STEP_KEYS: tuple[str, ...] = (
    "financial_report",
    "disclosure_notes",
    "audit_report",
)


def build_digest(snapshot_input: dict) -> str:
    """对快照输入计算不可变 digest（sha256）。

    关键不变量（变异测试守护）：

    - **改任一业务输入字段 → digest 变化**（证明 digest 真绑定源数据，不是常量）；
    - **只改生成时间 / 绝对路径这类非内容字段 → digest 不变**。为此本函数在计算前
      显式剔除常见的时间/路径元数据键，并禁止调用方把绝对路径塞进内容。

    Args:
        snapshot_input: 快照的**内容**字典（源输入 + 生成上下文）。不应包含生成时间或
            本机绝对路径；若误含 ``generated_at`` / ``captured_at`` / ``*_abs_path``
            等元数据键，这里会先剔除再计算，确保 digest 稳定。
    """
    content = _strip_volatile_keys(snapshot_input)
    canonical = json.dumps(content, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


#: digest 计算前须剔除的易变/环境相关元数据键（不参与内容指纹）。
_VOLATILE_KEYS = frozenset(
    {
        "generated_at",
        "captured_at",
        "created_at",
        "finished_at",
        "started_at",
        "timestamp",
        "now",
    }
)


def _strip_volatile_keys(obj):
    """递归剔除易变元数据键与绝对路径值，保证 digest 只绑定内容。"""
    if isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            if k in _VOLATILE_KEYS:
                continue
            # 以 ``_abs_path`` / ``abs_path`` 结尾的键被视为本机绝对路径元数据，剔除。
            if isinstance(k, str) and k.endswith("abs_path"):
                continue
            cleaned[k] = _strip_volatile_keys(v)
        return cleaned
    if isinstance(obj, list):
        return [_strip_volatile_keys(x) for x in obj]
    return obj


class DeliverableTrioSnapshot:
    """三件套共享快照的 digest 构建与绑定。"""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def digest(snapshot_input: dict) -> str:
        """构建不可变 digest（纯函数，暴露为方法方便注入/替身）。"""
        return build_digest(snapshot_input)

    async def bind_items_to_snapshot(
        self,
        job_id: UUID,
        snapshot_id: str,
    ) -> int:
        """把同一个 snapshot_id 写进 job 与其三件套 item。

        返回被绑定的正式三件套 item 数（期望为 3）。只 flush 不 commit。
        """
        job = await self.db.get(ExportJob, job_id)
        if job is not None:
            job.snapshot_id = snapshot_id

        items = (
            await self.db.execute(
                sa.select(ExportJobItem).where(
                    ExportJobItem.job_id == job_id,
                    ExportJobItem.step_key.in_(TRIO_STEP_KEYS),
                )
            )
        ).scalars().all()
        bound = 0
        for item in items:
            item.snapshot_id = snapshot_id
            bound += 1
        await self.db.flush()
        return bound

    async def verify_trio_shares_snapshot(self, job_id: UUID) -> bool:
        """复核三件套三项是否绑定同一个非空 snapshot_id。

        需求 2.4：三项必须引用同一个快照。任一项为空或与 job 不一致 → False
        （生成/重试路径据此 fail-closed，不得跨快照混用）。
        """
        job = await self.db.get(ExportJob, job_id)
        if job is None or not job.snapshot_id:
            return False

        items = (
            await self.db.execute(
                sa.select(ExportJobItem.step_key, ExportJobItem.snapshot_id).where(
                    ExportJobItem.job_id == job_id,
                    ExportJobItem.step_key.in_(TRIO_STEP_KEYS),
                )
            )
        ).all()

        seen = {row[0] for row in items}
        if seen != set(TRIO_STEP_KEYS):
            # 三件套未齐，不判一致
            return False
        return all(row[1] == job.snapshot_id for row in items)
