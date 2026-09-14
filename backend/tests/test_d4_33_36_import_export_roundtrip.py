# -*- coding: utf-8 -*-
"""D4-33/34/35/36 其他业务收入组导入导出往返守卫（纯函数级，不连库）。

锁定 spec d4-33-36-writeback-formula-and-io-closure 的 Requirement 1 行为：
- 6 个专用 parser 产出结构逐字段对齐前端类型（Requirement 1.1/1.2/1.3/1.4）
- export 行构造 → parser 回读，录入字段逐字段一致（round-trip，Requirement 1.8）
- D4-34 两区合并写回不互相覆盖、D4-35 sampling/periodAmount 不被行导入冲掉（Property 3）
- D4-36 backward 按列头名映射不交叉错位（Requirement 1.4）
- 空金额往返保持空串不写 0（Requirement 1.7 / Property 1）

断言的是**行为/结构**（字段值、重算结果、往返一致），非"函数存在"。
"""
from pathlib import Path

from app.routers.wp_render_strategies import _d4_import_export as m

_SRC = Path(m.__file__).read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# D4-33 毛利率分析：{bizTypes, months, priorYear} 嵌套 store（Requirement 1.1）
# ═══════════════════════════════════════════════════════════════════════════

def _d4_33_sample_store() -> dict:
    biz = [{"id": "biz-a", "name": "出租固定资产"}, {"id": "biz-b", "name": "销售材料"}]
    months = {
        "biz-a": [{"revenue": (i + 1) * 100, "cost": (i + 1) * 60} for i in range(12)],
        "biz-b": [{"revenue": (i + 1) * 50, "cost": (i + 1) * 30} for i in range(12)],
    }
    prior = {"biz-a": {"revenue": 1000, "cost": 600}, "biz-b": {"revenue": 500, "cost": 300}}
    return {"bizTypes": biz, "months": months, "priorYear": prior}


def test_d4_33_dynamic_headers_follow_biz_types():
    """列头随实际业务类型动态生成（月份 + 合计3 + 每业务3）。"""
    store = _d4_33_sample_store()
    headers = m._d4_33_dynamic_headers(store["bizTypes"])
    assert headers[:4] == ["月份", "合计-收入", "合计-成本", "合计-毛利率"]
    assert "出租固定资产-收入" in headers and "出租固定资产-毛利率" in headers
    assert "销售材料-成本" in headers
    # 2 业务 → 4 固定 + 2*3 = 10 列
    assert len(headers) == 10


def test_d4_33_roundtrip_via_openpyxl():
    """D4-33 export 展开 16 行 → parse 每行 → rebuild store：12月+上年数录入值逐字段一致。"""
    from openpyxl import Workbook

    store = _d4_33_sample_store()
    wb = Workbook()
    ws = wb.active
    headers = m._d4_33_dynamic_headers(store["bizTypes"])
    ws.append(headers)
    m._write_d4_33_rows(ws, store["bizTypes"], store["months"], store["priorYear"])

    # 读回：首行列头 + 数据行
    all_rows = list(ws.iter_rows(values_only=True))
    actual_headers = [str(h).strip() if h is not None else "" for h in all_rows[0]]
    parsed = []
    for r in all_rows[1:]:
        d = m._parse_d4_33_row(r, actual_headers)
        if d:
            parsed.append(d)
    rebuilt = m._rebuild_d4_33_store(parsed, actual_headers)

    # 业务类型名保序
    assert [b["name"] for b in rebuilt["bizTypes"]] == ["出租固定资产", "销售材料"]
    # 12 月录入值逐字段一致（用 name 对齐，id 会被重命名）
    name_to_id_src = {b["name"]: b["id"] for b in store["bizTypes"]}
    name_to_id_new = {b["name"]: b["id"] for b in rebuilt["bizTypes"]}
    for name in ("出租固定资产", "销售材料"):
        src_months = store["months"][name_to_id_src[name]]
        new_months = rebuilt["months"][name_to_id_new[name]]
        for i in range(12):
            assert float(new_months[i]["revenue"]) == float(src_months[i]["revenue"]), f"{name} 第{i+1}月收入"
            assert float(new_months[i]["cost"]) == float(src_months[i]["cost"]), f"{name} 第{i+1}月成本"
        # 上年数
        src_prior = store["priorYear"][name_to_id_src[name]]
        new_prior = rebuilt["priorYear"][name_to_id_new[name]]
        assert float(new_prior["revenue"]) == float(src_prior["revenue"])
        assert float(new_prior["cost"]) == float(src_prior["cost"])


def test_d4_33_margin_is_percentage():
    """毛利率百分比口径：(rev-cost)/rev*100（Property 5，防回归小数比率）。"""
    assert m._fmt_margin_pct(1000, 600) == 40.0  # (1000-600)/1000*100 = 40
    assert m._fmt_margin_pct(0, 100) == 0.0       # 收入 0 → 0


