# -*- coding: utf-8 -*-
"""Task 59 守卫：Word definition/instrumentation candidate upgrader 与 tagged-SDT engine。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 5 Task 59
Requirements: 2.3, 6.10, 6.18, 7.1, 7.2, 7.3, 7.4, 7.5, 7.8, 7.9, 7.10, 8.10, 8.11,
9.1, 9.8, 9.9, 9.10, 14.16
Properties: **P28** / **P30** / **P31** / **P32** / **P34** / **P65** / **P67** / **P71**

═══ 为什么 fixture 必须是**真实权威模板** ═══

手搓的最小 DOCX 上「SDT 外自由正文」是空集、「受保护部件」是空 dict、「表格」是空
list ⇒ 一切「保留」判据 `equivalent=True` 恒真（假绿第⑥源「空集恒等价」）。所以本文件
的 fixture 是 `backend/wp_templates/` 里 Task 6 探针真正跑过的两份权威模板：

* `F2-22 存货监盘计划.docx` —— field 载体（含跨 run、同段多 token、同 key 多实例、
  block 嵌 inline 的 depth=2 层级）；实测 17 个部件 / 31 块自由正文 / 5 个受保护部件。
* `B30-11-2 内部控制缺陷汇总与评估.docx` —— 行身份载体（1 张表 4 行 ×10 列，三个数据
  行**全空**故只能用一次性结构坐标注入）；实测 18 个部件 / 22 块自由正文 / 5 个受保护
  部件 / 2 种字体。

:class:`TestCoverageIsNotEmpty` 把「各 aspect 覆盖计数全部 > 0」当**硬判据**，
于是有人把 fixture 换成手搓文档时会立刻打红。

模板本体**只读**：:data:`F222_SHA` / :data:`B30112_SHA` 是哨兵常量，
:class:`TestAuthorityTemplatesAreReadOnly` 在跑完后逐字节复核。
"""

from __future__ import annotations

import ast
import copy
import hashlib
import io
import json
import re
import sys
import tempfile
import zipfile
from datetime import date
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))

from app.services.word_sdt_fingerprint import structure_fingerprint  # noqa: E402
from app.services.workpaper_sync import contracts as C  # noqa: E402
from app.services.workpaper_sync import word_instrumentation as WI  # noqa: E402
from app.services.workpaper_sync import word_sdt_engine as WE  # noqa: E402
from app.services.workpaper_sync.adapters.base import (  # noqa: E402
    FieldValue,
    Projection,
    SubstrateRole,
)
from app.services.workpaper_sync.conflicts import ConflictKind  # noqa: E402
from app.services.workpaper_sync.models import (  # noqa: E402
    ArtifactKind,
    ArtifactState,
    IncomingNotDurableError,
    QuarantinedIncomingError,
)

# ═══════════════════════════════════════════════════════════════════════════
# fixture 常量（权威模板哨兵）
# ═══════════════════════════════════════════════════════════════════════════

TEMPLATES = _BACKEND / "wp_templates"
F222 = TEMPLATES / "F" / "F2-22 存货监盘计划.docx"
B30112 = TEMPLATES / "B" / "B30-11-2 内部控制缺陷汇总与评估.docx"

#: Task 6 契约里登记的权威 digest。跑完必须一字不差（Requirement 9.9：权威模板只读）。
F222_SHA = "f19aa64a9daa01022231d91f43d342a4ae973088dbd42b58459ad65c206662ba"
B30112_SHA = "b4facd6b7d31b1419eb102ede582e7e77b1a5c685a3f9513bb546b9de0bbb247"

PLAN_ID = "f2.stocktake.plan"
DEF_ID = "b30.11.2.deficiencies"

ROW_UUIDS = (
    "36cd5ee6-a95a-4101-a45c-8289857322a7",
    "86f54ae5-f4d8-4f31-ae95-b9e60e656a50",
    "bd7e5233-6d56-4c5a-addc-07d0a4024dfe",
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(seed: str) -> str:
    return _sha(seed.encode("utf-8"))


# ═══════════════════════════════════════════════════════════════════════════
# fixture：spec / contract / binding / 注入产物
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def gate() -> WI.WordSdtCarrierGate:
    return WI.WordSdtCarrierGate.load()


def plan_spec() -> WI.WordInstrumentationSpec:
    """F2-22 的注入声明。四个 token 覆盖 Requirement 7.5 的三种硬场景。"""
    return WI.WordInstrumentationSpec(
        entry_id=PLAN_ID,
        contract_id=PLAN_ID,
        template_id="F2-22",
        template_relative_path="F/F2-22 存货监盘计划.docx",
        fields=(
            # single run
            WI.WordFieldInjection(
                token="${purpose}", stable_field_key="plan/purpose", alias="监盘目的"
            ),
            # 同段多 token 之一 + 同 stable key 多实例（p04 与 p01 各一处）
            WI.WordFieldInjection(
                token="${entityName}",
                stable_field_key="plan/entity_name",
                expected_token_occurrences=2,
            ),
            WI.WordFieldInjection(token="${scope}", stable_field_key="plan/scope"),
            # 同段多 token 的另一个（与 `${entityName}` 同在 p04）+ **非 text** 值类型
            WI.WordFieldInjection(token="${bsDate}", stable_field_key="plan/bs_date"),
            # block 嵌 inline ⇒ depth=2 层级
            WI.WordFieldInjection(
                token="${warehouses}",
                stable_field_key="plan/warehouses",
                carrier="field_sdt_block",
                alias="监盘地点",
            ),
        ),
    )


def deficiency_spec() -> WI.WordInstrumentationSpec:
    """B30-11-2 的注入声明：literal 标题 + 三个空单元格的一次性结构坐标行注入。"""
    return WI.WordInstrumentationSpec(
        entry_id=DEF_ID,
        contract_id=DEF_ID,
        template_id="B30-11-2",
        template_relative_path="B/B30-11-2 内部控制缺陷汇总与评估.docx",
        fields=(
            WI.WordFieldInjection(
                token="内部控制缺陷汇总与评估",
                stable_field_key="deficiencies/title",
                literal_anchor=True,
                expected_token_occurrences=2,
            ),
        ),
        rows=tuple(
            WI.WordRowInjection(
                row_field_key_template="rows/{row_uuid}/deficiency",
                row_uuid=u,
                table_index=0,
                row_index=idx + 1,
                cell_index=1,
            )
            for idx, u in enumerate(ROW_UUIDS)
        ),
    )


def plan_contract_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "contract-definition:v1",
        "contract_id": PLAN_ID,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "docx",
        "template": {
            "relative_path": "F/F2-22 存货监盘计划.docx",
            "template_sha256": F222_SHA,
            "normalized_structure_hash": _digest("f222-structure"),
        },
        "template_definition_sha256": _digest("f222-template-def"),
        "instrumentation_definition_sha256": _digest("f222-instr-def"),
        "identity_carriers": ["field_sdt_inline", "field_sdt_block"],
        "fields": [
            {
                "stable_field_key": "plan/purpose",
                "json_pointer": "/plan/purpose",
                "mode": "editable",
                "value_type": "text",
                "source_ref": "F2-22!p06:${purpose}",
                "sdt_tag": f"gt:field:{PLAN_ID}:plan/purpose",
            },
            {
                "stable_field_key": "plan/scope",
                "json_pointer": "/plan/scope",
                "mode": "editable",
                "value_type": "text",
                "source_ref": "F2-22!p08:${scope}",
                "sdt_tag": f"gt:field:{PLAN_ID}:plan/scope",
            },
            {
                "stable_field_key": "plan/entity_name",
                "json_pointer": "/plan/entity_name",
                "mode": "editable",
                "value_type": "text",
                "source_ref": "F2-22!p04:${entityName}",
                "sdt_tag": f"gt:field:{PLAN_ID}:plan/entity_name",
                "instances": "many",
            },
            {
                "stable_field_key": "plan/bs_date",
                "json_pointer": "/plan/bs_date",
                "mode": "editable",
                # 🔴 **非 text** 值类型：`_canonical` 的类型化分支必须被真实覆盖，
                #    否则「类型化等值」这条判据只在文本上被测过（M19 变异实测 GREEN）。
                "value_type": "date",
                "source_ref": "F2-22!p04:${bsDate}",
                "sdt_tag": f"gt:field:{PLAN_ID}:plan/bs_date",
            },
            {
                "stable_field_key": "plan/warehouses",
                "json_pointer": "/plan/warehouses",
                "mode": "editable",
                "value_type": "text",
                "source_ref": "F2-22!p10:${warehouses}",
                "sdt_tag": f"gt:block:{PLAN_ID}:plan/warehouses",
            },
        ],
    }
    payload.update(overrides)
    return payload


def deficiency_contract_payload() -> dict[str, Any]:
    return {
        "schema_version": "contract-definition:v1",
        "contract_id": DEF_ID,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "docx",
        "template": {
            "relative_path": "B/B30-11-2 内部控制缺陷汇总与评估.docx",
            "template_sha256": B30112_SHA,
            "normalized_structure_hash": _digest("b30112-structure"),
        },
        "template_definition_sha256": _digest("b30112-template-def"),
        "instrumentation_definition_sha256": _digest("b30112-instr-def"),
        "identity_carriers": ["cell_level_field_sdt_tag_carrying_row_uuid"],
        "fields": [
            {
                "stable_field_key": "deficiencies/title",
                "json_pointer": "/deficiencies/title",
                "mode": "word_only",
                "value_type": "text",
                "source_ref": "B30-11-2!p01",
                "sdt_tag": f"gt:field:{DEF_ID}:deficiencies/title",
                "instances": "many",
            }
        ],
        "repeaters": [
            {
                "stable_field_key": "rows/{row_uuid}/deficiency",
                "json_pointer": "/rows/{row_uuid}/deficiency",
                "mode": "editable",
                "value_type": "text",
                "source_ref": "B30-11-2!tbl1.col2",
                "sdt_tag": f"gt:field:{DEF_ID}:rows/{{row_uuid}}/deficiency",
            }
        ],
    }


def binding_for(payload: dict[str, Any], *, entry_id: str) -> WE.WordEngineBinding:
    contract = C.parse_contract(payload, adapter_id=payload["contract_id"])
    return WE.WordEngineBinding(
        contract=contract,
        entry_id=entry_id,
        mode=WE.WordEngineMode.offline_candidate_validation,
    )


@pytest.fixture(scope="module")
def plan_instrumented(gate: WI.WordSdtCarrierGate) -> WI.InstrumentedDocx:
    return WI.instrument_docx_bytes(F222.read_bytes(), plan_spec(), gate=gate)


@pytest.fixture(scope="module")
def deficiency_instrumented(gate: WI.WordSdtCarrierGate) -> WI.InstrumentedDocx:
    return WI.instrument_docx_bytes(B30112.read_bytes(), deficiency_spec(), gate=gate)


