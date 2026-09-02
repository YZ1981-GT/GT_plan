# -*- coding: utf-8 -*-
"""Task 15 守卫（纯域 / 无库）：唯一 `ContentMutationService.commit(...)` 与独立
`RepresentationService` 的形态判据、拒绝矩阵与 revision 域边界。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 15
Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.6, 6.18, 8.10, 8.12, 13.1
Properties: **P4**（业务版本与 representation generation 正交）/ **P5**（无悬空可见态）/
**P10**（单次 commit 与 representation 幂等）/ **P61**（所有 writer 进入唯一 revision 域）/
**P65**（projection 与同 revision representation 等值）/ **P67**（candidate 先行）

═══ 本文件与 `test_task15_content_mutation_pg.py` 的分工 ═══

原子性（单事务、rollback 零可见、pointer/revision 不变）**只能**在真库上判，全部在 PG
文件里。本文件负责能在纯域判死的四类：

1. **拒绝矩阵**：每条拒绝各自的异常类型 + 各自的消息文本。
   🔴 Task 12/13/14 连续三次实测：多条拒绝共用一个异常类且文案重叠时，短路其中一条会
   被另一条遮蔽 ⇒ 变异检验判 GREEN。因此这里既断类型、又断该条专属的文案片段。
2. **revision 域门面**：`RevisionLockedRepository` 对三个 revision 域方法恒抛，其余透传。
   这是 Property 4 的**构造式**实现 —— 纯表示路径不是「不该」碰 revision，而是碰不到。
3. **单事务见证的判定逻辑**：缺步骤 / 多事务 / 单事务三态各自可判（用真实
   `_TransactionWitness` + 假 session 只喂 xid，不连库）。
4. **唯一入口边界**：`bump_content_revision` / `set_current_content_version` 在
   `backend/app` 里的调用点**恰在** `content_mutation.py`；两个新模块零 `file_version` /
   `parsed_data['_version']`（Property 61 的静态半边，真 writer 迁移归 Task 18/19）。

═══ roundtrip 等值为什么用真 adapter 桩而不是 mock ═══

`_FakeExcelAdapter` 不是「让测试通过的 mock」：它是一个**真的**载体引擎替身 —— 把
projection 写进文件、再从文件读回来，因此 `_assert_roundtrip_equivalent` 走的是真实
执行路径（含类型规范化比较）。真正的 openpyxl/python-docx 引擎归 Tasks 36~38 / 59~61；
在它们落地前用 JSON 当载体格式，判据（等值/缺字段/多字段/word_only 排除）完全一样。
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys
import uuid
import zipfile
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Mapping

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync import conflicts as CF  # noqa: E402
from app.services.workpaper_sync import content_mutation as CM  # noqa: E402
from app.services.workpaper_sync import contracts as C  # noqa: E402
from app.services.workpaper_sync import merge as M  # noqa: E402
from app.services.workpaper_sync import representations as R  # noqa: E402
from app.services.workpaper_sync.adapters.base import (  # noqa: E402
    AdapterSideEffectError,
    FieldValue,
    MaterializeResult,
    Projection,
    SubstrateRole,
    UnmanagedRegionReport,
)
from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository  # noqa: E402
from app.services.workpaper_sync.conflicts import UnresolvedConflictError  # noqa: E402
from app.services.workpaper_sync.definitions import (  # noqa: E402
    PublishStage,
    marker_slot_spec,
)
from app.services.workpaper_sync.models import (  # noqa: E402
    ArtifactKind,
    ArtifactState,
    AuthorityModel,
    BundleSlot,
    BundleSlotSpec,
    DefinitionState,
)
from app.services.workpaper_sync.resolution import DefinitionBundleSnapshot  # noqa: E402

_SYNC_DIR = _BACKEND / "app" / "services" / "workpaper_sync"
_APP_DIR = _BACKEND / "app"
_CM_PY = _SYNC_DIR / "content_mutation.py"
_REP_PY = _SYNC_DIR / "representations.py"
_V151 = _BACKEND / "migrations" / "V151__workpaper_sync_content_application_bundle_scope.sql"

# 双哨兵：单哨兵会被历史空目录骗停。
assert (_BACKEND / "app" / "main.py").is_file(), "哨兵失效：backend/app/main.py 不存在"
assert _V151.is_file(), f"哨兵失效：{_V151} 不存在"

_HYP = settings(max_examples=50, deadline=None)


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


TEMPLATE_DEF = _d("task15-template")
INSTR_DEF = _d("task15-instrumentation")
ADAPTER_BUILD = _d("task15-adapter-build")
R1 = "11111111-1111-4111-8111-111111111111"
PERIOD = "header_block/period_label"
TOTAL = "header_block/total_amount"


def ek(row: str, leaf: str) -> str:
    return f"equity_changes/{row}/{leaf}"


# ═══════════════════════════════════════════════════════════════════════════
# 0. 契约 / bundle / projection 构造器
# ═══════════════════════════════════════════════════════════════════════════


def xlsx_payload(contract_id: str = "g7.disclosure.listed") -> dict[str, Any]:
    return {
        "schema_version": C.CONTRACT_SCHEMA_VERSION,
        "contract_id": contract_id,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "xlsx",
        "template_definition_sha256": TEMPLATE_DEF,
        "instrumentation_definition_sha256": INSTR_DEF,
        "template": {
            "relative_path": "G/G7 权益工具投资.xlsx",
            "template_sha256": _d("template-blob"),
            "normalized_structure_hash": _d("template-structure"),
        },
        "identity_carriers": ["hidden_sheet", "defined_name", "hidden_uuid_column"],
        "sheets": [
            {
                "sheet_key": "g7-disclosure",
                "excel_name": "G7 披露表",
                "locator": {"anchor": "defined_name_ref"},
                "tables": [
                    {
                        "table_key": "equity_changes",
                        "anchor": "A7",
                        "header_rows": 2,
                        "row_identity": {"kind": "field", "json_pointer": "/rows/*/rowUuid"},
                        "delete_policy": "tombstone",
                        "dynamic_columns": {
                            "identity": "{slot}_{seq}",
                            "source_ref": "源xlsx!B6:Z6",
                        },
                        "formula_mask": ["I8:I200"],
                        "fields": [
                            {
                                "stable_field_key": "equity_changes/{row_uuid}/name",
                                "json_pointer": "/rows/{row_uuid}/name",
                                "column_key": "name",
                                "cell": {"column": "G", "row_from": "row_identity"},
                                "mode": "editable",
                                "value_type": "text",
                                "source_ref": "源xlsx!G8",
                            },
                            {
                                "stable_field_key": "equity_changes/{row_uuid}/closing_amount",
                                "json_pointer": "/rows/{row_uuid}/closingAmount",
                                "column_key": "closing_amount",
                                "cell": {"column": "H", "row_from": "row_identity"},
                                "mode": "editable",
                                "value_type": "amount",
                                "source_ref": "源xlsx!H8",
                            },
                            {
                                "stable_field_key": "equity_changes/{row_uuid}/subtotal",
                                "json_pointer": "/rows/{row_uuid}/subtotal",
                                "column_key": "subtotal",
                                "cell": {"column": "I", "row_from": "row_identity"},
                                "mode": "formula",
                                "value_type": "amount",
                                "source_ref": "源xlsx!I8",
                            },
                        ],
                    },
                    {
                        "table_key": "header_block",
                        "anchor": "A1",
                        "header_rows": 1,
                        "fields": [
                            {
                                "stable_field_key": "header_block/period_label",
                                "json_pointer": "/header/periodLabel",
                                "column_key": "period_label",
                                "cell": {"column": "B", "row_from": 2},
                                "mode": "editable",
                                "value_type": "text",
                                "source_ref": "源xlsx!B2",
                            },
                            {
                                "stable_field_key": "header_block/total_amount",
                                "json_pointer": "/header/totalAmount",
                                "column_key": "total_amount",
                                "cell": {"column": "C", "row_from": 3},
                                "mode": "editable",
                                "value_type": "amount",
                                "source_ref": "源xlsx!C3",
                            },
                        ],
                    },
                ],
            }
        ],
    }


def docx_payload(contract_id: str = "f2.stocktake.plan") -> dict[str, Any]:
    """带 `word_only` 字段的 docx 契约 —— roundtrip 排除判据要用它。"""
    return {
        "schema_version": C.CONTRACT_SCHEMA_VERSION,
        "contract_id": contract_id,
        "semantic_version": "1.0.0-sdt1",
        "review_status": "reviewed",
        "document_type": "docx",
        "template_definition_sha256": TEMPLATE_DEF,
        "instrumentation_definition_sha256": INSTR_DEF,
        "template": {
            "relative_path": "F/F2 存货监盘计划.docx",
            "template_sha256": _d("docx-blob"),
            "normalized_structure_hash": _d("docx-structure"),
        },
        "identity_carriers": ["field_sdt_inline"],
        "fields": [
            {
                "stable_field_key": "plan/location",
                "json_pointer": "/plan/location",
                "sdt_tag": f"gt:field:{contract_id}:plan/location",
                "mode": "editable",
                "value_type": "text",
                "source_ref": "源docx!监盘地点",
            },
            {
                "stable_field_key": "plan/free_notes",
                "json_pointer": "/plan/freeNotes",
                "sdt_tag": f"gt:field:{contract_id}:plan/free_notes",
                "mode": "word_only",
                "value_type": "text",
                "source_ref": "源docx!补充说明",
            },
        ],
    }


@pytest.fixture(scope="module")
def xc() -> C.SyncContract:
    return C.parse_contract(xlsx_payload())


@pytest.fixture(scope="module")
def dc() -> C.SyncContract:
    return C.parse_contract(docx_payload())


def proj(contract: C.SyncContract, values: Mapping[str, Any]) -> Projection:
    index = M.ContractIndex(contract)
    fields: dict[str, FieldValue] = {}
    for key, raw in values.items():
        loc = index.resolve(key)
        fields[key] = FieldValue(
            stable_key=key,
            value=raw,
            value_type=loc.value_type,
            mode=loc.mode,
            row_key=loc.row_key or None,
        )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=fields,
    )


def definition_slots(contract: C.SyncContract) -> dict[BundleSlot, BundleSlotSpec]:
    """三 definition child 的 typed slots（`projection_contract` 形态）。"""
    return {
        BundleSlot.template: BundleSlotSpec(
            BundleSlot.template, "definition", f"definition:{uuid.uuid4()}", TEMPLATE_DEF
        ),
        BundleSlot.instrumentation: BundleSlotSpec(
            BundleSlot.instrumentation, "definition", f"definition:{uuid.uuid4()}", INSTR_DEF
        ),
        BundleSlot.contract: BundleSlotSpec(
            BundleSlot.contract,
            "definition",
            f"definition:{uuid.uuid4()}",
            contract.canonical_sha256,
        ),
    }


def bundle_snapshot(
    contract: C.SyncContract | None = None,
    *,
    authority: AuthorityModel = AuthorityModel.projection_contract,
    state: DefinitionState = DefinitionState.approved,
    slots: Mapping[BundleSlot, BundleSlotSpec] | None = None,
    bundle_sha256: str | None = None,
    authority_sha256: str | None = None,
) -> DefinitionBundleSnapshot:
    if slots is None:
        if authority is AuthorityModel.projection_contract:
            assert contract is not None
            slots = definition_slots(contract)
        else:
            slots = {
                BundleSlot.template: BundleSlotSpec(
                    BundleSlot.template, "definition", f"definition:{uuid.uuid4()}",
                    TEMPLATE_DEF,
                ),
                BundleSlot.instrumentation: marker_slot_spec(BundleSlot.instrumentation),
                BundleSlot.contract: marker_slot_spec(BundleSlot.contract),
            }
    return DefinitionBundleSnapshot(
        bundle_id=uuid.uuid4(),
        bundle_sha256=bundle_sha256 or _d("task15-bundle"),
        schema_version="definition-bundle:v1",
        state=state,
        authority_model=authority,
        authority_model_definition_id=uuid.uuid4(),
        authority_model_definition_sha256=authority_sha256 or _d("task15-authority"),
        slots=dict(slots),
    )


def plan(
    *,
    bundle: DefinitionBundleSnapshot,
    contract: C.SyncContract | None,
    document_type: str = "xlsx",
    expected_revision: int = 3,
    substrate_path: Path | None = None,
    substrate_kind: ArtifactKind = ArtifactKind.canonical,
    substrate_state: ArtifactState = ArtifactState.published,
    substrate_role: SubstrateRole = SubstrateRole.published_representation,
    source: str = "html",
    reason: str = "content_commit",
    **kwargs: Any,
) -> CM.ContentCommitPlan:
    return CM.ContentCommitPlan(
        project_id=uuid.uuid4(),
        wp_id=uuid.uuid4(),
        entry_id="g7.disclosure.listed",
        source=CM.ContentSource(source),
        expected_revision=expected_revision,
        bundle=bundle,
        adapter_id="g7.disclosure.listed",
        adapter_build_digest=ADAPTER_BUILD,
        document_type=document_type,
        substrate_path=substrate_path or Path("substrate.xlsx"),
        substrate_role=substrate_role,
        substrate_kind=substrate_kind,
        substrate_state=substrate_state,
        contract=contract,
        reason=reason,
        **kwargs,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. adapter 桩（真写真读，不是 mock）
# ═══════════════════════════════════════════════════════════════════════════


class _FakeExcelAdapter:
    """把 projection 真写进文件再真读回来的载体替身。

    `drop_keys` / `extra_values` / `mutate` 三个开关用于制造 roundtrip 反例
    （缺字段 / 多字段 / 值漂移），它们改的是**写盘内容**，因此
    `_assert_roundtrip_equivalent` 是在真实执行上判定，不是被喂了假返回值。
    """

    adapter_id = "g7.disclosure.listed"
    document_type = "xlsx"
    contract_version = "1.0.0"

    def __init__(
        self,
        *,
        drop_keys: tuple[str, ...] = (),
        extra_values: Mapping[str, Any] | None = None,
        mutate: Mapping[str, Any] | None = None,
        unmanaged_equivalent: bool = True,
    ) -> None:
        self.drop_keys = drop_keys
        self.extra_values = dict(extra_values or {})
        self.mutate = dict(mutate or {})
        self.unmanaged_equivalent = unmanaged_equivalent
        self.materialize_calls = 0
        self.extract_calls = 0

    # ── 协议方法 ────────────────────────────────────────────────────
    async def read_current_projection(self, ctx: Any) -> Projection:  # pragma: no cover
        raise NotImplementedError

    async def stage_projection_mutation(  # pragma: no cover
        self, ctx: Any, merged: Projection, *, expected_revision: int
    ) -> Any:
        raise NotImplementedError

    def materialize(
        self, *, substrate: Path, projection: Projection, output: Path, contract: Any
    ) -> MaterializeResult:
        self.materialize_calls += 1
        payload: dict[str, Any] = {}
        for key, value in projection.values.items():
            if key in self.drop_keys:
                continue
            payload[key] = {
                "value": self.mutate.get(key, _plain(value.value)),
                "value_type": value.value_type.value,
                "mode": value.mode.value,
                "row_key": value.row_key,
            }
        for key, value in self.extra_values.items():
            payload[key] = value
        # 真 OOXML 容器：`publish_representation` 会跑完 Task 11 的全部安全门
        # （magic/entry 名/体积/必需部件/内部类型标记）。写裸 JSON 会在 zip_magic
        # 就被拒 —— 那样测到的是「桩不合法」，不是本任务的判据。
        blob = _minimal_ooxml(
            projection.document_type,
            extra={
                "_gt_sync/projection.json": json.dumps(
                    {"contract_id": projection.contract_id, "values": payload},
                    sort_keys=True,
                    ensure_ascii=False,
                ).encode("utf-8")
            },
        )
        output.write_bytes(blob)
        digest = hashlib.sha256(blob).hexdigest()
        return MaterializeResult(
            output_path=output,
            document_type=projection.document_type,
            artifact_sha256=digest,
            structure_hash=_d("structure"),
            identity_inventory_sha256=_d("identity"),
            managed_field_count=len(payload),
        )

    def extract(self, *, artifact: Path, contract: C.SyncContract) -> Projection:
        self.extract_calls += 1
        with zipfile.ZipFile(artifact) as zf:
            raw = json.loads(zf.read("_gt_sync/projection.json").decode("utf-8"))
        values: dict[str, FieldValue] = {}
        for key, item in raw["values"].items():
            values[key] = FieldValue(
                stable_key=key,
                value=item["value"],
                value_type=C.ValueType(item["value_type"]),
                mode=C.FieldMode(item["mode"]),
                row_key=item.get("row_key"),
            )
        return Projection(
            contract_id=raw["contract_id"],
            semantic_version=contract.semantic_version,
            document_type=contract.document_type,
            values=values,
        )

    def verify_unmanaged_regions(
        self, *, before: Path, after: Path, contract: Any
    ) -> UnmanagedRegionReport:
        if self.unmanaged_equivalent:
            return UnmanagedRegionReport(
                equivalent=True, inspected_aspects=("formula", "style", "drawing")
            )
        return UnmanagedRegionReport(
            equivalent=False,
            inspected_aspects=("formula", "style", "drawing"),
            first_difference="xl/drawings/drawing1.xml 被重写",
        )


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


_CONTENT_TYPES: Final[bytes] = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    b'<Default Extension="xml" ContentType="application/xml"/></Types>'
)


def _minimal_ooxml(document_type: str, *, extra: Mapping[str, bytes] | None = None) -> bytes:
    """能通过 Task 11 全部安全门的最小 OOXML 容器。

    内部类型标记（`xl/workbook.xml` / `word/document.xml`）是**类型真源**：Task 7 fs7
    实测过「xlsx 改名 .docx」会被内部部件识破，所以这里按 document_type 写对应部件。
    """
    marker = "xl/workbook.xml" if document_type == "xlsx" else "word/document.xml"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr(marker, b'<?xml version="1.0"?><root/>')
        for name, payload in (extra or {}).items():
            zf.writestr(name, payload)
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════════════════
# 2. bundle 拒绝矩阵（Requirement 2.3：四条禁令各自可分辨）
# ═══════════════════════════════════════════════════════════════════════════


class TestBundleRejectionMatrix:
    """approved / slot omission / 空 slot / 全零 digest / marker 冒充 contract 五条互不遮蔽。

    🔴 每条既断**类型**又断**该条专属文案**。只断类型时，把 slot 形态判据短路掉之后
    approved 判据会顶上来把它遮蔽（Task 12 的 M34、Task 14 的 M71/M72 都是这个形态）。
    """

    def test_approved_bundle_passes(self, xc: C.SyncContract) -> None:
        """反向：门不能是恒红的死路，否则「合法 bundle 可用」这条判据不可达。"""
        R.assert_bundle_snapshot_finalizable(bundle_snapshot(xc))

    def test_unapproved_bundle_rejected(self, xc: C.SyncContract) -> None:
        with pytest.raises(R.RepresentationBundleError) as exc:
            R.assert_bundle_snapshot_finalizable(
                bundle_snapshot(xc, state=DefinitionState.candidate)
            )
        assert "approved" in str(exc.value)

    def test_slot_omission_rejected(self, xc: C.SyncContract) -> None:
        slots = definition_slots(xc)
        slots.pop(BundleSlot.instrumentation)
        with pytest.raises(R.RepresentationSlotError) as exc:
            R.assert_bundle_snapshot_finalizable(bundle_snapshot(xc, slots=slots))
        assert "缺 typed slot" in str(exc.value)
        assert "instrumentation" in str(exc.value)

    def test_empty_slot_type_rejected(self, xc: C.SyncContract) -> None:
        slots = definition_slots(xc)
        slots[BundleSlot.contract] = BundleSlotSpec(
            BundleSlot.contract, "   ", "definition:x", xc.canonical_sha256
        )
        with pytest.raises(R.RepresentationSlotError) as exc:
            R.assert_bundle_snapshot_finalizable(bundle_snapshot(xc, slots=slots))
        assert "slot_type" in str(exc.value)

    def test_empty_slot_ref_rejected(self, xc: C.SyncContract) -> None:
        slots = definition_slots(xc)
        slots[BundleSlot.template] = BundleSlotSpec(
            BundleSlot.template, "definition", "", TEMPLATE_DEF
        )
        with pytest.raises(R.RepresentationSlotError) as exc:
            R.assert_bundle_snapshot_finalizable(bundle_snapshot(xc, slots=slots))
        assert "slot_ref" in str(exc.value)

    @pytest.mark.parametrize("bad", ["", "0" * 64, "ZZ" * 32, "abc"])
    def test_invalid_slot_digest_rejected(self, xc: C.SyncContract, bad: str) -> None:
        """空串 / 全零 / 非小写 hex / 长度不足全部拒绝（Requirement 2.3 原文四种）。"""
        slots = definition_slots(xc)
        slots[BundleSlot.instrumentation] = BundleSlotSpec(
            BundleSlot.instrumentation, "definition", "definition:x", bad
        )
        with pytest.raises(R.RepresentationSlotError) as exc:
            R.assert_bundle_snapshot_finalizable(bundle_snapshot(xc, slots=slots))
        assert "digest 非法" in str(exc.value)

    def test_all_zero_bundle_digest_rejected(self, xc: C.SyncContract) -> None:
        with pytest.raises(R.RepresentationBundleError) as exc:
            R.assert_bundle_snapshot_finalizable(
                bundle_snapshot(xc, bundle_sha256="0" * 64)
            )
        assert "canonical digest 非法" in str(exc.value)

    def test_all_zero_authority_digest_rejected(self, xc: C.SyncContract) -> None:
        with pytest.raises(R.RepresentationBundleError) as exc:
            R.assert_bundle_snapshot_finalizable(
                bundle_snapshot(xc, authority_sha256="0" * 64)
            )
        assert "authority model definition digest 非法" in str(exc.value)

    def test_marker_cannot_impersonate_per_entry_contract(self, xc: C.SyncContract) -> None:
        """`projection_contract` 的 contract slot 必须是 approved definition。"""
        slots = definition_slots(xc)
        slots[BundleSlot.contract] = marker_slot_spec(BundleSlot.contract)
        with pytest.raises(R.RepresentationSlotError) as exc:
            R.assert_bundle_snapshot_finalizable(bundle_snapshot(xc, slots=slots))
        assert "marker 不得冒充" in str(exc.value)

    def test_custom_authority_may_use_typed_null_markers(self) -> None:
        """反向：custom/opaque 用版本化 typed null marker 是**合法**形态（不得一刀切拒绝）。"""
        R.assert_bundle_snapshot_finalizable(
            bundle_snapshot(None, authority=AuthorityModel.custom_authoritative_ooxml)
        )

    def test_rejection_types_are_pairwise_distinct(self) -> None:
        """两个类型互不继承 —— 否则 `pytest.raises` 的类型断言可被父类吞掉。"""
        assert not issubclass(R.RepresentationSlotError, R.RepresentationBundleError)
        assert not issubclass(R.RepresentationBundleError, R.RepresentationSlotError)
        assert issubclass(R.RepresentationSlotError, R.RepresentationError)
        assert issubclass(R.RepresentationBundleError, R.RepresentationError)


# ═══════════════════════════════════════════════════════════════════════════
# 3. revision 域门面（Property 4 的构造式实现）
# ═══════════════════════════════════════════════════════════════════════════


class _RepoSpy:
    """只记录调用的仓储替身（门面透传判据用）。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __getattr__(self, name: str):
        def _record(*args: Any, **kwargs: Any) -> str:
            self.calls.append(name)
            return name

        return _record


