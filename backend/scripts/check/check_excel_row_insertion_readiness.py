# -*- coding: utf-8 -*-
"""全量底稿**可插行清册** —— 逐 entry 现算「这份底稿今天能不能安全插行」。

spec: excel-structural-row-insertion-and-shift-aware-verification（Task 19 / N2）
Requirements: 10.1 ~ 10.6 · Properties: **P27** / **P28**

═══ 这份清册回答什么 ═══════════════════════════════════════════════════════

结构性插行的能力**受契约形态约束**，不是「引擎支持了就到处都能用」。本清册把
「哪些 entry 今天能插、哪些不能、不能的原因是什么、解除条件是什么」逐条现算出来。

🔴 **全部结论由真实模板 + 真实契约现算，一个字都不手填**（AC 10.3）。判定复用
`excel_row_shift` / `excel_materialize` 的**生产函数**，不在本脚本里另写一套 ——
另写一套的话清册会和引擎各说各话，而「清册说能插、引擎说不能」比没有清册更糟。

═══ 封闭结算词表（AC 10.2）═════════════════════════════════════════════════

每个 entry 恰好落进一格，两两互斥、合起来穷尽：

| verdict | 含义 |
|---|---|
`no_insertion_needed`                    | HTML 行数 <= 骨架行数，本来不需要插行
`insertion_safe`                         | 需要插行且**可安全执行**
`blocked_no_contract`                    | 该 entry 没有已发布契约 ⇒ 谈不上插行
`blocked_unlisted_structure`             | 受管 sheet 上有清单外的位移敏感元素
`blocked_style_source_missing`           | 样式来源行在模板里不存在
`blocked_shared_formula`                 | 共享公式组跨度/朝向不支持按行 fill-down
`blocked_out_of_range`                   | 插入点或样式源越界
`blocked_static_row_below_insertion`     | 🔴 契约静态行落在插入点及其之下
`blocked_total_formula_not_extendable`   | 🔴 合计公式不会扩张而契约未授权扩张

🔴 后两格是**实施中实测发现**的，design.md 的词表里没有 —— 它们恰好是今天
**两个既有 pilot（K11 / H1）真实命中**的两格。词表少了它们，清册就会把「引擎明确拒绝」
错报成 `insertion_safe`，那是最坏的一种假绿：它会让人以为可以上线。

═══ 用法 ═══════════════════════════════════════════════════════════════════

    python backend/scripts/check/check_excel_row_insertion_readiness.py            # 摘要
    python backend/scripts/check/check_excel_row_insertion_readiness.py --json     # 落盘
    python backend/scripts/check/check_excel_row_insertion_readiness.py --check    # 与磁盘比对

`--json` 的落盘由脚本内 `Path.write_text(encoding="utf-8")` 完成，**不用 shell 重定向**
（PowerShell 重定向会写出 UTF-16 / 带 BOM，下游 `json.loads` 直接炸）。

`--rows` 从真实库取 HTML 行数；不给则只出**结构性**结论（后者不依赖库，可离线复现）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any, Final, Mapping

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_REPO))

from app.services.workpaper_sync import excel_materialize as M  # noqa: E402
from app.services.workpaper_sync import excel_row_shift as RS  # noqa: E402
from app.services.workpaper_sync.contracts import (  # noqa: E402
    SyncContract,
    available_contract_ids,
    load_contract,
)

#: 模板库根 —— 唯一权威源，本脚本**只读**。
TEMPLATE_ROOT: Final[Path] = _REPO / "wp_templates"

#: 清册落盘位置。
OUTPUT_PATH: Final[Path] = _REPO / "data" / "workpaper_excel_row_insertion_readiness.json"

#: 封闭结算词表（AC 10.2）。顺序即报告里的展示顺序。
VERDICTS: Final[tuple[str, ...]] = (
    "no_insertion_needed",
    "insertion_safe",
    "blocked_no_contract",
    "blocked_unlisted_structure",
    "blocked_style_source_missing",
    "blocked_shared_formula",
    "blocked_out_of_range",
    "blocked_static_row_below_insertion",
    "blocked_total_formula_not_extendable",
)

#: 每格阻塞理由的**解除条件**（AC 10.6：不可插行的 entry 各给判据编号与解除条件）。
RESOLUTIONS: Final[Mapping[str, str]] = {
    "blocked_no_contract": "为该 entry 发布契约（走 template → instrumentation → contract → bundle → representation 发布链）",
    "blocked_unlisted_structure": "把该结构登记进 excel_row_shift.ROW_BEARING_STRUCTURES 并实现其位移分支（清单与实现由 assert_shift_handlers_cover_structures 双向锁）",
    "blocked_style_source_missing": "模板侧补齐样式来源行（受管区末行必须存在于 sheet XML）",
    "blocked_shared_formula": "在模板里解开该共享公式组，或把它改成逐格公式",
    "blocked_out_of_range": "修正受管区域声明使其与物理行集自洽",
    "blocked_static_row_below_insertion": "让 Task 37 的 extract 侧静态行定位也变成位移感知（读写两侧一起改），或把该静态字段移到插入点之上",
    "blocked_total_formula_not_extendable": "在契约的 footer_anchor 上声明 carries_total_formula=true（授权引擎把合计区间随受管区间扩张）",
}

#: `error_code` → verdict。**由生产异常的 `error_code` 驱动**，不在这里重写判定逻辑。
_CODE_TO_VERDICT: Final[Mapping[str, str]] = {
    RS.UnlistedRowBearingStructureError.error_code: "blocked_unlisted_structure",
    RS.RowShiftStyleSourceMissingError.error_code: "blocked_style_source_missing",
    RS.SharedFormulaSpanError.error_code: "blocked_shared_formula",
    RS.SharedFormulaOrientationError.error_code: "blocked_shared_formula",
    RS.RowShiftPlanRangeError.error_code: "blocked_out_of_range",
    RS.RowShiftPlanCountError.error_code: "blocked_out_of_range",
}


class ReadinessError(RuntimeError):
    """清册无法现算 —— fail closed，不给「大概能插」这种结论。"""


@dataclass(frozen=True)
class EntryReadiness:
    """一个 entry 的可插行结论。"""

    adapter_id: str
    template_relative_path: str
    sheet_name: str
    verdict: str
    #: 骨架（模板自带）数据行数。
    skeleton_rows: int
    #: 受管区间（位移前）。
    first_row: int
    last_row: int
    #: 插入点 = 最后一个骨架数据行 +1。
    insert_at: int
    #: HTML store 实际行数（`--rows` 才有；否则 `None`）。
    store_rows: int | None = None
    #: 需要插几行（`store_rows` 已知时才有）。
    rows_needed: int | None = None
    diagnostic_code: str = ""
    detail: str = ""
    resolution: str = ""
    #: 实测事实（供人工复核，不参与判定）。
    facts: Mapping[str, Any] = dataclass_field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "template_relative_path": self.template_relative_path,
            "sheet_name": self.sheet_name,
            "verdict": self.verdict,
            "skeleton_rows": self.skeleton_rows,
            "managed_rows": [self.first_row, self.last_row],
            "insert_at": self.insert_at,
            "store_rows": self.store_rows,
            "rows_needed": self.rows_needed,
            "diagnostic_code": self.diagnostic_code,
            "detail": self.detail,
            "resolution": self.resolution,
            "facts": dict(sorted(self.facts.items())),
        }


# ═══════════════════════════════════════════════════════════════════════════
# 1. 模板侧实测
# ═══════════════════════════════════════════════════════════════════════════


#: `r:id` 的完整命名空间形态 —— ElementTree 会把前缀展开成 `{uri}local`。
_R_NS: Final[str] = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _sheet_part(zf: zipfile.ZipFile, sheet_name: str) -> str:
    """sheet 名 → zip part。**按 `r:id` 关系解析**，不假设 `sheetN.xml` 的编号顺序。

    🔴 用 `ElementTree` 而不是正则：`r:id` 是**带命名空间前缀**的属性，而前缀在文档里
    不保证叫 `r`（`xmlns:rel=...` + `rel:id=...` 同样合法）。正则按字面 `r:id=` 找，
    在换了前缀的工作簿上会静默找不到 —— 本脚本首版就这么错了三个 entry（D2 恰好用 `r:`
    所以通过，掩盖了缺陷；那正是「一个样本上通过不等于判据成立」的实例）。
    """
    import xml.etree.ElementTree as ET

    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_map = {
        node.get("Id", ""): node.get("Target", "")
        for node in rels
        if node.get("Id")
    }
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    seen: list[str] = []
    for node in workbook.iter():
        if not node.tag.endswith("}sheet") and node.tag != "sheet":
            continue
        name = node.get("name")
        if name is None:
            continue
        seen.append(name)
        if name != sheet_name:
            continue
        rid = node.get(_R_NS) or node.get("r:id") or ""
        target = rel_map.get(rid, "")
        if not target:
            raise ReadinessError(
                f"sheet {sheet_name!r} 的 r:id={rid!r} 在 workbook.xml.rels 里没有对应 Target"
                f"（实测 rel ids: {sorted(rel_map)[:8]}）"
            )
        return "xl/" + target.lstrip("/").removeprefix("xl/")
    raise ReadinessError(
        f"sheet {sheet_name!r} 在 workbook.xml 里定位不到（实测 sheet 名: {seen}）"
    )


def _last_data_row(xml: str, *, first_row: int, footer_row: int | None) -> int:
    """骨架最后一个**数据行** —— footer 之上、`first_row` 之下的最大 `<row r>`。"""
    rows = [int(m.group(1)) for m in re.finditer(r'<row r="(\d+)"', xml)]
    candidates = [
        r for r in rows if r >= first_row and (footer_row is None or r < footer_row)
    ]
    if not candidates:
        raise ReadinessError(
            f"受管区间起点 {first_row} 之下、footer {footer_row} 之上一行都没有"
        )
    return max(candidates)


def _footer_row(xml: str, *, marker: str, column: str, entries: Mapping[str, bytes]) -> int | None:
    """footer marker 所在行 —— **直接调生产侧的 `_find_marker_row`**。

    🔴 本脚本首版在这里手写了第二份 marker 定位（三载体 sharedString/inlineStr/str），
    结果在 H1 / B60 / G7 上**一个都找不到**：那三份模板既没有 `sharedStrings.xml`，
    中文文本又以**数字字符引用**（`&#21512;&#35745;` = 合计）存在 inline `<t>` 里，
    而生产侧早有 `_decode_numeric_char_refs` 处理这一形态，我那份没有。

    症状最坏的地方不是「找不到」，而是找不到之后清册走进「无 footer 声明 ⇒ 无合计漏算
    问题」那一支，把三个 entry 全报成 `insertion_safe` —— 一个**会让人以为可以上线**的
    假绿。教训与本 spec 已记录的三次同源：**判据必须复用唯一入口，不重写第二份**。
    """
    return M._find_marker_row(
        xml, column=column, marker=marker, shared=M._shared_strings(entries)
    )


def _static_rows_at_or_below(contract: SyncContract, insert_at: int) -> list[str]:
    return [
        f"{spec.stable_field_key}@{spec.cell.column}{spec.cell.static_row}"
        for sheet in contract.sheets
        for table in sheet.tables
        for spec in table.fields
        if spec.cell is not None
        and spec.cell.static_row is not None
        and spec.cell.static_row >= insert_at
    ]


def _total_formula_extendable(
    xml: str, *, footer_row: int | None, carries: bool, last_row: int
) -> tuple[bool, str]:
    """footer 上的合计公式会不会随受管区间扩张。

    返回 `(是否可扩张, 说明)`。契约声明了 `carries_total_formula` 即可扩张；
    未声明但 footer 上有覆盖不到位移后末行的区间 ⇒ 不可扩张（照插会漏算）。
    """
    if footer_row is None:
        return True, "契约无 footer 声明 ⇒ 无合计漏算问题"
    if carries:
        return True, "契约已声明 carries_total_formula ⇒ 引擎有权扩张"
    block = re.search(rf'<row r="{footer_row}"[^>]*>(?P<body>.*?)</row>', xml, re.S)
    if block is None:
        return True, f"footer 行 {footer_row} 在 XML 里不存在 ⇒ 无合计公式"
    ranges = re.findall(r"[A-Z]{1,3}(\d+):[A-Z]{1,3}(\d+)", block.group("body"))
    for _first, end in ranges:
        if int(end) < last_row + 1:
            return False, (
                f"footer 行 {footer_row} 上有区间末行 {end} < 位移后末行 {last_row + 1}，"
                "而契约未声明 carries_total_formula"
            )
    return True, "footer 上没有会漏算的区间"


# ═══════════════════════════════════════════════════════════════════════════
# 2. 逐 entry 现算
# ═══════════════════════════════════════════════════════════════════════════


def assess(adapter_id: str, *, store_rows: int | None = None) -> EntryReadiness:
    """现算一个 entry 的可插行结论。**全部判定复用生产函数**。"""
    contract = load_contract(adapter_id)
    template = TEMPLATE_ROOT / contract.template.relative_path
    if not template.is_file():
        raise ReadinessError(f"{adapter_id}: 模板不在模板库里: {template}")

    sheet = contract.sheets[0]
    dynamic = next((t for t in sheet.tables if t.has_dynamic_rows), None)
    if dynamic is None:
        raise ReadinessError(f"{adapter_id}: 契约里没有动态行表 ⇒ 谈不上插行")

    anchor_row = int(re.sub(r"\D", "", dynamic.anchor))
    first_row = anchor_row + dynamic.header_rows

    with zipfile.ZipFile(template) as zf:
        part = _sheet_part(zf, sheet.excel_name)
        entries = {name: zf.read(name) for name in zf.namelist()}
        xml = entries[part].decode("utf-8")

    footer = dynamic.footer_anchor
    footer_row = (
        _footer_row(
            xml, marker=footer.marker, column=footer.search_column, entries=entries
        )
        if footer is not None
        else None
    )
    # 🔴 契约声明了 footer 但定位不到 ⇒ **fail closed**，不得当成「没有 footer 问题」。
    #    生产侧 `assert_footer_anchor_stable` 在同样情形下抛 `FooterAnchorDriftError`
    #    （"footer anchor 是 AC 6.3 要求契约表达的结构之一，定位不到即结构漂移"），
    #    清册不能比它宽松 —— 宽松的那一版会把 3 个 entry 报成可安全插行。
    if footer is not None and footer_row is None:
        raise ReadinessError(
            f"{adapter_id}: 契约声明的 footer marker {footer.marker!r} 在列 "
            f"{footer.search_column} 上一处都找不到 —— 结构漂移，不得给出可插行结论"
            "（生产侧 assert_footer_anchor_stable 在此情形下同样 fail closed）"
        )
    last_row = _last_data_row(xml, first_row=first_row, footer_row=footer_row)
    skeleton_rows = last_row - first_row + 1
    insert_at = last_row + 1

    facts: dict[str, Any] = {
        "sheet_part": part,
        "footer_row": footer_row,
        "footer_marker": footer.marker if footer else None,
        "carries_total_formula": bool(footer and footer.carries_total_formula),
        "shared_formula_groups": len(RS.shared_formula_groups(xml)),
    }

    def _make(verdict: str, *, code: str = "", detail: str = "") -> EntryReadiness:
        return EntryReadiness(
            adapter_id=adapter_id,
            template_relative_path=contract.template.relative_path,
            sheet_name=sheet.excel_name,
            verdict=verdict,
            skeleton_rows=skeleton_rows,
            first_row=first_row,
            last_row=last_row,
            insert_at=insert_at,
            store_rows=store_rows,
            rows_needed=(
                max(0, store_rows - skeleton_rows) if store_rows is not None else None
            ),
            diagnostic_code=code,
            detail=detail,
            resolution=RESOLUTIONS.get(verdict, ""),
            facts=facts,
        )

    # ── ① 契约静态行落在插入点及其之下 ──────────────────────────────
    offenders = _static_rows_at_or_below(contract, insert_at)
    if offenders:
        return _make(
            "blocked_static_row_below_insertion",
            code="contract_static_row_below_insertion",
            detail=(
                f"契约静态格 {offenders[:3]}（共 {len(offenders)} 个）落在插入点 "
                f"{insert_at} 及其之下 —— 插行会把它们推下去，而 extract 仍按契约 "
                "static_row 反读固定行号，于是读到一个新插入的空行（静默取空值）"
            ),
        )

    # ── ② 合计公式不会扩张而契约未授权 ─────────────────────────────
    extendable, why = _total_formula_extendable(
        xml,
        footer_row=footer_row,
        carries=bool(footer and footer.carries_total_formula),
        last_row=last_row,
    )
    if not extendable:
        return _make(
            "blocked_total_formula_not_extendable",
            code="contract_total_formula_not_extendable",
            detail=why + " ⇒ 照插会产出一张合计漏算的审计底稿",
        )

    # ── ③ 结构性可执行性 —— **干跑生产位移函数**，不重写判定 ───────
    plan_rows = max(1, (store_rows or 0) - skeleton_rows) if store_rows else 1
    try:
        plan = RS.RowShiftPlan(
            insert_at=insert_at,
            count=plan_rows,
            style_from=last_row,
            table_key=dynamic.table_key,
        )
        RS.shift_sheet_rows(
            xml,
            plan,
            total_formula_rows=(footer_row,) if (footer_row and footer and footer.carries_total_formula) else (),
        )
    except RS.RowShiftError as exc:
        code = type(exc).error_code
        return _make(
            _CODE_TO_VERDICT.get(code, "blocked_unlisted_structure"),
            code=code,
            detail=str(exc)[:400],
        )

    # ── ④ 不需要插行 vs 可安全插行 ─────────────────────────────────
    if store_rows is not None and store_rows <= skeleton_rows:
        return _make("no_insertion_needed", detail=f"HTML {store_rows} 行 <= 骨架 {skeleton_rows} 行")
    return _make("insertion_safe", detail=f"干跑位移通过（插入点 {insert_at}，样式源 {last_row}）")


def build_report(*, store_rows: Mapping[str, int] | None = None) -> dict[str, Any]:
    """全量清册。**每个 entry 恰好一格**，并断言词表封闭。"""
    rows = store_rows or {}
    entries: list[EntryReadiness] = []
    errors: list[dict[str, str]] = []
    for adapter_id in sorted(available_contract_ids()):
        try:
            entries.append(assess(adapter_id, store_rows=rows.get(adapter_id)))
        except (ReadinessError, Exception) as exc:  # noqa: BLE001 - 逐条记录，不中断全量
            errors.append({"adapter_id": adapter_id, "error": f"{type(exc).__name__}: {exc}"[:400]})

    counts = {v: sum(1 for e in entries if e.verdict == v) for v in VERDICTS}
    unknown = sorted({e.verdict for e in entries} - set(VERDICTS))
    if unknown:
        raise ReadinessError(
            f"出现封闭词表之外的结论 {unknown} —— 词表必须穷尽，否则清册会把未知情形"
            "混进某一格里（AC 10.2）"
        )
    return {
        "schema_version": "excel-row-insertion-readiness:v1",
        "verdict_vocabulary": list(VERDICTS),
        "resolutions": dict(RESOLUTIONS),
        "counts": counts,
        "total_entries": len(entries),
        "store_rows_provided": bool(rows),
        "entries": [e.as_dict() for e in entries],
        "errors": errors,
    }


def _print_summary(report: Mapping[str, Any]) -> None:
    print(f"Excel 结构性插行可插性清册 —— {report['total_entries']} 个已发布契约")
    print(f"{'HTML 行数来源: 真实库' if report['store_rows_provided'] else 'HTML 行数: 未取（只出结构性结论）'}")
    print()
    for verdict in report["verdict_vocabulary"]:
        count = report["counts"][verdict]
        if count:
            print(f"  {verdict:<38} {count}")
    print()
    for entry in report["entries"]:
        print(f"  [{entry['verdict']:<36}] {entry['adapter_id']}")
        print(f"       模板 {entry['template_relative_path']}")
        print(
            f"       sheet {entry['sheet_name']} / 受管 {entry['managed_rows'][0]}..{entry['managed_rows'][1]}"
            f" / 骨架 {entry['skeleton_rows']} 行 / 插入点 {entry['insert_at']}"
        )
        if entry["diagnostic_code"]:
            print(f"       ⛔ [{entry['diagnostic_code']}] {entry['detail'][:150]}")
            print(f"       解除: {entry['resolution']}")
        else:
            print(f"       ✅ {entry['detail'][:150]}")
    if report["errors"]:
        print()
        print("  现算失败（fail closed，不给结论）:")
        for row in report["errors"]:
            print(f"    {row['adapter_id']}: {row['error'][:180]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ and __doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="落盘清册（脚本内写文件，不用 shell 重定向）")
    parser.add_argument("--check", action="store_true", help="与磁盘清册比对，不一致即非零退出")
    parser.add_argument("--stdout-json", action="store_true", help="把清册打到 stdout")
    args = parser.parse_args(argv)

    report = build_report()

    if args.check:
        if not OUTPUT_PATH.is_file():
            print(f"[FAIL] 清册不存在: {OUTPUT_PATH} —— 先跑 --json")
            return 2
        on_disk = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        live = json.loads(json.dumps(report, ensure_ascii=False, sort_keys=True))
        if json.dumps(on_disk, ensure_ascii=False, sort_keys=True) != json.dumps(
            live, ensure_ascii=False, sort_keys=True
        ):
            print("[FAIL] 磁盘清册与现算不一致 —— 模板/契约变了，请重跑 --json 并复核 diff")
            return 1
        print(f"[OK] 清册与现算一致（{report['total_entries']} 个 entry）")
        return 0

    if args.json:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"[OK] 已落盘 {OUTPUT_PATH}")
    if args.stdout_json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if not args.json and not args.stdout_json:
        _print_summary(report)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
