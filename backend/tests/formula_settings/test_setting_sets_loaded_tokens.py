"""整表差量保存协议：调用生产函数，只在下一层注入真实 EffectiveSlot，不连接数据库。"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call
from uuid import UUID

import pytest

from app.services.formula_settings import setting_sets
from app.services.formula_settings.effective import EffectiveSlot
from app.services.formula_settings.errors import FormulaSettingError, VersionConflict, VersionRequired
from app.services.formula_settings.stores import SlotRecord

PROJECT = UUID("00000000-0000-0000-0000-000000000101")
ACTOR = UUID("00000000-0000-0000-0000-000000000102")
ROW = UUID("00000000-0000-0000-0000-000000000103")
SOURCE = "isolated_set_protocol"
pytestmark = pytest.mark.asyncio


def _slot(key, *, layer="project", version=3, definition=None):
    definition = {"formula": "1"} if definition is None else deepcopy(definition)
    record = SlotRecord(key, definition, version=version, layer=layer, row_id=ROW)
    return EffectiveSlot(key, key, layer, definition,
                         upstream=record if layer != "project" else None,
                         local=record if layer == "project" else None)


def _want(**definition):
    return {"definition": definition, "label": "规则"}


@pytest.fixture
def protocol(monkeypatch):
    state = SimpleNamespace(slots={}, db=SimpleNamespace(commit=AsyncMock()))
    state.read = AsyncMock(side_effect=lambda *_: dict(state.slots))
    state.save = AsyncMock(return_value={"events": []})
    state.remove = AsyncMock(return_value={"events": []})
    monkeypatch.setattr(setting_sets, "effective_slots", state.read)
    monkeypatch.setattr(setting_sets, "save_overrides", state.save)
    monkeypatch.setattr(setting_sets, "restore_global", state.remove)
    yield state
    state.db.commit.assert_not_called()


async def _replace(protocol, *, desired, loaded, domain="tb_detail", prefix=""):
    return await setting_sets.replace_set(
        protocol.db, domain=domain, project_id=PROJECT, desired=desired, loaded=loaded,
        user_id=ACTOR, source=SOURCE, prefix=prefix)


def _no_writes(protocol):
    protocol.save.assert_not_awaited()
    protocol.remove.assert_not_awaited()


@pytest.mark.parametrize("layer", ["project", "global", "preset"])
@pytest.mark.parametrize("coverage", ["absent", "empty", "other"])
async def test_changed_existing_slot_requires_its_own_loaded_key(protocol, layer, coverage):
    protocol.slots = {"old": _slot("old", layer=layer), "other": _slot("other")}
    loaded = {"other": "L3"} if coverage == "other" else (None if coverage == "absent" else {})
    # 把合法新增放在前面：整批预检失败时不得已写入前面的 item。
    desired = {"new": _want(formula="9"), "old": _want(formula="2"), "other": _want(formula="1")}
    with pytest.raises(VersionRequired, match="载入版本") as exc:
        await _replace(protocol, desired=desired, loaded=loaded)
    assert exc.value.status_code == 428
    assert exc.value.detail == {"slot_key": "old"}
    _no_writes(protocol)


@pytest.mark.parametrize("layer", ["project", "global", "preset"])
@pytest.mark.parametrize("loaded", [None, {}], ids=["no_snapshot", "empty_snapshot"])
async def test_unchanged_existing_slot_does_not_block_legal_addition(protocol, layer, loaded):
    protocol.slots = {"old": _slot("old", layer=layer)}
    result = await _replace(protocol, loaded=loaded, desired={
        "old": _want(formula=" 1 ", formula_category="auto_calc", _editing=True),
        "new": _want(formula="2")})
    assert result == {"saved": 1, "removed": 0, "events": []}
    protocol.save.assert_awaited_once_with(
        protocol.db, domain="tb_detail", project_id=PROJECT, user_id=ACTOR, source=SOURCE,
        items=[{"slot_key": "new", "definition": {"formula": "2"}, "label": "规则", "expected_version": None}])
    protocol.remove.assert_not_awaited()


@pytest.mark.parametrize("layer,token,expected", [("project", "L3", 3), ("global", "G3", None),
                                                 ("preset", None, None)])
async def test_matching_loaded_token_allows_change_including_explicit_preset_none(protocol, layer, token, expected):
    protocol.slots = {"old": _slot("old", layer=layer)}
    result = await _replace(protocol, desired={"old": _want(formula="2")}, loaded={"old": token})
    assert result["saved"] == 1 and result["removed"] == 0
    assert protocol.save.await_args.kwargs["items"] == [
        {"slot_key": "old", "definition": {"formula": "2"}, "label": "规则", "expected_version": expected}]
    protocol.remove.assert_not_awaited()


@pytest.mark.parametrize("loaded", [None, {}, {"new": None}])
async def test_genuinely_new_slot_can_be_added_without_an_existing_revision(protocol, loaded):
    result = await _replace(protocol, desired={"new": _want(formula="2")}, loaded=loaded)
    assert result == {"saved": 1, "removed": 0, "events": []}
    assert protocol.save.await_args.kwargs["items"][0]["expected_version"] is None
    protocol.remove.assert_not_awaited()


@pytest.mark.parametrize("layer,token,current", [
    ("project", "L2", "L3"), ("global", "G2", "G3"),
    ("project", "G3", "L3"), ("project", None, "L3"), ("global", None, "G3"),
])
@pytest.mark.parametrize("keep", [True, False], ids=["unchanged_definition", "omitted_definition"])
async def test_every_supplied_token_keeps_full_layer_and_revision_cas(protocol, layer, token, current, keep):
    protocol.slots = {"old": _slot("old", layer=layer)}  # row_id 不变，修订号仍须比较。
    desired = {"new": _want(formula="2")}
    if keep:
        desired["old"] = _want(formula="1")
    with pytest.raises(VersionConflict, match="刷新") as exc:
        await _replace(protocol, desired=desired, loaded={"old": token})
    assert exc.value.status_code == 409
    assert exc.value.detail == {"problems": [{"slot_key": "old", "loaded": token, "current": current}]}
    _no_writes(protocol)


@pytest.mark.parametrize("loaded", [None, {}, {"disabled": "L3"}])
async def test_reenabling_existing_disabled_local_slot_needs_its_loaded_revision(protocol, loaded):
    protocol.slots = {"disabled": _slot("disabled", definition={"disabled": True})}
    if loaded and "disabled" in loaded:
        await _replace(protocol, desired={"disabled": _want(formula="2")}, loaded=loaded)
        assert protocol.save.await_args.kwargs["items"][0]["expected_version"] == 3
    else:
        with pytest.raises(VersionRequired, match="载入版本") as exc:
            await _replace(protocol, desired={"disabled": _want(formula="2")}, loaded=loaded)
        assert exc.value.detail == {"slot_key": "disabled"}
        _no_writes(protocol)


@pytest.mark.parametrize("domain,old,new", [
    ("tb_detail", {"formula": "1", "row_name": "旧名称"}, {"formula": "1", "row_name": "新名称"}),
    ("cross_check", {"left_ref": "1", "label": "旧名称"}, {"left_ref": "1", "label": "新名称"}),
    ("cross_check", {"left_ref": "1", "description": "旧说明"}, {"left_ref": "1", "description": "新说明"}),
])
async def test_registered_descriptive_changes_are_not_misclassified_as_noops(protocol, domain, old, new):
    protocol.slots = {"old": _slot("old", definition=old)}
    with pytest.raises(VersionRequired, match="载入版本"):
        await _replace(protocol, domain=domain, desired={"old": _want(**new)}, loaded={})
    _no_writes(protocol)


@pytest.mark.parametrize("loaded", [None, {}])
async def test_cross_check_normalized_noop_plus_new_rule_needs_no_old_token(protocol, loaded):
    old = {"left_ref": " 1 ", "right_ref": "1", "tolerance": Decimal("0.0100"), "label": "规则"}
    protocol.slots = {"node#old": _slot("node#old", definition=old)}
    desired = {"node#old": _want(left_ref="1", right_ref="1", tolerance=0.01, operator="=", label="规则",
                                 rule_id="old", _editing=True),
               "node#new": _want(left_ref="2", right_ref="2")}
    result = await _replace(protocol, domain="cross_check", desired=desired, loaded=loaded)
    assert result["saved"] == 1
    assert [item["slot_key"] for item in protocol.save.await_args.kwargs["items"]] == ["node#new"]
    protocol.remove.assert_not_awaited()


async def test_normalized_noop_and_outer_label_keep_existing_no_write_contract(protocol):
    protocol.slots = {"old": _slot("old")}
    result = await _replace(protocol, desired={"old": {"definition": {"formula": "1"}, "label": "新展示名"}},
                            loaded={})
    assert result == {"saved": 0, "removed": 0, "events": []}
    _no_writes(protocol)


async def test_missing_snapshot_still_rejects_ambiguous_whole_set_removal(protocol):
    protocol.slots = {"old": _slot("old")}
    with pytest.raises(VersionRequired, match="缺少载入时"):
        await _replace(protocol, desired={}, loaded=None)
    _no_writes(protocol)


@pytest.mark.parametrize("layer,token", [("project", "L3"), ("global", "G3"), ("preset", None)])
async def test_omission_only_removes_loaded_slots_and_preserves_unloaded_concurrent_addition(protocol, layer, token):
    protocol.slots = {"loaded": _slot("loaded", layer=layer), "concurrent": _slot("concurrent", version=4)}
    before = deepcopy(protocol.slots)
    result = await _replace(protocol, desired={}, loaded={"loaded": token})
    if layer == "project":
        assert (result["saved"], result["removed"]) == (0, 1)
        protocol.save.assert_not_awaited()
        protocol.remove.assert_awaited_once_with(
            protocol.db, domain="tb_detail", project_id=PROJECT, slot_keys=["loaded"],
            user_id=ACTOR, expected_versions=None)
    else:
        assert (result["saved"], result["removed"]) == (1, 0)
        protocol.save.assert_awaited_once_with(
            protocol.db, domain="tb_detail", project_id=PROJECT, user_id=ACTOR, source=SOURCE,
            items=[{"slot_key": "loaded", "definition": {"disabled": True}, "expected_version": None}])
        protocol.remove.assert_not_awaited()
    assert protocol.slots == before


async def test_explicit_empty_snapshot_never_deletes_unloaded_slots(protocol):
    protocol.slots = {"concurrent": _slot("concurrent")}
    assert await _replace(protocol, desired={}, loaded={}) == {"saved": 0, "removed": 0, "events": []}
    _no_writes(protocol)


@pytest.mark.parametrize("loaded", [{"first#same": "L3"}, {"first#same": "L3", "second#same": "L3"}],
                         ids=["missing_second_key", "stale_second_revision"])
async def test_slot_identity_includes_node_not_only_rule_id(protocol, loaded):
    definition = {"label": "规则", "left_ref": "1", "right_ref": "1"}
    protocol.slots = {"first#same": _slot("first#same", definition=definition),
                      "second#same": _slot("second#same", version=4, definition=definition)}
    desired = {"first#same": _want(**definition), "second#same": _want(label="规则", left_ref="2", right_ref="1")}
    error = VersionConflict if "second#same" in loaded else VersionRequired
    with pytest.raises(error) as exc:
        await _replace(protocol, domain="cross_check", desired=desired, loaded=loaded)
    if error is VersionConflict:
        assert exc.value.detail["problems"] == [{"slot_key": "second#same", "loaded": "L3", "current": "L4"}]
    else:
        assert exc.value.detail == {"slot_key": "second#same"}
    _no_writes(protocol)


@pytest.mark.parametrize("where", ["desired", "loaded"])
async def test_prefix_rejects_outside_keys_before_any_write(protocol, where):
    protocol.slots = {"五、1|old": _slot("五、1|old"), "五、10|old": _slot("五、10|old")}
    desired = {"五、1|old": _want(formula="2")}
    loaded = {"五、1|old": "L3"}
    if where == "desired":
        desired["五、10|old"] = _want(formula="1")
    else:
        loaded["五、10|old"] = "L3"
    with pytest.raises(FormulaSettingError, match="不属于本次保存的范围") as exc:
        await _replace(protocol, desired=desired, loaded=loaded, prefix="五、1|")
    assert exc.value.status_code == 400
    _no_writes(protocol)


@pytest.mark.parametrize("loaded", [None, {}])
async def test_outside_live_slots_do_not_block_prefix_local_new_slot(protocol, loaded):
    protocol.slots = {"五、10|old": _slot("五、10|old")}
    result = await _replace(protocol, desired={"五、1|new": _want(formula="2")}, loaded=loaded, prefix="五、1|")
    assert result["saved"] == 1 and result["removed"] == 0
    assert [item["slot_key"] for item in protocol.save.await_args.kwargs["items"]] == ["五、1|new"]
    protocol.remove.assert_not_awaited()


async def test_mixed_plan_keeps_cas_arguments_prefix_and_merged_receipt_without_committing(protocol):
    protocol.slots = {
        "五、1|change": _slot("五、1|change"), "五、1|remove": _slot("五、1|remove"),
        "五、1|disable": _slot("五、1|disable", layer="global"),
        "五、1|concurrent": _slot("五、1|concurrent", version=4),
        "五、10|outside": _slot("五、10|outside"),
    }
    protocol.save.return_value = {"events": [{"project_id": str(PROJECT), "slot_keys": ["五、1|change", "五、1|disable"]}]}
    protocol.remove.return_value = {"events": [{"project_id": str(PROJECT), "slot_keys": ["五、1|remove"]}]}
    # 两个 writer 共用调用轨迹，既验内容又验先保存、后恢复的既有顺序。
    order = Mock()
    order.attach_mock(protocol.save, "save")
    order.attach_mock(protocol.remove, "remove")
    result = await _replace(protocol, desired={"五、1|change": _want(formula="2")}, prefix="五、1|",
                            loaded={"五、1|change": "L3", "五、1|remove": "L3", "五、1|disable": "G3"})
    assert order.mock_calls == [
        call.save(protocol.db, domain="tb_detail", project_id=PROJECT, user_id=ACTOR, source=SOURCE, items=[
            {"slot_key": "五、1|change", "definition": {"formula": "2"}, "label": "规则", "expected_version": 3},
            {"slot_key": "五、1|disable", "definition": {"disabled": True}, "expected_version": None}]),
        call.remove(protocol.db, domain="tb_detail", project_id=PROJECT, slot_keys=["五、1|remove"],
                    user_id=ACTOR, expected_versions=None),
    ]
    assert result == {"saved": 2, "removed": 1, "events": [{
        "project_id": str(PROJECT), "slot_keys": ["五、1|change", "五、1|disable", "五、1|remove"]}]}
    protocol.read.assert_awaited_once_with(protocol.db, "tb_detail", PROJECT)


async def test_distinct_nodes_with_same_rule_id_save_with_their_own_current_revisions(protocol):
    definition = {"label": "规则", "left_ref": "1", "right_ref": "1"}
    protocol.slots = {
        "first#same": _slot("first#same", definition=definition),
        "second#same": _slot("second#same", version=4, definition=definition),
    }
    result = await _replace(protocol, domain="cross_check", loaded={"first#same": "L3", "second#same": "L4"},
                            desired={"first#same": _want(label="规则", left_ref="2", right_ref="1"),
                                     "second#same": _want(label="规则", left_ref="3", right_ref="1")})
    assert result == {"saved": 2, "removed": 0, "events": []}
    assert [(item["slot_key"], item["expected_version"]) for item in protocol.save.await_args.kwargs["items"]] == [
        ("first#same", 3), ("second#same", 4)]
    protocol.remove.assert_not_awaited()
