"""Task 6/12: D4-12 转置表 materialize→extract 逐字段往返 + 边界。

spec: d4-12-transposed-writeback / Requirement 3.3, 3.4, 3.4a / Property 3, 7

验证泛化通用引擎在 SPEC_D412（首列 B / 21 字段 R11-R31 / 扁平 store / GT-CONTRACT- carrier）
下往返闭合：21 字段 × N 合同 materialize→extract 逐字段一致；空值 / 占位空列跳过 / 扩列 /
首列 B（不误写 A）/ 载体行 hidden 强校验 / 公式格拒绝。

模板经通用 instrumentation 注入 GT_MANAGED_REGION_D412 + 隐藏 R9 载体行（Task 7 的注入路径
即既有 excel_instrumentation 的 transposed_sheets 分支，D4-12 声明 sheet_payload 即复用）。
"""
from __future__ import annotations

import io

import pytest
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string

from app.services.workpaper_sync import phase5_d4_12_contract as d12
from app.services.workpaper_sync import phase5_d4_revenue_detail as provider
from app.services.workpaper_sync.contracts import parse_contract
from app.services.workpaper_sync.excel_instrumentation import instrument_workbook_bytes_multi


@pytest.fixture
def template():
    """注入了 D4-12 转置锚点 + 隐藏载体行的合并模板字节。

    Task 8 后 provider.instrumentation_specs() 已含 D4-12 transposed_sheet, 直接用即可
    （不再手动追加, 否则重复注入 GT_MANAGED_REGION_D412 报 Duplicate）。
    """
    return instrument_workbook_bytes_multi(
        provider.read_authoritative_template(), provider.instrumentation_specs(),
        gate=provider.excel_carrier_gate(),
    ).instrumented_bytes


@pytest.fixture
def contract():
    """live 契约（Task 8 后 build_contract_payload 已含 d4-12-managed）。"""
    return parse_contract(provider.build_contract_payload(), adapter_id=provider.ADAPTER_ID)


def contracts(count=3):
    """扁平 store 形态的合同（21 字段平铺 + id）。"""
    out = []
    for i in range(count):
        item = {"id": f"c-{i}", "indexNo": f"D4-12-{i + 1}", "label": f"合同{i}"}
        for k in d12.FIELD_KEYS:
            item[k] = 100 + i if k == "contractAmount" else f"{k}-{i}"
        out.append(item)
    return out


def _extract_business(data):
    """extract 后只保留 id + 21 受管字段（元字段 indexNo/label 不入转置区）。"""
    return d12.extract_transposed_workbook(data)


def test_geometry_injected(template):
    """注入后模板认出 workbook-scope definedName + R9 hidden。"""
    wb, ws = d12.resolve_managed_sheet(template)
    assert ws.title == d12.MANAGED_SHEET
    # definedName 唯一 + workbook-scope 由 resolve_managed_sheet 内部校验（不抛即通过）。
    assert d12.DEFINED_NAME in wb.defined_names


def test_21_field_roundtrip(template, contract):
    payload = contracts(3)
    data = d12.materialize_transposed_workbook(template, payload)
    extracted = _extract_business(data)
    # extract 返回 id + 21 字段（扁平），逐字段与写入一致。
    assert len(extracted) == 3
    for src, got in zip(payload, extracted):
        assert got["id"] == src["id"]
        for k in d12.FIELD_KEYS:
            assert got[k] == src[k], f"字段 {k} 往返漂移: {got[k]!r} != {src[k]!r}"


def test_first_column_is_B_not_A(template):
    """Property 7: 首实体列是 B，A 是字段标签列不受写入。"""
    payload = contracts(2)
    data = d12.materialize_transposed_workbook(template, payload)
    ws = load_workbook(io.BytesIO(data))[d12.MANAGED_SHEET]
    # 第一合同写在 B 列（carrier R9 + 字段 R11..R31）。
    assert ws.cell(d12.IDENTITY_CARRIER_ROW, column_index_from_string("B")).value == "GT-CONTRACT-c-0"
    assert ws.cell(11, column_index_from_string("B")).value == "contractNo-0"
    # A 列是标签列，保持模板原标签不被业务值覆盖。
    assert ws["A11"].value == "合同编号"
    assert ws["A15"].value == "合同金额"


def test_carrier_row_hidden(template):
    payload = contracts(1)
    data = d12.materialize_transposed_workbook(template, payload)
    ws = load_workbook(io.BytesIO(data))[d12.MANAGED_SHEET]
    assert ws.row_dimensions[d12.IDENTITY_CARRIER_ROW].hidden


def test_empty_and_placeholder_columns_skipped(template):
    """空合同 / 模板预画占位空列被识别为非业务列跳过（不报错）。"""
    assert _extract_business(d12.materialize_transposed_workbook(template, [])) == []
    # 写 2 份后模板仍预画到 K 列（10 列），尾随空列应被跳过而非报错。
    data = d12.materialize_transposed_workbook(template, contracts(2))
    assert len(_extract_business(data)) == 2


