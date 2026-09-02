# -*- coding: utf-8 -*-
"""writer 清册的**行级 diff + 逐行归因**（Task 19 交付，后续 writer 迁移任务复用）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure
Requirements: 2.2（所有 writer 经统一入口提交）、9.11（writer/resolver 必须进迁移矩阵）

═══ 为什么需要归因，而不是「看总数降了就行」═══

`backend/data/workpaper_writer_inventory.json` 由生成器从**整棵源码树**推导，任何并发
会话改任何一处生产代码都会让它变化。只报「bypass 从 266 降到 262」是**全局等值型**判据，
在多会话仓库里必然假红或假绿 —— 降 4 也可能是别人删了 4 个 writer，或是我改对了 2 个而
别人弄坏了 2 个。

所以判据是**归因型**的：每一条 added / removed / changed 都必须落到「是不是我这次动的
那几个文件里的那几个函数」，落不上的必须逐条解释。四种归因：

* `MINE` —— 在 :data:`MINE` 名单里（本次直接改造的 writer，或只改了裁决说明的行）；
* `MINE-LINE-SHIFT` —— 落在我改过的文件里，且 `facts` 的差异**只**在行号字段上
  （抹平行号后逐字节相等）⇒ 行为没变，位置变了；
* `MINE-COLLATERAL` —— 落在我改过的文件里，且差异是判据发现面的连带效应（例如
  `has_characterization_test` 因为「按名称就近」匹配而被顺带点亮），必须给出具体机制；
* `OTHER-SESSION-OR-UNEXPLAINED` —— 退出码非 0，必须人工解释后才能收口。

🔴 `MINE` 名单是**手写**的，不从 diff 反推。从 diff 反推等于「凡是变了的都算我的」，
归因就退化成重言式（本 spec 反复消灭的假绿第③源）。

用法（仓库根）::

    # 先快照基线，再改生产、重生成清册，最后跑本脚本
    python backend/scripts/diagnose/diff_workpaper_writer_inventory_rows.py \\
        --before <baseline.json> --out <row_diff.json>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
EVIDENCE = (
    REPO
    / ".kiro" / "specs" / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
    / "evidence" / "task19-writer-migration"
)
LIVE = REPO / "backend" / "data" / "workpaper_writer_inventory.json"

#: Task 19 两个增量真正改过的 writer / retired 行。
MINE: frozenset[str] = frozenset({
    # 增量一（custom / WOPI / 上传）
    "app.routers.custom_workpaper_cells::update_custom_cells",
    "app.services.wopi_service::WOPIHostService.put_file",
    "app.services.wopi_service::WOPIHostService.put_file._auto_parse",
    "app.services.wopi_service::WOPIHostService.put_file._auto_fine_extract",
    "app.services.wp_download_service::WpUploadService.upload_file",
    # 增量二（rollback / 历史恢复 / F2 / .versions 快照）
    "app.services.wp_migration_service::WpMigrationService.rollback",
    "app.services.wp_migration_service::WpMigrationService._load_restore_scope",
    "app.services.version_trail_service::VersionTrailService.rollback_to_snapshot",
    "app.services.version_trail_service::VersionTrailService._load_restore_scope",
    "app.services.wp_storage_service::WpStorageService.save_version",
    "app.routers.wp_render_strategies._f2_stocktake_plan_sync::_save_fields",
    "app.routers.wp_render_strategies._f2_stocktake_plan_sync::f2_st_plan_sync_from_oo",
    "app.routers.wp_render_strategies._f2_stocktake_plan_sync::f2_st_plan_sync_to_oo",
    "app.routers.wp_render_strategies._f2_stocktake_summary_sync::_save_fields",
    "app.routers.wp_render_strategies._f2_stocktake_summary_sync::f2_st_summary_sync_from_oo",
    "app.routers.wp_render_strategies._f2_stocktake_summary_sync::f2_st_summary_sync_to_oo",
    # 只改了裁决说明（BLOCKED 的理由），生产代码一行没动
    "app.routers.excel_html::rollback_file_version",
})

#: 我改过的源文件。落在这些文件里但不是目标函数的行，只可能是附带影响。
MY_FILES: frozenset[str] = frozenset({
    "backend/app/routers/custom_workpaper_cells.py",
    "backend/app/services/wopi_service.py",
    "backend/app/services/wp_download_service.py",
    "backend/app/services/wp_migration_service.py",
    "backend/app/services/version_trail_service.py",
    "backend/app/services/wp_storage_service.py",
    "backend/app/routers/wp_render_strategies/_f2_stocktake_plan_sync.py",
    "backend/app/routers/wp_render_strategies/_f2_stocktake_summary_sync.py",
})

#: `facts` 里纯粹是「源码行号」的字段。只有它们变化 ⇒ 行为没变，位置变了。
_LINE_ONLY_FACT_KEYS = ("swallowed_exception_lines", "ad_hoc_paths")

_COMPARED_KEYS = (
    "kind",
    "delegates_to_content_writer",
    "facts",
    "verdicts",
    "adjudication",
    "content_stores_written",
    "resolver_identities",
    "canonical_resolver",
)


def _rows(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["writer_id"]: row for row in inventory.get("entries", [])}


def _retired(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["writer_id"]: row for row in inventory.get("retired_writers", [])}


def _facts_differ_only_in_line_numbers(delta: dict[str, Any]) -> bool:
    """`facts` 的差异是否只落在行号字段上。

    做法是「把行号字段抹平后是否逐字节相等」，而不是「检查行号字段变了」—— 后者在
    「行号变了**并且**别的也变了」时会误判成无害。
    """
    if set(delta) != {"facts"}:
        return False
    before = dict(delta["facts"]["before"] or {})
    after = dict(delta["facts"]["after"] or {})
    for key in _LINE_ONLY_FACT_KEYS:
        before[key] = "<line-numbers-erased>"
        after[key] = "<line-numbers-erased>"
    return before == after


def _attribute(
    writer_id: str, *, source_path: str | None = None, delta: dict[str, Any] | None = None
) -> tuple[str, str]:
    """返回 `(归因, 理由)`。理由必须能独立复核，不能只有一个标签。"""
    if writer_id in MINE:
        return "MINE", "本次直接改造的 writer / 裁决说明"
    normalized = (source_path or "").replace("\\", "/")
    if delta is not None and _facts_differ_only_in_line_numbers(delta):
        if normalized in MY_FILES:
            return (
                "MINE-LINE-SHIFT",
                "同文件内纯行号位移（新增 import/docstring 把后续代码推下去），"
                "抹平行号字段后 facts 逐字节相等",
            )
        return "OTHER-SESSION-LINE-SHIFT", f"行号位移但文件不在我的改动集内: {normalized}"
    if delta is not None and set(delta) == {"verdicts"}:
        before = delta["verdicts"]["before"] or {}
        after = delta["verdicts"]["after"] or {}
        flipped = {key for key in after if before.get(key) != after.get(key)}
        if flipped == {"has_characterization_test"} and normalized in MY_FILES:
            return (
                "MINE-COLLATERAL",
                "🔴 生成器的 characterization-test 发现面是**按名称就近**匹配的：新写的守卫"
                "提到了这个模块，于是同模块的其它函数也被记成「有 characterization 测试」。"
                "这是判据的 fail-open（高估覆盖），不是真的为它写了测试。",
            )
    return "OTHER-SESSION-OR-UNEXPLAINED", "需要逐条解释"


def _delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {
        key: {"before": before.get(key), "after": after.get(key)}
        for key in _COMPARED_KEYS
        if before.get(key) != after.get(key)
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--before", default=str(EVIDENCE / "inventory_before.json"),
        help="基线清册（默认取 Task 19 的 pre-migration 快照）",
    )
    parser.add_argument("--live", default=str(LIVE), help="当前清册")
    parser.add_argument("--out", default=str(EVIDENCE / "inventory_row_diff.json"))
    parser.add_argument(
        "--write-after", default=str(EVIDENCE / "inventory_after.json"),
        help="把当前清册另存为 after 快照；传空串跳过",
    )
    args = parser.parse_args(argv)

    before = json.loads(Path(args.before).read_text(encoding="utf-8"))
    after = json.loads(Path(args.live).read_text(encoding="utf-8"))
    if args.write_after:
        Path(args.write_after).write_text(
            json.dumps(after, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    rows_before, rows_after = _rows(before), _rows(after)
    retired_before, retired_after = _retired(before), _retired(after)

    def _row(wid: str, base: dict[str, Any], **extra: Any) -> dict[str, Any]:
        attribution, reason = _attribute(
            wid, source_path=base.get("source_path"), delta=extra.get("deltas")
        )
        return {
            "writer_id": wid,
            "attribution": attribution,
            "attribution_reason": reason,
            "source_path": base.get("source_path"),
            **extra,
        }

    added = [
        _row(wid, rows_after[wid], kind=rows_after[wid].get("kind"),
             domain=(rows_after[wid].get("adjudication") or {}).get("domain"))
        for wid in sorted(set(rows_after) - set(rows_before))
    ]
    removed = [
        _row(wid, rows_before[wid], kind=rows_before[wid].get("kind"),
             domain=(rows_before[wid].get("adjudication") or {}).get("domain"),
             now_retired=wid in retired_after)
        for wid in sorted(set(rows_before) - set(rows_after))
    ]
    changed = [
        _row(wid, rows_after[wid], deltas=delta)
        for wid, delta in (
            (wid, _delta(rows_before[wid], rows_after[wid]))
            for wid in sorted(set(rows_before) & set(rows_after))
        )
        if delta
    ]
    retired_added = [
        _row(wid, retired_after[wid], domain=retired_after[wid].get("domain"),
             source_state=retired_after[wid].get("source_state"))
        for wid in sorted(set(retired_after) - set(retired_before))
    ]

    unattributed = [
        row for row in (added + removed + changed + retired_added)
        if not row["attribution"].startswith("MINE")
    ]

    report = {
        "baseline": Path(args.before).name,
        "stats_before": before.get("stats"),
        "stats_after": after.get("stats"),
        "added": added,
        "removed": removed,
        "changed": changed,
        "retired_added": retired_added,
        "unattributed_rows": len(unattributed),
        "unattributed_sample": unattributed[:10],
    }
    Path(args.out).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"[diff] added={len(added)} removed={len(removed)} changed={len(changed)} "
        f"retired_added={len(retired_added)} unattributed={len(unattributed)}"
    )
    for row in added + removed + retired_added:
        print(f"  {row['attribution']:>28}  {row['writer_id']}")
    for row in changed:
        print(
            f"  {row['attribution']:>28}  ~ {row['writer_id']} "
            f"[{','.join(sorted(row['deltas']))}]"
        )
    print(f"[ok] wrote {args.out}")
    return 1 if unattributed else 0


if __name__ == "__main__":
    sys.exit(main())
