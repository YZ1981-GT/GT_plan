/**
 * H4-5 减少检查表 — 纯函数模型单测
 */
import { describe, it, expect } from 'vitest'
import {
  calcNetValue,
  calcDisposalNetPl,
  calcCoverageRate,
  normalizeDisposalRow,
  normalizeDisposalMethod,
  needsH2Ref,
  calcDisposalSummary,
  sumDetailDecrease,
  buildNoteDraft,
  buildConclusionDraft,
  getEvidenceHint,
} from '../h4DisposalCheckModel'

describe('h4DisposalCheckModel', () => {
  describe('calcNetValue / calcDisposalNetPl', () => {
    it('净值 = 原值 − 减值准备', () => {
      expect(calcNetValue({ originalCost: 1000, impairment: 200 })).toBe(800)
    })

    it('清理净损益 = 收入 − 费用 − 净值（对齐致同 M=L-K-J）', () => {
      // 原值1000 减值200 净值800；收入500 费用50 → 500-50-800 = -350
      const row = {
        originalCost: 1000,
        impairment: 200,
        netValue: 800,
        disposalIncome: 500,
        disposalCost: 50,
      }
      expect(calcDisposalNetPl(row)).toBe(-350)
    })

    it('领用出库无清理收支时净损益 = 0（成本转入在建，非处置损益）', () => {
      expect(calcDisposalNetPl({
        originalCost: 500,
        impairment: 0,
        netValue: 500,
        disposalIncome: 0,
        disposalCost: 0,
        disposalMethod: '领用出库',
        reason: '领用出库',
      })).toBe(0)
    })

    it('报废无清理收入时净损益 = −净值', () => {
      expect(calcDisposalNetPl({
        originalCost: 500,
        impairment: 0,
        netValue: 500,
        disposalIncome: 0,
        disposalCost: 0,
        disposalMethod: '报废',
        reason: '报废',
      })).toBe(-500)
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

  describe('normalizeDisposalMethod / needsH2Ref', () => {
    it('兼容旧减少原因别名', () => {
      expect(normalizeDisposalMethod('领用')).toBe('领用出库')
      expect(normalizeDisposalMethod('处置')).toBe('出售')
      expect(normalizeDisposalMethod('报废')).toBe('报废')
    })

    it('领用出库且无 H2 编号时 needsH2Ref=true', () => {
      expect(needsH2Ref({ disposalMethod: '领用出库', reason: '领用出库', h2Ref: '' })).toBe(true)
      expect(needsH2Ref({ disposalMethod: '领用出库', reason: '领用出库', h2Ref: 'H2-3' })).toBe(false)
      expect(needsH2Ref({ disposalMethod: '报废', reason: '报废', h2Ref: '' })).toBe(false)
    })
  })

  describe('normalizeDisposalRow', () => {
    it('旧字段 amount/reason/spec 可迁移', () => {
      const row = normalizeDisposalRow({
        name: '钢材',
        spec: '螺纹钢',
        amount: 12000,
        reason: '领用出库',
        impairment: 0,
      }, 0)
      expect(row.originalCost).toBe(12000)
      expect(row.amount).toBe(12000)
      expect(row.disposalMethod).toBe('领用出库')
      expect(row.category).toBe('螺纹钢')
      expect(row.netValue).toBe(12000)
    })

    it('自动计算净值与清理净损益', () => {
      const row = normalizeDisposalRow({
        name: '设备',
        originalCost: 10000,
        impairment: 1000,
        disposalIncome: 2000,
        disposalCost: 100,
        disposalMethod: '出售',
      })
      expect(row.netValue).toBe(9000)
      expect(row.disposalNetPl).toBe(2000 - 100 - 9000)
    })
  })

  describe('sumDetailDecrease / calcDisposalSummary', () => {
    it('从 H4-2 汇总本期减少', () => {
      const linked = sumDetailDecrease([
        { usageAmount: 800, returnAmount: 50, scrapAmount: 100, otherDecrease: 50 },
        { usageAmount: 200, returnAmount: 0, scrapAmount: 0, otherDecrease: 0 },
      ])
      expect(linked.amount).toBe(1200)
      expect(linked.usage).toBe(1000)
      expect(linked.source).toBe('H4-2')
    })

    it('summary 统计异常、H2缺口、核对未完', () => {
      const rows = [
        normalizeDisposalRow({
          name: 'A', originalCost: 500, disposalMethod: '领用出库', h2Ref: '',
          isAbnormal: '是',
        }),
        normalizeDisposalRow({
          name: 'B', originalCost: 500, disposalMethod: '报废', h2Ref: '',
          check1: true, check2: true, check3: true, check4: true,
        }),
      ]
      const s = calcDisposalSummary(rows, 2000)
      expect(s.checkedCount).toBe(2)
      expect(s.checkedAmount).toBe(1000)
      expect(s.coverageRate).toBe(50)
      expect(s.missingH2Count).toBe(1)
      expect(s.anomalyCount).toBe(1)
      expect(s.incompleteCheckCount).toBe(1) // 第一行核对未完
    })
  })

  describe('draft helpers', () => {
    it('buildNoteDraft 含检查比例与低覆盖提示', () => {
      const note = buildNoteDraft({
        checkedCount: 2,
        checkedAmount: 100,
        coverageRate: 10,
        anomalyCount: 0,
        incompleteCheckCount: 0,
        missingH2Count: 1,
        issueCount: 1,
      }, 1000)
      expect(note).toContain('10.00%')
      expect(note).toContain('检查比例偏低')
      expect(note).toContain('H2')
    })

    it('buildConclusionDraft 无样本时提示待完成', () => {
      expect(buildConclusionDraft({
        checkedCount: 0,
        checkedAmount: 0,
        coverageRate: 0,
        anomalyCount: 0,
        incompleteCheckCount: 0,
        missingH2Count: 0,
        issueCount: 0,
      })).toContain('尚未抽取')
    })
  })

  describe('getEvidenceHint', () => {
    it('按减少方式返回证据提示', () => {
      expect(getEvidenceHint('领用出库')).toContain('H2')
      expect(getEvidenceHint('出售')).toContain('合同')
    })
  })
})
