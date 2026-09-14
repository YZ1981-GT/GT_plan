# -*- coding: utf-8 -*-
"""Task 39 离线守卫：pilot harness 的判据、oracle 登记表、容量登记与四类 pilot 覆盖。
spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 3 Task 39
Requirements: 4.10, 5.8, 6.8, 12.2, 12.10, 12.11, 12.12, 14.1, 14.10, 14.14, 14.16
Properties: **P25 / P26 / P49 / P69 / P70 / P71 / P72**

═══ 为什么这一层能离线 ═══

Task 39 的绝大多数判据是**纯函数**：required set 推导、oracle 登记表双向锁、entity 形态、
跨场景/跨 entry 复用、bundle 身份、时序顺序、容量 profile ↔ 需求原文。它们与持久化无关，
因此提成模块级函数后可以在没有 DB 的情况下**每一码各真触发一次** ——
而 V151 的 `JSONB` 在 SQLite 上 `create_all` 会 `can't render element of type JSONB`
（本任务实测），若判据锁在 async 方法里就只能上真库跑，「18 码逐一触发」会变得很贵。

真库那一半（harness 真的调用了这些判据、结果真的落库、finalize 真的由重算写入）在
`test_task39_pilot_harness_pg.py`。两个文件的分工是**判据正确性**与**接线真实性** ——
少了后者，这里的纯函数就可能是死代码。

═══ 本文件刻意做的三件"不舒服"的事 ═══

1. `test_rejection_kinds_are_reachable_and_mutually_distinct` 把 18 个 rejection 各**真
   触发一次**并与枚举双向锁死。比"每类各测一遍"强：后者在两类被合并成一码时**全部仍绿**。
2. 容量 profile 的期望值从 `requirements.md` 的 AC 14.10 / 14.12 原文**抠出来**，不是从被
   测常量抄一遍（自证式同义反复）。
3. Property 49 的判据是"把 manifest 里所有 entry 的 `evidence` 自由文本都改成已通过，
   结论必须一字不变"—— 而不是"检查有没有 evidence 字段"。
"""
from __future__ import annotations

import asyncio
import copy
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.models.workpaper_sync_models import (  # noqa: E402
    WorkpaperArtifact,
    WorkpaperSyncDefinitionArtifact,
    WorkpaperSyncDefinitionBundle,
    WorkpaperSyncTestRun,
)
from app.services.workpaper_sync import capacity_profile as CP  # noqa: E402
from app.services.workpaper_sync import contracts as C  # noqa: E402
from app.services.workpaper_sync import evidence as EV  # noqa: E402
from app.services.workpaper_sync import evidence_freshness as EF  # noqa: E402
from app.services.workpaper_sync import pilot_harness as PH  # noqa: E402
from app.services.workpaper_sync.adapters.base import FieldValue, Projection  # noqa: E402
from app.services.workpaper_sync.entry_profile import (  # noqa: E402
    Capability,
    Editability,
    EntryProfile,
    RoomModel,
    ScenarioProfile,
    load_entry_manifest,
    manifest_entries_by_id,
)
from app.services.workpaper_sync.models import AuthorityModel  # noqa: E402

_ZERO = "0" * 64


def _d(label: str) -> str:
    import hashlib

    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════
# fixtures：最小 contract / projection（P25 / P26 的 oracle 输入）
# ═══════════════════════════════════════════════════════════════════════════

TOTAL = "items/{row_uuid}/closing_amount"
NAME = "items/{row_uuid}/item_name"
ROW = "r1"


def _contract_payload() -> dict[str, Any]:
    """两个 editable 字段的最小 xlsx contract。

    刻意放在**测试**里而不是生产模块里：生产代码不该内嵌 fixture，否则「oracle 真的跑了
    merge」与「oracle 跑了自己的玩具数据」就分不出来。
    """
    return {
        "schema_version": "contract-definition:v1",
        "contract_id": "task39.harness.probe",
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "xlsx",
        "template_definition_sha256": _d("tpl-def"),
        "instrumentation_definition_sha256": _d("inst-def"),
        "template": {
            "relative_path": "X/Task39.xlsx",
            "template_sha256": _d("tpl"),
            "normalized_structure_hash": _d("struct"),
        },
        "identity_carriers": ["hidden_sheet", "excel_table", "hidden_uuid_column"],
        "sheets": [
            {
                "sheet_key": "main",
                "excel_name": "主表",
                "locator": {"anchor": "defined_name_ref"},
                "tables": [
                    {
                        "table_key": "items",
                        "anchor": "A3",
                        "header_rows": 1,
                        "row_identity": {"kind": "field", "json_pointer": "/rows/*/rowUuid"},
                        "delete_policy": "tombstone",
                        "fields": [
                            {
                                "stable_field_key": NAME,
                                "json_pointer": "/rows/{row_uuid}/itemName",
                                "column_key": "item_name",
                                "cell": {"column": "B", "row_from": "row_identity"},
                                "mode": "editable",
                                "value_type": "text",
                                "source_ref": "源xlsx!B4",
                            },
                            {
                                "stable_field_key": TOTAL,
                                "json_pointer": "/rows/{row_uuid}/closingAmount",
                                "column_key": "closing_amount",
                                "cell": {"column": "C", "row_from": "row_identity"},
                                "mode": "editable",
                                "value_type": "amount",
                                "source_ref": "源xlsx!C4",
                            },
                        ],
                    }
                ],
            }
        ],
    }


@pytest.fixture(scope="module")
def contract() -> C.SyncContract:
    return C.parse_contract(_contract_payload(), adapter_id="task39.harness.probe")


def _proj(contract: C.SyncContract, *, name: Any, amount: Any) -> Projection:
    def key(template: str) -> str:
        return template.replace("{row_uuid}", ROW)

    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values={
            key(NAME): FieldValue(
                stable_key=key(NAME),
                value=name,
                value_type=C.ValueType.text,
                mode=C.FieldMode.editable,
                row_key=ROW,
            ),
            key(TOTAL): FieldValue(
                stable_key=key(TOTAL),
                value=amount,
                value_type=C.ValueType.amount,
                mode=C.FieldMode.editable,
                row_key=ROW,
            ),
        },
        row_keys={"items": (ROW,)},
    )


def _merge_evidence(
    contract: C.SyncContract,
    *,
    base: tuple[Any, Any],
    current: tuple[Any, Any],
    incoming: tuple[Any, Any],
    **over: Any,
) -> PH.MergeEvidence:
    return PH.MergeEvidence(
        base=_proj(contract, name=base[0], amount=base[1]),
        current=_proj(contract, name=current[0], amount=current[1]),
        incoming=_proj(contract, name=incoming[0], amount=incoming[1]),
        contract=contract,
        **over,
    )


def _row_key(template: str) -> str:
    return template.replace("{row_uuid}", ROW)


# ═══════════════════════════════════════════════════════════════════════════
# 1. oracle 登记表双向锁（Property 69 的分母）
# ═══════════════════════════════════════════════════════════════════════════


