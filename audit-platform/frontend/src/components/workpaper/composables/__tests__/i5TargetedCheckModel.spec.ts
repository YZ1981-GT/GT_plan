/**
 * i5TargetedCheckModel 单元测试 — 对齐 Excel I5-4
 */
import { describe, it, expect } from 'vitest'
import {
  emptyI5TargetedRow,
  normalizeI5TargetedRow,
  normalizeI5TargetedRiskFocus,
  summarizeI5Targeted,
  extractI5PeriodMovement,
  formatCoverageLabel,
  formatLayeredCoverageLabel,
  hasFailedCheck,
  isAbnormalFlag,
  buildI5TargetedConclusionDraft,
  buildI5TargetedAdjDrafts,
  buildI53LinesFromTargetedDrafts,
  mergeI53LinesSkippingExisting,
  suggestAbnormalFromFailedChecks,
  syncSpecificAmountFromRows,
  checkI5SpecificAmountConsistency,
  extractI52ProjectCatalog,
  matchI52ProjectName,
  riskFocusIncomplete,
  emptyI5TargetedRiskFocus,
  I5_4_TEST_CONTENT,
  I5_4_TEST_REASONS,
  I5_4_OBJECTIVES,
  I5_4_ABNORMAL_OPTIONS,
} from '../i5TargetedCheckModel'

