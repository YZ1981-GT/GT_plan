"""R13：OO 在可编辑文本列里填的数字按文本读回；读不懂的 incoming 值不得被直接采纳。

真栈实证（和平药房 2025 D2，10-24 01:26 UTC，operation 813a2167）：incoming 的 C13（公司代码，
契约 text）是数值 231；base / current 都没有这个字段 ⇒ 三方合并不比较值、直接采纳 int ⇒
物化写盘 `EditableCellWriteError`（`excel_materialize_editable_write_failed`），incoming 已
durable、表单没变（spec writeback-followup-issue-closure R13 / design D14）。

三层：

1. `numeric_cell_as_text` 纯函数，含不转换的边界；
2. `excel_extract._collect_fields`：可编辑文本列转换，受保护文本列、金额列、枚举列不转换；
3. 真 D2 链路（生产 instrument / materialize / extract / merge / rematerialize / roundtrip），
   复现那次失败的形态：首行没有公司代码，OO 在该行 C 列写数值 231；
4. merge：base / current 都没有的字段，incoming 读不懂 ⇒ schema 冲突、不采纳；能规范化的照常采纳。
"""
from __future__ import annotations

import dataclasses
import hashlib
import io
import json
import math
import os
import re
import sys
import uuid
import zipfile
from decimal import Decimal
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.excel_structure_fingerprint import identity_inventory  # noqa: E402
from app.services.workpaper_sync import excel_extract as X  # noqa: E402
from app.services.workpaper_sync import pilot_d2_large_json as P  # noqa: E402
from app.services.workpaper_sync import projection_first_publication as F  # noqa: E402
from app.services.workpaper_sync.adapters import excel as AX  # noqa: E402
from app.services.workpaper_sync.adapters.base import FieldValue, Projection  # noqa: E402
from app.services.workpaper_sync.conflicts import ConflictKind, SchemaAnomalyKind  # noqa: E402
from app.services.workpaper_sync.content_mutation import (  # noqa: E402
    assert_roundtrip_equivalent,
)
from app.services.workpaper_sync.contracts import FieldMode, ValueType  # noqa: E402
from app.services.workpaper_sync.excel_entry_gate import (  # noqa: E402
    AdapterBuild,
    FrozenEntryDefinitions,
    parse_identity_inventory,
)
from app.services.workpaper_sync.merge import FieldVerdict, merge_projections  # noqa: E402
from app.services.workpaper_sync.models import (  # noqa: E402
    AuthorityModel,
    BundleSlot,
    BundleSlotSpec,
    DefinitionState,
)
from app.services.workpaper_sync.oo_text_cell import numeric_cell_as_text  # noqa: E402
from app.services.workpaper_sync.resolution import DefinitionBundleSnapshot  # noqa: E402

_T = P.ROWS_TABLE_KEY
ROW_A = "dr-r13-row-a"
ROW_B = "dr-r13-row-b"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 纯函数
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (231, "231"),
        (0, "0"),
        (-15, "-15"),
        (12345678901234567890, "12345678901234567890"),
        (231.0, "231"),
        (-0.0, "0"),
        (1.5, "1.5"),
        (-2.25, "-2.25"),
        (0.1, "0.1"),
        (1e-05, "0.00001"),
        (123456.789, "123456.789"),
        (float(2**53 - 1), str(2**53 - 1)),
        (Decimal("231.50"), "231.5"),
        (Decimal("100"), "100"),
        (Decimal("-0.0"), "0"),
    ],
)
def test_numbers_read_back_as_the_digits_the_user_typed(value: Any, text: str) -> None:
    assert numeric_cell_as_text(value) == text


@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        math.nan,
        math.inf,
        -math.inf,
        float(2**53),
        1.2345678901234568e18,
        Decimal("NaN"),
        Decimal("Infinity"),
        "231",
        None,
        date(2025, 1, 1),
        datetime(2025, 1, 1, 8, 0),
    ],
)
def test_values_that_cannot_be_restored_unambiguously_are_not_converted(value: Any) -> None:
    assert numeric_cell_as_text(value) is None


# ═══════════════════════════════════════════════════════════════════════════
# 2. extract：只转换可编辑文本列
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def contract() -> Any:
    return P.load_pilot_contract()