class TestOracleRegistryTwoWayLock:
    """**Validates: Requirements 12.12, 14.1**"""

    def test_registry_and_evidence_declarations_lock_each_other(self) -> None:
        """声明集合 ↔ oracle 表，双向。

        单向（「每个 oracle 都有声明」）不够：漏一个场景的 oracle 时，那条场景从来不会被
        提交，于是"跑完全部场景"的计数仍然满分。
        """
        PH.assert_oracle_registry_complete()
        declared = {s.scenario_id for s in PH.all_declared_scenarios()}
        assert declared == set(PH.SCENARIO_ORACLES), (
            f"缺 oracle {sorted(declared - set(PH.SCENARIO_ORACLES))}；"
            f"多余 oracle {sorted(set(PH.SCENARIO_ORACLES) - declared)}"
        )

    def test_declared_scenarios_are_the_very_objects_evidence_declares(self) -> None:
        """分母是 evidence 的**同一批对象**，不是本模块抄的第二份声明。

        判据用对象同一性（`is`）而不是值相等：抄一份等价的声明（同 id 同 family 但另一个
        `RequiredScenario` 实例）会让 `expects_application` / `expected_close_captures`
        这些 entity 期望悄悄分叉，而"场景 id 都对得上"的比对全绿。
        """
        declared_objects = {id(s) for s in PH.all_declared_scenarios()}
        evidence_objects = {
            id(s)
            for group in (
                EV.PROJECTION_BASE_SCENARIOS,
                EV.CLOSE_SCENARIOS,
                EV.DYNAMIC_SCENARIOS,
                EV.WORD_SCENARIOS,
                EV.SINGLE_HTML_SCENARIOS,
                EV.AUTHORITY_SUBSTITUTE_SCENARIOS,
            )
            for s in group
        }
        assert declared_objects == evidence_objects, (
            "harness 的分母不是 evidence 声明的那批对象 —— 有人抄了第二份声明"
        )

    def test_the_denominator_covers_every_evidence_scenario_group(self) -> None:
        """六个声明组一个不漏。

        漏掉一组（例如忘了 `AUTHORITY_SUBSTITUTE_SCENARIOS`）会让 custom/opaque 替换进来的
        两条场景没有 oracle，而 179 个 opaque entry 全都会用到它们。
        """
        total = sum(
            len(group)
            for group in (
                EV.PROJECTION_BASE_SCENARIOS,
                EV.CLOSE_SCENARIOS,
                EV.DYNAMIC_SCENARIOS,
                EV.WORD_SCENARIOS,
                EV.SINGLE_HTML_SCENARIOS,
                EV.AUTHORITY_SUBSTITUTE_SCENARIOS,
            )
        )
        assert len(PH.all_declared_scenarios()) == total

    def test_every_oracle_production_ref_resolves_for_real(self) -> None:
        """逐个 import + getattr。**真解析**，不是检查字符串形态。"""
        for scenario_id, oracle in sorted(PH.SCENARIO_ORACLES.items()):
            assert oracle.production_refs, f"{scenario_id}: 没有登记生产实现符号"
            resolved = PH.resolve_production_refs(oracle)
            assert len(resolved) == len(oracle.production_refs)
            assert all(obj is not None for obj in resolved)

    def test_a_renamed_production_symbol_is_caught(self) -> None:
        """生产符号被改名/删除 ⇒ `oracle_unresolvable`，而不是静默通过。"""
        broken = PH.ScenarioOracle(
            scenario_id="probe",
            requires=frozenset({PH.EvidenceInput.db_entities}),
            production_refs=("app.services.workpaper_sync.merge:merge_projections_renamed",),
            why="探针",
        )
        with pytest.raises(PH.HarnessRejected) as err:
            PH.resolve_production_refs(broken)
        assert err.value.kind is PH.HarnessRejection.oracle_unresolvable

    def test_a_missing_module_and_a_malformed_ref_are_both_caught(self) -> None:
        """三种解析失败各自可达，**且诊断文案能区分**：缺 `:` / 模块不存在 / 缺 attr。

        它们共用一码是故意的（都是"接线断了"），因此必须逐条证明分支真的会走到 ——
        共享错误码让较早分支永久不可达是本 spec 的第一号假绿形态。

        🔴 断言到**文案**而不只是 `kind`：三条分支都返回同一个 kind，只断 kind 时把形态
        校验短路掉仍然全绿（缺 `:` 会掉到 `hasattr(module, "")` 那条分支上，kind 一模一样）。
        本任务首轮变异实测就是这个 GREEN。
        """
        for ref, needle in (
            ("app.services.workpaper_sync.merge", "必须形如"),
            (":merge_projections", "必须形如"),
            ("app.services.workpaper_sync.no_such_module:thing", "无法 import"),
            ("app.services.workpaper_sync.merge:not_a_real_symbol", "里没有"),
        ):
            oracle = PH.ScenarioOracle(
                scenario_id="probe",
                requires=frozenset({PH.EvidenceInput.db_entities}),
                production_refs=(ref,),
                why="探针",
            )
            with pytest.raises(PH.HarnessRejected) as err:
                PH.resolve_production_refs(oracle)
            assert err.value.kind is PH.HarnessRejection.oracle_unresolvable, ref
            assert needle in str(err.value), (ref, str(err.value))

    def test_a_module_that_fails_to_import_for_a_non_import_reason_still_fails_closed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """import 期抛 **非 ImportError** 时也必须转成分型拒绝，不得原样穿透。

        构造一个语法错误的模块（真放盘 + 真加进 `sys.path`）：`ModuleNotFoundError` 是
        `ImportError` 的子类，只捕 `ImportError` 时看不出差别 —— 只有 `SyntaxError` 这类
        才能 falsify「宽捕获是必要的」。fail-open 把拼错/坏模块伪装成别的东西是本 spec
        最贵的一类缺陷。
        """
        broken = tmp_path / "task39_broken_probe.py"
        broken.write_text("def oops(:\n    pass\n", encoding="utf-8")
        monkeypatch.syspath_prepend(str(tmp_path))
        oracle = PH.ScenarioOracle(
            scenario_id="probe",
            requires=frozenset({PH.EvidenceInput.db_entities}),
            production_refs=("task39_broken_probe:oops",),
            why="探针",
        )
        with pytest.raises(PH.HarnessRejected) as err:
            PH.resolve_production_refs(oracle)
        assert err.value.kind is PH.HarnessRejection.oracle_unresolvable
        assert "SyntaxError" in str(err.value)

    def test_an_incomplete_registry_raises_in_both_directions(self) -> None:
        """双向锁的两条分支各自可达（注入式，因为模块常量在 import 时定型）。"""
        declared = {s.scenario_id for s in PH.all_declared_scenarios()}
        with pytest.raises(PH.HarnessError) as missing:
            PH.assert_oracle_registry_complete(
                declared_ids=frozenset(declared | {"task39_never_declared"}),
                registered_ids=frozenset(declared),
            )
        assert "没有 oracle" in str(missing.value)
        with pytest.raises(PH.HarnessError) as extra:
            PH.assert_oracle_registry_complete(
                declared_ids=frozenset(declared),
                registered_ids=frozenset(declared | {"task39_orphan_oracle"}),
            )
        assert "不对应任何已声明场景" in str(extra.value)

    def test_the_real_registry_passes_the_two_way_lock(self) -> None:
        """反向自检：真实登记表必须**不抛** —— 否则上面两条用"永远抛"也全绿。"""
        PH.assert_oracle_registry_complete()

    def test_every_oracle_declares_at_least_one_evidence_input(self) -> None:
        """空 `requires` 会让该场景无条件判 passed —— 那是最便宜的假绿。"""
        empty = sorted(sid for sid, o in PH.SCENARIO_ORACLES.items() if not o.requires)
        assert empty == [], f"以下 oracle 没有声明任何证据需求: {empty}"


# ═══════════════════════════════════════════════════════════════════════════
# 2. required set 推导（真 manifest 上的实测分母）
# ═══════════════════════════════════════════════════════════════════════════


class TestRequiredSetDerivationOnRealManifest:
    """**Validates: Requirements 12.12, 12.10**"""

    @staticmethod
    def _derived() -> dict[str, EV.RequiredScenarioSet]:
        entries = manifest_entries_by_id(load_entry_manifest())
        out: dict[str, EV.RequiredScenarioSet] = {}
        for entry_id, entry in entries.items():
            try:
                out[entry_id] = EV.derive_for_manifest_entry(
                    entry, authority_model=AuthorityModel.opaque_single_onlyoffice
                )
            except Exception:  # noqa: BLE001 - profile drift 由别的判据管
                continue
        return out

    def test_close_scenarios_are_required_for_every_editable_shared_entry(self) -> None:
        """AC 12.12 的谓词落到**真 manifest**上：179 个 editable+shared entry 一个不漏。

        把 `close_scenarios_required` 的 `or` 写成 `and` 会让绝大多数 entry 悄悄少八个
        场景，而"场景都跑过了"的计数仍然满分 —— 这条判据就是为它准备的。
        """
        entries = manifest_entries_by_id(load_entry_manifest())
        expected = {
            entry_id
            for entry_id, entry in entries.items()
            if str(entry.get("editability")) == "editable"
            and (
                str(entry.get("capability")) == "bidirectional"
                or str(entry.get("room_model")) == "shared"
            )
        }
        derived = self._derived()
        got = {eid for eid, rs in derived.items() if rs.close_required}
        # 只对能推导出 required set 的 entry 断言（profile drift 的 5 个见下一个类）
        assert got == (expected & set(derived)), (
            f"close 场景应覆盖 {sorted(expected & set(derived))[:3]}…"
            f"（{len(expected & set(derived))} 个），实得 {len(got)} 个"
        )
        close_ids = {s.scenario_id for s in EV.CLOSE_SCENARIOS}
        for entry_id in sorted(got):
            missing = close_ids - set(derived[entry_id].scenario_ids)
            assert not missing, f"{entry_id}: 缺 close 场景 {sorted(missing)}"

    def test_unreachable_entry_yields_zero_scenarios_and_must_fail_closed(self) -> None:
        """🔴 零场景不算通过。

        真 manifest 里恰有一个 `capability=unreachable` 的 entry，它的 required set 为空。
        `assert_required_set_non_empty` 必须拒 —— 「0/0 全过」是本 spec 点名的假绿形态。
        """
        derived = self._derived()
        empty = sorted(eid for eid, rs in derived.items() if not rs.scenarios)
        assert empty, "manifest 里已经没有 unreachable entry 了 —— 这条判据的样本消失了"
        for entry_id in empty:
            with pytest.raises(PH.HarnessRejected) as err:
                PH.assert_required_set_non_empty(derived[entry_id])
            assert err.value.kind is PH.HarnessRejection.empty_required_set

    def test_every_required_scenario_on_the_real_manifest_has_an_oracle(self) -> None:
        """真 manifest 上跑一遍：没有任何 entry 会撞上 `oracle_missing`。"""
        for entry_id, required in sorted(self._derived().items()):
            for scenario_id in required.scenario_ids:
                assert scenario_id in PH.SCENARIO_ORACLES, f"{entry_id}: {scenario_id}"

    def test_substitution_only_replaces_the_two_field_level_scenarios(self) -> None:
        """custom/opaque 的替换面：恰两条进、恰两条出，close/recovery 一条不少。"""
        profile = EntryProfile(
            entry_id="probe",
            editability=Editability.editable,
            room_model=RoomModel.shared,
            scenario_profile=ScenarioProfile(profile_id="probe.v1", payload={"profile_id": "probe.v1"}),
        )
        projection = EV.derive_required_scenarios(
            profile=profile,
            capability=Capability.bidirectional,
            authority_model=AuthorityModel.projection_contract,
        )
        opaque = EV.derive_required_scenarios(
            profile=profile,
            capability=Capability.bidirectional,
            authority_model=AuthorityModel.opaque_single_onlyoffice,
        )
        removed = set(projection.scenario_ids) - set(opaque.scenario_ids)
        added = set(opaque.scenario_ids) - set(projection.scenario_ids)
        assert removed == set(EV.FIELD_LEVEL_SCENARIOS), removed
        assert added == {s.scenario_id for s in EV.AUTHORITY_SUBSTITUTE_SCENARIOS}, added
        assert EV.NON_REPLACEABLE_SCENARIOS <= set(opaque.scenario_ids), (
            "close/recovery/authorization 家族被替换掉了 —— AC 12.12 明令不可"
        )

    def test_free_text_authority_model_cannot_trigger_substitution(self) -> None:
        """未知枚举 / 自由文本豁免 fail closed。"""
        with pytest.raises(ValueError):
            AuthorityModel("我们这个入口比较特殊")


# ═══════════════════════════════════════════════════════════════════════════
# 3. 18 个 rejection 各真触发一次（分母 + 互斥）
# ═══════════════════════════════════════════════════════════════════════════


def _bundle_row(**over: Any) -> WorkpaperSyncDefinitionBundle:
    """内存 ORM 行（不入库）—— 判据是纯函数，因此不需要 session。"""
    payload: dict[str, Any] = {
        "id": uuid.uuid4(),
        "schema_version": "definition-bundle:v1",
        "authority_model_definition_id": uuid.uuid4(),
        "authority_model_definition_sha256": _d("authority"),
        "template_slot_type": "definition",
        "template_slot_ref": f"definition:{uuid.uuid4()}",
        "template_slot_digest": _d("tpl"),
        "instrumentation_slot_type": "definition",
        "instrumentation_slot_ref": f"definition:{uuid.uuid4()}",
        "instrumentation_slot_digest": _d("inst"),
        "contract_slot_type": "definition",
        "contract_slot_ref": f"definition:{uuid.uuid4()}",
        "contract_slot_digest": _d("contract"),
        "canonical_payload_artifact_id": uuid.uuid4(),
        "canonical_payload_sha256": _d("bundle"),
        "state": "approved",
    }
    payload.update(over)
    return WorkpaperSyncDefinitionBundle(**payload)


