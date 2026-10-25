"""Task 3 变异检验：破坏 ingestion policy / quota / scanner provenance 关键点，确认守卫真会红。

Spec: custom-workpaper-template-ingestion-and-sync-closure
Requirements: 3.3, 3.4, 3.5, 3.6, 3.7, 4.3, 4.4, 4.5, 4.6, 4.7

用法：
    python scripts/diagnose/mutate_custom_ingestion_task3.py --check-anchors   # 只读，秒级
    python scripts/diagnose/mutate_custom_ingestion_task3.py --apply           # 逐条打补丁+复原

🔴 不看退出码下结论：区分 RED（真打红预期项）/ GREEN（守卫缺陷）/
   ANCHOR-MISS（脚本缺陷：锚点未命中或命中 >1）/ WRONG-TEST（打红了但不是
   预期项 = 污染残留或锚点错行）。

锚点约定（比 Task 2 更严）：一律**单行**行首锚定正则 —— 多行锚点在 CRLF/换行
归一化下极易 MISS，而单行锚点唯一且短。
🔴 正则特殊字符必须转义：``(`` ``)`` ``{`` ``}`` ``[`` ``]`` —— 否则整段被当
捕获组或字符类，表现为 unterminated subpattern 或静默 0 命中。
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

#: .../backend/scripts/diagnose/x.py → repo root
ROOT = Path(__file__).resolve().parents[3]
POL = ROOT / "backend/app/services/custom_template_ingestion/policy.py"

# pytest rootdir / pytest.ini 在 backend/
PYTEST_ARGS = [
    sys.executable, "-m", "pytest",
    "tests/custom_template_ingestion/test_policy.py", "-q", "-p", "no:randomly",
    "--tb=line",
]
PYTEST_CWD = ROOT / "backend"

# 🔴 字节级捕获 + 显式 UTF-8：Windows 默认 GBK 会在 pytest 的中文输出上
# UnicodeDecodeError，导致 stdout=None、变异判据静默失效。
ENVPATCH: dict[str, str] = {**os.environ, "PYTHONIOENCODING": "utf-8"}


@dataclass(frozen=True)
class Case:
    """一条变异。

    file: 被改文件；anchor: 行首锚定单行正则（re.MULTILINE，必须恰好命中 1 次）；
    replacement: 替换文本（原样字符串，re.subn 的 replacement 语义：``\\`` 需写
    成 ``\\\\`` 才能进字面反斜杠）；wants: 预期变红的测试名。
    """

    id: str
    file: Path
    anchor: str
    replacement: str
    wants: tuple[str, ...]
    requirement: str


CASES: list[Case] = [
    # ── Requirement 3.6：空报告不再产出 BLOCKER（最核心的假绿防线）──
    # 🔴 变异点在「空报告 finding 的生成」而非 derive_verdict 的空分支 ——
    # 后者即使破坏，空报告已有 1 条 finding，verdict 仍由 BLOCKER finding 派生。
    Case(
        id="M1-empty-report-yields-no-blocker",
        file=POL,
        anchor=r"            code=FINDING_EMPTY_REPORT,$",
        replacement="            code=FINDING_EMPTY_REPORT if False else FINDING_WITHIN_LIMITS,",
        wants=(
            "test_empty_observation_never_yields_valid",
        ),
        requirement="3.6",
    ),
    # ── Requirement 3.6：derive_verdict 空 findings 隐式 PASS ──
    Case(
        id="M1b-derive-verdict-empty-implicit-pass",
        file=POL,
        anchor=r"        return Verdict\.BLOCKED$",
        replacement="        return Verdict.PREFLIGHT_READY",
        wants=(
            "test_derive_verdict_has_no_implicit_pass_branch",
        ),
        requirement="3.6",
    ),
    # ── Requirement 3.6：越界观测不再报 BLOCKER ──
    Case(
        id="M2-exceeded-observation-ignored",
        file=POL,
        anchor=r"        if value > limit:$",
        replacement="        if False and value > limit:",
        wants=("test_each_limit_is_enforced_as_structured_blocker",),
        requirement="3.6/3.7",
    ),
    # ── Requirement 3.6：非法观测值（负数/NaN）不再阻断 ──
    Case(
        id="M3-invalid-observation-ignored",
        file=POL,
        anchor=r"        if not _is_valid_observation\(value\):$",
        replacement="        if False and not _is_valid_observation(value):",
        wants=("test_negative_observation_is_blocked_not_zeroed",),
        requirement="3.6",
    ),
    # ── Requirement 4.7：未知能力默认 ALLOW（fail-open）──
    Case(
        id="M4-unknown-feature-defaults-allow",
        file=POL,
        anchor=r"    return FEATURE_MATRIX\.get\(key, FeatureDecision\.BLOCK_PENDING_POLICY\)$",
        replacement="    return FEATURE_MATRIX.get(key, FeatureDecision.ALLOW_TO_PREFLIGHT)",
        wants=("test_unknown_feature_is_block_pending_policy_not_allowed",),
        requirement="4.7",
    ),
    # ── Requirement 4.4：.xlsm 可 finalize（PREFLIGHT_ONLY 被放进 FINALIZE_CAPABLE）──
    Case(
        id="M5-xlsm-becomes-finalize-capable",
        file=POL,
        anchor=r"    FeatureDecision\.ALLOW_TO_PREFLIGHT,$",
        replacement="    FeatureDecision.ALLOW_TO_PREFLIGHT, FeatureDecision.PREFLIGHT_ONLY,",
        wants=("test_xlsm_is_preflight_only_and_never_finalize_capable",),
        requirement="4.4",
    ),
    # ── Requirement 4.5：VBA 宏放行（无豁免路径）──
    Case(
        id="M6-vba-macro-allowed",
        file=POL,
        anchor=r'    "vba_macro": FeatureDecision\.BLOCK,$',
        replacement='    "vba_macro": FeatureDecision.ALLOW_TO_PREFLIGHT,',
        wants=("test_macro_dde_activex_ole_are_blocked",),
        requirement="4.5",
    ),
    # ── Requirement 4.6：external link 放行（v1 永久 BLOCKER 被打开）──
    Case(
        id="M7-external-link-allowed",
        file=POL,
        anchor=r'    "external_link": FeatureDecision\.BLOCK,$',
        replacement='    "external_link": FeatureDecision.ALLOW_TO_PREFLIGHT,',
        wants=("test_external_links_are_permanently_blocked_in_v1",),
        requirement="4.6",
    ),
    # ── Requirement 3.4：阈值变化不再使旧 evidence stale ──
    Case(
        id="M8-policy-threshold-change-not-stale",
        file=POL,
        anchor=r"            self\.policy_fingerprint != policy\.fingerprint\(\)$",
        replacement="            True",
        wants=("test_policy_threshold_change_makes_old_evidence_stale",),
        requirement="3.4",
    ),
    # ── Requirement 3.5：未知 scanner build 复用旧 PASS ──
    # 🔴 变异方向必须是「scanner build 变化不再算 stale」（or False）——
    # 若写成 or True，stale 恒为 True，反而会满足「变化即 stale」的断言。
    Case(
        id="M9-scanner-build-change-not-stale",
        file=POL,
        anchor=r"            or self\.scanner_build_digest != scanner_build_digest$",
        replacement="            or False",
        wants=("test_scanner_build_change_makes_old_evidence_stale",),
        requirement="3.5",
    ),
    # ── Requirement 3.4：只比 version 字符串（阈值漂移不可见）──
    Case(
        id="M10-staleness-by-version-string",
        file=POL,
        anchor=r"            self\.policy_fingerprint != policy\.fingerprint\(\)$",
        replacement="            self.policy_version != policy.version",
        wants=("test_staleness_comparing_fingerprints_not_version_strings",),
        requirement="3.4",
    ),
    # ── Requirement 17.2 变异项：手工注入 policy_fingerprint 绕过 stale 判定 ──
    # 🔴 `sha256(payload.encode("utf-8")).hexdigest()` 在文件里命中 2 次
    # （policy.fingerprint 与 provenance.fingerprint 各一），必须用前一行
    # 区分 provenance 的那个。
    Case(
        id="M11-fingerprint-echoes-scanner-build",
        file=POL,
        anchor=r"        return hashlib\.sha256\(payload\.encode\(\"utf-8\"\)\)\.hexdigest\(\)\n\n    def is_stale_for",
        replacement='        return self.scanner_build_digest\n\n    def is_stale_for',
        wants=("test_provenance_fingerprint_is_derived_not_client_supplied",),
        requirement="3.5/17.2",
    ),
    # ── Requirement 3.3：组织存储 quota 忽略 pending_upload（并发爆库）──
    Case(
        id="M12-storage-ignores-pending-upload",
        file=POL,
        anchor=r"    projected = storage_used_bytes \+ pending_upload_bytes$",
        replacement="    projected = storage_used_bytes",
        wants=("test_organization_storage_quota_accounts_for_pending_upload",),
        requirement="3.3",
    ),
    # ── Requirement 3.7：quota 输入非法时仍拒绝（code 改名即打红）──
    Case(
        id="M13-invalid-quota-input-code-renamed",
        file=POL,
        anchor=r'            code="POLICY\.quota_input_invalid",$',
        replacement='            code="POLICY.quota_input_ignored",',
        wants=("test_organization_quota_fails_closed_on_invalid_input",),
        requirement="3.7",
    ),
    # ── Requirement 3.6：bool 观测值被当数字放行 ──
    Case(
        id="M14-boolean-observation-accepted",
        file=POL,
        anchor=r"    if isinstance\(value, bool\):$",
        replacement="    if False and isinstance(value, bool):",
        wants=("test_boolean_observation_is_not_accepted_as_number",),
        requirement="3.6",
    ),
    # ── Requirement 3.3：压缩比一致性自洽校验被绕过 ──
    Case(
        id="M15-compression-ratio-consistency-bypassed",
        file=POL,
        anchor=r"        if self\.max_entry_compression_ratio > self\.max_total_compression_ratio \+ 1e-9:$",
        replacement="        if False and self.max_entry_compression_ratio > self.max_total_compression_ratio + 1e-9:",
        wants=("test_policy_enforces_compression_ratio_consistency",),
        requirement="3.3",
    ),
    # ── Requirement 15.6：TTL 递增校验被绕过 ──
    Case(
        id="M16-ttl-ordering-bypassed",
        file=POL,
        anchor=r"        if not \($",
        replacement="        if not True and not (",
        wants=("test_policy_enforces_ttl_strictly_increasing",),
        requirement="3.3/15.6",
    ),
    # ── Requirement 4.5：DDE 放行 ──
    Case(
        id="M17-dde-link-allowed",
        file=POL,
        anchor=r'    "dde_link": FeatureDecision\.BLOCK,$',
        replacement='    "dde_link": FeatureDecision.ALLOW_TO_PREFLIGHT,',
        wants=("test_macro_dde_activex_ole_are_blocked",),
        requirement="4.5",
    ),
]


def _count_matches(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text, re.MULTILINE))


def check_anchors() -> int:
    """只读校验：每条锚点必须命中且仅命中 1 次。"""
    bad = 0
    for case in CASES:
        text = case.file.read_text(encoding="utf-8")
        try:
            n = _count_matches(text, case.anchor)
        except re.error as exc:
            print(f"  [ANCHOR-MISS] {case.id} 正则非法: {exc}")
            bad += 1
            continue
        status = "OK" if n == 1 else "ANCHOR-MISS"
        if n != 1:
            bad += 1
        print(f"  [{status}] {case.id} (n={n})")
    print(f"\nANCHOR-MISS 条数: {bad}/{len(CASES)}")
    return 1 if bad else 0


def run_pytest() -> tuple[int, bytes]:
    """返回 (exit code, stdout 字节)。cwd=backend（pytest rootdir）。"""
    proc = subprocess.run(
        PYTEST_ARGS, cwd=str(PYTEST_CWD), capture_output=True, env=ENVPATCH,
    )
    return proc.returncode, proc.stdout


def apply_one(case: Case) -> str:
    """对单条变异打补丁并复原，返回四态结论。"""
    text = case.file.read_text(encoding="utf-8")
    n = _count_matches(text, case.anchor)
    if n != 1:
        return f"{case.id}: ANCHOR-MISS (n={n})"
    new_text, cnt = re.subn(case.anchor, case.replacement, text, count=1,
                            flags=re.MULTILINE)
    if cnt != 1:
        return f"{case.id}: ANCHOR-MISS (subn={cnt})"

    backup = case.file.with_suffix(case.file.suffix + ".bak")
    shutil.copy2(case.file, backup)
    try:
        case.file.write_text(new_text, encoding="utf-8")
        rc, out = run_pytest()
        if rc == 0:
            return (f"{case.id}: GREEN ✗ —— 守卫缺陷！破坏 Requirement "
                    f"{case.requirement} 后测试仍全绿")
        out_str = out.decode("utf-8", errors="replace")
        hit = [w for w in case.wants if w in out_str]
        if len(hit) != len(case.wants):
            failed = [l for l in out_str.splitlines() if "FAILED" in l][:5]
            return (f"{case.id}: WRONG-TEST ✗ —— 预期项 {case.wants} 未全部打红；"
                    f"实际: {failed}")
        return f"{case.id}: RED ✓ —— 预期项 {hit} 全部变红"
    finally:
        shutil.copy2(backup, case.file)
        backup.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-anchors", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    if args.check_anchors:
        return check_anchors()

    if not args.apply:
        print(__doc__)
        return 0

    rc, out = run_pytest()
    if rc != 0:
        print(f"✗ 基线不绿 (rc={rc})，先修守卫再跑变异")
        print(out.decode("utf-8", errors="replace")[-2000:])
        return 1
    print("✓ 基线全绿\n")

    bad = 0
    for case in CASES:
        result = apply_one(case)
        print(f"  {result}")
        if "✗" in result:
            bad += 1
    print(f"\n守卫缺陷/脚本缺陷条数: {bad}/{len(CASES)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
