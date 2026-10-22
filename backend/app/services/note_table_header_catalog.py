"""附注表格标题行库 · 库目录生成（四版：国企 / 上市 × 单体 / 合并）。

spec: consol-note-header-library-and-node-reaggregate（design §6）

目录是生成产物：给维护的人看每张表的标题行、逐列语义键、续表关系，以及每张合并表对到单体哪张表、
哪些列对上了；给 CI 比对（``--check``）、给测试断言覆盖率。请求期不读它 —— 识别口径只在
``note_table_header_library`` / ``note_table_header_match`` 与词表里。

- 单体：``note_template_{std}.json`` 里适用单体口径的章节，表标识 ``章节号#表序``；
- 合并：``consol_note_sections_{std}.json``，表标识 ``section_id``，按 section_id 前缀分组算续表；
- 对应：按 ``consol_note_section_mapping.json`` 找单体章节，再用 ``choose_unit`` 选表、``match_columns`` 对列。

输出确定：无时间戳，内容不变则字节不变；每张表 / 每条对应 / 每条异常一行，便于看 diff。
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from app.services.consol_note_headers import multi_header_rows, normalize_consol_note_section
from app.services.note_table_header_library import (
    ColumnKey,
    base_key,
    column_keys,
    column_paths,
    continuation_links,
    load_vocabulary,
    norm,
    table_identity,
)
from app.services.note_table_header_match import choose_unit

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
LIBRARY_PATH = DATA_DIR / "note_table_header_library.json"
STDS = ("soe", "listed")

__all__ = ["LIBRARY_PATH", "build_catalog", "check_catalog", "render_catalog", "standalone_sections"]


def _load(name: str) -> Any:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def standalone_sections(std: str) -> list[tuple[str, list[dict]]]:
    """单体口径章节（种子文件顺序）：[(章节键, 表列表)]；同号章节第 n 个（n ≥ 2）键为「章节号#n」。"""
    from app.services.note_section_catalog import section_applies_to_scope

    seen: Counter[str] = Counter()
    out: list[tuple[str, list[dict]]] = []
    for sec in _load(f"note_template_{std}.json").get("sections") or []:
        tables = [t for t in sec.get("tables") or [] if isinstance(t, dict)]
        if not tables or not section_applies_to_scope(sec, "standalone"):
            continue
        code = str(sec.get("section_number") or "").strip()
        seen[code] += 1
        out.append((code if seen[code] == 1 else f"{code}#{seen[code]}", tables))
    return out


def _consol_groups(std: str) -> list[tuple[str, list[dict]]]:
    groups: dict[str, list[dict]] = {}
    for entry in _load(f"consol_note_sections_{std}.json"):
        sid = str(entry.get("section_id") or "")
        groups.setdefault(sid.rsplit("-", 1)[0] if "-" in sid else sid, []).append(entry)

    def order(e: dict) -> tuple[int, str]:
        tail = str(e.get("section_id") or "").rsplit("-", 1)[-1]
        return (int(tail) if tail.isdigit() else 10**6, str(e.get("section_id")))

    return [(key, sorted(items, key=order)) for key, items in groups.items()]


# ─── 单张表 ──────────────────────────────────────────────────────────────────


def _header_rows(table: dict, paths: list[tuple[str, ...]], consol: bool) -> tuple[list, str | None]:
    """紧凑标题行 [[文字, 跨列, 跨行], ...]：合并表取展示用 header_rows；单体表由逐列路径按同一分区算法生成。"""
    width = len(table.get("headers") or [])
    try:
        if consol:
            rows = normalize_consol_note_section({
                "headers": table.get("headers") or [], "multi_header": table.get("multi_header"),
                "_column_groups": table.get("_column_groups"), "rows": [],
            })["header_rows"]
        else:
            depth = max((len(p) for p in paths), default=1) or 1
            grid = [[
                p[r] if r < len(p) and (c == 0 or paths[c - 1][: r + 1] != p[: r + 1]) else ""
                for c, p in enumerate(paths)
            ] for r in range(depth)]
            rows = multi_header_rows(grid, width) if width else []
    except (ValueError, TypeError, KeyError) as exc:
        return [], f"{type(exc).__name__}: {exc}"
    return [[[c["text"], c["colspan"], c["rowspan"]] for c in row] for row in rows], None


