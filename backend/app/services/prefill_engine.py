"""底稿预填充引擎 — 真正打开 .xlsx 扫描公式并写入计算结果

替代 prefill_service.py 的 stub 实现。

流程：
1. openpyxl 打开底稿 .xlsx（保留公式和格式）
2. 扫描所有单元格，识别 =TB()/=SUM_TB()/=AUX()/=PREV()/=WP() 公式
3. 批量调用 FormulaEngine 执行公式
4. 将结果写入单元格值（保留公式文本到 comment）
5. 保存文件
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WorkingPaper

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 公式正则 & FormulaCell（兼容旧 prefill_service 接口）
# ---------------------------------------------------------------------------

_FORMULA_RE = re.compile(
    r'=(TB|WP|AUX|PREV|SUM_TB)\s*\(([^)]*)\)',
    re.IGNORECASE,
)


class FormulaCell:
    """Represents a formula cell found during scanning."""

    def __init__(self, sheet: str, cell_ref: str, formula_type: str, raw_args: str):
        self.sheet = sheet
        self.cell_ref = cell_ref
        self.formula_type = formula_type.upper()
        self.raw_args = raw_args

    def to_dict(self) -> dict:
        return {"sheet": self.sheet, "cell_ref": self.cell_ref, "formula_type": self.formula_type, "raw_args": self.raw_args}


def _parse_args(raw: str) -> list[str]:
    """解析公式参数，处理引号和逗号"""
    args = []
    current = []
    in_quote = False
    for ch in raw:
        if ch == '"' or ch == "'":
            in_quote = not in_quote
        elif ch == ',' and not in_quote:
            args.append(''.join(current).strip().strip('"').strip("'"))
            current = []
            continue
        current.append(ch)
    if current:
        args.append(''.join(current).strip().strip('"').strip("'"))
    return args


async def prefill_workpaper_real(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    wp_id: UUID,
) -> dict[str, Any]:
    """
    真正的预填充：打开 .xlsx → 扫描公式 → 执行 → 写回
    """
    try:
        import openpyxl
    except ImportError:
        return {"wp_id": str(wp_id), "status": "error", "message": "openpyxl 未安装"}

    # 获取底稿文件路径
    wp = (await db.execute(
        sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
    )).scalar_one_or_none()
    if not wp or not wp.file_path:
        return {"wp_id": str(wp_id), "status": "error", "message": "底稿文件不存在"}

    fp = Path(wp.file_path)
    if not fp.exists():
        return {"wp_id": str(wp_id), "status": "error", "message": f"文件不存在: {fp}"}

    # 打开 Excel（保留格式）
    try:
        wb = openpyxl.load_workbook(str(fp), data_only=False)
    except Exception as e:
        return {"wp_id": str(wp_id), "status": "error", "message": f"打开文件失败: {e}"}

    # 扫描所有公式
    formulas_found = []
    for sheet_idx, ws in enumerate(wb.worksheets):
        for row in ws.iter_rows():
            for cell in row:
                if cell.value and isinstance(cell.value, str) and cell.value.startswith('='):
                    match = _FORMULA_RE.search(cell.value)
                    if match:
                        formulas_found.append({
                            "sheet": ws.title,
                            "sheet_idx": sheet_idx,
                            "cell": cell.coordinate,
                            "row": cell.row - 1,       # 0-based row index
                            "col": cell.column - 1,    # 0-based column index
                            "formula_type": match.group(1).upper(),
                            "raw_args": match.group(2).strip(),
                            "original": cell.value,
                            "cell_obj": cell,
                        })

    if not formulas_found:
        wb.close()
        return {
            "wp_id": str(wp_id), "status": "ok",
            "formulas_found": 0, "formulas_filled": 0,
            "message": "未发现取数公式",
        }

    # 批量执行公式（需求 46：只更新 structure.json 的 v 字段，保留 xlsx 公式）
    from app.services.formula_engine import FormulaEngine
    import json as _json
    engine = FormulaEngine()

    # 读取 structure.json（供填入 v 字段）
    structure_path = fp.with_suffix(".structure.json")
    structure_data: dict | None = None
    if structure_path.exists():
        try:
            with open(structure_path, "r", encoding="utf-8") as sf:
                structure_data = _json.load(sf)
        except Exception as e:
            _logger.warning("prefill_real: structure.json 读取失败 wp=%s err=%s", wp_id, e)
            structure_data = None
    else:
        _logger.warning("prefill_real: structure.json 不存在 wp=%s path=%s，预填充将跳过值写入", wp_id, structure_path)

    filled = 0
    errors = []

    for f in formulas_found:
        args = _parse_args(f["raw_args"])
        ft = f["formula_type"]

        params: dict[str, Any] = {}
        if ft == "TB" and len(args) >= 2:
            params = {"account_code": args[0], "column_name": args[1]}
        elif ft == "SUM_TB" and len(args) >= 2:
            params = {"account_range": args[0], "column_name": args[1]}
        elif ft == "AUX" and len(args) >= 4:
            params = {"account_code": args[0], "aux_dimension": args[1], "dimension_value": args[2], "column_name": args[3]}
        elif ft == "WP" and len(args) >= 2:
            params = {"wp_code": args[0], "cell_ref": args[1]}
        elif ft == "PREV" and len(args) >= 2:
            params = {"formula_type": args[0], "account_code": args[1] if len(args) > 1 else "", "column_name": args[2] if len(args) > 2 else ""}
        else:
            errors.append({"cell": f["cell"], "error": f"参数不足: {f['original']}"})
            continue

        try:
            result = await engine.execute(
                db=db,
                project_id=project_id,
                year=year if ft != "PREV" else year - 1,
                formula_type=ft if ft != "PREV" else params.get("formula_type", "TB"),
                params=params,
            )

            if hasattr(result, 'message'):
                # FormulaError
                errors.append({"cell": f["cell"], "error": result.message})
                continue

            value = float(result) if isinstance(result, Decimal) else result

            # 需求 46.1/46.2：只更新 structure.json 的 v 字段，保留 xlsx 中的公式
            # 不再写 cell_obj.value（避免覆盖公式），不再将公式移入 comment
            if structure_data is not None:
                # structure.json 的 rows 是跨 sheet 扁平化的，需累加前序 sheet 的行数
                row_offset = 0
                sheets_meta = structure_data.get("sheets", [])
                snapshot_sheets = wb.worksheets
                for prior_idx in range(f["sheet_idx"]):
                    if prior_idx < len(snapshot_sheets):
                        row_offset += snapshot_sheets[prior_idx].max_row or 0

                target_row_idx = row_offset + f["row"]
                rows_arr = structure_data.get("rows", [])
                if 0 <= target_row_idx < len(rows_arr):
                    cells_arr = rows_arr[target_row_idx].get("cells", [])
                    # 补齐列（若 structure.json 之前是稀疏写入）
                    while len(cells_arr) <= f["col"]:
                        cells_arr.append({"value": "", "formula": None})
                    # 保留 formula 字段不变，仅更新 value
                    cells_arr[f["col"]]["value"] = value
                    if cells_arr[f["col"]].get("formula") is None:
                        cells_arr[f["col"]]["formula"] = f["original"]
                    rows_arr[target_row_idx]["cells"] = cells_arr
                    filled += 1
                else:
                    errors.append({"cell": f["cell"], "error": f"structure.json 行越界: {target_row_idx}"})
            else:
                # 无 structure.json：跳过本单元格（避免破坏公式），但不算错误
                # 上面已记录 warning 日志
                pass

        except Exception as e:
            errors.append({"cell": f["cell"], "error": str(e)})

    # 保存 structure.json（需求 46.1：不再修改 xlsx）
    if structure_data is not None and filled > 0:
        try:
            with open(structure_path, "w", encoding="utf-8") as sf:
                _json.dump(structure_data, sf, ensure_ascii=False, indent=2)
        except Exception as e:
            wb.close()
            return {"wp_id": str(wp_id), "status": "error", "message": f"structure.json 保存失败: {e}"}

    wb.close()

    _logger.info("prefill_real: wp=%s found=%d filled=%d errors=%d", wp_id, len(formulas_found), filled, len(errors))

    return {
        "wp_id": str(wp_id),
        "status": "ok",
        "formulas_found": len(formulas_found),
        "formulas_filled": filled,
        "errors": errors[:10],
        "message": f"预填充完成：{filled}/{len(formulas_found)} 个公式已计算",
    }


async def parse_workpaper_real(
    db: AsyncSession,
    project_id: UUID,
    wp_id: UUID,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    真正的解析回写：打开 .xlsx → 提取关键数据 → 写入 parsed_data

    参数：
      dry_run=True  — 仅返回解析预览，不写入 parsed_data（用于两步确认流程的步骤1）
      dry_run=False — 解析并写入 parsed_data（默认，用于步骤2确认后）

    提取内容：
    1. 审定数（审定表中的审定数合计）
    2. 未审数
    3. AJE/RJE 调整金额
    4. 结论文本（搜索"审计结论"/"结论"附近的单元格）
    5. 交叉引用（=WP() 公式）
    """
    try:
        import openpyxl
    except ImportError:
        return {"wp_id": str(wp_id), "status": "error", "message": "openpyxl 未安装"}

    wp = (await db.execute(
        sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
    )).scalar_one_or_none()
    if not wp or not wp.file_path:
        return {"wp_id": str(wp_id), "status": "error", "message": "底稿文件不存在"}

    fp = Path(wp.file_path)
    if not fp.exists():
        return {"wp_id": str(wp_id), "status": "error", "message": f"文件不存在: {fp}"}

    try:
        wb = openpyxl.load_workbook(str(fp), data_only=True, read_only=False)
    except Exception as e:
        return {"wp_id": str(wp_id), "status": "error", "message": f"打开文件失败: {e}"}

    parsed = {
        "audited_amount": None,
        "unadjusted_amount": None,
        "aje_adjustment": 0,
        "rje_adjustment": 0,
        "conclusion": None,
        "conclusion_text": None,
        "audit_explanation": None,
        "cross_refs": [],
        "ai_content": [],
        "extracted_at": None,
    }

    # 关键词搜索
    _AUDITED_KW = ["审定数", "审定金额", "审定余额", "审计后金额", "Audited"]
    _UNADJUSTED_KW = ["未审数", "未审金额", "账面数", "账面金额", "Unadjusted"]
    _AJE_KW = ["AJE", "审计调整", "调整分录"]
    _RJE_KW = ["RJE", "重分类"]
    _CONCLUSION_KW = ["审计结论", "结论", "审计意见", "Conclusion"]
    _EXPLANATION_KW = ["审计说明", "审计结论", "执行情况", "审计程序执行", "审计发现", "Explanation"]
    _WP_REF_RE = re.compile(r'=WP\s*\(\s*["\']([^"\']+)["\']', re.IGNORECASE)

    for ws in wb.worksheets:
        for row in ws.iter_rows(max_row=200, max_col=20):
            for cell in row:
                val = cell.value
                if val is None:
                    continue
                s = str(val).strip()

                # 检查是否是关键词标签（左侧标签，右侧是数值）
                for kw_list, key in [
                    (_AUDITED_KW, "audited_amount"),
                    (_UNADJUSTED_KW, "unadjusted_amount"),
                    (_AJE_KW, "aje_adjustment"),
                    (_RJE_KW, "rje_adjustment"),
                ]:
                    if any(kw in s for kw in kw_list):
                        # 取右侧单元格的值
                        try:
                            right_cell = ws.cell(row=cell.row, column=cell.column + 1)
                            if right_cell.value is not None:
                                num = float(right_cell.value)
                                if parsed[key] is None or key in ("aje_adjustment", "rje_adjustment"):
                                    parsed[key] = num
                        except (ValueError, TypeError):
                            pass

                # 结论文本（标题行含关键词，下方或右侧是结论内容）
                for kw in _CONCLUSION_KW:
                    if kw in s:
                        # 情况1：关键词和结论在同一单元格（长文本）
                        if len(s) > len(kw) + 10:
                            parsed["conclusion"] = s
                            parsed["conclusion_text"] = s
                            break
                        # 情况2：关键词是标题，结论在右侧单元格
                        try:
                            right_cell = ws.cell(row=cell.row, column=cell.column + 1)
                            if right_cell.value and len(str(right_cell.value).strip()) > 5:
                                parsed["conclusion"] = str(right_cell.value).strip()
                                parsed["conclusion_text"] = parsed["conclusion"]
                                break
                        except Exception:
                            pass
                        # 情况3：关键词是标题，结论在下方单元格
                        try:
                            below_cell = ws.cell(row=cell.row + 1, column=cell.column)
                            if below_cell.value and len(str(below_cell.value).strip()) > 5:
                                parsed["conclusion"] = str(below_cell.value).strip()
                                parsed["conclusion_text"] = parsed["conclusion"]
                                break
                        except Exception:
                            pass

                # 审计说明提取
                if parsed["audit_explanation"] is None:
                    for ekw in _EXPLANATION_KW:
                        if ekw in s:
                            parts = []
                            if len(s) > len(ekw) + 20:
                                parts.append(s)
                            for co in range(1, 6):
                                try:
                                    rc = ws.cell(row=cell.row, column=cell.column + co)
                                    if rc.value and str(rc.value).strip():
                                        parts.append(str(rc.value).strip())
                                    else:
                                        break
                                except Exception:
                                    break
                            if not parts:
                                for ro in range(1, 10):
                                    try:
                                        bc = ws.cell(row=cell.row + ro, column=cell.column)
                                        if bc.value and str(bc.value).strip():
                                            parts.append(str(bc.value).strip())
                                        else:
                                            break
                                    except Exception:
                                        break
                            if parts:
                                parsed["audit_explanation"] = "\n".join(parts)
                            break

                # 交叉引用
                if isinstance(val, str):
                    for m in _WP_REF_RE.finditer(val):
                        parsed["cross_refs"].append(m.group(1))

    wb.close()

    # 写入 parsed_data（dry_run=True 时跳过写入，仅返回预览）
    from datetime import datetime, timezone
    parsed["extracted_at"] = datetime.now(timezone.utc).isoformat()
    if not dry_run:
        wp_write = (await db.execute(
            sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
        )).scalar_one_or_none()
        if wp_write:
            wp_write.parsed_data = parsed
            wp_write.last_parsed_at = datetime.now(timezone.utc)
            await db.flush()

    _logger.info(
        "parse_real: wp=%s audited=%s unadj=%s conclusion=%s refs=%d dry_run=%s",
        wp_id, parsed["audited_amount"], parsed["unadjusted_amount"],
        "yes" if parsed["conclusion"] else "no", len(parsed["cross_refs"]), dry_run,
    )

    return {
        "wp_id": str(wp_id),
        "status": "ok",
        "dry_run": dry_run,
        "audited_amount": parsed["audited_amount"],
        "unadjusted_amount": parsed["unadjusted_amount"],
        "has_conclusion": parsed["conclusion"] is not None,
        "cross_ref_count": len(parsed["cross_refs"]),
        "parsed_data": parsed,
        "message": "解析预览（未写入）" if dry_run else "解析完成",
    }


