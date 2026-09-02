# -*- coding: utf-8 -*-
"""Task 36 守卫（纯域 / 无库）：Excel per-entry contract/bundle loader 与 candidate
finalize gate。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 3 Task 36
Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.10, 6.13, 6.14, 6.15, 6.16, 6.17, 6.18, 6.20
Properties: **P20 / P21 / P22 / P23 / P28 / P66 / P67**

═══ 为什么本任务的判据能在无库下判死 ═══

Task 36 的六类 fail-closed 原因（slot omission / NULL / 空串 / 全零 hash / 非法 marker /
missing-unapproved contract）里有三类**根本无法**由一条已落库的行触发：V151 把
`working_paper_sync_definition_bundle` 的九个 slot 列声明成 `NOT NULL` 并挂了
`wpsync_is_digest()` CHECK。若只在真库上测，这三条永远是不可达分支，它们的变异恒
GREEN —— 也就是「守住了」这句话不可 falsify。

所以分类判据被做成**纯函数**（`assert_frozen_slot_shape` 吃任意来源的 raw slot map：
ORM row / 尚未 flush 的内存对象 / 人写的 bundle JSON），本文件逐条合成反例。DB CHECK
是第二道锁，不是第一道。

═══ 三个替身都是「真跑」而不是「喂假返回值」 ═══

* `_FakeSession` 按 `select(Entity).where(Entity.id == x)` 的**真实 statement** 取
  `column_descriptions[0]["entity"]` 与绑定参数值分派 —— 生产侧的查询构造被真的执行了；
* `_FakeResolution` 只提供 Task 12 的两个方法并**记录调用**，于是「有没有真的过
  `load_bundle_snapshot`」是可观察事实；
* `_RecordingCoordinator` 记录 `finalize_definition_upgrade` 的调用次数与入参 —— 于是
  「任一前置不过 ⇒ 一次写入都没发生」不是文档承诺（Property 67）。

契约走**真文件**：`monkeypatch.setattr(contracts, "CONTRACTS_DIR", tmp)` 之后
`load_contract()` 是生产函数本体在读一份真 JSON，不是被打桩掉。
"""

from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
import os
import sys
import uuid
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

import sqlalchemy as sa  # noqa: E402

from app.models.workpaper_sync_models import (  # noqa: E402
    WorkpaperSyncDefinitionArtifact,
    WorkpaperSyncDefinitionBundle,
)
from app.services.excel_structure_fingerprint import GT_SYNC_SHEET_NAME  # noqa: E402
from app.services.workpaper_sync import contracts as C  # noqa: E402
from app.services.workpaper_sync import definitions as D  # noqa: E402
from app.services.workpaper_sync import excel_entry_gate as G  # noqa: E402
from app.services.workpaper_sync.adapters.registry import StaleAdapterError  # noqa: E402
from app.services.workpaper_sync.artifacts import StagedCandidate  # noqa: E402
from app.services.workpaper_sync.models import (  # noqa: E402
    AuthorityModel,
    BundleIntegrityError,
    BundleSlot,
    BundleSlotSpec,
    DefinitionState,
)
from app.services.workpaper_sync.representations import (  # noqa: E402
    RepresentationFinalizeOutcome,
)
from app.services.workpaper_sync.resolution import DefinitionBundleSnapshot  # noqa: E402

_SYNC_DIR = _BACKEND / "app" / "services" / "workpaper_sync"
_GATE_PY = _SYNC_DIR / "excel_entry_gate.py"
_V151 = _BACKEND / "migrations" / "V151__workpaper_sync_content_application_bundle_scope.sql"

# 双哨兵：单哨兵会被历史空目录骗停。
assert (_BACKEND / "app" / "main.py").is_file(), "哨兵失效：backend/app/main.py 不存在"
assert _GATE_PY.is_file(), f"哨兵失效：{_GATE_PY} 不存在"

_HYP = settings(max_examples=50, deadline=None)

ENTRY: Final[str] = "g7.disclosure.listed"


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


TEMPLATE_DEF = _d("task36-template")
INSTR_DEF = _d("task36-instrumentation")
ADAPTER_BUILD = _d("task36-adapter-build")


# ═══════════════════════════════════════════════════════════════════════════
# 0. 契约（真文件）
# ═══════════════════════════════════════════════════════════════════════════


def xlsx_payload(contract_id: str = ENTRY) -> dict[str, Any]:
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
        "identity_carriers": [
            "hidden_sheet",
            "defined_name",
            "excel_table",
            "hidden_uuid_column",
        ],
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
                        ],
                    },
                ],
            }
        ],
    }


#: 手写的 structure inventory —— **刻意不调** `declared_structure_inventory()` 生成。
#:
#: 🔴 用被测函数的输出当期望值会让判据空转：契约与实测同时漂移时仍然相等。这里的四行
#: 是按契约 payload 人工推出来的，任一侧变动都会打红。
DECLARED_STRUCTURE: Final[tuple[tuple[str, str, str, str], ...]] = (
    (
        "g7-disclosure",
        "equity_changes",
        "equity_changes/{row_uuid}/closing_amount",
        "H:row_identity",
    ),
    ("g7-disclosure", "equity_changes", "equity_changes/{row_uuid}/name", "G:row_identity"),
    (
        "g7-disclosure",
        "equity_changes",
        "equity_changes/{row_uuid}/subtotal",
        "I:row_identity",
    ),
    ("g7-disclosure", "header_block", "header_block/period_label", "B:static:2"),
)


#: 「另一个 entry」的契约 —— 用来实测「禁止复用别人的 contract」。
OTHER_ENTRY: Final[str] = "d2.receivables"


