"""存量项目附注表格结构搬值（spec disclosure-note-template-word-realignment Task 12，design §4.2）。

纯函数、只处理一节的 ``table_data``。把库内表格的值搬进「现行种子表结构」（= 底稿 xlsx 口径，Task 6 既定），
搬不进新结构的非空值保留在 ``table_data._realign_orphans`` 并报告，不丢不造。

搬值口径（design §4.2）：

- 新结构 = 种子节的 ``tables``（表名、headers、rows 的 label / row_type / is_total / key / format 等结构元数据，
  种子表无 values）。表配对先按「规范化表名」一对一（同名多张按出现序），表名配不上的两侧剩余表再按相对顺序
  配对（种子改了表名的情形）。不按表序直接配：库内表序可能与种子不同（续表排在最后、夹着提示语「表」），按表序
  会把值搬进结构相同的兄弟表（如「应收海外企业客户」的期末数进「应收中央企业客户（续：期初数）」）。
- 行：种子行按「规范化 label」找库内同标签行；库内多行同标签按出现顺序一一对应。
- 列：``values[i]`` 对应 ``headers[i+1]``（headers[0] 是标签列）；种子列先按 ``columns[].key`` 找库内同 key 列，
  key 对不上（或库内没有列元数据）时按「规范化表头文字」找。``_cell_modes`` / ``_cell_meta`` 边车按列索引建键
  （字符串），随值一起搬到新列索引。
- 孤儿：库内非空单元格（值非 None、非空串），其所在（库内行、库内列）在新结构里找不到落点 ⇒ 记进
  ``_realign_orphans``；库内多出来的整张表（种子表数少于库内）也整表进孤儿。

硬断言由 :func:`realign_section_tables` 保证，破坏即抛 :class:`TableRealignError`：

1. 非空值多重集合（含孤儿区）搬值前后完全相等 —— 不丢值、不造值；
2. 按剩余表序配上、表名不同的一对，若要把库内非空值搬进新表 ⇒ 不猜，整节拒绝（人工核对后再处理）；
3. 正文（``text_content``）不属本模块职责，调用方另按行核对，这里只碰 ``table_data``。
"""
from __future__ import annotations

import copy
import re
from collections import Counter
from typing import Any

_WS = re.compile(r"[\s\u3000]+")


class TableRealignError(RuntimeError):
    """搬值破坏了非空值多重集合（调用方回滚）。"""


def _norm(s: Any) -> str:
    return _WS.sub("", str(s or "").strip())


def _is_empty(v: Any) -> bool:
    """空单元格：None、空串、纯空白串。数字 0、0.0 不算空（是真实数据）。"""
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip() == ""
    return False


def _cell_value_multiset(table_data: Any) -> Counter:
    """一节全部表（含 ``_realign_orphans``）的非空单元格值多重集合。值按 JSON 原子归一（str/数/bool）。"""
    counter: Counter = Counter()
    if not isinstance(table_data, dict):
        return counter
    tables = _tables_of(table_data)
    for tbl in tables:
        for row in tbl.get("rows") or []:
            if not isinstance(row, dict):
                continue
            for v in row.get("values") or []:
                if not _is_empty(v):
                    counter[_atom(v)] += 1
    for orphan in table_data.get("_realign_orphans") or []:
        for v in orphan.get("values") or []:
            if not _is_empty(v):
                counter[_atom(v)] += 1
    return counter


def _atom(v: Any):
    """把单元格值归一成可哈希的比较原子（区分 1 与 "1"：JSON 里是不同的，搬值不得改变类型）。"""
    return (type(v).__name__, v)


def _tables_of(table_data: dict[str, Any]) -> list[dict[str, Any]]:
    """多表取 ``_tables``；旧单表（顶层 rows）当一张；其它 0 张。"""
    tables = table_data.get("_tables")
    if isinstance(tables, list):
        return [t for t in tables if isinstance(t, dict)]
    return [table_data] if isinstance(table_data.get("rows"), list) else []


