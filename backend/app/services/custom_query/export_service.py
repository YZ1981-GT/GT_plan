"""ExportService — 高级查询结果导出（advanced-query-module Task 13.1）。

设计对应 design.md §Components 6「ExportService（导出 + 流式，R7/R8）」。

本文件实现 **非流式** ``export_xlsx``（小结果集物化导出，task 13.1）、xlsx 容量守卫
（``EXPORT_CAPACITY``）与 **RFC 5987 文件名编码** ``build_content_disposition``
（task 13.2，中文文件名铁律），以及 **流式导出** ``stream_xlsx``（task 13.3）。

流式导出（task 13.3，R8）要点：

- **仅平铺明细可流式**：``stream_xlsx`` 只服务「明细 / 未透视」的平铺结果集——行数
  > 流式触发阈值（默认 5000，可配）→ ``StreamingResponse`` 生成器分块（默认 1000
  行/块）返回；单次驻留内存的行数限制在配置上限内（默认 1000 行，R8.1/R8.2/R8.3）。
- **分组/透视为物化导出**：分组/透视结果已在内存成型（受 ``PivotEngine`` 512 列 /
  行上限约束），走非流式 ``export_xlsx``，不流式（design §Components 6）。
- **自动择路**：``resolve_export_mode`` 按结果形态择路——透视/分组或小平铺集 →
  物化 ``export_xlsx``；大平铺集 → ``stream_xlsx``（R8.1）。
- **硬上限**：结果集行数 > ``EXPORT_ROW_HARD_LIMIT``（默认 1,000,000，且不超过 xlsx
  单表 1,048,576 行上限）→ 不启动导出，抛 ``EXPORT_ROW_HARD_LIMIT``（R8.4）。
- **中途错误**：流式生成器在物化写盘完成、首个字节 yield 之前完成全部行迭代与容量
  守卫；任一步失败即 ``raise`` 中断（此时尚未 yield 任何字节，不产生可被误认为
  完整的部分文件），由 router 层置 ``X-Export-Incomplete: 1`` 头（R7.7/R8.6）。

openpyxl ``write_only`` 模式的取舍：``ws.append`` 会将行增量写入磁盘临时文件（lxml
``xmlfile`` 流式），不在内存驻留全部行；本实现进一步以 ≤ ``memory_row_cap`` 的缓冲
批量 append，显式约束单次行驻留。最终 ``wb.save`` 落临时文件后，按字节块流式读出
（不将整个 xlsx 载入内存），保证大结果集导出的内存平稳（6000 并发目标）。

复用 ``query_builder.export_excel`` 既有 ``Workbook(write_only=True)`` +
``WriteOnlyCell`` + 分批 append 模式，避免 openpyxl 全量内存峰值：

- 保留列标题文本 / 列顺序 / 分组透视后的行列结构 / 单元格显示值，与界面一致（R7.2）。
- 追加数据来源标识列：对每个携带 addr_id 的可下钻列，导出一列
  ``{addr_id}｜{semantic_label}`` 供离线追溯（R7.4）。
- 0 行 → 仅标题行 + 空提示行（R7.5）。
- 结果集行数 > 1,048,576 或（含来源列的）总列数 > 16,384 → ``EXPORT_CAPACITY``
  (HTTP 400)，中止导出、不返回文件（R7.6）。

``_excel_cell_value`` 与 ``query_builder._excel_cell_value`` 同源（镜像，避免
service → router 反向依赖）：UUID / Decimal / tz-aware datetime / 枚举需转换，
openpyxl 不接受 timezone-aware datetime。

_Requirements: 7.1, 7.2, 7.4, 7.5, 7.6_
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import tempfile
from collections.abc import AsyncIterator
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from urllib.parse import quote
from uuid import UUID

from fastapi import HTTPException

if TYPE_CHECKING:  # 避免运行时循环导入；仅类型标注需要
    from app.services.custom_query.query_orchestrator import ColumnMeta, QueryResult

logger = logging.getLogger(__name__)

# ─── Excel 原生上限（R7.6）──────────────────────────────────────────────────
XLSX_MAX_ROWS = 1_048_576
XLSX_MAX_COLS = 16_384

# 每批写入行数（复用 query_builder 分批 append 模式，避免峰值）
_EXPORT_APPEND_BATCH = 2000

# ─── 流式导出参数（R8）──────────────────────────────────────────────────────
# 流式触发阈值：平铺明细结果行数 > 此值 → 走 stream_xlsx（R8.1，默认 5000，可配）
STREAM_ROW_THRESHOLD = 5000
# 每块行数：StreamingResponse 分块粒度（R8.2，默认 1000）
STREAM_CHUNK_ROWS = 1000
# 单次驻留内存的行数上限（R8.3，默认 1000）——append 缓冲不超过此值
STREAM_MEMORY_ROW_CAP = 1000
# 导出硬上限：> 此行数不启动导出（R8.4，默认 1,000,000，< xlsx 1,048,576 上限）
EXPORT_ROW_HARD_LIMIT = 1_000_000
# 字节流分块大小（从落盘 xlsx 按块读出，避免整文件载入内存）
_STREAM_BYTE_CHUNK = 64 * 1024

# 导出模式（resolve_export_mode 返回值）
EXPORT_MODE_MATERIALIZED = "materialized"  # 非流式：透视/分组 或 小平铺集
EXPORT_MODE_STREAM = "stream"              # 流式：大平铺明细集

# 空结果提示（R7.5）
_EMPTY_NOTICE = "（查询结果为空）"

# ASCII 回退文件名（RFC 5987，供不支持 filename* 的老客户端；R7.3）
_ASCII_FALLBACK_FILENAME = "query.xlsx"


def _excel_cell_value(v: Any) -> Any:
    """Excel cell 接受 str/number/datetime；UUID/Decimal/枚举要转换。

    镜像自 ``query_builder._excel_cell_value``。openpyxl 不支持 timezone-aware
    datetime（会抛 TypeError），PG ``timestamptz`` 字段带 tzinfo，必须显式 strip。
    """
    if v is None:
        return None
    if isinstance(v, bool):  # bool 是 int 子类，需先于 Decimal/number 判定保留原值
        return v
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, datetime):
        # strip tzinfo（保持壁钟时间，符合用户本地化预期）
        return v.replace(tzinfo=None) if v.tzinfo is not None else v
    if isinstance(v, date):
        return v
    if isinstance(v, UUID):
        return str(v)
    if hasattr(v, "value") and not isinstance(v, (str, int, float, bool)):
        return v.value
    return v


def _source_identity_value(col: "ColumnMeta") -> str:
    """数据来源标识列的值：``{addr_id}｜{semantic_label}``（R7.4）。"""
    label = col.semantic_label or col.title or col.addr_id or ""
    return f"{col.addr_id}｜{label}" if col.addr_id else ""


def _row_export_values(
    row: dict,
    columns: list["ColumnMeta"],
    source_cols: list["ColumnMeta"],
) -> list[Any]:
    """按列顺序取一行的显示值 + 追加数据来源标识值（R7.2/R7.4）。

    与非流式 ``export_xlsx`` 数据行构造同源，保证流式与非流式对同一结果集的行内容
    完全一致（R8.5 model-based）。
    """
    values = [_excel_cell_value(row.get(c.key)) for c in columns]
    values += [_source_identity_value(c) for c in source_cols]
    return values


class ExportService:
    """高级查询结果导出器（非流式 export_xlsx，task 13.1）。

    仅负责把已在内存成型的 ``QueryResult``（含分组/透视后形态）物化为 ``.xlsx``
    字节流；不做寻址/权限/取数（那些在上游编排链完成）。
    """

    async def export_xlsx(self, result: "QueryResult") -> bytes:
        """将查询结果导出为 ``.xlsx`` 字节流（非流式，小结果集物化）。

        步骤：
        1. 容量守卫（R7.6）：结果集行数 > 1,048,576 或总列数（含来源列）> 16,384
           → ``EXPORT_CAPACITY`` (HTTP 400)，不返回文件。
        2. 表头（R7.2）：按 ``result.columns`` 顺序写标题 + 追加数据来源标识列（R7.4）。
        3. 数据行（R7.2）：按列顺序写显示值 + 追加来源标识值。
        4. 0 行（R7.5）：仅标题行 + 空提示行。

        返回 ``.xlsx`` 文件的原始字节（``bytes``）。
        """
        columns = list(result.columns)

        # 可下钻列 → 追加数据来源标识列（R7.4）
        source_cols = [c for c in columns if getattr(c, "addr_id", None)]
        total_cols = len(columns) + len(source_cols)

        # ── step1: 容量守卫（R7.6）——在物化大列表之前先行拦截 ──────────
        row_count = len(result.rows)
        if row_count > XLSX_MAX_ROWS or total_cols > XLSX_MAX_COLS:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "EXPORT_CAPACITY",
                    "message": (
                        "结果集超出 Excel 原生上限（"
                        f"{XLSX_MAX_ROWS:,} 行 / {XLSX_MAX_COLS:,} 列），"
                        "已中止导出，请缩小查询范围"
                    ),
                    "actual_rows": row_count,
                    "actual_cols": total_cols,
                    "max_rows": XLSX_MAX_ROWS,
                    "max_cols": XLSX_MAX_COLS,
                },
            )

        return self._build_workbook_bytes(columns, source_cols, list(result.rows))

    # ── RFC 5987 文件名编码（R7.3）────────────────────────────────────────
    def build_content_disposition(self, display_name: str) -> str:
        """构造 RFC 5987 编码的 ``Content-Disposition`` 头值（R7.3）。

        平台铁律「StreamingResponse 中文文件名必须 RFC5987 编码」：非 ASCII
        （含中文）文件名若不编码，浏览器无法正确还原，甚至丢弃响应。返回形如::

            attachment; filename="query.xlsx"; filename*=UTF-8''<percent-encoded>

        - ``filename="query.xlsx"``：纯 ASCII 回退名，供不支持 ``filename*`` 的老客户端。
        - ``filename*=UTF-8''...``：RFC 5987 百分号编码的真实名，含中文可正确解码还原。

        ``quote(name, safe="")`` 对 attr-char 集合之外的所有字符（含空格、``/``、
        中文字节）逐字节百分号编码，保证头值合法且可 round-trip 解码（P13）。
        """
        name = (display_name or "").strip() or _ASCII_FALLBACK_FILENAME
        fn_utf8 = quote(name, safe="")
        return (
            f'attachment; filename="{_ASCII_FALLBACK_FILENAME}"; '
            f"filename*=UTF-8''{fn_utf8}"
        )

    # ── 流式导出（task 13.3，R8）──────────────────────────────────────────
    def resolve_export_mode(
        self,
        *,
        row_count: int,
        materialized: bool,
        stream_threshold: int = STREAM_ROW_THRESHOLD,
        row_hard_limit: int = EXPORT_ROW_HARD_LIMIT,
    ) -> str:
        """按结果形态自动择路：``materialized`` 或 ``stream``（R8.1/R8.4）。

        - **硬上限先行**（R8.4）：``row_count > row_hard_limit``（默认 1,000,000）→
          抛 ``EXPORT_ROW_HARD_LIMIT``、不启动导出。router 在创建 StreamingResponse
          **之前**调用本方法完成预检（避免流已开始才发现超限）。
        - **透视/分组 = 物化**（design §Components 6）：``materialized=True`` 的结果已
          在内存成型（受 PivotEngine 512 列 / 行上限约束），一律走非流式
          ``export_xlsx``，不流式。
        - **平铺明细**：``row_count > stream_threshold``（默认 5000）→ ``stream``；
          否则小结果集仍走物化 ``export_xlsx``。

        返回 :data:`EXPORT_MODE_MATERIALIZED` 或 :data:`EXPORT_MODE_STREAM`。
        """
        if row_count > row_hard_limit:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "EXPORT_ROW_HARD_LIMIT",
                    "message": (
                        f"结果集行数 {row_count:,} 超出导出硬上限 "
                        f"{row_hard_limit:,} 行，已中止导出，请缩小查询范围"
                    ),
                    "actual_rows": row_count,
                    "row_hard_limit": row_hard_limit,
                },
            )
        if materialized:
            return EXPORT_MODE_MATERIALIZED
        if row_count > stream_threshold:
            return EXPORT_MODE_STREAM
        return EXPORT_MODE_MATERIALIZED

    async def stream_xlsx(
        self,
        result_iter: Any,
        columns: list["ColumnMeta"],
        *,
        chunk_rows: int = STREAM_CHUNK_ROWS,
        memory_row_cap: int = STREAM_MEMORY_ROW_CAP,
        row_hard_limit: int = EXPORT_ROW_HARD_LIMIT,
        byte_chunk: int = _STREAM_BYTE_CHUNK,
    ) -> AsyncIterator[bytes]:
        """流式导出平铺明细结果集为 ``.xlsx`` 字节块（异步生成器，R8）。

        ``result_iter`` 为**平铺明细**行的可迭代对象（同步或异步均可），每项为一行
        ``dict``（键为 ``ColumnMeta.key``），或一批行的 ``list[dict]``；由
        :meth:`_aiter_rows` 归一为逐行异步流。**不接受**分组/透视结果（那些走物化
        ``export_xlsx``，见 :meth:`resolve_export_mode`）。

        流程（R8.1/R8.2/R8.3/R8.4/R8.6/R7.7）：
        1. 容量守卫：含来源列的总列数 > 16,384 → ``EXPORT_CAPACITY``（首字节前）。
        2. write_only 工作簿写表头 + 数据来源标识列表头（R7.4）。
        3. 以 ≤ ``memory_row_cap`` 的缓冲批量 ``append``，行随即增量写入磁盘临时文件，
           单次行驻留受限（R8.3）；逐行计数，超 ``row_hard_limit`` / xlsx 行上限 →
           首字节前 ``raise``（不产生部分文件，R8.4/R7.6）。
        4. ``wb.save`` 落临时文件（executor 内执行），按 ``byte_chunk`` 字节块流式
           读出并 ``yield``（R8.2）；读毕删除临时文件。

        **中途错误**（R7.7/R8.6）：步骤 1–3 的任一失败都在 **首个字节 yield 之前**
        发生，直接 ``raise`` 中断——此时未产出任何字节，客户端不会得到可被误认为完整
        的文件；router 层据此置 ``X-Export-Incomplete: 1``。

        **一致性**（R8.5）：数据行经 :func:`_row_export_values` 构造，与非流式
        ``export_xlsx`` 同源，保证流式与物化对同一结果集的行内容逐行一致。
        """
        from openpyxl import Workbook

        columns = list(columns)
        source_cols = [c for c in columns if getattr(c, "addr_id", None)]
        total_cols = len(columns) + len(source_cols)

        # ── step1: 容量守卫（列，R7.6）——首字节前拦截 ──
        if total_cols > XLSX_MAX_COLS:
            raise HTTPException(
                status_code=400,
                detail={
                    "error_code": "EXPORT_CAPACITY",
                    "message": (
                        f"结果集列数（含来源列 {total_cols}）超出 Excel 原生上限 "
                        f"{XLSX_MAX_COLS:,} 列，已中止导出"
                    ),
                    "actual_cols": total_cols,
                    "max_cols": XLSX_MAX_COLS,
                },
            )

        wb = Workbook(write_only=True)
        ws = wb.create_sheet(title="高级查询结果"[:31])

        # ── step2–4: 构建并落临时文件（首字节 yield 之前完成，中途错误在此 raise）──
        # 任一步失败（容量守卫 / 行迭代 / 硬上限 / 落盘）都在产出任何字节前发生，直接
        # raise 中断；此处兜底 close 工作簿以释放 openpyxl write_only 内部 lxml 写入器
        # 与其自建临时文件，避免中途 raise 时的资源泄漏（R7.7/R8.6）。
        try:
            # step2: 表头
            ws.append(self._header_cells(ws, columns, source_cols))

            # step3: 逐行 append（缓冲 ≤ memory_row_cap，行驻留受限 R8.3）
            buffer: list[list[Any]] = []
            cap = max(1, min(memory_row_cap, chunk_rows))
            row_count = 0
            async for row in self._aiter_rows(result_iter):
                row_count += 1
                # 硬上限 / xlsx 行上限守卫（首字节前，R8.4/R7.6）——防御式，即便 total 未知
                if row_count > row_hard_limit:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error_code": "EXPORT_ROW_HARD_LIMIT",
                            "message": (
                                f"结果集行数超出导出硬上限 {row_hard_limit:,} 行，"
                                "已中止导出，请缩小查询范围"
                            ),
                            "row_hard_limit": row_hard_limit,
                        },
                    )
                if row_count > XLSX_MAX_ROWS:
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error_code": "EXPORT_CAPACITY",
                            "message": (
                                f"结果集行数超出 Excel 原生上限 {XLSX_MAX_ROWS:,} 行，"
                                "已中止导出"
                            ),
                            "max_rows": XLSX_MAX_ROWS,
                        },
                    )
                buffer.append(_row_export_values(row, columns, source_cols))
                if len(buffer) >= cap:
                    for values in buffer:
                        ws.append(values)
                    buffer.clear()

            # flush 剩余缓冲
            for values in buffer:
                ws.append(values)
            buffer.clear()

            # 空结果 → 仅标题行 + 空提示行（R7.5，防御式；流式通常不用于空集）
            if row_count == 0:
                ws.append([_EMPTY_NOTICE])

            # step4: 落临时文件（executor 内执行 openpyxl 保存）
            loop = asyncio.get_event_loop()
            tmp_path = await loop.run_in_executor(None, self._save_to_tempfile, wb)
        except BaseException:
            # 中途中断：best-effort 释放 write_only 内部写入器/临时文件后上抛
            self._safe_close_workbook(wb)
            raise

        # ── 按字节块流式读出并 yield（内存驻留仅一块）──
        try:
            for chunk in self._iter_file_bytes(tmp_path, byte_chunk):
                yield chunk
        finally:
            try:
                os.remove(tmp_path)
            except OSError:  # pragma: no cover - 清理尽力而为
                logger.warning("流式导出临时文件清理失败: %s", tmp_path)

    async def _aiter_rows(self, result_iter: Any) -> AsyncIterator[dict]:
        """将 ``result_iter`` 归一为逐行异步流。

        支持：异步可迭代（``__aiter__``，如 DB 游标）或同步可迭代（``list`` /
        生成器）；每项可为单行 ``dict`` 或一批行的 ``list[dict]``（自动展平）。
        """

        def _emit(item: Any) -> list[dict]:
            # 一批行（list/tuple 且非 dict）→ 展平；单行 dict → 单元素
            if isinstance(item, dict):
                return [item]
            if isinstance(item, (list, tuple)):
                return [r for r in item if isinstance(r, dict)]
            return []

        if hasattr(result_iter, "__aiter__"):
            async for item in result_iter:
                for row in _emit(item):
                    yield row
        else:
            for item in result_iter:
                for row in _emit(item):
                    yield row

    # ── 内部：构建 write_only 工作簿 ──────────────────────────────────────
    @staticmethod
    def _header_cells(
        ws: Any,
        columns: list["ColumnMeta"],
        source_cols: list["ColumnMeta"],
    ) -> list[Any]:
        """构造 write_only 表头单元格：列标题 + 数据来源标识列表头（R7.2/R7.4）。"""
        from openpyxl.cell import WriteOnlyCell
        from openpyxl.styles import Alignment, Font, PatternFill

        header_font = Font(bold=True)
        header_fill = PatternFill(
            start_color="F0EDF5", end_color="F0EDF5", fill_type="solid"
        )
        header_alignment = Alignment(horizontal="center")

        def _header_cell(text: str) -> Any:
            cell = WriteOnlyCell(ws, value=text)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
            return cell

        cells = [_header_cell(c.title) for c in columns]
        cells += [_header_cell(f"{c.title}·来源(addr_id)") for c in source_cols]
        return cells

    def _build_workbook_bytes(
        self,
        columns: list["ColumnMeta"],
        source_cols: list["ColumnMeta"],
        rows: list[dict],
    ) -> bytes:
        """复用 ``Workbook(write_only=True)`` + ``WriteOnlyCell`` 逐批 append。"""
        from openpyxl import Workbook

        wb = Workbook(write_only=True)
        ws = wb.create_sheet(title="高级查询结果"[:31])

        # ── step2: 表头（write_only 模式通过 WriteOnlyCell 设置样式）──
        ws.append(self._header_cells(ws, columns, source_cols))

        # ── step4: 0 行 → 仅标题行 + 空提示行（R7.5）──
        if not rows:
            notice_row: list[Any] = [_EMPTY_NOTICE]
            # 其余单元格留空，保持与标题行同宽不是必须（openpyxl 允许不等长）
            ws.append(notice_row)
            return self._save_bytes(wb)

        # ── step3: 数据行（保留列顺序与显示值，R7.2）──
        n = len(rows)
        for start in range(0, n, _EXPORT_APPEND_BATCH):
            batch = rows[start : start + _EXPORT_APPEND_BATCH]
            for row in batch:
                ws.append(_row_export_values(row, columns, source_cols))

        return self._save_bytes(wb)

    @staticmethod
    def _save_bytes(wb: Any) -> bytes:
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output.getvalue()

    @staticmethod
    def _safe_close_workbook(wb: Any) -> None:
        """best-effort 释放 write_only 工作簿内部 lxml 写入器与自建临时文件。

        openpyxl 的 ``write_only`` 模式不支持「中途放弃」：``WriteOnlyWorksheet`` 首次
        ``append`` 即启动一个挂起的 lxml 增量写入器并占用一份每-worksheet 临时文件；
        若在 ``save`` 之前中断并直接丢弃，挂起的写入器不会关闭，Windows 上其临时文件
        句柄保持打开、无法删除（``WinError 32``），并在 GC/atexit 时抛 lxml
        "inconsistent exit" 噪声。

        正确的释放办法是让 openpyxl **完成写出**（``save`` 到一个一次性 scratch 文件，
        从而正常闭合 lxml 元素上下文、关闭内部写入器与临时文件），随即删除该产物。
        ``save`` 若因状态损坏失败，则回退 ``close``。全程吞掉清理异常，不掩盖原始异常。
        """
        scratch: str | None = None
        try:
            fd, scratch = tempfile.mkstemp(suffix=".xlsx", prefix="aqm_abort_")
            os.close(fd)
            wb.save(scratch)  # 完成 lxml context → 关闭内部写入器/临时文件
        except Exception:  # noqa: BLE001 - 清理尽力而为
            try:
                wb.close()
            except Exception:  # noqa: BLE001
                pass
        finally:
            if scratch:
                try:
                    os.remove(scratch)
                except OSError:  # pragma: no cover - 清理尽力而为
                    pass

    @staticmethod
    def _save_to_tempfile(wb: Any) -> str:
        """将 write_only 工作簿保存到磁盘临时文件，返回路径（供分块读出）。

        write_only + 落盘避免将整个 xlsx 字节载入内存，配合按字节块读出保证大结果集
        流式导出的内存平稳（R8.3）。
        """
        fd, path = tempfile.mkstemp(suffix=".xlsx", prefix="aqm_export_")
        os.close(fd)
        wb.save(path)
        return path

    @staticmethod
    def _iter_file_bytes(path: str, byte_chunk: int):
        """按 ``byte_chunk`` 字节块读出文件（内存驻留仅一块）。"""
        with open(path, "rb") as fh:
            while True:
                chunk = fh.read(byte_chunk)
                if not chunk:
                    break
                yield chunk


# 模块级单例（与同包 addressing_service / ownership_guard / query_cache 一致）
export_service = ExportService()
