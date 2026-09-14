"""从 ACNR catalog 生成前端 registry — workpaper-import-export-lifecycle-closure Task 13

## 为什么必须生成而不是手写

前端 `CYCLE_IMPORT_EXPORT` 改造前只手写了 **10 个 key**，而 catalog 有 **59 个**
启用 I/E 的 api_prefix ⇒ 49 个前缀的能力后端有、用户点不到。

手写补齐 49 条不是办法：catalog 是 `bulk_tab` 全链的路由真源
（`manifest_builder` → `list_export_sheets` → `list_import_export` → `catalog.list_sheets`），
前端若手抄一份，等于平台内并存两套 I/E 目录，改一处忘一处。

## 🔴 为什么不能只从 catalog 生成（R4.6 零回归的关键）

既有 10 个 key 里含 **catalog 表达不了的传输层键**：

| 类型 | 例 | catalog 有吗 |
|---|---|---|
| G0/H0 函证传输键 | `G0-3S` | ❌ 它是 `_SHEET_NAME_MAP` 的**键**，不是 `sheet_code` |
| F3/F4 复合变体键 | `F3-7-debit` / `F4-8-credit` | ❌ 存在于**后端 specs**，catalog 只登记基础 `sheet_code` |

实测 catalog 的 `f3` 只有 5 个 sheet（`F3-2`~`F3-6`），而后端 specs 有 16 个键；
`f4` catalog 4 个 vs 后端 24 个。**纯 catalog 生成会丢掉这些变体键，
导致既有导入导出下拉直接少掉一半区段**。

⇒ 架构定为 **generated（catalog 派生）+ MANUAL_OVERRIDES（既有 10 key 逐字保留）**，
门面里 overrides 后置覆盖。既满足 R4.1 覆盖面，又满足 R4.6 零回归。

## 用法

    python backend/scripts/fix/gen_cycle_import_export_registry.py --check
    python backend/scripts/fix/gen_cycle_import_export_registry.py --apply
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_REPO = _BACKEND.parent
_TARGET = (
    _REPO
    / "audit-platform/frontend/src/components/workpaper/shared"
    / "cycleImportExportRegistry.generated.ts"
)

#: 由 `MANUAL_OVERRIDES` 接管的前缀 —— 生成文件里**排除**它们，避免两处都有。
#: 与前端 `cycleImportExportRegistry.ts` 的 `MANUAL_OVERRIDES` 键集必须一致，
#: 守卫 `cycleImportExportRegistry.spec.ts` 双向锁死。
MANUAL_PREFIXES: frozenset[str] = frozenset({
    "f1", "f2", "f2-val", "f2-spe", "f2-st", "f3", "f4", "f5", "g0", "h0",
})

_HEADER = """/**
 * 🔴 本文件由脚本生成，请勿手工编辑。
 *
 * 生成器：`backend/scripts/fix/gen_cycle_import_export_registry.py`
 * 真源  ：ACNR catalog（`backend/data/acnr/global_catalog.json`）的
 *         `sheets[].import_export` 段 —— 也是 `bulk_tab` 全链的路由真源。
 *
 * ## 这里为什么不含 f1 / f2 系列 / f3 / f4 / f5 / g0 / h0
 *
 * 🔴 注意：本段文字不得出现 `f2` 后紧跟星号加斜杠的写法 —— 那会提前闭合
 * 块注释，导致生成文件语法错误（本生成器初版即踩此坑，esbuild 报
 * `Unexpected "*"`）。
 *
 * 那 10 个前缀由 `cycleImportExportRegistry.ts` 的 `MANUAL_OVERRIDES` 接管，
 * 因为它们的 `sheets[]` 含 **catalog 表达不了的传输层键**：
 *   · `G0-3S` 是后端 `_SHEET_NAME_MAP` 的键，不是 `sheet_code`
 *   · `F3-7-debit` / `F4-8-credit` 等复合变体键存在于后端 specs，catalog 只登记基础码
 * 纯 catalog 生成会丢掉它们（实测 f3 catalog 5 键 vs 后端 16 键）⇒ 下拉少掉一半区段。
 *
 * 重新生成：
 *   python backend/scripts/fix/gen_cycle_import_export_registry.py --apply
 */