def _seed_col_keys(seed_tbl: dict[str, Any]) -> list[str | None]:
    """种子表每个值列（headers[1:] 对应）的 key：优先 ``columns[].key``，否则 None（走表头文字匹配）。"""
    headers = seed_tbl.get("headers") or []
    value_cols = max(len(headers) - 1, 0)
    cols = seed_tbl.get("columns")
    keys: list[str | None] = [None] * value_cols
    if isinstance(cols, list):
        # columns 含标签列时跳过第一个（is_label / 对应 headers[0]）
        value_defs = [c for c in cols if isinstance(c, dict) and not c.get("is_label")]
        for i in range(min(value_cols, len(value_defs))):
            k = value_defs[i].get("key")
            keys[i] = str(k) if k else None
    return keys


def _db_col_keys(db_tbl: dict[str, Any]) -> list[str | None]:
    headers = db_tbl.get("headers") or []
    value_cols = max(len(headers) - 1, 0)
    cols = db_tbl.get("columns")
    keys: list[str | None] = [None] * value_cols
    if isinstance(cols, list):
        value_defs = [c for c in cols if isinstance(c, dict) and not c.get("is_label")]
        for i in range(min(value_cols, len(value_defs))):
            k = value_defs[i].get("key")
            keys[i] = str(k) if k else None
    return keys


def _column_map(db_tbl: dict[str, Any], seed_tbl: dict[str, Any]) -> tuple[list[int | None], set[int], int]:
    """种子值列 i → 库内值列索引（或 None = 新列，无来源）。先按 key、再按规范化表头文字，一对一。

    返回（映射, 已被消费的库内值列集合, 库内值列总数）。
    """
    db_headers = db_tbl.get("headers") or []
    seed_headers = seed_tbl.get("headers") or []
    db_keys, seed_keys = _db_col_keys(db_tbl), _seed_col_keys(seed_tbl)
    db_value_cols = max(len(db_headers) - 1, 0)
    used: set[int] = set()
    mapping: list[int | None] = []
    # 库内值列 j（0-based，对应 db_headers[j+1]）的 key 与规范化表头
    db_text = [_norm(db_headers[j + 1]) if j + 1 < len(db_headers) else "" for j in range(db_value_cols)]
    for i in range(max(len(seed_headers) - 1, 0)):
        src: int | None = None
        want_key = seed_keys[i] if i < len(seed_keys) else None
        if want_key:
            for j in range(db_value_cols):
                if j not in used and db_keys[j] and db_keys[j] == want_key:
                    src = j
                    break
        if src is None:
            want_text = _norm(seed_headers[i + 1]) if i + 1 < len(seed_headers) else ""
            if want_text:
                for j in range(db_value_cols):
                    if j not in used and db_text[j] and db_text[j] == want_text:
                        src = j
                        break
        if src is not None:
            used.add(src)
        mapping.append(src)
    return mapping, used, db_value_cols


def _carry_sidecar(src_row: dict[str, Any], key: str, src_idx: int, dst_idx: int, dst_row: dict[str, Any]) -> None:
    """把 ``_cell_modes`` / ``_cell_meta`` 从库内列索引搬到新列索引（边车按字符串列索引建键）。"""
    side = src_row.get(key)
    if not isinstance(side, dict):
        return
    val = side.get(str(src_idx))
    if val is None:
        return
    bucket = dst_row.setdefault(key, {})
    if isinstance(bucket, dict):
        bucket[str(dst_idx)] = val