def _columns(keys: list[ColumnKey]) -> list[list[str]]:
    return [[k.label, k.key] for k in keys]


def _table_entries(
    variant: str, section: str, tables: list[dict], *, consol: bool, anomalies: list[dict],
) -> list[dict]:
    vocab = load_vocabulary()
    ids = [str(t.get("section_id")) if consol else f"{section}#{i}" for i, t in enumerate(tables)]
    links = continuation_links(
        tables, variant=variant, section=None if consol else section,
        table_ids=ids if consol else None, vocab=vocab,
    )
    out: list[dict] = []
    for i, table in enumerate(tables):
        name = str((table.get("title") if consol else table.get("name")) or "")
        identity = table_identity(variant, ids[i] if consol else f"{section}#{name}")
        keys = column_keys(table, identity=identity, vocab=vocab)
        paths = column_paths(table)
        header_rows, header_error = _header_rows(table, paths, consol)
        entry: dict[str, Any] = {"id": ids[i], "section": section, "name": name}
        period = next((k.period for k in keys[1:] if k.period), None)
        entry["period"] = period
        entry["header_rows"] = header_rows
        entry["columns"] = _columns(keys)
        link = links.get(i)
        if link is not None:
            entry["continuation"] = {
                "of": ids[link.of] if link.of is not None else None, "kind": link.kind, "via": link.via,
            }
        out.append(entry)
        _table_anomalies(variant, ids, i, table, keys, paths, link, header_error, consol, anomalies)
    if not consol:
        _section_anomalies(variant, ids, tables, links, anomalies)
    return out


def _anomaly(out: list[dict], variant: str, table_id: str, kind: str, detail: str) -> None:
    out.append({"variant": variant, "id": table_id, "kind": kind, "detail": detail})


def _table_anomalies(
    variant: str, ids: list[str], i: int, table: dict, keys: list[ColumnKey], paths: list[tuple[str, ...]],
    link: Any, header_error: str | None, consol: bool, out: list[dict],
) -> None:
    tid = ids[i]
    name = str((table.get("title") if consol else table.get("name")) or "")
    if header_error:
        _anomaly(out, variant, tid, "header_rows_invalid", header_error)
    if link is not None and link.of is None:
        _anomaly(out, variant, tid, "continuation_without_primary", name)
    if "续" in norm(name) and link is None:
        _anomaly(out, variant, tid, "xu_word_not_continuation", f"「{name[:40]}」含「续」但不是续表（旧规则会误判）")
    counts = Counter(k.key for k in keys[1:] if k.kind == "amount" and (k.period or k.measure))
    dup = sorted(k for k, n in counts.items() if n > 1)
    if dup:
        _anomaly(out, variant, tid, "duplicate_column_keys", "；".join(dup))
    if paths and paths[0] and any(p and p[0] == paths[0][0] for p in paths[1:]):
        _anomaly(out, variant, tid, "label_header_spans_data_columns", f"标签列表头「{paths[0][0]}」盖到数据列")
    multi = table.get("multi_header")
    if isinstance(multi, list) and len(multi) >= 2:
        last = [str(x or "").strip() for x in multi[-1]]
        if last and last[0] and not any(last[1:]):
            _anomaly(out, variant, tid, "header_row_has_data", f"多级表头末行只有首格「{last[0]}」（像数据行）")


