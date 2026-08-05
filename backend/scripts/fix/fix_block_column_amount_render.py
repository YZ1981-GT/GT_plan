"""给替代程序区块配置的**金额列**标注 `render: 'amount'`（七枢纽，幂等）。

spec: confirmation-orphan-and-amount-format-closure，Task 9（Requirement 2 / Property 9~12）

## 为什么需要脚本而不是手改

8 个配置文件共 **125 个 `type:'number'` 列**（32 个 `seq` + 76 金额 + 17 非金额）。
手改 76 处必漏，且漏掉的那几列在 UI 上表现为「金额不带千分符」——
`get_diagnostics` / vitest / Vite 全绿，只有肉眼逐格看才发现（G0 实测已复现一次）。

## 判据（单一真源 + 双向锁死）

- **非金额**清单来自 `blockColumnAmountRegistry.ts` 的 `NON_AMOUNT_NUMBER_COLUMNS`
  （17 条，每条带 `reason`）→ 本脚本**读它**，不自带一份关键字规则。
- 其余 `type:'number'` 且 `field !== 'seq'` 的列一律标 `render: 'amount'`。
- identity = `(file, block, field)`，**不是 field 单独** —— 同名 field 会跨区块复现
  （`transport_qty` 在 D06 的 block1/block3 各一次），按 field 建索引会静默漏标。

## 🔴 `seq` 不标注

`CheckBlock.vue` 的 `col.field === 'seq'` 分支**早于** number 分支命中 → 序号列
永远不走数值渲染分支，标了是死配置。

用法：
    python backend/scripts/fix/fix_block_column_amount_render.py            # dry-run
    python backend/scripts/fix/fix_block_column_amount_render.py --apply
    python backend/scripts/fix/fix_block_column_amount_render.py --check    # 有欠账则 exit 1
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WP = REPO_ROOT / "audit-platform/frontend/src/components/workpaper"
CONFIRM = WP / "confirmation"

REGISTRY = CONFIRM / "alternativeD05/blockColumnAmountRegistry.ts"

TARGETS = [
    CONFIRM / "alternativeD05/blockColumnConfigs.ts",
    CONFIRM / "alternativeD06/blockColumnConfigsD06.ts",
    CONFIRM / "alternativeF05/blockColumnConfigsF05.ts",
    CONFIRM / "alternativeF06/blockColumnConfigsF06.ts",
    CONFIRM / "alternativeH05/blockColumnConfigsH05.ts",
    CONFIRM / "alternativeK05/blockColumnConfigsK05.ts",
    CONFIRM / "alternativeK06/blockColumnConfigsK06.ts",
    WP / "g0-confirmation/alternativeG06/blockColumnConfigsG06.ts",
]

BLOCK_DECL = re.compile(r"^const BLOCK([1-4])_COLUMNS:\s*BlockColumnDef\[\]\s*=\s*\[")
SHARED_DECL = re.compile(r"^const VOUCHER_COLS:\s*BlockColumnDef\[\]\s*=\s*\[")
# 🔴 共享列数组：H0-5 / K0-5 / K0-6 / G0-6 把「记账凭证」5 列抽成 `VOUCHER_COLS`
#    并在四个区块里展开复用（实测各被引用 4 次）→ 它声明在 BLOCK1_COLUMNS **之前**，
#    只按 BLOCK 分区扫会把它整段漏掉（首版 dry-run 因此少 4 列：72 vs 实测 76）。
#    标注它一次即覆盖该文件四个区块，故归属键用 'shared'。
SHARED_DECL = re.compile(r"^const (VOUCHER_COLS):\s*BlockColumnDef\[\]\s*=\s*\[")
FIELD_RE = re.compile(r"field:\s*'([^']+)'")
TYPE_NUMBER_RE = re.compile(r"type:\s*'number'")
HAS_RENDER_RE = re.compile(r"render:\s*'amount'")


def load_non_amount() -> set[tuple[str, str, str]]:
    """从登记表读 17 条非金额列（file, block, field）。"""
    src = REGISTRY.read_text(encoding="utf-8")
    m = re.search(
        r"NON_AMOUNT_NUMBER_COLUMNS[^=]*=\s*Object\.freeze\(\[(.*?)\n\]\)", src, re.S
    )
    if not m:
        raise SystemExit("[FAIL] 未能在 registry 抽到 NON_AMOUNT_NUMBER_COLUMNS（正则失效即报错，不静默空转）")
    body = m.group(1)
    out: set[tuple[str, str, str]] = set()
    for entry in re.finditer(
        r"file:\s*'([^']+)'[\s\S]{0,400}?block:\s*'([^']+)'[\s\S]{0,400}?field:\s*'([^']+)'",
        body,
    ):
        out.add((entry.group(1), entry.group(2), entry.group(3)))
    if not out:
        raise SystemExit("[FAIL] 登记表解析出 0 条（判据失效，拒绝继续）")
    return out


def plan_file(path: Path, non_amount: set[tuple[str, str, str]]):
    """返回 (新内容, 变更明细, 已标注数)。逐行处理，仅在 BLOCKn_COLUMNS 数组内生效。"""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    fname = path.name
    block: str | None = None
    depth = 0
    changes: list[tuple[str, str]] = []
    already = 0

    for i, line in enumerate(lines):
        decl = BLOCK_DECL.match(line)
        if decl:
            block = f"block{decl.group(1)}"
            depth = 1
            continue
        # 🔴 共享列数组 VOUCHER_COLS（H0-5 / K0-5 / K0-6 / G0-6 各一处）：
        #    它声明在 BLOCK1_COLUMNS **之前**，被四个区块各 spread 一次（实测引用 4 次）。
        #    首版扫描只认 `BLOCKn_COLUMNS` → 这 4 个金额列（voucher_amount / amount）
        #    整个漏标（dry-run 报 72 而实测应为 76，差额即此）。
        #    标注一次即覆盖该文件四个区块，故 block 记为 'shared'；
        #    登记表用 (file,'shared',field) 表态，与 blockN 命名空间正交。
        shared = SHARED_DECL.match(line)
        if shared:
            block = "shared"
            depth = 1
            continue
        if block is None:
            continue
        # 数组结束（行首 `]`）
        if depth and re.match(r"^\]", line):
            block = None
            depth = 0
            continue
        if not TYPE_NUMBER_RE.search(line):
            continue
        fm = FIELD_RE.search(line)
        if not fm:
            continue
        field = fm.group(1)
        if field == "seq":
            continue
        if (fname, block, field) in non_amount:
            continue
        if HAS_RENDER_RE.search(line):
            already += 1
            continue
        lines[i] = TYPE_NUMBER_RE.sub("type: 'number', render: 'amount'", line, count=1)
        changes.append((block, field))

    return "".join(lines), changes, already


def main() -> int:
    apply = "--apply" in sys.argv
    check = "--check" in sys.argv
    non_amount = load_non_amount()
    print(f"[INFO] 非金额登记表：{len(non_amount)} 条")

    total_changes = 0
    total_already = 0
    for path in TARGETS:
        if not path.exists():
            print(f"[FAIL] 缺文件 {path}")
            return 2
        new_src, changes, already = plan_file(path, non_amount)
        total_changes += len(changes)
        total_already += already
        tag = "OK" if not changes else ("APPLY" if apply else "TODO")
        print(f"[{tag}] {path.name}: 待标注 {len(changes)} / 已标注 {already}")
        for block, field in changes:
            print(f"        + {block}.{field}")
        if apply and changes:
            path.write_text(new_src, encoding="utf-8")

    print(f"[SUM] 待标注 {total_changes} / 已标注 {total_already}")
    if check and total_changes:
        print("[FAIL] 仍有未标注的金额列")
        return 1
    if not apply and total_changes:
        print("（dry-run，未写盘。加 --apply 生效）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
