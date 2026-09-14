# -*- coding: utf-8 -*-
"""Task 39 辐射面选取：按 **AST 级 import / 符号引用** 推导受影响测试文件。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 3 Task 39

═══ 为什么不用词面搜索 ═══

`backend/tests` 根目录下有约 2285 个测试文件，整跑会被当成卡死。本 spec 已实测过词面搜索的
后果：一次产生 67 个假阳性、把 14 个无关失败拖进判定。因此这里只认两类结构化证据：

1. **import 图** —— 测试文件是否 import 了本任务新建/改动的模块；
2. **符号引用** —— 是否在 AST 里以 `Name` / `Attribute` / `ImportFrom` 形式引用了本任务
   新增的符号。

两者都从 `ast` 取，不看注释、不看字符串（登记表的 `why` 文案里就写着这些名字）。

═══ 本任务的改动面 ═══

* **新建** `pilot_harness.py` / `evidence_freshness.py` / `capacity_profile.py`
* **只加不动** `evidence.py`：`StaleReason` 新增一个成员
  `definition_bundle_child_changed`（emit 点在 `evidence_freshness.bundle_stale_reasons`）

因此辐射面必须包含 Task 29/30 那批消费 `evidence` 的守卫 —— 枚举加成员会让任何
「逐成员比对 StaleReason 全集」的判据变化。

用法::

    py -3 backend/scripts/diagnose/select_task39_radiation.py
    py -3 backend/scripts/diagnose/select_task39_radiation.py --print-args
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
TESTS = BACKEND / "tests"

#: 本任务新建 + 只加不动的生产模块。
#:
#: `merge.py` 在列，是因为本任务往它的 `RETIRED_DEFERRALS` 追加了一条登记
#: （harness 是 merge 域的**只读**消费方）—— Task 14 的「消费方集合 ↔ 退役登记双向等值」
#: 判据会因此变化，不把它算进辐射面就会漏掉那条红。
CHANGED_MODULES: tuple[str, ...] = (
    "app.services.workpaper_sync.pilot_harness",
    "app.services.workpaper_sync.evidence_freshness",
    "app.services.workpaper_sync.capacity_profile",
    "app.services.workpaper_sync.evidence",
    "app.services.workpaper_sync.merge",
)

#: 本任务新增的符号（含 evidence.py 那一个新枚举成员）。
CHANGED_SYMBOLS: frozenset[str] = frozenset(
    {
        # evidence.py 只加不动
        "definition_bundle_child_changed",
        # merge.py 只加不动（退役登记追加一条）
        "RETIRED_DEFERRALS",
        # pilot_harness 新建
        "SyncTestRunHarness",
        "SCENARIO_ORACLES",
        "ScenarioOracle",
        "ScenarioObservation",
        "ScenarioDecision",
        "HarnessRejection",
        "HarnessRejected",
        "HarnessPlan",
        "BundleIdentity",
        "EvidenceInput",
        "OracleOutcome",
        "OracleVerdict",
        "MergeEvidence",
        "PilotClass",
        "PilotClassAssessment",
        "PilotClassStatus",
        "assert_oracle_registry_complete",
        "resolve_production_refs",
        "run_scenario_oracle",
        "evaluate_different_field_merge",
        "evaluate_same_field_conflict",
        "evaluate_timeline_order",
        "assert_entity_shape",
        "assert_no_reuse_within_run",
        "assert_no_reuse_across_entry",
        "assert_trace_bundle_published",
        "assert_required_set_non_empty",
        "assert_scenario_not_recorded",
        "assert_plan_matches_run",
        "assert_run_open",
        "bundle_identity_from_rows",
        "scenario_in_required_set",
        "oracle_for",
        "entry_for",
        "assess_pilot_classes",
        "pilot_coverage_summary",
        "build_run_manifest_payload",
        "all_declared_scenarios",
        "HARNESS_VERSION",
        "NOT_EXECUTED",
        # evidence_freshness 新建
        "EvidenceFreshnessGuard",
        "FreshnessVerdict",
        "BundleTamperError",
        "BUNDLE_AXES",
        "bundle_stale_reasons",
        "recompute_bundle_canonical_digest",
        "assert_bundle_child_inventory_intact",
        "summarize_freshness",
        # capacity_profile 新建
        "CAPACITY_PROFILE",
        "CapacityProfile",
        "CapacityMeasurement",
        "CapacityOutcome",
        "CapacityStatus",
        "CapacityNotExecutedError",
        "evaluate_capacity_run",
        "assert_capacity_verified",
        "requirement_facts",
        "assert_profile_matches_requirements",
    }
)

TEST_MODULE_PREFIX = "test_"


def _module_names(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out.update(f"{node.module}.{alias.name}" for alias in node.names)
    return out


def _referenced_symbols(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            out.update(alias.name for alias in node.names)
    return out


def _touches(path: Path) -> tuple[bool, list[str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return (False, [])
    modules = _module_names(tree)
    reasons: list[str] = []
    for module in CHANGED_MODULES:
        if any(name == module or name.startswith(module + ".") for name in modules):
            reasons.append(f"import:{module.rsplit('.', 1)[-1]}")
    hits = CHANGED_SYMBOLS & _referenced_symbols(tree)
    if hits:
        reasons.append("symbols:" + ",".join(sorted(hits)[:4]))
    return (bool(reasons), reasons)


def _test_module_edges() -> dict[str, set[str]]:
    """测试模块 → 它 import 的其它测试模块（fixture 复用链）。"""
    edges: dict[str, set[str]] = {}
    for path in sorted(TESTS.rglob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        edges[path.stem] = {
            name.split(".")[0]
            for name in _module_names(tree)
            if name.startswith(TEST_MODULE_PREFIX)
        }
    return edges


def main() -> int:
    parser = argparse.ArgumentParser(description="Task 39 辐射面选取")
    parser.add_argument("--print-args", action="store_true", help="只输出 pytest 参数")
    args = parser.parse_args()

    direct: dict[Path, list[str]] = {}
    for path in sorted(TESTS.rglob("test_*.py")):
        touched, reasons = _touches(path)
        if touched:
            direct[path] = reasons

    edges = _test_module_edges()
    hit_stems = {p.stem for p in direct}
    grown = True
    while grown:
        grown = False
        for path in sorted(TESTS.rglob("test_*.py")):
            if path in direct:
                continue
            if edges.get(path.stem, set()) & hit_stems:
                direct[path] = ["test-import-closure"]
                hit_stems.add(path.stem)
                grown = True

    rels = sorted(p.relative_to(REPO).as_posix() for p in direct)
    if args.print_args:
        print(" ".join(rels))
        return 0
    for rel in rels:
        print(f"{rel}  <- {', '.join(direct[REPO / rel])}")
    print(f"\n辐射面：{len(rels)} 个测试文件（AST 级 import/符号引用 + 测试模块 import 闭包）")
    print(f"分母参考：backend/tests 下共 {len(list(TESTS.rglob('test_*.py')))} 个测试文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
