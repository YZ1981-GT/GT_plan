"""单体附注模板 ↔ 底稿披露表：配对、逐列比对、白名单（只读，不连库）。

spec: consol-note-header-library-and-node-reaggregate R8.4（design §17.5）；底稿切表见 ``note_workpaper_disclosure``。

权威 = 底稿模板 xlsx 的附注披露 sheet（用户 2026-10-16「表格以底稿 xlsx 为准」、2026-10-24「单体都按底稿披露表格式，
包括上市版」）。按 ``note_workpaper_sync_registry.json``（底稿 → 附注章节 + 披露 sheet 名）找 sheet，同一章节几张底稿
合并比；编辑器 / Word 导出只认两层表头，底稿表可接受的两层写法见 ``two_level_forms``。模板表名带期间（「（期末余额）」
「（续：上年年末余额）」）、底稿把同一期间写在最上层通栏 ⇒ 去掉这一层再比。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

from app.services.note_table_header_library import (
    column_paths,
    load_vocabulary,
    name_period,
    norm,
    parse_segment,
    path_keys,
)
from app.services.note_workpaper_disclosure import (
    DATA_DIR,
    STDS,
    WpColumn,
    WpTable,
    base_name,
    find_sheet,
    is_continuation,
    name_key,
    section_entries,
    workpaper_tables,
)

ALLOWLIST_PATH = DATA_DIR / "note_template_workpaper_alignment_allowlist.json"
_TOTAL_LABEL = re.compile(r"^(?:合计|小计|总计|其中:?|减:.*)$")


# ─── 模板侧表头路径（与标题行库同一读法） ────────────────────────────────────


def template_paths(table: dict, source: str) -> list[tuple[str, ...]] | None:
    """``source`` = headers（展示：headers + _column_groups）/ columns（推送骨架：columns 的 group + label）。
    没有 ``columns`` 的表 columns 一侧返回 None。"""
    if source == "headers":
        return column_paths(table)
    cols = [c for c in (table.get("columns") or []) if isinstance(c, dict)]
    if not cols:
        return None
    return column_paths({"headers": [c.get("label", "") for c in cols], "columns": cols})


def _top_period(paths: list[tuple[str, ...]]) -> str | None:
    """数据列（第 1 列起）都以同一个纯期间词开头、且下面还有一层 ⇒ 该期间词。"""
    data = paths[1:]
    if not data or any(len(p) < 2 for p in data):
        return None
    top = {p[0] for p in data}
    if len(top) != 1:
        return None
    seg = next(iter(top))
    period, measure = parse_segment(seg)
    return seg if period and not measure else None


def flat(path: Iterable[str]) -> str:
    """逐列表头文字自上而下连起来、去掉「/」：两层写法（「第一阶段 / 未来12个月…」）、上下拆写的一个词
    （「利息资 / 本化累 / 计金额」）、列名里带「/」的第三层（spec 69「账面余额/金额」）都按字比。
    相邻两段相同只算一段（底稿「期末余额」通栏下又写「期末余额」，标题行库读模板时也并成一段）。"""
    segs: list[str] = []
    for seg in path:
        if not segs or segs[-1] != seg:
            segs.append(seg)
    return "".join(segs).replace("/", "")


_UNIT = re.compile(r"\(%\)$|%$")


def _canon(seg: str) -> str:
    """表头一段的「意思」：按标题行库词表把同义写法归成一个 —— 期间词换成类别（期末余额 / 期末数 / 年末余额… 同为 end，
    期初余额 / 年初余额 / 上年年末余额 / 期初数… 同为 prior；「余额 / 数 / 金额」这类纯计量词不计），计量词按
    ``measure_aliases`` / ``measure_synonyms`` 归一（账面金额 ≡ 账面余额、变动情况 ≡ 变动金额、坏账准备 ≡ 减值准备），
    比例 / 利率的单位注记「(%)」「%」不计。只比一段的意思：分几层、哪段在上仍按字。"""
    vocab = load_vocabulary()
    period, measure = parse_segment(_UNIT.sub("", norm(seg)), vocab)
    m = "" if not measure or measure in vocab.pure_remainders else vocab.measure_aliases.get(measure, measure)
    m = vocab.measure_synonyms.get(m, m)
    return f"〈{period}〉{m}" if period else m


def _meanings(path: Iterable[str]) -> list[str]:
    out: list[str] = []
    for seg in path:
        c = _canon(seg)
        if not out or out[-1] != c:  # 相邻同义的两段只算一段（与 ``flat`` 同）
            out.append(c)
    return out


def same_text(a: Iterable[str], b: Iterable[str], meanings: tuple[list[str], list[str]] | None = None) -> bool:
    """两列表头算相同：逐段连起来的字相同（``flat``），或段数相同且逐段意思相同（``_canon``）—— 用户 2026-10-24
    「期末余额和期末数类似这种你需要兼容，都算通过，是一个意思的」。``meanings`` = 已按整张表算好的两列意思
    （``_table_meanings``）；逐列比对（``_same_paths``）只走这一处。"""
    a, b = list(a), list(b)
    ma, mb = meanings if meanings is not None else (_meanings(a), _meanings(b))
    return flat(a) == flat(b) or ma == mb


def _same_label(x: tuple[str, ...], y: tuple[str, ...]) -> bool:
    """标签列：底稿为空时不比（底稿常留白）；底稿写「项目/类别」这类二选一的，模板写其中一个也算。"""
    return not y or flat(x) in (flat(y), y[0], *y[0].split("/"))


def _table_meanings(paths: list[tuple[str, ...]], name: Any) -> list[list[str]]:
    """逐列意思；整张表一个期间词都没有、只有一列只写「金额 / 余额」的，这一列按表名期间认（表名不带期间 = 期末）——
    底稿 K3 上市「项目 | 金额 | 未偿还或未结转的原因」与模板「项目 | 期末余额 | …」是一个意思。"""
    out = [_meanings(p) for p in paths]
    data = out[1:]
    if not any("〈" in s for m in data for s in m) and sum(m == [""] for m in data) == 1:
        out = [[f"〈{name_period(name) or 'end'}〉"] if i and m == [""] else m for i, m in enumerate(out)]
    return out


def _same_paths(tpl: list[tuple[str, ...]], wp: list[tuple[str, ...]], name: Any = None) -> bool:
    """逐列表头相同（标签列 ``_same_label``，其余 ``same_text``，意思按整张表算：``_table_meanings``）。"""
    if len(tpl) != len(wp):
        return False
    mt, mw = _table_meanings(tpl, name), _table_meanings(wp, name)
    return all(_same_label(x, y) if i == 0 else same_text(x, y, (a, b))
               for i, (x, y, a, b) in enumerate(zip(tpl, wp, mt, mw)))


def same_as_workpaper(tpl: list[tuple[str, ...]], wp: WpTable, name: Any = None) -> bool:
    """模板表头与底稿表的某一种两层写法（``two_level_forms``）逐列相同。"""
    return any(_same_paths(tpl, form.paths, name) for form in two_level_forms(wp, name))


# ─── 配对 ────────────────────────────────────────────────────────────────────


def _units(names: list[str]) -> list[list[int]]:
    out: list[list[int]] = []
    for i, n in enumerate(names):
        if out and is_continuation(n):
            out[-1].append(i)
        else:
            out.append([i])
    return out


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / max(1, len(a | b)) if (a or b) else 0.0


def _row_keys(labels: Iterable[Any]) -> set[str]:
    """行名比较键（去合计 / 小计 / 其中 / 减项这类各表都有的行）。"""
    return {k for k in (norm(x) for x in labels) if k and not _TOTAL_LABEL.match(k)}


def _pair_score(wp: WpTable, tpl: dict) -> float:
    """名字分（最近的表名完全相同 3 / 包含 2 / 组合名同前缀 1.8 / 续表 1.5 / 相近 1.2）+ 1.5 × 列重合度（逐列文字、
    去掉期间写法差异后的列语义键，取高者）+ 模板行名在底稿里找得到的比例 + 列数相同 0.3。

    更上面的表名（章节标题、格式提示上面的真表名）只按「包含」计：K1 上市「其他应收款」下面才是「① 按账龄披露」，
    账龄表配模板账龄表（3 分）而不配同名汇总表（2 分）。列语义键与行名只在名字有关联时计入（名字无关、只是都是
    「期末 / 期初」两列的表不靠它们配上）。"""
    tn = str(tpl.get("name") or "")
    keys = [k for k in (name_key(c) for c in wp.title_candidates) if k] or [name_key(wp.title)]
    tk, tb = name_key(tn), base_name(tn)
    s = 0.0
    if keys[0] and keys[0] in (tk, tb):
        s = 3.0
    elif any(k and len(k) >= 4 and (k in tk or tb in k) for k in keys):
        s = 2.0
    elif any(k.startswith("续") for k in keys) and is_continuation(tn):
        s = 1.5
    else:
        head = next((k.split(":")[0] for k in keys if ":" in k), None)
        if head and tk.split(":")[0] == head:  # 「组合计提项目：X」组合名只是参考，按前缀 + 顺序
            s = 1.8
        elif keys and max(SequenceMatcher(None, k, tb).ratio() for k in keys) >= 0.6:
            s = 1.2
    wp_paths = wp.paths
    if _top_period(wp_paths):
        wp_paths = [wp_paths[0], *[p[1:] for p in wp_paths[1:]]]
    tpl_p = template_paths(tpl, "columns") or template_paths(tpl, "headers")
    a = {flat(p) for p in wp_paths[1:]} | {p[-1] for p in wp_paths[1:] if p}
    b = {flat(p) for p in tpl_p[1:]} | {p[-1] for p in tpl_p[1:] if p}
    overlap = _jaccard(a, b)
    rows = 0.0
    if s > 0:  # 名字有关联时，期间写法不同（期末数 / 期末余额）不算列对不上；名字无关的只认逐列文字
        overlap = max(overlap, _jaccard({k.key for k in path_keys(wp.paths, name=wp.title)[1:]},
                                        {k.key for k in path_keys(tpl_p, name=tn)[1:]}))
        # 行名只作参考，但能分开同名同列的两张表（K1 国企「其他应收款」标题下是账龄表，模板同名的是汇总表）
        rt = _row_keys(r.get("label") for r in (tpl.get("rows") or []) if isinstance(r, dict))
        if rt:
            rows = len(rt & _row_keys(wp.row_labels)) / len(rt)
    if overlap == 0 and s < 3.0:
        return 0.0  # 名字只是相近、列一个都对不上 ⇒ 不配对
    return s + 1.5 * overlap + rows + (0.3 if len(wp_paths) == len(tpl_p) else 0.0)


def _align(xs: list[WpTable], ts: list[dict]) -> list[tuple[int | None, int | None]]:
    """保序配对（最长公共子序列式 DP，配对分 ≥ 1.5 才算）。"""
    n, m = len(xs), len(ts)
    score = [[_pair_score(x, t) for t in ts] for x in xs]
    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            best = max(dp[i - 1][j], dp[i][j - 1])
            if score[i - 1][j - 1] >= 1.5:
                best = max(best, dp[i - 1][j - 1] + score[i - 1][j - 1])
            dp[i][j] = best
    out: list[tuple[int | None, int | None]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and score[i - 1][j - 1] >= 1.5 and dp[i][j] == dp[i - 1][j - 1] + score[i - 1][j - 1]:
            out.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i > 0 and (j == 0 or dp[i][j] == dp[i - 1][j]):
            out.append((i - 1, None))
            i -= 1
        else:
            out.append((None, j - 1))
            j -= 1
    return out[::-1]


@dataclass
class Pair:
    std: str
    section: str
    wp_code: str
    tpl_idx: list[int]
    wp: list[WpTable]


@dataclass
class SectionResult:
    std: str
    section: str
    wp_codes: list[str]
    pairs: list[Pair] = field(default_factory=list)
    tpl_only: list[int] = field(default_factory=list)
    wp_only: list[WpTable] = field(default_factory=list)
    missing_sheets: list[str] = field(default_factory=list)
    used_corrections: set[int] = field(default_factory=set)


def pair_section(std: str, section: str, tables: list[dict], entries: Iterable[dict[str, Any]],
                 title: str | None = None) -> SectionResult:
    """一节模板表与推这一节的各张底稿披露表配对：每张底稿各自与整节模板保序对齐，再合并（同一模板单元取分高的）。
    底稿册第一张表上方没有表名（只有索引行 / 提示：K6 国企、H8 两版）时以本节标题 ``title`` 作它的表名。"""
    entries = list(entries)
    res = SectionResult(std=std, section=section, wp_codes=[e["wp_code"] for e in entries])
    t_units = _units([str(t.get("name") or "") for t in tables])
    heads = [tables[u[0]] for u in t_units]
    best: dict[int, tuple[float, Pair]] = {}
    for e in entries:
        wps = list(workpaper_tables(e["wp_code"], std, e.get(f"sheet_{std}")))
        if not wps and find_sheet(e["wp_code"], std, e.get(f"sheet_{std}")) is None:
            res.missing_sheets.append(f"{e['wp_code']}:{e.get(f'sheet_{std}')}")
            continue
        if wps and title and not wps[0].title_candidates:
            wps[0] = replace(wps[0], title=title, title_candidates=[title])
        x_units = _units([w.title for w in wps])
        for xi, tj in _align([wps[u[0]] for u in x_units], heads):
            if tj is None:
                res.wp_only.extend(wps[k] for k in x_units[xi])
                continue
            if xi is None:
                continue
            sc = _pair_score(wps[x_units[xi][0]], heads[tj])
            if tj not in best or sc > best[tj][0]:
                if tj in best:
                    res.wp_only.extend(best[tj][1].wp)
                best[tj] = (sc, Pair(std, section, e["wp_code"], t_units[tj], [wps[k] for k in x_units[xi]]))
            else:
                res.wp_only.extend(wps[k] for k in x_units[xi])
    for tj, unit in enumerate(t_units):
        if tj in best:
            res.pairs.append(best[tj][1])
        else:
            res.tpl_only.extend(unit)
    return res


# ─── 逐列比对 ────────────────────────────────────────────────────────────────


@dataclass(frozen=True, order=True)
class Mismatch:
    std: str
    section: str
    table: int  # 模板表序（单元首表；split 记单元首表）
    kind: str  # columns / headers / split
    detail: str = field(compare=False)

    @property
    def key(self) -> tuple[str, str, int, str]:
        return (self.std, self.section, self.table, self.kind)


_STAGE = re.compile(r"第[一二三]阶段")
_STAGE_CELL = re.compile(r"^(第[一二三]阶段)(.+)$")


def _joined(col: WpColumn) -> list[tuple[str, tuple[int, int]]]:
    """一列的表头段：上下相邻、盖住同样几列的两段是拆开写的一个词（「利息资 / 本化累 / 计金额」、「设定受益计划
    净负债 / （净资产）」），连成一段；三阶段表的「第一阶段 / 未来12个月预期信用损失」是两层（上市、国企同表都这样），
    写在同一格里换行的也拆成两层。"""
    out: list[tuple[str, tuple[int, int]]] = []
    for txt, cov in zip(col.raw, col.cover):
        if out and cov == out[-1][1] and not _STAGE.fullmatch(out[-1][0]):
            out[-1] = (out[-1][0] + txt, cov)
        else:
            out.append((txt, cov))
    if len(out) == 1 and (m := _STAGE_CELL.match(out[0][0])):
        out = [(m.group(1), out[0][1]), (m.group(2), out[0][1])]
    return out


def two_level_forms(wp: WpTable, name: Any = None) -> list[WpTable]:
    """底稿表写成一张模板表（编辑器 ``_column_groups`` / Word 导出都只认两层表头）可以接受的写法，首个是按底稿改
    模板时默认写进去的写法；表名期间与底稿最上层期间不符时为空（配错表 / 模板写错期间）。

    - 最上层是统一期间：三层表头去掉这一层（期间由表名「（期末余额）」「（续：上年年末余额）」或续表关系表达）；两层
      表头保留这一层，模板表名已写同一期间时也可以不写。
    - 仍是三层（并列几期，每期「账面余额 / 金额、比例」）：父表头取期间，子列名写「中间段-最下一段」（「账面余额-
      金额」「账面余额-比例(%)」，默认用这种：信息不丢，标题行库 ``_level_parts`` 按连字符拆层，G5 载荷同此）；也可只留
      一段 —— 最下一段是「金额 / 余额」这类纯计量词时留中间段（「期末数 / 账面余额」），否则留最下一段（「期末数 /
      比例(%)」）。按期间拆成几张的模板表由 ``split_by_period`` 先拆再比。
    - 上下相邻、盖住同样几列的两段连成一段（``_joined``）。一格只盖这一列的也一样（G7 国企「发起 / 规模」读作
      「发起规模」）；模板写成两层（分组「发起」、列名「规模」）逐段连起来的字相同（``flat``），也算一致。"""
    label = wp.columns[0] if wp.columns else WpColumn(raw=(), cover=())
    cols = [list(zip(label.raw, label.cover)), *(_joined(c) for c in wp.columns[1:])]  # 标签列原样（只比最上一段）
    pure = load_vocabulary().pure_remainders
    data = cols[1:]
    tops = {norm(c[0][0]) for c in data if c}
    top = next(iter(tops)) if len(tops) == 1 and all(len(c) >= 2 for c in data) else None
    top_period = parse_segment(top)[0] if top else None
    if top and (not top_period or parse_segment(top)[1]):
        top = top_period = None
    np = name_period(name)
    if top_period and np and np != top_period:
        return []
    depth = max((len(c) for c in data), default=0)

    Seg = tuple[str, tuple[int, int]]

    def build(columns: list[list[Seg]]) -> WpTable:
        return replace(wp, columns=[WpColumn(raw=tuple(t for t, _ in c), cover=tuple(v for _, v in c)) for c in columns])

    def collapse(c: list[Seg]) -> list[Seg]:
        if len(c) <= 2:
            return c
        leaf = c[-1] if norm(c[-1][0]) not in pure else c[-2]
        return [c[0], leaf]

    def qualified(c: list[Seg]) -> list[Seg]:
        if len(c) <= 2:
            return c
        return [c[0], ("-".join(t for t, _ in c[1:]), c[-1][1])]

    forms: list[list[list[Seg]]] = []
    if top and (depth >= 3 or np):
        forms.append([cols[0], *[qualified(c[1:]) for c in data]])
        if depth >= 4:
            forms.append([cols[0], *[collapse(c[1:]) for c in data]])
    if depth <= 2:
        forms.append(cols)
    elif not top:
        forms.append([cols[0], *[qualified(c) for c in data]])
        forms.append([cols[0], *[collapse(c) for c in data]])
    return [build(f) for f in forms]


def split_by_period(wp: WpTable) -> list[WpTable] | None:
    """一张表并列几期（每列最上层都是纯期间词，同一期间的列相邻）→ 按期间拆成几张（各带标签列、保留期间这一层，
    由模板表名对上）。不是这种表返回 None。平台单张表只认两层表头（编辑器 ``_column_groups`` / Word 导出两行
    表头），三层的底稿表按期间拆成「（期末…）」「（续：上年年末…）」两张（d1 / d6 附注映射同一范式）。"""
    if _top_period(wp.paths):
        return None
    groups: list[list[WpColumn]] = []
    last = None
    for col in wp.columns[1:]:
        if len(col.raw) < 2:
            return None
        period, measure = parse_segment(col.raw[0])
        if not period or measure:
            return None
        if groups and norm(col.raw[0]) == last:
            groups[-1].append(col)
        else:
            groups.append([col])
            last = norm(col.raw[0])
    if len(groups) < 2:
        return None
    return [replace(wp, columns=[wp.columns[0], *g]) for g in groups]


def compare_pair(pair: Pair, tables: list[dict]) -> list[Mismatch]:
    out: list[Mismatch] = []
    wps = pair.wp
    if len(pair.tpl_idx) != len(pair.wp):
        parts = split_by_period(pair.wp[0]) if len(pair.wp) == 1 else None
        if parts is None or len(parts) != len(pair.tpl_idx):
            out.append(Mismatch(pair.std, pair.section, pair.tpl_idx[0], "split",
                                f"模板 {len(pair.tpl_idx)} 张 / 底稿 {len(pair.wp)} 张（{pair.wp[0].sheet}）"))
            return out
        wps = parts  # 模板按期间拆成几张、底稿一张并列几期：逐期比
    for j, wp in zip(pair.tpl_idx, wps):
        name = tables[j].get("name")
        forms = two_level_forms(wp, name)
        for source in ("columns", "headers"):
            tp = template_paths(tables[j], source)
            if tp is None or same_as_workpaper(tp, wp, name):
                continue
            shown = forms[0].paths if forms else wp.paths
            w0 = shown[0] if shown else ()
            first = 0 if w0 and tp and flat(tp[0]) not in (flat(w0), w0[0]) else 1
            why = "" if forms else "；表名期间与底稿最上层期间不符"
            out.append(Mismatch(pair.std, pair.section, j, source,
                                f"模板 {['/'.join(p) for p in tp[first:]]} ≠ 底稿 {['/'.join(p) for p in shown[first:]]}"
                                f"（{wp.sheet} 第 {wp.header_rows[0]} 行{why}）"))
    return out


def load_templates() -> dict[str, dict[str, Any]]:
    return {std: json.loads((DATA_DIR / f"note_template_{std}.json").read_text(encoding="utf-8")) for std in STDS}


def load_allowlist(path: Path = ALLOWLIST_PATH) -> dict[str, list[dict[str, Any]]]:
    """``corrections``：底稿笔误 / 提示，比之前先把底稿那段字换成模板的写法（表的其余部分照常逐列比）；
    ``exceptions``：整张表不按底稿（底稿两表并排读成一张、模板实例化了占位列、批 9b-2 待改的结构差异）。"""
    if not path.exists():
        return {"corrections": [], "exceptions": []}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {"corrections": list(doc.get("corrections") or []), "exceptions": list(doc.get("exceptions") or [])}


def _entry_key(e: dict[str, Any]) -> tuple[str, str, int]:
    return (e["std"], e["section"], int(e["table"]))


def apply_corrections(wp: WpTable, corrections: Iterable[dict[str, Any]]) -> tuple[WpTable, set[int]]:
    """把底稿表头里与 ``workpaper`` 相同（规范化后）的段换成 ``template``（空串 = 去掉这一段）；条目带 ``columns``
    （逻辑列序号，0 = 标签列）时只改这几列，带 ``leaf: true`` 时只改每列最下一段。返回（改过的副本, 用上了的条目
    序号）—— 不改缓存里的原表。"""
    rules = [(i, norm(c["workpaper"]), str(c.get("template") or ""), set(c["columns"]) if c.get("columns") else None,
              bool(c.get("leaf"))) for i, c in enumerate(corrections)]
    used: set[int] = set()
    columns: list[WpColumn] = []
    for ci, col in enumerate(wp.columns):
        raw, cover = [], []
        for si, (seg, cov) in enumerate(zip(col.raw, col.cover)):
            last = si == len(col.raw) - 1
            hit = next(((i, to) for i, frm, to, only, leaf in rules
                        if norm(seg) == frm and (only is None or ci in only) and (last or not leaf)), None)
            if hit is not None:
                used.add(hit[0])
                seg = hit[1]
            if seg:
                raw.append(seg)
                cover.append(cov)
        columns.append(WpColumn(raw=tuple(raw), cover=tuple(cover)))
    return replace(wp, columns=columns), used


def compare_all(templates: dict[str, dict[str, Any]] | None = None, *,
                corrections: list[dict[str, Any]] | None = None
                ) -> tuple[list[Mismatch], list[SectionResult]]:
    """推送注册表覆盖的全部章节：（逐列不一致, 各节配对结果）。``templates`` 可传内存中的模板（改模板前预演用）；
    ``corrections`` 默认取白名单文件的 ``corrections``，按（口径, 章节, 模板表序）套到配上的底稿表（结果里的
    ``pairs`` 存的就是改过的底稿表；用上的条目序号记在各节的 ``used_corrections``，见 ``unused_corrections``）。"""
    templates = templates or load_templates()
    if corrections is None:
        corrections = load_allowlist()["corrections"]
    by_key: dict[tuple[str, str, int], list[tuple[int, dict[str, Any]]]] = {}
    for i, c in enumerate(corrections):
        by_key.setdefault(_entry_key(c), []).append((i, c))
    by_sec = {std: {s.get("section_number"): s for s in templates[std]["sections"]} for std in STDS}
    mismatches: list[Mismatch] = []
    results: list[SectionResult] = []
    for (std, sec), entries in sorted(section_entries().items()):
        s = by_sec[std].get(sec)
        if s is None:
            continue
        tables = s.get("tables") or []
        res = pair_section(std, sec, tables, entries, s.get("section_title"))
        for p in res.pairs:
            if len(p.tpl_idx) == len(p.wp):  # 拆表方式不同的单元整体记 split，不逐表套
                fixed = []
                for j, wp in zip(p.tpl_idx, p.wp):
                    mine = by_key.get((std, sec, j), [])
                    wp2, hit = apply_corrections(wp, [c for _i, c in mine])
                    res.used_corrections |= {mine[k][0] for k in hit}
                    fixed.append(wp2)
                p.wp = fixed
            mismatches.extend(compare_pair(p, tables))
        results.append(res)
    return sorted(mismatches), results


def unused_corrections(results: list[SectionResult], corrections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """白名单里一次都没用上的 ``corrections`` 条目（底稿已改 / 表序变了 / 写错字）。"""
    used = set().union(*(r.used_corrections for r in results)) if results else set()
    return [c for i, c in enumerate(corrections) if i not in used]


def check_against_allowlist(mismatches: list[Mismatch], exceptions: list[dict[str, Any]]
                            ) -> tuple[list[Mismatch], list[dict[str, Any]]]:
    """（白名单外的不一致, 失效白名单条目）。条目须有 std / section / table / kinds（columns / headers / split）/ reason。"""
    keys = set()
    for e in exceptions:
        if not str(e.get("reason") or "").strip():
            raise ValueError(f"白名单条目缺理由：{e}")
        keys |= {(*_entry_key(e), k) for k in e["kinds"]}
    live = {m.key for m in mismatches}
    return ([m for m in mismatches if m.key not in keys],
            [e for e in exceptions if any((*_entry_key(e), k) not in live for k in e["kinds"])])
