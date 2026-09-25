"""同 sheet 兄弟 Table 的 ref 必须随插行下移 —— 否则下一趟 extract 读到错位区域。

Bug: D4-1 切「在线编辑」恒 500 `excel_extract_identity_carrier_missing`
真栈复现：project `0ec33ac9…` / wp `b3ab3c46…` / entry `xlsx/gt-d4-operating-revenue`

═══ 根因（已逐层实证，不是推断）═══

1. D4-1 审定表在**同一张 sheet** 上有两个受管区：
   主营 `GT_D41_MAIN_ROWS`（W 列，Table ref `A7:W11`）/ 其他 `GT_D41_OTHER_ROWS`（X 列，`A14:X17`）。
2. 主营段现在要落 7 个派生行，而模板数据区只有 4 行 ⇒ **需要结构性插行**。
3. 「任一 binding 需插行」会让 `_try_single_pass_materialize` **decline**，回落**逐趟链式**
   路径（`adapters/excel.py`：`current = target`，上一趟产物当下一趟 substrate）。
4. 主营那一趟插行后，`excel_materialize._grow_managed_table_ref` 只更新
   **`plan.table_part`** 一个 Table part（本 binding 的）。同 sheet 位于插入点**下方**的
   兄弟 Table（其他区）ref 逐字不动 ⇒ 数据行下移了、ref 还指 `A14:X17`。
5. 其他区那一趟对该产物 extract：按旧 ref 读 14..17，那里已经是主营区的新行，X 列无 UUID
   ⇒ `resolved_sheet_by=None` ⇒ `assert_identity_carriers_usable` 抛
   `IdentityCarrierMissingError`。

   真栈实测（钩住载体门打印每次 inventory）：
   `载体门失败于第 42 次调用：sheet='营业收入审定表D4-1' table_ref='A14:X17' uuid_col='X'
    uuids=0 resolved_by=None empty_rows=4`

🔴 **错误文案有误导性**：它报的是 `dynamic_tables[0]`（契约里第一张动态表 =
`d42-managed/revenue_detail_rows`），与真正失败的 binding 无关 —— 于是现场看起来像"D4-2 坏了"。
本文件的判据直接钉住兄弟 Table 的 ref，不依赖那句文案。

═══ 影响面（不止 D4-1）═══

同 sheet 多受管区 + 上区插行的组合全部中招。D4 内实测同 sheet 多区的有：
D4-1（主营/其他）、D4-9（本期/上期）、D4-20（三区）、D4-34（租金/咨询）、D4-36（顺查/逆查）。
"""
from __future__ import annotations

import hashlib
import io
import os
import sys
import uuid
import warnings
from pathlib import Path
from typing import Any, Mapping

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")
warnings.filterwarnings("ignore")

from app.services.excel_structure_fingerprint import identity_inventory  # noqa: E402
from app.services.workpaper_sync import excel_extract as EE  # noqa: E402
from app.services.workpaper_sync import excel_instrumentation as EI  # noqa: E402
from app.services.workpaper_sync import phase5_d4_adjudication_sheet as A  # noqa: E402
from app.services.workpaper_sync import phase5_d4_revenue_detail as D4  # noqa: E402
from app.services.workpaper_sync.adapters import excel as AX  # noqa: E402
from app.services.workpaper_sync.contracts import parse_contract  # noqa: E402
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

#: 主营段要落的派生行数（> 模板 4 行占位 ⇒ 必然触发结构性插行，这是复现的前提）。
DERIVED_MAIN_ROWS = 7
#: 其他段要落的行数（同样 > 4 行）。
DERIVED_OTHER_ROWS = 6


def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _make_definitions(contract: Any, inventory_raw: Mapping[str, Any]) -> FrozenEntryDefinitions:
    def slot(kind: BundleSlot, digest: str) -> BundleSlotSpec:
        return BundleSlotSpec(kind, "definition", f"definition:{uuid.uuid4()}", digest)

    bundle = DefinitionBundleSnapshot(
        bundle_id=uuid.uuid4(),
        bundle_sha256=_d("sibling-ref-bundle"),
        schema_version="definition-bundle:v1",
        state=DefinitionState.approved,
        authority_model=AuthorityModel.projection_contract,
        authority_model_definition_id=uuid.uuid4(),
        authority_model_definition_sha256=_d("sibling-ref-authority"),
        slots={
            BundleSlot.template: slot(BundleSlot.template, contract.template_definition_sha256),
            BundleSlot.instrumentation: slot(
                BundleSlot.instrumentation, contract.instrumentation_definition_sha256
            ),
            BundleSlot.contract: slot(BundleSlot.contract, contract.canonical_sha256),
        },
    )
    return FrozenEntryDefinitions(
        entry_id=D4.ENTRY_ID,
        bundle=bundle,
        contract=contract,
        adapter_build=AdapterBuild(
            adapter_id=D4.ADAPTER_ID,
            adapter_build_digest=_d("sibling-ref-build"),
            document_type="xlsx",
            contract_version=contract.semantic_version,
        ),
        identity_inventory=parse_identity_inventory(inventory_raw),
        business_sheets=(),
        dynamic_column_keys={},
        structure_inventory_size=0,
    )


