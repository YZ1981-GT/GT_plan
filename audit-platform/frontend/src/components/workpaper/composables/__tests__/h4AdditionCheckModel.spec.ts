/**
 * H4-4 增加检查表 — 纯函数模型单测
 */
import { describe, it, expect } from 'vitest'
import {
  calcInvoiceDiff,
  calcCoverageRate,
  normalizeAdditionRow,
  calcAdditionSummary,
  sumDetailIncrease,
  buildNoteDraft,
  buildConclusionDraft,
  isCheckIncomplete,
} from '../h4AdditionCheckModel'

describe('h4AdditionCheckModel', () => {
  describe('calcInvoiceDiff', () => {
    it('差异 = 借方金额 − 发票金额', () => {
      expect(calcInvoiceDiff({ amount: 1000, invoiceAmount: 900 })).toBe(100)
      expect(calcInvoiceDiff({ amount: 1000, invoiceAmount: 1000 })).toBe(0)
    })
  })

  describe('calcCoverageRate', () => {
    it('总体为 0 时返回 0，避免 #DIV/0!', () => {
      expect(calcCoverageRate(1000, 0)).toBe(0)
      expect(calcCoverageRate(1000, -1)).toBe(0)
    })

    it('正常计算检查比例并封顶 100%', () => {
      expect(calcCoverageRate(200, 1000)).toBe(20)
      expect(calcCoverageRate(1500, 1000)).toBe(100)
    })
  })

  describe('normalizeAdditionRow', () => {
    it('旧字段 name/spec/inboundDate/amount 可迁移', () => {
      const row = normalizeAdditionRow({
        name: '电缆',
        spec: 'YJV',
        amount: 50000,
        inboundDate: '2025-06-01',
        invoiceAmount: 48000,
        invoiceNo: 'FP001',
        contractNo: 'HT-1',
        inspector: '张三',
      }, 0)
      expect(row.category).toBe('YJV')
      expect(row.amount).toBe(50000)
      expect(row.voucherDate).toBe('2025-06-01')
      expect(row.diff).toBe(2000)
      expect(row.supportingDocs).toContain('FP001')
    })

    it('导入别名 materialName/receiptDate/debitAmount 可识别', () => {
      const row = normalizeAdditionRow({
        materialName: '钢管',
        receiptDate: '2025-01-15',
        debitAmount: 12000,
      }, 1)
      expect(row.name).toBe('钢管')
      expect(row.voucherDate).toBe('2025-01-15')
      expect(row.amount).toBe(12000)
      expect(row.seq).toBe(2)
    })
  })

  describe('isCheckIncomplete / calcAdditionSummary', () => {
    it('核对 1–4 未齐视为未完', () => {
      const row = normalizeAdditionRow({ name: 'a', amount: 100, checks: { check1: true } })
      expect(isCheckIncomplete(row)).toBe(true)
      row.checks = { check1: true, check2: true, check3: true, check4: true, check5: false }
      expect(isCheckIncomplete(row)).toBe(false)
    })

    it('汇总检查比例与差异笔数', () => {
      const rows = [
        normalizeAdditionRow({ name: 'a', amount: 200, invoiceAmount: 200, isAbnormal: '' }),
        normalizeAdditionRow({ name: 'b', amount: 300, invoiceAmount: 250, isAbnormal: '是' }),
      ]
      const s = calcAdditionSummary(rows, 1000)
      expect(s.checkedCount).toBe(2)
      expect(s.checkedAmount).toBe(500)
      expect(s.coverageRate).toBe(50)
      expect(s.diffCount).toBe(1)
      expect(s.anomalyCount).toBe(1)
    })
  })

  describe('sumDetailIncrease', () => {
    it('从 H4-2 汇总采购+其他增加', () => {
      const linked = sumDetailIncrease([
        { purchaseAmount: 1000, otherIncrease: 200 },
        { purchaseAmount: 500, otherIncrease: 0 },
      ])
      expect(linked.amount).toBe(1700)
      expect(linked.purchase).toBe(1500)
      expect(linked.otherIncrease).toBe(200)
      expect(linked.source).toBe('H4-2')
    })

    it('仅有 increaseSubtotal 时作为回退', () => {
      const linked = sumDetailIncrease([{ increaseSubtotal: 800 }])
      expect(linked.amount).toBe(800)
      expect(linked.source).toBe('H4-2')
    })
  })

  describe('drafts', () => {
    it('无样本时结论提示先完成选取', () => {
      const s = calcAdditionSummary([], 0)
      expect(buildConclusionDraft(s)).toContain('尚未抽取')
    })

    it('比例偏低时说明含扩大样本提示', () => {
      const rows = [normalizeAdditionRow({ name: 'a', amount: 100 })]
      const s = calcAdditionSummary(rows, 10000)
      expect(buildNoteDraft(s, 10000)).toContain('检查比例偏低')
    })
  })
})
