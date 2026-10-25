# -*- coding: utf-8 -*-
"""守住 D1 三端点基线脚本「真的测了三段生产函数」，不是空转假绿。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 4

═══ 为什么要这条守卫 ═══

本 spec 反复踩「脚本存在但没真跑」的坑（P 节 `api.flushPendingSaves?.()` 可选链静默空转 /
X5 节「门禁脚本存在 ≠ CI 真跑它」）。基线脚本 `measure_d1_sync_endpoints_baseline.py` 需真库
才能跑，CI 上跑不动它的 `run()`；但它**是否真调了三端点的核心生产函数**可以用 AST 纯静态
验证（不连库）。缺了这层，脚本退化成「三段都 return 常数」也照样打印一份好看的基线。

判据（纯 AST，不连库）：
  1. 三个 `_measure_*` 函数各自真调了对应的生产入口；
  2. `run()` 真的把三段结果收集进了各自的样本列表；
  3. 变异反证：把任一 `_measure_*` 的生产调用抽掉 ⇒ 本守卫必红。
"""
from __future__ import annotations

import ast
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_SCRIPT = (
    _REPO
    / "backend"
    / "scripts"
    / "analyze"
    / "measure_d1_sync_endpoints_baseline.py"
)

#: 每个 `_measure_*` 段必须真调的生产函数名（属性调用取尾段 attr，普通调用取 func id）。
_REQUIRED_CALLS = {
    "_measure_store_projection": {
        "build_combined_store_projection",
        "_overlay_with_published_substrate",
    },
    "_measure_pending_mutation": {
        "build_combined_store_projection",
    },
    "_measure_materialize": {
        "build_combined_store_projection",
        "_overlay_with_published_substrate",
        "materialize",
        "extract",
        "verify_unmanaged_regions",
    },
}


def _module() -> ast.Module:
    return ast.parse(_SCRIPT.read_text(encoding="utf-8"))


def _called_names(fn: ast.AST) -> set[str]:
    """函数体内所有被调用的名字（普通调用取 func.id，属性调用取 .attr 尾段）。"""
    names: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def _find_func(mod: ast.Module, name: str) -> ast.AST | None:
    for node in ast.walk(mod):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def test_script_exists_and_parses() -> None:
    assert _SCRIPT.is_file(), f"基线脚本缺失: {_SCRIPT}"
    _module()  # 解析不报错即可


def test_each_measure_segment_calls_its_production_entry() -> None:
    """三段各自真调了对应生产入口 —— 这是「不空转」的核心断言。"""
    mod = _module()
    for seg_name, required in _REQUIRED_CALLS.items():
        fn = _find_func(mod, seg_name)
        assert fn is not None, f"脚本缺少 {seg_name}"
        called = _called_names(fn)
        missing = required - called
        assert not missing, (
            f"{seg_name} 没有调用生产函数 {sorted(missing)} —— "
            f"段退化成空转会给出假的基线数。实际调用: {sorted(called)}"
        )


def test_run_collects_all_three_endpoint_samples() -> None:
    """run() 真的把三段结果 append 进样本列表（否则基线里某端点恒空也不报错）。"""
    mod = _module()
    run = _find_func(mod, "run")
    assert run is not None, "脚本缺少 run()"
    src = ast.get_source_segment(_SCRIPT.read_text(encoding="utf-8"), run) or ""
    for marker in (
        "store_samples.append",
        "pending_samples.append",
        "mat_samples.append",
        "_measure_store_projection",
        "_measure_pending_mutation",
        "_measure_materialize",
    ):
        assert marker in src, f"run() 未收集/调用 {marker!r} —— 该端点样本会恒空"


