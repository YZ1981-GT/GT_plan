"""D4-1 营业收入审定表 — 导入导出十列 + per-field 键守卫

Spec: .kiro/specs/d4-1-adjudication-bidirectional-writeback-and-formula-io/ Task 4.1
Requirements 4.1 / 4.2 / 4.3 / 4.4

覆盖：
- 十列列头（含科目码），派生列不进导入列
- 导入解析 → per-field 中间形态（rowId/label/source/accountCode/sectionKey + 六金额）
- _build_d4_1_import_items → 清单 D4-1-rows + N×6 field 键，不写 D4-1-adj-rows blob，item_id 去重
- round-trip：导出十列 → 再导入解析，label/accountCode/六金额/rowId/source 逐字段一致
- 缺科目码 → 不拒整行但进 warnings（Req 4.2）；非法码/未知区块进 warnings
- 派生列（审定数）导入被忽略（塞假审定数不落库）
- 旧 D4-1-adj-rows blob 导出兼容回退
- 区块 ↔ sectionKey 映射正确
- 反向自检（判据不恒真）
"""

from __future__ import annotations

import json

from app.routers.wp_render_strategies import _d4_import_export as mod


# ═══════════════════════════════════════════════════════════════════════════════
# 测试辅助：模拟一行 xlsx（按 headers 顺序的 tuple）
# ═══════════════════════════════════════════════════════════════════════════════

HEADERS = mod._get_headers("D4-1")


def _row(**cells) -> tuple:
    """按 D4-1 列头顺序构造一行 tuple（未给的列为 None）。"""
    return tuple(cells.get(h) for h in HEADERS)


# ═══════════════════════════════════════════════════════════════════════════════
# 列头
# ═══════════════════════════════════════════════════════════════════════════════


def test_headers_are_ten_columns_with_account_code() -> None:
    """Req 4.1：十列列头，含「科目码」，派生列（审定数/合计/差异/变动率）不在导入列。"""
    assert HEADERS == [
        "区块", "行键", "项目", "科目码",
        "本期未审", "本期AJE", "本期RJE",
        "上期未审", "上期AJE", "上期RJE",
    ]
    assert len(HEADERS) == 10
    assert "科目码" in HEADERS
    # 派生列不作为导入列
    for derived in ("审定数", "本期审定", "上期审定", "小计", "合计", "差异", "变动率"):
        assert derived not in HEADERS


def test_reverse_headers_missing_account_code_would_fail() -> None:
    """反向自检：若列头缺「科目码」（旧九列），断言必须失败。"""
    old_nine = [
        "区块", "行键", "项目",
        "本期未审", "本期AJE", "本期RJE",
        "上期未审", "上期AJE", "上期RJE",
    ]
    assert "科目码" not in old_nine  # 旧九列确实无科目码
    assert HEADERS != old_nine  # 当前真源已不是九列


# ═══════════════════════════════════════════════════════════════════════════════
# 导入解析 → per-field 中间形态
# ═══════════════════════════════════════════════════════════════════════════════


def test_parse_row_produces_per_field_shape() -> None:
    """Req 4.1：解析一行 → {rowId, label, source, accountCode, sectionKey, 六字段}。"""
    warnings: list[str] = []
    row = _row(**{
        "区块": "主营业务收入", "行键": "r-abc123", "项目": "批发收入", "科目码": "600101",
        "本期未审": 1000, "本期AJE": 10, "本期RJE": 5,
        "上期未审": 900, "上期AJE": 8, "上期RJE": 3,
    })
    parsed = mod._parse_d4_1_row(row, HEADERS, HEADERS, warnings)

    assert parsed["rowId"] == "r-abc123"
    assert parsed["label"] == "批发收入"
    assert parsed["source"] == "manual"
    assert parsed["accountCode"] == "600101"
    assert parsed["sectionKey"] == "main-revenue"
    assert parsed["currentUnadjusted"] == 1000.0
    assert parsed["currentAje"] == 10.0
    assert parsed["currentRje"] == 5.0
    assert parsed["priorUnadjusted"] == 900.0
    assert parsed["priorAje"] == 8.0
    assert parsed["priorRje"] == 3.0
    # 6001 族科目码 → 无 warning
    assert warnings == []