def _realign_one_table(db_tbl: dict[str, Any], seed_tbl: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """按种子结构重建一张表，把库内值搬进去；返回（新表, 该表产生的孤儿列表）。"""
    new_tbl = copy.deepcopy(seed_tbl)
    orphans: list[dict[str, Any]] = []
    col_map, used_db_cols, db_value_cols = _column_map(db_tbl, seed_tbl)

    # 库内行按规范化 label 分组（保出现顺序，多行同标签一一对应）
    db_rows = [r for r in (db_tbl.get("rows") or []) if isinstance(r, dict)]
    by_label: dict[str, list[dict[str, Any]]] = {}
    for r in db_rows:
        by_label.setdefault(_norm(r.get("label")), []).append(r)
    consumed: set[int] = set()  # 已配对的库内行（按 id(r)）
    label_cursor: dict[str, int] = {}

    seed_rows = [r for r in (new_tbl.get("rows") or []) if isinstance(r, dict)]
    for s_row in seed_rows:
        key = _norm(s_row.get("label"))
        pool = by_label.get(key, [])
        cursor = label_cursor.get(key, 0)
        src_row = pool[cursor] if cursor < len(pool) else None
        if src_row is not None:
            label_cursor[key] = cursor + 1
            consumed.add(id(src_row))
            src_values = src_row.get("values") or []
            new_values: list[Any] = []
            # 清掉种子行自带的边车，改由搬入决定
            s_row.pop("_cell_modes", None)
            s_row.pop("_cell_meta", None)
            for seed_col_i, db_col_j in enumerate(col_map):
                if db_col_j is not None and db_col_j < len(src_values):
                    new_values.append(src_values[db_col_j])
                    _carry_sidecar(src_row, "_cell_modes", db_col_j, seed_col_i, s_row)
                    _carry_sidecar(src_row, "_cell_meta", db_col_j, seed_col_i, s_row)
                else:
                    new_values.append(None)
            s_row["values"] = new_values
        else:
            # 种子有、库内无此行 ⇒ 空值行（种子结构保留，无来源）
            s_row["values"] = [None] * max(len(new_tbl.get("headers") or []) - 1, 0)

    # 孤儿：每个库内非空值恰进一处（否则会重复计入 ⇒ multiset 虚增）。
    #   - 未配对行（标签在新结构无落点）⇒ 整行非空值一次性进孤儿；
    #   - 已配对行 ⇒ 只有「未被任何种子列映射消费」的列（unmapped_cols）里的非空值进孤儿，其余已搬入新表。
    unmapped_cols = [j for j in range(db_value_cols) if j not in used_db_cols]
    db_headers = db_tbl.get("headers") or []
    table_name = str(db_tbl.get("name") or (db_headers[0] if db_headers else ""))
    for r in db_rows:
        vals = r.get("values") or []
        collected: list[Any] = []
        reasons: set[str] = set()
        if id(r) not in consumed:
            for v in vals:
                if not _is_empty(v):
                    collected.append(v)
            if collected:
                reasons.add("行标签在新结构中不存在")
        else:
            for j in unmapped_cols:
                if j < len(vals) and not _is_empty(vals[j]):
                    collected.append(vals[j])
                    col_name = _norm(db_headers[j + 1]) if j + 1 < len(db_headers) else f"col{j}"
                    reasons.add(f"列「{col_name}」在新结构中不存在")
        if collected:
            orphans.append({"table": table_name, "label": str(r.get("label") or ""),
                            "values": collected, "reason": "；".join(sorted(reasons))})
    return new_tbl, orphans


def _pair_tables(db: list[dict[str, Any]], seed: list[dict[str, Any]]) -> list[int | None]:
    """种子第 i 张 → 库内表索引（None = 无来源）。

    先按规范化表名一对一（同名多张按出现序）；表名配不上的，两侧剩余表按相对顺序配对（种子改了表名）。
    """
    pairing: list[int | None] = [None] * len(seed)
    used: set[int] = set()
    for i, s in enumerate(seed):
        name = _norm(s.get("name"))
        if not name:
            continue
        hit = next((j for j, d in enumerate(db) if j not in used and _norm(d.get("name")) == name), None)
        if hit is not None:
            pairing[i] = hit
            used.add(hit)
    rest = iter([j for j in range(len(db)) if j not in used])
    for i in range(len(seed)):
        if pairing[i] is None:
            j = next(rest, None)
            if j is None:
                break
            pairing[i] = j
    return pairing


def _renamed_pair(db_tbl: dict[str, Any], seed_tbl: dict[str, Any]) -> bool:
    """两侧都有表名且规范化后不同 = 按剩余表序配上的「改名」配对。"""
    a, b = _norm(db_tbl.get("name")), _norm(seed_tbl.get("name"))
    return bool(a and b and a != b)


def _carried_values(new_tbl: dict[str, Any]) -> int:
    """新表里的非空值个数（种子表无值 ⇒ 都是从库内搬进来的）。"""
    return sum(1 for r in (new_tbl.get("rows") or []) if isinstance(r, dict)
               for v in (r.get("values") or []) if not _is_empty(v))


def realign_section_tables(table_data: Any, seed_tables: list[dict[str, Any]]) -> dict[str, Any]:
    """按种子表结构重建一节的 ``table_data``，搬值 + 收孤儿；返回新 ``table_data``。

    硬断言：新 ``table_data``（含 ``_realign_orphans``）的非空值多重集合 == 原 ``table_data`` 的，破坏即
    :class:`TableRealignError`。入参不被修改（深拷贝）。
    """
    if not isinstance(table_data, dict) or not table_data:
        # 库内本就无表：没有值可搬，种子有表则建空结构、无表则不动
        if seed_tables:
            new = {"_tables": [copy.deepcopy(t) for t in seed_tables]}
            for t in new["_tables"]:
                for r in t.get("rows") or []:
                    if isinstance(r, dict):
                        r["values"] = [None] * max(len(t.get("headers") or []) - 1, 0)
            _assert_multiset(table_data, new)
            return new
        return copy.deepcopy(table_data) if isinstance(table_data, dict) else {}

    before = _cell_value_multiset(table_data)
    db = _tables_of(table_data)
    seed = [t for t in (seed_tables or []) if isinstance(t, dict)]

    new_tables: list[dict[str, Any]] = []
    orphans: list[dict[str, Any]] = []
    pairing = _pair_tables(db, seed)
    for i, s in enumerate(seed):
        j = pairing[i]
        d = db[j] if j is not None else {}
        new_tbl, tbl_orphans = _realign_one_table(d, s)
        if j is not None and _renamed_pair(d, s) and _carried_values(new_tbl):
            raise TableRealignError(
                f"种子表「{s.get('name')}」只能按剩余表序配到库内表「{d.get('name')}」（表名不同），且要搬入 "
                f"{_carried_values(new_tbl)} 个非空值：表名不同时不猜落点，需人工核对")
        new_tables.append(new_tbl)
        orphans.extend(tbl_orphans)
    # 库内没配上任何种子表的整张表（种子表数少、或提示语「表」）⇒ 整表非空值进孤儿
    paired = {j for j in pairing if j is not None}
    for i in range(len(db)):
        if i in paired:
            continue
        d = db[i]
        headers = d.get("headers") or []
        for r in d.get("rows") or []:
            if not isinstance(r, dict):
                continue
            collected = [v for v in (r.get("values") or []) if not _is_empty(v)]
            if collected:
                orphans.append({"table": str(d.get("name") or (headers[0] if headers else f"表{i + 1}")),
                                "label": str(r.get("label") or ""), "values": collected,
                                "reason": "整张表在新结构中不存在（种子里没有可配的表）"})

    new_td: dict[str, Any] = {"_tables": new_tables}
    # 保留库内非 _tables / 非 rows 的顶层键（如 note 级元数据），但不保留旧 rows/headers（已重建进 _tables）
    for k, v in table_data.items():
        if k not in ("_tables", "rows", "headers", "columns", "multi_header", "_column_groups",
                     "name", "_cell_modes", "_cell_meta", "_realign_orphans", "_row_types"):
            new_td[k] = copy.deepcopy(v)
    # 库内有顶层首表镜像（生成链 / 旧单表格式）⇒ 按新首表重建，不让读顶层 rows 的地方读到空表
    if isinstance(table_data.get("rows"), list) and new_tables:
        first = new_tables[0]
        new_td.update(name=first.get("name"), headers=copy.deepcopy(first.get("headers") or []),
                      rows=copy.deepcopy(first.get("rows") or []))
    existing_orphans = table_data.get("_realign_orphans")
    if isinstance(existing_orphans, list):
        orphans = [*existing_orphans, *orphans]
    if orphans:
        new_td["_realign_orphans"] = orphans

    _assert_multiset(table_data, new_td, before=before)
    return new_td


def _assert_multiset(before_td: Any, after_td: Any, *, before: Counter | None = None) -> None:
    b = before if before is not None else _cell_value_multiset(before_td)
    a = _cell_value_multiset(after_td)
    if a != b:
        lost = b - a
        gained = a - b
        raise TableRealignError(
            f"搬值改变了非空值多重集合：丢 {len(list(lost.elements()))} 个 {list(lost)[:5]}，"
            f"多 {len(list(gained.elements()))} 个 {list(gained)[:5]}")


def plan_section(code: str, table_data: Any, seed_tables: list[dict[str, Any]]) -> dict[str, Any]:
    """dry-run 一节的搬值预演：是否改动、孤儿清单、改动是否安全（multiset 恒等）。不抛错（安全性进报告）。"""
    try:
        new_td = realign_section_tables(table_data, seed_tables)
    except TableRealignError as err:
        return {"note_section": code, "safe": False, "error": str(err),
                "db_tables": len(_tables_of(table_data) if isinstance(table_data, dict) else []),
                "seed_tables": len([t for t in (seed_tables or []) if isinstance(t, dict)])}
    orphans = new_td.get("_realign_orphans") or []
    changed = section_needs_write(table_data, new_td)
    return {"note_section": code, "safe": True, "changed": changed,
            "db_tables": len(_tables_of(table_data) if isinstance(table_data, dict) else []),
            "seed_tables": len([t for t in (seed_tables or []) if isinstance(t, dict)]),
            "orphan_values": sum(len(o.get("values") or []) for o in orphans),
            "orphans": orphans}


def _row_signature(tbl: dict[str, Any]) -> list[tuple[str, list[Any]]]:
    """行标签原文 + 值（去掉尾部空单元格）；只比较用户看得见的表格内容。"""
    out = []
    for r in tbl.get("rows") or []:
        if not isinstance(r, dict):
            continue
        values = list(r.get("values") or [])
        while values and _is_empty(values[-1]):
            values.pop()
        out.append((str(r.get("label") or ""), values))
    return out


def section_needs_write(before_td: Any, after_td: dict[str, Any]) -> bool:
    """搬值后这一节要不要写库：表数、表名、表头、行标签、单元格值有变化，或孤儿区有变化。

    只差种子带来的结构元数据（``account_codes`` / ``columns`` / ``is_detail`` / ``text_after_table`` 等）或顶层
    镜像形态时**不写** —— 读时增强本就从模板回填这些，整节重写只会无谓地改动几乎全部章节（2026-10-31 真库实测：
    预演「会改 5 节」而写入 104 节，已按备份原样恢复）。dry-run 的 ``changed`` 与写入共用本判据。
    """
    before = _tables_of(before_td) if isinstance(before_td, dict) else []
    after = _tables_of(after_td)
    if len(before) != len(after):
        return True
    for d, s in zip(before, after):
        if (d.get("name") or "") != (s.get("name") or "") or (d.get("headers") or []) != (s.get("headers") or []):
            return True
        if _row_signature(d) != _row_signature(s):
            return True
    old_orphans = before_td.get("_realign_orphans") if isinstance(before_td, dict) else None
    return (after_td.get("_realign_orphans") or []) != (old_orphans or [])
