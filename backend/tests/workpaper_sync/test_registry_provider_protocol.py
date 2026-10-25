from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.services.workpaper_sync.adapters import registry as RG
from app.services.workpaper_sync.entry_profile import Capability


def _registry_for(
    entry_ids: tuple[str, ...],
) -> RG.WorkpaperSyncAdapterRegistry:
    entries = {
        entry_id: {
            "entry_id": entry_id,
            "independent_entry": True,
            "capability": Capability.bidirectional.value,
        }
        for entry_id in entry_ids
    }
    registry = RG.WorkpaperSyncAdapterRegistry(manifest={"entries": list(entries.values())})
    registry.bind_registration_plan(
        tuple(
            RG.ManifestRegistrationPlanItem(
                entry_id=entry_id,
                capability=Capability.bidirectional,
                provider_module=f"probe.{entry_id}",
            )
            for entry_id in entry_ids
        )
    )
    return registry


@pytest.fixture
def no_supply_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _supply_is_present(*, session: Any, entry_id: str) -> None:
        del session, entry_id
        return None

    monkeypatch.setattr(RG, "_describe_entry_supply", _supply_is_present)


def test_register_from_manifest_accepts_sync_and_async_providers(
    monkeypatch: pytest.MonkeyPatch,
    no_supply_gate: None,
) -> None:
    """统一 provider 协议必须同时接受同步返回值和 awaitable 返回值，并转发 session。"""
    observed_sessions: list[tuple[str, object]] = []
    session = object()
    registry = _registry_for(("xlsx/probe-sync", "xlsx/probe-async"))

    def sync_provider(_registry: Any, *, session: Any) -> tuple[str, ...]:
        observed_sessions.append(("sync", session))
        return ("adapter.sync",)

    async def async_provider(_registry: Any, *, session: Any) -> tuple[str, ...]:
        observed_sessions.append(("async", session))
        return ("adapter.async",)

    providers = {
        "xlsx/probe-sync": sync_provider,
        "xlsx/probe-async": async_provider,
    }
    monkeypatch.setattr(RG, "_load_entry_provider", lambda item: providers[item.entry_id])

    outcome = asyncio.run(registry.register_from_manifest(session=session))

    assert outcome.registered_adapter_ids == ("adapter.async", "adapter.sync")
    assert outcome.registered_entry_ids == ("xlsx/probe-async", "xlsx/probe-sync")
    assert outcome.reasons == {}
    assert outcome.failures == {}
    assert observed_sessions == [("sync", session), ("async", session)]


def test_register_from_manifest_isolates_sync_domain_errors(
    monkeypatch: pytest.MonkeyPatch,
    no_supply_gate: None,
) -> None:
    """域内注册失败只隔离当前 entry，后续 entry 仍继续处理。"""
    registry = _registry_for(("xlsx/probe-failure", "xlsx/probe-ok"))

    def failing_provider(_registry: Any, *, session: Any) -> tuple[str, ...]:
        del session
        raise RG.RegistrationError("probe registration failure")

    async def succeeding_provider(_registry: Any, *, session: Any) -> tuple[str, ...]:
        del session
        return ("adapter.ok",)

    providers = {
        "xlsx/probe-failure": failing_provider,
        "xlsx/probe-ok": succeeding_provider,
    }
    monkeypatch.setattr(RG, "_load_entry_provider", lambda item: providers[item.entry_id])

    outcome = asyncio.run(registry.register_from_manifest(session=object()))

    assert outcome.registered_adapter_ids == ("adapter.ok",)
    assert outcome.registered_entry_ids == ("xlsx/probe-ok",)
    assert outcome.reasons == {}
    failure = outcome.failures["xlsx/probe-failure"]
    assert failure.error_code == "adapter_registration_invalid"
    assert failure.exc_type == "RegistrationError"
    assert failure.message == "probe registration failure"


def test_register_from_manifest_does_not_swallow_provider_type_error(
    monkeypatch: pytest.MonkeyPatch,
    no_supply_gate: None,
) -> None:
    """provider 内部 TypeError 是真实 bug，不能被记成 typed failure。"""
    registry = _registry_for(("xlsx/probe-type-error",))

    def broken_provider(_registry: Any, *, session: Any) -> tuple[str, ...]:
        del session
        raise TypeError("provider implementation bug")

    monkeypatch.setattr(RG, "_load_entry_provider", lambda _item: broken_provider)

    with pytest.raises(TypeError, match="provider implementation bug"):
        asyncio.run(registry.register_from_manifest(session=object()))


@pytest.mark.parametrize("provider_kind", ["sync", "async"])
def test_e1_provider_accepts_registry_session(provider_kind: str) -> None:
    """E1 的 capability 关闭分支仍须接受统一 registry 的 session 参数。"""
    from app.services.workpaper_sync import phase5_e1_monetary_fund as e1

    if provider_kind == "sync":
        result = e1.attach_pilot_adapters(object(), session=object())
    else:
        async def _call() -> tuple[Any, ...]:
            return e1.attach_pilot_adapters(object(), session=object())

        result = asyncio.run(_call())

    assert result == ()


