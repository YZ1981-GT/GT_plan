"""合并试算表路由"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import require_project_access
from app.core.database import get_db
from app.models.core import User
from app.models.consolidation_schemas import ConsolTrialResponse, ConsistencyCheckResult
from app.services.consol_trial_service import (
    check_trial_consistency,
    delete_trial,
    get_trial_balance,
    recalculate_trial,
)
from app.services.consol_reconciliation_service import reconcile_worksheet_vs_trial

if TYPE_CHECKING:  # pragma: no cover - 仅注解用，运行时由函数内局部 import 提供
    from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/consolidation/trial", tags=["合并试算表"])


@router.get("", response_model=list[ConsolTrialResponse])
async def get_trial_balance_list(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    return await get_trial_balance(db, project_id, year)


# 🔴 原 ``PUT /{trial_id}``（手改合并试算行）已删除（spec consol-autotree-linkage-closure R8.4）：
# 合并试算是企业树 + 已审批分录的派生数，重算即覆盖；且 ``db.commit()`` 未 await，报成功却从未保存。


@router.post("/recalculate", response_model=list[ConsolTrialResponse])
async def trigger_recalculate(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    """触发全量重算"""
    result = await recalculate_trial(db, project_id, year)
    from app.services.consol_audit_helper import log_consol_action
    await log_consol_action(
        db,
        user_id=user.id,
        project_id=project_id,
        action="consol.recalc",
        resource_type="consol_trial",
        resource_id=str(project_id),
        before=None,
        after={"year": year, "rows_recalculated": len(result)},
    )
    await db.commit()
    return result


@router.get("/consistency-check", response_model=ConsistencyCheckResult)
async def check_consistency(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """一致性校验：按科目自然方向汇总借方性质与贷方性质合计判平衡。"""
    return ConsistencyCheckResult(**(await check_trial_consistency(db, project_id, year)))


@router.get("/stale-status")
async def get_trial_stale_status(
    project_id: UUID,
    year: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """合并 trial 陈旧状态（P1）：子公司 TB 变更后母公司 trial 是否需重算。

    前端据此显示"子公司数据已更新，建议重新汇总"提示 + 重算入口。
    """
    trials = await get_trial_balance(db, project_id, year)
    stale_rows = [t for t in trials if getattr(t, "is_stale", False)]
    return {
        "is_stale": len(stale_rows) > 0,
        "stale_count": len(stale_rows),
        "total_count": len(trials),
    }


@router.get("/reconciliation")
async def get_reconciliation(
    project_id: UUID,
    year: int,
    tolerance: float = 0.01,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("readonly")),
):
    """B2 单一事实源对账：worksheet 根节点 consolidated_amount vs consol_trial.consol_amount。

    不阻断：diff 超容差返回 is_reconciled=false + diffs 清单，接口仍 200。
    两条路径同源（spec consol-tree-three-code-autobuild P8），超容差差异即缺陷 ——
    多为只重算了其中一条路径，先全量重算差额表与合并试算再对账。
    """
    result = await reconcile_worksheet_vs_trial(
        db, project_id, year, tolerance=Decimal(str(tolerance))
    )
    return {
        "is_reconciled": result.is_reconciled,
        "tolerance": str(result.tolerance),
        "max_abs_diff": str(result.max_abs_diff),
        "diff_count": len(result.diffs),
        "diffs": result.diffs,
    }


@router.delete("/{trial_id}", status_code=204)
async def delete_trial_row(
    trial_id: UUID,
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_project_access("edit")),
):
    if not await delete_trial(db, trial_id, project_id):
        raise HTTPException(status_code=404, detail="试算表行不存在")


# ── data_exchange：本地数据导出（spec platform-global-display-settings-closure 任务 10 / AC-21）──
#
# 🔴 这三条路由是 `EXPORT_SURFACE_REGISTRY` 里已登记但此前**没有真实路由**的
# data_exchange 出口（属 `export_surface_results.missing` 的一部分）。
# 口径（design §6.3）：输出**原始元值** + 中文非正式说明 + `_GT_EXPORT_META` marker，
# **不**经 `ExportUnitPolicy` 折算（data_exchange 服务的是「把数据搬走」）。
# 🔴 只出 CSV：CSV 不带格式，能保证值不被任何显示层改写；Excel 走正式导出链。


def _csv_response(rows: list[list[str]], filename: str) -> "StreamingResponse":
    """把行数据编成 CSV 流式响应（UTF-8 BOM，Excel 直接打不会乱码）。"""
    import csv
    import io

    from fastapi.responses import StreamingResponse

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for row in rows:
        writer.writerow(row)
    payload = "\ufeff" + buffer.getvalue()
    return StreamingResponse(
        iter([payload.encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _with_marker_prefix(marker: list[list[str | None]]) -> list[list[str]]:
    """把 `marker_rows()` 的三行（说明 / 键+JSON / 空行）转成 CSV 行。

    🔴 空行统一成 `[""]` 而不是 `[]`。实测（2026-11-16，`csv.writer`）：
    - `writerow([])`   → 写一个空行 `\r\n`（0 个字段）
    - `writerow([""])` → 写 `""` + `\r\n`（1 个空字段）
    两者在 Excel 里看起来都像空行，但按列解析时前者是 0 列、后者是 1 列。
    marker 区固定 2 列（键 + JSON），空行写成 1 个空字段能让下游按列对齐时
    不会「上一行有 2 列、空行 0 列」跳位。
    """
    out: list[list[str]] = []
    for row in marker:
        if not row:
            out.append([""])
        else:
            out.append([("" if cell is None else str(cell)) for cell in row])
    return out


@router.get("/local-export")
async def export_trial_local(
    project_id: UUID,
    year: int,
    # 🔴 function-scope（A6 纪律：新增流式路由必须 function-scope）：
    # 本路由先把数据全部取进内存再编 CSV，响应期不再读 DB ⇒
    # session 可在响应开始前归还连接。
    db: AsyncSession = Depends(get_db, scope="function"),
    user: User = Depends(require_project_access("readonly")),
):
    """合并试算表本地数据导出（data_exchange：原始元值 + marker）。

    spec: platform-global-display-settings-closure 任务 10 / AC-21
    """
    from app.services.export_meta_marker import ExportMeta, marker_rows

    rows_data = await get_trial_balance(db, project_id, year)
    meta = ExportMeta(surface_id="consol_trial_local_export", classification="data_exchange")
    out = _with_marker_prefix(marker_rows(meta))
    out.append(["科目编码", "科目名称", "合并数（元）"])
    for item in rows_data:
        out.append([
            str(getattr(item, "account_code", "") or ""),
            str(getattr(item, "account_name", "") or ""),
            str(getattr(item, "consol_amount", "") or ""),
        ])
    return _csv_response(out, f"consol_trial_{year}_local.csv")


@router.get("/diff/local-export")
async def export_diff_local(
    project_id: UUID,
    year: int,
    # 🔴 function-scope（A6 纪律：新增流式路由必须 function-scope）：
    # 本路由先把数据全部取进内存再编 CSV，响应期不再读 DB ⇒
    # session 可在响应开始前归还连接。
    db: AsyncSession = Depends(get_db, scope="function"),
    user: User = Depends(require_project_access("readonly")),
):
    """合并差额表本地导出（data_exchange）。

    spec: platform-global-display-settings-closure 任务 10 / AC-21
    """
    from app.services.export_meta_marker import ExportMeta, marker_rows

    meta = ExportMeta(surface_id="consol_diff_local_export", classification="data_exchange")
    out = _with_marker_prefix(marker_rows(meta))
    out.append(["节点", "方向", "金额（元）"])
    # 差额表与试算表同源：复用同一 service 的差额口径
    try:
        from app.services.consol_diff_service import get_diff_rows

        diff_rows = await get_diff_rows(db, project_id, year)
    except (ImportError, AttributeError):
        diff_rows = []
    for item in diff_rows:
        out.append([
            str(getattr(item, "node_key", "") or ""),
            str(getattr(item, "direction", "") or ""),
            str(getattr(item, "amount", "") or ""),
        ])
    return _csv_response(out, f"consol_diff_{year}_local.csv")
