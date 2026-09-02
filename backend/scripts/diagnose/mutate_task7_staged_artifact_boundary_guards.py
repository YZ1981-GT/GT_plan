"""Task 7 守卫变异检验（spec: workpaper-html-onlyoffice-bidirectional-writeback-closure）

对边界契约、原始 evidence 与 spec 文档逐点注入变异，验证守卫是否**真的**打红，并按四态判定：

  RED          期望的那条测试确实失败（守卫有效）
  GREEN        变异后全绿（守卫缺陷）
  ANCHOR-MISS  锚点未命中或命中 >1 处（脚本缺陷，不能当 RED）
  WRONG-TEST   打红了但不是期望那条（污染残留 / 锚点错行）

用法（仓库根）：
    python backend/scripts/diagnose/mutate_task7_staged_artifact_boundary_guards.py
    python backend/scripts/diagnose/mutate_task7_staged_artifact_boundary_guards.py --run
    python backend/scripts/diagnose/mutate_task7_staged_artifact_boundary_guards.py --run --only 8 14
    python backend/scripts/diagnose/mutate_task7_staged_artifact_boundary_guards.py --run --report-path tmp.json

安全性：
  - 逐条变异 → 跑测试 → **立即还原**，还原后校验 sha256 与变异前一致；不一致立刻中止并告警。
  - 只碰三类文件：边界契约 JSON、Task 7 evidence、spec 文档（design.md 一处措辞）。
    不碰生产代码、不写数据库、不发网络请求。
  - `.json`/`.md` 的换行风格不同（evidence 是 CRLF，契约是 LF），anchor 按文件实际风格
    自动升级为 `\\r\\n`，否则 CRLF 文件上必 ANCHOR-MISS。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CONTRACT = REPO / "backend" / "data" / "workpaper_staged_artifact_boundary_contract.json"
SPEC_DIR = REPO / ".kiro" / "specs" / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
DESIGN = SPEC_DIR / "design.md"
EVIDENCE_DIR = SPEC_DIR / "evidence" / "task7-staged-artifact-db-rollback"
FS_EVIDENCE = EVIDENCE_DIR / "fs_observations.json"
DB_EVIDENCE = EVIDENCE_DIR / "db_observations.json"
RUN_META = EVIDENCE_DIR / "run_meta.json"
SQL_LOG = EVIDENCE_DIR / "db_sql_log.json"
FINDINGS = EVIDENCE_DIR / "findings.md"

TEST_FILES = ["backend/tests/test_workpaper_staged_artifact_boundary_contract.py"]


@dataclass
class Mutation:
    ident: int
    label: str
    path: Path
    anchor: str
    replacement: str
    expect_tests: tuple[str, ...]
    note: str = ""
    result: str = field(default="", init=False)
    failed_tests: tuple[str, ...] = field(default=(), init=False)


MUTATIONS: list[Mutation] = [
    # ---- 契约结构 ----
    Mutation(
        1,
        "契约 schema_version 漂移",
        CONTRACT,
        '"schema_version": 1,',
        '"schema_version": 2,',
        ("test_contract_is_versioned_and_complete",),
    ),
    # ---- 跨介质事务表述（Requirement 5.9）----
    Mutation(
        2,
        "契约声称文件系统与 PostgreSQL 同一事务",
        CONTRACT,
        '"filesystem_and_postgres_share_one_transaction": false,',
        '"filesystem_and_postgres_share_one_transaction": true,',
        ("test_contract_declares_no_cross_medium_transaction",),
    ),
    Mutation(
        3,
        "design.md 把「不宣称同事务」改成「宣称同事务」",
        DESIGN,
        "不可见 orphan 清理；不宣称文件系统与 PostgreSQL 同事务。",
        "不可见 orphan 清理；宣称文件系统与 PostgreSQL 同事务。",
        (
            "test_spec_docs_never_claim_filesystem_and_postgres_share_a_transaction",
            "test_spec_docs_keep_the_explicit_disclaimer",
        ),
    ),
    # ---- Windows 文件系统事实 ----
    Mutation(
        4,
        "跨卷 winerror 漂移（17 → 18）",
        CONTRACT,
        '"observed_errno": 18,\n      "observed_winerror": 17,',
        '"observed_errno": 18,\n      "observed_winerror": 18,',
        ("test_cross_volume_replace_facts_match_evidence",),
    ),
    Mutation(
        5,
        "谎称 FILE_SHARE_DELETE 能让 os.replace 成功",
        CONTRACT,
        '"share_delete_makes_replace_succeed": false,',
        '"share_delete_makes_replace_succeed": true,',
        ("test_file_occupancy_matrix_matches_evidence",),
    ),
    Mutation(
        6,
        "目标占用 winerror 集合被掺入 32",
        CONTRACT,
        '"observed_target_winerrors": [5],',
        '"observed_target_winerrors": [5, 32],',
        ("test_file_occupancy_matrix_matches_evidence",),
    ),
    Mutation(
        7,
        "share 模式清单删掉 read_write_delete（只测一种就下结论）",
        CONTRACT,
        '"observed_share_modes_tested": ["none", "read", "read_write", "read_delete", "read_write_delete", "delete_only"],',
        '"observed_share_modes_tested": ["none", "read", "read_write", "read_delete", "delete_only"],',
        ("test_file_occupancy_matrix_matches_evidence",),
    ),
    Mutation(
        8,
        "谎称 Windows 支持目录 fsync",
        CONTRACT,
        '"supported_on_windows": false,\n      "observed_failure_stage": "open",',
        '"supported_on_windows": true,\n      "observed_failure_stage": "open",',
        ("test_directory_fsync_unsupported_claim_matches_evidence",),
    ),
    Mutation(
        9,
        "原子性观测下限被抬高到不可能（暴露观测量不足即假绿）",
        CONTRACT,
        '"size_sampling_min_observations": 200,',
        '"size_sampling_min_observations": 100000,',
        ("test_same_volume_replace_atomicity_is_backed_by_enough_observations",),
    ),
    Mutation(
        10,
        "跨卷 fallback 的未完成大小被手填成实测不存在的值",
        CONTRACT,
        '"observed_incomplete_sizes": [0],',
        '"observed_incomplete_sizes": [0, 1048576],',
        ("test_cross_volume_replace_facts_match_evidence",),
    ),
    # ---- 路径安全（Property 42）----
    Mutation(
        11,
        "path_safety 必拒清单删掉 symlink_escape",
        CONTRACT,
        '      "cross_project_traversal",\n      "symlink_escape"\n    ],',
        '      "cross_project_traversal"\n    ],',
        ("test_path_safety_rejections_match_evidence",),
    ),
    Mutation(
        12,
        "谎称软链接越界未覆盖（覆盖状态与实证不符）",
        CONTRACT,
        '"symlink_escape_covered": true,',
        '"symlink_escape_covered": false,',
        ("test_symlink_escape_is_really_covered",),
    ),
    # ---- DB 边界（Property 5）----
    Mutation(
        13,
        "resolver 拒绝 candidate/incoming 的 pgcode 漂移",
        CONTRACT,
        '"observed_reject_pgcode": "23514",',
        '"observed_reject_pgcode": "23505",',
        ("test_resolver_never_returns_candidate_incoming_or_orphan",),
    ),
    Mutation(
        14,
        "GC 二次确认原因被改成 grace 原因",
        CONTRACT,
        '"observed_reference_reappears_reason": "reference_found_on_recheck",',
        '"observed_reference_reappears_reason": "grace_not_elapsed",',
        ("test_retention_gc_respects_grace_recheck_and_legal_hold",),
    ),
    Mutation(
        15,
        "not_covered 抹掉 os.replace 中断项（把未实证含混成已覆盖）",
        CONTRACT,
        '"item": "os.replace 自身被中断的半成品",',
        '"item": "os.replace 中断（已覆盖）",',
        ("test_os_replace_interruption_is_declared_as_not_independently_injected",),
    ),
    Mutation(
        16,
        "声称 Task 9 的表已迁移",
        CONTRACT,
        '"target_tables_not_yet_migrated": true,',
        '"target_tables_not_yet_migrated": false,',
        ("test_target_tables_are_declared_as_not_yet_migrated",),
    ),
    # ---- evidence 篡改（证明守卫真的在读原始观测）----
    Mutation(
        17,
        "evidence 篡改：FILE_SHARE_DELETE 下 os.replace 改成没失败",
        FS_EVIDENCE,
        '"hold_mode": "read_write_delete",\n        "held_file": "target",\n        "os_replace": {\n          "raised": true,',
        '"hold_mode": "read_write_delete",\n        "held_file": "target",\n        "os_replace": {\n          "raised": false,',
        ("test_file_occupancy_matrix_matches_evidence",),
    ),
    Mutation(
        18,
        "evidence 篡改：DB rollback 后文件也没了（等于宣称同事务）",
        DB_EVIDENCE,
        '"file_survived_db_rollback": true,',
        '"file_survived_db_rollback": false,',
        (
            "test_contract_declares_no_cross_medium_transaction",
            "test_db_rollback_leaves_pointer_and_revision_untouched",
        ),
        note="anchor 命中 2 处（两种失败注入），按 replace_all 处理（见 ALLOW_MULTI）",
    ),
    Mutation(
        19,
        "evidence 篡改：probe_status 变 error（fail-open 检测）",
        RUN_META,
        '"probe_status": "ok",',
        '"probe_status": "error",',
        ("test_probe_reported_no_fail_open_errors",),
    ),
    Mutation(
        20,
        "evidence 篡改：校验门失败后竟然发布了 artifact",
        FS_EVIDENCE,
        '"published": false,',
        '"published": true,',
        ("test_validation_gate_injections_leave_current_untouched",),
        note="anchor 命中 3 处（三个注入点），按 replace_all 处理",
    ),
    Mutation(
        21,
        "evidence 篡改：写目标换成业务表但仍保留 scratch schema 名（打弱判据）",
        SQL_LOG,
        '"sql": "INSERT INTO ',
        '"sql": "INSERT INTO public.working_paper_artifact -- ',
        ("test_db_probe_did_not_touch_business_tables",),
        note="故意保留 scratch schema 名：若守卫只做『语句里有 schema 名』的子串检查就会 GREEN。"
        "首轮实测确实 GREEN ⇒ 已把守卫改成结构化提取写目标后复测。anchor 多处命中，replace_all。",
    ),
    Mutation(
        23,
        "findings.md 把「不是同一事务」改成「是同一事务」（evidence 文档也在扫描面内）",
        FINDINGS,
        "**不是同一事务**，且不得如此宣称",
        "**是同一事务**，且不得如此宣称",
        ("test_spec_docs_never_claim_filesystem_and_postgres_share_a_transaction",),
    ),
    # ---- GREEN 对照：无害新增字段，期望守卫不误红 ----
    Mutation(
        22,
        "契约新增一个无人消费的说明字段（GREEN 对照）",
        CONTRACT,
        '  "staging": {\n    "must_be_same_volume_as_publish_target": true,',
        '  "staging": {\n    "probe_note_unused_by_guard": "harmless",\n    "must_be_same_volume_as_publish_target": true,',
        (),
        note="期望 GREEN：守卫按字段语义判据而非整文件 hash，无害新增不应误红",
    ),
]

#: 允许 anchor 多处命中并全量替换的变异（其余一律要求唯一命中）。
ALLOW_MULTI = {18, 20, 21}

GUARDED_PATHS = {CONTRACT, DESIGN, FS_EVIDENCE, DB_EVIDENCE, RUN_META, SQL_LOG, FINDINGS}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_tests() -> tuple[int, tuple[str, ...]]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *TEST_FILES, "-q", "--tb=no", "-rf", "-p", "no:cacheprovider"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=900,
    )
    failed = tuple(
        sorted(set(re.findall(r"FAILED [^\s:]+::([\w]+)", proc.stdout + proc.stderr)))
    )
    return proc.returncode, failed


def _apply(mutation: Mutation) -> tuple[bool, bytes]:
    """字节级注入变异，返回 (是否成功, 原始字节)。

    🔴 必须字节级：本仓库 evidence JSON 是 CRLF、契约 JSON / design.md 是 LF，用 `write_text`
    会按 `os.linesep` 重写换行 ⇒ 还原后 sha256 必不一致，且会产生整文件换行 diff。
    故 anchor 在 CRLF 文件上自动升级为 `\\r\\n`（这也是 ANCHOR-MISS 最常见成因）。
    """
    original = mutation.path.read_bytes()
    text = original.decode("utf-8")
    crlf = "\r\n" in text
    anchor = mutation.anchor.replace("\n", "\r\n") if crlf else mutation.anchor
    replacement = mutation.replacement.replace("\n", "\r\n") if crlf else mutation.replacement
    count = text.count(anchor)
    if count == 0 or (count > 1 and mutation.ident not in ALLOW_MULTI):
        print(f"        anchor 命中 {count} 次（crlf={crlf}）")
        return False, original
    mutation.path.write_bytes(text.replace(anchor, replacement).encode("utf-8"))
    return True, original


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="执行变异（不给则只列出）")
    ap.add_argument("--only", nargs="*", type=int, default=None)
    ap.add_argument("--report-path", default=None, help="把四态汇总写入该 JSON 文件（evidence 用）")
    args = ap.parse_args()

    selected = [m for m in MUTATIONS if args.only is None or m.ident in args.only]
    if not args.run:
        for m in selected:
            print(f"[{m.ident:>2}] {m.label} → {m.path.name} 期望红: {m.expect_tests or '(GREEN 对照)'}")
        return 0

    for path in GUARDED_PATHS:
        if not path.exists():
            print(f"FATAL 变异目标缺失: {path}")
            return 2

    baseline_rc, baseline_failed = _run_tests()
    if baseline_rc != 0 or baseline_failed:
        print(f"BASELINE 非全绿，无法做变异检验：rc={baseline_rc} failed={baseline_failed}")
        return 2
    print("BASELINE 全绿，开始变异\n")

    pre_hashes = {p: _sha(p) for p in GUARDED_PATHS}

    for mutation in selected:
        applied, original = _apply(mutation)
        if not applied:
            mutation.result = "ANCHOR-MISS"
            print(f"[{mutation.ident:>2}] {mutation.label}: ANCHOR-MISS")
            continue
        try:
            _rc, failed = _run_tests()
        finally:
            mutation.path.write_bytes(original)
            restored = _sha(mutation.path)
            if restored != pre_hashes[mutation.path]:
                print(f"FATAL 还原后 sha256 不一致: {mutation.path}")
                return 3
        mutation.failed_tests = failed
        expected = set(mutation.expect_tests)
        if not expected:
            mutation.result = "GREEN" if not failed else "WRONG-TEST"
        elif not failed:
            mutation.result = "GREEN"
        elif expected & set(failed):
            mutation.result = "RED"
        else:
            mutation.result = "WRONG-TEST"
        print(f"[{mutation.ident:>2}] {mutation.label}: {mutation.result} failed={failed or '()'}")

    print("\n=== 汇总 ===")
    tally: dict[str, int] = {}
    for m in selected:
        tally[m.result] = tally.get(m.result, 0) + 1
    print(json.dumps({m.ident: {"label": m.label, "result": m.result} for m in selected}, ensure_ascii=False, indent=2))
    print("四态计数:", tally)

    # 还原后必须回到全绿，否则说明有污染残留
    final_rc, final_failed = _run_tests()
    print("还原后基线:", "全绿" if final_rc == 0 and not final_failed else f"rc={final_rc} failed={final_failed}")

    if args.report_path:
        report = {
            "generated_by": "backend/scripts/diagnose/mutate_task7_staged_artifact_boundary_guards.py",
            "spec": "workpaper-html-onlyoffice-bidirectional-writeback-closure",
            "task": 7,
            "test_files": TEST_FILES,
            "baseline_all_green": True,
            "restored_baseline_all_green": final_rc == 0 and not final_failed,
            "tally": tally,
            "mutations": [
                {
                    "id": m.ident,
                    "label": m.label,
                    "file": str(m.path.relative_to(REPO)).replace("\\", "/"),
                    "expect_tests": list(m.expect_tests),
                    "result": m.result,
                    "failed_tests": list(m.failed_tests),
                    "note": m.note,
                }
                for m in selected
            ],
        }
        Path(args.report_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("报告已写入", args.report_path)

    bad = [m.ident for m in selected if m.result not in ("RED", "GREEN")] + [
        m.ident for m in selected if m.result == "GREEN" and m.expect_tests
    ]
    if bad or final_rc != 0:
        print(f"存在需处理项（GREEN 应红 / ANCHOR-MISS / WRONG-TEST / 还原后不绿）: {sorted(set(bad))}")
        return 1
    print("全部变异检验通过（期望红的都红了，对照项按预期绿，还原后回到全绿）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
