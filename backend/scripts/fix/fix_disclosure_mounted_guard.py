#!/usr/bin/env python
"""移除披露 Tab 里的 `_xxxMounted` 一次性防护（幂等）。

## 为什么是 bug（2026-07-30 浏览器实测）

各披露 Tab 曾用下面这段"跳过挂载时那一次 watch"的防护：

```ts
let _xxxMounted = false
watch([...], () => {
  if (!_xxxMounted) { _xxxMounted = true; return }
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}, { deep: true })
```

它的**消耗时机取决于「数据是否已加载」**：

- **首次挂载**：`allResponses` 异步填充 → computed 变化 → watch 触发一次 → 防护被消耗（符合设计意图）；
- **切走再切回**：数据已在内存里 → computed 不变 → watch 不触发 → **防护没被消耗**
  → 吞掉用户回到本页后的**第一次真实编辑**。

实测症状：`checklist_responses` 已写入，但 `disclosure_notes._last_sync_at` 不变；
在同一次挂载内再改一次才会同步。

Vue `watch` 默认 `immediate: false`，**挂载本身不会触发**，所以这个防护从一开始就不必要；
数据加载引起的那一次同步反而是有益的（幂等 + 空载荷 no-op，后端 `sync_from_workpaper`
对空 `sub_table_data` 明确不清空既有子表）。

## 处理

删除 `if (!_xxxMounted) { _xxxMounted = true; return }` 与配套的 `let _xxxMounted = false`。
守卫：`__tests__/disclosureAutoSyncCoverage.spec.ts`（禁止再出现该形态）。

Usage::

    python backend/scripts/fix/fix_disclosure_mounted_guard.py --dry-run
    python backend/scripts/fix/fix_disclosure_mounted_guard.py
    python backend/scripts/fix/fix_disclosure_mounted_guard.py --check

spec: .kiro/specs/disclosure-note-follow-actual-content/ Task 4.8
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent.parent
WP_ROOT = (
    _BACKEND.parent / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
)

# `if (!_xxxMounted) { _xxxMounted = true; return }`（允许行首缩进与行尾空白）
_GUARD_RE = re.compile(
    r"^[ \t]*if \(!(?P<flag>_\w*Mounted)\)\s*\{\s*\1\s*=\s*true;?\s*return\s*\}[ \t]*\r?\n",
    re.M,
)
# `let _xxxMounted = false`（可带分号）
_DECL_RE = re.compile(r"^[ \t]*let (?P<flag>_\w*Mounted)\s*=\s*false;?[ \t]*\r?\n", re.M)


def _process(path: Path, *, dry_run: bool, check_only: bool) -> tuple[bool, list[str]]:
    src = io.open(path, encoding="utf-8", newline="").read()
    guards = _GUARD_RE.findall(src)
    decls = _DECL_RE.findall(src)
    if not guards and not decls:
        return True, []

    rel = path.relative_to(WP_ROOT).as_posix()
    if check_only:
        return False, [f"[FAIL] {rel} 仍有一次性防护（guard={len(guards)} decl={len(decls)}）"]

    out = _GUARD_RE.sub("", src)
    # 只删掉声明确实不再被引用的 flag（防误删他用同名变量）
    for flag in set(decls):
        if not re.search(rf"\b{re.escape(flag)}\b", _DECL_RE.sub("", out)):
            out = re.sub(
                rf"^[ \t]*let {re.escape(flag)}\s*=\s*false;?[ \t]*\r?\n", "", out, flags=re.M
            )
    if out == src:
        return True, []
    if not dry_run:
        io.open(path, "w", encoding="utf-8", newline="").write(out)
    tag = "[dry-run] " if dry_run else ""
    return True, [f"{tag}{rel}: 删除防护 {len(guards)} 处 / 声明 {len(set(decls))} 个"]


def main() -> int:
    ap = argparse.ArgumentParser(description="移除披露 Tab 的 _xxxMounted 一次性防护（幂等）")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check", action="store_true", help="仅校验（供 CI）")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

    if not WP_ROOT.is_dir():
        print(f"[FATAL] 找不到 {WP_ROOT}")
        return 2

    ok_all = True
    logs: list[str] = []
    for path in sorted(WP_ROOT.rglob("*.vue")):
        ok, log = _process(path, dry_run=args.dry_run, check_only=args.check)
        ok_all = ok_all and ok
        logs += log

    print("\n".join(logs) or "无需修改")
    if not ok_all:
        print(
            "\n[FAIL] 存在残留：`_xxxMounted` 一次性防护会吞掉「切走再切回后的第一次编辑」，"
            "请跑 `python backend/scripts/fix/fix_disclosure_mounted_guard.py` 清除"
        )
        return 1
    print("[OK] 全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
