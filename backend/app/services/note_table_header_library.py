"""附注表格标题行库 —— 四版（国企 / 上市 × 单体 / 合并）表头识别的唯一口径。

spec: consol-note-header-library-and-node-reaggregate（design §2~§5）

- ``column_paths``：逐列表头路径。合并表与展示 / Word 导出同一 ``header_rows``
  （``consol_note_headers.normalize_consol_note_section``）；单体表认 ``_column_groups`` 平铺
  ``{group,start,span}`` 与投影器树形格式、``columns[].group``（「/」分层）。平表头文字里的「/」不拆段。
- ``column_keys``：列语义键 = 期间（end / prior / cur / prev）× 计量段；单体种子把三级表头的
  顶层期间写进表名（「（期末数）」「（续：期初数）」），路径里没有期间时用表名期间。
- ``is_continuation_name`` / ``continuation_links``：续表只认标记，分列续（同一批行补期间或补列）
  与行续（同样的列补行）。
- 逐列对应与选表（名字证据 + 列语义键重合度）在 ``note_table_header_match``。

词表 ``data/note_table_header_vocabulary.json`` 手工维护；库目录 ``data/note_table_header_library.json``
由 ``note_table_header_catalog`` 生成（审阅 / CI / 测试用，请求期不读）。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

__all__ = [
    "PERIODS",
    "ColumnKey",
    "ContinuationLink",
    "VOCABULARY_PATH",
    "base_key",
    "column_keys",
    "column_paths",
    "continuation_links",
    "is_continuation_name",
    "load_vocabulary",
    "name_period",
    "norm",
    "parse_segment",
    "reset_vocabulary_cache",
    "table_identity",
    "table_key",
]

VOCABULARY_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "note_table_header_vocabulary.json"

PERIODS = ("end", "prior", "cur", "prev")
#: 同侧期间：期末余额 与 本期发生额 都在「本期」一侧（最弱规则才跨类对应）
_FAMILY = {"end": "current", "cur": "current", "prior": "previous", "prev": "previous"}
#: 主表没有期间、列续表是这个期间时，主表取对侧（「有『续：期初』续表的主表承载期末」）
_OPPOSITE = {"prior": "end", "prev": "cur", "end": "prior", "cur": "prev"}

_WS_RE = re.compile(r"[\s\u3000]+")
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_HALF = str.maketrans({"（": "(", "）": ")", "％": "%", "：": ":", "，": ",", "；": ";"})
_TRAILING_DOT = re.compile(r"[.。．]+$")
#: 表头尾部的序号 / 勾稽式注记：「期初余额(1)」「期末余额(4)=(1)+(2)-(3)」
_TRAILING_NO = re.compile(r"\(\d{1,2}\)(?:=[\d()+\-−×÷*/]*)?$")
# 表名开头的序号：（1） 1、 一、 ① A. 等；以及「其中，」「其中：」引导语
_ENUM_RE = re.compile(
    r"^(?:\([0-9一二三四五六七八九十]+\)|[0-9一二三四五六七八九十]+[、.．]|[①-⑳]|[A-Za-z][.、．])"
)
_LEAD_RE = re.compile(r"^其中[:,]?")
_CONT_SUFFIX_RE = re.compile(r"\(续[^()]*\).*$")
_CONT_PREFIX_RE = re.compile(r"^续(?:表)?(?:\(\d+\))?:?")
_PERIOD_PAREN_RE = re.compile(r"\(([^()]*)\)[:.]?$")
_REST_PAREN_RE = re.compile(r"^(.*?)\((.+)\)$")


def norm(text: Any) -> str:
    """去 HTML 换行与全部空白，全角括号 / 百分号 / 冒号 / 逗号归一为半角，去尾部句点。"""
    s = _WS_RE.sub("", _BR_RE.sub("", str(text if text is not None else "")))
    return _TRAILING_DOT.sub("", s.translate(_HALF))


# ─── 词表 ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Vocabulary:
    period_words: dict[str, str]
    prefixes: tuple[tuple[str, str], ...]  # 从长到短
    pure_remainders: frozenset[str]
    suffixes: tuple[tuple[str, str], ...]  # 从长到短
    measure_aliases: dict[str, str]
    measure_synonyms: dict[str, str]  # 词 → 同义组代表词（只给「同义」规则用）
    ratio_re: re.Pattern
    text_re: re.Pattern
    continuation_re: re.Pattern
    column_overrides: dict[tuple[str, str, int], dict]
    continuation_overrides: dict[tuple[str, str], dict]
    digest: str


def _require_reason(entry: dict, kind: str) -> None:
    if not str(entry.get("reason") or "").strip():
        raise ValueError(f"标题行库词表 overrides.{kind} 条目缺 reason：{entry}")


def _override_table_key(variant: str, table: str) -> tuple[str, str]:
    """覆盖定位键：合并表 section_id 原样；单体「章节号#表名」的表名部分按表名比较键归一。"""
    if "#" in table:
        section, name = table.split("#", 1)
        return variant, f"{norm(section)}#{table_key(name)}"
    return variant, norm(table)


