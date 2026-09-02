# -*- coding: utf-8 -*-
"""Task 20：把 writer 清册的行级差异逐条归因到「本任务改了哪个谓词」。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 20
Requirements: 2.1, 2.2, 2.12, 9.11 · Property 4, Property 61

`backend/data/workpaper_writer_inventory.json` 是**并发多会话共用**的生成物（Task 3 建、
Task 18/19 各重生成过）。所以「重生成后行变了」不能一句「应该是我的改动」了事 —— 必须能
证明**每一行**的变化都落在本任务改的三个谓词里，其余字节逐字相等。

与 Task 19 的 `diff_workpaper_writer_inventory_rows.py` 的区别：Task 19 改的是**几个具体
函数的生产代码**，归因用手写 MINE 名单；Task 20 改的是**谓词本身**（characterization 判据
从「名称就近」改成「真的有调用点」、新增 artifact-snapshot 正面类别、新增两个 verdict/两个
fact 键），影响面天然是全表。名单式归因在这里没有意义，改用**形状式归因**：

* 先剥掉本任务新增的 fact / verdict 键，剥完两侧必须逐字节相等；
* 剩下的差异只允许是三类：characterization 证据变化、snapshot 类别导致的 bypass 翻转、
  以及由前两者派生的 verdict 变化；
* 任何其它字段变化 → `UNATTRIBUTED`，退出码 1（并发会话动了生产源码，或我的改动有副作用）。

用法（仓库根）::

    python backend/scripts/diagnose/diff_task20_writer_inventory_rows.py \\
        --before .kiro/specs/.../evidence/task20-writer-gate/inventory_before.json \\
        --after  backend/data/workpaper_writer_inventory.json \\
        --out    .kiro/specs/.../evidence/task20-writer-gate/inventory_row_diff.json
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]

#: 本任务新增的 fact 键（每一行都会多出来，绝大多数为空）。
NEW_FACT_KEYS = (
    "artifact_write_targets",
    "representation_candidate_calls",
    "revision_bump_calls",
)
#: 本任务新增的 verdict 键。
NEW_VERDICT_KEYS = (
    "artifact_snapshot_only",
    "writes_business_content",
    "keeps_legacy_write_path_beside_unified_commit",
)


def _strip_new_keys(entry: dict[str, Any]) -> dict[str, Any]:
    """去掉本任务新增的键，剩下的部分必须与改造前逐字节相同。"""
    trimmed = copy.deepcopy(entry)
    for key in NEW_FACT_KEYS:
        trimmed.get("facts", {}).pop(key, None)
    for key in NEW_VERDICT_KEYS:
        trimmed.get("verdicts", {}).pop(key, None)
    return trimmed


def _classify(before: dict[str, Any], after: dict[str, Any]) -> tuple[str, list[str]]:
    """返回 (归因标签, 变化字段列表)。"""
    trimmed_before = _strip_new_keys(before)
    trimmed_after = _strip_new_keys(after)
    if trimmed_before == trimmed_after:
        return "MINE-NEW-KEYS-ONLY", []

    changed: list[str] = []
    for key in sorted(set(trimmed_before) | set(trimmed_after)):
        if trimmed_before.get(key) != trimmed_after.get(key):
            if key == "verdicts":
                for name in sorted(
                    set(trimmed_before["verdicts"]) | set(trimmed_after["verdicts"])
                ):
                    if trimmed_before["verdicts"].get(name) != trimmed_after["verdicts"].get(name):
                        changed.append(f"verdicts.{name}")
            elif key == "facts":
                for name in sorted(set(trimmed_before["facts"]) | set(trimmed_after["facts"])):
                    if trimmed_before["facts"].get(name) != trimmed_after["facts"].get(name):
                        changed.append(f"facts.{name}")
            else:
                changed.append(key)

    characterization = {"characterization_tests", "verdicts.has_characterization_test"}
    snapshot = {"verdicts.bypasses_unified_commit"}
    if set(changed) <= characterization:
        return "MINE-CHARACTERIZATION-CALLSITE", changed
    if set(changed) <= snapshot:
        return "MINE-ARTIFACT-SNAPSHOT-CATEGORY", changed
    if set(changed) <= characterization | snapshot:
        return "MINE-CHARACTERIZATION+SNAPSHOT", changed
    return "UNATTRIBUTED", changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True)
    parser.add_argument("--after", required=True)
    parser.add_argument("--out")
    args = parser.parse_args(argv)

    before = json.loads(Path(args.before).read_text(encoding="utf-8"))
    after = json.loads(Path(args.after).read_text(encoding="utf-8"))
    before_rows = {row["writer_id"]: row for row in before["entries"]}
    after_rows = {row["writer_id"]: row for row in after["entries"]}

    added = sorted(set(after_rows) - set(before_rows))
    removed = sorted(set(before_rows) - set(after_rows))

    changed_rows: list[dict[str, Any]] = []
    for writer_id in sorted(set(before_rows) & set(after_rows)):
        if before_rows[writer_id] == after_rows[writer_id]:
            continue
        label, fields = _classify(before_rows[writer_id], after_rows[writer_id])
        changed_rows.append(
            {
                "writer_id": writer_id,
                "attribution": label,
                "changed_fields": fields,
                "characterization_before": before_rows[writer_id].get("characterization_tests"),
                "characterization_after": after_rows[writer_id].get("characterization_tests"),
            }
            if fields
            else {"writer_id": writer_id, "attribution": label, "changed_fields": fields}
        )

    by_label: dict[str, int] = {}
    for item in changed_rows:
        by_label[item["attribution"]] = by_label.get(item["attribution"], 0) + 1
    unattributed = [item for item in changed_rows if item["attribution"] == "UNATTRIBUTED"]

    # 证据落盘的是**判据**，不是叙述：门的每个准则前后计数 + 新增/删除行 + 归因分布。
    report = {
        "before_digest": before.get("inventory_digest"),
        "after_digest": after.get("inventory_digest"),
        "before_source_digest": before.get("source_digest"),
        "after_source_digest": after.get("source_digest"),
        "row_count_before": len(before_rows),
        "row_count_after": len(after_rows),
        "added_rows": added,
        "removed_rows": removed,
        "changed_row_count": len(changed_rows),
        "attribution_histogram": dict(sorted(by_label.items())),
        "unattributed_rows": [item["writer_id"] for item in unattributed],
        "new_fact_keys": list(NEW_FACT_KEYS),
        "new_verdict_keys": list(NEW_VERDICT_KEYS),
        "stats_before": before.get("stats"),
        "stats_after": after.get("stats"),
        "representation_upgrade_lane_after": after.get("representation_upgrade_lane"),
        "changed_rows": changed_rows,
    }
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        print(f"[OUT] {out}")

    print(f"rows {len(before_rows)} -> {len(after_rows)} (added={len(added)} removed={len(removed)})")
    print(f"changed rows: {len(changed_rows)}")
    for label, count in sorted(by_label.items()):
        print(f"  {label}: {count}")
    if added or removed:
        print(f"[FAIL] row denominator moved: added={added} removed={removed}")
        return 1
    if unattributed:
        print(f"[FAIL] {len(unattributed)} unattributed rows:")
        for item in unattributed[:20]:
            print(f"  {item['writer_id']}: {item['changed_fields']}")
        return 1
    print("[OK] every changed row is attributed to a Task 20 predicate change")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
