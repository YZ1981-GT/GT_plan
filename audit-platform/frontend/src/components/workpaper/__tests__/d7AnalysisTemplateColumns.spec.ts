/**
 * D7-4 分析表按模板补列（spec oo-writeback-template-parity-closure R3.1：模板有、前端没有的列前端补上）。
 *
 * 模板「（一）借方发生额分析」表头：项目 / 金额 / 数据来源 / 备注；
 * 「（三）贷方发生额分析」表头：金额 / 数据来源 / 与对方科目核对 / 说明。
 * 契约贷方区 D 列接 counterCheck、E 列接 remark；借方区 D 列接 remark。
 * 原表单借贷两区都只显示 项目 / 金额 / 数据来源，备注 / 说明 / 与对方科目核对 在 OnlyOffice 里改了回到表单看不见。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { normalizeD7CreditRow } from '../composables/useD7Analysis'

const vueSrc = readFileSync(resolve(__dirname, '../d7/D7TabAnalysis.vue'), 'utf-8')

/** 取「(一)…」或「(三)…」卡片里的模板片段（从卡片标题 h4 起，到下一张卡片止；注释里的同名标题不算） */
function card(title: string): string {
  const start = vueSrc.indexOf(`>${title}</h4>`)
  expect(start, `D7TabAnalysis.vue 里找不到标题为 ${title} 的卡片`).toBeGreaterThan(-1)
  const end = vueSrc.indexOf('<div class="analysis-card">', start + title.length)
  return vueSrc.slice(start, end === -1 ? undefined : end)
}

describe('D7-4 贷方分析行', () => {
  it('载入保留「与对方科目核对」与说明，缺省字段补空', () => {
    const row = normalizeD7CreditRow({ rowId: 'c1', item: '银行存款收款', amount: '12.5', counterCheck: '一致', remark: '说明' })
    expect(row).toEqual({
      rowId: 'c1', item: '银行存款收款', amount: 12.5, dataSource: '', remark: '说明', counterCheck: '一致',
    })
    const blank = normalizeD7CreditRow({})
    expect(blank.counterCheck).toBe('')
    expect(blank.rowId).toMatch(/^ana-/)
  })
})

describe('D7-4 表单列与模板表头一致', () => {
  it('借方区显示并可录「备注」', () => {
    const debit = card('(一) 借方发生额分析')
    expect(debit).toContain('label="备注"')
    expect(debit).toContain("updateDebitCell(row.rowId, 'remark'")
  })

  it('贷方区显示并可录「与对方科目核对」「说明」', () => {
    const credit = card('(三) 贷方发生额分析')
    expect(credit).toContain('label="与对方科目核对"')
    expect(credit).toContain("updateCreditCell(row.rowId, 'counterCheck'")
    expect(credit).toContain('label="说明"')
    expect(credit).toContain("updateCreditCell(row.rowId, 'remark'")
  })
})