def test_parse_generates_rowid_when_missing() -> None:
    """Req 4.1：无行键 → 生成 r-{hex} 形态 rowId（与前端 nextRowId 一致）。"""
    row = _row(**{"区块": "其他业务收入", "项目": "废料收入", "科目码": "605101", "本期未审": 50})
    parsed = mod._parse_d4_1_row(row, HEADERS, HEADERS, None)
    assert parsed["rowId"].startswith("r-")
    assert parsed["sectionKey"] == "other-revenue"


def test_parse_empty_row_returns_empty() -> None:
    """无行键无项目 → 跳过（返回空 dict）。"""
    row = _row(**{"本期未审": 0})
    assert mod._parse_d4_1_row(row, HEADERS, HEADERS, None) == {}


# ═══════════════════════════════════════════════════════════════════════════════
# 区块 ↔ sectionKey 映射
# ═══════════════════════════════════════════════════════════════════════════════


def test_section_mapping_both_directions() -> None:
    """Req 4.3：区块中文 ↔ sectionKey 双向映射与前端锁死。"""
    assert mod._D4_1_SECTION_BY_LABEL["主营业务收入"] == "main-revenue"
    assert mod._D4_1_SECTION_BY_LABEL["其他业务收入"] == "other-revenue"
    assert mod._D4_1_SECTION_LABEL["main-revenue"] == "主营业务收入"
    assert mod._D4_1_SECTION_LABEL["other-revenue"] == "其他业务收入"


def test_unknown_section_not_guessed_and_warned() -> None:
    """Req 4.2：未知区块不臆测归段（sectionKey 为空）并进 warnings。"""
    warnings: list[str] = []
    row = _row(**{"区块": "海外收入", "项目": "外销", "科目码": "600101"})
    parsed = mod._parse_d4_1_row(row, HEADERS, HEADERS, warnings)
    assert parsed["sectionKey"] == ""  # 不自动归主营
    assert any("海外收入" in w and "无法识别" in w for w in warnings)


# ═══════════════════════════════════════════════════════════════════════════════
# Req 4.2 科目码缺失/非法 → warnings（不静默猜测）
# ═══════════════════════════════════════════════════════════════════════════════


def test_missing_account_code_not_rejected_but_warned() -> None:
    """Req 4.2：缺科目码不拒整行，进 warnings。"""
    warnings: list[str] = []
    row = _row(**{"区块": "主营业务收入", "项目": "手工明细行", "本期未审": 100})
    parsed = mod._parse_d4_1_row(row, HEADERS, HEADERS, warnings)
    # 不拒整行
    assert parsed["label"] == "手工明细行"
    assert parsed["accountCode"] == ""
    # 进 warnings
    assert any("手工明细行" in w and "缺科目码" in w for w in warnings)


def test_illegal_account_code_warned_not_assigned_to_main() -> None:
    """Req 4.2：填了非 6001/6051 收入族码 → warnings，不自动归主营。"""
    warnings: list[str] = []
    row = _row(**{"区块": "主营业务收入", "项目": "疑似成本", "科目码": "640101", "本期未审": 100})
    parsed = mod._parse_d4_1_row(row, HEADERS, HEADERS, warnings)
    assert parsed["accountCode"] == "640101"  # 原样保留，不改写
    assert any("640101" in w and "非营业收入族" in w for w in warnings)


def test_account_code_status_three_states() -> None:
    """_d4_1_account_code_status 三态：空/ok/illegal。"""
    assert mod._d4_1_account_code_status("") == ""
    assert mod._d4_1_account_code_status("  ") == ""
    assert mod._d4_1_account_code_status("600101") == "ok"
    assert mod._d4_1_account_code_status("605101") == "ok"
    assert mod._d4_1_account_code_status("640101") == "illegal"


