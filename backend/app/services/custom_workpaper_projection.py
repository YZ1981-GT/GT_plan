"""自定义底稿（componentType=custom）的 xlsx → parsed_data 投影单一入口。

## 架构口径（用户 2026-08-06 拍板）

**xlsx 文件是唯一权威，`parsed_data.html_data[sheet]` 是它的投影。**

自定义底稿是自由网格，HTML 侧与 OnlyOffice 侧编的是**同一批单元格**，故不能照抄
标准循环底稿的「两侧各存一份」范式（那些底稿 HTML 侧是结构化表单、与 xlsx 网格编
的不是同一批东西）。

## 🔴 为什么不复用 `wp_grid_extract.extract_grid`

立项时假设「`extract_grid` 键集正好覆盖 `GtGridSheet`，投影层无需新造」。
2026-08-06 探针实测**两处不成立**：

1. **它重编行号** —— `extract_grid_from_sheet` 内 `row_offset = data_start_row - 1`，
   `new_coord = f"{_col_letter(c)}{new_r}"`。实测：xlsx `B6=123.45` 投影成 **`B2`**
   （列不变，只有行位移）。若据此做「HTML 编辑写回 xlsx」，用户改投影 `B2` 会被
   写进 xlsx `B2`（表头区）**覆盖别的单元格**；且 `data_start_row` 是启发式
   （首个含「项目」/「序号」的行），会随用户录入内容**跳变** ⇒ 同一投影坐标在两次
   加载之间指向不同 xlsx 行。
2. **空/失败路径只返 5 键** —— 缺 `header_rows` / `column_meta`。

`extract_grid` 有 11 个既有调用方依赖其现行为（重编号对**只读**渲染是有意设计：
剥掉表头区让数据表从第 1 行开始），故它**保持零改动**。

本模块另提供**恒等坐标**投影：不剥表头、不重编行号、不裁空列 ⇒ 投影 `B6` ≡ xlsx `B6`。
恒等坐标顺带消掉第三个隐患：`wp_formula.target_cell` 究竟是投影坐标还是 xlsx 坐标
的歧义（两者相等则该歧义不存在）。

spec: .kiro/specs/custom-workpaper-dual-mode-formula-and-batch/ Wave 1 / Wave 2
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

logger = logging.getLogger(__name__)

#: 单次扫描的最大行/列（防超大 sheet 把 render-config 拖垮）
MAX_SCAN_ROWS = 500
MAX_SCAN_COLS = 100

#: `GtGridSheet` 的硬依赖键集（前端 `hasData` 与渲染分支消费）。
#: 🔴 守卫按此断言投影输出键集 ⊇ 该集合；改动须同步前端守卫。
GRID_REQUIRED_KEYS: frozenset[str] = frozenset(
    {"cells", "max_row", "max_col", "col_widths", "merged_cells", "header_rows"}
)


def _col_letter(c: int) -> str:
    """列号(1-based) → 字母（1→A, 26→Z, 27→AA）。"""
    s = ""
    while c > 0:
        c, rem = divmod(c - 1, 26)
        s = chr(65 + rem) + s
    return s


def col_letter_to_index(letters: str) -> int:
    """列字母 → 1-based 列号（"A"→1, "AA"→27）。非法返回 0。"""
    n = 0
    for ch in letters.upper():
        if not ("A" <= ch <= "Z"):
            return 0
        n = n * 26 + (ord(ch) - 64)
    return n


def parse_cell_ref(cell_ref: str) -> tuple[int, int]:
    """单元格引用 → (row, col)，均 1-based，与 openpyxl 一致。

    非法引用返回 `(0, 0)`（调用方据此跳过，不抛异常）。
    支持 `$B$5` 绝对引用与小写。
    """
    if not cell_ref:
        return (0, 0)
    raw = str(cell_ref).strip().upper().replace("$", "")
    letters = ""
    digits = ""
    for ch in raw:
        if "A" <= ch <= "Z":
            if digits:  # 字母出现在数字之后 → 非法（如 "B5C"）
                return (0, 0)
            letters += ch
        elif ch.isdigit():
            digits += ch
        else:
            return (0, 0)
    if not letters or not digits:
        return (0, 0)
    col = col_letter_to_index(letters)
    try:
        row = int(digits)
    except ValueError:
        return (0, 0)
    if row <= 0 or col <= 0:
        return (0, 0)
    return (row, col)


def normalize_cell_ref(cell_ref: str) -> str | None:
    """归一化单元格引用（`b5` / `$B$5` → `B5`）。非法返回 None。"""
    row, col = parse_cell_ref(cell_ref)
    if row == 0 or col == 0:
        return None
    return f"{_col_letter(col)}{row}"


def ensure_grid_bounds(grid: dict[str, Any]) -> dict[str, Any]:
    """按 `cells` 的键补齐 `max_row` / `max_col`（返回新 dict，不改入参）。

    🔴 为什么必需：`GtGridSheet.hasData = Object.keys(cells).length > 0 && maxRow > 0`。
    只写 `cells` 不维护 `max_row` 的路径（改造前的 `write_cell_to_parsed_data`）会让
    网格**恒显示「此表格底稿模板暂无内容」**。

    🔴 只增不减（单调）：删公式不缩边界，避免把用户其他内容挤出可见范围。
    """
    out = dict(grid or {})
    cells = out.get("cells")
    if not isinstance(cells, dict):
        cells = {}
        out["cells"] = cells

    try:
        cur_row = int(out.get("max_row") or 0)
    except (TypeError, ValueError):
        cur_row = 0
    try:
        cur_col = int(out.get("max_col") or 0)
    except (TypeError, ValueError):
        cur_col = 0

    for ref in cells:
        r, c = parse_cell_ref(str(ref))
        if r > cur_row:
            cur_row = r
        if c > cur_col:
            cur_col = c

    out["max_row"] = cur_row
    out["max_col"] = cur_col
    # 键集完整性兜底（fail-open 路径也必须齐备，否则守卫在该路径必红）
    out.setdefault("col_widths", {})
    out.setdefault("merged_cells", [])
    out.setdefault("header_rows", 0)
    return out


def empty_grid() -> dict[str, Any]:
    """空网格（键集齐备）。文件缺失/解析失败时返回它，绝不返回 None 形态的半成品。"""
    return {
        "cells": {},
        "max_row": 0,
        "max_col": 0,
        "col_widths": {},
        "merged_cells": [],
        "header_rows": 0,
    }


def _is_accounting_format(numfmt: str | None) -> bool:
    if not numfmt:
        return False
    return "#,##0" in numfmt or "0.00" in numfmt


def _extract_identity_grid(ws: Any) -> dict[str, Any]:
    """从 openpyxl worksheet 提取**恒等坐标**网格（纯函数，无 DB、无 IO）。

    与 `wp_grid_extract.extract_grid_from_sheet` 的差异（有意为之）：
    - **不剥表头区**、**不重编行号** ⇒ 投影坐标 == xlsx 坐标
    - **不裁空列**（列号即 xlsx 列号）
    - 公式格保留 `formula` 原文供只读展示，`v` 取缓存值

    单元格形态 `{"v": 值, "r": 行, "c": 列, "style": {...}}`，与既有网格消费方同构。
    """
    max_row = min(int(ws.max_row or 0), MAX_SCAN_ROWS)
    max_col = min(int(ws.max_column or 0), MAX_SCAN_COLS)
    if max_row <= 0 or max_col <= 0:
        return empty_grid()

    cells: dict[str, dict[str, Any]] = {}
    eff_row = 0
    eff_col = 0

    for r in range(1, max_row + 1):
        for c in range(1, max_col + 1):
            cell = ws.cell(row=r, column=c)
            raw = cell.value
            is_formula = isinstance(raw, str) and raw.startswith("=")
            value: Any
            if raw is None:
                value = None
            elif isinstance(raw, (int, float, str)):
                value = raw
            else:
                value = str(raw)

            numeric = _is_accounting_format(cell.number_format)
            has_content = value is not None and value != ""
            if not has_content and not numeric:
                continue

            style: dict[str, Any] = {}
            try:
                font = cell.font
                if font is not None:
                    if font.bold:
                        style["bold"] = True
                    if font.sz:
                        style["font_size"] = float(font.sz)
                    fc = font.color
                    if fc is not None and fc.type == "rgb" and isinstance(fc.rgb, str):
                        rgb = fc.rgb[-6:]
                        if rgb not in ("000000", "FFFFFF"):
                            style["font_color"] = f"#{rgb}"
            except Exception as e:  # pragma: no cover - openpyxl 样式缺失
                logger.debug("提取字体样式失败 %s: %s", f"{_col_letter(c)}{r}", e)
            try:
                if cell.alignment is not None and cell.alignment.horizontal:
                    style["align"] = cell.alignment.horizontal
            except Exception as e:  # pragma: no cover
                logger.debug("提取对齐样式失败: %s", e)
            if numeric:
                style["numeric"] = True

            entry: dict[str, Any] = {
                "v": "" if not has_content else (None if is_formula else value),
                "r": r,
                "c": c,
                "style": style,
            }
            if is_formula:
                # 公式格：保留原文供只读展示（HTML 侧禁编辑公式格）
                entry["formula"] = value
                entry["v"] = ""
            cells[f"{_col_letter(c)}{r}"] = entry
            if r > eff_row:
                eff_row = r
            if c > eff_col:
                eff_col = c

    merged: list[dict[str, Any]] = []
    try:
        for mr in ws.merged_cells.ranges:
            if mr.min_row > eff_row or mr.min_col > eff_col:
                continue
            merged.append(
                {
                    "s": {"r": mr.min_row, "c": mr.min_col},
                    "e": {"r": min(mr.max_row, eff_row), "c": min(mr.max_col, eff_col)},
                }
            )
    except Exception as e:  # pragma: no cover
        logger.debug("提取合并区失败: %s", e)

    col_widths: dict[str, float] = {}
    try:
        for c in range(1, eff_col + 1):
            letter = _col_letter(c)
            dim = ws.column_dimensions.get(letter)
            if dim is not None and dim.width:
                col_widths[letter] = round(float(dim.width), 2)
    except Exception as e:  # pragma: no cover
        logger.debug("提取列宽失败: %s", e)

    return {
        "cells": cells,
        "max_row": eff_row,
        "max_col": eff_col,
        "col_widths": col_widths,
        "merged_cells": merged,
        # 恒等坐标下不剥表头，故 header_rows=0（前端据此不做粘顶表头假设）
        "header_rows": 0,
    }


def project_custom_workpaper(
    file_path: str | Path | None, sheet_name: str
) -> dict[str, Any]:
    """从 xlsx 投影出恒等坐标网格。**自定义底稿投影的唯一入口。**

    Args:
        file_path: xlsx 路径（可为 None）
        sheet_name: 目标 sheet 名。🔴 自定义底稿恒为 `wp_code`
            （`_maybe_custom_classifications` 合成的 `ClassificationResult.sheet_name = wp_code`）

    Returns:
        键集齐备的 grid。文件缺失 / sheet 不存在 / 解析失败 → `empty_grid()` + WARNING
        （fail-open，不抛异常阻断整个 render-config）。
    """
    grid = empty_grid()
    if not file_path or not sheet_name:
        return grid

    fp = Path(file_path)
    if not fp.exists() or fp.stat().st_size == 0:
        logger.warning("custom 投影: xlsx 不存在或为空 %s", fp)
        return grid

    import openpyxl

    wb = None
    try:
        wb = openpyxl.load_workbook(str(fp), read_only=False, data_only=True)
        if sheet_name not in wb.sheetnames:
            logger.warning("custom 投影: sheet 不存在 %s/%s", fp, sheet_name)
            return grid
        return ensure_grid_bounds(_extract_identity_grid(wb[sheet_name]))
    except Exception as e:
        logger.warning("custom 投影失败 %s/%s: %s", fp, sheet_name, e)
        return grid
    finally:
        if wb is not None:
            try:
                wb.close()
            except Exception:  # pragma: no cover
                pass


def grid_has_content(grid: Any) -> bool:
    """网格是否有可渲染内容（与前端 `GtGridSheet.hasData` 同口径）。

    前端：`Object.keys(cells).length > 0 && maxRow > 0`。两侧口径必须一致 ——
    后端判「有内容」而前端判「无内容」会让存量补齐白跑（补了但仍显示空态）。
    """
    if not isinstance(grid, dict):
        return False
    cells = grid.get("cells")
    if not isinstance(cells, dict) or not cells:
        return False
    try:
        return int(grid.get("max_row") or 0) > 0
    except (TypeError, ValueError):
        return False


def project_if_empty(
    wp: Any, sheet_name: str, existing: Any
) -> dict[str, Any]:
    """**存量补齐**：`existing` 无内容时从 xlsx 现投一份（不落库、天然幂等）。

    🔴 为什么必需（R2.6 / Property 13 / Property 22）：`create_custom_workpaper` 的
    建时投影只覆盖**新建**底稿，而库里既有自定义底稿的 `parsed_data` 已经是空的 ——
    不补齐它们永远显示「此表格底稿模板暂无内容」，也就永远选不了公式目标格。

    🔴 **不落库**：render-config 是 GET，不在读端点写库（避免锁竞争与并发写）。
    投影是 xlsx 的派生物，重算成本只在「该底稿确实还是空的」时发生；用户一旦编辑过
    一格（`PUT /custom-cells`）投影就被持久化，此后本函数直接短路返回。

    返回值额外带 `source_unavailable`（仅当投影为空时）：
    - `True`  → xlsx 文件缺失/不可读 ⇒ 前端提示「底稿文件异常，请重新上传」
    - `False` → 文件在但确实是空表 ⇒ 前端提示「空底稿，请录入或切换在线编辑」
    🔴 两者必须可区分（R1.4）：都显示「暂无内容」会让文件损坏被当成正常空表。
    """
    if grid_has_content(existing):
        return existing  # type: ignore[return-value]

    fp = getattr(wp, "file_path", None)
    grid = project_custom_workpaper(fp, sheet_name)
    if not grid.get("cells"):
        grid = dict(grid)
        try:
            grid["source_unavailable"] = not (fp and Path(fp).exists())
        except OSError:  # pragma: no cover - 路径异常按不可用处理
            grid["source_unavailable"] = True
    return grid


def write_projection_to_parsed_data(
    wp: Any, sheet_name: str, grid: dict[str, Any]
) -> None:
    """把投影整块写入 `parsed_data['html_data'][sheet_name]` 并标脏。

    🔴 整块替换而非合并：投影是 xlsx 的派生物，合并会留下 xlsx 里已删除的残留格。
    🔴 必须 `flag_modified` —— JSON/JSONB 列就地改嵌套 dict 不标脏则 UPDATE 不发出
    （平台已记铁律）。
    """
    parsed = dict(wp.parsed_data or {})
    html_data = parsed.get("html_data")
    html_data = dict(html_data) if isinstance(html_data, dict) else {}
    html_data[sheet_name] = ensure_grid_bounds(grid)
    parsed["html_data"] = html_data
    wp.parsed_data = parsed
    flag_modified(wp, "parsed_data")


def refresh_custom_projection(wp: Any, sheet_name: str) -> dict[str, Any]:
    """从 xlsx 重投影并写回 `parsed_data`（三个写入点共用的收口动作）。

    三个写入点：① HTML 格编辑 ② 公式求值回填 ③ OnlyOffice forcesave 落盘。
    全部「先写 xlsx，再调本函数刷投影」。
    """
    grid = project_custom_workpaper(getattr(wp, "file_path", None), sheet_name)
    write_projection_to_parsed_data(wp, sheet_name, grid)
    return grid


def write_cells_to_xlsx(
    file_path: str | Path, sheet_name: str, updates: dict[str, Any]
) -> int:
    """把单元格补丁写入 xlsx 本体（openpyxl）。返回实际写入格数。

    🔴 sheet 不存在时**抛异常不创建** —— 自定义底稿的 sheet 名恒等于 wp_code，
    对不上说明上游有 bug，静默创建会掩盖它。
    🔴 写盘失败**抛异常不 fail-open** —— xlsx 是权威，写不进去就不能向用户报成功。

    Raises:
        FileNotFoundError: 文件不存在
        KeyError: sheet 不存在
        ValueError: 单元格引用非法
    """
    fp = Path(file_path)
    if not fp.exists():
        raise FileNotFoundError(f"底稿文件不存在: {fp}")

    import openpyxl

    wb = openpyxl.load_workbook(str(fp), read_only=False, data_only=False, keep_vba=False)
    try:
        if sheet_name not in wb.sheetnames:
            raise KeyError(f"sheet 不存在: {sheet_name}")
        ws = wb[sheet_name]
        written = 0
        for raw_ref, value in (updates or {}).items():
            ref = normalize_cell_ref(str(raw_ref))
            if ref is None:
                raise ValueError(f"单元格引用非法: {raw_ref}")
            ws[ref] = value
            written += 1
        wb.save(str(fp))
        return written
    finally:
        try:
            wb.close()
        except Exception:  # pragma: no cover
            pass
