/**
 * i6TargetedCheckModel 单元测试 — 对齐 Excel I6-4
 */
import { describe, it, expect } from 'vitest'
import {
  emptyI6TargetedRow,
  normalizeI6TargetedRow,
  summarizeI6Targeted,
  extractI6PeriodMovement,
  formatCoverageLabel,
  formatLayeredCoverageLabel,
  buildI6CoverageFooter,
  suggestAbnormalFromFailedChecks,
  syncSpecificAmountFromRows,
  hasFailedCheck,
  isAbnormalFlag,
  buildI6TargetedConclusionDraft,
  buildI6TargetedAdjDrafts,
  buildI63LinesFromTargetedDrafts,
  mergeI63LinesSkippingExisting,
  I6_4_TEST_CONTENT,
  I6_4_TEST_REASONS,
  I6_4_OBJECTIVES,
  I6_4_ABNORMAL_OPTIONS,
  extractI62ProjectCatalog,
  mapSampledToI6TargetedRow,
  enrichRowsWithI62Projects,
  analyzeI62ProjectConsistency,
} from '../i6TargetedCheckModel'

describe('i6TargetedCheckModel', () => {
  it('测试内容说明为 5 项（第 5 项补全 I6-2/I2 一致性，对齐 Excel 空缺）', () => {
    expect(I6_4_TEST_CONTENT).toHaveLength(5)
    expect(I6_4_TEST_CONTENT[0]).toContain('原始凭证')
    expect(I6_4_TEST_CONTENT[2]).toContain('费用化')
    expect(I6_4_TEST_CONTENT[4]).toContain('I6-2')
    expect(I6_4_TEST_REASONS).toContain('委外研发')
    expect(I6_4_ABNORMAL_OPTIONS).toContain('资本化不当')
  })

  it('测试目标对齐 Excel 发生/分类 + 准确性/列报', () => {
    expect(I6_4_OBJECTIVES[0]).toContain('发生')
    expect(I6_4_OBJECTIVES[0]).toContain('分类')
    expect(I6_4_OBJECTIVES[1]).toContain('准确性')
    expect(I6_4_OBJECTIVES[1]).toContain('列报')
  })

  it('检查比例 = 样本借方 / 总体；总体为 0 时 N/A（避免 #DIV/0!）', () => {
    const rows = [
      emptyI6TargetedRow({ debitAmount: 100 }),
      emptyI6TargetedRow({ debitAmount: 150 }),
    ]
    const s = summarizeI6Targeted(rows, 1000)
    expect(s.checkedDebitTotal).toBe(250)
    expect(s.coverageRate).toBe(25)
    expect(formatCoverageLabel(s.coverageRate)).toBe('25.00%')
    expect(formatLayeredCoverageLabel(s)).toContain('借方 25.00%')

    const empty = summarizeI6Targeted(rows, 0)
    expect(empty.coverageRate).toBeNull()
    expect(formatCoverageLabel(null)).toBe('N/A')

    const footer = buildI6CoverageFooter(empty)
    expect(footer.debitCoverageLabel).toBe('N/A')
  })

  it('从 I6-2 明细推算本期审定合计', () => {
    const rows = [
      { category: '项目A', months: [100, 200], aje: 10, rje: 0 },
      { category: '项目B', months: [50], aje: 0, rje: 5 },
      { category: '合计', months: [] },
    ]
    const mv = extractI6PeriodMovement(JSON.stringify(rows))
    expect(mv.debitTotal).toBe(365)
    expect(mv.source).toBe('I6-2审定合计')
  })

  it('核对× 建议异常类型；特定样本金额同步', () => {
    const row = emptyI6TargetedRow({
      check1: '√', check2: '×', check3: '√', check4: 'N/A', check5: '√',
    })
    expect(hasFailedCheck(row)).toBe(true)
    expect(suggestAbnormalFromFailedChecks(row)).toBe('归集差异')

    const rows = [
      emptyI6TargetedRow({ debitAmount: 300, isSpecific: true, selectionReason: '大额' }),
      emptyI6TargetedRow({ debitAmount: 100 }),
    ]
    expect(syncSpecificAmountFromRows(rows)).toBe(300)
  })

  it('抽凭映射可挂接 I6-2 项目', () => {
    const catalog = extractI62ProjectCatalog([
      { category: '智能平台研发', months: [1000], aje: 0, rje: 0 },
    ])
    const mapped = mapSampledToI6TargetedRow(
      { summary: '智能平台研发人工费', debitAmount: 500, voucherNo: '记-001' },
      catalog,
    )
    expect(mapped.projectName).toBe('智能平台研发')

    const { linked } = enrichRowsWithI62Projects(
      [emptyI6TargetedRow({ businessDesc: '智能平台研发材料', projectName: '' })],
      catalog,
    )
    expect(linked).toBe(1)
  })

  it('analyzeI62ProjectConsistency 识别不在 I6-2 的项目与未填项', () => {
    const catalog = extractI62ProjectCatalog([
      { category: '智能平台研发', months: [1000], aje: 0, rje: 0 },
    ])
    const report = analyzeI62ProjectConsistency(
      [
        emptyI6TargetedRow({ projectName: '智能平台研发' }),
        emptyI6TargetedRow({ projectName: '未知项目' }),
        emptyI6TargetedRow({ projectName: '' }),
      ],
      catalog,
    )
    expect(report.unmatchedCount).toBe(1)
    expect(report.missingProjectCount).toBe(1)
    expect(report.orphanNames).toEqual(['未知项目'])
  })

  it('结论草稿包含覆盖率与专项风险', () => {
    const text = buildI6TargetedConclusionDraft({
      sampleCount: 10,
      coverageLabel: '借方 30.00%（特定 10.00% + 抽样 20.00%）',
      anomalyCount: 0,
      failCheckCount: 0,
      testReasons: ['大额'],
      riskFocus: {
        completeness: '',
        allocation: '',
        i2Consistency: '',
        completenessConclusion: '归集完整',
        allocationConclusion: '',
        i2ConsistencyConclusion: '',
        legacyDeductionNote: '',
      },
    })
    expect(text).toContain('10 笔')
    expect(text).toContain('费用归集：归集完整')
    expect(text).toContain('I6-2')
  })

  it('normalize 兼容旧字段名', () => {
    const row = normalizeI6TargetedRow({ rdProject: '测试项目', amount: 88 })
    expect(row.projectName).toBe('测试项目')
    expect(row.debitAmount).toBe(88)
  })

  it('buildI6TargetedAdjDrafts 对资本化核对×生成建议', () => {
    const row = emptyI6TargetedRow({
      voucherNo: '记-99',
      debitAmount: 1000,
      check1: '√', check2: '√', check3: '×', check4: '√', check5: '√',
    })
    const drafts = buildI6TargetedAdjDrafts([row])
    expect(drafts).toHaveLength(1)
    expect(drafts[0].draftKind).toBe('capitalize')
    expect(drafts[0].suggestedEntry).toContain('I6-3')
    expect(isAbnormalFlag('资本化不当')).toBe(true)
    expect(isAbnormalFlag('否')).toBe(false)
  })

  it('buildI63LinesFromTargetedDrafts 生成平衡借贷对并去重', () => {
    const drafts = buildI6TargetedAdjDrafts([
      emptyI6TargetedRow({
        projectName: '平台A',
        voucherNo: '记-1',
        debitAmount: 500,
        check1: '√', check2: '√', check3: '×', check4: '√', check5: '√',
      }),
    ])
    const lines = buildI63LinesFromTargetedDrafts(drafts)
    expect(lines).toHaveLength(2)
    expect(lines[0].accountName).toBe('开发支出')
    expect(lines[0].accountCode).toBe('1717')
    expect(lines[0].category).toBe('账项调整')
    expect(lines[0].debitAmount).toBe(500)
    expect(lines[1].creditAmount).toBe(500)

    const { merged, added } = mergeI63LinesSkippingExisting(lines, lines)
    expect(added).toBe(0)
    expect(merged).toHaveLength(2)
  })
})