def test_reverse_illegal_code_status_not_always_ok() -> None:
    """反向自检：状态判据不恒真 —— 非法码不能被判 ok。"""
    assert mod._d4_1_account_code_status("640101") != "ok"
    assert mod._d4_1_account_code_status("") != "ok"


# ═══════════════════════════════════════════════════════════════════════════════
# _build_d4_1_import_items → 清单 + per-field 键（不写 blob）
# ═══════════════════════════════════════════════════════════════════════════════


def test_build_import_items_writes_rows_and_per_field_not_blob() -> None:
    """Req 4.1/4.4：产出 D4-1-rows 清单 + N×6 field 键；不写 D4-1-adj-rows blob。"""
    rows_data = [
        {
            "rowId": "r-1", "label": "批发", "source": "manual",
            "accountCode": "600101", "sectionKey": "main-revenue",
            "currentUnadjusted": 100, "currentAje": 1, "currentRje": 2,
            "priorUnadjusted": 90, "priorAje": 3, "priorRje": 4,
        },
        {
            "rowId": "r-2", "label": "废料", "source": "manual",
            "accountCode": "", "sectionKey": "other-revenue",
            "currentUnadjusted": 50, "currentAje": 0, "currentRje": 0,
            "priorUnadjusted": 40, "priorAje": 0, "priorRje": 0,
        },
    ]
    items = mod._build_d4_1_import_items(rows_data)
    ids = [it["item_id"] for it in items]

    # 不写旧 blob
    assert "D4-1-adj-rows" not in ids
    # 清单键
    assert "D4-1-rows" in ids
    # per-field 键：2 行 × 6 字段 = 12
    field_ids = [i for i in ids if i not in ("D4-1-rows",)]
    assert len(field_ids) == 12
    assert "D4-1-r-1-currentUnadjusted" in ids
    assert "D4-1-r-2-priorRje" in ids

    # 清单 JSON 形态 = 前端 serializeRows（accountCode/sectionKey 为空不写字段）
    rows_item = next(it for it in items if it["item_id"] == "D4-1-rows")
    row_list = json.loads(rows_item["remark"])
    assert row_list[0] == {
        "rowId": "r-1", "label": "批发", "source": "manual",
        "accountCode": "600101", "sectionKey": "main-revenue",
    }
    # r-2 accountCode 为空 → 不写该字段
    assert "accountCode" not in row_list[1]
    assert row_list[1]["sectionKey"] == "other-revenue"

    # per-field 值正确
    v = {it["item_id"]: it["remark"] for it in items}
    assert v["D4-1-r-1-currentUnadjusted"] == "100.0"
    assert v["D4-1-r-1-priorRje"] == "4.0"


def test_build_import_items_dedups_item_ids() -> None:
    """同批次重复 rowId 去重（后端整批重复 item_id 会拒绝 → 必须去重）。"""
    rows_data = [
        {"rowId": "r-1", "label": "a", "currentUnadjusted": 1},
        {"rowId": "r-1", "label": "b", "currentUnadjusted": 2},  # 重复 rowId
    ]
    items = mod._build_d4_1_import_items(rows_data)
    ids = [it["item_id"] for it in items]
    # item_id 全局唯一
    assert len(ids) == len(set(ids))
    # 只保留首次
    rows_item = next(it for it in items if it["item_id"] == "D4-1-rows")
    row_list = json.loads(rows_item["remark"])
    assert len(row_list) == 1
    assert row_list[0]["label"] == "a"


