"""附注章节结构对齐脚本的共享工具（行/列构造 + 应用 + 校验 + CLI）。

由 `fix_note_d1_notes_receivable_structure.py` 的实现抽出，供后续循环复用
（首个消费方 = `fix_note_d_cycle_rest_structure.py`，覆盖 D3/D5/D6/D7）。

**加载方式**：消费脚本必须先把本目录加入 `sys.path` 再 import，因为守卫测试用
`importlib.util.spec_from_file_location` 直接按文件路径加载脚本（无包上下文）::

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _note_structure_kit import flat_columns, grouped_columns, run_variant

> D1 脚本仍保留自带的同款 helper（改动它需重跑其 189 项守卫，收益低风险高），
> 语义一致性由两侧各自与后端 `disclosure_engine` / `note_sub_table_projector`
> 的逐样本比对测试保证。

铁律来源（详见 `.kiro/steering/memory.md`）：

- 附注两级表头唯一机制 = `ColumnDef.group` → `_column_groups`，`group` 内禁 `/`
- `_extract_column_groups` 三态：`None`=未声明（回退前缀推断）/ `[]`=显式单级 / 非空=显式分组
  → **源模板单行表头的表必须标 `flat`**
- 模板 `rows` 里的占位说明（「可无限量添加行」「……」）是假数据行，必删，语义移入 `guidance`
- `text_sections` 里的裸表名会被当披露正文渲染，须加 `#### ` 前缀
"""
from __future__ import annotations

import argparse
import copy
import datetime as _dt
import json
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# 🔴 `row_type` 判据的单一真源（纯函数、stdlib-only）。本 kit 是**多个 per-cycle
# 幂等脚本共用的行构造器**，若在这里硬编码 `"row_type": "data"`，就会与
# `fix_note_expandable_rows.py` 互相翻转 —— 实测 soe `四、生物资产` 的 4 行 `……`
# 被 `fix_note_h_policy_chapter_structure.py`（经本 kit 构造 rows）翻回 `data`
# （2026-08-08）。故行构造一律走 `row_type_for_label()`。
from app.services.note_expandable_markers import row_type_for_label  # noqa: E402

AMOUNT = "amount"
PERCENT = "percent"
TEXT = "text"


# ─────────────────────────── 行构造 ───────────────────────────

def data_row(label: str = "") -> dict[str, Any]:
    """普通数据行；label 若是源模板可扩位标记（`……` / `可无限量添加行` 等）
    则自动标 ``expandable``（零可见内容），见 `row_type_for_label` 的 docstring。
    """
    return {"label": label, "row_type": row_type_for_label(label)}


def total_row(label: str = "合计") -> dict[str, Any]:
    return {"label": label, "is_total": True, "row_type": "total"}


def subtotal_row(label: str) -> dict[str, Any]:
    return {"label": label, "is_total": True, "row_type": "subtotal"}


def blanks_then_total(n: int, label: str = "合计") -> list[dict[str, Any]]:
    """n 个空白录入行 + 合计行（源模板「可无限量添加行」的正确落法）。"""
    return [data_row() for _ in range(n)] + [total_row(label)]


def labels_then_total(labels: list[str], total_label: str = "合计") -> list[dict[str, Any]]:
    return [data_row(x) for x in labels] + [total_row(total_label)]


# ─────────────────────────── 列构造 ───────────────────────────

def flat_columns(pairs: list[tuple[str, str, str | None]]) -> list[dict[str, Any]]:
    """单级表头列定义：`(key, label, format)`，首列自动标 `is_label` + `flat`。"""
    out: list[dict[str, Any]] = []
    for i, (key, label, fmt) in enumerate(pairs):
        col: dict[str, Any] = {"key": key, "label": label}
        if i == 0:
            col["is_label"] = True
            col["flat"] = True
        if fmt:
            col["format"] = fmt
        out.append(col)
    return out


