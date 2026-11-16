"""旧式 OO URL 门的 **binding 级状态机**（spec `onlyoffice-sheet-open-via-published-artifact` 2.6）。

═══ 为什么与 `test_legacy_onlyoffice_url_retirement_gate.py` 分开 ═══

那个文件测的是 **readiness 层**（umbrella spec 2.8 第 ① 步），三条臂是「就绪拒 / 未就绪放 /
算不出来放」。本文件测的是 2.6 新加的 **binding 层**，五条臂：

| binding status | 期望 | 理由 |
| --- | --- | --- |
| `migrated` | 拒（409） | 已走 room 协议，再签旧 URL 就是双写 |
| `retired` | 拒（409） | 旧路径已下线 |
| `draining` | 拒（409，文案不同） | 不再为新请求造旧 doc key |
| `pending` | 放 + `sync_mode=independent` | 映射未完成，必须保留独立在线编辑（R6.2） |
| `out_of_scope` | 放 + `sync_mode=independent` | custom / Word / single 不适用本迁移 |

═══ 关键反面臂 ═══

只有 `migrated` 拒是**不够**的：把实现改成「一律 409」也能让它全绿，而那会让所有 pending
入口的在线编辑彻底打不开（R12.8 禁做假切换）。所以 `pending` / `out_of_scope` 两条**必须**
放行且带 `independent` 标记 —— 前端据此显示「独立在线编辑（不同步）」而不是「已同步」。

═══ fail-closed 的方向差异 ═══

binding 层「算不出来」（生成物缺失 / schema 不符）取**中间档**：放行 + 标记
`binding_status=resolution_failed` + `logger.error`。不拒是因为那会让全平台在线编辑一起挂；
不静默放是因为那是本 spec 自己的交付物坏了，必须让监控抓到。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.routers import _wp_onlyoffice_legacy_url_gate as GATE

WP_ID = "wp"
PROJECT_ID = "proj"
ENTRY = "xlsx/gt-k11-asset-impairment-loss"
_ROUTER_PY = Path(__file__).resolve().parents[2] / "app" / "routers" / "wp_onlyoffice_router.py"


def _verdict_for(binding_status: str | None, *, readiness_ready: bool = False) -> dict[str, Any]:
    """在给定 binding 状态下跑门，返回 verdict（拒则从 HTTPException.detail 取）。"""
    binding = None if binding_status is None else {
        "status": binding_status,
        "entry_id": ENTRY,
        "effective_entry_id": ENTRY,
        "source_wp_code": "K11",
        "document_type": "xlsx",
        "document_scope": "single_sheet",
        "target_sheet": "资产减值损失检查表K11",
        "mapping_kind": "exact" if binding_status != "pending" else "provider",
    }

    def fake_binding(**_kwargs: Any):
        if binding_status is None:
            return "no_binding", None
        if binding_status == "__unresolved__":
            return "unresolved", None
        mapping = {
            "migrated": "refuse_migrated",
            "retired": "refuse_migrated",
            "draining": "refuse_draining",
            "pending": "keep_independent",
            "out_of_scope": "keep_independent",
            "ready": "keep_independent",
        }
        return mapping[binding_status], binding

    async def fake_readiness(_db, *, wp_id, project_id, entry_id):
        return {
            "allowed": not readiness_ready,
            "sync_mode": "independent" if not readiness_ready else "bound",
            "error_code": None if not readiness_ready else GATE.LEGACY_ONLYOFFICE_URL_RETIRED,
            "message": None if not readiness_ready else GATE.RETIRED_MESSAGE,
            "entry_id": entry_id,
            "allowed_modes": ["html", "onlyoffice"],
            "binding_status": None,
        }

    async def run() -> dict[str, Any]:
        with patch.object(GATE, "_binding_verdict", fake_binding), patch.object(
            GATE, "_readiness_verdict", fake_readiness
        ):
            try:
                return await GATE.refuse_legacy_url_when_room_ready(
                    AsyncMock(),
                    wp_id=WP_ID,
                    project_id=PROJECT_ID,
                    entry_id=ENTRY,
                    source_wp_code="K11",
                    sheet_name="资产减值损失检查表K11",
                    whole_workbook=False,
                )
            except HTTPException as exc:
                return {"__refused__": True, **exc.detail}

    return asyncio.run(run())


# ═══════════════════════════════════════════════════════════════════════════
# 臂 1：migrated / retired ⇒ 拒（且不查 readiness）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("status", ["migrated", "retired"])
def test_migrated_and_retired_bindings_refuse_legacy_url(status: str) -> None:
    """已迁移 / 已下线的 binding 不得再签旧 URL —— 那正是「双写」的入口。"""
    out = _verdict_for(status, readiness_ready=True)
    assert out.get("__refused__") is True, f"{status} 竟放行旧式签发：{out}"
    assert out["error_code"] == GATE.LEGACY_ONLYOFFICE_URL_RETIRED
    assert "统一在线编辑协议" in out["message"] or "协同编辑" in out["message"]


def test_migrated_refusal_does_not_consult_readiness() -> None:
    """binding 已 migrated 时**不查** readiness —— 查了就会被「未就绪」放行。

    🔴 这条是分层的关键：readiness 回答的是「room 供给好了没」，binding 回答的是
    「这个入口该不该走 room」。migrated 的入口即便供给暂时不就绪，也不得回退旧路径
    （那会让新旧两个 doc key 同时存在）。
    """
    consulted: list[str] = []

    def fake_binding(**_kwargs: Any):
        return "refuse_migrated", {"status": "migrated", "effective_entry_id": ENTRY}

    async def fake_readiness(**_kwargs: Any):
        consulted.append("readiness")
        return {"allowed": True, "sync_mode": "independent", "binding_status": None}

    async def run() -> None:
        with patch.object(GATE, "_binding_verdict", fake_binding), patch.object(
            GATE, "_readiness_verdict", fake_readiness
        ):
            try:
                await GATE.refuse_legacy_url_when_room_ready(
                    AsyncMock(), wp_id=WP_ID, project_id=PROJECT_ID, entry_id=ENTRY
                )
            except HTTPException:
                pass

    asyncio.run(run())
    assert consulted == [], "migrated binding 竟去查了 readiness —— 供给未就绪时会回退旧路径"


# ═══════════════════════════════════════════════════════════════════════════
# 臂 2：draining ⇒ 拒，但文案指向「已签发会话收尾」
# ═══════════════════════════════════════════════════════════════════════════


def test_draining_refuses_new_requests_with_its_own_message() -> None:
    """draining 不再为新请求造旧 doc key，但文案要说「已打开的会话还能存」。

    与 `migrated` 共用一句文案会让已经打开编辑器的用户以为自己的改动没救了。
    """
    out = _verdict_for("draining")
    assert out.get("__refused__") is True
    assert out["error_code"] == GATE.LEGACY_ONLYOFFICE_URL_RETIRED
    assert out["message"] == GATE.DRAINING_MESSAGE
    assert out["message"] != GATE.RETIRED_MESSAGE


# ═══════════════════════════════════════════════════════════════════════════
# 臂 3：pending / out_of_scope / ready ⇒ 放行，且必须标 independent
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("status", ["pending", "out_of_scope", "ready"])
def test_unmigrated_bindings_keep_independent_editing(status: str) -> None:
    """映射未完成 / 不适用 / 已审核未切 ⇒ **必须**放行，否则在线编辑彻底打不开。

    🔴 这条是「门不是对任何输入都拒绝」的唯一证据。删掉它之后，把实现改成「一律 409」
    也能让臂 1 全绿 —— 而那会让所有 pending 入口失去在线编辑（R12.8 明令禁止）。
    """
    out = _verdict_for(status, readiness_ready=True)
    assert not out.get("__refused__"), f"{status} 竟被拒绝：{out}"
    assert out["allowed"] is True
    assert out["sync_mode"] == GATE.SYNC_MODE_INDEPENDENT, (
        f"{status} 的 sync_mode 应为 independent（独立在线编辑、不同步），实得 {out['sync_mode']!r}"
    )


def test_independent_marking_is_not_silently_dropped() -> None:
    """`sync_mode` 必须有值 —— 缺字段时前端只能猜，「猜成已同步」正是要消灭的假状态。"""
    out = _verdict_for("pending")
    assert out["sync_mode"] in {GATE.SYNC_MODE_INDEPENDENT, GATE.SYNC_MODE_BOUND}
    assert out["sync_mode"] == GATE.SYNC_MODE_INDEPENDENT


# ═══════════════════════════════════════════════════════════════════════════
# 臂 4：无 binding ⇒ 落到 readiness 层（与 2.8 第 ① 步同口径）
# ═══════════════════════════════════════════════════════════════════════════


def test_no_binding_falls_through_to_readiness_refusal() -> None:
    """未纳入本 spec 的入口：binding 层无结论时由 readiness 层决定。"""
    out = _verdict_for(None, readiness_ready=True)
    assert out.get("__refused__") is True
    assert out["error_code"] == GATE.LEGACY_ONLYOFFICE_URL_RETIRED


def test_no_binding_and_readiness_not_ready_allows_legacy() -> None:
    out = _verdict_for(None, readiness_ready=False)
    assert not out.get("__refused__")
    assert out["sync_mode"] == GATE.SYNC_MODE_INDEPENDENT


# ═══════════════════════════════════════════════════════════════════════════
# 臂 5：生成物坏掉 ⇒ 中间档（放行 + 标出来）
# ═══════════════════════════════════════════════════════════════════════════


def test_unresolved_binding_allows_but_marks_resolution_failed() -> None:
    """生成物缺失 / schema 不符 ⇒ 放行（否则全平台在线编辑一起挂）但**必须标出来**。

    静默放行会让 migrated 入口继续双写；拒会让所有入口一起失效。中间档是唯一正确选择。
    """
    out = _verdict_for("__unresolved__", readiness_ready=False)
    assert not out.get("__refused__"), "生成物坏掉时拒签会让全平台在线编辑一起挂"
    assert out["binding_status"] == "resolution_failed", (
        f"生成物解析失败必须显式标出，实得 binding_status={out['binding_status']!r}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 常量封闭性
# ═══════════════════════════════════════════════════════════════════════════


def test_sync_mode_values_are_a_closed_set() -> None:
    """`sync_mode` 只有两个值 —— 第三个值会让前端 `switch` 落到 default 而显示错误状态。"""
    assert {GATE.SYNC_MODE_INDEPENDENT, GATE.SYNC_MODE_BOUND} == {"independent", "bound"}


def test_binding_state_sets_cover_the_whole_closed_domain() -> None:
    """binding 状态机的五个状态必须被三层集合**完整**覆盖（不许有落空的状态）。"""
    all_states = {"pending", "ready", "migrated", "draining", "retired"}
    refuse = GATE._BINDING_STATES_REFUSING_LEGACY
    keep = GATE._BINDING_STATES_KEEPING_INDEPENDENT
    assert refuse == {"migrated", "retired"}
    assert keep == {"pending", "out_of_scope"}
    # `draining` 与 `ready` 分别走独立分支（前者拒、后者放），必须在代码里显式出现。
    assert "draining" not in refuse | keep
    assert "ready" not in refuse | keep
    # 五个正式状态一个都不能漏出「既不拒也不放」的空洞。
    assert all_states <= (refuse | keep | {"draining", "ready"})


# ═══════════════════════════════════════════════════════════════════════════
# `_binding_verdict` 自身的容错方向（M8）
#
# 🔴 上面各臂都把 `_binding_verdict` 整个打桩了 —— 那证明不了它**内部**遇到
# 生成物异常时的行为。M8 变异（把它改成 `raise HTTPException(503)`）因此存活：
# 打桩后那段代码根本不执行。所以这一组必须调用**真实的** `_binding_verdict`，
# 只把 `SheetOpenBindingResolver` 打桩成抛异常。
# ═══════════════════════════════════════════════════════════════════════════


def test_binding_resolver_failure_returns_unresolved_not_raise() -> None:
    """生成物缺失 / schema 不符 ⇒ `_binding_verdict` 返回 `unresolved`，**不抛**。

    抛 503 会让全平台在线编辑一起挂（本函数在每个旧式 config 请求上跑）；
    静默返回 `no_binding` 又会让 migrated 入口继续双写。中间档是唯一正确选择。
    """
    from app.services.workpaper_sync import sheet_open_bindings as SOB

    class _Boom:
        def resolve(self, **_kwargs: Any):
            raise FileNotFoundError("workpaper_sync_sheet_open_bindings.json 缺失")

    with patch.object(SOB, "SheetOpenBindingResolver", _Boom):
        verdict, binding = GATE._binding_verdict(
            source_wp_code="K11",
            sheet_name="资产减值损失检查表K11",
            whole_workbook=False,
        )
    assert verdict == "unresolved", f"生成物异常应返回 unresolved，实得 {verdict!r}"
    assert binding is None


def test_binding_resolver_failure_does_not_short_circuit_to_no_binding() -> None:
    """`unresolved` 与 `no_binding` 必须可分辨 —— 前者要报警、后者是正常。

    合成同一个值时，监控看不到「生成物坏了」，而本 spec 自己的交付物坏掉是最该被
    立刻发现的事故。
    """
    from app.services.workpaper_sync import sheet_open_bindings as SOB

    class _Boom:
        def resolve(self, **_kwargs: Any):
            raise ValueError("schema_version 不受支持")

    class _Empty:
        """返回 `no_binding` 形态：状态值不在任何已知集合里 ⇒ `_binding_verdict` 落 no_binding。"""

        def resolve(self, **_kwargs: Any):
            return SimpleNamespace(status="__unknown__", reason=None, binding=None)

    with patch.object(SOB, "SheetOpenBindingResolver", _Boom):
        broken, _ = GATE._binding_verdict(
            source_wp_code="K11", sheet_name="x", whole_workbook=False
        )
    with patch.object(SOB, "SheetOpenBindingResolver", _Empty):
        normal, _ = GATE._binding_verdict(
            source_wp_code="K11", sheet_name="x", whole_workbook=False
        )
    assert broken == "unresolved"
    assert normal == "no_binding"
    assert broken != normal


# ═══════════════════════════════════════════════════════════════════════════
# 端点响应必须带 sync_mode（M9）
# ═══════════════════════════════════════════════════════════════════════════


def test_config_endpoint_response_carries_sync_mode() -> None:
    """旧式 config 响应必须带 `sync_mode` 与 `binding_status`。

    🔴 缺这两个字段时前端只能猜 —— 而「猜成已同步」正是本 spec 要消灭的假状态
    （Requirement 4.2 / 6.2）。AST 判据查的是 dict 字面量里的键，不是字符串里提一句。
    """
    import ast

    tree = ast.parse(_ROUTER_PY.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = {
            k.value for k in node.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        }
        if "config" in keys and "token" in keys:
            found |= keys
    assert "sync_mode" in found, (
        f"旧式 config 响应字典里没有 sync_mode —— 前端无法判断是否同步（现有键：{sorted(found)}）"
    )
    assert "binding_status" in found, (
        f"旧式 config 响应字典里没有 binding_status（现有键：{sorted(found)}）"
    )


def test_sync_mode_in_response_is_not_hardcoded() -> None:
    """`sync_mode` 的值必须来自 verdict，不能写死字面量。

    写死 `"independent"` 时，migrated 入口即便被误放行也会显示「独立编辑」——
    那正好掩盖了双写。
    """
    import ast

    tree = ast.parse(_ROUTER_PY.read_text(encoding="utf-8"))
    values: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value == "sync_mode":
                values.append(ast.unparse(value))
    assert values, "没有找到 sync_mode 的赋值"
    for expr in values:
        assert "legacy_verdict" in expr, (
            f"sync_mode 的值不是从 verdict 取的：{expr!r} —— 写死会掩盖双写"
        )
