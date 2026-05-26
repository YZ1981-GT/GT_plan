"""底稿索引解析校验端点

GET /api/wp-index-resolve
按 design §5.1.6 实现：<GtIndexChip> 解析校验。

解析 ref → 查 wp_index 校验存在性 → 返回 resolved 结构。

Requirements: 3.11.9（11 命名空间）
"""

from __future__ import annotations

import logging
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.procedure_models import ProcedureInstance
from app.models.workpaper_models import WpIndex

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/wp-index-resolve",
    tags=["wp-index-resolve"],
)


# ─── Types ───────────────────────────────────────────────────────────────────

VALID_NAMESPACES = [
    "wp", "sheet", "cell",
    "Note", "TB", "Adj", "Att", "EQCR", "Calc", "Sample", "Confirm",
]

# Case-insensitive lookup: lowercase → canonical namespace
NS_LOOKUP: dict[str, str] = {ns.lower(): ns for ns in VALID_NAMESPACES}

# Namespace → Layer mapping
NAMESPACE_LAYER_MAP: dict[str, int] = {
    "cell": 1,
    "sheet": 2,
    "wp": 3,
    "Note": 4,
    "TB": 4,
    "Adj": 4,
    "Att": 4,
    "EQCR": 4,
    "Calc": 4,
    "Sample": 4,
    "Confirm": 4,
}

# External module namespaces (not validated against wp_index)
EXTERNAL_NAMESPACES = {"Note", "TB", "Adj", "Att", "EQCR", "Calc", "Sample", "Confirm"}

# Regex patterns (mirror frontend parseIndexRef.ts)
STRICT_RE = re.compile(
    r"^(wp|sheet|cell|Note|TB|Adj|Att|EQCR|Calc|Sample|Confirm):(.+)$",
    re.IGNORECASE,
)
LOOSE_RE = re.compile(r"^[A-S]\d+(?:-\d+)*[A-Z]?$", re.IGNORECASE)
GT_CUSTOM_RE = re.compile(r"^GT_Custom", re.IGNORECASE)


# ─── Response schemas ────────────────────────────────────────────────────────


class ResolveResponse(BaseModel):
    exists: bool
    trimmed: bool = False
    reason: str | None = None
    empty: bool = False
    ns: str
    layer: int
    target: str


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _parse_ref(ref: str) -> tuple[str, int, str] | None:
    """Parse a ref string into (ns, layer, target) or None if invalid.

    Mirrors the frontend parseIndexRef logic.
    """
    trimmed = ref.strip()
    if not trimmed:
        return None

    # GT_Custom — not resolvable
    if GT_CUSTOM_RE.match(trimmed):
        return None

    # Strict mode: <ns>:<target>
    strict_match = STRICT_RE.match(trimmed)
    if strict_match:
        raw_ns = strict_match.group(1)
        raw_target = strict_match.group(2).strip()
        if not raw_target:
            return None
        ns = NS_LOOKUP.get(raw_ns.lower())
        if not ns:
            return None
        layer = NAMESPACE_LAYER_MAP[ns]
        return (ns, layer, raw_target)

    # Loose mode: workpaper code pattern [A-S]\d+(-\d+)*[A-Z]?
    normalized = trimmed.upper()

    # Cell reference with ! separator
    if "!" in trimmed:
        parts = trimmed.split("!")
        if len(parts) == 2:
            sheet_part = parts[0].strip().upper()
            cell_part = parts[1].strip().upper()
            if sheet_part and cell_part and LOOSE_RE.match(sheet_part):
                return ("cell", 1, f"{sheet_part}!{cell_part}")
        return None

    if LOOSE_RE.match(normalized):
        # Determine if it's a sheet ref or wp ref
        # Sheet refs: D2-1, D2-1-1, D2A (letter suffix)
        # WP refs: D2, E1, F2 (letter + digits only)
        if re.match(r"^[A-S]\d+(?:-\d+)+$", normalized, re.IGNORECASE):
            return ("sheet", 2, normalized)
        if re.match(r"^[A-S]\d+[A-Z]$", normalized, re.IGNORECASE):
            return ("sheet", 2, normalized)
        # Main workpaper code
        return ("wp", 3, normalized)

    return None


