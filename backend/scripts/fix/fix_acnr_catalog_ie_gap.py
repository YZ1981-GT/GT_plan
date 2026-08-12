"""补 ACNR catalog 的 I/E 缺口 — workpaper-import-export-lifecycle-closure Task 14

## 缺口实证（2026-08-10）

| 维度 | 数 |
|---|---|
| 运行期三态齐全前缀 | **100** |
| catalog 已登记 `api_prefix` | **59** |
| 缺口 | **41** |

41 个缺口按「能否安全补」分四档：

| 档 | 数 | 判据 | 处置 |
|---|---|---|---|
| `SAFE` | **13** | 工厂族 `specs` 字典可 AST 抽出逐 sheet 的 `item_id`/`storage_field`，且有 bulk 适配器 | **本脚本补** |
| `RISKY` | 4 | 有适配器但 `specs` 抽不出（`item_id` 散落函数体） | 登记，人工核后另补 |
| `NO_ADAPTER` | 23 | `IE_ADAPTER_REGISTRY` 无该前缀 | **禁止补**（见下） |
| `NO_MODULE` | 1 | 找不到声明该前缀的 I/E 模块 | 登记 |

## 🔴 为什么 `NO_ADAPTER` 必须禁止补

`bulk_export_service` / `bulk_import_service` 对无适配器的 `api_prefix` 走
`except KeyError` → 标 `skip_reason=no_adapter` **静默跳过**。

本 spec 的 Task 2 刚修掉的正是这个缺陷（catalog 有 5 个前缀无适配器，
15 个 sheet 长期静默不导出）。**往 catalog 加没有适配器的前缀 = 重新制造同一个缺陷**，
而且这次是 23 个前缀、规模大 4 倍。

⇒ 正确顺序是**先建适配器、再登记 catalog**。本脚本内建该前置校验，
无适配器的前缀一律拒绝写入（不是警告，是拒绝）。

## 🔴 为什么 `item_id` 不能猜

catalog 的 `item_id` 决定 bulk 从哪个 `checklist_responses.item_id` 读写。
猜错 ⇒ 导出读空、导入写进别的键（数据错位，比"不可用"更糟且更难发现）。
故本脚本只补能从**后端 specs 字典 AST 直取**的那 13 个前缀，其余显式登记。

## 用法

    python backend/scripts/fix/fix_acnr_catalog_ie_gap.py --check
    python backend/scripts/fix/fix_acnr_catalog_ie_gap.py --dry-run
    python backend/scripts/fix/fix_acnr_catalog_ie_gap.py --apply
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

CATALOG = _BACKEND / "data" / "acnr" / "global_catalog.json"
WPRS = _BACKEND / "app" / "routers" / "wp_render_strategies"

_THREE = ("export-template", "export-data", "import-data")
_PARAM = re.compile(r"^\{.*\}$")

#: 缺口前缀的显式登记表（R4.7）—— 每条含理由，不得静默遗漏。
#:
#: 🔴 `NO_ADAPTER` 那 23 条**不是遗漏而是有意不补**：补了会让 bulk 静默跳过。
GAP_REGISTRY: dict[str, str] = {
    # ── 无 bulk 适配器：补进 catalog 会让 bulk 以 no_adapter 静默跳过 ──────
    "d1-ecl": "无 bulk 适配器；且 D1-15 的能力已由 `d1` 前缀覆盖（Task 2 已把 catalog 改指 d1）",
    "disclosure": "无 bulk 适配器；披露专用端点，不属四场景批量半径",
    "import-export": "无 bulk 适配器；J3 异形路径（/template|/export|/import），需专用适配器",
    "s-estimate": "无 bulk 适配器；S 类估计专用，独立路由族",
    "h9-lease-liabilities": "无 bulk 适配器；专属 router 族（非 wp_render_strategies 工厂）",
    "l2-interest-payable": "无 bulk 适配器；同上",
    "l6-special-payables": "无 bulk 适配器；同上",
    "l7-other-noncurrent-liabilities": "无 bulk 适配器；同上",
    "l8-financial-expenses": "无 bulk 适配器；同上",
    "m1-dividends-payable": "无 bulk 适配器；同上",
    "m2-paid-in-capital": "无 bulk 适配器；同上",
    "m3-treasury-stock": "无 bulk 适配器；同上",
    "m4-capital-reserve": "无 bulk 适配器；同上",
    "m5-surplus-reserve": "无 bulk 适配器；同上",
    "m6-retained-earnings": "无 bulk 适配器；同上",
    "m7-special-reserve": "无 bulk 适配器；同上",
    "m8-general-risk-reserve": "无 bulk 适配器；同上",
    "m9-other-comprehensive-income": "无 bulk 适配器；同上",
    "m10-other-equity-instruments": "无 bulk 适配器；同上",
    "n1-deferred-tax-assets": "无 bulk 适配器；同上",
    "n2-taxes-payable": "无 bulk 适配器；同上",
    "n3-deferred-tax-liabilities": "无 bulk 适配器；同上",
    "n5-income-tax-expense": "无 bulk 适配器；同上",
    # ── 有适配器但 item_id 抽不出：需人工核，宁缺勿造 ─────────────────────
    "c24-journal": "specs 非字典字面量（item_id 在函数体常量 _ITEM_ID），需人工核后另补",
    "e1": "specs 抽取失败，需人工核 item_id 后另补",
    "j1": "specs 抽取失败，需人工核 item_id 后另补",
    "l0": "函证族（跨循环共享 D0 组件），item_id 形态待核",
    # ── 找不到声明模块 ──────────────────────────────────────────────────
    "j2": "未找到声明该前缀的 I/E 模块；J2 composable 层整体是孤儿链（见 Task 17）",
}


def _runtime_full3() -> set[str]:
    from app.main import app

    groups: dict[str, set[str]] = {}
    for r in app.routes:
        segs = getattr(r, "path", "").strip("/").split("/")
        if len(segs) < 2 or segs[-1] not in _THREE:
            continue
        p = segs[-2]
        if _PARAM.match(p):
            if len(segs) < 3 or _PARAM.match(segs[-3]):
                continue
            p = segs[-3]
        groups.setdefault(p, set()).add(segs[-1])
    return {k for k, v in groups.items() if len(v) == 3}


def _adapter_keys() -> set[str]:
    from app.services.bulk_tab import _d_cycle_adapters, _kfgh_cycle_adapters
    from app.services.bulk_tab.single_tab_adapter import IE_ADAPTER_REGISTRY

    for mod in (_d_cycle_adapters, _kfgh_cycle_adapters):
        for fn in dir(mod):
            if fn.startswith("register_") and fn.endswith("_adapters"):
                try:
                    getattr(mod, fn)()
                except Exception:  # noqa: BLE001
                    pass
    return set(IE_ADAPTER_REGISTRY)


def _factory_specs(path: Path) -> dict[str, dict] | None:
    """AST 抽 `create_cycle_import_export_router(specs=…)` 的字典。

    🔴 必须同时解析 `Assign` 与 **`AnnAssign`**：`_I1_SPECS: dict[...] = {...}`
    是带注解的赋值，只收 `Assign` 会让 13 个可抽模块被误判成"抽不出"
    （本脚本初版探针即此缺陷，一度把 SAFE 数报成 0）。
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return None

    consts: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            if isinstance(node.targets[0], ast.Name):
                consts[node.targets[0].id] = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            if isinstance(node.target, ast.Name):
                consts[node.target.id] = node.value

    def deref(n: ast.AST) -> ast.AST:
        hops = 0
        while isinstance(n, ast.Name) and n.id in consts and hops < 5:
            n = consts[n.id]
            hops += 1
        return n

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if fn != "create_cycle_import_export_router":
            continue
        for kw in node.keywords:
            if kw.arg != "specs":
                continue
            d = deref(kw.value)
            if not isinstance(d, ast.Dict):
                return None
            out: dict[str, dict] = {}
            for k, v in zip(d.keys, d.values):
                if not isinstance(k, ast.Constant):
                    continue
                entry: dict = {}
                vv = deref(v)
                if isinstance(vv, ast.Dict):
                    for kk, val in zip(vv.keys, vv.values):
                        if isinstance(kk, ast.Constant) and isinstance(val, ast.Constant):
                            entry[str(kk.value)] = val.value
                out[str(k.value)] = entry
            return out
    return None


