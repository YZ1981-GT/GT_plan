r"""
attachment-ocr-ai-evidence-governance-hardening — 最终发布门聚合器 (Task 11.4)

把前序 wave 产出的证据聚合成单一 **机器可读 release evidence** 工件
(`release_evidence.json`)，并强制执行发布门 (design §14 Release Gates)。

聚合并逐项校验以下发布门 (每项 = 一个 check，含 pass/fail + 证据指针):

  1. traceability   —— 三件套追溯与完成守卫 (Task 11.1)
  2. pbt_p1_p29     —— 六个 Wave-8 属性组测试文件 (P1–P29)
  3. p30_snapshot   —— P30 固定不可变快照独立门 (`-m release_gate_p30`)
  4. uat_01_15      —— Wave 9 Playwright UAT suite (读取最新结果; 不可无头运行时
                       如实记录 per-scenario 状态, 不伪造)
  5. pg16_contracts —— 真实 PG16 约束/并发/trigger 契约 (typed adapter + governance PG)
  6. adapter_contracts —— 八引擎 adapter 契约 (未复制引擎)
  7. ai_coverage    —— AI 入口覆盖 gap = 0 (P18 scanner)
  8. offline_manifest —— 归档离线 manifest 验签
  9. capacity_6000vu —— 6000 VU 容量计划契约 (scenario.json); 若存在 live 报告则解析并逐项
                       验收 (passed/peak>=target/error_rate<阈值/泄露·重复·丢失=0), 达标才
                       PASS, 未达标/不可解析→FAIL, 无 live 报告→EVIDENCE_PENDING (不伪造 live run)
 10. health_rollback —— migration health gate + 回滚演练 (Task 11.2)

只有 **全部必需门为 pass** 时才判定 `release-ready`
(更新实施状态并发起归档评审)；否则输出 `BLOCKED` 并列出精确失败门,
且 **不得** 声称 release-ready。诚实原则: 只能在 plan/contract 级取证的门
(如 6000VU 需专用容量环境) 如实标注, 不伪造 live run。

用法:
    python backend/scripts/check/check_evidence_governance_release_gate.py [options]

    --collect-only   只列出发布门定义与执行计划, 不运行子进程 (供 dry-run / 自测)
    --output PATH    release_evidence.json 输出路径 (默认写入 spec 目录)
    --gate ID        只运行指定门 (可重复); 默认运行全部
    --timeout SEC    单门子进程超时 (默认 1800s)
    --strict         任一必需门非 pass 时返回 exit 1; 否则始终 exit 0 (报告模式)

Exit codes (仅 --strict):
    0 = release-ready (全部必需门 pass)
    1 = BLOCKED (至少一个必需门非 pass)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

# Windows GBK console 兼容
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:  # pragma: no cover - non-reconfigurable stream
    pass

# ─── 路径常量 ─────────────────────────────────────────────────────────────────

# 本文件: backend/scripts/check/check_evidence_governance_release_gate.py
BACKEND_DIR = Path(__file__).resolve().parents[2]          # backend/
ROOT = BACKEND_DIR.parent                                   # GT_plan 根
SPEC_DIR = ROOT / ".kiro" / "specs" / "attachment-ocr-ai-evidence-governance-hardening"
DEFAULT_EVIDENCE_PATH = SPEC_DIR / "release_evidence.json"

FEATURE = "attachment-ocr-ai-evidence-governance-hardening"

# 六个 Wave-8 属性组测试文件 (P1–P29 逐项覆盖; P30 由固定快照独立门单独取证)
WAVE8_PROPERTY_FILES = [
    "tests/attachment_ocr_ai_evidence_governance_hardening/test_security_attachment_ref_property_group_pbt.py",
    "tests/test_evidence_governance_ocr_properties_wave8_9_2.py",
    "tests/test_evidence_governance_rag_ai_properties_wave8_9_3.py",
    "tests/test_evidence_governance_stale_review_properties_wave8_9_4.py",
    "tests/test_evidence_governance_archive_hold_properties_wave8_9_5.py",
    "tests/test_evidence_governance_migration_quality_properties_wave8_9_6.py",
]

# 真实 PG16 约束/并发/trigger 契约 (governance PG 层)
PG16_CONTRACT_FILES = [
    "tests/evidence_governance/test_citation_snapshot_pg16_contract.py",
    "tests/test_evidence_governance_wave1_capstone_v2_5.py",
    "tests/evidence_governance/test_unified_graph_stale_closure_pbt.py",
]

ADAPTER_CONTRACT_FILE = "tests/evidence_governance/test_engine_adapter_contracts.py"
OFFLINE_VERIFIER_FILE = "tests/evidence_governance/test_archive_adapter_offline_verifier.py"
P30_SNAPSHOT_FILE = "tests/test_evidence_governance_release_gate_p30_fixed_snapshot_task_11_3.py"
HEALTH_ROLLBACK_FILE = (
    "tests/attachment_ocr_ai_evidence_governance_hardening/"
    "test_migration_health_gate_rollback_rehearsal_pg.py"
)
CAPACITY_TOOLING_FILE = "tests/load/evidence_governance_capacity/test_capacity_tooling.py"
CAPACITY_SCENARIO = "tests/load/evidence_governance_capacity/scenario.json"

TRACEABILITY_SCRIPT = "scripts/check/check_evidence_governance_traceability.py"
AI_COVERAGE_SCRIPT = "scripts/check/check_ai_entry_coverage.py"

# UAT Playwright suite (Wave 9) — 机器可读结果候选位置
UAT_RESULT_CANDIDATES = [
    "audit-platform/frontend/playwright-uat-report/results.json",
    "audit-platform/frontend/playwright-uat-report/uat-results.json",
    "audit-platform/frontend/test-results/uat-results.json",
]

# ─── 门状态常量 ───────────────────────────────────────────────────────────────

PASS = "pass"
FAIL = "fail"
ERROR = "error"
EVIDENCE_PENDING = "evidence_pending"   # 需专用环境/无头不可取证; 视为非绿, 阻断发布
SKIPPED = "skipped"

# 非 pass 一律视为阻断
_GREEN = {PASS}


# ─── 数据模型 ─────────────────────────────────────────────────────────────────

@dataclass
class GateSpec:
    id: str
    title: str
    requirements: list[str]
    kind: str                       # 'script' | 'pytest' | 'contract' | 'evidence'
    required: bool = True
    # runner 返回 (status, evidence_pointers, detail)
    runner: Optional[Callable[["GateContext"], "GateResult"]] = None


@dataclass
class GateResult:
    id: str
    title: str
    requirements: list[str]
    kind: str
    required: bool
    status: str
    evidence: list[str] = field(default_factory=list)
    detail: str = ""
    command: str = ""
    duration_s: float = 0.0
    timestamp: str = ""


@dataclass
class GateContext:
    backend_dir: Path
    root: Path
    timeout: int
    collect_only: bool


# ─── 子进程执行辅助 ──────────────────────────────────────────────────────────

def _run(cmd: list[str], ctx: GateContext) -> tuple[int, str]:
    """在 backend/ 目录运行子进程, 返回 (exit_code, tail_output)。"""
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ctx.backend_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=ctx.timeout,
        )
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT after {ctx.timeout}s"
    except FileNotFoundError as e:
        return 127, f"command not found: {e}"
    out = (proc.stdout or "") + (proc.stderr or "")
    # 保留尾部, 避免 evidence.json 过大
    tail = "\n".join(out.splitlines()[-40:])
    return proc.returncode, tail


def _pytest_status(exit_code: int, output: str) -> str:
    """把 pytest exit code 映射到门状态。

    pytest: 0=all pass, 1=tests failed, 2=usage/interrupt, 5=no tests collected.
    全部 skip (无 fail) 也返回 exit 0 → pass (PG skip 场景由 detail 标注)。
    """
    if exit_code == 0:
        return PASS
    if exit_code == 5:
        # 没有收集到任何测试 → 视为证据缺失
        return ERROR
    if exit_code == 1:
        return FAIL
    return ERROR


# ─── 各门 runner ─────────────────────────────────────────────────────────────

def _runner_script(script_rel: str, args: list[str]):
    def run(ctx: GateContext) -> GateResult:
        cmd = [sys.executable, script_rel, *args]
        code, out = _run(cmd, ctx)
        status = PASS if code == 0 else (FAIL if code == 1 else ERROR)
        return GateResult(
            id="", title="", requirements=[], kind="script", required=True,
            status=status, evidence=[script_rel], command=" ".join(cmd), detail=out,
        )
    return run


def _runner_pytest(files: list[str], extra: Optional[list[str]] = None):
    def run(ctx: GateContext) -> GateResult:
        cmd = [sys.executable, "-m", "pytest", *files, "-q", "--no-header", "-p", "no:cacheprovider"]
        if extra:
            cmd += extra
        code, out = _run(cmd, ctx)
        status = _pytest_status(code, out)
        # 提取 pytest 结果摘要行
        summary = ""
        for line in reversed(out.splitlines()):
            if any(k in line for k in ("passed", "failed", "error", "skipped", "no tests")):
                summary = line.strip()
                break
        return GateResult(
            id="", title="", requirements=[], kind="pytest", required=True,
            status=status, evidence=list(files), command=" ".join(cmd),
            detail=summary or out,
        )
    return run


def _is_num(x) -> bool:
    """数值判定 (排除 bool, 因 isinstance(True, int) 为真)。"""
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def evaluate_capacity_report(report: dict, target_vu: int) -> tuple[bool, str]:
    """纯函数: 校验一份 live 容量报告 (CapacityReport.to_dict()) 是否满足 6000VU 发布门。

    要求 **全部** 满足 (design §9.1 / §14):
      * ``passed == True``
      * ``peak_virtual_users >= target_virtual_users``
        (target 取报告自带值与 scenario 的较大者, 且至少 = scenario 目标; 防伪造低目标)
      * ``error_rate_pct < max_error_rate_pct`` (取报告自带阈值, 缺失/非法回退 1.0)
      * ``cross_project_leakage == 0`` 且 ``duplicate_side_effects == 0``
        且 ``lost_persisted_jobs == 0``

    任一字段缺失/类型非法 → 判失败并给出精确原因 (present-but-invalid 是真实失败信号,
    绝不静默降级)。返回 (ok, reason)。
    """
    reasons: list[str] = []

    # passed 必须严格为 True
    passed = report.get("passed")
    if passed is not True:
        reasons.append(f"passed={passed!r} (要求 true)")

    # peak vs target: 有效目标 = max(scenario 目标, 报告目标), 防止报告伪造低目标蒙混过关
    effective_target = target_vu
    report_target = report.get("target_virtual_users")
    if _is_num(report_target):
        effective_target = max(target_vu, int(report_target))
    else:
        reasons.append(f"target_virtual_users 缺失或非数值={report_target!r}")
    peak = report.get("peak_virtual_users")
    if not _is_num(peak):
        reasons.append(f"peak_virtual_users 缺失或非数值={peak!r}")
    elif peak < effective_target:
        reasons.append(f"peak_virtual_users={peak} < target={effective_target}")

    # error rate: 防御性读取报告自带阈值, 缺失回退 1.0
    max_err = report.get("max_error_rate_pct")
    if not _is_num(max_err):
        max_err = 1.0
    err = report.get("error_rate_pct")
    if not _is_num(err):
        reasons.append(f"error_rate_pct 缺失或非数值={err!r}")
    elif err >= max_err:
        reasons.append(f"error_rate_pct={err} >= max_error_rate_pct={max_err}")

    # 干净计数器: 泄露/重复副作用/持久 job 丢失必须为 0
    for field_name in ("cross_project_leakage", "duplicate_side_effects", "lost_persisted_jobs"):
        val = report.get(field_name)
        if not _is_num(val):
            reasons.append(f"{field_name} 缺失或非数值={val!r}")
        elif val != 0:
            reasons.append(f"{field_name}={val} (要求 0)")

    return (not reasons, "; ".join(reasons))


def _runner_capacity(ctx: GateContext) -> GateResult:
    """6000VU 容量门: 校验 scenario.json 计划契约 (plan-level) + 若存在 live 报告则解析验收。

    诚实/防伪造原则:
      * 无 live 报告 → EVIDENCE_PENDING (计划/契约绿但无 6000VU live run, 发布仍阻断)。
      * 有 live 报告 → **必须解析并逐项校验**; 达标才 PASS, 未达标/不可解析/缺字段 → FAIL
        (present-but-invalid 报告是真实失败信号, 绝不因"文件存在"就伪绿, 也不降级为 pending)。
    """
    # 1) 计划契约: 运行 capacity tooling 契约测试
    cmd = [sys.executable, "-m", "pytest", CAPACITY_TOOLING_FILE, "-q", "--no-header",
           "-p", "no:cacheprovider"]
    code, out = _run(cmd, ctx)
    contract_status = _pytest_status(code, out)

    # 2) scenario.json 存在且声明 6000 VU
    scenario_path = ctx.backend_dir / CAPACITY_SCENARIO
    scenario_ok = False
    scenario_detail = "scenario.json 缺失"
    scenario_target = 6000  # 目标 VU (从 scenario.json / SCENARIO.target_virtual_users)
    if scenario_path.exists():
        try:
            data = json.loads(scenario_path.read_text(encoding="utf-8"))
            tv = data.get("target_virtual_users")
            err = data.get("acceptance", {}).get("max_error_rate_pct")
            leak = data.get("acceptance", {}).get("max_cross_project_leakage")
            scenario_ok = tv == 6000 and err == 1.0 and leak == 0
            if _is_num(tv):
                scenario_target = int(tv)
            scenario_detail = (
                f"target_virtual_users={tv}, max_error_rate_pct={err}, "
                f"max_cross_project_leakage={leak}"
            )
        except Exception as e:  # pragma: no cover
            scenario_detail = f"scenario.json 解析失败: {e}"

    # 3) 是否存在 live 6000VU run 报告
    live_reports = list((ctx.backend_dir / "tests" / "load").rglob("*capacity_report*.json"))
    live_reports += list((ctx.backend_dir / "tests" / "load").rglob("*run_*result*.json"))

    plan_green = contract_status == PASS and scenario_ok
    if not plan_green:
        status = FAIL
        detail = f"计划契约未通过: contract={contract_status}; {scenario_detail}"
    elif live_reports:
        # 存在 live 报告 → 解析最新的一份 (按 mtime) 并逐项校验, 不因文件存在就伪绿
        newest = max(live_reports, key=lambda p: p.stat().st_mtime)
        try:
            report = json.loads(newest.read_text(encoding="utf-8"))
            if not isinstance(report, dict):
                raise ValueError(f"报告根不是对象 (得到 {type(report).__name__})")
        except Exception as e:
            status = FAIL
            detail = (
                f"发现 live 容量报告但无法解析 ({newest}): {e} — "
                "present-but-invalid 报告视为真实失败信号, 不降级为 evidence_pending。"
            )
        else:
            ok, reason = evaluate_capacity_report(report, scenario_target)
            if ok:
                status = PASS
                detail = (
                    f"计划契约通过 + live 6000VU run 报告校验通过 ({newest}): "
                    f"passed=true, peak_virtual_users={report.get('peak_virtual_users')}"
                    f">=target={scenario_target}, error_rate_pct={report.get('error_rate_pct')}"
                    f"<{report.get('max_error_rate_pct')}, "
                    "cross_project_leakage/duplicate_side_effects/lost_persisted_jobs 均=0。"
                )
            else:
                status = FAIL
                detail = (
                    f"发现 live 容量报告但未达标 ({newest}): {reason} — "
                    "present-but-failing/invalid 报告视为真实失败信号, 不降级为 evidence_pending。"
                )
    else:
        # 计划/契约级通过, 但无 live 6000VU run → 如实标注为待专用容量环境取证
        status = EVIDENCE_PENDING
        detail = (
            f"计划契约通过 ({scenario_detail}); 但未发现 live 6000VU run 报告。"
            "6000VU 需专用容量/chaos 环境执行 (locustfile_evidence_capacity + run_capacity.py), "
            "此处仅取到 plan/contract 级证据, 未 live-verified — 不伪造 live run。"
        )
    return GateResult(
        id="", title="", requirements=[], kind="contract", required=True,
        status=status, evidence=[CAPACITY_SCENARIO, CAPACITY_TOOLING_FILE],
        command=" ".join(cmd), detail=detail,
    )


def _runner_uat(ctx: GateContext) -> GateResult:
    """UAT-01~15 门: 读取最新 Playwright 机器可读结果; 无则如实记录 per-scenario 状态。"""
    # 查找机器可读结果
    for rel in UAT_RESULT_CANDIDATES:
        p = ctx.root / rel
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                # Playwright json reporter: stats.unexpected==0 且 stats.expected>0 视为 pass
                stats = data.get("stats", {})
                unexpected = stats.get("unexpected", 1)
                expected = stats.get("expected", 0)
                status = PASS if (unexpected == 0 and expected > 0) else FAIL
                return GateResult(
                    id="", title="", requirements=[], kind="evidence", required=True,
                    status=status, evidence=[rel],
                    detail=f"Playwright 结果: {stats}",
                )
            except Exception as e:  # pragma: no cover
                return GateResult(
                    id="", title="", requirements=[], kind="evidence", required=True,
                    status=ERROR, evidence=[rel], detail=f"结果解析失败: {e}",
                )
    # 无机器可读结果: 如实记录 per-scenario 归属 (§10.2), 不伪造 PASS
    # UAT-15 = capacity/chaos-owned (与 6000VU 门关联); UAT-01~14 = Playwright-owned (用户可见流程)
    scenarios = {f"UAT-{i:02d}": "playwright-owned" for i in range(1, 15)}
    scenarios["UAT-15"] = "capacity/chaos-owned (§10.2; 关联 6000VU 门)"
    detail = (
        "未发现机器可读 Playwright UAT 结果 (需 live 3030+9980 服务器 + 多角色账号, "
        "无头环境不可复现)。按 §10.2 如实记录 per-scenario 归属, 不伪造 PASS: "
        + json.dumps(scenarios, ensure_ascii=False)
        + "。UAT-02/03/08/13 为一票否决; UAT-15 承接 R15/P29。"
        "Wave 9 任务在 tasks.md 标记完成, 但发布门要求 live UAT 机器证据, 此处未捕获 → evidence_pending。"
    )
    return GateResult(
        id="", title="", requirements=[], kind="evidence", required=True,
        status=EVIDENCE_PENDING, evidence=UAT_RESULT_CANDIDATES, detail=detail,
    )


# ─── 发布门定义 ──────────────────────────────────────────────────────────────

def build_gates() -> list[GateSpec]:
    return [
        GateSpec(
            id="traceability",
            title="三件套追溯与完成守卫 (R1–R16, P1–P30, UAT-01~15, 55 叶子/11 wave)",
            requirements=[f"R{i}" for i in range(1, 17)],
            kind="script",
            runner=_runner_script(TRACEABILITY_SCRIPT, ["--strict"]),
        ),
        GateSpec(
            id="pbt_p1_p29",
            title="六个 Wave-8 属性组 PBT (P1–P29 逐项)",
            requirements=[f"R{i}" for i in range(1, 16)],
            kind="pytest",
            runner=_runner_pytest(WAVE8_PROPERTY_FILES, extra=["-m", "not release_gate_p30"]),
        ),
        GateSpec(
            id="p30_snapshot",
            title="P30 固定不可变快照独立门 (release_gate_p30)",
            requirements=["R16"],
            kind="pytest",
            runner=_runner_pytest([P30_SNAPSHOT_FILE], extra=["-m", "release_gate_p30"]),
        ),
        GateSpec(
            id="uat_01_15",
            title="Wave 9 Playwright UAT-01~15",
            requirements=["R1", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10", "R11", "R13", "R14", "R15"],
            kind="evidence",
            runner=_runner_uat,
        ),
        GateSpec(
            id="pg16_contracts",
            title="真实 PG16 约束/并发/trigger 契约 (governance PG + 统一图闭包)",
            requirements=["R2", "R5", "R7", "R9", "R11", "R12", "R14"],
            kind="pytest",
            runner=_runner_pytest(PG16_CONTRACT_FILES),
        ),
        GateSpec(
            id="adapter_contracts",
            title="八引擎 adapter 契约 (未复制引擎)",
            requirements=["R5", "R7", "R8", "R9", "R11"],
            kind="pytest",
            runner=_runner_pytest([ADAPTER_CONTRACT_FILE]),
        ),
        GateSpec(
            id="ai_coverage",
            title="AI 入口覆盖 gap = 0 (P18 scanner)",
            requirements=["R8"],
            kind="script",
            runner=_runner_script(AI_COVERAGE_SCRIPT, ["--strict"]),
        ),
        GateSpec(
            id="offline_manifest",
            title="归档离线 manifest 成员/hash/签名验签",
            requirements=["R11"],
            kind="pytest",
            runner=_runner_pytest([OFFLINE_VERIFIER_FILE]),
        ),
        GateSpec(
            id="capacity_6000vu",
            title="6000 VU 容量计划契约 (scenario.json)",
            requirements=["R12", "R15"],
            kind="contract",
            runner=_runner_capacity,
        ),
        GateSpec(
            id="health_rollback",
            title="migration health gate + 回滚演练 (Task 11.2)",
            requirements=["R11", "R12", "R13", "R14", "R15"],
            kind="pytest",
            runner=_runner_pytest([HEALTH_ROLLBACK_FILE]),
        ),
    ]


# ─── 纯聚合/裁决逻辑 (供自测) ─────────────────────────────────────────────────

RELEASE_READY = "release-ready"
BLOCKED = "BLOCKED"

RELEASE_READY_MESSAGE = (
    "release-ready — 全部必需发布门为绿; 可更新实施状态 (Task 11.4 → [x]) 并发起归档评审。"
)


def compute_overall_verdict(results: list[GateResult]) -> dict:
    """纯函数: 由各门结果计算总体裁决。

    只有全部 **必需门** status==pass 时 → release-ready; 否则 BLOCKED 且列出精确失败门。
    非 pass 一律阻断 (fail/error/evidence_pending/skipped)。
    """
    required = [r for r in results if r.required]
    blocking = [r for r in required if r.status not in _GREEN]
    if not blocking:
        verdict = RELEASE_READY
        message = RELEASE_READY_MESSAGE
    else:
        verdict = BLOCKED
        parts = [f"{r.id}[{r.status}]" for r in blocking]
        message = (
            "BLOCKED — 以下必需发布门未通过, 不得声称 release-ready, "
            "保持 Task 11.4 待执行并阻断发布: " + ", ".join(parts)
        )
    return {
        "verdict": verdict,
        "message": message,
        "blocking_gates": [
            {"id": r.id, "status": r.status, "title": r.title} for r in blocking
        ],
        "total_gates": len(results),
        "required_gates": len(required),
        "green_gates": len([r for r in required if r.status in _GREEN]),
    }


# 发布门策略覆盖的需求范围 (design §14): R1–R16 全部纳入 rollup。
ALL_REQUIREMENTS = [f"R{i}" for i in range(1, 17)]


def compute_requirements_rollup(results: list[GateResult]) -> dict:
    """纯函数: 由各门结果反推每条需求 R1–R16 的验收状态 (机器可读 R1–R15 acceptance)。

    对每条需求 Rn: 汇总所有声明覆盖 Rn 的门:
      * green   —— 存在覆盖门且全部 pass;
      * blocked —— 至少一个覆盖门非 pass;
      * unmapped —— 无任何门覆盖 (视为 blocked, 不得默认放行)。
    green_gates / blocking_gates 精确列出证据指针。
    """
    rollup: dict[str, dict] = {}
    for req in ALL_REQUIREMENTS:
        covering = [r for r in results if req in (r.requirements or [])]
        green = [r.id for r in covering if r.status in _GREEN]
        blocking = [r.id for r in covering if r.status not in _GREEN]
        if not covering:
            status = "unmapped"
        elif blocking:
            status = "blocked"
        else:
            status = "green"
        rollup[req] = {
            "status": status,
            "green_gates": green,
            "blocking_gates": blocking,
        }
    return rollup


def compute_gate_summary(results: list[GateResult]) -> dict:
    """纯函数: 门级状态计数 (机器可读摘要)。"""
    counts = {PASS: 0, FAIL: 0, ERROR: 0, EVIDENCE_PENDING: 0, SKIPPED: 0}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    return {
        "total": len(results),
        "required": len([r for r in results if r.required]),
        "pass": counts[PASS],
        "fail": counts[FAIL],
        "error": counts[ERROR],
        "evidence_pending": counts[EVIDENCE_PENDING],
        "skipped": counts[SKIPPED],
    }


# ─── 主流程 ──────────────────────────────────────────────────────────────────

def run_gates(gates: list[GateSpec], ctx: GateContext) -> list[GateResult]:
    results: list[GateResult] = []
    for spec in gates:
        if ctx.collect_only:
            results.append(GateResult(
                id=spec.id, title=spec.title, requirements=spec.requirements,
                kind=spec.kind, required=spec.required, status=SKIPPED,
                detail="collect-only: 未执行",
                timestamp=datetime.now(timezone.utc).isoformat(),
            ))
            continue
        print(f"[release-gate] 运行门: {spec.id} — {spec.title} ...", flush=True)
        t0 = time.time()
        res = spec.runner(ctx)
        res.id = spec.id
        res.title = spec.title
        res.requirements = spec.requirements
        res.kind = spec.kind
        res.required = spec.required
        res.duration_s = round(time.time() - t0, 2)
        res.timestamp = datetime.now(timezone.utc).isoformat()
        print(f"[release-gate]   → {res.status} ({res.duration_s}s) {res.detail[:120]}", flush=True)
        results.append(res)
    return results


def build_evidence_document(results: list[GateResult], collect_only: bool) -> dict:
    verdict = compute_overall_verdict(results)
    return {
        "feature": FEATURE,
        "task": "11.4",
        "artifact": "release_evidence",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "collect_only": collect_only,
        "test_profile": {
            # 全局 fast profile 由 backend/tests/conftest.py 注册; example 数由此 env 覆盖。
            # 记录本次聚合运行时子进程继承的 example 上限, 供 release evidence 复算/审计。
            "hypothesis_profile": "fast",
            "hypothesis_max_examples_env": os.environ.get("HYPOTHESIS_MAX_EXAMPLES"),
        },
        "release_gate_policy": (
            "design §14: R1–R15 验收 + P1–P29 全绿 + UAT-01~15 全绿 + 真实 PG 约束/并发/trigger "
            "+ AI coverage gap=0 + 跨项目泄露=0 + offline manifest 验签 + 6000VU 错误率<1% + "
            "health/rollback 全绿; 全绿方可 release-ready 并发起归档评审, 否则 BLOCKED 且阻断发布。"
        ),
        "overall": verdict,
        "gate_summary": compute_gate_summary(results),
        "requirements_rollup": compute_requirements_rollup(results),
        "gates": [
            {
                "id": r.id,
                "title": r.title,
                "requirements": r.requirements,
                "kind": r.kind,
                "required": r.required,
                "status": r.status,
                "evidence": r.evidence,
                "command": r.command,
                "detail": r.detail,
                "duration_s": r.duration_s,
                "timestamp": r.timestamp,
            }
            for r in results
        ],
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Evidence governance 最终发布门聚合器 (Task 11.4)")
    parser.add_argument("--collect-only", action="store_true", help="只列出执行计划, 不运行子进程")
    parser.add_argument("--output", default=str(DEFAULT_EVIDENCE_PATH), help="release_evidence.json 输出路径")
    parser.add_argument("--gate", action="append", default=None, help="只运行指定门 (可重复)")
    parser.add_argument("--timeout", type=int, default=1800, help="单门子进程超时秒数")
    parser.add_argument("--strict", action="store_true", help="非 pass 时 exit 1")
    args = parser.parse_args(argv)

    gates = build_gates()
    if args.gate:
        wanted = set(args.gate)
        gates = [g for g in gates if g.id in wanted]
        if not gates:
            print(f"[release-gate] 无匹配门: {args.gate}", file=sys.stderr)
            return 2

    ctx = GateContext(
        backend_dir=BACKEND_DIR, root=ROOT, timeout=args.timeout,
        collect_only=args.collect_only,
    )

    results = run_gates(gates, ctx)
    doc = build_evidence_document(results, args.collect_only)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    # ─── 控制台报告 ───
    print("\n" + "=" * 78)
    print(f"最终发布门聚合结果 — {FEATURE} (Task 11.4)")
    print("=" * 78)
    for r in results:
        mark = {"pass": "✅", "fail": "❌", "error": "⚠️ ", "evidence_pending": "🟡", "skipped": "⏭️ "}.get(r.status, "??")
        print(f"  {mark} {r.id:<18} {r.status:<16} {r.title}")
    print("-" * 78)
    ov = doc["overall"]
    print(f"总体裁决: {ov['verdict']}  ({ov['green_gates']}/{ov['required_gates']} 必需门绿)")
    print(ov["message"])
    print(f"release_evidence.json → {out_path}")
    print("=" * 78)

    if args.strict and ov["verdict"] != RELEASE_READY:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
