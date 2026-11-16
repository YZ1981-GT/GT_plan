#!/usr/bin/env python
"""check_wp_version_trail.py — 版本链集成守卫

确保 D~N 循环全部底稿主入口组件已接入版本链（useWorkpaperVersionToolbar +
GtWpVersionTrail），防止新增底稿遗漏集成。

检测**任一**合规接入形态（三种，实测三种都存在过）：

  A. **共享 runtime 注入（当前主流，88/88 全用这个）**
     组件 `inject(WorkpaperRuntimeContextKey)` 后取 `runtime?.version.*`。
     版本能力由 `useWorkpaperScaffold()` 一处 `useWorkpaperVersionToolbar({...})`
     创建、`provide(WorkpaperRuntimeContextKey, runtime)` 下发
     （见 useWorkpaperScaffold.ts L88 `version: ReturnType<typeof ...>` /
     L186 真实调用 / L262 provide）。这是更优的架构：一处创建、多处复用，
     不会给 N 个组件各建一份 composable 实例。

  B. 直接调用 `useWorkpaperVersionToolbar(...)`

  C. template 中挂载 `<GtWpVersionTrail />`

\U0001f534 2026-11-14 判据修正：原实现只认 B / C 两种**字面量标记**，把 A 这一
主流形态判成「未接入」—— 于是 88 个 D~N 主入口全部报违规、`--strict` 从引入起
就恒红（governance-checks.yml 的注释还写着「当前全树已接入，直接 strict 阻断新增
违规」，与实际严重不符）。现改为三种形态任一即合规，并保留「完全无标记」的真判据。

用法：
  python backend/scripts/check/check_wp_version_trail.py            # 报告模式（退出码 0）
  python backend/scripts/check/check_wp_version_trail.py --strict   # CI 严格模式（有违规退出码 1）

设计为零依赖（仅标准库），可在 CI 与 pre-commit 直接运行。
参照 check_wp_ref_contract.py 风格。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ─── Windows GBK 安全 ────────────────────────────────────────────────────────
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except (AttributeError, ValueError):
    pass

# ─── 路径定位 ─────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[3]
WP_DIR = REPO_ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
WHITELIST_PATH = Path(__file__).resolve().parent / "version_trail_whitelist.txt"

# ─── 主入口识别正则 ──────────────────────────────────────────────────────────
# 匹配 Gt{D-N}{Digit(s)}*.vue（直接子文件，非子目录）
# 例：GtD3PrepaidAccounts.vue, GtE1CashAndBank.vue, GtG14xxx.vue
_RE_MAIN_ENTRY = re.compile(r"^Gt[D-N]\d+.*\.vue$")

# ─── 必备标记 ─────────────────────────────────────────────────────────────────
MARKER_COMPOSABLE = "useWorkpaperVersionToolbar"
MARKER_COMPONENT = "GtWpVersionTrail"
#: 共享 runtime 注入形态（当前主流）：组件 inject 上下文后取 `version.*`。
#: 两段都要出现才算 —— 只 inject 上下文但没取 version 能力的不算接入。
MARKER_RUNTIME_CONTEXT = "WorkpaperRuntimeContextKey"
MARKER_RUNTIME_VERSION = "version"


def load_whitelist(path: Path) -> set[str]:
    """加载白名单文件，返回豁免文件名集合。

    格式：每行一个文件名，# 开头为注释，空行跳过。
    文件不存在视为空白名单。
    """
    if not path.is_file():
        return set()
    whitelist: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        whitelist.add(stripped)
    return whitelist


def scan_file(path: Path) -> tuple[bool, bool]:
    """检测文件是否含两个必备标记。

    Returns:
        (has_composable, has_component)
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        # 读取失败视为无标记，由调用方决定如何处理
        return (False, False)
    has_composable = MARKER_COMPOSABLE in content
    has_component = MARKER_COMPONENT in content
    return (has_composable, has_component)


