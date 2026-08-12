"""修复 ACNR catalog 里指向「无 bulk 适配器」的 api_prefix（15 个 sheet / 5 个前缀）

spec: workpaper-import-export-lifecycle-closure（Wave 1 收口期发现的真缺陷）

## 缺陷本体

`backend/data/acnr/global_catalog.json` 的 `sheets[].import_export.api_prefix` 有
**5 个值在 `IE_ADAPTER_REGISTRY` 里没有对应适配器**：

| catalog 声明 | 正确值 | 受影响 sheet |
|---|---|---|
| `d1-ecl`    | `d1`                | D1-15 |
| `g4`        | `g4-main`           | G4-1 / G4-2 / G4-3 |
| `g6`        | `g6-main`           | G6-2 / G6-3 |
| `g7`        | `g7-main`           | G7-2 / G7-3 |
| `g7-method` | `g7-equity-method`  | G7-4 / G7-5 / G7-13 ~ G7-17 |

## 🔴 后果是「静默跳过」而非报错

`bulk_export_service` 对未注册前缀走 `except KeyError` → 标 `skip_reason=no_adapter`；
`bulk_import_service` 走 `except KeyError` → `report.mark(..., "skipped")`。
两侧都是 fail-soft，所以这 15 个 sheet 在批量导出/回传里**从来没有产出过**，
而用户只看到 ZIP 里少了几个 tab，日志里也只有一条 warning。

`d1-ecl` 稍有不同：它在运行期**确实有端点**
（`_d1_import_export/_impl.py` 里 hardcoded sheet="D1-15" 的三个专用端点），
但 bulk 层从来只按 `api_prefix` 找适配器，而 `d1` 前缀的模块本就支持 `D1-15`
（`_SHEET_TO_ITEM_ID` 含 `"D1-15": ["D1-ecl-portfolio-rows", "D1-ecl-individual-rows"]`），
故 `d1-ecl` 是多余分叉，归并到 `d1` 即可，不动任何生产代码。

## 判据来源（禁止凭名字相似推断）

目标前缀不是按字符串相似猜的，而是三条独立证据同时成立：
  E1  `IE_ADAPTER_REGISTRY` 里有该前缀（否则换了还是 no_adapter）
  E2  `_PREFIX_TO_MODULE[目标前缀]` 指向的模块源码里出现该 sheet 键
  E3  catalog 内该 sheet_code 唯一（避免改了 A 撞到 B）

`--check` 会重跑这三条，任一不成立即拒绝写盘。

## 用法

    python backend/scripts/fix/fix_acnr_dangling_api_prefix.py --check
    python backend/scripts/fix/fix_acnr_dangling_api_prefix.py --dry-run
    python backend/scripts/fix/fix_acnr_dangling_api_prefix.py --apply
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

CATALOG = _BACKEND / "data" / "acnr" / "global_catalog.json"

#: 声明式修复表 —— 键是 catalog 里的错值，值是 (正确前缀, 受影响 sheet_code 元组)。
#: 🔴 sheet_code 必须写全：修复只作用于这些 sheet，不做「凡是该前缀就改」的批量替换，
#:    否则将来 catalog 新增同前缀条目会被无声带走。
FIX_MAP: dict[str, tuple[str, tuple[str, ...]]] = {
    "d1-ecl": ("d1", ("D1-15",)),
    "g4": ("g4-main", ("G4-1", "G4-2", "G4-3")),
    "g6": ("g6-main", ("G6-2", "G6-3")),
    "g7": ("g7-main", ("G7-2", "G7-3")),
    "g7-method": (
        "g7-equity-method",
        ("G7-4", "G7-5", "G7-13", "G7-14", "G7-15", "G7-16", "G7-17"),
    ),
}

_EXPECTED_TOTAL = 15  # 全部受影响 sheet 数（守卫与本脚本共用的基线）


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def _load() -> tuple[dict, str]:
    raw = CATALOG.read_text(encoding="utf-8")
    return json.loads(raw), raw


def _adapter_keys() -> set[str]:
    """取 IE_ADAPTER_REGISTRY 的键集（需触发全部 register_*）。"""
    from app.services.bulk_tab import _d_cycle_adapters, _kfgh_cycle_adapters
    from app.services.bulk_tab.single_tab_adapter import IE_ADAPTER_REGISTRY

    for mod in (_d_cycle_adapters, _kfgh_cycle_adapters):
        for fn_name in dir(mod):
            if fn_name.startswith("register_") and fn_name.endswith("_adapters"):
                try:
                    getattr(mod, fn_name)()
                except Exception:  # noqa: BLE001 — 重复注册无害
                    pass
    return set(IE_ADAPTER_REGISTRY)


def _module_source(prefix: str) -> str:
    """取目标前缀对应模块的全部源码（含包形态的 `_impl.py`）。

    🔴 两条解析路径都要走，缺一条会误判：

    1. `_kfgh_cycle_adapters._PREFIX_TO_MODULE` —— K/F/G/H/I/L 等统一族的权威映射。
    2. **按命名约定兜底** —— `d1` 等 D 循环前缀的适配器注册在
       `_d_cycle_adapters` 里（它按模块直接 import 命名函数、不建 prefix→module 表），
       故 `_PREFIX_TO_MODULE.get('d1')` 返 None。若只走路径 1 就会把
       「源码里明明有 D1-15」误报成 E2 失败（本脚本首跑即踩此坑）。

    兜底同时接受**单文件**与**包**两种形态：`_d1_import_export.py` 与
    `_d1_import_export/`（后者的 sheet 键在 `_impl.py` 里，只读 `__init__.py` 取不到）。
    """
    from app.services.bulk_tab._kfgh_cycle_adapters import _PREFIX_TO_MODULE

    base = _BACKEND / "app" / "routers" / "wp_render_strategies"
    candidates: list[str] = []

    mapped = _PREFIX_TO_MODULE.get(prefix)
    if mapped:
        candidates.append(mapped)
    # 兜底：`{prefix}` 归一成模块名前缀（`g7-main` → `g7_main`）
    candidates.append(f"_{prefix.replace('-', '_')}_import_export")

    parts: list[str] = []
    seen: set[Path] = set()
    for mod_name in candidates:
        single = base / f"{mod_name}.py"
        if single.is_file() and single not in seen:
            seen.add(single)
            parts.append(single.read_text(encoding="utf-8"))
        pkg = base / mod_name
        if pkg.is_dir():
            for f in sorted(pkg.rglob("*.py")):
                if f not in seen:
                    seen.add(f)
                    parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _verify_targets(cat: dict) -> list[str]:
    """重跑 E1/E2/E3 三条证据，返回违规说明列表（空 = 全部成立）。"""
    problems: list[str] = []
    adapters = _adapter_keys()
    sheets = cat.get("sheets", [])

    src_cache: dict[str, str] = {}
    for wrong, (target, codes) in FIX_MAP.items():
        # E1 目标前缀必须有适配器
        if target not in adapters:
            problems.append(f"E1 失败: 目标前缀 {target!r} 不在 IE_ADAPTER_REGISTRY")
            continue
        if target not in src_cache:
            src_cache[target] = _module_source(target)
        src = src_cache[target]
        for code in codes:
            # E2 目标模块源码必须含该 sheet 键
            if f'"{code}"' not in src and f"'{code}'" not in src:
                problems.append(
                    f"E2 失败: {target!r} 的模块源码未出现 sheet 键 {code!r}"
                )
            # E3 catalog 内该 sheet_code 唯一
            hits = [s for s in sheets if s.get("sheet_code") == code]
            if len(hits) != 1:
                problems.append(
                    f"E3 失败: sheet_code={code!r} 在 catalog 命中 {len(hits)} 次（应为 1）"
                )
            elif (hits[0].get("import_export") or {}).get("api_prefix") not in (
                wrong,
                target,
            ):
                actual = (hits[0].get("import_export") or {}).get("api_prefix")
                problems.append(
                    f"意外前缀: {code!r} 当前 api_prefix={actual!r}（预期 {wrong!r} 或 {target!r}）"
                )
    return problems


def _pending(cat: dict) -> list[tuple[str, str, str]]:
    """返回待改条目 (sheet_code, 现值, 目标值)。已改过的不再返回（幂等）。"""
    out: list[tuple[str, str, str]] = []
    by_code = {s.get("sheet_code"): s for s in cat.get("sheets", [])}
    for wrong, (target, codes) in FIX_MAP.items():
        for code in codes:
            s = by_code.get(code)
            if not s:
                continue
            cur = (s.get("import_export") or {}).get("api_prefix")
            if cur == wrong:
                out.append((code, cur, target))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="仅校验，有待改项则 exit 2")
    g.add_argument("--dry-run", action="store_true", help="打印将改动的条目")
    g.add_argument("--apply", action="store_true", help="写盘")
    args = ap.parse_args()

    if not CATALOG.is_file():
        print(f"[FAIL] catalog 不存在: {CATALOG}")
        return 1

    cat, raw = _load()

    # ─── round-trip 自检：不能逐字复现原文就拒绝写盘 ────────────────────────
    # 🔴 catalog 有 1215 个 sheet / 1MB+，若 json.dumps 的格式与原文不同，
    #    写盘会重排整个文件 ⇒ 与并发会话互相回退（memory 已记这类事故）。
    round_trip = json.dumps(cat, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if round_trip != raw:
        if args.apply:
            print("[FAIL] round-trip 不一致（json.dumps 无法逐字复现原文），拒绝写盘")
            print(f"       原文 {len(raw)} 字符 / 复现 {len(round_trip)} 字符")
            return 2
        print("[WARN] round-trip 不一致 —— apply 前必须先对齐序列化参数")

    problems = _verify_targets(cat)
    if problems:
        print(f"[FAIL] 目标前缀验证不通过（{len(problems)} 项），拒绝任何改动：")
        for p in problems:
            print(f"  · {p}")
        return 2

    total_declared = sum(len(codes) for _, codes in FIX_MAP.values())
    if total_declared != _EXPECTED_TOTAL:
        print(f"[FAIL] FIX_MAP 声明的 sheet 数 {total_declared} != 基线 {_EXPECTED_TOTAL}")
        return 2

    pending = _pending(cat)

    if args.check:
        if pending:
            print(f"[FAIL] 仍有 {len(pending)} 个 sheet 的 api_prefix 无适配器：")
            for code, cur, target in pending:
                print(f"  · {code}: {cur} → {target}")
            return 2
        print(f"[OK] 全部 {total_declared} 个 sheet 的 api_prefix 均已归位")
        return 0

    if not pending:
        print("[OK] 无待改项（幂等）")
        return 0

    print(f"待改 {len(pending)} 个 sheet：")
    for code, cur, target in pending:
        print(f"  · {code}: {cur} → {target}")

    if args.dry_run:
        print("[DRY-RUN] 未写盘")
        return 0

    by_code = {s.get("sheet_code"): s for s in cat.get("sheets", [])}
    for code, _cur, target in pending:
        by_code[code]["import_export"]["api_prefix"] = target

    before = _md5(CATALOG)
    out = json.dumps(cat, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    CATALOG.write_text(out, encoding="utf-8")  # 🔴 必须显式 utf-8（PS 会腌坏中文）
    after = _md5(CATALOG)

    print(f"[APPLIED] {len(pending)} 项；md5 {before[:8]} → {after[:8]}")

    cat2, _ = _load()
    left = _pending(cat2)
    if left:
        print(f"[FAIL] 写盘后仍有 {len(left)} 项未生效")
        return 2
    print("[OK] 写盘后复查归零")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
