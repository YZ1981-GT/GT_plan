import io
from pathlib import Path

import pytest
from openpyxl import load_workbook
from app.services.workpaper_sync import phase5_d4_29_customer_detail as d
from app.services.workpaper_sync.contracts import load_contract


@pytest.fixture
def contract():
    return load_contract('d4.revenue_detail')


@pytest.fixture
def template():
    return Path('backend/wp_templates/D/D4 收入底稿.xlsx').read_bytes()


def customers(count=12):
    return [{'id': f'id{i}', 'name': f'客户{i}', 'fields': {k: f'{k}-{i}' for k in d.FIELD_KEYS}} for i in range(count)]


def test_contract_and_frozen_digest(contract, monkeypatch):
    assert d.assert_mapping_digest()
    expected = d.sheet_payload()
    actual = next(s for s in contract.canonical_payload['sheets'] if s['sheet_key'] == d.SHEET_KEY)
    assert actual['sheet_key'] == expected['sheet_key']
    assert actual['excel_name'] == expected['excel_name']
    assert actual['tables'] == expected['tables']
    from app.services.workpaper_sync import phase5_d4_revenue_detail as provider
    assert contract.instrumentation_definition_sha256 == provider.build_contract_payload()['instrumentation_definition_sha256']
    monkeypatch.setitem(d.FIELD_ROWS, 'chairman', 27)
    with pytest.raises(ValueError, match='drift'):
        d.assert_mapping_digest()


def test_projection_merge_add_delete_rename(contract):
    payload = customers(2)
    payload[0]['name'] = '改名'
    projection = d.build_store_projection(payload, contract=contract)
    projection.assert_matches_contract(contract)
    merged, applied, _, removed = d.merge_projection_into_store(projection=projection, base_payload=customers(3))
    assert merged == payload
    assert removed == {'id2'} and applied > 0
    empty = d.build_store_projection([], contract=contract)
    merged, applied, _, removed = d.merge_projection_into_store(projection=empty, base_payload=payload)
    assert merged == [] and applied > 0 and removed == {'id0', 'id1'}


def test_source_mapping_and_12_customer_roundtrip(template, contract):
    original = load_workbook(io.BytesIO(template))[d.MANAGED_SHEET]
    data = d.materialize_transposed_workbook(template, customers())
    ws = load_workbook(io.BytesIO(data))[d.MANAGED_SHEET]
    assert ws['N10'].value == '客户11'
    assert ws['N9'].value == d.IDENTITY_CARRIER_PREFIX + 'id11'
    assert ws.row_dimensions[9].hidden
    assert ws['C28'].value == 'chairman-0'
    assert ws['C34'].value == 'actualController-0'
    assert ws['C41'].value == 'infoSource-0'
    assert ws.column_dimensions['N'].width == original.column_dimensions['M'].width
    assert ws['N28']._style == ws['M28']._style
    for row in original.iter_rows(min_row=42):
        for cell in row:
            assert ws[cell.coordinate].value == cell.value
            assert ws[cell.coordinate]._style == cell._style
    assert set(map(str, original.merged_cells.ranges)) <= set(map(str, ws.merged_cells.ranges))
    assert d.extract_transposed_workbook(data) == customers()
    projection = d.build_store_projection(d.extract_transposed_workbook(data), contract=contract)
    assert len(projection.row_keys[d.TABLE_KEY]) == 12


def test_delete_rename_and_expand_again(template):
    full = d.materialize_transposed_workbook(template, customers())
    remaining = [customers()[11], customers()[0]]
    remaining[0]['name'] = '同名客户'
    remaining[1]['name'] = '同名客户'
    reduced = d.materialize_transposed_workbook(full, remaining)
    assert d.extract_transposed_workbook(reduced) == remaining
    ws = load_workbook(io.BytesIO(reduced))[d.MANAGED_SHEET]
    assert ws['N9'].value is None and ws['N10'].value is None
    assert d.extract_transposed_workbook(d.materialize_transposed_workbook(reduced, [])) == []
    assert len(d.extract_transposed_workbook(d.materialize_transposed_workbook(reduced, customers(14)))) == 14


def test_dispatcher_files(template, contract, tmp_path):
    artifact = tmp_path / 'workbook.xlsx'
    artifact.write_bytes(template)
    d.materialize_file(artifact, d.build_store_projection(customers(), contract=contract), contract)
    projection = d.extract_file(artifact, contract)
    merged, _, _, _ = d.merge_projection_into_store(projection=projection, base_payload=[])
    assert merged == customers()


def test_invalid_duplicate_identity(template):
    with pytest.raises(ValueError, match='unique'):
        d.materialize_transposed_workbook(template, customers(1) * 2)


def test_production_adapter_dispatch(template, contract, tmp_path, monkeypatch):
    import shutil
    from dataclasses import dataclass
    from types import SimpleNamespace
    from app.services.workpaper_sync.adapters import excel
    from app.services.workpaper_sync.adapters.base import SubstrateRole
    from app.services.workpaper_sync.models import ArtifactKind, ArtifactState

    @dataclass
    class Result:
        artifact_sha256: str = ''
        structure_hash: str = ''

    def generic_materialize(**kwargs):
        shutil.copyfile(kwargs['substrate'], kwargs['output'])
        return SimpleNamespace(result=Result())

    monkeypatch.setattr(excel, 'materialize_projection', generic_materialize)
    empty = d.build_store_projection([], contract=contract)
    monkeypatch.setattr(excel, 'extract_projection', lambda **kw: SimpleNamespace(projection=empty))
    class Host:
        adapter_id = 'd4.revenue_detail'
        baseline_representation = None
        substrate_kind = ArtifactKind.canonical
        substrate_role = SubstrateRole.published_representation
        substrate_state = ArtifactState.published
        capability = None
        definitions = None
        _limits = None
        binding = SimpleNamespace(table_key='primary')
        def _assert_same_contract(self, *a, **kw): pass
        def _all_bindings(self): return (self.binding,)
        def _baseline_pair(self): return None, None
        def _substrate_shape_of(self, artifact):
            return self.substrate_role, self.substrate_kind, self.substrate_state
        def _merge_projections(self, parts): return parts[-1]
    source, output = tmp_path / 'source.xlsx', tmp_path / 'output.xlsx'
    source.write_bytes(template)
    host = Host()
    excel.ExcelSyncAdapter.materialize(host, substrate=source, output=output,
        projection=d.build_store_projection(customers(), contract=contract), contract=contract)
    projection = excel.ExcelSyncAdapter.extract(host, artifact=output, contract=contract)
    assert len(projection.row_keys[d.TABLE_KEY]) == 12
    assert projection.get(d.stable_key_for('id11', 'name')).value == '客户11'
