#!/usr/bin/env python
"""check_wp_ref_contract.py — 工作底稿组件 ref 契约守卫

背景（2026-07-11 F5+G 类 ref-unwrap 全面清扫复盘）：
  D~N 专属底稿的「子 tab 组件 ↔ composable」之间存在一类反复出现、且能穿过
  单元测试与 get_diagnostics 的**运行时崩溃/空表** bug。三件套(需求/设计/任务)
  流程未规定该契约，单测传真 ref 造成"假绿"，故补一道 author-time/CI 守卫。

拦截两类**客观**反模式（正则可判、零误报）：

  A. props ref-unwrap 崩溃
     子组件 `defineProps` 把 allResponses/wpId/projectId/htmlData/isReadonly 声明成
     `Ref<...>`，但父组件用模板绑定（`:all-responses="xxx"`）传入时会**自动解包**成纯值，
     子组件再当 ref 用 → `props.allResponses.value.get()` 对纯值取 `.value`=undefined → 崩。
     正确：props 声明为**解包类型**（Map/string/boolean），再 `toRef(props,'x')` 重新包 ref。

  B. 对 prop 直接取 .value
     `props.allResponses.value` / `props.wpId.value` 等 —— 与 A 同源的运行时症状。

第三类「嵌套 ref 不解包」(模板 `x.rows` 无 .value 且未解构) 需模板 AST 解析，
误报率高，本脚本不自动拦截，仅在 steering 文档说明；靠 Playwright 逐 tab 兜底。

用法：
  python backend/scripts/check/check_wp_ref_contract.py            # 报告模式（退出码始终 0）
  python backend/scripts/check/check_wp_ref_contract.py --strict   # 严格模式（有违规退出码 1）

设计为零依赖（仅标准库），可在 CI 与 pre-commit 直接运行。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ─── 扫描范围 ────────────────────────────────────────────────────────────────
# 相对仓库根定位前端 workpaper 组件目录
REPO_ROOT = Path(__file__).resolve().parents[3]
WP_DIR = REPO_ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"

# 受契约约束的 prop 名（父组件均以模板绑定传解包值）
GUARDED_PROPS = ("allResponses", "wpId", "projectId", "htmlData", "isReadonly")

# ─── 反模式 A：defineProps 中把受约束 prop 声明成 Ref<...> ────────────────────
# 命中形如：  allResponses: Ref<Map<...>>   /   wpId: Ref<string>
_RE_PROP_AS_REF = re.compile(
    r"\b(" + "|".join(GUARDED_PROPS) + r")\s*:\s*Ref\s*<"
)

# ─── 反模式 B：对受约束 prop 直接取 .value ───────────────────────────────────
# 命中形如：  props.allResponses.value   /   props.wpId.value
_RE_PROP_DOT_VALUE = re.compile(
    r"\bprops\.(" + "|".join(GUARDED_PROPS) + r")\.value\b"
)


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """返回 [(行号, 类别, 行内容)] 违规列表。"""
    violations: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return violations
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        # 跳过注释行，减少误报
        if stripped.startswith("//") or stripped.startswith("*"):
            continue
        # 反模式 A：仅 defineProps 里的属性声明才算；排除局部变量 `const x: Ref<..> = ref()`
        if _RE_PROP_AS_REF.search(line) and not _is_local_ref_decl(line):
            violations.append((lineno, "A(props 声明 Ref)", stripped))
        # 反模式 B：排除 `typeof props.x === 'string' ? ... : props.x.value` 防御式兼容写法
        if _RE_PROP_DOT_VALUE.search(line) and "typeof props." not in line:
            violations.append((lineno, "B(prop 取 .value)", stripped))
    return violations


def _is_local_ref_decl(line: str) -> bool:
    """判断是否为局部变量的 Ref 类型声明（非 defineProps 属性），避免误报。

    如 `const allResponses: Ref<Map<string, any>> = ref(new Map())`。
    defineProps 里的属性声明形如 `allResponses: Ref<Map<...>>`，无 const/let/=。
    """
    return bool(re.search(r"\b(const|let|var)\b", line)) or "= ref(" in line or "=ref(" in line


def main() -> int:
    parser = argparse.ArgumentParser(description="工作底稿组件 ref 契约守卫")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="严格模式：检测到违规时退出码 1（用于 CI 强制期 / pre-commit）",
    )
    args = parser.parse_args()

    # Windows 控制台默认 GBK，输出中文/emoji 会抛 UnicodeEncodeError；强制 utf-8。
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    if not WP_DIR.is_dir():
        print(f"::warning::未找到 workpaper 目录 {WP_DIR}，跳过检查")
        return 0

    total_violations = 0
    files_with_violations = 0
    for vue in sorted(WP_DIR.rglob("*.vue")):
        v = scan_file(vue)
        if not v:
            continue
        files_with_violations += 1
        rel = vue.relative_to(REPO_ROOT).as_posix()
        for lineno, kind, content in v:
            total_violations += 1
            print(f"{rel}:{lineno}  [{kind}]  {content}")

    if total_violations:
        print(
            f"\n检测到违规：{total_violations} 处，涉及 {files_with_violations} 个文件。\n"
            "修复：props 改解包类型（Map/string/boolean），再 "
            "`const xRef = toRef(props, 'x') as Ref<...>` 喂 composable；"
            "把 `props.x.value` 改为 `xRef.value`。参考 "
            "f5-cost-of-sales/F5TabAdjudication.vue 与 "
            "g1-trading-financial-assets/core/G1TabDetail.vue。"
        )
        if args.strict:
            return 1
        print("（报告模式：未阻断。CI 强制期后 --strict 将 fail）")
        return 0

    print("✅ 工作底稿组件 ref 契约检查通过：无 props ref-unwrap / prop.value 反模式")
    return 0


if __name__ == "__main__":
    sys.exit(main())
