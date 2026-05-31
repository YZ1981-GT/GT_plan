"""E1 spec Sprint 1 Task 1.19-1.21: 用户自定义公式编辑器后端

提供 3 个端点支持手动公式编辑器:
- GET    /api/workpapers/{wp_id}/user-formulas     列出用户自定义公式
- PUT    /api/workpapers/{wp_id}/user-formulas     批量更新用户自定义公式
- DELETE /api/workpapers/{wp_id}/user-formulas/{cell_key}  恢复某 cell 到预设公式
- POST   /api/workpapers/{wp_id}/validate-formula  公式语法校验 + 预览

数据存储: WorkingPaper.parsed_data["user_formulas"] = {
    "{sheet_name}!{cell_ref}": {
        "formula": "=TB('1001','期末余额')",
        "formula_type": "TB",
        "edited_by": "uuid",
        "edited_at": "iso datetime",
        "original_preset": "..."  # 覆盖预设时记录原始,供"↺ 恢复"使用
    }
}

执行优先级 (Task 1.20):
    user_formulas (覆盖) > prefill_formula_mapping (预设) > 模板内置公式
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db
from app.models.core import User
from app.models.workpaper_models import WorkingPaper
from app.services.prefill_engine import (
    _FORMULA_RE,
    _FORMULA_RESOLVERS,
    _parse_args,
    resolve_extended_formula,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/workpapers/{wp_id}",
    tags=["workpaper-user-formulas"],
)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class UserFormulaItem(BaseModel):
    cell_key: str = Field(..., description="格式 sheet_name!cell_ref")
    formula: str
    formula_type: str | None = None
    edited_by: str | None = None
    edited_at: str | None = None
    original_preset: str | None = None


class BatchUserFormulasRequest(BaseModel):
    formulas: dict[str, str] = Field(
        ..., description="cell_key -> formula 文本(以 = 开头),空字符串=删除该自定义"
    )


class ValidateFormulaRequest(BaseModel):
    formula: str = Field(..., description="待校验的公式,例: =TB('1001','期末余额')")
    project_id: UUID | None = Field(None, description="预览执行需要 project_id")
    year: int | None = Field(None, description="预览执行需要 year")
    preview: bool = Field(False, description="是否实际执行预览(需要 project_id+year)")


class ValidateFormulaResponse(BaseModel):
    valid: bool
    formula_type: str | None = None
    args: list[str] | None = None
    error: str | None = None
    preview_value: float | str | None = None


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


_CELL_KEY_RE = re.compile(r"^[^!]+![A-Z]+\d+$")
_SUPPORTED_TYPES = set(_FORMULA_RESOLVERS.keys()) | {"TB", "SUM_TB"}


def _parse_formula_or_raise(formula: str) -> tuple[str, list[str]]:
    """提取公式类型 + 参数列表;失败抛 HTTPException 422"""
    s = (formula or "").strip()
    if not s.startswith("="):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error_code": "FORMULA_NOT_EQUALS", "message": "公式必须以 = 开头"},
        )
    m = _FORMULA_RE.search(s)
    if not m:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "FORMULA_TYPE_UNKNOWN",
                "message": f"未识别的公式类型,支持: {sorted(_SUPPORTED_TYPES)}",
            },
        )
    ftype = m.group(1).upper()
    args = _parse_args(m.group(2).strip())
    if ftype not in _SUPPORTED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "FORMULA_TYPE_UNSUPPORTED",
                "message": f"公式类型 {ftype} 暂不支持",
            },
        )
    # 参数数量基本校验
    arg_min = {
        "TB": 2,
        "SUM_TB": 2,
        "WP": 3,
        "PREV": 2,
        "ADJ": 2,
        "AUX": 4,
        "LEDGER": 3,
        "LEDGER_DETAIL": 1,
        "COUNT_LEDGER": 1,
        "NOTE": 3,
    }.get(ftype, 1)
    if len(args) < arg_min:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "FORMULA_ARGS_INSUFFICIENT",
                "message": f"{ftype} 至少需要 {arg_min} 个参数,实际 {len(args)}",
            },
        )
    return ftype, args


async def _load_wp(db: AsyncSession, wp_id: UUID) -> WorkingPaper:
    wp = (await db.execute(
        sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
    )).scalar_one_or_none()
    if wp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": "WP_NOT_FOUND", "message": f"底稿 {wp_id} 不存在"},
        )
    return wp


# ---------------------------------------------------------------------------
# 端点 1: 列出用户自定义公式
# ---------------------------------------------------------------------------


@router.get("/user-formulas")
async def list_user_formulas(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    wp = await _load_wp(db, wp_id)
    user_formulas = (wp.parsed_data or {}).get("user_formulas", {}) or {}
    return {
        "wp_id": str(wp_id),
        "count": len(user_formulas),
        "user_formulas": user_formulas,
    }


# ---------------------------------------------------------------------------
# 端点 2: 批量更新用户自定义公式
# ---------------------------------------------------------------------------


@router.put("/user-formulas")
async def update_user_formulas(
    wp_id: UUID,
    payload: BatchUserFormulasRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    wp = await _load_wp(db, wp_id)

    # 校验每条公式
    for cell_key, formula in payload.formulas.items():
        if not _CELL_KEY_RE.match(cell_key):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error_code": "CELL_KEY_INVALID",
                    "message": f"cell_key 格式应为 'sheet!A1':{cell_key}",
                },
            )
        if formula:  # 空字符串 = 删除
            _parse_formula_or_raise(formula)

    parsed_data = dict(wp.parsed_data or {})
    user_formulas: dict[str, dict] = dict(parsed_data.get("user_formulas") or {})

    # 加载预设公式映射用于 original_preset 备份(从 prefill_formula_mapping.json)
    preset_lookup: dict[str, str] = {}
    try:
        from pathlib import Path
        import json
        fp = Path(__file__).resolve().parents[2] / "data" / "prefill_formula_mapping.json"
        if fp.exists():
            with open(fp, "r", encoding="utf-8") as f:
                preset_data = json.load(f)
            # 这里 cell_key (sheet!cell) 在 mapping json 里通常是 cell_ref + sheet 不是组合 key,
            # 简化:仅匹配相同 sheet+cell 的预设
            for ent in preset_data.get("mappings", []):
                sheet_n = ent.get("sheet", "")
                for c in ent.get("cells", []):
                    cr = c.get("cell_ref", "")
                    preset_lookup[f"{sheet_n}!{cr}"] = c.get("formula", "")
    except Exception as e:
        logger.warning("preset_lookup 加载失败,original_preset 将留空: %s", e)

    now_iso = datetime.now(timezone.utc).isoformat()
    updated = 0
    deleted = 0
    # 记录变更前的旧公式（审计留痕用）
    _old_formulas: dict[str, str] = {}
    for cell_key, formula in payload.formulas.items():
        existing_entry = user_formulas.get(cell_key) or {}
        _old_formulas[cell_key] = existing_entry.get("formula", "")

    for cell_key, formula in payload.formulas.items():
        if not formula:
            if cell_key in user_formulas:
                del user_formulas[cell_key]
                deleted += 1
            continue

        # 解析公式类型供前端展示
        ftype, _args = _parse_formula_or_raise(formula)
        existing = user_formulas.get(cell_key) or {}
        original = (
            existing.get("original_preset")
            or preset_lookup.get(cell_key)
            or None
        )
        user_formulas[cell_key] = {
            "formula": formula,
            "formula_type": ftype,
            "edited_by": str(user.id) if hasattr(user, "id") else None,
            "edited_at": now_iso,
            "original_preset": original,
        }
        updated += 1

    parsed_data["user_formulas"] = user_formulas
    wp.parsed_data = parsed_data
    # 强制 SQLAlchemy 检测 JSONB 修改(否则不脏)
    sa.orm.attributes.flag_modified(wp, "parsed_data")

    # ── 底稿公式变更走哈希链 formula.changed 留痕（需求 8.4 / Q5）──
    if updated > 0 or deleted > 0:
        try:
            from app.services.audit_log_helper import append_audit_log

            for cell_key, formula in payload.formulas.items():
                old_formula = _old_formulas.get(cell_key, "")
                # 跳过无实际变更的条目
                if formula == old_formula:
                    continue
                action = "delete" if not formula else "update"
                await append_audit_log(db, {
                    "user_id": user.id if hasattr(user, "id") else None,
                    "project_id": wp.project_id,
                    "action": "formula.changed",
                    "resource_type": "workpaper",
                    "resource_id": cell_key,
                    "details": {
                        "event_type": "formula_changed",
                        "module": "workpaper",
                        "row_code": cell_key,
                        "action": action,
                        "old_formula": old_formula,
                        "new_formula": formula,
                        "result_value": "",
                    },
                })
        except Exception as e:
            # 审计写入失败仅 warning，不影响公式保存
            logger.warning("底稿公式审计留痕写入失败: %s", e)

    await db.commit()

    return {
        "wp_id": str(wp_id),
        "updated": updated,
        "deleted": deleted,
        "total": len(user_formulas),
    }


# ---------------------------------------------------------------------------
# 端点 3: 删除某 cell 自定义公式(恢复预设)
# ---------------------------------------------------------------------------


@router.delete("/user-formulas/{cell_key:path}")
async def restore_preset_formula(
    wp_id: UUID,
    cell_key: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    wp = await _load_wp(db, wp_id)
    parsed_data = dict(wp.parsed_data or {})
    user_formulas: dict[str, dict] = dict(parsed_data.get("user_formulas") or {})
    if cell_key not in user_formulas:
        return {"wp_id": str(wp_id), "status": "noop", "cell_key": cell_key}

    removed = user_formulas.pop(cell_key)
    parsed_data["user_formulas"] = user_formulas
    wp.parsed_data = parsed_data
    sa.orm.attributes.flag_modified(wp, "parsed_data")

    # ── 底稿公式恢复预设走哈希链 formula.changed 留痕 ──
    try:
        from app.services.audit_log_helper import append_audit_log

        await append_audit_log(db, {
            "user_id": _user.id if hasattr(_user, "id") else None,
            "project_id": wp.project_id,
            "action": "formula.changed",
            "resource_type": "workpaper",
            "resource_id": cell_key,
            "details": {
                "event_type": "formula_changed",
                "module": "workpaper",
                "row_code": cell_key,
                "action": "restore_preset",
                "old_formula": removed.get("formula", ""),
                "new_formula": removed.get("original_preset", ""),
                "result_value": "",
            },
        })
    except Exception as e:
        logger.warning("底稿公式审计留痕写入失败: %s", e)

    await db.commit()

    return {
        "wp_id": str(wp_id),
        "status": "restored",
        "cell_key": cell_key,
        "restored_to_preset": removed.get("original_preset"),
    }


# ---------------------------------------------------------------------------
# 端点 4: 公式语法校验 + 预览
# ---------------------------------------------------------------------------


@router.post("/validate-formula", response_model=ValidateFormulaResponse)
async def validate_formula(
    wp_id: UUID,
    payload: ValidateFormulaRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> ValidateFormulaResponse:
    """校验公式语法并可选预览结果

    锚定 tasks 1.21 / requirements F2.3 手动公式编辑器后端支持。
    """
    try:
        ftype, args = _parse_formula_or_raise(payload.formula)
    except HTTPException as e:
        # 转换为 200 + valid=False 让前端做友好显示(非 422 表单错误)
        det = e.detail if isinstance(e.detail, dict) else {"message": str(e.detail)}
        return ValidateFormulaResponse(
            valid=False,
            error=det.get("message") or det.get("error_code") or "公式语法错误",
        )

    response = ValidateFormulaResponse(valid=True, formula_type=ftype, args=args)

    if not payload.preview:
        return response

    # 预览执行
    if payload.project_id is None or payload.year is None:
        response.error = "预览需要 project_id + year"
        return response

    try:
        # TB / SUM_TB 走 formula_engine,其他走 prefill_engine extended resolver
        if ftype in ("TB", "SUM_TB"):
            from app.services.formula_engine import FormulaEngine
            engine = FormulaEngine()
            params: dict[str, Any] = {}
            if ftype == "TB" and len(args) >= 2:
                params = {"account_code": args[0], "column_name": args[1]}
            elif ftype == "SUM_TB" and len(args) >= 2:
                params = {"account_range": args[0], "column_name": args[1]}
            result = await engine.execute(
                db=db,
                project_id=payload.project_id,
                year=payload.year,
                formula_type=ftype,
                params=params,
            )
            if hasattr(result, "message"):
                response.preview_value = f"[ERROR] {result.message}"
            else:
                response.preview_value = float(result) if result is not None else None
        else:
            # 其他类型用 resolve_extended_formula
            raw_args = _FORMULA_RE.search(payload.formula).group(2)
            val = await resolve_extended_formula(
                db, payload.project_id, payload.year, ftype, raw_args
            )
            response.preview_value = float(val) if val is not None else None
    except Exception as e:
        response.error = f"预览失败: {e}"
        logger.warning("validate-formula preview failed: %s", e, exc_info=True)

    return response
