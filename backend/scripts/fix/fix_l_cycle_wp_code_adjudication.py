"""幂等：为 L 循环 entry 补 `workpaper_sync_entry_wp_code_adjudication.json` 条目。

spec: `.kiro/specs/l-cycle-true-adapter-registration`（Task 7 前置）

═══ 为什么需要它 ═══

`fix_projection_first_publication.py`（首版 published representation 的唯一宿主）在
`_adjudicated_wp_codes(entry_id)` 处 fail-closed：entry 不在裁决表里就抛
`ProjectionTargetResolutionError` —— 因为回落启发式产出的正是**幻影码**
（manifest 从宿主 Vue 文件名 CamelCase 抽的 `L1S`，wp_index 零命中）。

⇒ L1 接线前必须先在裁决表登记，否则连 `--check` 只读预演都跑不起来。

用法::

    python backend/scripts/fix/fix_l_cycle_wp_code_adjudication.py --check
    python backend/scripts/fix/fix_l_cycle_wp_code_adjudication.py --apply
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

_L1_WP_INDEX_EVIDENCE = (
    "wp_code=L1「短期借款」4 项目各 1 行未删除，且 file_path 是**真路径**"
    "（`storage/projects/{project_id}/workpapers/L/L1.xlsx`，即整册 13 sheet 的工作簿）。"
    "🔴 `L1-2`「短期借款明细表」虽也有 4 行未删除，但其 file_path 全是**空字符串 `''`**"
    "（不是 NULL）⇒ 索引行非真底稿文件。同理 L1-1 / L1-3~L1-6 各 2 行亦为空串索引行。"
    "🔴 **判据陷阱**：`count(wp.file_path)` 只排除 NULL **不排除空串**，按它判会误认为 "
    "`L1-2` 也有文件、从而把目标码定到一个没有工作簿的索引行上（本条裁决首版即踩过，"
    "改用 `file_path <> ''` 复算后纠正）。"
    "受管 sheet `明细表L1-2` 只是 `L1.xlsx` 里的一张 sheet，不是独立文件 ⇒ "
    "目标码取持有整册文件的 `L1`。`L1S` 是 CamelCase 幻影码（GtL1ShortTermLoans → L1S），"
    "wp_index 零命中（与 D1/D3/D6/D7 的 D1N/D3P/D6C/D7C 同型）。"
)

_L1_STORE_WHY_NULL = (
    "`L1-2-rows` 全库 0 行（明细表从未录入，同 H1-8-rows / D3-det-rows / D6-2-rows "
    "空表单是合法业务事实）⇒ 目标 item 无法定码，本条以 file_path 证据定 `L1`。"
    "🔴 旧位置化键 `L1-det-*`（`L1-det-{rowIndex+1}-{field}`）现算亦为 **0 行**，"
    "故切稳定 rowId 形态零迁移负担。全库 L1 载荷只有 `L1-adj-*` 32 行 + "
    "`L1-chk-conclusion` 1 行，它们属 `审定表L1-1` —— 该表 R7~R11 全是 SUMIF/加总/裸 IF、"
    "无一可输入格，已在契约里登记为 `review.derived_readonly_sheet` 只读投影，不受管。"
)

#: 本轮补录的条目（L2~L8 接线时在此追加；键是 entry_id，消费方按 entry_id 查）。
_ROWS: tuple[dict[str, Any], ...] = (
    {
        "entry_id": "xlsx/gt-l1-short-term-loans",
        "contract_id": "l1.short_term_loans",
        "wp_codes": ["L1"],
        "resolvable_for_provisioning": True,
        "matcher_domain_conflict": None,
        "basis": {
            "heuristic_is_wrong_because": (
                "manifest 从宿主 Vue 文件名 CamelCase 抽出的 L1S 在 wp_index 里 0 命中"
                "（GtL1ShortTermLoans → L1S 是幻影码）"
            ),
            "heuristic_would_say": ["L1S"],
            "managed_excel_name": "明细表L1-2",
            "template_relative_path": "L/L1 短期借款.xlsx",
            "wp_index_evidence": _L1_WP_INDEX_EVIDENCE,
        },
        "store_payload_evidence": {
            "max_payload_bytes": 0,
            "measured_at": "2026-09-28",
            "store_item_id": "L1-2-rows",
            "why_null": _L1_STORE_WHY_NULL,
            "wp_code_with_payload": None,
            "wp_count_with_payload": 0,
        },
    },
    {
        "entry_id": "xlsx/gt-l4-bonds-payable",
        "contract_id": "l4.bonds_payable",
        "wp_codes": ["L4"],
        "resolvable_for_provisioning": True,
        "matcher_domain_conflict": None,
        "basis": {
            "heuristic_is_wrong_because": (
                "manifest 从宿主 Vue 文件名 CamelCase 抽出的 L4B 经 wp_template_finder "
                "单册与 sheet 级解析均零命中（GtL4BondsPayable → L4B 是幻影码）"
            ),
            "heuristic_would_say": ["L4B"],
            "managed_excel_name": "划分为金融负债的其他金融工具明细表L4-3",
            "template_relative_path": "L/L4 应付债券.xlsx",
            "wp_index_evidence": (
                "2026-10-01 现算：wp_code=L4 有 3 份未删除底稿且 file_path 非空"
                "（`storage/projects/005a6f2d…/workpapers/L/L4.xlsx` 等）；受管 sheet 是整册 "
                "16 sheet 工作簿里的一张，不是独立文件 ⇒ 目标码取持有整册文件的 `L4`。"
                "判据用 `COALESCE(file_path,'') <> ''`（L1 裁决记过的空串陷阱）。"
            ),
        },
        "store_payload_evidence": {
            "max_payload_bytes": 0,
            "measured_at": "2026-10-01",
            "store_item_id": "L4-3-rows",
            "why_null": (
                "`L4-3-rows` 是本 spec 新建的键，全库 0 行；旧位置化键 `L4-3-row-*` 亦 0 行 "
                "⇒ 零迁移负担。真库 L4 现有 6 行均为 `l-cycle-canary-e2e` 夹具"
                "（L4-adj-1-* / L4-chk-conclusion / L4-3-note），不属受管表。"
            ),
            "wp_code_with_payload": None,
            "wp_count_with_payload": 0,
        },
    },
    {
        "entry_id": "xlsx/gt-l3-long-term-loans",
        "contract_id": "l3.long_term_loans",
        "wp_codes": ["L3"],
        "resolvable_for_provisioning": True,
        "matcher_domain_conflict": None,
        "basis": {
            "heuristic_is_wrong_because": "manifest 幻影码 L3L 经 wp_template_finder 单册与 sheet 级均零命中",
            "heuristic_would_say": ["L3L"],
            "managed_excel_name": "长期借款检查表L3-9",
            "template_relative_path": "L/L3 长期借款.xlsx",
            "wp_index_evidence": (
                "2026-10-01 现算 wp_code=L3 有 4 份未删除底稿，最早目标 wp=33cfc857；"
                "无 L3-* 子码 working paper，受管 L3-9 是整册内 sheet ⇒ 目标码取 L3。"
            ),
        },
        "store_payload_evidence": {
            "max_payload_bytes": 0,
            "measured_at": "2026-10-01",
            "store_item_id": "L3-L3-9-voucher-rows",
            "why_null": (
                "本 item 真库 0 行；现有 11 条 L3 行 11/11 均为 `l-cycle-canary-e2e` 夹具，"
                "且键属于 adj/blank/note，不属受管表 ⇒ 零迁移负担。"
            ),
            "wp_code_with_payload": None,
            "wp_count_with_payload": 0,
        },
    },
    {
        "entry_id": "xlsx/gt-l2-interest-payable",
        "contract_id": "l2.interest_payable",
        "wp_codes": ["L2"],
        "resolvable_for_provisioning": True,
        "matcher_domain_conflict": None,
        "basis": {
            "heuristic_is_wrong_because": "manifest 幻影码 L2I 经 wp_template_finder 单册与 sheet 级均零命中",
            "heuristic_would_say": ["L2I"],
            "managed_excel_name": "应付利息检查表L2-4",
            "template_relative_path": "L/L2 应付利息.xlsx",
            "wp_index_evidence": (
                "受管 L2-4 是整册 8 sheet 工作簿里的一张，不是独立文件 ⇒ 目标码取持有整册的 L2；"
                "判据用 `COALESCE(file_path,'') <> ''`（L1 空串陷阱）。"
            ),
        },
        "store_payload_evidence": {
            "max_payload_bytes": 0,
            "measured_at": "2026-10-01",
            "store_item_id": "L2-L2-4-voucher-rows",
            "why_null": (
                "本 item 真库 0 行；现有 L2 行均为 `l-cycle-canary-e2e` 夹具（adj/note），"
                "不属受管表 ⇒ 零迁移负担。"
            ),
            "wp_code_with_payload": None,
            "wp_count_with_payload": 0,
        },
    },
    {
        "entry_id": "xlsx/gt-l7-other-noncurrent-liabilities",
        "contract_id": "l7.other_noncurrent_liabilities",
        "wp_codes": ["L7"],
        "resolvable_for_provisioning": True,
        "matcher_domain_conflict": None,
        "basis": {
            "heuristic_is_wrong_because": "manifest 幻影码 L7O 经 wp_template_finder 单册与 sheet 级均零命中（GtL7OtherNoncurrentLiabilities → L7O 是幻影码）",
            "heuristic_would_say": ["L7O"],
            "managed_excel_name": "明细表L7-2",
            "template_relative_path": "L/L7 其他非流动负债.xlsx",
            "wp_index_evidence": (
                "受管 明细表L7-2 是整册 8 sheet 工作簿里的一张（L7 整册唯一的数据录入源，"
                "审定表 L7-1 / 两张附注 / 检查表 L7-4 全部跨 sheet 引用它），不是独立文件 ⇒ "
                "目标码取持有整册文件的 L7；判据用 `COALESCE(file_path,'') <> ''`（L1 空串陷阱）。"
            ),
        },
        "store_payload_evidence": {
            "max_payload_bytes": 0,
            "measured_at": "2026-10-01",
            "store_item_id": "L7-L7-2-full-data",
            "why_null": (
                "本 item 真库 `L7-L7-2-%` 现算 0 行（明细表从未录入，空表单是合法业务事实）；"
                "旧 full-data 用过的 key 字段已收敛到稳定 rowId（newRowIdentity('l72det')），"
                "零迁移负担。真库 L7 载荷仅 5 行 `l-cycle-canary-e2e` 夹具（L7-adj-* / "
                "L7-chk-conclusion），键属 审定表L7-1 相关，不属受管表 L7-2。"
            ),
            "wp_code_with_payload": None,
            "wp_count_with_payload": 0,
        },
    },
    {
        "entry_id": "xlsx/gt-l6-special-payables",
        "contract_id": "l6.special_payables",
        "wp_codes": ["L6"],
        "resolvable_for_provisioning": True,
        "matcher_domain_conflict": None,
        "basis": {
            "heuristic_is_wrong_because": "manifest 幻影码 L6S 经 wp_template_finder 单册与 sheet 级均零命中（GtL6SpecialPayables → L6S 是幻影码）",
            "heuristic_would_say": ["L6S"],
            "managed_excel_name": "明细表L6-2",
            "template_relative_path": "L/L6 专项应付款.xlsx",
            "wp_index_evidence": (
                "受管 明细表L6-2 是整册 9 sheet 工作簿里的一张（L6 整册唯一的数据录入源，"
                "审定表 L6-1 / 两张附注 / 检查表 L6-4 全部跨 sheet 引用它），不是独立文件 ⇒ "
                "目标码取持有整册文件（科目 2711 专项应付款）的 L6；判据用 `COALESCE(file_path,'') <> ''`（L1 空串陷阱）。"
            ),
        },
        "store_payload_evidence": {
            "max_payload_bytes": 0,
            "measured_at": "2026-10-01",
            "store_item_id": "L6-L6-2-rows",
            "why_null": (
                "本 item 真库 `L6-L6-2-%` 现算 0 行（明细表从未录入，空表单是合法业务事实）；"
                "旧 L6-L6-2-rows 用过的 key 字段已收敛到稳定 rowId（newRowIdentity('l62det')），"
                "零迁移负担。真库 L6 载荷仅 5 行 `l-cycle-canary-e2e` 夹具（L6-adj-* / "
                "L6-chk-conclusion），键属 审定表L6-1 相关，不属受管表 L6-2。"
            ),
            "wp_code_with_payload": None,
            "wp_count_with_payload": 0,
        },
    },
    {
        "entry_id": "xlsx/gt-l8-financial-expenses",
        "contract_id": "l8.financial_expenses",
        "wp_codes": ["L8"],
        "resolvable_for_provisioning": True,
        "matcher_domain_conflict": None,
        "basis": {
            "heuristic_is_wrong_because": "manifest 幻影码 L8F 经 wp_template_finder 单册与 sheet 级均零命中（GtL8FinancialExpenses → L8F 是幻影码）",
            "heuristic_would_say": ["L8F"],
            "managed_excel_name": "明细表L8-2",
            "template_relative_path": "L/L8 财务费用.xlsx",
            "wp_index_evidence": (
                "受管 明细表L8-2 是整册 10 sheet 工作簿里的一张（L8 整册唯一的数据录入源，"
                "审定表 L8-1 / 两张附注 / 检查表 L8-6 全部跨 sheet 引用它），不是独立文件 ⇒ "
                "目标码取持有整册文件（科目 6603 财务费用，损益类）的 L8；判据用 "
                "`COALESCE(file_path,'') <> ''`（L1 空串陷阱）。🔴 wp_codes 用整册底稿码 L8"
                "（不是科目码 6603，照 L1~L7 一律用底稿码）。"
            ),
        },
        "store_payload_evidence": {
            "max_payload_bytes": 0,
            "measured_at": "2026-10-01",
            "store_item_id": "L8-2-full-data",
            "why_null": (
                "本 item 真库 `L8-2-%` 现算 0 行（明细表从未录入，空表单是合法业务事实）；"
                "身份字段 key 已收敛到稳定 rowId（newRowIdentity('l82det')，已有不重铸），"
                "旧位置化键 `L8-2-row-%` 亦 0 行 ⇒ 零迁移负担。真库 L8 载荷仅 5 行 "
                "`l-cycle-canary-e2e` 夹具（L8-adj-* / L8-chk-conclusion），键属 审定表L8-1 "
                "相关，不属受管表 L8-2。"
            ),
            "wp_code_with_payload": None,
            "wp_count_with_payload": 0,
        },
    },
    {
        "entry_id": "xlsx/gt-l5-long-term-payables",
        "contract_id": "l5.long_term_payables",
        "wp_codes": ["L5"],
        "resolvable_for_provisioning": True,
        "matcher_domain_conflict": None,
        "basis": {
            "heuristic_is_wrong_because": "manifest 幻影码 L5L 经 wp_template_finder 单册与 sheet 级均零命中（GtL5LongTermPayables → L5L 是幻影码）",
            "heuristic_would_say": ["L5L"],
            "managed_excel_name": "明细表L5-2",
            "template_relative_path": "L/L5 长期应付款.xlsx",
            "wp_index_evidence": (
                "受管 明细表L5-2 是整册 12 sheet 工作簿里的一张（科目 2701 长期应付款），"
                "审定表 L5-1 / 两张附注 / L5-3~L5-7 全部跨 sheet 引用它，不是独立文件 ⇒ "
                "目标码取持有整册文件的 L5；判据用 `COALESCE(file_path,'') <> ''`（L1 空串陷阱）。"
                "🔴 wp_codes 用整册底稿码 L5（不是科目码 2701，照 L1~L8 一律用底稿码）。"
            ),
        },
        "store_payload_evidence": {
            "max_payload_bytes": 0,
            "measured_at": "2026-10-01",
            "store_item_id": "L5-L5-2-rows",
            "why_null": (
                "本 item 真库 `L5-L5-2-rows` 现算 0 行（三区同键，明细表从未录入，空表单是"
                "合法业务事实）；身份字段 key 已收敛到稳定 rowId（newRowIdentity('l52det')，"
                "已有不重铸、历史行补铸 + section 落默认区）⇒ 零迁移负担。真库 L5 载荷仅 "
                "`L5-adj-*` / `L5-*-note` / `L5-chk-conclusion` 等夹具行，属 审定表L5-1 / L5-4 "
                "相关，不属受管表 L5-2。"
            ),
            "wp_code_with_payload": None,
            "wp_count_with_payload": 0,
        },
    },
)


def _digest(adjudications: list[dict[str, Any]]) -> str:
    """与文件里 `adjudication_digest_algorithm` 声明的算法逐字一致。"""
    blob = json.dumps(
        adjudications, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="写盘（默认只读预演）")
    args = ap.parse_args()

    doc = json.loads(ADJ_PATH.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = list(doc.get("adjudications") or [])
    by_id = {str(r.get("entry_id")): i for i, r in enumerate(rows)}

    # 先自检：磁盘 digest 必须与现算一致，否则说明有人手改过而没重算 ⇒ 不在此处顺手掩盖。
    on_disk_digest = str(doc.get("adjudication_digest") or "")
    recomputed = _digest(rows)
    if on_disk_digest != recomputed:
        print(
            f"[error] 磁盘 digest {on_disk_digest} 与现算 {recomputed} 不一致 —— "
            "有人改了 adjudications 却没重算 digest，先修那个再跑本脚本"
        )
        return 2

    added, updated = [], []
    for raw_row in _ROWS:
        # 只把**新条目自身**的键归一成字母序（与既有条目书写风格一致）。
        # 🔴 整份文档**不得** sort_keys 写回 —— 见下方 write 处注释。
        row = json.loads(json.dumps(raw_row, ensure_ascii=False, sort_keys=True))
        eid = str(row["entry_id"])
        if eid in by_id:
            if rows[by_id[eid]] != row:
                rows[by_id[eid]] = row
                updated.append(eid)
        else:
            rows.append(row)
            added.append(eid)

    if not added and not updated:
        print(f"[check] OK 已是目标态（{len(rows)} 条，digest={recomputed}）")
        return 0

    # 🔴 **不排序**：`adjudications` 是 list，digest 算法里的 `sort_keys=True` 只排 dict 的
    # 键、**不改 list 顺序** ⇒ 重排数组会改 digest，并把「加 1 条」的 diff 放大成整文件重写
    # （首版实测 888 行变动，难 review 且无故动了他人条目的相对位置）。新条目一律追加在末尾。
    new_digest = _digest(rows)
    doc["adjudications"] = rows
    doc["adjudication_digest"] = new_digest

    if not args.apply:
        print(
            f"[check] 将新增 {added} / 更新 {updated}；"
            f"条目数 {len(by_id)} → {len(rows)}；digest {recomputed} → {new_digest}"
        )
        print("[check] 一行未写 —— 加 --apply 才落盘")
        return 1

    # 🔴 `write_bytes` 而非 `write_text`：Windows 上后者按 CRLF 写回（原文件是纯 LF）。
    # 🔴 **不传 `sort_keys`**：既有条目的嵌套键是人工书写顺序（不是字母序），
    # 整份文档 sort_keys 写回会把 D3/F2/F3/F4/F5 等**他人条目**的 `note` /
    # `wp_count_with_payload` 等键位置全部重排 —— 首版实测多出 20 行无谓删改，
    # 等于在一次「加 1 条」的提交里动了别人的数据。
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    ADJ_PATH.write_bytes(text.encode("utf-8"))
    print(
        f"[apply] 新增 {added} / 更新 {updated}；条目数 {len(rows)}；digest={new_digest}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