class TestRevisionLockedRepository:
    """纯表示路径**碰不到** revision 域 —— 不是「不该碰」。"""

    @pytest.mark.parametrize(
        "method", sorted(CM.REVISION_DOMAIN_WRITE_METHODS)
    )
    def test_revision_domain_methods_are_unreachable(self, method: str) -> None:
        locked = CM.RevisionLockedRepository(_RepoSpy())  # type: ignore[arg-type]
        with pytest.raises(CM.RevisionBumpForbiddenError) as exc:
            getattr(locked, method)
        assert method in str(exc.value)
        assert "content revision" in str(exc.value)

    def test_other_methods_pass_through(self) -> None:
        """反向：门面不是「什么都不让做」，否则纯表示路径根本无法工作。"""
        spy = _RepoSpy()
        locked = CM.RevisionLockedRepository(spy)  # type: ignore[arg-type]
        for name in (
            "register_artifact",
            "create_representation",
            "set_entry_pointer",
            "finalize_candidate",
        ):
            assert getattr(locked, name)() == name
        assert spy.calls == [
            "register_artifact",
            "create_representation",
            "set_entry_pointer",
            "finalize_candidate",
        ]

    def test_forbidden_set_covers_the_three_revision_writers(self) -> None:
        """禁用名单必须与 repository 的真实 revision 域写方法**双向**对齐。

        只声明名单不校验，等于名单可以被悄悄改空。这里反查 `repository.py` 里所有
        动 `content_revision` / `current_content_version_id` 的方法，逐个要求进名单。
        """
        body = (_SYNC_DIR / "repository.py").read_text(encoding="utf-8")
        revision_writers = {
            name
            for name, chunk in _method_bodies(body).items()
            if "content_revision = content_revision + 1" in chunk
            or "SET current_content_version_id" in chunk
            or "WorkpaperContentVersion(" in chunk
        }
        assert revision_writers, "反查不到任何 revision 域写方法 —— 判据失去锚点"
        assert revision_writers <= CM.REVISION_DOMAIN_WRITE_METHODS, (
            f"以下 revision 域写方法未进禁用名单: "
            f"{sorted(revision_writers - CM.REVISION_DOMAIN_WRITE_METHODS)}"
        )

    def test_representation_service_wraps_even_a_bare_repository(self) -> None:
        """构造 `RepresentationService` 时即便传裸 repository 也拿不到 revision 域。"""
        svc = R.RepresentationService(
            session=object(),  # type: ignore[arg-type]
            repository=_RepoSpy(),  # type: ignore[arg-type]
            artifacts=object(),  # type: ignore[arg-type]
            resolution=object(),  # type: ignore[arg-type]
        )
        inner = svc._repo  # noqa: SLF001 - 边界判据必须看真实持有对象
        assert isinstance(inner, CM.RevisionLockedRepository)
        with pytest.raises(CM.RevisionBumpForbiddenError):
            inner.bump_content_revision  # noqa: B018


