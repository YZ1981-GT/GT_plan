#!/usr/bin/env python
"""给 `useXFormData.saveBatch(items)` 加入按 `item_id` 去重（幂等）。

## 为什么

后端批量 PUT 校验「同一批次不得重复提交相同 item_id」。一旦调用方在一次
`saveBatch([...])` 里对同一 `itemId` 传了两条（联动回写常见：先写整表 JSON、
再写其中某个汇总字段），**整批被拒 → 该批全部数据丢失**（不是只丢那一条）。
D2 曾实测踩中并单独修过；本脚本把同样的防护铺到形状一致的 legacy 实现上。

## 处理

对签名为 ``saveBatch(items: Array<{ itemId: string; data: Partial<ChecklistResponse> }>)``
且函数体以 ``const toSave: ChecklistResponse[] = []`` 起头的实现，在循环前插入
按 `itemId` 去重（**后写覆盖先写**，与用户最后一次输入语义一致）：

```ts
// 同一批次不得重复提交相同 item_id（后端会整批拒绝 → 全批数据丢失）；
// 同 itemId 多次传入时后写覆盖先写。
const deduped = [...new Map(items.map((it) => [it.itemId, it])).values()]
```

并把循环源从 `items` 换成 `deduped`。**不改**其它形状的 `saveBatch`
（`ChecklistResponse[]` / `{itemId, value}` 等）—— 它们语义不同，需单独评估。

Usage::

    python backend/scripts/fix/fix_save_batch_dedup.py --dry-run
    python backend/scripts/fix/fix_save_batch_dedup.py
    python backend/scripts/fix/fix_save_batch_dedup.py --check

spec: .kiro/specs/disclosure-note-follow-actual-content/（复盘遗留项）
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
FRONTEND_SRC = _BACKEND.parent / "audit-platform" / "frontend" / "src"

MARKER = "const deduped = [...new Map(items.map("

# saveBatch(items: Array<{ itemId: string; data: Partial<ChecklistResponse> }>) ... {
#   const toSave: ChecklistResponse[] = []
#   for (const { itemId, data } of items) {
_TARGET_RE = re.compile(
    r"(?P<head>async function saveBatch\(\s*\n?\s*items: Array<\{ itemId: string; data: Partial<ChecklistResponse> \}>,?"
    r"[^{]*\{\s*\r?\n)"
    r"(?P<body>(?:[ \t]*//[^\n]*\r?\n|[ \t]*\r?\n)*)"
    r"(?P<decl>[ \t]*const toSave: ChecklistResponse\[\] = \[\][ \t]*\r?\n)"
    r"(?P<loop>[ \t]*for \(const \{ itemId, data \} of )items(?P<tail>\)[ \t]*\{)",
    re.M,
)

_DEDUP_TPL = (
    "{indent}// 🔴 同一批次不得重复提交相同 item_id：后端会**整批拒绝** → 该批全部数据丢失\n"
    "{indent}//    （联动回写常见：先写整表 JSON、再写其中某个汇总字段）。\n"
    "{indent}//    同 itemId 多次传入时后写覆盖先写，与「用户最后一次输入」语义一致。\n"
    "{indent}const deduped = [...new Map(items.map((it) => [it.itemId, it])).values()]\n"
)


def _process(path: Path, *, dry_run: bool, check_only: bool) -> tuple[bool, list[str]]:
    src = io.open(path, encoding="utf-8", newline="").read()
    if "async function saveBatch(" not in src:
        return True, []
    m = _TARGET_RE.search(src)
    if not m:
        return True, []
    rel = path.relative_to(FRONTEND_SRC).as_posix()
    if MARKER in src:
        return True, []
    if check_only:
        return False, [f"[FAIL] {rel} 的 saveBatch 未按 item_id 去重"]

    indent = re.match(r"[ \t]*", m.group("decl")).group(0)
    replacement = (
        m.group("head")
        + m.group("body")
        + _DEDUP_TPL.format(indent=indent)
        + m.group("decl")
        + m.group("loop")
        + "deduped"
        + m.group("tail")
    )
    out = src[: m.start()] + replacement + src[m.end():]
    if not dry_run:
        io.open(path, "w", encoding="utf-8", newline="").write(out)
    return True, [f"{'[dry-run] ' if dry_run else ''}{rel}: saveBatch 已加 item_id 去重"]


def main() -> int:
    ap = argparse.ArgumentParser(description="saveBatch 按 item_id 去重（幂等）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true", help="仅校验（供 CI）")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

    if not FRONTEND_SRC.is_dir():
        print(f"[FATAL] 找不到 {FRONTEND_SRC}")
        return 2

    ok_all, logs = True, []
    for path in sorted(FRONTEND_SRC.rglob("use*FormData.ts")):
        ok, log = _process(path, dry_run=args.dry_run, check_only=args.check)
        ok_all = ok_all and ok
        logs += log
    print("\n".join(logs) or "无需修改")
    if not ok_all:
        print("\n[FAIL] 存在未去重的 saveBatch，请跑 python backend/scripts/fix/fix_save_batch_dedup.py")
        return 1
    print("[OK] 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