def _table(contract: Any) -> Any:
    return next(t for sheet in contract.sheets for t in sheet.tables if t.table_key == _T)


def _spec(contract: Any, column_key: str) -> Any:
    return next(f for f in _table(contract).fields if f.column_key == column_key)


class _Budget:
    def add_field(self) -> None:
        return None


def _collect(
    contract: Any, spec: Any, raw: Any, *, incoming: bool = True
) -> tuple[dict[str, FieldValue], list[Any]]:
    values: dict[str, FieldValue] = {}
    anomalies: list[Any] = []
    X._collect_fields(
        specs=[spec], row_identity=ROW_A, excel_rows=[13],
        cells={f"{spec.cell.column}13": raw}, formula_cells={},
        table=_table(contract), region=SimpleNamespace(sheet_name=P.MANAGED_SHEET), binding=None,
        values=values, formula_inventory={}, anomalies=anomalies, findings=[],
        baseline=None, baseline_formulas=None, budget=_Budget(), sidecar=None,
        numbers_as_typed_text=incoming,
    )
    return values, anomalies


def test_editable_text_column_reads_a_number_as_its_text(contract: Any) -> None:
    spec = _spec(contract, "company_code")
    assert spec.value_type is ValueType.text and not spec.is_protected
    values, anomalies = _collect(contract, spec, 231)
    key = P.stable_key_for("company_code", ROW_A)
    assert values[key].value == "231" and isinstance(values[key].value, str)
    assert anomalies == []


def test_published_and_staged_artifacts_are_still_read_strictly(contract: Any) -> None:
    """只有 OO 保存回来的 incoming 才按键入的文本读：已发布版本与物化产物上的数值格照旧记
    观测、保留原值 —— 反读校验靠这一点看出「文本格没写」（test_single_pass_artifact_equivalence
    的漏写反证就是这一类）。"""
    values, anomalies = _collect(contract, _spec(contract, "company_code"), 231, incoming=False)
    assert values[P.stable_key_for("company_code", ROW_A)].value == 231
    assert [a.kind for a in anomalies] == [SchemaAnomalyKind.type_normalization_failure]


def test_editable_text_column_keeps_strings_unchanged(contract: Any) -> None:
    values, anomalies = _collect(contract, _spec(contract, "company_code"), "0231")
    assert values[P.stable_key_for("company_code", ROW_A)].value == "0231"
    assert anomalies == []


@pytest.mark.parametrize(
    ("column_key", "mode", "raw"),
    [
        ("company_code", FieldMode.formula, 231),   # 受保护文本列：公式结果的类型不由用户键入决定
        ("company_code", None, datetime(2025, 1, 1)),  # 文本列里的日期：不转换
        ("company_code", None, True),               # 布尔：不转换
        ("company_code", None, float(2**53)),        # 超出双精度整数精度：不转换
        ("prior_unadjusted", None, "abc"),          # 金额列填文字
        ("relation_type", None, 1),                 # 枚举列填数字：不在本次范围
    ],
)
def test_other_type_mismatches_still_record_the_anomaly(
    contract: Any, column_key: str, mode: FieldMode | None, raw: Any
) -> None:
    spec = _spec(contract, column_key)
    if mode is not None:
        spec = dataclasses.replace(spec, mode=mode)
    values, anomalies = _collect(contract, spec, raw)
    assert values[P.stable_key_for(column_key, ROW_A)].value == raw, "保留原值供裁决"
    assert [a.kind for a in anomalies] == [SchemaAnomalyKind.type_normalization_failure]


