"""附注模板列元数据 / 表名 / guidance 覆盖率与 legacy 快照就绪度探针（只读）。

spec: note-template-columns-and-legacy-snapshot-closure（Task 1）

判据真源
--------
* 模板侧 = ``backend/data/note_template_{listed,soe}.json``
* 母公司章排除 = ``app.services.parent_company_note_sections.is_parent_company_section``
  （**按章节号逐字相等**，不是 ``section_id`` 前缀 —— listed 的 ``chapter-12-*``
  是「十二、股份支付」而非母公司章，按前缀判会把它误排除，见 Notes）
* 表头泄漏判据 = ``migrate_legacy_note_snapshots._name_is_meaningful`` 取反
  （R1.6：复用既有真源，不另写一份）
* per-cycle 覆盖面 = ``backend/data/note_workpaper_sync_registry.json``
  （由前端 ``*NoteSectionMap.ts`` 生成，是「该章节有对应底稿披露 sheet」的唯一机器可读真源）

用法
----
    python backend/scripts/diagnose/diagnose_note_columns_coverage.py
    python backend/scripts/diagnose/diagnose_note_columns_coverage.py --db
    python backend/scripts/diagnose/diagnose_note_columns_coverage.py --out backend/data/note_columns_coverage_baseline.json

约束
----
* 全程只读（无 UPDATE/INSERT/DELETE）。
* 控制台输出只用 ASCII 标记（``[OK]`` / ``[ERR]`` / ``[WARN]``）—— GBK 控制台
  遇 emoji 会在写盘之后抛 ``UnicodeEncodeError``，让人误判执行失败。
* 结果一律由脚本自己 ``Path.write_text(..., encoding="utf-8")`` 写盘，
  不依赖 PowerShell 重定向（会腌坏 UTF-8 中文）。
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve()
BACKEND_ROOT = _HERE.parents[2]
REPO_ROOT = _HERE.parents[3]
DATA_DIR = BACKEND_ROOT / "data"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

VARIANTS = ("listed", "soe")
TEMPLATE_PATHS = {v: DATA_DIR / f"note_template_{v}.json" for v in VARIANTS}
REGISTRY_PATH = DATA_DIR / "note_workpaper_sync_registry.json"
DEFAULT_OUT = DATA_DIR / "note_columns_coverage_baseline.json"


# ---------------------------------------------------------------------------
# 判据真源复用
# ---------------------------------------------------------------------------


def _load_migrator():
    """按文件路径加载 ``migrate_legacy_note_snapshots``（scripts/fix 不是包）。"""
    path = BACKEND_ROOT / "scripts" / "fix" / "migrate_legacy_note_snapshots.py"
    spec = importlib.util.spec_from_file_location(
        "note_legacy_migrator_for_probe", path
    )
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"无法加载迁移器：{path}")
    mod = importlib.util.module_from_spec(spec)
    # dataclass 装饰器要求模块已在 sys.modules 里，否则 _is_type 会拿到 None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


MIGRATOR = _load_migrator()
name_is_meaningful = MIGRATOR._name_is_meaningful  # noqa: SLF001 - 有意复用唯一真源


def _load_parent_sections() -> dict[str, frozenset[str]]:
    from app.services.parent_company_note_sections import (  # noqa: PLC0415
        load_parent_company_sections,
    )

    return load_parent_company_sections()


def _load_registry_sections() -> dict[str, set[str]]:
    """返回 ``{variant: {章节号}}`` —— 有底稿披露 sheet 且已被 per-cycle 消费的章节。"""
    out: dict[str, set[str]] = {v: set() for v in VARIANTS}
    try:
        raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception as err:  # noqa: BLE001
        print(f"[WARN] 读不到 registry（{REGISTRY_PATH}）：{err}")
        return out
    for entry in raw.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        for variant in VARIANTS:
            code = entry.get(variant)
            if isinstance(code, str) and code.strip():
                out[variant].add(code.strip())
    return out


def _load_registry_wp_by_section() -> dict[str, dict[str, list[str]]]:
    out: dict[str, dict[str, list[str]]] = {v: {} for v in VARIANTS}
    try:
        raw = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return out
    for entry in raw.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        wp = str(entry.get("wp_code") or "")
        for variant in VARIANTS:
            code = entry.get(variant)
            if isinstance(code, str) and code.strip() and wp:
                out[variant].setdefault(code.strip(), []).append(wp)
    return out


# ---------------------------------------------------------------------------
# 分类
# ---------------------------------------------------------------------------

SCOPE_PARENT = "parent_chapter"          # ② 母公司章 → A spec
SCOPE_REGISTRY = "registry_covered"      # 有底稿披露 sheet 且已被 per-cycle map 消费
SCOPE_UNREGISTERED = "unregistered"      # 无 per-cycle map（① 真缺口 或 ③ 非科目章节）


def classify_section(
    *,
    section_number: str,
    variant: str,
    parent_sections: dict[str, frozenset[str]],
    registry_sections: dict[str, set[str]],
) -> str:
    code = (section_number or "").strip()
    if code and code in parent_sections.get(variant, frozenset()):
        return SCOPE_PARENT
    if code and code in registry_sections.get(variant, set()):
        return SCOPE_REGISTRY
    return SCOPE_UNREGISTERED


# ---------------------------------------------------------------------------
# 模板扫描
# ---------------------------------------------------------------------------

_HTML_RE = re.compile(r"<[^>]+>")


def _norm_ws(s: Any) -> str:
    return re.sub(r"\s+", "", str(s or ""))


def _column_stance(col: Any) -> str:
    """单列的两级结构表态：``flat`` / ``group`` / ``none``。"""
    if not isinstance(col, dict):
        return "none"
    if col.get("flat") is True:
        return "flat"
    if isinstance(col.get("group"), str) and col["group"].strip():
        return "group"
    return "none"


def scan_table(table: Any, *, index: int) -> dict[str, Any]:
    t = table if isinstance(table, dict) else {}
    name = str(t.get("name") or "")
    headers = t.get("headers") if isinstance(t.get("headers"), list) else []
    columns = t.get("columns") if isinstance(t.get("columns"), list) else []
    guidance = str(t.get("guidance") or "")
    rows = t.get("rows") if isinstance(t.get("rows"), list) else []
    stances = [_column_stance(c) for c in columns]
    labels = [str(c.get("label") or "") for c in columns if isinstance(c, dict)]
    groups = [str(c.get("group") or "") for c in columns if isinstance(c, dict)]
    return {
        "index": index,
        "name": name,
        "header_count": len(headers),
        "column_count": len(columns),
        "row_count": len(rows),
        "has_guidance": bool(guidance.strip()),
        "guidance_has_bold": "**" in guidance,
        "guidance_has_html": bool(_HTML_RE.search(guidance)),
        "is_empty_name": not name.strip(),
        "is_leak_name": bool(name.strip()) and not name_is_meaningful(name, headers),
        "headers_have_html": any(_HTML_RE.search(str(h or "")) for h in headers),
        "labels_have_html": any(_HTML_RE.search(x) for x in labels + groups),
        "stance_none": stances.count("none"),
        "stance_flat": stances.count("flat"),
        "stance_group": stances.count("group"),
        "legacy_aliases": list(t.get("legacy_aliases") or []),
        "row_types": dict(
            Counter(
                str(r.get("row_type") or "(none)")
                for r in rows
                if isinstance(r, dict)
            )
        ),
    }


def scan_templates() -> dict[str, Any]:
    parent_sections = _load_parent_sections()
    registry_sections = _load_registry_sections()
    registry_wp = _load_registry_wp_by_section()

    result: dict[str, Any] = {}
    for variant in VARIANTS:
        path = TEMPLATE_PATHS[variant]
        raw = json.loads(path.read_text(encoding="utf-8"))
        sections_out: list[dict[str, Any]] = []
        for sec in raw.get("sections") or []:
            if not isinstance(sec, dict):
                continue
            number = str(sec.get("section_number") or "")
            scope = classify_section(
                section_number=number,
                variant=variant,
                parent_sections=parent_sections,
                registry_sections=registry_sections,
            )
            tables = sec.get("tables") if isinstance(sec.get("tables"), list) else []
            tinfo = [scan_table(t, index=i) for i, t in enumerate(tables)]
            names = [x["name"] for x in tinfo]
            dup_names = {n for n, c in Counter(names).items() if c > 1}
            for x in tinfo:
                x["dup_group"] = x["name"] if x["name"] in dup_names else None
            sections_out.append(
                {
                    "section_id": str(sec.get("section_id") or ""),
                    "section_number": number,
                    "section_title": str(sec.get("section_title") or ""),
                    "level": sec.get("level"),
                    "scope": scope,
                    "wp_codes": registry_wp.get(variant, {}).get(number, []),
                    "table_count": len(tinfo),
                    "has_dup_name": bool(dup_names),
                    "tables": tinfo,
                }
            )
        result[variant] = {
            "template_path": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "sections": sections_out,
            "summary": _summarize_variant(sections_out),
        }
    result["_parent_sections"] = {v: sorted(parent_sections[v]) for v in VARIANTS}
    return result


def _summarize_variant(sections: list[dict[str, Any]]) -> dict[str, Any]:
    per_scope: dict[str, Counter] = {}
    total = Counter()
    row_types: Counter = Counter()
    for sec in sections:
        bucket = per_scope.setdefault(sec["scope"], Counter())
        for t in sec["tables"]:
            for c in (bucket, total):
                c["tables"] += 1
                if t["column_count"] == 0:
                    c["cols0"] += 1
                if t["column_count"] and t["column_count"] != t["header_count"]:
                    c["cols_ne_headers"] += 1
                if not t["has_guidance"]:
                    c["no_guidance"] += 1
                if t["guidance_has_bold"]:
                    c["guidance_bold"] += 1
                if t["guidance_has_html"]:
                    c["guidance_html"] += 1
                if t["is_empty_name"]:
                    c["empty_name"] += 1
                if t["is_leak_name"]:
                    c["leak_name"] += 1
                if t["headers_have_html"] or t["labels_have_html"]:
                    c["html_in_headers"] += 1
                if t["column_count"] and t["stance_none"]:
                    c["stance_none_tables"] += 1
            row_types.update(t["row_types"])
        for c in (bucket, total):
            c["sections"] += 1
            if sec["has_dup_name"]:
                c["dup_sections"] += 1
    return {
        "total": dict(total),
        "by_scope": {k: dict(v) for k, v in sorted(per_scope.items())},
        "row_types": dict(sorted(row_types.items())),
    }


# ---------------------------------------------------------------------------
# legacy 快照扫描（--db）
# ---------------------------------------------------------------------------

_LEGACY_SQL = """
SELECT id::text AS note_id,
       project_id::text AS project_id,
       note_section,
       section_title,
       source_template,
       table_data