def _method_bodies(source: str) -> dict[str, str]:
    """把 `async def name(...)` 切成 `{name: body}`（按缩进定界，不用固定字符窗口）。"""
    out: dict[str, str] = {}
    lines = source.splitlines(keepends=True)
    starts = [
        (n, m.group(1))
        for n, line in enumerate(lines)
        if (m := re.match(r"\s*(?:async\s+)?def\s+(\w+)\s*\(", line))
    ]
    for idx, (start, name) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        out[name] = "".join(lines[start:end])
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 4. 单事务见证与 commit 计数
# ═══════════════════════════════════════════════════════════════════════════


class _XidSession:
    """只回答 `pg_current_xact_id()` 的假 session（不连库，仅测判定逻辑）。"""

    def __init__(self, xids: list[str]) -> None:
        self._xids = list(xids)
        self.commits = 0

    async def execute(self, *_args: Any, **_kwargs: Any) -> Any:
        value = self._xids.pop(0) if len(self._xids) > 1 else self._xids[0]

        class _R:
            @staticmethod
            def scalar_one() -> str:
                return value

        return _R()

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.asyncio
class TestTransactionWitness:
    """三态各自可判：单事务通过 / 缺步骤 / 多事务。"""

    async def test_single_transaction_passes(self) -> None:
        witness = CM._TransactionWitness()  # noqa: SLF001
        session = _XidSession(["4242"])
        for step in CM.CONTENT_COMMIT_STEPS:
            await witness.stamp(session, step)  # type: ignore[arg-type]
        witness.assert_single_transaction()
        assert witness.transaction_ids == ("4242",)

    async def test_missing_step_is_its_own_error_type(self) -> None:
        """删掉 representation 写入 ⇒ 缺步骤，而不是「事务未分裂所以没问题」。"""
        witness = CM._TransactionWitness()  # noqa: SLF001
        session = _XidSession(["4242"])
        for step in CM.CONTENT_COMMIT_STEPS:
            if step == "representation":
                continue
            await witness.stamp(session, step)  # type: ignore[arg-type]
        with pytest.raises(CM.TransactionStepMissingError) as exc:
            witness.assert_single_transaction()
        assert "representation" in str(exc.value)

    async def test_split_transaction_is_detected(self) -> None:
        """中途 commit ⇒ 后续步骤落到新 xid ⇒ TransactionSplitError。"""
        witness = CM._TransactionWitness()  # noqa: SLF001
        session = _XidSession(["100", "100", "777", "777", "777"])
        for step in CM.CONTENT_COMMIT_STEPS:
            await witness.stamp(session, step)  # type: ignore[arg-type]
        with pytest.raises(CM.TransactionSplitError) as exc:
            witness.assert_single_transaction()
        assert "2 个数据库事务" in str(exc.value)

    async def test_two_error_types_are_pairwise_distinct(self) -> None:
        assert not issubclass(CM.TransactionSplitError, CM.TransactionStepMissingError)
        assert not issubclass(CM.TransactionStepMissingError, CM.TransactionSplitError)

    async def test_commit_latch_allows_exactly_one_commit(self) -> None:
        latch = CM._CommitLatch()  # noqa: SLF001
        session = _XidSession(["1"])
        await latch.commit_once(session)  # type: ignore[arg-type]
        assert latch.count == 1 and session.commits == 1
        with pytest.raises(CM.DoubleCommitError):
            await latch.commit_once(session)  # type: ignore[arg-type]
        assert session.commits == 1, "第二次提交必须在真正 commit 之前被拦住"

    @given(
        st.lists(st.sampled_from(["11", "22", "33"]), min_size=5, max_size=5)
    )
    @_HYP
    async def test_property_witness_passes_iff_all_steps_share_one_xid(
        self, xids: list[str]
    ) -> None:
        """Property：五步齐全时，「通过」等价于「xid 集合大小为 1」。

        判据是**等价**而不是单向：xid 全等必须通过（否则单事务提交是恒红死路），
        xid 有分裂必须抛（否则「先提交 projection-only version 再补一次 revision」
        这条被明令禁止的形态无人拦）。

        **Validates: Requirements 2.4**
        """
        witness = CM._TransactionWitness()  # noqa: SLF001
        for step, xid in zip(CM.CONTENT_COMMIT_STEPS, xids):
            await witness.stamp(_XidSession([xid]), step)  # type: ignore[arg-type]
        if len(set(xids)) == 1:
            witness.assert_single_transaction()
        else:
            with pytest.raises(CM.TransactionSplitError):
                witness.assert_single_transaction()


