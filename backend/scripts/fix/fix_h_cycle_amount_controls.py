"""fix_h_cycle_amount_controls — H 类披露表/审定表金额控件替换（幂等）

Spec: .kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/ Task 12
      (R10.1 / R10.2)

把 H 类**披露 Tab 与审定表**里的金额 `el-input-number` 换成
`components/workpaper/shared/WpAmountInput.vue`。

为什么必须换（平台铁律，双证）：
  1) 源码 —— element-plus 2.13.6 的 `es/components/input-number/**` 全文无
     `formatter` / `parser`，该 prop 不存在；
  2) 浏览器实测 —— `el-input-number :formatter` 下输 1234567.5 显示 `1234567.50`
     （无千分符），换 `el-input` 后显示 `1,234,567.50`。

非金额字段（利率 / 比例 / 年限 / 笔数）**保留** `el-input-number`，
清单在前端单一真源 `composables/hCycleAmountControlRegistry.ts`
（本脚本读它，不在这里抄第二份）。

用法（Windows）：
    python backend/scripts/fix/fix_h_cycle_amount_controls.py --check
    python backend/scripts/fix/fix_h_cycle_amount_controls.py --dry-run
    python backend/scripts/fix/fix_h_cycle_amount_controls.py --apply

控制台输出禁 emoji（GBK 崩点在写盘之后，会让 exit code 与实际写入状态背离）。
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# backend/scripts/fix/x.py -> parents[2] == backend/
BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
WP_DIR = REPO_ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
REGISTRY = WP_DIR / "composables" / "hCycleAmountControlRegistry.ts"

AMOUNT_COMPONENT = "WpAmountInput"
IMPORT_LINE = "import WpAmountInput from '{rel}/shared/WpAmountInput.vue'\n"


# ─────────────────────────── 读前端登记表（单一真源） ───────────────────────────


def _ts_string_list(src: str, const_name: str) -> list[str]:
    """抽 `export const X: readonly string[] = [ '...', ... ]` 的字面量。"""
    m = re.search(rf"export const {const_name}[^=]*=\s*\[", src)
    if not m:
        raise SystemExit(f"[ERR] 登记表缺常量 {const_name}（正则失效或已改名）")
    # 🔴 不能写 src.index("[", m.start()) —— 会命中**类型注解**里的 `string[]`，
    # depth 立刻回零、body 截成空串 ⇒ 目标清单变空而脚本"成功退出"。
    # 正则末尾的 `\[` 就是数组字面量的开括号，直接用它。
    start = m.end() - 1
    depth = 0
    for i in range(start, len(src)):
        if src[i] == "[":
            depth += 1
        elif src[i] == "]":
            depth -= 1
            if depth == 0:
                body = src[start + 1 : i]
                break
    else:  # pragma: no cover
        raise SystemExit(f"[ERR] {const_name} 方括号未配对")
    return re.findall(r"'([^']+)'", body)


def _ts_record_keys(src: str, const_name: str) -> set[str]:
    """抽 `Object.freeze({ 'a::b': '理由', ... })` 的键集。"""
    m = re.search(rf"export const {const_name}[^=]*=\s*Object\.freeze\(\{{", src)
    if not m:
        raise SystemExit(f"[ERR] 登记表缺常量 {const_name}")
    # 同 `_ts_string_list`：用正则末尾定位，不要 index("{") ——
    # 类型注解 `Readonly<Record<string, string>>` 里没有 `{`，但形态一变就会踩
    start = m.end() - 1
    depth = 0
    for i in range(start, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                body = src[start + 1 : i]
                break
    else:  # pragma: no cover
        raise SystemExit(f"[ERR] {const_name} 花括号未配对")
    # 键形如 'h2/core/X.vue::interestCapRate':
    return set(re.findall(r"'([^']+::[^']+)'\s*:", body))


# ─────────────────────────────── 替换核心 ───────────────────────────────


@dataclass
class Change:
    file: str
    field: str
    kind: str  # 'replace' | 'keep' | 'import'


TAG_OPEN = re.compile(r"<el-input-number(?=[\s/>])")


def _find_tag_end(src: str, open_at: int) -> int:
    """从 `<el-input-number` 起找到该标签的结束位置（含 `/>` 或 `>`）。

    属性值里可能出现 `>`（箭头函数 `(v) =>`），故按引号状态扫。
    """
    i = src.index(">", open_at)  # 先给个下界；下面按状态机重扫
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
    raise SystemExit(f"[ERR] 标签未闭合 @ {open_at}")


FIELD_RE = re.compile(
    r"""(?:v-model|:model-value)\s*=\s*"([^"]+)\"""",
)


def _field_of(tag: str) -> str:
    """从标签文本抽 v-model / :model-value 绑定的**字段名**。

    形态举例：
        v-model="row.beginBalance"          -> beginBalance
        v-model="state.summary.clearingEnd" -> clearingEnd
        :model-value="cellAmt(row,'begin')" -> cellAmt   （函数式，用函数名）
        :model-value="rawCell(m, row.key, cat.key)" -> rawCell
    """
    m = FIELD_RE.search(tag)
    if not m:
        return ""
    expr = m.group(1).strip()
    fn = re.match(r"([A-Za-z_$][\w$]*)\s*\(", expr)
    if fn:
        return fn.group(1)
    return expr.split(".")[-1].strip()


def _strip_controls(tag: str) -> str:
    """去掉 `WpAmountInput` 不存在的 prop（`:controls="false"` / `:precision`）。"""
    out = re.sub(r'\s*:controls\s*=\s*"false"', "", tag)
    out = re.sub(r'\s*:precision\s*=\s*"\d+"', "", out)
    out = re.sub(r'\s*:min\s*=\s*"[^"]*"', "", out)
    out = re.sub(r'\s*:max\s*=\s*"[^"]*"', "", out)
    out = re.sub(r'\s*:step\s*=\s*"[^"]*"', "", out)
    return out


def _rel_shared_prefix(rel_path: str) -> str:
    """由文件相对 `components/workpaper/` 的路径算 `shared/` 的相对前缀。"""
    depth = rel_path.count("/")
    return "/".join([".."] * depth) if depth else "."


def process_file(
    rel: str, non_amount_keys: set[str]
) -> tuple[str, list[Change]] | None:
    path = WP_DIR / rel
    if not path.exists():
        raise SystemExit(f"[ERR] 目标文件不存在: {path}")
    src = path.read_text(encoding="utf-8")

    changes: list[Change] = []
    out: list[str] = []
    pos = 0
    for m in TAG_OPEN.finditer(src):
        open_at = m.start()
        if open_at < pos:
            continue
        end = _find_tag_end(src, open_at)
        tag = src[open_at : end + 1]
        field = _field_of(tag)
        key = f"{rel}::{field}"
        if key in non_amount_keys:
            changes.append(Change(rel, field, "keep"))
            continue  # 原样保留（不写进 out，靠最后的整体切片）
        # 替换：开标签名 + 去掉不存在的 prop；闭合标签在下面统一处理
        new_tag = _strip_controls(tag).replace(
            "<el-input-number", f"<{AMOUNT_COMPONENT}", 1
        )
        out.append(src[pos:open_at])
        out.append(new_tag)
        pos = end + 1
        changes.append(Change(rel, field, "replace"))
    out.append(src[pos:])
    new_src = "".join(out)

    # 闭合标签：只在本文件已无 el-input-number 开标签（或剩下的都是 keep）时安全处理。
    # `</el-input-number>` 与开标签一一对应，替换数量必须等于 replace 数量。
    replace_n = sum(1 for c in changes if c.kind == "replace")
    keep_n = sum(1 for c in changes if c.kind == "keep")
    close_total = new_src.count("</el-input-number>")
    if replace_n and close_total:
        # 剩余 keep 的闭合标签数 = keep_n（自闭合的 keep 不产生闭合标签，故取 min）
        to_replace = close_total - min(keep_n, close_total)
        if to_replace > 0:
            new_src = new_src.replace(
                "</el-input-number>", f"</{AMOUNT_COMPONENT}>", to_replace
            )

    # import 行
    if replace_n and f"shared/{AMOUNT_COMPONENT}.vue" not in new_src:
        prefix = _rel_shared_prefix(rel)
        imp = IMPORT_LINE.format(rel=prefix)
        # 插在最后一个顶层 import 之后
        last = None
        for im in re.finditer(r"^import .*$", new_src, re.M):
            last = im
        if not last:
            raise SystemExit(f"[ERR] {rel} 无 import 行，无法插入")
        at = last.end() + 1
        new_src = new_src[:at] + imp + new_src[at:]
        changes.append(Change(rel, AMOUNT_COMPONENT, "import"))

    if new_src == src:
        return None
    return new_src, changes


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="只报欠账，有欠账 exit 1")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if not REGISTRY.exists():
        print(f"[ERR] 登记表不存在: {REGISTRY}")
        return 2
    reg = REGISTRY.read_text(encoding="utf-8")
    targets = _ts_string_list(reg, "H_AMOUNT_TARGET_FILES")
    non_amount = _ts_record_keys(reg, "H_NON_AMOUNT_FIELDS")
    if not targets:
        print("[ERR] 目标文件清单为空（登记表解析失效？）")
        return 2
    print(f"[INFO] targets={len(targets)} non_amount_registered={len(non_amount)}")

    pending: list[tuple[str, str, list[Change]]] = []
    for rel in targets:
        res = process_file(rel, non_amount)
        if res is None:
            continue
        new_src, changes = res
        pending.append((rel, new_src, changes))

    total_replace = 0
    total_keep = 0
    for rel, _new, changes in pending:
        r = sum(1 for c in changes if c.kind == "replace")
        k = sum(1 for c in changes if c.kind == "keep")
        imp = any(c.kind == "import" for c in changes)
        total_replace += r
        total_keep += k
        kept = sorted({c.field for c in changes if c.kind == "keep"})
        print(
            f"  {rel}: replace={r} keep={k}"
            + (f" kept_fields={kept}" if kept else "")
            + (" +import" if imp else "")
        )

    # 已收敛的文件也要报 keep 数（--check 归零判据只看 replace）
    for rel in targets:
        if any(p[0] == rel for p in pending):
            continue
        print(f"  {rel}: already converged")

    print(f"[INFO] total replace={total_replace} keep={total_keep}")

    if args.check:
        if total_replace:
            print(f"[ERR] {total_replace} 处金额 el-input-number 未替换")
            return 1
        print("[OK] no pending")
        return 0

    if args.dry_run:
        print("[OK] dry-run only, nothing written")
        return 0

    for rel, new_src, _c in pending:
        (WP_DIR / rel).write_text(new_src, encoding="utf-8")
    print(f"[OK] applied to {len(pending)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
