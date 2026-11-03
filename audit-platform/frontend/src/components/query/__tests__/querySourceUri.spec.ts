import { describe, it, expect } from 'vitest'
import { buildWorkpaperUri, buildTraceUri, reportTypeOfSource, RESOLVE_FAIL_MSG } from '../querySourceUri'

describe('buildWorkpaperUri — URI 拼装 (Property 7)', () => {
  it('完整三段', () => {
    expect(buildWorkpaperUri('D2', '审定表D2-1', 'B7')).toBe('workpaper:D2|审定表D2-1|B7')
  })

  it('省略 cellRef', () => {
    expect(buildWorkpaperUri('K1', '明细表K1-2')).toBe('workpaper:K1|明细表K1-2')
  })

  it('省略 sheetName 和 cellRef', () => {
    expect(buildWorkpaperUri('E1')).toBe('workpaper:E1')
  })

  it('sheetName 为空字符串视同省略', () => {
    expect(buildWorkpaperUri('F2', '')).toBe('workpaper:F2')
  })

  it('有 cellRef 但无 sheetName 时不输出 cellRef（语法依赖 sheet 段）', () => {
    expect(buildWorkpaperUri('G1', '', 'C3')).toBe('workpaper:G1')
  })
})

describe('buildTraceUri — 溯源 URI 推断分支', () => {
  it('优先 workpaper（有 wp_code + sheet_name）', () => {
    const row = { wp_code: 'D2', sheet_name: '审定表D2-1', cell_ref: 'A1', module: 'report', report_type: 'BS' }
    expect(buildTraceUri(row, 'fallback')).toBe('workpaper:D2|审定表D2-1|A1')
  })

  it('report 分支', () => {
    const row = { module: 'report', report_type: 'IS' }
    expect(buildTraceUri(row, '')).toBe('report:IS')
  })

  it('note 分支', () => {
    const row = { module: 'note', section_id: '五、1' }
    expect(buildTraceUri(row, '')).toBe('note:五、1')
  })

  it('按数据源生成 address-resolve 认的模块前缀（原先注册表源键原样发出 ⇒ 400；advanced-query-linkage-closure 任务 32）', () => {
    const row = { amount: 100 }
    expect(buildTraceUri(row, 'tb_detail')).toBe('tb:tb_detail')
    expect(buildTraceUri(row, 'ledger_entries')).toBe('tb:ledger_entries')
    expect(buildTraceUri(row, 'adj_aje')).toBe('adj:adj_aje')
    expect(buildTraceUri(row, 'adjustment')).toBe('adj:adjustment')
    expect(buildTraceUri(row, 'report_balance_sheet')).toBe('report:balance_sheet')
    expect(buildTraceUri({ report_type: 'cash_flow_statement', row_code: 'CF-001' }, 'report_lines'))
      .toBe('report:cash_flow_statement')
    expect(buildTraceUri(row, 'disclosure_note:八、1')).toBe('note:八、1')
    expect(buildTraceUri(row, 'disclosure')).toBe('note:')
    expect(buildTraceUri(row, 'workpaper:D2|审定表D2-1')).toBe('workpaper:D2|审定表D2-1')
  })

  it('底稿清单行只有 wp_code（没有 sheet）也按底稿溯源', () => {
    expect(buildTraceUri({ wp_code: 'E1', wp_name: '货币资金' }, 'workpaper')).toBe('workpaper:E1')
  })

  it('全无则返回空串', () => {
    expect(buildTraceUri({}, '')).toBe('')
  })
})

describe('reportTypeOfSource — 只有报表叶子带报表类型（advanced-query-linkage-closure 任务 17）', () => {
  it('报表叶子 report_{类型} → 类型', () => {
    expect(reportTypeOfSource('report_balance_sheet')).toBe('balance_sheet')
    expect(reportTypeOfSource('report_income_statement')).toBe('income_statement')
    expect(reportTypeOfSource('report_impairment_provision')).toBe('impairment_provision')
  })

  it('报表行次配置 report_lines 不是报表叶子（否则请求带 report_type=lines，后端得 0 行）', () => {
    expect(reportTypeOfSource('report_lines')).toBeNull()
  })

  it('通用 report、其他源与空键 → null', () => {
    expect(reportTypeOfSource('report')).toBeNull()
    expect(reportTypeOfSource('report_')).toBeNull()
    expect(reportTypeOfSource('tb_detail')).toBeNull()
    expect(reportTypeOfSource('adj_aje')).toBeNull()
    expect(reportTypeOfSource('')).toBeNull()
  })
})

describe('RESOLVE_FAIL_MSG — 文案常量', () => {
  it('wpNotFound 包含底稿编码', () => {
    expect(RESOLVE_FAIL_MSG.wpNotFound('K3')).toContain('K3')
  })

  it('常量非空', () => {
    expect(RESOLVE_FAIL_MSG.notRegistered).toBeTruthy()
    expect(RESOLVE_FAIL_MSG.noUri).toBeTruthy()
  })
})