# ═══════════════════════════════════════════════════════════════════════════
# D4-34 合同测算：两区 RentalRow / ConsultRow（Requirement 1.2）
# ═══════════════════════════════════════════════════════════════════════════

def test_parse_d4_34_rental_row_fields_and_recalc():
    headers = m._SHEET_HEADERS["D4-34-rental"]
    # 序号/承租方/租赁期间/租赁面积/合同单价/合同索引/本期实际租赁月数/本期应计收入/本期实计收入/差异/索引号
    row = ("1", "甲公司", "2024全年", "100", 50.0, "HT-1", "12", 60000.0, 58000.0, 999999.0, "IDX-R1")
    d = m._parse_d4_34_rental_row(row, headers)
    assert d["tenant"] == "甲公司"
    assert d["period"] == "2024全年"
    assert d["unitPrice"] == 50.0
    assert d["expectedRevenue"] == 60000.0
    assert d["actualRevenue"] == 58000.0
    # 差异重算（忽略文件里 999999），= actual - expected
    assert d["diff"] == 58000.0 - 60000.0 == -2000.0
    assert d["indexRef"] == "IDX-R1"
    assert "承租方" not in d  # 无中文 key 泄漏


def test_parse_d4_34_consult_row_fields_and_recalc():
    headers = m._SHEET_HEADERS["D4-34-consult"]
    # 序号/委托方/咨询项目/委托期限/合同金额/合同索引/本期应计收入/本期实计收入/差异/索引号
    row = ("1", "乙公司", "尽调项目", "6个月", 120000.0, "HT-2", 60000.0, 60000.0, 0.0, "IDX-C1")
    d = m._parse_d4_34_consult_row(row, headers)
    assert d["client"] == "乙公司"
    assert d["project"] == "尽调项目"
    assert d["contractAmount"] == 120000.0
    assert d["diff"] == 0.0
    assert d["indexRef"] == "IDX-C1"


def test_d4_34_merge_writeback_preserves_other_region():
    """🔴 Property 3：合并写回逻辑源码断言——rental 导入保留 consults，反之亦然。

    合并逻辑在 import 端点内联（读旧 → 合并 → 写回），此处以源码结构 + 语义断言锁定：
    源码必须对 D4-34-rental 只替换 rentals、对 D4-34-consult 只替换 consults。
    """
    # 源码含合并写回分支（读既有 → 合并另一区）
    assert 'merged = {"rentals": rows_data, "consults": existing_data.get("consults", [])}' in _SRC
    assert 'merged = {"rentals": existing_data.get("rentals", []), "consults": rows_data}' in _SRC


# ═══════════════════════════════════════════════════════════════════════════
# D4-35 检查表：{rows, sampling, periodAmount}（Requirement 1.3）
# ═══════════════════════════════════════════════════════════════════════════

def test_parse_d4_35_row_string_isanomalous_and_blank_amount():
    headers = m._SHEET_HEADERS["D4-35"]
    # 日期/凭证编号/业务内容/对方科目/明细科目/金额/支持性文件/核对1..6/索引号/是否异常/备注说明
    row = ("2024-03-01", "PZ-9", "材料销售", "银行存款", "其他业务收入", 12000.0, "发票",
           "√", "√", "", "√", "", "", "IDX-1", "是", "大额关注")
    d = m._parse_d4_35_row(row, headers)
    assert d["voucherNo"] == "PZ-9"
    assert d["amount"] == 12000.0
    assert d["check1"] == "√" and d["check3"] == "" and d["check4"] == "√"
    # isAnomalous 保持 string，不转 boolean
    assert d["isAnomalous"] == "是"
    assert isinstance(d["isAnomalous"], str)
    assert d["remark"] == "大额关注"


def test_parse_d4_35_blank_amount_stays_blank():
    """空金额保持空串，不写 0（Requirement 1.7）。"""
    headers = m._SHEET_HEADERS["D4-35"]
    row = ("2024-03-02", "PZ-10", "服务", "", "", None, "", "", "", "", "", "", "", "", "否", "")
    d = m._parse_d4_35_row(row, headers)
    assert d["amount"] == ""  # 不是 0
    assert d["isAnomalous"] == "否"


def test_d4_35_sampling_protected_in_merge():
    """🔴 Property 3 / 变异⑫：D4-35 合并写回保留 sampling/periodAmount（不被行导入冲掉）。"""
    assert 'existing_data.get("sampling", {})' in _SRC
    assert 'existing_data.get("periodAmount", "")' in _SRC


# ═══════════════════════════════════════════════════════════════════════════
# D4-36 截止性测试：两区，backward 列头顺序相反（Requirement 1.4）
# ═══════════════════════════════════════════════════════════════════════════