def has_runtime_inject(path: Path) -> bool:
    """共享 runtime 注入形态：`inject(WorkpaperRuntimeContextKey)` 且取过 `version.*`。

    \U0001f534 两段都必须现读命中：只 import Key 但没取 version 能力（例如只用了
    review / reload）不算接入 —— 那是本判据最容易退化成恒真的地方。
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return False
    if MARKER_RUNTIME_CONTEXT not in content:
        return False
    return bool(re.search(r"runtime\??\.version\b|\.version\.versionTrailRef\b", content))


def find_main_entries(wp_dir: Path) -> list[Path]:
    """扫描 workpaper/ 直接子文件，识别 D~N 循环主入口组件。"""
    entries: list[Path] = []
    if not wp_dir.is_dir():
        return entries
    for item in sorted(wp_dir.iterdir()):
        if item.is_file() and _RE_MAIN_ENTRY.match(item.name):
            entries.append(item)
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(
        description="版本链集成守卫：检测 D~N 循环主入口是否已接入 version trail"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="严格模式：检测到违规时退出码 1（用于 CI）",
    )
    args = parser.parse_args()

    if not WP_DIR.is_dir():
        print(f"::warning::未找到 workpaper 目录 {WP_DIR}，跳过检查")
        return 0

    whitelist = load_whitelist(WHITELIST_PATH)
    entries = find_main_entries(WP_DIR)

    if not entries:
        print("::warning::未找到任何 D~N 主入口组件，跳过检查")
        return 0

    violations: list[tuple[str, str]] = []  # (filename, missing_description)
    compliant = 0
    whitelisted_count = 0

    for entry in entries:
        fname = entry.name
        if fname in whitelist:
            whitelisted_count += 1
            continue

        has_composable, has_component = scan_file(entry)
        # 形态 A：共享 runtime 注入（当前主流，88/88 用这个）
        runtime_ok = has_runtime_inject(entry)

        if (has_composable and has_component) or (runtime_ok and has_component) or runtime_ok:
            compliant += 1
            continue

        # 构建缺失描述
        missing: list[str] = []
        if not has_composable:
            missing.append(MARKER_COMPOSABLE)
        if not has_component:
            missing.append(MARKER_COMPONENT)
        violations.append((fname, " + ".join(missing)))

    # ─── 输出结果 ─────────────────────────────────────────────────────────
    total = len(entries)
    print(f"扫描 D~N 主入口组件：{total} 个")
    print(f"  已接入：{compliant} 个")
    print(f"  白名单豁免：{whitelisted_count} 个")
    print(f"  违规：{len(violations)} 个")
    print()

    if violations:
        print("未接入版本链的组件：")
        for fname, missing_desc in violations:
            rel = f"audit-platform/frontend/src/components/workpaper/{fname}"
            print(f"  {rel}  [缺少 {missing_desc}]")
        print()
        print(
            "修复（推荐形态 A：共享 runtime 注入）：\n"
            "  1. import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'\n"
            "  2. const runtime = inject(WorkpaperRuntimeContextKey, null)\n"
            "  3. const versionTrailRef = runtime?.version.versionTrailRef ?? ref(null)\n"
            "     const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)\n"
            "     const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)\n"
            "  4. 保存成功后调 scheduleAutoSnapshot()\n"
            "  5. template 挂 <GtWpVersionTrail :workpaper-id :project-id />\n"
            "  6. provide('<cycle>VersionTrailRef', versionTrailRef) 给子对话框用\n"
            "版本能力由 useWorkpaperScaffold() 一处创建并 provide，不要在组件里重复 new。"
        )

        if args.strict:
            print(f"\n::error::版本链集成守卫失败：{len(violations)} 个组件未接入")
            return 1
        print("\n（报告模式：未阻断。--strict 将 fail）")
        return 0

    print("[OK] 版本链集成守卫通过：所有 D~N 主入口已接入 version trail")
    return 0


if __name__ == "__main__":
    sys.exit(main())
