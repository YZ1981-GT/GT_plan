"""幂等：为 N 循环 entry 补 `workpaper_sync_entry_wp_code_adjudication.json` 条目。

spec: `.kiro/specs/n-cycle-sync-foundation-and-first-canary`（N4 canary · Task 7c 前置）

照 `fix_l_cycle_wp_code_adjudication.py` 范式。`fix_projection_first_publication.py` 在
`_adjudicated_wp_codes(entry_id)` 处 fail-closed：entry 不在裁决表里就抛，因回落启发式产出的
正是幻影码（manifest 从宿主 Vue 文件名 CamelCase 抽的 `N4T`，wp_index 零命中）。N4 接线前
必须先在裁决表登记。

用法::
    python backend/scripts/fix/fix_n_cycle_wp_code_adjudication.py --check
    python backend/scripts/fix/fix_n_cycle_wp_code_adjudication.py --apply
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
ADJ_PATH = BACKEND / "data" / "workpaper_sync_entry_wp_code_adjudication.json"

_N4_WP_INDEX_EVIDENCE = (
    "2026-10-01 现算：wp_code=N4「税金及附加」5 份未删除底稿且 file_path **全部非空真路径**"
    "（`storage/projects/{project_id}/workpapers/...`，整册 9 sheet 工作簿；首目标 wp "
    "4e5fdd29-9dc3-45c5-abad-640d522af188 / project 14fb8c10）。N4-1 / N4-2 子码在 wp_index "
    "有行但**无对应 working_paper 文件**。受管 sheet `税金及附加明细表N4-2` 只是 `N4.xlsx` 里的"
    "一张 sheet，不是独立文件 ⇒ 目标码取持有整册文件的 `N4`。`N4T` 是 CamelCase 幻影码"
    "（GtN4TaxesAndSurcharges → N4T），wp_index 零命中（与 L1/D1 的 L1S/D1N 同型）。"
    "判据用 `COALESCE(file_path,'') <> ''`（L1 裁决记过的空串陷阱）。"
)

_N4_STORE_WHY_NULL = (
    "`N4-2-detail-rows` 全库 0 行（明细表从未录入，同 L1-2-rows / H1-8-rows 空表单是合法"
    "业务事实）⇒ 目标 item 无法定码，本条以 file_path 证据定 `N4`。零迁移负担。"
    "行身份是熵键 rowKey（同税种可多行），不切语义键。全库 N 载荷只有 3 行且全在 N2 宿主"
    "（n_cycle_facts.LIVE_DB_N_ROWS），不属 N4 受管表。"
)

#: 本轮补录的条目（N1/N2/N3/N5 接线时在此追加；键是 entry_id）。
_ROWS: tuple[dict[str, Any], ...] = (
    {
        "entry_id": "xlsx/gt-n4-taxes-and-surcharges",
        "contract_id": "n4.taxes_and_surcharges",
        "wp_codes": ["N4"],
        "resolvable_for_provisioning": True,
        "matcher_domain_conflict": None,
        "basis": {
            "heuristic_is_wrong_because": (
                "manifest 从宿主 Vue 文件名 CamelCase 抽出的 N4T 在 wp_index 里 0 命中"
                "（GtN4TaxesAndSurcharges → N4T 是幻影码）"
            ),
            "heuristic_would_say": ["N4T"],
            "managed_excel_name": "税金及附加明细表N4-2",
            "template_relative_path": "N/N4 税金及附加.xlsx",
            "wp_index_evidence": _N4_WP_INDEX_EVIDENCE,
        },
        "store_payload_evidence": {
            "max_payload_bytes": 0,
            "measured_at": "2026-10-01",
            "store_item_id": "N4-2-detail-rows",
            "why_null": _N4_STORE_WHY_NULL,
            "wp_code_with_payload": None,
            "wp_count_with_payload": 0,
        },
    },
)


def _digest(adjudications: list[dict[str, Any]]) -> str:
    blob = json.dumps(adjudications, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="写盘（默认只读预演）")
    args = ap.parse_args()

    doc = json.loads(ADJ_PATH.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = list(doc.get("adjudications") or [])
    by_id = {str(r.get("entry_id")): i for i, r in enumerate(rows)}

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

    # 🔴 不排序 list（append 在末尾），不整文档 sort_keys（会重排他人条目）—— 同 L 脚本教训。
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

    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    ADJ_PATH.write_bytes(text.encode("utf-8"))
    print(f"[apply] 新增 {added} / 更新 {updated}；条目数 {len(rows)}；digest={new_digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