def _section_anomalies(
    variant: str, ids: list[str], tables: list[dict], links: dict, out: list[dict],
) -> None:
    for i, table in enumerate(tables):
        idx = table.get("continuation_of_index")
        if idx is None:
            continue
        name = str(table.get("name") or "")
        if idx == i:
            _anomaly(out, variant, ids[i], "continuation_self_reference", f"continuation_of_index 指向自己：{name[:40]}")
        elif i not in links:
            _anomaly(out, variant, ids[i], "continuation_index_not_continuation",
                     f"continuation_of_index={idx} 但表名不是续表（并列表）：{name[:40]}")
        elif isinstance(idx, int) and links[i].of != idx:
            _anomaly(out, variant, ids[i], "continuation_index_disagrees",
                     f"种子标 #{idx}，按标记认到 {ids[links[i].of] if links[i].of is not None else '无'}")
    plain = [i for i in range(len(tables)) if i not in links]
    for a_pos, a in enumerate(plain):
        for b in plain[a_pos + 1:]:
            ta, tb = tables[a], tables[b]
            if base_key(ta.get("name")) != base_key(tb.get("name")) or not base_key(ta.get("name")):
                continue
            ka = [(k.measure, k.kind) for k in column_keys(ta)[1:]]
            kb = [(k.measure, k.kind) for k in column_keys(tb)[1:]]
            if ka == kb:
                _anomaly(out, variant, ids[b], "same_base_same_columns",
                         f"与 {ids[a]} 同基名同列结构（疑似新旧模板重复表）")


# ─── 单体 ↔ 合并对应 ─────────────────────────────────────────────────────────


def _correspondence(std: str, standalone: dict[str, list[dict]]) -> list[dict]:
    from app.services.consol_note_section_mapping import resolve_mapping_entry

    vocab = load_vocabulary()
    out: list[dict] = []
    for _group, entries in _consol_groups(std):
        for entry in entries:
            sid = str(entry.get("section_id"))
            mapped = resolve_mapping_entry(std, sid) or {}
            sec = mapped.get("standalone_note_section")
            target = column_keys(entry, identity=table_identity(f"{std}_consolidated", sid), vocab=vocab)
            amount = [k for k in target[1:] if k.kind == "amount" and (k.period or k.measure)]
            item: dict[str, Any] = {
                "consol": sid, "standalone_section": sec,
                "mapping_table": mapped.get("standalone_table_name"), "amount_columns": len(amount),
            }
            tables = standalone.get(sec) if sec else None
            if not sec or tables is None:
                item["via"] = "no_source" if not sec else "section_missing"
                out.append(item)
                continue
            variant = f"{std}_standalone"
            identities = [table_identity(variant, f"{sec}#{t.get('name') or ''}") for t in tables]
            choice = choose_unit(
                tables, target_keys=target, table_name=mapped.get("standalone_table_name"),
                title=mapped.get("consol_title") or entry.get("title"),
                section_title=mapped.get("standalone_section_title"),
                links=continuation_links(tables, variant=variant, section=sec, vocab=vocab),
                identities=identities, vocab=vocab,
            )
            item["via"] = choice.method
            if choice.primary is None:
                item["reason"] = choice.reason
                out.append(item)
                continue
            match = choice.match
            item.update({
                "standalone": f"{sec}#{choice.primary}",
                "chosen_name": tables[choice.primary].get("name"),
                "members": [f"{sec}#{i}" for i in choice.members],
                "row_members": [f"{sec}#{i}" for i in choice.row_members],
                "matched": len(match.col_map) if match else 0,
                "columns": [
                    [c, f"{sec}#{choice.members[pos]}", src, match.rules[c]]
                    for c, (pos, src) in sorted(match.col_map.items())
                ] if match else [],
                "unmatched": [target[c].label for c in match.unmatched] if match else [],
            })
            out.append(item)
    return out


# ─── 汇总 / 渲染 / 比对 ──────────────────────────────────────────────────────


