/**
 * i2TargetedCheckModel 单元测试 — 对齐 Excel I2-12
 */
import { describe, it, expect } from 'vitest'
import {
  emptyI2TargetedRow,
  normalizeI2TargetedRow,
  normalizeI2TargetedRiskFocus,
  summarizeI2Targeted,
  extractI2CapIncreaseTotal,
  formatCoverageLabel,
  hasFailedCheck,
  isAbnormalFlag,
  buildI2TargetedConclusionDraft,
  I2_12_TEST_CONTENT,
} from '../i2TargetedCheckModel'

describe('i2TargetedCheckModel', () => {
  it('测试内容说明为 5 项（对齐 Excel）', () => {
    expect(I2_12_TEST_CONTENT).toHaveLength(5)
    expect(I2_12_TEST_CONTENT[0]).toContain('原始凭证')
  })

  it('检查比例 = 样本借方 / 总体；总体为 0 时 N/A', () => {
    const rows = [
      emptyI2TargetedRow({ debitAmount: 100 }),
      emptyI2TargetedRow({ debitAmount: 150 }),
    ]
    const s = summarizeI2Targeted(rows, 1000)
    expect(s.checkedDebitTotal).toBe(250)
    expect(s.coverageRate).toBe(25)
    expect(formatCoverageLabel(s.coverageRate)).toBe('25.00%')

    const empty = summarizeI2Targeted(rows, 0)
    expect(empty.coverageRate).toBeNull()
    expect(formatCoverageLabel(null)).toBe('N/A')
  })

  it('核对× 计为失败；异常标记识别', () => {
    const row = emptyI2TargetedRow({ check1: '√', check2: '×', check3: '√', check4: 'N/A', check5: '√' })
    expect(hasFailedCheck(row)).toBe(true)
    expect(isAbnormalFlag('是')).toBe(true)
    expect(isAbnormalFlag('否')).toBe(false)
  })

  it('从 I2-2 汇总本期资本化增加（跳过合计行）', () => {
    const total = extractI2CapIncreaseTotal([
      { projectName: 'A', capIncrease: 1000 },
      { name: 'B', capIncrease: 500.5 },
      { projectName: '合计', capIncrease: 9999 },
    ])
    expect(total).toBe(1500.5)
  })

  it('兼容旧段落型 I2-12-targeted 数据结构', () => {
    const rf = normalizeI2TargetedRiskFocus({
      sections: { deductionCompliance: '已核查', capitalizationRatio: '合理', projectProgress: '正常' },
      conclusions: { deductionCompliance: '合规', capitalizationRatio: '合理', projectProgress: '正常' },
    })
    expect(rf.deductionCompliance).toBe('已核查')
    expect(rf.deductionConclusion).toBe('合规')
    expect(rf.capitalizationConclusion).toBe('合理')
  })

  it('兼容旧行字段 name/amount', () => {
    const row = normalizeI2TargetedRow({ name: '项目X', amount: 88, voucherNo: '记-1' })
    expect(row.projectName).toBe('项目X')
    expect(row.debitAmount).toBe(88)
    expect(row.voucherNo).toBe('记-1')
  })

  it('结论草稿包含样本量与异常摘要', () => {
    const text = buildI2TargetedConclusionDraft({
      sampleCount: 5,
      coverageLabel: '30.00%',
      anomalyCount: 0,
      failCheckCount: 0,
      riskFocus: {
        deductionCompliance: '',
        capitalizationRatio: '',
        projectProgress: '',
        deductionConclusion: '合规',
        capitalizationConclusion: '合理',
        progressConclusion: '正常',
      },
    })
    expect(text).toContain('5 笔')
    expect(text).toContain('30.00%')
    expect(text).toContain('未见重大异常')
    expect(text).toContain('加计扣除：合规')
  })
})
