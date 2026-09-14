# -*- coding: utf-8 -*-
"""Task 37 守卫：Excel identity-aware extractor 与共用 roundtrip / unmanaged verifier。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 3 Task 37
Requirements: 6.5, 6.6, 6.7, 6.8, 6.9, 6.11, 6.12, 6.15, 6.16, 6.20, 8.11, 14.11, 14.12
Properties: **P23** / **P24** / **P27** / **P29** / **P60** / **P66**

═══ 为什么用**真实权威模板**做 fixture ═══

`backend/wp_templates/K/K11 资产减值损失.xlsx` 带来 7 张 sheet、450 条公式、54 处 merge、
1 个 drawing。手搓的最小 xlsx 上「未管理区域」是空集，`equivalent == True` 恒真 ⇒ 判据空
转（假绿第③源：把空值当基线锁死）。本文件的 `test_unmanaged_region_coverage_is_not_empty`
把「8 个 aspect 的覆盖计数全部 > 0」当硬判据，正是为了让空转不可能通过。

fixture 链条：真实模板 → Task 17 `instrument_workbook_bytes`（注入真载体）→ 真实 zip
字节编辑写入业务值 → 落盘 → 生产 extractor 反读。**不 mock** 任何一层。

═══ 判据形态（逐条对应 tasks.md 的四类假绿）═══

1. **不用 presence 式断言**：所有「某能力接没接」都落在真实执行结果上 —— 例如「预算门
   真的挂在 extract 上」是靠缩小预算后真跑一次 extract 打红来证明的，不是 grep 调用点。
2. **五类身份/保护异常各自可达且可分辨**：`test_five_anomaly_classes_are_each_reachable`
   把它们的 `SchemaAnomalyKind` / `FormulaTamperKind` 收集起来，断言互不相同 ——
   共用一个错误码会让较早分支永久不可达，那是本 spec 已出现 3 次的形态。
3. **不自证同义反复**：期望值一律写字面量或从**源侧**（instrumented workbook 的
   `row_uuids` / Table ref）推导，绝不调用被测函数算期望。
4. **N-1/N/N+1 真的构造三侧样本**：行/field 预算用生产数字驱动纯门，并用**缩小的**预算
   在真实 artifact 上端到端跑一遍，证明它挂在 extract 里而不是只存在于 limits 模块。
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import sys
import uuid
import zipfile
from pathlib import Path
from typing import Any, Mapping

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.excel_structure_fingerprint import (  # noqa: E402
    GT_SYNC_SHEET_NAME,
    identity_inventory,
)
from app.services.workpaper_sync import excel_extract as X  # noqa: E402
from app.services.workpaper_sync import excel_instrumentation as EI  # noqa: E402
from app.services.workpaper_sync.adapters.base import (  # noqa: E402
    AdapterCandidateSubstrateError,
    FieldValue,
    Projection,
    QuarantinedIncomingError,
    SubstrateRole,
    UnmanagedRegionDriftError,
)
from app.services.workpaper_sync.conflicts import (  # noqa: E402
    ConflictKind,
    SchemaAnomalyKind,
)
from app.services.workpaper_sync.contracts import (  # noqa: E402
    ExtractCarrierTier,
    FieldMode,
    ValueType,
    parse_contract,
)
from app.services.workpaper_sync.excel_entry_gate import (  # noqa: E402
    AdapterBuild,
    FrozenEntryDefinitions,
    parse_identity_inventory,
)
from app.services.workpaper_sync.limits import (  # noqa: E402
    BudgetExceededError,
    OoxmlPolicy,
    SyncLimits,
    load_limits,
)
from app.services.workpaper_sync.merge import merge_projections  # noqa: E402
from app.services.workpaper_sync.models import (  # noqa: E402
    ArtifactKind,
    ArtifactState,
    AuthorityModel,
    BundleSlot,
    BundleSlotSpec,
    DefinitionState,
)
from app.services.workpaper_sync.resolution import (  # noqa: E402
    DefinitionBundleSnapshot,
)

# ═══════════════════════════════════════════════════════════════════════════
# 0. 固定期望值（来自真实模板与 Task 5/17 实证，两侧互锁）
# ═══════════════════════════════════════════════════════════════════════════

TEMPLATE = _BACKEND / "wp_templates" / "K" / "K11 资产减值损失.xlsx"

#: Task 5 findings 记录的权威源 digest。本文件跑完必须仍是这个值（运行时不得写模板库）。
TEMPLATE_SHA = "dc0e5434b7c8e345913864ce524ad30a0a3729b5655627f3c30bce52294a9190"

ENTRY_ID = "k11.adjudication"
CONTRACT_ID = "k11.adjudication"
MANAGED_SHEET = "审定表K11-1"
TABLE_NAME = "GT_K11_1_ROWS"
UUID_COL = "N"
FIRST_ROW = 7
LAST_ROW = 25
FOOTER_ROW = 27

#: 期望的 Table ref（由 `ExcelInstrumentationSpec` 的行列区间决定，字面量写死以互锁）。
EXPECTED_TABLE_REF = "A7:N25"
#: 19 行（7..25）。
EXPECTED_ROW_COUNT = LAST_ROW - FIRST_ROW + 1

SPEC = EI.ExcelInstrumentationSpec(
    entry_id=ENTRY_ID,
    template_id="K11",
    template_relative_path="K/K11 资产减值损失.xlsx",
    managed_sheet=MANAGED_SHEET,
    first_data_row=FIRST_ROW,
    last_data_row=LAST_ROW,
    footer_row=26,
    managed_last_col="L",
    uuid_col=UUID_COL,
    table_name=TABLE_NAME,
)


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════
# 1. 真实 zip 字节编辑工具（不 mock，不用 openpyxl 重写整簿）
# ═══════════════════════════════════════════════════════════════════════════
#
# 🔴 用 openpyxl 全量重写会丢掉 drawing/chart，未管理区域 fixture 就没了内容 ⇒
#    「未管理区域不变」这条判据变成空转。因此一律 zip 级定点改字节。


def _read_entries(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def _write_entries(entries: Mapping[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for name, payload in entries.items():
            out.writestr(name, payload)
    return buf.getvalue()


def _sheet_part_of(data: bytes, sheet_name: str) -> str:
    entries = _read_entries(data)
    workbook = entries["xl/workbook.xml"].decode("utf-8")
    rels = entries["xl/_rels/workbook.xml.rels"].decode("utf-8")
    match = re.search(
        r'<sheet [^>]*name="' + re.escape(sheet_name) + r'"[^>]*r:id="(rId\d+)"', workbook
    )
    assert match, f"找不到 sheet {sheet_name!r}"
    rel = re.search(r'Id="' + match.group(1) + r'"[^>]*Target="([^"]+)"', rels)
    assert rel
    target = rel.group(1).lstrip("/")
    return target if target.startswith("xl/") else f"xl/{target}"


#: 单个 `<c r="COORD" .../>` 或 `<c r="COORD" ...>…</c>`。
#:
#: 🔴 自闭合分支必须在前、属性段必须**惰性**。写成 `(?: [^>]*)?(?:/>|>.*?</c>)` 时
#: `[^>]*` 会贪心吃掉 `s="56"/`，于是 `>.*?</c>` 从下一格开始一路吞到**下一个** `</c>`，
#: 把紧邻的隐藏 UUID 格 `<c r="N7">…</c>` 一起替换掉 —— 实测：改 J7 之后 N7 消失，
#: extract 报「一个 row identity 都没反读到」，看起来像守卫抓到了缺陷，其实是 fixture 坏了。
_CELL_RE = (
    '(?:<c r="{coord}"(?:\\s[^>]*?)?/>)' '|(?:<c r="{coord}"(?:\\s[^>]*?)?>.*?</c>)'
)
_ANY_CELL_RE = re.compile(
    r'<c r="([A-Z]+)(\d+)"(?:\s[^>]*?)?/>|<c r="([A-Z]+)(\d+)"(?:\s[^>]*?)?>.*?</c>',
    re.S,
)


def _col_index(letters: str) -> int:
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - 64)
    return idx


def _cell_xml(coord: str, value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str) and value.startswith("="):
        return f'<c r="{coord}"><f>{value[1:]}</f><v>0</v></c>'
    if isinstance(value, str):
        return (
            f'<c r="{coord}" t="inlineStr"><is>'
            f'<t xml:space="preserve">{value}</t></is></c>'
        )
    return f'<c r="{coord}"><v>{value}</v></c>'


def patch_cells(data: bytes, sheet_part: str, cells: Mapping[str, Any]) -> bytes:
    """在真实 sheet XML 上定点写/删单元格，按列序插入，保持 workbook 合法。"""
    entries = _read_entries(data)
    xml = entries[sheet_part].decode("utf-8")
    for coord, value in cells.items():
        column = re.match(r"[A-Z]+", coord).group(0)  # type: ignore[union-attr]
        row = int(re.search(r"\d+$", coord).group(0))  # type: ignore[union-attr]
        new = _cell_xml(coord, value)
        pattern = re.compile(_CELL_RE.format(coord=coord), re.S)
        if pattern.search(xml):
            xml = pattern.sub(new, xml, count=1)
            continue
        if not new:
            continue
        row_pat = re.compile(rf'(<row r="{row}"(?:\s[^>]*?)?>)(.*?)(</row>)', re.S)
        found = row_pat.search(xml)
        if found is None:
            xml = xml.replace(
                "</sheetData>", f'<row r="{row}">{new}</row></sheetData>', 1
            )
            continue
        body = found.group(2)
        target = _col_index(column)
        inserted = False
        out: list[str] = []
        for match in _ANY_CELL_RE.finditer(body):
            letters = match.group(1) or match.group(3)
            if not inserted and _col_index(letters) > target:
                out.append(new)
                inserted = True
            out.append(match.group(0))
        if not inserted:
            out.append(new)
        xml = xml[: found.start(2)] + "".join(out) + xml[found.end(2) :]
    entries[sheet_part] = xml.encode("utf-8")
    return _write_entries(entries)


def table_part_of(data: bytes) -> str:
    return next(name for name in _read_entries(data) if name.startswith("xl/tables/"))


def grow_table_to(data: bytes, last_row: int) -> bytes:
    """把 Excel Table 的 ref 行区间扩到 `last_row`（模拟 OO 在受管区域内插行）。"""
    return edit_part(
        data,
        table_part_of(data),
        lambda blob: blob.decode("utf-8")
        .replace(
            f'ref="{EXPECTED_TABLE_REF}"', f'ref="A{FIRST_ROW}:{UUID_COL}{last_row}"'
        )
        .encode("utf-8"),
    )


def add_row(
    data: bytes, sheet_part: str, *, row: int, cells: Mapping[str, Any]
) -> bytes:
    """在受管区域**末尾追加一行**：先扩 Table ref，再写该行的格。

    🔴 这是「OO 新增行」的正确 fixture 形态。早先版本改的是**已有行**（把第 25 行的 UUID
    清空/换成重复值），那在语义上是「原有 identity 消失」⇒ 先被保留门（Property 66）拦住，
    身份异常分类分支根本走不到 —— 「在真实数据上分支不可达 = 永久 GREEN」的典型。
    """
    return patch_cells(grow_table_to(data, row), sheet_part, cells)


def drop_part(data: bytes, part: str) -> bytes:
    entries = _read_entries(data)
    assert part in entries, part
    del entries[part]
    return _write_entries(entries)


def edit_part(data: bytes, part: str, transform: Any) -> bytes:
    entries = _read_entries(data)
    assert part in entries, part
    before = entries[part]
    after = transform(before)
    assert after != before, f"部件编辑未生效: {part}（用例会变成无效变异）"
    entries[part] = after
    return _write_entries(entries)


# ═══════════════════════════════════════════════════════════════════════════
# 2. 契约与 frozen 身份 fixture
# ═══════════════════════════════════════════════════════════════════════════


def contract_payload(
    *, delete_policy: str = "tombstone", with_dynamic_columns: bool = False
) -> dict[str, Any]:
    """一份 **reviewed** 的 per-entry 契约 payload。

    fixture 契约，不落 `backend/data/workpaper_sync_contracts/`：正式契约的发布是
    Tasks 40~57 的活（需要真实 template/instrumentation digest 与人工审核），
    在这里落盘会让 `available_contract_ids()` 多出一个假的生产 adapter。
    """
    rows_table: dict[str, Any] = {
        "table_key": "k11_rows",
        "anchor": f"A{FIRST_ROW}",
        "header_rows": 2,
        "row_identity": {"kind": "field", "json_pointer": "/rows/*/rowUuid"},
        "delete_policy": delete_policy,
        "formula_mask": [f"H{FIRST_ROW}:I{LAST_ROW}"],
        "footer_anchor": {"marker": "合计", "search_column": "A"},
        "fields": [
            {
                "stable_field_key": "k11_rows/{row_uuid}/adjustment",
                "json_pointer": "/rows/{row_uuid}/adjustment",
                "column_key": "adjustment",
                "cell": {"column": "C", "row_from": "row_identity"},
                "mode": "editable",
                "value_type": "amount",
                "source_ref": "源xlsx!审定表K11-1!C7",
            },
            {
                "stable_field_key": "k11_rows/{row_uuid}/reason",
                "json_pointer": "/rows/{row_uuid}/reason",
                "column_key": "reason",
                "cell": {"column": "J", "row_from": "row_identity"},
                "mode": "editable",
                "value_type": "text",
                "source_ref": "源xlsx!审定表K11-1!J7",
            },
            {
                "stable_field_key": "k11_rows/{row_uuid}/variance",
                "json_pointer": "/rows/{row_uuid}/variance",
                "column_key": "variance",
                "cell": {"column": "H", "row_from": "row_identity"},
                "mode": "formula",
                "value_type": "amount",
                "source_ref": "源xlsx!审定表K11-1!H7",
            },
        ],
    }
    if with_dynamic_columns:
        rows_table["dynamic_columns"] = {
            "identity": "{slot}_{seq}",
            "source_ref": "源xlsx!审定表K11-1!B6:G6",
        }
    return {
        "schema_version": "contract-definition:v1",
        "contract_id": CONTRACT_ID,
        "semantic_version": "1.0.0",
        "review_status": "reviewed",
        "document_type": "xlsx",
        "template_definition_sha256": _d("k11-template-definition"),
        "instrumentation_definition_sha256": _d("k11-instrumentation-definition"),
        "template": {
            "relative_path": "K/K11 资产减值损失.xlsx",
            "template_sha256": TEMPLATE_SHA,
            "normalized_structure_hash": _d("k11-normalized-structure"),
        },
        "identity_carriers": [
            "hidden_sheet",
            "defined_name",
            "excel_table",
            "hidden_uuid_column",
        ],
        "sheets": [
            {
                "sheet_key": "adjudication",
                "excel_name": MANAGED_SHEET,
                "locator": {"anchor": X.TABLE_SHEET_ANCHOR},
                "tables": [
                    rows_table,
                    {
                        "table_key": "k11_footer",
                        "anchor": f"A{FOOTER_ROW}",
                        "header_rows": 1,
                        "fields": [
                            {
                                "stable_field_key": "k11_footer/tb_amount",
                                "json_pointer": "/tbAmount",
                                "column_key": "tb_amount",
                                "cell": {"column": "B", "row_from": FOOTER_ROW},
                                "mode": "auto_source",
                                "value_type": "amount",
                                "source_ref": "trial_balance.audited_amount",
                            }
                        ],
                    },
                ],
            }
        ],
    }


def make_bundle(contract: Any, *, state: DefinitionState = DefinitionState.approved,
                contract_slot_digest: str | None = None) -> DefinitionBundleSnapshot:
    def slot(kind: BundleSlot, digest: str) -> BundleSlotSpec:
        return BundleSlotSpec(kind, "definition", f"definition:{uuid.uuid4()}", digest)

    return DefinitionBundleSnapshot(
        bundle_id=uuid.uuid4(),
        bundle_sha256=_d("k11-bundle"),
        schema_version="definition-bundle:v1",
        state=state,
        authority_model=AuthorityModel.projection_contract,
        authority_model_definition_id=uuid.uuid4(),
        authority_model_definition_sha256=_d("k11-authority"),
        slots={
            BundleSlot.template: slot(
                BundleSlot.template, contract.template_definition_sha256
            ),
            BundleSlot.instrumentation: slot(
                BundleSlot.instrumentation, contract.instrumentation_definition_sha256
            ),
            BundleSlot.contract: slot(
                BundleSlot.contract, contract_slot_digest or contract.canonical_sha256
            ),
        },
    )


def make_definitions(
    contract: Any, inventory_raw: Mapping[str, Any], **over: Any
) -> FrozenEntryDefinitions:
    payload: dict[str, Any] = {
        "entry_id": ENTRY_ID,
        "bundle": make_bundle(contract),
        "contract": contract,
        "adapter_build": AdapterBuild(
            adapter_id=CONTRACT_ID,
            adapter_build_digest=_d("k11-adapter-build"),
            document_type="xlsx",
            contract_version="1.0.0",
        ),
        "identity_inventory": parse_identity_inventory(inventory_raw),
        "business_sheets": (),
        "dynamic_column_keys": {},
        "structure_inventory_size": 0,
    }
    payload.update(over)
    return FrozenEntryDefinitions(**payload)  # type: ignore[arg-type]


BINDING = X.ExcelIdentityBinding(
    table_name=TABLE_NAME, uuid_column=UUID_COL, table_key="k11_rows"
)


# ═══════════════════════════════════════════════════════════════════════════
# 3. module 级 fixture：真实模板注入一次
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def instrumented() -> EI.InstrumentedWorkbook:
    gate = EI.ExcelIdentityCarrierGate.load()
    return EI.instrument_workbook_bytes(TEMPLATE.read_bytes(), SPEC, gate=gate)


@pytest.fixture(scope="module")
def sheet_part(instrumented: EI.InstrumentedWorkbook) -> str:
    return _sheet_part_of(instrumented.instrumented_bytes, MANAGED_SHEET)


def business_cells() -> dict[str, Any]:
    """写进受管区域的业务值：C 列金额、J 列文本、B27 的 TB 取数。"""
    cells: dict[str, Any] = {f"B{FOOTER_ROW}": 12345.67}
    for row in range(FIRST_ROW, LAST_ROW + 1):
        cells[f"C{row}"] = 100 + row
        cells[f"J{row}"] = f"原因{row}"
    return cells


@pytest.fixture(scope="module")
def base_bytes(instrumented: EI.InstrumentedWorkbook, sheet_part: str) -> bytes:
    return patch_cells(instrumented.instrumented_bytes, sheet_part, business_cells())


@pytest.fixture(scope="module")
def workdir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("task37")


@pytest.fixture(scope="module")
def base_path(base_bytes: bytes, workdir: Path) -> Path:
    path = workdir / "base.xlsx"
    path.write_bytes(base_bytes)
    return path


@pytest.fixture(scope="module")
def contract() -> Any:
    return parse_contract(contract_payload(), adapter_id=CONTRACT_ID)


@pytest.fixture(scope="module")
def base_inventory(base_bytes: bytes) -> dict[str, Any]:
    return identity_inventory(
        base_bytes, expected_table=TABLE_NAME, uuid_column_letter=UUID_COL
    )


@pytest.fixture(scope="module")
def definitions(contract: Any, base_inventory: dict[str, Any]) -> FrozenEntryDefinitions:
    return make_definitions(contract, base_inventory)


def write(workdir: Path, name: str, data: bytes) -> Path:
    path = workdir / name
    path.write_bytes(data)
    return path


def extract(
    path: Path, definitions: FrozenEntryDefinitions, **over: Any
) -> X.ExcelExtractOutcome:
    kwargs: dict[str, Any] = {
        "artifact": path,
        "definitions": definitions,
        "binding": BINDING,
        "substrate_role": SubstrateRole.incoming,
        "artifact_kind": ArtifactKind.incoming,
        "artifact_state": ArtifactState.durable,
    }
    kwargs.update(over)
    return X.extract_projection(**kwargs)


@pytest.fixture(scope="module")
def base_outcome(
    base_path: Path, definitions: FrozenEntryDefinitions
) -> X.ExcelExtractOutcome:
    return extract(base_path, definitions)


# ═══════════════════════════════════════════════════════════════════════════
# 4. 基线：identity-aware 反读的确定性事实
# ═══════════════════════════════════════════════════════════════════════════


class TestBaselineExtract:
    """**Validates: Requirements 6.7 / 6.20**"""

    def test_authority_template_is_untouched(self) -> None:
        """跑完全部注入与 zip 编辑，模板库字节必须原样（Requirement 9.9）。"""
        assert hashlib.sha256(TEMPLATE.read_bytes()).hexdigest() == TEMPLATE_SHA

    def test_projection_is_keyed_by_row_identity_not_position(
        self, base_outcome: X.ExcelExtractOutcome, instrumented: EI.InstrumentedWorkbook
    ) -> None:
        """受管字段的键里带的是 row UUID，而不是行号/下标（Requirement 6.5）。"""
        source_uuids = set(instrumented.row_uuids.values())
        assert len(source_uuids) == EXPECTED_ROW_COUNT
        for identity in source_uuids:
            key = f"k11_rows/{identity}/adjustment"
            assert key in base_outcome.projection.values, key
        # 行号绝不出现在键里：任何 `/7/`、`/row7/` 形态都是位置身份泄漏。
        leaked = [k for k in base_outcome.projection.values if re.search(r"/\d+/", k)]
        assert leaked == [], f"projection 键里出现了位置下标: {leaked[:3]}"

    def test_row_keys_are_source_uuids_in_row_order(
        self, base_outcome: X.ExcelExtractOutcome, instrumented: EI.InstrumentedWorkbook
    ) -> None:
        expected = tuple(v for _, v in sorted(instrumented.row_uuids.items()))
        assert base_outcome.projection.row_keys["k11_rows"] == expected

    def test_field_count_equals_declared_shape(
        self, base_outcome: X.ExcelExtractOutcome
    ) -> None:
        """19 行 × 3 个行域字段 + 1 个静态 auto_source = 58（字面量，不由被测函数算）。"""
        assert base_outcome.stats.field_count == EXPECTED_ROW_COUNT * 3 + 1 == 58
        assert base_outcome.stats.table_row_counts == {"k11_rows": EXPECTED_ROW_COUNT}

    def test_static_and_row_scoped_values_read_back(
        self, base_outcome: X.ExcelExtractOutcome
    ) -> None:
        values = base_outcome.projection.values
        assert float(values["k11_footer/tb_amount"].value) == pytest.approx(12345.67)
        assert values[f"k11_rows/GTROW-K11-{FIRST_ROW:04d}/adjustment"].value == 107
        assert values[f"k11_rows/GTROW-K11-{FIRST_ROW:04d}/reason"].value == f"原因{FIRST_ROW}"

    def test_protected_field_value_is_computed_not_formula_text(
        self, base_outcome: X.ExcelExtractOutcome
    ) -> None:
        """公式字段的 projection 值是**缓存值**、公式文本另入 inventory。

        反过来（把公式文本当 `amount` 值）会让每个公式字段都变成
        `type_normalization_failure` schema 冲突，protected 冲突（Property 24）永久不可达。
        """
        key = f"k11_rows/GTROW-K11-{FIRST_ROW:04d}/variance"
        assert base_outcome.projection.values[key].value == 0
        assert base_outcome.formula_inventory[key] == f"=G{FIRST_ROW}-D{FIRST_ROW}"
        assert base_outcome.anomalies == ()

    def test_carrier_tier_is_instrumented_identity(
        self, base_outcome: X.ExcelExtractOutcome
    ) -> None:
        assert base_outcome.stats.carrier_tier is ExtractCarrierTier.instrumented_identity

    def test_metadata_sheet_never_enters_business_enumeration(
        self, base_outcome: X.ExcelExtractOutcome
    ) -> None:
        assert GT_SYNC_SHEET_NAME not in base_outcome.identity_inventory.business_sheets
        assert base_outcome.identity_inventory.excluded_from_business_enumeration is True

    def test_managed_region_resolved_by_table_association_only(
        self, base_outcome: X.ExcelExtractOutcome
    ) -> None:
        assert base_outcome.region.table_ref == EXPECTED_TABLE_REF
        assert base_outcome.region.sheet_name == MANAGED_SHEET
        assert base_outcome.identity_inventory.resolved_sheet_by == X.TABLE_SHEET_ANCHOR


# ═══════════════════════════════════════════════════════════════════════════
# 5. Property 66：identity 载体在 OO 操作矩阵后保留；缺失即阻断 engine gate
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty66IdentityRetention:
    """**Validates: Requirements 6.16**

    Task 5 已经用真实 OO 9.4 证过载体本身；本节测的是 **engine 侧的门**：把
    「OO 操作后的产物」逐种构造出来，断言保留则通过、缺失则阻断。
    """

    def test_sheet_rename_does_not_break_identity(
        self,
        base_bytes: bytes,
        definitions: FrozenEntryDefinitions,
        workdir: Path,
    ) -> None:
        """改 sheet 展示名后仍能反读 —— 证明定位没依赖被证伪的展示名锚点。"""
        renamed = edit_part(
            base_bytes,
            "xl/workbook.xml",
            lambda blob: blob.replace(
                MANAGED_SHEET.encode("utf-8"), "审定表-改名了".encode("utf-8")
            ),
        )
        path = write(workdir, "renamed.xlsx", renamed)
        outcome = extract(path, definitions)
        assert outcome.region.sheet_name == "审定表-改名了"
        assert outcome.stats.field_count == 58

    def test_sheet_id_renumbering_does_not_break_identity(
        self, base_bytes: bytes, definitions: FrozenEntryDefinitions, workdir: Path
    ) -> None:
        """把全部 `sheetId` 重编号（OO 9.4 每次保存的实测行为）后仍能反读。"""

        def renumber(blob: bytes) -> bytes:
            text = blob.decode("utf-8")
            return re.sub(
                r'sheetId="(\d+)"',
                lambda m: f'sheetId="{int(m.group(1)) + 500}"',
                text,
            ).encode("utf-8")

        path = write(workdir, "resheetid.xlsx", edit_part(base_bytes, "xl/workbook.xml", renumber))
        outcome = extract(path, definitions)
        assert outcome.stats.field_count == 58

    def test_renamed_table_blocks_engine(
        self, base_bytes: bytes, definitions: FrozenEntryDefinitions, workdir: Path
    ) -> None:
        """Excel Table 的 displayName 变了 ⇒ 区域边界锚点没了，fail closed，不按中文表头猜。"""
        table_part = next(
            name for name in _read_entries(base_bytes) if name.startswith("xl/tables/")
        )
        renamed = edit_part(
            base_bytes,
            table_part,
            lambda blob: blob.replace(TABLE_NAME.encode(), b"GT_SOMETHING_ELSE"),
        )
        path = write(workdir, "table_renamed.xlsx", renamed)
        with pytest.raises(X.IdentityCarrierMissingError) as exc:
            extract(path, definitions)
        assert TABLE_NAME in str(exc.value)

    def test_dangling_table_part_is_error_not_fail_open(
        self, base_bytes: bytes, definitions: FrozenEntryDefinitions, workdir: Path
    ) -> None:
        """Table 部件被删但 rel 还在 ⇒ 采集异常必须**转译成错误**，不得降级成「无 identity」。

        这是 fail-open 的反向自检：`except Exception` 把采集失败吞成「本项目无此数据」时，
        表现就是「静默取空 + 一切照常」，四层静态检查全绿。
        """
        table_part = next(
            name for name in _read_entries(base_bytes) if name.startswith("xl/tables/")
        )
        path = write(workdir, "dangling_table.xlsx", drop_part(base_bytes, table_part))
        with pytest.raises(X.IdentityCarrierMissingError) as exc:
            extract(path, definitions)
        assert table_part in str(exc.value)

    def test_uuid_column_wiped_blocks_engine(
        self, base_bytes: bytes, sheet_part: str,
        definitions: FrozenEntryDefinitions, workdir: Path
    ) -> None:
        """整列 UUID 被删 ⇒ Requirement 6.15 的「拒绝」形态，且**不是**锚点误用。"""
        wiped = patch_cells(
            base_bytes, sheet_part, {f"{UUID_COL}{r}": None for r in range(FIRST_ROW, LAST_ROW + 1)}
        )
        path = write(workdir, "no_uuid.xlsx", wiped)
        with pytest.raises(X.IdentityCarrierMissingError) as exc:
            extract(path, definitions)
        assert "6.15" in str(exc.value) or "identity" in str(exc.value)

    def test_hidden_metadata_sheet_removed_blocks_engine(
        self, base_bytes: bytes, definitions: FrozenEntryDefinitions, workdir: Path
    ) -> None:
        def unhide(blob: bytes) -> bytes:
            text = blob.decode("utf-8")
            return re.sub(
                r'(<sheet [^>]*name="' + re.escape(GT_SYNC_SHEET_NAME) + r'"[^>]*?) state="[^"]*"',
                r"\1",
                text,
            ).encode("utf-8")

        path = write(workdir, "meta_visible.xlsx", edit_part(base_bytes, "xl/workbook.xml", unhide))
        with pytest.raises(X.IdentityCarrierMissingError) as exc:
            extract(path, definitions)
        assert GT_SYNC_SHEET_NAME in str(exc.value) or "metadata" in str(exc.value)

    def test_defined_names_stripped_blocks_engine(
        self, base_bytes: bytes, definitions: FrozenEntryDefinitions, workdir: Path
    ) -> None:
        def strip_names(blob: bytes) -> bytes:
            text = blob.decode("utf-8")
            return re.sub(r"<definedNames>.*?</definedNames>", "", text, flags=re.S).encode(
                "utf-8"
            )

        path = write(workdir, "no_names.xlsx", edit_part(base_bytes, "xl/workbook.xml", strip_names))
        with pytest.raises(X.IdentityCarrierMissingError) as exc:
            extract(path, definitions)
        assert "defined name" in str(exc.value)

    def test_lost_row_identity_is_retention_failure_not_silent_pass(
        self, base_bytes: bytes, sheet_part: str,
        definitions: FrozenEntryDefinitions, workdir: Path
    ) -> None:
        """只丢**一个** row UUID（其余仍在）⇒ 保留门打红，不得静默少读一行。"""
        wiped = patch_cells(base_bytes, sheet_part, {f"{UUID_COL}{LAST_ROW}": None})
        path = write(workdir, "one_uuid_lost.xlsx", wiped)
        with pytest.raises(X.IdentityRetentionError) as exc:
            extract(path, definitions)
        assert f"GTROW-K11-{LAST_ROW:04d}" in str(exc.value)

    def test_row_insert_is_not_retention_failure(
        self, base_bytes: bytes, sheet_part: str,
        definitions: FrozenEntryDefinitions, workdir: Path
    ) -> None:
        """OO 合法插行（Table ref 行区间变大）不得被判成载体漂移。

        这条是保留门的**反向自检**：判据若写成「行区间/行号必须逐字相等」，合法插删行
        会全部打红，调用方只能整体关掉这道门。
        """
        grown = add_row(
            base_bytes,
            sheet_part,
            row=LAST_ROW + 1,
            cells={
                f"{UUID_COL}{LAST_ROW + 1}": "GTROW-K11-0026",
                f"C{LAST_ROW + 1}": 999,
                f"J{LAST_ROW + 1}": "新增行",
            },
        )
        path = write(workdir, "row_inserted.xlsx", grown)
        outcome = extract(path, definitions)
        assert "GTROW-K11-0026" in outcome.projection.row_keys["k11_rows"]
        assert outcome.stats.table_row_counts["k11_rows"] == EXPECTED_ROW_COUNT + 1

    def test_forbidden_anchor_path_has_its_own_error_type(self, contract: Any) -> None:
        """`resolved_sheet_by` 是被证伪的锚点 ⇒ 专属 :class:`ForbiddenSheetAnchorError`。

        与「载体缺失」严格分开：两条判据共用一个类型时，「整列 UUID 被删」会先撞上锚点
        判据，于是真正的锚点误用分支不可分辨、它的变异恒 GREEN（Task 17 实测过）。
        """
        inventory = X.RuntimeIdentityInventory(
            hidden_sheet_present=True,
            hidden_sheet_is_hidden=True,
            excluded_from_business_enumeration=True,
            defined_names=("GT_MANAGED_REGION_K11",),
            table_present=True,
            table_ref=EXPECTED_TABLE_REF,
            table_sheet=MANAGED_SHEET,
            resolved_sheet_by="sheet_id",
            uuid_column=UUID_COL,
            uuid_column_hidden=True,
            row_uuids={"7": "GTROW-K11-0007"},
            duplicate_row_uuids=(),
            empty_row_uuids=(),
            business_sheets=(MANAGED_SHEET,),
        )
        with pytest.raises(X.ForbiddenSheetAnchorError) as exc:
            X.assert_identity_carriers_usable(
                inventory, contract=contract, entry_id=ENTRY_ID
            )
        assert X.TABLE_SHEET_ANCHOR in str(exc.value)
        assert "sheet_id" in str(exc.value)

    def test_disproved_anchors_are_never_allowlisted(self) -> None:
        assert "sheet_id" in X.DISPROVED_SHEET_ANCHORS
        assert "sheet_display_name" in X.DISPROVED_SHEET_ANCHORS
        assert X.TABLE_SHEET_ANCHOR not in X.DISPROVED_SHEET_ANCHORS

    def test_retention_field_coverage_is_exhaustive(self) -> None:
        """`EntryIdentityInventory` 的每个字段都必须显式裁决参不参与保留判据。

        加字段而不裁决 ⇒ 这里打红。这是「逐条清单漏项」唯一可靠的兜底（总 digest 在子集
        语义下做不到，硬写出来就是与逐条判据同义反复的自证式判据）。
        """
        import dataclasses

        from app.services.workpaper_sync.excel_entry_gate import EntryIdentityInventory

        declared = set(X.RETENTION_CHECKED_FIELDS) | set(X.RETENTION_EXEMPT_FIELDS)
        actual = {f.name for f in dataclasses.fields(EntryIdentityInventory)}
        assert declared == actual, (
            f"未裁决字段 {sorted(actual - declared)}；多余声明 {sorted(declared - actual)}"
        )
        assert not (set(X.RETENTION_CHECKED_FIELDS) & set(X.RETENTION_EXEMPT_FIELDS))
        assert all(len(reason) > 10 for reason in X.RETENTION_EXEMPT_FIELDS.values())


# ═══════════════════════════════════════════════════════════════════════════
# 6. Property 23：动态行身份不使用下标
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty23RowIdentityIsNotPositional:
    """**Validates: Requirements 6.5**

    Property 23 原文：删除/重排/再新增后旧 `row_uuid` 不复用，原行数据不串到新行。
    因此三件事各有独立判据：**不复用**、**不串行**、**重排不改身份**。
    """

    def test_reorder_keeps_values_attached_to_identity(
        self, base_bytes: bytes, sheet_part: str,
        definitions: FrozenEntryDefinitions, workdir: Path
    ) -> None:
        """把第 7 行与第 25 行互换位置，各自的值必须仍跟着自己的 UUID。"""
        first = f"GTROW-K11-{FIRST_ROW:04d}"
        last = f"GTROW-K11-{LAST_ROW:04d}"
        swapped = patch_cells(
            base_bytes,
            sheet_part,
            {
                f"{UUID_COL}{FIRST_ROW}": last,
                f"{UUID_COL}{LAST_ROW}": first,
                f"C{FIRST_ROW}": 100 + LAST_ROW,
                f"C{LAST_ROW}": 100 + FIRST_ROW,
                f"J{FIRST_ROW}": f"原因{LAST_ROW}",
                f"J{LAST_ROW}": f"原因{FIRST_ROW}",
            },
        )
        path = write(workdir, "reordered.xlsx", swapped)
        outcome = extract(path, definitions)
        values = outcome.projection.values
        # 期望值是**源侧**写进去的字面量，不是调用被测函数算出来的。
        assert values[f"k11_rows/{first}/adjustment"].value == 100 + FIRST_ROW
        assert values[f"k11_rows/{last}/adjustment"].value == 100 + LAST_ROW
        assert values[f"k11_rows/{first}/reason"].value == f"原因{FIRST_ROW}"
        assert values[f"k11_rows/{last}/reason"].value == f"原因{LAST_ROW}"
        assert outcome.anomalies == ()

    def test_new_row_gets_minted_identity_never_reusing_deleted_one(
        self, base_bytes: bytes, sheet_part: str, contract: Any,
        base_inventory: dict[str, Any], workdir: Path
    ) -> None:
        """删掉一行、再在同位置新增空 UUID 行 ⇒ 分配**新** ID，绝不复用已删的那个。"""
        deleted = f"GTROW-K11-{FIRST_ROW + 1:04d}"
        new_row = LAST_ROW + 1
        reused_slot = patch_cells(
            base_bytes,
            sheet_part,
            {f"{UUID_COL}{FIRST_ROW + 1}": None, f"C{FIRST_ROW + 1}": None},
        )
        reused_slot = add_row(
            reused_slot,
            sheet_part,
            row=new_row,
            cells={f"{UUID_COL}{new_row}": "", f"C{new_row}": 777},
        )
        path = write(workdir, "minted.xlsx", reused_slot)
        # frozen 预期里去掉那一行，否则会先被保留门拦住（那是另一条判据）。
        frozen = dict(base_inventory)
        column = dict(frozen["hidden_uuid_column"])
        column["row_uuids"] = {
            k: v for k, v in column["row_uuids"].items() if v != deleted
        }
        frozen["hidden_uuid_column"] = column
        definitions = make_definitions(contract, frozen)
        outcome = extract(
            path,
            definitions,
            binding=X.ExcelIdentityBinding(
                table_name=TABLE_NAME,
                uuid_column=UUID_COL,
                table_key="k11_rows",
                tombstoned_row_keys=(deleted,),
            ),
        )
        minted = outcome.scan.minted_by_row
        assert set(minted) == {FIRST_ROW + 1, new_row}, minted
        new_id = minted[new_row]
        assert new_id.startswith(X.MINTED_ROW_IDENTITY_PREFIX)
        assert new_id != deleted
        assert deleted not in outcome.projection.row_keys["k11_rows"]
        # 新行的数据挂在新 ID 上，没有串到任何旧 ID。
        assert outcome.projection.values[f"k11_rows/{new_id}/adjustment"].value == 777
        assert outcome.anomalies == ()

    def test_minted_identity_is_deterministic_across_retries(self) -> None:
        """同一 artifact 同一行必须恒得同一 ID —— 否则同一 operation retry 结果不同。"""
        args = dict(table_key="k11_rows", artifact_sha256=_d("artifact"), excel_row=9)
        first = X.mint_row_identity(taken=(), **args)  # type: ignore[arg-type]
        second = X.mint_row_identity(taken=(), **args)  # type: ignore[arg-type]
        assert first == second
        # 撞上 taken（含 tombstone）时换盐继续，且仍然确定。
        avoided = X.mint_row_identity(taken=(first,), **args)  # type: ignore[arg-type]
        assert avoided != first
        assert avoided == X.mint_row_identity(taken=(first,), **args)  # type: ignore[arg-type]

    def test_minted_identity_never_collides_with_tombstones(self) -> None:
        """把前 32 个候选全部塞进 tombstone，仍必须能收敛到一个未占用 ID。"""
        args = dict(table_key="t", artifact_sha256=_d("a"), excel_row=11)
        taken: list[str] = []
        for _ in range(32):
            taken.append(X.mint_row_identity(taken=tuple(taken), **args))  # type: ignore[arg-type]
        assert len(set(taken)) == 32
        final = X.mint_row_identity(taken=tuple(taken), **args)  # type: ignore[arg-type]
        assert final not in taken

    def test_empty_identity_classification_is_contract_driven(self) -> None:
        """三种处置各由**真实契约变体**触发，互不重叠（Requirement 6.15）。"""
        tombstone = parse_contract(
            contract_payload(delete_policy="tombstone"), adapter_id=CONTRACT_ID
        )
        reject = parse_contract(
            contract_payload(delete_policy="reject"), adapter_id=CONTRACT_ID
        )
        rows_t = next(
            t for s in tombstone.sheets for t in s.tables if t.table_key == "k11_rows"
        )
        rows_r = next(
            t for s in reject.sheets for t in s.tables if t.table_key == "k11_rows"
        )
        footer = next(
            t for s in tombstone.sheets for t in s.tables if t.table_key == "k11_footer"
        )
        assert (
            X.classify_empty_row_identity(rows_t)
            is X.EmptyRowIdentityDisposition.assign_new_id
        )
        assert (
            X.classify_empty_row_identity(rows_r)
            is X.EmptyRowIdentityDisposition.structural_conflict
        )
        assert X.classify_empty_row_identity(footer) is X.EmptyRowIdentityDisposition.reject
        # 🔴 「有 row_identity 但没有 delete_policy」在合法契约上不存在（CS-14 拦住），
        #    因此这条只能由手工构造的 `TableSpec` 触发。它必须**抛**而不是回落到 reject ——
        #    回落会让它与上一条在合法契约上完全等价，`has_dynamic_rows` 判据删掉行为不变
        #    ⇒ 变异恒 GREEN（实测过）。
        from dataclasses import replace as dc_replace

        bypassed = dc_replace(rows_t, delete_policy=None)
        with pytest.raises(X.ExcelExtractError) as exc:
            X.classify_empty_row_identity(bypassed)
        assert "CS-14" in str(exc.value)
        # 三个取值互不相同 —— 共用一个取值会让其中两条永久不可达。
        assert (
            len(
                {
                    X.classify_empty_row_identity(rows_t),
                    X.classify_empty_row_identity(rows_r),
                    X.classify_empty_row_identity(footer),
                }
            )
            == 3
        )


# ═══════════════════════════════════════════════════════════════════════════
# 7. 五类身份/结构异常：各自可达、各有专属 kind
# ═══════════════════════════════════════════════════════════════════════════


def _anomaly_kinds(outcome: X.ExcelExtractOutcome) -> set[SchemaAnomalyKind]:
    return {a.kind for a in outcome.anomalies}


class TestAnomalyClassesAreDistinctAndReachable:
    """**Validates: Requirements 6.15 / 6.20**

    🔴 本 spec 已三次踩到「共享错误码让较早分支永久不可达」。因此这里不是「各测一遍」，
    而是把每一类的 `SchemaAnomalyKind` 收集起来断言**互不相同**，并逐类给出独立反例。
    """

    @pytest.fixture(scope="class")
    def reject_definitions(
        self, base_inventory: dict[str, Any]
    ) -> FrozenEntryDefinitions:
        reject = parse_contract(
            contract_payload(delete_policy="reject"), adapter_id=CONTRACT_ID
        )
        return make_definitions(reject, base_inventory)

    def test_empty_identity_on_reject_table_becomes_schema_anomaly(
        self, base_bytes: bytes, sheet_part: str,
        reject_definitions: FrozenEntryDefinitions, workdir: Path
    ) -> None:
        new_row = LAST_ROW + 1
        blanked = add_row(
            base_bytes,
            sheet_part,
            row=new_row,
            cells={f"{UUID_COL}{new_row}": "", f"C{new_row}": 777, f"J{new_row}": "新行"},
        )
        path = write(workdir, "empty_identity_reject.xlsx", blanked)
        outcome = extract(path, reject_definitions)
        assert SchemaAnomalyKind.empty_row_identity in _anomaly_kinds(outcome)
        anomaly = next(
            a for a in outcome.anomalies if a.kind is SchemaAnomalyKind.empty_row_identity
        )
        assert anomaly.blocks_row_key == f"row{new_row}"
        assert f"{UUID_COL}{new_row}" in (anomaly.oo_location or "")

    def test_duplicate_identity_with_same_values_is_identity_anomaly_only(
        self, base_bytes: bytes, sheet_part: str,
        definitions: FrozenEntryDefinitions, workdir: Path
    ) -> None:
        """复制行、值一致 ⇒ 只有 `duplicate_row_identity`，**没有**多位置异值。"""
        victim = f"GTROW-K11-{FIRST_ROW:04d}"
        new_row = LAST_ROW + 1
        copied = add_row(
            base_bytes,
            sheet_part,
            row=new_row,
            cells={
                f"{UUID_COL}{new_row}": victim,
                f"C{new_row}": 100 + FIRST_ROW,
                f"J{new_row}": f"原因{FIRST_ROW}",
                f"H{new_row}": 0,
            },
        )
        path = write(workdir, "dup_same.xlsx", copied)
        outcome = extract(path, definitions)
        kinds = _anomaly_kinds(outcome)
        assert SchemaAnomalyKind.duplicate_row_identity in kinds
        assert SchemaAnomalyKind.multi_location_divergence not in kinds

    def test_duplicate_identity_with_divergent_values_adds_multi_location(
        self, base_bytes: bytes, sheet_part: str,
        definitions: FrozenEntryDefinitions, workdir: Path
    ) -> None:
        """复制行、值不同 ⇒ 两条都在，且多位置异值列出全部 OO 地址。"""
        victim = f"GTROW-K11-{FIRST_ROW:04d}"
        new_row = LAST_ROW + 1
        copied = add_row(
            base_bytes,
            sheet_part,
            row=new_row,
            cells={f"{UUID_COL}{new_row}": victim, f"C{new_row}": 999999},
        )
        path = write(workdir, "dup_divergent.xlsx", copied)
        outcome = extract(path, definitions)
        kinds = _anomaly_kinds(outcome)
        assert SchemaAnomalyKind.duplicate_row_identity in kinds
        assert SchemaAnomalyKind.multi_location_divergence in kinds
        divergence = next(
            a
            for a in outcome.anomalies
            if a.kind is SchemaAnomalyKind.multi_location_divergence
        )
        assert f"C{FIRST_ROW}" in (divergence.oo_location or "")
        assert f"C{new_row}" in (divergence.oo_location or "")

    def test_tombstoned_identity_reuse_has_its_own_kind(
        self, base_path: Path, definitions: FrozenEntryDefinitions
    ) -> None:
        victim = f"GTROW-K11-{FIRST_ROW + 2:04d}"
        outcome = extract(
            base_path,
            definitions,
            binding=X.ExcelIdentityBinding(
                table_name=TABLE_NAME,
                uuid_column=UUID_COL,
                table_key="k11_rows",
                tombstoned_row_keys=(victim,),
            ),
        )
        kinds = _anomaly_kinds(outcome)
        assert kinds == {SchemaAnomalyKind.reused_tombstoned_row_identity}
        anomaly = outcome.anomalies[0]
        assert anomaly.row_key == victim

    def test_type_normalization_failure_keeps_raw_value(
        self, base_bytes: bytes, sheet_part: str,
        definitions: FrozenEntryDefinitions, workdir: Path
    ) -> None:
        """往 `amount` 列写文本 ⇒ 记 `type_normalization_failure` 并**保留原值**供裁决。"""
        broken = patch_cells(base_bytes, sheet_part, {f"C{FIRST_ROW}": "不是数字"})
        path = write(workdir, "bad_type.xlsx", broken)
        outcome = extract(path, definitions)
        assert SchemaAnomalyKind.type_normalization_failure in _anomaly_kinds(outcome)
        key = f"k11_rows/GTROW-K11-{FIRST_ROW:04d}/adjustment"
        assert outcome.projection.values[key].value == "不是数字"

    def test_all_five_anomaly_kinds_are_pairwise_distinct(
        self,
        base_bytes: bytes,
        sheet_part: str,
        definitions: FrozenEntryDefinitions,
        reject_definitions: FrozenEntryDefinitions,
        workdir: Path,
    ) -> None:
        """五类反例各自跑一遍，收集到的 kind 必须是 5 个互不相同的值。

        共用一个 kind ⇒ 集合尺寸缩水 ⇒ 这里打红。这一条比「五个测试各断言一次」强：
        后者在两类合并成同一个 kind 时**全部仍然通过**。
        """
        collected: set[SchemaAnomalyKind] = set()

        new_row = LAST_ROW + 1
        blanked = write(
            workdir,
            "distinct_empty.xlsx",
            add_row(
                base_bytes, sheet_part, row=new_row, cells={f"{UUID_COL}{new_row}": ""}
            ),
        )
        collected |= _anomaly_kinds(extract(blanked, reject_definitions))

        victim = f"GTROW-K11-{FIRST_ROW:04d}"
        dup = write(
            workdir,
            "distinct_dup.xlsx",
            add_row(
                base_bytes,
                sheet_part,
                row=new_row,
                cells={f"{UUID_COL}{new_row}": victim, f"C{new_row}": 424242},
            ),
        )
        collected |= _anomaly_kinds(extract(dup, definitions))

        collected |= _anomaly_kinds(
            extract(
                write(workdir, "distinct_tomb.xlsx", base_bytes),
                definitions,
                binding=X.ExcelIdentityBinding(
                    table_name=TABLE_NAME,
                    uuid_column=UUID_COL,
                    table_key="k11_rows",
                    tombstoned_row_keys=(f"GTROW-K11-{FIRST_ROW + 3:04d}",),
                ),
            )
        )

        bad_type = write(
            workdir,
            "distinct_type.xlsx",
            patch_cells(base_bytes, sheet_part, {f"C{FIRST_ROW}": "文本"}),
        )
        collected |= _anomaly_kinds(extract(bad_type, definitions))

        assert collected == {
            SchemaAnomalyKind.empty_row_identity,
            SchemaAnomalyKind.duplicate_row_identity,
            SchemaAnomalyKind.multi_location_divergence,
            SchemaAnomalyKind.reused_tombstoned_row_identity,
            SchemaAnomalyKind.type_normalization_failure,
        }, sorted(k.value for k in collected)

    def test_identity_carrier_missing_is_exception_not_anomaly(
        self, base_bytes: bytes, sheet_part: str,
        definitions: FrozenEntryDefinitions, workdir: Path
    ) -> None:
        """第 6 类（载体整体缺失）走**异常**而不是 anomaly —— Requirement 6.20 要求 fail closed。

        与前五类分开的理由：前五类是「个别行/格坏了，其余照常合并」，本类是「整块读不出来」，
        继续合并等于按空集覆盖整表。
        """
        wiped = patch_cells(
            base_bytes,
            sheet_part,
            {f"{UUID_COL}{r}": None for r in range(FIRST_ROW, LAST_ROW + 1)},
        )
        path = write(workdir, "carrier_missing.xlsx", wiped)
        with pytest.raises(X.IdentityCarrierMissingError):
            extract(path, definitions)


# ═══════════════════════════════════════════════════════════════════════════
# 8. Property 24：保护字段被改必生成 protected 冲突，current 公式与值不变
# ═══════════════════════════════════════════════════════════════════════════

VARIANCE_KEY = f"k11_rows/GTROW-K11-{FIRST_ROW:04d}/variance"
TB_KEY = "k11_footer/tb_amount"


def merge_with(
    base_outcome: X.ExcelExtractOutcome,
    incoming: X.ExcelExtractOutcome,
    contract: Any,
) -> Any:
    """把 extract 结果喂进 Task 14 的真 merge（不 mock，不另立并行通路）。"""
    return merge_projections(
        base=base_outcome.projection,
        current=base_outcome.projection,
        incoming=incoming.projection,
        contract=contract,
        structural_anomalies=incoming.anomalies,
    )


class TestProperty24ProtectedFieldConflicts:
    """**Validates: Requirements 6.6**

    Property 24 原文：OO 修改 formula/auto-source 单元格时 **current 公式和值不变**，
    **并生成 protected conflict**。两句都要有判据。
    """

    @pytest.mark.parametrize(
        "coord,new_value,expected_kind,changed_key",
        [
            (
                f"H{FIRST_ROW}",
                555,
                X.FormulaTamperKind.formula_replaced_by_literal,
                VARIANCE_KEY,
            ),
            (
                f"H{FIRST_ROW}",
                f"=G{FIRST_ROW}-D{FIRST_ROW}+1",
                X.FormulaTamperKind.formula_text_changed,
                VARIANCE_KEY,
            ),
            (
                f"B{FOOTER_ROW}",
                "=D26",
                X.FormulaTamperKind.formula_added_to_literal_cell,
                TB_KEY,
            ),
            (
                f"B{FOOTER_ROW}",
                999.99,
                X.FormulaTamperKind.literal_value_changed,
                TB_KEY,
            ),
        ],
    )
    def test_four_tamper_kinds_are_each_reachable_and_distinct(
        self,
        base_bytes: bytes,
        sheet_part: str,
        base_outcome: X.ExcelExtractOutcome,
        definitions: FrozenEntryDefinitions,
        workdir: Path,
        coord: str,
        new_value: Any,
        expected_kind: X.FormulaTamperKind,
        changed_key: str,
    ) -> None:
        tampered = patch_cells(base_bytes, sheet_part, {coord: new_value})
        path = write(workdir, f"tamper_{expected_kind.value}.xlsx", tampered)
        outcome = extract(
            path,
            definitions,
            baseline=base_outcome.projection,
            baseline_formulas=base_outcome.formula_inventory,
        )
        kinds = {f.kind for f in outcome.protected_findings}
        assert expected_kind in kinds, sorted(k.value for k in kinds)
        finding = next(f for f in outcome.protected_findings if f.kind is expected_kind)
        assert finding.stable_field_key == changed_key
        assert coord in finding.oo_location

    def test_all_four_tamper_kinds_map_to_distinct_values(self) -> None:
        """四类 tamper 必须是四个互不相同的取值 —— 合并任意两类会让其中一类不可分辨。"""
        assert len({k.value for k in X.FormulaTamperKind}) == 4

    def test_value_level_tamper_yields_protected_conflict_and_keeps_current(
        self,
        base_bytes: bytes,
        sheet_part: str,
        base_outcome: X.ExcelExtractOutcome,
        definitions: FrozenEntryDefinitions,
        contract: Any,
        workdir: Path,
    ) -> None:
        """公式格被敲成字面量 ⇒ Task 14 的 merge 直接给出 protected 冲突，且 merged 取 current。"""
        tampered = patch_cells(base_bytes, sheet_part, {f"H{FIRST_ROW}": 555})
        path = write(workdir, "protected_value.xlsx", tampered)
        incoming = extract(
            path,
            definitions,
            baseline=base_outcome.projection,
            baseline_formulas=base_outcome.formula_inventory,
        )
        outcome = merge_with(base_outcome, incoming, contract)
        protected = [
            r for r in outcome.conflicts.records if r.kind is ConflictKind.protected
        ]
        assert [r.locator.stable_field_key for r in protected] == [VARIANCE_KEY]
        # current 的值不变（merged 取 current 的 0，而不是 incoming 的 555）。
        assert outcome.merged.values[VARIANCE_KEY].value == 0
        assert base_outcome.formula_inventory[VARIANCE_KEY] == f"=G{FIRST_ROW}-D{FIRST_ROW}"

    def test_formula_text_only_tamper_is_invisible_to_value_merge_and_must_be_补齐(
        self,
        base_bytes: bytes,
        sheet_part: str,
        base_outcome: X.ExcelExtractOutcome,
        definitions: FrozenEntryDefinitions,
        contract: Any,
        workdir: Path,
    ) -> None:
        """公式文本被改但缓存值相同 ⇒ merge 看不到差异，必须由公式层补齐 protected 冲突。

        这条是 Property 24 最容易漏的形态：只靠值比较时它**恒不产生冲突**，而
        `verify_formula_regions` 只在 rematerialize 反读时跑，OO→HTML 这一侧不经过它。
        """
        tampered = patch_cells(
            base_bytes, sheet_part, {f"H{FIRST_ROW}": f"=G{FIRST_ROW}-D{FIRST_ROW}+1"}
        )
        path = write(workdir, "protected_formula_only.xlsx", tampered)
        incoming = extract(
            path,
            definitions,
            baseline=base_outcome.projection,
            baseline_formulas=base_outcome.formula_inventory,
        )
        # 值层：incoming 与 base 的 variance 完全相同 ⇒ merge 零冲突（这是被证明的前提）。
        assert incoming.projection.values[VARIANCE_KEY].value == 0
        merged = merge_with(base_outcome, incoming, contract)
        assert [
            r for r in merged.conflicts.records if r.kind is ConflictKind.protected
        ] == []
        # 未补齐时闭合判据必须打红。
        with pytest.raises(X.FormulaRegionDriftError) as exc:
            X.assert_protected_tamper_fully_reported(
                findings=incoming.protected_findings,
                conflicts=merged.conflicts.records,
            )
        assert VARIANCE_KEY in str(exc.value)
        # 补齐之后闭合判据通过，且冲突正是 protected。
        补齐 = X.protected_conflicts_for_findings(
            findings=incoming.protected_findings,
            contract=contract,
            base=base_outcome.projection,
            current=base_outcome.projection,
            incoming=incoming.projection,
            existing=merged.conflicts.records,
        )
        assert [r.kind for r in 补齐] == [ConflictKind.protected]
        X.assert_protected_tamper_fully_reported(
            findings=incoming.protected_findings,
            conflicts=(*merged.conflicts.records, *补齐),
        )

    def test_no_double_reporting_when_value_layer_already_conflicted(
        self,
        base_bytes: bytes,
        sheet_part: str,
        base_outcome: X.ExcelExtractOutcome,
        definitions: FrozenEntryDefinitions,
        contract: Any,
        workdir: Path,
    ) -> None:
        """值层已经给出 protected 冲突时不得重复补齐（否则撞破 ConflictSet 的唯一键）。"""
        tampered = patch_cells(base_bytes, sheet_part, {f"H{FIRST_ROW}": 555})
        path = write(workdir, "protected_no_double.xlsx", tampered)
        incoming = extract(
            path,
            definitions,
            baseline=base_outcome.projection,
            baseline_formulas=base_outcome.formula_inventory,
        )
        merged = merge_with(base_outcome, incoming, contract)
        extra = X.protected_conflicts_for_findings(
            findings=incoming.protected_findings,
            contract=contract,
            base=base_outcome.projection,
            current=base_outcome.projection,
            incoming=incoming.projection,
            existing=merged.conflicts.records,
        )
        assert extra == ()

    def test_untampered_protected_field_yields_no_finding(
        self, base_path: Path, base_outcome: X.ExcelExtractOutcome,
        definitions: FrozenEntryDefinitions
    ) -> None:
        """反向自检：同一份字节再读一遍，受保护格不得凭空报出篡改。"""
        again = extract(
            base_path,
            definitions,
            baseline=base_outcome.projection,
            baseline_formulas=base_outcome.formula_inventory,
        )
        assert again.protected_findings == ()

    def test_no_baseline_means_no_guessing(
        self, base_bytes: bytes, sheet_part: str,
        definitions: FrozenEntryDefinitions, workdir: Path
    ) -> None:
        """没有 baseline 时不猜「原本是什么」—— 只读当前值，不报 tamper。"""
        tampered = patch_cells(base_bytes, sheet_part, {f"H{FIRST_ROW}": 555})
        path = write(workdir, "no_baseline.xlsx", tampered)
        outcome = extract(path, definitions)
        assert outcome.protected_findings == ()
        assert outcome.projection.values[VARIANCE_KEY].value == 555


# ═══════════════════════════════════════════════════════════════════════════
# 9. Property 27：delete/update 冲突只锁该行，其余照常合并
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty27DeleteUpdateDoesNotOverwriteWholeTable:
    """**Validates: Requirements 6.9**

    真跑 extract → merge，不构造合成 projection：Property 27 的价值恰恰在于「位置变化不得
    被误判成整表覆盖」，而位置变化只有在真实 workbook 上才会发生。
    """

    def test_row_deleted_in_oo_while_current_edits_it(
        self,
        base_bytes: bytes,
        sheet_part: str,
        base_outcome: X.ExcelExtractOutcome,
        contract: Any,
        base_inventory: dict[str, Any],
        workdir: Path,
    ) -> None:
        victim_row = FIRST_ROW + 4
        victim = f"GTROW-K11-{victim_row:04d}"
        # OO 侧删掉这一行（identity 与业务值一起清掉）。
        deleted = patch_cells(
            base_bytes,
            sheet_part,
            {
                f"{UUID_COL}{victim_row}": None,
                f"C{victim_row}": None,
                f"J{victim_row}": None,
                f"H{victim_row}": None,
            },
        )
        path = write(workdir, "row_deleted.xlsx", deleted)
        # frozen 预期同步去掉它（否则先撞保留门 —— 那是另一条判据）。
        frozen = dict(base_inventory)
        column = dict(frozen["hidden_uuid_column"])
        column["row_uuids"] = {k: v for k, v in column["row_uuids"].items() if v != victim}
        frozen["hidden_uuid_column"] = column
        definitions = make_definitions(contract, frozen)
        incoming = extract(path, definitions)
        assert victim not in incoming.projection.row_keys["k11_rows"]

        # current 侧改了同一行的 adjustment。
        current_values = dict(base_outcome.projection.values)
        edited_key = f"k11_rows/{victim}/adjustment"
        current_values[edited_key] = FieldValue(
            stable_key=edited_key,
            value=88888,
            value_type=ValueType.amount,
            mode=FieldMode.editable,
            row_key=victim,
        )
        current = Projection(
            contract_id=contract.contract_id,
            semantic_version=contract.semantic_version,
            document_type=contract.document_type,
            values=current_values,
            row_keys=base_outcome.projection.row_keys,
        )
        outcome = merge_projections(
            base=base_outcome.projection,
            current=current,
            incoming=incoming.projection,
            contract=contract,
            structural_anomalies=incoming.anomalies,
        )
        # 只有这一行冲突。
        conflicted_rows = {r.locator.row_key for r in outcome.conflicts.records}
        assert conflicted_rows == {victim}, conflicted_rows
        assert all(
            r.kind is ConflictKind.delete_update for r in outcome.conflicts.records
        )
        # 其他行照常合并 —— 逐条断言未受影响。
        for row in range(FIRST_ROW, LAST_ROW + 1):
            if row == victim_row:
                continue
            identity = f"GTROW-K11-{row:04d}"
            key = f"k11_rows/{identity}/adjustment"
            assert outcome.merged.values[key].value == 100 + row, key

    def test_footer_shift_is_not_whole_table_overwrite(
        self,
        base_bytes: bytes,
        sheet_part: str,
        base_outcome: X.ExcelExtractOutcome,
        definitions: FrozenEntryDefinitions,
        contract: Any,
        workdir: Path,
    ) -> None:
        """新增一行把 footer 往下推 ⇒ 只多出一行，其余行的值逐条不变（AC 6.9）。"""
        new_row = LAST_ROW + 1
        grown = add_row(
            base_bytes,
            sheet_part,
            row=new_row,
            cells={
                f"{UUID_COL}{new_row}": "GTROW-K11-9001",
                f"C{new_row}": 4242,
                f"J{new_row}": "追加",
            },
        )
        path = write(workdir, "footer_shift.xlsx", grown)
        incoming = extract(path, definitions)
        outcome = merge_projections(
            base=base_outcome.projection,
            current=base_outcome.projection,
            incoming=incoming.projection,
            contract=contract,
            structural_anomalies=incoming.anomalies,
        )
        assert outcome.conflicts.records == ()
        assert outcome.merged.values["k11_rows/GTROW-K11-9001/adjustment"].value == 4242
        for row in range(FIRST_ROW, LAST_ROW + 1):
            identity = f"GTROW-K11-{row:04d}"
            assert (
                outcome.merged.values[f"k11_rows/{identity}/adjustment"].value == 100 + row
            )


# ═══════════════════════════════════════════════════════════════════════════
# 10. Property 29：materialize / extract roundtrip 类型化等值
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty29RoundtripEquivalence:
    """**Validates: Requirements 6.11**

    🔴 本节的「写」用**测试自己的 zip 写字节**，不 import 任何 materializer ——
    Task 37 先于 Task 38，extractor 侧不得依赖写入侧（否则「materialize 写错了」会被
    「extract 读错了」互相抵消）。`test_module_has_no_materializer_dependency` 用真实
    import 图实测这一点。
    """

    def test_roundtrip_of_written_values_is_equivalent(
        self,
        base_bytes: bytes,
        sheet_part: str,
        definitions: FrozenEntryDefinitions,
        contract: Any,
        workdir: Path,
    ) -> None:
        """把一份 projection 写进真字节再反读，全部受管 editable 字段类型化相等。"""
        target: dict[str, Any] = {}
        cells: dict[str, Any] = {}
        for row in range(FIRST_ROW, LAST_ROW + 1):
            identity = f"GTROW-K11-{row:04d}"
            amount = row * 3.5
            text = f"裁决说明-{row}"
            cells[f"C{row}"] = amount
            cells[f"J{row}"] = text
            target[f"k11_rows/{identity}/adjustment"] = (amount, ValueType.amount)
            target[f"k11_rows/{identity}/reason"] = (text, ValueType.text)
        cells[f"B{FOOTER_ROW}"] = 4242.42
        path = write(
            workdir, "roundtrip.xlsx", patch_cells(base_bytes, sheet_part, cells)
        )
        extracted = extract(path, definitions)
        expected = Projection(
            contract_id=contract.contract_id,
            semantic_version=contract.semantic_version,
            document_type=contract.document_type,
            values={
                key: FieldValue(
                    stable_key=key,
                    value=value,
                    value_type=value_type,
                    mode=FieldMode.editable,
                    row_key=key.split("/")[1],
                )
                for key, (value, value_type) in target.items()
            },
            row_keys=extracted.projection.row_keys,
        )
        report = X.assert_roundtrip_equivalent(
            expected=expected, extracted=extracted.projection, contract=contract
        )
        assert report.equivalent is True
        assert len(report.compared_keys) == EXPECTED_ROW_COUNT * 2
        assert report.first_difference is None

    def test_roundtrip_compares_only_editable_fields(
        self, base_outcome: X.ExcelExtractOutcome, contract: Any
    ) -> None:
        """公式/auto-source 不进等值比较 —— 它们由服务端写、由 OO 重算。

        混进来会让 verifier 在真实数据上恒不通过 ⇒ 调用方只能整体关掉它。
        """
        report = X.verify_roundtrip_equivalence(
            expected=base_outcome.projection,
            extracted=base_outcome.projection,
            contract=contract,
        )
        assert VARIANCE_KEY not in report.compared_keys
        assert TB_KEY not in report.compared_keys
        assert report.compared_keys, "editable 字段一个都没比 ⇒ 判据空转"

    def test_single_cell_drift_is_located(
        self,
        base_bytes: bytes,
        sheet_part: str,
        base_outcome: X.ExcelExtractOutcome,
        definitions: FrozenEntryDefinitions,
        contract: Any,
        workdir: Path,
    ) -> None:
        """只改一个受管 editable 格 ⇒ 反读不等值，且报出**那一个**键。"""
        path = write(
            workdir,
            "roundtrip_drift.xlsx",
            patch_cells(base_bytes, sheet_part, {f"C{FIRST_ROW + 3}": -1}),
        )
        drifted = extract(path, definitions)
        report = X.verify_roundtrip_equivalence(
            expected=base_outcome.projection,
            extracted=drifted.projection,
            contract=contract,
        )
        assert report.equivalent is False
        assert f"GTROW-K11-{FIRST_ROW + 3:04d}/adjustment" in (report.first_difference or "")
        with pytest.raises(X.RoundtripEquivalenceError) as exc:
            X.assert_roundtrip_equivalent(
                expected=base_outcome.projection,
                extracted=drifted.projection,
                contract=contract,
            )
        assert "8.11" in str(exc.value)

    def test_missing_and_unexpected_keys_have_distinct_first_difference(
        self, base_outcome: X.ExcelExtractOutcome, contract: Any
    ) -> None:
        """「写下去读不回来」与「反读出多余键」是两条独立诊断，不能都报成「值不等」。"""
        values = dict(base_outcome.projection.values)
        dropped_key = f"k11_rows/GTROW-K11-{FIRST_ROW:04d}/adjustment"
        shrunk = dict(values)
        shrunk.pop(dropped_key)
        smaller = Projection(
            contract_id=contract.contract_id,
            semantic_version=contract.semantic_version,
            document_type=contract.document_type,
            values=shrunk,
            row_keys=base_outcome.projection.row_keys,
        )
        missing = X.verify_roundtrip_equivalence(
            expected=base_outcome.projection, extracted=smaller, contract=contract
        )
        assert missing.missing_keys == (dropped_key,)
        assert "缺失" in (missing.first_difference or "")

        extra = X.verify_roundtrip_equivalence(
            expected=smaller, extracted=base_outcome.projection, contract=contract
        )
        assert extra.unexpected_keys == (dropped_key,)
        assert "多出" in (extra.first_difference or "")
        assert missing.first_difference != extra.first_difference

    def test_typed_equality_uses_the_same_normalizer_as_merge(
        self, base_outcome: X.ExcelExtractOutcome, contract: Any
    ) -> None:
        """`107` 与 `Decimal('107.00')` 在 `amount` 下等值 —— verifier 与 merge 同口径。

        两侧各用一套规范化时会出现「merge 认为等值、verifier 认为不等值」的无法解释的
        发布失败。
        """
        from decimal import Decimal

        key = f"k11_rows/GTROW-K11-{FIRST_ROW:04d}/adjustment"
        values = dict(base_outcome.projection.values)
        values[key] = FieldValue(
            stable_key=key,
            value=Decimal("107.00"),
            value_type=ValueType.amount,
            mode=FieldMode.editable,
            row_key=f"GTROW-K11-{FIRST_ROW:04d}",
        )
        restated = Projection(
            contract_id=contract.contract_id,
            semantic_version=contract.semantic_version,
            document_type=contract.document_type,
            values=values,
            row_keys=base_outcome.projection.row_keys,
        )
        assert base_outcome.projection.values[key].value == 107
        report = X.verify_roundtrip_equivalence(
            expected=restated, extracted=base_outcome.projection, contract=contract
        )
        assert report.equivalent is True

    def test_report_cannot_claim_inequivalence_without_location(self) -> None:
        """`equivalent=False` 必须带 `first_difference` —— 只报「不等值」无法定位。"""
        with pytest.raises(X.RoundtripEquivalenceError):
            X.RoundtripReport(equivalent=False, compared_keys=("a",))
        with pytest.raises(X.RoundtripEquivalenceError):
            X.RoundtripReport(
                equivalent=True, compared_keys=("a",), first_difference="不该有"
            )


# ═══════════════════════════════════════════════════════════════════════════
# 11. Property 60：预算 N-1 / N / N+1，且真的挂在 extract 上
# ═══════════════════════════════════════════════════════════════════════════


def scaled_limits(**over: Any) -> SyncLimits:
    """按生产配置派生一份缩小的预算。

    只覆盖显式给出的字段，其余原样 —— 这样「被测常量」仍来自单一真源配置文件，
    不是在测试里另写一套数字（自证式同义反复）。
    """
    base = load_limits()
    fields = {
        name: getattr(base, name)
        for name in base.__dataclass_fields__
        if name != "ooxml"
    }
    fields.update(over)
    return SyncLimits(ooxml=base.ooxml, **fields)


class TestProperty60BudgetsFailVisible:
    """**Validates: Requirements 14.11**"""

    def test_streaming_row_budget_boundaries(self) -> None:
        """行预算 N-1 / N 合法、N+1 拒绝 —— 用**生产数字**驱动流式计数器。"""
        limits = load_limits()
        budget = X.StreamingProjectionBudget(limits)
        for _ in range(limits.max_table_rows):
            budget.add_row("t")
        assert budget.table_row_counts["t"] == limits.max_table_rows
        with pytest.raises(BudgetExceededError) as exc:
            budget.add_row("t")
        assert exc.value.budget == "max_table_rows"
        assert exc.value.observed == limits.max_table_rows + 1
        assert exc.value.limit == limits.max_table_rows

    def test_streaming_field_budget_boundaries(self) -> None:
        limits = load_limits()
        budget = X.StreamingProjectionBudget(limits)
        budget.add_field(limits.max_projection_fields - 1)
        budget.add_field(1)
        assert budget.field_count == limits.max_projection_fields
        with pytest.raises(BudgetExceededError) as exc:
            budget.add_field(1)
        assert exc.value.budget == "max_projection_fields"

    def test_row_budget_is_wired_into_extract(
        self, base_path: Path, definitions: FrozenEntryDefinitions
    ) -> None:
        """N（=19 行）通过、N-1 拒绝 —— 证明预算门真的在 extract 里跑，不是只存在于 limits。"""
        ok = extract(
            base_path, definitions, limits=scaled_limits(max_table_rows=EXPECTED_ROW_COUNT)
        )
        assert ok.stats.table_row_counts["k11_rows"] == EXPECTED_ROW_COUNT
        with pytest.raises(BudgetExceededError) as exc:
            extract(
                base_path,
                definitions,
                limits=scaled_limits(max_table_rows=EXPECTED_ROW_COUNT - 1),
            )
        assert exc.value.budget == "max_table_rows"
        assert exc.value.observed == EXPECTED_ROW_COUNT

    def test_field_budget_is_wired_into_extract(
        self, base_path: Path, definitions: FrozenEntryDefinitions
    ) -> None:
        total = EXPECTED_ROW_COUNT * 3 + 1
        extract(base_path, definitions, limits=scaled_limits(max_projection_fields=total))
        with pytest.raises(BudgetExceededError) as exc:
            extract(
                base_path,
                definitions,
                limits=scaled_limits(max_projection_fields=total - 1),
            )
        assert exc.value.budget == "max_projection_fields"

    def test_zip_entry_budget_is_wired_into_extract(
        self, base_path: Path, base_bytes: bytes, definitions: FrozenEntryDefinitions
    ) -> None:
        """ZIP 边界由 Task 11 的安全门承担，但必须证明它在 extract 入口真的跑。"""
        entries = len([n for n in _read_entries(base_bytes) if not n.endswith("/")])
        extract(base_path, definitions, limits=scaled_limits(max_zip_entries=entries))
        with pytest.raises(BudgetExceededError) as exc:
            extract(base_path, definitions, limits=scaled_limits(max_zip_entries=entries - 1))
        assert exc.value.budget == "max_zip_entries"

    def test_compressed_size_budget_is_wired_into_extract(
        self, base_path: Path, definitions: FrozenEntryDefinitions
    ) -> None:
        size = base_path.stat().st_size
        extract(base_path, definitions, limits=scaled_limits(max_compressed_bytes=size))
        with pytest.raises(BudgetExceededError) as exc:
            extract(
                base_path, definitions, limits=scaled_limits(max_compressed_bytes=size - 1)
            )
        assert exc.value.budget == "max_compressed_bytes"

    def test_budget_abort_leaves_no_truncated_sidecar(
        self, base_path: Path, definitions: FrozenEntryDefinitions, workdir: Path
    ) -> None:
        """越界中止时不得留下被截断的 sidecar —— 留下就是「静默截断」。"""
        sidecar = workdir / "aborted.ndjson.gz"
        with pytest.raises(BudgetExceededError):
            extract(
                base_path,
                definitions,
                limits=scaled_limits(max_projection_fields=5),
                sidecar_path=sidecar,
            )
        assert not sidecar.exists(), "越界中止后仍留下半成品 sidecar"

    def test_rows_per_chunk_is_derived_from_limits_not_hardcoded(self) -> None:
        """块大小随预算变化 —— 写死数字时这里打红。"""
        limits = load_limits()
        assert X.rows_per_chunk(limits) == limits.peak_memory_budget_bytes // limits.chunk_bytes
        smaller = scaled_limits(peak_memory_budget_bytes=limits.chunk_bytes * 5)
        assert X.rows_per_chunk(smaller) == 5
        assert X.rows_per_chunk(scaled_limits(peak_memory_budget_bytes=1)) == 1


# ═══════════════════════════════════════════════════════════════════════════
# 12. 未管理区域 digest 与 verifier（Requirement 6.17 / AC 8.11）
# ═══════════════════════════════════════════════════════════════════════════


def unmanaged_verify(
    before: Path, after: Path, contract: Any, outcome: X.ExcelExtractOutcome
) -> Any:
    return X.verify_unmanaged_regions(
        before=before,
        after=after,
        contract=contract,
        region=outcome.region,
        binding=BINDING,
        scan=outcome.scan,
    )


class TestUnmanagedRegionVerifier:
    """**Validates: Requirements 6.11 / 6.17 / 8.11**"""

    def test_coverage_is_not_empty_for_any_aspect(
        self, base_outcome: X.ExcelExtractOutcome
    ) -> None:
        """8 个 aspect 的覆盖计数全部 > 0 —— 空集恒等价是假绿第③源。

        真实 K11 模板带 7 sheet / 1 drawing / 212 个 sharedString，正是为了让这条判据
        有内容可比；换成手搓的最小 xlsx 时这里会立刻打红。
        """
        assert set(base_outcome.unmanaged.aspects) == set(X.UNMANAGED_ASPECTS)
        zero = {k: v for k, v in base_outcome.unmanaged.coverage.items() if v <= 0}
        assert zero == {}, f"空转的 aspect: {zero}"
        assert base_outcome.unmanaged.coverage["protected_parts"] >= 1
        assert base_outcome.unmanaged.coverage["other_sheet_parts"] >= 5
        assert base_outcome.unmanaged.part_count > 20

    def test_identical_bytes_are_equivalent(
        self, base_path: Path, contract: Any, base_outcome: X.ExcelExtractOutcome
    ) -> None:
        report = unmanaged_verify(base_path, base_path, contract, base_outcome)
        assert report.equivalent is True
        assert report.first_difference is None
        assert report.inspected_aspects == X.UNMANAGED_ASPECTS

    def test_managed_cell_change_is_allowed(
        self,
        base_bytes: bytes,
        sheet_part: str,
        base_path: Path,
        contract: Any,
        base_outcome: X.ExcelExtractOutcome,
        workdir: Path,
    ) -> None:
        """只改受管格 ⇒ 未管理区域仍等价（否则 materialize 每次都会被自己的写入打红）。"""
        after = write(
            workdir,
            "managed_only.xlsx",
            patch_cells(base_bytes, sheet_part, {f"C{FIRST_ROW}": 4321}),
        )
        report = unmanaged_verify(base_path, after, contract, base_outcome)
        assert report.equivalent is True, report.first_difference

    def test_unmanaged_cell_on_managed_sheet_is_caught(
        self,
        base_bytes: bytes,
        sheet_part: str,
        base_path: Path,
        contract: Any,
        base_outcome: X.ExcelExtractOutcome,
        workdir: Path,
    ) -> None:
        """改受管 sheet 上一个**非受管**格（表头 A5）⇒ 打红，按单元格粒度而不是按行。"""
        after = write(
            workdir,
            "unmanaged_cell.xlsx",
            patch_cells(base_bytes, sheet_part, {"A5": "被改过的表头"}),
        )
        report = unmanaged_verify(base_path, after, contract, base_outcome)
        assert report.equivalent is False
        assert "managed_sheet_unmanaged_cells" in (report.first_difference or "")

    def test_protected_part_change_is_caught(
        self,
        base_bytes: bytes,
        base_path: Path,
        contract: Any,
        base_outcome: X.ExcelExtractOutcome,
        workdir: Path,
    ) -> None:
        """drawing 部件被改 ⇒ 打红（Requirement 6.17 的 drawing/chart/pivot 一格）。"""
        drawing = next(
            n for n in _read_entries(base_bytes) if n.startswith("xl/drawings/")
        )
        after = write(
            workdir,
            "drawing_changed.xlsx",
            edit_part(base_bytes, drawing, lambda blob: blob + b"<!--tampered-->"),
        )
        report = unmanaged_verify(base_path, after, contract, base_outcome)
        assert report.equivalent is False
        assert "protected_parts" in (report.first_difference or "")

    def test_other_sheet_change_is_caught(
        self,
        base_bytes: bytes,
        base_path: Path,
        contract: Any,
        base_outcome: X.ExcelExtractOutcome,
        workdir: Path,
    ) -> None:
        other = _sheet_part_of(base_bytes, "明细表K11-2")
        after = write(
            workdir,
            "other_sheet_changed.xlsx",
            patch_cells(base_bytes, other, {"B11": "偷改了明细表"}),
        )
        report = unmanaged_verify(base_path, after, contract, base_outcome)
        assert report.equivalent is False
        assert "other_sheet_parts" in (report.first_difference or "")

    def test_managed_sheet_structure_change_is_caught(
        self,
        base_bytes: bytes,
        sheet_part: str,
        base_path: Path,
        contract: Any,
        base_outcome: X.ExcelExtractOutcome,
        workdir: Path,
    ) -> None:
        """merge 区域被改 ⇒ `managed_sheet_structure` 打红（Requirement 6.17 的 merge 一格）。"""

        def drop_a_merge(blob: bytes) -> bytes:
            text = blob.decode("utf-8")
            match = re.search(r'<mergeCell ref="[^"]+"/>', text)
            assert match, "受管 sheet 上没有 mergeCell，判据无法构造"
            return text.replace(match.group(0), "", 1).encode("utf-8")

        after = write(
            workdir,
            "merge_changed.xlsx",
            edit_part(base_bytes, sheet_part, drop_a_merge),
        )
        report = unmanaged_verify(base_path, after, contract, base_outcome)
        assert report.equivalent is False
        assert "managed_sheet_structure" in (report.first_difference or "")

    def test_appending_shared_strings_is_allowed_but_editing_existing_is_not(
        self,
        base_bytes: bytes,
        base_path: Path,
        contract: Any,
        base_outcome: X.ExcelExtractOutcome,
        workdir: Path,
    ) -> None:
        """追加 `<si>` 合法（写新文本必然发生），改动**已有** `<si>` 打红。"""

        def append_si(blob: bytes) -> bytes:
            text = blob.decode("utf-8")
            return text.replace(
                "</sst>", "<si><t>全新的字符串</t></si></sst>", 1
            ).encode("utf-8")

        appended = write(
            workdir,
            "si_appended.xlsx",
            edit_part(base_bytes, "xl/sharedStrings.xml", append_si),
        )
        assert unmanaged_verify(base_path, appended, contract, base_outcome).equivalent is True

        def edit_first_si(blob: bytes) -> bytes:
            text = blob.decode("utf-8")
            match = re.search(r"<si>(.*?)</si>", text, re.S)
            assert match
            return text.replace(
                match.group(0), "<si><t>第一个被改了</t></si>", 1
            ).encode("utf-8")

        edited = write(
            workdir,
            "si_edited.xlsx",
            edit_part(base_bytes, "xl/sharedStrings.xml", edit_first_si),
        )
        report = unmanaged_verify(base_path, edited, contract, base_outcome)
        assert report.equivalent is False
        assert "shared_strings_prefix" in (report.first_difference or "")

    def test_catch_all_bucket_catches_new_unknown_part(
        self,
        base_bytes: bytes,
        base_path: Path,
        contract: Any,
        base_outcome: X.ExcelExtractOutcome,
        workdir: Path,
    ) -> None:
        """凭空多出一个没登记类别的部件 ⇒ catch-all 桶打红。

        没有 catch-all 时，「只检查了列出来的东西」这类漏检会静默通过。
        """
        entries = dict(_read_entries(base_bytes))
        entries["xl/somethingBrandNew.xml"] = b"<root/>"
        after = write(workdir, "new_part.xlsx", _write_entries(entries))
        report = unmanaged_verify(base_path, after, contract, base_outcome)
        assert report.equivalent is False
        assert "other_parts" in (report.first_difference or "")

    def test_calc_chain_is_explicitly_derived_and_ignored(
        self,
        base_bytes: bytes,
        base_path: Path,
        contract: Any,
        base_outcome: X.ExcelExtractOutcome,
        workdir: Path,
    ) -> None:
        """`xl/calcChain.xml` 是派生缓存，Excel/OO 每次保存重算 ⇒ 显式豁免，不得假红。"""
        assert "xl/calcChain.xml" in X.DERIVED_PARTS
        entries = dict(_read_entries(base_bytes))
        if "xl/calcChain.xml" not in entries:
            pytest.skip("该模板没有 calcChain 部件，此豁免在本 fixture 上不可观测")
        entries["xl/calcChain.xml"] = b"<calcChain/>"
        after = write(workdir, "calcchain.xlsx", _write_entries(entries))
        assert unmanaged_verify(base_path, after, contract, base_outcome).equivalent is True

    def test_digest_is_stable_across_recomputation(
        self,
        base_path: Path,
        contract: Any,
        base_outcome: X.ExcelExtractOutcome,
    ) -> None:
        """同一份字节两次计算 digest 必须相同（否则 verifier 会随机假红）。"""
        first = X.unmanaged_region_digest(
            base_path,
            contract=contract,
            region=base_outcome.region,
            binding=BINDING,
            scan=base_outcome.scan,
        )
        second = X.unmanaged_region_digest(
            base_path,
            contract=contract,
            region=base_outcome.region,
            binding=BINDING,
            scan=base_outcome.scan,
        )
        assert first.digest == second.digest
        assert first.aspects == second.aspects

    def test_missing_aspect_is_rejected_at_construction(self) -> None:
        with pytest.raises(UnmanagedRegionDriftError) as exc:
            X.UnmanagedRegionDigest(
                aspects={"managed_sheet_unmanaged_cells": _d("x")},
                coverage={"managed_sheet_unmanaged_cells": 1},
                part_count=1,
            )
        assert "aspect" in str(exc.value)


# ═══════════════════════════════════════════════════════════════════════════
# 13. projection sidecar：streaming gzip 与分块（Requirement 6.12）
# ═══════════════════════════════════════════════════════════════════════════


class TestStreamingSidecarAndChunking:
    """**Validates: Requirements 6.12**"""

    def test_sidecar_is_gzip_ndjson_and_round_trips(
        self, base_path: Path, definitions: FrozenEntryDefinitions, workdir: Path
    ) -> None:
        sidecar = workdir / "projection.ndjson.gz"
        outcome = extract(base_path, definitions, sidecar_path=sidecar)
        assert sidecar.read_bytes()[:2] == b"\x1f\x8b", "不是 gzip 流"
        header, fields = X.read_projection_sidecar(sidecar)
        assert header["contract_id"] == CONTRACT_ID
        assert header["table_key"] == "k11_rows"
        assert header["table_ref"] == EXPECTED_TABLE_REF
        assert len(fields) == outcome.stats.field_count == 58
        by_key = {row["stable_key"]: row for row in fields}
        for key, value in outcome.projection.values.items():
            assert key in by_key, key
            assert by_key[key]["value_type"] == value.value_type.value
            assert by_key[key]["mode"] == value.mode.value

    def test_sidecar_bytes_are_reproducible(
        self, base_path: Path, definitions: FrozenEntryDefinitions, workdir: Path
    ) -> None:
        """两次导出逐字节相同（`mtime=0`）—— 否则同一 projection 的 evidence digest 会漂。"""
        first = workdir / "repro_a.gz"
        second = workdir / "repro_b.gz"
        extract(base_path, definitions, sidecar_path=first)
        extract(base_path, definitions, sidecar_path=second)
        assert first.read_bytes() == second.read_bytes()

    def test_sidecar_never_holds_whole_projection_in_one_buffer(
        self, base_path: Path, definitions: FrozenEntryDefinitions, workdir: Path
    ) -> None:
        """峰值内存增量必须远小于「整份 projection 的序列化体积 × 2」。

        判据落在 `tracemalloc` 实测峰值上，不是「代码里写了 flush」。
        """
        import tracemalloc

        sidecar = workdir / "peak.gz"
        tracemalloc.start()
        try:
            extract(base_path, definitions, sidecar_path=sidecar)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        limits = load_limits()
        assert peak < limits.peak_memory_budget_bytes, (
            f"峰值 {peak} 超过流式内存预算 {limits.peak_memory_budget_bytes}"
        )

    def test_chunking_is_observable_and_driven_by_limits(
        self, base_path: Path, definitions: FrozenEntryDefinitions
    ) -> None:
        """缩小内存预算 ⇒ 块数真的变多（`chunk_count` 是实测量，不是声明值）。"""
        limits = load_limits()
        assert extract(base_path, definitions).stats.chunk_count == 1
        small = scaled_limits(peak_memory_budget_bytes=limits.chunk_bytes * 5)
        outcome = extract(base_path, definitions, limits=small)
        assert outcome.stats.rows_per_chunk == 5
        assert outcome.stats.chunk_count == -(-EXPECTED_ROW_COUNT // 5) == 4
        # 分块不得改变结果。
        assert outcome.projection.values == extract(base_path, definitions).projection.values

    def test_sidecar_rejects_wrong_schema_version(self, workdir: Path) -> None:
        bad = workdir / "bad_schema.gz"
        with gzip.open(bad, "wt", encoding="utf-8") as fh:
            fh.write(json.dumps({"schema_version": "excel-projection-sidecar:v0"}) + "\n")
        with pytest.raises(X.ExcelExtractError) as exc:
            X.read_projection_sidecar(bad)
        assert "schema" in str(exc.value)

    def test_standalone_sidecar_writer_matches_inline_one(
        self, base_outcome: X.ExcelExtractOutcome, workdir: Path
    ) -> None:
        """事后补写的 sidecar 与边读边写的字段集合一致（同一 writer，不是第二实现）。"""
        path = X.write_projection_sidecar(base_outcome, workdir / "after_the_fact.gz")
        _, fields = X.read_projection_sidecar(path)
        assert {row["stable_key"] for row in fields} == set(base_outcome.projection.values)


# ═══════════════════════════════════════════════════════════════════════════
# 14. commit 前置门（AC 8.11：未过不得交 ContentMutationService）
# ═══════════════════════════════════════════════════════════════════════════


class TestVerifyBeforeCommitGate:
    """**Validates: Requirements 8.11**"""

    def test_happy_path_passes_all_three_verifiers(
        self,
        base_bytes: bytes,
        sheet_part: str,
        base_path: Path,
        base_outcome: X.ExcelExtractOutcome,
        definitions: FrozenEntryDefinitions,
        workdir: Path,
    ) -> None:
        """staged result == substrate（只改了受管格）⇒ 三个 verifier 全过，可交 commit。"""
        staged = write(
            workdir,
            "staged_ok.xlsx",
            patch_cells(base_bytes, sheet_part, {f"C{FIRST_ROW}": 100 + FIRST_ROW}),
        )
        bundle = X.verify_before_commit(
            expected=base_outcome.projection,
            staged_result=staged,
            substrate=base_path,
            definitions=definitions,
            binding=BINDING,
            baseline_formulas=base_outcome.formula_inventory,
        )
        assert bundle.passed is True
        assert bundle.failed_verifiers == ()
        bundle.assert_publishable()
        assert bundle.as_dict()["passed"] is True

    def test_roundtrip_failure_blocks_commit_with_its_own_error(
        self,
        base_bytes: bytes,
        sheet_part: str,
        base_path: Path,
        base_outcome: X.ExcelExtractOutcome,
        definitions: FrozenEntryDefinitions,
        workdir: Path,
    ) -> None:
        staged = write(
            workdir,
            "staged_roundtrip_bad.xlsx",
            patch_cells(base_bytes, sheet_part, {f"C{FIRST_ROW}": -12345}),
        )
        bundle = X.verify_before_commit(
            expected=base_outcome.projection,
            staged_result=staged,
            substrate=base_path,
            definitions=definitions,
            binding=BINDING,
            baseline_formulas=base_outcome.formula_inventory,
        )
        assert bundle.failed_verifiers == ("roundtrip",)
        with pytest.raises(X.RoundtripEquivalenceError):
            bundle.assert_publishable()

    def test_formula_drift_blocks_commit_with_its_own_error(
        self,
        base_bytes: bytes,
        sheet_part: str,
        base_path: Path,
        base_outcome: X.ExcelExtractOutcome,
        definitions: FrozenEntryDefinitions,
        workdir: Path,
    ) -> None:
        staged = write(
            workdir,
            "staged_formula_bad.xlsx",
            patch_cells(
                base_bytes, sheet_part, {f"H{FIRST_ROW}": f"=G{FIRST_ROW}-D{FIRST_ROW}*2"}
            ),
        )
        bundle = X.verify_before_commit(
            expected=base_outcome.projection,
            staged_result=staged,
            substrate=base_path,
            definitions=definitions,
            binding=BINDING,
            baseline_formulas=base_outcome.formula_inventory,
        )
        assert bundle.failed_verifiers == ("formula_regions",)
        with pytest.raises(X.FormulaRegionDriftError):
            bundle.assert_publishable()

    def test_unmanaged_drift_blocks_commit_with_its_own_error(
        self,
        base_bytes: bytes,
        base_path: Path,
        base_outcome: X.ExcelExtractOutcome,
        definitions: FrozenEntryDefinitions,
        workdir: Path,
    ) -> None:
        drawing = next(
            n for n in _read_entries(base_bytes) if n.startswith("xl/drawings/")
        )
        staged = write(
            workdir,
            "staged_unmanaged_bad.xlsx",
            edit_part(base_bytes, drawing, lambda blob: blob + b"<!--x-->"),
        )
        bundle = X.verify_before_commit(
            expected=base_outcome.projection,
            staged_result=staged,
            substrate=base_path,
            definitions=definitions,
            binding=BINDING,
            baseline_formulas=base_outcome.formula_inventory,
        )
        assert bundle.failed_verifiers == ("unmanaged_regions",)
        with pytest.raises(UnmanagedRegionDriftError):
            bundle.assert_publishable()

    def test_three_failures_raise_three_distinct_exception_types(self) -> None:
        """三条判据各抛自己的类型 —— 统一成一个类型会让删掉任一条都不打红。"""
        assert len(
            {
                X.RoundtripEquivalenceError,
                X.FormulaRegionDriftError,
                UnmanagedRegionDriftError,
            }
        ) == 3
        codes = {
            X.RoundtripEquivalenceError.error_code,
            X.FormulaRegionDriftError.error_code,
            UnmanagedRegionDriftError.error_code,
        }
        assert len(codes) == 3, codes

    def test_empty_projection_is_not_a_pass(
        self,
        base_bytes: bytes,
        sheet_part: str,
        base_path: Path,
        definitions: FrozenEntryDefinitions,
        contract: Any,
        workdir: Path,
    ) -> None:
        """反读出零个受管字段时不得判「全过」—— 零次比对不是比对（AC 6.11）。"""
        wiped: dict[str, Any] = {f"B{FOOTER_ROW}": None}
        for row in range(FIRST_ROW, LAST_ROW + 1):
            wiped[f"C{row}"] = None
            wiped[f"J{row}"] = None
            wiped[f"H{row}"] = None
        staged = write(
            workdir, "staged_empty.xlsx", patch_cells(base_bytes, sheet_part, wiped)
        )
        empty = Projection(
            contract_id=contract.contract_id,
            semantic_version=contract.semantic_version,
            document_type=contract.document_type,
            values={},
            row_keys={},
        )
        bundle = X.verify_before_commit(
            expected=empty,
            staged_result=staged,
            substrate=base_path,
            definitions=definitions,
            binding=BINDING,
        )
        assert bundle.extracted.projection.values == {}
        with pytest.raises(X.VerificationNotPassedError) as exc:
            bundle.assert_publishable()
        assert "6.11" in str(exc.value)

    def test_quarantined_substrate_is_rejected_at_gate(
        self,
        base_path: Path,
        base_outcome: X.ExcelExtractOutcome,
        definitions: FrozenEntryDefinitions,
    ) -> None:
        with pytest.raises(QuarantinedIncomingError):
            X.verify_before_commit(
                expected=base_outcome.projection,
                staged_result=base_path,
                substrate=base_path,
                definitions=definitions,
                binding=BINDING,
                substrate_state=ArtifactState.quarantined,
            )


# ═══════════════════════════════════════════════════════════════════════════
# 15. engine 入口门与结构性自证
# ═══════════════════════════════════════════════════════════════════════════


class TestEngineEntryGates:
    """**Validates: Requirements 6.10 / 6.20 / 8.10**"""

    def test_quarantined_incoming_never_enters_engine(
        self, base_path: Path, definitions: FrozenEntryDefinitions
    ) -> None:
        with pytest.raises(QuarantinedIncomingError):
            extract(base_path, definitions, artifact_state=ArtifactState.quarantined)

    def test_upgrade_candidate_never_enters_engine(
        self, base_path: Path, definitions: FrozenEntryDefinitions
    ) -> None:
        with pytest.raises(AdapterCandidateSubstrateError):
            extract(
                base_path,
                definitions,
                artifact_kind=ArtifactKind.upgrade_candidate,
                artifact_state=ArtifactState.candidate,
            )

    def test_handmade_definitions_without_bundle_are_rejected(
        self, base_path: Path, contract: Any, base_inventory: dict[str, Any]
    ) -> None:
        """绕过 Task 36 loader 手拼的 `FrozenEntryDefinitions` 必须被拒。"""
        handmade = make_definitions(contract, base_inventory, bundle=None)
        with pytest.raises(X.ExcelExtractError) as exc:
            extract(base_path, handmade)
        assert "Task 36" in str(exc.value)

    def test_unapproved_bundle_is_rejected(
        self, base_path: Path, contract: Any, base_inventory: dict[str, Any]
    ) -> None:
        from app.services.workpaper_sync.models import BundleIntegrityError

        unapproved = make_definitions(
            contract,
            base_inventory,
            bundle=make_bundle(contract, state=DefinitionState.candidate),
        )
        with pytest.raises(BundleIntegrityError):
            extract(base_path, unapproved)

    def test_contract_digest_drift_is_rejected(
        self, base_path: Path, contract: Any, base_inventory: dict[str, Any]
    ) -> None:
        """bundle 的 contract slot digest 与磁盘契约不符 ⇒ 按 alias 顶替被拒（Property 28）。"""
        from app.services.workpaper_sync.adapters.registry import StaleAdapterError

        drifted = make_definitions(
            contract,
            base_inventory,
            bundle=make_bundle(contract, contract_slot_digest=_d("some-other-contract")),
        )
        with pytest.raises(StaleAdapterError):
            extract(base_path, drifted)

    def test_dynamic_columns_without_measured_binding_fail_closed(
        self, base_path: Path, base_inventory: dict[str, Any]
    ) -> None:
        """契约声明了 dynamic_columns 却没给实测列绑定 ⇒ fail closed，不按右移一格猜。"""
        dyn = parse_contract(
            contract_payload(with_dynamic_columns=True), adapter_id=CONTRACT_ID
        )
        definitions = make_definitions(dyn, base_inventory)
        with pytest.raises(X.DynamicColumnBindingMissingError) as exc:
            extract(base_path, definitions)
        assert "6.4" in str(exc.value)

    def test_dynamic_columns_with_measured_binding_work(
        self, base_path: Path, base_inventory: dict[str, Any]
    ) -> None:
        """给了实测 `{slot}_{seq}` → 列绑定后照常反读（证明上一条不是把功能关掉了）。"""
        dyn = parse_contract(
            contract_payload(with_dynamic_columns=True), adapter_id=CONTRACT_ID
        )
        definitions = make_definitions(dyn, base_inventory)
        binding = X.ExcelIdentityBinding(
            table_name=TABLE_NAME,
            uuid_column=UUID_COL,
            table_key="k11_rows",
            dynamic_column_columns={
                "k11_rows": {"adjustment": "C", "reason": "J", "variance": "H"}
            },
        )
        outcome = extract(base_path, definitions, binding=binding)
        assert outcome.stats.field_count == 58

    def test_second_dynamic_table_on_same_sheet_fails_closed(
        self, base_inventory: dict[str, Any]
    ) -> None:
        """第二张动态行表没有自己的 Table/UUID 绑定 ⇒ 拒绝沿用第一组。"""
        payload = contract_payload()
        second = json.loads(json.dumps(payload["sheets"][0]["tables"][0]))
        second["table_key"] = "k11_rows_2"
        second["anchor"] = "A30"
        for field in second["fields"]:
            field["stable_field_key"] = field["stable_field_key"].replace(
                "k11_rows/", "k11_rows_2/"
            )
        payload["sheets"][0]["tables"].append(second)
        contract = parse_contract(payload, adapter_id=CONTRACT_ID)
        with pytest.raises(X.ManagedRegionResolutionError) as exc:
            X.managed_tables_of(contract, binding=BINDING)
        assert "k11_rows_2" in str(exc.value)

    def test_binding_table_key_must_be_dynamic(self, contract: Any) -> None:
        with pytest.raises(X.ManagedRegionResolutionError):
            X.managed_tables_of(
                contract,
                binding=X.ExcelIdentityBinding(
                    table_name=TABLE_NAME, uuid_column=UUID_COL, table_key="k11_footer"
                ),
            )

    def test_uuid_column_outside_table_span_fails_closed(
        self, base_path: Path, definitions: FrozenEntryDefinitions
    ) -> None:
        """UUID 列落在 Table 列跨度之外 ⇒ 插删行时会与数据行错位，必须拒。"""
        with pytest.raises(X.ManagedRegionResolutionError) as exc:
            extract(
                base_path,
                definitions,
                binding=X.ExcelIdentityBinding(
                    table_name=TABLE_NAME, uuid_column="Z", table_key="k11_rows"
                ),
            )
        assert "Z" in str(exc.value)


class TestStructuralSelfChecks:
    """**Validates: Requirements 6.20 / 14.11**（守卫自身的反向自检）"""

    def test_module_has_no_materializer_dependency(self) -> None:
        """真实 import 图里没有 Task 38 的 materializer（不是 grep 源码字符串）。"""
        assert X.assert_no_materializer_dependency() == ()
        assert X.FORBIDDEN_DOWNSTREAM_MODULES, "禁用清单为空 ⇒ 判据恒真"

    def test_materializer_dependency_guard_can_actually_fail(self) -> None:
        """反向自检：把一个下游模块塞进 `sys.modules`，守卫必须打红。

        少了这一条，`assert_no_materializer_dependency` 在「清单写错模块名」时恒返回空。
        """
        name = X.FORBIDDEN_DOWNSTREAM_MODULES[0]
        import types

        sys.modules[name] = types.ModuleType(name)
        try:
            with pytest.raises(X.ExcelExtractError) as exc:
                X.assert_no_materializer_dependency()
            assert name in str(exc.value)
        finally:
            del sys.modules[name]

    def test_every_error_code_is_unique(self) -> None:
        """本模块每个异常类型有自己的 `error_code` —— 共用会让分类不可分辨。"""
        classes = [
            getattr(X, name)
            for name in X.__all__
            if isinstance(getattr(X, name), type)
            and issubclass(getattr(X, name), Exception)
        ]
        assert len(classes) >= 8, [c.__name__ for c in classes]
        codes = [c.error_code for c in classes]
        assert len(set(codes)) == len(codes), sorted(codes)

    def test_unmanaged_aspects_end_with_catch_all(self) -> None:
        assert X.UNMANAGED_ASPECTS[-1] == "other_parts"
        assert len(set(X.UNMANAGED_ASPECTS)) == len(X.UNMANAGED_ASPECTS) == 8

    def test_extract_never_writes_to_the_artifact(
        self, base_path: Path, definitions: FrozenEntryDefinitions
    ) -> None:
        """extract 是只读的：跑完 artifact 的 mtime 与 digest 都不变。"""
        before = (base_path.stat().st_mtime_ns, hashlib.sha256(base_path.read_bytes()).hexdigest())
        extract(base_path, definitions)
        after = (base_path.stat().st_mtime_ns, hashlib.sha256(base_path.read_bytes()).hexdigest())
        assert before == after

    def test_outcome_carries_no_write_surface(
        self, base_outcome: X.ExcelExtractOutcome
    ) -> None:
        """outcome 是纯数据：不得暴露 commit/flush/publish 之类的能力面。"""
        from app.services.workpaper_sync.adapters.base import assert_no_mutation_surface

        assert_no_mutation_surface(base_outcome, label="ExcelExtractOutcome")

    def test_as_dict_is_json_serialisable_for_evidence(
        self, base_outcome: X.ExcelExtractOutcome
    ) -> None:
        payload = base_outcome.as_dict()
        blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        assert json.loads(blob)["field_count"] == 58
        assert len(payload["formula_inventory_sha256"]) == 64
        assert payload["formula_inventory_size"] == EXPECTED_ROW_COUNT


class TestStagedResultSubstrateRole:
    """新增的 `SubstrateRole.staged_result` 的边界（Task 13 `base.py` 的加法）。

    **Validates: Requirements 6.11 / 8.10**

    加它而不是让 verifier 绕过 substrate 门：绕过会把 quarantined / candidate 的准入判据
    一起绕掉。这里逐条锁死它**只**接受 `canonical/staged`，且不成为隔离样本的旁路。
    """

    def test_canonical_staged_is_accepted(self) -> None:
        from app.services.workpaper_sync.adapters.base import assert_substrate_usable

        assert_substrate_usable(
            role=SubstrateRole.staged_result,
            artifact_kind=ArtifactKind.canonical,
            artifact_state=ArtifactState.staged,
        )

    @pytest.mark.parametrize(
        "kind,state,expected",
        [
            (ArtifactKind.incoming, ArtifactState.staged, "kind=canonical"),
            (ArtifactKind.canonical, ArtifactState.published, "state=staged"),
            (ArtifactKind.canonical, ArtifactState.durable, "state=staged"),
        ],
    )
    def test_other_combinations_are_rejected(
        self, kind: ArtifactKind, state: ArtifactState, expected: str
    ) -> None:
        from app.services.workpaper_sync.adapters.base import (
            AdapterSubstrateError,
            assert_substrate_usable,
        )

        with pytest.raises(AdapterSubstrateError) as exc:
            assert_substrate_usable(role=SubstrateRole.staged_result, artifact_kind=kind,
                                    artifact_state=state)
        assert expected in str(exc.value)

    def test_quarantined_and_candidate_still_rejected_first(self) -> None:
        """新角色不得成为隔离/candidate 的旁路 —— 两条判据在 role 分支**之前**。"""
        from app.services.workpaper_sync.adapters.base import assert_substrate_usable

        with pytest.raises(QuarantinedIncomingError):
            assert_substrate_usable(
                role=SubstrateRole.staged_result,
                artifact_kind=ArtifactKind.canonical,
                artifact_state=ArtifactState.quarantined,
            )
        with pytest.raises(AdapterCandidateSubstrateError):
            assert_substrate_usable(
                role=SubstrateRole.staged_result,
                artifact_kind=ArtifactKind.upgrade_candidate,
                artifact_state=ArtifactState.staged,
            )