import type { CycleImportExportEntry } from './cycleImportExportRegistry'

/** 从 ACNR catalog 派生的 I/E 条目（不含 MANUAL_OVERRIDES 接管的前缀） */
export const GENERATED_IMPORT_EXPORT: Record<string, CycleImportExportEntry> = {
"""

_FOOTER = """}

/** 生成时的 catalog 前缀总数（含 MANUAL 接管的），供守卫核对覆盖面 */
export const CATALOG_PREFIX_TOTAL = %d

/** 本文件登记的前缀数 */
export const GENERATED_PREFIX_COUNT = %d
"""


def collect_from_catalog() -> tuple[dict[str, list[str]], int]:
    """返回 `(prefix → sorted sheet_codes, catalog 前缀总数)`。"""
    from app.services.acnr.catalog import list_sheets

    by_prefix: dict[str, set[str]] = {}
    for s in list_sheets(import_export_only=True):
        ie = s.get("import_export") or {}
        if not ie.get("enabled"):
            continue
        prefix = ie.get("api_prefix")
        code = s.get("sheet_code")
        if not prefix or not code:
            continue
        by_prefix.setdefault(prefix, set()).add(code)

    total = len(by_prefix)
    kept = {
        p: sorted(codes)
        for p, codes in by_prefix.items()
        if p not in MANUAL_PREFIXES
    }
    return dict(sorted(kept.items())), total


def render(entries: dict[str, list[str]], catalog_total: int) -> str:
    lines: list[str] = [_HEADER]
    for prefix, codes in entries.items():
        key = prefix if prefix.replace("-", "").isalnum() and "-" not in prefix else f"'{prefix}'"
        sheets = ", ".join(f"'{c}'" for c in codes)
        lines.append(f"  {key}: {{ apiPrefix: '{prefix}', sheets: [{sheets}] }},\n")
    lines.append(_FOOTER % (catalog_total, len(entries)))
    return "".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="磁盘内容与应生成内容不一致则 exit 2")
    g.add_argument("--apply", action="store_true", help="写盘")
    args = ap.parse_args()

    entries, catalog_total = collect_from_catalog()

    if not entries:
        print("[FAIL] catalog 未产出任何条目 —— 拒绝写空文件")
        return 2
    if catalog_total < 50:
        print(f"[FAIL] catalog 前缀总数异常少（{catalog_total}）—— 疑似 catalog 未加载")
        return 2

    content = render(entries, catalog_total)

    if args.check:
        if not _TARGET.is_file():
            print(f"[FAIL] 生成文件不存在: {_TARGET}")
            return 2
        on_disk = _TARGET.read_text(encoding="utf-8")
        if on_disk != content:
            print("[FAIL] 生成文件与 catalog 不一致，请重跑 --apply")
            print(f"       磁盘 {len(on_disk)} 字符 / 应为 {len(content)} 字符")
            return 2
        print(f"[OK] 一致（{len(entries)} 个前缀 / catalog 共 {catalog_total} 个）")
        return 0

    before = (
        hashlib.md5(_TARGET.read_bytes()).hexdigest()[:8] if _TARGET.is_file() else "—"
    )
    _TARGET.parent.mkdir(parents=True, exist_ok=True)
    _TARGET.write_text(content, encoding="utf-8")  # 🔴 显式 utf-8
    after = hashlib.md5(_TARGET.read_bytes()).hexdigest()[:8]

    print(f"[APPLIED] {_TARGET.relative_to(_REPO)}")
    print(f"          前缀 {len(entries)} 个（catalog 共 {catalog_total} 个）")
    print(f"          md5 {before} → {after}")
    print(f"          MANUAL 接管: {sorted(MANUAL_PREFIXES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
