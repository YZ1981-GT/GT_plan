# -*- coding: utf-8 -*-
"""Task 29 辐射面：按**真实 import/引用**反查受本次改动影响的测试文件。
spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 29

用法（仓库根目录）::

    py -3 backend/scripts/diagnose/radiation_task29_timeline_evidence.py
    py -3 backend/scripts/diagnose/radiation_task29_timeline_evidence.py --pytest-args

═══ 为什么不能跑全量 ═══

`backend/tests` 下有 1500+ 测试文件，前台跑数分钟无输出会被当成卡死。判据是
**引用关系**：扫每个测试文件的 `Import`/`ImportFrom` 模块名与源码里对本次改动符号的
引用，命中即纳入辐射面。

═══ 为什么用 AST 而不是裸词 ═══

裸词会把「注释/docstring 里提到 `RedactionPolicy`」的文件也拉进来 —— 本 spec 的 evidence
README 与多个守卫的 docstring 里都逐字写着这些模块与类名。AST 只认真实 import 与真实
符号引用，并逐条输出**为什么**命中，便于人工复核辐射面不是猜的。

═══ 与 Task 28 的差异 ═══

Task 29 动的是 `timeline / evidence / redaction / alerting / metrics` 五个模块加
`wp_sync_router` 的指标/timeline 接线，而 `workpaper_sync/__init__.py` 的导出面把这五个
模块都摆在包级 —— 所以 `import app.services.workpaper_sync` 的文件同样在辐射面内
（Task 28 已经证明这个包级导入会显著放大辐射面，这里如实纳入而不是缩小判据）。
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TESTS = REPO / "backend" / "tests"

#: 本次改动/直接相关的生产模块（相对 `backend/`，点分）。
CHANGED_MODULES: tuple[str, ...] = (
    "app.services.workpaper_sync",
    "app.services.workpaper_sync.timeline",
    "app.services.workpaper_sync.evidence",
    "app.services.workpaper_sync.redaction",
    "app.services.workpaper_sync.alerting",
    "app.services.workpaper_sync.metrics",
    "app.services.workpaper_sync.entry_profile",
    "app.routers.wp_sync_router",
    "app.models.workpaper_sync_models",
)

#: 本次改动/新增的符号（被引用即算辐射）。
CHANGED_SYMBOLS: tuple[str, ...] = (
    # timeline
    "SyncTimelineService",
    "TimelineQuery",
    "TimelineEvent",
    "ProjectionCheck",
    "OperationTimeline",
    "RecoveryTimeline",
    "assert_server_clock_only",
    # evidence
    "EvidenceRecomputer",
    "RequiredScenario",
    "RequiredScenarioSet",
    "derive_required_scenarios",
    "derive_for_manifest_entry",
    "close_scenarios_required",
    "ScenarioKind",
    "ScenarioFamily",
    "manifest_source_digest",
    # redaction
    "RedactionPolicy",
    "load_redaction_policy",
    "load_redaction_config",
    "RedactionReport",
    # alerting
    "AlertRuleRegistry",
    "load_alert_registry",
    "load_alert_config",
    "validate_registry",
    "AlertCondition",
    # metrics
    "SyncMetrics",
    "METRIC_CATALOG",
    "METRICS_BY_NAME",
    "AttributionClass",
    "AttributionDim",
    "validate_catalog",
    "sync_metrics",
)


def _imports_of(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name)
    return out


def _names_of(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                out.add(alias.asname or alias.name)
    return out


def scan() -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for path in sorted(TESTS.rglob("test_*.py")):
        try:
            # `utf-8-sig` 剥 BOM：仓库里有带 BOM 的测试文件，`ast.parse` 对 U+FEFF 直接
            # `invalid non-printable character` ⇒ 会被误判成「坏文件」而混进辐射面。
            tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"))
        except SyntaxError:  # pragma: no cover - 坏文件如实报告，不静默跳过
            hits[path.relative_to(REPO).as_posix()] = ["<SyntaxError>"]
            continue
        imports = _imports_of(tree)
        names = _names_of(tree)
        why: list[str] = []
        for module in CHANGED_MODULES:
            if any(imp == module or imp.startswith(module + ".") for imp in imports):
                why.append(f"import:{module}")
        for symbol in CHANGED_SYMBOLS:
            if symbol in names:
                why.append(f"symbol:{symbol}")
        if why:
            hits[path.relative_to(REPO).as_posix()] = sorted(set(why))
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Task 29 辐射面反查")
    parser.add_argument(
        "--pytest-args", action="store_true", help="只输出可直接喂给 pytest 的路径列表"
    )
    parser.add_argument("--json", metavar="PATH", help="把结果落盘为 JSON")
    args = parser.parse_args(argv)

    hits = scan()
    total = len(list(TESTS.rglob("test_*.py")))
    if args.pytest_args:
        print(" ".join(sorted(hits)))
        return 0
    print(f"辐射面：{len(hits)} 个测试文件（全量 {total} 个）\n")
    for path, why in sorted(hits.items()):
        print(f"  {path}")
        print(f"      {', '.join(why)}")
    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {"total_test_files": total, "files": hits}, ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
        )
        print(f"\n已写入 {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
