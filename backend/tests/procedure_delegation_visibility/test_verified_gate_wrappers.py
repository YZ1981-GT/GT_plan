"""coverage_guard.VERIFIED_GATE_WRAPPERS：经注入对象到达统一门的 router 包装函数。

判据必须**可伪证**：包装函数名只在登记模块内生效，且登记的 verifier 源码里真的调用了门函数
（AST）。否则任何模块里叫 `_guard` 的函数、或 verifier 被改成不调门，都会被误判为已接门。
"""
from __future__ import annotations

import pytest

from app.security import coverage_guard as cg


def test_sync_router_wrapper_is_registered_and_verifier_really_gates() -> None:
    mod, verifier = cg.VERIFIED_GATE_WRAPPERS["_guard"]
    assert mod == "app.routers.wp_sync_router"
    assert cg.verified_wrapper_gate(mod, verifier) is True


def test_sync_handlers_detect_as_gated_through_the_wrapper() -> None:
    from app.routers import wp_sync_router as R

    wired, detail = cg.detect_handler_gate(R.read_entry_readiness)
    assert wired and detail.startswith("wrapper:_guard->"), detail


def test_verifier_that_does_not_call_a_gate_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """把 verifier 指到一个不调门的函数 ⇒ 不再算接门（防登记变成万能开关）。"""
    from app.routers import wp_sync_router as R

    monkeypatch.setitem(cg.VERIFIED_GATE_WRAPPERS, "_guard", ("app.routers.wp_sync_router", "_action_authorizer"))
    assert cg.verified_wrapper_gate("app.routers.wp_sync_router", "_action_authorizer") is False
    wired, _detail = cg.detect_handler_gate(R.read_entry_readiness)
    assert wired is False


def test_wrapper_name_outside_its_module_does_not_count() -> None:
    """其他模块里同名的 `_guard` 不得借登记被判为接门。"""

    async def _guard(*_a, **_k):  # noqa: ANN202
        return None

    async def handler():  # noqa: ANN202
        await _guard()

    wired, _detail = cg.detect_handler_gate(handler)
    assert wired is False


def test_missing_verifier_is_rejected() -> None:
    assert cg.verified_wrapper_gate("app.routers.wp_sync_router", "NoSuchProbe.observe") is False
