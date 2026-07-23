"""K1-9 转回/核销检查 — 导入导出行映射单元测试."""

from __future__ import annotations

from app.routers.wp_render_strategies._k1_import_export import (
    _K1_9_HEADERS,
    _k1_9_export_rows,
    _k1_9_parse_row,
)


def test_k1_9_headers_present():
    assert '类别' in _K1_9_HEADERS
    assert '单位名称' in _K1_9_HEADERS


def test_k1_9_parse_reversal_row():
    headers = _K1_9_HEADERS
    row = (
        '转回', '示例单位', '收回货款', '银行转账', '账龄较长',
        10000, 12000, '合理', '分析', 'IDX-1',
    )
    kind, parsed = _k1_9_parse_row(row, headers)
    assert kind == 'reversal'
    assert parsed['unit'] == '示例单位'
    assert parsed['amount'] == 10000
    assert parsed['accumProvision'] == 12000


def test_k1_9_parse_writeoff_row():
    headers = _K1_9_HEADERS
    row = (
        '核销', '示例单位', '无法收回', '', '',
        5000, '', '押金', '审批', '否', '合理', '分析', 'IDX-2',
    )
    kind, parsed = _k1_9_parse_row(row, headers)
    assert kind == 'writeoff'
    assert parsed['nature'] == '押金'
    assert parsed['relatedParty'] == '否'
    assert parsed['amount'] == 5000


def test_k1_9_export_rows_dual_section():
    payload = {
        'tables': {
            'reversal': [{
                'unit': 'A公司',
                'reason': '收回',
                'method': '转账',
                'basis': '账龄',
                'amount': 1000,
                'accumProvision': 1500,
                'isReasonable': '合理',
                'analysis': '',
                'indexNo': '',
            }],
            'writeoff': [{
                'unit': 'B公司',
                'reason': '核销',
                'nature': '押金',
                'procedure': '审批',
                'relatedParty': '否',
                'amount': 800,
                'isReasonable': '合理',
                'analysis': '',
                'indexNo': '',
            }],
        },
    }
    rows = _k1_9_export_rows(payload)
    assert len(rows) == 2
    assert rows[0][0] == '转回'
    assert rows[1][0] == '核销'