@pytest.fixture(scope="module")
def plan_binding() -> WE.WordEngineBinding:
    return binding_for(plan_contract_payload(), entry_id=PLAN_ID)


@pytest.fixture(scope="module")
def deficiency_binding() -> WE.WordEngineBinding:
    return binding_for(deficiency_contract_payload(), entry_id=DEF_ID)


@pytest.fixture(scope="module")
def workdir() -> Any:
    with tempfile.TemporaryDirectory(prefix="tmp_task59_guard_") as tmp:
        yield Path(tmp)


@pytest.fixture(scope="module")
def plan_substrate(workdir: Path, plan_instrumented: WI.InstrumentedDocx) -> Path:
    target = workdir / "plan.substrate.docx"
    target.write_bytes(plan_instrumented.instrumented_bytes)
    return target


@pytest.fixture(scope="module")
def deficiency_substrate(
    workdir: Path, deficiency_instrumented: WI.InstrumentedDocx
) -> Path:
    target = workdir / "deficiency.substrate.docx"
    target.write_bytes(deficiency_instrumented.instrumented_bytes)
    return target


def _extract(artifact: Path, binding: WE.WordEngineBinding) -> WE.WordExtractOutcome:
    return WE.extract_word_projection(
        artifact=artifact,
        binding=binding,
        substrate_role=SubstrateRole.staged_result,
        artifact_kind=ArtifactKind.canonical,
        artifact_state=ArtifactState.staged,
    )


#: 契约里每个 stable key 的值类型（守卫构造 projection 时按它分派，不写死 text）。
_PLAN_VALUE_TYPES: dict[str, C.ValueType] = {
    "plan/purpose": C.ValueType.text,
    "plan/scope": C.ValueType.text,
    "plan/entity_name": C.ValueType.text,
    "plan/bs_date": C.ValueType.date,
    "plan/warehouses": C.ValueType.text,
}

_PLAN_DEFAULTS: dict[str, Any] = {
    "plan/purpose": "验证存货存在性、所有权与品质状况",
    "plan/scope": "全部仓库及在途存货",
    "plan/entity_name": "甲公司",
    "plan/bs_date": date(2026, 12, 31),
    "plan/warehouses": "A 库\nB 库",
}


def _text_projection(contract_id: str, values: dict[str, Any]) -> Projection:
    return Projection(
        contract_id=contract_id,
        semantic_version="1.0.0",
        document_type="docx",
        values={
            key: FieldValue(
                stable_key=key,
                value=value,
                value_type=_PLAN_VALUE_TYPES.get(key, C.ValueType.text),
                mode=C.FieldMode.editable,
                row_key=(key.split("/")[1] if key.startswith("rows/") else None),
            )
            for key, value in values.items()
        },
    )


def _plan_projection(**overrides: Any) -> Projection:
    """F2-22 的完整 projection（五个受管字段全给值），可逐字段覆写。

    「全给值」是必需的：漏一个字段会让 materialize 跳过它，反读时那个字段还留着
    substrate 的旧值 ⇒ 等值门的判据被削弱成「只比写过的字段」。
    """
    values = dict(_PLAN_DEFAULTS)
    values.update({key.replace("__", "/"): val for key, val in overrides.items()})
    return _text_projection(PLAN_ID, values)


def _rewrite_document(data: bytes, mutate: Any) -> bytes:
    """在 DOCX 上改写 `word/document.xml`（其余部件逐字节复制）—— 只给守卫造反例用。"""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        infos = zf.infolist()
        parts = {i.filename: zf.read(i) for i in infos}
        order = [(i.filename, i.compress_type) for i in infos]
    parts[WE.WORD_DOCUMENT_PART] = mutate(
        parts[WE.WORD_DOCUMENT_PART].decode("utf-8")
    ).encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as out:
        for name, compress in order:
            out.writestr(zipfile.ZipInfo(name), parts[name], compress_type=compress)
    return buffer.getvalue()


# ═══════════════════════════════════════════════════════════════════════════
# Property 71：载体裁决与 evidence 的 stale 门
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty71ProbeGateFreshness:
    """OO build / source commit / runner / probe 模板 / evidence 任一漂移即失效。"""

    def test_tier_a_and_tier_b_are_enforced_against_real_files(
        self, gate: WI.WordSdtCarrierGate
    ) -> None:
        assert gate.onlyoffice_build == "9.4.0-129"
        assert gate.lock_policy == WI.REQUIRED_PROBE_LOCK_POLICY == "no_w_lock_injected"
        # 反面：policy 一变就必须打红（判据在 `load()` 内部结构不可达，M31 首轮 GREEN）
        WI.assert_probe_lock_policy(gate.lock_policy)
        for wrong in ("", "w_lock_injected", "sdtLocked"):
            with pytest.raises(WI.WordCarrierGateError):
                WI.assert_probe_lock_policy(wrong)
        assert set(gate.probed_template_digests) == {"F2-22", "F2-23", "B30-11-2"}
        assert gate.probed_template_digests["F2-22"] == F222_SHA
        assert gate.probed_template_digests["B30-11-2"] == B30112_SHA
        roles = gate.assert_evidence_fresh()
        # evidence 必须真的有内容（空 dict 会让「evidence 新鲜」恒真）
        assert set(roles) >= {"probe_script", "operation_matrix", "instrumentation_report"}
        assert all(len(v) == 64 for v in roles.values())

    @pytest.mark.parametrize(
        "mutate_key",
        ["onlyoffice_build", "source_commit", "runner"],
    )
    def test_environment_drift_is_stale(self, tmp_path: Path, mutate_key: str) -> None:
        baseline = json.loads(WI.WORD_GATE_BASELINE_PATH.read_text(encoding="utf-8"))
        baseline["tier_a_runtime"][mutate_key] = "drifted"
        path = tmp_path / "gate.json"
        path.write_text(json.dumps(baseline), encoding="utf-8")
        with pytest.raises(WI.WordProbeEvidenceStaleError):
            WI.WordSdtCarrierGate.load(baseline_path=path)

    def test_probe_template_digest_drift_is_stale(self, tmp_path: Path) -> None:
        baseline = json.loads(WI.WORD_GATE_BASELINE_PATH.read_text(encoding="utf-8"))
        baseline["tier_a_runtime"]["probed_templates"][0]["sha256"] = "0" * 63 + "1"
        path = tmp_path / "gate.json"
        path.write_text(json.dumps(baseline), encoding="utf-8")
        with pytest.raises(WI.WordProbeEvidenceStaleError):
            WI.WordSdtCarrierGate.load(baseline_path=path)

    def test_carrier_contract_digest_drift_is_stale(self, tmp_path: Path) -> None:
        baseline = json.loads(WI.WORD_GATE_BASELINE_PATH.read_text(encoding="utf-8"))
        for item in baseline["tier_a_runtime"]["files"]:
            if item["role"] == "carrier_contract":
                item["sha256"] = "0" * 63 + "2"
        path = tmp_path / "gate.json"
        path.write_text(json.dumps(baseline), encoding="utf-8")
        with pytest.raises(WI.WordProbeEvidenceStaleError):
            WI.WordSdtCarrierGate.load(baseline_path=path)

    def test_missing_evidence_is_stale_not_skipped(self, tmp_path: Path) -> None:
        """evidence 文件缺失本身即判 stale —— 不得降级成 skip。"""
        baseline = json.loads(WI.WORD_GATE_BASELINE_PATH.read_text(encoding="utf-8"))
        baseline["tier_b_evidence"]["files"].append(
            {"role": "ghost", "path": "does/not/exist.json", "sha256": "0" * 64}
        )
        path = tmp_path / "gate.json"
        path.write_text(json.dumps(baseline), encoding="utf-8")
        loaded = WI.WordSdtCarrierGate.load()
        with pytest.raises(WI.WordProbeEvidenceStaleError):
            loaded.assert_evidence_fresh(baseline_path=path)

    def test_row_sdt_carrier_is_blocked_and_field_carriers_allowed(
        self, gate: WI.WordSdtCarrierGate
    ) -> None:
        """`row_sdt` 在 OO 9.4 上 failed ⇒ 任何声明它的契约/注入都必须被拒。"""
        assert "row_sdt" in gate.carrier_gate.blocked_carriers
        with pytest.raises(WI.WordCarrierGateError):
            gate.assert_carrier_allowed("row_sdt")
        for allowed in (
            "field_sdt_inline",
            "field_sdt_block",
            "cell_level_field_sdt_tag_carrying_row_uuid",
        ):
            gate.assert_carrier_allowed(allowed)

    @pytest.mark.parametrize(
        "anchor", ["paragraph_index", "run_index", "sdt_id", "alias_display_name"]
    )
    def test_pseudo_anchors_are_blocked(
        self, gate: WI.WordSdtCarrierGate, anchor: str
    ) -> None:
        with pytest.raises(WI.WordCarrierGateError):
            gate.assert_anchor_allowed(anchor)

    def test_probe_gate_identity_records_requirement_14_16_fields(
        self, gate: WI.WordSdtCarrierGate
    ) -> None:
        identity = gate.probe_gate_identity()
        for key in (
            "carrier_contract_sha256",
            "carrier_gate_digest",
            "onlyoffice_build",
            "browser",
            "source_commit",
            "runner",
            "lock_policy",
        ):
            assert identity[key], f"{key} 必须非空（Requirement 14.16 的记录清单）"


