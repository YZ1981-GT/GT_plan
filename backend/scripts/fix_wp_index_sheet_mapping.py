"""让专属组件 currentSheet 把「底稿目录」sheet 映射到其索引页编码。

背景：render-config 之前隐藏「底稿目录」sheet（whole-wp dedicated），现已放开。
但部分科目专属组件（H1~H8/I1~I6/K1~K13 等）的 currentSheet 只用「裸编码（无后缀）」
匹配目录页（`/\\bH1\\b/` 对 "底稿目录" 不命中 → 返回 '' → 目录页签空白）。
本脚本把这些组件的裸编码分支改为「同时接受『底稿目录』命名」，与 J1/K10/I4 等已正确
映射的组件对齐，消除空白目录页签。

幂等：已在更早分支 return 目录的组件（earlier `/底稿目录/` 命中先返回），本改动为死代码无害。
仅改匹配条件，不动其它逻辑。UTF-8 显式读写，不碰中文。

用法：
  python scripts/fix_wp_index_sheet_mapping.py          # 预览
  python scripts/fix_wp_index_sheet_mapping.py --apply  # 写回
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_FE = Path(__file__).resolve().parent.parent.parent / "audit-platform" / "frontend" / "src" / "components" / "workpaper"

# 匹配裸编码目录分支：
#   if (/\bH1\b/.test(name) && !/H1-/.test(name) && !/H1A/.test(name)) return 'H1'
_PAT = re.compile(
    r"if \(/\\b([A-Z]\d+)\\b/\.test\(name\) && !/\1-/\.test\(name\) && !/\1A/\.test\(name\)\) return '\1'"
)


def _repl(m: re.Match) -> str:
    code = m.group(1)
    return (
        f"if (/底稿目录/.test(name) || (/\\b{code}\\b/.test(name) "
        f"&& !/{code}-/.test(name) && !/{code}A/.test(name))) return '{code}'"
    )


def main() -> None:
    apply = "--apply" in sys.argv
    changed = []
    for vue in sorted(_FE.glob("Gt*.vue")):
        text = vue.read_text(encoding="utf-8")
        new, n = _PAT.subn(_repl, text)
        if n > 0 and new != text:
            changed.append((vue.name, n))
            if apply:
                vue.write_text(new, encoding="utf-8")
    for name, n in changed:
        print(f"  {'[FIXED]' if apply else '[WOULD]'} {name} ({n})")
    print(f"\n{'已修改' if apply else '将修改'} {len(changed)} 个组件")
    if not apply:
        print("[DRY-RUN] 加 --apply 生效。")


if __name__ == "__main__":
    main()
