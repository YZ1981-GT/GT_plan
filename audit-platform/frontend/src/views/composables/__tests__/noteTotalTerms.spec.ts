/**
 * noteTotalTerms — 附注合计构成（spec note-pull-header-formula-closure R5）
 *
 * 前后端交叉锁：后端 `note_total_terms.total_terms` / `note_formula_tables.amount_columns` 按单体 / 合并模板逐表算出的
 * golden（`backend/data/note_total_terms_golden.json`，`gen_note_total_terms_golden.py --write` 生成、后端
 * `test_note_total_terms.py` 守卫与现算一致）在这里逐表对照前端实现。任一侧改判定，另一侧必红。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import {
  RATIO_PATTERN,
  TEXT_PATTERN,
  amountColumns,
  columnTotalUpdates,
  labelRowType,
  recalcConsolTotalRows,
  recalcNoteTableTotals,
  totalMismatch,
  totalTerms,
  type TotalTermsResult,
} from '../noteTotalTerms'

const DATA = resolve(__dirname, '../../../../../../backend/data')
const load = (name: string) => JSON.parse(readFileSync(resolve(DATA, name), 'utf-8'))

interface GoldenEntry {
  key: string
  plans: Record<string, number[][]>
  reasons: number[]
  amount_columns: number[]
  rows?: number
  types?: Record<string, string>
  column_groups?: unknown
}
const GOLDEN = load('note_total_terms_golden.json') as {
  ratio_pattern: string
  text_pattern: string
  single: GoldenEntry[]
  consol: GoldenEntry[]
  label_types: Record<string, string>
}

function shape(result: TotalTermsResult) {
  const plans: Record<string, number[][]> = {}
  for (const [k, v] of [...result.plans.entries()].sort((a, b) => a[0] - b[0])) plans[String(k)] = v.map(([r, s]) => [r, s])
  return { plans, reasons: [...result.reasons.keys()].sort((a, b) => a - b) }
}

describe('golden 交叉锁（后端逐表现算）', () => {
  it('比例 / 说明列规则与标题行库词表逐字一致', () => {
    expect(RATIO_PATTERN).toBe(GOLDEN.ratio_pattern)
    expect(TEXT_PATTERN).toBe(GOLDEN.text_pattern)
  })

  it('单体模板逐表：合计构成、判不准的行、金额列与后端一致', () => {
    const templates: Record<string, any> = { soe: load('note_template_soe.json'), listed: load('note_template_listed.json') }
    const diffs: string[] = []
    for (const g of GOLDEN.single) {
      const [tt, si, ti] = g.key.split('|')
      const table = templates[tt].sections[Number(si)].tables[Number(ti)]
      const got = shape(totalTerms(table.rows))
      if (JSON.stringify(got.plans) !== JSON.stringify(g.plans) || JSON.stringify(got.reasons) !== JSON.stringify(g.reasons)) {
        diffs.push(`${g.key} 构成 ${JSON.stringify(got)} ≠ ${JSON.stringify({ plans: g.plans, reasons: g.reasons })}`)
      }
      const cols = amountColumns(table)
      if (JSON.stringify(cols) !== JSON.stringify(g.amount_columns)) diffs.push(`${g.key} 金额列 ${cols} ≠ ${g.amount_columns}`)
    }
    expect(GOLDEN.single.length).toBeGreaterThan(500)
    expect(diffs.slice(0, 5)).toEqual([])
  })

  it('合并模板逐表：按后端补齐的行类型算出的合计构成与金额列一致', () => {
    const sections: Record<string, Map<string, any>> = {}
    for (const tt of ['soe', 'listed']) {
      sections[tt] = new Map((load(`consol_note_sections_${tt}.json`) as any[]).map((s) => [s.section_id, s]))
    }
    const diffs: string[] = []
    for (const g of GOLDEN.consol) {
      const [tt, sid] = g.key.split('|')
      const raw = sections[tt].get(sid)
      const rows = (raw.rows as unknown[][]).map((r, i) => ({ label: String(r?.[0] ?? ''), row_type: g.types?.[String(i)] ?? 'data' }))
      expect(rows.length).toBe(g.rows)
      const got = shape(totalTerms(rows))
      if (JSON.stringify(got.plans) !== JSON.stringify(g.plans) || JSON.stringify(got.reasons) !== JSON.stringify(g.reasons)) {
        diffs.push(`${g.key} 构成 ${JSON.stringify(got)} ≠ ${JSON.stringify({ plans: g.plans, reasons: g.reasons })}`)
      }
      const cols = amountColumns({ headers: raw.headers, multi_header: raw.multi_header, _column_groups: g.column_groups })
      if (JSON.stringify(cols) !== JSON.stringify(g.amount_columns)) diffs.push(`${g.key} 金额列 ${cols} ≠ ${g.amount_columns}`)
    }
    expect(GOLDEN.consol.length).toBeGreaterThan(300)
    expect(diffs.slice(0, 5)).toEqual([])
  })

  it('合并模板行名的行类型（以「小计」结尾 = 小计，先于合计判）与后端一致', () => {
    const diffs: string[] = []
    let seen = 0
    for (const tt of ['soe', 'listed']) {
      for (const s of load(`consol_note_sections_${tt}.json`) as any[]) {
        for (const r of s.rows as unknown[][]) {
          const text = String(r?.[0] ?? '')
          const want = GOLDEN.label_types[text] ?? 'data'
          if (labelRowType(text) !== want) diffs.push(`${text}: ${labelRowType(text)} ≠ ${want}`)
          seen++
        }
      }
    }
    expect(seen).toBeGreaterThan(3000)
    expect(Object.values(GOLDEN.label_types)).toContain('subtotal')
    expect(diffs.slice(0, 5)).toEqual([])
  })
})

type TestRow = { label: string; values: unknown[] } & Record<string, unknown>
const row = (label: string, values: unknown[], extra: Record<string, unknown> = {}): TestRow => ({ label, values, ...extra })
const total = (label: string, values: unknown[], extra: Record<string, unknown> = {}) =>
  row(label, values, { is_total: true, row_type: label.includes('小计') ? 'subtotal' : 'total', ...extra })

describe('合计构成', () => {
  it('标题式小计表删空了一组：那组小计判不准、合计 = 各小计；续表「小计 / 减 / 合计」不是标题式', () => {
    const sub = (label: string) => ({ label, row_type: 'subtotal', is_total: true })
    const got = totalTerms([sub('商业承兑汇票小计'), { label: '甲' }, sub('银行承兑汇票小计'), { label: '合计', is_total: true }])
    expect(shape(got)).toEqual({ plans: { 0: [[1, 1]], 3: [[0, 1], [2, 1]] }, reasons: [2] })
    const cont = totalTerms([sub('小计'), { label: '减：一年内到期' }, { label: '合计', is_total: true }])
    expect(shape(cont)).toEqual({ plans: { 2: [[0, 1], [1, -1]] }, reasons: [0] })
  })

  it('段首合计（R7）：每个「一、…合计」= 本段明细；段内「其中：X」只许是第一行；坏段单独判不准', () => {
    const tot = (label: string) => ({ label, row_type: 'total', is_total: true })
    const sub = (label: string) => ({ label, row_type: 'subtotal', is_total: true })
    const got = totalTerms([tot('一、账面原值合计'), { label: '其中：土地资产' }, { label: '房屋、建筑物' }, { label: '……' },
      tot('二、累计折旧合计'), { label: '1、房屋、建筑物' }, { label: '2、土地使用权' }])
    expect(shape(got)).toEqual({ plans: { 0: [[1, 1], [2, 1]], 4: [[5, 1], [6, 1]] }, reasons: [] })
    const bads: Array<[Array<Record<string, unknown>>, string]> = [
      [[{ label: '房屋' }, { label: '其中：境外' }], '其中'],
      [[{ label: '其中：' }, { label: '房屋' }], '其中'],
      [[{ label: '房屋' }, { label: '减：减值准备' }], '减项'],
      [[{ label: '房屋' }, { label: '（一）境外' }], '分段标题'],
      [[], '没有可合计的明细行'],
    ]
    for (const [bad, reason] of bads) {
      const r = totalTerms([tot('一、原价合计'), ...bad, tot('二、累计摊销合计'), { label: '专利权' }, { label: '软件' }])
      const second = bad.length + 1
      expect([...r.reasons.keys()]).toEqual([0])
      expect(r.reasons.get(0)).toContain(reason)
      expect(shape(r).plans).toEqual({ [second]: [[second + 1, 1], [second + 2, 1]] })
    }
    // 不是这种形态：第一行不是合计 / 有合计不是分段标题式 / 有小计 ⇒ 照旧整表判不准
    for (const rows of [
      [{ label: '流动资产' }, tot('一、资产合计'), { label: '流动负债' }, tot('二、负债合计')],
      [tot('一、成本合计'), { label: '房屋' }, tot('合计'), { label: '土地' }],
      [tot('一、成本合计'), { label: '房屋' }, sub('（一）小计'), { label: '土地' }],
    ]) {
      const r = totalTerms(rows)
      expect(r.plans.size).toBe(0)
      expect([...r.reasons.values()][0]).toContain('多个合计')
    }
    expect(shape(totalTerms([tot('一、成本合计'), { label: '房屋' }, { label: '土地' }])).plans).toEqual({ 0: [[1, 1], [2, 1]] })
    expect(shape(totalTerms([tot('合计'), { label: '房屋' }, { label: '土地' }]))).toEqual({ plans: {}, reasons: [0] })
  })
})

describe('单体附注合计回填', () => {
  it('多段小计各算各的，合计 = 各小计（旧实现每个合计都等于全表之和）', () => {
    const table = {
      headers: ['项目', '期末余额', '期初余额'],
      rows: [row('合营企业', [10, 1]), row('', [5, null]), total('小计', [null, null]),
        row('联营企业', [20, 2]), total('小计', [null, null]), total('合  计', [null, null])],
    }
    expect(recalcNoteTableTotals(table)).toBe(6)
    expect(table.rows.map((r) => r.values)).toEqual([[10, 1], [5, null], [15, 1], [20, 2], [20, 2], [35, 3]])
  })

  it('「小计 / 减：坏账准备 / 合计」= 小计 − 坏账准备；比例列不加总；手工格不动', () => {
    const table = {
      headers: ['账龄', '账面余额', '比例(%)'],
      rows: [row('1年以内', [100, 60]), row('1至2年', [50, 40]), total('小计', [null, null]),
        row('减：坏账准备', [15, null]), total('合计', [7, null], { _cell_modes: { 0: 'manual' } })],
    }
    recalcNoteTableTotals(table)
    expect(table.rows[2].values).toEqual([150, null])
    expect(table.rows[4].values).toEqual([7, null])
    table.rows[4]._cell_modes = { 0: 'auto' }
    recalcNoteTableTotals(table)
    expect(table.rows[4].values).toEqual([135, null])
  })

  it('「其中：」标记下面的明细不重复加；合计行之后的「其中：境外」不加；明细全空不写 0', () => {
    const table = {
      headers: ['项目', '期末余额'],
      rows: [row('按单项计提', [10]), row('按组合计提', [90]), row('其中：', [null]), row('中央企业客户', [60]),
        row('海外客户', [30]), total('合计', [null]), row('其中：存放在境外的款项', [999])],
    }
    recalcNoteTableTotals(table)
    expect(table.rows[5].values).toEqual([100])
    const blank = { headers: ['项目', '期末余额'], rows: [row('库存现金', [null]), total('合计', [500000])] }
    expect(recalcNoteTableTotals(blank)).toBe(0)
    expect(blank.rows[1].values).toEqual([500000])
  })

  it('改单元格：只给这一列判得准的合计 / 小计（先小计、合计用新小计）', () => {
    const table = {
      headers: ['项目', '期末余额', '期初余额'],
      rows: [row('1年以内', [100, 1]), row('1至2年', [50, 2]), total('小计', [140, 3]), row('减：坏账准备', [15, null]),
        total('合计', [125, 3])],
    }
    expect(columnTotalUpdates(table, 0)).toEqual([{ row: 2, value: 150 }, { row: 4, value: 135 }])
    expect(columnTotalUpdates(table, 1)).toEqual([])
    expect(columnTotalUpdates(table, 5)).toEqual([])
    const ambiguous = {
      headers: ['项目', '期末余额'],
      rows: [row('交易性金融负债', [100]), row('其中：发行的交易性债券', [30]), row('其他', [20]), total('合计', [120])],
    }
    expect(columnTotalUpdates(ambiguous, 0)).toEqual([])
  })

  it('合计格与构成不一致才标红；判不准 / 构成全空不标', () => {
    const table = {
      headers: ['项目', '期末余额'],
      rows: [row('库存现金', [100]), row('银行存款', [50]), total('合计', [150]), row('其中：境外', [30])],
    }
    expect(totalMismatch(table, 2, 0)).toBe(false)
    table.rows[2].values = [180]
    expect(totalMismatch(table, 2, 0)).toBe(true)
    expect(totalMismatch({ headers: ['项目', '期末'], rows: [row('甲', [null]), total('合计', [9])] }, 1, 0)).toBe(false)
    expect(totalMismatch({
      headers: ['项目', '期末'], rows: [row('甲', [1]), row('其中：乙', [1]), total('合计', [9])],
    }, 2, 0)).toBe(false)
  })
})

describe('合并附注编辑行合计回填', () => {
  const headers = ['项目', '期末余额', '比例(%)']

  it('小计 − 减项 = 合计（旧算法合计 = 减项）；两位小数；手工格与比例列不动', () => {
    const rows = [
      { 0: '1年以内', 1: '100', 2: '60' }, { 0: '1至2年', 1: '50.5', 2: '40' }, { 0: '小  计', 1: '', 2: '' },
      { 0: '减：坏账准备', 1: '15', 2: '' }, { 0: '合  计', 1: '', 2: '' }, { 0: '', 1: '', 2: '' },
    ]
    expect(recalcConsolTotalRows(rows, ['data', 'data', 'subtotal', 'data', 'total'], { headers })).toBe(2)
    expect(rows.map((r) => r[1])).toEqual(['100', '50.5', '150.50', '15', '135.50', ''])
    expect(rows[2][2]).toBe('')
    rows[3][1] = '20'
    recalcConsolTotalRows(rows, null, { headers }, (r, c) => r === 4 && c === 1)
    expect(rows[4][1]).toBe('135.50')
  })

  it('行类型缺省按行名判（「X小计」= 小计）；判不准的合计不动', () => {
    const rows = [{ 0: '资产：', 1: '7' }, { 0: '资产小计', 1: '' }, { 0: '负债：', 1: '3' }, { 0: '负债小计', 1: '' }]
    recalcConsolTotalRows(rows, null, { headers: ['项目', '金额'] })
    expect(rows.map((r) => r[1])).toEqual(['7', '7.00', '3', '3.00'])
    const ambiguous = [{ 0: '甲', 1: '1' }, { 0: '其中：乙', 1: '2' }, { 0: '合计', 1: '9' }]
    expect(recalcConsolTotalRows(ambiguous, null, { headers: ['项目', '金额'] })).toBe(0)
  })
})

describe('接线：三处前端合计回填都走合计构成（禁回退成整表求和）', () => {
  const src = (rel: string) => readFileSync(resolve(__dirname, rel), 'utf-8')
  const between = (text: string, from: string, to: string) => {
    const start = text.indexOf(from)
    expect(start, `找不到 ${from}`).toBeGreaterThanOrEqual(0)
    return text.slice(start, text.indexOf(to, start + from.length))
  }

  it('单体附注编辑器：改单元格回填合计、合计标红', () => {
    const editor = src('../../DisclosureEditor.vue')
    expect(editor).toContain("import { columnTotalUpdates, totalMismatch } from '@/views/composables/noteTotalTerms'")
    const onChange = between(editor, 'function onCellValueChange(', '\nfunction ')
    expect(onChange).toContain('columnTotalUpdates(activeTableData.value, colIndex)')
    expect(onChange).not.toMatch(/is_total\)/)
    expect(between(editor, 'function isFormulaMismatch(', '\n}\n')).toContain('totalMismatch(')
  })

  it('结构编辑（加删行 / 列、恢复模板）', () => {
    const struct = src('../../../composables/useNoteTableStructure.ts')
    expect(between(struct, 'function recalcTotals()', '\n  }\n')).toContain('recalcNoteTableTotals(table)')
    expect(struct).toContain('if (isTotalRow(row) || isPushedFixedRow(row)) return')
  })

  it('合并附注编辑', () => {
    const tab = src('../../../components/consolidation/ConsolNoteTab.vue')
    expect(tab).toContain("import { recalcConsolTotalRows } from '@/views/composables/noteTotalTerms'")
    expect(between(tab, 'function recalcTotalRows()', '\n}\n')).toContain('recalcConsolTotalRows(rows, sec.rowTypes')
    expect(tab).not.toContain('_inferRowType')
  })
})