# ═══════════════════════════════════════════════════════════════════════════
# 5. plan / mutation 形态
# ═══════════════════════════════════════════════════════════════════════════


class TestPlanAndMutationShape:
    def test_plan_carries_no_mutation_surface(self, xc: C.SyncContract) -> None:
        """plan 会被写进 evidence 快照 —— 它握着 session 就等于边界只是注释。"""
        p = plan(bundle=bundle_snapshot(xc), contract=xc)
        assert p.target_revision == p.expected_revision + 1

        class _Session:
            def commit(self) -> None:  # pragma: no cover
                ...

        with pytest.raises(AdapterSideEffectError):
            CM.ContentCommitPlan(
                project_id=p.project_id,
                wp_id=p.wp_id,
                entry_id=p.entry_id,
                source=p.source,
                expected_revision=p.expected_revision,
                bundle=p.bundle,
                adapter_id=p.adapter_id,
                adapter_build_digest=p.adapter_build_digest,
                document_type=p.document_type,
                substrate_path=p.substrate_path,
                substrate_role=p.substrate_role,
                substrate_kind=p.substrate_kind,
                substrate_state=p.substrate_state,
                contract=_Session(),  # type: ignore[arg-type]
            )

    # 🔴 `upload` / `wopi` 从这张反例表里搬走了：Task 19 的 V152 把它们**加进**了
    #    `ck_wpcv_source`（WOPI PutFile 与离线上传迁入统一 revision 域时需要各自的
    #    审计分桶，折进 `onlyoffice` 会让 evidence/timeline 事后分不出走的哪条协议）。
    #    它们现在是**合法**值，正面断言在
    #    `test_task19_writer_migration.py::test_the_content_source_vocabulary_matches_the_migration`。
    @pytest.mark.parametrize("bad", ["", "HTML", "definition_upgrade", "offline_upload"])
    def test_source_vocabulary_is_closed(self, bad: str) -> None:
        """`source` 值域 = `ck_wpcv_source`，构造点即拒绝（不等 DB 抛 IntegrityError）。"""
        with pytest.raises(CM.ContentMutationError) as exc:
            CM.ContentSource(bad)
        assert "ck_wpcv_source" in str(exc.value)

    def test_source_vocabulary_matches_the_owning_migration(self) -> None:
        """封闭词表与迁移文件**双向**锁死（改一侧必红）。

        🔴 判据取的是**最后一个修改 `ck_wpcv_source` 的迁移**，不是写死 V151：
        V152 放宽了这条 CHECK（加 `upload` / `wopi`），只读 V151 会把「生产已放宽」
        误判成「代码漂移」。按迁移号取最大值 = 数据库上真正生效的那份。
        """
        migrations = sorted(
            (path for path in (_BACKEND / "migrations").glob("V*.sql")
             if "ck_wpcv_source CHECK" in path.read_text(encoding="utf-8")),
            key=lambda path: int(re.match(r"V(\d+)__", path.name).group(1)),  # type: ignore[union-attr]
        )
        assert migrations, "没有任何迁移声明 ck_wpcv_source —— 判据失去锚点"
        sql = migrations[-1].read_text(encoding="utf-8")
        match = re.search(
            r"ck_wpcv_source CHECK \(\s*source IN \(([^)]*)\)", sql, re.S
        )
        assert match, f"{migrations[-1].name} 里 ck_wpcv_source 形态变了 —— 判据失去锚点"
        declared = {
            value.strip().strip("'")
            for value in match.group(1).split(",")
            if value.strip()
        }
        assert declared == set(CM._ALLOWED_SOURCES), (  # noqa: SLF001
            f"source 词表漂移：{migrations[-1].name}={sorted(declared)} "
            f"vs 代码={sorted(CM._ALLOWED_SOURCES)}"  # noqa: SLF001
        )

    def test_definition_upgrade_reason_is_rejected_on_business_commit(
        self, xc: C.SyncContract
    ) -> None:
        """业务 commit 不得冒充 `definition_upgrade` —— 那条路径属 RepresentationService。"""
        with pytest.raises(CM.ContentMutationError) as exc:
            plan(bundle=bundle_snapshot(xc), contract=xc, reason="definition_upgrade")
        assert "RepresentationService" in str(exc.value)

    def test_mutation_requires_exactly_one_content_form(self, xc: C.SyncContract) -> None:
        with pytest.raises(CM.AuthorityModelMismatchError):
            CM.BusinessMutation()
        with pytest.raises(CM.AuthorityModelMismatchError):
            CM.BusinessMutation(
                projection=proj(xc, {PERIOD: "2025 年度"}), authoritative_payload=b"x"
            )
        assert CM.BusinessMutation(projection=proj(xc, {PERIOD: "2025 年度"}))
        assert CM.BusinessMutation(authoritative_payload=b"xlsx-bytes")

    def test_negative_expected_revision_rejected(self, xc: C.SyncContract) -> None:
        with pytest.raises(CM.ContentMutationError):
            plan(bundle=bundle_snapshot(xc), contract=xc, expected_revision=-1)


# ═══════════════════════════════════════════════════════════════════════════
# 6. authority model ↔ 内容形态 ↔ contract 三向自洽
# ═══════════════════════════════════════════════════════════════════════════


def _service() -> CM.ContentMutationService:
    return CM.ContentMutationService(
        session=object(),  # type: ignore[arg-type]
        repository=object(),  # type: ignore[arg-type]
        artifacts=object(),  # type: ignore[arg-type]
        resolution=object(),  # type: ignore[arg-type]
    )


class TestAuthorityShapeMatrix:
    """Requirement 2.11 / 3.3 / 6.19 的五条拒绝各自可分辨。"""

    def test_projection_based_requires_projection(self, xc: C.SyncContract) -> None:
        with pytest.raises(CM.AuthorityModelMismatchError) as exc:
            _service()._assert_authority_shape(  # noqa: SLF001
                plan(bundle=bundle_snapshot(xc), contract=xc),
                CM.BusinessMutation(authoritative_payload=b"x"),
                _FakeExcelAdapter(),
            )
        assert "必须提交业务 projection" in str(exc.value)

    def test_projection_based_requires_contract(self, xc: C.SyncContract) -> None:
        with pytest.raises(CM.ContractRequiredError) as exc:
            _service()._assert_authority_shape(  # noqa: SLF001
                plan(bundle=bundle_snapshot(xc), contract=None),
                CM.BusinessMutation(projection=proj(xc, {PERIOD: "x"})),
                _FakeExcelAdapter(),
            )
        assert "缺 per-entry contract" in str(exc.value)

    def test_projection_based_requires_adapter(self, xc: C.SyncContract) -> None:
        """判据落在**另一条文案**上：与「缺 contract」共用类型，必须能区分。"""
        with pytest.raises(CM.ContractRequiredError) as exc:
            _service()._assert_authority_shape(  # noqa: SLF001
                plan(bundle=bundle_snapshot(xc), contract=xc),
                CM.BusinessMutation(projection=proj(xc, {PERIOD: "x"})),
                None,
            )
        assert "必须给 adapter" in str(exc.value)

    def test_custom_authority_rejects_projection(self, xc: C.SyncContract) -> None:
        with pytest.raises(CM.AuthorityModelMismatchError) as exc:
            _service()._assert_authority_shape(  # noqa: SLF001
                plan(
                    bundle=bundle_snapshot(
                        None, authority=AuthorityModel.custom_authoritative_ooxml
                    ),
                    contract=None,
                ),
                CM.BusinessMutation(projection=proj(xc, {PERIOD: "x"})),
                None,
            )
        assert "authoritative_payload" in str(exc.value)

    def test_custom_authority_rejects_contract(self, xc: C.SyncContract) -> None:
        with pytest.raises(CM.AuthorityModelMismatchError) as exc:
            _service()._assert_authority_shape(  # noqa: SLF001
                plan(
                    bundle=bundle_snapshot(
                        None, authority=AuthorityModel.opaque_single_onlyoffice
                    ),
                    contract=xc,
                ),
                CM.BusinessMutation(authoritative_payload=b"x"),
                None,
            )
        assert "typed null marker" in str(exc.value)

    def test_valid_shapes_pass(self, xc: C.SyncContract) -> None:
        """反向：两条合法形态都必须通过，否则拒绝矩阵是恒红死路。"""
        _service()._assert_authority_shape(  # noqa: SLF001
            plan(bundle=bundle_snapshot(xc), contract=xc),
            CM.BusinessMutation(projection=proj(xc, {PERIOD: "2025 年度"})),
            _FakeExcelAdapter(),
        )
        _service()._assert_authority_shape(  # noqa: SLF001
            plan(
                bundle=bundle_snapshot(
                    None, authority=AuthorityModel.custom_authoritative_ooxml
                ),
                contract=None,
            ),
            CM.BusinessMutation(authoritative_payload=b"xlsx"),
            None,
        )

    def test_unregistered_projection_key_is_rejected(self, xc: C.SyncContract) -> None:
        """projection 里出现 contract 未登记的 key ⇒ fail closed（禁位置猜测）。"""
        from app.services.workpaper_sync.adapters.base import ProjectionShapeError

        bad = Projection(
            contract_id=xc.contract_id,
            semantic_version=xc.semantic_version,
            document_type=xc.document_type,
            values={
                "header_block/unknown_field": FieldValue(
                    stable_key="header_block/unknown_field",
                    value="x",
                    value_type=C.ValueType.text,
                    mode=C.FieldMode.editable,
                )
            },
        )
        with pytest.raises(ProjectionShapeError):
            _service()._assert_authority_shape(  # noqa: SLF001
                plan(bundle=bundle_snapshot(xc), contract=xc),
                CM.BusinessMutation(projection=bad),
                _FakeExcelAdapter(),
            )


