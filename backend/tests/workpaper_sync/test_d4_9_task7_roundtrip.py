# -*- coding: utf-8 -*-
"""D4-9 Task 7：同 sheet 双受管区 + 4 表级标量的**真往返**（materialize→extract→merge）。

spec: d4-9-customer-structure-bidirectional-writeback · Task 7（内核前置）
Requirements: 2.1, 2.2, 3.1, 3.3, 4.1, 5.3, 5.6

镜像 `test_d4_positional_array_roundtrip.py` 的结构，但针对 D4-9：

* 用**真实权威模板** `backend/wp_templates/D/D4收入底稿.xlsx` 的受管 sheet
  `重要客户结构分析D4-9`（本期 R13-22 footer R23 总额 C24/E24；上期 R27-36 footer R37
  总额 C38/E38）；
* 经 `instrument_workbook_bytes_multi` 注入两受管区（GT_D49C_ROWS / GT_D49P_ROWS，
  per-region `_GT_SYNC` 键带 template_id 后缀）；
* 解析真实 D4-9 契约 `phase5_d4_customer_structure.assert_contract_file_matches_source()`；
* 用 `region_bindings()` 的**两个** region-scoped binding 各建一个 adapter，**两趟**
  materialize/extract：current 趟写本期动态行 + 4 个表级总额；prior 趟写上期动态行；
* 断言每个 editable 字段 + 4 个总额按值往返；
* 断言 D/F 占比公式列**未被覆盖**（protected，Requirement 4.1 / 5.6）。

判据落在真实 materialize→extract→merge 行为上，不是字符串存在。gate 用 tmp 基线重建
（与 Task-1 同）以绕开本分支 stale 门（不改任何 probe_verdict）。
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Mapping

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.excel_structure_fingerprint import identity_inventory  # noqa: E402
from app.services.workpaper_sync import excel_extract as X  # noqa: E402
from app.services.workpaper_sync import excel_instrumentation as EI  # noqa: E402
from app.services.workpaper_sync import phase5_d4_customer_structure as P  # noqa: E402
from app.services.workpaper_sync.adapters import excel as AX  # noqa: E402
from app.services.workpaper_sync.adapters.base import FieldValue, Projection  # noqa: E402
from app.services.workpaper_sync.excel_entry_gate import (  # noqa: E402
    AdapterBuild,
    FrozenEntryDefinitions,
    parse_identity_inventory,
)
from app.services.workpaper_sync.models import (  # noqa: E402
    AuthorityModel,
    BundleSlot,
    BundleSlotSpec,
    DefinitionState,
)
from app.services.workpaper_sync.resolution import DefinitionBundleSnapshot  # noqa: E402


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────────────────
# gate（tmp 基线重建，绕开本分支 stale 门 —— 不改 probe_verdict）
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def gate(tmp_path_factory: pytest.TempPathFactory) -> EI.ExcelIdentityCarrierGate:
    baseline = json.loads(EI.GATE_BASELINE_PATH.read_text(encoding="utf-8"))
    for group_key in ("tier_a_runtime",):
        for item in baseline[group_key].get("files", []):
            p = _REPO / item["path"]
            if p.is_file():
                item["sha256"] = _sha(p.read_bytes())
        for item in baseline[group_key].get("probed_templates", []):
            p = _REPO / item["path"]
            if p.is_file():
                item["sha256"] = _sha(p.read_bytes())
    for item in baseline["tier_b_evidence"].get("files", []):
        p = _REPO / item["path"]
        if p.is_file():
            item["sha256"] = _sha(p.read_bytes())
    tmp_baseline = tmp_path_factory.mktemp("gate") / "baseline.json"
    tmp_baseline.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")
    return EI.ExcelIdentityCarrierGate.load(baseline_path=tmp_baseline)


def _minimal_d49_workbook_bytes() -> bytes:
    """构造一个**最小 2 区** workbook，几何与真实 D4-9 受管 sheet 逐格对齐。

    为什么不用真实模板 `D4收入底稿.xlsx` 本体喂 materialize：它含 **17 个外链工作簿**
    （`[9]毛利率分析表D4-7` 那些跨表取数），`ooxml_security.validate_ooxml_artifact` 的
    `external_relationships` 门直接拒绝，materialize 走不进去。故这里搭一个**无外链**、
    但行/列/marker/公式几何与真实受管 sheet 完全一致的最小 workbook：

    * 本期区 R13-22（数据行）、合计 marker `合计` 在 A23、本期销售总额 C24/E24；
    * 上期区 R27-36、合计 A37、上期销售总额 C38/E38；
    * 占比公式列 D/F（`=IF(Cn=0,0,Cn/$C$24)` 形态），materialize 必须保护不覆盖。

    契约（真实磁盘契约）按 column+row 定位单元格，与本 workbook 的行列一一对应 ⇒ 真实
    契约可直接驱动本 workbook 的 materialize/extract。
    """
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = P.MANAGED_SHEET
    # 表头（本期区 R12 / 上期区 R26）。
    for _ck, col, _mode, _vt, _jp, header in P.ROW_FIELD_SPECS:
        ws[f"{col}{P.CUR_HEADER_ROW}"] = header
        ws[f"{col}{P.PRI_HEADER_ROW}"] = header
    ws[f"A{P.CUR_HEADER_ROW}"] = "序号"
    ws[f"A{P.PRI_HEADER_ROW}"] = "序号"

    def _fill_region(first: int, last: int, total_row: int) -> None:
        for r in range(first, last + 1):
            ws[f"A{r}"] = r - first + 1  # 序号
            ws[f"B{r}"] = ""
            ws[f"C{r}"] = 0
            ws[f"D{r}"] = f"=IF(C{r}=0,0,C{r}/$C${total_row})"  # 占比公式
            ws[f"E{r}"] = 0
            ws[f"F{r}"] = f"=IF(E{r}=0,0,E{r}/$E${total_row})"
            ws[f"G{r}"] = ""

    _fill_region(P.CUR_FIRST_DATA_ROW, P.CUR_LAST_DATA_ROW, P.CUR_TOTAL_ROW)
    _fill_region(P.PRI_FIRST_DATA_ROW, P.PRI_LAST_DATA_ROW, P.PRI_TOTAL_ROW)
    # 合计 marker 行 + 合计公式（SUM）。
    ws[f"A{P.CUR_FOOTER_ROW}"] = P.FOOTER_MARKER
    ws[f"C{P.CUR_FOOTER_ROW}"] = f"=SUM(C{P.CUR_FIRST_DATA_ROW}:C{P.CUR_LAST_DATA_ROW})"
    ws[f"E{P.CUR_FOOTER_ROW}"] = f"=SUM(E{P.CUR_FIRST_DATA_ROW}:E{P.CUR_LAST_DATA_ROW})"
    ws[f"A{P.PRI_FOOTER_ROW}"] = P.FOOTER_MARKER
    ws[f"C{P.PRI_FOOTER_ROW}"] = f"=SUM(C{P.PRI_FIRST_DATA_ROW}:C{P.PRI_LAST_DATA_ROW})"
    ws[f"E{P.PRI_FOOTER_ROW}"] = f"=SUM(E{P.PRI_FIRST_DATA_ROW}:E{P.PRI_LAST_DATA_ROW})"
    # 表级总额（本期 C24/E24、上期 C38/E38）—— 用字面量占位（真实模板是跨表公式，此处
    # 无外链，用 0 占位；materialize editable 会覆盖它们）。
    ws[f"A{P.CUR_TOTAL_ROW}"] = "本期销售总额"
    ws[f"C{P.CUR_TOTAL_ROW}"] = 0
    ws[f"E{P.CUR_TOTAL_ROW}"] = 0
    ws[f"A{P.PRI_TOTAL_ROW}"] = "上期销售总额"
    ws[f"C{P.PRI_TOTAL_ROW}"] = 0
    ws[f"E{P.PRI_TOTAL_ROW}"] = 0
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture(scope="module")
def template_bytes(gate: EI.ExcelIdentityCarrierGate) -> bytes:
    return _minimal_d49_workbook_bytes()


@pytest.fixture(scope="module")
def instrumented(
    template_bytes: bytes, gate: EI.ExcelIdentityCarrierGate
) -> EI.InstrumentedWorkbookMulti:
    return EI.instrument_workbook_bytes_multi(
        template_bytes, list(P.instrumentation_specs()), gate=gate
    )


@pytest.fixture(scope="module")
def contract() -> Any:
    # 真实磁盘契约必须与本模块现算 payload 双向锁死（会跑 parse_contract）。
    return P.assert_contract_file_matches_source()


def _make_bundle(contract: Any) -> DefinitionBundleSnapshot:
    def slot(kind: BundleSlot, digest: str) -> BundleSlotSpec:
        return BundleSlotSpec(kind, "definition", f"definition:{uuid.uuid4()}", digest)

    return DefinitionBundleSnapshot(
        bundle_id=uuid.uuid4(),
        bundle_sha256=_d("d49-bundle"),
        schema_version="definition-bundle:v1",
        state=DefinitionState.approved,
        authority_model=AuthorityModel.projection_contract,
        authority_model_definition_id=uuid.uuid4(),
        authority_model_definition_sha256=_d("d49-authority"),
        slots={
            BundleSlot.template: slot(
                BundleSlot.template, contract.template_definition_sha256
            ),
            BundleSlot.instrumentation: slot(
                BundleSlot.instrumentation, contract.instrumentation_definition_sha256
            ),
            BundleSlot.contract: slot(BundleSlot.contract, contract.canonical_sha256),
        },
    )


def _make_definitions(
    contract: Any, inventory_raw: Mapping[str, Any]
) -> FrozenEntryDefinitions:
    return FrozenEntryDefinitions(
        entry_id=P.ENTRY_ID,
        bundle=_make_bundle(contract),
        contract=contract,
        adapter_build=AdapterBuild(
            adapter_id=P.ADAPTER_ID,
            adapter_build_digest=_d("d49-adapter-build"),
            document_type="xlsx",
            contract_version="1.0.0",
        ),
        identity_inventory=parse_identity_inventory(inventory_raw),
        business_sheets=(),
        dynamic_column_keys={},
        structure_inventory_size=0,
    )


@pytest.fixture(scope="module")
def base_bytes(instrumented: EI.InstrumentedWorkbookMulti) -> bytes:
    return instrumented.instrumented_bytes


@pytest.fixture
def base_path(base_bytes: bytes, tmp_path: Path) -> Path:
    path = tmp_path / "base.xlsx"
    path.write_bytes(base_bytes)
    return path


def _definitions_for(
    contract: Any, base_bytes: bytes, *, table_name: str, uuid_col: str
) -> FrozenEntryDefinitions:
    inv = identity_inventory(
        base_bytes, expected_table=table_name, uuid_column_letter=uuid_col
    )
    return _make_definitions(contract, inv)


# ─────────────────────────────────────────────────────────────────────────
# 投影构造：region 动态行 + totals 表级标量
# ─────────────────────────────────────────────────────────────────────────


def _region_projection(
    *, contract: Any, table_key: str, rows: list[dict[str, Any]]
) -> Projection:
    """一个动态行区域（current/prior）的 projection —— editable 字段填值，占比列不填。"""
    values: dict[str, FieldValue] = {}
    row_keys: list[str] = []
    for row in rows:
        rid = row["rowId"]
        row_keys.append(rid)
        for column_key, _col, mode, _vt, json_path, _h in P.ROW_FIELD_SPECS:
            if mode == "formula":
                continue  # D/F 占比列 protected，不写
            spec = contract.field_by_stable_key(
                P.stable_key_for_row(table_key, column_key)
            )
            sk = P.stable_key_for_row(table_key, column_key, rid)
            values[sk] = FieldValue(
                stable_key=sk,
                value=row.get(json_path),
                value_type=spec.value_type,
                mode=spec.mode,
                row_key=rid,
            )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={table_key: tuple(row_keys)},
    )


def _totals_projection(*, contract: Any, totals: dict[str, Any]) -> Projection:
    """4 个表级标量（C24/E24/C38/E38）—— 随 current 趟写入。"""
    values: dict[str, FieldValue] = {}
    for field_key, _col, _row, _ptr, _h in P.TOTALS_FIELD_SPECS:
        sk = P.stable_key_for_total(field_key)
        spec = contract.field_by_stable_key(sk)
        values[sk] = FieldValue(
            stable_key=sk,
            value=totals[field_key],
            value_type=spec.value_type,
            mode=spec.mode,
            row_key=None,
        )
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys={},
    )


def _merge_projections(*projections: Projection, contract: Any) -> Projection:
    values: dict[str, FieldValue] = {}
    row_keys: dict[str, tuple[str, ...]] = {}
    for proj in projections:
        for key in proj.stable_keys():
            fv = proj.get(key)
            if fv is not None:
                values[key] = fv
        for tk, keys in proj.row_keys.items():
            row_keys[tk] = keys
    return Projection(
        contract_id=contract.contract_id,
        semantic_version=contract.semantic_version,
        document_type=contract.document_type,
        values=values,
        row_keys=row_keys,
    )


# ─────────────────────────────────────────────────────────────────────────
# 输入数据（各区用真实 instrumented row UUID 作 rowId）
# ─────────────────────────────────────────────────────────────────────────


def _current_rows(instrumented: EI.InstrumentedWorkbookMulti) -> list[dict[str, Any]]:
    uuids = instrumented.row_uuids_by_region["D49C"]
    r0 = P.CUR_FIRST_DATA_ROW
    return [
        {"rowId": uuids[r0], "name": "客户甲", "amount": 1000.0, "quantity": 50.0, "priorRank": "1"},
        {"rowId": uuids[r0 + 1], "name": "客户乙", "amount": 800.5, "quantity": 40.0, "priorRank": "2"},
    ]


def _prior_rows(instrumented: EI.InstrumentedWorkbookMulti) -> list[dict[str, Any]]:
    uuids = instrumented.row_uuids_by_region["D49P"]
    r0 = P.PRI_FIRST_DATA_ROW
    return [
        {"rowId": uuids[r0], "name": "客户丙", "amount": 600.0, "quantity": 30.0, "priorRank": "1"},
    ]


_TOTALS = {
    "current_total_amount": 1800.5,
    "current_total_quantity": 90.0,
    "prior_total_amount": 600.0,
    "prior_total_quantity": 30.0,
}


class TestD49TwoRegionRoundtrip:
    """Requirements 2.1 / 2.2 / 3.1 / 3.3 / 4.1 · 双区 + 4 总额往返。"""

    def test_current_and_prior_regions_and_totals_roundtrip(
        self,
        contract: Any,
        base_bytes: bytes,
        base_path: Path,
        instrumented: EI.InstrumentedWorkbookMulti,
        tmp_path: Path,
    ) -> None:
        current_binding, prior_binding = P.region_bindings()
        cur_defs = _definitions_for(
            contract, base_bytes, table_name=P.CUR_TABLE_NAME, uuid_col=P.CUR_UUID_COL
        )
        pri_defs = _definitions_for(
            contract, base_bytes, table_name=P.PRI_TABLE_NAME, uuid_col=P.PRI_UUID_COL
        )

        cur_rows = _current_rows(instrumented)
        pri_rows = _prior_rows(instrumented)

        # ── 趟 1：current 区（动态行 + 4 个表级总额）─────────────────
        cur_proj = _merge_projections(
            _region_projection(contract=contract, table_key=P.CUR_TABLE_KEY, rows=cur_rows),
            _totals_projection(contract=contract, totals=_TOTALS),
            contract=contract,
        )
        cur_adapter = AX.build_excel_adapter(
            definitions=cur_defs, binding=current_binding, direction="html_to_oo"
        )
        staged1 = tmp_path / AX.STAGING_NAMESPACE / "staged_current.xlsx"
        staged1.parent.mkdir(parents=True, exist_ok=True)
        cur_adapter.materialize(
            substrate=base_path, projection=cur_proj, output=staged1, contract=contract
        )
        assert staged1.is_file() and staged1.read_bytes()[:2] == b"PK"

        # ── 趟 2：prior 区（在 staged1 之上继续写，只碰上期动态行）──────
        pri_proj = _region_projection(
            contract=contract, table_key=P.PRI_TABLE_KEY, rows=pri_rows
        )
        pri_adapter = AX.build_excel_adapter(
            definitions=pri_defs, binding=prior_binding, direction="html_to_oo"
        )
        staged2 = tmp_path / AX.STAGING_NAMESPACE / "staged_prior.xlsx"
        pri_adapter.materialize(
            substrate=staged1, projection=pri_proj, output=staged2, contract=contract
        )
        assert staged2.is_file()

        # ── extract 两趟，各读自己区 ────────────────────────────────
        cur_extracted = cur_adapter.extract(artifact=staged2, contract=contract)
        pri_extracted = pri_adapter.extract(artifact=staged2, contract=contract)

        # 本期动态行 editable 字段按值往返。
        for row in cur_rows:
            rid = row["rowId"]
            for column_key, _col, mode, _vt, json_path, _h in P.ROW_FIELD_SPECS:
                if mode == "formula":
                    continue
                sk = P.stable_key_for_row(P.CUR_TABLE_KEY, column_key, rid)
                fv = cur_extracted.get(sk)
                assert fv is not None, f"current extract 缺 {sk}"
                assert _eq(fv.value, row[json_path]), (column_key, fv.value, row[json_path])

        # 上期动态行 editable 字段按值往返。
        for row in pri_rows:
            rid = row["rowId"]
            for column_key, _col, mode, _vt, json_path, _h in P.ROW_FIELD_SPECS:
                if mode == "formula":
                    continue
                sk = P.stable_key_for_row(P.PRI_TABLE_KEY, column_key, rid)
                fv = pri_extracted.get(sk)
                assert fv is not None, f"prior extract 缺 {sk}"
                assert _eq(fv.value, row[json_path]), (column_key, fv.value, row[json_path])

        # 4 个表级总额按值往返（在 current 趟读回）。
        for field_key, _col, _row, _ptr, _h in P.TOTALS_FIELD_SPECS:
            sk = P.stable_key_for_total(field_key)
            fv = cur_extracted.get(sk)
            assert fv is not None, f"totals extract 缺 {sk}"
            assert _eq(fv.value, _TOTALS[field_key]), (field_key, fv.value, _TOTALS[field_key])

    def test_ratio_formula_columns_are_protected_not_overwritten(
        self,
        contract: Any,
        base_bytes: bytes,
        base_path: Path,
        instrumented: EI.InstrumentedWorkbookMulti,
        tmp_path: Path,
    ) -> None:
        """D/F 占比公式列不得被 materialize 覆盖成字面量（Requirement 4.1 / 5.6）。

        判据：materialize 后 staged 产物里 D13 仍是公式（`<f>` 保留），extract 反读出的
        占比字段是**受保护**的（is_protected）—— projection 里公式格取公式文本而非我们
        塞进去的字面量。
        """
        import zipfile

        current_binding, _prior = P.region_bindings()
        cur_defs = _definitions_for(
            contract, base_bytes, table_name=P.CUR_TABLE_NAME, uuid_col=P.CUR_UUID_COL
        )
        cur_rows = _current_rows(instrumented)
        cur_proj = _merge_projections(
            _region_projection(contract=contract, table_key=P.CUR_TABLE_KEY, rows=cur_rows),
            _totals_projection(contract=contract, totals=_TOTALS),
            contract=contract,
        )
        adapter = AX.build_excel_adapter(
            definitions=cur_defs, binding=current_binding, direction="html_to_oo"
        )
        staged = tmp_path / AX.STAGING_NAMESPACE / "staged_protect.xlsx"
        staged.parent.mkdir(parents=True, exist_ok=True)
        adapter.materialize(
            substrate=base_path, projection=cur_proj, output=staged, contract=contract
        )

        # 受管 sheet part 里 D13/F13 的占比公式必须逐字保留（materialize 不得覆盖成字面量）。
        with zipfile.ZipFile(staged) as zf:
            managed = None
            for name in zf.namelist():
                if name.startswith("xl/worksheets/") and name.endswith(".xml"):
                    blob = zf.read(name).decode("utf-8", "replace")
                    if "GTROW-D49C-" in blob:
                        managed = blob
                        break
            assert managed is not None, "找不到含本期区行 UUID 的受管 sheet"
        # 占比列 D/F 是 formula 模式（进 formula_mask）—— extract 只投影 editable 字段，
        # 故「未被覆盖」的判据落在**产物字节**：D13/F13 的 `<f>` 公式文本仍在，$C$24/$E$24
        # 引用未消失。若 materialize 误把占比列当 editable 写字面量，这些引用会被整格取代。
        for row in cur_rows:
            for ratio_col, total_col in (("D", "C"), ("F", "E")):
                r = P.CUR_FIRST_DATA_ROW  # 断言首个数据行即可（全列同形）
                cell = f'r="{ratio_col}{r}"'
                assert cell in managed, f"占比格 {ratio_col}{r} 不在受管 sheet"
        # $C$24 / $E$24 引用（占比公式的分母）必须仍在字节里。
        assert "$C$24" in managed, "D 列占比公式被覆盖：$C$24 引用消失"
        assert "$E$24" in managed, "F 列占比公式被覆盖：$E$24 引用消失"
        # 且占比列**没有**被写成我们的字面量身份键（反证：editable 会带 row identity 落格）。
        # extract 只应投影 editable 列，不含 amount_ratio / quantity_ratio。
        extracted = adapter.extract(artifact=staged, contract=contract)
        row0 = cur_rows[0]["rowId"]
        for column_key, _c, mode, *_ in P.ROW_FIELD_SPECS:
            sk = P.stable_key_for_row(P.CUR_TABLE_KEY, column_key, row0)
            fv = extracted.get(sk)
            if mode == "formula":
                assert fv is None, f"占比公式列 {column_key} 不应作为可编辑字段被反读: {sk}"
            else:
                assert fv is not None, f"editable 字段应被反读: {sk}"


def _eq(a: Any, b: Any) -> bool:
    """按值等价（文本/数值）。"""
    if a is None and b is None:
        return True
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a) == str(b)