BINDING_MAIN = EE.ExcelIdentityBinding(
    table_name=A.TABLE_NAME_MAIN, uuid_column=A.UUID_COL_MAIN, table_key=A.ROWS_TABLE_KEY_MAIN
)
BINDING_OTHER = EE.ExcelIdentityBinding(
    table_name=A.TABLE_NAME_OTHER, uuid_column=A.UUID_COL_OTHER, table_key=A.ROWS_TABLE_KEY_OTHER
)


@pytest.fixture(scope="module")
def contract() -> Any:
    return parse_contract(D4.build_contract_payload(), adapter_id=D4.ADAPTER_ID)


@pytest.fixture(scope="module")
def instrumented() -> EI.InstrumentedWorkbook:
    return EI.instrument_workbook_bytes_multi(
        D4.read_authoritative_template(), D4.instrumentation_specs(), gate=D4.excel_carrier_gate()
    )


@pytest.fixture(scope="module")
def definitions(contract: Any, instrumented: EI.InstrumentedWorkbook) -> FrozenEntryDefinitions:
    inv = identity_inventory(
        instrumented.instrumented_bytes,
        expected_table=A.TABLE_NAME_MAIN,
        uuid_column_letter=A.UUID_COL_MAIN,
    )
    return _make_definitions(contract, inv)


@pytest.fixture
def base_path(instrumented: EI.InstrumentedWorkbook, tmp_path: Path) -> Path:
    p = tmp_path / "d41-base.xlsx"
    p.write_bytes(instrumented.instrumented_bytes)
    return p


def _rows_needing_insertion() -> list[dict[str, Any]]:
    """两区各超过模板占位行数的行集 —— 落库后 materialize 必须插行。"""
    rows: list[dict[str, Any]] = []
    for i in range(DERIVED_MAIN_ROWS):
        rows.append({
            "rowId": f"xsheet-main-p{i}", "label": f"主营派生{i}", "source": "tb",
            "accountCode": "6001", A.SECTION_KEY_FIELD: A.SECTION_KEY_MAIN,
            "currentUnadjusted": 1000.0 + i, "currentAje": 0, "currentRje": 0,
            "priorUnadjusted": 0, "priorAje": 0, "priorRje": 0,
        })
    for i in range(DERIVED_OTHER_ROWS):
        rows.append({
            "rowId": f"xsheet-other-q{i}", "label": f"其他派生{i}", "source": "tb",
            "accountCode": "6051", A.SECTION_KEY_FIELD: A.SECTION_KEY_OTHER,
            "currentUnadjusted": 200.0 + i, "currentAje": 0, "currentRje": 0,
            "priorUnadjusted": 0, "priorAje": 0, "priorRje": 0,
        })
    return rows


def _table_refs(path: Path) -> dict[str, str]:
    """读产物里每个 Excel Table 的 `displayName -> ref`（真字节，不经业务代码）。"""
    import zipfile

    with zipfile.ZipFile(path) as zf:
        return {
            str(t.get("display_name") or t.get("name")): str(t.get("ref") or "")
            for t in EE._tables_of(zf)
        }


def _table_refs_from_entries(entries: Mapping[str, bytes]) -> dict[str, str]:
    """同上，但直接从 zip entries dict 读（判据 6 走 entries 级入口，不落盘）。"""
    import re as _re

    out: dict[str, str] = {}
    for name, raw in entries.items():
        if not _re.match(r"xl/tables/[^/]+\.xml$", name):
            continue
        xml = raw.decode("utf-8", errors="replace")
        disp = _re.search(r'\bdisplayName="([^"]*)"', xml) or _re.search(
            r'\bname="([^"]*)"', xml
        )
        ref = _re.search(r'<table\b[^>]*\bref="([^"]*)"', xml) or _re.search(
            r'\bref="([^"]*)"', xml
        )
        if disp and ref:
            out[disp.group(1)] = ref.group(1)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 判据 1：前提确认 —— 两区同 sheet，且主营在其他区**之上**
#         （若哪天模板改成不同 sheet 或顺序反了，本文件测的就不是原缺陷）
# ═══════════════════════════════════════════════════════════════════════════