# ═══════════════════════════════════════════════════════════════════════════
# 7. 冲突门（不自动选边）
# ═══════════════════════════════════════════════════════════════════════════


class TestConflictGate:
    """未裁决冲突一律拒绝提交 —— merge 域不选边，commit 也不替它选。

    **2026-08-27（Task 27）追加的第二段**：覆盖率过了还不够，提交的 projection 必须
    **真的是**裁决折叠的结果。Task 26 收口审计抓到的静默错值路径就是「覆盖率过了、
    落库的仍是 `merge.merged`（每个冲突字段保留 current 侧值）」。本域的判据从「覆盖率」
    升级成「覆盖率 + 独立重算逐字节等值」，两段各自可证伪。
    """

    def _conflicting(self, xc: C.SyncContract) -> M.MergeOutcome:
        return M.merge_projections(
            base=proj(xc, {TOTAL: 100}),
            current=proj(xc, {TOTAL: 200}),
            incoming=proj(xc, {TOTAL: 300}),
            contract=xc,
        )

    def test_unresolved_conflicts_block_commit(self, xc: C.SyncContract) -> None:
        outcome = self._conflicting(xc)
        assert outcome.has_conflicts
        with pytest.raises(UnresolvedConflictError) as exc:
            _service()._settle_projection(  # noqa: SLF001
                plan(bundle=bundle_snapshot(xc), contract=xc),
                CM.BusinessMutation(projection=outcome.merged, merge=outcome),
            )
        assert "未裁决冲突" in str(exc.value)

    def test_resolved_merge_passes(self, xc: C.SyncContract) -> None:
        """反向：裁决齐全且已折叠后必须能提交，否则冲突门是恒红死路。"""
        outcome = self._conflicting(xc)
        record = outcome.conflicts.records[0]
        choice = CF.ResolutionChoice(
            stable_field_key=record.locator.stable_field_key,
            kind=CF.ResolutionKind.take_incoming,
            row_key=record.locator.row_key,
            oo_location=record.locator.oo_location,
        )
        settled = M.apply_resolutions(outcome, [choice], contract=xc)
        assert settled.get(TOTAL) is not None and settled.get(TOTAL).value == 300, (
            "裁决为 take_incoming 后 merged 必须取 incoming 值"
        )
        got = _service()._settle_projection(  # noqa: SLF001
            plan(bundle=bundle_snapshot(xc), contract=xc),
            CM.BusinessMutation(
                projection=settled, merge=outcome, resolution_choices=(choice,)
            ),
        )
        assert got is settled

    def test_unfolded_projection_is_rejected_even_with_full_coverage(
        self, xc: C.SyncContract
    ) -> None:
        """🔴 覆盖率齐全但提交 `merge.merged` ⇒ 必须打红（Task 26 审计的静默错值路径）。

        前提先自证：`merge.merged` 与折叠结果**确实不同**（否则拦的是无害路径）。
        """
        outcome = self._conflicting(xc)
        record = outcome.conflicts.records[0]
        choice = CF.ResolutionChoice(
            stable_field_key=record.locator.stable_field_key,
            kind=CF.ResolutionKind.take_incoming,
            row_key=record.locator.row_key,
            oo_location=record.locator.oo_location,
        )
        folded = M.apply_resolutions(outcome, [choice], contract=xc)
        assert outcome.merged.get(TOTAL).value == 200, "merged 保持 current 侧（Task 14 语义）"
        assert folded.get(TOTAL).value == 300
        with pytest.raises(CM.AdjudicationNotFoldedError) as exc:
            _service()._settle_projection(  # noqa: SLF001
                plan(bundle=bundle_snapshot(xc), contract=xc),
                CM.BusinessMutation(
                    projection=outcome.merged,  # ← 未折叠
                    merge=outcome,
                    resolution_choices=(choice,),
                ),
            )
        assert exc.value.error_code == "adjudication_projection_not_folded"
        assert not issubclass(CM.AdjudicationNotFoldedError, UnresolvedConflictError), (
            "两条判据必须是两个类型 —— 共用 error_code 会让靠前的分支永久不可达"
        )

    def test_adjudication_without_contract_is_rejected(
        self, xc: C.SyncContract
    ) -> None:
        """缺 contract 时无法重算折叠 ⇒ 只能 fail closed，不得盲信调用方。"""
        outcome = self._conflicting(xc)
        record = outcome.conflicts.records[0]
        choice = CF.ResolutionChoice(
            stable_field_key=record.locator.stable_field_key,
            kind=CF.ResolutionKind.take_incoming,
            row_key=record.locator.row_key,
            oo_location=record.locator.oo_location,
        )
        folded = M.apply_resolutions(outcome, [choice], contract=xc)
        with pytest.raises(CM.ContractRequiredError):
            _service()._settle_projection(  # noqa: SLF001
                plan(bundle=bundle_snapshot(xc), contract=None),
                CM.BusinessMutation(
                    projection=folded, merge=outcome, resolution_choices=(choice,)
                ),
            )

    def test_partial_resolution_is_still_rejected(self, xc: C.SyncContract) -> None:
        """裁决只覆盖一部分冲突 ⇒ 仍然拒绝（判据走 Task 14 的逐条覆盖检查）。"""
        outcome = M.merge_projections(
            base=proj(xc, {TOTAL: 100, PERIOD: "旧"}),
            current=proj(xc, {TOTAL: 200, PERIOD: "服务端"}),
            incoming=proj(xc, {TOTAL: 300, PERIOD: "编辑器"}),
            contract=xc,
        )
        assert outcome.conflict_count == 2
        record = outcome.conflicts.records[0]
        with pytest.raises(UnresolvedConflictError):
            _service()._settle_projection(  # noqa: SLF001
                plan(bundle=bundle_snapshot(xc), contract=xc),
                CM.BusinessMutation(
                    projection=outcome.merged,
                    merge=outcome,
                    resolution_choices=(
                        CF.ResolutionChoice(
                            stable_field_key=record.locator.stable_field_key,
                            kind=CF.ResolutionKind.keep_current,
                            row_key=record.locator.row_key,
                            oo_location=record.locator.oo_location,
                        ),
                    ),
                )
            )

    def test_merge_outcome_drives_client_refresh_judgement(
        self, xc: C.SyncContract
    ) -> None:
        """merged ≠ incoming ⇒ 需要编辑器确认新基线（AC 8.12 的判据来源）。"""
        incoming = proj(xc, {PERIOD: "旧期间"})
        outcome = M.merge_projections(
            base=proj(xc, {PERIOD: "旧期间"}),
            current=proj(xc, {PERIOD: "服务端改过"}),
            incoming=incoming,
            contract=xc,
        )
        assert outcome.requires_client_refresh(incoming) is True


# ═══════════════════════════════════════════════════════════════════════════
# 8. roundtrip 等值（Property 65）
# ═══════════════════════════════════════════════════════════════════════════


