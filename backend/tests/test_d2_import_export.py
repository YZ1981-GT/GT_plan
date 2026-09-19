"""D2 import/export parser tests."""
from __future__ import annotations

from app.routers.wp_render_strategies._d2_import_export import (
    D2_3_ITEM_IDS,
    SHEET_COLUMNS,
    _parse_d2_2_rows,
    _parse_d2_3_by_category,
    _parse_d2_4_rows,
    _parse_d2_7_rows,
    _parse_d2_9_rows,
    _parse_d2_10_rows,
    _validate_columns,
    _create_template_workbook,
)

def test_parse_d2_2_row_maps_fields():
    rows = _parse_d2_2_rows([{
        '序号': 1,
        '客户名称': '测试客户',
        '公司代码': 'C001',
        '关联方类型': '非关联方',
        '期初未审': 100,
        '期初AJE': 0,
        '期初RJE': 0,
        '期末未审': 200,
        '账项调整(AJE)': 10,
        '重分类调整(RJE)': 0,
        '期末审定': 210,
        '信用风险组合方式': '账龄组合',
        '是否函证': '是',
    }])
    assert len(rows) == 1
    assert rows[0]['customerName'] == '测试客户'
    assert rows[0]['currentAudited'] == 210
    assert rows[0]['isConfirmation'] is True
    assert rows[0]['creditRiskClassification'] == '账龄组合'


def test_parse_d2_9_row_computes_should_provision():
    rows = _parse_d2_9_rows([{
        '债务人名称': 'A公司',
        '审定账面余额': 1000000,
        '预期信用损失率': 0.05,
        '实际计提金额': 48000,
    }])
    assert rows[0]['shouldProvision'] == 50000
    assert rows[0]['difference'] == -2000


def test_parse_d2_10_migration_matrix():
    rows = _parse_d2_10_rows([{
        '账龄段': '1年以内',
        '年度1迁徙率': 0.1,
        '年度2迁徙率': 0.2,
        '年度3迁徙率': 0.3,
    }])
    assert abs(rows[0]['avgRate'] - 0.2) < 1e-9
    assert abs(rows[0]['expectedLossRate'] - 0.006) < 1e-9


def test_validate_columns_rejects_unknown():
    wb = _create_template_workbook('D2-2')
    ws = wb.active
    ws.delete_rows(1)
    ws.append(['错误列名', '客户名称'])
    invalid = _validate_columns(ws, 'D2-2')
    assert '错误列名' in invalid


def test_parse_d2_4_maps_adjustment_fields():
    rows = _parse_d2_4_rows([{
        '序号': 1, '类型': 'AJE', '借方科目': '应收账款', '贷方科目': '坏账准备',
        '借方金额': 1000, '贷方金额': 1000, '摘要': '补提坏账', '日期': '2025-12-31',
        '编制人': '张三', '备注': '测试',
    }])
    assert rows[0]['description'] == '补提坏账'
    assert rows[0]['entryType'] == 'AJE'
    assert rows[0]['debitAmount'] == 1000
    assert rows[0]['accountName'] == '应收账款'
    assert '日期:2025-12-31' in rows[0]['remark']


def test_parse_d2_7_maps_voucher_fields():
    rows = _parse_d2_7_rows([{
        '序号': 2, '客户名称': '甲公司', '日期': '2025-06-01', '凭证编号': '记-001',
        '业务内容': '销售回款', '对方科目': '银行存款', '借方金额': 50000,
        '原始凭证齐全': '是', '是否异常': '否', '记录期间正确': '是', '结论': '无异常',
    }])
    assert rows[0]['counterparty'] == '甲公司'
    assert rows[0]['voucherNo'] == '记-001'
    assert rows[0]['amount'] == 50000
    assert rows[0]['hasOriginal'] == 'Y'
    assert rows[0]['isCutoff'] is False


def test_parse_d2_3_splits_by_category():
    result = _parse_d2_3_by_category([
        {
            '项目': '客户A', '分类': '单项计提',
            '期初审定': 100, '本期计提': 10, '期末审定': 110,
        },
        {
            '项目': '组合B', '分类': '账龄组合',
            '期初审定': 200, '本期计提': 20, '期末审定': 220,
        },
    ])
    assert set(result.keys()) == set(D2_3_ITEM_IDS.values())
    ind = result[D2_3_ITEM_IDS['individual']]
    assert any(r['label'] == '客户A' and r['isSubRow'] for r in ind)
    assert any(r['isFixed'] for r in ind)
    aging = result[D2_3_ITEM_IDS['aging']]
    assert any(r['label'] == '组合B' for r in aging)
    cust = result[D2_3_ITEM_IDS['customer-type']]
    assert len(cust) >= 1
    assert cust[0]['isFixed']


def test_sheet_columns_d2_10_has_six_headers():
    assert len(SHEET_COLUMNS['D2-10']) == 6
