"""源 URI 解析 / 序列化与附注虚拟列名。

跨模块单元格级取数（``ModuleCellResolver`` 与 report / note / adj / tb 四个 ``_query_*_cells``）已按
advanced-query-linkage-closure ADR-AQL-13 删除（任务 34，AQ-25）：前端没有任何入口发 ``report:类型|区域`` 这类
源键，业务视图分派现在按未知数据源 400。本模块只留两样仍有调用方的东西：

- ``parse_source_uri`` / ``format_source_uri``：``routers/custom_query.address_resolve`` 解析模板溯源 URI；
- ``_NOTE_COLUMNS``：附注虚拟 sheet 的列名，``snapshot_writer_modules.write_note_cell`` 惰性导入。

Source URI 格式：
  report:{report_type}[|{cell_range}]   — e.g. report:balance_sheet|C5:C10
  note:{section_id}[|{cell_range}]      — e.g. note:五-1-1|C3:D8
  adj:{adjustment_type}[|{cell_range}]  — e.g. adj:aje|B2:E10
  tb:{aux_dim}[|{cell_range}]           — e.g. tb:detail|C1:C50
  workpaper:{wp_code}[|{sheet_name}[|{cell_range}]]
"""

# ─── Source URI 解析 / 序列化 ─────────────────────────────────────────────────

# 支持的模块前缀
_MODULE_PREFIXES = ("report:", "note:", "adj:", "tb:")


def parse_source_uri(source: str) -> dict | None:
    """解析 source URI 为结构化字典。

    Returns:
        {module, qualifier, cell_range} 或 None（无法解析时）

    Examples:
        parse_source_uri("report:balance_sheet|C5:C10")
        → {"module": "report", "qualifier": "balance_sheet", "cell_range": "C5:C10"}

        parse_source_uri("note:五-1-1|C3:D8")
        → {"module": "note", "qualifier": "五-1-1", "cell_range": "C3:D8"}
    """
    if not source or not isinstance(source, str):
        return None

    for prefix in _MODULE_PREFIXES:
        if source.startswith(prefix):
            tail = source[len(prefix):]
            module = prefix.rstrip(":")
            if "|" in tail:
                qualifier, cell_range = tail.split("|", 1)
                return {"module": module, "qualifier": qualifier, "cell_range": cell_range}
            else:
                # 无 cell_range 时 qualifier 是整个 tail
                return {"module": module, "qualifier": tail, "cell_range": None}

    # workpaper: 前缀也支持（兼容）
    if source.startswith("workpaper:"):
        tail = source[len("workpaper:"):]
        parts = tail.split("|")
        if len(parts) == 3:
            return {"module": "workpaper", "qualifier": parts[0], "sheet_name": parts[1], "cell_range": parts[2]}
        elif len(parts) == 2:
            return {"module": "workpaper", "qualifier": parts[0], "sheet_name": parts[1], "cell_range": None}
        else:
            return {"module": "workpaper", "qualifier": tail, "sheet_name": None, "cell_range": None}

    return None


def format_source_uri(parsed: dict) -> str:
    """从结构化字典重新序列化为 source URI 字符串。

    Inverse of parse_source_uri — round-trip property: format(parse(uri)) == uri
    """
    module = parsed.get("module", "")
    qualifier = parsed.get("qualifier", "")
    cell_range = parsed.get("cell_range")

    if module == "workpaper":
        sheet_name = parsed.get("sheet_name")
        if sheet_name and cell_range:
            return f"workpaper:{qualifier}|{sheet_name}|{cell_range}"
        elif sheet_name:
            return f"workpaper:{qualifier}|{sheet_name}"
        else:
            return f"workpaper:{qualifier}"

    if cell_range:
        return f"{module}:{qualifier}|{cell_range}"
    else:
        return f"{module}:{qualifier}"


# ─── 附注虚拟 sheet 列映射（write_note_cell 按此把单元格列号映射到附注行字段） ──────────

_NOTE_COLUMNS = ["code", "name", "year_end", "year_begin", "formula"]
