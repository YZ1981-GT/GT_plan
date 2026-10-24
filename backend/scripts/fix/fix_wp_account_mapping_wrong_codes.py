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

# ── 2026-10-24 第二批（spec formula-fetch-followup-defect-closure R1）────────────
#: 依据 = 四表口径单一来源（`four_table/*_cycle_specs`、`j_cycle_account_scope`、`dual_family_codes`，均已真库对账）
#: + 真库 `account_chart` / `trial_balance` 逐码现查（1124 / 1412 / 1606B / 1703B / 2261 / 2611 / 2802 / 4501 全库不存在）。
#: 客户科目表（10 个项目）：4001 实收资本 / 4002 资本公积 / 4003 其他综合收益 / 4101 盈余公积 / 4103 本年利润 /
#: 4104 利润分配 / 4201 库存股 / 4301 专项储备 / 4401 其他权益工具 —— M3~M10 原先整体错位一格。
#: 没有标准科目的改为空（宁缺勿造）：取数改为用户填写或按名定位，不能借用别的科目。
_SECOND_BATCH: list[tuple[list[str], list[str], list[str], str]] = [
    (["D5", "D5-1", "D5-2"], ["1124"], [],
     "1124 全库科目表与试算表都没有；d_cycle_specs 不给兜底码（应收款项融资按名定位 / 用户填写）"),
    (["F2-55", "F2-56", "F2-57", "F2-58"], ["1411", "1412"], ["1411"], "1412 全库不存在；周转材料只有 1411"),
    (["H6", "H6-1", "H6-2", "H6-3", "H6-4"], ["1606B"], ["1606"], "试算表标准码没有字母后缀；h6_account_scope 兜底 1606"),
    (["H8", "H8-1", "H8-2", "H8-3", "H8-4", "H8-5", "H8-6"], ["1901"], ["1641", "1651"],
     "1901 是待处理财产损溢；使用权资产双族 1641 / 1651（dual_family_codes H8 gross）"),
    (["H9", "H9-1", "H9-2", "H9-3", "H9-4", "H9-5", "H9-6"], ["2802"], ["2601", "2651"],
     "2802 全库不存在；租赁负债双族 2601 / 2651（dual_family_codes H9 gross）"),
    (["I1", "I1-1", "I1A"], ["1701", "1702", "1703B"], ["1701", "1702", "1703"], "试算表标准码没有字母后缀（1703 无形资产减值准备）"),
    (["I1-4", "I1-12", "I1-13"], ["1703B"], ["1703"], "试算表标准码没有字母后缀（1703 无形资产减值准备）"),
    (["I5", "I5-1", "I5-2", "I5-3", "I5-4"], ["1901"], [],
     "1901 是待处理财产损溢；其他非流动资产没有标准科目（i_cycle_accounts I5 兜底为空）"),
    (["J2", "J2-1", "J2-2", "J2-3", "J2-4", "J2-5", "J2-6", "J2A"], ["2611"], ["2705"],
     "2611 全库不存在；长期应付职工薪酬 2705（J2_GROSS_FALLBACK，8 个项目）"),
    (["J3", "J3-1", "J3-2", "J3-3", "J3-4", "J3-5", "J3-6", "J3A"], ["2711"], [],
     "2711 是 L6 专项应付款；股份支付没有独立科目（经应付职工薪酬 / 资本公积入账）"),
    (["K4", "K4-1", "K4-2", "K4-3", "K4-4"], ["2261"], [],
     "2261 全库不存在；其他流动负债没有标准科目（k_cycle_specs K4 兜底为空）"),
    (["L7", "L7-1", "L7-2", "L7-3", "L7-4"], ["2801"], [],
     "2801 是 K5 预计负债；其他非流动负债没有标准科目（l_cycle_specs L7 兜底为空）"),
    (["M3", "M3-1", "M3-2", "M3-3", "M3-4", "M3A"], ["4002"], ["4201"], "库存股 4201（4002 是资本公积）"),
    (["M4", "M4-1", "M4-2", "M4-3", "M4-4", "M4-5", "M4-6", "M4A"], ["4101"], ["4002"], "资本公积 4002（4101 是盈余公积）"),
    (["M5", "M5-1", "M5-2", "M5-3", "M5-4", "M5A"], ["4103"], ["4101"], "盈余公积 4101（4103 是本年利润）"),
    (["M7", "M7-1", "M7-2", "M7-3", "M7-4", "M7A"], ["4201"], ["4301"], "专项储备 4301（4201 是库存股）"),
    (["M8", "M8-1", "M8-2", "M8-3", "M8-4", "M8A"], ["4301"], [],
     "4301 是专项储备；一般风险准备各项目科目表都没有（m_cycle_specs M8 兜底为空）"),
    (["M9", "M9-1", "M9-2", "M9-3", "M9-4", "M9-5", "M9-6", "M9A"], ["4401"], ["4003"],
     "其他综合收益 4003（4401 是其他权益工具）"),
    (["M10", "M10-1", "M10-2", "M10-3", "M10-4", "M10A"], ["4501"], ["4401"], "其他权益工具 4401（4501 全库不存在）"),
]
for _codes, _old, _new, _why in _SECOND_BATCH:
    _add_family(_codes, "account_codes", _old, _new, _why)

