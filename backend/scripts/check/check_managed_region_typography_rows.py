#!/usr/bin/env python
"""受管区末行「排版占位行」清册 —— BP-21 的取证与验收判据。

**Spec: published-representation-production-path-and-lane-adjudication**（Open Gate 4）
**落地方: excel-structural-row-insertion-and-shift-aware-verification**（`resolve_managed_region`）

═══ 为什么需要这个脚本 ════════════════════════════════════════════════════════

受管区的行范围是**派生**的：`anchor` + `header_rows` 定首行，footer 锚点（「合计」）定末行。
派生规则「表头与合计之间都是数据行」把中文审计模板的**续行省略号**一并吞进受管区：

    A13..A26 = 1..14        整数 seq，合法
    A27      = ……           ← 排版占位，被当成第 15 行业务数据的 seq
    A28      = 合计          footer

后果实测（`fix_projection_first_publication.py --apply`）：H1 首版发布在
`plan_managed_writes` 抛 `EditableCellWriteError` —— 「受管格 A27 的值 '……' 无法按 integer
规范化」。整条首版链被一格排版符号卡住。

契约侧对**列**方向已有先例：`h1.disposal_check.json` 的 `review.excluded_columns` 排除了 X 列，
理由「模板的扩展占位列（表头文本恰为 `……`），没有业务语义」。缺的是**行**方向的对应物。

═══ 本脚本的两个用途 ══════════════════════════════════════════════════════════

1. **取证**（§A 全库清册，BP-21 裁决依据）：这种形态在全模板库有多普遍？逐契约声明排除
   是否可行？**这个数不随修复变化** —— 模板里的 `……` 行还在，变的是它是否落进受管区。
2. **验收**（§B 逐 pilot 受管区扫描，BP-21 落地判据）：现读 `resolve_managed_region` 对每个
   已交付 entry 派生出的受管区，断言区间内不含排版占位行。

🔴 §B 才是验收判据。首版实现只有 §A，`--expect-managed-hits 0` 拿全库清册当验收是**错的**：
那个数恒为 170，修完也不会变，判据永远打红。

用法::

    python backend/scripts/check/check_managed_region_typography_rows.py
    python backend/scripts/check/check_managed_region_typography_rows.py --json out.json

    # BP-21 验收（落地前应为非零 ⇒ 退出码 1；落地后应为 0 ⇒ 退出码 0）
    python backend/scripts/check/check_managed_region_typography_rows.py \
        --expect-managed-region-hits 0

🔴 **必须解全部数字字符引用**。H1 权威模板把中文整体写成 `&#21512;&#35745;` 形态
（`sharedStrings` 为 **0** 条）；本脚本第一版只解了 `&#8230;` 一个，「合计」认不出来，
**H1 自己反而漏计**（162 处 / 35 份 → 真值 170 处 / 37 份）。任何对模板做文本判据的脚本
都会踩这个坑。
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Final, Sequence

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_ROOT = _REPO_ROOT / "backend"
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.excel_structure_fingerprint import (  # noqa: E402
    _normalise_part,
    _parse_workbook_xml,
)

#: U+2026 HORIZONTAL ELLIPSIS。中文模板的续行占位一般是两个连排。
ELLIPSIS: Final[str] = "\u2026"

#: footer 锚点标记。取自 pilot 契约 `footer_anchor.marker` 的实际取值域，不自造。
FOOTER_MARKERS: Final[tuple[str, ...]] = ("合计", "小计", "总计")

#: 「整格就是排版占位」允许出现的字符集 —— 必须含至少一个 U+2026，且不含其它内容。
_TYPOGRAPHY_CHARS: Final[frozenset[str]] = frozenset({ELLIPSIS, ".", "\u3002", " "})

#: 只看行标签可能出现的前几列。受管区的 `seq` / 分类 / 编号列都落在这里。
_LABEL_COLUMNS: Final[str] = "A-C"

_TEMPLATES_DIR: Final[Path] = _BACKEND_ROOT / "wp_templates"
_CONTRACT_DIR: Final[Path] = _BACKEND_ROOT / "data" / "workpaper_sync_contracts"

_CELL = re.compile(
    r'<c\b[^>]*?\br="([%s])(\d+)"([^>]*?)(?:/>|>(.*?)</c>)' % _LABEL_COLUMNS, re.S
)
_V = re.compile(r"<v>(.*?)</v>", re.S)
_T = re.compile(r"<t[^>]*>(.*?)</t>", re.S)
_SI = re.compile(r"<si\b.*?</si>", re.S)
_NUMREF = re.compile(r"&#(x[0-9a-fA-F]+|\d+);")


class TypographyScanError(RuntimeError):
    """清册自身的装配失败（与被扫模板的问题区分开）。"""

    error_code = "managed_region_typography_scan_failed"


def _unescape(text: str) -> str:
    """解全部数字字符引用 + 三个基础实体。"""

    def _sub(match: re.Match[str]) -> str:
        token = match.group(1)
        return chr(int(token[1:], 16) if token[0] in "xX" else int(token))

    text = _NUMREF.sub(_sub, text)
    return text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").strip()


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    payload = zf.read("xl/sharedStrings.xml").decode("utf-8", "replace")
    return ["".join(_T.findall(item)) for item in _SI.findall(payload)]


def _label_cells(sheet_xml: str, shared: Sequence[str]) -> dict[str, str]:
    """单次遍历取前三列全部非空格文本。

    🔴 不要写成「逐格 `re.search` 回查」—— 那是 O(n²)，全库 2602 张 sheet 扫不完
    （实测第一版 15 分钟未出结果，改单次遍历后 1.4 秒）。
    """
    cells: dict[str, str] = {}
    for match in _CELL.finditer(sheet_xml):
        column, row, attrs, inner = (
            match.group(1),
            match.group(2),
            match.group(3) or "",
            match.group(4),
        )
        if inner is None:
            continue
        value = _V.search(inner)
        raw = value.group(1) if value else "".join(_T.findall(inner))
        if 't="s"' in attrs and raw.isdigit():
            index = int(raw)
            raw = shared[index] if index < len(shared) else ""
        text = _unescape(raw)
        if text:
            cells[f"{column}{row}"] = text
    return cells


def _is_typography_placeholder(text: str) -> bool:
    return ELLIPSIS in text and not (set(text) - _TYPOGRAPHY_CHARS)


def scan_managed_regions() -> dict[str, Any]:
    """§B —— BP-21 的**验收判据**：逐 pilot 契约现读受管区，区内不得含排版占位行。

    ═══ 为什么必须消费生产实现 ═══════════════════════════════════════════════════

    判据落在 `excel_extract.resolve_managed_region` 的**真实返回值**上，而不是本脚本自己
    照 `anchor + header_rows + footer 锚点` 再推一遍。自己推一遍的后果是：BP-21 修的是
    那个派生规则，而本判据用的是自己那份副本 ⇒ 修了也不变绿，判据与被验对象脱钩。

    零数据库：`stage_instrumented_substrate` 签名里没有 session，`resolve_managed_region`
    只吃 zip。B60 会在 OOXML 安全门被拒（`external_relationships`），那不是本判据的失败，
    记 `unverifiable_ooxml_gate` 并**从分母里剔除且把剔除数写出来**。
    """
    import tempfile

    from app.services.workpaper_sync import projection_first_publication as F2
    from app.services.workpaper_sync.adapters import registry as registry_module
    from app.services.workpaper_sync.excel_extract import resolve_managed_region

    rows: list[dict[str, Any]] = []
    for entry in registry_module.DELIVERED_PER_ENTRY_CONTRACTS:
        entry_id = str(entry["entry_id"])
        record: dict[str, Any] = {"entry_id": entry_id, "contract_id": str(entry["contract_id"])}
        try:
            provider = importlib.import_module(str(entry["provider_module"]))
            contract = provider.load_pilot_contract()
            with tempfile.TemporaryDirectory(prefix="tmp_bp21_") as work:
                staged = F2.stage_instrumented_substrate(
                    entry_id=entry_id, staging_dir=Path(work), contract=contract
                )
                binding = F2._identity_binding(
                    provider=provider, staged=staged, contract=contract
                )
                with zipfile.ZipFile(staged.staged_path) as zf:
                    region = resolve_managed_region(
                        zf, contract=contract, binding=binding
                    )
                    shared = _shared_strings(zf)
                    sheet_xml = zf.read(region.sheet_part).decode("utf-8", "replace")
                cells = _label_cells(sheet_xml, shared)
                label_column = str(region.first_column)
                placeholders = [
                    number
                    for number in range(int(region.first_row), int(region.last_row) + 1)
                    if _is_typography_placeholder(
                        cells.get(f"{label_column}{number}", "")
                    )
                ]
                record.update(
                    {
                        "status": "scanned",
                        "sheet_name": region.sheet_name,
                        "table_ref": str(getattr(region, "table_ref", "")),
                        "first_row": int(region.first_row),
                        "last_row": int(region.last_row),
                        "label_column": label_column,
                        "managed_row_count": int(region.last_row)
                        - int(region.first_row)
                        + 1,
                        "placeholder_rows_inside_region": placeholders,
                        "clean": not placeholders,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            gate = str(getattr(exc, "gate", "") or "")
            record.update(
                {
                    "status": "unverifiable_ooxml_gate" if gate else "error",
                    "gate": gate,
                    "detail": f"{type(exc).__name__}: {exc}"[:300],
                }
            )
        rows.append(record)

    scanned = [row for row in rows if row.get("status") == "scanned"]
    if not scanned:
        raise TypographyScanError(
            f"一个 entry 的受管区都没扫到（登记 {len(rows)} 个）—— "
            "分母为 0 时「区内 0 处占位行」是空转，不是通过"
        )
    return {
        "entries": rows,
        "entry_total": len(rows),
        "scanned": len(scanned),
        "excluded_unverifiable": len(rows) - len(scanned),
        "entries_with_placeholder_in_region": sum(
            1 for row in scanned if row["placeholder_rows_inside_region"]
        ),
        "placeholder_rows_in_regions": sum(
            len(row["placeholder_rows_inside_region"]) for row in scanned
        ),
    }


def _pilot_contract_facts() -> list[dict[str, Any]]:
    """pilot 契约的行/列排除声明面 —— 证明「行方向没有对应物」不是猜的。"""
    rows: list[dict[str, Any]] = []
    for path in sorted(_CONTRACT_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        review = data.get("review") or {}
        entry_id = str(review.get("entry_id") or "")
        if not entry_id:
            continue
        anchors: list[dict[str, Any]] = []
        for sheet in data.get("sheets", []):
            for table in sheet.get("tables", []):
                anchors.append(
                    {
                        "table_key": table.get("table_key"),
                        "anchor": table.get("anchor"),
                        "header_rows": table.get("header_rows"),
                        "footer_anchor": table.get("footer_anchor"),
                    }
                )
        rows.append(
            {
                "contract": path.name,
                "entry_id": entry_id,
                "excluded_columns": [
                    c.get("column") for c in (review.get("excluded_columns") or [])
                ],
                "excluded_columns_cite_ellipsis": any(
                    ELLIPSIS in str(c.get("reason", ""))
                    for c in (review.get("excluded_columns") or [])
                ),
                "declares_excluded_rows": "excluded_rows" in review,
                "reviewed_basis_cites_ellipsis": ELLIPSIS
                in str(review.get("reviewed_basis", "")),
                "tables": anchors,
            }
        )
    return rows


def scan() -> dict[str, Any]:
    """全模板库现算。分母一律写进结果，防止在空集上恒真。"""
    index_path = _TEMPLATES_DIR / "_index.json"
    if not index_path.exists():
        raise TypographyScanError(f"模板索引不存在: {index_path}")
    index = json.loads(index_path.read_text(encoding="utf-8"))["files"]
    xlsx_rows = [
        row
        for row in index
        if str(row.get("relative_path", "")).lower().endswith(".xlsx")
    ]

    hits: list[dict[str, Any]] = []
    typography_cells = 0
    scanned = 0
    sheets_scanned = 0
    failures: list[str] = []
    started = time.time()

    for row in xlsx_rows:
        template = _TEMPLATES_DIR / str(row["relative_path"])
        if template.name.startswith("~$") or not template.exists():
            continue
        try:
            with zipfile.ZipFile(template) as zf:
                shared = _shared_strings(zf)
                sheets, _defined = _parse_workbook_xml(zf)
                parts = set(zf.namelist())
                scanned += 1
                for sheet in sheets:
                    part = _normalise_part(sheet["rel_target"])
                    if part not in parts:
                        continue
                    sheets_scanned += 1
                    cells = _label_cells(
                        zf.read(part).decode("utf-8", "replace"), shared
                    )
                    for coord, text in cells.items():
                        if not _is_typography_placeholder(text):
                            continue
                        typography_cells += 1
                        column, number = coord[0], int(coord[1:])
                        following = cells.get(f"{column}{number + 1}", "")
                        if any(marker in following for marker in FOOTER_MARKERS):
                            hits.append(
                                {
                                    "template": str(row["relative_path"]).replace(
                                        "\\", "/"
                                    ),
                                    "wp_code": row.get("wp_code"),
                                    "sheet": sheet["name"],
                                    "cell": coord,
                                    "following_row_text": following[:24],
                                }
                            )
        except Exception as exc:  # noqa: BLE001
            # 🔴 不吞：扫描失败必须计数并可见，否则「扫不动的模板」会被伪装成「没命中」。
            failures.append(f"{row['relative_path']}: {type(exc).__name__}: {exc}")

    if scanned == 0:
        raise TypographyScanError(
            f"一份 xlsx 都没扫到（索引声明 {len(xlsx_rows)} 份）—— "
            "分母为 0 时任何「命中数」结论都是空转"
        )

    return {
        "index_total": len(index),
        "xlsx_declared_in_index": len(xlsx_rows),
        "xlsx_scanned": scanned,
        "sheets_scanned": sheets_scanned,
        "elapsed_sec": round(time.time() - started, 2),
        "typography_placeholder_cells": typography_cells,
        "placeholder_row_before_footer": len(hits),
        "distinct_templates": len({hit["template"] for hit in hits}),
        "distinct_wp_codes": sorted({str(hit["wp_code"]) for hit in hits}),
        "hits": hits,
        "scan_failures": failures,
        "scan_failure_count": len(failures),
        "pilot_contracts": _pilot_contract_facts(),
        "managed_region_scan": scan_managed_regions(),
    }


def _render(result: dict[str, Any]) -> str:
    lines = ["=== §A 全库排版占位行清册（裁决证据，不随修复变化）==="]
    for key in (
        "index_total",
        "xlsx_declared_in_index",
        "xlsx_scanned",
        "sheets_scanned",
        "elapsed_sec",
        "typography_placeholder_cells",
        "placeholder_row_before_footer",
        "distinct_templates",
        "scan_failure_count",
    ):
        lines.append(f"  {key:34s} {result[key]}")
    lines.append(f"  涉及 wp_code {len(result['distinct_wp_codes'])} 个: "
                 f"{result['distinct_wp_codes']}")
    pilots = result["pilot_contracts"]
    lines.append(
        f"  pilot 契约 {len(pilots)} 份，声明了行级排除的: "
        f"{sum(1 for p in pilots if p['declares_excluded_rows'])}"
        f"（列级排除引用了 …… 的: "
        f"{sum(1 for p in pilots if p['excluded_columns_cite_ellipsis'])}）"
    )
    for hit in result["hits"]:
        if str(hit["wp_code"]).upper() in {"H1", "D2", "G7", "B60"}:
            lines.append(
                f"    [pilot] {hit['wp_code']} {hit['sheet']}!{hit['cell']} "
                f"→ 下一行 {hit['following_row_text']!r}"
            )
    if result["scan_failures"]:
        lines.append("  🔴 扫描失败:")
        for item in result["scan_failures"][:10]:
            lines.append(f"    {item}")

    region = result["managed_region_scan"]
    lines.append("")
    lines.append("=== §B 逐 pilot 受管区扫描（BP-21 验收判据）===")
    lines.append(
        f"  entry 登记 {region['entry_total']} 个 · 实扫 {region['scanned']} 个 · "
        f"因 OOXML 门不可验 {region['excluded_unverifiable']} 个"
    )
    lines.append(
        f"  区内含排版占位行的 entry: {region['entries_with_placeholder_in_region']} 个"
        f"（占位行共 {region['placeholder_rows_in_regions']} 行）"
    )
    for row in region["entries"]:
        if row.get("status") != "scanned":
            lines.append(
                f"    ⊘ {row['entry_id']} status={row['status']} "
                f"gate={row.get('gate') or '—'}"
            )
            continue
        mark = "✅" if row["clean"] else "🔴"
        lines.append(
            f"    {mark} {row['entry_id']} {row['sheet_name']} "
            f"{row['label_column']}{row['first_row']}..{row['last_row']}"
            f"（{row['managed_row_count']} 行，table_ref={row['table_ref']}）"
        )
        if not row["clean"]:
            coords = ", ".join(
                f"{row['label_column']}{n}" for n in row["placeholder_rows_inside_region"]
            )
            lines.append(f"        区内占位行: {coords}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="受管区排版占位行清册（BP-21）")
    parser.add_argument("--json", dest="json_path", default=None, help="清册落盘路径")
    parser.add_argument(
        "--expect-managed-region-hits",
        type=int,
        default=None,
        help=(
            "BP-21 验收判据：**受管区内**排版占位行的期望条数（落地后应为 0）。"
            "注意不是 §A 的全库清册数 —— 那个数恒为 170，修完也不变"
        ),
    )
    args = parser.parse_args(argv)

    result = scan()
    print(_render(result))

    if args.json_path:
        # 🔴 脚本内写文件，不用 PowerShell 重定向（`>` 会把中文腌成乱码）。
        Path(args.json_path).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if result["scan_failure_count"]:
        return 2
    if args.expect_managed_region_hits is not None:
        region = result["managed_region_scan"]
        actual = region["placeholder_rows_in_regions"]
        if actual != args.expect_managed_region_hits:
            print(
                f"\n🔴 BP-21 验收未过：受管区内排版占位行期望 "
                f"{args.expect_managed_region_hits} 行，实测 {actual} 行"
                f"（涉及 {region['entries_with_placeholder_in_region']} 个 entry；"
                f"实扫分母 {region['scanned']} 个，因 OOXML 门不可验 "
                f"{region['excluded_unverifiable']} 个）"
            )
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
