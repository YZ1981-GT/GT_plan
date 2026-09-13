"""`/d2-sync/*` 退役的永久防复活守卫（G4-2）。

═══ 为什么要永久留着 ═══

被删的 `d2_sync_router` 有两个**平台级**危害，删掉不等于危害消失 —— 只要有人再把
同形态的东西加回来，危害立刻复现：

1. `_load_context()` 把 artifact 固定解析成 `{oo_dir}/D2-2.xlsx`、`_bump_oo_revision()`
   固定推进 room entry `xlsx-sheet/D2-2/D2-2`（总控 gap 15）。manifest 里 179 个 entry
   共用同一个 `GtOnlyOfficeSheet`，任何一个误调都在命令 D2-2 的文件与 room。
2. 它自增 `working_paper_oo_content_revision` 而不是业务 `content_revision`（DEC-09），
   于是「同步成功」可以在业务版本域一动不动的情况下被报出来。

所以本文件不是「删除记录」，是**结构性禁令**：谁再挂一条 `d2-sync` 路由、或让前端
生产代码重新引用它，都会在这里打红。

判据委派给 `check_d2_sync_retirement_eligibility.py`（唯一真源，CI 也跑同一份），
本文件只负责把它接进常规测试套件，并额外守住「门自身可被翻动」。
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_GATE_PATH = _REPO / "backend" / "scripts" / "check" / "check_d2_sync_retirement_eligibility.py"


def _load_gate():
    name = "d2_sync_retirement_gate"
    spec = importlib.util.spec_from_file_location(name, _GATE_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"无法加载退役门：{_GATE_PATH}")
    module = importlib.util.module_from_spec(spec)
    # 🔴 必须先注册进 sys.modules 再 exec：门里有 `@dataclass`，而 dataclasses 解析
    # 注解时会去 `sys.modules[cls.__module__]` 取命名空间；不注册就 AttributeError。
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_gate()


# ═══════════════════════════════════════════════════════════════════
# 1. 结构性禁令：模块/路由/前端引用都不得回来
# ═══════════════════════════════════════════════════════════════════


def test_legacy_router_module_is_not_importable() -> None:
    """`app.routers.d2_sync_router` 必须彻底不可导入。

    用 `find_spec` 而不是 try-import：try-import 会被模块内部的任何 ImportError
    伪装成「已删除」，而那时文件其实还在盘上。
    """
    assert importlib.util.find_spec("app.routers.d2_sync_router") is None, (
        "`d2_sync_router` 又回来了 —— 它把 artifact 固定解析成 D2-2.xlsx、"
        "固定推进 room entry `xlsx-sheet/D2-2/D2-2`，179 个共用 GtOnlyOfficeSheet "
        "的 entry 里任何一个误调都会命令 D2-2（总控 gap 15）"
    )


def test_legacy_frontend_bridge_file_is_gone(gate) -> None:
    assert not gate.LEGACY_FRONTEND_BRIDGE.is_file(), (
        f"{gate.LEGACY_FRONTEND_BRIDGE} 又回来了 —— 前端不得再有第二条同步桥"
    )


def test_phase_is_post_delete(gate) -> None:
    """半删状态必须打红：前端调用面还在而后端已 404 是最难查的形态。"""
    assert gate.detect_phase() == "post_delete"


def test_no_route_declares_a_d2_sync_path(gate) -> None:
    verdict = gate.verdict_no_route_registration("post_delete")
    assert verdict.result == "pass", verdict.detail


def test_no_production_source_uses_the_retired_endpoint(gate) -> None:
    """后端与前端生产代码都不得再把 `d2-sync` 当代码用（注释不算）。"""
    for verdict in (
        gate.verdict_backend_no_caller("post_delete"),
        gate.verdict_frontend_no_caller("post_delete"),
    ):
        assert verdict.result == "pass", verdict.detail


# ═══════════════════════════════════════════════════════════════════
# 2. 别删多了：保留面与替换面都必须还在
# ═══════════════════════════════════════════════════════════════════


def test_reusable_bridge_is_retained_not_collateral_damage(gate) -> None:
    """`d2_bidirectional_bridge` 是统一路径在用的资产，**不得**被顺手删掉。

    这条是反方向的门：它打红表示删过头，而不是没删干净。
    """
    verdict = gate.verdict_bridge_retained()
    assert verdict.result == "pass", verdict.detail


def test_replacement_surface_still_covers_what_legacy_covered(gate) -> None:
    """legacy 守卫覆盖过的三件事必须各有继任者，否则删除等于丢覆盖。"""
    for verdict in (
        gate.verdict_command_service_superset(),  # legacy forcesave 三态
        gate.verdict_defect_a_reverse_lock(),  # 缺陷 A：flush 早于 push
        gate.verdict_four_state_text_guard(),  # 缺陷 B：耐久确认与文案不得报「同步成功」
        gate.verdict_forcesave_fail_closed(),  # G4-0a：无注入端点 fail-closed
        gate.verdict_store_value_rehomed(),  # Half A：store 值等价判据
    ):
        assert verdict.result == "pass", verdict.detail


def test_anti_revival_negative_assertions_are_all_alive(gate) -> None:
    """七处负向断言是删除后唯一的防复活手段，缺一处即失守。"""
    verdict = gate.verdict_negative_assertions()
    assert verdict.result == "pass", verdict.detail


# ═══════════════════════════════════════════════════════════════════
# 3. 守卫的守卫：门自身必须可被翻动
# ═══════════════════════════════════════════════════════════════════


def test_the_gate_itself_is_falsifiable(gate) -> None:
    """每条判据都要能被打红 —— 否则本文件只是一堆恒真重言式（假绿第②源）。"""
    rows = gate.self_check()
    assert rows, "反向自检一条都没有"
    stuck = [row for row in rows if not row["flipped"]]
    assert not stuck, f"以下判据翻不动，门自身有缺陷：{stuck}"


def test_overall_gate_is_green(gate) -> None:
    report = gate.evaluate()
    assert report["phase"] == "post_delete"
    assert report["post_delete_clean"] is True, report["counts"]
    assert report["counts"]["fail"] == 0
    assert report["counts"]["unverifiable"] == 0
