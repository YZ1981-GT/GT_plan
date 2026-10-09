"""Pure header projection shared by the API, formula configuration and Word.

Rows and formula/manual/locked coordinates stay in their original storage domain.
``header_rows`` uses the existing Word fill_multi_header cell contract.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


def header_cells(header_rows: list[list[dict]], width: int) -> list[tuple[int, int, dict]]:
    """Place compact header cells, skipping columns occupied by a rowspan."""
    occupied = [[False] * width for _ in header_rows]
    placed = []
    for r, row in enumerate(header_rows):
        cursor = 0
        for cell in row:
            while cursor < width and occupied[r][cursor]:
                cursor += 1
            cs, rs = cell.get("colspan", 1), cell.get("rowspan", 1)
            if any(type(n) is not int or n < 1 for n in (cs, rs)):
                raise ValueError("Invalid header span")
            if cursor + cs > width or r + rs > len(header_rows):
                raise ValueError("Header span exceeds declared columns or rows")
            if any(occupied[rr][cc] for rr in range(r, r + rs) for cc in range(cursor, cursor + cs)):
                raise ValueError("Overlapping header spans")
            placed.append((r, cursor, {"text": str(cell.get("text", "")), "colspan": cs, "rowspan": rs}))
            for rr in range(r, r + rs):
                for cc in range(cursor, cursor + cs):
                    occupied[rr][cc] = True
            cursor += cs
    if any(not value for row in occupied for value in row):
        raise ValueError("Header does not cover every declared column")
    return placed


def multi_header_rows(multi_header: list[list[str]], width: int) -> list[list[dict]]:
    """Partition each parent range before interpreting blanks as horizontal merges."""
    grid = [[str(row[c] or "") if c < len(row) else "" for c in range(width)] for row in multi_header]
    out: list[list[dict]] = [[] for _ in grid]

    def visit(r: int, start: int, end: int) -> None:
        anchors = [start] + [c for c in range(start + 1, end) if grid[r][c].strip()]
        for i, c in enumerate(anchors):
            stop = anchors[i + 1] if i + 1 < len(anchors) else end
            leaf = all(not grid[rr][cc].strip() for rr in range(r + 1, len(grid)) for cc in range(c, stop))
            out[r].append({"text": grid[r][c], "colspan": stop - c, "rowspan": len(grid) - r if leaf else 1})
            if not leaf:
                visit(r + 1, c, stop)

    if grid and width:
        visit(0, 0, width)
        header_cells(out, width)
    return out


def normalize_consol_note_section(section: dict[str, Any]) -> dict[str, Any]:
    """Return a detached projection; never remove rows or renumber stored cells."""
    out = deepcopy(section)
    headers = out.get("headers") or []
    width = len(headers)
    multi = out.get("multi_header")
    if out.get("header_rows"):
        rows = out["header_rows"]
    elif isinstance(multi, list) and multi:
        rows = multi_header_rows(multi, width)
    elif out.get("_column_groups"):
        top, bottom, cursor = [], [], 0
        groups = sorted(out["_column_groups"], key=lambda g: g["start"])
        for group in groups:
            start, span = group["start"], group["span"]
            for c in range(cursor, start):
                top.append({"text": headers[c], "colspan": 1, "rowspan": 2})
            top.append({"text": group["group"], "colspan": span, "rowspan": 1})
            bottom.extend({"text": str(headers[c]).split("/")[-1], "colspan": 1, "rowspan": 1} for c in range(start, start + span))
            cursor = start + span
        top.extend({"text": headers[c], "colspan": 1, "rowspan": 2} for c in range(cursor, width))
        rows = [top, bottom]
    else:
        rows = [[{"text": text, "colspan": 1, "rowspan": 1} for text in headers]] if width else []
    header_cells(rows, width)
    excluded = out.get("_header_row_indexes") or []
    if (any(type(i) is not int or i < 0 or i >= len(out.get("rows") or []) for i in excluded)
            or len(set(excluded)) != len(excluded)):
        raise ValueError("Invalid configured header row index")
    out["header_rows"] = rows
    out["_header_row_indexes"] = list(excluded)
    out["_body_row_indexes"] = [i for i in range(len(out.get("rows") or [])) if i not in excluded]
    return out