async def _check_wp_exists(
    db: AsyncSession,
    ns: str,
    target: str,
    project_id: UUID | None,
) -> tuple[bool, bool, str | None]:
    """Check if a wp/sheet/cell target exists in wp_index.

    Returns (exists, trimmed, reason).
    """
    if not project_id:
        # Without project_id, cannot validate wp_index
        return (True, False, None)

    # Determine the wp_code to look up
    if ns == "wp":
        wp_code = target.upper()
    elif ns == "sheet":
        # Sheet refs like D2-1 → wp_code is the prefix (D2)
        # Extract main wp_code: take everything before the first dash-number
        match = re.match(r"^([A-S]\d+)", target, re.IGNORECASE)
        if match:
            wp_code = match.group(1).upper()
        else:
            wp_code = target.upper()
    elif ns == "cell":
        # Cell refs like D2-1!B23 → extract sheet part → extract wp_code
        sheet_part = target.split("!")[0] if "!" in target else target
        match = re.match(r"^([A-S]\d+)", sheet_part, re.IGNORECASE)
        if match:
            wp_code = match.group(1).upper()
        else:
            wp_code = sheet_part.upper()
    else:
        return (True, False, None)

    # Query wp_index for existence
    stmt = select(WpIndex).where(
        WpIndex.project_id == project_id,
        WpIndex.wp_code == wp_code,
        WpIndex.is_deleted == False,  # noqa: E712
    )
    result = await db.execute(stmt)
    wp_index = result.scalar_one_or_none()

    if not wp_index:
        return (False, False, None)

    # Check if the workpaper has been trimmed (ProcedureInstance.status='not_applicable')
    trim_stmt = select(ProcedureInstance).where(
        ProcedureInstance.project_id == project_id,
        ProcedureInstance.wp_code == wp_code,
        ProcedureInstance.status == "not_applicable",
        ProcedureInstance.is_deleted == False,  # noqa: E712
    )
    trim_result = await db.execute(trim_stmt)
    trim_instance = trim_result.scalar_one_or_none()

    if trim_instance:
        reason = trim_instance.skip_reason
        return (True, True, reason)

    return (True, False, None)


# ─── Endpoint ────────────────────────────────────────────────────────────────


@router.get("", response_model=ResolveResponse)
async def resolve_wp_index(
    ref: str = Query(..., description="索引引用字符串（必填）"),
    project_id: UUID | None = Query(None, description="项目 ID（可选，用于校验存在性）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """解析底稿索引引用并校验存在性。

    解析 ref 字符串 → 确定命名空间和目标 → 查 wp_index 校验存在性 → 返回 resolved 结构。

    EARS:
    - WHEN ref 为合法格式 THEN 返回 resolved 结构（ns/layer/target/exists/trimmed）
    - IF ref 格式非法 THEN 返回 422
    - IF ns ∈ {Note/TB/Adj/Att/EQCR/Calc/Sample/Confirm} THEN exists=true（外部模块不校验）
    - IF ns ∈ {wp/sheet/cell} AND project_id 提供 THEN 查 wp_index 校验存在性
    - IF 底稿已裁剪（ProcedureInstance.status='not_applicable'）THEN trimmed=true + reason
    """
    parsed = _parse_ref(ref)
    if parsed is None:
        raise HTTPException(
            status_code=422,
            detail=f"无法解析索引引用: '{ref}'",
        )

    ns, layer, target = parsed

    # External module namespaces — always exists=true (not validated here)
    if ns in EXTERNAL_NAMESPACES:
        return ResolveResponse(
            exists=True,
            trimmed=False,
            reason=None,
            empty=False,
            ns=ns,
            layer=layer,
            target=target,
        )

    # wp/sheet/cell namespaces — validate against wp_index
    exists, trimmed, reason = await _check_wp_exists(db, ns, target, project_id)

    return ResolveResponse(
        exists=exists,
        trimmed=trimmed,
        reason=reason,
        empty=False,
        ns=ns,
        layer=layer,
        target=target,
    )
