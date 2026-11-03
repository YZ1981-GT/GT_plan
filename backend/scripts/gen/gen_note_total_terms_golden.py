"""附注合计构成 golden：按单体 / 合并模板逐表算合计构成，前端 ``noteTotalTerms.ts`` 用同一份逐表对照（前后端交叉锁死）。

spec note-pull-header-formula-closure R5。判定真源 = ``app/services/note_total_terms.py``；前端改判定、后端改判定、
模板改行，任一处变化都要重跑本脚本（``--check`` 守卫：``tests/test_note_total_terms.py``）。

内容：
* ``single``：单体模板（``note_template_{soe,listed}.json``）里有合计 / 小计行的表 —— 键 ``口径|章节下标|表下标``，
  合计构成 ``plans``（行号 → [[行号, 符号], …]）、判不准的合计行 ``reasons``、金额列 ``amount_columns``；
* ``consol``：合并模板（``consol_note_sections_{soe,listed}.json``）同上，另带后端补齐的行类型 ``types``（只列
  非 data 的行号 → 类型）与 ``column_groups``（合并附注编辑器拿到的就是这两项）；
* ``label_types``：合并模板里按行名判为合计 / 小计的行名（其余行名一律 data）；
* ``ratio_pattern`` / ``text_pattern``：标题行库判比例 / 说明列的规则（前端常量逐字对照）。

用法::

    python scripts/gen/gen_note_total_terms_golden.py --write   # 生成 / 更新
    python scripts/gen/gen_note_total_terms_golden.py --check   # 与现算不一致 exit 2
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

DATA = BACKEND / "data"
OUT = DATA / "note_total_terms_golden.json"


def _plans(plans: dict[int, list[tuple[int, int]]]) -> dict[str, list[list[int]]]:
    return {str(k): [[r, s] for r, s in v] for k, v in sorted(plans.items())}


def build() -> dict[str, Any]:
    from app.services.consol_note_formula_service import consol_note_tables
    from app.services.note_formula_tables import amount_columns
    from app.services.note_total_terms import label_row_type, row_kind, total_terms

    vocab = json.loads((DATA / "note_table_header_vocabulary.json").read_text(encoding="utf-8"))
    single: list[dict[str, Any]] = []
    for tt in ("soe", "listed"):
        doc = json.loads((DATA / f"note_template_{tt}.json").read_text(encoding="utf-8"))
        for si, sec in enumerate(doc.get("sections") or []):
            for ti, table in enumerate(sec.get("tables") or []):
                rows = table.get("rows") or []
                if not any(row_kind(r) in ("total", "subtotal") for r in rows):
                    continue
                plans, reasons = total_terms(rows)
                single.append({"key": f"{tt}|{si}|{ti}", "plans": _plans(plans), "reasons": sorted(reasons),
                               "amount_columns": amount_columns(table)})
    consol: list[dict[str, Any]] = []
    label_types: dict[str, str] = {}
    for tt in ("soe", "listed"):
        for table in consol_note_tables(tt):
            rows = table.get("rows") or []
            types = [str(t) for t in table.get("_row_types") or []]
            labels = [str(r[0]) if isinstance(r, list) and r else "" for r in rows]
            for text in labels:
                kind = label_row_type(text)
                if kind != "data":
                    label_types[text] = kind
            shaped = [{"label": text, "row_type": types[i] if i < len(types) else "data"}
                      for i, text in enumerate(labels)]
            if not any(row_kind(r) in ("total", "subtotal") for r in shaped):
                continue
            plans, reasons = total_terms(shaped)
            consol.append({"key": f"{tt}|{table.get('section_id')}", "rows": len(rows),
                           "types": {str(i): t for i, t in enumerate(types) if t != "data"},
                           "column_groups": table.get("_column_groups") or None,
                           "plans": _plans(plans), "reasons": sorted(reasons),
                           "amount_columns": amount_columns(table)})
    return {
        "_comment": "附注合计构成 golden（前后端交叉锁死，spec note-pull-header-formula-closure R5）。"
                    "由 backend/scripts/gen/gen_note_total_terms_golden.py --write 生成，勿手改。",
        "ratio_pattern": vocab.get("ratio_pattern"),
        "text_pattern": vocab.get("text_pattern"),
        "single": single,
        "consol": consol,
        "label_types": dict(sorted(label_types.items())),
    }


def render() -> str:
    """一表一行（diff 按表看），输出确定：内容不变则字节不变。"""
    doc = build()

    def one(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    lines = ["{"]
    keys = list(doc)
    for n, key in enumerate(keys):
        tail = "," if n < len(keys) - 1 else ""
        value = doc[key]
        if isinstance(value, list):
            lines.append(f" {one(key)}:[")
            lines.extend(f"  {one(item)}{',' if i < len(value) - 1 else ''}" for i, item in enumerate(value))
            lines.append(f" ]{tail}")
        else:
            lines.append(f" {one(key)}:{one(value)}{tail}")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = render()
    current = OUT.read_text(encoding="utf-8") if OUT.exists() else None
    if args.check:
        if current != text:
            print(f"[drift] {OUT.name} 与现算不一致：python scripts/gen/gen_note_total_terms_golden.py --write")
            return 2
        print(f"[ok] {OUT.name} 与现算一致")
        return 0
    if current == text:
        print(f"[ok] {OUT.name} 未变化")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"[ok] 写入 {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