def grouped_columns(
    label: tuple[str, str],
    specs: list[tuple[str, str, str | None, str | None]],
) -> list[dict[str, Any]]:
    """两级表头列定义。

    Args:
        label: 标签列 `(key, label)`（源模板 rowspan=2 的首列）
        specs: `(key, label, format, group|None)`；``group=None`` 表示该列本身是
            rowspan=2 的独立列（混合分组，后端与前端均已支持）。
    """
    out: list[dict[str, Any]] = [{"key": label[0], "label": label[1], "is_label": True}]
    for key, lbl, fmt, group in specs:
        col: dict[str, Any] = {"key": key, "label": lbl}
        if group:
            col["group"] = group
        if fmt:
            col["format"] = fmt
        out.append(col)
    return out


def two_period_columns(
    label: tuple[str, str],
    groups: tuple[str, str],
    subs: list[tuple[str, str, str | None]],
    *,
    prefixes: tuple[str, str] = ("end", "prior"),
) -> list[dict[str, Any]]:
    """双期同构两级表头：标签列 + `groups[0]`{subs} + `groups[1]`{subs}。

    `subs` 是 `(key_suffix, label, format)`，最终 key = `{prefix}_{key_suffix}`。
    两期子列名序列必然相等（Property「两期同构」由构造保证，不靠人工维护）。
    """
    specs: list[tuple[str, str, str | None, str | None]] = []
    for prefix, group in zip(prefixes, groups):
        for suffix, lbl, fmt in subs:
            specs.append((f"{prefix}_{suffix}", lbl, fmt, group))
    return grouped_columns(label, specs)


