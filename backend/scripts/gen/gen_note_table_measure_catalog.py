"""生成附注稳定 table/column ID 与七类显示度量目录。

用法：
  python backend/scripts/gen/gen_note_table_measure_catalog.py --check
  python backend/scripts/gen/gen_note_table_measure_catalog.py --write

单体模板首次写入 ``table_id``，之后原样保留；合并模板复用章节已有 UUID ``id``。
列 ID 由 table UUID + 规范 ColumnKey + 同键序号确定，标题行库负责多级表头规范化。
ratio scale 在目录中显式落为 percent_points（沿用现存附注持久化值 20=20% 的合同），请求期不再猜。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.contracts.display_measure import DisplayMeasureKind, build_measure_spec  # noqa: E402
from app.services.note_table_header_library import column_keys  # noqa: E402

DATA = BACKEND / "data"
TARGET = DATA / "note_table_measure_catalog.json"
TABLE_NS = uuid.UUID("9ced9ca3-0c7e-4b9d-ad11-d662f8dc7761")


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _uuid(value: Any, *, seed: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return str(uuid.uuid5(TABLE_NS, seed))


def _measure_kind(base_kind: str, label: str) -> tuple[str, str | None, str]:
    compact = "".join(str(label).split())
    if base_kind == "label" or base_kind == "text":
        return DisplayMeasureKind.text.value, None, "header-library"
    if base_kind == "ratio":
        # 表头只能证明「比例」，不能证明原值是 0.2 还是 20。没有经人工校验的逐表 override
        # 时故意不填 ratio_scale，运行时将整表标 invalid 并按元口径原样展示，不能静默错放大 100 倍。
        return DisplayMeasureKind.ratio.value, None, "unresolved-ratio-scale"
    if "汇率" in compact:
        return DisplayMeasureKind.exchange_rate.value, None, "header:汇率"
    if any(word in compact for word in ("单价", "平均价格", "每股价格")):
        return DisplayMeasureKind.unit_price.value, None, "header:单价"
    if any(word in compact for word in ("人数", "家数", "户数", "笔数", "项数", "次数")):
        return DisplayMeasureKind.count.value, None, "header:计数"
    if any(word in compact for word in ("数量", "股数", "面积", "重量")):
        return DisplayMeasureKind.quantity.value, None, "header:数量"
    return DisplayMeasureKind.amount.value, None, "header-library"


def _columns(table: dict[str, Any], table_id: str, *, identity: tuple[str, str]) -> list[dict[str, Any]]:
    keys = column_keys(table, identity=identity)
    occurrences: dict[str, int] = {}
    result: list[dict[str, Any]] = []
    for key in keys:
        occurrence = occurrences.get(key.key, 0)
        occurrences[key.key] = occurrence + 1
        kind, scale, source = _measure_kind(key.kind, key.label)
        if not (kind == DisplayMeasureKind.ratio.value and scale is None):
            build_measure_spec(kind, scale, locator=f"{identity[0]}:{identity[1]}:{key.index}")
        result.append({
            "column_id": str(uuid.uuid5(uuid.UUID(table_id), f"{key.key}#{occurrence}")),
            "index": key.index,
            "path": list(key.path),
            "semantic_key": key.key,
            "kind": kind,
            "ratio_scale": scale,
            "source": source,
        })
    return result


def _fingerprint(table: dict[str, Any]) -> str:
    payload = {
        "headers": table.get("headers") or [],
        "multi_header": table.get("multi_header"),
        "header_rows": table.get("header_rows"),
        "column_groups": table.get("_column_groups"),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _standalone(variant: str, *, write_ids: bool) -> tuple[list[dict[str, Any]], bool]:
    path = DATA / f"note_template_{variant}.json"
    data = _read(path)
    entries: list[dict[str, Any]] = []
    changed = False
    for section in data.get("sections") or []:
        section_id = str(section.get("section_number") or section.get("section_id") or "").strip()
        for index, table in enumerate(section.get("tables") or []):
            if not isinstance(table, dict):
                continue
            table_id = _uuid(table.get("table_id"), seed=f"standalone:{variant}:{section_id}:{index}")
            if table.get("table_id") != table_id:
                table["table_id"] = table_id
                changed = True
            entries.append({
                "variant": variant,
                "section_id": section_id,
                "table_index": index,
                "table_id": table_id,
                "table_name": str(table.get("name") or ""),
                "header_fingerprint": _fingerprint(table),
                "columns": _columns(table, table_id, identity=(variant, table_id)),
            })
    if changed and write_ids:
        path.write_text(_dump(data), encoding="utf-8", newline="\n")
    return entries, changed


def _consolidated(variant: str) -> list[dict[str, Any]]:
    path = DATA / f"consol_note_sections_{variant}.json"
    data = _read(path)
    entries: list[dict[str, Any]] = []
    for index, section in enumerate(data):
        if not isinstance(section, dict) or not section.get("headers"):
            continue
        section_id = str(section.get("section_id") or "").strip()
        table_id = _uuid(section.get("id"), seed=f"consolidated:{variant}:{section_id}")
        if str(section.get("id")) != table_id:
            raise ValueError(f"合并模板 {variant}:{section_id} 缺稳定 UUID id")
        entries.append({
            "variant": f"consol_{variant}",
            "section_id": section_id,
            "table_index": index,
            "table_id": table_id,
            "table_name": str(section.get("title") or ""),
            "header_fingerprint": _fingerprint(section),
            "columns": _columns(section, table_id, identity=(variant, section_id)),
        })
    return entries


def build(*, write_ids: bool) -> tuple[dict[str, Any], bool]:
    entries: list[dict[str, Any]] = []
    ids_changed = False
    for variant in ("soe", "listed"):
        part, changed = _standalone(variant, write_ids=write_ids)
        entries.extend(part)
        ids_changed = ids_changed or changed
        entries.extend(_consolidated(variant))
    entries.sort(key=lambda row: (row["variant"], row["section_id"], row["table_index"]))
    table_ids = [row["table_id"] for row in entries]
    column_ids = [col["column_id"] for row in entries for col in row["columns"]]
    if len(table_ids) != len(set(table_ids)):
        raise ValueError("table_id 不唯一")
    if len(column_ids) != len(set(column_ids)):
        raise ValueError("column_id 不唯一")
    return {"schema_version": 1, "entries": entries}, ids_changed


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()
    catalog, ids_changed = build(write_ids=args.write)
    rendered = _dump(catalog)
    if args.write:
        TARGET.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"已写入 {len(catalog['entries'])} 张表：{TARGET}")
        return 0
    if ids_changed:
        print("单体附注模板缺 table_id；请先运行 --write", file=sys.stderr)
        return 2
    if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != rendered:
        print("note_table_measure_catalog.json 与模板不一致；请运行 --write", file=sys.stderr)
        return 2
    print(f"附注度量目录一致：{len(catalog['entries'])} 张表")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