@pytest.fixture()
def contracts_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把契约目录换到 tmp，写两份真 JSON —— `load_contract()` 走生产路径读真文件。

    第二份是**另一个 entry** 的合法契约：Task 36 明令禁止复用别人的 contract/bundle，
    而只有当那份契约真实存在、能通过强校验时，这条禁令才被真的检验（写一个不存在的
    adapter_id 只会测出「文件缺失」，那是另一回事）。
    """
    target = tmp_path / "workpaper_sync_contracts"
    target.mkdir()
    (target / f"{ENTRY}.json").write_text(
        json.dumps(xlsx_payload(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    other = xlsx_payload(OTHER_ENTRY)
    (target / f"{OTHER_ENTRY}.json").write_text(
        json.dumps(other, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    monkeypatch.setattr(C, "CONTRACTS_DIR", target)
    return target


@pytest.fixture()
def contract(contracts_dir: Path) -> C.SyncContract:
    return C.load_contract(ENTRY)


# ═══════════════════════════════════════════════════════════════════════════
# 1. bundle row / snapshot / identity inventory 构造器
# ═══════════════════════════════════════════════════════════════════════════

CONTRACT_DEF_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
TEMPLATE_DEF_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
INSTR_DEF_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
BUNDLE_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")
AUTHORITY_DEF_ID = uuid.UUID("55555555-5555-4555-8555-555555555555")
CANDIDATE_ID = uuid.UUID("66666666-6666-4666-8666-666666666666")
PROJECT_ID = uuid.UUID("77777777-7777-4777-8777-777777777777")
WP_ID = uuid.UUID("88888888-8888-4888-8888-888888888888")


def raw_bundle_map(contract_sha: str, **over: Any) -> dict[str, Any]:
    """一份**合法**的 raw slot map（列名取自生产侧 `SLOT_COLUMNS`，不在此抄字面量）。"""
    template_cols = G.SLOT_COLUMNS[BundleSlot.template]
    instr_cols = G.SLOT_COLUMNS[BundleSlot.instrumentation]
    contract_cols = G.SLOT_COLUMNS[BundleSlot.contract]
    raw = {
        template_cols[0]: "definition",
        template_cols[1]: f"definition:{TEMPLATE_DEF_ID}",
        template_cols[2]: TEMPLATE_DEF,
        instr_cols[0]: "definition",
        instr_cols[1]: f"definition:{INSTR_DEF_ID}",
        instr_cols[2]: INSTR_DEF,
        contract_cols[0]: "definition",
        contract_cols[1]: f"definition:{CONTRACT_DEF_ID}",
        contract_cols[2]: contract_sha,
    }
    raw.update(over)
    return raw


def bundle_row(contract_sha: str, *, canonical_sha: str | None = None, **over: Any):
    row = WorkpaperSyncDefinitionBundle(
        id=BUNDLE_ID,
        schema_version=D.BUNDLE_SCHEMA_VERSION,
        authority_model_definition_id=AUTHORITY_DEF_ID,
        authority_model_definition_sha256=_d("task36-authority"),
        canonical_payload_artifact_id=uuid.uuid4(),
        canonical_payload_sha256=canonical_sha or _d("task36-bundle-canonical"),
        state=DefinitionState.approved.value,
        **raw_bundle_map(contract_sha),
    )
    for key, value in over.items():
        setattr(row, key, value)
    return row


def contract_child(contract_sha: str, *, kind: str = "contract", state: str = "approved"):
    return WorkpaperSyncDefinitionArtifact(
        id=CONTRACT_DEF_ID,
        kind=kind,
        logical_id=f"excel-contract/{ENTRY}",
        semantic_version="1.0.0",
        blob_artifact_id=uuid.uuid4(),
        sha256=contract_sha,
        source_commit="task36",
        state=state,
    )


def snapshot(
    contract_sha: str,
    *,
    authority: AuthorityModel = AuthorityModel.projection_contract,
    state: DefinitionState = DefinitionState.approved,
    contract_slot: BundleSlotSpec | None = None,
    template_digest: str = TEMPLATE_DEF,
    canonical_sha: str | None = None,
) -> DefinitionBundleSnapshot:
    slots = {
        BundleSlot.template: BundleSlotSpec(
            BundleSlot.template, "definition", f"definition:{TEMPLATE_DEF_ID}", template_digest
        ),
        BundleSlot.instrumentation: BundleSlotSpec(
            BundleSlot.instrumentation,
            "definition",
            f"definition:{INSTR_DEF_ID}",
            INSTR_DEF,
        ),
        BundleSlot.contract: contract_slot
        or BundleSlotSpec(
            BundleSlot.contract, "definition", f"definition:{CONTRACT_DEF_ID}", contract_sha
        ),
    }
    return DefinitionBundleSnapshot(
        bundle_id=BUNDLE_ID,
        bundle_sha256=canonical_sha or _d("task36-bundle-canonical"),
        schema_version=D.BUNDLE_SCHEMA_VERSION,
        state=state,
        authority_model=authority,
        authority_model_definition_id=AUTHORITY_DEF_ID,
        authority_model_definition_sha256=_d("task36-authority"),
        slots=slots,
    )


def inventory_payload(**over: Any) -> dict[str, Any]:
    """镜像 `excel_structure_fingerprint.identity_inventory()` 的输出形态。"""
    payload: dict[str, Any] = {
        "hidden_sheet": {
            "present": True,
            "is_hidden": True,
            "excluded_from_business_enumeration": True,
            "pairs": {"gt.identity_schema_version": "1"},
        },
        "defined_name": {"names": ["GT_MANAGED_REGION_G7", "GT_SYNC_ANCHOR_G7"]},
        "excel_table": {
            "present": True,
            "table_ref": "A8:Z207",
            "header_row_count_zero": True,
        },
        "hidden_uuid_column": {
            "resolved_sheet_by": "table_sheet",
            "uuid_column_hidden": True,
            "row_uuids": {"8": "GTROW-G7-0008", "9": "GTROW-G7-0009"},
            "duplicate_row_uuids": [],
            "empty_row_uuids": [],
            "sheet_resolution_candidates": ["table_sheet"],
        },
        "errors": [],
    }
    for key, value in over.items():
        payload[key] = value
    return payload


def evidence_bytes(*, instrumented_sha: str, entry_id: str = ENTRY, **over: Any) -> bytes:
    payload: dict[str, Any] = {
        "schema_version": "instrumentation-upgrade-evidence:v1",
        "entry_id": entry_id,
        "template_definition_sha256": TEMPLATE_DEF,
        "instrumentation_definition_sha256": INSTR_DEF,
        "instrumented_sha256": instrumented_sha,
        "visible_equivalence": {
            "equivalent": True,
            "aspect_verdicts": {"visible_sheets": True, "formulas": True},
            "hidden_sheets_added": [GT_SYNC_SHEET_NAME],
            "metadata_sheet_excluded_from_business": True,
        },
        "identity_inventory": inventory_payload(),
        "probe_gate": {
            "carrier_contract_sha256": _d("task36-carrier-contract"),
            "onlyoffice_build": "9.4.0",
            "source_commit": "task36",
        },
    }
    for key, value in over.items():
        payload[key] = value
    return D.canonical_json_bytes(payload)


def staged_candidate(sha: str, *, entry_id: str = ENTRY, tmp: Path | None = None):
    base = tmp or Path("/tmp/task36")
    return StagedCandidate(
        candidate_id=CANDIDATE_ID,
        project_id=PROJECT_ID,
        wp_id=WP_ID,
        entry_id=entry_id,
        path=base / "artifact-abc.candidate.ooxml",
        relative_path=".upgrade-candidates/x/artifact-abc.candidate.ooxml",
        sha256=sha,
        size_bytes=4096,
        document_type="xlsx",
        equivalence_relative_path=".upgrade-candidates/x/equivalence-abc.json",
        equivalence_sha256=_d("evidence-placeholder"),
        verified_before_move=True,
        verified_after_move=True,
    )


def adapter_build(**over: Any) -> G.AdapterBuild:
    base: dict[str, Any] = {
        "adapter_id": ENTRY,
        "adapter_build_digest": ADAPTER_BUILD,
        "document_type": "xlsx",
        "contract_version": "1.0.0",
    }
    base.update(over)
    return G.AdapterBuild(**base)  # type: ignore[arg-type]


# ═══════════════════════════════════════════════════════════════════════════
# 2. 替身（真跑，不喂假返回值）
# ═══════════════════════════════════════════════════════════════════════════


class _FakeResult:
    def __init__(self, row: Any) -> None:
        self._row = row

    def scalar_one_or_none(self) -> Any:
        return self._row


class _FakeSession:
    """按真实 `select(Entity).where(Entity.id == x)` 分派 —— 生产查询构造被真的执行。"""

    def __init__(self, rows: Mapping[tuple[type, uuid.UUID], Any]) -> None:
        self._rows = dict(rows)
        self.queries: list[tuple[str, Any]] = []

    async def execute(self, statement: Any) -> _FakeResult:
        entity = statement.column_descriptions[0]["entity"]
        clause = statement.whereclause
        key = getattr(getattr(clause, "right", None), "value", None)
        self.queries.append((entity.__name__, key))
        return _FakeResult(self._rows.get((entity, key)))


class _FakeResolution:
    """只提供 Task 12 的两个方法，并记录调用（于是「有没有真的过它」可观察）。"""

    def __init__(self, *, bundle: Any = None, candidate: Any = None, raises: Any = None) -> None:
        self._bundle = bundle
        self._candidate = candidate
        self._raises = raises
        self.bundle_calls: list[uuid.UUID] = []
        self.candidate_calls: list[uuid.UUID] = []

    async def load_bundle_snapshot(self, bundle_id: uuid.UUID):
        self.bundle_calls.append(bundle_id)
        if self._raises is not None:
            raise self._raises
        return self._bundle

    async def assert_candidate_finalizable(self, candidate_id: uuid.UUID):
        self.candidate_calls.append(candidate_id)
        return self._candidate


class _CandidateRow:
    def __init__(
        self,
        *,
        entry_id: str = ENTRY,
        bundle_id: uuid.UUID | None = BUNDLE_ID,
        report_sha: str = "",
    ) -> None:
        self.id = CANDIDATE_ID
        self.entry_id = entry_id
        self.target_definition_bundle_id = bundle_id
        self.target_contract_definition_id = CONTRACT_DEF_ID
        self.visible_equivalence_report_sha256 = report_sha
        self.content_version_id = uuid.uuid4()


class _RecordingCoordinator:
    """记录 `finalize_definition_upgrade` 的调用 —— Property 67 的可观察面。"""

    def __init__(self, *, outcome: RepresentationFinalizeOutcome | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._outcome = outcome

    async def finalize_definition_upgrade(self, **kwargs: Any) -> RepresentationFinalizeOutcome:
        self.calls.append(dict(kwargs))
        assert self._outcome is not None
        return self._outcome


def finalize_outcome(*, bundle_id: uuid.UUID = BUNDLE_ID, revision: int = 7):
    return RepresentationFinalizeOutcome(
        candidate_id=CANDIDATE_ID,
        content_version_id=uuid.uuid4(),
        representation_id=uuid.uuid4(),
        representation_generation=2,
        artifact_sha256=_d("published-artifact"),
        definition_bundle_id=bundle_id,
        definition_bundle_sha256=_d("task36-bundle-canonical"),
        authority_model=AuthorityModel.projection_contract.value,
        content_revision_before=revision,
        content_revision_after=revision,
        previous_representation_id=uuid.uuid4(),
        entry_pointer_moved=True,
        transaction_ids=("1",),
        pending_event=None,
    )


#: `build_loader` 的「用默认值」哨兵。
#:
#: 🔴 不能用 `None` 当哨兵：`child=None` 恰恰是「contract child 行不存在」这个要测的反例，
#: 用 `None` 表示「用默认」会让 FS-6 的 child-missing 用例静默变成 happy path
#: （首轮实测就是这样 DID NOT RAISE）。
_DEFAULT: Final[object] = object()


def build_loader(
    contract_sha: str,
    *,
    row: Any = _DEFAULT,
    child: Any = _DEFAULT,
    resolution: _FakeResolution | None = None,
) -> tuple[G.ExcelEntryDefinitionLoader, _FakeSession, _FakeResolution]:
    bundle_db_row = bundle_row(contract_sha) if row is _DEFAULT else row
    child_row = contract_child(contract_sha) if child is _DEFAULT else child
    session = _FakeSession(
        {
            (WorkpaperSyncDefinitionBundle, BUNDLE_ID): bundle_db_row,
            (WorkpaperSyncDefinitionArtifact, CONTRACT_DEF_ID): child_row,
        }
    )
    res = resolution or _FakeResolution(bundle=snapshot(contract_sha))
    return G.ExcelEntryDefinitionLoader(session=session, resolution=res), session, res  # type: ignore[arg-type]


def load_kwargs(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "entry_id": ENTRY,
        "frozen_bundle_id": BUNDLE_ID,
        "frozen_bundle_sha256": _d("task36-bundle-canonical"),
        "adapter_build": adapter_build(),
        "identity_inventory": G.parse_identity_inventory(inventory_payload()),
        "observed_structure": DECLARED_STRUCTURE,
        "observed_business_sheets": ["G7 披露表", "封面"],
        "observed_dynamic_columns": {
            "equity_changes": observed_columns(["公司甲", "公司乙", "公司甲"])
        },
    }
    base.update(over)
    return base


# ═══════════════════════════════════════════════════════════════════════════
# 3. 六类 frozen slot 分类（FS-1 ~ FS-5）
# ═══════════════════════════════════════════════════════════════════════════


class TestFrozenSlotClassification:
    """**Validates: Requirements 6.2**

    六条禁令各有自己的 error_code。共用类型时靠后那条会遮蔽靠前那条 ⇒ 变异 GREEN，
    Task 12/13/14 已连续三次实测过该形态。
    """

    def test_all_six_causes_have_distinct_types_and_error_codes(self) -> None:
        types = list(G.FROZEN_SLOT_FAILURE_CAUSES.values())
        codes = [t.error_code for t in types]
        assert len(set(types)) == 6, f"六类原因未各占一个类型: {types}"
        assert len(set(codes)) == 6, f"六类原因的 error_code 有重复: {codes}"
        for cause, exc_type in G.FROZEN_SLOT_FAILURE_CAUSES.items():
            assert issubclass(exc_type, G.ExcelEntryGateError), cause

    def test_every_declared_cause_is_actually_raised_in_production(self) -> None:
        """登记的六个类型必须**真的**在生产模块里被 raise（否则名单是死清册）。"""
        tree = ast.parse(_GATE_PY.read_text(encoding="utf-8"))
        raised = {
            node.exc.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Raise)
            and isinstance(node.exc, ast.Call)
            and isinstance(node.exc.func, ast.Name)
        }
        missing = sorted(
            t.__name__ for t in G.FROZEN_SLOT_FAILURE_CAUSES.values() if t.__name__ not in raised
        )
        assert not missing, f"登记但从不 raise 的异常类型（additive 死代码）: {missing}"

    @pytest.mark.parametrize(
        "slot",
        list(BundleSlot),
        ids=[s.value for s in BundleSlot],
    )
    def test_fs1_slot_omission_names_the_missing_column(self, slot: BundleSlot) -> None:
        raw = raw_bundle_map(_d("c"))
        dropped = G.SLOT_COLUMNS[slot][0]
        raw.pop(dropped)
        with pytest.raises(G.FrozenSlotOmittedError) as exc:
            G.assert_frozen_slots_shape(raw)
        assert dropped in str(exc.value)
        assert exc.value.error_code == "frozen_bundle_slot_omitted"

    @pytest.mark.parametrize(
        "field_index,label",
        [(0, "type"), (1, "ref"), (2, "digest")],
        ids=["type", "ref", "digest"],
    )
    def test_fs2_null_is_separate_from_blank(self, field_index: int, label: str) -> None:
        column = G.SLOT_COLUMNS[BundleSlot.instrumentation][field_index]
        with pytest.raises(G.FrozenSlotNullError) as null_exc:
            G.assert_frozen_slots_shape(raw_bundle_map(_d("c"), **{column: None}))
        assert column in str(null_exc.value)
        assert null_exc.value.error_code == "frozen_bundle_slot_null"

        with pytest.raises(G.FrozenSlotBlankError) as blank_exc:
            G.assert_frozen_slots_shape(raw_bundle_map(_d("c"), **{column: "   "}))
        assert column in str(blank_exc.value)
        assert blank_exc.value.error_code == "frozen_bundle_slot_blank"

    def test_fs4_all_zero_digest_is_its_own_cause(self) -> None:
        column = G.SLOT_COLUMNS[BundleSlot.contract][2]
        with pytest.raises(G.FrozenSlotAllZeroDigestError) as exc:
            G.assert_frozen_slots_shape(raw_bundle_map(_d("c"), **{column: G.ALL_ZERO_DIGEST}))
        assert column in str(exc.value)
        assert exc.value.error_code == "frozen_bundle_slot_all_zero_digest"

    @pytest.mark.parametrize(
        "bad_type",
        ["contract:none:v9", "template:none:v1", "marker", "Definition"],
        ids=["unregistered-version", "other-slot-marker", "bare-marker", "wrong-case"],
    )
    def test_fs5_illegal_marker(self, bad_type: str) -> None:
        cols = G.SLOT_COLUMNS[BundleSlot.contract]
        raw = raw_bundle_map(
            _d("c"), **{cols[0]: bad_type, cols[1]: f"marker:{bad_type}"}
        )
        with pytest.raises(G.FrozenSlotIllegalMarkerError) as exc:
            G.assert_frozen_slots_shape(raw)
        assert exc.value.error_code == "frozen_bundle_slot_illegal_marker"

    def test_registered_marker_for_its_own_slot_is_accepted(self) -> None:
        """反向自检：合法 marker 必须放行，否则上面四条测的是「一律拒绝」。"""
        marker = D.marker_for(BundleSlot.instrumentation)
        cols = G.SLOT_COLUMNS[BundleSlot.instrumentation]
        raw = raw_bundle_map(
            _d("c"),
            **{
                cols[0]: marker.slot_type,
                cols[1]: marker.slot_ref,
                cols[2]: marker.slot_digest,
            },
        )
        slots = G.assert_frozen_slots_shape(raw)
        assert slots[BundleSlot.instrumentation].slot_type == marker.slot_type

    def test_marker_digest_tampering_is_rejected(self) -> None:
        marker = D.marker_for(BundleSlot.instrumentation)
        cols = G.SLOT_COLUMNS[BundleSlot.instrumentation]
        raw = raw_bundle_map(
            _d("c"),
            **{
                cols[0]: marker.slot_type,
                cols[1]: marker.slot_ref,
                cols[2]: _d("not-the-registry-digest"),
            },
        )
        with pytest.raises(G.FrozenSlotIllegalMarkerError):
            G.assert_frozen_slots_shape(raw)

    def test_form_predicates_stay_delegated_to_models(self) -> None:
        """非全零但形态非法的 digest 仍由 `models.validate_bundle_slot` 判（不复制一份）。"""
        column = G.SLOT_COLUMNS[BundleSlot.template][2]
        with pytest.raises(BundleIntegrityError):
            G.assert_frozen_slots_shape(raw_bundle_map(_d("c"), **{column: "ABC"}))

    def test_happy_path_returns_all_three_typed_slots(self) -> None:
        slots = G.assert_frozen_slots_shape(raw_bundle_map(_d("c")))
        assert set(slots) == set(BundleSlot)
        assert all(spec.is_definition for spec in slots.values())

    def test_raw_slot_map_does_not_normalize(self) -> None:
        """`raw_slot_map_of` 必须原样搬运：归一会让 NULL/空串两条判据同时失效。"""
        column = G.SLOT_COLUMNS[BundleSlot.template][0]
        row = bundle_row(_d("c"))
        setattr(row, column, None)
        got = G.raw_slot_map_of(row)
        assert got[column] is None
        assert set(got) == {c for cols in G.SLOT_COLUMNS.values() for c in cols}

    def test_raw_slot_map_omits_absent_attributes(self) -> None:
        """键缺失与键为 NULL 必须可分辨 —— 否则 FS-1 与 FS-2 合流。"""
        column = G.SLOT_COLUMNS[BundleSlot.contract][1]
        partial = {k: v for k, v in raw_bundle_map(_d("c")).items() if k != column}
        got = G.raw_slot_map_of(partial)
        assert column not in got


# ═══════════════════════════════════════════════════════════════════════════
# 4. `_GT_SYNC` 业务枚举排除（Requirement 6.13 / 6.17）
# ═══════════════════════════════════════════════════════════════════════════


class TestMetadataSheetExclusion:
    """**Validates: Requirements 6.17**"""

    def test_business_enumeration_leak_names_the_first_offender(self) -> None:
        with pytest.raises(G.MetadataSheetLeakError) as exc:
            G.assert_metadata_sheet_excluded(
                ["封面", GT_SYNC_SHEET_NAME, "明细表"], where="entry x"
            )
        assert "第 1 项" in str(exc.value)
        assert exc.value.error_code == "excel_entry_metadata_sheet_leaked"

    def test_clean_enumeration_passes_and_keeps_order(self) -> None:
        names = ["审定表K11-1", GT_SYNC_SHEET_NAME, "明细表", "封面"]
        assert G.business_sheet_names(names) == ("审定表K11-1", "明细表", "封面")
        G.assert_metadata_sheet_excluded(G.business_sheet_names(names), where="entry x")

    def test_offline_import_meta_sheet_is_not_swept_up(self) -> None:
        """`_meta_` 是离线导入自有隐藏表，**不得**被本门排除（越界即导入全线失效）。"""
        assert G.business_sheet_names(["_meta_", "审定表"]) == ("_meta_", "审定表")

    def test_contract_may_not_declare_the_metadata_sheet(
        self, contracts_dir: Path
    ) -> None:
        payload = xlsx_payload()
        payload["sheets"][0]["excel_name"] = GT_SYNC_SHEET_NAME
        bad = C.parse_contract(payload, adapter_id=ENTRY)
        with pytest.raises(G.MetadataSheetLeakError) as exc:
            G.assert_contract_declares_no_metadata_sheet(bad)
        assert "excel_name" in str(exc.value)

    def test_declaration_and_runtime_enumeration_are_two_predicates(
        self, contract: C.SyncContract
    ) -> None:
        """契约干净时运行态判据仍要能红，反之亦然 —— 两条不得合并成一条。"""
        G.assert_contract_declares_no_metadata_sheet(contract)
        with pytest.raises(G.MetadataSheetLeakError):
            G.assert_metadata_sheet_excluded([GT_SYNC_SHEET_NAME], where="entry x")


# ═══════════════════════════════════════════════════════════════════════════
# 5. 动态列 identity 与 label 解耦（Property 22）
# ═══════════════════════════════════════════════════════════════════════════


def observed_columns(labels: list[str], *, slot: str = "equity_changes") -> list[tuple[str, str]]:
    """把 label 序列配上**正确**的 `{slot}_{seq}` 键（happy path 输入）。"""
    return [(label, f"{slot}_{index}") for index, label in enumerate(labels, start=1)]


class TestDynamicColumnIdentity:
    """**Validates: Requirements 6.4**"""

    def test_renaming_labels_does_not_change_keys(self) -> None:
        before = G.assert_dynamic_columns_label_independent(
            slot="equity_changes", observed=observed_columns(["甲公司", "乙公司"]), where="t"
        )
        after = G.assert_dynamic_columns_label_independent(
            slot="equity_changes", observed=observed_columns(["改名了", "也改名了"]), where="t"
        )
        assert before == after == ("equity_changes_1", "equity_changes_2")

    def test_duplicate_labels_do_not_collide(self) -> None:
        keys = G.assert_dynamic_columns_label_independent(
            slot="equity_changes",
            observed=observed_columns(["同名", "同名", "同名"]),
            where="t",
        )
        assert len(set(keys)) == 3

    def test_label_derived_key_is_rejected(self) -> None:
        """真实缺陷形态①：运行态直接把中文 label 当列身份。"""
        with pytest.raises(G.DynamicColumnIdentityError) as exc:
            G.assert_dynamic_columns_label_independent(
                slot="equity_changes",
                observed=[("甲公司", "甲公司"), ("乙公司", "乙公司")],
                where="t",
            )
        assert "非 ASCII" in str(exc.value)
        assert exc.value.error_code == "excel_entry_dynamic_column_identity_invalid"

    def test_ascii_but_label_shaped_key_is_rejected(self) -> None:
        """形态门：ASCII 的 label（如英文简称）同样不得作列身份。"""
        with pytest.raises(G.DynamicColumnIdentityError) as exc:
            G.assert_dynamic_columns_label_independent(
                slot="equity_changes",
                observed=[("ACME", "acme"), ("BETA", "beta")],
                where="t",
            )
        assert "形态" in str(exc.value)

    def test_duplicate_observed_keys_are_their_own_cause(self) -> None:
        """真实缺陷形态②：两家同名公司共用一个键（H7 实测过的撞键）。"""
        with pytest.raises(G.DynamicColumnIdentityError) as exc:
            G.assert_dynamic_columns_label_independent(
                slot="equity_changes",
                observed=[("同名", "equity_changes_1"), ("同名", "equity_changes_1")],
                where="t",
            )
        assert "冲突" in str(exc.value)

    def test_reordered_or_renumbered_keys_are_rejected(self) -> None:
        """真实缺陷形态③：按 label 排序后重新编号 ⇒ 与 label 无关的派生结果不等。"""
        with pytest.raises(G.DynamicColumnIdentityError) as exc:
            G.assert_dynamic_columns_label_independent(
                slot="equity_changes",
                observed=[("甲", "equity_changes_2"), ("乙", "equity_changes_1")],
                where="t",
            )
        assert "派生键" in str(exc.value)

    def test_key_shape_is_derived_from_the_contract_template(self) -> None:
        """形态正则由 `DYNAMIC_COLUMN_IDENTITY_TEMPLATE` 派生，不是写死的 `_\\d+`。"""
        assert C.DYNAMIC_COLUMN_IDENTITY_TEMPLATE == "{slot}_{seq}"
        pattern = G._dynamic_key_pattern("equity_changes")
        assert pattern.match("equity_changes_1")
        assert not pattern.match("equity_changes_0")
        assert not pattern.match("equity_changes_甲")
        assert not pattern.match("equity_changesX1")

    @given(labels=st.lists(st.text(min_size=0, max_size=6), min_size=0, max_size=12))
    @_HYP
    def test_property22_keys_are_label_independent_and_unique(
        self, labels: list[str]
    ) -> None:
        """**Validates: Requirements 6.4**

        Property 22：对任意 label 序列（含空串、重名、中文），键集合只由长度决定且互不相同。
        """
        keys = G.dynamic_column_stable_keys(slot="tbl", count=len(labels))
        assert len(keys) == len(labels)
        assert len(set(keys)) == len(keys)
        for key in keys:
            assert key.isascii()
        # 长度相同 ⇒ 键逐项相同（与 label 内容无关）
        assert keys == G.dynamic_column_stable_keys(slot="tbl", count=len(labels))

    def test_declared_dynamic_table_without_observed_columns_fails_closed(
        self, contract: C.SyncContract
    ) -> None:
        with pytest.raises(G.DynamicColumnIdentityError) as exc:
            G._assert_dynamic_columns_declared(contract, {})
        assert "equity_changes" in str(exc.value)

    def test_observed_columns_for_undeclared_table_fail_closed(
        self, contract: C.SyncContract
    ) -> None:
        with pytest.raises(G.DynamicColumnIdentityError) as exc:
            G._assert_dynamic_columns_declared(
                contract,
                {
                    "equity_changes": observed_columns(["甲"]),
                    "header_block": observed_columns(["乙"], slot="header_block"),
                },
            )
        assert "header_block" in str(exc.value)


# ═══════════════════════════════════════════════════════════════════════════
# 6. identity inventory（Requirement 6.15 / 6.16 / Property 23 / 66）
# ═══════════════════════════════════════════════════════════════════════════


class TestIdentityInventory:
    """**Validates: Requirements 6.15**"""

    def test_happy_path(self, contract: C.SyncContract) -> None:
        inv = G.parse_identity_inventory(inventory_payload())
        G.assert_identity_inventory_usable(inv, contract=contract, entry_id=ENTRY)

    @pytest.mark.parametrize(
        "mutate,needle",
        [
            ({"hidden_sheet": {"present": False, "is_hidden": False}}, "反读失败"),
            (
                {
                    "hidden_sheet": {
                        "present": True,
                        "is_hidden": True,
                        "excluded_from_business_enumeration": False,
                    }
                },
                "未被业务 sheet 枚举排除",
            ),
            ({"defined_name": {"names": []}}, "defined name"),
            ({"excel_table": {"present": False, "table_ref": ""}}, "Excel Table"),
        ],
        ids=["hidden-sheet-gone", "not-excluded", "no-defined-name", "no-table"],
    )
    def test_each_missing_carrier_fails_closed(
        self, contract: C.SyncContract, mutate: dict[str, Any], needle: str
    ) -> None:
        inv = G.parse_identity_inventory(inventory_payload(**mutate))
        with pytest.raises(G.IdentityInventoryError) as exc:
            G.assert_identity_inventory_usable(inv, contract=contract, entry_id=ENTRY)
        assert needle in str(exc.value)

    @pytest.mark.parametrize(
        "resolved_by",
        ["sheet_id", "sheet_display_name", None],
        ids=["sheet-id-falsified", "display-name-falsified", "identity-column-deleted"],
    )
    def test_forbidden_sheet_anchors_are_rejected(
        self, contract: C.SyncContract, resolved_by: str | None
    ) -> None:
        """Task 5 实测 `sheet_id` / sheet 展示名在 OO 9.4 上 failed ⇒ 生产反读只能走 table。"""
        column = dict(inventory_payload()["hidden_uuid_column"])
        column["resolved_sheet_by"] = resolved_by
        inv = G.parse_identity_inventory(inventory_payload(hidden_uuid_column=column))
        with pytest.raises(G.IdentityInventoryError) as exc:
            G.assert_identity_inventory_usable(inv, contract=contract, entry_id=ENTRY)
        assert "excel_table_sheet_association" in str(exc.value)

    def test_first_empty_row_uuid_is_named(self, contract: C.SyncContract) -> None:
        column = dict(inventory_payload()["hidden_uuid_column"])
        column["empty_row_uuids"] = ["11", "12"]
        inv = G.parse_identity_inventory(inventory_payload(hidden_uuid_column=column))
        with pytest.raises(G.IdentityInventoryError) as exc:
            G.assert_identity_inventory_usable(inv, contract=contract, entry_id=ENTRY)
        assert "'11'" in str(exc.value)

    def test_first_duplicate_row_uuid_is_named(self, contract: C.SyncContract) -> None:
        column = dict(inventory_payload()["hidden_uuid_column"])
        column["duplicate_row_uuids"] = ["GTROW-G7-0008"]
        inv = G.parse_identity_inventory(inventory_payload(hidden_uuid_column=column))
        with pytest.raises(G.IdentityInventoryError) as exc:
            G.assert_identity_inventory_usable(inv, contract=contract, entry_id=ENTRY)
        assert "GTROW-G7-0008" in str(exc.value)

    def test_dynamic_row_table_without_any_identity_names_the_first_table(
        self, contract: C.SyncContract
    ) -> None:
        """Property 23：契约声明动态行却零 row identity ⇒ 拒绝，并点名首张表。"""
        column = dict(inventory_payload()["hidden_uuid_column"])
        column["row_uuids"] = {}
        inv = G.parse_identity_inventory(inventory_payload(hidden_uuid_column=column))
        with pytest.raises(G.IdentityInventoryError) as exc:
            G.assert_identity_inventory_usable(inv, contract=contract, entry_id=ENTRY)
        assert "equity_changes" in str(exc.value)

    def test_static_only_contract_needs_no_row_identity(
        self, contracts_dir: Path
    ) -> None:
        """反向：纯静态 entry（无 row_identity）不得因「零 row UUID」被误拒。"""
        payload = xlsx_payload()
        payload["sheets"][0]["tables"] = [payload["sheets"][0]["tables"][1]]
        static = C.parse_contract(payload, adapter_id=ENTRY)
        column = dict(inventory_payload()["hidden_uuid_column"])
        column["row_uuids"] = {}
        inv = G.parse_identity_inventory(inventory_payload(hidden_uuid_column=column))
        G.assert_identity_inventory_usable(inv, contract=static, entry_id=ENTRY)

    def test_missing_inventory_section_is_not_degraded_to_no_identity(self) -> None:
        with pytest.raises(G.IdentityInventoryError) as exc:
            G.parse_identity_inventory({"hidden_sheet": {}, "defined_name": {}})
        assert "excel_table" in str(exc.value)


# ═══════════════════════════════════════════════════════════════════════════
# 7. adapter build
# ═══════════════════════════════════════════════════════════════════════════


class TestAdapterBuild:
    """**Validates: Requirements 6.2**"""

    def test_happy_path(self, contract: C.SyncContract) -> None:
        G.assert_adapter_build_usable(
            adapter_build(),
            contract=contract,
            bundle=snapshot(contract.canonical_sha256),
            entry_id=ENTRY,
        )

    @pytest.mark.parametrize(
        "over,needle",
        [
            ({"adapter_build_digest": G.ALL_ZERO_DIGEST}, "adapter_build_digest"),
            ({"adapter_id": "d2.receivables"}, "双向锁死"),
            ({"document_type": "docx"}, "document_type"),
            ({"contract_version": "0.9.0"}, "contract_version"),
        ],
        ids=["all-zero-build-digest", "borrowed-contract", "wrong-doc-type", "stale-version"],
    )
    def test_each_mismatch_fails_closed(
        self, contract: C.SyncContract, over: dict[str, Any], needle: str
    ) -> None:
        with pytest.raises(G.AdapterBuildError) as exc:
            G.assert_adapter_build_usable(
                adapter_build(**over),
                contract=contract,
                bundle=snapshot(contract.canonical_sha256),
                entry_id=ENTRY,
            )
        assert needle in str(exc.value)

    def test_non_projection_authority_model_is_rejected(
        self, contract: C.SyncContract
    ) -> None:
        with pytest.raises(G.AdapterBuildError) as exc:
            G.assert_adapter_build_usable(
                adapter_build(),
                contract=contract,
                bundle=snapshot(
                    contract.canonical_sha256,
                    authority=AuthorityModel.custom_authoritative_ooxml,
                ),
                entry_id=ENTRY,
            )
        assert "projection_contract" in str(exc.value)


# ═══════════════════════════════════════════════════════════════════════════
# 8. candidate 证据（roundtrip / visible equivalence / probe gate）
# ═══════════════════════════════════════════════════════════════════════════


class TestCandidateEvidence:
    """**Validates: Requirements 6.16, 6.17, 6.18**"""

    def test_happy_path(self) -> None:
        blob = evidence_bytes(instrumented_sha=_d("instrumented"))
        got = G.parse_candidate_evidence(
            report_bytes=blob,
            expected_sha256=hashlib.sha256(blob).hexdigest(),
            entry_id=ENTRY,
        )
        assert got.instrumented_sha256 == _d("instrumented")
        assert got.identity_inventory.resolved_sheet_by == "table_sheet"

    def test_digest_mismatch_blocks_borrowed_evidence(self) -> None:
        blob = evidence_bytes(instrumented_sha=_d("instrumented"))
        with pytest.raises(G.CandidateEvidenceError) as exc:
            G.parse_candidate_evidence(
                report_bytes=blob, expected_sha256=_d("someone-else"), entry_id=ENTRY
            )
        assert "顶替" in str(exc.value)

    def test_other_entry_evidence_is_rejected(self) -> None:
        blob = evidence_bytes(instrumented_sha=_d("i"), entry_id="d2.receivables")
        with pytest.raises(G.CandidateEvidenceError) as exc:
            G.parse_candidate_evidence(
                report_bytes=blob,
                expected_sha256=hashlib.sha256(blob).hexdigest(),
                entry_id=ENTRY,
            )
        assert "d2.receivables" in str(exc.value)

    def test_failed_visible_equivalence_is_rejected(self) -> None:
        blob = evidence_bytes(
            instrumented_sha=_d("i"),
            visible_equivalence={
                "equivalent": False,
                "aspect_verdicts": {"formulas": False, "visible_sheets": True},
                "metadata_sheet_excluded_from_business": True,
            },
        )
        with pytest.raises(G.CandidateEvidenceError) as exc:
            G.parse_candidate_evidence(
                report_bytes=blob,
                expected_sha256=hashlib.sha256(blob).hexdigest(),
                entry_id=ENTRY,
            )
        assert "formulas" in str(exc.value)

    def test_metadata_sheet_not_excluded_is_rejected(self) -> None:
        blob = evidence_bytes(
            instrumented_sha=_d("i"),
            visible_equivalence={
                "equivalent": True,
                "aspect_verdicts": {},
                "metadata_sheet_excluded_from_business": False,
            },
        )
        with pytest.raises(G.CandidateEvidenceError) as exc:
            G.parse_candidate_evidence(
                report_bytes=blob,
                expected_sha256=hashlib.sha256(blob).hexdigest(),
                entry_id=ENTRY,
            )
        assert "业务枚举" in str(exc.value)

    @pytest.mark.parametrize(
        "key",
        ["carrier_contract_sha256", "onlyoffice_build"],
        ids=["carrier-contract", "oo-build"],
    )
    def test_probe_gate_identity_is_required(self, key: str) -> None:
        """Property 66：载体没过真实 OO 9.4 探针时不得 finalize。"""
        gate_payload = {
            "carrier_contract_sha256": _d("carrier"),
            "onlyoffice_build": "9.4.0",
        }
        gate_payload[key] = ""
        blob = evidence_bytes(instrumented_sha=_d("i"), probe_gate=gate_payload)
        with pytest.raises(G.CandidateEvidenceError) as exc:
            G.parse_candidate_evidence(
                report_bytes=blob,
                expected_sha256=hashlib.sha256(blob).hexdigest(),
                entry_id=ENTRY,
            )
        assert key in str(exc.value)

    def test_missing_required_key_is_named(self) -> None:
        payload = json.loads(evidence_bytes(instrumented_sha=_d("i")).decode("utf-8"))
        payload.pop("identity_inventory")
        blob = D.canonical_json_bytes(payload)
        with pytest.raises(G.CandidateEvidenceError) as exc:
            G.parse_candidate_evidence(
                report_bytes=blob,
                expected_sha256=hashlib.sha256(blob).hexdigest(),
                entry_id=ENTRY,
            )
        assert "identity_inventory" in str(exc.value)

    def test_required_keys_match_task17_writer(self) -> None:
        """本门要求的键必须真的是 Task 17 写进报告的键（两侧不得漂移）。"""
        src = (_SYNC_DIR / "excel_instrumentation.py").read_text(encoding="utf-8")
        for key in G.REQUIRED_EQUIVALENCE_KEYS:
            assert f'"{key}"' in src, (
                f"本门要求 equivalence 报告含 {key!r}，但 Task 17 的写入侧没有这个键 —— "
                "两侧漂移会让所有 candidate 恒被拒"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 9. loader（frozen FK/digest → immutable children → inventory → adapter build）
# ═══════════════════════════════════════════════════════════════════════════


class TestLoader:
    """**Validates: Requirements 6.2, 6.10, 6.20**"""

    @pytest.mark.asyncio
    async def test_happy_path_loads_frozen_identity(self, contract: C.SyncContract) -> None:
        loader, session, res = build_loader(contract.canonical_sha256)
        got = await loader.load(**load_kwargs())
        assert got.entry_id == ENTRY
        assert got.contract.contract_id == ENTRY
        assert got.bundle.bundle_id == BUNDLE_ID
        assert got.dynamic_column_keys == {
            "equity_changes": ("equity_changes_1", "equity_changes_2", "equity_changes_3")
        }
        assert got.business_sheets == ("G7 披露表", "封面")
        assert res.bundle_calls == [BUNDLE_ID], "没有真的过 Task 12 的 bundle 深度校验"
        assert (WorkpaperSyncDefinitionBundle.__name__, BUNDLE_ID) in session.queries
        assert (WorkpaperSyncDefinitionArtifact.__name__, CONTRACT_DEF_ID) in session.queries

    @pytest.mark.asyncio
    async def test_bundle_row_is_read_by_frozen_fk(self, contract: C.SyncContract) -> None:
        loader, _, _ = build_loader(contract.canonical_sha256, row=None)
        with pytest.raises(G.FrozenBundleDigestMismatchError) as exc:
            await loader.load(**load_kwargs())
        assert "不存在" in str(exc.value)

    @pytest.mark.asyncio
    async def test_frozen_digest_mismatch_fails_closed(
        self, contract: C.SyncContract
    ) -> None:
        """Property 28：调用方冻结的 digest 与 row 不符 ⇒ 拒绝，不按当前 alias 顶替。"""
        loader, _, res = build_loader(contract.canonical_sha256)
        with pytest.raises(G.FrozenBundleDigestMismatchError) as exc:
            await loader.load(**load_kwargs(frozen_bundle_sha256=_d("stale-digest")))
        assert exc.value.error_code == "frozen_bundle_digest_mismatch"
        assert res.bundle_calls == [], "digest 不符时不该继续做深度校验"

    @pytest.mark.asyncio
    async def test_blank_frozen_digest_is_not_treated_as_wildcard(
        self, contract: C.SyncContract
    ) -> None:
        loader, _, _ = build_loader(contract.canonical_sha256)
        with pytest.raises(G.FrozenBundleDigestMismatchError) as exc:
            await loader.load(**load_kwargs(frozen_bundle_sha256=""))
        # 🔴 必须断言到**这一条**的文案：「digest 非法」与「digest 不一致」是两条判据，
        # 只断异常类型时把前者短路掉会被后者遮蔽（空串 != row digest）⇒ 变异判 GREEN。
        assert "非法" in str(exc.value)

    @pytest.mark.asyncio
    async def test_marker_cannot_impersonate_the_per_entry_contract(
        self, contract: C.SyncContract
    ) -> None:
        marker = D.marker_for(BundleSlot.contract)
        cols = G.SLOT_COLUMNS[BundleSlot.contract]
        row = bundle_row(contract.canonical_sha256)
        setattr(row, cols[0], marker.slot_type)
        setattr(row, cols[1], marker.slot_ref)
        setattr(row, cols[2], marker.slot_digest)
        loader, _, res = build_loader(contract.canonical_sha256, row=row)
        with pytest.raises(G.PerEntryContractUnapprovedError) as exc:
            await loader.load(**load_kwargs())
        assert exc.value.error_code == "per_entry_contract_missing_or_unapproved"
        assert res.bundle_calls == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "child,needle",
        [
            ("missing", "不存在的 definition"),
            ("wrong-kind", "kind="),
            ("candidate", "state="),
        ],
        ids=["child-missing", "wrong-kind", "unapproved"],
    )
    async def test_fs6_contract_child_states(
        self, contract: C.SyncContract, child: str, needle: str
    ) -> None:
        row_child: Any
        if child == "missing":
            row_child = None
        elif child == "wrong-kind":
            row_child = contract_child(contract.canonical_sha256, kind="instrumentation")
        else:
            row_child = contract_child(contract.canonical_sha256, state="candidate")
        loader, _, res = build_loader(contract.canonical_sha256, child=row_child)
        with pytest.raises(G.PerEntryContractUnapprovedError) as exc:
            await loader.load(**load_kwargs())
        assert needle in str(exc.value)
        assert res.bundle_calls == [], (
            "FS-6 必须先于 `load_bundle_snapshot`，否则它永远被 BundleIntegrityError 遮蔽"
        )

    @pytest.mark.asyncio
    async def test_contract_drift_from_frozen_slot_is_stale_adapter(
        self, contract: C.SyncContract
    ) -> None:
        """磁盘契约被改过而 bundle 未重发布 ⇒ Task 13 的 RG-10（本模块不重写一份）。"""
        drifted = _d("someone-edited-the-contract")
        row = bundle_row(contract.canonical_sha256)
        setattr(row, G.SLOT_COLUMNS[BundleSlot.contract][2], drifted)
        loader, _, _ = build_loader(
            contract.canonical_sha256,
            row=row,
            child=contract_child(drifted),
            resolution=_FakeResolution(
                bundle=snapshot(
                    contract.canonical_sha256,
                    contract_slot=BundleSlotSpec(
                        BundleSlot.contract,
                        "definition",
                        f"definition:{CONTRACT_DEF_ID}",
                        drifted,
                    ),
                )
            ),
        )
        with pytest.raises(StaleAdapterError):
            await loader.load(**load_kwargs())

    @pytest.mark.asyncio
    async def test_template_definition_drift_fails_closed(
        self, contract: C.SyncContract
    ) -> None:
        loader, _, _ = build_loader(
            contract.canonical_sha256,
            resolution=_FakeResolution(
                bundle=snapshot(contract.canonical_sha256, template_digest=_d("new-template"))
            ),
        )
        with pytest.raises(C.ContractDriftError):
            await loader.load(**load_kwargs())

    @pytest.mark.asyncio
    async def test_unapproved_bundle_snapshot_propagates(
        self, contract: C.SyncContract
    ) -> None:
        loader, _, _ = build_loader(
            contract.canonical_sha256,
            resolution=_FakeResolution(
                bundle=snapshot(contract.canonical_sha256, state=DefinitionState.candidate)
            ),
        )
        with pytest.raises(BundleIntegrityError):
            await loader.load(**load_kwargs())

    @pytest.mark.asyncio
    async def test_structure_drift_names_the_first_offender(
        self, contract: C.SyncContract
    ) -> None:
        loader, _, _ = build_loader(contract.canonical_sha256)
        observed = list(copy.deepcopy(DECLARED_STRUCTURE))
        observed[0] = (observed[0][0], observed[0][1], observed[0][2], "Z:row_identity")
        with pytest.raises(C.ContractDriftError) as exc:
            await loader.load(**load_kwargs(observed_structure=tuple(observed)))
        assert "closing_amount" in str(exc.value)

    @pytest.mark.asyncio
    async def test_metadata_sheet_in_business_enumeration_fails_closed(
        self, contract: C.SyncContract
    ) -> None:
        loader, _, _ = build_loader(contract.canonical_sha256)
        with pytest.raises(G.MetadataSheetLeakError):
            await loader.load(
                **load_kwargs(observed_business_sheets=["G7 披露表", GT_SYNC_SHEET_NAME])
            )

    @pytest.mark.asyncio
    async def test_contract_schema_errors_are_not_degraded(
        self, contracts_dir: Path, contract: C.SyncContract
    ) -> None:
        """Property 20/21：generated `col_a` 占位与缺字段必须原样上抛，禁 fail-open。"""
        payload = xlsx_payload()
        payload["sheets"][0]["tables"][0]["fields"][0]["stable_field_key"] = "col_a"
        (contracts_dir / f"{ENTRY}.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        loader, _, _ = build_loader(contract.canonical_sha256)
        with pytest.raises(C.ContractSchemaError) as exc:
            await loader.load(**load_kwargs())
        assert "col_" in str(exc.value)

    @pytest.mark.asyncio
    async def test_loader_never_resolves_a_registry_alias(
        self, contract: C.SyncContract, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Requirement 6.2：执行中不得解析当前 alias。判据是**真实执行**，不是 grep。"""

        def _boom(*_a: Any, **_k: Any) -> Any:
            raise AssertionError("loader 在执行中解析了 registry alias")

        monkeypatch.setattr(D.DefinitionAliasRegistry, "resolve_for_publish", _boom)
        monkeypatch.setattr(D.DefinitionAliasRegistry, "resolve_for_history", _boom)
        loader, _, _ = build_loader(contract.canonical_sha256)
        got = await loader.load(**load_kwargs())
        assert got.bundle.bundle_id == BUNDLE_ID

    def test_module_has_no_alias_surface_at_all(self) -> None:
        """结构侧：模块里不出现 alias 入口（行为判据的补充，不是替代）。"""
        src = _GATE_PY.read_text(encoding="utf-8")
        tree = ast.parse(src)
        names = {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        } | {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        for forbidden in (
            "DefinitionAliasRegistry",
            "resolve_for_publish",
            "resolve_for_history",
        ):
            assert forbidden not in names, f"loader 出现 alias 入口 {forbidden}"

    def test_loader_reuses_the_existing_predicates(self) -> None:
        """判据复用清册：任一条被换成本模块自写的副本都会让这里变红。"""
        tree = ast.parse(_GATE_PY.read_text(encoding="utf-8"))
        target = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "load"
        )
        called = {
            node.func.id
            for node in ast.walk(target)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        } | {
            node.func.attr
            for node in ast.walk(target)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        for required in (
            "assert_frozen_slots_shape",
            "load_bundle_snapshot",
            "assert_bundle_usable",
            "load_contract",
            "assert_authority_model_contract_pairing",
            "assert_contract_identity_frozen",
            "assert_no_structure_drift",
            "assert_identity_inventory_usable",
            "assert_adapter_build_usable",
            "assert_contract_declares_no_metadata_sheet",
            "assert_metadata_sheet_excluded",
        ):
            assert required in called, f"loader.load 不再调用 {required} ⇒ 判据被绕开"

    def test_contract_child_check_precedes_the_deep_snapshot(self) -> None:
        """源码顺序判据：FS-6 在 `load_bundle_snapshot` 之前（可达性的结构证明）。"""
        src = _GATE_PY.read_text(encoding="utf-8")
        tree = ast.parse(src)
        target = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "load"
        )
        fs6 = [
            node.lineno
            for node in ast.walk(target)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_assert_contract_child_approved"
        ]
        deep = [
            node.lineno
            for node in ast.walk(target)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "load_bundle_snapshot"
        ]
        assert fs6 and deep, (fs6, deep)
        assert min(fs6) < min(deep), (
            "FS-6 被挪到 `load_bundle_snapshot` 之后 ⇒ "
            "`PerEntryContractUnapprovedError` 成为不可达分支"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 10. finalize gate（Property 67）
# ═══════════════════════════════════════════════════════════════════════════


def build_gate(
    contract_sha: str,
    *,
    report: bytes,
    candidate: Any = None,
    coordinator: _RecordingCoordinator | None = None,
    row: Any = _DEFAULT,
    child: Any = _DEFAULT,
    resolution_bundle: Any = None,
) -> tuple[G.ExcelEntryFinalizeGate, _RecordingCoordinator, _FakeResolution]:
    res = _FakeResolution(
        bundle=resolution_bundle if resolution_bundle is not None else snapshot(contract_sha),
        candidate=candidate
        or _CandidateRow(report_sha=hashlib.sha256(report).hexdigest()),
    )
    loader, _, _ = build_loader(contract_sha, row=row, child=child, resolution=res)
    coord = coordinator or _RecordingCoordinator(outcome=finalize_outcome())
    gate = G.ExcelEntryFinalizeGate(loader=loader, resolution=res, coordinator=coord)  # type: ignore[arg-type]
    return gate, coord, res


def gate_kwargs(report: bytes, *, sha: str, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "project_id": PROJECT_ID,
        "entry_id": ENTRY,
        "candidate_id": CANDIDATE_ID,
        "staged_candidate": staged_candidate(sha),
        "frozen_bundle_sha256": _d("task36-bundle-canonical"),
        "adapter_build": adapter_build(),
        "observed_structure": DECLARED_STRUCTURE,
        "observed_business_sheets": ["G7 披露表", "封面"],
        "observed_dynamic_columns": {
            "equity_changes": observed_columns(["公司甲", "公司乙", "公司甲"])
        },
        "equivalence_report_bytes": report,
    }
    base.update(over)
    return base


class TestFinalizeGate:
    """**Validates: Requirements 6.18**"""

    @pytest.mark.asyncio
    async def test_happy_path_delegates_to_the_task25_only_exit(
        self, contract: C.SyncContract
    ) -> None:
        sha = _d("instrumented-bytes")
        report = evidence_bytes(instrumented_sha=sha)
        gate, coord, res = build_gate(contract.canonical_sha256, report=report)
        outcome = await gate.finalize_candidate(**gate_kwargs(report, sha=sha))
        assert len(coord.calls) == 1
        assert res.candidate_calls == [CANDIDATE_ID]
        assert outcome.revision_unchanged
        call = coord.calls[0]
        assert call["adapter_id"] == ENTRY
        assert call["adapter_build_digest"] == ADAPTER_BUILD
        assert call["document_type"] == "xlsx"
        assert call["candidate_id"] == CANDIDATE_ID
        # identity inventory digest 必须来自 candidate 证据，而不是随手造一个
        assert call["identity_inventory_sha256"] == D.canonical_digest(
            outcome.evidence.identity_inventory.inventory_digest_input
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "over,expected",
        [
            ({"frozen_bundle_sha256": _d("stale")}, G.FrozenBundleDigestMismatchError),
            (
                {"observed_business_sheets": [GT_SYNC_SHEET_NAME]},
                G.MetadataSheetLeakError,
            ),
            ({"observed_dynamic_columns": {}}, G.DynamicColumnIdentityError),
            (
                {"adapter_build": adapter_build(adapter_id=OTHER_ENTRY)},
                StaleAdapterError,
            ),
        ],
        ids=["digest-drift", "metadata-leak", "missing-dynamic-columns", "borrowed-contract"],
    )
    async def test_any_failed_precheck_writes_nothing(
        self, contract: C.SyncContract, over: dict[str, Any], expected: type[Exception]
    ) -> None:
        """Property 67：前置不过 ⇒ coordinator 一次都没被调 ⇒ 无 representation/pointer/revision。"""
        sha = _d("instrumented-bytes")
        report = evidence_bytes(instrumented_sha=sha)
        gate, coord, _ = build_gate(contract.canonical_sha256, report=report)
        with pytest.raises(expected):
            await gate.finalize_candidate(**gate_kwargs(report, sha=sha, **over))
        assert coord.calls == [], "前置失败却调了唯一写入出口 ⇒ 会留下半成品 representation"

    @pytest.mark.asyncio
    async def test_candidate_from_another_entry_is_rejected(
        self, contract: C.SyncContract
    ) -> None:
        sha = _d("instrumented-bytes")
        report = evidence_bytes(instrumented_sha=sha)
        gate, coord, _ = build_gate(
            contract.canonical_sha256,
            report=report,
            candidate=_CandidateRow(
                entry_id="d2.receivables", report_sha=hashlib.sha256(report).hexdigest()
            ),
        )
        with pytest.raises(G.EntryFinalizeGateError) as exc:
            await gate.finalize_candidate(**gate_kwargs(report, sha=sha))
        assert "d2.receivables" in str(exc.value)
        assert coord.calls == []

    @pytest.mark.asyncio
    async def test_candidate_without_approved_bundle_is_rejected(
        self, contract: C.SyncContract
    ) -> None:
        """Task 17 产出的 candidate（bundle 为空）必须在此被拒。"""
        sha = _d("instrumented-bytes")
        report = evidence_bytes(instrumented_sha=sha)
        gate, coord, _ = build_gate(
            contract.canonical_sha256,
            report=report,
            candidate=_CandidateRow(
                bundle_id=None, report_sha=hashlib.sha256(report).hexdigest()
            ),
        )
        with pytest.raises(G.PerEntryContractUnapprovedError):
            await gate.finalize_candidate(**gate_kwargs(report, sha=sha))
        assert coord.calls == []

    @pytest.mark.asyncio
    async def test_evidence_bytes_must_describe_the_artifact_being_published(
        self, contract: C.SyncContract
    ) -> None:
        report = evidence_bytes(instrumented_sha=_d("some-other-bytes"))
        gate, coord, _ = build_gate(contract.canonical_sha256, report=report)
        with pytest.raises(G.CandidateEvidenceError) as exc:
            await gate.finalize_candidate(
                **gate_kwargs(report, sha=_d("instrumented-bytes"))
            )
        assert "roundtrip" in str(exc.value)
        assert coord.calls == []

    @pytest.mark.asyncio
    async def test_staged_candidate_scope_mismatch_is_rejected(
        self, contract: C.SyncContract
    ) -> None:
        sha = _d("instrumented-bytes")
        report = evidence_bytes(instrumented_sha=sha)
        gate, coord, _ = build_gate(contract.canonical_sha256, report=report)
        with pytest.raises(G.EntryFinalizeGateError):
            await gate.finalize_candidate(
                **gate_kwargs(
                    report, sha=sha, staged_candidate=staged_candidate(sha, entry_id="h1.x")
                )
            )
        assert coord.calls == []

    @pytest.mark.asyncio
    async def test_missing_coordinator_fails_visible(self, contract: C.SyncContract) -> None:
        sha = _d("instrumented-bytes")
        report = evidence_bytes(instrumented_sha=sha)
        gate, _, _ = build_gate(contract.canonical_sha256, report=report)
        gate._coordinator = None  # type: ignore[attr-defined]
        with pytest.raises(G.EntryFinalizeGateError) as exc:
            await gate.finalize_candidate(**gate_kwargs(report, sha=sha))
        assert "finalize_definition_upgrade" in str(exc.value)

    @pytest.mark.asyncio
    async def test_result_bundle_must_equal_the_frozen_one(
        self, contract: C.SyncContract
    ) -> None:
        sha = _d("instrumented-bytes")
        report = evidence_bytes(instrumented_sha=sha)
        gate, coord, _ = build_gate(
            contract.canonical_sha256,
            report=report,
            coordinator=_RecordingCoordinator(
                outcome=finalize_outcome(bundle_id=uuid.uuid4())
            ),
        )
        with pytest.raises(G.FrozenBundleDigestMismatchError):
            await gate.finalize_candidate(**gate_kwargs(report, sha=sha))
        assert len(coord.calls) == 1

    @pytest.mark.asyncio
    async def test_equivalence_report_is_read_from_the_candidate_directory(
        self, contract: C.SyncContract, tmp_path: Path
    ) -> None:
        """不传 `equivalence_report_bytes` 时走真实文件读取（路径由 StagedCandidate 携带）。"""
        sha = _d("instrumented-bytes")
        report = evidence_bytes(instrumented_sha=sha)
        cdir = tmp_path / "cand"
        cdir.mkdir()
        (cdir / "equivalence-abc.json").write_bytes(report)
        gate, coord, _ = build_gate(contract.canonical_sha256, report=report)
        outcome = await gate.finalize_candidate(
            **gate_kwargs(
                report,
                sha=sha,
                staged_candidate=staged_candidate(sha, tmp=cdir),
                equivalence_report_bytes=None,
            )
        )
        assert len(coord.calls) == 1
        assert outcome.evidence.report_sha256 == hashlib.sha256(report).hexdigest()

    @pytest.mark.asyncio
    async def test_missing_report_file_fails_visible(
        self, contract: C.SyncContract, tmp_path: Path
    ) -> None:
        sha = _d("instrumented-bytes")
        report = evidence_bytes(instrumented_sha=sha)
        gate, coord, _ = build_gate(contract.canonical_sha256, report=report)
        with pytest.raises(G.CandidateEvidenceError) as exc:
            await gate.finalize_candidate(
                **gate_kwargs(
                    report,
                    sha=sha,
                    staged_candidate=staged_candidate(sha, tmp=tmp_path / "nope"),
                    equivalence_report_bytes=None,
                )
            )
        assert "读不到" in str(exc.value)
        assert coord.calls == []


# ═══════════════════════════════════════════════════════════════════════════
# 11. 结构判据：唯一出口、无写入面、Tasks 40~57 的可复用性
# ═══════════════════════════════════════════════════════════════════════════


class TestGateShape:
    """**Validates: Requirements 6.18**"""

    def test_the_only_write_path_is_task25_and_it_comes_last(self) -> None:
        tree = ast.parse(_GATE_PY.read_text(encoding="utf-8"))
        target = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "finalize_candidate"
        )
        exits = [
            node.lineno
            for node in ast.walk(target)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "finalize_definition_upgrade"
        ]
        assert len(exits) == 1, f"definitions-only 升级出口不唯一: {exits}"
        prechecks = [
            node.lineno
            for node in ast.walk(target)
            if isinstance(node, ast.Call)
            and (
                (isinstance(node.func, ast.Name) and node.func.id.startswith(("assert_", "parse_")))
                or (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr
                    in {"assert_candidate_finalizable", "load", "_read_equivalence_report"}
                )
            )
        ]
        assert prechecks, "finalize_candidate 里一条前置校验都没有"
        assert max(prechecks) < exits[0], (
            f"有前置校验排在唯一写入出口之后（前置 {sorted(prechecks)} vs 出口 {exits[0]}）"
            " —— 那部分校验对「失败不产生 representation」毫无作用"
        )

    def test_task25_really_exposes_that_exit(self) -> None:
        """反向自检：出口方法名必须真的存在于 Task 25，否则接线是静默 AttributeError。"""
        from app.services.workpaper_sync.materialize_coordinator import MaterializeCoordinator

        assert callable(getattr(MaterializeCoordinator, "finalize_definition_upgrade", None))

    def test_gate_does_not_reach_around_task25(self) -> None:
        """gate 不得自己调 Task 15/仓储的写入面（那会绕过 revision 域门面）。"""
        src = _GATE_PY.read_text(encoding="utf-8")
        tree = ast.parse(src)
        called = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        } | {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        for forbidden in (
            "finalize_candidate_artifact",
            "create_representation",
            "set_entry_pointer",
            "bump_content_revision",
            "set_current_content_version",
            "register_artifact",
            "commit",
        ):
            assert forbidden not in called, (
                f"gate 直接调用了 {forbidden} —— definitions-only 升级只能经 Task 25 的"
                "唯一出口，绕过它就绕过了 `RevisionLockedRepository`"
            )

    def test_gate_calls_representation_service_only_through_the_coordinator(self) -> None:
        """判据是「**导入/使用** RepresentationService」，不是「出现这个词」。

        🔴 首轮实测：按词判会被本模块 docstring 里那句「Task 15 的
        `RepresentationService.finalize_candidate` 能在单事务里…」打成假红 —— 与
        `test_task13` 里 `FORBIDDEN_SIDE_EFFECT_ATTRS` 名单被误判成调用同源。
        """
        tree = ast.parse(_GATE_PY.read_text(encoding="utf-8"))
        imported = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert "RepresentationService" not in imported, (
            "gate 导入了 RepresentationService ⇒ 出现第二条 definitions-only 升级路径，"
            "绕过 Task 25 的唯一出口"
        )
        used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        assert "RepresentationService" not in used

    def test_the_denylist_vs_call_distinction_is_real(self) -> None:
        """反向自检：写在文档/字符串里的名字不算使用，真引用必须被抓（防上一条假绿）。"""
        doc_only = ast.parse('"""见 RepresentationService.finalize_candidate。"""\n')
        real = ast.parse("from x import RepresentationService\n")
        names = lambda tree: {  # noqa: E731
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert "RepresentationService" not in names(doc_only), "文档提及被误判成导入 ⇒ 假红"
        assert "RepresentationService" in names(real), "真导入没被抓 ⇒ 假绿"

    def test_module_declares_no_pilot_specific_entry(self) -> None:
        """本模块不得内置任何 pilot 的 entry_id/contract_id（复用别人的契约是明令禁止的）。"""
        src = _GATE_PY.read_text(encoding="utf-8")
        for pilot in ("g7.disclosure", "d2.receivables", "h1.", "checklist."):
            assert pilot not in src, (
                f"生产模块里出现 pilot 专属身份 {pilot!r} —— Tasks 40~57 必须各自带自己的"
                "contract/bundle/candidate，gate 不得预置或复用"
            )

    def test_slot_columns_match_the_orm_model(self) -> None:
        """`SLOT_COLUMNS` 的列名必须真的在 ORM 模型上（写错一个字母就静默 KeyError）。"""
        for slot, columns in G.SLOT_COLUMNS.items():
            for column in columns:
                assert hasattr(WorkpaperSyncDefinitionBundle, column), (
                    f"{slot.value} slot 登记的列 {column!r} 不在 "
                    "WorkpaperSyncDefinitionBundle 上"
                )

    def test_slot_columns_cover_every_bundle_slot(self) -> None:
        assert set(G.SLOT_COLUMNS) == set(BundleSlot)

    def test_no_broad_except_in_the_module(self) -> None:
        """禁 fail-open：`except Exception` 会把接线错误吞成「本项目无此数据」。"""
        tree = ast.parse(_GATE_PY.read_text(encoding="utf-8"))
        broad = [
            handler.lineno
            for handler in ast.walk(tree)
            if isinstance(handler, ast.ExceptHandler)
            and (
                handler.type is None
                or (isinstance(handler.type, ast.Name) and handler.type.id in {"Exception", "BaseException"})
            )
        ]
        assert not broad, f"出现宽泛 except（fail-open）于行 {broad}"

    def test_every_exception_has_its_own_error_code(self) -> None:
        module_errors = [
            obj
            for name, obj in vars(G).items()
            if inspect.isclass(obj)
            and issubclass(obj, G.ExcelEntryGateError)
            and obj.__module__ == G.__name__
            and obj is not G.ExcelEntryGateError
        ]
        codes = [obj.error_code for obj in module_errors]
        assert len(codes) == len(set(codes)), f"error_code 有重复: {sorted(codes)}"
        assert len(module_errors) >= 6
