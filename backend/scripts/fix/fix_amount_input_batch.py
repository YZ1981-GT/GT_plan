"""fix_amount_input_batch — 可编辑金额控件分批迁移（幂等）

Spec: `.kiro/specs/amount-input-migration-and-column-typing/` Task 5（批 1）

把「金额语义」的 `el-input-number` 迁移到 `WpAmountInput`。批 1 = 全库所有带
`:formatter` 的 `el-input-number`（80 处 / 实测 13 文件）—— 这些是**确定的
formatter 空操作**（EP 2.13.6 无 `:formatter` prop，千分符从未生效）。

## 判据（复用列类型单一真源，不抄第二份）

import 探针模块 `audit_amount_input_columns`，用其 `classifyColumnLabel` 与块扫描
原语。对每个带 `:formatter` 的 `el-input-number` 标签，取**就近 label**
（向前最近的静态 `label="..."`，覆盖 el-table-column 与 el-form-item 两类）：

  - amount     → 换 `WpAmountInput`（删 `:formatter`/`:parser`/`:controls`）
  - non_amount → 只删 `:formatter`/`:parser`，**保留** `el-input-number`
                 （🔴 写了 formatter 不等于是金额列，作者可能误加）
  - ambiguous / 动态 label / 非自闭合 → **跳过并登记**（交人工，Task 9）

## 等价性保留（R5）

`:model-value`/`v-model` / `@change` / `:disabled` / `size` / `class` / `style` /
`v-if` 逐字保留；金额列换 WpAmountInput 时删无支持的 `:precision`（平台守卫要求）；
**非金额列（保留 el-input-number）的 `:precision` 数值一律不动**（R4.4 / Property 17）；
`:min`/`:max` 若原无则不新增（备抵/调整列需负数）。

## 安全

- 目标文件 `git status` 为已修改（并发会话在改）→ **跳过并登记**，不覆盖（R4.5）
- import 插在 `<script setup>` 之后（不用「最后一个 import 行」锚点 ——
  `fix_vite_transform_anchor_damage.py` 的事故正是那样插进了多行 import 中间）
- 字节级读写：按原换行风格写回，不改文件换行

用法（Windows）::

    python backend/scripts/fix/fix_amount_input_batch.py --dry-run
    python backend/scripts/fix/fix_amount_input_batch.py --apply
    python backend/scripts/fix/fix_amount_input_batch.py --check
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
WP_DIR = REPO_ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"

# 复用探针模块（列类型真源 + 块扫描原语），不在此抄第二份
sys.path.insert(0, str(BACKEND_ROOT / "scripts" / "check"))
import audit_amount_input_columns as probe  # noqa: E402

def _owning_label(src: str, pos: int) -> tuple[str, bool] | None:
    """找控件 pos 归属的列/表单项 label，返回 (label, is_dynamic) 或 None。

    🔴 用「包含 pos 的最内层 el-table-column 块」的 label，而非就近 rfind ——
    否则 v-for 动态列（`:label="period==='prior'?..."`）会让金额列取到前一个静态
    label（如月度变动金额列取到「月份」）而漏判/误判。动态 :label 标记 is_dynamic。
    回退：pos 所在未闭合 el-form-item 的 label（E1TabBankDetail 编辑弹窗）。
    都无 → None（调用方跳过登记，交后续批次）。
    """
    best_span: int | None = None
    best: tuple[str, bool] | None = None
    for m in probe.TAG_OPEN.finditer(src):
        open_at = m.start()
        if open_at > pos:
            break
        tag_end = probe.find_tag_end(src, open_at)
        if src[tag_end - 1] == "/":
            continue  # 自闭合列无 content
        close_at = probe.find_block_close(src, tag_end + 1)
        if close_at < 0 or not (tag_end < pos < close_at):
            continue
        span = close_at - tag_end
        if best_span is None or span < best_span:
            best_span = span
            best = probe._extract_label(src[open_at : tag_end + 1])
    if best is not None:
        return best
    fm_open = src.rfind("<el-form-item", 0, pos)
    if fm_open >= 0 and src.find("</el-form-item>", fm_open, pos) == -1:
        lm = re.search(r'\blabel="([^"]*)"', src[fm_open:pos])
        if lm:
            return (lm.group(1), False)
    return None


def _amount_tag(tag: str) -> str:
    """el-input-number → WpAmountInput，删 WpAmountInput 不支持/无意义的 prop。

    删 `:formatter`/`:parser`（EP 无此 prop）、`:controls`（无步进按钮）、
    `:precision`（🔴 WpAmountInput 固定 2 位小数、无 precision prop；平台守卫
    `e1AmountControlIronLaw.spec.ts` 明确断言 WpAmountInput 不得传 :precision）。
    删除金额列的无效 :precision **不违背** Property 17 —— 该 Property 约束的是
    「不改**保留的 el-input-number**（非金额列）的 precision 数值」。
    """
    out = tag.replace("<el-input-number", "<WpAmountInput", 1)
    out = re.sub(r'\s*:formatter="[^"]*"', "", out)
    out = re.sub(r'\s*:parser="[^"]*"', "", out)
    out = re.sub(r'\s*:controls="false"', "", out)
    out = re.sub(r'\s*:precision="[^"]*"', "", out)
    # 🔴 WpAmountInput 无 :min/:max prop（平台标准金额控件允许负，与备抵/调整列一致）。
    # 原金额列的 :min="0"（禁负）语义无法保留 —— 删除（登记：原值等迁移后允许负，
    # 符合 R5.3「WpAmountInput 允许负」的既有平台行为）。
    out = re.sub(r'\s*:min="[^"]*"', "", out)
    out = re.sub(r'\s*:max="[^"]*"', "", out)
    return out


def _strip_formatter(tag: str) -> str:
    """非金额列：只删 formatter/parser，保留 el-input-number 与 precision。"""
    out = re.sub(r'\s*:formatter="[^"]*"', "", tag)
    out = re.sub(r'\s*:parser="[^"]*"', "", out)
    return out


def _rel_shared_prefix(rel: str) -> str:
    d = rel.count("/")
    return "/".join([".."] * d) if d else "."


def _ensure_import(src: str, rel: str) -> str:
    if "shared/WpAmountInput.vue" in src:
        return src
    prefix = _rel_shared_prefix(rel)
    imp = f"import WpAmountInput from '{prefix}/shared/WpAmountInput.vue'\n"
    m = re.search(r"<script setup[^>]*>\n", src)
    if not m:
        raise SystemExit(f"[ERR] {rel} 无 <script setup>，无法插 import")
    at = m.end()
    return src[:at] + imp + src[at:]


def _git_modified(path: Path) -> bool:
    r = subprocess.run(
        ["git", "status", "--porcelain", "--", str(path)],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    return bool(r.stdout.strip())


def target_files() -> list[Path]:
    """批 1 目标：全库含 `:formatter` 的 .vue（formatter 空操作确定错误）。"""
    out = []
    for p in WP_DIR.rglob("*.vue"):
        if "__tests__" in p.parts:
            continue
        if ":formatter" in p.read_text(encoding="utf-8"):
            out.append(p)
    return sorted(out)


def process_file(
    path: Path, sem, require_formatter: bool = True
) -> tuple[str, Counter, list[tuple[str, str]]] | None:
    """返回 (new_src, stats, skipped)；无变更返回 None。

    require_formatter=True（批1）：只处理带 :formatter 的金额列。
    require_formatter=False（批2 --files）：处理指定文件的**所有**金额列（含无 formatter）。
    """
    rel = path.relative_to(WP_DIR).as_posix()
    raw = path.read_bytes()
    crlf = b"\r\n" in raw
    src = raw.decode("utf-8").replace("\r\n", "\n")

    edits: list[tuple[int, int, str]] = []
    stats: Counter = Counter()
    skipped: list[tuple[str, str]] = []

    for m in probe.CTRL_INUM.finditer(src):
        cs = m.start()
        ce = probe.find_ctrl_tag_end(src, cs)
        tag = src[cs : ce + 1]
        has_fmt = ":formatter" in tag
        if require_formatter and not has_fmt:
            continue  # 批1只处理 formatter 列；批2(--files)处理所有金额列
        owner = _owning_label(src, cs)
        if owner is None:
            skipped.append(("<无法归属>", "no_owner"))
            stats["skip"] += 1
            continue
        label, dynamic = owner
        if dynamic or not label:
            skipped.append((label or "<dynamic>", "dynamic_label"))
            stats["skip"] += 1
            continue
        if src[ce - 1] != "/":  # 非自闭合（带 slot），本批不处理
            skipped.append((label, "not_self_closing"))
            stats["skip"] += 1
            continue
        sem_cls = probe.classify(label, rel, sem)
        if sem_cls == "ambiguous":
            skipped.append((label, "ambiguous"))
            stats["skip"] += 1
            continue
        if sem_cls == "amount":
            edits.append((cs, ce + 1, _amount_tag(tag)))
            stats["amount"] += 1
        elif probe.non_amount_category(label, sem) is not None:
            # 明确命中非金额模式（比率/汇率/期限…）：仅当作者误加 formatter 才删；
            # 无 formatter 的非金额列（如「使用期限(年)」）保持 el-input-number 不动
            if has_fmt:
                edits.append((cs, ce + 1, _strip_formatter(tag)))
                stats["non_amount"] += 1
        else:
            # 🔴 兜底 non_amount（label 无任何金额/非金额关键词）→ 可疑：可能是金额列
            # 漏判（如「期初原币」外币金额）。不擅自删 formatter，跳过登记交人工核查。
            skipped.append((label, "unknown_no_keyword"))
            stats["skip"] += 1

    if not edits:
        return None

    edits.sort(key=lambda e: e[0], reverse=True)
    out = src
    for s, e, new in edits:
        out = out[:s] + new + out[e:]
    if stats["amount"] > 0:
        out = _ensure_import(out, rel)

    if out == src:
        return None
    final = out.replace("\n", "\r\n") if crlf else out
    return final, stats, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="有待迁移则 exit 1")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument(
        "--files", default="",
        help="批2：逗号分隔的相对 workpaper 路径，处理这些文件的所有金额列（含无 :formatter）",
    )
    ap.add_argument(
        "--cycle", default="",
        help="批3：逗号分隔的循环目录前缀（如 'f2,f3-notes-payable'），迁移这些目录下所有 .vue "
             "的金额列（含无 :formatter）。git 已修改文件自动 SKIP。",
    )
    args = ap.parse_args()

    sem = probe.load_semantics(probe.SEMANTICS_TS.read_text(encoding="utf-8"))
    if args.files:
        files = [WP_DIR / f.strip() for f in args.files.split(",") if f.strip()]
        for p in files:
            if not p.exists():
                print(f"[ERR] 文件不存在: {p}")
                return 2
        require_formatter = False
        print(f"[INFO] 批2 指定 {len(files)} 文件（处理所有金额列，含无 formatter）")
    elif args.cycle:
        # 批3：按循环目录前缀（相对 workpaper 的首段目录名）选文件。前缀精确匹配首段，
        # 不用首字母（否则顶层 Gt*.vue 首字母 g 会混入 G 循环）。
        prefixes = tuple(c.strip() for c in args.cycle.split(",") if c.strip())
        files = sorted(
            p for p in WP_DIR.rglob("*.vue")
            if "__tests__" not in p.parts
            and p.relative_to(WP_DIR).as_posix().split("/")[0] in prefixes
        )
        require_formatter = False
        print(f"[INFO] 批3 循环迁移 {len(files)} 文件（目录前缀 {prefixes}）")
    else:
        files = target_files()
        require_formatter = True
        print(f"[INFO] 批 1 目标（含 :formatter）文件 {len(files)} 个")

    tot = Counter()
    skipped_all: list[tuple[str, str, str]] = []
    modified_skipped: list[str] = []
    pending: list[tuple[Path, bytes]] = []

    for path in files:
        rel = path.relative_to(WP_DIR).as_posix()
        if _git_modified(path):
            modified_skipped.append(rel)
            print(f"  [SKIP-M] {rel}: 并发会话在改（git 已修改），跳过登记")
            continue
        res = process_file(path, sem, require_formatter)
        if res is None:
            continue
        new_bytes_src, stats, skipped = res
        tot.update(stats)
        for lab, reason in skipped:
            skipped_all.append((rel, lab, reason))
        print(
            f"  {rel}: amount→WpAmountInput={stats['amount']} "
            f"non_amount删formatter={stats['non_amount']} skip={stats['skip']}"
        )
        pending.append((path, new_bytes_src.encode("utf-8")))

    print(
        f"[INFO] 合计 amount={tot['amount']} non_amount={tot['non_amount']} "
        f"skip={tot['skip']} | M跳过文件={len(modified_skipped)}"
    )
    if skipped_all:
        print("[INFO] 跳过登记（交人工 / Task 9）：")
        for rel, lab, reason in skipped_all:
            print(f"    {rel}: label={lab!r} reason={reason}")

    if args.check:
        n = tot["amount"] + tot["non_amount"]
        if n:
            print(f"[ERR] 批 1 仍有 {n} 处 formatter 列待迁移")
            return 1
        print("[OK] 批 1 无待迁移 formatter 列")
        return 0

    if args.dry_run:
        print(f"[OK] dry-run：{len(pending)} 文件将变更，未写盘")
        return 0

    for path, data in pending:
        path.write_bytes(data)
    print(f"[OK] 已写入 {len(pending)} 个文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