def test_static_text_cell_next_to_a_dynamic_table_follows_the_same_rule(tmp_path: Path) -> None:
    """动态区那张 sheet 上的静态格块（`extract_projection` 7.1）同一规则：D2 没有这种格，
    用 Task 37 的 K11 真模板 + 页脚加一个可编辑文本格。"""
    from app.services.workpaper_sync import excel_instrumentation as EI
    from app.services.workpaper_sync.adapters.base import SubstrateRole
    from app.services.workpaper_sync.contracts import parse_contract
    from app.services.workpaper_sync.models import ArtifactKind, ArtifactState

    import test_task37_excel_extract as K

    payload = K.contract_payload()
    footer = next(t for t in payload["sheets"][0]["tables"] if t["table_key"] == "k11_footer")
    footer["fields"].append({
        "stable_field_key": "k11_footer/footer_note", "json_pointer": "/footerNote",
        "column_key": "footer_note", "cell": {"column": "J", "row_from": K.FOOTER_ROW},
        "mode": "editable", "value_type": "text", "source_ref": f"源xlsx!{K.MANAGED_SHEET}!J{K.FOOTER_ROW}",
    })
    k11 = parse_contract(payload, adapter_id=K.CONTRACT_ID)
    instrumented = EI.instrument_workbook_bytes(
        K.TEMPLATE.read_bytes(), K.SPEC, gate=EI.ExcelIdentityCarrierGate.load()
    ).instrumented_bytes
    part = K._sheet_part_of(instrumented, K.MANAGED_SHEET)
    data = K.patch_cells(instrumented, part, {**K.business_cells(), f"J{K.FOOTER_ROW}": 4567})
    definitions = K.make_definitions(
        k11, identity_inventory(data, expected_table=K.TABLE_NAME, uuid_column_letter=K.UUID_COL)
    )
    path = tmp_path / "k11.xlsx"
    path.write_bytes(data)
    shapes = {
        "incoming": (SubstrateRole.incoming, ArtifactKind.incoming, ArtifactState.durable),
        "published": (SubstrateRole.published_representation, ArtifactKind.canonical,
                      ArtifactState.published),
    }
    outcomes = {
        name: X.extract_projection(
            artifact=path, definitions=definitions, binding=K.BINDING, substrate_role=role,
            artifact_kind=kind, artifact_state=state,
        )
        for name, (role, kind, state) in shapes.items()
    }
    assert outcomes["incoming"].projection.get("k11_footer/footer_note").value == "4567"
    assert outcomes["published"].projection.get("k11_footer/footer_note").value == 4567
    kinds = {name: [a.kind for a in o.anomalies if a.stable_field_key == "k11_footer/footer_note"]
             for name, o in outcomes.items()}
    assert kinds == {"incoming": [], "published": [SchemaAnomalyKind.type_normalization_failure]}


# ═══════════════════════════════════════════════════════════════════════════
# 3. 真 D2 链路：复现 10-24 那次失败的形态
# ═══════════════════════════════════════════════════════════════════════════


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


@pytest.fixture(scope="module")
def staged(contract: Any, tmp_path_factory: pytest.TempPathFactory) -> Any:
    return F.stage_instrumented_substrate(
        entry_id=P.PILOT_ENTRY_ID, staging_dir=tmp_path_factory.mktemp("r13-staged"), contract=contract
    )


def _adapter(
    contract: Any, staged: Any, *, direction: str, baseline: Path | None = None,
    inventory_from: Path | None = None,
) -> Any:
    """与生产注册同形：读已发布产物时冻结 inventory 取已发布那一份（Task 75 的观测口径），
    不取模板的 —— 骨架槽位复用后模板的 12 个骨架身份已不在已发布产物里。"""
    inventory = staged.identity_inventory
    source = inventory_from or baseline
    if source is not None:
        inventory = parse_identity_inventory(
            identity_inventory(
                source.read_bytes(), expected_table=P.TABLE_NAME, uuid_column_letter=P.UUID_COL
            )
        )

    def slot(kind: BundleSlot, digest: str) -> BundleSlotSpec:
        return BundleSlotSpec(kind, "definition", f"definition:{uuid.uuid4()}", digest)

    bundle = DefinitionBundleSnapshot(
        bundle_id=uuid.uuid4(), bundle_sha256=_d("r13-bundle"), schema_version="definition-bundle:v1",
        state=DefinitionState.approved, authority_model=AuthorityModel.projection_contract,
        authority_model_definition_id=uuid.uuid4(), authority_model_definition_sha256=_d("r13-authority"),
        slots={
            BundleSlot.template: slot(BundleSlot.template, contract.template_definition_sha256),
            BundleSlot.instrumentation: slot(
                BundleSlot.instrumentation, contract.instrumentation_definition_sha256
            ),
            BundleSlot.contract: slot(BundleSlot.contract, contract.canonical_sha256),
        },
    )
    definitions = FrozenEntryDefinitions(
        entry_id=P.PILOT_ENTRY_ID, bundle=bundle, contract=contract,
        adapter_build=AdapterBuild(
            adapter_id=P.PILOT_ADAPTER_ID, adapter_build_digest=_d("r13-build"),
            document_type="xlsx", contract_version=str(contract.semantic_version),
        ),
        identity_inventory=inventory, business_sheets=(), dynamic_column_keys={},
        structure_inventory_size=0,
    )
    primary = F._identity_binding(provider=P, staged=staged, contract=contract)
    siblings = F._sibling_identity_bindings(
        provider=P, staged=staged, contract=contract, primary=primary
    )
    return AX.build_excel_adapter(
        definitions=definitions, binding=primary, direction=direction,
        baseline_representation=baseline, sibling_bindings=siblings,
    )