def test_build_import_items_ignores_derived_columns() -> None:
    """Req 4.3：派生列（审定数）即使塞进来也不落库（只写六字段）。"""
    rows_data = [
        {
            "rowId": "r-1", "label": "批发", "source": "manual",
            "currentUnadjusted": 100, "currentAje": 1, "currentRje": 2,
            "priorUnadjusted": 90, "priorAje": 3, "priorRje": 4,
            # 假审定数/合计/差异（不应落库）
            "currentAudited": 999999, "subtotal": 888888, "diff": 777777,
        },
    ]
    items = mod._build_d4_1_import_items(rows_data)
    field_ids = [it["item_id"] for it in items if it["item_id"] != "D4-1-rows"]
    # 只有六个金额字段键，没有派生列键
    assert len(field_ids) == 6
    for it in items:
        assert "currentAudited" not in it["item_id"]
        assert "subtotal" not in it["item_id"]
        assert "diff" not in it["item_id"]
        # 派生假值 999999/888888/777777 不出现在任何 remark
        assert "999999" not in it["remark"]
        assert "888888" not in it["remark"]
        assert "777777" not in it["remark"]


# ═══════════════════════════════════════════════════════════════════════════════
# 导出十列 + round-trip
# ═══════════════════════════════════════════════════════════════════════════════


def test_export_row_produces_ten_columns() -> None:
    """Req 4.1：导出十列，与列头一一对应。"""
    row = {
        "rowId": "r-1", "label": "批发", "source": "manual",
        "accountCode": "600101", "sectionKey": "main-revenue",
    }
    field_values = {
        "currentUnadjusted": 100, "currentAje": 1, "currentRje": 2,
        "priorUnadjusted": 90, "priorAje": 3, "priorRje": 4,
    }
    out = mod._export_d4_1_row(row, field_values)
    assert len(out) == len(HEADERS) == 10
    assert out[0] == "主营业务收入"  # 区块
    assert out[1] == "r-1"          # 行键
    assert out[2] == "批发"          # 项目
    assert out[3] == "600101"       # 科目码
    assert out[4:] == [100.0, 1.0, 2.0, 90.0, 3.0, 4.0]


def test_round_trip_field_fidelity() -> None:
    """Req 4.3：导出 → 再导入，label/accountCode/六金额/rowId/source 逐字段一致。"""
    original_rows = [
        {
            "rowId": "r-abc", "label": "批发收入", "source": "manual",
            "accountCode": "600101", "sectionKey": "main-revenue",
        },
        {
            "rowId": "r-def", "label": "废料收入", "source": "manual",
            "accountCode": "605101", "sectionKey": "other-revenue",
        },
    ]
    original_fields = {
        "r-abc": {"currentUnadjusted": 1234.5, "currentAje": 10, "currentRje": -5,
                  "priorUnadjusted": 1100, "priorAje": 8, "priorRje": 2},
        "r-def": {"currentUnadjusted": 50, "currentAje": 0, "currentRje": 0,
                  "priorUnadjusted": 40, "priorAje": 0, "priorRje": 0},
    }

    # 导出成十列行
    exported = [mod._export_d4_1_row(r, original_fields[r["rowId"]]) for r in original_rows]

    # 再导入解析
    reparsed = [mod._parse_d4_1_row(tuple(cells), HEADERS, HEADERS, None) for cells in exported]

    for orig, rp in zip(original_rows, reparsed):
        assert rp["rowId"] == orig["rowId"]
        assert rp["label"] == orig["label"]
        assert rp["source"] == orig["source"]
        assert rp["accountCode"] == orig["accountCode"]
        assert rp["sectionKey"] == orig["sectionKey"]
        of = original_fields[orig["rowId"]]
        for field in mod._D4_1_VALUE_FIELDS:
            assert rp[field] == float(of[field]), f"{orig['rowId']}.{field}"


def test_reverse_round_trip_detects_field_corruption() -> None:
    """反向自检：若导出把 accountCode 写到错列，round-trip 必然不一致。"""
    row = {"rowId": "r-1", "label": "批发", "source": "manual",
           "accountCode": "600101", "sectionKey": "main-revenue"}
    fields = {f: 0 for f in mod._D4_1_VALUE_FIELDS}
    out = mod._export_d4_1_row(row, fields)
    # 故意破坏：清空科目码列
    corrupted = list(out)
    corrupted[3] = None
    rp = mod._parse_d4_1_row(tuple(corrupted), HEADERS, HEADERS, None)
    assert rp["accountCode"] != "600101"  # 破坏后不再一致 → 判据不恒真


