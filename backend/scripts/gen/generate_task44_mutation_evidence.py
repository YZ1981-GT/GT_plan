# -*- coding: utf-8 -*-
"""生成 Task 44 gate 的变异覆盖面与变异报告。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 44
Requirements: 14.7

变异列表来自 test_task44_oo94_excel_pilot_gate.py 中已有的行为级反向自检。
每条变异都对应一个**真实可运行**的 pytest 测试，它证明当把某个关键判据注入为
错误值时，gate 会检测到并拒绝。

变异不等于截图或声明。只有 test suite 真跑且全 RED 才算通过。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_EVIDENCE_DIR = (
    _REPO
    / ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure"
    / "evidence/task44-oo94-excel-pilot-gate"
)

# ═══════════════════════════════════════════════════════════════════════════
# 变异声明表
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class MutationDecl:
    id: str
    anchor: str  # 对应 test 的 test id（pytest nodeid 的尾部）
    why: str  # 这条变异证明什么


MUTATIONS: tuple[MutationDecl, ...] = (
    MutationDecl(
        id="M01",
        anchor="test_removing_one_enumerated_item_from_the_task_text_fails_the_gate",
        why="正文枚举项被删 ⇒ probe 分母锁立刻抛；证明分母不可悄悄缩小",
    ),
    MutationDecl(
        id="M02",
        anchor="test_an_unclaimed_requirement_is_a_structural_failure",
        why="AC 编号无 probe 对应 ⇒ 结构性失效；证明每个声明的 Requirement 都有验证路径",
    ),
    MutationDecl(
        id="M03",
        anchor="test_a_property_missing_from_design_md_is_a_structural_failure",
        why="design.md 里不存在的 Property 编号 ⇒ 拒绝；证明 Property 与 design 双向锁",
    ),
    MutationDecl(
        id="M04",
        anchor="test_a_vanished_production_symbol_fails_the_probe",
        why="生产符号被改名/删除 ⇒ probe 立刻失效；证明 probe 与生产代码双向锁",
    ),
    MutationDecl(
        id="M05",
        anchor="test_dropping_one_scenario_probe_makes_the_denominator_shrink_detectable",
        why="required set 里有场景却没人声明 probe ⇒ 结构性失效；证明场景分母不可缩小",
    ),
    MutationDecl(
        id="M06",
        anchor="test_a_scenario_probe_without_a_production_oracle_is_rejected",
        why="probe 声明但无 oracle ⇒ 拒绝；证明每条 probe 都有真实验证函数",
    ),
    MutationDecl(
        id="M07",
        anchor="test_a_hardcoded_admission_would_fail_the_state_sensitivity_probe",
        why="把 probe_finalize_signals 硬编码为恒 False ⇒ 替身翻转不变 ⇒ 失败；"
        "证明准入判定读的是真实状态而非 return False",
    ),
    MutationDecl(
        id="M08",
        anchor="test_all_four_pilots_are_blocked_before_task_36_finalize",
        why="finalize 未完成时四个 pilot 全被阻断；证明 gate 真实读取 finalize 状态",
    ),
    MutationDecl(
        id="M09",
        anchor="test_every_burial_form_of_a_result_claim_is_rejected",
        why="执行记录携带结果声明字段 ⇒ 拒绝；证明不得以文档声明冒充真实执行",
    ),
    MutationDecl(
        id="M10",
        anchor="test_load_execution_records_rejects_a_claiming_file",
        why="文件中携带声明字段 ⇒ 拒绝；证明外部输入也不得包含结果声明",
    ),
    MutationDecl(
        id="M11",
        anchor="test_the_probe_would_fail_if_the_refusal_stopped_working",
        why="把拒绝逻辑替换为放行 ⇒ probe 失败；证明拒绝路径被 probe 覆盖",
    ),
    MutationDecl(
        id="M12",
        anchor="test_a_broken_record_reaches_failed",
        why="记录字段被改坏 ⇒ validator 返回 failed（而非通过/unverifiable）；"
        "证明 validator 是双向可达的",
    ),
    MutationDecl(
        id="M13",
        anchor="test_reused_application_ids_across_scenarios_are_rejected_by_production",
        why="同一 application 跨场景复用 ⇒ oracle 拒绝；证明 Property 70 的跨场景不可复用",
    ),
    MutationDecl(
        id="M14",
        anchor="test_naive_timestamps_are_rejected",
        why="naive 时间戳（无时区）⇒ 失败；证明 timeline 校验真实使用 aware datetime",
    ),
    MutationDecl(
        id="M15",
        anchor="test_wrong_close_capture_count_is_failed_by_production_oracle",
        why="close-capture 数不为 1 ⇒ oracle 失败；证明 exactly-one 的 liveness 判据",
    ),
    MutationDecl(
        id="M16",
        anchor="test_structural_failure_exits_two_not_one",
        why="结构性失效返回退出码 2 而非 1；证明结构错误与普通阻断区分",
    ),
    MutationDecl(
        id="M17",
        anchor="test_mutation_probe_requires_declared_equals_executed",
        why="declared != executed ⇒ 变异 probe 不通过；证明不可用已跑子集冒充全量",
    ),
    MutationDecl(
        id="M18",
        anchor="test_mutation_probe_rejects_a_non_red_verdict",
        why="变异结果含 GREEN ⇒ 不通过；证明每条变异必须 RED",
    ),
)


def _test_nodeid(decl: MutationDecl) -> str:
    """pytest nodeid：从锚点名推导。"""
    return f"backend/tests/workpaper_sync/test_task44_oo94_excel_pilot_gate.py::{decl.anchor}"


def _full_nodeid(decl: MutationDecl) -> str:
    """搜索全测试类。"""
    return (
        f"backend/tests/workpaper_sync/"
        f"test_task44_oo94_excel_pilot_gate.py -k {decl.anchor}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 执行与落盘
# ═══════════════════════════════════════════════════════════════════════════


def run_mutations(*, dry_run: bool = False) -> tuple[list[dict], dict]:
    """逐条运行变异并记录结果。"""
    report: list[dict] = []
    for decl in MUTATIONS:
        if dry_run:
            report.append({
                "id": decl.id,
                "anchor": decl.anchor,
                "why": decl.why,
                "verdict": "NOT-EXECUTED",
                "exit_code": None,
                "summary": "dry-run",
            })
            continue

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                f"backend/tests/workpaper_sync/test_task44_oo94_excel_pilot_gate.py",
                "-k",
                decl.anchor,
                "-v",
                "--tb=line",
                "-q",
            ],
            cwd=str(_REPO),
            capture_output=True,
            text=True,
            timeout=120,
        )
        # 拿 summary 行
        lines = (result.stdout + result.stderr).strip().splitlines()
        summary_line = ""
        for line in reversed(lines):
            if "passed" in line or "failed" in line or "error" in line:
                summary_line = line.strip()
                break

        # 判定：测试通过 = RED（变异被检测到了）
        verdict = "RED" if result.returncode == 0 else "GREEN"
        report.append({
            "id": decl.id,
            "anchor": decl.anchor,
            "why": decl.why,
            "verdict": verdict,
            "exit_code": result.returncode,
            "summary": summary_line or f"exit={result.returncode}",
        })

    coverage = {
        "declared_count": len(MUTATIONS),
        "executed_count": sum(1 for r in report if r["verdict"] != "NOT-EXECUTED"),
        "all_red": all(r["verdict"] == "RED" for r in report if r["verdict"] != "NOT-EXECUTED"),
    }
    return report, coverage


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Task 44 变异覆盖面生成器")
    parser.add_argument("--apply", action="store_true", help="执行变异并写入 evidence")
    parser.add_argument("--check", action="store_true", help="只检查 evidence 存在且有效")
    parser.add_argument("--dry-run", action="store_true", help="只生成声明，不跑测试")
    args = parser.parse_args(argv)

    if args.check:
        coverage_path = _EVIDENCE_DIR / "mutation_coverage.json"
        report_path = _EVIDENCE_DIR / "mutation_report.json"
        if not coverage_path.exists() or not report_path.exists():
            print("[FAIL] evidence 文件不存在")
            return 1
        coverage = json.loads(coverage_path.read_bytes())
        report = json.loads(report_path.read_bytes())
        if coverage["declared_count"] != len(MUTATIONS):
            print(f"[FAIL] declared_count={coverage['declared_count']} != {len(MUTATIONS)}")
            return 1
        if coverage["declared_count"] != coverage["executed_count"]:
            print(f"[FAIL] declared != executed")
            return 1
        non_red = [r for r in report if r.get("verdict") != "RED"]
        if non_red:
            print(f"[FAIL] {len(non_red)} 条变异非 RED: {[r['id'] for r in non_red]}")
            return 1
        print(f"[OK] {len(report)} mutations all RED")
        return 0

    if args.apply or args.dry_run:
        report, coverage = run_mutations(dry_run=args.dry_run)
        _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        report_path = _EVIDENCE_DIR / "mutation_report.json"
        coverage_path = _EVIDENCE_DIR / "mutation_coverage.json"
        report_path.write_bytes(json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8"))
        coverage_path.write_bytes(
            json.dumps(coverage, indent=2, ensure_ascii=False).encode("utf-8")
        )
        print(f"[WRITE] {report_path.relative_to(_REPO)}")
        print(f"[WRITE] {coverage_path.relative_to(_REPO)}")
        all_red = all(r["verdict"] == "RED" for r in report)
        non_red = [r for r in report if r["verdict"] != "RED"]
        if non_red:
            print(f"[WARN] {len(non_red)} 条变异非 RED:")
            for r in non_red:
                print(f"  {r['id']}: {r['verdict']} ({r['anchor']})")
        else:
            print(f"[OK] {len(report)} mutations all RED")
        return 0 if all_red else 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