class TestRoundtripEquivalence:
    def _check(self, xc: C.SyncContract, intended: Projection, extracted: Projection) -> None:
        _service()._assert_roundtrip_equivalent(  # noqa: SLF001
            intended=intended, extracted=extracted, contract=xc
        )

    def test_identical_projections_pass(self, xc: C.SyncContract) -> None:
        p = proj(xc, {PERIOD: "2025 年度", TOTAL: Decimal("1234.50")})
        self._check(xc, p, p)

    def test_typed_equality_tolerates_formatting(self, xc: C.SyncContract) -> None:
        """`"1234.50"` / `1234.5` / `Decimal("1234.5")` 是同一个金额 —— 用 merge 的类型口径。

        注意 merge 的 `_as_decimal` **不接受**千分符（`"1,234.50"` 抛
        `ValueNormalizationError`）：那是「载体写出了不合法数值」，属 extract 侧的
        schema 冲突，不该在等值判据里被悄悄容忍。这里锁的是合法表示之间的等价。
        """
        self._check(
            xc, proj(xc, {TOTAL: Decimal("1234.50")}), proj(xc, {TOTAL: "1234.50"})
        )
        self._check(xc, proj(xc, {TOTAL: Decimal("1234.5")}), proj(xc, {TOTAL: 1234.5}))

    def test_illegal_numeric_representation_is_not_silently_equal(
        self, xc: C.SyncContract
    ) -> None:
        """反读出千分符字符串 ⇒ 规范化失败必须抛出，不得被当成等值放过。"""
        with pytest.raises(M.ValueNormalizationError):
            self._check(
                xc, proj(xc, {TOTAL: Decimal("1234.50")}), proj(xc, {TOTAL: "1,234.50"})
            )

    def test_missing_managed_field_is_rejected(self, xc: C.SyncContract) -> None:
        with pytest.raises(CM.RoundtripEquivalenceError) as exc:
            self._check(
                xc,
                proj(xc, {PERIOD: "2025 年度", TOTAL: 1}),
                proj(xc, {PERIOD: "2025 年度"}),
            )
        assert "反读后缺少受管字段" in str(exc.value)

    def test_extra_managed_field_is_rejected(self, xc: C.SyncContract) -> None:
        with pytest.raises(CM.RoundtripEquivalenceError) as exc:
            self._check(
                xc,
                proj(xc, {PERIOD: "2025 年度"}),
                proj(xc, {PERIOD: "2025 年度", TOTAL: 9}),
            )
        assert "反读出未提交的受管字段" in str(exc.value)

    def test_value_drift_is_rejected(self, xc: C.SyncContract) -> None:
        with pytest.raises(CM.RoundtripEquivalenceError) as exc:
            self._check(
                xc, proj(xc, {TOTAL: Decimal("100")}), proj(xc, {TOTAL: Decimal("100.01")})
            )
        assert "反读不等值" in str(exc.value)
        assert "Property 65" in str(exc.value)

    def test_three_failure_reasons_have_distinct_messages(self, xc: C.SyncContract) -> None:
        """缺字段 / 多字段 / 值漂移共用一个异常类 ⇒ 必须靠**专属短语**区分，否则互相遮蔽。

        🔴 判据不是「消息前 N 个字符不同」（那会随文案微调假红/假绿），而是「每条命中
        自己那个短语、且不命中另两条的短语」—— 双向断言。
        """
        phrases = ("反读后缺少受管字段", "反读出未提交的受管字段", "反读不等值")
        cases = (
            (proj(xc, {PERIOD: "a", TOTAL: 1}), proj(xc, {PERIOD: "a"})),
            (proj(xc, {PERIOD: "a"}), proj(xc, {PERIOD: "a", TOTAL: 1})),
            (proj(xc, {TOTAL: 1}), proj(xc, {TOTAL: 2})),
        )
        for idx, (intended, extracted) in enumerate(cases):
            with pytest.raises(CM.RoundtripEquivalenceError) as exc:
                self._check(xc, intended, extracted)
            message = str(exc.value)
            assert phrases[idx] in message, f"第 {idx} 条未命中自己的短语: {message}"
            for other, phrase in enumerate(phrases):
                if other == idx:
                    continue
                assert phrase not in message, (
                    f"第 {idx} 条同时命中了第 {other} 条的短语 ⇒ 两条判据不可区分: {message}"
                )

    def test_word_only_fields_are_excluded(self, dc: C.SyncContract) -> None:
        """`word_only` 永不进 HTML projection —— 拿它比较会让 Word 底稿恒判不等值。"""
        intended = proj(dc, {"plan/location": "北京仓"})
        extracted = proj(
            dc, {"plan/location": "北京仓", "plan/free_notes": "Word 侧自由正文"}
        )
        _service()._assert_roundtrip_equivalent(  # noqa: SLF001
            intended=intended, extracted=extracted, contract=dc
        )

    @given(st.decimals(min_value=-10**6, max_value=10**6, places=2, allow_nan=False))
    @_HYP
    def test_property_amount_roundtrip_is_format_insensitive(self, amount: Decimal) -> None:
        """Property：金额只要数值相同，格式（千分符/字符串/Decimal）不影响等值判定。

        反读回来的受管金额在 OOXML 里可能是字符串形态，如果比较口径按字节，任何真实
        底稿都会恒判「不等值」而无法发布；反之若口径过宽（浮点近似），漂移的那天两边
        都「全绿」。这条属性锁住中间那个正确口径。

        **Validates: Requirements 8.10**
        """
        contract = C.parse_contract(xlsx_payload())
        intended = proj(contract, {TOTAL: amount})
        extracted = proj(contract, {TOTAL: format(amount, "f")})
        _service()._assert_roundtrip_equivalent(  # noqa: SLF001
            intended=intended, extracted=extracted, contract=contract
        )


# ═══════════════════════════════════════════════════════════════════════════
# 9. 真实 materialize/extract 往返（adapter 桩，真写真读）
# ═══════════════════════════════════════════════════════════════════════════


class TestStageAndVerifyWithRealFiles:
    """`_stage_and_verify` 的三条失败与一条成功都跑真实文件读写。"""

    def _plan(self, xc: C.SyncContract, tmp: Path) -> CM.ContentCommitPlan:
        substrate = tmp / "substrate.xlsx"
        substrate.write_bytes(b"substrate-bytes")
        return plan(
            bundle=bundle_snapshot(xc), contract=xc, substrate_path=substrate
        )

    def _svc(self, tmp: Path) -> CM.ContentMutationService:
        (tmp / "storage").mkdir(exist_ok=True)
        (tmp / "definition_store").mkdir(exist_ok=True)
        return CM.ContentMutationService(
            session=object(),  # type: ignore[arg-type]
            repository=object(),  # type: ignore[arg-type]
            artifacts=CanonicalArtifactRepository(tmp),
            resolution=object(),  # type: ignore[arg-type]
        )

    @pytest.mark.asyncio
    async def test_successful_stage_publishes_both_artifacts(
        self, xc: C.SyncContract, tmp_path: Path
    ) -> None:
        p = self._plan(xc, tmp_path)
        adapter = _FakeExcelAdapter()
        projection = proj(xc, {PERIOD: "2025 年度", TOTAL: Decimal("100.00")})
        staged = await self._svc(tmp_path)._stage_and_verify(  # noqa: SLF001
            plan=p,
            mutation=CM.BusinessMutation(projection=projection),
            projection=projection,
            adapter=adapter,
        )
        assert adapter.materialize_calls == 1 and adapter.extract_calls == 1
        assert staged.projection is not None
        assert Path(tmp_path / staged.representation.relative_path).is_file()
        assert Path(tmp_path / staged.projection.relative_path).is_file()
        # 🔴 文件已 publish 但**没有任何 DB 行引用它** ⇒ 此刻是不可见 orphan
        #    （Requirement 2.4：事务失败的 artifact 不可见并由 orphan GC 清理）。
        assert ".versions" in staged.representation.relative_path

    @pytest.mark.asyncio
    async def test_roundtrip_gap_blocks_before_any_db_write(
        self, xc: C.SyncContract, tmp_path: Path
    ) -> None:
        """materialize 漏写一个受管字段 ⇒ 在事务之前失败（不得只提交 HTML projection）。"""
        p = self._plan(xc, tmp_path)
        projection = proj(xc, {PERIOD: "2025 年度", TOTAL: Decimal("100.00")})
        with pytest.raises(CM.RoundtripEquivalenceError):
            await self._svc(tmp_path)._stage_and_verify(  # noqa: SLF001
                plan=p,
                mutation=CM.BusinessMutation(projection=projection),
                projection=projection,
                adapter=_FakeExcelAdapter(drop_keys=(TOTAL,)),
            )

    @pytest.mark.asyncio
    async def test_unmanaged_region_drift_blocks_commit(
        self, xc: C.SyncContract, tmp_path: Path
    ) -> None:
        from app.services.workpaper_sync.adapters.base import UnmanagedRegionDriftError

        p = self._plan(xc, tmp_path)
        projection = proj(xc, {PERIOD: "2025 年度"})
        with pytest.raises(UnmanagedRegionDriftError) as exc:
            await self._svc(tmp_path)._stage_and_verify(  # noqa: SLF001
                plan=p,
                mutation=CM.BusinessMutation(projection=projection),
                projection=projection,
                adapter=_FakeExcelAdapter(unmanaged_equivalent=False),
            )
        assert "drawing1.xml" in str(exc.value)

    @pytest.mark.asyncio
    async def test_custom_authoritative_path_skips_materialize(
        self, tmp_path: Path
    ) -> None:
        """custom：xlsx 本体即权威，不 materialize、不投影、structure hash 用自身 digest。"""
        p = plan(
            bundle=bundle_snapshot(
                None, authority=AuthorityModel.custom_authoritative_ooxml
            ),
            contract=None,
            substrate_path=tmp_path / "any.xlsx",
        )
        payload = _minimal_ooxml("xlsx", extra={"xl/user-uploaded.xml": b"<custom/>"})
        staged = await self._svc(tmp_path)._stage_and_verify(  # noqa: SLF001
            plan=p,
            mutation=CM.BusinessMutation(authoritative_payload=payload),
            projection=None,
            adapter=None,
        )
        assert staged.projection is None and staged.materialize is None
        assert staged.structure_hash == staged.representation.sha256
        assert staged.representation.sha256 == hashlib.sha256(payload).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# 10. 事件 payload（Requirement 13.1 / 13.2）
# ═══════════════════════════════════════════════════════════════════════════


class _RepStub:
    def __init__(self, generation: int = 1) -> None:
        self.id = uuid.uuid4()
        self.generation = generation
        self.content_version_id = uuid.uuid4()


