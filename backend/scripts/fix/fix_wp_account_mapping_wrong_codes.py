#!/usr/bin/env python
r"""修正 `wp_account_mapping.json` 中 4 条错误的科目码与报表行（幂等）。

spec: .kiro/specs/voucher-sampling-account-scope-and-attach-closure/
勘误登记: docs/reference/wp-account-mapping-errata-2026-09-28.md

## 背景

抽凭科目真源接线时把三方（`wp_index` 底稿名 / 前端 `*AccountScope.ts` / 本 json）
逐条对账，发现 4 条 `account_codes` 错。进一步核对 `report_config` 后发现
**`report_row` 也错**（勘误文档首版只记了 `account_codes`）。

## 修正清单与判据

每条都有三重判据：`account_chart`（科目定义表，**权威源**）+ `report_config`（报表公式）
+ 前端 `*AccountScope.ts`（已上线运行态口径）。

| wp | 字段 | 原值 | 原值实为 | 新值 | 判据 |
|---|---|---|---|---|---|
| G4 债权投资 | account_codes | `1501` | 持有至到期投资（`account_chart` 7 条） | `1504` | `account_chart` `1504`=债权投资（6 条）；`gCycleScope('G4')`=`1504` |
| G4 | report_row | `BS-030` | **生产性生物资产** | `BS-021` | `report_config` `BS-021 债权投资 = TB('1504','期末余额')` |
| H5 油气资产 | account_codes | `1606` | 固定资产清理 | `1631` | `account_chart` `1631`=油气资产；`H5_ACCOUNT_DEF.grossFallback`=`1631` |
| H5 | report_row | `BS-031` | **使用权资产** | `None` | `report_config` **无**资产负债表「油气资产」行（仅 CFSS-005 折耗 / IMP-014 减值准备）；`H5_ACCOUNT_DEF.reportRowCode`=`null` |
| K10 其他收益 | account_codes | `6301` | 营业外收入 | `6117` | `account_chart` `6117`=其他收益；`K10_FALLBACK_STANDARD`=`6117` |
| K10 | report_row | `None` | — | `IS-010` | `report_config` `IS-010 加：其他收益 = TB('6117','本期发生额')` |
| K12 营业外收入 | account_codes | `6001` | 主营业务收入 | `6301` | `account_chart` `6301`=营业外收入；`K12_FALLBACK_STANDARD`=`6301` |
| K12 | report_row | `None` | — | `IS-020` | `report_config` `IS-020 加：营业外收入 = TB('6301','本期发生额')` |

🔴 四条的 `wp_name` 与 `account_name` **本来就是对的**（债权投资/油气资产/其他收益/营业外收入），
只有码错 ⇒ 改码后整条自洽，不需要动名称。

## 影响面（改动前已实测）

| 消费方 | 读取字段 | 影响 |
|---|---|---|
| `scripts/validate_seed_files.py`（`WpAccountMappingSeed`） | 全部 | **不拦**：`report_row: str \| None`，无格式校验 |
| `backend/data/note_template_{listed,soe}.json` | 曾被 `backfill_note_seed_account_codes.py` 回填 | **零污染**（实测这 4 条的 label 在两个模板里命中 0）⇒ 无需连带修 |
| `scripts/generate_note_template_bindings.py` → `note_template_bindings.json` | `note_section` + `account_codes` | 产物已被 git 跟踪，**需重新生成并 diff**（见下方 `--regen-hint`） |
| `app/routers/row_name_alignment_router._resolve_account_prefixes` | `account_codes` | 行为变化即**修正**（原按错码查 `tb_balance`） |
| `app/services/address_registry.py` | wp 域条目 | 公式选址候选随之修正 |
| `note_formula_generator._load_cross_table_data` | `account_code → account_name` 反查 | 修正错误映射 |

用法::

    python backend/scripts/fix/fix_wp_account_mapping_wrong_codes.py --check
    python backend/scripts/fix/fix_wp_account_mapping_wrong_codes.py --dry-run
    python backend/scripts/fix/fix_wp_account_mapping_wrong_codes.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
MAPPING_PATH = ROOT / "backend" / "data" / "wp_account_mapping.json"

#: 🔴 **规模更正（2026-09-28 触类旁通复扫）**
#:
#: 首版只改了 4 个**主条目**（G4/H5/K10/K12），实测发现**同族子底稿全部同错**，
#: 且另有一个未登记的错码族 **H3 投资性房地产**（用 `1501` 持有至到期投资）。
#: 发现方式：改完主条目后重新生成 `note_template_bindings.json`，diff 里
#: **只有新增没有删除** ⇒ 旧错码仍被别处引用 ⇒ 顺着查出同族子条目。
#:
#: | 族 | 条数 | 现值 | 该码实为 | 应为 |
#: |---|---|---|---|---|
#: | G4 + G4-1~8 | 9 | `1501` | 持有至到期投资（7 条） | `1504` 债权投资（6 条） |
#: | H5 + H5-1~4 | 5 | `1606` | 固定资产清理 | `1631` 油气资产 |
#: | K10 + K10-1~4 | 5 | `6301` | 营业外收入（K12 的） | `6117` 其他收益（19 条） |
#: | K12 + K12-1~4 | 5 | `6001` | 主营业务收入（D4 的） | `6301` 营业外收入（19 条） |
#: | **H3 + H3-1~6** | **7** | `1501` | 持有至到期投资 | `1521` 投资性房地产（16 条） |
#:
#: H3 的 `report_row` 亦错：`BS-026` 是**其他非流动金融资产**（`TB('1519')`），
#: `BS-027` 才是投资性房地产（`TB('1521')`）；真源 `H3_ACCOUNT_DEF.reportRowCode='BS-027'`
#: 且其 `wrongLegacyCodes=['1503','1504']` 已记录该族历史误用码。

#: (wp_code, 字段, 期望原值, 新值, 判据说明)
#: 🔴 `account_codes` 用 list 比较；`report_row` 用标量（含 None）。
FIXES: list[tuple[str, str, Any, Any, str]] = []


def _add_family(
    codes: list[str],
    field: str,
    old: Any,
    new: Any,
    why: str,
) -> None:
    for c in codes:
        FIXES.append((c, field, old, new, why))


# ── G4 债权投资族：1501（持有至到期投资）→ 1504 ────────────────────────────
_G4 = ["G4", "G4-1", "G4-2", "G4-3", "G4-4", "G4-5", "G4-6", "G4-7", "G4-8"]
_add_family(
    _G4,
    "account_codes",
    ["1501"],
    ["1504"],
    "1501 是持有至到期投资(account_chart 7 条)；1504 才是债权投资(6 条)",
)
FIXES.append(
    (
        "G4",
        "report_row",
        "BS-030",
        "BS-021",
        "BS-030 是生产性生物资产；BS-021 债权投资 = TB('1504','期末余额')",
    )
)

# ── H3 投资性房地产族：1501 → 1521 ────────────────────────────────────────
_H3 = ["H3", "H3-1", "H3-2", "H3-3", "H3-4", "H3-5", "H3-6"]
_add_family(
    _H3,
    "account_codes",
    ["1501"],
    ["1521"],
    "1501 是持有至到期投资；1521 才是投资性房地产(account_chart 16 条)；"
    "真源 H3_ACCOUNT_DEF.grossFallback='1521'",
)
for _c in ("H3", "H3-1"):
    FIXES.append(
        (
            _c,
            "report_row",
            "BS-026",
            "BS-027",
            "BS-026 是其他非流动金融资产(TB('1519'))；BS-027 才是投资性房地产(TB('1521'))",
        )
    )

# ── H5 油气资产族：1606（固定资产清理）→ 1631 ─────────────────────────────
_H5 = ["H5", "H5-1", "H5-2", "H5-3", "H5-4"]
_add_family(
    _H5,
    "account_codes",
    ["1606"],
    ["1631"],
    "1606 是固定资产清理；1631 才是油气资产",
)
FIXES.append(
    (
        "H5",
        "report_row",
        "BS-031",
        None,
        "BS-031 是使用权资产；report_config 无资产负债表「油气资产」行 ⇒ 宁缺勿造置 null",
    )
)

# ── K10 其他收益族：6301（营业外收入）→ 6117 ──────────────────────────────
_K10 = ["K10", "K10-1", "K10-2", "K10-3", "K10-4"]
_add_family(
    _K10,
    "account_codes",
    ["6301"],
    ["6117"],
    "6301 是营业外收入(K12 的科目)；6117 才是其他收益(account_chart 19 条)",
)
FIXES.append(
    (
        "K10",
        "report_row",
        None,
        "IS-010",
        "IS-010 加：其他收益 = TB('6117','本期发生额')",
    )
)

# ── K12 营业外收入族：6001（主营业务收入）→ 6301 ──────────────────────────
_K12 = ["K12", "K12-1", "K12-2", "K12-3", "K12-4"]
_add_family(
    _K12,
    "account_codes",
    ["6001"],
    ["6301"],
    "6001 是主营业务收入(D4 的科目)；6301 才是营业外收入(account_chart 19 条)",
)
FIXES.append(
    (
        "K12",
        "report_row",
        None,
        "IS-020",
        "IS-020 加：营业外收入 = TB('6301','本期发生额')",
    )
)


def _load() -> dict[str, Any]:
    return json.loads(MAPPING_PATH.read_text(encoding="utf-8"))


def _find_entries(doc: dict[str, Any], wp_code: str) -> list[dict[str, Any]]:
    return [
        m
        for m in doc.get("mappings", [])
        if str(m.get("wp_code", "")).strip() == wp_code
    ]


def plan(doc: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    """返回 (待改, 已是新值/幂等跳过, 异常)。"""
    todo: list[str] = []
    done: list[str] = []
    bad: list[str] = []

    for wp, field, old, new, why in FIXES:
        entries = _find_entries(doc, wp)
        if len(entries) != 1:
            bad.append(f"{wp}: 期望恰 1 条，实得 {len(entries)} 条 —— 人工确认后再改")
            continue
        cur = entries[0].get(field)
        if cur == new:
            done.append(f"{wp}.{field} 已是 {new!r}（幂等跳过）")
        elif cur == old:
            todo.append(f"{wp}.{field}: {old!r} → {new!r}    ∵ {why}")
        else:
            # 🔴 既不是期望原值也不是新值 ⇒ 有人改过，绝不盲目覆盖
            bad.append(
                f"{wp}.{field} 现值 {cur!r} 既非期望原值 {old!r} 也非目标 {new!r}"
                " —— 可能已被他处改动，本脚本拒绝覆盖，请人工裁决"
            )
    return todo, done, bad


def apply_fixes(doc: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    for wp, field, old, new, _why in FIXES:
        entries = _find_entries(doc, wp)
        if len(entries) != 1:
            continue
        e = entries[0]
        if e.get(field) == old:
            before_name = e.get("account_name")
            before_wp_name = e.get("wp_name")
            e[field] = new
            # 🔴 只动目标字段：名称本来就是对的，改它会让语义漂移
            assert e.get("account_name") == before_name, "account_name 被误改"
            assert e.get("wp_name") == before_wp_name, "wp_name 被误改"
            changed.append(f"{wp}.{field} = {new!r}")
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="只报告是否仍有待修项（CI 用，有待修则退出码 1）")
    g.add_argument("--dry-run", action="store_true", help="打印将要做的改动，不写文件")
    g.add_argument("--apply", action="store_true", help="写回文件")
    args = ap.parse_args()

    if not MAPPING_PATH.exists():
        print(f"[ERR] 找不到 {MAPPING_PATH}", file=sys.stderr)
        return 2

    doc = _load()
    todo, done, bad = plan(doc)

    for line in done:
        print(f"  [skip] {line}")
    for line in todo:
        print(f"  [todo] {line}")
    for line in bad:
        print(f"  [BAD ] {line}")

    if bad:
        print(f"\n[ERR] {len(bad)} 项异常，未做任何改动", file=sys.stderr)
        return 2

    if args.check:
        if todo:
            print(f"\n[FAIL] 仍有 {len(todo)} 项待修（跑 --apply）")
            return 1
        print(f"\n[OK] 4 条错误均已修正（{len(done)} 项幂等）")
        return 0

    if args.dry_run:
        print(f"\n[DRY-RUN] 将改动 {len(todo)} 项，未写文件")
        return 0

    if not todo:
        print("\n[OK] 无待修项，文件未改动")
        return 0

    changed = apply_fixes(doc)
    # 🔴 保持原文件风格（indent=2 + ensure_ascii=False + 末尾换行），最小化 diff
    MAPPING_PATH.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\n[APPLIED] {len(changed)} 项：")
    for c in changed:
        print(f"    {c}")
    print(
        "\n🔴 后续必做：\n"
        "  1. 重新生成下游产物并 diff（该产物已被 git 跟踪）：\n"
        "     python scripts/generate_note_template_bindings.py\n"
        "     git diff --stat backend/data/note_template_bindings.json\n"
        "  2. 种子校验：python scripts/validate_seed_files.py\n"
        "  3. 重启后端让 address_registry / row_name_alignment 重新加载该 json"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
