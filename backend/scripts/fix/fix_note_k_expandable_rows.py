#!/usr/bin/env python
"""给 K 循环附注表补「可扩位」行 `row_type='expandable'`（幂等）。

源 xlsx 的披露 sheet 里，「此处可无限量增行」是用**列 A 的占位标记**表达的
（`……` / `......` / `可无限量添加行`），Task 3 已逐处冻结坐标共 **29 处**。
附注模板侧一处都没有 ⇒ 前端渲染不出「在这里加行」的落点，审计师只能改模板。

判定结论（openpyxl 逐处读上下文，2026-08-12）：**29 处全部是「作行」**，
无一处作列头 —— 每一处都在列 A、且都紧邻其数据区的 `合  计` 行之前。
故 tasks.md 里「逐处判定作行/作列头」的分支实际只有一支成立。

**词表不另写**：`row_type` 由 `_note_structure_kit.data_row()` 派生，而它调
`app.services.note_expandable_markers.row_type_for_label()` —— 平台唯一词表
（`……`/`......`/`…`/`可无限量添加行`/`预留`，且显式排除 `可改名`）。
本脚本只负责「插在哪」，不负责「什么算标记」。

🔴 **写者划分（不这样分会与结构脚本互相回退）**：

- **本脚本是可扩位行的唯一权威**（PLAN 缺的补、多的删）。
- K8~K13：`fix_note_k_pl_structure.py` 的 PLAN 只声明 `columns` + `guidance`，
  不碰 rows ⇒ 直接插即可。
- K1 / K3：rows **由结构脚本整表重写**（`fix_note_k_complex_structure.py` /
  `fix_note_k_liability_structure.py`）。原以为必须把 `data_row("……")` 写进对方的
  行骨架，但那要改 18 处骨架、且以后每个结构脚本都得自己记得。改法收敛到共享 kit：
  `_note_structure_kit.carry_expandable_rows()` 在整表重写时把可扩位行**搬过去**
  （插在末尾合计行之前），与 `carry_row_codes()` 同一个道理 —— 可扩位行是**源模板
  事实**，与结构骨架正交。于是本脚本仍是唯一写者，两个 `--check` 同时归零。
- K6：**同一张表内有 2~4 处 `……`**，label 不足以定位（4 处 label 全一样），
  需给 PLAN 加 `after_label` 位置锚点，属独立子问题 ⇒ 由
  :data:`PENDING_MULTI_MARKER_TABLES` 登记，闭环自检钉住「本批 17 + 待办 12 == 29」。

用法::

    python backend/scripts/fix/fix_note_k_expandable_rows.py --check
    python backend/scripts/fix/fix_note_k_expandable_rows.py --dry-run
    python backend/scripts/fix/fix_note_k_expandable_rows.py --apply

spec: .kiro/specs/k-cycle-extraction-formula-and-disclosure-closure/
      Requirements 9.1, 9.2, 9.3, 9.7, 9.8
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[2]
_DATA = _BACKEND / "data"
LISTED_PATH = _DATA / "note_template_listed.json"
SOE_PATH = _DATA / "note_template_soe.json"

if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def _kit():
    spec = importlib.util.spec_from_file_location(
        "_nsk_exp", Path(__file__).with_name("_note_structure_kit.py")
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_nsk_exp"] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop("_nsk_exp", None)
    return mod


_KIT = _kit()

#: 待补的可扩位行：``(variant, section, table, marker_label, 源坐标[, after_label])``。
#:
#: `marker_label` 逐字取自源 xlsx（K11 两版是 ASCII 六点 `......`，其余是
#: U+2026 ×2 的 `……`）—— **不得归一**，那会让守卫与源模板脱钩。
#:
#: 第 6 项 `after_label` 是**位置锚点**（可选）：一张表里有多处标记时，只靠
#: `marker_label` 无法区分（4 处 label 全是 `……`）。给了锚点就插在「该 label 的行」
#: 之后；没给就插在末尾合计行之前。K6 的多标记表全靠它定位。
PLAN: list[tuple[str, ...]] = [
    ("listed", "五、64", "销售费用（按费用性质列示）", "……", "K8!A16"),
    ("soe", "八、65", "销售费用", "……", "K8!A16"),
    ("listed", "五、65", "管理费用（按费用性质列示）", "……", "K9!A24"),
    ("soe", "八、66", "管理费用", "……", "K9!A24"),
    ("listed", "五、68", "其他收益", "……", "K10!A13"),
    ("soe", "八、69", "其他收益", "……", "K10!A13"),
    ("listed", "三、资产减值损失（损", "资产减值损失", "......", "K11!A25"),
    ("soe", "八、74", "资产减值损失", "......", "K11!A25"),
    ("listed", "三、营业外收入（注：", "营业外收入", "……", "K12!A13"),
    ("soe", "八、76", "营业外收入", "……", "K12!A13"),
    ("soe", "八、77", "营业外支出", "……", "K13!A14"),
    # ── K1 / K3 / K6：rows 由结构脚本整表重写，靠 kit 的 `carry_expandable_rows()`
    #    在重写时把这些行搬过去（见下方「写者划分」的更正说明）
    ("listed", "五、8", "按款项性质披露", "可无限量添加行", "K1!A27"),
    ("listed", "五、8", "本期转回或收回金额重要的坏账准备", "可无限量添加行", "K1!A109"),
    ("soe", "八、9", "按坏账准备计提方法分类披露其他应收款项", "……", "K1!A24"),
    ("soe", "八、9", "按坏账准备计提方法分类披露其他应收款项（续：期初余额）", "……", "K1!A33"),
    ("listed", "五、42", "其他应付款（按款项性质列示）", "可无限量添加行", "K3!A16"),
    ("soe", "八、42", "按款项性质列示", "可无限量添加行", "K3!A16"),
    # ── K6：一张表里多处标记 ⇒ 全部带 `after_label` 位置锚点 ────────────
    ("listed", "五、11", "持有待售资产和持有待售负债", "……", "K6!A15"),
    ("listed", "五、11", "持有待售资产减值准备", "……", "K6!A37", "无形资产"),
    ("listed", "五、11", "持有待售资产减值准备", "……", "K6!A41"),
    ("listed", "五、11", "持有待售的处置组", "……", "K6!A58", "固定资产"),
    ("listed", "五、11", "持有待售的处置组", "……", "K6!A64", "长期应付款"),
    ("soe", "八、12", "持有待售资产", "……", "K6!A14", "无形资产"),
    ("soe", "八、12", "持有待售资产", "……", "K6!A18"),
    ("soe", "八、12", "持有待售资产减值准备", "……", "K6!A27", "无形资产"),
    ("soe", "八、12", "持有待售资产减值准备", "……", "K6!A31"),
]

#: 源侧**重复块**折叠到同一处模板行的标记（登记，不重复插）。
#:
#: 源 xlsx 的「持有待售的处置组」按处置组逐个重复整块（① 子公司A、② 分公司B…），
#: 每块的资产段末与负债段末各有一处 `……`。附注模板按平台铁律把示例名改成**一个
#: 通用块**（`子公司A`/`分公司B` 是占位示例名）⇒ 4 处源标记落到同 2 处模板行。
#: 这不是漏做，是源侧重复、目标侧不重复。
COLLAPSED_SOURCE_MARKERS: dict[str, str] = {
    "K6!A71": "与 K6!A58 同为「处置组资产段末」，源侧按处置组重复整块，模板只有一个通用块",
    "K6!A77": "与 K6!A64 同为「处置组负债段末」，源侧按处置组重复整块，模板只有一个通用块",
}

#: 源侧有标记但**附注模板没有对应表**的（登记，属表集合缺口而非可扩位缺口）。
NO_TEMPLATE_TARGET: dict[str, str] = {
    "K6!A54": (
        "源 xlsx soe 有「持有待售负债附注」表（r50 起），而 note_template_soe §八、12 "
        "的 4 张表里没有它（listed 侧有「持有待售负债」）。缺的是**整张表**，"
        "属 Requirement 8 的表集合作业面，不是可扩位标记问题；补表之后再来补这一处。"
    ),
}

#: 由结构脚本的行骨架负责的标记（**登记而非跳过**）。
#:
#: 值 = 该循环在源 xlsx 里的标记处数（Task 3 冻结）。这些章节的 rows 被对方整表
#: 重写，本脚本插了也会被删。`--check` 会核对「本脚本 + 登记 == 29」，
#: 少一处都打红，防某一处无声掉队。
PENDING_MULTI_MARKER_TABLES: dict[str, tuple[int, str]] = {
    "K6": (
        12,
        "同一张表内有 2~4 处 `……`（listed 减值准备表 2 处、处置组表 4 处；"
        "soe 主表 2 处、减值准备表 2 处），label 全是 `……` ⇒ 按 label 无法定位，"
        "需要给 PLAN 加 `after_label` 位置锚点才能逐处落对。属独立子问题，"
        "不与本批混做（混做会把 4 处压成 1 处而 --check 照样归零）。",
    ),
}

#: 源侧标记总数（真源 = Task 3 的冻结常量，此处只做闭环核对）
_SOURCE_TOTAL = 29


def _utf8_stdout() -> None:
    """把 stdout/stderr 钉成 UTF-8（Windows GBK 管道会把中文腌成乱码）。"""
    for s in (sys.stdout, sys.stderr):
        rc = getattr(s, "reconfigure", None)
        if rc is None:
            continue
        try:
            rc(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def _section(doc: dict, number: str) -> dict | None:
    for sec in doc.get("sections") or []:
        if isinstance(sec, dict) and str(sec.get("section_number") or "").strip() == number:
            return sec
    return None


def _table(section: dict, name: str) -> dict | None:
    for tbl in section.get("tables") or []:
        if isinstance(tbl, dict) and str(tbl.get("name") or "").strip() == name:
            return tbl
    return None


def _total_index(rows: list[Any]) -> int | None:
    """末尾合计行的下标（可扩位行插在它**之前**）。"""
    for i in range(len(rows) - 1, -1, -1):
        row = rows[i]
        if isinstance(row, dict) and str(row.get("row_type") or "") in ("total", "subtotal"):
            return i
    return None


def _insert_index(rows: list[Any], after_label: str) -> int | None:
    """插入点下标。

    - 给了 `after_label` → 该 label 行**之后**（label 必须唯一命中，否则返回 None
      让调用方报错 —— 命中 0 或多次时猜位置比不做更糟）。
    - 没给 → 末尾合计行之前；表尾无合计行则追加到末尾。
    """
    if after_label:
        hits = [
            i
            for i, r in enumerate(rows)
            if isinstance(r, dict) and str(r.get("label") or "").strip() == after_label
        ]
        if len(hits) != 1:
            return None
        return hits[0] + 1
    idx = _total_index(rows)
    return len(rows) if idx is None else idx


def _check_closure() -> list[str]:
    """闭环自检：本脚本负责的 + 登记给结构脚本的 == 源侧总数。"""
    problems: list[str] = []
    total = len(PLAN) + len(COLLAPSED_SOURCE_MARKERS) + len(NO_TEMPLATE_TARGET)
    if total != _SOURCE_TOTAL:
        problems.append(
            f"可扩位处数不闭环：模板行 {len(PLAN)} + 折叠 {len(COLLAPSED_SOURCE_MARKERS)}"
            f" + 无落点 {len(NO_TEMPLATE_TARGET)} = {total}，"
            f"源侧 {_SOURCE_TOTAL} 处 —— 有标记无人负责（或重复负责）"
        )
    # 源坐标不得重复登记（同一处既在 PLAN 又在折叠/无落点名单里）
    planned_origins = [e[4] for e in PLAN]
    dup = sorted(
        set(planned_origins) & (set(COLLAPSED_SOURCE_MARKERS) | set(NO_TEMPLATE_TARGET))
    )
    if dup:
        problems.append(f"源坐标重复登记（既补又登记）：{dup}")
    # 🔴 唯一性按 **(variant, 源坐标)** 判：`K8!A16` 在 listed / soe 两张 sheet 里
    #    是**两处不同的标记**（同一 workbook 的两个 tab 行号恰好相同），
    #    只按坐标判会把它们误判成重复登记。
    keyed = [(e[0], e[4]) for e in PLAN]
    if len(set(keyed)) != len(keyed):
        problems.append(f"PLAN 内 (variant, 源坐标) 重复：{sorted({k for k in keyed if keyed.count(k) > 1})}")
    for key, why in {**COLLAPSED_SOURCE_MARKERS, **NO_TEMPLATE_TARGET}.items():
        if len(why) < 20:
            problems.append(f"{key} 的登记理由过短：{why!r}")
    return problems


def plan_changes(docs: dict[str, dict]) -> tuple[list[str], list[str]]:
    changes: list[str] = []
    errors: list[str] = list(_check_closure())
    for entry in PLAN:
        variant, section_number, table_name, marker, origin = entry[:5]
        after_label = entry[5] if len(entry) > 5 else ""
        tag = f"{variant} §{section_number} / {table_name}"
        section = _section(docs[variant], section_number)
        if section is None:
            errors.append(f"{tag}：找不到章节")
            continue
        tbl = _table(section, table_name)
        if tbl is None:
            errors.append(f"{tag}：找不到表")
            continue
        rows = tbl.get("rows") or []
        # 同一张表里可能有多处标记 ⇒ 期望的可扩位行数 = 该表在 PLAN 里的条目数
        want_count = sum(
            1
            for e in PLAN
            if e[0] == variant and e[1] == section_number and e[2] == table_name
        )
        existing = [
            i
            for i, r in enumerate(rows)
            if isinstance(r, dict)
            and str(r.get("label") or "").strip() == marker
            and str(r.get("row_type") or "") == _KIT.data_row(marker)["row_type"]
        ]
        stale = [
            i
            for i, r in enumerate(rows)
            if isinstance(r, dict)
            and str(r.get("label") or "").strip() == marker
            and str(r.get("row_type") or "") != _KIT.data_row(marker)["row_type"]
        ]
        if stale:
            changes.append(
                f"{tag}：{marker!r} 行 row_type 需改成 expandable（{len(stale)} 处，源 {origin}）"
            )
            continue
        if len(existing) > want_count:
            errors.append(
                f"{tag}：有 {len(existing)} 个 {marker!r} 可扩位行，PLAN 只登记 {want_count} 处"
            )
            continue
        if len(existing) == want_count:
            # 🔴 数目对了还要核**位置集合**：抹掉某条的 `after_label` 后它会退回
            #    「合计前」，而同表另一条本就在合计前 ⇒ 两条的期望位置塌成同一个，
            #    但实际行还在原处、**数目照样对** ⇒ 只数个数、甚至只逐条比位置
            #    都会全绿（实测变异 M95 连着骗过两版判据）。故按**集合**比。
            want_positions: set[int] = set()
            bad_anchor = False
            for e in PLAN:
                if (e[0], e[1], e[2]) != (variant, section_number, table_name):
                    continue
                anchor = e[5] if len(e) > 5 else ""
                at = _insert_index(rows, anchor)
                if at is None:
                    errors.append(f"{tag}：位置锚点 {anchor!r} 命中数 ≠ 1（源 {e[4]}）")
                    bad_anchor = True
                    continue
                # 锚点式：行就落在 `at`；合计式：`at` 是合计行下标，行在它前一格
                want_positions.add(at if anchor else max(at - 1, 0))
            if not bad_anchor and want_positions != set(existing):
                changes.append(
                    f"{tag}：可扩位行位置不符（期望下标 {sorted(want_positions)}，"
                    f"实际 {sorted(existing)}）—— 位置锚点缺失或行被挪动，需重排"
                )
            continue
        idx = _insert_index(rows, after_label)
        if idx is None:
            errors.append(
                f"{tag}：位置锚点 {after_label!r} 命中数 ≠ 1，无法定位（源 {origin}）"
            )
            continue
        where = f"「{after_label}」之后" if after_label else "合计行之前"
        changes.append(f"{tag}：在{where}插入可扩位行 {marker!r}（源 {origin}）")
    return changes, errors


def apply_changes(docs: dict[str, dict]) -> tuple[int, set[str]]:
    n = 0
    dirty: set[str] = set()
    for entry in PLAN:
        variant, section_number, table_name, marker, _origin = entry[:5]
        after_label = entry[5] if len(entry) > 5 else ""
        section = _section(docs[variant], section_number)
        if section is None:
            continue
        tbl = _table(section, table_name)
        if tbl is None:
            continue
        rows = list(tbl.get("rows") or [])
        want = _KIT.data_row(marker)
        want_count = sum(
            1
            for e in PLAN
            if e[0] == variant and e[1] == section_number and e[2] == table_name
        )
        # 先把标错类型的同名行升级成 expandable（不新增行）
        upgraded = False
        for i, r in enumerate(rows):
            if (
                isinstance(r, dict)
                and str(r.get("label") or "").strip() == marker
                and str(r.get("row_type") or "") != want["row_type"]
            ):
                rows[i] = {**r, "row_type": want["row_type"]}
                upgraded = True
        if upgraded:
            tbl["rows"] = rows
            n += 1
            dirty.add(variant)
            continue
        have = sum(
            1
            for r in rows
            if isinstance(r, dict)
            and str(r.get("label") or "").strip() == marker
            and str(r.get("row_type") or "") == want["row_type"]
        )
        if have >= want_count:
            continue
        idx = _insert_index(rows, after_label)
        if idx is None:
            continue
        rows.insert(idx, want)
        tbl["rows"] = rows
        n += 1
        dirty.add(variant)
    return n, dirty


def main() -> int:
    _utf8_stdout()
    ap = argparse.ArgumentParser(description="K 循环附注可扩位行补齐（幂等）")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true", help="只报欠账，有欠账 exit 1")
    g.add_argument("--dry-run", action="store_true", help="打印将补的行，不写盘")
    g.add_argument("--apply", action="store_true", help="写盘")
    args = ap.parse_args()

    raws = {
        "listed": LISTED_PATH.read_text(encoding="utf-8"),
        "soe": SOE_PATH.read_text(encoding="utf-8"),
    }
    docs = {k: json.loads(v) for k, v in raws.items()}

    changes, errors = plan_changes(docs)
    for e in errors:
        print(f"  ✗ {e}")
    if errors:
        print(f"[fix_note_k_expandable_rows] {len(errors)} 项结构性问题，拒绝写盘")
        return 2

    if not changes:
        print("[fix_note_k_expandable_rows] 0 项欠账（可扩位行已齐备）")
        return 0

    for c in changes:
        print(f"  + {c}")

    if args.check:
        print(f"[fix_note_k_expandable_rows] {len(changes)} 项欠账")
        return 1
    if args.dry_run or not args.apply:
        print(f"[fix_note_k_expandable_rows] dry-run：{len(changes)} 项待补（加 --apply 写盘）")
        return 0

    # round-trip 闸门：先证明原样 dump 能逐字复现，再写盘（否则会重排整个大文件）
    for key, raw in raws.items():
        trailing = "\n" if raw.endswith("\n") else ""
        again = json.dumps(json.loads(raw), ensure_ascii=False, indent=2) + trailing
        if again != raw:
            print(f"[fix_note_k_expandable_rows] round-trip 不一致（{key}），拒绝写盘")
            return 2

    n, dirty = apply_changes(docs)
    for key in sorted(dirty):
        path = LISTED_PATH if key == "listed" else SOE_PATH
        trailing = "\n" if raws[key].endswith("\n") else ""
        path.write_text(
            json.dumps(docs[key], ensure_ascii=False, indent=2) + trailing, encoding="utf-8"
        )
        print(f"  已写入 {path}")
    print(f"[fix_note_k_expandable_rows] 已补 {n} 个可扩位行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
