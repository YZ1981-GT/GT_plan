"""幂等：为 J 循环 entry 补 `workpaper_sync_entry_wp_code_adjudication.json` 条目。

spec: `.kiro/specs/j-cycle-sync-foundation-and-first-canary`（首版发布前置，参照
`fix_l_cycle_wp_code_adjudication.py` 同构；裁决表 digest 自检 / 追加不重排 / LF 写回三条纪律照搬）

═══ 为什么需要它 ═══

`fix_projection_first_publication.py` 在 `_adjudicated_wp_codes(entry_id)` 处 fail-closed：
entry 不在裁决表里就抛 —— 回落启发式产出的是**幻影码** `J1E`
（GtJ1EmployeeCompensation → J1E，wp_index 零命中）。

用法::

    python backend/scripts/fix/fix_j_cycle_wp_code_adjudication.py           # 只读预演
    python backend/scripts/fix/fix_j_cycle_wp_code_adjudication.py --apply
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
ADJ_PATH = BACKEND / "data" / "workpaper_sync_entry_wp_code_adjudication.json"

_J1_WP_INDEX_EVIDENCE = (
    "2026-10-01 真库现查（`file_path <> ''` 口径，不用 `count(file_path)` —— 它不排除空串）："
    "wp_code=J1「应付职工薪酬」3 行且 3 行都有真路径 `storage/projects/{pid}/workpapers/J/J1.xlsx`"
    "（整册 23 sheet 的工作簿）；另有 J1「应付职工薪酬审定表」2 行指向 `wp_storage/` 下 uuid 文件名。"
    "`J1-2`「应付职工薪酬明细表」2 行有独立 `J1-2.xlsx`，1 行无文件。"
    "受管 sheet `计提情况检查表J1-6` 是 `J1.xlsx` 里的一张 sheet（wp_index 无 `J1-6` 行）⇒ "
    "目标码取持有整册文件的 `J1`。`J1E` 是 CamelCase 幻影码，wp_index 零命中。"
)

_J1_STORE_WHY_NULL = (
    "🔴 2026-10-01 现查 `checklist_responses` 全表仅 **122** 行、`item_id ~ '^J[0-9]'` **0** 行 —— "
    "spec Task 20 记录的 `J1-6-short-term` 3473 B 载荷在当前真库**已不存在**"
    "（同时 `working_paper_content_representation` 由 L spec 记录的 274 行降为 1 行，"
    "判断为库被重置，非本脚本所为）⇒ 目标 item 无法按载荷定码，本条以 file_path 证据定 `J1`。"
)

_ROWS: tuple[dict[str, Any], ...] = (
    {
        "entry_id": "xlsx/j1/gt-j1-employee-compensation",
        "contract_id": "j1.accrual_check_short_term",
        "wp_codes": ["J1"],
        "resolvable_for_provisioning": True,
        "matcher_domain_conflict": None,
        "basis": {
            "heuristic_is_wrong_because": (
                "manifest 从宿主 Vue 文件名 CamelCase 抽出的 J1E 在 wp_index 里 0 命中"
                "（GtJ1EmployeeCompensation → J1E 是幻影码）"
            ),
            "heuristic_would_say": ["J1E"],
            "managed_excel_name": "计提情况检查表J1-6",
            "template_relative_path": "J/J1 应付职工薪酬.xlsx",
            "wp_index_evidence": _J1_WP_INDEX_EVIDENCE,
        },
        "store_payload_evidence": {
            "max_payload_bytes": 0,
            "measured_at": "2026-10-01",
            "store_item_id": "J1-6-short-term",
            "why_null": _J1_STORE_WHY_NULL,
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

    on_disk_digest = str(doc.get("adjudication_digest") or "")
    recomputed = _digest(rows)
    if on_disk_digest != recomputed:
        print(f"[error] 磁盘 digest {on_disk_digest} 与现算 {recomputed} 不一致，先修那个再跑")
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

    new_digest = _digest(rows)
    doc["adjudications"] = rows
    doc["adjudication_digest"] = new_digest
    if not args.apply:
        print(f"[check] 将新增 {added} / 更新 {updated}；{len(by_id)} → {len(rows)}；加 --apply 落盘")
        return 1
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    ADJ_PATH.write_bytes(text.encode("utf-8"))
    print(f"[apply] 新增 {added} / 更新 {updated}；条目数 {len(rows)}；digest={new_digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
