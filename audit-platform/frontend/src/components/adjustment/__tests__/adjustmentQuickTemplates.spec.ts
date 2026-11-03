/**
 * 快捷模板按科目名称匹配本项目科目（spec adjustment-hall-entry-review-closure 需求 1.4）。
 * 原模板写死 6601 资产减值损失、5001 主营业务收入、1503 一年内到期的非流动资产，与现行准则科目表不符。
 */
import { describe, expect, it } from 'vitest'
import { QUICK_TEMPLATES, applyQuickTemplate, matchTemplateAccount } from '../adjustmentQuickTemplates'

/** 真实项目里常见的混合科目表：同名不同码（5602 / 6602 管理费用）、6001 叫「营业收入」、存货跌价准备用 1416 */
const CHART = [
  { code: '1122', name: '应收账款' }, { code: '1123', name: '预付账款' }, { code: '1231', name: '坏账准备' },
  { code: '1416', name: '存货跌价准备' }, { code: '1602', name: '累计折旧' }, { code: '1702', name: '累计摊销' },
  { code: '2202', name: '应付账款' }, { code: '2205', name: '合同负债' }, { code: '2211', name: '应付职工薪酬' },
  { code: '2221', name: '应交税费' }, { code: '2501', name: '长期借款' }, { code: '5602', name: '管理费用' },
  { code: '6001', name: '营业收入' }, { code: '6602', name: '管理费用' }, { code: '6701', name: '资产减值损失' },
  { code: '6702', name: '信用减值损失' }, { code: '6801', name: '所得税费用' },
]

describe('快捷模板', () => {
  it('每个模板至少一借一贷，类型只能是 AJE / RJE', () => {
    for (const t of QUICK_TEMPLATES) {
      expect(['aje', 'rje']).toContain(t.type)
      expect(t.lines.some((l) => l.side === 'debit') && t.lines.some((l) => l.side === 'credit'), t.key).toBe(true)
    }
  })

  it('不再写死与准则不符的科目（信用减值走 6702、收入不用 5001）', () => {
    const codes = QUICK_TEMPLATES.flatMap((t) => t.lines.flatMap((l) => l.codes))
    expect(codes).not.toContain('5001')
    expect(codes).not.toContain('1503')
    const badDebt = QUICK_TEMPLATES.find((t) => t.key === 'bad_debt')!
    expect(badDebt.lines[0]).toMatchObject({ names: ['信用减值损失'], codes: ['6702'], side: 'debit' })
  })

  it('建议编码且名称对得上 ⇒ 采用（同名多码时取 6602 而非 5602）', () => {
    const tpl = QUICK_TEMPLATES.find((t) => t.key === 'depreciation')!
    expect(matchTemplateAccount(tpl.lines[0], CHART)?.code).toBe('6602')
  })

  it('建议编码在本项目是别的科目 ⇒ 不采用，改按名称找', () => {
    const line = { names: ['存货跌价准备'], codes: ['1471'], side: 'credit' as const }
    expect(matchTemplateAccount(line, [...CHART, { code: '1471', name: '存货' }])?.code).toBe('1416')
  })

  it('套用：金额留空、带方向；收入按「营业收入」匹配；找不到的科目名返回并留空待选', () => {
    const revenue = applyQuickTemplate(QUICK_TEMPLATES.find((t) => t.key === 'revenue_cutoff')!, CHART)
    expect(revenue.lines.map((l) => [l.standard_account_code, l.side, l.debit_amount, l.credit_amount]))
      .toEqual([['6001', 'debit', undefined, undefined], ['1122', 'credit', undefined, undefined]])
    expect(revenue.unmatched).toEqual([])
    const loan = applyQuickTemplate(QUICK_TEMPLATES.find((t) => t.key === 'rcl_current_loan')!, CHART)
    expect(loan.type).toBe('rje')
    expect(loan.unmatched).toEqual(['一年内到期的非流动负债'])
    expect(loan.lines[1]).toMatchObject({ standard_account_code: '', account_name: '一年内到期的非流动负债' })
  })
})
