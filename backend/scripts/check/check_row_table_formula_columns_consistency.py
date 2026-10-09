# -*- coding: utf-8 -*-
"""`formula_columns` 与 `mode=formula` 列集必须逐值相等（全仓 row-table spec）。

spec: d1-sync-row-table-engine-and-d1-coverage · 缺陷② 修复的防复发卡点
Requirements 1.2 / 6.6（CS-13 的反向面）

═══ 这条门禁钉的是什么 ═══

`RowTableSheetSpec.formula_mask` 是**现算**的：`{col}{first_data_row}:{col}{last_data_row}`
（需求 1.2）—— 它覆盖的是**数据区**，覆盖不到 footer 行。

于是把「只在 footer 出现的 SUM 列」填进 `formula_columns` 会产生一个**无声**的后果：
那些列的整个数据区被 `merge._protection` 判 `read_only_masked_cell`，OO 侧对这些格的改动
一律被挡在 store 之外（`stored` 永不改变）⇒ 需求 1.5「OO 改动 SHALL 生效」在后端不可达。
对保护 footer 却**毫无作用**（mask 本来就覆盖不到 footer）。

2026-09-28 实测：D1 有 8 个受管区犯了这个错，共 **14 个** `editable` 字段被误判只读
（D1-8 E/F/L/M + E · D1-16 E/F + C · D1-12 H/J · D1-10 H · D1-13 G/H + G）。
它与 D4-1 修前的缺陷同型，而当时那个缺陷让「已实现的四态 UI 成了死代码」。

═══ 判据 ═══

对全仓每一个 `RowTableSheetSpec`：

    set(spec.formula_columns) ∩ {col | col 在 field_specs 里且 mode == "editable"} == ∅

即：**`formula_columns` 不得覆盖任何 `editable` 字段的列**。

🔴 **规则不是「恰等于 mode=formula 列集」** —— 那个更严的版本在本仓库会误报。实证反例：
`phase5_i1_02_detail.TEMPLATE_ONLY_FORMULA_COLUMNS_I102` 登记了 19 列，其注释原文是
「模板有列、store 侧是前端重算的派生值 ⇒ 只进 FORMULA_MASK」——它们**根本不在 field_specs 里**
（store 不持久化、前端重算），进 `formula_columns` 只为让 OO 侧只读，**完全正当**。
I2-2 / I3-2 / I4-2 / I5-2 / I6-2 / F3-6 / F5-1 / J1-6 同属这一形态（实测：它们的 extra 列
与模板数据区实测有公式的列**逐值相同**，且 field_specs 里没有这些列）。

⇒ 用「恰等于」规则跑全仓会得到 10 处假阳。这正是「缺陷类判据必须过双向变异」那条纪律的
又一个样本：只用 D1 的坏样本校准规则，会把干净的 I/F/J 判成缺陷。

**正面依据**：2026-09-28 实测 18 个 D1 受管区 —— 无冲突的 10 个区其
`formula_columns ∩ editable 列 = ∅`；出冲突的 8 个区交集恰是那 14 个被误判只读的字段。
修复后全仓 135 个 spec 交集全空。

两个方向的分工：
  * 本卡点守 `formula_columns ∩ editable 列 == ∅`（缺陷②的精确判据，O(1) 纯内存）；
  * `formula_columns ⊇ mode=formula 列`（CS-13）由 `contracts.py:_parse_field` 在契约装配时
    抛 `ContractSchemaError` 守，不在本卡点重复。

🔴 **不校验「模板数据区实际有无公式」** —— 那需要逐册 openpyxl（慢，且 provider 的模板路径
   各异），归 pytest 判据（`test_d1_sheet_specs.py::test_formula_columns_match_template` 等
   按 provider 参数化的那批）。本卡点只守声明层内部一致性，可进 CI 快速门。

自测：`backend/tests/scripts/test_check_row_table_formula_columns_consistency.py`（含变异反证）。
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover
        pass

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_SYNC_DIR = _BACKEND / "app" / "services" / "workpaper_sync"

#: field_specs 的 7 元组里 mode 的位置（`(col_key, column, mode, value_type, json_key, label, gh)`）。
_MODE_INDEX = 2
_COLUMN_INDEX = 1

#: 🔴 已知缺口白名单（冻结棘轮：只许变短，不许变长）。
#:
#: 每条必须写明**归属 lane** 与**为什么本 spec 不修** —— 白名单不是「允许存在」，是
#: 「已登记、归属明确、有 owner」。新增一条需要同时改本表与自测里的期望集合，
#: 两处都改才能通过（防止顺手放行）。
#:
#: 反向断言（`run()` 内实现，需求㉕③）：名单项若**已经合规**，本卡点同样打红并要求删除
#: 该条 —— 防止白名单里躺着失效条目，让后来者误以为还有缺口。
KNOWN_GAPS: dict[tuple[str, str], str] = {
    ("银行存款余额调节表E1-6", "reconciliation_rows"): (
        "归属 lane：e1-sync-coverage-and-first-canary（`phase5_e1_06_reconciliation.py` "
        "在本卡点落地时仍是未提交的并发新增文件，介入会冲突）。"
        "形态与 D1 的 footer-only 误填**不同型**：该 sheet 是余额调节表，`field_specs` 把 "
        "**7 个字段全声明在 C 列**（book_balance/statement_balance 为 editable，"
        "bank_received/bank_paid/company_received/company_paid/diff 为 formula）—— "
        "同一列上混了两种 mode，因此 formula_columns=('C',) 必然覆盖到那两个 editable 字段。"
        "真实修法要先裁决它到底是行表还是转置表（竖排一行一项目），不是调 formula_columns。"
        "本卡点只登记，不代 E1 lane 决策。"
    ),
}


def _candidate_modules() -> list[str]:
    """全仓 sheet 声明层模块（现扫目录，不写死清单）。"""
    names: list[str] = []
    for pattern in ("phase5_*.py", "pilot_*.py"):
        for path in sorted(_SYNC_DIR.glob(pattern)):
            names.append(f"app.services.workpaper_sync.{path.stem}")
    return names


def _collect_specs() -> tuple[dict[tuple[str, str], Any], list[str]]:
    """收集全仓 `RowTableSheetSpec` 实例。

    以 `(managed_sheet, table_key)` 为身份去重 —— 同一个 spec 常被多个模块 re-export
    （伴生模块 / entry 模块），按对象 id 去重会重复计数。
    """
    from app.services.workpaper_sync.phase5_row_table_sheet import RowTableSheetSpec

    found: dict[tuple[str, str], Any] = {}
    skipped: list[str] = []
    for name in _candidate_modules():
        try:
            mod = importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001
            skipped.append(f"{name}: {type(exc).__name__}: {exc}")
            continue
        for attr in vars(mod).values():
            if isinstance(attr, RowTableSheetSpec):
                found[(attr.managed_sheet, attr.table_key)] = attr
            elif isinstance(attr, (tuple, list)):
                for item in attr:
                    if isinstance(item, RowTableSheetSpec):
                        found[(item.managed_sheet, item.table_key)] = item
    return found, skipped


def columns_by_mode(spec: Any, mode: str) -> set[str]:
    """spec 的 `field_specs` 里指定 mode 的列集。"""
    return {
        row[_COLUMN_INDEX]
        for row in (spec.field_specs or ())
        if len(row) > _MODE_INDEX and row[_MODE_INDEX] == mode
    }


def check_spec(spec: Any) -> dict[str, Any] | None:
    """返回 None 表示合规；否则返回违规明细（`formula_columns` 覆盖了 editable 列）。"""
    declared = set(spec.formula_columns or ())
    editable = columns_by_mode(spec, "editable")
    masked_editable = declared & editable
    if not masked_editable:
        return None
    fields_by_col = {
        row[_COLUMN_INDEX]: row[0]
        for row in (spec.field_specs or ())
        if len(row) > _MODE_INDEX and row[_MODE_INDEX] == "editable"
    }
    return {
        "managed_sheet": spec.managed_sheet,
        "table_key": spec.table_key,
        "declared": sorted(declared),
        "mode_formula": sorted(columns_by_mode(spec, "formula")),
        "masked_editable": sorted(masked_editable),
        "masked_editable_fields": sorted(
            f"{col}:{fields_by_col[col]}" for col in masked_editable
        ),
        "first_data_row": spec.first_data_row,
        "last_data_row": spec.last_data_row,
        "footer_row": spec.footer_row,
    }


def run() -> dict[str, Any]:
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    os.environ.setdefault("DB_DISABLE_SSL", "True")

    specs, skipped = _collect_specs()
    all_violations = [v for v in (check_spec(s) for s in specs.values()) if v is not None]

    violations: list[dict[str, Any]] = []
    known_hit: list[dict[str, Any]] = []
    for v in all_violations:
        key = (v["managed_sheet"], v["table_key"])
        if key in KNOWN_GAPS:
            v = {**v, "known_gap_reason": KNOWN_GAPS[key]}
            known_hit.append(v)
        else:
            violations.append(v)

    # 反向断言：白名单里已经合规的条目必须删掉（防失效条目长期占位）。
    #
    # 🔴 但「已合规」与「在当前检出里根本不存在」必须分开（2026-09-28 实测）：
    #    E1-6 的 provider `phase5_e1_06_reconciliation.py` 是**别 lane 尚未入库**的文件。
    #    在开发者工作树上它存在且仍违规（白名单正确），在纯 HEAD 检出上它不存在 ⇒
    #    旧口径 `k not in hit_keys` 会把它判成「已失效，请删白名单」—— 于是 CI 上
    #    要求删掉一条**其实仍然有效**的登记，删了之后等那条 lane 提交，门就变成漏报。
    #    正确口径：只有受管区**确实被扫到**且不再违规，才算失效。
    hit_keys = {(v["managed_sheet"], v["table_key"]) for v in known_hit}
    stale_gaps = [k for k in KNOWN_GAPS if k in specs and k not in hit_keys]
    absent_gaps = [k for k in KNOWN_GAPS if k not in specs]

    return {
        "ok": not violations and not stale_gaps,
        "scanned_specs": len(specs),
        "masked_editable_field_count": sum(
            len(v["masked_editable_fields"]) for v in violations
        ),
        "skipped_modules": skipped,
        "violations": sorted(violations, key=lambda v: (v["managed_sheet"], v["table_key"])),
        "known_gaps_hit": sorted(known_hit, key=lambda v: (v["managed_sheet"], v["table_key"])),
        "stale_known_gaps": sorted(f"{s} / {t}" for s, t in stale_gaps),
        # 不判红，但必须打印 —— 它意味着「该登记项所属 provider 模块在当前检出里
        # 不存在」（通常是别 lane 未入库）。不打印就会变成第二种遮羞布。
        "absent_known_gaps": sorted(f"{s} / {t}" for s, t in absent_gaps),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=str, default=None)
    args = parser.parse_args()

    report = run()
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if report["ok"]:
        print(
            f"✅ formula_columns 未覆盖任何 editable 列："
            f"扫描 {report['scanned_specs']} 个 RowTableSheetSpec，"
            f"新增违规 0（已登记缺口 {len(report['known_gaps_hit'])} 条，见 KNOWN_GAPS）"
        )
        for v in report["known_gaps_hit"]:
            print(
                f"   [已登记] {v['managed_sheet']} / {v['table_key']}："
                f"{v['masked_editable_fields']}"
            )
        for s in report["absent_known_gaps"]:
            print(
                f"   [登记项不在本检出] {s} —— 其 provider 模块在当前检出里不存在"
                "（通常是别 lane 未入库）。登记保留，等该模块入库后本门会重新校验它。"
            )
        if report["skipped_modules"]:
            print(f"   （{len(report['skipped_modules'])} 个模块导入失败，已跳过，不影响判定）")
        return 0

    if report["stale_known_gaps"]:
        print(
            f"❌ KNOWN_GAPS 里有 {len(report['stale_known_gaps'])} 条**已失效**"
            f"（这些受管区现已合规）—— 请从白名单删除，别让它躺着占位："
        )
        for s in report["stale_known_gaps"]:
            print(f"   [失效] {s}")
        if not report["violations"]:
            return 1

    print(
        f"❌ formula_columns 覆盖了 editable 字段的列"
        f"（{len(report['violations'])} 个受管区 / "
        f"{report['masked_editable_field_count']} 个字段）／扫描 "
        f"{report['scanned_specs']} 个 spec："
    )
    for v in report["violations"]:
        print(f"   [{v['managed_sheet']} / {v['table_key']}]")
        print(f"      formula_columns={v['declared']}  mode=formula 的列={v['mode_formula']}")
        print(
            f"      🔴 被 mask 误伤的 editable 字段：{v['masked_editable_fields']}\n"
            f"         这些列的数据区 R{v['first_data_row']}-{v['last_data_row']} 会被 "
            f"merge._protection 判 read_only_masked_cell ⇒ OO 侧改动写不回 store。\n"
            f"         若这些列的公式只在 footer R{v['footer_row']}，mask 本来就覆盖不到它 ⇒ "
            f"应从 formula_columns 移除（footer 公式文本另立 FOOTER_SUM_TEMPLATES_* 常量留证）；\n"
            f"         若数据区真有公式，则应把 field_specs 里这些列的 mode 改成 formula，\n"
            f"         或按 `TEMPLATE_ONLY_FORMULA_COLUMNS_*` 形态把它们从 field_specs 移出。"
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
