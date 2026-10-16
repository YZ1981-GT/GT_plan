"""存量项目附注表格结构与种子的差异分类（spec disclosure-note-template-word-realignment Task 11，design §4.2）。

只读、纯函数。每节按表序逐张比对库内 ``table_data`` 与种子 ``tables``：

- 表数不同（节级）：库内表数 ≠ 种子表数（库内无表也算）；
- 逐张（按位序配对到较短一侧）：列增减（列数不同）＞ 行增减（行标签序列不同）＞ 仅表头文字不同（列数、行标签都同，
  表名或表头文字不同）＞ 一致。一张表只归一类，取最重的那一类。

比对两次：库内原样，以及经读时增强 ``enrich_note_table_data``（详情端点返回前做的那一步）之后 —— 后者才是用户
在编辑器里看到的；两者之差 = 读时增强已经替库内补上的部分。
"""
from __future__ import annotations

import copy
from typing import Any

CLASSES = ("一致", "仅表头文字不同", "列增减", "行增减")


def db_tables(table_data: Any) -> list[dict[str, Any]]:
    """库内一节的表：多表格式取 ``_tables``；旧单表格式（顶层 rows）算一张；JSON null / 空算 0 张。"""
    if not isinstance(table_data, dict) or not table_data:
        return []
    tables = table_data.get("_tables")
    if isinstance(tables, list):
        return [t for t in tables if isinstance(t, dict)]
    return [table_data] if isinstance(table_data.get("rows"), list) else []


def _labels(tbl: dict[str, Any]) -> list[str]:
    return [str(r.get("label") or "").strip() if isinstance(r, dict) else str(r or "").strip()
            for r in tbl.get("rows") or []]


def _headers(tbl: dict[str, Any]) -> list[str]:
    return [str(h or "").strip() for h in tbl.get("headers") or []]


def classify_table(db: dict[str, Any], seed: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    dh, sh = _headers(db), _headers(seed)
    dl, sl = _labels(db), _labels(seed)
    if len(dh) != len(sh):
        return "列增减", {"db_headers": dh, "seed_headers": sh}
    if dl != sl:
        return "行增减", {"db_rows": len(dl), "seed_rows": len(sl),
                        "only_db": [x for x in dl if x not in sl][:8], "only_seed": [x for x in sl if x not in dl][:8]}
    name_d, name_s = str(db.get("name") or "").strip(), str(seed.get("name") or "").strip()
    if dh != sh or name_d != name_s:
        squash = lambda xs: [x.replace(" ", "").replace("\u3000", "") for x in xs]  # noqa: E731
        return "仅表头文字不同", {"db_headers": dh, "seed_headers": sh, "db_name": name_d, "seed_name": name_s,
                             "whitespace_only": squash(dh) == squash(sh) and squash([name_d]) == squash([name_s])}
    return "一致", {}


def compare_section(table_data: Any, seed_tables: list[dict[str, Any]]) -> dict[str, Any]:
    """一节的比对结果：``{"db": n, "seed": m, "count_mismatch": bool, "tables": [(类, 细节), …]}``。"""
    db = db_tables(table_data)
    seed = [t for t in seed_tables or [] if isinstance(t, dict)]
    pairs = [classify_table(d, s) for d, s in zip(db, seed)]
    return {"db": len(db), "seed": len(seed), "count_mismatch": len(db) != len(seed), "tables": pairs}


def enriched(table_data: Any, template_type: str, note_section: str) -> Any:
    """读时增强后的副本（与详情端点同一函数；不改入参）。"""
    from app.services.note_table_enrichment import enrich_note_table_data

    out = copy.deepcopy(table_data)
    if isinstance(out, dict):
        enrich_note_table_data(out, template_type, note_section)
    return out


def summarize(results: list[dict[str, Any]]) -> dict[str, int]:
    counts = {c: 0 for c in CLASSES}
    counts["表数不同（节）"] = sum(r["count_mismatch"] for r in results)
    counts["比对节数"] = len(results)
    for r in results:
        for cls, _detail in r["tables"]:
            counts[cls] += 1
    counts["其中仅空白差异"] = sum(1 for r in results for cls, d in r["tables"]
                             if cls == "仅表头文字不同" and d.get("whitespace_only"))
    return counts
