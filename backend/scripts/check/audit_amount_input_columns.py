"""audit_amount_input_columns — 可编辑金额控件全库探针（能力强于 Task18 旧探针）

Spec: `.kiro/specs/amount-input-migration-and-column-typing/` Task 2（R2.1/2.4/2.5/2.6）

## 判据（🔴 相对 Task18 旧探针的核心改进）

判据是「**金额语义列 ∧ 控件 ≠ WpAmountInput**」，**不以 `:formatter` 是否存在为
必要条件** —— 这正是 Task18 旧探针（按「找 `:formatter`」）漏掉 I1-10/I1-11
（`el-input-number` + `:precision="2"`、根本没写 `:formatter`）的原因。
`has_formatter` 在本探针里**只作输出字段**，不参与筛选（Property 4）。

## 列类型真源

关键词不在本脚本里抄第二份 —— 从前端单一真源
`components/workpaper/shared/amountColumnSemantics.ts` **解析**出金额/非金额模式
与 override（同 H 循环 `fix_h_cycle_amount_controls.py` 读 registry.ts 的做法），
在 Python 侧复现 `classifyColumnLabel` 逻辑，保证跨语言单一真源（R1.1）。

## 扫描方式

🔴 按 `<el-table-column>` … `</el-table-column>` **块配对扫描**（引号状态机定位标签
边界 + 深度计数处理多级表头嵌套），**禁固定字符窗口** —— Task18 首版用 400 字符
窗口报 22 处，逐标签复核全是 `style="width:100%"` 的 `%` 落进窗口的误报（R2.6）。

## 三分类（Property 7，无遗漏桶）

对每个叶子数据列取其可编辑金额控件（`el-input-number` / `WpAmountInput`）：

- `confirmed_violation` = 金额列 + `el-input-number`
- `reverse_violation`   = 非金额列 + `WpAmountInput`
- `ambiguous`           = label 歧义（两类都命中）或动态 label（`:label`）
- `ok`                  = 其余（金额列 + WpAmountInput / 非金额列 + el-input-number）

无可编辑金额控件的列（纯文本 el-input / 只读 span / 日期选择等）**不计入分母**
（design Property 19：只读展示金额归 `displayPrefs.fmtAmount()` 口径，不在本 spec）。

用法（Windows）::

    python backend/scripts/check/audit_amount_input_columns.py --json
    python backend/scripts/check/audit_amount_input_columns.py --check
    python backend/scripts/check/audit_amount_input_columns.py --check-files a.vue,b.vue
    python backend/scripts/check/audit_amount_input_columns.py --self-check

控制台禁 emoji（GBK 崩点在写盘之后会让 exit code 与实际状态背离）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# UTF-8 控制台（含中文 label 的 print 在 Windows GBK 控制台会崩）
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass

# backend/scripts/check/x.py -> parents[2] == backend/
BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
WP_DIR = REPO_ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
SEMANTICS_TS = WP_DIR / "shared" / "amountColumnSemantics.ts"
OUT_JSON = BACKEND_ROOT / "data" / "amount_input_migration_status.json"


# ─────────────────────────── 解析 TS 单一真源 ───────────────────────────


def _balanced_body(src: str, header_re: str, open_ch: str, close_ch: str) -> str:
    """定位 `export const X ... = <open_ch>` 后配对到 close_ch 的 body。

    🔴 用正则末尾（header 的开括号）定位，不用 src.index(open_ch) —— 后者会命中
    类型注解里的括号（如 `readonly string[]` 的 `[`），depth 立刻回零截成空串
    而脚本"成功退出"（H 脚本 `_ts_string_list` 踩过的坑）。
    """
    m = re.search(header_re, src)
    if not m:
        raise SystemExit(f"[ERR] 真源缺常量（正则失效或已改名）: {header_re}")
    start = m.end() - 1  # 指向 header 末尾的 open_ch
    if src[start] != open_ch:
        raise SystemExit(f"[ERR] 定位到的不是 {open_ch}: {header_re}")
    depth = 0
    for i in range(start, len(src)):
        c = src[i]
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return src[start + 1 : i]
    raise SystemExit(f"[ERR] {open_ch}{close_ch} 未配对: {header_re}")


@dataclass
class Semantics:
    amount_patterns: list[str]
    non_amount: list[tuple[str, str]]  # (category, pattern_src)
    overrides: dict[str, str]  # {file}::{label} -> 'amount'|'non_amount'
    global_overrides: dict[str, str]  # label -> 'amount'|'non_amount'（跨文件）


def load_semantics(ts_src: str) -> Semantics:
    # NON_AMOUNT_LABEL_PATTERNS: [ { category: '利率', pattern: /利率/, sample: '利率' }, ... ]
    non_body = _balanced_body(
        ts_src, r"export const NON_AMOUNT_LABEL_PATTERNS[^=]*=\s*\[", "[", "]"
    )
    non_amount = re.findall(
        r"category:\s*'([^']+)'\s*,\s*pattern:\s*/([^/]+)/", non_body
    )
    if len(non_amount) < 19:
        raise SystemExit(
            f"[ERR] 非金额模式解析到 {len(non_amount)} 类，少于 R1.2 要求的 19 类"
        )

    # AMOUNT_LABEL_PATTERNS: [ /金额/, /余额/, ... ]
    amt_body = _balanced_body(
        ts_src, r"export const AMOUNT_LABEL_PATTERNS[^=]*=\s*\[", "[", "]"
    )
    # 🔴 只抽「整行是 /xxx/,」的 pattern 行；不能用宽松的 /([^/]+)/，
    # 否则注释里的 `/`（如「审定表 / 披露表」）会污染配对、吞掉真正的 pattern。
    amount_patterns = re.findall(r"^\s*/([^/]+)/,?\s*$", amt_body, re.M)
    if not amount_patterns:
        raise SystemExit("[ERR] 金额模式解析为空")

    # EXPLICIT_OVERRIDES: Object.freeze({ 'k::l': { classification: 'non_amount', evidence: '...' }, ... })
    ov_body = _balanced_body(
        ts_src,
        r"export const EXPLICIT_OVERRIDES[^=]*=\s*Object\.freeze\(\{",
        "{",
        "}",
    )
    overrides = dict(
        re.findall(
            r"'([^']+::[^']+)'\s*:\s*\{\s*classification:\s*'(amount|non_amount)'",
            ov_body,
        )
    )

    # GLOBAL_LABEL_OVERRIDES: Object.freeze({ '账面数量': { classification: 'non_amount', … }, … })
    gov_body = _balanced_body(
        ts_src,
        r"export const GLOBAL_LABEL_OVERRIDES[^=]*=\s*Object\.freeze\(\{",
        "{",
        "}",
    )
    # 键不含 `::`（文件级 override 才含），故用非 `::`、非 `'` 的键正则
    global_overrides = dict(
        re.findall(
            r"'([^']+)'\s*:\s*\{\s*classification:\s*'(amount|non_amount)'",
            gov_body,
        )
    )

    return Semantics(amount_patterns, non_amount, overrides, global_overrides)


def classify_raw(label: str, sem: Semantics) -> str:
    a = any(re.search(p, label) for p in sem.amount_patterns)
    n = any(re.search(p, label) for _, p in sem.non_amount)
    if a and n:
        return "ambiguous"
    if n:
        return "non_amount"
    if a:
        return "amount"
    return "non_amount"


def classify(label: str, rel_file: str, sem: Semantics) -> str:
    key = f"{rel_file}::{label}"
    if key in sem.overrides:
        return sem.overrides[key]
    if label in sem.global_overrides:
        return sem.global_overrides[label]
    return classify_raw(label, sem)


def non_amount_category(label: str, sem: Semantics) -> str | None:
    for cat, pat in sem.non_amount:
        if re.search(pat, label):
            return cat
    return None


# ─────────────────────────── 块配对扫描 ───────────────────────────

TAG_OPEN = re.compile(r"<el-table-column(?=[\s/>])")
TOKEN = re.compile(r"<el-table-column(?=[\s/>])|</el-table-column>")
CTRL_INUM = re.compile(r"<el-input-number(?=[\s/>])")
CTRL_WAI = re.compile(r"<WpAmountInput(?=[\s/>])")
LABEL_STATIC = re.compile(r'(?<![:\w])label="([^"]*)"')
LABEL_DYNAMIC = re.compile(r':label="([^"]*)"')


def find_tag_end(src: str, open_at: int) -> int:
    """引号状态机：从 `<el-table-column` 起找到该开标签的 `>`（含 `/>`）。"""
    i = open_at
    quote = ""
    while i < len(src):
        c = src[i]
        if quote:
            if c == quote:
                quote = ""
        elif c in "\"'":
            quote = c
        elif c == ">":
            return i
        i += 1
    raise SystemExit(f"[ERR] el-table-column 标签未闭合 @ {open_at}")


def find_block_close(src: str, content_start: int) -> int:
    """深度计数找匹配的 `</el-table-column>`，返回其起始位置；未闭合返回 -1。"""
    depth = 1
    for m in TOKEN.finditer(src, content_start):
        tok = m.group()
        if tok.startswith("</"):
            depth -= 1
            if depth == 0:
                return m.start()
        else:
            te = find_tag_end(src, m.start())
            if src[te - 1] != "/":  # 自闭合不增加深度
                depth += 1
    return -1


@dataclass
class ColRecord:
    open_at: int
    block_end: int  # 块结束（自闭合=tag_end；块=闭合标签末尾）
    label: str
    dynamic: bool
    is_leaf: bool
    control: str  # 'el-input-number' | 'WpAmountInput' | ''
    has_formatter: bool
    line: int


def _extract_label(tag_text: str) -> tuple[str, bool]:
    """返回 (label, is_dynamic)。静态优先；仅有 :label 则 dynamic。"""
    m = LABEL_STATIC.search(tag_text)
    if m:
        return m.group(1), False
    d = LABEL_DYNAMIC.search(tag_text)
    if d:
        return d.group(1), True
    return "", False


def scan_source(src: str, rel_file: str, sem: Semantics) -> list[dict]:
    """扫一个 .vue 源，返回**叶子金额控件列**的分类记录。"""
    cols: list[ColRecord] = []
    for m in TAG_OPEN.finditer(src):
        open_at = m.start()
        tag_end = find_tag_end(src, open_at)
        tag_text = src[open_at : tag_end + 1]
        self_closing = src[tag_end - 1] == "/"
        if self_closing:
            content_start = content_end = tag_end + 1
            block_end = tag_end + 1
        else:
            content_start = tag_end + 1
            close_at = find_block_close(src, content_start)
            if close_at < 0:
                raise SystemExit(
                    f"[ERR] {rel_file}: el-table-column 块未闭合 @ 行"
                    f" {src.count(chr(10), 0, open_at) + 1}"
                )
            content_end = close_at
            block_end = close_at + len("</el-table-column>")
        content = src[content_start:content_end]
        is_leaf = TAG_OPEN.search(content) is None
        label, dynamic = _extract_label(tag_text)

        control = ""
        has_formatter = False
        if is_leaf:
            has_inum = CTRL_INUM.search(content) is not None
            has_wai = CTRL_WAI.search(content) is not None
            if has_inum:
                control = "el-input-number"
                # 该 el-input-number 标签内是否有 :formatter（仅输出字段）
                im = CTRL_INUM.search(content)
                if im:
                    ie = find_ctrl_tag_end(content, im.start())
                    has_formatter = ":formatter" in content[im.start() : ie + 1]
            elif has_wai:
                control = "WpAmountInput"

        cols.append(
            ColRecord(
                open_at=open_at,
                block_end=block_end,
                label=label,
                dynamic=dynamic,
                is_leaf=is_leaf,
                control=control,
                has_formatter=has_formatter,
                line=src.count("\n", 0, open_at) + 1,
            )
        )

    # full_label：祖先 label 链拼接（仅用于输出展示，不用于分类）
    results: list[dict] = []
    for c in cols:
        if not c.is_leaf or not c.control:
            continue  # 父组列 / 无金额控件列不计入分母
        ancestors = [
            a
            for a in cols
            if a.open_at < c.open_at and a.block_end > c.block_end and a.label
        ]
        ancestors.sort(key=lambda a: a.open_at)
        full = " / ".join([a.label for a in ancestors] + ([c.label] if c.label else []))

        reason = ""
        if c.dynamic:
            sem_cls = "ambiguous"
            reason = "dynamic_label"
        elif not c.label:
            sem_cls = "ambiguous"
            reason = "no_label"
        else:
            sem_cls = classify(c.label, rel_file, sem)

        nac = non_amount_category(c.label, sem) if sem_cls == "non_amount" else None
        bucket = _bucket(sem_cls, c.control, nac)
        results.append(
            {
                "file": rel_file,
                "line": c.line,
                "label": c.label,
                "full_label": full or c.label,
                "control": c.control,
                "has_formatter": c.has_formatter,  # Property 4：仅输出，不参与判定
                "semantic": sem_cls,
                "bucket": bucket,
                "reason": reason,
                "non_amount_category": nac,
                "batch": _batch_of(rel_file, c.has_formatter),
            }
        )
    return results


def find_ctrl_tag_end(src: str, open_at: int) -> int:
    """引号状态机找控件开标签的 `>`（复用于 el-input-number/WpAmountInput）。"""
    i = open_at
    quote = ""
    while i < len(src):
        c = src[i]
        if quote:
            if c == quote:
                quote = ""
        elif c in "\"'":
            quote = c
        elif c == ">":
            return i
        i += 1
    return len(src) - 1


def _bucket(sem_cls: str, control: str, non_amount_cat: str | None) -> str:
    """列级三分类。

    🔴 反向违规（reverse_violation）只在 label **明确命中非金额模式**
    （`non_amount_cat is not None`）时触发，**不含** `classify_raw` 的兜底
    「都不命中 → non_amount」。否则「坏账准备 / 期初AJE / 账项调整」这类已正确
    迁移为 WpAmountInput 的**金额列**（label 不含金额关键词而落到兜底 non_amount）
    会被误报反向违规，污染反向断言（实测假阳性 273 条全是 category=None）。
    也满足 Property 11：反向失败消息必须能给出「命中的非金额语义类别」。
    """
    if sem_cls == "ambiguous":
        return "ambiguous"
    if control == "el-input-number":
        return "confirmed_violation" if sem_cls == "amount" else "ok"
    if control == "WpAmountInput":
        return "reverse_violation" if non_amount_cat is not None else "ok"
    return "ok"


def _batch_of(rel_file: str, has_formatter: bool) -> int:
    """初步批次归属（Task 9 细化）：formatter 空操作=1；I 循环摊销=2；其余=3。"""
    if "i1/amortization" in rel_file:
        return 2
    if has_formatter:
        return 1
    return 3


# ─────────────────────────── totals（控件级，独立于列级分类） ───────────────────────────


def count_controls(src: str) -> tuple[int, int, int]:
    """返回 (el_input_number, el_input_number_with_formatter, wp_amount_input)。"""
    inum = 0
    inum_fmt = 0
    for m in CTRL_INUM.finditer(src):
        inum += 1
        te = find_ctrl_tag_end(src, m.start())
        if ":formatter" in src[m.start() : te + 1]:
            inum_fmt += 1
    wai = len(CTRL_WAI.findall(src))
    return inum, inum_fmt, wai


# ─────────────────────────── 反向自检（Property 8） ───────────────────────────

SELF_CHECK_CASES = [
    # (label, control 片段, 期望 bucket, 说明)
    ("原值", "<WpAmountInput v-model=\"row.cost\" />", "ok", "已迁移金额列不报违规"),
    (
        "使用期限(年)",
        "<el-input-number v-model=\"row.years\" :controls=\"false\" :precision=\"2\" />",
        "ok",
        "el-input-number 年限列不报违规",
    ),
    (
        "原值",
        "<el-input-number v-model=\"row.cost\" :controls=\"false\" :precision=\"2\" />",
        "confirmed_violation",
        "el-input-number 金额列必报违规",
    ),
    (
        "使用期限(年)",
        "<WpAmountInput v-model=\"row.years\" />",
        "reverse_violation",
        "WpAmountInput 用在非金额列必报反向违规",
    ),
]


def run_self_check(sem: Semantics) -> bool:
    ok = True
    for label, ctrl, expect_bucket, desc in SELF_CHECK_CASES:
        src = (
            f'<el-table-column label="{label}">'
            f'<template #default="{{ row }}">{ctrl}</template>'
            f"</el-table-column>"
        )
        res = scan_source(src, "__selfcheck__.vue", sem)
        got = res[0]["bucket"] if res else "<none>"
        mark = "OK " if got == expect_bucket else "FAIL"
        if got != expect_bucket:
            ok = False
        print(f"  [{mark}] {desc}: label={label!r} -> {got}（期望 {expect_bucket}）")
    return ok


# ─────────────────────────── 主流程 ───────────────────────────


def iter_vue_files() -> list[Path]:
    return sorted(
        p
        for p in WP_DIR.rglob("*.vue")
        if "__tests__" not in p.parts
    )


def scan_all(sem: Semantics) -> dict:
    files = iter_vue_files()
    confirmed: list[dict] = []
    reverse: list[dict] = []
    ambiguous: list[dict] = []
    ok_count = 0
    tot_inum = tot_fmt = tot_wai = 0

    for p in files:
        src = p.read_text(encoding="utf-8")
        rel = p.relative_to(WP_DIR).as_posix()
        i, f, w = count_controls(src)
        tot_inum += i
        tot_fmt += f
        tot_wai += w
        for rec in scan_source(src, rel, sem):
            b = rec["bucket"]
            if b == "confirmed_violation":
                confirmed.append(rec)
            elif b == "reverse_violation":
                reverse.append(rec)
            elif b == "ambiguous":
                ambiguous.append(rec)
            else:
                ok_count += 1

    classified = len(confirmed) + len(reverse) + len(ambiguous) + ok_count
    return {
        "scanned_files": len(files),
        "totals": {
            "el_input_number": tot_inum,
            "el_input_number_with_formatter": tot_fmt,
            "wp_amount_input": tot_wai,
        },
        "column_classified_total": classified,
        "confirmed_violation": confirmed,
        "reverse_violation": reverse,
        "ambiguous": ambiguous,
        "ok_count": ok_count,
    }


def _cycle_of(file: str) -> str:
    """由文件相对 workpaper 的路径首段推审计循环字母（e1→E、k1→K、h2→H…）。"""
    seg = file.split("/")[0]
    m = re.match(r"([a-z])", seg)
    return m.group(1).upper() if m else "?"


# 正在推进的 active spec 循环（其文件迁移须待该 spec 收口，避免覆盖在途改动）
ACTIVE_SPEC_CYCLES = {"E", "I", "K", "L", "M", "N"}


def build_plan(report: dict) -> dict:
    """把 confirmed_violation 按循环分组产出批 3+ 规划（Task 9，不执行迁移）。"""
    from collections import defaultdict

    by_cyc: dict[str, dict] = defaultdict(lambda: {"files": set(), "count": 0})
    for r in report["confirmed_violation"]:
        c = _cycle_of(r["file"])
        by_cyc[c]["files"].add(r["file"])
        by_cyc[c]["count"] += 1
    batches = [
        {
            "cycle": c,
            "files": len(by_cyc[c]["files"]),
            "columns": by_cyc[c]["count"],
            "active_spec_conflict": c in ACTIVE_SPEC_CYCLES,
        }
        for c in sorted(by_cyc)
    ]
    amb_reason: dict[str, int] = defaultdict(int)
    for r in report["ambiguous"]:
        amb_reason[r.get("reason") or "label_hit_both"] += 1
    return {
        "confirmed_total": len(report["confirmed_violation"]),
        "ambiguous_total": len(report["ambiguous"]),
        "batches_by_cycle": batches,
        "ambiguous_by_reason": dict(amb_reason),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="扫全库并写产物 JSON")
    ap.add_argument("--check", action="store_true", help="全库 confirmed_violation 应为 0，否则 exit 1")
    ap.add_argument("--check-files", default="", help="逗号分隔的相对路径，仅检查这些文件的 confirmed_violation")
    ap.add_argument("--self-check", action="store_true", help="只跑反向自检三条")
    ap.add_argument("--plan", action="store_true", help="按循环分组 confirmed，产出批 3+ 规划 JSON")
    args = ap.parse_args()

    if not SEMANTICS_TS.exists():
        print(f"[ERR] 列类型真源不存在: {SEMANTICS_TS}")
        return 2
    sem = load_semantics(SEMANTICS_TS.read_text(encoding="utf-8"))
    print(
        f"[INFO] 真源: 金额模式={len(sem.amount_patterns)} "
        f"非金额类={len(sem.non_amount)} override={len(sem.overrides)}"
    )

    # 探针自检永远先跑（保证探针本体没坏）
    print("[INFO] 反向自检：")
    if not run_self_check(sem):
        print("[ERR] 反向自检未通过，探针能力受损，中止")
        return 3

    if args.self_check:
        print("[OK] 反向自检通过")
        return 0

    if args.plan:
        plan = build_plan(scan_all(sem))
        plan_json = BACKEND_ROOT / "data" / "amount_input_batch3_plan.json"
        plan_json.write_text(
            json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[INFO] confirmed={plan['confirmed_total']} ambiguous={plan['ambiguous_total']}")
        for b in plan["batches_by_cycle"]:
            tag = " [active spec 冲突，待其收口]" if b["active_spec_conflict"] else ""
            print(f"  循环 {b['cycle']}: 文件={b['files']} 列={b['columns']}{tag}")
        print(f"  ambiguous 分类: {plan['ambiguous_by_reason']}")
        print(f"[OK] 已写 {plan_json.relative_to(REPO_ROOT)}")
        return 0

    if args.check_files:
        wanted = {s.strip() for s in args.check_files.split(",") if s.strip()}
        viol = []
        for name in sorted(wanted):
            p = WP_DIR / name
            if not p.exists():
                print(f"[ERR] 指定文件不存在: {name}")
                return 2
            for rec in scan_source(p.read_text(encoding="utf-8"), name, sem):
                if rec["bucket"] == "confirmed_violation":
                    viol.append(rec)
        for r in viol:
            print(f"  VIOLATION {r['file']}:{r['line']} label={r['label']!r}")
        if viol:
            print(f"[ERR] {len(viol)} 处金额列未迁移（指定文件范围）")
            return 1
        print(f"[OK] 指定 {len(wanted)} 文件无 confirmed_violation")
        return 0

    report = scan_all(sem)
    t = report["totals"]
    print(
        f"[INFO] 扫描 {report['scanned_files']} 文件 | "
        f"el-input-number={t['el_input_number']} "
        f"(with :formatter={t['el_input_number_with_formatter']}) "
        f"WpAmountInput={t['wp_amount_input']}"
    )
    print(
        f"[INFO] 列级分类={report['column_classified_total']} | "
        f"confirmed={len(report['confirmed_violation'])} "
        f"reverse={len(report['reverse_violation'])} "
        f"ambiguous={len(report['ambiguous'])} ok={report['ok_count']}"
    )

    if args.json:
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        OUT_JSON.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[OK] 已写 {OUT_JSON.relative_to(REPO_ROOT)}")
        return 0

    if args.check:
        if report["confirmed_violation"]:
            print(
                f"[ERR] 全库 {len(report['confirmed_violation'])} 处金额列未迁移"
                f"（confirmed_violation）"
            )
            return 1
        print("[OK] 全库无 confirmed_violation")
        return 0

    print("[INFO] 无操作（用 --json / --check / --check-files / --self-check）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
