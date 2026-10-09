"""幂等：为 G 循环 17 条 entry 补 `workpaper_sync_entry_wp_code_adjudication.json` 条目。

spec: `.kiro/specs/g-cycle-sync-foundation-and-first-canary`（Task 1）

═══ 为什么是 17 条而不是 tasks.md 写的 13 条 ═══

tasks.md Task 1 写「新增 **13 条** G 条目（按册，G4/G6 各一条覆盖三 entry）」。
本脚本按 **17 条（一 entry 一条）** 交付，理由三条，均可现算复核：

1. **文件的键是 `entry_id`，消费方按 `entry_id` 查**：
   `projection_target_resolution.py` / `fix_task76_provision_projection_definitions.py`
   都是 `adjudication.get(entry_id)`。按册写 13 条会让 `gt-g4-bond-investment-sppi` /
   `-ecl` / `gt-g6-other-bond-sppi` / `-investment-ecl` 四条在 provisioning 时查不到裁决
   ⇒ 落回那条被 Task 76 判定为错的启发式（产出 0 命中的幻影码）。
2. **F2 先例就是一 entry 一条**：四条共用 wp_code `F2` 的 entry 各有独立条目，
   彼此在 `matcher_domain_conflict.conflicting_entries` 里互相列出。G4/G6 与它同型。
3. **GC-1 明令 pointer 按 `entry_id`**（BP-8 的解法本体）。按册写等于在这份裁决表里
   重新引入「按册/按码」的聚合，与 GC-1 自相矛盾。

⇒ 偏差已登记在 `evidence/task1-slice-review-and-adjudication.md`，不静默改口径。

用法：
    python backend/scripts/fix/fix_g_cycle_wp_code_adjudication.py --check
    python backend/scripts/fix/fix_g_cycle_wp_code_adjudication.py --apply
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
ADJ_PATH = BACKEND / "data" / "workpaper_sync_entry_wp_code_adjudication.json"

#: 共用册的两组（GC-1 / BP-8）：一册三 entry，`wp_code_pattern` 同值。
_SHARED_WORKBOOKS: dict[str, tuple[str, ...]] = {
    "G4": (
        "xlsx/gt-g4-bond-investment-main",
        "xlsx/gt-g4-bond-investment-sppi",
        "xlsx/gt-g4-bond-investment-ecl",
    ),
    "G6": (
        "xlsx/gt-g6-other-bond-main",
        "xlsx/gt-g6-other-bond-sppi",
        "xlsx/gt-g6-other-bond-investment-ecl",
    ),
}

_BP8_VERBATIM = (
    "`G4 债权投资.xlsx` 与 `G6 其他债权投资.xlsx` 各服务 3 条 entry，而它们的 "
    "wp_code_patterns 分别同为 `G4B` / `G6O`。若 representation entry_id 只用 wp_code"
    "（或 wp_code_pattern），G4 的三条与 G6 的三条会各自互相顶掉对方的 entry pointer / "
    "representation generation。"
)

_GC1_RESOLUTION = (
    "GC-1：entry pointer / working_paper_sync_entry_state 主键 / representation generation "
    "一律用 entry_id；matcher 域用互斥 sheet_keys（沿用 F2-H1 解法，运行时走 "
    "resolve_for_entry(entry_id)）；模板归属用 belongs_to_entries（复数），"
    "守卫断言「owner 模板并集 == entry 全集」且「每条 entry 恰被一张模板认领」。"
)

#: 17 条 entry 的逐条事实。全部取自：
#:   * `workpaper_sync_g_cycle_manifest_slice.json`（entry_id / wp_code_pattern / template_ref /
#:     html_counterpart.transport_key_shape）
#:   * 真库 `checklist_responses` × `working_paper` × `wp_index`（store_payload_evidence，2026-09-27 实测）
#:   * `wp_index`（真码行数 / 幻影码 0 命中，2026-09-27 实测）
#:
#: 🔴 `store_item_id` 一律取 slice 的 `transport_key_shape`（primary managed table），
#:    **不按 sheet 号推演**（RG-9/GC-6：键在生产源码有多处重复声明，按值取才不会漂）。
_ENTRIES: tuple[dict[str, Any], ...] = (
    {
        "entry_id": "xlsx/gt-g1-trading-financial-assets",
        "contract_id": "g1.trading_financial_assets_detail",
        "wp_code": "G1",
        "phantom": "G1T",
        "template": "G/G1 交易性金融资产.xlsx",
        "managed_excel_name": "明细表G1-2",
        "store_item_id": "G1-2-rows",
        "payload_remark": 0,
        "payload_conclusion": 0,
        "payload_note": (
            "G1-2-rows 真库 0 行（G1 现有 5 键均为其它 sheet：G1-14-id-result 10+7 / "
            "G1-8-sub-portfolios 102 / G1-note-listed-store 4899 / G1-note-soe-rows 597+581）"
            "⇒ 主受管表空载荷，受管前须 seed。"
        ),
    },
    {
        "entry_id": "xlsx/gt-g2-interest-receivable",
        "contract_id": "g2.interest_receivable_detail",
        "wp_code": "G2",
        "phantom": "G2I",
        "template": "G/G2 应收利息.xlsx",
        "managed_excel_name": "明细表G2-2",
        "store_item_id": "G2-2-detail-rows",
        "payload_remark": 475,
        "payload_conclusion": 0,
        "payload_note": (
            "🔴 canary：真库有 475 B 真实 remark 载荷、conclusion 为 0 ⇒ remark_only 形态被"
            "字节实证（GC-5）。裁决 GF-H2：不交付 seed，但验收判据须断言行数 > 0 且来自真库。"
        ),
    },
    {
        "entry_id": "xlsx/gt-g3-dividend-receivable",
        "contract_id": "g3.dividend_receivable_detail",
        "wp_code": "G3",
        "phantom": "G3D",
        "template": "G/G3 应收股利.xlsx",
        "managed_excel_name": "明细表G3-2",
        "store_item_id": "G3-2-detail-rows",
        "payload_remark": 0,
        "payload_conclusion": 0,
        "payload_note": (
            "G3 全册真库仅 12 B（G3-5-aging-custom-segments 2 + G3-5-aging-preset 10），"
            "**是 G 循环载荷最少的一册**；主受管表 G3-2-detail-rows 0 行。"
        ),
    },
    {
        "entry_id": "xlsx/gt-g4-bond-investment-main",
        "contract_id": "g4.bond_main",
        "wp_code": "G4",
        "phantom": "G4B",
        "template": "G/G4 债权投资.xlsx",
        "managed_excel_name": "明细表G4-2",
        "store_item_id": "G4-2-rows",
        "payload_remark": 0,
        "payload_conclusion": 0,
        "payload_note": (
            "G4-2-rows 真库 0 行；G4 册唯一载荷是 G4-4-interest-calc(445 B)，不属本受管表。"
        ),
    },
    {
        "entry_id": "xlsx/gt-g4-bond-investment-sppi",
        "contract_id": "g4.sppi_inventory",
        "wp_code": "G4",
        "phantom": "G4B",
        "template": "G/G4 债权投资.xlsx",
        "managed_excel_name": "有价证券盘点表G4-7",
        "store_item_id": "G4-7-items",
        "payload_remark": 0,
        "payload_conclusion": 0,
        "payload_note": "G4-7-items 真库 0 行 ⇒ 受管前须 seed。",
    },
    {
        "entry_id": "xlsx/gt-g4-bond-investment-ecl",
        "contract_id": "g4.ecl_stage",
        "wp_code": "G4",
        "phantom": "G4B",
        "template": "G/G4 债权投资.xlsx",
        "managed_excel_name": "债权投资三阶段划分G4-9",
        "store_item_id": "G4-9-rows",
        "payload_remark": 0,
        "payload_conclusion": 0,
        "payload_note": (
            "G4-9-rows 真库 0 行。🔴 该表 max_column=16384(XFD) 且是转置形态 ⇒ "
            "走 TransposedSheetSpec，UUID 放有效内容列 +1（裁决 G46-H3）。"
        ),
    },
    {
        "entry_id": "xlsx/gt-g5-long-term-receivable",
        "contract_id": "g5.long_term_receivable_detail",
        "wp_code": "G5",
        "phantom": "G5L",
        "template": "G/G5 长期应收款.xlsx",
        "managed_excel_name": "余额明细表G5-2",
        "store_item_id": "G5-2-rows",
        "payload_remark": 572,
        "payload_conclusion": 572,
        "payload_note": (
            "🔴 全 G 循环唯一被字节数证实的 dual_write：G5-2-rows 572+572、G5-3-rows 254+254、"
            "G5-4-rows 1209+1209、G5-5-rows 798+798、G5-2-aging-preset 9+9 —— 五键 remark 与 "
            "conclusion 字节完全相等。G5 册合计 8 行 / remark 12952 B + conclusion 2844 B，"
            "是 G 循环载荷最多的一册。"
        ),
    },
    {
        "entry_id": "xlsx/gt-g6-other-bond-main",
        "contract_id": "g6.other_bond_main",
        "wp_code": "G6",
        "phantom": "G6O",
        "template": "G/G6 其他债权投资.xlsx",
        "managed_excel_name": "明细表G6-2",
        "store_item_id": "G6-2-rows",
        "payload_remark": 0,
        "payload_conclusion": 2,
        "payload_note": (
            "🔴 G4/G6 六条主表里**唯一有行**的：remark 0 / conclusion 2（= 空数组 `[]` 只落 "
            "conclusion）⇒ 判据须覆盖「空数组落 conclusion」形态，不得假设 remark 非空。"
        ),
    },
    {
        "entry_id": "xlsx/gt-g6-other-bond-sppi",
        "contract_id": "g6.sppi_fair_value",
        "wp_code": "G6",
        "phantom": "G6O",
        "template": "G/G6 其他债权投资.xlsx",
        "managed_excel_name": "公允价值测试表G6-5",
        "store_item_id": "G6-5-fair-value-data",
        "payload_remark": 0,
        "payload_conclusion": 0,
        "payload_note": (
            "G6-5-fair-value-data 真库 0 行。🔴 BP-7 唯一有正文证据的 entry："
            "行身份会退化成数组下标（useG6SppiFairValue.ts#L331 + #L128 的 `fv-${Date.now()}-${seq}` 回退）"
            "⇒ 受管与发布 contract 之前必修。"
        ),
    },
    {
        "entry_id": "xlsx/gt-g6-other-bond-investment-ecl",
        "contract_id": "g6.ecl_stage",
        "wp_code": "G6",
        "phantom": "G6O",
        "template": "G/G6 其他债权投资.xlsx",
        "managed_excel_name": "其他债权投资三阶段划分G6-11",
        "store_item_id": "G6-11-rows",
        "payload_remark": 0,
        "payload_conclusion": 0,
        "payload_note": (
            "G6-11-rows 真库 0 行。🔴 同 G4-9：max_column=16384 + 转置形态；"
            "另 R9 是区标题「（一）信用风险是否显著增加」，表头在 **R10**。"
        ),
    },
    {
        "entry_id": "xlsx/gt-g8-other-equity-instruments",
        "contract_id": "g8.other_equity_detail",
        "wp_code": "G8",
        "phantom": "G8O",
        "template": "G/G8 其他权益工具投资.xlsx",
        "managed_excel_name": "明细表G8-2",
        "store_item_id": "G8-detail-rows",
        "payload_remark": 2,
        "payload_conclusion": 0,
        "payload_note": (
            "G8-detail-rows 真库 2 B（空数组）。另有 G8-adj-tb-writeback 40 B —— "
            "🔴 该键在前端源码按字面量 grep 零命中（RG-10 模板化拼接键），普查须按值匹配。"
            "行身份字段是 `rowId`（不是 `id`）。"
        ),
    },
    {
        "entry_id": "xlsx/gt-g9-other-noncurrent-financial",
        "contract_id": "g9.other_noncurrent_detail",
        "wp_code": "G9",
        "phantom": "G9O",
        "template": "G/G9 其他非流动金融资产.xlsx",
        "managed_excel_name": "明细表G9-2",
        "store_item_id": "G9-detail-rows",
        "payload_remark": 605,
        "payload_conclusion": 0,
        "payload_note": (
            "G9-detail-rows 真库两行：一行 605 B（真实载荷，G 循环单键最大的主受管表载荷）、"
            "一行 2 B（空数组）。另 G9-adj-tb-writeback 40 B 同属 RG-10 模板化拼接键。"
            "行身份字段是 `rowId`。"
        ),
    },
    {
        "entry_id": "xlsx/gt-g10-trading-financial-liabilities",
        "contract_id": "g10.trading_liabilities_detail",
        "wp_code": "G10",
        "phantom": "G10T",
        "template": "G/G10 交易性金融负债.xlsx",
        "managed_excel_name": "明细表G10-2",
        "store_item_id": "G10-detail-rows",
        "payload_remark": 2,
        "payload_conclusion": 0,
        "payload_note": (
            "G10-detail-rows 真库 2 B（空数组）。🔴 该键是 BP-10 第二严重的重复声明"
            "（6 处），发布 per-entry contract 前须收敛。行身份字段是 `rowId`。"
        ),
    },
    {
        "entry_id": "xlsx/gt-g11-investment-income",
        "contract_id": "g11.investment_income_detail",
        "wp_code": "G11",
        "phantom": "G11I",
        "template": "G/G11 投资收益.xlsx",
        "managed_excel_name": "明细分析表G11-2",
        "store_item_id": "G11-detail-rows",
        "payload_remark": 2,
        "payload_conclusion": 0,
        "payload_note": (
            "G11-detail-rows 真库 2 B（空数组）；同册 G11-adj-rows 有 2480 B 真实载荷。"
            "另 G11-adj-tb-writeback 46 B 属 RG-10 模板化拼接键。"
            "🔴 损益类（科目 6111）⇒ TB 口径是**本期发生额**不是期末余额。"
            "受管表 明细分析表G11-2 自带 44 格裸 IF（G 循环主受管表里最多）。"
        ),
    },
    {
        "entry_id": "xlsx/gt-g12-net-hedge-gains",
        "contract_id": "g12.net_hedge_detail",
        "wp_code": "G12",
        "phantom": "G12N",
        "template": "G/G12 净敞口套期收益.xlsx",
        "managed_excel_name": "明细表G12-2",
        "store_item_id": "G12-hedge-detail-rows",
        "payload_remark": 2,
        "payload_conclusion": 0,
        "payload_note": (
            "G12-hedge-detail-rows 真库 2 B（空数组）。🔴 损益类（科目 6103）⇒ 发生额口径。"
            "该表 G 列是布尔校验列 `=D9=SUM(E9:F9)`，extract 读回布尔值须容错。"
            "行身份字段是 `rowId`。"
        ),
    },
    {
        "entry_id": "xlsx/gt-g13-fair-value-changes",
        "contract_id": "g13.fair_value_changes_detail",
        "wp_code": "G13",
        "phantom": "G13F",
        "template": "G/G13 公允价值变动收益.xlsx",
        "managed_excel_name": "明细表G13-2",
        "store_item_id": "G13-detail-rows",
        "payload_remark": 2,
        "payload_conclusion": 0,
        "payload_note": (
            "G13-detail-rows 真库 2 B（空数组）。🔴 损益类（科目 6101）⇒ 发生额口径。"
            "🔴 prefill 块 [169] 的 sheet 名曾错写成 `明细分析表G13-2`（真名 `明细表G13-2`），"
            "本 spec Task 7 已修 + 补 sheet 存在性守卫。K 列是布尔校验列 `=J11=D11`。"
            "行身份字段是 `rowId`。"
        ),
    },
    {
        "entry_id": "xlsx/gt-g14-credit-impairment-loss",
        "contract_id": "g14.credit_impairment_detail",
        "wp_code": "G14",
        "phantom": "G14C",
        "template": "G/G14 信用减值损失.xlsx",
        "managed_excel_name": "明细表G14-2",
        "store_item_id": "G14-detail-rows",
        "payload_remark": 2,
        "payload_conclusion": 0,
        "payload_note": (
            "G14-detail-rows 真库 2 B（空数组）。🔴 损益类（科目 6702）⇒ 发生额口径。"
            "🔴 prefill 块 [170] 同 G13 错名（真名 `明细表G14-2`），Task 7 已修。"
            "🔴 行身份字段是 **`rowKey`**（kind=stable_template_row_key）—— 全 G 循环唯一，"
            "照抄 F 的 `row_identity_key in ('rowId','id')` 白名单会把它判违规，"
            "而它恰是最稳的一族（源模板固定行集）。L 列是布尔校验列 `=D11=K11`。"
        ),
    },
)


def _build_adjudication(spec: dict[str, Any]) -> dict[str, Any]:
    wp_code = spec["wp_code"]
    shared = _SHARED_WORKBOOKS.get(wp_code)
    conflict: dict[str, Any] | None = None
    if shared is not None:
        others = [e for e in shared if e != spec["entry_id"]]
        # 🔴 键按字母序写入：本文件既有形态是 indent=2 / sort_keys=False 且插入序恰为字母序，
        #    乱序会让 round-trip 判据（json.dumps 逐字节复现原文）失败。
        conflict = {
            "belongs_to_entries": list(shared),
            "bp8_verbatim": _BP8_VERBATIM,
            "conflicting_entries": others,
            "error": "RG-3 MatcherOverlapError",
            "resolution": _GC1_RESOLUTION,
            "why": (
                f"一册服务 3 条 entry（{spec['template']}），三条的 wp_code_pattern 同为 "
                f"`{spec['phantom']}` ⇒ BP-8。FC-3「一 entry 恰一 template_ref」的**单射在 G 不成立**，"
                "改为满射 + 唯一认领。"
            ),
        }

    payload_bytes = max(int(spec["payload_remark"]), int(spec["payload_conclusion"]))
    return {
        "basis": {
            "heuristic_is_wrong_because": (
                f"manifest 的 `{spec['phantom']}` 是 CamelCase 启发式产物，在 wp_index **0 命中**"
                f"（幻影码，FC-2，2026-09-27 现算）；真码 `{wp_code}` 在 wp_index 有活行。"
            ),
            "heuristic_would_say": [spec["phantom"]],
            "managed_excel_name": spec["managed_excel_name"],
            "template_relative_path": spec["template"],
            "wp_index_evidence": (
                f"wp_code={wp_code} 在 wp_index 有活行（is_deleted=false），wp_name 唯一；"
                f"该 entry 的全部 store 键（含 {spec['store_item_id']}）在 checklist_responses × "
                f"working_paper × wp_index 上全部落在父码 {wp_code}，无一落在子码或幻影码。"
            ),
        },
        "contract_id": spec["contract_id"],
        "entry_id": spec["entry_id"],
        "matcher_domain_conflict": conflict,
        "resolvable_for_provisioning": True,
        "store_payload_evidence": {
            "conclusion_bytes": int(spec["payload_conclusion"]),
            "max_payload_bytes": payload_bytes,
            "measured_at": "2026-09-27",
            "note": spec["payload_note"],
            "remark_bytes": int(spec["payload_remark"]),
            "store_item_id": spec["store_item_id"],
            "wp_code_with_payload": wp_code if payload_bytes else None,
            "wp_count_with_payload": 1 if payload_bytes else 0,
        },
        "wp_codes": [wp_code],
    }


def _digest(adjudications: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        json.dumps(
            adjudications, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="只报欠账，不写盘")
    g.add_argument("--apply", action="store_true", help="写盘")
    args = ap.parse_args()

    raw = ADJ_PATH.read_text(encoding="utf-8")
    doc = json.loads(raw)
    adjudications: list[dict[str, Any]] = doc["adjudications"]
    existing = {a["entry_id"]: a for a in adjudications}

    wanted = {s["entry_id"]: _build_adjudication(s) for s in _ENTRIES}

    missing = [k for k in wanted if k not in existing]
    stale = [k for k, v in wanted.items() if k in existing and existing[k] != v]

    print(f"G entry 目标条目数: {len(wanted)}（一 entry 一条，见模块 docstring）")
    print(f"缺失: {len(missing)}　需更新: {len(stale)}")
    for k in missing:
        print(f"  + {k}")
    for k in stale:
        print(f"  ~ {k}")

    if not missing and not stale:
        print("0 项欠账，无需修改")
        return 0

    if args.check:
        print(f"共 {len(missing) + len(stale)} 项欠账（--apply 写盘）")
        return 1

    for k, v in wanted.items():
        if k in existing:
            adjudications[adjudications.index(existing[k])] = v
        else:
            adjudications.append(v)

    doc["adjudication_digest"] = _digest(adjudications)
    # 🔴 口径逐字对齐既有文件（实测 indent=2 / sort_keys=False 能逐字节复现原文）——
    #    该文件被多 spec 共享，换缩进或开 sort_keys 会把整文件重排、与并发会话互相回退。
    ADJ_PATH.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    print(f"已写盘；新 digest = {doc['adjudication_digest']}")
    print(f"adjudications 总数 = {len(adjudications)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
