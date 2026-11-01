"""Task 66 legacy 删除计划 → **可收缩执行账**（spec task 5.5）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / task 5.5
AC: 1.7, 12.9

═══════════════════════════════════════════════════════════════════════════
为什么是新生成器，而不是重跑 `generate_task66_legacy_deletion_plan.py`
═══════════════════════════════════════════════════════════════════════════

那份计划是 Wave 6 的**计划**产物（它自己的 `why_this_task_only_plans` 写着「只生成计划：
不 feature-disable、不删除、不改调用点」），`plan_commit` 钉在 `d330d7cea6bb`。它的
生成器把每个 owner 都对 `tasks.md` 校验，而 Wave-6 的任务号（66 / 71 / 72 / …）嵌在多个
**已冻结的数据文件**里（resolver 迁移矩阵、各 per-cycle 删除计划）。本轮任务号整套重编后
要让它重新跑通，就得为每个 legacy 号配一条 legacy→current 映射 —— 那正是「手抄编号」，
只是摊开成一张表，而且写下之后再没有东西能证明它对。

所以：**冻结计划当输入，不再重生成**。本生成器只做 task 5.5 要的三件事：

1. **三态现算**（`landed` / `drifted` / `intact`）—— 计划里每条 path 对现盘逐条核。
2. **失效项自动移除** —— `landed`（已不在盘上）自动出账；`drifted`（内容变了）必须重判
   是否仍是 legacy，不再盲目沿用计划里的裁决。
3. **计划外新增立即打红** —— 用**同一个** legacy 判据（复用冻结生成器的正则，不另写一份）
   重扫现盘，任何不在计划里的 legacy 对象都是 red。

加一条棘轮：`outstanding` 只许变小。棘轮基线放在**守卫**里而不是本产物里 —— 否则重跑
`--write` 就能把基线抬上去，棘轮就成了装饰。

输出**幂等**：不写 `generated_at` 之类每次都变的字段（否则 `--write` + `git diff` 式门禁
必然永红，而永红门禁等于没门禁）。所有「什么时候算的」由输入 digest 承担。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from typing import Any

_HERE = pathlib.Path(__file__).resolve().parent
_BACKEND = _HERE.parents[1]
_REPO = _BACKEND.parent
for _extra in (str(_BACKEND), str(_HERE)):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

# 🔴 复用冻结生成器的判据与常量，**不**另写一份 legacy 正则。
# 判据分叉过一次就会永久分叉：两边各自演化，谁也说不清哪个是对的。
import generate_task66_legacy_deletion_plan as frozen_plan  # noqa: E402

SCHEMA_VERSION = "task66-execution-ledger:v1"
OWNER_TASK = "5.5"
SPEC = "workpaper-html-onlyoffice-bidirectional-writeback-closure"

FROZEN_PLAN_PATH = frozen_plan.OUTPUT_PATH
FROZEN_GENERATOR_PATH = pathlib.Path(frozen_plan.__file__).resolve()
OUTPUT_PATH = _BACKEND / "data" / "workpaper_sync_task66_execution_ledger.json"

#: 计划里 legacy 组合式所在目录 —— 「计划外新增」就在这里扫。
COMPOSABLES_DIR = frozen_plan.FRONTEND_SRC / "components" / "workpaper" / "composables"

STATES = ("landed", "drifted", "intact")


class LedgerError(RuntimeError):
    """执行账现算失败。一律 fail closed：算不出就报错，不出半份账。"""


def _rel(path: pathlib.Path) -> str:
    return path.relative_to(_REPO).as_posix()


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_tracked(rel_path: str) -> bool:
    proc = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", rel_path],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


# ═══════════════════════════════════════════════════════════════════════════
# 1. 三态现算
# ═══════════════════════════════════════════════════════════════════════════


def _still_legacy_composable(path: pathlib.Path) -> bool:
    """文件内容变了之后，它**还是不是**计划所说的那种 legacy 组合式。

    只认文件名形态（与冻结生成器同一正则）；内容判据留给 `drifted` 的 owner 复判 ——
    本账不替它下结论，只把「需要重判」这件事显式记下来。
    """
    return bool(frozen_plan._LEGACY_COMPOSABLE_NAME.match(path.name))


def build_path_rows(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """按 path 聚合计划条目，逐条对现盘现算三态。"""
    by_path: dict[str, dict[str, Any]] = {}
    for item in plan["items"]:
        rel_path = item["path"]
        bucket = by_path.setdefault(
            rel_path,
            {
                "path": rel_path,
                "planned_sha256": item.get("sha256"),
                "item_ids": [],
                "categories": set(),
                "dispositions": set(),
                "deletion_units": set(),
            },
        )
        bucket["item_ids"].append(item["item_id"])
        bucket["categories"].add(item["category"])
        bucket["dispositions"].add(item["disposition"])
        bucket["deletion_units"].add(item.get("deletion_unit"))
        planned = bucket["planned_sha256"]
        if item.get("sha256") and planned and item["sha256"] != planned:
            raise LedgerError(
                f"计划内自相矛盾：{rel_path} 的多个条目记了不同 sha256 —— "
                "聚合口径失效，先修计划或改聚合键"
            )

    rows: list[dict[str, Any]] = []
    for rel_path, bucket in sorted(by_path.items()):
        abs_path = _REPO / rel_path
        planned_sha = bucket["planned_sha256"]
        if not abs_path.is_file():
            state, current_sha = "landed", None
            still_legacy = None
        else:
            current_sha = _sha256(abs_path)
            if planned_sha and current_sha != planned_sha:
                state = "drifted"
            else:
                state = "intact"
            still_legacy = _still_legacy_composable(abs_path)
        rows.append(
            {
                "path": rel_path,
                "state": state,
                "planned_sha256": planned_sha,
                "current_sha256": current_sha,
                "item_count": len(bucket["item_ids"]),
                "categories": sorted(bucket["categories"]),
                "dispositions": sorted(bucket["dispositions"]),
                "deletion_units": sorted(u for u in bucket["deletion_units"] if u),
                "still_matches_legacy_name_form": still_legacy,
                "tracked_in_git": _git_tracked(rel_path) if abs_path.is_file() else False,
            }
        )
    return rows


# ═══════════════════════════════════════════════════════════════════════════
# 2. 计划外 legacy 普查（同一判据重扫现盘）
# ═══════════════════════════════════════════════════════════════════════════


def unplanned_legacy_paths(planned: set[str]) -> list[str]:
    """现盘上符合 legacy 判据、但**不在**计划里的对象。

    这一条是 task 5.5 的「计划外 legacy/unreachable 新增立即打红」。判据与冻结生成器同源
    （`_LEGACY_COMPOSABLE_NAME`），所以不会出现「计划按一种口径、守卫按另一种口径」。
    """
    if not COMPOSABLES_DIR.is_dir():
        raise LedgerError(
            f"组合式目录不在：{_rel(COMPOSABLES_DIR)} —— 计划外普查会得出假的 0，fail closed"
        )
    found: list[str] = []
    for path in sorted(COMPOSABLES_DIR.rglob("*.ts")):
        if not frozen_plan._LEGACY_COMPOSABLE_NAME.match(path.name):
            continue
        rel_path = _rel(path)
        if rel_path not in planned:
            found.append(rel_path)
    return found


# ═══════════════════════════════════════════════════════════════════════════
# 3. 释放条件现算（哪些 outstanding 已经可以删了）
# ═══════════════════════════════════════════════════════════════════════════

#: 替代面被生产宿主消费的锚点组件。BP-66-1 的释放条件就是「宿主真 import/渲染它」。
EDITOR_HOST_BASENAME = "WorkpaperSyncEditorHost"


def recompute_blocking_points(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """把计划里的 BP 逐条对现盘重算，而不是沿用计划里冻结的 verdict。"""
    out: list[dict[str, Any]] = []
    for bp in plan["blocking_preconditions"]:
        bp_id = bp["id"]
        measured: dict[str, Any] = {}
        if bp_id == "BP-66-2":
            # 「替代面自身未入库」—— 直接问 git，不看计划里冻结的 untracked 计数
            surface = [entry["path"] for entry in plan["replacement_registry"]]
            untracked = [p for p in surface if not _git_tracked(p)]
            measured = {
                "replacement_surface_total": len(surface),
                "replacement_surface_untracked": len(untracked),
                "untracked_sample": untracked[:8],
            }
            still_blocking = bool(untracked)
        elif bp_id == "BP-66-1":
            # 「替代面未被任何生产宿主消费」—— 现算有多少生产文件 import 了锚点组件
            importers = _production_importers_of(EDITOR_HOST_BASENAME)
            measured = {
                "anchor": EDITOR_HOST_BASENAME,
                "production_importer_count": len(importers),
                "production_importers": importers[:12],
            }
            still_blocking = not importers
        else:
            # BP-66-3（required scenario authority model 未定）不在本账能力范围内：
            # 它的 owner 在 Phase 6。如实标 not_recomputable_here，不假装算过。
            measured = {"recomputed": False, "owner_task_in_plan": bp.get("owner_task")}
            still_blocking = True
        out.append(
            {
                "id": bp_id,
                "title": bp["title"],
                "release_condition": bp.get("release_condition"),
                "measured": measured,
                "still_blocking": still_blocking,
            }
        )
    return out


def _production_importers_of(basename: str) -> list[str]:
    """哪些**生产**文件（非测试）import 了给定组件。"""
    hits: list[str] = []
    needle = re.compile(rf"\b{re.escape(basename)}\b")
    for path in sorted(frozen_plan.FRONTEND_SRC.rglob("*")):
        if path.suffix not in (".ts", ".vue"):
            continue
        rel_path = _rel(path)
        if "__tests__" in rel_path or rel_path.endswith((".spec.ts", ".test.ts")):
            continue
        if path.name.startswith(basename):
            continue  # 组件自身不算消费方
        code = frozen_plan.strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        if needle.search(code):
            hits.append(rel_path)
    return hits


# ═══════════════════════════════════════════════════════════════════════════
# 4. 组账
# ═══════════════════════════════════════════════════════════════════════════


def build_record() -> dict[str, Any]:
    if not FROZEN_PLAN_PATH.is_file():
        raise LedgerError(f"冻结计划不在：{_rel(FROZEN_PLAN_PATH)}")
    plan_bytes = FROZEN_PLAN_PATH.read_bytes()
    plan = json.loads(plan_bytes.decode("utf-8"))

    rows = build_path_rows(plan)
    planned_paths = {row["path"] for row in rows}
    unplanned = unplanned_legacy_paths(planned_paths)
    blocking = recompute_blocking_points(plan)

    pending_rows = [row for row in rows if "pending_delete" in row["dispositions"]]
    outstanding = [row for row in pending_rows if row["state"] != "landed"]
    live_blockers = [bp["id"] for bp in blocking if bp["still_blocking"]]

    counters = {
        "plan_paths_total": len(rows),
        "state_landed": sum(1 for r in rows if r["state"] == "landed"),
        "state_drifted": sum(1 for r in rows if r["state"] == "drifted"),
        "state_intact": sum(1 for r in rows if r["state"] == "intact"),
        "pending_delete_paths": len(pending_rows),
        "pending_delete_landed": sum(1 for r in pending_rows if r["state"] == "landed"),
        "outstanding_paths": len(outstanding),
        "outstanding_drifted_need_reverdict": sum(
            1 for r in outstanding if r["state"] == "drifted"
        ),
        "unplanned_legacy_paths": len(unplanned),
        "live_blocking_points": len(live_blockers),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "spec": SPEC,
        "owner_task": OWNER_TASK,
        "description": (
            "Task 66 冻结删除计划的可收缩执行账：三态现算（landed/drifted/intact）、"
            "失效项自动出账、计划外 legacy 打红、outstanding 棘轮只减。"
        ),
        "generator": _rel(pathlib.Path(__file__).resolve()),
        "output_is_idempotent": (
            "本产物不含时间戳等每次都变的字段 —— 否则 `--write` + `git diff` 式门禁必然永红，"
            "而永红门禁等于没门禁。「什么时候算的」由下面的输入 digest 承担。"
        ),
        "frozen_inputs": {
            "plan_path": _rel(FROZEN_PLAN_PATH),
            "plan_digest": hashlib.sha256(plan_bytes).hexdigest(),
            "plan_commit_declared_in_plan": plan.get("plan_commit"),
            "plan_items_total": plan["counters"]["items_total"],
            "plan_pending_delete_paths_distinct": plan["counters"][
                "pending_delete_paths_distinct"
            ],
            "frozen_generator_path": _rel(FROZEN_GENERATOR_PATH),
            "frozen_generator_digest": _sha256(FROZEN_GENERATOR_PATH),
        },
        "frozen_generator_verdict": {
            "verdict": "retired_superseded_by_this_ledger",
            "why": (
                "它的 owner 校验把 Wave-6 任务号（66/71/72…）对当前 tasks.md 比对，而那些号"
                "嵌在多个已冻结数据文件里；全部复活等于手抄一张 legacy→current 映射表，"
                "且写下后无从证明其正确。计划本身是历史记录（plan_commit 已钉）。"
            ),
            "not_a_permanently_red_gate": (
                "退役后它的 `--check` 不得留在任何门禁里。要断言的是「冻结产物真的没再变」，"
                "由 frozen_inputs.plan_digest 承担。"
            ),
            "parser_fixes_kept": (
                "该文件里 _TASK_LINE / cycle_owner_tasks / tasks_md_task_ids / "
                "_word_lane_owner_task / resolve_current_deletion_executor 的修复保留并被本"
                "生成器复用 —— 它们本身是真缺陷（含两处静默错）。"
            ),
        },
        "state_vocabulary": {
            "landed": "计划里的 path 已不在盘上 ⇒ 删除确已发生，自动出账（失效项自动移除）",
            "drifted": "path 还在但内容已变 ⇒ 计划里的裁决不再可信，必须由 owner 重判",
            "intact": "path 在且内容与计划一致 ⇒ 计划仍然适用，计入 outstanding",
        },
        "blocking_points": blocking,
        "live_blocking_point_ids": live_blockers,
        "eligibility": {
            "rule": (
                "outstanding 项要进物理删除，必须 live_blocking_point_ids 为空。"
                "只要还有一条 BP 现算成立，就不存在 eligible_now —— 这不是豁免，是前置未满足。"
            ),
            "eligible_now_paths": [] if live_blockers else [r["path"] for r in outstanding],
            "eligible_now_count": 0 if live_blockers else len(outstanding),
        },
        "unplanned_legacy_paths": unplanned,
        "counters": counters,
        "paths": rows,
        "requirements_covered": ["1.7", "12.9"],
    }


def _canonical_text(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="只读：现算并与磁盘逐字节比对")
    mode.add_argument("--write", action="store_true", help="现算并落盘")
    args = parser.parse_args(argv)

    record = build_record()
    text = _canonical_text(record)
    if args.write:
        OUTPUT_PATH.write_text(text, encoding="utf-8")
        print(f"[write] {OUTPUT_PATH.name}")
        print(json.dumps(record["counters"], ensure_ascii=False, indent=2))
        return 0
    if not OUTPUT_PATH.is_file():
        raise LedgerError(f"{OUTPUT_PATH.name} 不存在 —— 先跑 `--write`，`--check` 不得因缺文件而成功")
    on_disk = OUTPUT_PATH.read_text(encoding="utf-8")
    if on_disk != text:
        raise LedgerError(
            f"{OUTPUT_PATH.name} 与现算不一致（磁盘 "
            f"{hashlib.sha256(on_disk.encode('utf-8')).hexdigest()[:12]} vs 现算 "
            f"{hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]}）—— 重跑 `--write` 并复核 diff"
        )
    print(f"[check] {OUTPUT_PATH.name} 与现算逐字节一致")
    print(json.dumps(record["counters"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