# ---------------------------------------------------------------------------
# mark_stale — 标记底稿预填数据为过期（从 prefill_service_v2 迁移）
# ---------------------------------------------------------------------------

async def mark_stale(
    db: AsyncSession,
    project_id: UUID,
    account_codes: list[str] | None = None,
) -> int:
    """标记底稿预填数据为过期"""
    q = (
        sa.update(WorkingPaper)
        .where(
            WorkingPaper.project_id == project_id,
            WorkingPaper.is_deleted == False,  # noqa: E712
        )
        .values(prefill_stale=True)
    )
    result = await db.execute(q)
    return result.rowcount


# ---------------------------------------------------------------------------
# scan_formulas — 从文本列表中扫描公式（兼容旧 PrefillService 接口）
# ---------------------------------------------------------------------------

def scan_formulas(cell_texts: list[dict]) -> list[FormulaCell]:
    """Scan a list of cell text entries for formula patterns."""
    results: list[FormulaCell] = []
    for entry in cell_texts:
        text = entry.get("text", "")
        sheet = entry.get("sheet", "Sheet1")
        cell_ref = entry.get("cell_ref", "")
        for match in _FORMULA_RE.finditer(text):
            results.append(FormulaCell(
                sheet=sheet, cell_ref=cell_ref,
                formula_type=match.group(1).upper(),
                raw_args=match.group(2).strip(),
            ))
    return results