def test_premise_two_regions_share_one_sheet_main_above_other(base_path: Path) -> None:
    refs = _table_refs(base_path)
    assert A.TABLE_NAME_MAIN in refs and A.TABLE_NAME_OTHER in refs, (
        f"两区 Table 应都在，实得 {sorted(refs)}"
    )
    assert A.MANAGED_SHEET_D41 == "营业收入审定表D4-1"
    # 主营数据区在其他区之上（8..11 vs 14..17）—— 插行发生在其他区上方是复现的必要条件。
    assert A.LAST_DATA_ROW_MAIN < A.FIRST_DATA_ROW_OTHER, (
        f"主营末行 {A.LAST_DATA_ROW_MAIN} 应在其他区首行 {A.FIRST_DATA_ROW_OTHER} 之上"
    )
    # 要落的行数超过模板占位 ⇒ 必然插行。
    template_main = A.LAST_DATA_ROW_MAIN - A.FIRST_DATA_ROW_MAIN + 1
    assert DERIVED_MAIN_ROWS > template_main, (
        f"主营要落 {DERIVED_MAIN_ROWS} 行但模板只有 {template_main} 行占位 —— 必须插行"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 判据 2（核心红判据）：上区插行后，**同 sheet 下方兄弟 Table** 的 ref 必须随之下移
# ═══════════════════════════════════════════════════════════════════════════


def test_sibling_table_ref_shifts_down_when_upper_region_inserts_rows(
    contract: Any, definitions: FrozenEntryDefinitions, base_path: Path, tmp_path: Path
) -> None:
    """只跑**主营那一趟**（单 binding materialize），断言其他区 Table ref 跟着下移。

    这是逐趟链式路径里真实发生的第一趟。修复前：其他区 ref 逐字不动（仍 `A14:X17`）⇒
    下一趟按旧 ref 读到主营新行、X 列无 UUID ⇒ IdentityCarrierMissingError。
    """
    from app.services.workpaper_sync.excel_materialize import materialize_projection

    before = _table_refs(base_path)
    other_before = before[A.TABLE_NAME_OTHER]
    main_before = before[A.TABLE_NAME_MAIN]

    proj = A.build_store_projection_d41(_rows_needing_insertion(), contract=contract)
    staged = tmp_path / AX.STAGING_NAMESPACE / "trip1-main.xlsx"
    staged.parent.mkdir(parents=True, exist_ok=True)

    outcome = materialize_projection(
        substrate=base_path,
        projection=proj,
        output=staged,
        definitions=definitions,
        binding=BINDING_MAIN,
        substrate_role="published_representation",
        substrate_kind="canonical",
        substrate_state="published",
    )
    result = outcome.result
    assert result.row_shift is not None, (
        "主营段要落 7 行而模板 4 行占位 —— 本趟必须声明结构性插行；"
        "若为 None 则本判据测的不是插行路径"
    )
    inserted = int(result.row_shift.count)
    assert inserted > 0

    after = _table_refs(staged)
    # 本区 ref 必须长（既有行为，顺带守住不回归）。
    assert after[A.TABLE_NAME_MAIN] != main_before, "主营区自己的 ref 没长"

    def _rows(ref: str) -> tuple[int, int]:
        head, tail = ref.split(":", 1)
        return (
            int("".join(ch for ch in head if ch.isdigit())),
            int("".join(ch for ch in tail if ch.isdigit())),
        )

    b_head, b_tail = _rows(other_before)
    a_head, a_tail = _rows(after[A.TABLE_NAME_OTHER])
    assert (a_head, a_tail) == (b_head + inserted, b_tail + inserted), (
        f"同 sheet 下方兄弟 Table 的 ref 没随插行下移：{other_before} → "
        f"{after[A.TABLE_NAME_OTHER]}（插了 {inserted} 行，应为 "
        f"{b_head + inserted}..{b_tail + inserted}）—— 下一趟 extract 会按旧 ref 读到"
        "上区的新行，UUID 列全空 ⇒ IdentityCarrierMissingError"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 判据 3（端到端）：两区一起走真 adapter（逐趟链式），materialize 必须整体成功
# ═══════════════════════════════════════════════════════════════════════════


def test_dual_region_materialize_survives_row_insertion(
    contract: Any, definitions: FrozenEntryDefinitions, base_path: Path, tmp_path: Path
) -> None:
    """真 adapter（primary=主营 + sibling=其他）+ 需插行的 projection ⇒ 不得抛载体缺失。

    这条就是生产 500 的最小复现：修复前抛 `IdentityCarrierMissingError`
    （文案误报契约首张表 `d42-managed/revenue_detail_rows`）。
    """
    adapter = AX.build_excel_adapter(
        definitions=definitions,
        binding=BINDING_MAIN,
        direction="html_to_oo",
        sibling_bindings=(BINDING_OTHER,),
    )
    proj = A.build_store_projection_d41(_rows_needing_insertion(), contract=contract)
    staged = tmp_path / AX.STAGING_NAMESPACE / "dual.xlsx"
    staged.parent.mkdir(parents=True, exist_ok=True)

    adapter.materialize(
        substrate=base_path, projection=proj, output=staged, contract=contract
    )
    assert staged.is_file() and staged.read_bytes()[:2] == b"PK"

    # 产物上两区都必须能反读回自己的行身份（= 载体门会放行）。
    extracted = adapter.extract(artifact=staged, contract=contract)
    main_keys = set(extracted.row_keys.get(A.ROWS_TABLE_KEY_MAIN, ()))
    other_keys = set(extracted.row_keys.get(A.ROWS_TABLE_KEY_OTHER, ()))
    for i in range(DERIVED_MAIN_ROWS):
        assert f"xsheet-main-p{i}" in main_keys, f"主营派生行 p{i} 没落进产物"
    for i in range(DERIVED_OTHER_ROWS):
        assert f"xsheet-other-q{i}" in other_keys, f"其他派生行 q{i} 没落进产物"


# ═══════════════════════════════════════════════════════════════════════════
# 判据 4：同 sheet 兄弟区的 per-region **坐标声明**也必须与物理结构同源
#         （`_GT_SYNC` 的 GT_FOOTER_ROW_{TID} + workbook definedName 三件）
#
# 为什么单独一条：动态区靠 Excel Table 定位、**不**读这些 definedName，所以它们错位是
# **静默**的 —— 判据 3 绿了也不代表它们对。「声明与实况不符」本身是一类缺陷
# （excel_typography_rows 模块 docstring 的原话），必须单独钉。
# ═══════════════════════════════════════════════════════════════════════════


def _defined_names(path: Path) -> dict[str, str]:
    import re as _re
    import zipfile

    with zipfile.ZipFile(path) as zf:
        xml = zf.read("xl/workbook.xml").decode("utf-8", errors="replace")
    out: dict[str, str] = {}
    for m in _re.finditer(r'<definedName\b([^>]*)>(.*?)</definedName>', xml, _re.S):
        name = _re.search(r'\bname="([^"]*)"', m.group(1))
        if name:
            out[name.group(1)] = m.group(2).strip()
    return out


def _gt_sync_pairs(path: Path) -> dict[str, str]:
    """读隐藏 `_GT_SYNC` 的 key/value（A 列 key / B 列 value）。"""
    import re as _re
    import zipfile

    from app.services.workpaper_sync.excel_instrumentation import GT_SYNC_SHEET_NAME

    with zipfile.ZipFile(path) as zf:
        wb = zf.read("xl/workbook.xml").decode("utf-8", errors="replace")
        rels = zf.read("xl/_rels/workbook.xml.rels").decode("utf-8", errors="replace")
        rid = None
        for m in _re.finditer(r"<sheet\b([^>]*)/?>", wb):
            attrs = m.group(1)
            nm = _re.search(r'\bname="([^"]*)"', attrs)
            if nm and nm.group(1) == GT_SYNC_SHEET_NAME:
                r = _re.search(r'r:id="([^"]*)"', attrs)
                rid = r.group(1) if r else None
                break
        assert rid, f"定位不到 {GT_SYNC_SHEET_NAME} 的 r:id"
        tgt = _re.search(rf'Id="{rid}"[^>]*Target="([^"]*)"', rels) or _re.search(
            rf'Target="([^"]*)"[^>]*Id="{rid}"', rels
        )
        assert tgt, "定位不到 _GT_SYNC 的 part"
        part = "xl/" + tgt.group(1).lstrip("/")
        sx = zf.read(part).decode("utf-8", errors="replace")
    pairs: dict[str, str] = {}
    for m in _re.finditer(r'<c r="A(\d+)"[^>]*>\s*<is>\s*<t[^>]*>(.*?)</t>', sx, _re.S):
        row, key = m.group(1), m.group(2)
        v = _re.search(rf'<c r="B{row}"[^>]*>\s*<is>\s*<t[^>]*>(.*?)</t>', sx, _re.S)
        pairs[key] = v.group(1) if v else ""
    return pairs


def test_sibling_region_coordinate_declarations_stay_in_sync(
    contract: Any, definitions: FrozenEntryDefinitions, base_path: Path, tmp_path: Path
) -> None:
    """主营插行后，其他区的 `GT_FOOTER_ROW_D41OTHER` 与三个 per-region definedName
    都必须按同一 delta 下移（声明与物理同源）。"""
    from app.services.workpaper_sync.excel_materialize import materialize_projection

    before_pairs = _gt_sync_pairs(base_path)
    before_names = _defined_names(base_path)
    other_tid = A.TEMPLATE_ID_OTHER
    footer_key = f"GT_FOOTER_ROW_{other_tid}"
    assert footer_key in before_pairs, (
        f"前提不成立：`_GT_SYNC` 里没有 {footer_key}（实得 "
        f"{[k for k in before_pairs if k.startswith('GT_FOOTER_ROW')]}）"
    )
    footer_before = int(before_pairs[footer_key])

    proj = A.build_store_projection_d41(_rows_needing_insertion(), contract=contract)
    staged = tmp_path / AX.STAGING_NAMESPACE / "decl.xlsx"
    staged.parent.mkdir(parents=True, exist_ok=True)
    result = materialize_projection(
        substrate=base_path,
        projection=proj,
        output=staged,
        definitions=definitions,
        binding=BINDING_MAIN,
        substrate_role="published_representation",
        substrate_kind="canonical",
        substrate_state="published",
    ).result
    assert result.row_shift is not None
    delta = int(result.row_shift.count)

    after_pairs = _gt_sync_pairs(staged)
    assert int(after_pairs[footer_key]) == footer_before + delta, (
        f"同 sheet 兄弟区的 {footer_key} 没随插行下移："
        f"{footer_before} → {after_pairs[footer_key]}（插了 {delta} 行）—— "
        "其他区那一趟会撞 FooterAnchorDriftError"
    )

    # 三个 per-region definedName（区域 / footer 锚 / UUID 区间）都带行号，必须同步。
    after_names = _defined_names(staged)
    import re as _re

    def _max_row(ref: str) -> int:
        rows = [int(x) for x in _re.findall(r"\$(\d+)", ref)]
        return max(rows) if rows else 0

    for dn in (
        f"GT_MANAGED_REGION_{other_tid}",
        f"GT_FOOTER_ANCHOR_{other_tid}",
        f"GT_ROW_UUID_RANGE_{other_tid}",
    ):
        if dn not in before_names:
            continue  # 该形态未注入（非本判据面）
        b, a = _max_row(before_names[dn]), _max_row(after_names.get(dn, ""))
        assert a == b + delta, (
            f"兄弟区 definedName {dn} 的行号没同步下移：{before_names[dn]!r} → "
            f"{after_names.get(dn)!r}（插了 {delta} 行）—— 动态区靠 Table 定位不读它，"
            "所以这是**静默**的声明/实况不符"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 判据 5：materialize 之后 `verify_unmanaged_regions` 必须通过
#
# 🔴 为什么必须有这一条：判据 3 只跑 `adapter.materialize` + `adapter.extract`，
#    而生产 coordinator 在这之后**还要**跑 `verify_unmanaged_regions`。判据 3 绿而生产仍
#    500（`adapter_unmanaged_region_drift`）就是这个缺口的直接证据 —— 判据没覆盖真实路径，
#    等于在没被测的那一段上「看运气」。
#
# ═══ 第三层（同 sheet 多趟插行的累积归一化）修复记录 ═══
#
# 本条曾以 `xfail(strict=True)` 登记，修复后转正。三处改动缺一不可：
#
# ③-1 `excel_row_shift.CompositeRowShift` —— 累积位移的链式 `unshift` / 正序 `shift` /
#     `inserted_rows`（每趟新行经其后各趟 shift 映射到 after 口径后取并集）。
#     单趟仍传原 `RowShiftPlan` ⇒ 单 sheet / Word 路径逐字节不变。
# ③-2 `excel_workbook_row_change.normalise_propagated_part` —— **链式声明按链尾往前还原**。
#     同一处引用被两趟各改一次时声明是一条链（`$A$18→$A$25`、`$A$25→$A$31`），逆替换
#     顺序反了会停在中间态（`$A$25`）⇒ `workbook_and_styles` 误判 drift。新增链深度排序。
# ③-3 `adapters/excel._sheet_cumulative_shift` —— 合并 `total_formula_rows` 时把**每趟的
#     中间口径**映射回最初 before：其他区合计行在模板是 18，而其他区那趟声明的是 25
#     （= 18 + 主营插的 7）；verify 的 `_is_total_row` 用最初 before 坐标比对，拿 25 永远
#     不中 ⇒ 合计公式扩张不被还原 ⇒ 项数已对齐（292/292）但内容不等。
# ═══════════════════════════════════════════════════════════════════════════


def test_verify_unmanaged_regions_passes_after_row_insertion(
    contract: Any, definitions: FrozenEntryDefinitions, base_path: Path, tmp_path: Path
) -> None:
    adapter = AX.build_excel_adapter(
        definitions=definitions,
        binding=BINDING_MAIN,
        direction="html_to_oo",
        sibling_bindings=(BINDING_OTHER,),
    )
    proj = A.build_store_projection_d41(_rows_needing_insertion(), contract=contract)
    staged = tmp_path / AX.STAGING_NAMESPACE / "verify.xlsx"
    staged.parent.mkdir(parents=True, exist_ok=True)

    result = adapter.materialize(
        substrate=base_path, projection=proj, output=staged, contract=contract
    )
    # 🔴 先证明声明**真的**带出来了，再断言 verify —— 否则「我传了 None」会被误读成
    #    「归一化模型不支持」。两区同 sheet 都插了行 ⇒ per_table_shift 应有两条。
    pts = getattr(result, "per_table_shift", None)
    assert pts, f"per_table_shift 应随产物带出，实得 {pts!r}"
    assert A.ROWS_TABLE_KEY_MAIN in pts, (
        f"主营那趟的位移声明缺失：{sorted(pts)}"
    )
    # 🔴 复现前提：**两区都插行**（同一 sheet 被插两次）才需要累积归一化。
    #    若只有一条，本用例测的就不是累积场景 —— 那时 drift 另有原因，必须看见。
    detail = {k: (getattr(v[0], "count", None), tuple(v[1] or ())) for k, v in pts.items()}
    assert A.ROWS_TABLE_KEY_OTHER in pts, (
        f"其他区那趟的位移声明缺失 ⇒ 本用例不是累积场景。per_table_shift={detail}"
    )
    # 三个归一化声明都取 materialize 随产物带出的那一份（生产 coordinator 同口径）。
    adapter.verify_unmanaged_regions(
        before=base_path,
        after=staged,
        contract=contract,
        row_shift=getattr(result, "row_shift", None),
        total_formula_rows=getattr(result, "total_formula_rows", ()) or (),
        propagation=getattr(result, "workbook_row_change", None),
        per_table_shift=getattr(result, "per_table_shift", None),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 判据 5b：OO→HTML rematerialize 不得把同 sheet 兄弟受管格判成 unmanaged drift
#
# 真栈（op f57a28ea / incoming callback-8c95228c4b96）：merge 已过，卡在 rematerializing
# → `adapter_unmanaged_region_drift`（managed_sheet_unmanaged_cells 403/403 内容不等）。
# 差分面：OO 把 materialize 写的 `inlineStr` 改成 sharedString、把金额写成 IEEE 噪声；
# rematerialize 再改回本口径时，**主营区的格**对「其他区」那个 binding 是「未管理」、
# 反之亦然 —— 逐 binding 校验互把兄弟区当 unmanaged ⇒ 假漂移。
# 修法：同 sheet 兄弟受管坐标并进 `extra_managed_coords`。
# ═══════════════════════════════════════════════════════════════════════════


def test_same_sheet_sibling_coords_exclude_peer_rewrites_from_unmanaged_digest(
    contract: Any, definitions: FrozenEntryDefinitions, base_path: Path, tmp_path: Path
) -> None:
    """同 sheet 兄弟受管格被改写时，并进 extra_managed_coords 后 unmanaged digest 不变。

    这是 OO→HTML rematerialize 假漂移的最小面：不跑完整 rematerialize，只证明
    「兄弟区坐标并集」能把本 binding 眼中的假 unmanaged 格从 digest 里摘掉。
    """
    import re
    import zipfile

    from app.services.workpaper_sync.excel_extract import (
        _managed_coordinates,
        resolve_managed_region,
        unmanaged_region_digest,
    )

    adapter = AX.build_excel_adapter(
        definitions=definitions,
        binding=BINDING_MAIN,
        direction="html_to_oo",
        sibling_bindings=(BINDING_OTHER,),
    )
    proj = A.build_store_projection_d41(_rows_needing_insertion(), contract=contract)
    staged = tmp_path / AX.STAGING_NAMESPACE / "peer-digest.xlsx"
    staged.parent.mkdir(parents=True, exist_ok=True)
    adapter.materialize(
        substrate=base_path, projection=proj, output=staged, contract=contract
    )

    with zipfile.ZipFile(staged) as zf:
        region_main = resolve_managed_region(
            zf, contract=contract, binding=BINDING_MAIN
        )
        region_other = resolve_managed_region(
            zf, contract=contract, binding=BINDING_OTHER
        )
        assert region_main.sheet_part == region_other.sheet_part
        sheet_part = region_main.sheet_part

    main_coords = _managed_coordinates(
        contract=contract, region=region_main, binding=BINDING_MAIN, scan=None
    )
    target = None
    with zipfile.ZipFile(staged, "r") as zf:
        entries = {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}
    xml = entries[sheet_part].decode("utf-8")
    for cand in sorted(c for c in main_coords if c.startswith("A")):
        cell_m = re.search(
            rf'<c r="{re.escape(cand)}"[^>]*/>|<c r="{re.escape(cand)}"[^>]*>.*?</c>',
            xml,
            re.S,
        )
        if cell_m and ("<t" in cell_m.group(0) or "<v>" in cell_m.group(0)):
            target = cand
            cell_xml = cell_m.group(0)
            cell_span = cell_m.span()
            break
    assert target, f"主营区 A 列没有带文本的受管格可改，coords={sorted(main_coords)[:12]}"

    if "<t" in cell_xml:
        new_cell = re.sub(
            r"(<t[^>]*>)(.*?)(</t>)",
            r"\1PEER-REWRITE-MARKER\3",
            cell_xml,
            count=1,
            flags=re.S,
        )
    else:
        new_cell = re.sub(
            r"(<v>)(.*?)(</v>)",
            r"\1PEER-REWRITE-MARKER\3",
            cell_xml,
            count=1,
            flags=re.S,
        )
    assert new_cell != cell_xml, target
    entries[sheet_part] = (
        xml[: cell_span[0]] + new_cell + xml[cell_span[1] :]
    ).encode("utf-8")
    mutated = tmp_path / AX.STAGING_NAMESPACE / "peer-mutated.xlsx"
    with zipfile.ZipFile(mutated, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)

    base_without = unmanaged_region_digest(
        staged, contract=contract, region=region_other, binding=BINDING_OTHER
    )
    base_with = unmanaged_region_digest(
        staged,
        contract=contract,
        region=region_other,
        binding=BINDING_OTHER,
        extra_managed_coords=main_coords,
    )
    mut_without = unmanaged_region_digest(
        mutated, contract=contract, region=region_other, binding=BINDING_OTHER
    )
    mut_with = unmanaged_region_digest(
        mutated,
        contract=contract,
        region=region_other,
        binding=BINDING_OTHER,
        extra_managed_coords=main_coords,
    )

    assert mut_without.aspects["managed_sheet_unmanaged_cells"] != (
        base_without.aspects["managed_sheet_unmanaged_cells"]
    ), "未并兄弟坐标时应能看见主营格被改写（否则判据测空）"
    assert mut_with.aspects["managed_sheet_unmanaged_cells"] == (
        base_with.aspects["managed_sheet_unmanaged_cells"]
    ), (
        f"并进主营坐标后，改写 {target} 仍改变了其他区 unmanaged digest —— "
        "同 sheet 兄弟受管格排除未生效"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 判据 6（参数化）：D4 **全部**同 sheet 多受管区底稿，上区插行后下方兄弟区 ref 必须位移
#
# 不只盯 D4-1：从 provider 的 `instrumentation_specs()` **动态**算出「同一 managed_sheet
# 有 ≥2 个受管区」的组（实测 30 个受管 sheet 里有 5 张），逐张验证。硬编码清单会在新增
# 受管区时静默漏掉 —— 而漏掉的那张就是下一个线上 500。
# ═══════════════════════════════════════════════════════════════════════════


def _multi_region_sheets() -> dict[str, list[Any]]:
    """`managed_sheet → [spec, …]`，只保留同 sheet ≥2 个受管区的组（按首数据行升序）。"""
    by_sheet: dict[str, list[Any]] = {}
    for spec in D4.instrumentation_specs():
        if not (getattr(spec, "table_name", None) and getattr(spec, "uuid_col", None)):
            continue
        by_sheet.setdefault(str(spec.managed_sheet), []).append(spec)
    return {
        sheet: sorted(specs, key=lambda s: int(s.first_data_row))
        for sheet, specs in by_sheet.items()
        if len(specs) >= 2
    }


_MULTI = _multi_region_sheets()


def test_premise_multi_region_sheets_discovered() -> None:
    """前提：provider 上确实存在同 sheet 多受管区（否则判据 6 是空跑）。"""
    assert _MULTI, "一张同 sheet 多受管区底稿都没发现 —— 判据 6 会空转"
    assert A.MANAGED_SHEET_D41 in _MULTI, (
        f"D4-1 应在同 sheet 多区清单里，实得 {sorted(_MULTI)}"
    )
    # D4-20 是三区 —— 三区场景与两区不同（中间区既被上区推、又要推下区）。
    three = [s for s, v in _MULTI.items() if len(v) >= 3]
    assert three, f"应有至少一张三区底稿（D4-20），实得各组区数 " \
                  f"{ {s: len(v) for s, v in _MULTI.items()} }"


@pytest.mark.parametrize("sheet_name", sorted(_MULTI))
def test_all_multi_region_sheets_shift_sibling_table_refs(
    sheet_name: str, instrumented: EI.InstrumentedWorkbook, tmp_path: Path
) -> None:
    """对每张同 sheet 多区底稿：最上区插 N 行 ⇒ 其下方**每个**兄弟区 ref 整体下移 N。

    走 `excel_materialize._grow_managed_table_ref` 这一真实入口（它内部会调
    `_shift_sibling_table_refs`），plan 用鸭子对象只喂它读的三个字段。
    """
    import zipfile
    from types import SimpleNamespace

    from app.services.workpaper_sync.excel_materialize import (
        _grow_managed_table_ref,
        _managed_table_part,
    )
    from app.services.workpaper_sync.excel_row_shift import RowShiftPlan

    specs = _MULTI[sheet_name]
    upper = specs[0]
    lowers = specs[1:]

    data = instrumented.instrumented_bytes
    entries: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            if not name.endswith("/"):
                entries[name] = zf.read(name)
        sheet_part = EE._sheet_parts(zf).get(sheet_name)
    assert sheet_part, f"定位不到受管 sheet part：{sheet_name}"

    before = _table_refs_from_entries(entries)
    upper_part = _managed_table_part(entries, table_name=str(upper.table_name))
    assert upper_part, f"定位不到上区 Table part：{upper.table_name}"

    insert_at = int(upper.last_data_row) + 1
    count = 5
    plan = SimpleNamespace(
        row_shift=RowShiftPlan(
            insert_at=insert_at,
            count=count,
            style_from=int(upper.last_data_row),
            table_key=str(upper.table_name),
        ),
        sheet_part=sheet_part,
        table_part=upper_part,
    )
    out = _grow_managed_table_ref(dict(entries), plan=plan)
    after = _table_refs_from_entries(out)

    def _rows(ref: str) -> tuple[int, int]:
        head, tail = ref.split(":", 1)
        return (
            int("".join(c for c in head if c.isdigit())),
            int("".join(c for c in tail if c.isdigit())),
        )

    # 上区自己：末行长 count（追加插行语义），首行不动。
    ub, ua = before[str(upper.table_name)], after[str(upper.table_name)]
    ub_head, ub_tail = _rows(ub)
    ua_head, ua_tail = _rows(ua)
    assert (ua_head, ua_tail) == (ub_head, ub_tail + count), (
        f"{sheet_name} 上区 {upper.table_name} ref 未按追加语义增长：{ub} → {ua}"
    )

    # 下方每个兄弟区：首末行都 +count（整体下移）。
    for lower in lowers:
        name = str(lower.table_name)
        lb, la = before[name], after[name]
        lb_head, lb_tail = _rows(lb)
        la_head, la_tail = _rows(la)
        assert lb_head > insert_at, (
            f"{sheet_name} 的 {name} 首行 {lb_head} 不在插入点 {insert_at} 之下 —— "
            "本例不是「下方兄弟区」场景，判据前提不成立"
        )
        assert (la_head, la_tail) == (lb_head + count, lb_tail + count), (
            f"{sheet_name} 下方兄弟区 {name} 的 ref 没随上区插 {count} 行下移："
            f"{lb} → {la}（应为 {lb_head + count}..{lb_tail + count}）"
        )

    # 其它 sheet 上的 Table 一处都不能动（位移不得越 sheet）。
    same_sheet = {str(s.table_name) for s in specs}
    for name, ref in before.items():
        if name in same_sheet:
            continue
        assert after.get(name) == ref, (
            f"位移越过了 sheet 边界：{name} 的 ref {ref} → {after.get(name)}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 判据 7：**单区** sheet 的行为必须逐字节不变（纯增量纪律）
#
# 本次修复的三处都是「多区才生效」的分支。单区底稿（实测 30 个受管 sheet 里 25 张）
# 必须走原路径 —— 否则「修好 5 张、弄坏 25 张」。这两条是结构性保证，比再跑 25 遍
# 业务链路便宜且更精确。
# ═══════════════════════════════════════════════════════════════════════════


def _single_region_sheets() -> dict[str, Any]:
    by_sheet: dict[str, list[Any]] = {}
    for spec in D4.instrumentation_specs():
        if not (getattr(spec, "table_name", None) and getattr(spec, "uuid_col", None)):
            continue
        by_sheet.setdefault(str(spec.managed_sheet), []).append(spec)
    return {s: v[0] for s, v in by_sheet.items() if len(v) == 1}


_SINGLE = _single_region_sheets()


def test_premise_most_d4_sheets_are_single_region() -> None:
    assert len(_SINGLE) >= 20, (
        f"单区 sheet 应占多数（实测应 25 张），实得 {len(_SINGLE)} —— "
        "若结构变了，判据 7 的代表性要重新评估"
    )


def test_single_trip_returns_the_original_plan_not_a_composite() -> None:
    """`_sheet_cumulative_shift` 单趟时必须返回**原 `RowShiftPlan` 对象本身**。

    返回 composite 会让单区/Word/旧调用方走上新的归一化代码路径 —— 即便数学等价，
    也把「纯增量」这条纪律破掉了（一旦 composite 有 bug，25 张单区底稿一起中招）。
    """
    from app.services.workpaper_sync.adapters.excel import _sheet_cumulative_shift
    from app.services.workpaper_sync.excel_row_shift import (
        CompositeRowShift,
        RowShiftPlan,
    )

    plan = RowShiftPlan(insert_at=20, count=3, style_from=19, table_key="solo_rows")
    shift, totals = _sheet_cumulative_shift(
        {"solo_rows": (plan, (19,))},
        sheet_of_table={"solo_rows": "xl/worksheets/sheet9.xml"},
        sheet_part="xl/worksheets/sheet9.xml",
    )
    assert shift is plan, f"单趟应原样返回 plan 本身，实得 {type(shift).__name__}"
    assert not isinstance(shift, CompositeRowShift)
    assert totals == (19,)

    # 两趟才合成 composite，且 totals 按前序趟 unshift 回最初 before 口径。
    plan2 = RowShiftPlan(insert_at=30, count=2, style_from=29, table_key="second_rows")
    shift2, totals2 = _sheet_cumulative_shift(
        {"solo_rows": (plan, (19,)), "second_rows": (plan2, (30,))},
        sheet_of_table={
            "solo_rows": "xl/worksheets/sheet9.xml",
            "second_rows": "xl/worksheets/sheet9.xml",
        },
        sheet_part="xl/worksheets/sheet9.xml",
    )
    assert isinstance(shift2, CompositeRowShift)
    assert shift2.plans == (plan, plan2), "plans 顺序必须是逐趟顺序（链式 unshift 依赖它）"
    # 第二趟声明的 30 是「主营已插 3 行之后」的中间口径 ⇒ 回到最初 before 是 27。
    assert totals2 == (19, 27), (
        f"第二趟 totals 未映射回最初 before 口径：{totals2}（应为 (19, 27)）"
    )


def test_other_sheet_tables_are_untouched_for_single_region_sheet(
    instrumented: EI.InstrumentedWorkbook,
) -> None:
    """单区 sheet 插行时，`_shift_sibling_table_refs` 必须零改动（它没有同 sheet 兄弟）。"""
    import zipfile

    from app.services.workpaper_sync.excel_materialize import (
        _managed_table_part,
        _shift_sibling_table_refs,
    )
    from app.services.workpaper_sync.excel_row_shift import RowShiftPlan

    assert _SINGLE, "无单区 sheet 可测"
    # 取一张代表（按名字排序保证稳定）。
    sheet_name = sorted(_SINGLE)[0]
    spec = _SINGLE[sheet_name]

    entries: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(instrumented.instrumented_bytes)) as zf:
        for name in zf.namelist():
            if not name.endswith("/"):
                entries[name] = zf.read(name)
        sheet_part = EE._sheet_parts(zf).get(sheet_name)
    assert sheet_part, sheet_name

    own_part = _managed_table_part(entries, table_name=str(spec.table_name))
    before = dict(entries)
    from types import SimpleNamespace

    plan = SimpleNamespace(
        row_shift=RowShiftPlan(
            insert_at=int(spec.last_data_row) + 1,
            count=4,
            style_from=int(spec.last_data_row),
            table_key=str(spec.table_name),
        ),
        sheet_part=sheet_part,
        table_part=own_part,
    )
    out, changes = _shift_sibling_table_refs(dict(entries), plan=plan, own_part=own_part)
    assert changes == 0, (
        f"单区 sheet {sheet_name} 上不应有兄弟 Table 被改（实改 {changes} 处）"
    )
    assert out == before, "单区 sheet 的 entries 必须逐字节不变"