def derive_column_groups(cols: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从 columns 派生 `_column_groups`（`start` 为 headers 下标，标签列占 0）。

    与后端 `note_sub_table_projector._extract_column_groups` 单级分支同口径：
    相邻同名 group 合并；无 group 的列不进任何条目。
    """
    groups: list[dict[str, Any]] = []
    idx = 1
    for col in cols[1:]:
        name = col.get("group")
        if not name:
            idx += 1
            continue
        last = groups[-1] if groups else None
        if last and last["group"] == name and last["start"] + last["span"] == idx:
            last["span"] += 1
        else:
            groups.append({"group": name, "start": idx, "span": 1})
        idx += 1
    return groups


def headers_of(cols: list[dict[str, Any]]) -> list[str]:
    """headers = 各列 label（两级表头时是**叶子**列名，父表头由 `_column_groups` 承载）。"""
    return [str(c["label"]) for c in cols]


def rule(
    name: str,
    cols: list[dict[str, Any]],
    rows: list[dict[str, Any]] | None,
    guidance: str,
    aliases: list[str] | None = None,
    *,
    insert: bool = False,
) -> dict[str, Any]:
    """一张表的目标态。`aliases` 用于按旧表名定位（末项即目标名）。

    `insert=True` 时，若章节里找不到该表（含 aliases），就在当前游标位置**插入**新表
    （源模板存在但模板 JSON 整张缺失的情况，如 D6 上市减值准备计提情况的上年年末续表）。
    默认 False —— 找不到只告警，避免误插他 spec 的表。
    """
    return {
        "aliases": (aliases or []) + [name],
        "new_name": name,
        "headers": headers_of(cols),
        "columns": cols,
        "rows": rows,
        "guidance": guidance,
        "insert": insert,
    }


# ─────────────────────────── 应用 ───────────────────────────

def find_section(doc: dict[str, Any], section_number: str) -> dict[str, Any] | None:
    for sec in doc.get("sections", []):
        if str(sec.get("section_number", "")) == section_number:
            return sec
    return None


def drop_tables(section: dict[str, Any], names: list[str]) -> list[str]:
    """删除显式登记的垃圾表（空名 / 表头首格泄漏名 等）。

    宁漏不误杀：只删 `names` 里逐字命中的表；空字符串条目匹配「名字为空白」的表。
    """
    tables: list[dict[str, Any]] = section.get("tables") or []
    changes: list[str] = []
    keep: list[dict[str, Any]] = []
    wanted = {str(n) for n in names}
    for i, tbl in enumerate(tables):
        name = str(tbl.get("name", ""))
        if name in wanted or (not name.strip() and "" in wanted):
            changes.append(f"[{i}] 删除垃圾表：「{name}」")
            continue
        keep.append(tbl)
    if changes:
        section["tables"] = keep
    return changes


#: 可扩位行的 `row_type`（与 `app.services.note_expandable_markers` 同值；
#: 此处不 import 是为了让 kit 保持 stdlib-only、可被脚本单独 importlib 加载）
_EXPANDABLE_ROW_TYPE = "expandable"

#: 汇总行的 `row_type`（可扩位行要插在它们**之前**）
_TOTAL_ROW_TYPES_KIT = frozenset({"total", "subtotal"})


def carry_row_codes(
    old_rows: Any,
    new_rows: list[dict[str, Any]],
    *,
    table_name: str = "",
    warnings: list[str] | None = None,
) -> list[dict[str, Any]]:
    """整表重写 ``rows`` 时**保留** ``report_row_code``（按 label 配对）。

    🔴 为什么必须有这一步（2026-08-12 实测踩到）：``report_row_code`` 是
    `note_shared_table_segments.split_segments` 唯一的**切段依据** —— 共享表里
    哪几行归哪个循环，全靠它。它由 `fix_note_k_report_row_codes.py` 按
    `report_config` 连库对账后落到行上，**与结构对齐（表名/表头/列/行骨架）正交**。

    而结构脚本的 rows 骨架（`data_row(...)` 那套）里不带这个字段，于是
    「结构对齐脚本」与「段首码脚本」会**互相回退**：前者一跑就把码抹掉、后者
    再跑又补回来，两个 `--check` 永远不可能同时归零。实测形态 = K1 listed
    `五、8 其他应收款` 的 `rows：4 → 4 项`（行数一样、只差一个键）。

    修在共享 kit 而不是逐个脚本里：所有 `fix_note_*_structure.py` 都走
    :func:`apply_plan`，任何一个重写 rows 都会遇到同样的问题。

    配对按 **label** 而不是下标 —— 结构修订常会插/删行，下标会串位。
    同名行 >1 时不搬（并记 warning），避免猜错归属。
    """
    codes: dict[str, str] = {}
    seen: dict[str, int] = {}
    for row in old_rows or []:
        if not isinstance(row, Mapping):
            continue
        label = str(row.get("label") or "").strip()
        seen[label] = seen.get(label, 0) + 1
        code = str(row.get("report_row_code") or "").strip()
        if code:
            codes.setdefault(label, code)
    if not codes:
        return new_rows

    out: list[dict[str, Any]] = []
    for row in new_rows:
        if not isinstance(row, Mapping):
            out.append(row)
            continue
        new_row = dict(row)
        label = str(new_row.get("label") or "").strip()
        code = codes.get(label)
        if code and not str(new_row.get("report_row_code") or "").strip():
            if seen.get(label, 0) > 1:
                if warnings is not None:
                    warnings.append(
                        f"{table_name}：行「{label}」重名 {seen[label]} 次，"
                        f"report_row_code={code} 不搬（避免猜错段归属）"
                    )
            else:
                new_row["report_row_code"] = code
        out.append(new_row)
    return out


def carry_expandable_rows(
    old_rows: Any,
    new_rows: list[dict[str, Any]],
    *,
    table_name: str = "",
    warnings: list[str] | None = None,
) -> list[dict[str, Any]]:
    """整表重写 ``rows`` 时**保留可扩位行**（`row_type == "expandable"`）。

    🔴 与 :func:`carry_row_codes` 同一个道理，但保留的是**整行**而不是一个字段：
    可扩位行（源模板标了「此处可无限量增行」的那一行）是**源模板事实**，与结构
    骨架正交 —— 骨架说「这张表有哪些固定行」，可扩位行说「审计师可以在哪里加行」。
    结构脚本的骨架里没有它，一跑就把它抹掉，而
    `fix_note_k_expandable_rows.py` 再跑又插回来 ⇒ 两个 `--check` 永远不可能同时归零。

    插入位置 = **末尾合计/小计行之前**（源模板 29 处标记全部就在那里）；表尾没有
    合计行时追加到末尾。

    去重与去陈旧由 `fix_note_k_expandable_rows.py` 的 PLAN 负责（它是可扩位行的
    唯一权威：缺的补、多的删）。本函数只负责「结构重写时别弄丢」。
    """
    old_list = list(old_rows or [])
    # 连带记下**前一行的 label** 作位置锚点：可扩位行可能落在表中间（源模板里
    # 一张表有多处「此处可增行」），只会「插在合计前」会把它们全挤到表尾，
    # 与 `fix_note_k_expandable_rows.py` 的落位打架 ⇒ 两个 `--check` 互相回退。
    def _tail_total_start(rows: list[Any]) -> int:
        at = len(rows)
        for i in range(len(rows) - 1, -1, -1):
            row = rows[i]
            if isinstance(row, Mapping) and str(row.get("row_type") or "") in _TOTAL_ROW_TYPES_KIT:
                at = i
            else:
                break
        return at

    old_tail = _tail_total_start(old_list)
    keep: list[tuple[dict[str, Any], str]] = []
    for i, r in enumerate(old_list):
        if not isinstance(r, Mapping):
            continue
        if str(r.get("row_type") or "") != _EXPANDABLE_ROW_TYPE:
            continue
        # 🔴 两种落位要分开还原，否则会与 `fix_note_k_expandable_rows.py` 打架：
        #   * 原本就贴在**表尾合计之前** → 新骨架里仍放到合计之前（哪怕骨架加了新行，
        #     它也该留在数据区末尾，而不是被新行挤到中间）
        #   * 原本在**表中间**（源模板一张表有多处「此处可增行」）→ 按**前一行 label**
        #     还原相对位置
        prev_label = ""
        if i != old_tail - 1 and i > 0 and isinstance(old_list[i - 1], Mapping):
            prev_label = str(old_list[i - 1].get("label") or "").strip()
        keep.append((dict(r), prev_label))
    if not keep:
        return new_rows

    have = sum(
        1
        for r in new_rows
        if isinstance(r, Mapping)
        and str(r.get("row_type") or "") == _EXPANDABLE_ROW_TYPE
    )
    if have >= len(keep):
        return new_rows

    out = [dict(r) if isinstance(r, Mapping) else r for r in new_rows]

    for row, prev_label in keep[have:]:
        at = None
        if prev_label:
            hits = [
                i
                for i, r in enumerate(out)
                if isinstance(r, Mapping) and str(r.get("label") or "").strip() == prev_label
            ]
            if len(hits) == 1:
                at = hits[0] + 1
            elif warnings is not None:
                warnings.append(
                    f"{table_name}：可扩位行的位置锚点「{prev_label}」命中 {len(hits)} 次，"
                    "退回「合计行之前」"
                )
        if at is None:
            at = _tail_total_start(out)
        out.insert(at, row)
    return out


def apply_plan(section: dict[str, Any], plan: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """按计划就地修订 ``section.tables``（游标只前进，重名表由位置区分）。"""
    tables: list[dict[str, Any]] = section.get("tables") or []
    changes: list[str] = []
    warnings: list[str] = []
    cursor = 0

    for r in plan:
        aliases = r["aliases"]
        idx = next(
            (i for i in range(cursor, len(tables)) if str(tables[i].get("name", "")) in aliases),
            None,
        )
        if idx is None and r.get("insert"):
            idx = min(cursor, len(tables))
            tables.insert(idx, {"name": r["aliases"][-1]})
            section["tables"] = tables
            changes.append(f"[{idx}] 新增表：「{r['aliases'][-1]}」（源模板有、模板 JSON 整张缺失）")
        if idx is None:
            warnings.append(f"未找到表：{aliases[-1]}（游标 {cursor}）→ 跳过")
            continue

        tbl = tables[idx]
        old_name = str(tbl.get("name", ""))
        new_name = r.get("new_name")
        if new_name and old_name != new_name:
            dup = next(
                (j for j, t in enumerate(tables) if j != idx and str(t.get("name", "")) == new_name),
                None,
            )
            if dup is not None:
                warnings.append(f"表名迁移跳过：「{old_name}」→「{new_name}」，索引 {dup} 已占用")
            else:
                tbl["name"] = new_name
                changes.append(f"[{idx}] 表名：「{old_name}」→「{new_name}」")

        for key in ("headers", "columns", "rows"):
            want = r.get(key)
            if want is None:
                continue
            if key == "rows":
                want = carry_row_codes(
                    tbl.get("rows"), want, table_name=str(tbl.get("name", "")),
                    warnings=warnings,
                )
                want = carry_expandable_rows(
                    tbl.get("rows"), want, table_name=str(tbl.get("name", "")),
                    warnings=warnings,
                )
            if tbl.get(key) != want:
                old_len = len(tbl.get(key) or [])
                tbl[key] = json.loads(json.dumps(want, ensure_ascii=False))
                changes.append(f"[{idx}] {tbl.get('name')}.{key}：{old_len} → {len(want)} 项")

        want_groups = derive_column_groups(r.get("columns") or tbl.get("columns") or [])
        if want_groups:
            if tbl.get("_column_groups") != want_groups:
                tbl["_column_groups"] = json.loads(json.dumps(want_groups, ensure_ascii=False))
                changes.append(
                    f"[{idx}] {tbl.get('name')}._column_groups：{len(want_groups)} 组（两级表头）"
                )
        elif tbl.pop("_column_groups", None) is not None:
            changes.append(f"[{idx}] {tbl.get('name')}._column_groups：删除（单级表头）")

        guidance = r.get("guidance")
        if guidance and tbl.get("guidance") != guidance:
            tbl["guidance"] = guidance
            changes.append(f"[{idx}] {tbl.get('name')}.guidance → {len(guidance)} 字")

        cursor = idx + 1

    return changes, warnings


# ─────────────── text_sections 标题化（裸表名不得当正文）───────────────

# 与后端 `disclosure_engine._NUMBERED_TITLE_RE` 同口径（`（N）xxx` / `N. xxx`）
_NUMBERED_TITLE_RE = re.compile(r"^(?:（(\d+)）|(\d+)[.、])")


def is_title_paragraph(para: str) -> bool:
    """复刻 `disclosure_engine._is_table_title_paragraph`（stdlib-only，供 --check 独立跑）。"""
    s = (para or "").strip()
    if not s:
        return False
    if s.startswith("#"):
        return True
    if len(s) > 20:
        return False
    return bool(_NUMBERED_TITLE_RE.match(s))


def titleize_text_sections(section: dict[str, Any]) -> list[str]:
    """把 `text_sections` 里的**裸表名**加上 `#### ` 前缀，返回变更说明。"""
    paras = section.get("text_sections")
    if not isinstance(paras, list):
        return []
    names = {str(t.get("name", "")).strip() for t in (section.get("tables") or [])}
    changes: list[str] = []
    out: list[str] = []
    for p in paras:
        s = str(p)
        stripped = s.strip()
        if stripped in names and not is_title_paragraph(s):
            out.append(f"#### {stripped}")
            changes.append(f"text_sections：裸表名「{stripped}」→ 加 #### 前缀（不再当正文渲染）")
        else:
            out.append(s)
    if changes:
        section["text_sections"] = out
    return changes


def missing_text_sections(section: dict[str, Any], required: list[str]) -> list[str]:
    """返回 `required` 里尚不存在于 `text_sections` 的段落（按 strip 后逐字比对）。"""
    paras = section.get("text_sections")
    existing = {str(p).strip() for p in (paras if isinstance(paras, list) else [])}
    return [r for r in (required or []) if str(r).strip() not in existing]


def ensure_text_sections(section: dict[str, Any], required: list[str]) -> list[str]:
    """确保 `required` 段落存在 —— **缺失则按序追加到末尾**，已有的一律不动。幂等。

    与 `run_section(text_sections=...)` 的**整表替换**语义不同：这里是「补齐缺段」，
    用于「源模板有某小节说明、模板 JSON 漏了」的场景（如 K1 上市 ⑧⑨⑩ 三节），
    避免为补 3 段而手抄整份 47 段（手抄错字会被脚本写回模板，风险远大于收益）。

    ⚠️ 正文段**不要**带 `#### ` 前缀 —— `disclosure_engine._is_table_title_paragraph`
    见 `#` 即判为标题，标题本身不进任何输出 → 实质披露正文会被静默丢弃。
    """
    paras = section.get("text_sections")
    paras = list(paras) if isinstance(paras, list) else []
    existing = {str(p).strip() for p in paras}
    changes: list[str] = []
    for r in required or []:
        key = str(r).strip()
        if not key or key in existing:
            continue
        paras.append(r)
        existing.add(key)
        changes.append(f"text_sections：追加「{key[:24]}…」")
    if changes:
        section["text_sections"] = paras
    return changes


def find_bare_table_name_paragraphs(section: dict[str, Any]) -> list[str]:
    """返回仍会被当正文渲染的裸表名段落（供 validate / 测试）。"""
    names = {str(t.get("name", "")).strip() for t in (section.get("tables") or [])}
    return [
        str(p).strip()
        for p in (section.get("text_sections") or [])
        if str(p).strip() in names and not is_title_paragraph(str(p))
    ]


def stamp(section: dict[str, Any], aligned_by: str) -> None:
    section["_aligned_by"] = aligned_by
    section["_aligned_at"] = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ─────────────────────────── 校验 ───────────────────────────

def validate_section(
    section: dict[str, Any],
    expected: list[str],
    *,
    forbidden_names: list[str] | None = None,
) -> list[str]:
    """表名齐备唯一 / 无 header_label / columns 表态 / 分组自洽 / guidance 齐备。

    `forbidden_names` 额外拦「本应删除的垃圾表名」（空串条目 = 空白表名）。
    """
    errs: list[str] = []
    tables = section.get("tables") or []
    seen: dict[str, int] = {}
    forbidden = {str(n) for n in (forbidden_names or [])}

    for i, tbl in enumerate(tables):
        name = str(tbl.get("name", ""))
        if name in seen:
            errs.append(f"[{i}] 表名重复：「{name}」（首现于 {seen[name]}）")
        seen[name] = i
        if name in forbidden or (not name.strip() and "" in forbidden):
            errs.append(f"[{i}] 垃圾表未清理：「{name}」")
        if name not in expected:
            continue

        headers = tbl.get("headers") or []
        if any(not str(h).strip() for h in headers):
            errs.append(f"[{i}] {name} headers 含空串：{headers}")
        if any("<" in str(h) for h in headers):
            errs.append(f"[{i}] {name} headers 含 HTML：{headers}")

        for j, row in enumerate(tbl.get("rows") or []):
            if str(row.get("row_type", "")) == "header_label":
                errs.append(f"[{i}] {name} 第 {j} 行仍为 header_label（压扁的第二行表头）")

        cols = tbl.get("columns") or []
        has_group = any(c.get("group") for c in cols)
        if not cols:
            errs.append(f"[{i}] {name} 缺 columns")
        else:
            if len(cols) != len(headers):
                errs.append(f"[{i}] {name} columns={len(cols)} ≠ headers={len(headers)}")
            if str(cols[0].get("label", "")) != str(headers[0] if headers else ""):
                errs.append(
                    f"[{i}] {name} columns[0].label={cols[0].get('label')!r} ≠ "
                    f"headers[0]={(headers[0] if headers else None)!r}"
                )
            if cols[0].get("is_label") is not True:
                errs.append(f"[{i}] {name} 首列未标 is_label")
            has_flat = any(c.get("flat") for c in cols)
            if has_flat and has_group:
                errs.append(f"[{i}] {name} flat 与 group 并存（表态冲突）")
            if not has_flat and not has_group:
                errs.append(f"[{i}] {name} columns 未表态（既无 flat 也无 group）")
            if has_group and cols[0].get("group"):
                errs.append(f"[{i}] {name} 标签列不得带 group")
            if any("/" in str(c.get("group") or "") for c in cols):
                errs.append(
                    f"[{i}] {name} group 含 '/'（多级）→ 前端 activeTableColumns 只认扁平"
                    " {group,start,span}，树形会渲染崩"
                )
            by_group: dict[str, list[str]] = {}
            for c in cols[1:]:
                by_group.setdefault(str(c.get("group") or ""), []).append(str(c.get("label")))
            for g, labels in by_group.items():
                dup = {x for x in labels if labels.count(x) > 1}
                if dup:
                    errs.append(f"[{i}] {name} 分组「{g or '(无)'}」内列名重复：{sorted(dup)}")

        groups = tbl.get("_column_groups")
        if has_group:
            want = derive_column_groups(cols)
            if groups != want:
                errs.append(f"[{i}] {name} _column_groups 与 columns.group 不一致")
            for g in groups or []:
                start, span = int(g.get("start", 0)), int(g.get("span", 0))
                if start < 1:
                    errs.append(f"[{i}] {name} 分组「{g.get('group')}」start={start} < 1")
                if start + span > len(headers):
                    errs.append(
                        f"[{i}] {name} 分组「{g.get('group')}」越界：{start}+{span} > {len(headers)}"
                    )
        elif groups is not None:
            errs.append(f"[{i}] {name} 单级表头仍残留 _column_groups")

        if not str(tbl.get("guidance") or "").strip():
            errs.append(f"[{i}] {name} 缺 guidance（附注 TAB 页签无编制提示）")

    missing = [n for n in expected if n not in seen]
    if missing:
        errs.append(f"缺表：{missing}")

    bare = find_bare_table_name_paragraphs(section)
    if bare:
        errs.append(
            f"text_sections 含裸表名 {bare} → 会被当披露正文渲染"
            "（附注正文与 Word 导出多出只有表名的段落），须加 #### 前缀"
        )
    return errs


# ─────────────────────────── CLI 骨架 ───────────────────────────

def run_section(
    path: Path,
    section_number: str,
    plan: list[dict[str, Any]],
    expected: list[str],
    *,
    aligned_by: str,
    dry_run: bool,
    check: bool,
    drops: list[str] | None = None,
    text_sections: list[str] | None = None,
    require_text_sections: list[str] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """处理单个章节，返回 `(changes, warnings, errs)`。

    `text_sections` = **整表替换**（目标清单即真源）；
    `require_text_sections` = **补齐缺段**（只追加缺的，已有段落不动）。两者可并用，
    补齐在替换之后执行。
    """
    doc = json.loads(path.read_text(encoding="utf-8"))
    section = find_section(doc, section_number)
    if section is None:
        return [], [f"未找到章节 {section_number}（{path.name}）"], []

    if check:
        errs = validate_section(section, expected, forbidden_names=drops)
        if text_sections is not None and section.get("text_sections") != list(text_sections):
            errs.append(
                "text_sections 与目标清单不一致（源模板要求的说明段落缺失或漂移）："
                f"现 {len(section.get('text_sections') or [])} 段 / 目标 {len(text_sections)} 段"
            )
        for miss in missing_text_sections(section, require_text_sections or []):
            errs.append(f"text_sections 缺源模板说明段：「{str(miss).strip()[:30]}…」")

        # ── 🔴 补强：把 `--check` 的判据与**写入路径**对齐（2026-08-12）─────────────
        #
        # 改造前 `--check` 只跑 `validate_section`（表名清单 + text_sections），
        # **完全不跑 `apply_plan`** ⇒ `headers` / `columns` / `rows` / `guidance` /
        # `_column_groups` 的任何偏差它都看不见。实测形态：
        #
        #   `fix_note_g7_soe_structure.py --dry-run` 报「共 2 处变更」
        #   （T9 标签列头 `类型` → `结构化主体类型`），
        #   而同一时刻 `--check` 报「0 项欠账」。
        #
        # 这是典型假绿：各 spec 普遍拿「`--check` 0 欠账」当幂等/对齐的验收判据
        # （本仓 G7 spec 的 Task 19「幂等双证」正是如此），而该判据**结构上**
        # 抓不到列结构欠账 ⇒ 验收恒过、欠账长期驻留。
        #
        # 修法：在**深拷贝**上重放写入路径的全部变换，任何 change 计为欠账。
        # 判据从此与 `--dry-run` 同源（同一函数、同一顺序），不存在两套口径。
        #
        # 实测影响面（`--dry-run` 变更数逐脚本比对，24 个用 build_cli 的脚本）：
        # 21 个本就干净、2 个原本已打红、**仅 1 个** `fix_note_l_cycle_structure.py`
        # 由绿转红（专项应付款 2 处 `guidance` 文本欠账，属 L 循环 spec 作用域）——
        # 即本次补强暴露的是真欠账，不是引入新失败。
        probe = copy.deepcopy(section)
        residual = drop_tables(probe, drops or [])
        probe_changes, _probe_warnings = apply_plan(probe, plan)
        residual += probe_changes
        if text_sections is not None and probe.get("text_sections") != list(text_sections):
            probe["text_sections"] = list(text_sections)
        residual += ensure_text_sections(probe, require_text_sections or [])
        residual += titleize_text_sections(probe)
        for change in residual:
            errs.append(f"结构未对齐（headers/columns/rows/guidance）：{change}")
        return [], [], errs

    changes = drop_tables(section, drops or [])
    plan_changes, warnings = apply_plan(section, plan)
    changes += plan_changes
    if text_sections is not None and section.get("text_sections") != text_sections:
        old = len(section.get("text_sections") or [])
        section["text_sections"] = list(text_sections)
        changes.append(f"text_sections：{old} → {len(text_sections)} 段")
    changes += ensure_text_sections(section, require_text_sections or [])
    changes += titleize_text_sections(section)
    errs = validate_section(section, expected, forbidden_names=drops)
    if changes and not dry_run and not errs:
        stamp(section, aligned_by)
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changes, warnings, errs


def build_cli(
    description: str,
    runner: Callable[[str, bool, bool], tuple[list[str], list[str], list[str]]],
    labels: dict[str, str],
) -> Callable[[], int]:
    """生成标准 `main()`：`--dry-run` / `--check` / `--only`（按 labels 的键筛选）。"""

    def main() -> int:
        ap = argparse.ArgumentParser(description=description)
        ap.add_argument("--dry-run", action="store_true", help="只打印变更，不写文件")
        ap.add_argument("--check", action="store_true", help="只校验现状，返回非零表示欠账")
        ap.add_argument("--only", choices=sorted(labels), help="只处理单个章节键")
        args = ap.parse_args()

        keys = [args.only] if args.only else list(labels)
        total_changes = 0
        total_errs = 0
        for key in keys:
            changes, warnings, errs = runner(key, args.dry_run, args.check)
            print(f"\n=== {labels[key]} ===")
            for c in changes:
                print(f"  ~ {c}")
            for w in warnings:
                print(f"  ! {w}")
            for e in errs:
                print(f"  x {e}")
            if not changes and not errs and not warnings:
                print("  = 已对齐（幂等空操作）")
            total_changes += len(changes)
            total_errs += len(errs) + len(warnings)

        if args.check:
            print(f"\n--check：{total_errs} 项欠账")
            return 1 if total_errs else 0
        print(
            f"\n{'[dry-run] ' if args.dry_run else ''}共 {total_changes} 处变更，"
            f"{total_errs} 项问题"
        )
        return 1 if total_errs else 0

    return main
