"""裁决表两类欠账一次补齐：13 条已交付却从未登记的 entry + 9 条批量 provision 写下的占位依据。

spec: `.kiro/specs/writeback-followup-issue-closure`（R12 · Property 36 / task76 结构判据）

═══ 一、缺行（只追加）═══

J2 / J3 / K2~K7 / M6 / N1 / N2 / N3 / N5 随 J2J3 / `k-cycle-batch-2026-10-07` /
`n-cycle-continuation-2026-10-08` / `m2-m3-m4-m7-m10-bidirectional-pipeline` 进了交付台账，裁决表
一条没加（git 史上从未出现过）⇒ 首版发布宿主 `_adjudicated_wp_codes(entry_id)` 对它们
fail-closed，Property 36 自那时起「只比对了 76 / 89」。provider 的 `WP_CODES` 是 matcher 域的
CamelCase 幻影码（K2O / N1D / M6R …，wp_index 零命中），不能当目标码。

═══ 二、占位依据（只改 basis / store_payload_evidence，wp_codes 原样）═══

c450c3fbf（批量 provision）给 C2 / K1 / K8~K13 写的依据是占位：模板路径是不存在的
「…调整核查表.xlsx」、受管 sheet 填的是整册名；E1 的受管 sheet 同样填成整册名 ⇒
`test_task76_wp_code_adjudication` 的两条结构判据（模板在盘上 / 受管 sheet 在模板里）
自那时起红。I1~I6 / J1 的占位由各自的 cycle 脚本恢复评审版，不在这里。只改「当前确实是
已知坏形态」的行：不是就报错退出，不覆盖（覆盖评审记录 = 再造一次 c450c3fbf）。

═══ 依据（2026-10-24 真库只读现查，口径 `COALESCE(file_path,'') <> ''`）═══

目标码 = 持有整册权威模板文件的真码；有 current published representation 的，
`working_paper_sync_entry_state` 指向的底稿 wp_code 与裁决码逐条相等；受管 store item 全库 0 行
（M6 例外见其条目）。digest 自检 / 追加不重排 / LF 写回三条纪律同 L / N 脚本。

用法::

    python backend/scripts/fix/fix_wp_code_adjudication_backfill.py           # 只读预演
    python backend/scripts/fix/fix_wp_code_adjudication_backfill.py --apply
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
ADJ_PATH = BACKEND / "data" / "workpaper_sync_entry_wp_code_adjudication.json"
TEMPLATE_ROOT = BACKEND / "wp_templates"
MEASURED_AT = "2026-10-24"
_PLACEHOLDER_NOTE = "批量 provision 补条目"


def _evidence(*, code: str, wp_rows: int, wp_files: int, managed: str, template: str,
              published: bool, phantom: str | None) -> str:
    files = (f"未删除底稿 {wp_rows} 份且 file_path 全部非空真路径" if wp_rows == wp_files
             else f"未删除底稿 {wp_rows} 份、其中 {wp_files} 份 file_path 非空")
    pointer = (f"本 entry 的 current published representation 落在 wp_code={code} 的底稿上"
               "（`working_paper_sync_entry_state` 1 行）。" if published
               else "本 entry 尚无 published representation（`working_paper_sync_entry_state` 0 行）。")
    tail = f"`{phantom}` 是 CamelCase 幻影码，wp_index 零命中。" if phantom else ""
    return (f"{MEASURED_AT} 现算：wp_code={code} {files}（整册工作簿）；受管 sheet `{managed}` 是 "
            f"`{template}` 里的一张 sheet ⇒ 目标码取持有整册文件的 `{code}`。{pointer}{tail}")


def _empty_store(store_item: str | None) -> dict[str, Any]:
    return {
        "max_payload_bytes": 0,
        "measured_at": MEASURED_AT,
        "store_item_id": store_item,
        "why_null": (f"`{store_item}` 全库 0 行（明细从未录入，空表单是合法业务事实）⇒ 以 file_path 证据定码"
                     if store_item else "provider 无单一受管 store item（多码控制测试宿主）；以 file_path 证据定码"),
        "wp_code_with_payload": None,
        "wp_count_with_payload": 0,
    }


def _basis(*, code: str, phantom: str | None, managed: str, template: str, wp_rows: int,
           wp_files: int, published: bool) -> dict[str, Any]:
    return {
        "heuristic_is_wrong_because": (
            f"manifest 从宿主 Vue 文件名 CamelCase 抽出的 {phantom} 在 wp_index 里 0 命中（幻影码）"
            if phantom else "manifest 没有可用的 wp_code_patterns（多码宿主），不能回落启发式"
        ),
        "heuristic_would_say": [phantom] if phantom else [],
        "managed_excel_name": managed,
        "template_relative_path": template,
        "wp_index_evidence": _evidence(code=code, wp_rows=wp_rows, wp_files=wp_files, managed=managed,
                                       template=template, published=published, phantom=phantom),
    }


def _new_row(*, entry_id: str, contract_id: str, code: str, phantom: str, managed: str, template: str,
             store_item: str, wp_files: int, published: bool, store: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "entry_id": entry_id,
        "contract_id": contract_id,
        "wp_codes": [code],
        "resolvable_for_provisioning": True,
        "matcher_domain_conflict": None,
        "basis": _basis(code=code, phantom=phantom, managed=managed, template=template,
                        wp_rows=wp_files, wp_files=wp_files, published=published),
        "store_payload_evidence": store or _empty_store(store_item),
    }


_M6_STORE = {
    "max_payload_bytes": 12,
    "measured_at": MEASURED_AT,
    "store_item_id": "M6-",
    "why_null": None,
    "wp_code_with_payload": "M6",
    "wp_count_with_payload": 3,
    "note": "前缀族 `M6-{sheet}-{field}` 只有 `M6-1-tb-amount`（审定表 M6-1 的试算取数，3 份底稿、≤12 B）；"
            "受管 `明细表M6-2` 的 `M6-2-*` 全库 0 行",
}

#: 一、缺行（只追加）
_MISSING: tuple[dict[str, Any], ...] = (
    _new_row(entry_id="xlsx/j2/gt-j2-defined-benefit-plan", contract_id="j2.defined_benefit_detail", code="J2",
             phantom="J2D", managed="明细表J2-2", template="J/J2 长期应付职工薪酬-设定受益计划净资产.xlsx",
             store_item="J2-2-main", wp_files=4, published=False),
    _new_row(entry_id="xlsx/j3/gt-j3-share-based-payment", contract_id="j3.share_based_payment_detail", code="J3",
             phantom="J3S", managed="股份支付情况表J3-1", template="J/J3 股份支付.xlsx",
             store_item="J3-1-plans", wp_files=5, published=False),
    _new_row(entry_id="xlsx/gt-k2-other-current-assets", contract_id="k2.other_current_assets_adjustment", code="K2",
             phantom="K2O", managed="调整分录汇总K2-3", template="K/K2 其他流动资产.xlsx",
             store_item="K2-3-adj-entries", wp_files=5, published=True),
    _new_row(entry_id="xlsx/gt-k3-other-payables", contract_id="k3.other_payables_adjustment", code="K3",
             phantom="K3O", managed="调整分录汇总K3-3", template="K/K3 其他应付款.xlsx",
             store_item="K3-3-adj-entries", wp_files=5, published=True),
    _new_row(entry_id="xlsx/gt-k4-other-current-liabilities", contract_id="k4.other_current_liabilities_adjustment",
             code="K4", phantom="K4O", managed="调整分录汇总 K4-3", template="K/K4 其他流动负债.xlsx",
             store_item="K4-3-adj-entries", wp_files=4, published=True),
    _new_row(entry_id="xlsx/gt-k5-provisions", contract_id="k5.provisions_adjustment", code="K5",
             phantom="K5P", managed="调整分录汇总 K5-3", template="K/K5 预计负债.xlsx",
             store_item="K5-3-entries", wp_files=5, published=True),
    _new_row(entry_id="xlsx/gt-k6-held-for-sale", contract_id="k6.held_for_sale_adjustment", code="K6",
             phantom="K6H", managed="调整分录汇总 K6-3", template="K/K6 持有待售资产和负债.xlsx",
             store_item="K6-3-adj-entries", wp_files=4, published=True),
    _new_row(entry_id="xlsx/gt-k7-deferred-income", contract_id="k7.deferred_income_adjustment", code="K7",
             phantom="K7D", managed="调整分录汇总K7-3", template="K/K7 递延收益.xlsx",
             store_item="K7-3-adj-entries", wp_files=5, published=True),
    _new_row(entry_id="xlsx/gt-m6-retained-earnings", contract_id="m6.retained_earnings", code="M6",
             phantom="M6R", managed="明细表M6-2", template="M/M6 未分配利润.xlsx",
             store_item="M6-", wp_files=4, published=True, store=_M6_STORE),
    _new_row(entry_id="xlsx/gt-n1-deferred-tax-assets", contract_id="n1.deferred_tax_assets", code="N1",
             phantom="N1D", managed="递延所得税资产明细表N1-2", template="N/N1 递延所得税资产.xlsx",
             store_item="N1-2-rows", wp_files=5, published=True),
    _new_row(entry_id="xlsx/gt-n2-taxes-payable", contract_id="n2.taxes_payable", code="N2",
             phantom="N2T", managed="应交税费明细表N2-2", template="N/N2 应交税费.xlsx",
             store_item="N2-2-rows", wp_files=5, published=True),
    _new_row(entry_id="xlsx/gt-n3-deferred-tax-liabilities", contract_id="n3.deferred_tax_liabilities", code="N3",
             phantom="N3D", managed="递延所得税负债明细表N3-2", template="N/N3 递延所得税负债.xlsx",
             store_item="N3-2-rows", wp_files=4, published=True),
    _new_row(entry_id="xlsx/gt-n5-income-tax-expense", contract_id="n5.income_tax_expense", code="N5",
             phantom="N5I", managed="所得税费用明细表N5-2", template="N/N5 所得税费用.xlsx",
             store_item="N5-2-rows", wp_files=4, published=True),
)

#: 二、占位依据修复：entry_id → (裁决码（必须与现行相等）, 幻影码, 受管 sheet, 模板, store item, 未删底稿, 有文件, 已发布)
_REPAIRS: dict[str, tuple[Any, ...]] = {
    "xlsx/gt-c-control-test": ("C2", None, "C2控制测试汇总表", "C/C2 销售循环控制测试.xlsx", None, 4, 4, True),
    "xlsx/gt-e1-monetary-fund": ("E1", "E1M", "现金明细表E1-2",
                                 "E/E1-1至E1-11 货币资金- 审定表明细表（Leap-常规程序）.xlsx",
                                 "E1-cash-detail-rows", 7, 2, True),
    "xlsx/gt-k1-other-receivables": ("K1", "K1O", "坏账准备转回（收回）、核销检查表K1-9", "K/K1 其他应收款.xlsx",
                                     "K1-9-writeoff", 5, 5, True),
    "xlsx/gt-k8-selling-expenses": ("K8", "K8S", "调整分录汇总K8-3", "K/K8 销售费用.xlsx", "K8-3-adj-entries", 5, 5, True),
    "xlsx/gt-k9-admin-expenses": ("K9", "K9A", "调整分录汇总K9-3", "K/K9 管理费用.xlsx", "K9-3-adj-entries", 4, 4, True),
    "xlsx/gt-k10-other-income": ("K10", "K10O", "调整分录汇总K10-3", "K/K10 其他收益.xlsx", "K10-3-entries", 5, 5, False),
    "xlsx/gt-k11-asset-impairment-loss": ("K11", "K11A", "调整分录汇总K11-3", "K/K11 资产减值损失.xlsx",
                                          "K11-3-adj-entries", 5, 5, True),
    "xlsx/gt-k12-non-operating-income": ("K12", "K12N", "调整分录汇总K12-3", "K/K12 营业外收入.xlsx",
                                         "K12-3-rows", 4, 4, True),
    "xlsx/gt-k13-non-operating-expense": ("K13", "K13N", "调整分录汇总K13-3", "K/K13 营业外支出.xlsx",
                                          "K13-3-adj-entries", 5, 5, True),
}


def _digest(adjudications: list[dict[str, Any]]) -> str:
    """与文件里 `adjudication_digest_algorithm` 声明的算法逐字一致。"""
    blob = json.dumps(adjudications, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _basis_is_broken(row: dict[str, Any]) -> bool:
    """已知坏形态：批量占位注记，或模板不在盘上，或受管 sheet 不在模板里（task76 的两条结构判据）。"""
    import openpyxl

    if (row.get("store_payload_evidence") or {}).get("note") == _PLACEHOLDER_NOTE:
        return True
    basis = row.get("basis") or {}
    path = TEMPLATE_ROOT / str(basis.get("template_relative_path") or "")
    if not path.is_file():
        return True
    wb = openpyxl.load_workbook(path, read_only=True)
    try:
        return basis.get("managed_excel_name") not in wb.sheetnames
    finally:
        wb.close()


def _repaired(row: dict[str, Any], spec: tuple[Any, ...]) -> dict[str, Any]:
    code, phantom, managed, template, store_item, wp_rows, wp_files, published = spec
    fixed = dict(row)
    fixed["basis"] = _basis(code=code, phantom=phantom, managed=managed, template=template,
                            wp_rows=wp_rows, wp_files=wp_files, published=published)
    fixed["store_payload_evidence"] = _empty_store(store_item)
    return json.loads(json.dumps(fixed, ensure_ascii=False, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="写盘（默认只读预演）")
    args = ap.parse_args(argv)

    doc = json.loads(ADJ_PATH.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = list(doc.get("adjudications") or [])
    index = {str(r.get("entry_id")): i for i, r in enumerate(rows)}
    recomputed = _digest(rows)
    if str(doc.get("adjudication_digest") or "") != recomputed:
        print(f"[error] 磁盘 digest 与现算 {recomputed} 不一致 —— 先修那个再跑本脚本")
        return 2

    added: list[str] = []
    for raw_row in _MISSING:
        row = json.loads(json.dumps(raw_row, ensure_ascii=False, sort_keys=True))
        eid = str(row["entry_id"])
        if eid not in index:
            rows.append(row)
            added.append(eid)
        elif rows[index[eid]] != row:
            print(f"[error] {eid} 已在裁决表里且内容不同 —— 缺行补录只追加，请人工核对")
            return 2

    repaired: list[str] = []
    for eid, spec in _REPAIRS.items():
        if eid not in index:
            print(f"[error] {eid} 不在裁决表里 —— 依据修复只改既有条目")
            return 2
        current = rows[index[eid]]
        if list(current.get("wp_codes") or []) != [spec[0]]:
            print(f"[error] {eid} 现行 wp_codes={current.get('wp_codes')} 与修复假设 {[spec[0]]} 不符 —— 不改")
            return 2
        target = _repaired(current, spec)
        if current == target:
            continue
        if not _basis_is_broken(current):
            print(f"[error] {eid} 的依据不是已知坏形态却与目标不同 —— 可能是评审版，不覆盖")
            return 2
        rows[index[eid]] = target
        repaired.append(eid)

    if not added and not repaired:
        print(f"[check] OK 已是目标态（{len(rows)} 条，digest={recomputed}）")
        return 0
    new_digest = _digest(rows)
    if not args.apply:
        print(f"[check] 将新增 {added} / 修复依据 {repaired}；digest {recomputed} → {new_digest}")
        print("[check] 一行未写 —— 加 --apply 才落盘")
        return 1
    doc["adjudications"] = rows
    doc["adjudication_digest"] = new_digest
    ADJ_PATH.write_bytes((json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(f"[apply] 新增 {len(added)} / 修复依据 {len(repaired)}；条目数 {len(rows)}；digest={new_digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
