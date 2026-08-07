"""E1 spec Sprint 1 Task 1.19-1.21: 用户自定义公式编辑器后端

提供 3 个端点支持手动公式编辑器:
- GET    /api/workpapers/{wp_id}/user-formulas     列出用户自定义公式
- PUT    /api/workpapers/{wp_id}/user-formulas     批量更新用户自定义公式
- DELETE /api/workpapers/{wp_id}/user-formulas/{cell_key}  恢复某 cell 到预设公式
- POST   /api/workpapers/{wp_id}/validate-formula  公式语法校验 + 预览

数据存储（**已于 formula-management-runtime-closure Wave 3 收敛**）:

    权威存储 = `wp_formula` 表（`formula_source='custom'`），经
    `wp_formula_service.save()` upsert，键 `(wp_id, sheet_name, target_cell)`。

    🔴 **为什么收敛**：改造前用户公式只落
    ``WorkingPaper.parsed_data["user_formulas"]``，而运行时求值器
    `FormulaRuntimeCoordinator._load_formulas` 只 ``select(WpFormula)``
    ⇒ 用户在公式管理里保存的公式**永远不会被求值**（两套互不可见的存储）。
    2026-08-06 实测两侧都是 0 行，故收敛零迁移压力。

    遗留兼容：GET 仍读时合并 ``parsed_data['user_formulas']``（优先级低于表），
    DELETE 会一并清掉遗留键。
    该兼容分支由 `test_user_formula_storage_convergence` 守卫钉死 ——
    全库 0 行时它是纯保险，删掉后若某环境有历史数据会**静默丢失**。

    🔴 **PUT 仍写 `parsed_data`，但只为 ``original_preset`` 溯源**
    （spec Task 17 修，2026-08-07）：``WpFormula`` **没有 ``original_preset`` 列**，
    而 ``restore_preset_formula`` 的 ``restored_to_preset`` 与 GET 的
    ``original_preset`` 都从遗留键取 ⇒ 一度「PUT 不写 parsed_data」导致
    新保存公式的「恢复预设」恒返回 ``None``（属性测试 P29 打红暴露）。
    公式**本体**仍以表为唯一权威（运行时只读该表），故不构成双真源。

对外响应形状保持不变（``user_formulas`` 为 ``cell_key -> {...}`` dict），
前端零改动。其中 ``formula_type`` 仍是**函数名**（TB/WP/…），与
``wp_formula.formula_type`` 的三类型（auto_calc/logic_check/reasonability）
是两个不同维度，见 ``USER_FORMULA_TYPE``。

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
from app.models.workpaper_models import WorkingPaper, WpFormula
from app.services.wp_formula_service import wp_formula_service
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

#: 用户公式在 `wp_formula` 表里的来源标识。
#:
#: 🔴 取值域由 `wp_formula_service._VALID_FORMULA_SOURCES` 定义 =
#: ``("preset", "custom", "reference")`` —— **没有 `"user"`**（spec design 首版写的
#: `formula_source='user'` 会被 `save()` 以 `invalid_formula_source` 拒绝写库）。
#: 用户手工编辑的公式语义上就是 "custom"。
USER_FORMULA_SOURCE = "custom"

#: 用户公式的三类型（`wp_formula.formula_type` 取值域是
#: ``auto_calc`` / ``logic_check`` / ``reasonability``）。
#:
#: 🔴 **注意与本模块 `formula_type` 字段的语义冲突**：本模块 `parsed_data` 里的
#: `formula_type` 存的是**函数名**（`TB`/`WP`/`AUX`…，见 `_parse_formula_or_raise`），
#: 与 `wp_formula.formula_type` 的三类型是**两个不同维度**。收敛时函数名继续留在
#: `parsed_data` 侧的响应形状里（前端零改动红线），落 `wp_formula` 一律用 `auto_calc`。
USER_FORMULA_TYPE = "auto_calc"


def _safe_function_name(expression: str | None) -> str | None:
    """从表达式提取函数名（``TB``/``WP``/…），**不抛异常**。

    读路径专用：`_parse_formula_or_raise` 会抛 422，而 GET 读回历史数据时
    即便表达式不合法也不该让整个列表 500 —— 取不出就返 ``None``。
    """
    if not expression:
        return None
    m = _FORMULA_RE.search(expression.strip())
    return m.group(1).upper() if m else None


def split_cell_key(cell_key: str) -> tuple[str, str]:
    """``sheet!A1`` → ``("sheet", "A1")``。

    与 :func:`join_cell_key` 互为逆运算（Property 11 往返无损）。
    sheet 名本身可含空格与中文括号，但**不含 `!`**（`_CELL_KEY_RE` 已保证）。
    """
    sheet, _, cell = cell_key.partition("!")
    return sheet, cell


def join_cell_key(sheet_name: str, target_cell: str) -> str:
    """``("sheet", "A1")`` → ``sheet!A1``（:func:`split_cell_key` 的逆）。"""
    return f"{sheet_name}!{target_cell}"


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

    # ── 读时合并：`wp_formula` 表（权威）∪ `parsed_data` 遗留键（兼容，优先级低）──
    #
    # 🔴 **遗留分支必须保留且有守卫钉死**：全库实测 `parsed_data ? 'user_formulas'`
    # 为 0 行，故它现在是纯保险；但删掉后若某环境存有历史数据就会**静默丢失**。
    # 守卫见 `test_user_formula_storage_convergence`。
    legacy: dict[str, dict] = dict((wp.parsed_data or {}).get("user_formulas") or {})

    rows = await wp_formula_service.list_by_wp(
        db, wp_id, project_id=wp.project_id
    )
    merged: dict[str, dict] = dict(legacy)
    for row in rows:
        if row.formula_source != USER_FORMULA_SOURCE:
            # 只把用户来源的公式呈现为「用户自定义公式」；preset/reference 不混入
            continue
        cell_key = join_cell_key(row.sheet_name, row.target_cell)
        prior = legacy.get(cell_key) or {}
        merged[cell_key] = {
            "formula": row.expression,
            # 响应形状不变：`formula_type` 仍是**函数名**（TB/WP/…），由表达式解析得出，
            # 不是 `wp_formula.formula_type` 的三类型（见 USER_FORMULA_TYPE 注释）。
            "formula_type": _safe_function_name(row.expression)
            or prior.get("formula_type"),
            "edited_by": str(row.created_by) if row.created_by else prior.get("edited_by"),
            "edited_at": row.updated_at.isoformat() if row.updated_at else prior.get("edited_at"),
            "original_preset": prior.get("original_preset"),
        }

    return {
        "wp_id": str(wp_id),
        "count": len(merged),
        "user_formulas": merged,
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

    # P2-2: 公式保存前校验地址有效性（悬空引用拒绝保存）
    # 同一次查询的 year/template_type 供下方 `wp_formula_service.save` 复用，
    # 避免二次查库（save 内部还会再做一次 ACNR 校验，属既有语义不动）。
    _resolved_year: int = 0
    _resolved_template_type: str = "soe"
    from app.models.core import Project  # noqa: PLC0415 - 与既有写法一致

    _project = (await db.execute(
        sa.select(Project).where(Project.id == wp.project_id)
    )).scalar_one_or_none()
    if _project is not None:
        # 🔴 年度真源是 `projects.audit_year`，**不是** `audit_period_end`
        #    （spec formula-management-runtime-closure Task 18，2026-08-07 真实库实测）：
        #    全库 8 个项目 `audit_period_end` **全部为 NULL** 而 `audit_year` 均已填
        #    （2025/2024）⇒ 原写法对每个项目都算出 `year=0` ⇒
        #    `validate_refs_via_acnr` → tb 域按 `TrialBalance.year == 0` 查得**空集**
        #    ⇒ 任何含 `TB()` 的用户公式都被判悬空引用、422 拒绝保存
        #    （报错文案「引用地址在当前项目中不存在」指向数据缺失，实为年度取错 = 误导）。
        #    平台其余 30+ 处一律用 `audit_year`（如 `_f1_import_export.py`
        #    的 `year = int(wp_row.audit_year or 0)`），本文件是唯一的例外。
        #    保留 `audit_period_end` 作次选，兼容将来只填期间不填年度的数据。
        _resolved_year = int(
            _project.audit_year
            or (_project.audit_period_end.year if _project.audit_period_end else 0)
        )
        _resolved_template_type = _project.template_type or "soe"

    non_empty_formulas = [f for f in payload.formulas.values() if f]
    if non_empty_formulas:
        from app.services.acnr.formula_validation import validate_refs_via_acnr

        project = _project
        if project:
            year = _resolved_year
            template_type = _resolved_template_type
            all_issues: list[dict] = []
            for formula in non_empty_formulas:
                issues = await validate_refs_via_acnr(
                    db, str(wp.project_id), year, formula, template_type
                )
                all_issues.extend(issues)
            if all_issues:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={
                        "error_code": "FORMULA_DANGLING_REFS",
                        "message": "公式含悬空引用，拒绝保存",
                        "issues": all_issues,
                    },
                )

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

    # ── 存储收敛：写 `wp_formula` 表（运行时唯一可见的公式定义存储）──
    #
    # 🔴 改造前用户公式**只**落 `working_paper.parsed_data['user_formulas']`，而
    # `FormulaRuntimeCoordinator._load_formulas` 只 `select(WpFormula)` ⇒
    # 用户在公式管理里保存的公式**永远不会被运行时求值**（两套互不可见的存储）。
    # 实测两侧都是 0 行 ⇒ 现在收敛零迁移压力，越晚越贵。
    #
    # 复用既有 `wp_formula_service.save()`（已具备 upsert / definition_version 递增 /
    # definition_hash / lifecycle_state / 悬空引用校验 / 归属校验），**不新写 upsert**。
    save_issues: list[dict] = []
    for cell_key, formula in payload.formulas.items():
        sheet_name, target_cell = split_cell_key(cell_key)
        if not formula:
            # 空串 = 删除：清掉 `wp_formula` 里的对应行
            existing_row = (
                await db.execute(
                    sa.select(WpFormula).where(
                        WpFormula.wp_id == wp_id,
                        WpFormula.sheet_name == sheet_name,
                        WpFormula.target_cell == target_cell,
                    )
                )
            ).scalar_one_or_none()
            if existing_row is not None:
                await db.delete(existing_row)
            continue

        saved, issues = await wp_formula_service.save(
            db,
            project_id=wp.project_id,
            wp_id=wp_id,
            sheet_name=sheet_name,
            target_cell=target_cell,
            expression=formula,
            year=_resolved_year,
            template_type=_resolved_template_type,
            description="用户自定义公式",
            created_by=getattr(user, "id", None),
            # 🔴 函数名（TB/WP/…）不是三类型，落表一律 auto_calc；见 USER_FORMULA_TYPE
            formula_type=USER_FORMULA_TYPE,
            formula_source=USER_FORMULA_SOURCE,
        )
        if saved is None:
            save_issues.extend(issues or [])

    if save_issues:
        # 与既有 422 语义一致：整批拒绝，不留半落状态
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": "FORMULA_SAVE_REJECTED",
                "message": "部分公式未通过校验，本批未保存",
                "issues": save_issues,
            },
        )

    # ── `original_preset` 溯源必须仍落 `parsed_data`（表侧无该列）─────────────
    #
    # 🔴 **这是 Task 17 零回归回归抓到的真实缺陷**（spec
    # formula-management-runtime-closure，2026-08-07）：Wave 3 把公式本体收敛进
    # `wp_formula` 表后一度**完全不写** `parsed_data`，但 `WpFormula` 模型
    # **没有 `original_preset` 列**（逐列核实：V052 基础列 + V100 三类型扩展 +
    # V104 生命周期列，无一可承载「本次覆盖的是哪条预设」）。后果：
    #   - `restore_preset_formula` 的 `restored_to_preset` 读的正是遗留键
    #     （该函数注释自承认「`original_preset` 在表侧不存，回落遗留键」）
    #     ⇒ 新保存的公式恢复预设时恒返回 `None`，用户点「恢复默认」后拿不回预设公式；
    #   - `list_user_formulas` 的读时合并同样从 `prior.get("original_preset")` 取
    #     ⇒ 公式管理页「原预设」列对新公式恒空。
    # 属性测试 `test_pbt_p29_restore_preset` 的
    # `restore(override(preset)) == preset` 因此不成立 —— 它锁定的是**正确**属性，
    # 故这里修生产代码而非改测试（R9.6）。
    #
    # **不是双真源**：公式本体（expression / formula_type / lifecycle）以
    # `wp_formula` 表为唯一权威（运行时 `_load_formulas` 只读该表），
    # `parsed_data` 侧只作「表结构无法承载的溯源元数据」载体，且 GET 的合并
    # 明确「表优先、遗留键仅补 `original_preset`」，DELETE 会一并清理。
    #
# 🔴 **只写 `original_preset` 一个键，绝不回写公式本体**：写整份
    # `user_formulas` 条目（含 formula / formula_type / edited_by / edited_at）
    # 就真的成了双写，Wave 3 的收敛守卫
    # `test_user_formula_storage_convergence` 会打红且理由正当。
    # 精简条目让两侧职责互斥：**表 = 公式本体**，**遗留键 = 表无列的溯源**。
    #
    # JSONB 写法遵循平台铁律：**整体重赋值 + `flag_modified`**（就地改嵌套
    # 不标脏 ⇒ 工作单元判无净变更 ⇒ 不发 UPDATE）。
    preset_trace: dict[str, dict] = {}
    for cell_key, entry in user_formulas.items():
        original = (entry or {}).get("original_preset")
        if original:
            preset_trace[cell_key] = {"original_preset": original}

    if preset_trace or "user_formulas" in parsed_data:
        parsed_data["user_formulas"] = preset_trace
        wp.parsed_data = parsed_data
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

    # NOTE: touch_wp_registry 已由 ACNR events.on_workpaper_saved 统一处理（R23.1/R23.2）

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

    # ── `wp_formula` 表（权威存储）里的对应行 ──
    sheet_name, target_cell = split_cell_key(cell_key)
    row = (
        await db.execute(
            sa.select(WpFormula).where(
                WpFormula.wp_id == wp_id,
                WpFormula.sheet_name == sheet_name,
                WpFormula.target_cell == target_cell,
            )
        )
    ).scalar_one_or_none()

    if cell_key not in user_formulas and row is None:
        return {"wp_id": str(wp_id), "status": "noop", "cell_key": cell_key}

    # 遗留键存在则一并清（避免删掉表行后 GET 仍从 parsed_data 读回）
    removed = user_formulas.pop(cell_key, None) or {}
    if user_formulas or "user_formulas" in parsed_data:
        parsed_data["user_formulas"] = user_formulas
        wp.parsed_data = parsed_data
        sa.orm.attributes.flag_modified(wp, "parsed_data")

    if row is not None:
        # `original_preset` 在表侧不存，回落遗留键（无则 None）
        removed.setdefault("formula", row.expression)
        await db.delete(row)

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

    # NOTE: touch_wp_registry 已由 ACNR events.on_workpaper_saved 统一处理（R23.1/R23.2）

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