def test_parse_d4_36_forward_row_by_header_name():
    headers = m._SHEET_HEADERS["D4-36-forward"]
    # 凭证日期/编号/品名/数量/金额 | 单据日期/编号/品名/数量/金额 | 是否跨期
    row = ("2024-12-30", "PZ-1", "甲", "10", 5000.0, "2025-01-03", "FH-1", "甲", "10", 5000.0, "")
    d = m._parse_d4_36_forward_row(row, headers)
    assert d["voucherDate"] == "2024-12-30"
    assert d["voucherAmount"] == 5000.0
    assert d["docDate"] == "2025-01-03"
    assert d["docNo"] == "FH-1"
    assert d["isCrossing"] == ""  # 派生留空由前端重算


def test_parse_d4_36_backward_by_header_name_not_position():
    """🔴 backward 列头顺序（单据在前、凭证在后）与 forward 相反，必须按列头名映射不交叉错位。"""
    headers = m._SHEET_HEADERS["D4-36-backward"]
    # backward 列头：单据日期/编号/品名/数量/金额 | 凭证日期/编号/品名/数量/金额 | 是否跨期
    assert headers[0] == "单据日期" and headers[5] == "凭证日期"
    # 单据在前列，凭证在后列
    row = ("2024-12-29", "FH-9", "乙", "5", 8000.0, "2025-01-05", "PZ-9", "乙", "5", 8000.0, "")
    d = m._parse_d4_36_backward_row(row, headers)
    # 关键：voucherDate 取到的是「凭证日期」列（第6列 2025-01-05），不是第1列
    assert d["voucherDate"] == "2025-01-05", "backward 必须按列头名取凭证日期，非列序"
    assert d["voucherNo"] == "PZ-9"
    assert d["docDate"] == "2024-12-29"  # 单据日期在第1列
    assert d["docNo"] == "FH-9"
    # voucherAmount 与 docAmount 不互换（本例相等，改用不同值再验）
    row2 = ("2024-12-29", "FH-9", "乙", "5", 8000.0, "2025-01-05", "PZ-9", "乙", "5", 3000.0, "")
    d2 = m._parse_d4_36_backward_row(row2, headers)
    assert d2["docAmount"] == 8000.0   # 单据金额（第5列）
    assert d2["voucherAmount"] == 3000.0  # 凭证金额（第10列）


def test_d4_36_merge_writeback_preserves_other_region():
    """🔴 Property 3：D4-36 forward 导入保留 backward，反之亦然。"""
    assert 'merged["forward"] = rows_data' in _SRC
    assert 'merged["backward"] = rows_data' in _SRC


def test_d4_36_forward_backward_roundtrip_symmetric():
    """两区 export 行构造 → parse 回读，voucher*/doc* 不因列序错位。"""
    fwd_headers = m._SHEET_HEADERS["D4-36-forward"]
    bwd_headers = m._SHEET_HEADERS["D4-36-backward"]
    src = {
        "voucherDate": "2024-12-31", "voucherNo": "PZ-A", "voucherProduct": "X", "voucherQty": "3", "voucherAmount": 1000.0,
        "docDate": "2025-01-02", "docNo": "FH-A", "docProduct": "X", "docQty": "3", "docAmount": 2000.0, "isCrossing": "×",
    }
    # forward 往返
    fwd_row = m._export_d4_36_forward_row(src)
    d_fwd = m._parse_d4_36_forward_row(tuple(fwd_row), fwd_headers)
    assert d_fwd["voucherAmount"] == 1000.0 and d_fwd["docAmount"] == 2000.0
    assert d_fwd["voucherNo"] == "PZ-A" and d_fwd["docNo"] == "FH-A"
    # backward 往返（列序相反但字段对齐）
    bwd_row = m._export_d4_36_backward_row(src)
    d_bwd = m._parse_d4_36_backward_row(tuple(bwd_row), bwd_headers)
    assert d_bwd["voucherAmount"] == 1000.0 and d_bwd["docAmount"] == 2000.0
    assert d_bwd["voucherNo"] == "PZ-A" and d_bwd["docNo"] == "FH-A"


# ═══════════════════════════════════════════════════════════════════════════
# 分发接线：四表走专用 parser 而非 generic（Requirement 1）
# ═══════════════════════════════════════════════════════════════════════════

def test_import_dispatch_uses_dedicated_parsers():
    import re
    assert re.search(r'elif sheet == "D4-33":\s*\n\s*row_dict = _parse_d4_33_row', _SRC)
    assert re.search(r'elif sheet == "D4-34-rental":\s*\n\s*row_dict = _parse_d4_34_rental_row', _SRC)
    assert re.search(r'elif sheet == "D4-34-consult":\s*\n\s*row_dict = _parse_d4_34_consult_row', _SRC)
    assert re.search(r'elif sheet == "D4-35":\s*\n\s*row_dict = _parse_d4_35_row', _SRC)
    assert re.search(r'elif sheet == "D4-36-forward":\s*\n\s*row_dict = _parse_d4_36_forward_row', _SRC)
    assert re.search(r'elif sheet == "D4-36-backward":\s*\n\s*row_dict = _parse_d4_36_backward_row', _SRC)
