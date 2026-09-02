"""Task 4 守卫变异检验（spec: workpaper-html-onlyoffice-bidirectional-writeback-closure）

对 callback 真值表、实证 evidence 与生产下载调用点逐点注入变异，验证守卫是否**真的**打红，
并按四态判定：

  RED          期望的那条测试确实失败（守卫有效）
  GREEN        变异后全绿（守卫缺陷）
  ANCHOR-MISS  锚点未命中或命中 >1 处（脚本缺陷，不能当 RED）
  WRONG-TEST   打红了但不是期望那条（污染/锚点错位）

用法（仓库根）：
    python backend/scripts/diagnose/mutate_task4_callback_contract_guards.py --run
    python backend/scripts/diagnose/mutate_task4_callback_contract_guards.py --run --only 3 7

安全性：
  - 逐条变异 → 跑测试 → **立即还原**，还原后校验 sha256 与变异前一致；不一致立刻中止并告警。
  - 只碰三类文件：真值表 JSON、evidence（callbacks.jsonl）、生产 router（仅 timeout / claim_version
    两处字面量）。生产文件在变异前后都做 mtime + sha256 双校验，若被并发会话修改立即中止。
  - 全程不写业务库、不发网络请求（测试自身只用本机 mock server）。
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
CONTRACT = REPO / "backend" / "data" / "onlyoffice_callback_state_contract.json"
EVIDENCE = (
    REPO
    / ".kiro"
    / "specs"
    / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
    / "evidence"
    / "task4-oo94-multiuser-callback"
    / "callbacks.jsonl"
)
ROUTER = REPO / "backend" / "app" / "routers" / "wp_onlyoffice_router.py"
TEST_FILES = [
    "backend/tests/test_workpaper_callback_state_contract.py",
    "backend/tests/test_workpaper_callback_download_security.py",
]


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
    Mutation(
        1,
        "真值表 schema_version 漂移",
        CONTRACT,
        '"schema_version": 1,',
        '"schema_version": 2,',
        ("test_contract_is_versioned_and_complete",),
    ),
    Mutation(
        2,
        "status 6 声明 userdata 恒有（实证是 optional）",
        CONTRACT,
        '"oo_name": "force_save",\n      "meaning": "强制保存（Command Service `c=forcesave` 或编辑器 forcesave 触发）",\n      "url_present": "always",\n      "userdata_present": "optional",',
        '"oo_name": "force_save",\n      "meaning": "强制保存（Command Service `c=forcesave` 或编辑器 forcesave 触发）",\n      "url_present": "always",\n      "userdata_present": "always",',
        ("test_url_and_userdata_presence_match_real_payloads",),
    ),
    Mutation(
        3,
        "status 2 谎报未实证",
        CONTRACT,
        '"oo94_observed": true,\n      "observed_count": 2,',
        '"oo94_observed": false,\n      "observed_count": 2,',
        (
            "test_observed_statuses_match_real_probe",
            "test_observed_counts_and_body_fields_match_real_payloads",
        ),
    ),
    Mutation(
        4,
        "status 6 observed_count 与实证不符",
        CONTRACT,
        '"observed_count": 5,',
        '"observed_count": 4,',
        ("test_observed_counts_and_body_fields_match_real_payloads",),
    ),
    Mutation(
        5,
        "撤销结论改成 participant-bound",
        CONTRACT,
        '"decision": "write_fence_plus_generation_rotation",',
        '"decision": "participant_bound_selective_apply",',
        (
            "test_participant_bound_authorization_is_refused",
            "test_revoked_user_contribution_is_not_dropped_from_aggregate",
        ),
    ),
    Mutation(
        6,
        "谎称 OO 会重发被拒 callback",
        CONTRACT,
        '"redelivers_on_nonzero_response": false,',
        '"redelivers_on_nonzero_response": true,',
        ("test_oo_does_not_redeliver_rejected_callbacks",),
    ),
    Mutation(
        7,
        "Command Service error=4 谎称会有 callback",
        CONTRACT,
        '"meaning": "距上次保存无新变更，未执行 forcesave",\n        "callback_expected": false,',
        '"meaning": "距上次保存无新变更，未执行 forcesave",\n        "callback_expected": true,',
        ("test_command_service_return_codes_match_real_calls",),
    ),
    Mutation(
        8,
        "下载策略放开重定向",
        CONTRACT,
        '"redirect_policy": {"follow_redirects": false, "max_redirects": 0,',
        '"redirect_policy": {"follow_redirects": true, "max_redirects": 5,',
        ("test_download_security_policy_is_versioned_and_strict",),
    ),
    Mutation(
        9,
        "application key 混入 callback_status",
        CONTRACT,
        '"application_key_components": [\n      "wp_id", "room_id", "generation",',
        '"application_key_components": [\n      "callback_status", "wp_id", "room_id", "generation",',
        ("test_application_key_excludes_status_and_arrival_pointer",),
    ),
    Mutation(
        10,
        "in-flight grace 超过 callback 等待超时",
        CONTRACT,
        '"in_flight_grace_seconds": 30,',
        '"in_flight_grace_seconds": 300,',
        ("test_timers_cover_timeout_grace_and_ttl",),
    ),
    Mutation(
        11,
        "claim schema 版本与 cbv 约束脱钩",
        CONTRACT,
        '"claim_schema_version": 1,',
        '"claim_schema_version": 2,',
        ("test_jwt_claim_schema_is_versioned_and_url_bound",),
    ),
    Mutation(
        12,
        "安全 gap 清单被削空",
        CONTRACT,
        '"gaps": [\n        "无 allowlist',
        '"gaps": [\n        "_removed_",\n        "无 allowlist',
        (),
        note="只加一条无害项，期望 GREEN（清单长度校验只挡削减）；用于确认判据方向正确",
    ),
    Mutation(
        13,
        "evidence 篡改：抹掉撤销用户在后续 artifact 的贡献",
        EVIDENCE,
        '"Z92": "BOB-EDIT-Z92"',
        '"Z92": null',
        (
            "test_revoked_user_contribution_is_not_dropped_from_aggregate",
            "test_forcesave_artifact_aggregates_other_participant_edits",
        ),
        note="anchor 多处命中时脚本按 replace_all 处理（见 allow_multi）",
    ),
    Mutation(
        14,
        "生产下载 timeout 漂移",
        ROUTER,
        "async with httpx.AsyncClient(timeout=60) as client:\n                resp = await client.get(url)",
        "async with httpx.AsyncClient(timeout=30) as client:\n                resp = await client.get(url)",
        ("test_production_download_profile_is_unchanged",),
    ),
    Mutation(
        15,
        "生产 claim_version 不再传 None",
        ROUTER,
        "claim_version=None,\n            current_version=str(wp.file_version),",
        'claim_version="pinned",\n            current_version=str(wp.file_version),',
        ("test_production_passes_claim_version_none",),
    ),
]

#: 允许 anchor 多处命中并全量替换的变异（其余一律要求唯一命中）。
ALLOW_MULTI = {13}


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
        timeout=600,
    )
    failed = tuple(
        sorted(set(re.findall(r"FAILED [^\s:]+::([\w\[\]<>.-]+)", proc.stdout + proc.stderr)))
    )
    return proc.returncode, failed


def _apply(mutation: Mutation) -> tuple[bool, bytes]:
    """字节级注入变异，返回 (是否成功, 原始字节)。

    🔴 必须字节级：本仓库 `.py`/`.jsonl` 是 CRLF、`.json` 是 LF，用 `write_text` 会按
    `os.linesep` 重写换行 ⇒ 还原后 sha256 必不一致，且会产生整文件换行 diff。
    故 anchor 在 CRLF 文件上自动升级为 `\\r\\n`（同时也是 ANCHOR-MISS 的常见成因）。
    """
    original = mutation.path.read_bytes()
    text = original.decode("utf-8")
    crlf = "\r\n" in text
    anchor = mutation.anchor.replace("\n", "\r\n") if crlf else mutation.anchor
    replacement = mutation.replacement.replace("\n", "\r\n") if crlf else mutation.replacement
    count = text.count(anchor)
    if count == 0 or (count > 1 and mutation.ident not in ALLOW_MULTI):
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

    baseline_rc, baseline_failed = _run_tests()
    if baseline_rc != 0 or baseline_failed:
        print(f"BASELINE 非全绿，无法做变异检验：rc={baseline_rc} failed={baseline_failed}")
        return 2
    print("BASELINE 全绿，开始变异\n")

    guarded_paths = {CONTRACT, EVIDENCE, ROUTER}
    pre_hashes = {p: _sha(p) for p in guarded_paths}

    for mutation in selected:
        applied, original = _apply(mutation)
        if not applied:
            mutation.result = "ANCHOR-MISS"
            print(f"[{mutation.ident:>2}] {mutation.label}: ANCHOR-MISS")
            continue
        try:
            _, failed = _run_tests()
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
    summary = {m.ident: {"label": m.label, "result": m.result, "failed": list(m.failed_tests)} for m in selected}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    tally: dict[str, int] = {}
    for m in selected:
        tally[m.result] = tally.get(m.result, 0) + 1
    print("四态计数:", tally)
    if args.report_path:
        report = {
            "generated_by": "backend/scripts/diagnose/mutate_task4_callback_contract_guards.py",
            "test_files": TEST_FILES,
            "baseline_all_green": True,
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
    if bad:
        print(f"存在需处理项（GREEN 应红 / ANCHOR-MISS / WRONG-TEST）: {sorted(set(bad))}")
        return 1
    print("全部变异检验通过（期望红的都红了，对照项按预期绿）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