describe('i5TargetedCheckModel', () => {
  it('测试内容说明为 5 项（第 5 项对齐 I5-2 分类/期限一致性）', () => {
    expect(I5_4_TEST_CONTENT).toHaveLength(5)
    expect(I5_4_TEST_CONTENT[0]).toContain('原始凭证')
    expect(I5_4_TEST_CONTENT[2]).toContain('分类')
    expect(I5_4_TEST_CONTENT[4]).toContain('I5-2')
    expect(I5_4_TEST_REASONS).toContain('大额')
    expect(I5_4_TEST_REASONS).toContain('分类变更')
    expect(I5_4_TEST_REASONS).toContain('可回收性疑虑')
  })

  it('测试目标对齐 Excel 存在/发生、计价和分摊并落到实质认定', () => {
    expect(I5_4_OBJECTIVES[0]).toContain('存在/发生')
    expect(I5_4_OBJECTIVES[0]).toContain('计价和分摊')
    expect(I5_4_OBJECTIVES[0]).toMatch(/分类|期限|可回收/)
    expect(I5_4_ABNORMAL_OPTIONS).toContain('分类不当')
    expect(I5_4_ABNORMAL_OPTIONS).toContain('入账差异')
  })

  it('检查比例 = 样本借方 / 总体；总体为 0 时 N/A（避免 #DIV/0!）', () => {
    const rows = [
      emptyI5TargetedRow({ debitAmount: 100, creditAmount: 20 }),
      emptyI5TargetedRow({ debitAmount: 150, creditAmount: 30 }),
    ]
    const s = summarizeI5Targeted(rows, 1000, 200)
    expect(s.checkedDebitTotal).toBe(250)
    expect(s.checkedCreditTotal).toBe(50)
    expect(s.coverageRate).toBe(25)
    expect(s.creditCoverageRate).toBe(25)
    expect(formatCoverageLabel(s.coverageRate)).toBe('25.00%')
    expect(formatLayeredCoverageLabel(s)).toContain('借方 25.00%')

    const empty = summarizeI5Targeted(rows, 0, 0)
    expect(empty.coverageRate).toBeNull()
    expect(empty.creditCoverageRate).toBeNull()
    expect(formatCoverageLabel(null)).toBe('N/A')
  })

  it('特定/抽样分层覆盖率与特定金额同步', () => {
    const rows = [
      emptyI5TargetedRow({ debitAmount: 400, isSpecific: true, selectionReason: '大额' }),
      emptyI5TargetedRow({ debitAmount: 100, isSpecific: false }),
    ]
    const s = summarizeI5Targeted(rows, 1000)
    expect(s.specificCount).toBe(1)
    expect(s.specificDebitTotal).toBe(400)
    expect(s.specificCoverageRate).toBe(40)
    expect(s.samplingCoverageRate).toBe(10)
    expect(syncSpecificAmountFromRows(rows)).toBe(400)
  })

  it('核对× 建议异常类型', () => {
    expect(suggestAbnormalFromFailedChecks(emptyI5TargetedRow({ check1: '×' }))).toBe('入账差异')
    expect(suggestAbnormalFromFailedChecks(emptyI5TargetedRow({ check3: '×' }))).toBe('分类不当')
    expect(suggestAbnormalFromFailedChecks(emptyI5TargetedRow({ check4: '×' }))).toBe('跨期')
    expect(suggestAbnormalFromFailedChecks(emptyI5TargetedRow({ check5: '×' }))).toBe('期限未重分类')
  })

  it('特定样本金额容差校验', () => {
    const ok = checkI5SpecificAmountConsistency(400, 400)
    expect(ok.ok).toBe(true)
    expect(ok.severity).toBe('ok')

    const warn = checkI5SpecificAmountConsistency(400, 0)
    expect(warn.ok).toBe(false)
    expect(warn.severity).toBe('warning')
    expect(warn.message).toContain('尚无特定样本')
  })

  it('从 I5-2 提取项目目录并可模糊匹配', () => {
    const catalog = extractI52ProjectCatalog([
      { projectName: '预付购房款-XX项目', increase: 1000 },
      { name: '押金B', increase: 50 },
      { projectName: '合计', increase: 9999 },
    ])
    expect(catalog).toHaveLength(2)
    expect(catalog[0].projectName).toBe('预付购房款-XX项目')
    expect(matchI52ProjectName(catalog, { summary: '支付预付购房款-XX项目首期' })).toBe('预付购房款-XX项目')
  })

  it('有样本但专项风险结论全空时提示', () => {
    expect(riskFocusIncomplete(emptyI5TargetedRiskFocus(), 3)).toBe(true)
    expect(riskFocusIncomplete(emptyI5TargetedRiskFocus({
      classificationConclusion: '分类正确，未见需重分类事项',
    }), 3)).toBe(false)
    expect(riskFocusIncomplete(emptyI5TargetedRiskFocus(), 0)).toBe(false)
  })

  it('核对× 计为失败；异常标记识别', () => {
    const row = emptyI5TargetedRow({ check1: '√', check2: '×', check3: '√', check4: 'N/A', check5: '√' })
    expect(hasFailedCheck(row)).toBe(true)
    expect(isAbnormalFlag('是')).toBe(true)
    expect(isAbnormalFlag('否')).toBe(false)
    expect(isAbnormalFlag('分类不当')).toBe(true)
  })

  it('从 I5-2 汇总本期发生额（本期增加=借方，本期减少=贷方）', () => {
    const mv = extractI5PeriodMovement([
      { name: '预付购房款A', originalAmount: 1000, increase: 1000, decrease: 0 },
      { name: '押金B', originalAmount: 500, increase: 0, decrease: 50 },
      { name: '合计', originalAmount: 9999, increase: 9999 },
    ])
    expect(mv.debitTotal).toBe(1000)
    expect(mv.creditTotal).toBe(50)
    expect(mv.originalTotal).toBe(1500)
    expect(mv.source).toBe('I5-2本期发生额')
  })

  it('无滚动字段时按发生日年份代理原值计入本期借方', () => {
    const mv = extractI5PeriodMovement([
      { name: '旧项目', originalAmount: 800, incurredDate: '2026-05-01' },
      { name: '往年项目', originalAmount: 300, incurredDate: '2024-01-01' },
    ], 2026)
    expect(mv.debitTotal).toBe(800)
    expect(mv.originalTotal).toBe(1100)
    expect(mv.source).toBe('I5-2')
  })

  it('兼容旧段落型 radio+textarea 拼装的迁移对象（分类/期限/可回收性）', () => {
    const rf = normalizeI5TargetedRiskFocus({
      classificationItems: '应重分类到长期待摊费用：异常',
      classificationText: '发现1笔应重分类到长期待摊费用',
      maturityItems: '',
      maturityText: '期限适当，未见异常',
      recoverabilityItems: '对方信用恶化/违约：异常',
      recoverabilityText: '发现1笔对方信用恶化',
    })
    expect(rf.classification).toContain('应重分类到长期待摊费用')
    expect(rf.classification).toContain('发现1笔应重分类到长期待摊费用')
    expect(rf.maturity).toBe('期限适当，未见异常')
    expect(rf.recoverability).toContain('对方信用恶化')
  })

  it('兼容旧行字段 name/amount', () => {
    const row = normalizeI5TargetedRow({ name: '预付购房款-XX项目', amount: 88, voucherNo: '记-1' })
    expect(row.projectName).toBe('预付购房款-XX项目')
    expect(row.debitAmount).toBe(88)
    expect(row.voucherNo).toBe('记-1')
  })

  it('结论草稿包含样本量、测试原因与专项风险摘要', () => {
    const text = buildI5TargetedConclusionDraft({
      sampleCount: 3,
      coverageLabel: '40.00%',
      creditCoverageLabel: 'N/A',
      anomalyCount: 0,
      failCheckCount: 0,
      testReasons: ['大额', '分类变更'],
      riskFocus: {
        classification: '',
        maturity: '',
        recoverability: '',
        classificationConclusion: '分类正确，未见需重分类事项',
        maturityConclusion: '',
        recoverabilityConclusion: '',
      },
    })
    expect(text).toContain('3 笔')
    expect(text).toContain('大额')
    expect(text).toContain('分类正确性：分类正确，未见需重分类事项')
    expect(text).toContain('I5-2')
  })

  it('核对× 生成调整建议草稿（分类判断相关）', () => {
    const drafts = buildI5TargetedAdjDrafts([
      emptyI5TargetedRow({
        voucherNo: '记-9',
        debitAmount: 100,
        check3: '×',
        check5: '×',
      }),
    ])
    expect(drafts).toHaveLength(1)
    expect(drafts[0].failedChecks.some((c) => c.startsWith('3.'))).toBe(true)
    expect(drafts[0].draftKind).toBe('expense_reclass')
    expect(drafts[0].suggestedEntry).toContain('分类')
  })

  it('核对× 跨期 → cutoff 草稿可推 I5-3', () => {
    const drafts = buildI5TargetedAdjDrafts([
      emptyI5TargetedRow({ voucherNo: '记-1', debitAmount: 50, check4: '×' }),
    ])
    expect(drafts[0].draftKind).toBe('cutoff')
    const lines = buildI53LinesFromTargetedDrafts(drafts)
    expect(lines).toHaveLength(2)
    expect(lines.reduce((s, r) => s + r.debitAmount, 0)).toBe(50)
  })

  it('核对× 期限 → current_reclass（I5-2 一年内到期）', () => {
    const detailRows = [{
      projectName: '预付工程款',
      maturityDate: '2026-06-30',
      gross: { auditedEnding: 80000 },
      impairment: { auditedEnding: 0 },
    }]
    const drafts = buildI5TargetedAdjDrafts([
      emptyI5TargetedRow({ voucherNo: '记-2', projectName: '预付工程款', debitAmount: 80000, check5: '×' }),
    ], { detailRows, auditYear: 2025 })
    expect(drafts[0].draftKind).toBe('current_reclass')
    const lines = buildI53LinesFromTargetedDrafts(drafts)
    expect(lines.some((l) => l.accountCode === '1461')).toBe(true)
  })

  it('mergeI53LinesSkippingExisting 去重', () => {
    const lines = buildI53LinesFromTargetedDrafts([
      {
        voucherNo: 'A', projectName: '预付工程款', debitAmount: 100, creditAmount: 0,
        failedChecks: ['4.x'], suggestedEntry: '', suggestedNote: '', draftKind: 'cutoff', amount: 100,
      },
    ])
    const { added, merged } = mergeI53LinesSkippingExisting([], lines)
    expect(added).toBe(2)
    const again = mergeI53LinesSkippingExisting(merged, lines)
    expect(again.added).toBe(0)
  })
})
