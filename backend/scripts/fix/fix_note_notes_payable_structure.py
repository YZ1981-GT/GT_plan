#!/usr/bin/env python
"""附注应付票据（F3）章节结构对齐源模板（幂等修订）。

**问题**：`五、36` / `八、36` 的「应付票据」表自 seed 生成起从未对齐过
（`_aligned_by` 为 null）：

- ``columns`` 完全缺失 → seed 路径（新建项目 / 重新生成附注）无列元数据，
  渲染回退 ``note_sub_table_projector._infer_groups_from_headers`` 前缀推断
- ``guidance`` 缺失 → 附注 TAB 没有编制提示
- ``rows`` 行序为「商业承兑汇票 → 银行承兑汇票」，与源模板相反

**权威源**（运行时权威，逐格 openpyxl 实证）：
``backend/wp_templates/F/F3 应付票据.xlsx``

===========================  ====  ========  ============  =========================
sheet                        A6    B6        C6            行序
===========================  ====  ========  ============  =========================
附注披露信息(上市公司)       种类  期末余额  上年年末余额  r7 银行承兑 → r8 商业承兑 → r9 合计
附注披露信息(国企)           类别  期末余额  期初余额      同上
===========================  ====  ========  ============  =========================

上市 r10 / r11、国企 r10 的说明与红字括注 → ``guidance``（不自造披露要求）。

Usage::

    python backend/scripts/fix/fix_note_notes_payable_structure.py --dry-run
    python backend/scripts/fix/fix_note_notes_payable_structure.py
    python backend/scripts/fix/fix_note_notes_payable_structure.py --check

spec: .kiro/specs/f-cycle-disclosure-parity/ R2 / R3
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _BACKEND / "data"

ALIGNED_BY = "f-cycle-disclosure-parity"

LISTED_PATH = DATA_DIR / "note_template_listed.json"
SOE_PATH = DATA_DIR / "note_template_soe.json"

LISTED_SECTION = "五、36"
SOE_SECTION = "八、36"

TABLE_NAME = "应付票据"

# 源 xlsx r7/r8 行序（银行在前）；合计行由 _total_row 追加
CLASS_LABELS = ["银行承兑汇票", "商业承兑汇票"]

_G_LISTED = (
    "按种类披露应付票据期末余额与上年年末余额。源模板说明：本期末已到期未支付的"
    "应付票据总额应在下方说明中披露。"
    "【如果法律上认定供应链票据属于《商业汇票承兑、贴现与再贴现管理办法》"
    "（中国人民银行 中国银行保险监督管理委员会令〔2022〕第4号）的范围、"
    "具备《票据法》规定的要件，则出票人应当自法律认定生效日（2023年1月1日）起"
    "将其作为“应付票据”进行会计处理，且无需对前期比较期间数据进行追溯调整。】"
    "勾稽：合计行 = 各种类行之和，并与 F3-1 审定表期末审定数、试算平衡表 2201 科目一致。"
)

_G_SOE = (
    "按类别披露应付票据期末余额与期初余额（国企版第 3 列为「期初余额」，"
    "与上市版「上年年末余额」用语不同）。源模板注：企业应说明本期已到期未支付的"
    "应付票据总金额。"
    "勾稽：合计行 = 各类别行之和，并与 F3-1 审定表期末审定数、试算平衡表 2201 科目一致。"
)


def _data_row(label: str) -> dict[str, Any]:
    return {"label": label, "row_type": "data"}


def _total_row(label: str = "合计") -> dict[str, Any]:
    return {"label": label, "is_total": True, "row_type": "total"}


def _patch(label_header: str, prior_header: str, guidance: str) -> dict[str, Any]:
    """单级表头 3 列；标签列标 ``flat`` 抑制 seed 路径的前缀推断。"""
    return {
        "headers": [label_header, "期末余额", prior_header],
        "columns": [
            {"key": "label", "label": label_header, "is_label": True, "flat": True},
            {"key": "end_amount", "label": "期末余额", "format": "amount"},
            {"key": "prior_amount", "label": prior_header, "format": "amount"},
        ],
        "guidance": guidance,
        "rows": [_data_row(x) for x in CLASS_LABELS] + [_total_row()],
    }


LISTED_PATCH = _patch("种类", "上年年末余额", _G_LISTED)
SOE_PATCH = _patch("类别", "期初余额", _G_SOE)


def _find_section(doc: dict[str, Any], section_number: str) -> dict[str, Any] | None:
    for s in doc.get("sections", []):
        if str(s.get("section_number", "")) == section_number:
            return s
    return None


def apply_patch(section: dict[str, Any], patch: dict[str, Any]) -> tuple[list[str], list[str]]:
    tables: list[dict[str, Any]] = section.get("tables") or []
    changes: list[str] = []
    warnings: list[str] = []

    idx = next((i for i, t in enumerate(tables) if str(t.get("name", "")) == TABLE_NAME), None)
    if idx is None:
        warnings.append(f"未找到表「{TABLE_NAME}」→ 跳过（现有表名：{[t.get('name') for t in tables]}）")
        return changes, warnings

    tbl = tables[idx]
    for key in ("headers", "columns", "rows"):
        if tbl.get(key) != patch[key]:
            old = len(tbl.get(key) or [])
            tbl[key] = json.loads(json.dumps(patch[key], ensure_ascii=False))
            changes.append(f"[{idx}] {TABLE_NAME}.{key}：{old} → {len(patch[key])} 项")
    if tbl.get("guidance") != patch["guidance"]:
        had = bool(tbl.get("guidance"))
        tbl["guidance"] = patch["guidance"]
        changes.append(
            f"[{idx}] {TABLE_NAME}.guidance：{'更新' if had else '新增'}（{len(patch['guidance'])} 字）"
        )
    return changes, warnings


def validate_section(section: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    tables = section.get("tables") or []
    seen: dict[str, int] = {}

    for i, tbl in enumerate(tables):
        name = str(tbl.get("name", ""))
        if name in seen:
            errs.append(f"[{i}] 表名重复：「{name}」（首现于 {seen[name]}）")
        seen[name] = i

        headers = tbl.get("headers") or []
        cols = tbl.get("columns") or []

        if not cols:
            errs.append(f"[{i}] {name} 缺 columns（seed 路径无列元数据）")
        elif len(cols) != len(headers):
            errs.append(f"[{i}] {name} columns={len(cols)} ≠ headers={len(headers)}")
        else:
            for k, (h, c) in enumerate(zip(headers, cols)):
                if not isinstance(c, dict):
                    continue
                if str(c.get("label") or "") != str(h):
                    errs.append(
                        f"[{i}] {name} 第 {k} 列 headers={h!r} ≠ columns.label={c.get('label')!r}"
                    )

        if cols:
            has_flat = any(isinstance(c, dict) and c.get("flat") for c in cols)
            has_group = any(isinstance(c, dict) and c.get("group") for c in cols)
            if not has_flat and not has_group:
                errs.append(f"[{i}] {name} 既无 columns[].group 也无 columns[].flat（须显式表态）")
            if has_flat and has_group:
                errs.append(f"[{i}] {name} 同时声明 flat 与 group（语义冲突）")

        if not str(tbl.get("guidance") or "").strip():
            errs.append(f"[{i}] {name} 缺 guidance（附注 TAB 编制提示）")

        for h in headers:
            if "<" in str(h) and ">" in str(h):
                errs.append(f"[{i}] {name} headers 含 HTML 标记：{h!r}（应为纯文本）")

        for j, row in enumerate(tbl.get("rows") or []):
            if str(row.get("row_type", "")) == "header_label":
                errs.append(f"[{i}] {name} 第 {j} 行仍为 header_label")

    # 行序：源 xlsx 银行承兑在前
    tbl = next((t for t in tables if str(t.get("name", "")) == TABLE_NAME), None)
    if tbl is not None:
        labels = [str(r.get("label")) for r in tbl.get("rows") or []]
        if labels != CLASS_LABELS + ["合计"]:
            errs.append(f"[rows] {TABLE_NAME} 行集/行序 {labels} ≠ {CLASS_LABELS + ['合计']}")

    return errs


def _stamp(section: dict[str, Any]) -> None:
    section["_aligned_by"] = ALIGNED_BY
    section["_aligned_at"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _process(
    path: Path,
    section_number: str,
    patch: dict[str, Any],
    *,
    dry_run: bool,
    check_only: bool,
) -> tuple[bool, list[str]]:
    raw = path.read_text(encoding="utf-8")
    doc = json.loads(raw)
    section = _find_section(doc, section_number)
    if section is None:
        return False, [f"[FATAL] {path.name} 未找到 section_number={section_number}"]

    log = [f"=== {path.name} §{section_number} {section.get('section_title')} ==="]

    if check_only:
        errs = validate_section(section)
        log.append(f"_aligned_by={section.get('_aligned_by')!r}")
        if section.get("_aligned_by") != ALIGNED_BY:
            errs.append("尚未对齐（缺 _aligned_by 标记）")
        log.extend(errs or ["结构校验通过"])
        return not errs, log

    changes, warnings = apply_patch(section, patch)
    log.extend(changes or ["无需修改（已对齐）"])
    log.extend(f"[WARN] {w}" for w in warnings)

    errs = validate_section(section)
    if errs:
        log.append("[FATAL] 修订后结构校验失败，未写入：")
        log.extend(f"  {e}" for e in errs)
        return False, log

    log.append(f"结构校验通过（{len(section.get('tables') or [])} 张表）")
    if dry_run:
        log.append("[dry-run] 未写文件")
        return True, log

    if not changes and section.get("_aligned_by") == ALIGNED_BY:
        log.append("已对齐且无变更，跳过写入")
        return True, log

    _stamp(section)
    trailing = "\n" if raw.endswith("\n") else ""
    path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + trailing,
        encoding="utf-8",
    )
    log.append(f"已写入 {path}")
    return True, log


def main() -> int:
    ap = argparse.ArgumentParser(description="附注应付票据章节结构对齐源模板（幂等）")
    ap.add_argument("--dry-run", action="store_true", help="只打印 diff 摘要，不写文件")
    ap.add_argument("--check", action="store_true", help="仅校验对齐状态（供 CI）")
    args = ap.parse_args()

    targets = [
        (LISTED_PATH, LISTED_SECTION, LISTED_PATCH),
        (SOE_PATH, SOE_SECTION, SOE_PATCH),
    ]

    ok_all = True
    for path, num, patch in targets:
        ok, log = _process(path, num, patch, dry_run=args.dry_run, check_only=args.check)
        print("\n".join(log))
        print()
        ok_all = ok_all and ok

    if not ok_all:
        print("[FAIL] 存在未通过项")
        return 1
    print("[OK] 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
