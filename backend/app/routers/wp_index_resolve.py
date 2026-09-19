"""底稿索引解析校验端点

GET /api/wp-index-resolve
按 design §5.1.6 实现：<GtIndexChip> 解析校验。

M1: 转发至 ACNR 统一 resolve 出口（R13.2, R13.4, R13.5）。
- 内部命名空间 (wp/sheet/cell): 调 ACNR full_resolve → 返回 exists/trimmed/reason
- 外部命名空间 (Note/TB/Adj/Att/EQCR/Calc/Sample/Confirm): exists=true（不校验）
- 转发失败: 返回错误，不回退旧解析逻辑（R13.5）

Requirements: 3.11.9（11 命名空间）, 13.1, 13.2, 13.4, 13.5
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
from app.services.acnr.grammar import STANDARD_WP_CODE_RE, STANDARD_WP_CODE_RE_STR
from app.services.acnr.resolver import full_resolve, resolve_instance

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
# Loose mode pattern: 基于 STANDARD_WP_CODE_RE (^[A-S]\d) 扩展完整底稿码匹配
# 格式: [A-S]\d+(-\d+)*[A-Z]? (如 D2, D2-1, A1-17, D2-1A)
LOOSE_RE = re.compile(
    STANDARD_WP_CODE_RE_STR + r"+(?:-\d+)*[A-Z]?$", re.IGNORECASE
)
# 提取 parent_wp_code 的模式（如 D2-2 → D2）：基于 STANDARD_WP_CODE_RE
_PARENT_WP_CODE_RE = re.compile(
    r"(" + STANDARD_WP_CODE_RE_STR.lstrip("^") + r"+)", re.IGNORECASE
)
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
    wp_id: str | None = None


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

    # Loose mode: workpaper code pattern (STANDARD_WP_CODE_RE + suffixes)
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
        # 所有松散匹配的底稿编码统一作 wp 引用（Layer 3）。
        # A2-2/D2-1/A1-17 等在致同体系中都是独立底稿编号，不是同底稿内的 sheet。
        return ("wp", 3, normalized)

    return None


# ─── Endpoint ────────────────────────────────────────────────────────────────


@router.get("", response_model=ResolveResponse)
async def resolve_wp_index(
    ref: str = Query(..., description="索引引用字符串（必填）"),
    project_id: UUID | None = Query(None, description="项目 ID（可选，用于校验存在性）"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """解析底稿索引引用并校验存在性 — 转发至 ACNR 统一 resolve 出口。

    M1 转发逻辑（R13.2, R13.4, R13.5）：
    - 解析 ref → 确定命名空间和目标
    - 外部命名空间 → exists=true（不校验物理格）
    - 内部命名空间 (wp/sheet/cell) → 转发至 ACNR full_resolve + resolve_instance
    - 转发失败 → 返回错误，**不回退旧解析逻辑**（R13.5）
    - 一次查询返回 exists / trimmed / reason（R13.4）
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

    # ─── 内部命名空间 (wp/sheet/cell) → 转发至 ACNR（R13.2）──────────────
    try:
        # 构造 index_ref 格式传入 ACNR full_resolve
        index_ref = f"{ns}:{target}"
        resolve_result = await full_resolve(
            index_ref=index_ref,
            project_id=str(project_id) if project_id else None,
            db=db if project_id else None,
        )

        # 从 ACNR resolve 结果判定 exists
        exists = resolve_result.found

        # 获取 wp_id（R13.1: resolve_instance 是唯一 wp_id 出口）
        wp_id: str | None = None
        trimmed = False
        reason: str | None = None

        if exists and project_id:
            # 确定 parent_wp_code 和 sheet_code 用于 resolve_instance
            parent_wp_code, sheet_code = _extract_parent_and_sheet(ns, target)
            if parent_wp_code and sheet_code:
                instance_result = await resolve_instance(
                    db=db,
                    project_id=project_id,
                    parent_wp_code=parent_wp_code,
                    sheet_code=sheet_code,
                )
                if instance_result.found:
                    wp_id = str(instance_result.wp_id) if instance_result.wp_id else None
                else:
                    # resolve_instance 失败不影响 exists 状态
                    pass

            # 检查裁剪状态（trimmed / reason）
            trimmed, reason = await _check_trimmed(db, project_id, ns, target)
        elif not project_id:
            # 无 project_id 时无法校验实例存在性，视为 exists=True（兼容旧行为）
            exists = True
        elif exists:
            wp_id = resolve_result.wp_id

        return ResolveResponse(
            exists=exists,
            trimmed=trimmed,
            reason=reason,
            empty=False,
            ns=ns,
            layer=layer,
            target=target,
            wp_id=wp_id,
        )

    except Exception as e:
        # R13.5: 转发失败返回错误，**不回退旧逻辑**
        logger.error("ACNR 转发失败 ref=%s: %s", ref, e, exc_info=True)
        raise HTTPException(
            status_code=502,
            detail=f"ACNR 解析服务转发失败: {e!s}",
        ) from e


# ─── ACNR Forwarding Helpers (R13.2) ─────────────────────────────────────────


def _extract_parent_and_sheet(ns: str, target: str) -> tuple[str | None, str | None]:
    """从命名空间和 target 提取 parent_wp_code 和 sheet_code。

    wp:D2 → (D2, D2)  # wp_code 即 sheet_code
    wp:D2-2 → (D2, D2-2)
    sheet:D2-2 → (D2, D2-2)
    cell:D2-2!E100 → (D2, D2-2)
    """
    if ns == "cell" and "!" in target:
        sheet_code = target.split("!")[0].strip().upper()
    else:
        sheet_code = target.strip().upper()

    # 提取 parent_wp_code（如 D2-2 → D2）
    match = _PARENT_WP_CODE_RE.match(sheet_code)
    if match:
        parent_wp_code = match.group(1).upper()
    else:
        parent_wp_code = sheet_code

    return (parent_wp_code, sheet_code)


async def _check_trimmed(
    db: AsyncSession,
    project_id: UUID,
    ns: str,
    target: str,
) -> tuple[bool, str | None]:
    """检查底稿裁剪状态（ProcedureInstance.status='not_applicable'）。

    返回 (trimmed, reason)。
    """
    # 确定 wp_code
    if ns == "wp":
        wp_code = target.upper()
    elif ns == "sheet":
        wp_code = target.upper()
    elif ns == "cell":
        sheet_part = target.split("!")[0] if "!" in target else target
        wp_code = sheet_part.upper()
    else:
        return (False, None)

    try:
        trim_stmt = select(ProcedureInstance).where(
            ProcedureInstance.project_id == project_id,
            ProcedureInstance.wp_code == wp_code,
            ProcedureInstance.status == "not_applicable",
            ProcedureInstance.is_deleted == False,  # noqa: E712
        )
        trim_result = await db.execute(trim_stmt)
        trim_instance = trim_result.scalar_one_or_none()

        if trim_instance:
            return (True, trim_instance.skip_reason)
    except Exception as e:
        logger.warning("检查裁剪状态失败 wp_code=%s: %s", wp_code, e)

    return (False, None)
