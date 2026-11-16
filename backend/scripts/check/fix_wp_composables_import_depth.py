#!/usr/bin/env python
"""fix_wp_composables_import_depth.py — 修复 workpaper 组件对 composables 的相对导入层级。

背景（2026-07-11 K 类底稿 Playwright 实测）：
  多个 `{cycle}/{sub}/*.vue` 底稿 tab 用 `../../../composables/`（3 级 → 解析到不存在的
  `src/components/composables/`），Vite transform 报 500「Failed to resolve import」→
  ErrorBoundary 崩溃。正确应为 `../../composables/`（2 级 → `workpaper/composables/`）。
  vitest/Volar 解析方式不同故未拦截，但浏览器运行时必崩。

🔴 2026-11-14 修正（原判据把正确代码判成错的、--apply 会改坏代码）：

原实现把「正确前缀」硬算成 `('../' * 到 workpaper 根的深度) + 'composables/'`，
**只认根级 `workpaper/composables/`**。但 workpaper 下实测有 **25 个** composables
目录（根级 + `d4/` `b60/` `cnote/` `GtDForm/` `confirmation/*/` 等 24 个二级）。
于是所有指向二级目录的、**本来就正确**的 import 全被判成「层级错误」，`--apply`
会把它们改到不存在的 `workpaper/composables/xxx` —— Vite 直接
"Failed to resolve import"，比它声称要修的 3 级错误更糟（实测 `D4TabDiscount.vue`
从 `../composables/useD4SyncMode`（正确，解析到 `d4/composables/`）改成
`../../composables/useD4SyncMode`（不存在））。

**现判据 = 目标是否真实存在**，不再按深度公式：
  - 对每处 `(../)+composables/<name>`，按当前前缀解析到磁盘路径
  - 解析得到真实文件 ⇒ 正确，不动（无论几级 `../`）
  - 解析不到 ⇒ 才去找 `<name>` 的真实归属 composables 目录，算出正确前缀并修
  - 连归属目录都找不到 ⇒ 只报告，不猜（`[WARN] … 不改`）

安全：以 UTF-8 显式读写，仅替换 ASCII 子串（`../` 与 `composables/`），不触碰中文。
用法：
  python backend/scripts/check/fix_wp_composables_import_depth.py            # dry-run 仅报告（退出码 0）
  python backend/scripts/check/fix_wp_composables_import_depth.py --apply    # 实际写回
  python backend/scripts/check/fix_wp_composables_import_depth.py --check    # CI 守卫：有错退出码 1
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WP_DIR = REPO_ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
COMPOSABLES_DIR = WP_DIR / "composables"

#: workpaper 下**全部** composables 目录（根级 + 各二级），现算而非硬编码清单 ——
#: 新增 `xxx/composables/` 时判据自动跟上，不会又把正确 import 判成错的。
COMPOSABLES_DIRS: tuple[Path, ...] = tuple(
    sorted({d.resolve() for d in WP_DIR.rglob("composables") if d.is_dir()})
)

# 命中 import ... from '<...>/composables/<name>' 中的相对前缀与名字
_RE_IMPORT = re.compile(r"(from\s*['\"])((?:\.\./)+)composables/([\w\.\-]+)")


def _resolves(base: Path, prefix: str, name: str) -> bool:
    """`prefix + composables/<name>` 从 `base` 出发是否解析到真实文件/目录。"""
    target = (base / f"{prefix}composables" / name)
    return any(
        p.exists()
        for p in (target, target.with_suffix(".ts"), target.with_suffix(".vue"), target / "index.ts")
    )


def _owner_prefix(vue_dir: Path, name: str) -> str | None:
    """`composables/<name>` 的真实归属目录 -> 从 `vue_dir` 出发、**到该 composables 目录**的
    相对前缀（调用方会再拼 `composables/<name>`，故这里只给到目录本身，例如 `../../d4/`）。
    找不到返回 None。"""
    hits = [
        d
        for d in COMPOSABLES_DIRS
        if any(
            p.exists()
            for p in (d / name, d / f"{name}.ts", d / f"{name}.vue", d / name / "index.ts")
        )
    ]
    if not hits:
        return None
    owner = min(hits, key=lambda d: len(d.parts))  # 多处同名取最外层
    import os

    rel = os.path.relpath(owner, vue_dir.resolve()).replace(os.sep, "/")
    if rel == ".":
        return "./"
    return rel + "/"


def main() -> int:
    apply = "--apply" in sys.argv
    check = "--check" in sys.argv
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    if not COMPOSABLES_DIR.is_dir():
        print(f"::error::composables 目录不存在 {COMPOSABLES_DIR}")
        return 1

    changed_files = 0
    total_repls = 0
    unresolved = 0
    for vue in sorted(WP_DIR.rglob("*.vue")):
        # composables 目录自身跳过
        if any(cd == vue.parent.resolve() or cd in {p.resolve() for p in vue.parents} for cd in COMPOSABLES_DIRS):
            continue
        text = vue.read_text(encoding="utf-8")
        vue_dir = vue.parent
        new_text = text
        fixes = 0
        for m in _RE_IMPORT.finditer(text):
            old_prefix, name = m.group(2), m.group(3)
            if _resolves(vue_dir, old_prefix, name):
                continue  # 已能解析到真实文件 ⇒ 正确，不动
            want = _owner_prefix(vue_dir, name)
            if want is None or want == old_prefix:
                unresolved += 1
                continue
            # `want` 已指向那个 composables 目录本身，故只补 `<name>`
            pat = re.compile(
                rf"(from\s*['\"]){re.escape(old_prefix)}composables/{re.escape(name)}(?=['\"/]|$)"
            )
            newer = pat.sub(lambda mm: f"{mm.group(1)}{want}{name}", new_text)
            if newer != new_text:
                new_text = newer
                fixes += 1
        if fixes == 0 or new_text == text:
            continue
        rel = vue.relative_to(REPO_ROOT).as_posix()
        print(f"{'FIX ' if apply else 'DRY '} {rel}  ({fixes} 处)")
        changed_files += 1
        total_repls += fixes
        if apply:
            vue.write_text(new_text, encoding="utf-8")

    if unresolved:
        print(f"[WARN] {unresolved} 处 import 解析不到归属 composables 目录，按规矩不改（不猜测）")

    if total_repls == 0:
        print("✅ workpaper composables 相对导入层级检查通过：无错误 ../ 深度")
        return 0

    print(
        f"\n{'已修复' if apply else '发现'}：{total_repls} 处，涉及 {changed_files} 个文件。"
        + ("" if apply else "  （dry-run，加 --apply 写回；--check 用于 CI 阻断）")
    )
    if check:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