# ── 2026-10-24 第三批（全表探针：映射码 ⊆ 四表口径单一来源；spec formula-fetch-followup-defect-closure R1.6）──
#: 真库 account_chart 现查（standard 侧 6 个项目一致）：1503 可供出售金融资产（旧准则）/ 1506 其他债权投资 /
#: 1507 其他权益工具投资 / 1901 待处理财产损溢 / 1701 无形资产。
_THIRD_BATCH: list[tuple[list[str], list[str], list[str], str]] = [
    (["G6", "G6-1", "G6-2", "G6-3", "G6-4", "G6-5", "G6-6"], ["1503"], ["1506"],
     "1503 是旧准则可供出售金融资产；其他债权投资 1506（g_cycle_specs G6，真库 6 个项目）"),
    (["G8", "G8-1", "G8-2", "G8-3", "G8-4", "G8-5", "G8-6"], ["1503"], ["1507"],
     "1503 是旧准则可供出售金融资产（G6 / G8 共用一个码会互相触发）；其他权益工具投资 1507（g_cycle_specs G8，真库 6 个项目）"),
    (["K2", "K2-1", "K2-2", "K2-3", "K2-4"], ["1701"], ["1901"],
     "1701 是 I1 无形资产；其他流动资产没有独立标准码，报表 BS-014 取 1901 待处理财产损溢（k_cycle_specs K2 兜底 1901）"),
]
for _codes, _old, _new, _why in _THIRD_BATCH:
    _add_family(_codes, "account_codes", _old, _new, _why)

# ── 2026-10-24 第四批（条目名 vs 科目名逐条核对；同 spec R1.6）──
#: 真库 account_chart 现查：存货科目并存两套标准科目表变体（`f2_extraction.category_rules` 文件头），
#: 1405 库存商品 / 自制半成品、1406 发出商品 / 库存商品、1408 委托加工物资 / 商品进销差价、1411 周转材料 / 委托加工物资
#: 在两套里含义互换 ⇒ 只写在所有变体里含义唯一的码：1402 在途物资、1403 原材料、1416 / 1461 存货跌价准备（变体 A / B）、
#: 1472 合同履约成本；1471 在平台标准科目表（6 个项目）是合同取得成本（仅 1 个客户科目表叫存货跌价准备）。
#: 族级条目（主条目 / 审定 / 分类 / 变动）列全族：1401~1499 里两套变体都是存货的码（含 1471 / 1472，
#: `category_rules` 把合同取得成本 / 合同履约成本归入存货的合同成本类）。
_F2_FAMILY = [
    "1401", "1402", "1403", "1404", "1405", "1406", "1407", "1408", "1409", "1411",
    "1416", "1421", "1431", "1441", "1451", "1452", "1461", "1471", "1472",
]
_FOURTH_BATCH: list[tuple[list[str], list[str], list[str], str]] = [
    (["E0-4"], ["1002"], ["2001", "2501"],
     "借款发函记录表：函证的是银行借款，短期借款 2001 / 长期借款 2501（与 L0 筹资循环函证同码）"),
    (["E0-5"], ["1002"], ["2201"], "应付银行承兑汇票发函记录表：应付票据 2201（f_cycle_specs F3）"),
    (["F2", "F2-1"], ["1401", "1402", "1403", "1405", "1408", "1461"], _F2_FAMILY,
     "存货按区间取数（BS-010 = SUM_TB('1401~1499')）：两套变体的存货科目全部列出（原先缺 1406 库存商品 / 1416 跌价准备等，"
     "变体 A 项目的这些行关联不到 F2）；不含 1481 / 1482 持有待售资产"),
    (["F2-2", "F2-3"], ["1401", "1402", "1403", "1405"], _F2_FAMILY, "存货分类明细 / 增减变动覆盖全部存货类别，同主条目"),
    (["F2-4"], ["1401"], ["1403"], "原材料 1403（1401 是材料采购）"),
    (["F2-5"], ["1402"], [], "1402 是在途物资；在产品没有存货类独立科目（是生产成本余额，4001 / 5001 在各套科目表里另有含义）"),
    (["F2-6"], ["1403"], [],
     "1403 是原材料；库存商品在两套变体里分别是 1405 / 1406，这两个码在另一套里是自制半成品 / 发出商品 ⇒ 静态码表达不了"),
    (["F2-7"], ["1404"], ["1402"], "在途物资 1402（1404 是材料成本差异）"),
    (["F2-8"], ["1408"], [],
     "委托加工物资在两套变体里分别是 1408 / 1411，这两个码在另一套里是商品进销差价 / 周转材料 ⇒ 静态码表达不了"),
    (["F2-9"], ["1405"], [], "1405 是库存商品 / 自制半成品；工程施工在平台标准科目表是 4401（客户科目表里是其他权益工具）⇒ 宁缺勿造"),
    (["F2-10"], ["1405"], [], "1405 是库存商品 / 自制半成品；开发产品没有标准独立码"),
    (["F2-11", "F2-12", "F2-47", "F2-48", "F2-49"], ["1461", "1471"], ["1416", "1461"],
     "存货跌价准备 1416 / 1461（两套变体）；1471 在平台标准科目表是合同取得成本"),
    (["F2-55", "F2-56", "F2-57", "F2-58"], ["1411"], ["1472"], "合同履约成本 1472（1411 是周转材料 / 委托加工物资）"),
]
for _codes, _old, _new, _why in _FOURTH_BATCH:
    _add_family(_codes, "account_codes", _old, _new, _why)