# ═══════════════════════════════════════════════════════════════════════════
# Property 30 / 34：Word 只认 tagged SDT，缺 tag 不降级
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty30TagOnly:
    """删除 tag 或只留 placeholder 文本后 extract 必须失败，不得回退段落索引/正则。"""

    def test_baseline_extract_reads_every_declared_field(
        self, plan_substrate: Path, plan_binding: WE.WordEngineBinding
    ) -> None:
        outcome = _extract(plan_substrate, plan_binding)
        assert set(outcome.projection.values) == set(_PLAN_VALUE_TYPES)
        # block 容器不进值集合，但进实例清册（层级判据要用它）
        assert outcome.unmanaged_sdt_count == 0
        assert any(inst.tag.kind == "block" for inst in outcome.instances)

    def test_removing_the_tag_fails_closed(
        self, workdir: Path, plan_instrumented: WI.InstrumentedDocx,
        plan_binding: WE.WordEngineBinding,
    ) -> None:
        """删掉一个 `w:tag` ⇒ `word_sdt_tag_missing`，而不是「按段落序号读到值」。"""
        target = f'<w:tag w:val="gt:field:{PLAN_ID}:plan/purpose"/>'
        broken = _rewrite_document(
            plan_instrumented.instrumented_bytes, lambda xml: xml.replace(target, "", 1)
        )
        path = workdir / "tag-removed.docx"
        path.write_bytes(broken)
        with pytest.raises(WE.WordTagMissingError) as err:
            _extract(path, plan_binding)
        assert "plan/purpose" in str(err.value)

    def test_placeholder_text_alone_is_not_a_protocol(
        self, workdir: Path, plan_binding: WE.WordEngineBinding
    ) -> None:
        """原始模板（只有 `${...}` 占位、零 SDT）必须整份 fail closed。

        这正是 Property 30 的原话「仅保留 placeholder 文本后 extract 必须失败」：
        占位文本永远只是一次性迁移线索，不是回写协议。
        """
        path = workdir / "raw-template.docx"
        path.write_bytes(F222.read_bytes())
        assert structure_fingerprint(F222.read_bytes()).sdt_nodes == []
        with pytest.raises(WE.WordTagMissingError):
            _extract(path, plan_binding)

    def test_unregistered_tag_fails_closed(
        self, workdir: Path, plan_instrumented: WI.InstrumentedDocx,
        plan_binding: WE.WordEngineBinding,
    ) -> None:
        broken = _rewrite_document(
            plan_instrumented.instrumented_bytes,
            lambda xml: xml.replace(
                f"gt:field:{PLAN_ID}:plan/purpose",
                f"gt:field:{PLAN_ID}:plan/not_in_contract",
                1,
            ),
        )
        path = workdir / "unregistered.docx"
        path.write_bytes(broken)
        with pytest.raises(WE.WordTagUnregisteredError):
            _extract(path, plan_binding)

    def test_foreign_contract_tag_fails_closed(
        self, workdir: Path, plan_instrumented: WI.InstrumentedDocx,
        plan_binding: WE.WordEngineBinding,
    ) -> None:
        """tag 的 contract 段与 frozen contract 不符 ⇒ 不得按 alias 换契约（P28）。"""
        broken = _rewrite_document(
            plan_instrumented.instrumented_bytes,
            lambda xml: xml.replace(f"gt:field:{PLAN_ID}:plan/scope",
                                    "gt:field:other.entry:plan/scope", 1),
        )
        path = workdir / "foreign-contract.docx"
        path.write_bytes(broken)
        with pytest.raises(WE.WordTagUnregisteredError):
            _extract(path, plan_binding)

    def test_instance_count_drift_fails_closed(
        self, workdir: Path, plan_instrumented: WI.InstrumentedDocx
    ) -> None:
        """契约声明 `instances=one` 却出现两个实例 ⇒ 独立 error_code。"""
        payload = plan_contract_payload()
        for field in payload["fields"]:
            if field["stable_field_key"] == "plan/entity_name":
                field["instances"] = "one"
        binding = binding_for(payload, entry_id=PLAN_ID)
        path = workdir / "instance-drift.docx"
        path.write_bytes(plan_instrumented.instrumented_bytes)
        with pytest.raises(WE.WordTagInstanceCountError):
            _extract(path, binding)

    def test_hierarchy_flattening_fails_closed(
        self, workdir: Path, plan_instrumented: WI.InstrumentedDocx,
        plan_binding: WE.WordEngineBinding,
    ) -> None:
        """把 block 容器的 tag 删掉 ⇒ 内层 field 的祖先链缺容器 ⇒ 层级漂移。"""
        block = f'<w:tag w:val="gt:block:{PLAN_ID}:plan/warehouses"/>'
        broken = _rewrite_document(
            plan_instrumented.instrumented_bytes,
            lambda xml: xml.replace(
                block, f'<w:tag w:val="gt:block:{PLAN_ID}:plan/purpose"/>', 1
            ),
        )
        path = workdir / "hierarchy-drift.docx"
        path.write_bytes(broken)
        with pytest.raises(
            (WE.WordTagHierarchyDriftError, WE.WordTagInstanceCountError)
        ) as err:
            _extract(path, plan_binding)
        assert err.value.error_code in {
            WE.WordTagHierarchyDriftError.error_code,
            WE.WordTagInstanceCountError.error_code,
        }

    def test_two_collector_disagreement_fails_closed(
        self, workdir: Path, plan_instrumented: WI.InstrumentedDocx,
        plan_binding: WE.WordEngineBinding,
    ) -> None:
        """两个采集口径数出的实例数不一致时必须 fail closed，绝不读到错位的值。

        engine 用两个独立口径读同一份 `word/document.xml`：结构树遍历
        （`word_sdt_fingerprint`，负责 tag/xpath/层级）与字节 span 扫描（本模块，
        负责 br-aware 的值文本）。两者本该一一对应；不一致就是采集器缺陷。

        🔴 这条判据在**真实数据上永远不触发**（两个口径一直一致），所以必须用**故障
        注入**让它可达 —— 否则它是「真实数据上分支不可达 = 永久 GREEN」那一类假绿
        （2026-08-29 M17 变异实测正是 GREEN）。

        为什么用 monkeypatch 而不是造畸形 XML：所有能让两个口径分歧的畸形形态
        （去掉 `w:sdtContent` 壳、`w:sdt` 里没有 tag……）都会被**更早**的
        `_fingerprint_or_fail` 当采集错误拦掉 —— 首轮实测得到
        `ERROR sdt_without_content`，本判据仍不可达。故障注入是「反向自检：故意写错
        必失败」，是这条判据唯一可达的路径。
        """
        path = workdir / "collector-disagreement.docx"
        path.write_bytes(plan_instrumented.instrumented_bytes)
        # 先确认未注入故障时是干净的（否则下面的红说明不了问题）
        _extract(path, plan_binding)

        real = WE._sdt_texts_by_tag
        try:
            WE._sdt_texts_by_tag = lambda xml: {  # type: ignore[assignment]
                tag: texts[:-1] if len(texts) > 1 else []
                for tag, texts in real(xml).items()
            }
            with pytest.raises(WE.WordEngineError) as err:
                _extract(path, plan_binding)
        finally:
            WE._sdt_texts_by_tag = real  # type: ignore[assignment]
        assert "两个采集口径" in str(err.value)
        # 还原后必须回到干净态（证明本用例没有污染同 module 的其他判据）
        _extract(path, plan_binding)

    def test_row_scoped_tag_outside_a_table_is_hierarchy_drift(
        self, workdir: Path, deficiency_instrumented: WI.InstrumentedDocx,
        deficiency_binding: WE.WordEngineBinding,
    ) -> None:
        """行域 tag 必须仍在 `w:tc` 内 —— 表外实例无法归属任何行。"""
        row_tag = f"gt:field:{DEF_ID}:rows/{ROW_UUIDS[0]}/deficiency"
        title_tag = f"gt:field:{DEF_ID}:deficiencies/title"
        broken = _rewrite_document(
            deficiency_instrumented.instrumented_bytes,
            lambda xml: xml.replace(title_tag, row_tag, 1),
        )
        path = workdir / "row-outside-table.docx"
        path.write_bytes(broken)
        with pytest.raises(WE.WordTagHierarchyDriftError):
            _extract(path, deficiency_binding)


class TestProperty34NoDegradation:
    """tag retention 失败时 operation error、incoming 保留、HTML 未变化。"""

    def test_incoming_bytes_survive_a_failed_extract(
        self, workdir: Path, plan_instrumented: WI.InstrumentedDocx,
        plan_binding: WE.WordEngineBinding,
    ) -> None:
        broken = _rewrite_document(
            plan_instrumented.instrumented_bytes,
            lambda xml: xml.replace(
                f'<w:tag w:val="gt:field:{PLAN_ID}:plan/scope"/>', "", 1
            ),
        )
        incoming = workdir / "p34-incoming.docx"
        incoming.write_bytes(broken)
        before = _sha(incoming.read_bytes())
        with pytest.raises(WE.WordTagMissingError):
            WE.extract_word_projection(
                artifact=incoming,
                binding=plan_binding,
                substrate_role=SubstrateRole.incoming,
                artifact_kind=ArtifactKind.incoming,
                artifact_state=ArtifactState.durable,
            )
        assert _sha(incoming.read_bytes()) == before, "失败的 extract 不得改动 incoming"

    def test_materialize_writes_nothing_when_row_identity_is_absent(
        self, workdir: Path, deficiency_substrate: Path,
        deficiency_binding: WE.WordEngineBinding,
    ) -> None:
        """要写的行 UUID 不存在时一个字节都不该落盘（不得按行号猜）。"""
        ghost = "11111111-2222-3333-4444-555555555555"
        projection = _text_projection(
            DEF_ID, {f"rows/{ghost}/deficiency": "凭空多出来的一行"}
        )
        output = workdir / "p34-never-written.docx"
        with pytest.raises(WE.WordRowIdentityMissingError):
            WE.materialize_word_projection(
                substrate=deficiency_substrate,
                projection=projection,
                output=output,
                binding=deficiency_binding,
                substrate_role=SubstrateRole.staged_result,
                artifact_kind=ArtifactKind.canonical,
                artifact_state=ArtifactState.staged,
            )
        assert not output.exists(), "行身份缺失时不得产出任何 staged result"


# ═══════════════════════════════════════════════════════════════════════════
# 结构判据：extract 路径上不存在 paragraph/regex fallback
# ═══════════════════════════════════════════════════════════════════════════