def _build_vocabulary(raw: dict) -> Vocabulary:
    words: dict[str, str] = {}
    for period, items in (raw.get("period_words") or {}).items():
        if period not in PERIODS:
            raise ValueError(f"未知期间类别：{period}")
        for w in items:
            words[norm(w)] = period
    prefixes = tuple(sorted(((norm(p), k) for p, k in raw.get("period_prefixes") or []), key=lambda x: -len(x[0])))
    suffixes = tuple(sorted(((norm(p), k) for p, k in raw.get("period_suffixes") or []), key=lambda x: -len(x[0])))
    columns: dict[tuple[str, str, int], dict] = {}
    for entry in (raw.get("overrides") or {}).get("columns") or []:
        _require_reason(entry, "columns")
        columns[(*_override_table_key(entry["variant"], entry["table"]), int(entry["col"]))] = entry
    continuations: dict[tuple[str, str], dict] = {}
    for entry in (raw.get("overrides") or {}).get("continuations") or []:
        _require_reason(entry, "continuations")
        continuations[_override_table_key(entry["variant"], entry["table"])] = entry
    digest = hashlib.sha1(json.dumps(raw, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return Vocabulary(
        period_words=words,
        prefixes=prefixes,
        pure_remainders=frozenset(norm(x) for x in raw.get("pure_remainders") or []),
        suffixes=suffixes,
        measure_aliases={norm(k): norm(v) for k, v in (raw.get("measure_aliases") or {}).items()},
        measure_synonyms={
            norm(word): norm(group[0])
            for group in raw.get("measure_synonyms") or [] if group for word in group
        },
        ratio_re=re.compile(raw.get("ratio_pattern") or r"比例|比率|率\(|率$|%"),
        text_re=re.compile(raw.get("text_pattern") or r"(?!)"),
        continuation_re=re.compile((raw.get("continuation") or {}).get("marker_pattern") or r"^续|\(续(?:表)?[):]"),
        column_overrides=columns,
        continuation_overrides=continuations,
        digest=digest,
    )


@lru_cache(maxsize=1)
def load_vocabulary() -> Vocabulary:
    return _build_vocabulary(json.loads(VOCABULARY_PATH.read_text(encoding="utf-8")))


def reset_vocabulary_cache() -> None:
    load_vocabulary.cache_clear()


# ─── 表名 ────────────────────────────────────────────────────────────────────


def table_key(name: Any) -> str:
    """表名比较键：规范化后去掉开头序号与「其中，」引导语。"""
    return _LEAD_RE.sub("", _ENUM_RE.sub("", norm(name)))


def is_continuation_name(name: Any, vocab: Vocabulary | None = None) -> bool:
    """续表只认标记（表名以「续」开头，或带「（续）」「（续：…）」「（续表）」）。

    不用「表名含『续』」：永续债 / 继续涉入 / 手续费 / 存续期 / 后续计量 / 连续五个会计年度 都含「续」。
    """
    return bool((vocab or load_vocabulary()).continuation_re.search(table_key(name)))


def _strip_period_paren(key: str, vocab: Vocabulary) -> str:
    m = _PERIOD_PAREN_RE.search(key)
    if m and _paren_period(m.group(1), vocab):
        return key[: m.start()]
    return key


def base_key(name: Any, vocab: Vocabulary | None = None) -> str:
    """去掉续表标记与表名期间括注后的基名（把续表认回主表、把期末 / 期初拆表认成一组）。"""
    vocab = vocab or load_vocabulary()
    key = _CONT_PREFIX_RE.sub("", _CONT_SUFFIX_RE.sub("", table_key(name)))
    return _strip_period_paren(key, vocab).rstrip(":")  # 「按单项计提减值准备：」≡「按单项计提减值准备（期末余额）」


def _paren_period(inner: str, vocab: Vocabulary) -> str | None:
    text = _CONT_PREFIX_RE.sub("", norm(inner))
    period, measure = parse_segment(text, vocab)
    return period if period and not measure else None


def name_period(name: Any, vocab: Vocabulary | None = None) -> str | None:
    """表名期间：表名最后一个括注去掉「续：」后整体是期间词（「（期末数）」「（续：上年年末余额）」）。"""
    vocab = vocab or load_vocabulary()
    m = _PERIOD_PAREN_RE.search(table_key(name))
    return _paren_period(m.group(1), vocab) if m else None


# ─── 表头段 → 期间 + 计量 ────────────────────────────────────────────────────


def parse_segment(segment: Any, vocab: Vocabulary | None = None) -> tuple[str | None, str | None]:
    """一个表头段 → (期间, 计量词)。纯期间返回 (期间, None)；不含期间返回 (None, 原词)。

    依次：整词是期间 →「A/B」两侧同侧期间 → 期间开头（期末公允价值）→ 期间结尾（减值准备期末余额）。
    """
    vocab = vocab or load_vocabulary()
    s = _TRAILING_NO.sub("", norm(segment))
    if not s:
        return None, None
    if s in vocab.period_words:
        return vocab.period_words[s], None
    if "/" in s:
        parts = [parse_segment(p, vocab) for p in s.split("/")]
        periods = {p for p, m in parts if not m}
        if parts and all(p and not m for p, m in parts) and len({_FAMILY[p] for p in periods}) == 1:
            # 「期末余额/本期发生额」整列就是本期一侧：取余额类（end / prior）
            return ("end" if _FAMILY[next(iter(periods))] == "current" else "prior"), None
        return None, s
    for prefix, period in vocab.prefixes:
        if s.startswith(prefix) and len(s) > len(prefix):
            rest = s[len(prefix):]
            m = _REST_PAREN_RE.match(rest)
            if m and m.group(1) in vocab.pure_remainders:
                rest = m.group(2)  # 期末余额（账面价值）→ 账面价值
            if rest in vocab.pure_remainders:
                return period, None
            return period, rest
    for suffix, period in vocab.suffixes:
        if s.endswith(suffix) and len(s) > len(suffix):
            return period, s[: -len(suffix)]
    return None, s


# ─── 逐列表头路径 ────────────────────────────────────────────────────────────


def _paths_from_header_rows(header_rows: list[list[dict]], width: int) -> list[tuple[str, ...]]:
    occupied: list[list[tuple[int, int, str] | None]] = [[None] * width for _ in header_rows]
    for r, row in enumerate(header_rows):
        cursor = 0
        for cell in row:
            while cursor < width and occupied[r][cursor] is not None:
                cursor += 1
            cs, rs = int(cell.get("colspan", 1)), int(cell.get("rowspan", 1))
            for rr in range(r, min(r + rs, len(header_rows))):
                for cc in range(cursor, min(cursor + cs, width)):
                    occupied[rr][cc] = (r, cursor, str(cell.get("text", "")))
            cursor += cs
    out: list[tuple[str, ...]] = []
    for c in range(width):
        seen: set[tuple[int, int]] = set()
        path: list[str] = []
        for r in range(len(header_rows)):
            owner = occupied[r][c]
            if owner is None or owner[:2] in seen:
                continue
            seen.add(owner[:2])
            text = norm(owner[2])
            if text:
                path.append(text)
        out.append(tuple(path))
    return out


def _walk_group(item: Any, prefix: tuple[str, ...], out: dict[int, tuple[str, ...]]) -> None:
    """``_column_groups`` 一项：平铺 ``{group,start,span}`` / 树形 ``{group,children}`` / ``{headerIdx}``。"""
    if not isinstance(item, dict):
        return
    name = norm(item.get("group"))
    levels = prefix + ((name,) if name else ())
    children = item.get("children")
    if isinstance(children, list):
        for child in children:
            _walk_group(child, levels, out)
        return
    if isinstance(item.get("columns"), list):
        for idx in item["columns"]:
            if isinstance(idx, int):
                out[idx] = levels
        return
    start = item.get("start")
    if isinstance(start, int):
        try:
            span = max(1, int(item.get("span") or 1))
        except (TypeError, ValueError):
            span = 1
        for k in range(start, start + span):
            out[k] = levels
    elif isinstance(item.get("headerIdx"), int) and levels:
        out[item["headerIdx"]] = levels


def _group_paths(table: dict, width: int) -> dict[int, tuple[str, ...]]:
    out: dict[int, tuple[str, ...]] = {}
    groups = table.get("_column_groups")
    if isinstance(groups, list) and groups:
        for g in groups:
            _walk_group(g, (), out)
        return out
    if groups is not None:  # [] = 显式单级表头
        return out
    cols = table.get("columns")
    if isinstance(cols, list) and len(cols) == width:
        for i, col in enumerate(cols):
            if isinstance(col, dict) and col.get("group") and not col.get("is_label"):
                out[i] = tuple(x for x in (norm(p) for p in str(col["group"]).split("/")) if x)
    return out


def column_paths(table: dict | None) -> list[tuple[str, ...]]:
    """每列自上而下的表头文字（规范化）；第 0 列是标签列。"""
    if not isinstance(table, dict):
        return []
    headers = list(table.get("headers") or [])
    width = len(headers)
    multi = table.get("multi_header")
    if (isinstance(multi, list) and len(multi) >= 2) or table.get("header_rows"):
        from app.services.consol_note_headers import normalize_consol_note_section

        try:
            rows = normalize_consol_note_section({
                "headers": headers, "multi_header": multi, "header_rows": table.get("header_rows"), "rows": [],
            })["header_rows"]
            return _paths_from_header_rows(rows, width)
        except (ValueError, TypeError, KeyError):
            pass  # 表头跨度坏了：退回平表头 / 分组
    groups = _group_paths(table, width)
    out: list[tuple[str, ...]] = []
    for c in range(width):
        leaf = norm(headers[c])
        path = list(groups.get(c, ()))
        if leaf and (not path or path[-1] != leaf):
            path.append(leaf)
        out.append(tuple(path))
    return out


# ─── 列语义键 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ColumnKey:
    index: int
    path: tuple[str, ...]
    period: str | None
    measure: tuple[str, ...]
    kind: str  # label / amount / ratio（不加总）/ text（说明类，不取数）
    source: str = "rule"  # rule / override

    @property
    def key(self) -> str:
        if self.kind == "label":
            return "§label"
        text = f"{self.period or '-'}|{'/'.join(self.measure)}"
        return f"{text}|{self.kind}" if self.kind in ("ratio", "text") else text

    @property
    def label(self) -> str:
        return "/".join(self.path) or f"第{self.index}列"


def _name_of(table: Any) -> str:
    if not isinstance(table, dict):
        return ""
    return str(table.get("name") or table.get("title") or "")


def table_identity(variant: str | None, table_id: str | None) -> tuple[str, str] | None:
    """覆盖定位用的表标识；缺一不可（运行期不知道口径时不套逐表覆盖）。"""
    return (variant, table_id) if variant and table_id else None


def column_keys(
    table: dict | None,
    *,
    identity: tuple[str, str] | None = None,
    vocab: Vocabulary | None = None,
) -> list[ColumnKey]:
    """逐列语义键。``identity`` = (口径, 表标识)，用于套词表里的逐表覆盖。"""
    vocab = vocab or load_vocabulary()
    paths = column_paths(table)
    table_period = name_period(_name_of(table), vocab)
    override_prefix = _override_table_key(*identity) if identity else None
    out: list[ColumnKey] = []
    for c, path in enumerate(paths):
        if c == 0:
            out.append(ColumnKey(0, path, None, (), "label"))
            continue
        period: str | None = None
        measure: list[str] = []
        for seg in (part for raw in path for part in _level_parts(raw)):
            p, m = parse_segment(seg, vocab)
            if p and period is None:
                period = p
            if m and m not in vocab.pure_remainders:  # 「账面余额/金额」≡「账面余额」
                measure.append(vocab.measure_aliases.get(m, m))
        leaf = path[-1] if path else ""
        kind = "ratio" if leaf and vocab.ratio_re.search(leaf) else (
            "text" if leaf and vocab.text_re.search(leaf) else "amount"
        )
        key = ColumnKey(c, path, period or table_period, tuple(measure), kind)
        ov = vocab.column_overrides.get((*override_prefix, c)) if override_prefix else None
        if ov:
            key = ColumnKey(
                c, path, ov.get("period") or None,
                tuple(norm(x) for x in ov.get("measure") or ()), ov.get("kind") or kind, "override",
            )
        out.append(key)
    return out


_LEVEL_SPLIT_RE = re.compile(r"[-－]")
_NO_SPLIT_RE = re.compile(r"[\d=+]")


def _level_parts(segment: str) -> list[str]:
    """单体种子把三级表头压成「中级-叶」（账面余额-金额）：按连字符拆层；含数字 / 公式的不拆（期末余额(4)=(1)+(2)-(3)）。"""
    if not _LEVEL_SPLIT_RE.search(segment) or _NO_SPLIT_RE.search(segment):
        return [segment]
    parts = [p for p in _LEVEL_SPLIT_RE.split(segment)]
    return parts if all(len(p) >= 2 for p in parts) else [segment]


def _has_period(keys: Sequence[ColumnKey]) -> bool:
    return any(k.period for k in keys[1:])


# ─── 续表 ────────────────────────────────────────────────────────────────────

_PLACEHOLDER_LABEL = re.compile(r"^[.…·\-—_]*$|添加行|^\d{1,3}$")


def _row_label(row: Any) -> str:
    if isinstance(row, dict):
        return str(row.get("label") or "")
    if isinstance(row, (list, tuple)) and row:
        return str(row[0] or "")
    return ""


def _data_labels(table: dict) -> set[str]:
    out: set[str] = set()
    for row in table.get("rows") or []:
        key = norm(_row_label(row)).rstrip(":")
        if not key or _PLACEHOLDER_LABEL.search(key) or key in ("合计", "总计") or key.endswith("小计"):
            continue
        out.add(key)
    return out


def _label_overlap(cont: dict, other: dict) -> float:
    labels = _data_labels(cont)
    return len(labels & _data_labels(other)) / len(labels) if labels else 0.0


@dataclass(frozen=True)
class ContinuationLink:
    index: int
    of: int | None
    kind: str  # columns（同一批行补期间 / 补列）/ rows（同样的列补行）
    via: str  # base（同基名）/ previous（前一张非续表）/ override


def _continuation_kind(primary: dict, cont: dict, vocab: Vocabulary) -> str:
    pl, cl = _data_labels(primary), _data_labels(cont)
    if pl and cl:
        return "columns" if len(cl & pl) / len(cl) >= 0.5 else "rows"
    pk, ck = column_keys(primary, vocab=vocab), column_keys(cont, vocab=vocab)
    pm = [(k.measure, k.kind) for k in pk[1:]]
    cm = [(k.measure, k.kind) for k in ck[1:]]
    if pm == cm:
        return "columns" if {k.period for k in pk[1:]} != {k.period for k in ck[1:]} else "rows"
    return "columns"


def continuation_links(
    tables: Sequence[Any],
    *,
    variant: str | None = None,
    section: str | None = None,
    table_ids: Sequence[str] | None = None,
    vocab: Vocabulary | None = None,
) -> dict[int, ContinuationLink]:
    """一个章节内的续表关系：续表序号 → 主表序号与类型。

    主表 = 前面紧挨着的非续表（Word「续」接上一张表）；更早还有同基名的非续表、且它与续表的行名更吻合时取它。
    逐表覆盖按 ``table_ids``（合并表 section_id）或「``section``#表名」（单体表）定位。
    """
    vocab = vocab or load_vocabulary()
    names = [_name_of(t) for t in tables]
    links: dict[int, ContinuationLink] = {}
    for i, table in enumerate(tables):
        if not isinstance(table, dict):
            continue
        locator = (
            table_ids[i] if table_ids is not None and i < len(table_ids)
            else f"{section}#{names[i]}" if section else None
        )
        ov = vocab.continuation_overrides.get(_override_table_key(variant, locator)) if variant and locator else None
        if ov and ov.get("not_continuation"):
            continue
        if not ov and not is_continuation_name(names[i], vocab):
            continue
        primary: int | None = None
        via = "previous"
        if ov and ov.get("of"):
            want = table_key(ov["of"])
            primary = next((j for j in range(i - 1, -1, -1) if table_key(names[j]) == want), None)
            via = "override"
        if primary is None:
            # Word 里「续」接的是紧挨着的上一张表；同基名的更早一张只有在行名更吻合时才取
            # （上市「应付债券（续）」续的是上一张「应付债券的增减变动」，不是同基名的「应付债券」汇总表）
            earlier = [j for j in range(i - 1, -1, -1) if j not in links and isinstance(tables[j], dict)]
            adjacent = earlier[0] if earlier else None
            base = base_key(names[i], vocab)
            same_base = next((j for j in earlier if base and base_key(names[j], vocab) == base), None)
            primary, via = adjacent, "previous"
            if same_base is not None and same_base == adjacent:
                via = "base"
            elif same_base is not None and _label_overlap(table, tables[same_base]) > _label_overlap(table, tables[adjacent]):
                primary, via = same_base, "base"
        kind = (ov or {}).get("kind") or (
            _continuation_kind(tables[primary], table, vocab) if primary is not None else "rows"
        )
        links[i] = ContinuationLink(i, primary, kind, via)
    return links
