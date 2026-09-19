"""Feature: attachment-ocr-ai-evidence-governance-hardening — Task 11.4

最终发布门聚合器 (`check_evidence_governance_release_gate.py`) 的轻量守卫测试。

验证聚合/裁决纯逻辑:
  * 任一必需门为红 (fail/error/evidence_pending/skipped) → 总体 BLOCKED, 且列出精确失败门。
  * 全部必需门为绿 (pass) → release-ready。
  * 非必需门为红不影响 release-ready。
  * gate 定义覆盖 design §14 要求的全部发布门 (traceability/P1-P29/P30/UAT/PG16/
    adapter/AI coverage/offline manifest/6000VU/health-rollback)。
  * --collect-only 不执行子进程即可产出完整 evidence 文档骨架。

这是纯逻辑单测, 不运行任何被聚合的重型子进程 (那些由聚合器 live 运行时取证)。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# ─── 动态加载被测脚本 (scripts/check 非 package) ──────────────────────────────

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts" / "check" / "check_evidence_governance_release_gate.py"
)


def _load_module():
    import sys as _sys

    spec = importlib.util.spec_from_file_location("rg_aggregator_task_11_4", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # 注册到 sys.modules, 否则 dataclass 前向引用解析 (cls.__module__ 查找) 会失败
    _sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


rg = _load_module()


def _result(gate_id: str, status: str, required: bool = True, requirements=None):
    return rg.GateResult(
        id=gate_id, title=f"gate {gate_id}",
        requirements=list(requirements) if requirements is not None else ["R1"],
        kind="pytest", required=required, status=status,
    )


def _results_from_gates(gates, status=None):
    """由真实门定义构造结果, 保留每个门声明的 requirements。"""
    out = []
    for g in gates:
        out.append(rg.GateResult(
            id=g.id, title=g.title, requirements=list(g.requirements),
            kind=g.kind, required=g.required, status=status or rg.PASS,
        ))
    return out


# ─── 门定义完整性 ─────────────────────────────────────────────────────────────

def test_all_release_gates_present():
    """gate 定义覆盖 design §14 全部发布门。"""
    ids = {g.id for g in rg.build_gates()}
    expected = {
        "traceability",
        "pbt_p1_p29",
        "p30_snapshot",
        "uat_01_15",
        "pg16_contracts",
        "adapter_contracts",
        "ai_coverage",
        "offline_manifest",
        "capacity_6000vu",
        "health_rollback",
    }
    assert ids == expected, f"发布门集合不匹配: 缺={expected - ids}, 多={ids - expected}"


def test_all_gates_required_by_default():
    """本任务所有发布门均为必需 (无 optional)。"""
    assert all(g.required for g in rg.build_gates())


# ─── 裁决逻辑: release-ready ──────────────────────────────────────────────────

def test_all_green_is_release_ready():
    results = [_result(g.id, rg.PASS) for g in rg.build_gates()]
    ov = rg.compute_overall_verdict(results)
    assert ov["verdict"] == rg.RELEASE_READY
    assert ov["blocking_gates"] == []
    assert ov["green_gates"] == ov["required_gates"]
    assert "release-ready" in ov["message"]


# ─── 裁决逻辑: 任一红 → BLOCKED ──────────────────────────────────────────────

@pytest.mark.parametrize("bad_status", [rg.FAIL, rg.ERROR, rg.EVIDENCE_PENDING, rg.SKIPPED])
def test_any_red_gate_blocks(bad_status):
    """任一必需门非 pass (含 evidence_pending) → BLOCKED, 且不得 release-ready。"""
    gates = rg.build_gates()
    results = [_result(g.id, rg.PASS) for g in gates]
    # 把 uat 门置红
    for r in results:
        if r.id == "uat_01_15":
            r.status = bad_status
    ov = rg.compute_overall_verdict(results)
    assert ov["verdict"] == rg.BLOCKED
    assert ov["verdict"] != rg.RELEASE_READY
    assert "uat_01_15" in [b["id"] for b in ov["blocking_gates"]]
    assert bad_status in ov["message"]


def test_multiple_red_gates_all_listed():
    gates = rg.build_gates()
    results = [_result(g.id, rg.PASS) for g in gates]
    red_ids = {"uat_01_15", "capacity_6000vu", "ai_coverage"}
    for r in results:
        if r.id in red_ids:
            r.status = rg.FAIL
    ov = rg.compute_overall_verdict(results)
    assert ov["verdict"] == rg.BLOCKED
    assert set(b["id"] for b in ov["blocking_gates"]) == red_ids


def test_evidence_pending_is_not_green():
    """诚实原则: evidence_pending (如未 live-verified 的 6000VU) 不算绿, 必须阻断。"""
    results = [_result("capacity_6000vu", rg.EVIDENCE_PENDING)]
    ov = rg.compute_overall_verdict(results)
    assert ov["verdict"] == rg.BLOCKED


def test_non_required_red_does_not_block():
    """非必需门为红不影响 release-ready (防御性: 当前无 optional 门, 逻辑仍需正确)。"""
    results = [
        _result("traceability", rg.PASS),
        _result("optional_probe", rg.FAIL, required=False),
    ]
    ov = rg.compute_overall_verdict(results)
    assert ov["verdict"] == rg.RELEASE_READY


# ─── R1–R16 需求 rollup (机器可读 acceptance) ────────────────────────────────

def test_requirements_rollup_all_green_when_all_gates_pass():
    """全部门 pass → 每条被覆盖需求 = green, 无 blocking。"""
    results = _results_from_gates(rg.build_gates(), rg.PASS)
    rollup = rg.compute_requirements_rollup(results)
    # design §14 覆盖 R1–R16
    assert set(rollup) == {f"R{i}" for i in range(1, 17)}
    for req, info in rollup.items():
        # 每条需求都被至少一个门覆盖 (无 unmapped)
        assert info["status"] == "green", f"{req} 应为 green, 实际 {info}"
        assert info["blocking_gates"] == []
        assert info["green_gates"]


def test_requirements_rollup_blocks_requirement_of_red_gate():
    """某门变红 → 其覆盖的需求全部标 blocked, 精确列出失败门。"""
    gates = rg.build_gates()
    results = _results_from_gates(gates, rg.PASS)
    # 令 pg16_contracts 变红 (覆盖 R2/R5/R7/R9/R11/R12/R14)
    pg16 = next(g for g in gates if g.id == "pg16_contracts")
    for r in results:
        if r.id == "pg16_contracts":
            r.status = rg.FAIL
    rollup = rg.compute_requirements_rollup(results)
    for req in pg16.requirements:
        assert rollup[req]["status"] == "blocked", f"{req} 应因 pg16 红而 blocked"
        assert "pg16_contracts" in rollup[req]["blocking_gates"]


def test_requirements_rollup_missing_evidence_blocks():
    """模拟证据缺失: 门为 evidence_pending → 覆盖需求 blocked (诚实原则)。"""
    gates = rg.build_gates()
    # 只保留覆盖 capacity 需求但不含 traceability 的最小集, 以隔离 evidence_pending 影响
    cap = next(g for g in gates if g.id == "capacity_6000vu")
    results = [
        rg.GateResult(id=cap.id, title=cap.title, requirements=list(cap.requirements),
                      kind=cap.kind, required=True, status=rg.EVIDENCE_PENDING),
    ]
    rollup = rg.compute_requirements_rollup(results)
    for req in cap.requirements:
        assert rollup[req]["status"] == "blocked"


def test_requirement_unmapped_is_blocked():
    """无任何门覆盖的需求 → unmapped (非绿), 不得默认放行。"""
    # 只有一个门, 仅覆盖 R1
    results = [_result("traceability", rg.PASS)]
    results[0].requirements = ["R1"]
    rollup = rg.compute_requirements_rollup(results)
    assert rollup["R1"]["status"] == "green"
    assert rollup["R2"]["status"] == "unmapped"


def test_gate_summary_counts():
    gates = rg.build_gates()
    results = [_result(g.id, rg.PASS) for g in gates]
    results[0].status = rg.FAIL
    results[1].status = rg.EVIDENCE_PENDING
    summary = rg.compute_gate_summary(results)
    assert summary["total"] == len(gates)
    assert summary["fail"] == 1
    assert summary["evidence_pending"] == 1
    assert summary["pass"] == len(gates) - 2


# ─── collect-only 文档骨架 ────────────────────────────────────────────────────

# ─── capacity_6000vu 门: live 报告解析验收 (Task 11.4 硬化) ────────────────────
#
# 证明发布门不再被"文件存在"蒙混:
#   (a) 无 live 报告 → evidence_pending (计划/契约绿但无 6000VU live run)
#   (b) 有报告且 passed=true & peak>=6000 & 计数器全 0 → pass
#   (c) 有报告但 peak<6000 (或 passed=false / 泄露>0 / 不可解析) → FAIL (非 pass, 非 pending)
#
# 用 tmp 目录 + monkeypatch 让 runner 只看到我们控制的报告文件, 不向仓库树落任何真实报告。

import json as _json


def _clean_report(**overrides) -> dict:
    """一份"达标"的容量报告基线 (对齐 CapacityReport.to_dict() 字段名)。"""
    base = {
        "passed": True,
        "peak_virtual_users": 7200,
        "target_virtual_users": 6000,
        "error_rate_pct": 0.12,
        "max_error_rate_pct": 1.0,
        "cross_project_leakage": 0,
        "duplicate_side_effects": 0,
        "lost_persisted_jobs": 0,
    }
    base.update(overrides)
    return base


def _make_capacity_ctx(tmp_path: Path, monkeypatch) -> "rg.GateContext":
    """构造一个 backend_dir 指向 tmp 的 ctx, 并让 contract 子进程/ scenario 校验短路为绿。

    - 在 tmp 下铺一份合法 scenario.json (6000VU/err=1.0/leak=0);
    - monkeypatch rg._run 让 capacity tooling 契约测试恒返回 pytest pass (exit 0);
    这样我们隔离出"live 报告解析"这一段行为进行断言。
    """
    # scenario.json
    scenario_dir = tmp_path / "tests" / "load" / "evidence_governance_capacity"
    scenario_dir.mkdir(parents=True, exist_ok=True)
    (scenario_dir / "scenario.json").write_text(
        _json.dumps({
            "target_virtual_users": 6000,
            "acceptance": {"max_error_rate_pct": 1.0, "max_cross_project_leakage": 0},
        }),
        encoding="utf-8",
    )
    # 契约子进程恒绿
    monkeypatch.setattr(rg, "_run", lambda cmd, ctx: (0, "1 passed"))
    return rg.GateContext(backend_dir=tmp_path, root=tmp_path, timeout=1, collect_only=False)


def _write_live_report(tmp_path: Path, payload) -> Path:
    d = tmp_path / "tests" / "load" / "evidence_governance_capacity"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "capacity_report.json"
    p.write_text(payload if isinstance(payload, str) else _json.dumps(payload), encoding="utf-8")
    return p


def test_capacity_no_live_report_is_evidence_pending(tmp_path, monkeypatch):
    """(a) 无 live 报告 → evidence_pending (保持今天行为: 计划绿但缺 6000VU live run)。"""
    ctx = _make_capacity_ctx(tmp_path, monkeypatch)
    res = rg._runner_capacity(ctx)
    assert res.status == rg.EVIDENCE_PENDING
    assert "未发现 live" in res.detail


def test_capacity_valid_passing_report_is_pass(tmp_path, monkeypatch):
    """(b) 存在报告 passed=true & peak>=6000 & 计数器全 0 → pass。"""
    ctx = _make_capacity_ctx(tmp_path, monkeypatch)
    _write_live_report(tmp_path, _clean_report())
    res = rg._runner_capacity(ctx)
    assert res.status == rg.PASS, res.detail


@pytest.mark.parametrize("mutation,needle", [
    ({"peak_virtual_users": 4200}, "peak_virtual_users"),          # sub-6000 VU
    ({"passed": False}, "passed"),                                  # 报告自判失败
    ({"cross_project_leakage": 3}, "cross_project_leakage"),        # 跨项目泄露
    ({"duplicate_side_effects": 1}, "duplicate_side_effects"),      # 重复副作用
    ({"lost_persisted_jobs": 2}, "lost_persisted_jobs"),            # 持久 job 丢失
    ({"error_rate_pct": 2.5}, "error_rate_pct"),                    # 错误率超阈值
])
def test_capacity_present_but_failing_report_is_fail(tmp_path, monkeypatch, mutation, needle):
    """(c) 报告存在但任一验收项不达标 → FAIL (绝不 pass, 绝不 evidence_pending)。"""
    ctx = _make_capacity_ctx(tmp_path, monkeypatch)
    _write_live_report(tmp_path, _clean_report(**mutation))
    res = rg._runner_capacity(ctx)
    assert res.status == rg.FAIL, res.detail
    assert res.status != rg.PASS
    assert res.status != rg.EVIDENCE_PENDING
    assert needle in res.detail


def test_capacity_unparseable_report_is_fail(tmp_path, monkeypatch):
    """(c') 报告存在但不可解析 → FAIL (present-but-invalid 是真实失败信号)。"""
    ctx = _make_capacity_ctx(tmp_path, monkeypatch)
    _write_live_report(tmp_path, "{ this is not valid json ")
    res = rg._runner_capacity(ctx)
    assert res.status == rg.FAIL
    assert res.status != rg.EVIDENCE_PENDING
    assert "无法解析" in res.detail


def test_capacity_report_missing_fields_is_fail(tmp_path, monkeypatch):
    """(c'') 报告缺关键字段 → FAIL (不静默通过)。"""
    ctx = _make_capacity_ctx(tmp_path, monkeypatch)
    _write_live_report(tmp_path, {"passed": True})  # 缺 peak/error_rate/计数器
    res = rg._runner_capacity(ctx)
    assert res.status == rg.FAIL


def test_capacity_report_fake_low_target_cannot_bypass(tmp_path, monkeypatch):
    """防伪造: 报告把 target_virtual_users 改到 100 并声称 peak=100 passed 也不能蒙混。"""
    ctx = _make_capacity_ctx(tmp_path, monkeypatch)
    _write_live_report(tmp_path, _clean_report(target_virtual_users=100, peak_virtual_users=100))
    res = rg._runner_capacity(ctx)
    assert res.status == rg.FAIL
    assert "peak_virtual_users" in res.detail


def test_evaluate_capacity_report_pure_helper():
    """纯函数 evaluate_capacity_report 直测: 达标 True, 计数器脏 False。"""
    ok, reason = rg.evaluate_capacity_report(_clean_report(), 6000)
    assert ok and reason == ""
    ok2, reason2 = rg.evaluate_capacity_report(_clean_report(cross_project_leakage=1), 6000)
    assert not ok2 and "cross_project_leakage" in reason2


def test_collect_only_builds_full_document():
    gates = rg.build_gates()
    ctx = rg.GateContext(
        backend_dir=rg.BACKEND_DIR, root=rg.ROOT, timeout=1, collect_only=True,
    )
    results = rg.run_gates(gates, ctx)
    doc = rg.build_evidence_document(results, collect_only=True)
    assert doc["feature"] == rg.FEATURE
    assert doc["task"] == "11.4"
    assert len(doc["gates"]) == len(gates)
    # collect-only 全部 skipped → BLOCKED (未取证不得放行)
    assert doc["overall"]["verdict"] == rg.BLOCKED
    assert all(g["status"] == rg.SKIPPED for g in doc["gates"])
    # 机器可读 R1–R16 rollup + gate_summary 必须存在
    assert set(doc["requirements_rollup"]) == {f"R{i}" for i in range(1, 17)}
    assert doc["gate_summary"]["total"] == len(gates)
    assert doc["gate_summary"]["skipped"] == len(gates)