class TestNoParagraphOrRegexFallback:
    """「没有 fallback」用**真实 AST** 证明，不是靠注释声明。"""

    @staticmethod
    def _engine_ast() -> ast.Module:
        source = WE.__file__
        return ast.parse(Path(source).read_text(encoding="utf-8"))

    def test_engine_never_reads_the_pseudo_anchor_attributes(self) -> None:
        """`w_id` / `alias` / `body_child_index` / `run_count` 在 engine AST 上零引用。

        这四个属性是 Task 6 逐条证伪/降级的伪锚点。判据落在 AST 的
        `Attribute`/`Name` 图上 —— 把它们中任何一个用进定位逻辑都会打红，而
        「源码里是否出现某个字符串」改个别名就能绕过。
        """
        tree = self._engine_ast()
        hits: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in WE.FORBIDDEN_SDT_LOCATOR_ATTRS:
                hits.append(f"L{node.lineno}:.{node.attr}")
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                continue
        # 允许出现在 `FORBIDDEN_SDT_LOCATOR_ATTRS` 声明里的**字符串字面量**，
        # 但绝不允许属性访问。
        assert hits == [], f"engine 读了被证伪的伪锚点属性: {hits}"

    def test_engine_never_imports_the_stale_tag_parsers(self) -> None:
        """旧 `gtsdt/v1` 方案的解析器在本 engine 上零引用。

        它们对真实 `gt:` tag 每次都返回 `None` ⇒ 表现成「文档里没有受管字段」，
        是 fail-open 的最贵形态。
        """
        tree = self._engine_ast()
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name in WE.FORBIDDEN_FALLBACK_SYMBOLS:
                        imported.append(f"L{node.lineno}:{alias.name}")
            if isinstance(node, ast.Attribute) and node.attr in WE.FORBIDDEN_FALLBACK_SYMBOLS:
                imported.append(f"L{node.lineno}:.{node.attr}")
            if isinstance(node, ast.Name) and node.id in WE.FORBIDDEN_FALLBACK_SYMBOLS:
                imported.append(f"L{node.lineno}:{node.id}")
        assert imported == [], f"engine 引用了旧方案/段落计数符号: {imported}"

    def test_engine_has_no_positional_table_or_paragraph_index_logic(self) -> None:
        """engine 里不存在表格/行/单元格/段落序号形态的定位参数。

        一次性结构坐标只允许出现在 `word_instrumentation`（迁移器）里；
        运行态 engine 一个都不许有。
        """
        source = Path(WE.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden = {"table_index", "row_index", "cell_index", "paragraph_index"}
        hits: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.arg) and node.arg in forbidden:
                hits.append(f"L{node.lineno}:arg {node.arg}")
            if isinstance(node, ast.Name) and node.id in forbidden:
                hits.append(f"L{node.lineno}:{node.id}")
        assert hits == [], f"engine 出现了位置型定位: {hits}"

    def test_tag_pattern_has_no_second_source_in_the_engine(self) -> None:
        """tag 形态单一真源：engine **import** 它，且自己**不 compile 任何正则**。

        🔴 判据不能用 `WE.SDT_TAG_PATTERN is C._SDT_TAG_RE` —— 2026-08-29 变异实测
        判 GREEN：`re` 模块内部对 `(pattern, flags)` 有编译缓存，所以
        `re.compile(<同样的字符串>)` 返回的是**同一个对象**，`is` 照样成立。于是
        「在 engine 里另写一份字面相同的正则」这种真正的第二真源检测不出来。

        改成 AST 结构判据：
        1. 必须存在 `from ...contracts import _SDT_TAG_RE as SDT_TAG_PATTERN`；
        2. engine 里**一次** `re.compile` 都不许出现（否则就是第二真源）。
        """
        tree = ast.parse(Path(WE.__file__).read_text(encoding="utf-8"))
        imported_from_contracts = [
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and (node.module or "").endswith(".contracts")
            for alias in node.names
            if alias.name == "_SDT_TAG_RE"
        ]
        assert imported_from_contracts == ["SDT_TAG_PATTERN"], (
            "engine 必须从 `contracts` 引入唯一的 tag 正则，"
            f"实得 {imported_from_contracts}"
        )
        compiles = [
            f"L{node.lineno}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "compile"
        ]
        assert compiles == [], (
            f"engine 里出现了 `*.compile(...)` 调用 {compiles} —— tag/结构形态只能有"
            "一份真源；另写一份字面相同的正则时 `is` 判据会被 re 编译缓存骗过"
        )
        # 便宜的二次确认（在没有第二真源的前提下必然成立）
        assert WE.SDT_TAG_PATTERN is C._SDT_TAG_RE

    def test_read_gate_order_puts_admission_before_any_parsing(self) -> None:
        """读侧门的声明顺序：准入 → 发布授权 → OOXML 安全（最贵的一步在最后）。"""
        assert WE.READ_GATE_ORDER == (
            "substrate_admission",
            "publish_authority",
            "ooxml_security",
        )
        assert WE.READ_GATE_ORDER.index("substrate_admission") < WE.READ_GATE_ORDER.index(
            "ooxml_security"
        )

    def test_instrumentation_locator_kinds_are_declared_one_time_only(self) -> None:
        """迁移器的定位方式全部登记为 `one_time_*`，且与实测取值双向锁死。"""
        assert all(k.startswith("one_time_") for k in WI.ONE_TIME_LOCATOR_KINDS)
        observed = {inj.locator_kind for inj in plan_spec().fields}
        observed |= {inj.locator_kind for inj in deficiency_spec().fields}
        observed |= {inj.locator_kind for inj in deficiency_spec().rows}
        assert observed == set(WI.ONE_TIME_LOCATOR_KINDS), (
            "登记清单与实测取值必须双向锁死：多登记一个会掩盖未被覆盖的定位方式，"
            f"少登记一个会让新定位方式静默通过（实测 {sorted(observed)}）"
        )


# ═══════════════════════════════════════════════════════════════════════════
# Property 32：同 stable tag 多实例
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty32DuplicateWordInstances:
    def test_identical_values_merge_into_one_field(
        self, plan_substrate: Path, plan_binding: WE.WordEngineBinding
    ) -> None:
        """AC 7.4 前半句：值一致时合并为一个字段，不报冲突。"""
        outcome = _extract(plan_substrate, plan_binding)
        instances = [
            inst for inst in outcome.instances
            if inst.tag.stable_key == "plan/entity_name"
        ]
        assert len(instances) == 2, "fixture 必须真的有两个实例，否则本判据空转"
        assert "plan/entity_name" in outcome.projection.values
        assert not [
            c for c in outcome.conflicts
            if c.kind is ConflictKind.duplicate_word_instance
        ]

    def test_divergent_values_produce_a_conflict_listing_every_xpath(
        self, workdir: Path, plan_instrumented: WI.InstrumentedDocx,
        plan_binding: WE.WordEngineBinding,
    ) -> None:
        """AC 7.4 后半句 / Property 32：异值 ⇒ duplicate conflict + **全部** XPath。"""
        def mutate(xml: str) -> str:
            # 只改**第二个** entity_name 实例的文本
            marker = f'<w:tag w:val="gt:field:{PLAN_ID}:plan/entity_name"/>'
            first = xml.find(marker)
            second = xml.find(marker, first + 1)
            assert second > first, "fixture 必须有两个实例"
            head, tail = xml[:second], xml[second:]
            return head + tail.replace("${entityName}", "乙公司", 1)

        path = workdir / "duplicate-divergent.docx"
        path.write_bytes(_rewrite_document(plan_instrumented.instrumented_bytes, mutate))
        outcome = _extract(path, plan_binding)
        dupes = [
            c for c in outcome.conflicts
            if c.kind is ConflictKind.duplicate_word_instance
        ]
        assert len(dupes) == 1
        record = dupes[0]
        assert len(record.word_instances) == 2, "必须列出全部实例位置（AC 7.4）"
        assert len({ref.xpath for ref in record.word_instances}) == 2
        assert all(ref.xpath.startswith("/w:document") for ref in record.word_instances)
        values = {str(ref.value.value) for ref in record.word_instances}
        assert values == {"${entityName}", "乙公司"}
        # 异值字段不得进 projection（engine 不许自行选边）
        assert "plan/entity_name" not in outcome.projection.values


# ═══════════════════════════════════════════════════════════════════════════
# Property 31：Word-only 正文保留
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty31WordOnlyPreserved:
    def test_two_materialize_passes_keep_every_non_sdt_node(
        self, workdir: Path, plan_substrate: Path, plan_binding: WE.WordEngineBinding
    ) -> None:
        """Property 31 原话：两次 materialize 前后，SDT 外 OOXML 正文规范化内容相等。"""
        first = workdir / "p31-pass1.docx"
        second = workdir / "p31-pass2.docx"
        base = _extract(plan_substrate, plan_binding)
        p1 = _plan_projection(plan__purpose="第一次写入的监盘目的")
        WE.materialize_word_projection(
            substrate=plan_substrate, projection=p1, output=first,
            binding=plan_binding, substrate_role=SubstrateRole.staged_result,
            artifact_kind=ArtifactKind.canonical, artifact_state=ArtifactState.staged,
        )
        p2 = _plan_projection(
            plan__purpose="第二次写入的监盘目的（更长的中文文本）",
            plan__scope="抽样仓库",
            plan__warehouses="C 库",
            plan__bs_date=date(2027, 6, 30),
        )
        WE.materialize_word_projection(
            substrate=first, projection=p2, output=second,
            binding=plan_binding, substrate_role=SubstrateRole.staged_result,
            artifact_kind=ArtifactKind.canonical, artifact_state=ArtifactState.staged,
        )
        after = _extract(second, plan_binding)
        assert after.word_only_digest == base.word_only_digest
        report = WE.verify_word_only_regions(
            before=plan_substrate, after=second, binding=plan_binding
        )
        assert report.equivalent, report.first_difference

    def test_word_only_drift_is_detected(
        self, workdir: Path, plan_substrate: Path, plan_binding: WE.WordEngineBinding
    ) -> None:
        """删掉一段 SDT 外自由正文 ⇒ 必须打红（否则等价判据是空转）。"""
        fingerprint = structure_fingerprint(plan_substrate.read_bytes())
        victim = next(
            block["text"] for block in fingerprint.outside_sdt_blocks
            if len(block["text"]) > 12
        )
        broken = _rewrite_document(
            plan_substrate.read_bytes(), lambda xml: xml.replace(victim, "", 1)
        )
        path = workdir / "word-only-drift.docx"
        path.write_bytes(broken)
        report = WE.verify_word_only_regions(
            before=plan_substrate, after=path, binding=plan_binding
        )
        assert not report.equivalent
        assert report.first_difference and "outside_sdt_text" in report.first_difference
        with pytest.raises(WE.UnmanagedRegionDriftError):
            report.assert_equivalent()

    def test_protected_part_regression_is_detected(
        self, workdir: Path, plan_substrate: Path, plan_binding: WE.WordEngineBinding
    ) -> None:
        """删掉一个受保护部件（styles/numbering/customXml）⇒ 必须打红。"""
        with zipfile.ZipFile(io.BytesIO(plan_substrate.read_bytes())) as zf:
            infos = zf.infolist()
            parts = {i.filename: zf.read(i) for i in infos}
            order = [(i.filename, i.compress_type) for i in infos]
        victims = [name for name in parts if name.startswith("customXml/")]
        assert victims, "fixture 必须真的带 customXml 部件"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as out:
            for name, compress in order:
                if name == victims[0]:
                    continue
                out.writestr(zipfile.ZipInfo(name), parts[name], compress_type=compress)
        path = workdir / "protected-part-lost.docx"
        path.write_bytes(buffer.getvalue())
        report = WE.verify_word_only_regions(
            before=plan_substrate, after=path, binding=plan_binding
        )
        assert not report.equivalent
        assert "protected_parts" in (report.first_difference or "")

    def test_row_identity_loss_is_detected_on_the_gt_scheme(
        self, workdir: Path, deficiency_substrate: Path,
        deficiency_binding: WE.WordEngineBinding,
    ) -> None:
        """行身份丢失必须被自算的 `managed_row_identity` 抓到。

        🔴 `word_sdt_fingerprint` 的 `row_uuid_set` 一格认旧 `gtsdt/v1` 方案，在
        `gt:` 方案下两侧恒空 ⇒ 恒真。本判据用 engine 自算的行身份索引，故有效。
        """
        row_tag = f"gt:field:{DEF_ID}:rows/{ROW_UUIDS[1]}/deficiency"
        broken = _rewrite_document(
            deficiency_substrate.read_bytes(),
            lambda xml: xml.replace(row_tag, f"gt:field:{DEF_ID}:deficiencies/title", 1),
        )
        path = workdir / "row-identity-lost.docx"
        path.write_bytes(broken)
        report = WE.verify_word_only_regions(
            before=deficiency_substrate, after=path, binding=deficiency_binding
        )
        assert not report.equivalent
        assert "managed_row_identity" in (report.first_difference or "")
        assert report.details["lost_row_identity"]