class TestEventPayload:
    def test_business_commit_payload_has_design_required_keys(
        self, xc: C.SyncContract
    ) -> None:
        p = plan(bundle=bundle_snapshot(xc), contract=xc, operation_id=uuid.uuid4())
        payload = CM.ContentMutationService._event_payload(  # noqa: SLF001
            plan=p,
            revision=4,
            version_id=uuid.uuid4(),
            representation=_RepStub(),  # type: ignore[arg-type]
            artifact_sha256=_d("artifact"),
            projection_sha256=_d("projection"),
            requires_client_refresh=False,
        )
        assert CM.EVENT_PAYLOAD_REQUIRED_KEYS <= set(payload), (
            f"design §outbox 的必填键缺 {sorted(CM.EVENT_PAYLOAD_REQUIRED_KEYS - set(payload))}"
        )
        assert payload["content_revision_advanced"] is True
        assert payload["revision"] == 4
        # AC 8.12：applied version 必须同时绑定 projection hash 与 representation/bundle identity
        for key in (
            "projection_sha256",
            "representation_id",
            "representation_generation",
            "definition_bundle_id",
            "definition_bundle_sha256",
            "authority_model",
        ):
            assert payload.get(key) is not None, f"payload 缺 AC 8.12 要求的 {key}"

    def test_definition_upgrade_payload_marks_revision_unchanged(self) -> None:
        """纯表示升级的事件必须自报「revision 没变」，否则下游会当成业务改动去刷新。"""
        payload = R.RepresentationService._event_payload(  # noqa: SLF001
            project_id=uuid.uuid4(),
            wp_id=uuid.uuid4(),
            entry_id="g7.disclosure.listed",
            revision=7,
            representation=_RepStub(generation=3),  # type: ignore[arg-type]
            bundle=bundle_snapshot(C.parse_contract(xlsx_payload())),
            adapter_id="g7.disclosure.listed",
            artifact_sha256=_d("artifact"),
        )
        assert CM.EVENT_PAYLOAD_REQUIRED_KEYS <= set(payload)
        assert payload["content_revision_advanced"] is False
        assert payload["revision"] == 7
        assert payload["source"] == "definition_upgrade"
        assert payload["reason"] == "definition_upgrade"

    def test_event_type_exists_and_matches_design(self) -> None:
        from app.models.audit_platform_schemas import EventType

        assert EventType.WORKPAPER_CONTENT_UPDATED.value == "workpaper.content.updated"
        # design §outbox 的键清单与代码常量双向锁死
        design = (
            _REPO
            / ".kiro"
            / "specs"
            / "workpaper-html-onlyoffice-bidirectional-writeback-closure"
            / "design.md"
        ).read_text(encoding="utf-8")
        block = design.split("### outbox", 1)[1].split("```", 2)[1]
        declared = set(re.findall(r'"(\w+)":', block))
        assert declared == set(CM.EVENT_PAYLOAD_REQUIRED_KEYS), (
            f"design §outbox 的 payload 键与代码常量漂移："
            f"design={sorted(declared)} vs 代码={sorted(CM.EVENT_PAYLOAD_REQUIRED_KEYS)}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 11. projection 内容寻址载荷
# ═══════════════════════════════════════════════════════════════════════════


class TestProjectionPayload:
    def test_same_projection_same_bytes(self, xc: C.SyncContract) -> None:
        """AC 3.6 的前提：相同业务 projection 必须算出相同 digest（否则幂等永不成立）。"""
        a = CM._projection_payload(proj(xc, {PERIOD: "2025", TOTAL: Decimal("1.10")}))  # noqa: SLF001
        b = CM._projection_payload(proj(xc, {TOTAL: Decimal("1.10"), PERIOD: "2025"}))  # noqa: SLF001
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    def test_value_change_changes_bytes(self, xc: C.SyncContract) -> None:
        a = CM._projection_payload(proj(xc, {TOTAL: Decimal("1.10")}))  # noqa: SLF001
        b = CM._projection_payload(proj(xc, {TOTAL: Decimal("1.11")}))  # noqa: SLF001
        assert a != b

    def test_decimal_is_serialized_without_float_error(self, xc: C.SyncContract) -> None:
        """`float(Decimal("0.1"))` 会引入二进制误差 ⇒ 同一金额算出不同 digest。"""
        payload = CM._projection_payload(proj(xc, {TOTAL: Decimal("0.1")}))  # noqa: SLF001
        assert payload["values"][TOTAL]["value"] == "0.1"

    def test_payload_has_no_machine_specific_fields(self, xc: C.SyncContract) -> None:
        blob = json.dumps(
            CM._projection_payload(proj(xc, {PERIOD: "2025"})), ensure_ascii=False  # noqa: SLF001
        )
        for forbidden in ("uuid", "created_at", "storage", ":\\\\", "artifact_id"):
            assert forbidden not in blob, (
                f"内容寻址载荷含机器/时点相关字段 {forbidden!r} ⇒ 幂等复用永不成立"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 12. Property 61：唯一 revision 域 / 唯一提交边界
# ═══════════════════════════════════════════════════════════════════════════

#: Requirement 2.1 明令不得充当跨通道同步版本的 legacy 字段。
#:
#: 🔴 用**词边界**正则而不是裸子串：`_version` 是 `semantic_version` /
#: `schema_version` 的后缀，裸子串会把两个合法字段判成违规（本文件首轮实测的假红）。
_LEGACY_VERSION_PATTERNS: Final[tuple[str, ...]] = (
    r"\bfile_version\b",
    r"parsed_data\s*\[\s*['\"]_version['\"]\s*\]",
    r"\.\s*_version\b",
    r"\bmtime_ns\b",
)


def _stripped(path: Path) -> str:
    sys.path.insert(0, str(_BACKEND / "scripts" / "gen"))
    from generate_workpaper_resolver_migration_matrix import (  # noqa: PLC0415
        strip_comments_and_docstrings,
    )

    return strip_comments_and_docstrings(path.read_text(encoding="utf-8"))


class TestProperty61SingleRevisionDomain:
    """Property 61 的静态半边：唯一提交边界 + 两个新模块零 legacy 版本字段。

    真 writer 的迁移（`wp_html_save` / 上传 / WOPI / custom）归 Tasks 18/19，其判据在
    writer inventory 清册里。这里锁的是**本任务自己不能反向制造第二个 revision 域**。
    """

    #: `ContentMutationService` 里推进 business revision 的 lane（每条恰一处 CAS）。
    #: Task 15 只有 bidirectional 一条；Task 18 加了 `single_html` 一条（那条 entry 没有
    #: OO representation，凭空造一个空白 artifact 违反 Requirement 3.9）。
    #: **判据的强项不是"1 处"而是"只有这一个模块"** —— 只要 revision 域没有溢出到第二个
    #: 模块，Property 61 就成立；lane 数量随迁移增长是预期的。
    #: 名字是**持有 CAS 与 latch 的那个函数体**，不是公开入口：bidirectional 的
    #: `commit()` 把事务体委托给 `_commit_once()`，CAS 在后者里。
    _REVISION_LANES = ("_commit_once", "commit_html_projection")

    def test_revision_bump_call_sites_live_in_exactly_one_module(self) -> None:
        """`bump_content_revision(` 只出现在唯一 commit 入口那个模块里，且逐 lane 恰一处。"""
        callers: dict[str, int] = {}
        for py in sorted(_APP_DIR.rglob("*.py")):
            if py.name == "repository.py":
                continue  # 定义处不算调用点
            body = _stripped(py)
            count = body.count("bump_content_revision(")
            if count:
                callers[py.relative_to(_APP_DIR).as_posix()] = count
        assert set(callers) == {"services/workpaper_sync/content_mutation.py"}, (
            f"business revision 递增溢出到别的模块，实测 {callers} —— "
            "那就是第二个 revision 域（Requirement 2.2 / Property 61）"
        )
        assert callers["services/workpaper_sync/content_mutation.py"] == len(
            self._REVISION_LANES
        ), (
            f"CAS 调用点数 {callers} 与登记的 lane 数 {len(self._REVISION_LANES)} 不符 —— "
            f"要么有 lane 偷偷加了第二次递增，要么新增了未登记的 lane（登记: "
            f"{self._REVISION_LANES}）"
        )
        # 逐 lane 各自恰一处：整模块计数对得上、但两处都挤在同一条 lane 里同样违规。
        import ast

        tree = ast.parse(_CM_PY.read_text(encoding="utf-8"))
        per_lane: dict[str, int] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in (
                self._REVISION_LANES
            ):
                per_lane[node.name] = sum(
                    1
                    for inner in ast.walk(node)
                    if isinstance(inner, ast.Call)
                    and getattr(inner.func, "attr", None) == "bump_content_revision"
                )
        assert per_lane == dict.fromkeys(self._REVISION_LANES, 1), per_lane

    def test_current_content_version_pointer_has_one_call_site(self) -> None:
        callers = {
            py.relative_to(_APP_DIR).as_posix()
            for py in sorted(_APP_DIR.rglob("*.py"))
            if py.name != "repository.py"
            and "set_current_content_version(" in _stripped(py)
        }
        assert callers == {"services/workpaper_sync/content_mutation.py"}, callers

    def test_new_modules_never_touch_legacy_version_fields(self) -> None:
        for path in (_CM_PY, _REP_PY):
            body = _stripped(path)
            for pattern in _LEGACY_VERSION_PATTERNS:
                hit = re.search(pattern, body)
                assert hit is None, (
                    f"{path.name} 出现 legacy 版本字段 {hit.group(0)!r}（模式 {pattern}）"
                    " —— Requirement 2.1 明令 `parsed_data._version` / "
                    "`working_paper.file_version` / 文件 mtime 不得充当跨通道同步版本"
                )

    def test_legacy_pattern_judgement_distinguishes_suffix_matches(self) -> None:
        """反向自检：`semantic_version` / `schema_version` 不得被误判成 legacy 字段。

        没有这条，上面那条判据既可能假红（合法字段被抓）也可能被人改成裸子串后
        永久假红 —— 而「改成恒红」与「改成恒绿」都是判据失效。
        """
        legit = "semantic_version = contract.schema_version\nrepresentation_generation = 1\n"
        for pattern in _LEGACY_VERSION_PATTERNS:
            assert re.search(pattern, legit) is None, (
                f"合法字段被模式 {pattern} 误判成 legacy 版本字段 ⇒ 假红"
            )
        violations = (
            "wp.file_version += 1",
            "parsed_data['_version'] = 3",
            'parsed_data["_version"] = 3',
            "payload._version = 2",
            "doc_key = md5(wp_code + str(mtime_ns))",
        )
        for text in violations:
            assert any(re.search(p, text) for p in _LEGACY_VERSION_PATTERNS), (
                f"真违规 {text!r} 没被任何模式抓到 ⇒ 假绿"
            )

    def test_writer_inventory_knows_the_unified_commit_marker(self) -> None:
        """清册生成器的统一提交入口标记必须与真实类名一致（双向锁死）。"""
        gen = (
            _BACKEND / "scripts" / "gen" / "generate_workpaper_writer_inventory.py"
        ).read_text(encoding="utf-8")
        assert '"ContentMutationService"' in gen, (
            "writer 清册生成器的 `_UNIFIED_COMMIT_MARKERS` 未包含真实类名 ⇒ "
            "「writer 是否已迁入唯一入口」这条判据在清册里失效"
        )
        assert "class ContentMutationService:" in _CM_PY.read_text(encoding="utf-8")

    def test_commit_is_the_only_session_commit_in_the_two_modules(self) -> None:
        """两个模块里 `session.commit()` 各自恰一处（唯一提交出口）。

        `content_mutation.py` 的计数是**每条 lane 一次** `commit_once(self._session)`：
        每条 lane 有自己的 `_CommitLatch`，所以「一次业务 mutation 恰一次数据库提交」
        这条断言对每条 lane 各自成立。裸 `self._session.commit()` 仍然必须为 0 ——
        绕过 latch 就无法断言提交次数。
        """
        cm_body = _stripped(_CM_PY)
        rep_body = _stripped(_REP_PY)
        assert cm_body.count("self._session.commit()") == 0, (
            "content_mutation.py 出现裸 `self._session.commit()` —— 业务提交必须经 "
            "`_CommitLatch.commit_once()`，否则「一次业务 commit 恰一次提交」无法断言"
        )
        assert cm_body.count("commit_once(self._session)") == len(self._REVISION_LANES), (
            f"latch 提交点数应等于 lane 数 {len(self._REVISION_LANES)}，实测 "
            f"{cm_body.count('commit_once(self._session)')}"
        )
        assert rep_body.count("self._session.commit()") == 1, (
            "representations.py 的提交出口必须恰一处"
        )

    def test_adapter_context_has_no_mutation_surface(self, xc: C.SyncContract) -> None:
        """`_build_context` 造出来的 `SyncContext` 逐字段实测零副作用面。"""
        from app.services.workpaper_sync.adapters.base import assert_no_mutation_surface

        ctx = _service()._build_context(plan(bundle=bundle_snapshot(xc), contract=xc))  # noqa: SLF001
        assert_no_mutation_surface(ctx, label="SyncContext")
        assert not hasattr(ctx, "session")


# ═══════════════════════════════════════════════════════════════════════════
# 13. 任务边界与可追溯性
# ═══════════════════════════════════════════════════════════════════════════


class TestTask15ScopeBoundary:
    def test_two_services_are_separate_classes(self) -> None:
        """业务应用与纯定义升级是两个类、两条路径，不是一个布尔开关。"""
        assert CM.ContentMutationService is not R.RepresentationService
        assert not issubclass(R.RepresentationService, CM.ContentMutationService)
        cm_methods = {m for m in dir(CM.ContentMutationService) if not m.startswith("__")}
        rep_methods = {m for m in dir(R.RepresentationService) if not m.startswith("__")}
        assert "commit" in cm_methods and "commit" not in rep_methods, (
            "RepresentationService 不得暴露 `commit`：纯表示升级不是业务提交"
        )
        assert "finalize_candidate" in rep_methods
        assert "finalize_candidate" not in cm_methods, (
            "ContentMutationService 不得自己 finalize candidate —— 那会绕过 "
            "RepresentationService 的 approved bundle 门"
        )

    def test_representation_path_declares_no_revision_step(self) -> None:
        """纯表示 finalize 的事务步骤里**没有** revision 一步（Property 4 的结构判据）。"""
        assert "revision" not in R.REPRESENTATION_FINALIZE_STEPS
        assert "revision" in CM.CONTENT_COMMIT_STEPS
        assert set(R.REPRESENTATION_FINALIZE_STEPS) >= {
            "representation",
            "entry_pointer",
            "outbox",
        }

    def test_publish_dag_order_is_enforced_before_finalize(self) -> None:
        """finalize 必须沿 template→instrumentation→contract→bundle→representation。"""
        from app.services.workpaper_sync.definitions import PublishOrderError

        with pytest.raises(PublishOrderError):
            R.assert_publish_order(
                stage=PublishStage.representation,
                approved_stages={PublishStage.template, PublishStage.instrumentation},
            )
        R.assert_publish_order(
            stage=PublishStage.representation,
            approved_stages={
                PublishStage.template,
                PublishStage.instrumentation,
                PublishStage.contract,
                PublishStage.bundle,
            },
        )

    def test_no_router_or_carrier_library_in_this_task(self) -> None:
        """本任务不注册路由（归 Task 27/28）、不引入载体库（归 Tasks 36~38 / 59~61）。"""
        for path in (_CM_PY, _REP_PY):
            body = _stripped(path)
            for forbidden in (
                "openpyxl",
                "python-docx",
                "docx",
                "APIRouter",
                "@router.",
                "Depends(",
            ):
                assert forbidden not in body, f"{path.name} 出现 {forbidden!r}"

    def test_modules_declare_spec_requirements_and_properties(self) -> None:
        for path in (_CM_PY, _REP_PY):
            head = path.read_text(encoding="utf-8")[:3000]
            assert "workpaper-html-onlyoffice-bidirectional-writeback-closure" in head
            assert "Requirements" in head
            assert "Task 15" in head
        cm_head = _CM_PY.read_text(encoding="utf-8")[:3000]
        for prop in ("4", "5", "10", "61", "65", "67"):
            assert f"P{prop}" in cm_head, f"content_mutation.py 的 Properties 溯源缺 P{prop}"

    def test_merge_domain_deferral_is_retired(self) -> None:
        """Task 14 的 merge 域延后登记已退役，且退役登记指向本任务的模块。

        🔴 判据是**归因型**，不是全局等值型。上一版写 `len(retired) == 1`：
        `RETIRED_DEFERRALS` 是**跨任务共享**的登记表，Task 26 落地 OO→HTML 编排层后
        合法地追加了自己那条（编排层允许跑 merge、但经 `commits_through` 落库），
        于是这条守卫被别人的合法改动打红 —— 全局等值判据在多 spec 共享文件上必然假红。

        改法不是放宽，而是换成更强的两段：
        1. **我的那条**（`retired_by_task == "15"`）唯一存在且指向 content_mutation；
        2. 任何**其他** merge 消费方必须显式声明 `commits_through` 回到 content_mutation
           —— 即唯一 commit 边界（Property 61）不因新增消费方而松动。
        第 2 段约束的是未来所有新增条目，比「只能有一条」严格：旧版对「新增一条
        不经 commit 边界的消费方」只会报 `2 == 1`，说不出问题在哪。
        """
        retired = [
            e for e in M.RETIRED_DEFERRALS if "merge_projections" in str(e["capability"])
        ]
        assert retired, "merge 域退役登记不得为空"
        mine = [e for e in retired if e["retired_by_task"] == "15"]
        assert len(mine) == 1, f"Task 15 的退役登记必须恰一条，实得 {len(mine)}"
        assert (
            mine[0]["expected_consumer_module"]
            == "app/services/workpaper_sync/content_mutation.py"
        )
        # 本任务就是 commit 边界本身，因此它这条不需要（也不得）再指向别人。
        assert mine[0]["commits_through"] is None

        others = [e for e in retired if e["retired_by_task"] != "15"]
        for entry in others:
            module = str(entry["expected_consumer_module"])
            if entry["commits_through"] is None:
                # 🔴 第三种合法形态（Task 39 的 evidence oracle）：**只读**消费方 ——
                # 它跑 merge 只为判定 Property 25/26，自己完全不碰内容域。
                #
                # 这不是放宽而是收紧：`commits_through=None` 在这里必须由**结构判据**
                # 证明「零内容写入面」，而不是靠登记表里的一句声明。原判据只有
                # 「必须声明 commits_through」一条，一个真正只读的消费方无法如实登记，
                # 于是唯一出路是把 capability 措辞改掉绕过字符串匹配 —— 那才是真的放宽
                # （Task 38 的两条登记就是这么绕过去的）。
                # 🔴 判据走 **AST** 而不是字符串包含：只读消费方完全可以在**数据**里
                # 提到 `content_mutation:ContentMutationService`（Task 39 的 oracle 登记表
                # 就用它做「该场景在生产上由谁实现」的可解析引用）。字符串判据会把这种
                # 纯数据引用误判成写入面 —— 实测踩过。
                import ast as _ast

                tree = _ast.parse(
                    (_BACKEND / "app" / module.split("app/", 1)[1]).read_text(
                        encoding="utf-8", errors="replace"
                    )
                )
                imported: set[str] = set()
                for node in _ast.walk(tree):
                    if isinstance(node, _ast.Import):
                        imported.update(a.name for a in node.names)
                    elif isinstance(node, _ast.ImportFrom) and node.module:
                        imported.add(node.module)
                        imported.update(f"{node.module}.{a.name}" for a in node.names)
                forbidden_modules = (
                    "app.services.workpaper_sync.content_mutation",
                    "app.services.workpaper_sync.outbox",
                    "app.services.workpaper_sync.representations",
                )
                for forbidden in forbidden_modules:
                    hit = [name for name in imported if name.startswith(forbidden)]
                    assert not hit, (
                        f"{module} 登记为只读 merge 消费方（commits_through=None），"
                        f"却 import 了内容写入面 {hit} —— 它要么经唯一 commit 边界落库，"
                        "要么必须真的零写入面（Property 61）"
                    )
                written_attrs: set[str] = set()
                for node in _ast.walk(tree):
                    targets = (
                        node.targets
                        if isinstance(node, _ast.Assign)
                        else [node.target]
                        if isinstance(node, (_ast.AugAssign, _ast.AnnAssign))
                        else []
                    )
                    written_attrs.update(
                        t.attr for t in targets if isinstance(t, _ast.Attribute)
                    )
                content_fields = {
                    "revision",
                    "content_revision",
                    "current_representation_id",
                    "representation_generation",
                    "projection_sha256",
                    "authoritative_artifact_sha256",
                }
                leaked = sorted(written_attrs & content_fields)
                assert not leaked, (
                    f"{module} 登记为只读 merge 消费方，却给内容域字段赋值 {leaked} —— "
                    "唯一 commit 边界只能是 ContentMutationService（Property 61）"
                )
                continue
            assert entry["commits_through"] == (
                "app/services/workpaper_sync/content_mutation.py"
            ), (
                f"merge 消费方 {entry['expected_consumer_module']!r} "
                f"（task {entry['retired_by_task']}）未声明经唯一 commit 边界落库："
                f"commits_through={entry['commits_through']!r}"
            )

        assert not any(
            "merge_projections" in str(e["capability"]) for e in M.DEFERRED_CONSUMERS
        ), "同一能力不得同时挂在 deferred 与 retired 两张表上"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
