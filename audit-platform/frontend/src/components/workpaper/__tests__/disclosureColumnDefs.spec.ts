/**
 * disclosureColumnDefs — 客户端兜底投影与后端 project_sub_tables 规则一致性
 * spec: disclosure-table-sync-convergence Task 2.2（P2~P8 关键用例镜像后端）
 */
import { describe, it, expect } from 'vitest'
import { defineColumns, projectSubTablesClient, deriveLegacyTableHeaders } from '../composables/disclosureColumnDefs'

function makeTd(withColumns = true, source = 'workpaper') {
  const td: Record<string, any> = {
    _source: source,
    sub_table_data: {
      存货分类: [
        { label: '原材料', end_gross: 100, end_impairment: 5 },
        { label: '库存商品', end_gross: 200, end_impairment: 10 },
        { label: '合计', end_gross: 300, end_impairment: 15, is_total: true },
      ],
    },
  }
  if (withColumns) {
    td._sub_table_columns = {
      存货分类: [
        { key: 'label', label: '存货类别', is_label: true },
        { key: 'end_gross', label: '期末账面余额' },
        { key: 'end_impairment', label: '期末跌价准备' },
      ],
    }
  }
  return td
}

describe('projectSubTablesClient', () => {
  it('P1 纯函数：不修改入参', () => {
    const td = makeTd()
    const snap = JSON.parse(JSON.stringify(td))
    projectSubTablesClient(td)
    expect(td).toEqual(snap)
  })

  it('P2 列序保持 + label 列置首', () => {
    const tables = projectSubTablesClient(makeTd())!
    expect(tables[0].headers).toEqual(['存货类别', '期末账面余额', '期末跌价准备'])
  })

  it('P2 label 由 is_label 决定而非位置', () => {
    const td = {
      _source: 'workpaper',
      sub_table_data: { t: [{ a: 1, label: '行1', b: 2 }] },
      _sub_table_columns: {
        t: [
          { key: 'a', label: '甲' },
          { key: 'label', label: '名称', is_label: true },
          { key: 'b', label: '乙' },
        ],
      },
    }
    const tables = projectSubTablesClient(td)!
    expect(tables[0].headers).toEqual(['名称', '甲', '乙'])
    expect(tables[0].rows[0].label).toBe('行1')
    expect(tables[0].rows[0].values).toEqual([1, 2])
  })

  it('P3 缺字段空单元不丢列', () => {
    const td = {
      _source: 'workpaper',
      sub_table_data: { t: [{ label: '行1', end_gross: 100 }] },
      _sub_table_columns: {
        t: [
          { key: 'label', label: '类别', is_label: true },
          { key: 'end_gross', label: '余额' },
          { key: 'end_impairment', label: '减值' },
        ],
      },
    }
    const tables = projectSubTablesClient(td)!
    expect(tables[0].headers).toEqual(['类别', '余额', '减值'])
    expect(tables[0].rows[0].values).toEqual([100, null])
  })

  it('P4 额外字段忽略', () => {
    const td = {
      _source: 'workpaper',
      sub_table_data: { t: [{ label: '行1', end_gross: 100, extra_x: 999 }] },
      _sub_table_columns: {
        t: [
          { key: 'label', label: '类别', is_label: true },
          { key: 'end_gross', label: '余额' },
        ],
      },
    }
    const tables = projectSubTablesClient(td)!
    expect(tables[0].headers).toEqual(['类别', '余额'])
    expect(tables[0].rows[0].values).toEqual([100])
  })

  it('P5 合计行保持', () => {
    const tables = projectSubTablesClient(makeTd())!
    expect(tables[0].rows[tables[0].rows.length - 1].is_total).toBe(true)
    expect(tables[0].rows[0].is_total).toBe(false)
  })

  it('P6 多表键序 + 跳过元数据键', () => {
    const td = {
      _source: 'workpaper',
      sub_table_data: {
        表A: [{ label: 'a' }],
        表B: [{ label: 'b' }],
        表C: [{ label: 'c' }],
        _note_texts: [{ text: 'meta' }],
      },
      _sub_table_columns: {
        表A: [{ key: 'label', label: 'L', is_label: true }],
        表B: [{ key: 'label', label: 'L', is_label: true }],
        表C: [{ key: 'label', label: 'L', is_label: true }],
      },
    }
    const tables = projectSubTablesClient(td)!
    expect(tables.map(t => t.name)).toEqual(['表A', '表B', '表C'])
  })

  it('P7 非 workpaper 来源 → null', () => {
    expect(projectSubTablesClient(makeTd(true, 'engine_fill'))).toBeNull()
    expect(projectSubTablesClient({ sub_table_data: { t: [{ label: 'x' }] } })).toBeNull()
    expect(projectSubTablesClient(null)).toBeNull()
    expect(projectSubTablesClient([] as any)).toBeNull()
  })

  it('P7 workpaper 来源但空 sub → []', () => {
    expect(projectSubTablesClient({ _source: 'workpaper', sub_table_data: {} })).toEqual([])
    expect(projectSubTablesClient({ _source: 'workpaper_html', sub_table_data: {} })).toEqual([])
  })

  it('P8 降级不用英文字段键当 header', () => {
    const tables = projectSubTablesClient(makeTd(false))!
    expect(tables).toHaveLength(1)
    const t = tables[0]
    expect(t._needs_columns).toBe(true)
    expect(t.headers).toEqual(['项目'])
    for (const h of t.headers) {
      expect(['end_gross', 'end_impairment', 'label', 'is_total']).not.toContain(h)
    }
    expect(t.rows.every(r => r.values.length === 0)).toBe(true)
    expect(t.rows[t.rows.length - 1].is_total).toBe(true)
  })

  it('P8 无 label 无 columns → 空表头', () => {
    const td = { _source: 'workpaper', sub_table_data: { t: [{ amount: 1 }] } }
    const tables = projectSubTablesClient(td)!
    expect(tables[0].headers).toEqual([])
  })
})