class TestCoverageIsNotEmpty:
    """各 aspect 覆盖计数全部 > 0 —— 防「空集恒等价」。"""

    def test_plan_fixture_covers_every_word_only_aspect(
        self, plan_substrate: Path, plan_binding: WE.WordEngineBinding
    ) -> None:
        report = WE.verify_word_only_regions(
            before=plan_substrate, after=plan_substrate, binding=plan_binding
        )
        coverage = report.details["coverage"]
        for aspect in ("outside_sdt_text", "sdt_tag_set", "sdt_hierarchy", "protected_parts"):
            assert coverage[aspect] > 0, (
                f"{aspect} 覆盖计数为 0 ⇒ 该 aspect 的等价判定是空转，"
                "fixture 必须换成真实权威模板"
            )

    def test_deficiency_fixture_covers_tables_and_row_identity(
        self, deficiency_substrate: Path, deficiency_binding: WE.WordEngineBinding
    ) -> None:
        report = WE.verify_word_only_regions(
            before=deficiency_substrate, after=deficiency_substrate,
            binding=deficiency_binding,
        )
        coverage = report.details["coverage"]
        assert coverage["table_shape"] > 0
        assert coverage["managed_row_identity"] == len(ROW_UUIDS)

    def test_instrumentation_equivalence_coverage_is_not_empty(
        self, gate: WI.WordSdtCarrierGate, plan_instrumented: WI.InstrumentedDocx,
        deficiency_instrumented: WI.InstrumentedDocx,
    ) -> None:
        plan = WI.verify_docx_visible_equivalence(
            source=F222.read_bytes(), instrumented=plan_instrumented, spec=plan_spec()
        )
        assert plan["coverage"]["visible_text_chars"] > 0
        assert plan["coverage"]["untouched_parts"] > 0
        assert plan["coverage"]["protected_parts"] > 0
        deficiency = WI.verify_docx_visible_equivalence(
            source=B30112.read_bytes(), instrumented=deficiency_instrumented,
            spec=deficiency_spec(),
        )
        assert deficiency["coverage"]["table_shape"] > 0
        assert deficiency["coverage"]["protected_part_classes"] >= 5


# ═══════════════════════════════════════════════════════════════════════════
# Property 65：projection 与 representation 等值 + substrate 准入
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty65ProjectionEquivalence:
    def test_materialize_extract_roundtrip_is_type_equal(
        self, workdir: Path, plan_substrate: Path, plan_binding: WE.WordEngineBinding
    ) -> None:
        projection = _plan_projection(plan__warehouses="A 库\nB 库\nC 库")
        output = workdir / "p65-roundtrip.docx"
        materialized = WE.materialize_word_projection(
            substrate=plan_substrate, projection=projection, output=output,
            binding=plan_binding, substrate_role=SubstrateRole.staged_result,
            artifact_kind=ArtifactKind.canonical, artifact_state=ArtifactState.staged,
        )
        # block 容器不是写入目标（否则内层 SDT 连 tag 一起被抹掉）
        assert materialized.skipped_container_tags == (
            f"gt:block:{PLAN_ID}:plan/warehouses",
        )
        assert materialized.untouched_part_count > 0
        bundle = WE.verify_word_before_commit(
            expected=projection, staged_result=output, substrate=plan_substrate,
            binding=plan_binding,
        )
        assert bundle.mismatched_keys == ()
        assert bundle.unmanaged.equivalent
        bundle.assert_publishable()

    def test_multiline_values_round_trip(
        self, workdir: Path, plan_substrate: Path, plan_binding: WE.WordEngineBinding
    ) -> None:
        """换行必须往返（design §Word extract「保留 contract 指定的换行」）。"""
        projection = _plan_projection(plan__purpose="第一行\n第二行")
        output = workdir / "p65-multiline.docx"
        WE.materialize_word_projection(
            substrate=plan_substrate, projection=projection, output=output,
            binding=plan_binding, substrate_role=SubstrateRole.staged_result,
            artifact_kind=ArtifactKind.canonical, artifact_state=ArtifactState.staged,
        )
        outcome = _extract(output, plan_binding)
        assert "\n" in str(outcome.projection.values["plan/purpose"].value), (
            "`w:br` 必须被读回成 `\\n` —— 否则「A\\nB」写进去读回来是「AB」，"
            "反读等值门在真实多行值上必红"
        )

    def test_managed_projection_mismatch_blocks_publication(
        self, workdir: Path, plan_substrate: Path, plan_binding: WE.WordEngineBinding
    ) -> None:
        """AC 8.11：反读不等值 ⇒ 不得推进（判据要能真打红）。"""
        projection = _plan_projection(plan__bs_date=date(2026, 12, 31))
        output = workdir / "p65-mismatch.docx"
        WE.materialize_word_projection(
            substrate=plan_substrate, projection=projection, output=output,
            binding=plan_binding, substrate_role=SubstrateRole.staged_result,
            artifact_kind=ArtifactKind.canonical, artifact_state=ArtifactState.staged,
        )
        # 🔴 对 `date` 字段说谎：`_canonical` 的**非 text** 分支必须真被覆盖，
        #    否则「类型化等值」只在文本上被测过（M19 变异实测 GREEN）。
        lying = _plan_projection(plan__bs_date=date(2020, 1, 1))
        bundle = WE.verify_word_before_commit(
            expected=lying, staged_result=output, substrate=plan_substrate,
            binding=plan_binding,
        )
        assert bundle.mismatched_keys == ("plan/bs_date",)
        with pytest.raises(WE.WordManagedProjectionMismatchError):
            bundle.assert_publishable()

    @pytest.mark.parametrize(
        ("kind", "state", "expected"),
        [
            (ArtifactKind.incoming, ArtifactState.quarantined, QuarantinedIncomingError),
            (ArtifactKind.incoming, ArtifactState.staged, IncomingNotDurableError),
        ],
    )
    def test_quarantined_and_non_durable_incoming_are_rejected_at_the_entry(
        self, workdir: Path, plan_substrate: Path, plan_binding: WE.WordEngineBinding,
        kind: ArtifactKind, state: ArtifactState, expected: type[Exception],
    ) -> None:
        """AC 8.10：engine 入口就拒，且**在任何解析之前**。

        用一份**不是 DOCX** 的文件当 artifact：若准入门排在解析之后，会先撞
        `ooxml_structure_invalid` ⇒ 准入判据落在永久不可达分支（本 spec 已实测同形态）。
        """
        not_a_docx = workdir / "not-a-docx.bin"
        not_a_docx.write_bytes(b"definitely not a zip")
        with pytest.raises(expected):
            WE.extract_word_projection(
                artifact=not_a_docx, binding=plan_binding,
                substrate_role=SubstrateRole.incoming,
                artifact_kind=kind, artifact_state=state,
            )

    def test_upgrade_candidate_is_never_an_engine_substrate(
        self, workdir: Path, plan_binding: WE.WordEngineBinding
    ) -> None:
        not_a_docx = workdir / "candidate.bin"
        not_a_docx.write_bytes(b"definitely not a zip")
        from app.services.workpaper_sync.adapters.base import (
            AdapterCandidateSubstrateError,
        )

        with pytest.raises(AdapterCandidateSubstrateError):
            WE.extract_word_projection(
                artifact=not_a_docx, binding=plan_binding,
                substrate_role=SubstrateRole.incoming,
                artifact_kind=ArtifactKind.upgrade_candidate,
                artifact_state=ArtifactState.candidate,
            )

    def test_rematerialize_uses_incoming_as_read_only_substrate(
        self, workdir: Path, plan_substrate: Path, plan_binding: WE.WordEngineBinding
    ) -> None:
        """OO→HTML：incoming 只读、输出写到独立 staged result，incoming 字节不变。"""
        incoming = workdir / "p65-incoming.docx"
        incoming.write_bytes(plan_substrate.read_bytes())
        before = _sha(incoming.read_bytes())
        merged = _plan_projection(
            plan__purpose="合并后的目的",
            plan__scope="合并后的范围",
            plan__warehouses="合并后的仓库",
        )
        output = workdir / "p65-result.docx"
        materialized, bundle = WE.rematerialize_word_merged_projection(
            merged=merged, incoming_substrate=incoming, output=output,
            binding=plan_binding,
        )
        assert _sha(incoming.read_bytes()) == before, "incoming 是只读 substrate"
        assert materialized.output_path == output
        assert output.resolve() != incoming.resolve()
        bundle.assert_publishable()


