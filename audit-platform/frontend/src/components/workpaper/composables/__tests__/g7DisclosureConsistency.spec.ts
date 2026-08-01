/**
 * g7DisclosureConsistency.spec.ts — G7 勾稽引擎单测
 *
 * 覆盖 6 条规则 + 容差 0.01 + 无数据时返「暂无可比对数据」（skip）。
 *
 * spec: .kiro/specs/g7-four-table-extraction-and-disclosure-alignment/ Task 6.2
 */
import { describe, it, expect } from 'vitest'
import {
  buildG7ConsistencyChecks,
  type G7ConsistencyInput,
  type G7MainTableRow,
} from '../g7DisclosureConsistency'

function emptyInput(): G7ConsistencyInput {
  return {
    classificationRows: [],
    classificationSubtotal: null,
    classificationImpairment: null,
    classificationTotal: null,
    mainTableRows: [],
    mainTableClosingTotal: null,
    adjudicatedAmount: null,
    disclosureImpairmentEnd: null,
    g7_17ImpairmentTotal: null,
    excessLoss: null,
  }
}

describe('g7DisclosureConsistency', () => {
  it('无数据时 6 条规则全部 skip', () => {
    const results = buildG7ConsistencyChecks(emptyInput())
    expect(results.length).toBe(6)
    for (const r of results) {
      expect(r.level).toBe('skip')
    }
  })

  describe('规则 1：分类表合计 = 小计 − 减值准备', () => {
    it('一致时 level=ok', () => {
      const input = emptyInput()
      input.classificationSubtotal = 1000
      input.classificationImpairment = 200
      input.classificationTotal = 800
      const results = buildG7ConsistencyChecks(input)
      const rule = results.find(r => r.label === '分类表合计')!
      expect(rule.level).toBe('ok')
      expect(rule.diff).toBe(0)
    })

    it('不一致时 level=error', () => {
      const input = emptyInput()
      input.classificationSubtotal = 1000
      input.classificationImpairment = 200
      input.classificationTotal = 900 // should be 800
      const results = buildG7ConsistencyChecks(input)
      const rule = results.find(r => r.label === '分类表合计')!
      expect(rule.level).toBe('error')
      expect(rule.diff).toBe(100)
    })

    it('容差 0.01 以内 level=ok', () => {
      const input = emptyInput()
      input.classificationSubtotal = 1000
      input.classificationImpairment = 200
      input.classificationTotal = 800.005 // diff = 0.005 < 0.01
      const results = buildG7ConsistencyChecks(input)
      const rule = results.find(r => r.label === '分类表合计')!
      expect(rule.level).toBe('ok')
    })
  })

  describe('规则 2：主表 roll-forward', () => {
    it('逐行一致时 level=ok', () => {
      const input = emptyInput()
      input.mainTableRows = [
        { name: '甲公司', openingBook: 100, totalIncrease: 50, totalDecrease: 20, closingBook: 130 },
        { name: '乙公司', openingBook: 200, totalIncrease: 10, totalDecrease: 30, closingBook: 180 },
      ]
      const results = buildG7ConsistencyChecks(input)
      const rule = results.find(r => r.label === '主表 roll-forward')!
      expect(rule.level).toBe('ok')
    })

    it('某行不平时 level=error', () => {
      const input = emptyInput()
      input.mainTableRows = [
        { name: '甲公司', openingBook: 100, totalIncrease: 50, totalDecrease: 20, closingBook: 999 },
      ]
      const results = buildG7ConsistencyChecks(input)
      const rule = results.find(r => r.label === '主表 roll-forward')!
      expect(rule.level).toBe('error')
    })
  })

  describe('规则 3：分类表 ↔ 主表', () => {
    it('分类表小计 ≥ 主表合计时 level=ok', () => {
      const input = emptyInput()
      input.classificationSubtotal = 1000
      input.mainTableClosingTotal = 800
      const results = buildG7ConsistencyChecks(input)
      const rule = results.find(r => r.label === '分类表 ↔ 主表')!
      expect(rule.level).toBe('ok')
    })

    it('分类表小计 < 主表合计时 level=warn', () => {
      const input = emptyInput()
      input.classificationSubtotal = 500
      input.mainTableClosingTotal = 800
      const results = buildG7ConsistencyChecks(input)
      const rule = results.find(r => r.label === '分类表 ↔ 主表')!
      expect(rule.level).toBe('warn')
    })
  })

  describe('规则 4：披露 ↔ 审定', () => {
    it('一致时 level=ok', () => {
      const input = emptyInput()
      input.mainTableClosingTotal = 40459060.60
      input.adjudicatedAmount = 40459060.60
      const results = buildG7ConsistencyChecks(input)
      const rule = results.find(r => r.label === '披露 ↔ 审定')!
      expect(rule.level).toBe('ok')
      expect(rule.diff).toBe(0)
    })

    it('不一致时 level=error', () => {
      const input = emptyInput()
      input.mainTableClosingTotal = 40459060.60
      input.adjudicatedAmount = 38000000.00
      const results = buildG7ConsistencyChecks(input)
      const rule = results.find(r => r.label === '披露 ↔ 审定')!
      expect(rule.level).toBe('error')
    })

    it('审定数为 null 时 level=skip', () => {
      const input = emptyInput()
      input.mainTableClosingTotal = 40459060.60
      input.adjudicatedAmount = null
      const results = buildG7ConsistencyChecks(input)
      const rule = results.find(r => r.label === '披露 ↔ 审定')!
      expect(rule.level).toBe('skip')
    })
  })

  describe('规则 5：减值 ↔ G7-17', () => {
    it('一致时 level=ok', () => {
      const input = emptyInput()
      input.disclosureImpairmentEnd = 4790032.97
      input.g7_17ImpairmentTotal = 4790032.97
      const results = buildG7ConsistencyChecks(input)
      const rule = results.find(r => r.label === '减值 ↔ G7-17')!
      expect(rule.level).toBe('ok')
    })

    it('不一致时 level=warn（非 error）', () => {
      const input = emptyInput()
      input.disclosureImpairmentEnd = 4790032.97
      input.g7_17ImpairmentTotal = 3000000.00
      const results = buildG7ConsistencyChecks(input)
      const rule = results.find(r => r.label === '减值 ↔ G7-17')!
      expect(rule.level).toBe('warn')
    })
  })

  describe('规则 6：超额亏损小计', () => {
    it('合营小计 + 联营小计 = 合计时 level=ok', () => {
      const input = emptyInput()
      input.excessLoss = { jvSubtotal: 100, associateSubtotal: 200, total: 300 }
      const results = buildG7ConsistencyChecks(input)
      const rule = results.find(r => r.label === '超额亏损小计')!
      expect(rule.level).toBe('ok')
      expect(rule.diff).toBe(0)
    })

    it('不一致时 level=error', () => {
      const input = emptyInput()
      input.excessLoss = { jvSubtotal: 100, associateSubtotal: 200, total: 500 }
      const results = buildG7ConsistencyChecks(input)
      const rule = results.find(r => r.label === '超额亏损小计')!
      expect(rule.level).toBe('error')
    })

    it('无超额亏损数据时 level=skip', () => {
      const input = emptyInput()
      input.excessLoss = null
      const results = buildG7ConsistencyChecks(input)
      const rule = results.find(r => r.label === '超额亏损小计')!
      expect(rule.level).toBe('skip')
    })
  })
})
