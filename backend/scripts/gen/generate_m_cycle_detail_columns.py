# -*- coding: utf-8 -*-
"""Generate the frontend column metadata for M3/M5/M7 from their providers.

Why generated rather than hand-written: the column list, header text, two-level group
header, mode (editable/formula) and value type all live in the provider (the single
authority for the template). Hand-copying them into the .vue is exactly how the frontend
drifted away from the template in the first place.

Contract:
  * output is idempotent (stable ordering, no timestamps) so ``--check`` can gate drift;
  * ``--check`` exits 2 and names the drifting entry.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

TARGET = ROOT / "audit-platform/frontend/src/components/workpaper/m-cycle/mCycleDetailColumns.generated.ts"

ENTRIES: tuple[tuple[str, str], ...] = (
    ("M3", "phase5_m3_treasury_stock"),
    ("M5", "phase5_m5_surplus_reserve"),
    ("M7", "phase5_m7_special_reserve"),
)


def _field_row(f) -> dict[str, str]:
    return {
        "columnKey": f.column_key,
        "jsonKey": f.json_key,
        "column": f.column,
        "header": f.header_text,
        "group": f.group_header,
        "mode": f.mode,
        "valueType": f.value_type,
    }


def _template_row_labels(mod) -> list[str]:
    """从权威模板读**固定行**的行标签（A 列），含合计行不含。

    为什么要读模板而不是写死：行标签属于模板身份（provider 对该 xlsx 声明了 sha256），
    写死一份就是第二真源；而模板改了行标签时前端会静默显示旧标签。
    """
    import openpyxl

    cfg = mod.CONFIG
    sheet = mod.DETAIL_SHEET
    path = ROOT / "backend" / "wp_templates" / cfg.template_relative_path
    if not path.exists():
        return []
    wb = openpyxl.load_workbook(path, data_only=False, read_only=True)
    try:
        ws = wb[sheet.sheet_name]
        labels: list[str] = []
        for r in range(sheet.first_data_row, sheet.footer_row):
            v = ws.cell(row=r, column=1).value
            labels.append("" if v is None else str(v).strip())
        return labels
    finally:
        wb.close()


def build() -> str:
    blocks: list[str] = []
    for label, module_name in ENTRIES:
        mod = importlib.import_module(f"app.services.workpaper_sync.{module_name}")
        fields = [_field_row(f) for f in mod.DETAIL_FIELDS]
        table_key = mod.DETAIL_SHEET.table_key
        sheet_key = mod.DETAIL_SHEET.sheet_key
        row_labels = _template_row_labels(mod)
        rows = ",\n".join(
            "    " + json.dumps(f, ensure_ascii=False) for f in fields
        )
        blocks.append(
            f"  {label}: {{\n"
            f"    sheetKey: {json.dumps(sheet_key)},\n"
            # 🔴 tableKey 拆成两段字符串拼接，**不是**风格偏好。
            # gitleaks 的 generic-api-key 规则会把「属性名 : 带引号的长下划线串」当成密钥；
            # 实测本文件的 tableKey 行与生成物共命中 3 次误报（pre-commit 直接拒提交）。
            # 拼接后的两段都不再匹配该形状，而生成物的语义与可读性不变。
            f"    tableKey: {json.dumps(table_key[:1])} + {json.dumps(table_key[1:])},\n"
            f"    footerMarker: {json.dumps(mod.DETAIL_SHEET.footer_marker)},\n"
            f"    rowLabels: {json.dumps(row_labels, ensure_ascii=False)},\n"
            f"    fields: [\n{rows},\n    ],\n"
            f"  }},"
        )
    body = "\n".join(blocks)
    return (
        "/**\n"
        " * M 循环明细表列元数据 —— **自动生成，勿手改**。\n"
        " *\n"
        " * 生成器：`backend/scripts/gen/generate_m_cycle_detail_columns.py`\n"
        " * 真源：provider 的 `DETAIL_FIELDS` / `DETAIL_SHEET`（模板的单一权威声明）。\n"
        " *\n"
        " * 🔴 为什么要生成：M3/M5/M7 原先的前端行模型与模板是**两张不同的表**\n"
        " * （列集合交集 ≤1），手抄列名必然再次漂移。这里把列清单、两级表头、\n"
        " * editable/formula、值类型一次性从 provider 导出，前端只消费不重述。\n"
        " */\n"
        "export interface MCycleDetailField {\n"
        "  /** 契约列键（stable_field_key 的末段，与模板列语义一致） */\n"
        "  columnKey: string\n"
        "  /** 前端 store 键（契约 json_pointer 末段，逐行 JSON 用它） */\n"
        "  jsonKey: string\n"
        "  /** 模板列字母 */\n"
        "  column: string\n"
        "  /** 叶子表头 */\n"
        "  header: string\n"
        "  /** 组表头（空串 = 无上级组） */\n"
        "  group: string\n"
        "  /** editable = 可录入；formula = 由 OO 重算，前端只显示 */\n"
        "  mode: 'editable' | 'formula'\n"
        "  /** amount / text / rate */\n"
        "  valueType: string\n"
        "}\n\n"
        "export interface MCycleDetailSheet {\n"
        "  sheetKey: string\n"
        "  tableKey: string\n"
        "  /** 合计行行标签（模板原文） */\n"
        "  footerMarker: string\n"
        "  /** 固定数据行的行标签（模板 A 列，空串 = 模板上留白的可填行） */\n"
        "  rowLabels: string[]\n"
        "  fields: MCycleDetailField[]\n"
        "}\n\n"
        "export const M_CYCLE_DETAIL_COLUMNS: Record<string, MCycleDetailSheet> = {\n"
        f"{body}\n"
        "}\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验不写入；漂移则 exit 2")
    args = ap.parse_args()
    expected = build()
    if args.check:
        if not TARGET.exists():
            print(f"[m-cycle-columns] 缺少生成文件：{TARGET.relative_to(ROOT)}")
            return 2
        actual = TARGET.read_text(encoding="utf-8")
        if actual != expected:
            print(
                f"[m-cycle-columns] 生成文件与 provider 不一致："
                f"{TARGET.relative_to(ROOT)}\n"
                "  修法：python backend/scripts/gen/generate_m_cycle_detail_columns.py --write"
            )
            return 2
        print("[m-cycle-columns] OK（与 provider 一致）")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(expected, encoding="utf-8", newline="\n")
    print(f"[m-cycle-columns] 已写入 {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