# ═══════════════════════════════════════════════════════════════════════════
# Property 28：immutable definition 漂移 fail closed
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty28FrozenDefinitionDrift:
    def test_offline_mode_must_not_carry_a_bundle(self) -> None:
        with pytest.raises(WE.WordApprovedBundleRequiredError):
            WE.WordEngineBinding(
                contract=C.parse_contract(plan_contract_payload(), adapter_id=PLAN_ID),
                entry_id=PLAN_ID,
                mode=WE.WordEngineMode.offline_candidate_validation,
                bundle=object(),  # type: ignore[arg-type]
            )

    def test_bundle_bound_mode_requires_a_bundle(self) -> None:
        with pytest.raises(WE.WordApprovedBundleRequiredError):
            WE.WordEngineBinding(
                contract=C.parse_contract(plan_contract_payload(), adapter_id=PLAN_ID),
                entry_id=PLAN_ID,
                mode=WE.WordEngineMode.bundle_bound,
            )

    def test_offline_binding_can_never_publish(
        self, plan_binding: WE.WordEngineBinding
    ) -> None:
        """缺 approved bundle 时 engine 只能离线验证 candidate。"""
        with pytest.raises(WE.WordApprovedBundleRequiredError):
            plan_binding.assert_may_publish()

    def test_published_representation_substrate_needs_an_approved_bundle(
        self, workdir: Path, plan_substrate: Path, plan_binding: WE.WordEngineBinding
    ) -> None:
        """读 published representation 是运行态动作 ⇒ 离线模式必须被拒。"""
        with pytest.raises(WE.WordApprovedBundleRequiredError):
            WE.extract_word_projection(
                artifact=plan_substrate, binding=plan_binding,
                substrate_role=SubstrateRole.published_representation,
                artifact_kind=ArtifactKind.canonical,
                artifact_state=ArtifactState.published,
            )

    def test_carrier_gate_rejects_a_contract_declaring_the_blocked_carrier(self) -> None:
        """契约声明 `row_sdt` ⇒ 在契约解析层就被拒（Task 13 的 gate 单一真源）。"""
        payload = plan_contract_payload()
        payload["identity_carriers"] = ["row_sdt"]
        with pytest.raises(C.ContractCarrierGateError):
            C.parse_contract(payload, adapter_id=PLAN_ID)

    def test_binding_rejects_non_docx_contract(self) -> None:
        """docx 契约改成 xlsx ⇒ 在契约层就被 Excel 载体门拒（不会走到 Word engine）。"""
        payload = plan_contract_payload()
        payload["document_type"] = "xlsx"
        with pytest.raises((WE.WordEngineError, C.ContractError)):
            binding_for(payload, entry_id=PLAN_ID)

    def test_word_engine_refuses_an_excel_carrier_gate(self) -> None:
        """把 Excel 域的 gate 塞给 Word engine ⇒ 载体门必须拒（域串用）。"""
        contract = C.parse_contract(plan_contract_payload(), adapter_id=PLAN_ID)
        with pytest.raises(WE.WordCarrierBlockedError):
            WE.WordEngineBinding(
                contract=contract,
                entry_id=PLAN_ID,
                mode=WE.WordEngineMode.offline_candidate_validation,
                carrier_gate=C.load_excel_carrier_gate(),
            )

    def test_frozen_identity_records_requirement_7_10_fields(
        self, plan_binding: WE.WordEngineBinding
    ) -> None:
        """Requirement 7.10：非空 bundle/authority/child identity + 实例计数。"""
        identity = plan_binding.frozen_identity
        assert identity["contract_sha256"] and len(identity["contract_sha256"]) == 64
        assert identity["template_definition_sha256"]
        assert identity["instrumentation_definition_sha256"]
        assert identity["carrier_gate_digest"]
        assert identity["declared_field_instances"]["plan/entity_name"] == "many"
        assert identity["declared_field_instances"]["plan/purpose"] == "one"
        # 离线模式必须诚实地把 bundle 三项报成 None，而不是编一个
        assert identity["definition_bundle_id"] is None
        assert identity["definition_bundle_sha256"] is None
        assert identity["authority_model"] is None

    def test_contract_digest_drift_changes_frozen_identity(self) -> None:
        """改契约任一受管语义 ⇒ canonical digest 变 ⇒ 历史 operation 不会被静默复用。"""
        base = binding_for(plan_contract_payload(), entry_id=PLAN_ID)
        drifted_payload = plan_contract_payload()
        drifted_payload["fields"][0]["json_pointer"] = "/plan/purpose_v2"
        drifted = binding_for(drifted_payload, entry_id=PLAN_ID)
        assert base.contract.canonical_sha256 != drifted.contract.canonical_sha256


# ═══════════════════════════════════════════════════════════════════════════
# Property 67：candidate 先行、approved bundle 后 finalize
# ═══════════════════════════════════════════════════════════════════════════