def _load() -> dict[str, Any]:
    return json.loads(MAPPING_PATH.read_text(encoding="utf-8"))


def _find_entries(doc: dict[str, Any], wp_code: str) -> list[dict[str, Any]]:
    return [
        m
        for m in doc.get("mappings", [])
        if str(m.get("wp_code", "")).strip() == wp_code
    ]


def _chains() -> dict[tuple[str, str], list[tuple[Any, Any, str]]]:
    """按 (底稿, 字段) 把各批修正串成链（批次顺序即登记顺序）。

    同一条目可能被后一批再次改正（F2-55~58：第二批 1411+1412 → 1411，第四批 1411 → 1472），
    链上相邻两步必须首尾相接（前一步的新值 = 后一步的原值），否则是登记错误。
    """
    chains: dict[tuple[str, str], list[tuple[Any, Any, str]]] = {}
    for wp, field, old, new, why in FIXES:
        chain = chains.setdefault((wp, field), [])
        if chain and chain[-1][1] != old:
            raise ValueError(f"{wp}.{field} 修正链断开：上一步改成 {chain[-1][1]!r}，这一步的原值写的是 {old!r}")
        chain.append((old, new, why))
    return chains


def plan(doc: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
    """返回 (待改, 已是最终值/幂等跳过, 异常)。现值必须在修正链上（原值或某一步的新值），否则拒绝覆盖。"""
    todo: list[str] = []
    done: list[str] = []
    bad: list[str] = []

    for (wp, field), chain in _chains().items():
        entries = _find_entries(doc, wp)
        if len(entries) != 1:
            bad.append(f"{wp}: 期望恰 1 条，实得 {len(entries)} 条 —— 人工确认后再改")
            continue
        cur = entries[0].get(field)
        final = chain[-1][1]
        values = [chain[0][0], *(new for _old, new, _why in chain)]
        if cur == final:
            done.append(f"{wp}.{field} 已是 {final!r}（幂等跳过）")
        elif cur in values:
            why = "；".join(w for _o, _n, w in chain[values.index(cur):])
            todo.append(f"{wp}.{field}: {cur!r} → {final!r}    ∵ {why}")
        else:
            # 🔴 不在修正链上 ⇒ 有人改过，绝不盲目覆盖
            bad.append(
                f"{wp}.{field} 现值 {cur!r} 不在修正链上（{values!r}）"
                " —— 可能已被他处改动，本脚本拒绝覆盖，请人工裁决"
            )
    return todo, done, bad


def apply_fixes(doc: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    for (wp, field), chain in _chains().items():
        entries = _find_entries(doc, wp)
        if len(entries) != 1:
            continue
        e = entries[0]
        final = chain[-1][1]
        values = [chain[0][0], *(new for _old, new, _why in chain)]
        if e.get(field) != final and e.get(field) in values:
            before_name = e.get("account_name")
            before_wp_name = e.get("wp_name")
            e[field] = list(final) if isinstance(final, list) else final
            # 🔴 只动目标字段：名称本来就是对的，改它会让语义漂移
            assert e.get("account_name") == before_name, "account_name 被误改"
            assert e.get("wp_name") == before_wp_name, "wp_name 被误改"
            changed.append(f"{wp}.{field} = {final!r}")
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
        print(f"\n[OK] 登记的错误均已修正（{len(done)} 项幂等）")
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
