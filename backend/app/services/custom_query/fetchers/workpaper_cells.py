"""底稿单元格区域取数与 sheet 选区器预览（从 ``routers/custom_query`` 迁入；查询路径只读，design §3.7 / R4.4）。

结构写死（AST 守卫 ``tests/advanced_query_linkage/test_aql_query_path_readonly.py``）：

- 写盘只出现在 ``_temp_copy(src, tmpdir)``，调用方只传 ``tempfile.TemporaryDirectory()`` 的目录；
- ``recompute_with_libreoffice(src) -> bytes | None`` 在临时副本上转换、读回字节，不写回 storage；
- 底稿没有 storage 文件时不从模板生成（原先调 ``init_workpaper_from_template`` 写文件）：预览返回
  ``available: false`` + ``NO_FILE_REASON``，区域取数 400 同文案；查找文件也不建目录；
- 公式未求值且重算失败（LibreOffice 不可用 / 转换失败）时 warnings 写明 ``RECOMPUTE_FAILED_WARNING``。
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

NO_FILE_REASON = "该底稿尚未生成文件，请先在底稿编辑器中打开一次"
RECOMPUTE_FAILED_WARNING = "公式未能重算，显示的是文件缓存值"


def _temp_copy(src: Path, tmpdir: Path) -> Path:
    """查询路径唯一的写盘点：把底稿文件复制进临时目录（调用方只传 ``tempfile.TemporaryDirectory()`` 的目录）。"""
    target = tmpdir / src.name
    shutil.copy2(src, target)
    return target


def existing_workpaper_file(project_id: uuid.UUID, wp_id: Any) -> Path | None:
    """只读查找底稿的 storage 文件，没有返回 None。

    项目目录不存在时直接返回 None，不调 ``get_workpaper_file``——它经 ``get_workpaper_storage_path`` 会 ``mkdir``
    项目目录（查询路径不得在 storage 里留下任何东西）。路径规则仍以 ``wp_template_init_service`` 为唯一来源。
    """
    from app.services import wp_template_init_service as storage

    if not (storage.STORAGE_DIR / str(project_id)).is_dir():
        return None
    return storage.get_workpaper_file(project_id, wp_id)


def _sync_parse_sheet_preview(content: bytes, sheet_name: str | None) -> dict:
    """同步函数：openpyxl 解析单 sheet 返回 cellData（供 run_in_executor 调用避免阻塞 event loop）

    公式 cell 处理：data_only=True 拿不到 cache（None）时同时附 formula 字段，前端可标识灰色斜体
    """
    from io import BytesIO
    from openpyxl import load_workbook
    wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
    target = sheet_name if sheet_name and sheet_name in wb.sheetnames else (wb.sheetnames[0] if wb.sheetnames else None)
    if not target:
        wb.close()
        return {"error": "工作簿无 sheet"}
    ws = wb[target]
    rows = min(ws.max_row or 0, 100)
    cols = min(ws.max_column or 0, 30)
    cells: dict[str, dict] = {}
    has_unresolved_formula = False
    # 第二份 wb 用 data_only=False 探测公式（仅按需打开）
    wb_formula = None
    ws_formula = None
    for row_iter in ws.iter_rows(min_row=1, max_row=rows, max_col=cols):
        for cell in row_iter:
            try:
                row_num = cell.row
                col_num = cell.column
                v = cell.value
            except AttributeError:
                continue
            key = f"{row_num - 1},{col_num - 1}"
            if v is None:
                # 可能是公式 cell 但 cache 缺失
                if wb_formula is None:
                    wb_formula = load_workbook(BytesIO(content), read_only=True, data_only=False)
                    ws_formula = wb_formula[target] if target in wb_formula.sheetnames else None
                if ws_formula is not None:
                    # read_only 模式不能 ws.cell(r, c)，用 iter_rows 一次性扫公式
                    if not hasattr(ws_formula, "_formula_cache"):
                        fcache: dict[tuple[int, int], str] = {}
                        for f_row_iter in ws_formula.iter_rows(min_row=1, max_row=rows, max_col=cols):
                            for fc in f_row_iter:
                                try:
                                    if isinstance(fc.value, str) and fc.value.startswith("="):
                                        fcache[(fc.row, fc.column)] = fc.value
                                except AttributeError:
                                    continue
                        ws_formula._formula_cache = fcache  # type: ignore[attr-defined]
                    raw = ws_formula._formula_cache.get((row_num, col_num))  # type: ignore[attr-defined]
                    if raw:
                        cells[key] = {"v": "", "f": raw}
                        has_unresolved_formula = True
                continue
            cells[key] = {"v": v if isinstance(v, (int, float)) else str(v)}
    merges = []
    for mr in (ws.merged_cells.ranges if hasattr(ws, "merged_cells") else []):
        merges.append({"r1": mr.min_row - 1, "c1": mr.min_col - 1, "r2": mr.max_row - 1, "c2": mr.max_col - 1})
    all_sheets = list(wb.sheetnames)
    wb.close()
    if wb_formula is not None:
        wb_formula.close()
    return {
        "sheet_name": target,
        "all_sheets": all_sheets,
        "rows": rows,
        "cols": cols,
        "cells": cells,
        "merges": merges,
        "has_unresolved_formula": has_unresolved_formula,
    }


def _sync_extract_cell_range(content: bytes, sheet_name: str | None, r1: int, c1: int, r2: int, c2: int, max_cells: int = 500) -> dict:
    """同步函数：按 cell_range 提取单元格值清单（run_in_executor 调用）

    公式还原策略：data_only=True 读 cache + data_only=False 探公式字符串。
    注意 openpyxl read_only 模式下 ws.cell(r, c) 不能随机访问，必须 iter_rows 顺序读取。
    """
    from io import BytesIO
    from openpyxl import load_workbook

    # 第一份：data_only=True 读 cache（用 iter_rows，read_only 模式 ws.cell 不可随机）
    wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
    target = sheet_name if sheet_name and sheet_name in wb.sheetnames else (wb.sheetnames[0] if wb.sheetnames else None)
    if not target:
        wb.close()
        return {"error": "工作簿无 sheet"}
    ws = wb[target]
    cache_map: dict[tuple[int, int], Any] = {}
    for row_iter in ws.iter_rows(min_row=r1, max_row=r2, min_col=c1, max_col=c2):
        for cell in row_iter:
            # read_only 模式下边界外为 EmptyCell（无 row/column 属性），跳过
            try:
                cache_map[(cell.row, cell.column)] = cell.value
            except AttributeError:
                continue
    wb.close()

    # 第二份：data_only=False 读公式字符串
    formula_map: dict[tuple[int, int], str] = {}
    has_unresolved_formula = False
    expected_count = (r2 - r1 + 1) * (c2 - c1 + 1)
    if any(v is None for v in cache_map.values()) or len(cache_map) < expected_count:
        wb_f = load_workbook(BytesIO(content), read_only=True, data_only=False)
        if target in wb_f.sheetnames:
            ws_f = wb_f[target]
            for row_iter in ws_f.iter_rows(min_row=r1, max_row=r2, min_col=c1, max_col=c2):
                for cell in row_iter:
                    try:
                        if isinstance(cell.value, str) and cell.value.startswith("="):
                            formula_map[(cell.row, cell.column)] = cell.value
                            if cache_map.get((cell.row, cell.column)) is None:
                                has_unresolved_formula = True
                    except AttributeError:
                        continue
        wb_f.close()

    out_rows: list[dict] = []
    idx = 0
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            idx += 1
            if idx > max_cells:
                break
            col_letters = ""
            cc = c
            while cc > 0:
                cc, rem = divmod(cc - 1, 26)
                col_letters = chr(65 + rem) + col_letters
            cell_ref = f"{col_letters}{r}"
            v = cache_map.get((r, c))
            f_str = formula_map.get((r, c))
            if v is None:
                val_str: str | int | float = ""
            elif isinstance(v, (int, float)):
                val_str = v
            else:
                val_str = str(v)
            row_obj: dict = {"cell_ref": cell_ref, "value": val_str}
            if f_str:
                row_obj["formula"] = f_str
            out_rows.append(row_obj)
        if idx >= max_cells:
            break
    return {
        "rows": out_rows,
        "sheet_name": target,
        "has_unresolved_formula": has_unresolved_formula,
    }


_LIBREOFFICE_PATHS = (
    "libreoffice", "soffice",
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    "/usr/bin/libreoffice",
    "/usr/bin/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
)


def _find_soffice() -> str | None:
    """检测 LibreOffice 可执行路径（4 路径 fallback，与 archive_pdf_generators 对齐）"""
    for cmd in _LIBREOFFICE_PATHS:
        path = shutil.which(cmd) if not Path(cmd).is_absolute() else (cmd if Path(cmd).exists() else None)
        if path:
            return path
    return None


def recompute_with_libreoffice(src: Path) -> bytes | None:
    """用 LibreOffice headless 在**临时副本**上重算 xlsx 公式，返回重算后的文件字节；不可用 / 失败返回 None。

    仅在 ``_sync_extract_cell_range`` 返回 ``has_unresolved_formula=True`` 时按需触发（run_in_executor 调用）。
    原文件只读：先 ``_temp_copy`` 进临时输入目录，再转换到另一个临时输出目录、读回字节；两个目录随 ``with`` 删除，
    函数体内没有任何写调用（原实现把转换结果 ``shutil.copy`` 回 storage 覆盖原文件，AQ-23）。
    """
    soffice = _find_soffice()
    if soffice is None:
        logger.warning("LibreOffice 未找到，公式无法重算（请装 LibreOffice 或在 PATH 中加 soffice）")
        return None
    try:
        with tempfile.TemporaryDirectory() as in_dir, tempfile.TemporaryDirectory() as out_dir:
            work = _temp_copy(src, Path(in_dir))
            # --calc 强制用 Calc 打开（默认会用 Writer 打开 xlsx 失败）；--convert-to xlsx 触发重算 + 写 cache
            result = subprocess.run(
                [soffice, "--headless", "--calc", "--convert-to", "xlsx", "--outdir", str(out_dir), str(work)],
                capture_output=True,
                timeout=60,
            )
            converted = Path(out_dir) / f"{work.stem}.xlsx"
            if result.returncode != 0 or not converted.is_file():
                logger.warning("LibreOffice 转换失败 rc=%d stderr=%s", result.returncode, result.stderr[:200])
                return None
            return converted.read_bytes()
    except Exception as e:
        logger.warning("LibreOffice 重算异常: %s", e)
        return None


def _try_render_preview_from_snapshot(parsed_data: dict, sheet_name: str | None) -> dict | None:
    """从 parsed_data['univer_snapshot'] 直接渲染 picker 预览（零计算）

    返回 {sheet_name, all_sheets, rows, cols, cells, merges} 或 None（snapshot 不可用降级 xlsx）
    """
    if not isinstance(parsed_data, dict):
        return None
    snapshot = parsed_data.get("univer_snapshot")
    if not isinstance(snapshot, dict):
        return None
    sheets_map = snapshot.get("sheets") or {}
    if not sheets_map:
        return None
    order = snapshot.get("sheet_order_names") or list(sheets_map.keys())
    target = sheet_name if sheet_name and sheet_name in sheets_map else (order[0] if order else None)
    if not target:
        return None
    sheet_obj = sheets_map.get(target) or {}
    cell_data = sheet_obj.get("cellData") or {}
    if not isinstance(cell_data, dict):
        return None
    # 转为 picker 期望的 {(r,c): {v, f}} 形式（0-indexed key 'r,c'），同时算 rows/cols 边界
    cells: dict[str, dict] = {}
    max_r = 0
    max_c = 0
    for r_str, row in cell_data.items():
        try:
            r = int(r_str)
        except (TypeError, ValueError):
            continue
        if not isinstance(row, dict):
            continue
        for c_str, cell in row.items():
            try:
                c = int(c_str)
            except (TypeError, ValueError):
                continue
            if not isinstance(cell, dict):
                continue
            obj: dict = {}
            v = cell.get("v")
            if v is not None and v != "":
                obj["v"] = v if isinstance(v, (int, float)) else str(v)
            else:
                obj["v"] = ""
            if cell.get("f"):
                obj["f"] = str(cell["f"])
            if obj.get("v") != "" or obj.get("f"):
                cells[f"{r},{c}"] = obj
                if r > max_r:
                    max_r = r
                if c > max_c:
                    max_c = c
    return {
        "sheet_name": target,
        "all_sheets": order,
        "rows": min(max_r + 1, 100) or 30,
        "cols": min(max_c + 1, 30) or 10,
        "cells": cells,
        "merges": [],  # snapshot 暂不存合并信息（未来可加 mergeData 字段）
    }


async def render_sheet_preview(
    project_id: uuid.UUID, wp_id: Any, wp_code: str, parsed_data: dict, sheet_name: str | None,
) -> dict:
    """sheet 选区器预览（``GET /wp-sheet-preview`` 的取数；只读）。

    数据源优先级：①``parsed_data['univer_snapshot']``（零计算）②storage xlsx 的缓存值（openpyxl 只读解析）。
    没有 storage 文件 ⇒ ``available: false`` + ``NO_FILE_REASON``，不从模板生成文件。
    """
    snap_view = _try_render_preview_from_snapshot(parsed_data, sheet_name)
    if snap_view is not None:
        return {"available": True, "wp_code": wp_code, "wp_id": str(wp_id), "source": "univer_snapshot", **snap_view}

    storage_path = existing_workpaper_file(project_id, wp_id)
    if storage_path is None:
        return {"available": False, "reason": NO_FILE_REASON, "wp_code": wp_code}
    if storage_path.suffix.lower() not in (".xlsx", ".xlsm"):
        return {"available": False, "reason": "非 xlsx 类底稿", "wp_code": wp_code}
    try:
        content = storage_path.read_bytes()
        loop = asyncio.get_running_loop()
        parsed = await loop.run_in_executor(None, _sync_parse_sheet_preview, content, sheet_name)
        if "error" in parsed:
            return {"available": False, "reason": parsed["error"], "wp_code": wp_code}
        return {"available": True, "wp_code": wp_code, "wp_id": str(wp_id), "source": "xlsx_cache", **parsed}
    except Exception as e:
        logger.warning("wp-sheet-preview parse failed for %s: %s", wp_code, e)
        return {"available": False, "reason": f"解析失败: {e}", "wp_code": wp_code}


async def _query_workpaper_cell_range(db, pid: str, filters: dict):
    """按 cell_range 提取真实单元格值（只读）

    数据源优先级（零计算路径优先）：
      1. `working_paper.parsed_data['univer_snapshot']` — 用户保存底稿时已落库的 Univer 计算后值（首选，零计算）
      2. storage xlsx 的 cache（data_only=True 读，模板从未保存过时为 None）；没有文件 ⇒ 错误 ``NO_FILE_REASON``
         （分派层转 400 ``QUERY_FAILED``），不从模板生成
      3. LibreOffice headless 重算（仅前两路径都拿不到值时按需触发）：只在临时副本上重算、读回字节，不写回 storage；
         重算失败 ⇒ 仍返回缓存值并在 warnings 写明 ``RECOMPUTE_FAILED_WARNING``

    支持语法：'A1:C3' / 'B5' / 'A1:A10,C1:C5' / 'A:A' / 'A:C'
    """
    wp_code = filters["wp_code"]
    sheet_name = filters.get("sheet_name")
    cell_range = filters["cell_range"]

    try:
        proj_uuid = uuid.UUID(pid)
    except (TypeError, ValueError):
        return {"rows": [], "columns": [], "total": 0, "error": "invalid project_id"}

    # 1. wp_code → wp_id + parsed_data 一次查询拿到
    row = (await db.execute(text("""
        SELECT w.id, w.parsed_data
        FROM working_paper w
        JOIN wp_index i ON w.wp_index_id = i.id
        WHERE i.project_id = :pid AND i.wp_code = :wpc AND w.is_deleted = false
        LIMIT 1
    """), {"pid": str(proj_uuid), "wpc": wp_code})).first()
    if not row:
        return {"rows": [], "columns": [], "total": 0, "error": f"底稿 {wp_code} 在当前项目不存在"}
    wp_id = row[0]
    parsed_data = row[1] if isinstance(row[1], dict) else {}

    # 2. 解析 cell_range 多区域
    ranges = _parse_cell_ranges(cell_range)
    if not ranges:
        return {"rows": [], "columns": [], "total": 0, "error": f"无效 cell_range: {cell_range}"}

    # 3. 优先尝试 parsed_data['univer_snapshot']（零计算快路径）
    snapshot_rows = _try_extract_from_univer_snapshot(parsed_data, sheet_name, ranges, wp_code)
    if snapshot_rows is not None:
        result_columns = ["index", "wp_code", "sheet_name", "cell_ref", "value"]
        if any("formula" in r for r in snapshot_rows):
            result_columns.append("formula")
        return {
            "rows": snapshot_rows,
            "columns": result_columns,
            "total": len(snapshot_rows),
            "source": "univer_snapshot",
        }

    # Req 6: snapshot 缺失，记录监控指标后走 LibreOffice 兜底
    from app.services.custom_query.metrics import inc_snapshot_missing
    inc_snapshot_missing(wp_code)

    # 4. 降级：storage xlsx 路径（含 LibreOffice 按需重算，只在临时副本上）；没有文件不从模板生成
    storage_path = existing_workpaper_file(proj_uuid, wp_id)
    if storage_path is None:
        return {"rows": [], "columns": [], "total": 0, "error": NO_FILE_REASON}

    if storage_path.suffix.lower() not in (".xlsx", ".xlsm"):
        return {"rows": [], "columns": [], "total": 0, "error": "非 xlsx 类底稿"}

    try:
        content = storage_path.read_bytes()
        loop = asyncio.get_running_loop()
        all_rows: list[dict] = []
        used_sheet = ""
        idx = 0
        MAX_TOTAL = 500
        any_unresolved = False
        for (r1, c1, r2, c2) in ranges:
            remaining = MAX_TOTAL - idx
            if remaining <= 0:
                break
            parsed = await loop.run_in_executor(
                None, _sync_extract_cell_range, content, sheet_name, r1, c1, r2, c2, remaining
            )
            if "error" in parsed:
                return {"rows": [], "columns": [], "total": 0, "error": parsed["error"]}
            used_sheet = parsed.get("sheet_name", used_sheet)
            if parsed.get("has_unresolved_formula"):
                any_unresolved = True
            for cell_row in parsed["rows"]:
                idx += 1
                row_obj = {
                    "index": idx,
                    "wp_code": wp_code,
                    "sheet_name": used_sheet,
                    "cell_ref": cell_row["cell_ref"],
                    "value": cell_row["value"],
                }
                if "formula" in cell_row:
                    row_obj["formula"] = cell_row["formula"]
                all_rows.append(row_obj)
                if idx >= MAX_TOTAL:
                    break

        # 公式还原：检测到未求值公式 → 在临时副本上调 LibreOffice 重算，读回字节再取一次（原文件不动）
        recomputed = False
        warnings: list[str] = []
        if any_unresolved:
            new_content = await loop.run_in_executor(None, recompute_with_libreoffice, storage_path)
            if new_content is None:
                warnings.append(RECOMPUTE_FAILED_WARNING)
            else:
                recomputed = True
                value_map: dict[str, Any] = {}
                for (r1, c1, r2, c2) in ranges:
                    parsed2 = await loop.run_in_executor(
                        None, _sync_extract_cell_range, new_content, sheet_name, r1, c1, r2, c2, MAX_TOTAL
                    )
                    if "error" in parsed2:
                        continue
                    for cell_row in parsed2["rows"]:
                        value_map[cell_row["cell_ref"]] = cell_row["value"]
                for row_obj in all_rows:
                    cref = row_obj.get("cell_ref")
                    if cref and cref in value_map and row_obj.get("formula"):
                        new_v = value_map[cref]
                        if new_v != "":
                            row_obj["value"] = new_v

        result_columns = ["index", "wp_code", "sheet_name", "cell_ref", "value"]
        if any(("formula" in r) for r in all_rows):
            result_columns.append("formula")
        return {
            "rows": all_rows,
            "columns": result_columns,
            "total": len(all_rows),
            "source": "xlsx_recomputed" if recomputed else "xlsx_cache",
            "formula_recomputed": recomputed,
            "warnings": warnings,
        }
    except Exception as e:
        logger.warning("cell_range extract failed for %s/%s: %s", wp_code, cell_range, e)
        return {"rows": [], "columns": [], "total": 0, "error": f"解析失败: {e}"}


def _try_extract_from_univer_snapshot(parsed_data: dict, sheet_name: str | None, ranges: list, wp_code: str) -> list[dict] | None:
    """从 working_paper.parsed_data['univer_snapshot'] 直接提取，零计算

    返回 None 表示快路径不可用（无 snapshot 或 sheet 不存在），让上层走 xlsx fallback
    """
    if not isinstance(parsed_data, dict):
        return None
    snapshot = parsed_data.get("univer_snapshot")
    if not isinstance(snapshot, dict):
        return None
    sheets_map = snapshot.get("sheets") or {}
    if not sheets_map:
        return None
    # 选 sheet：优先精确匹配 sheet_name，否则取第一个（与 _sync_extract_cell_range 行为一致）
    target_sheet_name = None
    if sheet_name and sheet_name in sheets_map:
        target_sheet_name = sheet_name
    else:
        order = snapshot.get("sheet_order_names") or list(sheets_map.keys())
        target_sheet_name = order[0] if order else None
    if not target_sheet_name:
        return None
    sheet_obj = sheets_map.get(target_sheet_name) or {}
    cell_data = sheet_obj.get("cellData") or {}
    if not isinstance(cell_data, dict):
        return None
    # snapshot 用 0-indexed (与 Univer 一致)，cell_range 解析后 ranges 是 1-indexed
    out_rows: list[dict] = []
    idx = 0
    MAX_TOTAL = 500
    for (r1, c1, r2, c2) in ranges:
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                idx += 1
                if idx > MAX_TOTAL:
                    break
                # cell_ref
                col_letters = ""
                cc = c
                while cc > 0:
                    cc, rem = divmod(cc - 1, 26)
                    col_letters = chr(65 + rem) + col_letters
                cell_ref = f"{col_letters}{r}"
                # 取值（snapshot 0-indexed: row=r-1, col=c-1）
                row_obj = cell_data.get(str(r - 1)) or {}
                cell = row_obj.get(str(c - 1)) if isinstance(row_obj, dict) else None
                v = ""
                f_str = ""
                if isinstance(cell, dict):
                    cv = cell.get("v")
                    if cv is None or cv == "":
                        v = ""
                    elif isinstance(cv, (int, float)):
                        v = cv
                    else:
                        v = str(cv)
                    if cell.get("f"):
                        f_str = str(cell["f"])
                row_dict: dict = {
                    "index": idx,
                    "wp_code": wp_code,
                    "sheet_name": target_sheet_name,
                    "cell_ref": cell_ref,
                    "value": v,
                }
                if f_str:
                    row_dict["formula"] = f_str
                out_rows.append(row_dict)
            if idx >= MAX_TOTAL:
                break
        if idx >= MAX_TOTAL:
            break
    return out_rows


def _parse_cell_ranges(spec: str) -> list[tuple[int, int, int, int]]:
    """解析 cell_range 字符串为 (r1, c1, r2, c2) 元组列表（1-indexed）

    支持：
      - 'A1:C3'    → [(1, 1, 3, 3)]
      - 'B5'       → [(5, 2, 5, 2)]
      - 'A1:A10,C1:C5' → [(1, 1, 10, 1), (1, 3, 5, 3)]
      - 'A:A'      → [(1, 1, 100, 1)]  整列限 100 行
      - 'A:C'      → [(1, 1, 100, 3)]
    """
    import re as _re
    INTEGER_COL_LIMIT = 100  # 整列默认行数上限

    def _col_to_idx(s: str) -> int:
        n = 0
        for ch in s:
            n = n * 26 + (ord(ch) - 64)
        return n

    out: list[tuple[int, int, int, int]] = []
    for part in spec.split(","):
        part = part.strip().upper()
        if not part:
            continue
        # 单 cell 'B5'
        m = _re.match(r"^([A-Z]+)(\d+)$", part)
        if m:
            col = _col_to_idx(m.group(1)); r = int(m.group(2))
            out.append((r, col, r, col))
            continue
        # 整列 'A:A' / 'A:C'
        m = _re.match(r"^([A-Z]+):([A-Z]+)$", part)
        if m:
            c1 = _col_to_idx(m.group(1)); c2 = _col_to_idx(m.group(2))
            out.append((1, min(c1, c2), INTEGER_COL_LIMIT, max(c1, c2)))
            continue
        # 矩形 'A1:C3'
        m = _re.match(r"^([A-Z]+)(\d+):([A-Z]+)(\d+)$", part)
        if m:
            c1 = _col_to_idx(m.group(1)); r1 = int(m.group(2))
            c2 = _col_to_idx(m.group(3)); r2 = int(m.group(4))
            out.append((min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2)))
            continue
    return out