def _store_rows() -> list[dict[str, Any]]:
    """首行没有公司代码（真库那一行同形），第二行有。"""
    return [
        {P.ROW_IDENTITY_STORE_KEY: ROW_A, "seq": 1, "customerName": "甲公司",
         "priorUnadjusted": 1000.0},
        {P.ROW_IDENTITY_STORE_KEY: ROW_B, "seq": 2, "customerName": "乙公司",
         "companyCode": "C002", "priorUnadjusted": 2000.0},
    ]


def _publish(contract: Any, staged: Any, out: Path) -> None:
    html = _adapter(contract, staged, direction="html_to_oo")
    store_projection = F._store_projection_for_provider(
        provider=P,
        store_payload={P.STORE_ITEM_ID: json.dumps(_store_rows(), ensure_ascii=False)},
        contract=contract,
    )
    projection = F._overlay_store_on_substrate_baseline(
        adapter=html, contract=contract, substrate=staged.staged_path,
        store_projection=store_projection,
    )
    html.materialize(
        substrate=staged.staged_path, projection=projection, output=out, contract=contract
    )


def _sheet_part(zf: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = zf.read("xl/workbook.xml").decode("utf-8")
    rid = re.search(rf'<sheet\b[^>]*\bname="{re.escape(sheet_name)}"[^>]*\br:id="([^"]+)"', workbook)
    assert rid, sheet_name
    rels = zf.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    target = re.search(rf'<Relationship\b[^>]*\bId="{rid.group(1)}"[^>]*\bTarget="([^"]+)"', rels)
    if target is None:
        target = re.search(rf'<Relationship\b[^>]*\bTarget="([^"]+)"[^>]*\bId="{rid.group(1)}"', rels)
    assert target, rid.group(1)
    path = target.group(1).lstrip("/")
    return path if path.startswith("xl/") else f"xl/{path}"


def _write_number(src: Path, dst: Path, *, coord: str, number: int) -> None:
    """像 OO 那样把 `coord` 存成数值格（`<v>` 无 `t`），其余部件逐字节不动。"""
    with zipfile.ZipFile(src) as zin:
        part = _sheet_part(zin, P.MANAGED_SHEET)
        xml = zin.read(part).decode("utf-8")
        cell = re.compile(rf'<c r="{coord}"(?P<attrs>[^>]*?)(?:/>|>.*?</c>)', re.S).search(xml)
        if cell is not None:
            attrs = re.sub(r'\s+t="[^"]*"', "", cell.group("attrs"))
            xml = f'{xml[:cell.start()]}<c r="{coord}"{attrs}><v>{number}</v></c>{xml[cell.end():]}'
        else:
            column, row = re.fullmatch(r"([A-Z]+)(\d+)", coord).groups()
            prev = f"{chr(ord(column) - 1)}{row}"
            before = re.compile(rf'<c r="{prev}"[^>]*?(?:/>|>.*?</c>)', re.S).search(xml)
            assert before is not None, prev
            xml = f'{xml[:before.end()]}<c r="{coord}"><v>{number}</v></c>{xml[before.end():]}'
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = xml.encode("utf-8") if item.filename == part else zin.read(item.filename)
                zout.writestr(item, data)


def _row_of(path: Path, identity: str) -> int:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(path.read_bytes()), read_only=True, data_only=False)
    try:
        ws = wb[P.MANAGED_SHEET]
        for row in range(13, 60):
            if ws[f"{P.UUID_COL}{row}"].value == identity:
                return row
    finally:
        wb.close()
    raise AssertionError(f"{identity} 不在 {P.MANAGED_SHEET}")