describe('defineColumns', () => {
  it('过滤无 key 项并规范化标志位', () => {
    const cols = defineColumns([
      { key: 'label', label: '类别', is_label: true },
      { key: '', label: '空' } as any,
      { key: 'v', label: '值', format: 'amount' },
    ])
    expect(cols.map(c => c.key)).toEqual(['label', 'v'])
    expect(cols[0].is_label).toBe(true)
    expect(cols[1].format).toBe('amount')
    expect(cols[1].is_label).toBeUndefined()
  })
})

describe('deriveLegacyTableHeaders', () => {
  const row = (label: string, values: any[], semantics: (string | null)[]) => ({
    label,
    values,
    _cell_meta: Object.fromEntries(semantics.map((s, i) => [String(i), { semantic: s }])),
  })

  it('货币资金式两列 → [项目, 期末余额, 上年年末余额]', () => {
    const td = { headers: [], rows: [row('库存现金', [376.73, null], ['closing_balance', 'prior_year_value'])] }
    expect(deriveLegacyTableHeaders(td)).toEqual(['项目', '期末余额', '上年年末余额'])
  })

  it('变动表四列 期初/增/减/期末', () => {
    const td = { headers: [], rows: [row('A', [1, 2, 3, 4], ['opening_balance', 'current_year_increase', 'current_year_decrease', 'closing_balance'])] }
    expect(deriveLegacyTableHeaders(td)).toEqual(['项目', '期初余额', '本期增加', '本期减少', '期末余额'])
  })

  it('无语义值列 → 空标签但列保留', () => {
    const td = { headers: [], rows: [row('X', [1, 2], ['closing_balance', null])] }
    expect(deriveLegacyTableHeaders(td)).toEqual(['项目', '期末余额', ''])
  })

  it('无 _cell_meta 按 values 长度出空标签列头', () => {
    expect(deriveLegacyTableHeaders({ headers: [], rows: [{ label: 'X', values: [1, 2] }] })).toEqual(['项目', '', ''])
  })

  it('无值列 → 仅标签列', () => {
    expect(deriveLegacyTableHeaders({ headers: [], rows: [{ label: '条款', values: [] }] })).toEqual(['项目'])
  })

  it('已有表头不改动 → null', () => {
    expect(deriveLegacyTableHeaders({ headers: ['项目', '金额'], rows: [row('A', [1], ['cost'])] })).toBeNull()
  })

  it('多表/空行/非对象 → null', () => {
    expect(deriveLegacyTableHeaders({ headers: [], _tables: [{}], rows: [row('A', [1], ['cost'])] })).toBeNull()
    expect(deriveLegacyTableHeaders({ headers: [], rows: [] })).toBeNull()
    expect(deriveLegacyTableHeaders(null)).toBeNull()
  })

  it('列数取所有行最大 values 长度', () => {
    const td = { headers: [], rows: [{ label: 'A', values: [1] }, row('B', [1, 2, 3], ['cost', 'closing_balance', 'prior_year_value'])] }
    expect(deriveLegacyTableHeaders(td)).toEqual(['项目', '成本', '期末余额', '上年年末余额'])
  })
})
