#!/usr/bin/env python3
r"""
attachment-ocr-ai-evidence-governance-hardening — 最终发布门聚合器 (Task 11.4)

唯一基线：requirements.md §8 Priority and Release Gates + design.md §14 Release Gates。

本脚本 **诚实聚合** 每个发布门项目的真实当前状态并计算 overall pass/fail：

  1. R1–R15 验收（映射到覆盖它们的测试套件/UAT）
  2. P1–P29 属性测试（Wave 8 PBT 组 9.1–9.6，HYPOTHESIS_MAX_EXAMPLES=1；P30 由 Task 11.3
     固定不可变快照单独验收，此处仅引用、不并入 UAT-15）
  3. UAT-01～15（Wave 9 Playwright 套件 + 后端 wave9 router 功能/接线 PG 证据）
  4. 真实 PG16 约束/并发/trigger 证据
  5. 八项既有引擎 adapter 契约（check_evidence_no_fork + adapter contract tests）
  6. AI coverage gap == 0（check_ai_entry_coverage + compute_coverage_gap）
  7. offline manifest 验签（offline_manifest_verifier 套件）
  8. 6000 VU 容量报告（task 8.2 工具 —— 实际 6000 VU 运行需专用容量环境；此处仅核验
     是否存在机器可读容量报告及其 verdict，缺失即记为 pending，绝不伪造 6000 VU 通过）
  9. migration health gate + rollback 演练（task 11.2）

只有当 **全部 required 门为 GREEN** 时 overall_verdict 才为 RELEASE-READY；否则 BLOCKED，
保持实施状态待执行并记录阻断项。

用法：
    python backend/scripts/release/evidence_governance_release_gate.py            # 后端门 + CI 守卫 + 工件核验
    python backend/scripts/release/evidence_governance_release_gate.py --with-playwright  # 额外驱动 Wave 9 Playwright UAT
    python backend/scripts/release/evidence_governance_release_gate.py --out <path.json>

退出码：overall RELEASE-READY -> 0；BLOCKED -> 1。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# ─── 路径常量 ─────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPT_DIR.parent.parent            # backend/
PROJECT_ROOT = BACKEND_DIR.parent                 # GT_plan/
SPEC_DIR = PROJECT_ROOT / ".kiro" / "specs" / "attachment-ocr-ai-evidence-governance-hardening"
FRONTEND_DIR = PROJECT_ROOT / "audit-platform" / "frontend"
DEFAULT_OUT = SPEC_DIR / "release_evidence.json"

# RED 门逐项 triage（RE-VERIFY 后的诚实结论；Task 2.3/2.5 曾假绿）
TRIAGE_FINDINGS = {
    "PG16-migration-hygiene-assertions": {
        "verdict": "RED — 3 项失败断言，均为迁移簿记/卫生层（非运行时 PG 行为）",
        "runtime_pg_behavior": "GREEN — 约束/并发/trigger/复合FK/immutable/CAS 运行时契约见 "
                               "PG16-constraint-trigger-concurrency (52 passed)，未受影响。",
        "findings": [
            {
                "test": "test_evidence_governance_wave1_capstone_v2_5.py::"
                        "test_checksum_drift_guard_method_exists_and_returns_list / "
                        "test_checksum_drift_guard_detects_edited_migration",
                "classification": "genuine-gap",
                "detail": "MigrationRunner.detect_checksum_drift() 与 ChecksumDrift 从未实现——"
                          "Task 2.3/2.5 capstone 断言它们已加入，实为 false-green。属 R14/P28 迁移防漂移"
                          "硬化缺口（migration_runner 目前只存 checksum 到 schema_version，无 drift 检测 API）。",
            },
            {
                "test": "test_evidence_governance_wave1_capstone_v2_5.py::"
                        "test_every_orm_column_present_in_wave1_migrations",
                "classification": "wave1-parity-gap",
                "detail": "ORM 列 ocr_jobs.next_retry_at 仅由跨 feature 修复迁移 V110 补建，"
                          "不在本 spec 的 Wave-1 迁移 (V106/V107/V108) 中；列在 DB 中真实存在，"
                          "但 Wave-1 迁移文件不自洽。",
            },
            {
                "test": "test_evidence_governance_ocr_citation_review_archive_hold_v108.py::"
                        "test_v108_no_duplicate_and_is_highest",
                "classification": "stale-bookkeeping",
                "detail": "断言 V108 为最高迁移号，现已过时——后续 feature 推进到 V112（procedure-delegation/"
                          "evidence 修复等）。此为陈旧簿记假设，非本 spec 运行时缺陷。",
            },
        ],
        "release_impact": "阻断 R14（迁移兼容/防漂移硬化）与 P28 卫生断言；不影响 P28 幂等运行时 PBT"
                          "(PBT-9.6 GREEN) 与 PG16 运行时契约。建议：①实现 detect_checksum_drift/ChecksumDrift "
                          "或修订 Task 2.3/2.5 断言；②将 next_retry_at 纳入 Wave-1 迁移或放宽 parity 扫描范围至"
                          "含修复迁移；③修订 highest-migration 断言为动态最高号。",
    },
    "capacity-6000vu": {
        "verdict": "PENDING — 需专用容量环境执行真实 6000 VU 压测",
        "classification": "pending-dedicated-environment",
        "detail": "task 8.2 工具链就绪（scenario.json 契约 + capacity_report.generate_report 纯函数生成器 + "
                  "connection_budget + chaos + locustfile + test_capacity_tooling 全绿），但本机未执行真实 "
                  "6000 VU + 30min 稳态/10min 突发 + PgBouncer/PG 配额压测，故无机器可读容量报告工件。"
                  "按发布门要求，此项 pending，绝不伪造 6000 VU 通过。UAT-15 的用户可见背压/降级维度已由 "
                  "Playwright migration-capacity spec 覆盖（含 §10.2 记录的容量环境 skip 交叉引用）。",
        "release_impact": "阻断 R15 容量验收的实测 6000 VU 部分（R15 其余降级安全维度经 PBT P29 + Playwright 覆盖）。",
    },
}

PYTEST_SUMMARY_RE = re.compile(
    r"=+\s*(?:(\d+)\s+failed[, ]*)?(?:(\d+)\s+passed[, ]*)?(?:(\d+)\s+skipped[, ]*)?"
    r"(?:(\d+)\s+errors?[, ]*)?(?:(\d+)\s+xfailed[, ]*)?(?:(\d+)\s+deselected[, ]*)?.*?=+\s*$"
)
FALSIFY_RE = re.compile(r"Falsifying example:.*?(?=\n\n|\nFAILED|\n=|\Z)", re.DOTALL)


# ─── 门结果模型 ────────────────────────────────────────────────────────────────
@dataclass
class GateResult:
    gate_id: str
    category: str
    description: str
    requirements: list[str]
    properties: list[str] = field(default_factory=list)
    uat: list[str] = field(default_factory=list)
    kind: str = "pytest"            # pytest | ci_guard | artifact | playwright | reference | derived
    required: bool = True           # 是否属于发布必需门
    status: str = "not_run"         # green | red | pending | error | not_run
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    returncode: int | None = None
    targets: list[str] = field(default_factory=list)
    detail: str = ""
    falsifying_example: str | None = None
    duration_s: float | None = None


def _parse_pytest_summary(text: str) -> dict:
    """从 pytest 输出解析 passed/failed/skipped/errors。

    取最后一条包含 passed/failed/error/skipped/'no tests ran' 的摘要行，
    对其中每个计数词做全局提取（对 -q 装饰行与非装饰行都稳健）。
    """
    out = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0, "no_tests": False}
    summary_line = None
    for line in reversed(text.strip().splitlines()):
        s = line.strip().strip("=").strip()
        if not s:
            continue
        if re.search(r"\bno tests ran\b", s):
            out["no_tests"] = True
            summary_line = s
            break
        if re.search(r"\b\d+\s+(passed|failed|error|errors|skipped|xfailed|xpassed|deselected)\b", s):
            summary_line = s
            break
    if summary_line:
        for key, kw in (("failed", r"failed"), ("passed", r"passed"),
                        ("skipped", r"skipped"), ("errors", r"errors?")):
            mm = re.search(rf"(\d+)\s+{kw}\b", summary_line)
            if mm:
                out[key] = int(mm.group(1))
    return out


def run_pytest_gate(gate: GateResult, extra_env: dict | None = None,
                    timeout: int = 900) -> GateResult:
    env = dict(os.environ)
    env.setdefault("HYPOTHESIS_MAX_EXAMPLES", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if extra_env:
        env.update(extra_env)
    cmd = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider",
           "--no-header", "-q", "-o", "addopts=", *gate.targets]
    t0 = datetime.now(timezone.utc)
    try:
        proc = subprocess.run(cmd, cwd=str(BACKEND_DIR), env=env,
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        gate.returncode = proc.returncode
        counts = _parse_pytest_summary(out)
        gate.passed, gate.failed = counts["passed"], counts["failed"]
        gate.skipped, gate.errors = counts["skipped"], counts["errors"]
        fm = FALSIFY_RE.search(out)
        if fm:
            gate.falsifying_example = fm.group(0).strip()[:2000]
        # 判定
        if gate.errors or gate.failed:
            gate.status = "red"
            gate.detail = _tail(out, 1400)
        elif counts["no_tests"] or gate.returncode == 5:  # no tests collected/ran
            gate.status = "error"
            gate.detail = "no tests collected/ran: " + _tail(out, 600)
        elif gate.returncode == 0 and (gate.passed > 0 or gate.skipped > 0):
            gate.status = "green"
            gate.detail = f"passed={gate.passed} skipped={gate.skipped}"
        else:
            gate.status = "error"
            gate.detail = _tail(out, 1200)
    except subprocess.TimeoutExpired:
        gate.status = "error"
        gate.detail = f"TIMEOUT after {timeout}s"
    gate.duration_s = round((datetime.now(timezone.utc) - t0).total_seconds(), 1)
    return gate


def run_ci_guard(gate: GateResult, script_rel: str, args: list[str],
                 timeout: int = 180) -> GateResult:
    cmd = [sys.executable, str(BACKEND_DIR / script_rel), *args]
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    t0 = datetime.now(timezone.utc)
    try:
        proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env,
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        gate.returncode = proc.returncode
        gate.status = "green" if proc.returncode == 0 else "red"
        gate.detail = _tail(out, 1200)
    except subprocess.TimeoutExpired:
        gate.status = "error"
        gate.detail = f"TIMEOUT after {timeout}s"
    gate.duration_s = round((datetime.now(timezone.utc) - t0).total_seconds(), 1)
    return gate


def _tail(text: str, n: int) -> str:
    text = text.strip()
    return text[-n:] if len(text) > n else text


# ─── 6000 VU 容量报告工件核验（绝不伪造）─────────────────────────────────────
def check_capacity_report(gate: GateResult) -> GateResult:
    """核验是否存在机器可读 6000 VU 容量报告及其 verdict。

    仅当存在报告 JSON 且 passed==True 且 peak>=6000 才 green；否则 pending（不伪造）。
    """
    candidates = [
        BACKEND_DIR / "tests" / "load" / "evidence_governance_capacity" / "capacity_run_report.json",
        BACKEND_DIR / "tests" / "load" / "evidence_governance_capacity" / "capacity_report_6000vu.json",
        SPEC_DIR / "capacity_report_6000vu.json",
        PROJECT_ROOT / "capacity_report_6000vu.json",
    ]
    found = next((p for p in candidates if p.exists()), None)
    if not found:
        gate.status = "pending"
        gate.detail = (
            "未找到机器可读 6000 VU 容量报告工件；实际 6000 VU 运行需专用容量环境 "
            "(locust harness + PgBouncer/PG 配额)。task 8.2 工具已就绪 "
            "(scenario.json 契约 + capacity_report.generate_report 生成器 + test_capacity_tooling)，"
            "但未在本机执行真实 6000 VU 压测。按发布门要求，此项 pending，不伪造 6000 VU 通过。"
        )
        return gate
    try:
        rep = json.loads(found.read_text(encoding="utf-8"))
        peak = rep.get("peak_virtual_users", 0)
        ok = bool(rep.get("passed")) and peak >= 6000
        gate.status = "green" if ok else "red"
        gate.detail = (f"capacity report: {found.name} passed={rep.get('passed')} "
                       f"peak={peak} err%={rep.get('error_rate_pct')} "
                       f"leakage={rep.get('cross_project_leakage')}")
    except (OSError, json.JSONDecodeError) as e:
        gate.status = "error"
        gate.detail = f"容量报告解析失败: {e}"
    return gate


# ─── Wave 9 Playwright UAT ────────────────────────────────────────────────────
# 本 spec 的 Playwright UAT 套件（按 config 分两组）。刻意排除 note-spec-uat.spec.ts /
# offline-roundtrip.spec.ts —— 它们属 disclosure-notes(note-spec) 另一 feature，不计入本门。
PLAYWRIGHT_UAT_SETS = [
    # (config, [spec 相对路径])
    (None, [  # 默认 playwright.config.ts (testDir=./e2e)
        "e2e/evidence-governance-secure-intake-uat.spec.ts",     # UAT-01/02/03
        "e2e/evidence-governance-secure-receipt-uat.spec.ts",    # 安全读取
        "e2e/uat-ocr-rag-governance.spec.ts",                    # UAT-06/07/08/09 + A1-A6
    ]),
    ("playwright-uat.config.ts", [  # testDir=./e2e-uat
        "e2e-uat/evidence-governance-attachment-ref-uat.spec.ts",      # UAT-04/05
        "e2e-uat/evidence-governance-ai-review-archive-hold.spec.ts",  # UAT-10/11/12/13
        "e2e-uat/evidence-governance-migration-capacity-uat.spec.ts",  # UAT-14/15
    ]),
]


def run_playwright_uat(gate: GateResult, timeout: int = 1800) -> GateResult:
    """驱动 Wave 9 Playwright UAT 套件（需 3030 前端 + 9980 后端 + 已安装浏览器）。

    仅统计本 spec 的 evidence-governance UAT specs；note-spec/offline-roundtrip 属另一 feature，
    刻意排除。跨两个 playwright config 聚合，并保留 per-file / skip 明细。
    """
    if not (FRONTEND_DIR / "package.json").exists():
        gate.status = "pending"
        gate.detail = "frontend 目录不可用"
        return gate
    total = {"passed": 0, "failed": 0, "skipped": 0}
    per_file: list[dict] = []
    ran_files: list[str] = []
    t0 = datetime.now(timezone.utc)
    for idx, (config, specs) in enumerate(PLAYWRIGHT_UAT_SETS):
        existing = [s for s in specs if (FRONTEND_DIR / s).exists()]
        if not existing:
            continue
        ran_files.extend(existing)
        report_json = FRONTEND_DIR / f"playwright-uat-set{idx}.json"
        cmd = ["npx", "playwright", "test"]
        if config:
            cmd += ["--config", config]
        cmd += [*existing, "--reporter=json", "--workers=1"]
        env = dict(os.environ)
        env["PLAYWRIGHT_JSON_OUTPUT_NAME"] = str(report_json)
        try:
            subprocess.run(cmd, cwd=str(FRONTEND_DIR), env=env,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, shell=True)
        except subprocess.TimeoutExpired:
            gate.status = "error"
            gate.detail = f"Playwright set{idx} TIMEOUT after {timeout}s"
            gate.duration_s = round((datetime.now(timezone.utc) - t0).total_seconds(), 1)
            return gate
        except FileNotFoundError:
            gate.status = "pending"
            gate.detail = "npx/playwright 不可用"
            return gate
        pf = _playwright_per_file(report_json)
        for row in pf:
            total["passed"] += row["passed"]
            total["failed"] += row["failed"]
            total["skipped"] += row["skipped"]
        per_file.extend(pf)
    gate.targets = ran_files
    gate.passed = total["passed"]
    gate.failed = total["failed"]
    gate.skipped = total["skipped"]
    gate.duration_s = round((datetime.now(timezone.utc) - t0).total_seconds(), 1)
    grand = total["passed"] + total["failed"] + total["skipped"]
    detail_files = "; ".join(f"{r['file']}:{r['passed']}p/{r['skipped']}s/{r['failed']}f"
                             for r in per_file)
    if grand == 0:
        gate.status = "error"
        gate.detail = "Playwright 未产出结果（检查 3030/9980 与浏览器）"
    elif total["failed"] == 0 and total["passed"] > 0:
        gate.status = "green"
        gate.detail = (f"passed={total['passed']} skipped={total['skipped']} "
                       f"(skips 为 design §10.2 PBT 覆盖维度) | {detail_files}")
    else:
        gate.status = "red"
        gate.detail = f"failed={total['failed']} passed={total['passed']} | {detail_files}"
    return gate


def _playwright_per_file(report_path: Path) -> list[dict]:
    """从 playwright json report 读取 per-file passed/skipped/failed。"""
    if not report_path.exists():
        return []
    try:
        d = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    def walk(suite, fil):
        for sp in suite.get("specs", []):
            for t in sp.get("tests", []):
                yield t.get("status")
        for s in suite.get("suites", []):
            yield from walk(s, fil)

    out = []
    for suite in d.get("suites", []):
        fil = suite.get("file", "")
        p = f = s = 0
        for st in walk(suite, fil):
            if st == "expected":
                p += 1
            elif st == "skipped":
                s += 1
            else:
                f += 1
        out.append({"file": fil, "passed": p, "skipped": s, "failed": f})
    return out


# ─── 门注册表 ──────────────────────────────────────────────────────────────────
def build_gates() -> list[GateResult]:
    T = "tests/"
    A = "tests/attachment_ocr_ai_evidence_governance_hardening/"
    E = "tests/evidence_governance/"
    return [
        # ── P1–P29 属性组 (Wave 8) ──
        GateResult("PBT-9.1-security-attachment", "properties",
                   "安全/附件引用属性组 P1–P8", ["R1", "R2", "R3", "R4", "R11", "R14"],
                   properties=["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"],
                   targets=[A + "test_security_attachment_ref_property_group_pbt.py",
                            A + "test_association_scope_baseline_pbt.py"]),
        GateResult("PBT-9.2-ocr", "properties",
                   "OCR 属性组 P9–P14", ["R5", "R6"],
                   properties=["P9", "P10", "P11", "P12", "P13", "P14"],
                   targets=[T + "test_evidence_governance_ocr_properties_wave8_9_2.py"]),
        GateResult("PBT-9.3-rag-ai", "properties",
                   "RAG/AI 属性组 P15–P19", ["R7", "R8", "R9"],
                   properties=["P15", "P16", "P17", "P18", "P19"],
                   targets=[T + "test_evidence_governance_rag_ai_properties_wave8_9_3.py"]),
        GateResult("PBT-9.4-stale-review", "properties",
                   "stale-review 属性组 P20–P22", ["R9", "R10"],
                   properties=["P20", "P21", "P22"],
                   targets=[T + "test_evidence_governance_stale_review_properties_wave8_9_4.py",
                            T + "test_evidence_governance_stale_review_wave8_9_4.py"]),
        GateResult("PBT-9.5-archive-hold", "properties",
                   "archive-hold 属性组 P23–P27", ["R11", "R12", "R13"],
                   properties=["P23", "P24", "P25", "P26", "P27"],
                   targets=[T + "test_evidence_governance_archive_hold_properties_wave8_9_5.py"]),
        GateResult("PBT-9.6-migration-quality", "properties",
                   "migration-quality 属性组 P28–P29 (P30 独立门)", ["R14", "R15", "R16"],
                   properties=["P28", "P29"],
                   targets=[T + "test_evidence_governance_migration_quality_properties_wave8_9_6.py"]),
        # ── 真实 PG16 约束/并发/trigger (运行时行为) ──
        GateResult("PG16-constraint-trigger-concurrency", "pg16",
                   "真实 PG16 约束/并发/trigger/复合FK/immutable/CAS 运行时契约",
                   ["R1", "R2", "R3", "R5", "R6", "R11", "R12", "R13"],
                   targets=[E + "test_citation_snapshot_pg16_contract.py",
                            E + "test_archive_hold_capstone_wave6_7_5.py",
                            T + "test_evidence_governance_attachment_versions_v106.py",
                            T + "test_evidence_governance_legacy_alias_evidence_ref_v107.py"]),
        # ── 迁移 parity / checksum-drift / highest-migration 断言 (R14/P28 卫生) ──
        # 这些是迁移簿记类断言，与运行时 PG 行为分离；当前 RED，见 detail 的逐项 triage。
        GateResult("PG16-migration-hygiene-assertions", "pg16",
                   "迁移 ORM-parity / checksum-drift / highest-migration 断言 (R14/P28 卫生)",
                   ["R14"], properties=["P28"],
                   targets=[T + "test_evidence_governance_ocr_citation_review_archive_hold_v108.py",
                            T + "test_evidence_governance_wave1_capstone_v2_5.py"]),
        # ── 八引擎 adapter 契约 ──
        GateResult("adapter-contracts", "adapter",
                   "八项既有引擎 typed adapter 契约",
                   ["R1", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10", "R11"],
                   targets=[E + "test_engine_adapter_contracts.py",
                            T + "test_evidence_typed_adapters_contract.py"]),
        # ── offline manifest 验签 ──
        GateResult("offline-manifest-verifier", "offline",
                   "offline manifest 成员/hash/签名验签器",
                   ["R11"],
                   targets=[E + "test_archive_adapter_offline_verifier.py",
                            E + "test_archive_manifest_service.py"]),
        # ── Wave 9 router 后端功能/接线 (UAT 后端证据) ──
        GateResult("wave9-router-functional-pg", "uat-backend",
                   "Wave 9 治理 HTTP router 接线 + 功能 PG 证据 (UAT 后端维度)",
                   ["R1", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10", "R11", "R13"],
                   uat=["UAT-01", "UAT-02", "UAT-03", "UAT-04", "UAT-05", "UAT-06",
                        "UAT-07", "UAT-08", "UAT-09", "UAT-10", "UAT-11", "UAT-12", "UAT-13"],
                   targets=[A + "test_wave9_router_wiring_contract.py",
                            A + "test_wave9_router_functional_pg.py",
                            A + "test_evidence_governance_http_wiring_integration.py",
                            E + "test_wave9_router_wiring_integration.py"]),
        # ── migration health gate + rollback 演练 (11.2) ──
        GateResult("migration-health-rollback", "health",
                   "migration health gate + 完整回滚演练 (task 11.2)",
                   ["R11", "R12", "R13", "R14", "R15"],
                   targets=[A + "test_migration_health_gate_rollback_rehearsal_pg.py"]),
        # ── P30 固定不可变快照 (11.3, 独立门, 引用) ──
        GateResult("P30-fixed-snapshot", "reference",
                   "P30 固定不可变快照独立门 (task 11.3；不并入 UAT-15)",
                   ["R16"], properties=["P30"], required=False,
                   targets=[T + "test_evidence_governance_release_gate_p30_fixed_snapshot_task_11_3.py"]),
        # ── CI 守卫 ──
        GateResult("ci-traceability", "ci_guard",
                   "三件套追溯与完成守卫 (R1–R16/P1–P30/UAT/55叶子/依赖图)",
                   ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10",
                    "R11", "R12", "R13", "R14", "R15", "R16"], kind="ci_guard"),
        GateResult("ci-no-fork", "ci_guard",
                   "八引擎禁止分叉守卫", ["R1", "R5", "R7", "R8", "R9", "R11", "R12", "R15"],
                   kind="ci_guard"),
        GateResult("ci-ai-entry-coverage", "ci_guard",
                   "AI coverage gap == 0 (P18)", ["R8"], properties=["P18"], kind="ci_guard"),
        # ── 6000 VU 容量报告 (工件核验) ──
        GateResult("capacity-6000vu", "capacity",
                   "6000 VU 容量报告 (R15/P29；实际压测需专用容量环境)",
                   ["R15"], properties=["P29"], uat=["UAT-15"], kind="artifact"),
        # ── Wave 9 Playwright UAT (可选驱动) ──
        GateResult("playwright-uat", "uat-e2e",
                   "Wave 9 Playwright UAT-01～15 (浏览器 e2e；需 3030+9980+浏览器)",
                   ["R1", "R3", "R4", "R8", "R9", "R10", "R11", "R13", "R14", "R15"],
                   uat=[f"UAT-{i:02d}" for i in range(1, 16)],
                   kind="playwright", required=True),
    ]


# ─── R1–R15 派生汇总 ──────────────────────────────────────────────────────────
def derive_requirement_status(gates: list[GateResult]) -> dict:
    """把门结果映射回 R1–R15 验收状态：某 R 只要有 green 门覆盖且无 red 门覆盖即 green。"""
    req_status: dict[str, dict] = {}
    for r in [f"R{i}" for i in range(1, 16)]:
        covering = [g for g in gates if r in g.requirements]
        greens = [g.gate_id for g in covering if g.status == "green"]
        reds = [g.gate_id for g in covering if g.status == "red"]
        pendings = [g.gate_id for g in covering if g.status in ("pending", "error")]
        if reds:
            st = "red"
        elif greens and not pendings:
            st = "green"
        elif greens and pendings:
            st = "partial"
        else:
            st = "pending"
        req_status[r] = {"status": st, "green_gates": greens,
                         "red_gates": reds, "pending_gates": pendings}
    return req_status


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--with-playwright", action="store_true",
                    help="额外驱动 Wave 9 Playwright UAT (慢；需 live e2e 环境)")
    ap.add_argument("--only", nargs="*", help="仅运行指定 gate_id (调试)")
    args = ap.parse_args()

    print("=" * 76)
    print("attachment-ocr-ai-evidence-governance-hardening — 最终发布门 (Task 11.4)")
    print("基线: requirements §8 + design §14")
    print("=" * 76)

    gates = build_gates()
    if args.only:
        gates = [g for g in gates if g.gate_id in set(args.only)]

    for g in gates:
        if g.kind == "playwright" and not args.with_playwright:
            g.status = "pending"
            g.detail = ("未在本次运行中驱动 (需 --with-playwright + live 3030/9980 + 浏览器)；"
                        "UAT 后端维度证据见 wave9-router-functional-pg；"
                        "部分 UAT 维度按 design §10.2 由 PBT 覆盖并有交叉引用。")
            print(f"[skip] {g.gate_id}: pending (playwright 未驱动)")
            continue
        print(f"[run ] {g.gate_id} ({g.category}) ...")
        if g.kind == "ci_guard":
            script = {
                "ci-traceability": "scripts/check/check_evidence_governance_traceability.py",
                "ci-no-fork": "scripts/check/check_evidence_no_fork.py",
                "ci-ai-entry-coverage": "scripts/check/check_ai_entry_coverage.py",
            }[g.gate_id]
            run_ci_guard(g, script, ["--strict"])
        elif g.kind == "artifact":
            check_capacity_report(g)
        elif g.kind == "playwright":
            run_playwright_uat(g)
        else:
            run_pytest_gate(g)
        print(f"       -> {g.status.upper()}  ({g.detail[:90] if g.detail else ''})")

    req_status = derive_requirement_status(gates)

    # ── overall verdict ──
    required_gates = [g for g in gates if g.required]
    blocking = [g.gate_id for g in required_gates if g.status != "green"]
    overall = "RELEASE-READY" if not blocking else "BLOCKED"

    payload = {
        "spec": "attachment-ocr-ai-evidence-governance-hardening",
        "task": "11.4",
        "baseline": "requirements.md §8 Priority and Release Gates + design.md §14 Release Gates",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hypothesis_max_examples": os.environ.get("HYPOTHESIS_MAX_EXAMPLES", "1"),
        "database_url_scheme": "postgresql" if _pg_is_postgres() else "non-postgres",
        "overall_verdict": overall,
        "blocking_gates": blocking,
        "gate_summary": {
            "total": len(gates),
            "green": sum(1 for g in gates if g.status == "green"),
            "red": sum(1 for g in gates if g.status == "red"),
            "pending": sum(1 for g in gates if g.status == "pending"),
            "error": sum(1 for g in gates if g.status == "error"),
        },
        "requirements_R1_R15": req_status,
        "gates": [asdict(g) for g in gates],
        "notes": [
            "P30 由 task 11.3 固定不可变快照单独验收，不并入 UAT-15。",
            "6000 VU 实际压测需专用容量环境；缺报告即 pending，绝不伪造 6000 VU 通过。",
            "Wave 9 Playwright UAT 需 live e2e 环境；未驱动时以 wave9-router-functional-pg 提供 UAT 后端维度证据。",
            "Playwright UAT 仅统计本 spec 的 evidence-governance specs；note-spec/offline-roundtrip 属 disclosure-notes 另一 feature，其失败与本发布门无关，刻意排除。",
            "Playwright 的 4 个 skip 为 design §10.2 明文由 PBT 覆盖的维度 (UAT-07 正向原子写回 / UAT-08 越权否决 → PBT P10/P12/P13/P14；UAT-14 legacy fixture / UAT-15 6000VU 容量环境)，均带交叉引用，非隐藏失败。",
            "仅当全部 required 门为 GREEN 时才更新实施状态并发起归档评审。",
        ],
        "triage_findings": TRIAGE_FINDINGS,
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 76)
    print(f"OVERALL VERDICT: {overall}")
    if blocking:
        print(f"BLOCKING GATES ({len(blocking)}): {blocking}")
    print(f"release evidence -> {args.out}")
    print("=" * 76)
    return 0 if overall == "RELEASE-READY" else 1


def _pg_is_postgres() -> bool:
    try:
        sys.path.insert(0, str(BACKEND_DIR))
        from app.core.config import settings
        return settings.DATABASE_URL.startswith("postgresql")
    except Exception:
        return False


if __name__ == "__main__":
    sys.exit(main())