# ---------------------------------------------------------------------------
# detect_conflicts — 版本冲突检测（从 prefill_service 迁移）
# ---------------------------------------------------------------------------

async def detect_conflicts(
    db: AsyncSession,
    project_id: UUID,
    wp_id: UUID,
    uploaded_version: int,
) -> dict[str, Any]:
    """Detect conflicts between uploaded file and server version."""
    result = await db.execute(
        sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
    )
    wp = result.scalar_one_or_none()
    if wp is None:
        return {"has_conflict": False, "error": "底稿不存在"}
    current_version = wp.file_version
    has_conflict = uploaded_version < current_version
    return {
        "has_conflict": has_conflict,
        "uploaded_version": uploaded_version,
        "server_version": current_version,
        "conflicts": [] if not has_conflict else [
            {"message": f"版本冲突: 上传版本 {uploaded_version} < 服务器版本 {current_version}"}
        ],
    }


# ---------------------------------------------------------------------------
# 兼容类（供旧测试代码导入，代理到模块级函数）
# ---------------------------------------------------------------------------

class PrefillService:
    """兼容旧接口"""
    def _scan_formulas(self, cell_texts: list[dict]) -> list[FormulaCell]:
        return scan_formulas(cell_texts)

    async def prefill_workpaper(self, db: AsyncSession, project_id: UUID, year: int, wp_id: UUID) -> dict:
        return await prefill_workpaper_real(db, project_id, year, wp_id)

    async def batch_prefill(self, db: AsyncSession, project_id: UUID, year: int, wp_ids: list[UUID]) -> dict:
        import asyncio
        tasks = [self.prefill_workpaper(db, project_id, year, wid) for wid in wp_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        success, errors = {}, {}
        for wid, r in zip(wp_ids, results):
            if isinstance(r, Exception):
                errors[str(wid)] = str(r)
            else:
                success[str(wid)] = r
        return {"total": len(wp_ids), "success_count": len(success), "error_count": len(errors), "results": success, "errors": errors}

    async def _get_cached_prefill(self, wp_id: UUID) -> dict | None:
        return None

    async def _set_cached_prefill(self, wp_id: UUID, data: dict) -> None:
        pass


class ParseService:
    """兼容旧接口"""
    async def parse_workpaper(self, db: AsyncSession, project_id: UUID, wp_id: UUID) -> dict:
        return await parse_workpaper_real(db, project_id, wp_id)

    async def detect_conflicts(self, db: AsyncSession, project_id: UUID, wp_id: UUID, uploaded_version: int) -> dict:
        return await detect_conflicts(db, project_id, wp_id, uploaded_version)
