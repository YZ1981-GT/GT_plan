/**
 * buildQueryEntry / tbRowDrill（advanced-query-linkage-closure 任务 46，design §10.1；ADR-AQL-20 表逐行一条）
 *
 * 判据：四种业务对象的落点与切换集合、年度取 `target.year ?? hostYear`、合计 / 小计行与空目标置灰、
 * 下钻只对带科目码的试算表结果行给出下一跳。
 */
import { describe, expect, it } from 'vitest'

import {
  buildQueryEntry, isQueryEntryRejected, tbRowDrill,
  ENTRY_NO_PROJECT, ENTRY_NOTE_NO_SECTION, ENTRY_REPORT_NO_ROW, ENTRY_REPORT_TOTAL_ROW,
  ENTRY_TB_NO_ACCOUNT, ENTRY_TB_TOTAL_ROW, ENTRY_WP_NO_CODE,
  type QueryEntryRequest, type QueryEntryTarget,
} from '../queryEntryContext'

const ROUTE = { name: 'TrialBalance', params: { projectId: 'p-1' }, query: {} }

function ok(result: ReturnType<typeof buildQueryEntry>): QueryEntryRequest {
  if (isQueryEntryRejected(result)) throw new Error(`期望可用，实得置灰：${result.disabledReason}`)
  return result
}

function reason(result: ReturnType<typeof buildQueryEntry>): string {
  if (!isQueryEntryRejected(result)) throw new Error('期望置灰，实得可用')
  return result.disabledReason
}

describe('ADR-AQL-20 四种业务对象的落点', () => {
  it('试算表行 → 该科目序时账，可切到科目余额 / 辅助余额 / 辅助明细', () => {
    const entry = ok(buildQueryEntry('tb_row', { standard_account_code: '1002', account_name: '银行存款' }, ROUTE, 2025))
    expect(entry.source).toBe('ledger_entries')
    expect(entry.filters).toEqual({ account_code: '1002' })
    expect(entry.label).toBe('试算表 1002 银行存款')
    expect(entry.switches.map((s) => s.source)).toEqual(
      ['ledger_entries', 'account_balance', 'aux_balance', 'aux_ledger'])
    expect(entry.projectId).toBe('p-1')
    expect(entry.year).toBe(2025)
  })

  it('报表行 → 试算表按 report_row 收窄，没有切换项（行内下钻另走 tbRowDrill）', () => {
    const entry = ok(buildQueryEntry('report_row', {
      report_type: 'balance_sheet', row_code: 'BS-002', row_name: '货币资金', year: 2024,
    }, ROUTE, 2025))
    expect(entry.source).toBe('tb_detail')
    expect(entry.filters).toEqual({ report_row: 'balance_sheet:BS-002' })
    expect(entry.label).toBe('资产负债表 BS-002 货币资金')
    expect(entry.switches).toEqual([])
    expect(entry.year).toBe(2024)
  })

  it('附注章节 → 该章节附注表格，可切到「相关科目（试算表）」并换上 note_section 筛选', () => {
    const entry = ok(buildQueryEntry('note_section', { note_section: '八、1', section_title: '货币资金' }, ROUTE, 2025))
    expect(entry.source).toBe('disclosure_note:八、1')
    expect(entry.filters).toEqual({})
    expect(entry.label).toBe('附注 八、1 货币资金')
    expect(entry.switches).toEqual([
      { source: 'disclosure_note:八、1', label: '附注表格', filters: {} },
      { source: 'tb_detail', label: '相关科目（试算表）', filters: { note_section: '八、1' } },
    ])
  })

  it('底稿 → 该底稿科目的序时账，可切账簿三源', () => {
    const entry = ok(buildQueryEntry('workpaper', { wp_code: 'E1', wp_name: '货币资金' }, ROUTE, 2025))
    expect(entry.source).toBe('ledger_entries')
    expect(entry.filters).toEqual({ wp_code: 'E1' })
    expect(entry.label).toBe('底稿 E1 货币资金')
    expect(entry.switches.map((s) => s.label)).toContain('辅助明细')
  })
})

describe('年度来源（§16 #7）', () => {
  it('target.year 优先于 hostYear', () => {
    expect(ok(buildQueryEntry('tb_row', { standard_account_code: '1002', year: 2023 }, ROUTE, 2025)).year).toBe(2023)
  })

  it('target 没有年度时取 hostYear（宿主取数用的年度）', () => {
    expect(ok(buildQueryEntry('tb_row', { standard_account_code: '1002' }, ROUTE, 2024)).year).toBe(2024)
  })

  it('两者都取不到就不带 year，交弹窗按项目审计年度解析（不按日历年兜底）', () => {
    const entry = ok(buildQueryEntry('tb_row', { standard_account_code: '1002' }, ROUTE, null))
    expect(entry.year).toBeUndefined()
    expect('year' in entry).toBe(false)
  })

  it('非法年度（0 / NaN / 字符串）一律当没有', () => {
    for (const bad of [0, NaN, undefined, null]) {
      const entry = ok(buildQueryEntry('tb_row', { standard_account_code: '1002', year: bad as never }, ROUTE, bad as never))
      expect(entry.year).toBeUndefined()
    }
  })
})