FROM disclosure_notes
WHERE is_deleted = false
ORDER BY project_id, note_section
"""


def _rows_of(obj: Any) -> list[dict[str, Any]]:
    rows = obj.get("rows") if isinstance(obj, dict) else None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _is_legacy_snapshot(td: Any) -> bool:
    if not isinstance(td, dict):
        return False
    sub = td.get("sub_table_data")
    if isinstance(sub, dict) and sub:
        return False
    has_tables = isinstance(td.get("_tables"), list) and td["_tables"]
    has_rows = bool(_rows_of(td))
    return bool(has_tables or has_rows)


def _template_index(templates: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    """``{variant: {section_number: {"tables": [...], "scope": ...}}}``"""
    idx: dict[str, dict[str, dict[str, Any]]] = {v: {} for v in VARIANTS}
    for variant in VARIANTS:
        for sec in templates[variant]["sections"]:
            idx[variant][sec["section_number"]] = {
                "scope": sec["scope"],
                "tables": sec["tables"],
            }
    return idx


def classify_legacy_note(
    *,
    note_section: str,
    table_data: dict[str, Any],
    tpl_section: dict[str, Any] | None,
) -> dict[str, Any]:
    """逐表 join 模板，产出四分类 + 纯名漂移判定（纯函数，供守卫复用）。"""
    legacy_tables = table_data.get("_tables")
    legacy_tables = (
        [t for t in legacy_tables if isinstance(t, dict)]
        if isinstance(legacy_tables, list)
        else []
    )
    top_rows = _rows_of(table_data)
    out: dict[str, Any] = {
        "note_section": note_section,
        "legacy_table_count": len(legacy_tables),
        "top_row_count": len(top_rows),
        "migratable": 0,
        "tpl_no_columns": 0,
        "not_in_tpl": 0,
        "verdict": "",
    }
    if tpl_section is None:
        out["verdict"] = "section_not_in_template"
        out["not_in_tpl"] = len(legacy_tables)
        return out

    tpl_tables = tpl_section["tables"]
    tpl_by_name = {t["name"]: t for t in tpl_tables if t["name"]}
    snap_names = [str(t.get("name") or "") for t in legacy_tables]

    for nm in snap_names:
        tpl = tpl_by_name.get(nm)
        if tpl is None:
            out["not_in_tpl"] += 1
        elif tpl["column_count"] == 0:
            out["tpl_no_columns"] += 1
        else:
            out["migratable"] += 1

    if not legacy_tables:
        out["verdict"] = "rows_only" if top_rows else "empty"
        return out

    matched = [n for n in snap_names if n in tpl_by_name]
    snap_meaningful = [
        name_is_meaningful(n, legacy_tables[i].get("headers"))
        for i, n in enumerate(snap_names)
    ]
    tpl_all_meaningful = all(
        not t["is_leak_name"] and not t["is_empty_name"] for t in tpl_tables
    )
    if not matched and len(legacy_tables) == len(tpl_tables) and tpl_all_meaningful and not any(snap_meaningful):
        out["verdict"] = "pure_name_drift"
    elif len(matched) == len(snap_names) and len(set(snap_names)) == len(snap_names):
        out["verdict"] = "by_name"
    elif len(legacy_tables) == len(tpl_tables):
        out["verdict"] = "positional"
    else:
        out["verdict"] = "count_mismatch"
    return out


async def scan_legacy(templates: dict[str, Any]) -> dict[str, Any]:
    import sqlalchemy as sa  # noqa: PLC0415

    from app.core.database import async_session  # noqa: PLC0415

    tpl_idx = _template_index(templates)
    details: list[dict[str, Any]] = []
    counts: Counter = Counter()
    verdicts: Counter = Counter()

    async with async_session() as db:
        rows = (await db.execute(sa.text(_LEGACY_SQL))).mappings().all()

    for row in rows:
        counts["notes_total"] += 1
        td = row["table_data"]
        if isinstance(td, str):
            try:
                td = json.loads(td)
            except Exception:  # noqa: BLE001
                td = None
        if isinstance(td, dict) and isinstance(td.get("sub_table_data"), dict) and td["sub_table_data"]:
            counts["notes_has_sub"] += 1
            continue
        if not _is_legacy_snapshot(td):
            counts["notes_other"] += 1
            continue
        counts["legacy_sections"] += 1
        variant = "listed" if str(row["source_template"] or "").startswith("listed") else "soe"
        note_section = str(row["note_section"] or "").strip()
        tpl_section = tpl_idx[variant].get(note_section) or tpl_idx[
            "soe" if variant == "listed" else "listed"
        ].get(note_section)
        info = classify_legacy_note(
            note_section=note_section, table_data=td, tpl_section=tpl_section
        )
        info["project_id"] = row["project_id"]
        info["variant"] = variant
        info["scope"] = (tpl_section or {}).get("scope", "section_not_in_template")
        counts["legacy_tables"] += info["legacy_table_count"]
        counts["tbl_migratable"] += info["migratable"]
        counts["tbl_tpl_no_columns"] += info["tpl_no_columns"]
        counts["tbl_not_in_tpl"] += info["not_in_tpl"]
        if info["legacy_table_count"] == 0:
            counts["rows_only_sections"] += 1
        if info["legacy_table_count"] and info["tpl_no_columns"] == 0 and info["not_in_tpl"] == 0:
            counts["sections_all_migratable"] += 1
        elif info["legacy_table_count"]:
            counts["sections_blocked"] += 1
        verdicts[info["verdict"]] += 1
        details.append(info)

    return {
        "counts": dict(counts),
        "verdicts": dict(sorted(verdicts.items())),
        "details": details,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_template_report(templates: dict[str, Any]) -> None:
    for variant in VARIANTS:
        s = templates[variant]["summary"]
        t = s["total"]
        print(f"[OK] {variant}: " + " ".join(f"{k}={v}" for k, v in sorted(t.items())))
        for scope, c in s["by_scope"].items():
            print(
                f"       - {scope}: "
                + " ".join(f"{k}={v}" for k, v in sorted(c.items()))
            )
        print(f"       row_types: {s['row_types']}")


def _print_legacy_report(legacy: dict[str, Any]) -> None:
    print("[OK] legacy: " + " ".join(f"{k}={v}" for k, v in sorted(legacy["counts"].items())))
    print(f"       verdicts: {legacy['verdicts']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__ or "")
    ap.add_argument("--db", action="store_true", help="额外只读连库扫 legacy 快照")
    ap.add_argument("--out", default=None, help="结果 JSON 落盘路径")
    ap.add_argument("--details", action="store_true", help="控制台打印逐章节明细")
    args = ap.parse_args(argv)

    templates = scan_templates()
    _print_template_report(templates)

    legacy: dict[str, Any] | None = None
    if args.db:
        try:
            legacy = asyncio.run(scan_legacy(templates))
            _print_legacy_report(legacy)
        except Exception as err:  # noqa: BLE001
            print(f"[ERR] DB 未连接或查询失败：{err!r}")
            print("[WARN] 已降级为仅模板侧输出（legacy 段缺失，不是 0）")
            legacy = {"error": repr(err)}

    if args.details:
        for variant in VARIANTS:
            for sec in templates[variant]["sections"]:
                gaps = [t for t in sec["tables"] if t["column_count"] == 0]
                if not gaps:
                    continue
                print(
                    f"  [{variant}] {sec['section_number']} | {sec['scope']} | "
                    f"cols0={len(gaps)}/{sec['table_count']} | wp={sec['wp_codes']}"
                )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "templates": templates,
        "legacy": legacy,
    }
    out_path = Path(args.out) if args.out else DEFAULT_OUT
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"[OK] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