def build_catalog() -> dict[str, Any]:
    from app.services.note_table_header_library import table_key

    vocab = load_vocabulary()
    anomalies: list[dict] = []
    variants: dict[str, list[dict]] = {}
    correspondence: dict[str, list[dict]] = {}
    stats: dict[str, Any] = {}
    for std in STDS:
        sections = standalone_sections(std)
        tables_by_section = {code: tables for code, tables in sections}
        variants[f"{std}_standalone"] = [
            e for code, tables in sections
            for e in _table_entries(f"{std}_standalone", code, tables, consol=False, anomalies=anomalies)
        ]
        variants[f"{std}_consolidated"] = [
            e for group, entries in _consol_groups(std)
            for e in _table_entries(f"{std}_consolidated", group, entries, consol=True, anomalies=anomalies)
        ]
        correspondence[std] = _correspondence(std, tables_by_section)
    for variant, entries in variants.items():
        stats[variant] = {
            "tables": len(entries),
            "multi_level_header": sum(1 for e in entries if len(e["header_rows"]) >= 2),
            "continuations": dict(sorted(Counter(
                f"{e['continuation']['kind']}/{e['continuation']['via']}" for e in entries if "continuation" in e
            ).items())),
        }
    for std, items in correspondence.items():
        chosen = [i for i in items if i.get("standalone")]
        amount = sum(i["amount_columns"] for i in chosen)
        matched = sum(i["matched"] for i in chosen)
        stats[f"{std}_correspondence"] = {
            "consol_tables": len(items),
            "by_via": dict(sorted(Counter(i["via"] for i in items).items())),
            "amount_columns_of_chosen": amount,
            "matched_columns": matched,
            "coverage": round(matched / amount, 4) if amount else 0.0,
            "mapping_disagreements": sum(
                1 for i in chosen if table_key(i.get("mapping_table")) != table_key(i.get("chosen_name"))
            ),
        }
    stats["anomalies"] = dict(sorted(Counter(a["kind"] for a in anomalies).items()))
    anomalies.sort(key=lambda a: (a["variant"], a["kind"], a["id"]))
    return {
        "version": 1,
        "_source": "生成自 backend/scripts/seed/build_note_table_header_library.py；识别口径见 "
                   "app/services/note_table_header_library.py + note_table_header_match.py，词表 "
                   "data/note_table_header_vocabulary.json。勿手改，改词表或种子后重新生成。",
        "_doc": [
            "variants：四版每张表的标题行 header_rows（[文字, 跨列, 跨行]）、逐列 [表头路径, 语义键]、续表关系。",
            "语义键「期间|计量」：end 期末余额类 / prior 期初·上年年末余额类 / cur 本期发生额类 / prev 上期发生额类；"
            "§label 标签列；|ratio 比例列（不加总）。",
            "correspondence：每张合并表对到单体哪张表（via：name 按表名 / structure 按表头结构 / single_table / "
            "no_source 合并特有），columns 为 [合并列, 单体表, 单体列, 规则]，unmatched 为没对上的合并列。",
        ],
        "vocabulary_sha1": vocab.digest,
        "stats": stats,
        "variants": variants,
        "correspondence": correspondence,
        "anomalies": anomalies,
    }


def _line(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _rows(items: list, indent: str) -> str:
    if not items:
        return "[]"
    return "[\n" + ",\n".join(indent + _line(x) for x in items) + "\n" + indent[:-2] + "]"


def render_catalog(catalog: dict[str, Any]) -> str:
    """每张表 / 每条对应 / 每条异常一行；顶层与统计缩进两格。"""
    head = {k: catalog[k] for k in ("version", "_source", "_doc", "vocabulary_sha1", "stats")}
    text = json.dumps(head, ensure_ascii=False, indent=2)[:-2]  # 去掉末尾「\n}」
    parts = [text + ","]
    parts.append('  "variants": {\n' + ",\n".join(
        f'    {_line(name)}: {_rows(entries, "      ")}' for name, entries in catalog["variants"].items()
    ) + "\n  },")
    parts.append('  "correspondence": {\n' + ",\n".join(
        f'    {_line(std)}: {_rows(items, "      ")}' for std, items in catalog["correspondence"].items()
    ) + "\n  },")
    parts.append(f'  "anomalies": {_rows(catalog["anomalies"], "    ")}')
    return "\n".join(parts) + "\n}\n"


def check_catalog() -> list[str]:
    """入库目录与按当前词表 / 种子生成的结果逐字节比对；一致返回空列表，否则返回差异摘要。"""
    import difflib

    expected = render_catalog(build_catalog())
    actual = LIBRARY_PATH.read_text(encoding="utf-8") if LIBRARY_PATH.exists() else ""
    if expected == actual:
        return []
    diff = difflib.unified_diff(actual.splitlines(), expected.splitlines(), "入库", "生成", n=0, lineterm="")
    return [line[:300] for line in list(diff)[:60]] or ["内容不同"]