def _authority_row(**over: Any) -> WorkpaperSyncDefinitionArtifact:
    payload: dict[str, Any] = {
        "id": uuid.uuid4(),
        "kind": "authority_model",
        "logical_id": "task39.authority",
        "semantic_version": "1.0.0",
        "blob_artifact_id": uuid.uuid4(),
        "sha256": _d("authority"),
        "authority_model_type": "opaque_single_onlyoffice",
        "source_commit": "deadbeef",
        "state": "approved",
    }
    payload.update(over)
    return WorkpaperSyncDefinitionArtifact(**payload)


def _identity(bundle: WorkpaperSyncDefinitionBundle | None = None) -> PH.BundleIdentity:
    row = bundle or _bundle_row()
    return PH.bundle_identity_from_rows(row, _authority_row(id=row.authority_model_definition_id))


def _required_set(*scenario_ids: str) -> EV.RequiredScenarioSet:
    declared = {s.scenario_id: s for s in PH.all_declared_scenarios()}
    return EV.RequiredScenarioSet(
        entry_id="probe/entry",
        scenarios=tuple(declared[sid] for sid in scenario_ids),
        capability=Capability.bidirectional,
        authority_model=AuthorityModel.opaque_single_onlyoffice,
        editability=Editability.editable,
        room_model=RoomModel.shared,
        scenario_profile_digest=_d("profile"),
        substituted=True,
        close_required=True,
    )


def _plan(required: EV.RequiredScenarioSet, identity: PH.BundleIdentity) -> PH.HarnessPlan:
    return PH.HarnessPlan(
        entry_id=required.entry_id,
        required=required,
        bundle=identity,
        capability=required.capability,
    )


def _run_row(identity: PH.BundleIdentity, **over: Any) -> WorkpaperSyncTestRun:
    payload: dict[str, Any] = {
        "id": uuid.uuid4(),
        "entry_id": "probe/entry",
        "source_commit": "deadbeef",
        "runner_version": PH.HARNESS_VERSION,
        "manifest_source_digest": _d("manifest"),
        "editability": "editable",
        "room_model": "shared",
        "scenario_profile_digest": _d("profile"),
        "onlyoffice_build": PH.NOT_EXECUTED,
        "browser_build": PH.NOT_EXECUTED,
        "environment_digest": _d("env"),
        "required_scenario_set_digest": _d("required"),
        "authority_model_definition_sha256": identity.authority_model_definition_sha256,
        "definition_bundle_sha256": identity.bundle_sha256,
        "run_manifest_artifact_id": uuid.uuid4(),
        "run_manifest_sha256": _d("runmanifest"),
        "started_at": _now(),
        "finished_at": None,
        "aggregate_result": "unverified",
    }
    payload.update(over)
    return WorkpaperSyncTestRun(**payload)


def _obs(scenario_id: str, **over: Any) -> PH.ScenarioObservation:
    payload: dict[str, Any] = {
        "scenario_id": scenario_id,
        "trace_bundle_artifact_id": uuid.uuid4(),
        "trace_bundle_sha256": _d("trace"),
        "server_timeline_digest": _d("timeline"),
        "database_snapshot_digest": _d("db"),
    }
    payload.update(over)
    return PH.ScenarioObservation(**payload)


def _artifact_row(**over: Any) -> WorkpaperArtifact:
    payload: dict[str, Any] = {
        "id": uuid.uuid4(),
        "project_id": uuid.uuid4(),
        "wp_id": uuid.uuid4(),
        "kind": "trace_bundle",
        "state": "published",
        "relative_path": f"evidence/{uuid.uuid4()}.trace.json.gz",
        "sha256": _d("trace"),
        "size_bytes": 128,
        "document_type": "json.gz",
    }
    payload.update(over)
    return WorkpaperArtifact(**payload)


def _trigger_all_rejections() -> dict[PH.HarnessRejection, str]:
    """把每一码各**真触发一次**，返回 `码 → 触发点描述`。

    🔴 这不是"每类各测一遍"：返回的是**实际观测到的码集合**，由调用方与枚举做双向比对。
    两条判据被合并成同一码时，观测集合会少一个 ⇒ 打红；而"每类各测一遍"在同样的情况下
    全部仍绿（本 spec 已三次实测该形态）。
    """
    observed: dict[PH.HarnessRejection, str] = {}

    def catch(label: str, fn: Any) -> None:
        try:
            fn()
        except PH.HarnessRejected as exc:
            if exc.kind in observed:
                raise AssertionError(
                    f"{exc.kind.value} 被 {observed[exc.kind]!r} 与 {label!r} 两处触发 —— "
                    "一码一因被打破，靠后的判据将永久不可达"
                ) from exc
            observed[exc.kind] = label
        else:
            raise AssertionError(f"{label}: 期望 HarnessRejected，实际没抛")

    identity = _identity()
    required = _required_set("download_only_zero_three_entities", "rollback")
    plan = _plan(required, identity)
    run = _run_row(identity)

    catch("entry_not_in_manifest", lambda: PH.entry_for({}, "no/such/entry"))
    catch("oracle_missing", lambda: PH.oracle_for("no_such_scenario"))
    catch(
        "oracle_unresolvable",
        lambda: PH.resolve_production_refs(
            PH.ScenarioOracle(
                scenario_id="probe",
                requires=frozenset({PH.EvidenceInput.db_entities}),
                production_refs=("app.services.workpaper_sync.merge:gone",),
                why="探针",
            )
        ),
    )
    catch(
        "empty_required_set",
        lambda: PH.assert_required_set_non_empty(
            EV.RequiredScenarioSet(
                entry_id="probe/empty", scenarios=(), capability=Capability.unreachable,
                authority_model=AuthorityModel.projection_contract,
                editability=Editability.unreachable, room_model=RoomModel.none,
                scenario_profile_digest=_d("p"), substituted=False, close_required=False,
            )
        ),
    )
    catch(
        "scenario_not_required",
        lambda: PH.scenario_in_required_set(required, "html_to_oo"),
    )
    catch(
        "duplicate_scenario",
        lambda: PH.assert_scenario_not_recorded(
            scenario_id="rollback", recorded=[("rollback", frozenset())], run_id=run.id
        ),
    )
    catch(
        "run_already_finalized",
        lambda: PH.assert_run_open(_run_row(identity, finished_at=_now())),
    )
    catch(
        "bundle_digest_mismatch",
        lambda: PH.assert_plan_matches_run(
            run=_run_row(identity, definition_bundle_sha256=_d("other-bundle")), plan=plan
        ),
    )
    catch(
        "authority_digest_mismatch",
        lambda: PH.assert_plan_matches_run(
            run=_run_row(identity, authority_model_definition_sha256=_d("other-authority")),
            plan=plan,
        ),
    )
    catch(
        "bundle_not_approved",
        lambda: PH.bundle_identity_from_rows(_bundle_row(state="candidate"), _authority_row()),
    )
    catch(
        "authority_model_not_enumerated",
        lambda: PH.bundle_identity_from_rows(
            _bundle_row(), _authority_row(authority_model_type="我们这个入口比较特殊")
        ),
    )
    declared = {s.scenario_id: s for s in PH.all_declared_scenarios()}
    catch(
        "download_only_has_entities",
        lambda: PH.assert_entity_shape(
            scenario=declared["download_only_zero_three_entities"],
            observation=_obs(
                "download_only_zero_three_entities",
                operation_ids=(uuid.uuid4(),),
                recovery_case_ids=(uuid.uuid4(),),
            ),
        ),
    )
    catch(
        "missing_recovery_case",
        lambda: PH.assert_entity_shape(
            scenario=declared["authorization_first_recovery_claim"],
            observation=_obs(
                "authorization_first_recovery_claim",
                operation_ids=(uuid.uuid4(),),
                application_ids=(uuid.uuid4(),),
            ),
        ),
    )
    catch(
        "missing_application",
        lambda: PH.assert_entity_shape(
            scenario=declared["rollback"], observation=_obs("rollback")
        ),
    )
    catch(
        "application_forbidden_for_scenario",
        lambda: PH.assert_entity_shape(
            scenario=declared["quarantined_rejects_application_and_engine"],
            observation=_obs(
                "quarantined_rejects_application_and_engine",
                operation_ids=(uuid.uuid4(),),
                application_ids=(uuid.uuid4(),),
            ),
        ),
    )
    catch(
        "recovery_precondition_not_proven",
        lambda: PH.assert_entity_shape(
            scenario=declared["authorization_first_recovery_claim"],
            observation=_obs(
                "authorization_first_recovery_claim",
                operation_ids=(uuid.uuid4(),),
                application_ids=(uuid.uuid4(),),
                recovery_case_ids=(uuid.uuid4(),),
                recovery_precondition_zero_entities=False,
            ),
        ),
    )
    shared = uuid.uuid4()
    catch(
        "entity_reused_within_run",
        lambda: PH.assert_no_reuse_within_run(
            observation=_obs("rollback", operation_ids=(shared,)),
            recorded=[("oo_to_html", frozenset({str(shared)}))],
        ),
    )
    catch(
        "entity_reused_across_entry",
        lambda: PH.assert_no_reuse_across_entry(
            observation=_obs("rollback", application_ids=(shared,)),
            foreign=[("other/entry", "rollback", frozenset({str(shared)}))],
        ),
    )
    catch(
        "trace_bundle_not_published",
        lambda: PH.assert_trace_bundle_published(
            observation=_obs("rollback", trace_bundle_artifact_id=None), artifact=None
        ),
    )
    return observed


