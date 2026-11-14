"""生成「金额显示核心文件清单」（frontend amount guard 的 core_files 唯一来源）。

## 背景

spec `platform-global-display-settings-closure` 任务 11A 复核抓到：
`frontend_amount_guard/cli.py` 里两处 `core_files: frozenset[str] = frozenset()`
**恒为空集合、没有任何加载逻辑** ⇒ 「核心面零违规」这条结论建立在
「核心面 = 空集」之上，等于没检。

## 口径（可伪证）

「核心文件」= 决定金额在屏幕上显示样式的那些文件。判据取三类**正面证据**：

1. **核心组件**：`GtAmountCell.vue` / `GtMeasureCell.vue` —— 屏幕金额的唯一渲染组件；
2. **格式化纯函数**：`utils/formatAmount.ts` / `utils/formatMeasure.ts` —— 所有金额
   格式化的单一来源；
3. **引用它们的宿主**：源码里出现上述组件标签或格式化函数调用的 `.vue` / `.ts`。

第 3 类按**实际引用**现算，不手写名单 —— 这样新增页面自动进入核心面，
不会出现「加了新表但核心清单还是老的」。

## 输出幂等

只写 `files`（排序去重）与 `generated_from`（口径说明），**不写时间戳**
（memory 铁律 ㉗②：生成类产物必须输出幂等，否则 `--check` 永远红）。

Usage:
    python -m scripts.gen.gen_frontend_amount_core_manifest --check
    python -m scripts.gen.gen_frontend_amount_core_manifest --write
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FRONTEND_SRC = _REPO_ROOT / "audit-platform" / "frontend" / "src"
_OUT = _REPO_ROOT / "audit-platform" / "frontend" / "scripts" / "amount-guard-core.json"

#: ① 核心组件（屏幕金额的唯一渲染组件）
_CORE_COMPONENTS = (
    "components/common/GtAmountCell.vue",
    "components/common/GtMeasureCell.vue",
)

#: ② 格式化纯函数（金额 / 度量格式化的单一来源）
_CORE_FORMATTERS = (
    "utils/formatAmount.ts",
    "utils/formatMeasure.ts",
)

#: ③ 引用判据：出现这些标签或调用即计入核心面
_REF_PATTERNS = (
    re.compile(r"<GtAmountCell\b"),
    re.compile(r"<GtMeasureCell\b"),
    re.compile(r"<gt-amount-cell\b"),
    re.compile(r"\bformatAmount\s*\("),
    re.compile(r"\bformatMeasure\s*\("),
    re.compile(r"\bfmtAmount\b"),
)

_EXCLUDE_PARTS = ("__tests__",)
_EXCLUDE_SUFFIXES = (".spec.ts", ".test.ts", ".spec.vue")


def _is_test_file(p: Path) -> bool:
    return any(part in _EXCLUDE_PARTS for part in p.parts) or p.name.endswith(
        _EXCLUDE_SUFFIXES
    )


def _iter_sources() -> list[Path]:
    out: list[Path] = []
    for suffix in (".vue", ".ts"):
        out.extend(_FRONTEND_SRC.rglob(f"*{suffix}"))
    return sorted(p for p in out if not _is_test_file(p))


def compute_manifest() -> dict:
    """按三类正面证据现算核心文件清单（纯函数，幂等）。"""
    files: set[str] = set()

    # ①② 固定核心（若文件不存在则不写入 —— 让它显式缺失而不是登记幻影路径）
    for rel in (*_CORE_COMPONENTS, *_CORE_FORMATTERS):
        if (_FRONTEND_SRC / rel).exists():
            files.add(rel)

    # ③ 引用现算
    for p in _iter_sources():
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(pat.search(text) for pat in _REF_PATTERNS):
            files.add(str(p.relative_to(_FRONTEND_SRC)).replace("\\", "/"))

    return {
        "_source": "scripts/gen/gen_frontend_amount_core_manifest.py",
        "criteria": {
            "core_components": list(_CORE_COMPONENTS),
            "core_formatters": list(_CORE_FORMATTERS),
            "reference_patterns": [pat.pattern for pat in _REF_PATTERNS],
            "note": (
                "第 3 类按实际引用现算，新增页面自动纳入；"
                "测试文件一律排除。文件不存在时不登记幻影路径。"
            ),
        },
        "files": sorted(files),
    }


def _dump(manifest: dict) -> str:
    return json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="校验磁盘与现算是否一致")
    group.add_argument("--write", action="store_true", help="写入清单")
    group.add_argument("--print", dest="print_only", action="store_true", help="打印现算结果")
    args = parser.parse_args(argv)

    manifest = compute_manifest()
    rendered = _dump(manifest)

    if args.print_only:
        sys.stdout.write(rendered)
        return 0

    if args.check:
        if not _OUT.exists():
            print(f"❌ 缺少核心清单 {_OUT}；先跑 --write 生成。", file=sys.stderr)
            return 1
        on_disk = _OUT.read_text(encoding="utf-8")
        if on_disk != rendered:
            # 点名差异，不用「有 diff 就红」这种无法定位的报错
            import difflib

            diff = list(
                difflib.unified_diff(
                    on_disk.splitlines(), rendered.splitlines(),
                    fromfile="disk", tofile="computed", lineterm="",
                )
            )
            print(
                f"❌ 核心清单漂移（{len([d for d in diff if d.startswith('+')])} 行新增 / "
                f"{len([d for d in diff if d.startswith('-')])} 行删除）：",
                file=sys.stderr,
            )
            for line in diff[:40]:
                print(line, file=sys.stderr)
            print("   修复：python -m scripts.gen.gen_frontend_amount_core_manifest --write",
                  file=sys.stderr)
            return 1
        print(f"✅ 核心清单一致（{len(manifest['files'])} 个文件）")
        return 0

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(rendered, encoding="utf-8")
    print(f"✅ 已写入 {_OUT}（{len(manifest['files'])} 个核心文件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())