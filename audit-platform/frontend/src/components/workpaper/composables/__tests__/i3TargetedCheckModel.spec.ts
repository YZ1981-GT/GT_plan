/**
 * i3TargetedCheckModel 单元测试 — 对齐 Excel I3-5
 */
import { describe, it, expect } from 'vitest'
import {
  emptyI3TargetedRow,
  normalizeI3TargetedRow,
  normalizeI3TargetedRiskFocus,
  summarizeI3Targeted,
  extractI3PeriodMovement,
  formatCoverageLabel,
  formatLayeredCoverageLabel,
  hasFailedCheck,
  isAbnormalFlag,
  buildI3TargetedConclusionDraft,
  buildI3TargetedAdjDrafts,
  I3_5_TEST_CONTENT,
  I3_5_TEST_REASONS,
} from '../i3TargetedCheckModel'

describe('i3TargetedCheckModel', () => {
  it('测试内容说明为 5 项（第 5 项补全商誉特有核对）', () => {
    expect(I3_5_TEST_CONTENT).toHaveLength(5)
    expect(I3_5_TEST_CONTENT[0]).toContain('原始凭证')
    expect(I3_5_TEST_CONTENT[4]).toContain('I3-4')
    expect(I3_5_TEST_REASONS).toContain('大额')
  })

  it('检查比例 = 样本借方 / 总体；总体为 0 时 N/A（避免 #DIV/0!）', () => {
    const rows = [
      emptyI3TargetedRow({ debitAmount: 100, creditAmount: 20 }),
      emptyI3TargetedRow({ debitAmount: 150, creditAmount: 30 }),
    ]
    const s = summarizeI3Targeted(rows, 1000, 200)
    expect(s.checkedDebitTotal).toBe(250)
    expect(s.checkedCreditTotal).toBe(50)
    expect(s.coverageRate).toBe(25)
    expect(s.creditCoverageRate).toBe(25)
    expect(formatCoverageLabel(s.coverageRate)).toBe('25.00%')
    expect(formatLayeredCoverageLabel(s)).toContain('借方 25.00%')

    const empty = summarizeI3Targeted(rows, 0, 0)
    expect(empty.coverageRate).toBeNull()
    expect(empty.creditCoverageRate).toBeNull()
    expect(formatCoverageLabel(null)).toBe('N/A')
  })

  it('核对× 计为失败；异常标记识别', () => {
    const row = emptyI3TargetedRow({ check1: '√', check2: '×', check3: '√', check4: 'N/A', check5: '√' })
    expect(hasFailedCheck(row)).toBe(true)
    expect(isAbnormalFlag('是')).toBe(true)
    expect(isAbnormalFlag('否')).toBe(false)
    expect(isAbnormalFlag('入账差异')).toBe(true)
  })

  it('从 I3-2 汇总本期发生额（当年新确认原值 + 本期减值）', () => {
    const mv = extractI3PeriodMovement([
      { investee: 'A', goodwillOriginal: 1000, currentImpairment: 100, mergerDate: '2026-03-01' },
      { investee: 'B', goodwillOriginal: 500, currentImpairment: 50, acquisitionDate: '2024-01-01' },
      { investee: '合计', goodwillOriginal: 9999, currentImpairment: 999 },
    ], 2026)
    expect(mv.debitTotal).toBe(1000)
    expect(mv.creditTotal).toBe(150)
    expect(mv.originalTotal).toBe(1500)
  })

  it('无并购日时不把期初原值误计入本期借方', () => {
    const mv = extractI3PeriodMovement([
      { investee: '旧商誉', goodwillOriginal: 800, currentImpairment: 0 },
    ], 2026)
    expect(mv.debitTotal).toBe(0)
    expect(mv.originalTotal).toBe(800)
  })

  it('优先使用 I3-2 原生 periodDebit/periodCredit（滚动发生额）', () => {
    const mv = extractI3PeriodMovement([
      {
        investee: 'A',
        goodwillOriginal: 5000,
        costIncrease: 1200,
        costDecrease: 100,
        impIncrease: 80,
        periodDebit: 1200,
        periodCredit: 180,
      },
    ], 2026)
    expect(mv.debitTotal).toBe(1200)
    expect(mv.creditTotal).toBe(180)
    expect(mv.source).toBe('I3-2本期发生额')
  })

  it('兼容旧段落型 I3-5-targeted 数据结构', () => {
    const rf = normalizeI3TargetedRiskFocus({
      sections: {
        externalIndicators: '市价下跌',
        internalIndicators: '业绩不达预期',
        mergerCostAllocation: '已分摊',
        synergyEffect: '协同合理',
        managementBasis: '按分部监控',
        priorYearConsistency: '与上年一致',
        internalReportConsistency: '与内部报告一致',
        cguChangeStatus: '无变更',
      },
      conclusions: {
        externalIndicators: '存在减值迹象',
        internalIndicators: '需进一步判断',
        mergerCostAllocation: '合理',
        priorYearConsistency: '一致',
      },
      overallConclusion: '综合可接受',
    })
    expect(rf.externalIndicators).toBe('市价下跌')
    expect(rf.externalConclusion).toBe('存在减值迹象')
    expect(rf.cguAllocation).toContain('已分摊')
    expect(rf.allocationConclusion).toBe('合理')
    expect(rf.consistencyConclusion).toBe('一致')
  })

  it('兼容旧行字段 investee/amount', () => {
    const row = normalizeI3TargetedRow({ investee: '子公司X', amount: 88, voucherNo: '记-1' })
    expect(row.projectName).toBe('子公司X')
    expect(row.debitAmount).toBe(88)
    expect(row.voucherNo).toBe('记-1')
  })

  it('结论草稿包含样本量、测试原因与异常摘要', () => {
    const text = buildI3TargetedConclusionDraft({
      sampleCount: 3,
      coverageLabel: '40.00%',
      creditCoverageLabel: 'N/A',
      anomalyCount: 0,
      failCheckCount: 0,
      testReasons: ['大额', '关联方'],
      riskFocus: {
        externalIndicators: '',
        internalIndicators: '',
        cguAllocation: '',
        cguConsistency: '',
        externalConclusion: '无减值迹象',
        internalConclusion: '',
        allocationConclusion: '合理',
        consistencyConclusion: '',
      },
    })
    expect(text).toContain('3 笔')
    expect(text).toContain('大额')
    expect(text).toContain('外部迹象：无减值迹象')
    expect(text).toContain('I3-6')
  })

  it('核对× 生成调整建议草稿', () => {
    const drafts = buildI3TargetedAdjDrafts([
      emptyI3TargetedRow({
        voucherNo: '记-9',
        debitAmount: 100,
        check3: '×',
        check5: '×',
      }),
    ])
    expect(drafts).toHaveLength(1)
    expect(drafts[0].failedChecks.some((c) => c.startsWith('3.'))).toBe(true)
    expect(drafts[0].suggestedEntry).toContain('CGU')
  })
})