def _cell(path: Path, coord: str) -> Any:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(path.read_bytes()), read_only=True, data_only=False)
    try:
        return wb[P.MANAGED_SHEET][coord].value
    finally:
        wb.close()


def test_every_extract_call_site_passes_the_substrate_role(
    contract: Any, staged: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """三个 `_collect_fields` 调用点（动态区的静态块 / 行域、静态区 binding）都按形态传开关：
    incoming 全是 True，已发布全是 False。D2 的 D2-1 是静态区 binding，D2-2 / D2-3 是行域。"""
    published = tmp_path / "published.xlsx"
    _publish(contract, staged, published)
    calls: list[tuple[str, bool, bool]] = []
    real = X._collect_fields

    def _spy(**kwargs: Any) -> None:
        calls.append((kwargs["table"].table_key, bool(kwargs["row_identity"]),
                      kwargs.get("numbers_as_typed_text", False)))
        real(**kwargs)

    monkeypatch.setattr(X, "_collect_fields", _spy)
    oo = _adapter(contract, staged, direction="oo_to_html", baseline=published)
    oo.extract(artifact=published, contract=contract)
    published_calls, calls[:] = list(calls), []
    incoming = tmp_path / "incoming.xlsx"
    incoming.write_bytes(published.read_bytes())
    oo.extract(artifact=incoming, contract=contract)
    assert {flag for *_, flag in published_calls} == {False}
    assert {flag for *_, flag in calls} == {True}
    tables = {(table, row_scoped) for table, row_scoped, _ in calls}
    assert ("adjudication_cells", False) in tables, "静态区 binding（D2-1）走到了"
    assert (_T, True) in tables, "行域走到了"


def test_number_typed_into_company_code_survives_the_oo_save(
    contract: Any, staged: Any, tmp_path: Path
) -> None:
    published = tmp_path / "published.xlsx"
    _publish(contract, staged, published)
    row = _row_of(published, ROW_A)
    coord = f"C{row}"
    assert _cell(published, coord) in (None, ""), "前置：首行没有公司代码"

    incoming = tmp_path / "incoming.xlsx"
    _write_number(published, incoming, coord=coord, number=231)
    assert _cell(incoming, coord) == 231, "前置：OO 侧存成数值"

    oo = _adapter(contract, staged, direction="oo_to_html", baseline=published)
    base = oo.extract(artifact=published, contract=contract)
    key = P.stable_key_for("company_code", ROW_A)
    assert base.get(key) is None, "前置：base / current 都没有这个字段（真库同形）"
    got = oo.extract(artifact=incoming, contract=contract)
    assert got.get(key).value == "231"
    # 同一个文件按已发布形态读（HTML→OO adapter）仍是严格的数值，不转换。
    strict = _adapter(contract, staged, direction="html_to_oo", inventory_from=published)
    assert strict.extract(artifact=incoming, contract=contract).get(key).value == 231

    merge = merge_projections(base=base, current=base, incoming=got, contract=contract)
    assert merge.conflicts.records == ()
    assert merge.verdicts[key] is FieldVerdict.took_incoming
    assert merge.merged.get(key).value == "231"

    out = tmp_path / "rematerialized.xlsx"
    result = oo.materialize(substrate=incoming, projection=merge.merged, output=out, contract=contract)
    retired = tuple(result.retired_row_identities or ())
    extracted = (
        oo.extract(artifact=out, contract=contract, retired_row_identities=retired)
        if retired else oo.extract(artifact=out, contract=contract)
    )
    assert_roundtrip_equivalent(intended=merge.merged, extracted=extracted, contract=contract)
    oo.verify_unmanaged_regions(
        before=incoming, after=out, contract=contract, row_shift=result.row_shift,
        total_formula_rows=result.total_formula_rows, propagation=result.workbook_row_change,
        per_table_shift=result.per_table_shift,
    ).assert_equivalent()
    assert _cell(out, coord) == "231", "落盘为文本格"
    assert extracted.get(P.stable_key_for("company_code", ROW_B)).value == "C002"


# ═══════════════════════════════════════════════════════════════════════════
# 4. merge：base / current 都没有的字段，incoming 读不懂 ⇒ schema 冲突
# ═══════════════════════════════════════════════════════════════════════════


def _fv(column_key: str, row: str, value: Any, value_type: ValueType) -> FieldValue:
    key = P.stable_key_for(column_key, row)
    return FieldValue(
        stable_key=key, value=value, value_type=value_type, mode=FieldMode.editable, row_key=row
    )


def _projection(contract: Any, *fields: FieldValue) -> Projection:
    rows: list[str] = []
    for fv in fields:
        if fv.row_key and fv.row_key not in rows:
            rows.append(fv.row_key)
    return Projection(
        contract_id=contract.contract_id, semantic_version=contract.semantic_version,
        document_type=contract.document_type, values={fv.stable_key: fv for fv in fields},
        row_keys={_T: tuple(rows)},
    )


def _name(row: str = ROW_A) -> FieldValue:
    return _fv("customer_name", row, "甲公司", ValueType.text)


def test_unreadable_incoming_with_no_base_or_current_becomes_a_schema_conflict(contract: Any) -> None:
    base = _projection(contract, _name())
    incoming = _projection(contract, _name(), _fv("prior_unadjusted", ROW_A, "abc", ValueType.amount))
    merge = merge_projections(base=base, current=base, incoming=incoming, contract=contract)
    key = P.stable_key_for("prior_unadjusted", ROW_A)
    records = merge.conflicts.records
    assert [(r.locator.stable_field_key, r.kind, r.schema_anomaly) for r in records] == [
        (key, ConflictKind.schema, SchemaAnomalyKind.type_normalization_failure)
    ]
    assert merge.verdicts[key] is FieldVerdict.conflict_schema
    assert merge.merged.get(key) is None, "不采纳 incoming，保留 current（这里是缺）"
    assert merge.merged.get(P.stable_key_for("customer_name", ROW_A)).value == "甲公司"


def test_unreadable_incoming_on_a_row_added_in_oo_is_held_too(contract: Any) -> None:
    base = _projection(contract, _name())
    incoming = _projection(
        contract, _name(), _fv("customer_name", ROW_B, "乙公司", ValueType.text),
        _fv("prior_unadjusted", ROW_B, "abc", ValueType.amount),
    )
    merge = merge_projections(base=base, current=base, incoming=incoming, contract=contract)
    assert [r.locator.stable_field_key for r in merge.conflicts.records] == [
        P.stable_key_for("prior_unadjusted", ROW_B)
    ]
    assert merge.merged.get(P.stable_key_for("customer_name", ROW_B)).value == "乙公司"


def test_readable_incoming_with_no_base_or_current_is_still_taken(contract: Any) -> None:
    base = _projection(contract, _name())
    incoming = _projection(contract, _name(), _fv("prior_unadjusted", ROW_A, 100, ValueType.amount))
    merge = merge_projections(base=base, current=base, incoming=incoming, contract=contract)
    key = P.stable_key_for("prior_unadjusted", ROW_A)
    assert merge.conflicts.records == ()
    assert merge.verdicts[key] is FieldVerdict.took_incoming
    assert merge.merged.get(key).value == 100


def test_unreadable_incoming_against_an_existing_value_is_unchanged(contract: Any) -> None:
    """base 有值时本来就会比较值并记 schema 冲突 —— R13 不改这一支。"""
    base = _projection(contract, _name(), _fv("prior_unadjusted", ROW_A, 100, ValueType.amount))
    incoming = _projection(contract, _name(), _fv("prior_unadjusted", ROW_A, "abc", ValueType.amount))
    merge = merge_projections(base=base, current=base, incoming=incoming, contract=contract)
    key = P.stable_key_for("prior_unadjusted", ROW_A)
    assert [(r.locator.stable_field_key, r.schema_anomaly) for r in merge.conflicts.records] == [
        (key, SchemaAnomalyKind.type_normalization_failure)
    ]
    assert merge.merged.get(key).value == 100