def _module_prefixes(path: Path) -> set[str]:
    src = path.read_text(encoding="utf-8")
    out = set(re.findall(r'api_prefix\s*=\s*["\']([^"\']+)["\']', src))
    out |= set(
        re.findall(r'@router\.\w+\(\s*["\']/api/workpapers/\{wp_id\}/([\w-]+)/', src)
    )
    out |= set(re.findall(r'@router\.\w+\(\s*["\']/api/([\w-]+)/\{wp_id\}/', src))
    return out


def plan_additions() -> tuple[dict[str, dict[str, dict]], list[str], list[str]]:
    """返回 `(prefix → {sheet_code → ie_segment}, safe_prefixes, blocked_reasons)`。"""
    from app.services.acnr.catalog import list_sheets

    cat_prefixes: set[str] = set()
    cat_sheet_codes: set[str] = set()
    for s in list_sheets(import_export_only=True):
        ie = s.get("import_export") or {}
        if ie.get("api_prefix"):
            cat_prefixes.add(ie["api_prefix"])
        if s.get("sheet_code"):
            cat_sheet_codes.add(s["sheet_code"])

    full3 = _runtime_full3()
    adapters = _adapter_keys()
    gap = sorted(full3 - cat_prefixes)

    prefix_to_mod: dict[str, Path] = {}
    for f in WPRS.glob("*_import_export.py"):
        for p in _module_prefixes(f):
            prefix_to_mod.setdefault(p, f)

    additions: dict[str, dict[str, dict]] = {}
    safe: list[str] = []
    blocked: list[str] = []

    for prefix in gap:
        if prefix not in adapters:
            blocked.append(f"{prefix}: 无 bulk 适配器（补进 catalog 会静默跳过）")
            continue
        mod = prefix_to_mod.get(prefix)
        if mod is None:
            blocked.append(f"{prefix}: 未找到声明模块")
            continue
        specs = _factory_specs(mod)
        if not specs:
            blocked.append(f"{prefix}: specs 抽取失败，item_id 不可确证")
            continue

        per_sheet: dict[str, dict] = {}
        for sheet_code, entry in specs.items():
            item_id = entry.get("item_id")
            if not item_id:
                continue
            # 🔴 已在 catalog 的 sheet_code 不动（防覆盖既有 item_id）
            if sheet_code in cat_sheet_codes:
                continue
            per_sheet[sheet_code] = {
                "enabled": True,
                "api_prefix": prefix,
                "item_id": item_id,
                "storage_field": entry.get("storage_field", "remark"),
            }
        if per_sheet:
            additions[prefix] = per_sheet
            safe.append(prefix)
        else:
            blocked.append(f"{prefix}: 无可补 sheet（全部已在 catalog 或无 item_id）")

    return additions, safe, blocked


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    additions, safe, blocked = plan_additions()

    # 登记表完整性：每个被挡下的前缀都必须在 GAP_REGISTRY 里有理由（R4.7）
    unregistered = [
        b.split(":")[0] for b in blocked if b.split(":")[0] not in GAP_REGISTRY
    ]
    if unregistered:
        print(f"[FAIL] 以下缺口前缀未登记理由（R4.7 要求显式登记）: {unregistered}")
        return 2

    total_sheets = sum(len(v) for v in additions.values())
    print(f"可安全补: {len(safe)} 个前缀 / {total_sheets} 个 sheet")
    print(f"已登记不补: {len(blocked)} 条")

    if args.check:
        if additions:
            print("[FAIL] 仍有可补但未补的条目，请跑 --apply")
            for p in safe:
                print(f"  · {p}: {sorted(additions[p])}")
            return 2
        print("[OK] catalog I/E 缺口已按登记表收口")
        return 0

    if args.dry_run:
        for p in safe:
            for code, seg in sorted(additions[p].items()):
                print(f"  + {code}: api_prefix={seg['api_prefix']} item_id={seg['item_id']}")
        print("[DRY-RUN] 未写盘")
        return 0

    if not additions:
        print("[OK] 无待补项（幂等）")
        return 0

    raw = CATALOG.read_text(encoding="utf-8")
    data = json.loads(raw)
    round_trip = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if round_trip != raw:
        print("[FAIL] round-trip 不一致，拒绝写盘（防重排整个文件与并发会话互相回退）")
        return 2

    by_code = {s.get("sheet_code"): s for s in data.get("sheets", [])}
    applied = 0
    missing_sheet: list[str] = []
    for prefix, per_sheet in additions.items():
        for code, seg in per_sheet.items():
            sheet = by_code.get(code)
            if sheet is None:
                # catalog 里没有这个 sheet 条目 —— 不新建 sheet（那属 ACNR 目录维护
                # 半径，需 addr_id / domain / cycle 等一整套元数据），只登记
                missing_sheet.append(f"{prefix}/{code}")
                continue
            sheet["import_export"] = seg
            applied += 1

    before = hashlib.md5(CATALOG.read_bytes()).hexdigest()[:8]
    CATALOG.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    after = hashlib.md5(CATALOG.read_bytes()).hexdigest()[:8]
    print(f"[APPLIED] {applied} 个 sheet 的 import_export 段；md5 {before} → {after}")
    if missing_sheet:
        print(f"[NOTE] {len(missing_sheet)} 个 sheet 在 catalog 无条目，未新建（属 ACNR 目录维护半径）:")
        for x in missing_sheet[:20]:
            print(f"  · {x}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
