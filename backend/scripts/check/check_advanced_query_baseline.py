"""高级查询硬化：红基线与回归辐射面判据（只读）。

Feature: advanced-query-hardening-wiring-closure（Task 1.1 / 1.2）

两个用途：

1. ``--radius``：按**引用关系**反查本 spec 改动的回归辐射面，产出目标测试清单。
   不跑全量 ``backend/tests``（实测 2224 个 test_*.py，前台跑数分钟无输出会被当卡死），
   而是扫测试文件里对本 spec 涉及模块的**实际 import / monkeypatch 引用**。

2. ``--check``：核对 spec 的红基线是否仍然成立 —— 也就是「立项时那 75 + 5 条红」
   是否都已转绿，且没有新的同域红冒出来。只读，不改任何文件。

用法::

    python backend/scripts/check/check_advanced_query_baseline.py --radius
    python backend/scripts/check/check_advanced_query_baseline.py --check
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TESTS_DIR = REPO / "backend" / "tests"
BASELINE_JSON = Path(__file__).with_name("advanced_query_hardening_baseline.json")

#: 本 spec 触达的模块标识 —— 测试文件若引用其中任一项即纳入辐射面。
#: 用 import 路径片段而非文件名：`from app.routers import custom_query` 与
#: `import app.routers.custom_query` 两种写法都要能命中。
TOUCHED_MODULES: tuple[str, ...] = (
    "routers.custom_query",
    "routers import custom_query",
    "routers.query_builder",
    "routers import query_builder",
    "custom_query.query_orchestrator",
    "custom_query.execute_compatibility",
    "custom_query.business_fetchers",
    "custom_query.pagination",
    "custom_query.builder_scope",
    "custom_query.execution_guard",
    "custom_query.table_whitelist",
    "custom_query.ownership_guard",
    "custom_query.template_service",
    "custom_query.template_scope_adapter",
    "custom_query.writeback_preview",
    "custom_query.audit_helper",
    "custom_query_models",
    "services.query_cache",
    "_ensure_custom_query_tables",
    "snapshot_writer",
    "pivot_engine",
    "grouping_engine",
)

#: 本 spec 自建的守卫文件（必须全绿）
SPEC_GUARD_FILES: tuple[str, ...] = (
    "backend/tests/test_advanced_query_hardening_wave012.py",
    "backend/tests/test_custom_query_template_scope_hardening.py",
    "backend/tests/test_custom_query_templates.py",
    "backend/tests/test_advanced_query_scope_budget_tiers.py",
    "backend/tests/test_advanced_query_param_sql_builder_wiring.py",
    "backend/tests/test_advanced_query_indicators_lazy.py",
    "backend/tests/test_advanced_query_ddl_cross_lock.py",
    "backend/tests/test_advanced_query_hardening_properties.py",
    "backend/tests/test_advanced_query_hardening_properties_scope.py",
    "backend/tests/test_template_config.py",
    "backend/tests/test_table_whitelist.py",
    "backend/tests/test_query_builder_joins.py",
    "backend/tests/test_query_builder_endpoint.py",
)


def compute_radius() -> list[str]:
    """扫描测试目录，返回引用了本 spec 模块的测试文件清单。"""
    hits: list[str] = []
    for path in sorted(TESTS_DIR.rglob("test_*.py")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(token in text for token in TOUCHED_MODULES):
            hits.append(path.relative_to(REPO).as_posix())
    return hits


def cmd_radius(write: bool) -> int:
    hits = compute_radius()
    total = len(list(TESTS_DIR.rglob("test_*.py")))
    print(f"辐射面 {len(hits)} 个测试文件（全仓 test_*.py 共 {total} 个）")
    for h in hits:
        print("  ", h)
    if write:
        out = REPO / "backend" / "scripts" / "check" / "advanced_query_radius.txt"
        out.write_text("\n".join(hits) + "\n", encoding="utf-8")
        print(f"\n已写入 {out.relative_to(REPO).as_posix()}")
    return 0


def _run_pytest(paths: list[str]) -> tuple[int, int, list[str]]:
    """跑 pytest，返回 (passed, failed, failed_nodeids)。"""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *paths, "-q", "--tb=no", "-p", "no:cacheprovider"],
        cwd=REPO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    failed = [
        line[len("FAILED "):].split(" - ")[0].strip()
        for line in out.splitlines()
        if line.startswith("FAILED ")
    ]
    passed = 0
    for line in out.splitlines():
        if " passed" in line:
            for token in line.replace(",", " ").split():
                if token.isdigit():
                    nxt = line.split(token, 1)[1][:8]
                    if "passed" in nxt:
                        passed = int(token)
                        break
    return passed, len(failed), failed


def cmd_check() -> int:
    """核对 spec 守卫文件全绿；有红即退出码 1 并列出。"""
    if not BASELINE_JSON.exists():
        print(f"缺判据文件 {BASELINE_JSON.name}")
        return 1
    baseline = json.loads(BASELINE_JSON.read_text(encoding="utf-8"))
    missing = [p for p in SPEC_GUARD_FILES if not (REPO / p).exists()]
    if missing:
        print("以下守卫文件不存在（产物未入库？）：")
        for m in missing:
            print("  ", m)
        return 1

    passed, failed_count, failed = _run_pytest(list(SPEC_GUARD_FILES))
    print(f"spec 守卫：{passed} passed / {failed_count} failed")
    if failed:
        print("\n红：")
        for f in failed:
            print("  ", f)
        return 1

    expected = baseline.get("expected_min_passed", 0)
    if passed < expected:
        print(f"\npassed {passed} 低于基线 {expected} —— 疑似测试被删或被 skip")
        return 1
    print(f"\n达标（基线要求 ≥ {expected}）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--radius", action="store_true", help="计算回归辐射面")
    parser.add_argument("--write", action="store_true", help="把辐射面写入文件")
    parser.add_argument("--check", action="store_true", help="核对 spec 守卫全绿")
    args = parser.parse_args()
    if args.radius:
        return cmd_radius(write=args.write)
    if args.check:
        return cmd_check()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
