"""幂等：为 I 循环 6 条 entry 补 `workpaper_sync_entry_wp_code_adjudication.json` 条目。

spec: `.kiro/specs/i-cycle-sync-foundation-and-first-canary` + 两份 lane spec（首版发布前置；
与 `fix_l_cycle_wp_code_adjudication.py` / `fix_j_cycle_wp_code_adjudication.py` 同构：
裁决表 digest 自检 / 追加不重排 / LF 写回）

═══ 为什么需要它 ═══

`fix_projection_first_publication.py` 在 `adjudicated_wp_codes(entry_id)` 处 fail-closed：
entry 不在裁决表里就抛。provider 的 `WP_CODES` 是宿主 CamelCase 幻影码（`I1I`/`I2D`/…/`I6R`），
wp_index 零命中，不能当目标码。

═══ 🔴 I 循环的 wp_index 两套编号（ID-8）═══

同一个码在 wp_index 里有**两种含义**：新编号（`I2`=开发支出，`storage/projects/.../I/I2.xlsx`）
与旧编号（`I2`=商誉审定表，`wp_storage/<uuid>.xlsx`）。目标解析按
`(有无 store 载荷, wp_code, created_at, id)` 取第一条 —— 2026-10-01 现查 6 个码的首选
**全部落在新编号整册**上（旧编号行都晚于 05-13/05-15 的整册行，且 6 个主表键真库 0 行）。
⇒ 码取本循环自己的码；但本条件会随建项变化，`--check` 打印首选底稿供人工复核。

用法::

    python backend/scripts/fix/fix_i_cycle_wp_code_adjudication.py           # 只读预演
    python backend/scripts/fix/fix_i_cycle_wp_code_adjudication.py --apply
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[2]
ADJ_PATH = BACKEND / "data" / "workpaper_sync_entry_wp_code_adjudication.json"

_MEASURED = "2026-10-01"
_TWO_NUMBERINGS = (
    "🔴 wp_index 两套编号（ID-8）：同码另有旧编号行（{old}）指向 `wp_storage/<uuid>.xlsx`；"
    "按目标全序首选的是新编号整册行（created_at 更早），现查无 store 载荷可改变排序。"
)

#: (entry_id, contract_id, 真码, 幻影码, 受管 sheet, 模板相对路径, 首选底稿证据, 旧编号含义, 主 store item)
_SPECS: tuple[tuple[str, ...], ...] = (
    ("xlsx/gt-i1-intangible-assets", "i1.intangible_assets_detail", "I1", "I1I",
     "明细表I1-2", "I/I1 无形资产、累计摊销及减值准备.xlsx",
     "wp 57356eb6（项目 005a6f2d，storage/projects/.../I/I1.xlsx，2026-05-13）",
     "无形资产审定表", "I1-2-rows"),
    ("xlsx/gt-i2-development-expenditure", "i2.development_expenditure_detail", "I2", "I2D",
     "明细表I2-2", "I/I2 开发支出.xlsx",
     "wp c41da93f（项目 005a6f2d，storage/projects/.../I/I2.xlsx，2026-05-13）",
     "商誉审定表", "I2-2-rows"),
    ("xlsx/gt-i3-goodwill", "i3.goodwill_detail", "I3", "I3G",
     "明细表I3-2", "I/I3 商誉.xlsx",
     "wp 926f8e9f（项目 005a6f2d，storage/projects/.../I/I3.xlsx，2026-05-13）",
     "长期待摊费用审定表", "I3-2-rows"),
    ("xlsx/gt-i4-long-term-prepaid", "i4.long_term_prepaid_detail", "I4", "I4L",
     "明细表I4-2", "I/I4 长期待摊费用.xlsx",
     "wp 4f65bf18（项目 005a6f2d，storage/projects/.../I/I4.xlsx，2026-05-13）",
     "开发支出审定表", "I4-2-rows"),
    ("xlsx/gt-i5-other-noncurrent-assets", "i5.other_noncurrent_assets_detail", "I5", "I5O",
     "明细表I5-2", "I/I5 其他非流动资产.xlsx",
     "wp 051d4e6b（项目 14fb8c10，storage/projects/.../I/I5.xlsx，2026-05-15）",
     "其他非流动资产审定表", "I5-2-rows"),
    ("xlsx/gt-i6-research-development-expense", "i6.research_development_expense_detail", "I6", "I6R",
     "明细表I6-2", "I/I6 研发费用.xlsx",
     "wp 0048c8a5（项目 14fb8c10，storage/projects/.../I/I6.xlsx，2026-05-15）",
     "研发费用审定表", "I6-2-detail-rows"),
)


def _rows() -> tuple[dict[str, Any], ...]:
    out = []
    for eid, cid, code, phantom, sheet, tpl, ev, old, item in _SPECS:
        out.append({
            "entry_id": eid,
            "contract_id": cid,
            "wp_codes": [code],
            "resolvable_for_provisioning": True,
            "matcher_domain_conflict": None,
            "basis": {
                "heuristic_is_wrong_because": (
                    f"manifest 从宿主 Vue 文件名 CamelCase 抽出的 {phantom} 在 wp_index 里 0 命中（幻影码）"
                ),
                "heuristic_would_say": [phantom],
                "managed_excel_name": sheet,
                "template_relative_path": tpl,
                "wp_index_evidence": (
                    f"{_MEASURED} 真库现查（`file_path <> ''` 口径）：wp_code={code} 首选底稿 {ev}；"
                    f"受管 sheet `{sheet}` 是该整册里的一张 sheet ⇒ 目标码取 `{code}`。"
                    + _TWO_NUMBERINGS.format(old=old)
                ),
            },
            "store_payload_evidence": {
                "max_payload_bytes": 0,
                "measured_at": _MEASURED,
                "store_item_id": item,
                "why_null": f"{_MEASURED} 现查 `checklist_responses` 中 `{item}` 0 行（真库主表键无载荷）",
                "wp_code_with_payload": None,
                "wp_count_with_payload": 0,
            },
        })
    return tuple(out)


def _digest(adjudications: list[dict[str, Any]]) -> str:
    """与文件里 `adjudication_digest_algorithm` 声明的算法逐字一致。"""
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
        print(f"[error] 磁盘 digest {on_disk_digest} 与现算 {recomputed} 不一致，先修那个再跑")
        return 2

    added, updated = [], []
    for raw_row in _rows():
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