def test_mutation_removing_a_production_call_is_detected() -> None:
    """变异反证：把 `_measure_materialize` 里的 materialize 调用源码抽掉 ⇒ 必被检出。

    不改真文件 —— 在内存里把源码的那一行调用替换掉，重解析后跑同一判定逻辑。
    """
    text = _SCRIPT.read_text(encoding="utf-8")
    # 把 `registration.adapter.materialize(` 换成一个无害的无关调用
    mutated = text.replace(
        "result = registration.adapter.materialize(",
        "result = _noop_sentinel(",
        1,
    )
    assert mutated != text, "变异锚点未命中 —— 脚本结构变了，先修锚点"
    mod = ast.parse(mutated)
    fn = _find_func(mod, "_measure_materialize")
    assert fn is not None
    called = _called_names(fn)
    # materialize 被抽掉后，_REQUIRED_CALLS 的检查应当发现缺失
    assert "materialize" not in called, (
        "变异后 materialize 仍在调用列表里 —— 变异没生效，这条反证无牙"
    )


# ═══════════════════════════════════════════════════════════════════════════
# P13 不劣化比对（`compare_against_baseline`）—— 纯函数，穷举验证
# ═══════════════════════════════════════════════════════════════════════════


def _load_compare_fn():
    """import 脚本模块取比对纯函数（它不连库，import 安全）。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_measure_d1_endpoints", _SCRIPT
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _report(**mins: float) -> dict:
    """造一份只含 min_s 的 report（比对只读 min_s）。"""
    return {
        "endpoints": {
            k: {"min_s": v, "median_s": v, "max_s": v} for k, v in mins.items()
        }
    }


def test_compare_passes_when_within_110_percent() -> None:
    mod = _load_compare_fn()
    base = _report(materialize=4.0, extract=0.5, verify_unmanaged_regions=0.4,
                   store_projection=0.009, pending_mutations_projection_segment=0.001)
    cur = _report(materialize=4.3, extract=0.52, verify_unmanaged_regions=0.42,
                  store_projection=0.009, pending_mutations_projection_segment=0.001)
    result = mod.compare_against_baseline(base, cur)
    assert result["ok"], result["violations"]
    assert result["per_endpoint"]["materialize"]["verdict"] == "ok"


def test_compare_flags_real_regression_above_110_percent() -> None:
    """变异反证：materialize 真变慢 20% ⇒ 必红。"""
    mod = _load_compare_fn()
    base = _report(materialize=4.0, extract=0.5, verify_unmanaged_regions=0.4,
                   store_projection=0.009, pending_mutations_projection_segment=0.001)
    cur = _report(materialize=4.8, extract=0.5, verify_unmanaged_regions=0.4,
                  store_projection=0.009, pending_mutations_projection_segment=0.001)
    result = mod.compare_against_baseline(base, cur)
    assert not result["ok"], "materialize 1.2× 应判劣化"
    assert result["per_endpoint"]["materialize"]["verdict"] == "regressed"
    assert any("materialize" in v for v in result["violations"])


def test_compare_exempts_sub_noise_floor_segments() -> None:
    """store-projection(0.009s) 即便翻倍也豁免（亚毫秒段 110% 无意义）。"""
    mod = _load_compare_fn()
    base = _report(materialize=4.0, extract=0.5, verify_unmanaged_regions=0.4,
                   store_projection=0.009, pending_mutations_projection_segment=0.001)
    cur = _report(materialize=4.0, extract=0.5, verify_unmanaged_regions=0.4,
                  store_projection=0.020, pending_mutations_projection_segment=0.002)
    result = mod.compare_against_baseline(base, cur)
    assert result["ok"], "亚毫秒段波动不应判劣化"
    assert result["per_endpoint"]["store_projection"]["verdict"] == "noise_floor_exempt"


def test_compare_reports_missing_median_as_violation() -> None:
    """基线缺某端点 ⇒ 不得静默放过（否则漏掉的端点等于没守）。"""
    mod = _load_compare_fn()
    base = _report(materialize=4.0)  # 缺 extract/verify/...
    cur = _report(materialize=4.0, extract=0.5, verify_unmanaged_regions=0.4,
                  store_projection=0.009, pending_mutations_projection_segment=0.001)
    result = mod.compare_against_baseline(base, cur)
    assert not result["ok"], "基线缺端点应判 missing 而非放过"
    assert any("extract" in v for v in result["violations"])