def test_expand_beyond_reserved_columns(template):
    """超过预留列 K（10 列）时样式克隆扩列，仍往返闭合。"""
    payload = contracts(12)  # > 10 预留列
    data = d12.materialize_transposed_workbook(template, payload)
    extracted = _extract_business(data)
    assert len(extracted) == 12
    assert extracted[11]["id"] == "c-11"


def test_contract_amount_numeric_semantics(template):
    """Property 3.4a: 合同金额往返语义。

    🔴 名实边界（复盘 #1 澄清）：`contractAmount` 的 value_type=amount **仅用于契约声明**；
    引擎的 materialize/extract 对它与其它字段**同走 text 编解码**（无 amount 专用类型化）。
    因此：
    - 非空数值（int/float）→ openpyxl 原样存/读，往返保数值（12345 / 0 均不丢）；
    - 空值 → 往返成空字符串 `''`（不静默投 0 覆盖），前端 `ContractInspectionItem.contractAmount:number`
      经 `parseNum('')===0` 兜底（useD4FormulaEngine.parseNum）。
    这不是「假装做了 amount 类型化」——是明确的「amount 声明 + text 编解码 + 前端 parseNum 兜底」。
    """
    # (a) 非空数值往返保数值
    payload = contracts(1)
    payload[0]["contractAmount"] = 12345
    data = d12.materialize_transposed_workbook(template, payload)
    ws = load_workbook(io.BytesIO(data))[d12.MANAGED_SHEET]
    cell = ws.cell(d12.FIELD_ROWS["contractAmount"], column_index_from_string("B"))
    assert cell.value == 12345
    assert _extract_business(data)[0]["contractAmount"] == 12345

    # (b) 0 往返保 0（不被空值逻辑误吞）
    p0 = contracts(1); p0[0]["contractAmount"] = 0
    assert _extract_business(d12.materialize_transposed_workbook(template, p0))[0]["contractAmount"] == 0

    # (c) 空值往返成 ''（不静默投 0 覆盖）；前端 parseNum('')===0 兜底
    pe = contracts(1); pe[0]["contractAmount"] = ""
    got_empty = _extract_business(d12.materialize_transposed_workbook(template, pe))[0]["contractAmount"]
    assert got_empty == "", f"空 amount 往返应为空字符串(不投0覆盖), 实得 {got_empty!r}"


def test_carrier_hidden_strong_check(template):
    """载体行未 hidden → extract fail-closed。"""
    data = d12.materialize_transposed_workbook(template, contracts(1))
    wb = load_workbook(io.BytesIO(data))
    wb[d12.MANAGED_SHEET].row_dimensions[d12.IDENTITY_CARRIER_ROW].hidden = False
    out = io.BytesIO()
    wb.save(out)
    with pytest.raises(ValueError, match="identity row must be hidden"):
        d12.extract_transposed_workbook(out.getvalue())


def test_formula_field_rejected(template):
    """字段格含公式 → extract fail-closed。"""
    data = d12.materialize_transposed_workbook(template, contracts(1))
    wb = load_workbook(io.BytesIO(data))
    wb[d12.MANAGED_SHEET].cell(11, column_index_from_string("B")).value = "=1+1"
    out = io.BytesIO()
    wb.save(out)
    with pytest.raises(ValueError, match="cannot contain a formula"):
        d12.extract_transposed_workbook(out.getvalue())


def test_duplicate_identity_rejected(template):
    with pytest.raises(ValueError, match="unique"):
        d12.materialize_transposed_workbook(template, contracts(1) * 2)


def test_store_projection_stable_key(template, contract):
    payload = contracts(2)
    projection = d12.build_store_projection(payload, contract=contract)
    projection.assert_matches_contract(contract)
    assert projection.get("contract_inspection_transposed/c-0/contractno") is not None
    assert projection.row_keys["contract_inspection_transposed"] == ("c-0", "c-1")


def test_merge_conflict_semantics_managed_overwritten_metafield_kept(contract):
    """复盘 #3 语义锚：merge 时受管字段由 projection 覆盖、未受管元字段以 base(HTML) 为准。

    base 有旧受管值 + 旧元字段(indexNo/label/attachmentId)；projection 携新受管值。
    结果：21 受管字段更新为 projection 新值；元字段保持 base(转置受管区不承载它们，OO 不覆盖)。
    """
    # base：合同 c-0 旧受管 contractNo=OLD + 元字段
    base = [{
        "id": "c-0", "indexNo": "D4-12-1", "label": "旧备注", "attachmentId": "att-old",
        "ocrStatus": "done",
        **{k: (0 if k == "contractAmount" else "OLD") for k in d12.FIELD_KEYS},
    }]
    # projection 源：同 id, 受管 contractNo=NEW（模拟 OO 侧改了受管字段）
    proj_src = [{"id": "c-0", **{k: (999 if k == "contractAmount" else "NEW") for k in d12.FIELD_KEYS}}]
    projection = d12.build_store_projection(proj_src, contract=contract)

    merged, applied, _visited, _removed = d12.merge_projection_into_store(
        projection=projection, base_payload=base
    )
    row = merged[0]
    # 受管字段被 projection 覆盖为新值
    assert row["contractNo"] == "NEW"
    assert row["contractAmount"] == 999
    # 未受管元字段以 base 为准（不被抹、不被 OO 覆盖）
    assert row["indexNo"] == "D4-12-1"
    assert row["label"] == "旧备注"
    assert row["attachmentId"] == "att-old"
    assert row["ocrStatus"] == "done"
    assert applied > 0


