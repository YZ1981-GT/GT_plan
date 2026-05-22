"""跨循环断裂清单服务

Requirements: 2.2, 2.3, 2.6

读取 cross_wp_references（400 条）引用定义，运行时 JOIN working_paper + wp_index
判断 target 是否断裂：
- target_missing：项目内无对应 wp_code
- target_stale：wp_code 存在但 prefill_stale=true

按 severity 降序排列（blocking > required > warning > recommended > info，5 级），
计算统计摘要（各 severity 级别条数）。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WorkingPaper, WpIndex

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Response Models
# ---------------------------------------------------------------------------

SEVERITY_ORDER: dict[str, int] = {
    "blocking": 0,
    "required": 1,
    "warning": 2,
    "recommended": 3,
    "info": 4,
}


class BreakageRecord(BaseModel):
    ref_id: str
    source_wp_code: str
    target_wp_code: str
    severity: Literal["blocking", "required", "warning", "recommended", "info"]
    reason: Literal["target_missing", "target_stale"]
    last_checked_at: datetime


class BreakageSummary(BaseModel):
    blocking: int = 0
    required: int = 0
    warning: int = 0
    recommended: int = 0
    info: int = 0


class BreakageListResponse(BaseModel):
    items: list[BreakageRecord]
    summary: BreakageSummary


# ---------------------------------------------------------------------------
# CWR File Loading
# ---------------------------------------------------------------------------

_CWR_FILE_DEFAULT = (
    Path(__file__).resolve().parents[2] / "data" / "cross_wp_references.json"
)


def _resolve_cwr_path() -> Path:
    """返回 cross_wp_references.json 文件路径。

    覆盖优先级：
    1. 环境变量 CROSS_WP_REF_PATH
    2. backend/data/cross_wp_references.json (默认)
    """
    env_path = os.environ.get("CROSS_WP_REF_PATH")
    if env_path:
        return Path(env_path)
    return _CWR_FILE_DEFAULT


def load_cwr_references() -> list[dict]:
    """加载 cross_wp_references.json 的 references 数组。

    加载失败时抛出异常（由调用方处理）。
    """
    path = _resolve_cwr_path()
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    refs = data.get("references")
    if not isinstance(refs, list):
        raise ValueError("references field missing or not a list")
    return refs


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


async def get_cross_cycle_breakage(
    db: AsyncSession,
    project_id: "str | __import__('uuid').UUID",
) -> BreakageListResponse:
    """检测跨循环断裂清单。

    流程：
    1. 加载 CWR JSON
    2. 查询项目内所有 wp_code 集合
    3. 查询项目内所有 prefill_stale=True 的 wp_code 集合
    4. 遍历 CWR 每条 reference 的 targets，判断断裂
    5. 按 severity 降序排序
    6. 计算统计摘要

    性能目标：≤ 1s（400 条 CWR 规模）。
    """
    from uuid import UUID

    if isinstance(project_id, str):
        project_id = UUID(project_id)

    # Step 1: 加载 CWR
    references = load_cwr_references()

    # Step 2: 查询项目内所有存在的 wp_code 集合
    existing_stmt = (
        select(WpIndex.wp_code)
        .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted.is_(False),
        )
    )
    existing_result = await db.execute(existing_stmt)
    existing_wp_codes: set[str] = {row[0] for row in existing_result.all() if row[0]}

    # Step 3: 查询项目内所有 prefill_stale=True 的 wp_code 集合
    stale_stmt = (
        select(WpIndex.wp_code)
        .join(WorkingPaper, WorkingPaper.wp_index_id == WpIndex.id)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted.is_(False),
            WorkingPaper.prefill_stale.is_(True),
        )
    )
    stale_result = await db.execute(stale_stmt)
    stale_wp_codes: set[str] = {row[0] for row in stale_result.all() if row[0]}

    # Step 4: 遍历 CWR，检测断裂
    now = datetime.now(timezone.utc)
    items: list[BreakageRecord] = []

    for ref in references:
        ref_id = ref.get("ref_id", "")
        source_wp = ref.get("source_wp", "")
        severity = ref.get("severity", "info")
        targets = ref.get("targets", [])

        # 确保 severity 是有效值
        if severity not in SEVERITY_ORDER:
            severity = "info"

        for target in targets:
            # 跳过 cross_module 类型的 target（无 wp_code）
            target_wp_code = target.get("wp_code")
            if not target_wp_code:
                continue

            # 判断断裂原因
            reason: Literal["target_missing", "target_stale"] | None = None

            if target_wp_code not in existing_wp_codes:
                reason = "target_missing"
            elif target_wp_code in stale_wp_codes:
                reason = "target_stale"

            if reason is not None:
                items.append(
                    BreakageRecord(
                        ref_id=ref_id,
                        source_wp_code=source_wp,
                        target_wp_code=target_wp_code,
                        severity=severity,
                        reason=reason,
                        last_checked_at=now,
                    )
                )

    # Step 5: 按 severity 降序排序，同 severity 内按 last_checked_at 降序
    items.sort(key=lambda item: (SEVERITY_ORDER.get(item.severity, 4), item.ref_id))

    # Step 6: 计算统计摘要
    summary = BreakageSummary()
    for item in items:
        if item.severity == "blocking":
            summary.blocking += 1
        elif item.severity == "required":
            summary.required += 1
        elif item.severity == "warning":
            summary.warning += 1
        elif item.severity == "recommended":
            summary.recommended += 1
        elif item.severity == "info":
            summary.info += 1

    return BreakageListResponse(items=items, summary=summary)