class _FakeRepository:
    """只提供 candidate 路径真正用到的那几个方法；其余一律没有。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def register_artifact(self, **kwargs: Any) -> Any:
        self.calls.append("register_artifact")
        return object()

    async def create_upgrade_candidate(self, **kwargs: Any) -> Any:
        self.calls.append("create_upgrade_candidate")
        return object()


class TestProperty67CandidateOnly:
    def test_forbidden_surface_covers_representation_pointer_finalize_and_revision(
        self,
    ) -> None:
        """禁令面是 Task 15 revision 三件套 ∪ 本任务三件套（**import 取并集**）。"""
        from app.services.workpaper_sync.content_mutation import (
            REVISION_DOMAIN_WRITE_METHODS,
        )

        assert {
            "create_representation",
            "set_entry_pointer",
            "finalize_candidate",
        } <= WI.CANDIDATE_FORBIDDEN_METHODS
        assert set(REVISION_DOMAIN_WRITE_METHODS) <= WI.CANDIDATE_FORBIDDEN_METHODS

    @pytest.mark.parametrize(
        "method",
        ["create_representation", "set_entry_pointer", "finalize_candidate"],
    )
    def test_candidate_only_repository_blocks_the_publication_surface(
        self, method: str
    ) -> None:
        repo = WI.CandidateOnlyRepository(_FakeRepository())
        with pytest.raises(WI.CandidateSurfaceForbiddenError):
            getattr(repo, method)

    def test_upgrader_wraps_a_bare_repository_unconditionally(self) -> None:
        """即便调用方传裸 repository，upgrader 也拿不到那四类写入面。"""
        upgrader = WI.WordInstrumentationUpgrader(
            session=object(),
            repository=_FakeRepository(),
            artifacts=object(),
            project_id=__import__("uuid").uuid4(),
            source_commit="task59-guard",
            gate=WI.WordSdtCarrierGate.load(),
        )
        assert isinstance(upgrader.repository, WI.CandidateOnlyRepository)
        with pytest.raises(WI.CandidateSurfaceForbiddenError):
            upgrader.repository.create_representation

    def test_offline_candidate_validation_reports_publish_blocked(
        self, workdir: Path, plan_binding: WE.WordEngineBinding
    ) -> None:
        """缺 approved bundle 时唯一允许的动作：离线验证 candidate。"""
        upgrader = WI.WordInstrumentationUpgrader(
            session=object(),
            repository=_FakeRepository(),
            artifacts=object(),
            project_id=__import__("uuid").uuid4(),
            source_commit="task59-guard",
            gate=WI.WordSdtCarrierGate.load(),
        )
        report = upgrader.validate_candidate_offline(
            source=F222.read_bytes(),
            spec=plan_spec(),
            binding=plan_binding,
            staging_dir=workdir / "offline",
        )
        assert report["publish_blocked"] is True
        assert report["word_only"]["equivalent"] is True
        assert report["word_only"]["coverage"]["outside_sdt_text"] > 0
        assert report["extract"]["managed_field_count"] == len(_PLAN_VALUE_TYPES)
        assert report["readback"]["untagged_sdt_count"] == 0

    def test_instrumentation_payload_has_no_contract_or_bundle_backreference(
        self, gate: WI.WordSdtCarrierGate
    ) -> None:
        """DAG：instrumentation 只单向引用 template digest（Task 12 单一真源强制）。"""
        payload = WI.build_word_instrumentation_payload(
            spec=plan_spec(),
            template_definition_sha256=_digest("tpl-def"),
            template_sha256=F222_SHA,
            gate=gate,
        )
        flat = json.dumps(payload, sort_keys=True)
        assert "contract_" not in flat
        assert "bundle" not in flat
        assert payload["template_definition_sha256"] == _digest("tpl-def")
        assert payload["identity_anchors"] == ["w_tag"]

    def test_instrumentation_payload_rejects_a_blocked_carrier(
        self, gate: WI.WordSdtCarrierGate
    ) -> None:
        spec = WI.WordInstrumentationSpec(
            entry_id=PLAN_ID,
            contract_id=PLAN_ID,
            template_id="F2-22",
            template_relative_path="F/F2-22 存货监盘计划.docx",
            fields=(
                WI.WordFieldInjection(
                    token="${purpose}",
                    stable_field_key="plan/purpose",
                    carrier="row_sdt",
                ),
            ),
        )
        with pytest.raises(WI.WordCarrierGateError):
            WI.build_word_instrumentation_payload(
                spec=spec,
                template_definition_sha256=_digest("tpl-def"),
                template_sha256=F222_SHA,
                gate=gate,
            )


# ═══════════════════════════════════════════════════════════════════════════
# instrumentation：只改 document.xml、可见文本零变化、无 w:lock
# ═══════════════════════════════════════════════════════════════════════════


class TestZipLevelInstrumentation:
    def test_only_the_document_part_changes(
        self, plan_instrumented: WI.InstrumentedDocx
    ) -> None:
        """批注/修订/图片/页眉页脚/styles/numbering/customXml 逐字节保留。"""
        changed = [
            name for name, same in plan_instrumented.part_bytes_identical.items()
            if not same
        ]
        assert changed == [WE.WORD_DOCUMENT_PART]
        assert plan_instrumented.untouched_parts == 16

    def test_visible_text_stream_is_byte_identical(
        self, plan_instrumented: WI.InstrumentedDocx,
        deficiency_instrumented: WI.InstrumentedDocx,
    ) -> None:
        """注入只加结构，一个可见字符都不许改。"""
        for source_path, instrumented in (
            (F222, plan_instrumented),
            (B30112, deficiency_instrumented),
        ):
            before = WI.visible_text_stream(source_path.read_bytes())
            after = WI.visible_text_stream(instrumented.instrumented_bytes)
            assert before == after, f"{source_path.name} 的可见文本流被改动"
            assert before[1] > 0, "可见文本为空 ⇒ 本判据空转"

    def test_visible_text_change_inside_an_sdt_is_still_rejected(
        self, plan_instrumented: WI.InstrumentedDocx
    ) -> None:
        """SDT **内部**的可见文本改动必须被抓到。

        这是「可见文本流逐字符相同」这条不变量的反例测试：SDT 内部的文本改动在逐
        aspect 口径下完全看不见（`outside_sdt_text` 不含它、`sdt_tag_set` 也不含它），
        所以撤掉不变量之后只剩 aspect 比对时这类改动会静默通过。
        """
        tampered = _rewrite_document(
            plan_instrumented.instrumented_bytes,
            lambda xml: xml.replace("${purpose}", "${purpose}被偷偷改了", 1),
        )
        fake = WI.InstrumentedDocx(
            instrumented_bytes=tampered,
            instrumented_sha256=_sha(tampered),
            injected_tags=plan_instrumented.injected_tags,
            row_uuids=plan_instrumented.row_uuids,
            untouched_parts=plan_instrumented.untouched_parts,
            part_bytes_identical=plan_instrumented.part_bytes_identical,
        )
        with pytest.raises(WI.WordVisibleEquivalenceError) as err:
            WI.verify_docx_visible_equivalence(
                source=F222.read_bytes(), instrumented=fake, spec=plan_spec()
            )
        assert "可见文本流" in str(err.value)

    def test_no_w_lock_is_injected(
        self, plan_instrumented: WI.InstrumentedDocx
    ) -> None:
        """Task 6 的 `lock_policy=no_w_lock_injected` 前提必须成立。

        两半判据：产物里没有 `w:lock`（正面），**且**判据函数在真有 `w:lock` 时会抛
        （反面）。只有正面那一半时，把判据整条删掉也不会红 —— `_sdt_wrapper` 本来就
        不写锁，判据在公开 API 上结构不可达（M28 首轮实测 GREEN）。
        """
        with zipfile.ZipFile(io.BytesIO(plan_instrumented.instrumented_bytes)) as zf:
            xml = zf.read(WE.WORD_DOCUMENT_PART).decode("utf-8")
        assert "<w:lock" not in xml
        WI.assert_no_sdt_lock(xml, entry_id=PLAN_ID)  # 干净产物必须放行
        with pytest.raises(WI.WordLockPolicyError):
            WI.assert_no_sdt_lock(
                xml.replace(
                    "<w:sdtPr>", '<w:sdtPr><w:lock w:val="sdtLocked"/>', 1
                ),
                entry_id=PLAN_ID,
            )

    def test_only_document_part_changed_is_enforced_not_just_observed(
        self, plan_instrumented: WI.InstrumentedDocx
    ) -> None:
        """「只改 document.xml」必须是**判据**而不是观察结果。

        同 `assert_no_sdt_lock`：`instrument_docx_bytes` 结构上只写一个部件，所以这条
        防御判据在公开 API 上不可达 ⇒ 必须直接喂反例（M27 首轮实测 GREEN）。
        """
        WI.assert_only_document_part_changed(
            plan_instrumented.part_bytes_identical, entry_id=PLAN_ID
        )
        tampered = dict(plan_instrumented.part_bytes_identical)
        victim = next(
            name for name in tampered if name.startswith("customXml/")
        )
        tampered[victim] = False
        with pytest.raises(WI.WordVisibleEquivalenceError) as err:
            WI.assert_only_document_part_changed(tampered, entry_id=PLAN_ID)
        assert victim in str(err.value)

    def test_swallowing_a_free_text_paragraph_is_rejected(
        self, plan_instrumented: WI.InstrumentedDocx
    ) -> None:
        """把一整段自由正文吞进 SDT ⇒ SDT 外正文的消失无法用声明 token 解释。

        这是 2026-08-29 首轮实测到的真实缺陷形态（`outside_sdt_text` 从 31 块掉到
        26 块，因为整个 run 被包进了 SDT）。反例构造刻意让**可见文本流不变**，
        于是它必须被 `outside_sdt_text` 的逐块解释判据抓住，而不是被更前面那条
        文本流不变量顺手挡掉（M26 首轮实测 GREEN 就是因为没有这条反例）。
        """
        fingerprint = structure_fingerprint(plan_instrumented.instrumented_bytes)
        tokens = {inj.token for inj in plan_spec().fields}
        victim = next(
            block["text"]
            for block in fingerprint.outside_sdt_blocks
            if len(block["text"]) > 12 and not any(t in block["text"] for t in tokens)
        )

        def mutate(xml: str) -> str:
            # 把该段的一个 run 包进带**已登记 tag** 的 SDT ⇒ 文本流不变、
            # 但那一整块自由正文从 outside 集合里消失，且它不含任何声明 token。
            at = xml.find(victim)
            assert at > 0, "反例文本必须真的出现在 document.xml 里"
            run_open = xml.rfind("<w:r>", 0, at)
            run_close = xml.find("</w:r>", at) + len("</w:r>")
            body = xml[run_open:run_close]
            wrapped = (
                f'<w:sdt><w:sdtPr><w:tag w:val="gt:field:{PLAN_ID}:plan/purpose"/>'
                f"</w:sdtPr><w:sdtContent>{body}</w:sdtContent></w:sdt>"
            )
            return xml[:run_open] + wrapped + xml[run_close:]

        swallowed = _rewrite_document(plan_instrumented.instrumented_bytes, mutate)
        fake = WI.InstrumentedDocx(
            instrumented_bytes=swallowed,
            instrumented_sha256=_sha(swallowed),
            injected_tags=plan_instrumented.injected_tags,
            row_uuids=plan_instrumented.row_uuids,
            untouched_parts=plan_instrumented.untouched_parts,
            part_bytes_identical=plan_instrumented.part_bytes_identical,
        )
        # 前置确认：可见文本流没变（否则打红的是上一条判据，本判据仍不可达）
        assert WI.visible_text_stream(swallowed) == WI.visible_text_stream(
            plan_instrumented.instrumented_bytes
        )
        with pytest.raises(WI.WordVisibleEquivalenceError) as err:
            WI.verify_docx_visible_equivalence(
                source=F222.read_bytes(), instrumented=fake, spec=plan_spec()
            )
        assert "无法用声明 token 解释" in str(err.value)

    def test_no_sdt_id_is_written(
        self, plan_instrumented: WI.InstrumentedDocx
    ) -> None:
        """不写 `w:id` —— Task 6 实测它在本协议下不唯一，写了就给伪锚点留素材。"""
        fingerprint = structure_fingerprint(plan_instrumented.instrumented_bytes)
        assert all(node.w_id is None for node in fingerprint.sdt_nodes)

    def test_token_occurrence_drift_fails_closed(
        self, gate: WI.WordSdtCarrierGate
    ) -> None:
        """声明 1 次而实际 2 次（或反之）必须 fail closed，不得按段落序号挑一个。"""
        spec = WI.WordInstrumentationSpec(
            entry_id=PLAN_ID, contract_id=PLAN_ID, template_id="F2-22",
            template_relative_path="F/F2-22 存货监盘计划.docx",
            fields=(
                WI.WordFieldInjection(
                    token="${entityName}", stable_field_key="plan/entity_name",
                ),
            ),
        )
        with pytest.raises(WI.WordTokenAnchorError) as err:
            WI.instrument_docx_bytes(F222.read_bytes(), spec, gate=gate)
        assert "命中 2 个段落" in str(err.value)

    def test_missing_token_fails_closed(self, gate: WI.WordSdtCarrierGate) -> None:
        spec = WI.WordInstrumentationSpec(
            entry_id=PLAN_ID, contract_id=PLAN_ID, template_id="F2-22",
            template_relative_path="F/F2-22 存货监盘计划.docx",
            fields=(
                WI.WordFieldInjection(
                    token="${doesNotExist}", stable_field_key="plan/purpose"
                ),
            ),
        )
        with pytest.raises(WI.WordTokenAnchorError):
            WI.instrument_docx_bytes(F222.read_bytes(), spec, gate=gate)

    def test_double_instrumentation_is_refused(
        self, gate: WI.WordSdtCarrierGate, plan_instrumented: WI.InstrumentedDocx
    ) -> None:
        """已注入过的字节不得二次注入（会产生同 tag 多实例）。"""
        with pytest.raises((WI.WordVisibleEquivalenceError, WI.WordTokenAnchorError)):
            second = WI.instrument_docx_bytes(
                plan_instrumented.instrumented_bytes, plan_spec(), gate=gate
            )
            WI.verify_docx_visible_equivalence(
                source=plan_instrumented.instrumented_bytes,
                instrumented=second,
                spec=plan_spec(),
            )

    def test_readback_detects_a_lost_instance_not_just_a_lost_tag(
        self, gate: WI.WordSdtCarrierGate, plan_instrumented: WI.InstrumentedDocx
    ) -> None:
        """同 tag 少一个实例时集合完全相同 ⇒ 只比集合会判绿（Requirement 7.10）。"""
        marker = f'<w:tag w:val="gt:field:{PLAN_ID}:plan/entity_name"/>'

        def mutate(xml: str) -> str:
            first = xml.find(marker)
            second = xml.find(marker, first + 1)
            return xml[:second] + xml[second + len(marker) :]

        broken = _rewrite_document(plan_instrumented.instrumented_bytes, mutate)
        fake = WI.InstrumentedDocx(
            instrumented_bytes=broken,
            instrumented_sha256=_sha(broken),
            injected_tags=plan_instrumented.injected_tags,
            row_uuids=plan_instrumented.row_uuids,
            untouched_parts=plan_instrumented.untouched_parts,
            part_bytes_identical=plan_instrumented.part_bytes_identical,
        )
        with pytest.raises(WI.WordTagReadbackError) as err:
            WI.read_back_word_tags(instrumented=fake, spec=plan_spec(), gate=gate)
        assert "实例计数不符" in str(err.value)

    def test_row_injection_requires_exactly_one_one_time_locator(self) -> None:
        with pytest.raises(WI.WordTokenAnchorError):
            WI.WordRowInjection(
                row_field_key_template="rows/{row_uuid}/deficiency",
                row_uuid=ROW_UUIDS[0],
                token="${x}",
                table_index=0,
                row_index=1,
                cell_index=1,
            )
        with pytest.raises(WI.WordTokenAnchorError):
            WI.WordRowInjection(
                row_field_key_template="rows/{row_uuid}/deficiency",
                row_uuid=ROW_UUIDS[0],
            )

    def test_duplicate_row_uuid_is_refused(self) -> None:
        with pytest.raises(WI.WordTokenAnchorError):
            WI.WordInstrumentationSpec(
                entry_id=DEF_ID, contract_id=DEF_ID, template_id="B30-11-2",
                template_relative_path="B/B30-11-2 内部控制缺陷汇总与评估.docx",
                fields=(
                    WI.WordFieldInjection(
                        token="内部控制缺陷汇总与评估",
                        stable_field_key="deficiencies/title",
                        literal_anchor=True,
                        expected_token_occurrences=2,
                    ),
                ),
                rows=(
                    WI.WordRowInjection(
                        row_field_key_template="rows/{row_uuid}/deficiency",
                        row_uuid=ROW_UUIDS[0], table_index=0, row_index=1, cell_index=1,
                    ),
                    WI.WordRowInjection(
                        row_field_key_template="rows/{row_uuid}/deficiency",
                        row_uuid=ROW_UUIDS[0], table_index=0, row_index=2, cell_index=1,
                    ),
                ),
            )

    def test_row_identity_must_live_in_the_tag(self) -> None:
        with pytest.raises(WI.WordTokenAnchorError):
            WI.WordRowInjection(
                row_field_key_template="rows/deficiency",  # 缺 {row_uuid}
                row_uuid=ROW_UUIDS[0], table_index=0, row_index=1, cell_index=1,
            )

    def test_literal_anchor_must_be_declared_explicitly(self) -> None:
        with pytest.raises(WI.WordTokenAnchorError):
            WI.WordFieldInjection(
                token="内部控制缺陷汇总与评估", stable_field_key="deficiencies/title"
            )

    def test_empty_instrumentation_spec_is_refused(self) -> None:
        """空声明会让「注入成功」恒真（空集恒等价）。"""
        with pytest.raises(WI.WordInstrumentationError):
            WI.WordInstrumentationSpec(
                entry_id=PLAN_ID, contract_id=PLAN_ID, template_id="F2-22",
                template_relative_path="F/F2-22 存货监盘计划.docx",
            )


class TestRowInventoryIsHonest:
    """行身份清册必须能真的数出「没有身份的行」。"""

    def test_header_row_is_reported_as_unidentified(
        self, deficiency_substrate: Path, deficiency_binding: WE.WordEngineBinding
    ) -> None:
        outcome = _extract(deficiency_substrate, deficiency_binding)
        inventory = outcome.row_inventory
        assert inventory.managed_table_count == 1
        assert inventory.total_rows == 4
        assert inventory.identified_rows == len(ROW_UUIDS)
        # 表头行没有身份，这是**事实**而不是错误；判据是它真的被数出来了
        assert inventory.unidentified_rows == 1

    def test_a_new_row_without_identity_increases_the_count(
        self, workdir: Path, deficiency_substrate: Path,
        deficiency_binding: WE.WordEngineBinding,
    ) -> None:
        """OO 新增行不带 identity（Task 6 实测）⇒ 计数必须 +1，不能恒 0。"""
        def mutate(xml: str) -> str:
            spans = WE._find_spans(xml, "tr")
            outer = WE._outermost(spans)
            victim = outer[-1]
            clone = xml[victim[0] : victim[3]]
            # 去掉克隆行里的全部 SDT tag ⇒ 一个没有行身份的新行
            clone = re.sub(r'<w:tag w:val="[^"]*"/>', "", clone)
            return xml[: victim[3]] + clone + xml[victim[3] :]

        path = workdir / "oo-created-row.docx"
        path.write_bytes(_rewrite_document(deficiency_substrate.read_bytes(), mutate))
        outcome = _extract(path, deficiency_binding)
        assert outcome.row_inventory.total_rows == 5
        assert outcome.row_inventory.identified_rows == len(ROW_UUIDS)
        assert outcome.row_inventory.unidentified_rows == 2


# ═══════════════════════════════════════════════════════════════════════════
# 失败 kind 的可达性与互异性
# ═══════════════════════════════════════════════════════════════════════════


class TestFailureKindsDistinctAndReachable:
    """把全部 kind 各真触发一次、断言集合基数 == 登记数、且与清单双向锁死。

    🔴 这比「每类各测一遍」强：后者在两类被合并成同一 `error_code` 时**全部仍绿**
    （本 spec 已实测三次「共享错误码让较早分支永久不可达」）。
    """

    def test_engine_failure_codes_are_pairwise_distinct(self) -> None:
        codes = WE.WORD_ENGINE_FAILURE_CODES
        assert len(set(codes)) == len(codes), f"登记清单里有重复 error_code: {codes}"

    def test_instrumentation_failure_codes_are_pairwise_distinct(self) -> None:
        codes = [
            WI.WordCarrierGateError.error_code,
            WI.WordProbeEvidenceStaleError.error_code,
            WI.WordTokenAnchorError.error_code,
            WI.WordVisibleEquivalenceError.error_code,
            WI.WordTagReadbackError.error_code,
            WI.WordLockPolicyError.error_code,
        ]
        assert len(set(codes)) == len(codes)

    def test_every_engine_failure_kind_is_reachable(
        self, workdir: Path, plan_instrumented: WI.InstrumentedDocx,
        plan_substrate: Path, deficiency_substrate: Path,
        deficiency_instrumented: WI.InstrumentedDocx,
        plan_binding: WE.WordEngineBinding,
        deficiency_binding: WE.WordEngineBinding,
    ) -> None:
        observed: set[str] = set()

        def _record(fn: Any) -> None:
            try:
                fn()
            except Exception as exc:  # noqa: BLE001 —— 收集 error_code，随后断言集合
                code = getattr(exc, "error_code", None)
                assert code, f"{type(exc).__name__} 缺 error_code：无法分辨拒绝原因"
                observed.add(code)
            else:  # pragma: no cover - 任何一条没抛都是缺陷
                pytest.fail("期望 fail closed，但没有抛异常")

        # 1) carrier blocked
        def _carrier_blocked() -> None:
            payload = plan_contract_payload()
            contract = C.parse_contract(payload, adapter_id=PLAN_ID)
            WE.WordEngineBinding(
                contract=contract, entry_id=PLAN_ID,
                mode=WE.WordEngineMode.offline_candidate_validation,
                carrier_gate=C.load_excel_carrier_gate(),
            )

        # 2) approved bundle required
        def _bundle_required() -> None:
            plan_binding.assert_may_publish()

        # 3) tag missing
        def _tag_missing() -> None:
            path = workdir / "kind-tag-missing.docx"
            path.write_bytes(F222.read_bytes())
            _extract(path, plan_binding)

        # 4) tag unregistered
        def _unregistered() -> None:
            broken = _rewrite_document(
                plan_instrumented.instrumented_bytes,
                lambda xml: xml.replace(
                    f"gt:field:{PLAN_ID}:plan/scope",
                    f"gt:field:{PLAN_ID}:plan/ghost", 1,
                ),
            )
            path = workdir / "kind-unregistered.docx"
            path.write_bytes(broken)
            _extract(path, plan_binding)

        # 5) instance count
        def _instance_count() -> None:
            payload = plan_contract_payload()
            for field in payload["fields"]:
                if field["stable_field_key"] == "plan/entity_name":
                    field["instances"] = "one"
            path = workdir / "kind-instance.docx"
            path.write_bytes(plan_instrumented.instrumented_bytes)
            _extract(path, binding_for(payload, entry_id=PLAN_ID))

        # 6) hierarchy drift
        def _hierarchy() -> None:
            row_tag = f"gt:field:{DEF_ID}:rows/{ROW_UUIDS[0]}/deficiency"
            broken = _rewrite_document(
                deficiency_instrumented.instrumented_bytes,
                lambda xml: xml.replace(
                    f"gt:field:{DEF_ID}:deficiencies/title", row_tag, 1
                ),
            )
            path = workdir / "kind-hierarchy.docx"
            path.write_bytes(broken)
            _extract(path, deficiency_binding)

        # 7) row identity missing
        def _row_identity() -> None:
            WE.materialize_word_projection(
                substrate=deficiency_substrate,
                projection=_text_projection(
                    DEF_ID, {"rows/99999999-9999-4999-8999-999999999999/deficiency": "x"}
                ),
                output=workdir / "kind-row-identity.docx",
                binding=deficiency_binding,
                substrate_role=SubstrateRole.staged_result,
                artifact_kind=ArtifactKind.canonical,
                artifact_state=ArtifactState.staged,
            )

        # 8) word-only drift
        def _word_only() -> None:
            fingerprint = structure_fingerprint(plan_substrate.read_bytes())
            victim = next(
                block["text"] for block in fingerprint.outside_sdt_blocks
                if len(block["text"]) > 12
            )
            broken = _rewrite_document(
                plan_substrate.read_bytes(), lambda xml: xml.replace(victim, "", 1)
            )
            path = workdir / "kind-word-only.docx"
            path.write_bytes(broken)
            WE.verify_word_only_regions(
                before=plan_substrate, after=path, binding=plan_binding
            ).assert_equivalent()

        # 9) managed projection mismatch
        def _mismatch() -> None:
            projection = _plan_projection()
            output = workdir / "kind-mismatch.docx"
            WE.materialize_word_projection(
                substrate=plan_substrate, projection=projection, output=output,
                binding=plan_binding, substrate_role=SubstrateRole.staged_result,
                artifact_kind=ArtifactKind.canonical,
                artifact_state=ArtifactState.staged,
            )
            lying = _plan_projection(plan__bs_date=date(2019, 3, 4))
            WE.verify_word_before_commit(
                expected=lying, staged_result=output, substrate=plan_substrate,
                binding=plan_binding,
            ).assert_publishable()

        for trigger in (
            _carrier_blocked, _bundle_required, _tag_missing, _unregistered,
            _instance_count, _hierarchy, _row_identity, _word_only, _mismatch,
        ):
            _record(trigger)

        assert observed == set(WE.WORD_ENGINE_FAILURE_CODES), (
            "实测触发的失败 kind 集合与登记清单必须**双向**锁死：\n"
            f"  未触发（可能永久不可达）: {sorted(set(WE.WORD_ENGINE_FAILURE_CODES) - observed)}\n"
            f"  未登记（清单漏了）      : {sorted(observed - set(WE.WORD_ENGINE_FAILURE_CODES))}"
        )
        assert len(observed) == len(WE.WORD_ENGINE_FAILURE_CODES)


# ═══════════════════════════════════════════════════════════════════════════
# 权威模板只读
# ═══════════════════════════════════════════════════════════════════════════


class TestAuthorityTemplatesAreReadOnly:
    def test_templates_are_byte_identical_after_the_whole_suite(
        self, plan_instrumented: WI.InstrumentedDocx,
        deficiency_instrumented: WI.InstrumentedDocx,
    ) -> None:
        """Requirement 9.9：运行态不得写回模板库。哨兵是 Task 6 契约登记的 digest。"""
        assert _sha(F222.read_bytes()) == F222_SHA
        assert _sha(B30112.read_bytes()) == B30112_SHA
        # 注入产物与源必须**不同**，否则「没改模板」是因为根本没注入
        assert plan_instrumented.instrumented_sha256 != F222_SHA
        assert deficiency_instrumented.instrumented_sha256 != B30112_SHA

    def test_template_authority_root_is_the_single_source(self) -> None:
        from app.services.workpaper_sync.canonical_paths import TEMPLATE_ROOT

        assert WI.WORD_TEMPLATE_AUTHORITY_ROOT is TEMPLATE_ROOT
        assert WI.WORD_TEMPLATE_AUTHORITY_ROOT == TEMPLATES

    def test_reference_copy_is_not_an_authority(self) -> None:
        """`基础数据/致同通用审计程序及底稿模板…` 是已落后的参考副本，不得作真源。

        判据落在**路径构成**上而不是「那个目录是否存在」：参考副本可能不在某个
        工作树里，用 `exists()` 会让本判据变成 skip（skip 等于没有判据）。
        """
        root = WI.WORD_TEMPLATE_AUTHORITY_ROOT.resolve()
        parts = root.parts
        assert "基础数据" not in parts, f"权威模板根落在参考副本下: {root}"
        assert parts[-1] == "wp_templates" and parts[-2] == "backend", (
            f"权威模板根必须是 `backend/wp_templates/`，实得 {root}"
        )
        # 三份 probe 模板也必须真的落在权威根内（而不是被指到副本）
        for template in (F222, B30112):
            assert root in template.resolve().parents


class TestNoRuntimeStateSurfaceInEngine:
    """engine 模块本身没有任何写库/发布面（构造上不可能）。"""

    def test_engine_module_imports_no_session_or_repository(self) -> None:
        tree = ast.parse(Path(WE.__file__).read_text(encoding="utf-8"))
        forbidden_modules = {
            "app.services.workpaper_sync.repository",
            "app.services.workpaper_sync.content_mutation",
            "app.services.workpaper_sync.representations",
            "sqlalchemy",
        }
        hits: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in forbidden_modules:
                hits.append(f"L{node.lineno}:{node.module}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden_modules:
                        hits.append(f"L{node.lineno}:{alias.name}")
        assert hits == [], f"engine 引入了写库/发布面: {hits}"

    def test_engine_declares_no_revision_or_pointer_writer(self) -> None:
        source = Path(WE.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden = {
            "bump_content_revision",
            "set_entry_pointer",
            "create_representation",
            "finalize_candidate",
            "set_current_content_version",
        }
        hits = [
            f"L{node.lineno}:{node.attr}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr in forbidden
        ]
        hits += [
            f"L{node.lineno}:{node.id}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and node.id in forbidden
        ]
        assert hits == [], f"engine 出现 revision/pointer/representation 写入面: {hits}"