# ═══════════════════════════════════════════════════════════════════════
# 空转置表中性化假 drift 回归守卫（本轮修复：adapters/excel.verify_unmanaged_regions）
#
# 🔴 根因：verify 侧转置中性化对**空转置表**（D4-12 无行）仍无条件跑
#    materialize_transposed_workbook，其 openpyxl `wb.save()` 会**重序列化目标 sheet
#    part**，即便零实体也产出字节不同的 XML。而 materialize 侧对空转置表是 no-op
#    （materialize_file: `if spec.table_key not in projection.row_keys: return`），故 after
#    的该 sheet 与 before 逐字节相同。若中性化仍无条件重投影，就把 before 那张 sheet 无谓
#    openpyxl 重写成字节不同 ⇒ verify 的 other_sheet_parts 把「after==before 的空转置
#    sheet」判成 drift（真栈 D4-12 无行时 sheet17 假漂移、apply 卡 adapter_unmanaged_region_drift）。
# 修复：中性化循环 `after_rows = _transposed_extract(after)`，**空则 continue 跳过**
#    （与 materialize 侧对称），仅当有非空实体才切 before_for_compare。
# ═══════════════════════════════════════════════════════════════════════


def test_empty_transposed_roundtrip_is_NOT_byte_idempotent(template):
    """记录陷阱本身：空转置表的 materialize(extract()) 往返**不是**逐字节幂等。

    这正是「中性化必须跳过空转置表」的理由 —— 若不跳，中性化会把 before 的该 sheet
    无谓重写成字节不同，从而在 verify 里制造假 drift。此测试把这个 openpyxl 重序列化
    事实钉死：一旦哪天引擎改成空表 no-op（字节幂等），本断言会提醒复核「跳过」是否仍必要。
    """
    import hashlib
    import zipfile

    S = "xl/worksheets/"

    def _managed_sheet_part(data: bytes) -> str:
        # D4-12 受管 sheet 的 part 路径（按 workbook.xml → rels 解析）
        import re
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            wb = z.read("xl/workbook.xml").decode("utf-8", "replace")
            rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8", "replace")
        rid = next(m.group(2) for m in re.finditer(r'<sheet[^>]*name="([^"]+)"[^>]*r:id="([^"]+)"', wb)
                   if m.group(1) == d12.MANAGED_SHEET)
        tgt = dict(re.findall(r'Id="([^"]+)"[^>]*Target="([^"]+)"', rels))[rid]
        return "xl/" + tgt.lstrip("/")

    def _part_sha(data: bytes, part: str) -> str:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            return hashlib.sha256(z.read(part)).hexdigest()

    part = _managed_sheet_part(template)
    # 空转置表：extract 得 0 实体
    assert _extract_business(template) == []
    # 无谓往返（extract 空 → materialize 回）——openpyxl 重序列化使字节改变
    round_tripped = d12.materialize_transposed_workbook(template, _extract_business(template))
    assert _part_sha(template, part) != _part_sha(round_tripped, part), (
        "若此断言失败说明空转置往返已字节幂等——需复核 verify 中性化的「空则跳过」是否仍必要"
    )


def test_verify_neutralization_skips_empty_transposed_spec_source_anchor():
    """AST 锚点：adapters/excel.verify_unmanaged_regions 的转置中性化循环必须**先取
    after_rows 再对空跳过**（`if not after_rows: continue`），否则空转置表假 drift 复发。

    这是行为级判据的源码形态守卫（同 repo 既有 AST 守卫风格）：删掉「空则跳过」这行、
    或改回无条件 `_transposed_materialize` 都会让本测试打红。
    """
    import ast
    import inspect
    import textwrap

    from app.services.workpaper_sync.adapters import excel as AX

    src = textwrap.dedent(inspect.getsource(AX.ExcelSyncAdapter.verify_unmanaged_regions))
    tree = ast.parse(src)

    # 找到「for spec in specs」循环体，断言其中有基于 after_rows 空值的 continue
    found_guard = False
    for node in ast.walk(tree):
        if isinstance(node, ast.For):
            body_src = ast.get_source_segment(src, node) or ""
            if "_transposed_extract" in body_src or "_transposed_materialize" in body_src:
                # 循环体里必须出现「空 rows → continue」的短路，且在 materialize 调用之前
                if "continue" in body_src and (
                    "not after_rows" in body_src or "if not " in body_src
                ):
                    found_guard = True
    assert found_guard, (
        "verify_unmanaged_regions 的转置中性化循环缺「空 after_rows 跳过」守卫 —— "
        "空转置表会被 openpyxl 重序列化制造假 other_sheet_parts drift（D4-12 真栈复现）"
    )
