/**
 * D3-4 分析表按模板补列（spec oo-writeback-template-parity-closure R3.1 / 任务 9.4c：模板有、前端没有的列前端补上）。
 *
 * 模板「（一）借方发生额分析」表头 R10：项目 / 金额 / 数据来源 / 备注；
 * 「（三）贷方发生额分析」表头 R20：（A 空）/ 金额 / 数据来源 / 与对方科目核对 / 说明。
 * 契约贷方区 D 列接 counterCheck、E 列接 remark；借方区 D 列接 remark。原贷方表格只显示「备注」⇒
 * OnlyOffice 里填的「与对方科目核对」回到表单看不见。本表只读（数据来自导入），只核列。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const vueSrc = readFileSync(resolve(__dirname, '../d3/D3TabAnalysis.vue'), 'utf-8')

/** 取「(一)…」或「(二)…」卡片里的模板片段（从卡片标题 h4 起，到下一张卡片止） */
function card(title: string): string {
  const start = vueSrc.indexOf(`>${title}</h4>`)
  expect(start, `D3TabAnalysis.vue 里找不到标题为 ${title} 的卡片`).toBeGreaterThan(-1)
  const end = vueSrc.indexOf('<div class="analysis-card">', start + title.length)
  return vueSrc.slice(start, end === -1 ? undefined : end)
}

describe('D3-4 表单列与模板表头一致', () => {
  it('借方区显示「备注」（接 remark）', () => {
    const debit = card('(一) 借方发生额分析')
    expect(debit).toContain('prop="remark" label="备注"')
    expect(debit).not.toContain('counterCheck')
  })

  it('贷方区显示「与对方科目核对」（接 counterCheck）与「说明」（接 remark），顺序同模板 D / E', () => {
    const credit = card('(二) 贷方发生额分析')
    const check = credit.indexOf('prop="counterCheck" label="与对方科目核对"')
    const note = credit.indexOf('prop="remark" label="说明"')
    expect(check).toBeGreaterThan(-1)
    expect(note).toBeGreaterThan(check)
    expect(credit).not.toContain('label="备注"')
  })
})
