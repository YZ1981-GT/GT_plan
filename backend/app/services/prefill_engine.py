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

# 公式正则
_FORMULA_RE = re.compile(
    r'=(TB|WP|AUX|PREV|SUM_TB)\s*\(([^)]*)\)',
    re.IGNORECASE,
)


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
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.value and isinstance(cell.value, str) and cell.value.startswith('='):
                    match = _FORMULA_RE.search(cell.value)
                    if match:
                        formulas_found.append({
                            "sheet": ws.title,
                            "cell": cell.coordinate,
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

    # 批量执行公式
    from app.services.formula_engine import FormulaEngine
    engine = FormulaEngine()

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

            # 写入单元格
            cell_obj = f["cell_obj"]
            value = float(result) if isinstance(result, Decimal) else result

            # 保留原始公式到 comment
            try:
                from openpyxl.comments import Comment
                cell_obj.comment = Comment(f"公式: {f['original']}", "审计平台预填充")
            except Exception:
                pass

            cell_obj.value = value
            filled += 1

        except Exception as e:
            errors.append({"cell": f["cell"], "error": str(e)})

    # 保存文件
    try:
        wb.save(str(fp))
    except Exception as e:
        return {"wp_id": str(wp_id), "status": "error", "message": f"保存失败: {e}"}
    finally:
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
) -> dict[str, Any]:
    """
    真正的解析回写：打开 .xlsx → 提取关键数据 → 写入 parsed_data
    
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

                # 交叉引用
                if isinstance(val, str):
                    for m in _WP_REF_RE.finditer(val):
                        parsed["cross_refs"].append(m.group(1))

    wb.close()

    # 写入 parsed_data
    from datetime import datetime, timezone
    parsed["extracted_at"] = datetime.now(timezone.utc).isoformat()
    wp_write = (await db.execute(
        sa.select(WorkingPaper).where(WorkingPaper.id == wp_id)
    )).scalar_one_or_none()
    if wp_write:
        wp_write.parsed_data = parsed
        wp_write.last_parsed_at = datetime.now(timezone.utc)
        await db.flush()

    _logger.info(
        "parse_real: wp=%s audited=%s unadj=%s conclusion=%s refs=%d",
        wp_id, parsed["audited_amount"], parsed["unadjusted_amount"],
        "yes" if parsed["conclusion"] else "no", len(parsed["cross_refs"]),
    )

    return {
        "wp_id": str(wp_id),
        "status": "ok",
        "audited_amount": parsed["audited_amount"],
        "unadjusted_amount": parsed["unadjusted_amount"],
        "has_conclusion": parsed["conclusion"] is not None,
        "cross_ref_count": len(parsed["cross_refs"]),
        "message": "解析完成",
    }