# ═══════════════════════════════════════════════════════════════════════════════
# 旧 blob 导出兼容回退
# ═══════════════════════════════════════════════════════════════════════════════


def test_load_export_prefers_new_keys() -> None:
    """Req 4.1：导出优先读新键 D4-1-rows + per-field。"""
    remark_by_item = {
        "D4-1-rows": json.dumps([
            {"rowId": "r-1", "label": "批发", "source": "manual",
             "accountCode": "600101", "sectionKey": "main-revenue"},
        ], ensure_ascii=False),
        "D4-1-r-1-currentUnadjusted": "100",
        "D4-1-r-1-priorUnadjusted": "90",
    }
    loaded = mod._load_d4_1_rows_for_export(remark_by_item)
    assert len(loaded) == 1
    row, fields = loaded[0]
    assert row["label"] == "批发"
    assert fields["currentUnadjusted"] == 100.0
    assert fields["priorUnadjusted"] == 90.0


def test_load_export_falls_back_to_legacy_blob() -> None:
    """Req 4.1：新键缺失时兼容回退旧 D4-1-adj-rows blob（老项目数据迁移）。"""
    legacy_blob = json.dumps([
        {
            "rowKey": "old-1", "label": "旧批发", "sectionKey": "main-revenue",
            "isFromCrossSheet": True,
            "currentUnadjusted": 500, "currentAje": 5, "currentRje": 0,
            "priorUnadjusted": 480, "priorAje": 0, "priorRje": 0,
        },
    ], ensure_ascii=False)
    remark_by_item = {"D4-1-adj-rows": legacy_blob}
    loaded = mod._load_d4_1_rows_for_export(remark_by_item)
    assert len(loaded) == 1
    row, fields = loaded[0]
    assert row["rowId"] == "old-1"
    assert row["label"] == "旧批发"
    assert row["source"] == "tb"  # isFromCrossSheet → tb
    assert row["sectionKey"] == "main-revenue"
    assert fields["currentUnadjusted"] == 500.0
    assert fields["priorUnadjusted"] == 480.0


def test_new_keys_win_over_legacy_when_both_present() -> None:
    """新键存在时忽略旧 blob（不双算）。"""
    remark_by_item = {
        "D4-1-rows": json.dumps([
            {"rowId": "r-new", "label": "新行", "source": "manual"},
        ], ensure_ascii=False),
        "D4-1-r-new-currentUnadjusted": "111",
        "D4-1-adj-rows": json.dumps([
            {"rowKey": "old", "label": "旧行", "currentUnadjusted": 999},
        ], ensure_ascii=False),
    }
    loaded = mod._load_d4_1_rows_for_export(remark_by_item)
    assert len(loaded) == 1
    assert loaded[0][0]["rowId"] == "r-new"


def test_load_export_empty_when_no_data() -> None:
    """无任何数据 → 空列表。"""
    assert mod._load_d4_1_rows_for_export({}) == []


# ═══════════════════════════════════════════════════════════════════════════════
# item_id 迁移：D4-1 不再走旧 blob 单键
# ═══════════════════════════════════════════════════════════════════════════════


def test_d4_1_no_longer_in_special_item_ids() -> None:
    """Req 4.1：D4-1 从 _SPECIAL_ITEM_IDS 移除（不再走 D4-1-adj-rows 单键）。"""
    assert "D4-1" not in mod._SPECIAL_ITEM_IDS
    # 清单键真源
    assert mod._D4_1_ROWS_ITEM_ID == "D4-1-rows"
    assert mod._D4_1_LEGACY_BLOB_ITEM_ID == "D4-1-adj-rows"


def test_field_item_id_format_matches_frontend() -> None:
    """per-field 键格式 = f"{prefix}-{rowId}-{field}"（与前端 rowFieldItemId 锁死）。"""
    assert mod._d4_1_field_item_id("r-1", "currentUnadjusted") == "D4-1-r-1-currentUnadjusted"
    assert mod._D4_1_PREFIX == "D4-1"