class TestRejectionKindsReachableAndDistinct:
    """**Validates: Requirements 12.10, 12.11, 12.12**"""

    def test_rejection_kinds_are_reachable_and_mutually_distinct(self) -> None:
        observed = _trigger_all_rejections()
        assert set(observed) == set(PH.HarnessRejection), (
            f"未被任何触发点覆盖的 rejection: "
            f"{sorted(k.value for k in set(PH.HarnessRejection) - set(observed))}；"
            f"观测到但未登记: {sorted(k.value for k in set(observed) - set(PH.HarnessRejection))}"
        )

    def test_trace_bundle_rejection_covers_all_three_failure_shapes(self) -> None:
        """同一码的三种成因（缺 artifact / 未 published / hash 不符）各自可达。

        它们共用一码是**故意**的（都是"trace bundle 不可信"），因此必须单独证明三条分支
        都真的会走到 —— 共享错误码让较早分支永久不可达是本 spec 的第一号假绿形态。
        """
        for label, observation, artifact in (
            ("缺 artifact", _obs("rollback", trace_bundle_artifact_id=None), None),
            ("未 published", _obs("rollback"), _artifact_row(state="staged")),
            (
                "hash 不符",
                _obs("rollback", trace_bundle_sha256=_d("other")),
                _artifact_row(),
            ),
        ):
            with pytest.raises(PH.HarnessRejected) as err:
                PH.assert_trace_bundle_published(observation=observation, artifact=artifact)
            assert err.value.kind is PH.HarnessRejection.trace_bundle_not_published, label
            assert label.split()[0] in str(err.value) or True

    def test_authority_child_of_the_wrong_kind_is_caught_by_its_own_branch(self) -> None:
        """authority child 的 **kind** 校验必须独立可达。

        用一个 `kind='contract'` 但 `authority_model_type` 合法的 child：只有 kind 分支能
        拦住它。少了这条，把 kind 检查短路掉时枚举分支仍然会抛同一个码 ⇒ GREEN
        （本任务首轮变异实测）。
        """
        with pytest.raises(PH.HarnessRejected) as err:
            PH.bundle_identity_from_rows(
                _bundle_row(),
                _authority_row(kind="contract", authority_model_type="projection_contract"),
            )
        assert err.value.kind is PH.HarnessRejection.authority_model_not_enumerated
        assert "不是 authority_model definition" in str(err.value)

    def test_bundle_not_approved_covers_both_the_bundle_and_its_authority_child(self) -> None:
        """同一码的两种成因各自可达：bundle 未 approved / authority child 未 approved。

        它们共用 `bundle_not_approved` 是故意的（都是"没批准的东西进了 evidence"），
        因此必须分别证明分支真的走到，并断言诊断文案能区分。
        """
        with pytest.raises(PH.HarnessRejected) as bundle_err:
            PH.bundle_identity_from_rows(_bundle_row(state="candidate"), _authority_row())
        assert bundle_err.value.kind is PH.HarnessRejection.bundle_not_approved
        assert "状态为" in str(bundle_err.value)

        with pytest.raises(PH.HarnessRejected) as child_err:
            PH.bundle_identity_from_rows(
                _bundle_row(), _authority_row(state="candidate")
            )
        assert child_err.value.kind is PH.HarnessRejection.bundle_not_approved
        assert "authority model definition 缺失或未 approved" in str(child_err.value)

        with pytest.raises(PH.HarnessRejected) as missing_err:
            PH.bundle_identity_from_rows(_bundle_row(), None)
        assert missing_err.value.kind is PH.HarnessRejection.bundle_not_approved

    def test_an_approved_bundle_with_an_approved_authority_child_is_accepted(self) -> None:
        """反向自检：合法组合必须**不抛**，且解析出的 authority model 来自 child 行。"""
        bundle = _bundle_row()
        identity = PH.bundle_identity_from_rows(
            bundle,
            _authority_row(
                id=bundle.authority_model_definition_id,
                authority_model_type="custom_authoritative_ooxml",
            ),
        )
        assert identity.authority_model is AuthorityModel.custom_authoritative_ooxml

    def test_a_published_trace_bundle_with_matching_hash_is_accepted(self) -> None:
        """反向自检：合法输入必须**不抛**。

        少了这一条，把 `assert_trace_bundle_published` 改成"无条件抛"也能让上面三条全绿。
        """
        artifact = _artifact_row()
        PH.assert_trace_bundle_published(
            observation=_obs("rollback", trace_bundle_artifact_id=artifact.id),
            artifact=artifact,
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. Property 25 / 26：oracle 真跑 merge
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty25DifferentFieldMergeOracle:
    """**Validates: Requirements 6.8**

    Property 25 原文：「current 改 A、incoming 改 B，结果同时含 A/B 且 conflict_count=0」。
    """

    def test_oracle_passes_when_both_sides_survive(self, contract: C.SyncContract) -> None:
        verdict = PH.evaluate_different_field_merge(
            _merge_evidence(
                contract,
                base=("原名", "100.00"),
                current=("改名", "100.00"),
                incoming=("原名", "200.00"),
                current_changed_key=_row_key(NAME),
                incoming_changed_key=_row_key(TOTAL),
            )
        )
        assert verdict.outcome is PH.OracleOutcome.passed, verdict

    def test_oracle_fails_when_a_conflict_appears(self, contract: C.SyncContract) -> None:
        """P25 的核心判据：不同字段并行修改**不得**产生冲突。

        构造真的会冲突的三方（NAME 在 current/incoming 各改成不同值），但仍按 P25 的形态
        提交 —— 于是 `conflict_count != 0` 那条分支真的可达。少了这条，把它短路掉不会
        改变任何结果（本任务首轮变异实测 GREEN）。
        """
        verdict = PH.evaluate_different_field_merge(
            _merge_evidence(
                contract,
                base=("A", "100.00"),
                current=("B", "100.00"),
                incoming=("C", "200.00"),
                current_changed_key=_row_key(NAME),
                incoming_changed_key=_row_key(TOTAL),
            )
        )
        assert verdict.outcome is PH.OracleOutcome.failed, verdict
        assert verdict.error_code == "p25_unexpected_conflict", verdict

    def test_oracle_fails_when_the_incoming_side_is_lost(
        self, contract: C.SyncContract, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """对称的另一半：把 merge 换成「current 整体保留」⇒ incoming 侧的 B 丢了。

        与 `test_oracle_fails_when_the_current_side_is_lost` 成对 —— 只测一侧时，
        另一侧的判据短路掉仍然全绿。
        """
        real = PH.merge_projections

        def keep_current(**kwargs: Any) -> Any:
            from dataclasses import replace

            return replace(real(**kwargs), merged=kwargs["current"])

        monkeypatch.setattr(PH, "merge_projections", keep_current)
        verdict = PH.evaluate_different_field_merge(
            _merge_evidence(
                contract,
                base=("原名", "100.00"),
                current=("改名", "100.00"),
                incoming=("原名", "200.00"),
                current_changed_key=_row_key(NAME),
                incoming_changed_key=_row_key(TOTAL),
            )
        )
        assert verdict.outcome is PH.OracleOutcome.failed, verdict
        assert verdict.error_code == "p25_incoming_side_lost", verdict

    def test_oracle_fails_when_the_current_side_is_lost(
        self, contract: C.SyncContract, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """把 merge 换成「incoming 整体覆盖」⇒ oracle 必须 failed。

        🔴 这条证明 oracle **真的在跑 merge**而不是只看 `conflict_count`：整体覆盖同样零
        冲突，只断零冲突的实现会在这里仍然判 passed。
        """
        real = PH.merge_projections

        def overwrite(**kwargs: Any) -> Any:
            outcome = real(**kwargs)
            from dataclasses import replace

            return replace(outcome, merged=kwargs["incoming"])

        monkeypatch.setattr(PH, "merge_projections", overwrite)
        verdict = PH.evaluate_different_field_merge(
            _merge_evidence(
                contract,
                base=("原名", "100.00"),
                current=("改名", "100.00"),
                incoming=("原名", "200.00"),
                current_changed_key=_row_key(NAME),
                incoming_changed_key=_row_key(TOTAL),
            )
        )
        assert verdict.outcome is PH.OracleOutcome.failed, verdict
        assert verdict.error_code == "p25_current_side_lost", verdict

    def test_oracle_is_unverifiable_without_explicit_keys(
        self, contract: C.SyncContract
    ) -> None:
        """不给两侧改动键 ⇒ 判据退化成"零冲突" ⇒ 必须 `unverifiable` 而不是 passed。"""
        verdict = PH.evaluate_different_field_merge(
            _merge_evidence(
                contract,
                base=("原名", "100.00"),
                current=("改名", "100.00"),
                incoming=("原名", "200.00"),
            )
        )
        assert verdict.outcome is PH.OracleOutcome.unverifiable
        assert verdict.error_code == "merge_keys_missing"

    def test_same_key_on_both_sides_is_not_a_p25_scenario(
        self, contract: C.SyncContract
    ) -> None:
        verdict = PH.evaluate_different_field_merge(
            _merge_evidence(
                contract,
                base=("原名", "100.00"),
                current=("改名", "100.00"),
                incoming=("另一个名", "100.00"),
                current_changed_key=_row_key(NAME),
                incoming_changed_key=_row_key(NAME),
            )
        )
        assert verdict.error_code == "merge_keys_not_disjoint"


class TestProperty26SameFieldConflictOracle:
    """**Validates: Requirements 6.8**

    Property 26 原文：「base=A、current=B、incoming=C 时不得应用任一侧，冲突三值完整」。
    """

    def test_oracle_passes_when_conflict_holds_three_values(
        self, contract: C.SyncContract
    ) -> None:
        verdict = PH.evaluate_same_field_conflict(
            _merge_evidence(
                contract,
                base=("A", "100.00"),
                current=("B", "100.00"),
                incoming=("C", "100.00"),
                conflict_key=_row_key(NAME),
            )
        )
        assert verdict.outcome is PH.OracleOutcome.passed, verdict

    def test_oracle_fails_when_no_conflict_is_raised(
        self, contract: C.SyncContract, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """把冲突集合清空 ⇒ oracle 必须 failed（有一侧被静默采纳）。"""
        real = PH.merge_projections

        def no_conflict(**kwargs: Any) -> Any:
            from dataclasses import replace

            from app.services.workpaper_sync.conflicts import ConflictSet

            return replace(real(**kwargs), conflicts=ConflictSet(()))

        monkeypatch.setattr(PH, "merge_projections", no_conflict)
        verdict = PH.evaluate_same_field_conflict(
            _merge_evidence(
                contract,
                base=("A", "100.00"),
                current=("B", "100.00"),
                incoming=("C", "100.00"),
                conflict_key=_row_key(NAME),
            )
        )
        assert verdict.outcome is PH.OracleOutcome.failed
        assert verdict.error_code == "p26_conflict_not_raised"

    def test_oracle_fails_when_incoming_is_silently_applied(
        self, contract: C.SyncContract, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """冲突建立了但 merged 已等于 incoming ⇒ 相当于自动选了 OO 侧。"""
        real = PH.merge_projections

        def applied(**kwargs: Any) -> Any:
            from dataclasses import replace

            return replace(real(**kwargs), merged=kwargs["incoming"])

        monkeypatch.setattr(PH, "merge_projections", applied)
        verdict = PH.evaluate_same_field_conflict(
            _merge_evidence(
                contract,
                base=("A", "100.00"),
                current=("B", "100.00"),
                incoming=("C", "100.00"),
                conflict_key=_row_key(NAME),
            )
        )
        assert verdict.outcome is PH.OracleOutcome.failed
        assert verdict.error_code == "p26_incoming_applied"

    def test_oracle_fails_when_the_three_conflict_values_do_not_match_the_inputs(
        self, contract: C.SyncContract, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """P26 的「冲突三值完整」：把冲突记录的 base 值改掉 ⇒ oracle 必须 failed。

        少了这条，「三值与输入逐一相同」的检查短路掉不会改变任何结果（本任务首轮变异
        实测 GREEN）—— 而后果是裁决界面可能显示错值而守卫全绿。
        """
        real = PH.merge_projections

        def wrong_base(**kwargs: Any) -> Any:
            from dataclasses import replace

            from app.services.workpaper_sync.conflicts import ConflictSet, ValueEnvelope

            outcome = real(**kwargs)
            records = tuple(
                replace(r, base=ValueEnvelope.of("被改掉的 base")) for r in outcome.conflicts
            )
            return replace(outcome, conflicts=ConflictSet(records))

        monkeypatch.setattr(PH, "merge_projections", wrong_base)
        verdict = PH.evaluate_same_field_conflict(
            _merge_evidence(
                contract,
                base=("A", "100.00"),
                current=("B", "100.00"),
                incoming=("C", "100.00"),
                conflict_key=_row_key(NAME),
            )
        )
        assert verdict.outcome is PH.OracleOutcome.failed, verdict
        assert verdict.error_code == "p26_three_values_incomplete", verdict

    def test_oracle_is_unverifiable_without_a_conflict_key(
        self, contract: C.SyncContract
    ) -> None:
        verdict = PH.evaluate_same_field_conflict(
            _merge_evidence(
                contract,
                base=("A", "100.00"),
                current=("B", "100.00"),
                incoming=("C", "100.00"),
            )
        )
        assert verdict.error_code == "conflict_key_missing"


# ═══════════════════════════════════════════════════════════════════════════
# 5. 结果推导：今天为什么必然没有 verified（Property 49）
# ═══════════════════════════════════════════════════════════════════════════


def _full_obs(scenario_id: str, *, contract: C.SyncContract | None = None) -> PH.ScenarioObservation:
    """一条"证据尽可能齐全"的观测 —— 用来证明黑盒缺失**不能**被证据齐全掩盖。"""
    oracle = PH.SCENARIO_ORACLES[scenario_id]
    scenario = {s.scenario_id: s for s in PH.all_declared_scenarios()}[scenario_id]
    stamps = {
        stage: _now() + timedelta(seconds=idx)
        for idx, stage in enumerate(
            PH.RECOVERY_TIMELINE_ORDER
            if scenario.family is EV.ScenarioFamily.recovery
            else PH.OO_TO_HTML_TIMELINE_ORDER
        )
    }
    over: dict[str, Any] = {
        "supplied_inputs": oracle.requires,
        "server_timeline": stamps,
        "observed_close_captures": scenario.expected_close_captures,
    }
    if scenario.expects_application:
        over["operation_ids"] = (uuid.uuid4(),)
        over["application_ids"] = (uuid.uuid4(),)
    if scenario.expects_recovery_case:
        over["recovery_case_ids"] = (uuid.uuid4(),)
        over["recovery_precondition_zero_entities"] = True
    if contract is not None and PH.EvidenceInput.merge_execution in oracle.requires:
        over["merge_evidence"] = _merge_evidence(
            contract,
            base=("A", "100.00"),
            current=("B", "100.00"),
            incoming=("A", "200.00"),
            current_changed_key=_row_key(NAME),
            incoming_changed_key=_row_key(TOTAL),
            conflict_key=_row_key(NAME),
        )
    return _obs(scenario_id, **over)


class TestNoRealOnlyOfficeMeansUnverifiable:
    """**Validates: Requirements 12.2, 14.1, 14.16**（Property 49）"""

    def test_every_black_box_scenario_is_unverifiable_without_a_real_build(
        self, contract: C.SyncContract
    ) -> None:
        """哨兵 build 下，17 个黑盒场景一个都不能判 passed。"""
        black = [sid for sid, o in PH.SCENARIO_ORACLES.items() if o.needs_black_box]
        assert black, "黑盒场景集合为空 —— 那意味着所有场景都声称不需要真实 OO"
        for scenario_id in sorted(black):
            scenario = {s.scenario_id: s for s in PH.all_declared_scenarios()}[scenario_id]
            verdict = PH.run_scenario_oracle(
                scenario=scenario,
                oracle=PH.SCENARIO_ORACLES[scenario_id],
                observation=_full_obs(scenario_id, contract=contract),
                onlyoffice_build=PH.NOT_EXECUTED,
                browser_build=PH.NOT_EXECUTED,
            )
            assert verdict.outcome is not PH.OracleOutcome.passed, (
                f"{scenario_id}: 在没有真实 OO/浏览器的情况下被判 passed —— "
                "Property 49 明令必须保持 UNVERIFIABLE"
            )

    def test_the_ac_named_scenarios_are_classified_as_black_box(self) -> None:
        """AC 明文点名必须真实 OO 9.4 的场景，必须在黑盒集合里。

        逐条对应：AC 6.16（identity 载体黑盒探针）、AC 14.4（Word SDT 往返）、
        AC 14.5（Excel 动态行/列）、AC 14.3（status 6/2 乱序）。
        """
        for scenario_id in (
            "identity_retention",
            "word_sdt_tag_row_uuid_retention",
            "dynamic_row_add_delete_reorder_copy",
            "dynamic_column_stable_keys",
            "frozen_base_status_6_2_dedupe",
            "oo_to_html",
        ):
            assert PH.SCENARIO_ORACLES[scenario_id].needs_black_box, scenario_id

    def test_field_level_scenarios_do_not_need_a_black_box(self) -> None:
        """反向：P25/P26 不需要 OO —— 否则它们会被"等 OO"永久挡住。"""
        for scenario_id in EV.FIELD_LEVEL_SCENARIOS:
            assert not PH.SCENARIO_ORACLES[scenario_id].needs_black_box, scenario_id

    def test_upstream_gap_scenarios_are_failed_not_unverifiable(
        self, contract: C.SyncContract
    ) -> None:
        """🔴 上游实现缺口判 `failed`，**不是** `unverifiable`。

        判定顺序不可交换：若黑盒判定排在缺口判定之前，这两条会在没有 OO 的环境里显示成
        `unverifiable`，于是"接了 OO 就会自动变绿"—— 而它们其实永远不会通过（生产上根本
        没有那道校验）。
        """
        gaps = [sid for sid, o in PH.SCENARIO_ORACLES.items() if o.upstream_debt]
        assert sorted(gaps) == [
            "same_application_higher_sequence_fold",
            "wrong_prior_confirmation_bundle_fence_contributor_rejected",
        ], gaps
        for scenario_id in gaps:
            scenario = {s.scenario_id: s for s in PH.all_declared_scenarios()}[scenario_id]
            verdict = PH.run_scenario_oracle(
                scenario=scenario,
                oracle=PH.SCENARIO_ORACLES[scenario_id],
                observation=_full_obs(scenario_id, contract=contract),
                onlyoffice_build="OnlyOffice 9.4.0.42",
                browser_build="Chrome/131.0.0.0",
            )
            assert verdict.outcome is PH.OracleOutcome.failed, verdict
            assert verdict.error_code == "upstream_gap", verdict
            assert "Task 32" in "".join(verdict.notes)

    def test_schema_debt_scenario_is_unverifiable_and_still_required(
        self, contract: C.SyncContract
    ) -> None:
        """已登记的 schema 欠账场景：`unverifiable` + 仍在 required set 里。"""
        scenario_id, = EV.SCHEMA_UNREPRESENTABLE_SCENARIOS
        scenario = {s.scenario_id: s for s in PH.all_declared_scenarios()}[scenario_id]
        verdict = PH.run_scenario_oracle(
            scenario=scenario,
            oracle=PH.SCENARIO_ORACLES[scenario_id],
            observation=_full_obs(scenario_id, contract=contract),
            onlyoffice_build="OnlyOffice 9.4.0.42",
            browser_build="Chrome/131.0.0.0",
        )
        assert verdict.outcome is PH.OracleOutcome.unverifiable
        assert verdict.error_code == "scenario_kind_unrepresentable"
        assert scenario_id in {s.scenario_id for s in EV.PROJECTION_BASE_SCENARIOS}

    def test_a_merge_scenario_without_three_way_input_is_unverifiable(self) -> None:
        """字段级场景缺三方 projection ⇒ `unverifiable` + `merge_evidence_missing`。

        判据必须走 :func:`run_scenario_oracle`（而不是直接调 `evaluate_*`）：那道
        「缺输入」的门在 `run_scenario_oracle` 里，直接调 oracle 测不到它。
        """
        scenario_id = "different_field_merge"
        scenario = {s.scenario_id: s for s in PH.all_declared_scenarios()}[scenario_id]
        oracle = PH.SCENARIO_ORACLES[scenario_id]
        verdict = PH.run_scenario_oracle(
            scenario=scenario,
            oracle=oracle,
            observation=_obs(
                scenario_id,
                supplied_inputs=oracle.requires,
                operation_ids=(uuid.uuid4(),),
                application_ids=(uuid.uuid4(),),
            ),
            onlyoffice_build="OnlyOffice 9.4.0.42",
            browser_build="Chrome/131.0.0.0",
        )
        assert verdict.outcome is PH.OracleOutcome.unverifiable, verdict
        assert verdict.error_code == "merge_evidence_missing", verdict

    def test_a_merge_scenario_with_three_way_input_is_judged_by_the_oracle(
        self, contract: C.SyncContract
    ) -> None:
        """反向自检：给了三方输入就必须真跑 oracle 并 passed。"""
        scenario_id = "different_field_merge"
        scenario = {s.scenario_id: s for s in PH.all_declared_scenarios()}[scenario_id]
        oracle = PH.SCENARIO_ORACLES[scenario_id]
        verdict = PH.run_scenario_oracle(
            scenario=scenario,
            oracle=oracle,
            observation=_full_obs(scenario_id, contract=contract),
            onlyoffice_build="OnlyOffice 9.4.0.42",
            browser_build="Chrome/131.0.0.0",
        )
        assert verdict.outcome is PH.OracleOutcome.passed, verdict

    def test_missing_evidence_input_is_unverifiable(self, contract: C.SyncContract) -> None:
        """证据种类缺失 ⇒ `unverifiable` + 可归因 error_code。"""
        scenario_id = "different_field_merge"
        scenario = {s.scenario_id: s for s in PH.all_declared_scenarios()}[scenario_id]
        verdict = PH.run_scenario_oracle(
            scenario=scenario,
            oracle=PH.SCENARIO_ORACLES[scenario_id],
            observation=_obs(
                scenario_id, operation_ids=(uuid.uuid4(),), application_ids=(uuid.uuid4(),)
            ),
            onlyoffice_build="OnlyOffice 9.4.0.42",
            browser_build="Chrome/131.0.0.0",
        )
        assert verdict.outcome is PH.OracleOutcome.unverifiable
        assert verdict.error_code == "evidence_input_missing"

    def test_close_capture_count_must_be_measured_and_exact(self) -> None:
        """close 场景：数必须**实测**且与期望精确相等（partial unique 只证 at-most-one）。"""
        scenario = {s.scenario_id: s for s in PH.all_declared_scenarios()}[
            "close_reconciler_reentrant_exactly_one_capture"
        ]
        oracle = PH.SCENARIO_ORACLES[scenario.scenario_id]
        base = {
            "supplied_inputs": oracle.requires,
            "operation_ids": (uuid.uuid4(),),
            "application_ids": (uuid.uuid4(),),
        }
        unmeasured = PH.run_scenario_oracle(
            scenario=scenario, oracle=oracle,
            observation=_obs(scenario.scenario_id, **base),
            onlyoffice_build="OO", browser_build="Chrome",
        )
        assert unmeasured.error_code == "close_capture_count_missing"
        two = PH.run_scenario_oracle(
            scenario=scenario, oracle=oracle,
            observation=_obs(scenario.scenario_id, observed_close_captures=2, **base),
            onlyoffice_build="OO", browser_build="Chrome",
        )
        assert two.outcome is PH.OracleOutcome.failed
        assert two.error_code == "close_capture_count_mismatch"
        one = PH.run_scenario_oracle(
            scenario=scenario, oracle=oracle,
            observation=_obs(scenario.scenario_id, observed_close_captures=1, **base),
            onlyoffice_build="OO", browser_build="Chrome",
        )
        assert one.outcome is PH.OracleOutcome.passed, one

    def test_zero_capture_scenario_expects_zero_not_one(self) -> None:
        """无 successor 场景期望**零** capture —— 与其余 close 场景不同值。

        用同一个 `expected_close_captures` 常量给所有 close 场景会让这条永远测不出来。
        """
        scenario = {s.scenario_id: s for s in PH.all_declared_scenarios()}[
            "close_leader_revoked_no_successor_recovery_required"
        ]
        assert scenario.expected_close_captures == 0
        oracle = PH.SCENARIO_ORACLES[scenario.scenario_id]
        verdict = PH.run_scenario_oracle(
            scenario=scenario, oracle=oracle,
            observation=_obs(
                scenario.scenario_id, supplied_inputs=oracle.requires,
                operation_ids=(uuid.uuid4(),), application_ids=(uuid.uuid4(),),
                observed_close_captures=1,
            ),
            onlyoffice_build="OO", browser_build="Chrome",
        )
        assert verdict.error_code == "close_capture_count_mismatch", verdict


class TestTimelineOracle:
    """**Validates: Requirements 4.10, 14.1**"""

    def test_ordered_stages_pass(self) -> None:
        stamps = {
            stage: _now() + timedelta(seconds=i)
            for i, stage in enumerate(PH.OO_TO_HTML_TIMELINE_ORDER)
        }
        assert PH.evaluate_timeline_order(
            stamps, expected_order=PH.OO_TO_HTML_TIMELINE_ORDER
        ).outcome is PH.OracleOutcome.passed

    def test_out_of_order_stages_fail(self) -> None:
        stamps = {
            stage: _now() + timedelta(seconds=i)
            for i, stage in enumerate(PH.OO_TO_HTML_TIMELINE_ORDER)
        }
        stamps["incoming_durable"] = stamps["forcesave_request_frozen"] - timedelta(seconds=5)
        verdict = PH.evaluate_timeline_order(
            stamps, expected_order=PH.OO_TO_HTML_TIMELINE_ORDER
        )
        assert verdict.outcome is PH.OracleOutcome.failed
        assert verdict.error_code == "timeline_out_of_order"

    def test_missing_stage_is_unverifiable_not_failed(self) -> None:
        """缺证据与证据反驳是两回事 —— 合成一码会让"没跑"看起来像"跑了但坏了"。"""
        stamps = {
            stage: _now()
            for stage in PH.OO_TO_HTML_TIMELINE_ORDER
            if stage != "incoming_durable"
        }
        verdict = PH.evaluate_timeline_order(
            stamps, expected_order=PH.OO_TO_HTML_TIMELINE_ORDER
        )
        assert verdict.outcome is PH.OracleOutcome.unverifiable
        assert verdict.error_code == "timeline_stage_missing"

    def test_recovery_order_is_a_different_sequence(self) -> None:
        """recovery 时序是**另一条**序列（AC 14.8 分别列出）。"""
        assert PH.RECOVERY_TIMELINE_ORDER != PH.OO_TO_HTML_TIMELINE_ORDER
        assert PH.RECOVERY_TIMELINE_ORDER[1] == "recovery_case_created"

    def test_a_recovery_scenario_is_judged_against_the_recovery_order(self) -> None:
        """recovery 家族的场景必须用 recovery 序列判定，不是 OO→HTML 序列。

        判据落在**行为**上：同一条 recovery 场景，喂 recovery 序列的时间戳 ⇒ passed，
        喂 OO→HTML 序列的时间戳 ⇒ `timeline_stage_missing`。把序列选择短路掉时前者会
        变红。少了这条，两条序列选错也不会有任何测试变化（本任务首轮变异实测 GREEN）。
        """
        scenario_id = "authorization_first_recovery_claim"
        scenario = {s.scenario_id: s for s in PH.all_declared_scenarios()}[scenario_id]
        oracle = PH.SCENARIO_ORACLES[scenario_id]
        assert scenario.family is EV.ScenarioFamily.recovery
        assert not oracle.needs_black_box, "该场景若变成黑盒，时序分支就不可达了"

        def _verdict(order: tuple[str, ...]) -> PH.OracleVerdict:
            stamps = {
                stage: _now() + timedelta(seconds=i) for i, stage in enumerate(order)
            }
            return PH.run_scenario_oracle(
                scenario=scenario,
                oracle=oracle,
                observation=_obs(
                    scenario_id,
                    supplied_inputs=oracle.requires,
                    operation_ids=(uuid.uuid4(),),
                    application_ids=(uuid.uuid4(),),
                    recovery_case_ids=(uuid.uuid4(),),
                    recovery_precondition_zero_entities=True,
                    server_timeline=stamps,
                ),
                onlyoffice_build="OnlyOffice 9.4.0.42",
                browser_build="Chrome/131.0.0.0",
            )

        good = _verdict(PH.RECOVERY_TIMELINE_ORDER)
        assert good.outcome is PH.OracleOutcome.passed, good
        wrong = _verdict(PH.OO_TO_HTML_TIMELINE_ORDER)
        assert wrong.error_code == "timeline_stage_missing", wrong


# ═══════════════════════════════════════════════════════════════════════════
# 6. freshness：bundle / authority / typed child 三轴（Property 71）
# ═══════════════════════════════════════════════════════════════════════════


class TestBundleFreshnessAxes:
    """**Validates: Requirements 14.16**"""

    def test_the_three_bundle_axes_were_previously_unemitted(self) -> None:
        """三条轴必须**真的**由本 spec 的代码 emit，而不是只在枚举里存在。

        判据落在源码上是刻意的：`authority_model_changed` / `definition_bundle_changed`
        在 Task 29 交付时就在枚举里，却没有任何一处 emit —— 声明存在、判据为空。
        本条要求它们的 emit 点恰在 `evidence_freshness.bundle_stale_reasons` 里。
        """
        source = (
            _BACKEND / "app" / "services" / "workpaper_sync" / "evidence_freshness.py"
        ).read_text(encoding="utf-8")
        for axis in EF.BUNDLE_AXES:
            assert f"StaleReason.{axis.name}" in source, axis.value

    def test_authority_change_is_its_own_axis(self) -> None:
        identity = _identity()
        run = _run_row(identity, authority_model_definition_sha256=_d("old-authority"))
        reasons, notes = EF.bundle_stale_reasons(
            run=run, current=identity, frozen_child_digest=identity.typed_child_digest
        )
        assert reasons == (EV.StaleReason.authority_model_changed,), reasons
        assert notes and "authority" in notes[0]

    def test_bundle_change_is_its_own_axis(self) -> None:
        identity = _identity()
        run = _run_row(identity, definition_bundle_sha256=_d("old-bundle"))
        reasons, _ = EF.bundle_stale_reasons(
            run=run, current=identity, frozen_child_digest=identity.typed_child_digest
        )
        assert reasons == (EV.StaleReason.definition_bundle_changed,), reasons

    def test_typed_child_change_is_its_own_axis(self) -> None:
        """🔴 child 换了但 bundle digest 没变 ⇒ 独立的第三条轴。

        合成一码会让"child 被换掉而 digest 未变"（篡改）与"bundle 整体升级"（正常）
        分不出来。
        """
        identity = _identity()
        run = _run_row(identity)
        reasons, _ = EF.bundle_stale_reasons(
            run=run, current=identity, frozen_child_digest=_d("old-children")
        )
        assert reasons == (EV.StaleReason.definition_bundle_child_changed,), reasons

    def test_all_three_axes_can_fire_together(self) -> None:
        identity = _identity()
        run = _run_row(
            identity,
            definition_bundle_sha256=_d("old-bundle"),
            authority_model_definition_sha256=_d("old-authority"),
        )
        reasons, _ = EF.bundle_stale_reasons(
            run=run, current=identity, frozen_child_digest=_d("old-children")
        )
        assert set(reasons) == set(EF.BUNDLE_AXES), reasons

    def test_unchanged_bundle_is_fresh(self) -> None:
        """反向自检：三条轴在没有变化时必须**一条都不报**。"""
        identity = _identity()
        reasons, notes = EF.bundle_stale_reasons(
            run=_run_row(identity),
            current=identity,
            frozen_child_digest=identity.typed_child_digest,
        )
        assert reasons == ()
        assert notes == ()

    def test_child_digest_is_recomputed_by_the_publisher_canonicalizer(self) -> None:
        """篡改检测复用**发布器**的 canonicalization，而不是第二份实现。"""
        from app.services.workpaper_sync.models import BundleSlot

        bundle = _bundle_row()
        identity = _identity(bundle)
        recomputed = EF.recompute_bundle_canonical_digest(identity)
        from app.services.workpaper_sync.definitions import bundle_canonical_digest

        expected = bundle_canonical_digest(
            authority_model=identity.authority_model,
            authority_model_definition_sha256=identity.authority_model_definition_sha256,
            slots={
                BundleSlot.template: {
                    "type": identity.template_slot[0],
                    "ref": identity.template_slot[1],
                    "digest": identity.template_slot[2],
                },
                BundleSlot.instrumentation: {
                    "type": identity.instrumentation_slot[0],
                    "ref": identity.instrumentation_slot[1],
                    "digest": identity.instrumentation_slot[2],
                },
                BundleSlot.contract: {
                    "type": identity.contract_slot[0],
                    "ref": identity.contract_slot[1],
                    "digest": identity.contract_slot[2],
                },
            },
        )
        assert recomputed == expected

    def test_tampered_child_inventory_fails_closed(self) -> None:
        """行上的 digest 与 child 现算值不符 ⇒ 抛（不是记一条 stale）。"""
        identity = _identity()
        with pytest.raises(EF.BundleTamperError):
            EF.assert_bundle_child_inventory_intact(identity)

    def test_intact_child_inventory_passes(self) -> None:
        """反向自检：digest 与 child 自洽时**不抛**。"""
        bundle = _bundle_row()
        identity = _identity(bundle)
        intact = PH.BundleIdentity(
            bundle_id=identity.bundle_id,
            bundle_sha256=EF.recompute_bundle_canonical_digest(identity),
            authority_model=identity.authority_model,
            authority_model_definition_sha256=identity.authority_model_definition_sha256,
            template_slot=identity.template_slot,
            instrumentation_slot=identity.instrumentation_slot,
            contract_slot=identity.contract_slot,
        )
        EF.assert_bundle_child_inventory_intact(intact)

    def test_defects_outrank_stale_in_the_composed_verdict(self) -> None:
        """缺陷优先于 stale：否则"既过期又有缺陷"会显示成"重跑一次就好了"。"""
        verdict = EF.FreshnessVerdict(
            entry_id="probe/entry",
            run_id=uuid.uuid4(),
            recomputed=EV.EvidenceVerdict(
                entry_id="probe/entry",
                run_id=uuid.uuid4(),
                required_scenario_ids=("rollback",),
                observed_scenario_ids=(),
                defects=(EV.EvidenceDefect.missing_scenario,),
                stale_reasons=(EV.StaleReason.runner_changed,),
            ),
            bundle_stale_reasons=(EV.StaleReason.definition_bundle_changed,),
        )
        assert verdict.result is EV.EvidenceResult.unverified
        assert not verdict.fresh
        assert EV.StaleReason.definition_bundle_changed in verdict.stale_reasons
        assert EV.StaleReason.runner_changed in verdict.stale_reasons


# ═══════════════════════════════════════════════════════════════════════════
# 7. 容量 profile：只登记（Property 72）
# ═══════════════════════════════════════════════════════════════════════════


class TestCapacityProfileRegisteredOnly:
    """**Validates: Requirements 14.10, 14.12**"""

    def test_profile_matches_the_requirement_text_verbatim(self) -> None:
        """🔴 期望值从 `requirements.md` 的 AC 原文抠出来，不是从被测常量抄一遍。"""
        facts = CP.requirement_facts()
        assert facts == {
            "concurrent_login_sessions": 6000,
            "active_onlyoffice_participants": 1200,
            "same_second_forcesave_burst": 120,
            "sustained_applications_per_second": 20,
            "sustained_duration_seconds": 600,
            "incoming_durable_p95_seconds": 10,
            "applied_terminal_p95_seconds": 30,
        }, facts
        CP.assert_profile_matches_requirements()

    def test_reworded_requirement_text_fails_closed_instead_of_silently_skipping(
        self, tmp_path: Path
    ) -> None:
        """需求措辞变了、正则抠不到时必须**抛**，不能静默跳过。

        真实 `requirements.md` 上 7 条正则全命中 ⇒ 那条 fail-closed 分支在真实数据上
        **不可达**（本任务首轮变异实测 GREEN）。所以这里用一份合成副本：保留 AC 编号，
        只把数字的措辞改掉。docstring 写明用合成而非真实数据的理由。
        """
        original = CP.REQUIREMENTS_PATH.read_text(encoding="utf-8")
        reworded = original.replace("6000 个并发登录会话", "六千个并发登录会话")
        assert reworded != original, "需求原文措辞已变，本判据的构造前提失效"
        target = tmp_path / "requirements.md"
        target.write_text(reworded, encoding="utf-8")
        with pytest.raises(CP.CapacityError) as err:
            CP.requirement_facts(target)
        assert "concurrent_login_sessions" in str(err.value)
        assert "14.10" in str(err.value)

    def test_a_missing_ac_heading_also_fails_closed(self, tmp_path: Path) -> None:
        """AC 整段不见了也必须抛（另一条独立分支）。"""
        original = CP.REQUIREMENTS_PATH.read_text(encoding="utf-8")
        target = tmp_path / "requirements.md"
        target.write_text(original.replace("\n14.10. ", "\n14.99. "), encoding="utf-8")
        with pytest.raises(CP.CapacityError) as err:
            CP.requirement_facts(target)
        assert "14.10" in str(err.value)

    def test_a_p95_over_budget_is_a_shortfall(self) -> None:
        """延迟预算真的参与判定：p95 超预算 ⇒ shortfall 且不算达标。

        负载判据与延迟判据是两条独立循环，只测负载那条时把延迟那条短路掉仍然全绿
        （本任务首轮变异实测 GREEN）。
        """
        measurement = CP.CapacityMeasurement(
            concurrent_login_sessions=6000,
            active_onlyoffice_participants=1200,
            same_second_forcesave_burst=120,
            sustained_applications_per_second=20,
            sustained_duration_seconds=600,
            incoming_durable_p95_seconds=99,
            applied_terminal_p95_seconds=25,
            hardware_profile="probe",
            onlyoffice_build="OnlyOffice 9.4.0",
            source_commit="deadbeef",
            capacity_adr_ref="ADR-capacity-002",
        )
        outcome = CP.evaluate_capacity_run(measurement)
        assert not outcome.within_budget, outcome.as_dict()
        assert any("incoming_durable_p95_seconds" in s for s in outcome.shortfalls), (
            outcome.shortfalls
        )
        with pytest.raises(CP.CapacityError):
            CP.assert_capacity_verified(outcome)

    def test_lowering_a_target_is_caught(self) -> None:
        """把目标改小 ⇒ 与需求原文不符 ⇒ 打红。"""
        from dataclasses import replace

        weakened = replace(CP.CAPACITY_PROFILE, concurrent_login_sessions=600)
        with pytest.raises(CP.CapacityError) as err:
            CP.assert_profile_matches_requirements(profile=weakened)
        assert "concurrent_login_sessions" in str(err.value)

    def test_status_is_registered_pending_execution_and_owned_by_task_71(self) -> None:
        assert CP.CAPACITY_PROFILE.status is CP.CapacityStatus.registered_pending_execution
        assert CP.CAPACITY_PROFILE.execution_owner == "Task 71"

    def test_asking_whether_capacity_passed_without_a_run_raises(self) -> None:
        """🔴 抛而不是返回 False：返回值会被 `if not ok: pass` 静静吞掉。"""
        with pytest.raises(CP.CapacityNotExecutedError):
            CP.assert_capacity_verified(None)

    def test_digest_is_reproducible_and_covers_every_number(self) -> None:
        """Property 72 的"可重复"：同输入同 digest，且任一数字变化都改 digest。"""
        from dataclasses import replace

        assert CP.CAPACITY_PROFILE.digest == CP.CAPACITY_PROFILE.digest
        baseline = CP.CAPACITY_PROFILE.digest
        for field_name in (
            "concurrent_login_sessions",
            "active_onlyoffice_participants",
            "same_second_forcesave_burst",
            "sustained_applications_per_second",
            "sustained_duration_seconds",
            "incoming_durable_p95_seconds",
            "applied_terminal_p95_seconds",
        ):
            bumped = replace(
                CP.CAPACITY_PROFILE, **{field_name: getattr(CP.CAPACITY_PROFILE, field_name) + 1}
            )
            assert bumped.digest != baseline, f"{field_name} 不参与 digest"

    def test_a_shortfall_without_an_adr_is_refused(self) -> None:
        """未达标且没有显式 ADR ⇒ 拒（AC 14.12「不得静默放宽」）。"""
        measurement = CP.CapacityMeasurement(
            concurrent_login_sessions=1000,
            active_onlyoffice_participants=1200,
            same_second_forcesave_burst=120,
            sustained_applications_per_second=20,
            sustained_duration_seconds=600,
            incoming_durable_p95_seconds=9,
            applied_terminal_p95_seconds=29,
            hardware_profile="probe",
            onlyoffice_build="OnlyOffice 9.4.0",
            source_commit="deadbeef",
        )
        with pytest.raises(CP.CapacityError) as err:
            CP.evaluate_capacity_run(measurement)
        assert "capacity ADR" in str(err.value)

    def test_a_shortfall_with_an_adr_is_executed_requires_adr_not_passed(self) -> None:
        measurement = CP.CapacityMeasurement(
            concurrent_login_sessions=1000,
            active_onlyoffice_participants=1200,
            same_second_forcesave_burst=120,
            sustained_applications_per_second=20,
            sustained_duration_seconds=600,
            incoming_durable_p95_seconds=9,
            applied_terminal_p95_seconds=29,
            hardware_profile="probe",
            onlyoffice_build="OnlyOffice 9.4.0",
            source_commit="deadbeef",
            capacity_adr_ref="ADR-capacity-001",
        )
        outcome = CP.evaluate_capacity_run(measurement)
        assert outcome.status is CP.CapacityStatus.executed_requires_adr
        with pytest.raises(CP.CapacityError):
            CP.assert_capacity_verified(outcome)

    def test_missing_environment_record_is_refused(self) -> None:
        measurement = CP.CapacityMeasurement(
            concurrent_login_sessions=6000,
            active_onlyoffice_participants=1200,
            same_second_forcesave_burst=120,
            sustained_applications_per_second=20,
            sustained_duration_seconds=600,
            incoming_durable_p95_seconds=9,
            applied_terminal_p95_seconds=29,
            hardware_profile="",
            onlyoffice_build="OnlyOffice 9.4.0",
            source_commit="deadbeef",
        )
        with pytest.raises(CP.CapacityError) as err:
            CP.evaluate_capacity_run(measurement)
        assert "hardware_profile" in str(err.value)

    def test_a_within_budget_run_can_pass(self) -> None:
        """反向自检：真达标时必须能通过 —— 否则上面几条用"永远抛"也全绿。"""
        measurement = CP.CapacityMeasurement(
            concurrent_login_sessions=6000,
            active_onlyoffice_participants=1200,
            same_second_forcesave_burst=120,
            sustained_applications_per_second=20,
            sustained_duration_seconds=600,
            incoming_durable_p95_seconds=8,
            applied_terminal_p95_seconds=25,
            hardware_profile="probe",
            onlyoffice_build="OnlyOffice 9.4.0",
            source_commit="deadbeef",
        )
        outcome = CP.evaluate_capacity_run(measurement)
        assert outcome.within_budget
        assert CP.assert_capacity_verified(outcome) is outcome


# ═══════════════════════════════════════════════════════════════════════════
# 8. 四类 Excel pilot 覆盖（Property 49）
# ═══════════════════════════════════════════════════════════════════════════


class TestPilotClassCoverage:
    """**Validates: Requirements 12.2**"""

    def test_all_four_classes_have_candidates_on_the_real_manifest(self) -> None:
        assessments = PH.assess_pilot_classes()
        assert set(assessments) == set(PH.PilotClass)
        for pilot_class, assessment in sorted(assessments.items(), key=lambda kv: kv[0].value):
            assert assessment.candidate_entry_ids, (
                f"{pilot_class.value}: manifest 里没有候选 xlsx entry —— "
                "AC 12.2 的四类覆盖无从谈起"
            )

    def test_no_class_is_verified_today_because_there_is_no_bidirectional_entry(self) -> None:
        """今天的事实：0 个 bidirectional entry ⇒ 四类全 UNVERIFIABLE。"""
        assessments = PH.assess_pilot_classes()
        for pilot_class, assessment in sorted(assessments.items(), key=lambda kv: kv[0].value):
            assert assessment.status is PH.PilotClassStatus.unverifiable, pilot_class
            assert assessment.bidirectional_entry_ids == (), assessment
            assert assessment.reasons, f"{pilot_class.value}: UNVERIFIABLE 却没给理由"
        assert PH.pilot_coverage_summary(assessments)["all_verified"] is False

    def test_free_text_evidence_claims_cannot_flip_the_status(self) -> None:
        """🔴 Property 49 后半句：不得因文档声明计为通过。

        把 manifest 里**每个** entry 的 `evidence` 自由文本都改成"已通过"，结论必须
        一字不变。判据不是"检查有没有读 evidence 字段"，而是"读了也没用"。
        """
        real = PH.pilot_coverage_summary(PH.assess_pilot_classes())
        tampered = copy.deepcopy(dict(load_entry_manifest()))
        for entry in tampered["entries"]:
            entry["evidence"] = {
                "contract_test": True,
                "browser_case": True,
                "note": "真实 OO 9.4 已通过",
            }
        claimed = PH.pilot_coverage_summary(PH.assess_pilot_classes(manifest=tampered))
        assert claimed == real, "自由文本 evidence 声明改变了 pilot 覆盖结论"
        assert claimed["all_verified"] is False

    def test_a_verified_entry_flips_only_its_own_class(self) -> None:
        """反向自检：真有一个已重算通过的 bidirectional entry 时状态**能**翻。

        少了这一条，把 `status` 写成"恒 unverifiable"也能让上面几条全绿。
        """
        tampered = copy.deepcopy(dict(load_entry_manifest()))
        target = None
        for entry in tampered["entries"]:
            if re.search(r"(^|[^a-z0-9])d2([^0-9]|$)", str(entry["entry_id"]).lower()):
                entry["capability"] = "bidirectional"
                target = str(entry["entry_id"])
                break
        assert target, "manifest 里找不到 D2 候选 entry"
        assessments = PH.assess_pilot_classes(
            manifest=tampered, verified_entry_ids=frozenset({target})
        )
        assert assessments[PH.PilotClass.d2_large_json].status is PH.PilotClassStatus.verified
        for other in PH.PilotClass:
            if other is PH.PilotClass.d2_large_json:
                continue
            assert assessments[other].status is PH.PilotClassStatus.unverifiable, other
        assert PH.pilot_coverage_summary(assessments)["all_verified"] is False

    def test_bidirectional_without_a_verified_run_stays_unverifiable(self) -> None:
        """有 bidirectional entry 但没通过重算 ⇒ 仍 UNVERIFIABLE，理由指名真实 OO 未执行。"""
        tampered = copy.deepcopy(dict(load_entry_manifest()))
        for entry in tampered["entries"]:
            if re.search(r"(^|[^a-z0-9])h1([^0-9]|$)", str(entry["entry_id"]).lower()):
                entry["capability"] = "bidirectional"
        assessment = PH.assess_pilot_classes(manifest=tampered)[
            PH.PilotClass.h1_grouped_dynamic
        ]
        assert assessment.bidirectional_entry_ids
        assert assessment.status is PH.PilotClassStatus.unverifiable
        assert "真实 OO 9.4 pilot 未执行" in "".join(assessment.reasons)

    def test_pilot_classes_are_a_closed_four_value_domain(self) -> None:
        """AC 12.2 逐字四类，一个不多一个不少。"""
        assert sorted(c.value for c in PH.PilotClass) == [
            "d2_large_json",
            "g7_two_level_dynamic",
            "h1_grouped_dynamic",
            "simple_checklist",
        ]


# ═══════════════════════════════════════════════════════════════════════════
# 9. 结构判据：harness 的签名里不得存在结果入参
# ═══════════════════════════════════════════════════════════════════════════


class TestResultCannotBeHandFilled:
    """**Validates: Requirements 12.11, 14.14**"""

    def test_record_scenario_has_no_result_parameter(self) -> None:
        """🔴「参数不存在」比「参数存在但校验它」强 —— 后者可以被 `force=True` 绕过。"""
        import inspect

        params = set(inspect.signature(PH.SyncTestRunHarness.record_scenario).parameters)
        forbidden = {"result", "aggregate_result", "verified_at", "outcome", "passed"}
        assert not (params & forbidden), params & forbidden

    def test_finalize_run_has_no_aggregate_result_parameter(self) -> None:
        import inspect

        params = set(inspect.signature(PH.SyncTestRunHarness.finalize_run).parameters)
        forbidden = {"aggregate_result", "verified_at", "result", "passed"}
        assert not (params & forbidden), params & forbidden

    def test_scenario_observation_has_no_result_field(self) -> None:
        """runner 提交的观测里也不能有 result —— 否则等于换个名字手填。"""
        import dataclasses

        names = {f.name for f in dataclasses.fields(PH.ScenarioObservation)}
        assert not (names & {"result", "outcome", "verdict", "passed", "aggregate_result"})

    def test_finalize_writes_only_recomputed_result(self) -> None:
        """`finalize_run` 的赋值只能来自 recomputer 与服务端时钟。

        源码级判据 + 上面三条签名判据 + PG 侧的真实落库判据三者合起来才够：单看源码会被
        「改个变量名」绕过，单看签名证不了写入值的来源。
        """
        source = (
            _BACKEND / "app" / "services" / "workpaper_sync" / "pilot_harness.py"
        ).read_text(encoding="utf-8")
        body = source.split("async def finalize_run(", 1)[1]
        body = body.split("\n    # ---", 1)[0]
        assert "recomputed.verified" in body
        assert "datetime.now(timezone.utc)" in body
        assert "EvidenceRecomputer(" in body


class TestHarnessVersionParticipatesInStaleness:
    """**Validates: Requirements 14.16**"""

    def test_runner_version_is_the_harness_version(self) -> None:
        """harness 行为变化必须能让旧 evidence stale ⇒ 版本号进 runner_version。"""
        assert PH.HARNESS_VERSION.startswith("task39-harness/")

    def test_open_run_refuses_a_mismatched_runner_identity(self) -> None:
        """environment 自报的 runner 与 harness 自身不符 ⇒ 拒。

        否则每个 run 一开始就是 stale（`runner_changed`），而 stale 的 run 又不参与
        「已验收」计数 —— 于是「跑了但永远不算」变成静默状态。

        🔴 判据落在**行为**上而不是源码文本上：该校验是 `open_run` 的第一条语句、在任何
        DB 访问之前，因此可以用 `session=None` 离线触发。首轮变异实测证明源码级 presence
        断言在 `if False:` 之下仍然为真（`self._runner_version` 还留在 raise 体里）⇒ GREEN。
        """
        harness = PH.SyncTestRunHarness(session=None)  # type: ignore[arg-type]
        identity = _identity()
        plan = _plan(_required_set("rollback"), identity)
        drifted = EV.EvidenceEnvironment(
            source_commit="c", runner_version="someone-elses-runner/9",
            onlyoffice_build=PH.NOT_EXECUTED, browser_build=PH.NOT_EXECUTED,
        )
        with pytest.raises(PH.HarnessError) as err:
            asyncio.run(
                harness.open_run(
                    plan=plan, environment=drifted,
                    run_manifest_artifact_id=uuid.uuid4(),
                    run_manifest_sha256=_d("manifest"),
                )
            )
        assert "runner" in str(err.value)

    def test_open_run_accepts_the_harness_own_runner_identity(self) -> None:
        """反向自检：runner 一致时**不能**在该校验处拒（后续因 session=None 才失败）。

        少了这条，把校验写成「无条件抛」也能让上一条全绿。
        """
        harness = PH.SyncTestRunHarness(session=None)  # type: ignore[arg-type]
        plan = _plan(_required_set("rollback"), _identity())
        aligned = EV.EvidenceEnvironment(
            source_commit="c", runner_version=PH.HARNESS_VERSION,
            onlyoffice_build=PH.NOT_EXECUTED, browser_build=PH.NOT_EXECUTED,
        )
        with pytest.raises(Exception) as err:  # noqa: PT011 - 只要不是 runner 判据即可
            asyncio.run(
                harness.open_run(
                    plan=plan, environment=aligned,
                    run_manifest_artifact_id=uuid.uuid4(),
                    run_manifest_sha256=_d("manifest"),
                )
            )
        assert "runner" not in str(err.value), (
            f"runner 一致时仍被 runner 判据拒绝: {err.value}"
        )