describe('不可用时给中文原因、不发事件', () => {
  it('不在项目页（路由没有项目）', () => {
    expect(reason(buildQueryEntry('tb_row', { standard_account_code: '1002' }, { name: 'Dashboard' }, 2025)))
      .toBe(ENTRY_NO_PROJECT)
  })

  it.each([
    ['小计行', { standard_account_code: '1002', _isSubtotal: true }, ENTRY_TB_TOTAL_ROW],
    ['合计行', { standard_account_code: '1002', _isTotal: true }, ENTRY_TB_TOTAL_ROW],
    ['没有科目码', { account_name: '银行存款' }, ENTRY_TB_NO_ACCOUNT],
    ['空目标', null, ENTRY_TB_NO_ACCOUNT],
  ])('试算表行：%s', (_name, target, expected) => {
    expect(reason(buildQueryEntry('tb_row', target as QueryEntryTarget | null, ROUTE, 2025))).toBe(expected)
  })

  it.each([
    ['合计行', { report_type: 'balance_sheet', row_code: 'BS-015', is_total_row: true }, ENTRY_REPORT_TOTAL_ROW],
    ['没有行次', { report_type: 'balance_sheet' }, ENTRY_REPORT_NO_ROW],
    ['未知报表类型', { report_type: 'no_such', row_code: 'X-1' }, ENTRY_REPORT_NO_ROW],
    ['空目标', null, ENTRY_REPORT_NO_ROW],
  ])('报表行：%s', (_name, target, expected) => {
    expect(reason(buildQueryEntry('report_row', target as QueryEntryTarget | null, ROUTE, 2025))).toBe(expected)
  })

  it('报表行不带报表类型时按资产负债表（与侧栏预选同口径）', () => {
    expect(ok(buildQueryEntry('report_row', { row_code: 'BS-002' }, ROUTE, 2025)).filters)
      .toEqual({ report_row: 'balance_sheet:BS-002' })
  })

  it('附注章节为空 / 底稿没有编码', () => {
    expect(reason(buildQueryEntry('note_section', { section_title: '货币资金' }, ROUTE, 2025))).toBe(ENTRY_NOTE_NO_SECTION)
    expect(reason(buildQueryEntry('note_section', null, ROUTE, 2025))).toBe(ENTRY_NOTE_NO_SECTION)
    expect(reason(buildQueryEntry('workpaper', { wp_name: '货币资金' }, ROUTE, 2025))).toBe(ENTRY_WP_NO_CODE)
  })

  it('不支持的 kind', () => {
    expect(reason(buildQueryEntry('nope' as never, { wp_code: 'E1' }, ROUTE, 2025))).toContain('不支持')
  })
})

describe('tbRowDrill 行内下钻', () => {
  const entry = ok(buildQueryEntry('report_row', {
    report_type: 'balance_sheet', row_code: 'BS-002', row_name: '货币资金',
  }, ROUTE, 2025))

  it('试算表结果行 → 该科目序时账，沿用入口的项目与年度', () => {
    const next = tbRowDrill({ standard_account_code: '1002', account_name: '银行存款' }, entry)
    expect(next).toMatchObject({
      kind: 'tb_row', projectId: 'p-1', year: 2025, source: 'ledger_entries',
      filters: { account_code: '1002' }, label: '1002 银行存款 序时账',
    })
    expect(next?.switches.map((s) => s.source)).toContain('aux_ledger')
  })

  it('合计 / 小计行与没有科目码的行不给下钻', () => {
    expect(tbRowDrill({ standard_account_code: '1002', _isTotal: true }, entry)).toBeNull()
    expect(tbRowDrill({ standard_account_code: '1002', _isSubtotal: true }, entry)).toBeNull()
    expect(tbRowDrill({ account_name: '银行存款' }, entry)).toBeNull()
    expect(tbRowDrill(null, entry)).toBeNull()
  })

  it('没有入口上下文时不给下钻（普通查询的结果行不出现「查明细」）', () => {
    expect(tbRowDrill({ standard_account_code: '1002' }, null)).toBeNull()
  })

  it('入口没有年度时下钻也不带年度', () => {
    const noYear = ok(buildQueryEntry('report_row', { row_code: 'BS-002' }, ROUTE, null))
    const next = tbRowDrill({ standard_account_code: '1002' }, noYear)
    expect(next && 'year' in next).toBe(false)
  })
})
