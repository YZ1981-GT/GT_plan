/**
 * i4TargetedCheckModel 单元测试 — 对齐 Excel I4-5
 */
import { describe, it, expect } from 'vitest'
import {
  emptyI4TargetedRow,
  normalizeI4TargetedRow,
  normalizeI4TargetedRiskFocus,
  summarizeI4Targeted,
  extractI4PeriodMovement,
  formatCoverageLabel,
  formatLayeredCoverageLabel,
  buildI4CoverageFooter,
  suggestAbnormalFromFailedChecks,
  syncSpecificAmountFromRows,
  hasFailedCheck,
  isAbnormalFlag,
  buildI4TargetedConclusionDraft,
  buildI4TargetedAdjDrafts,
  I4_5_TEST_CONTENT,
  I4_5_TEST_REASONS,
  I4_5_OBJECTIVES,
  I4_5_ABNORMAL_OPTIONS,
  buildI4CoverageExpansionAdvice,
  buildI4CreditCoverageExpansionAdvice,
  isCoverageNoteSatisfied,
  checkI4SpecificAmountConsistency,
  buildI4SamplingPresetFromTestReasons,
  applyI4SelectionReasonsToSamples,
  crossCheckI45WithI44,
  buildI44CrossNoteBlock,
  parseI44PolicySnapshot,
  emptyI4TargetedRiskFocus,
  extractI42ProjectCatalog,
  matchI42ProjectName,
  mapSampledToI4TargetedRow,
  enrichRowsWithI42Projects,
  buildI43LinesFromTargetedDrafts,
  mergeI43LinesSkippingExisting,
} from '../i4TargetedCheckModel'

describe('i4TargetedCheckModel', () => {
  it('测试内容说明为 5 项（第 5 项对齐 I4-2 受益期一致性，补全 Excel 空缺）', () => {
    expect(I4_5_TEST_CONTENT).toHaveLength(5)
    expect(I4_5_TEST_CONTENT[0]).toContain('原始凭证')
    expect(I4_5_TEST_CONTENT[2]).toContain('资本化')
    expect(I4_5_TEST_CONTENT[4]).toContain('I4-2')
    expect(I4_5_TEST_REASONS).toContain('大额')
    expect(I4_5_TEST_REASONS).toContain('受益期变更')
  })

  it('测试目标对齐 Excel 认定并落到资本化归属/受益期', () => {
    expect(I4_5_OBJECTIVES[0]).toContain('存在/发生')
    expect(I4_5_OBJECTIVES[0]).toContain('资本化归属')
    expect(I4_5_OBJECTIVES[0]).toContain('计价和分摊')
    expect(I4_5_OBJECTIVES[1]).toContain('I4-2')
    expect(I4_5_ABNORMAL_OPTIONS).toContain('受益期不一致')
  })

  it('检查比例 = 样本借方 / 总体；总体为 0 时 N/A（避免 #DIV/0!）', () => {
    const rows = [
      emptyI4TargetedRow({ debitAmount: 100, creditAmount: 20 }),
      emptyI4TargetedRow({ debitAmount: 150, creditAmount: 30 }),
    ]
    const s = summarizeI4Targeted(rows, 1000, 200)
    expect(s.checkedDebitTotal).toBe(250)
    expect(s.checkedCreditTotal).toBe(50)
    expect(s.coverageRate).toBe(25)
    expect(s.creditCoverageRate).toBe(25)
    expect(formatCoverageLabel(s.coverageRate)).toBe('25.00%')
    expect(formatLayeredCoverageLabel(s)).toContain('借方 25.00%')

    const empty = summarizeI4Targeted(rows, 0, 0)
    expect(empty.coverageRate).toBeNull()
    expect(empty.creditCoverageRate).toBeNull()
    expect(formatCoverageLabel(null)).toBe('N/A')

    const footer = buildI4CoverageFooter(empty, 0)
    expect(footer.debitCoverageLabel).toBe('N/A')
    expect(footer.layeredCoverageLabel).toBe('N/A')
  })

  it('特定/抽样分层覆盖率与特定样本金额同步', () => {
    const rows = [
      emptyI4TargetedRow({ debitAmount: 400, isSpecific: true, selectionReason: '大额' }),
      emptyI4TargetedRow({ debitAmount: 100 }),
    ]
    const s = summarizeI4Targeted(rows, 1000)
    expect(s.specificCount).toBe(1)
    expect(s.specificDebitTotal).toBe(400)
    expect(s.samplingDebitTotal).toBe(100)
    expect(s.specificCoverageRate).toBe(40)
    expect(s.samplingCoverageRate).toBe(10)
    expect(syncSpecificAmountFromRows(rows)).toBe(400)
  })

  it('核对× 建议异常类型；异常标记识别', () => {
    const row = emptyI4TargetedRow({ check1: '√', check2: '×', check3: '√', check4: 'N/A', check5: '√' })
    expect(hasFailedCheck(row)).toBe(true)
    expect(suggestAbnormalFromFailedChecks(row)).toBe('入账差异')
    expect(suggestAbnormalFromFailedChecks(emptyI4TargetedRow({ check3: '×' }))).toBe('资本化不当')
    expect(suggestAbnormalFromFailedChecks(emptyI4TargetedRow({ check4: '×' }))).toBe('跨期')
    expect(suggestAbnormalFromFailedChecks(emptyI4TargetedRow({ check5: '×' }))).toBe('受益期不一致')
    expect(isAbnormalFlag('是')).toBe(true)
    expect(isAbnormalFlag('否')).toBe(false)
    expect(isAbnormalFlag('资本化不当')).toBe(true)
  })

  it('从 I4-2 汇总本期发生额（本期增加=借方，本期减少=贷方）', () => {
    const mv = extractI4PeriodMovement([
      { projectName: '装修费A', originalAmount: 1000, currentIncrease: 1000, currentDecrease: 0 },
      { projectName: '开办费B', originalAmount: 500, currentIncrease: 0, currentDecrease: 50 },
      { projectName: '合计', originalAmount: 9999, currentIncrease: 9999 },
    ])
    expect(mv.debitTotal).toBe(1000)
    expect(mv.creditTotal).toBe(50)
    expect(mv.originalTotal).toBe(1500)
    expect(mv.source).toBe('I4-2本期发生额')
  })

  it('无滚动字段时按发生日年份代理原值计入本期借方', () => {
    const mv = extractI4PeriodMovement([
      { projectName: '旧项目', originalAmount: 800, occurDate: '2026-05-01' },
      { projectName: '往年项目', originalAmount: 300, occurDate: '2024-01-01' },
    ], 2026)
    expect(mv.debitTotal).toBe(800)
    expect(mv.originalTotal).toBe(1100)
    expect(mv.source).toBe('I4-2')
  })

  it('兼容旧段落型分散 key 拼装的迁移对象（大额新增/受益期变更/提前终止）', () => {
    const rf = normalizeI4TargetedRiskFocus({
      majorAddition: '本期新增装修费100万，凭证齐全',
      majorAdditionConclusion: '大额新增真实完整，资本化判断恰当',
      benefitChange: '本期无变更',
      benefitChangeConclusion: '受益期估计合理，本期无变更',
      earlyTermination: '',
      earlyTerminationConclusion: '本期无提前终止项目',
    })
    expect(rf.majorAddition).toContain('装修费')
    expect(rf.majorAdditionConclusion).toBe('大额新增真实完整，资本化判断恰当')
    expect(rf.benefitChangeConclusion).toBe('受益期估计合理，本期无变更')
    expect(rf.earlyTerminationConclusion).toBe('本期无提前终止项目')
  })

  it('兼容旧行字段 name/amount', () => {
    const row = normalizeI4TargetedRow({ name: '办公室装修', amount: 88, voucherNo: '记-1' })
    expect(row.projectName).toBe('办公室装修')
    expect(row.debitAmount).toBe(88)
    expect(row.voucherNo).toBe('记-1')
  })

  it('结论草稿包含样本量、测试原因与专项风险摘要', () => {
    const text = buildI4TargetedConclusionDraft({
      sampleCount: 3,
      coverageLabel: '40.00%',
      creditCoverageLabel: 'N/A',
      anomalyCount: 0,
      failCheckCount: 0,
      testReasons: ['大额', '受益期变更'],
      riskFocus: {
        majorAddition: '',
        benefitChange: '',
        earlyTermination: '',
        majorAdditionConclusion: '大额新增真实完整，资本化判断恰当',
        benefitChangeConclusion: '',
        earlyTerminationConclusion: '',
      },
    })
    expect(text).toContain('3 笔')
    expect(text).toContain('大额')
    expect(text).toContain('大额新增：大额新增真实完整，资本化判断恰当')
    expect(text).toContain('I4-2')
  })

  it('核对× 生成调整建议草稿（资本化判断相关）', () => {
    const drafts = buildI4TargetedAdjDrafts([
      emptyI4TargetedRow({
        voucherNo: '记-9',
        debitAmount: 100,
        check3: '×',
        check5: '×',
      }),
    ])
    expect(drafts).toHaveLength(1)
    expect(drafts[0].failedChecks.some((c) => c.startsWith('3.'))).toBe(true)
    expect(drafts[0].draftKind).toBe('expense_reclass')
    expect(drafts[0].suggestedEntry).toContain('资本化')
  })

  it('抽凭摘要模糊挂接 I4-2 项目名', () => {
    const catalog = extractI42ProjectCatalog([
      { projectName: '办公室装修费', unadjIncrease: 100 },
      { projectName: '租入固定资产改良', unadjIncrease: 50 },
      { projectName: '合计', unadjIncrease: 999 },
    ])
    expect(catalog).toHaveLength(2)
    const hit = matchI42ProjectName({ businessDesc: '支付办公室装修费尾款' }, catalog)
    expect(hit?.projectName).toBe('办公室装修费')
    const row = mapSampledToI4TargetedRow(
      { voucherNo: '记-1', summary: '办公室装修费验收', accountName: '长期待摊费用', debitAmount: 10 },
      catalog,
    )
    expect(row.projectName).toBe('办公室装修费')
    const { linked } = enrichRowsWithI42Projects(
      [emptyI4TargetedRow({ businessDesc: '租入固定资产改良支出', projectName: '' })],
      catalog,
    )
    expect(linked).toBe(1)
  })

  it('核对× 草稿可生成 I4-3 分录行并按说明+科目去重', () => {
    const drafts = buildI4TargetedAdjDrafts([
      emptyI4TargetedRow({ voucherNo: '记-3', projectName: '装修A', debitAmount: 80, check3: '×' }),
      emptyI4TargetedRow({ voucherNo: '记-4', projectName: '开办', debitAmount: 20, check4: '×' }),
    ])
    const lines = buildI43LinesFromTargetedDrafts(drafts)
    expect(lines.length).toBe(4) // 两组借贷
    expect(lines.every((l) => l.entryType === 'AJE')).toBe(true)
    // 已有第一组分录的借方行 → 只跳过该科目，贷方仍可补；此处模拟整组分录已在
    const existing = [
      { description: lines[0].description, accountCode: '6602' },
      { description: lines[0].description, accountCode: '1801' },
    ]
    const { added } = mergeI43LinesSkippingExisting(existing, lines)
    expect(added).toBe(2) // 仅第二组跨期两条
  })

  it('检查比例偏低时给出强制扩样建议（金额与约估笔数）', () => {
    const rows = [
      emptyI4TargetedRow({ debitAmount: 100 }),
      emptyI4TargetedRow({ debitAmount: 100 }),
    ]
    const s = summarizeI4Targeted(rows, 1000)
    expect(s.coverageRate).toBe(20)
    const advice = buildI4CoverageExpansionAdvice(s, 40)
    expect(advice.needed).toBe(true)
    expect(advice.side).toBe('debit')
    expect(advice.additionalDebitNeeded).toBe(200) // 40%*1000 - 200
    expect(advice.suggestedExtraSamples).toBe(2)
    expect(advice.noteTemplate).toContain('检查比例偏低')
    expect(isCoverageNoteSatisfied('', advice)).toBe(false)
    expect(isCoverageNoteSatisfied(advice.noteTemplate, advice)).toBe(true)
    expect(buildI4CoverageExpansionAdvice(s, 20).needed).toBe(false)
  })

  it('贷方检查比例偏低时给出对称扩样建议', () => {
    const rows = [
      emptyI4TargetedRow({ creditAmount: 50 }),
      emptyI4TargetedRow({ creditAmount: 50 }),
    ]
    const s = summarizeI4Targeted(rows, 0, 1000)
    expect(s.creditCoverageRate).toBe(10)
    const advice = buildI4CreditCoverageExpansionAdvice(s, 1000, 40, 2)
    expect(advice.needed).toBe(true)
    expect(advice.side).toBe('credit')
    expect(advice.additionalAmountNeeded).toBe(300) // 40%*1000 - 100
    expect(advice.suggestedExtraSamples).toBe(6)
    expect(advice.noteTemplate).toContain('贷方检查比例偏低')
    expect(isCoverageNoteSatisfied('', undefined, advice)).toBe(false)
    expect(isCoverageNoteSatisfied(advice.noteTemplate, undefined, advice)).toBe(true)
    // 借+贷同时偏低：须两边都回应（借方模板 alone 不能过贷方闸门）
    const debit = buildI4CoverageExpansionAdvice(
      summarizeI4Targeted([emptyI4TargetedRow({ debitAmount: 100 })], 1000),
      40,
    )
    expect(isCoverageNoteSatisfied(debit.noteTemplate, debit, advice)).toBe(false)
    expect(isCoverageNoteSatisfied(
      `${debit.noteTemplate}\n${advice.noteTemplate}`,
      debit,
      advice,
    )).toBe(true)
  })

  it('特定样本金额与表内特定借方容差校验', () => {
    expect(checkI4SpecificAmountConsistency(0, 0).ok).toBe(true)
    const syncHint = checkI4SpecificAmountConsistency(0, 100)
    expect(syncHint.ok).toBe(false)
    expect(syncHint.severity).toBe('info')
    const orphan = checkI4SpecificAmountConsistency(100, 0)
    expect(orphan.severity).toBe('warning')
    expect(checkI4SpecificAmountConsistency(100, 100).ok).toBe(true)
    expect(checkI4SpecificAmountConsistency(100, 100.02).ok).toBe(true) // 绝对容差内
    const mismatch = checkI4SpecificAmountConsistency(1000, 900)
    expect(mismatch.ok).toBe(false)
    expect(mismatch.severity).toBe('warning')
    expect(mismatch.diff).toBe(100)
  })

  it('测试原因预填抽凭引擎高值规则，并回填选取原因', () => {
    const mus = buildI4SamplingPresetFromTestReasons(['大额'])
    expect(mus.defaultMethod).toBe('mus')
    expect(mus.hintText).toContain('大额')

    const term = buildI4SamplingPresetFromTestReasons(['提前终止'])
    expect(term.directionFilter).toBe('credit')
    expect(term.summaryKeyword).toContain('终止')

    const related = buildI4SamplingPresetFromTestReasons(['关联方', '受益期变更'])
    expect(related.summaryKeyword).toMatch(/关联/)
    expect(related.summaryKeyword).toMatch(/受益期/)

    const samples = [
      { selectionReason: '', isHighValue: true, summary: '大额装修' },
      { selectionReason: '', summary: '关联方往来终止转出' },
      { selectionReason: '已有原因', summary: '其他' },
    ]
    const n = applyI4SelectionReasonsToSamples(samples, ['大额', '关联方', '提前终止'])
    expect(n).toBe(2)
    expect(samples[0].selectionReason).toBe('大额')
    expect(samples[1].selectionReason).toBe('关联方')
    expect(samples[2].selectionReason).toBe('已有原因')
  })

  it('与 I4-4 资本化/受益期变更结论交叉印证', () => {
    const gap = crossCheckI45WithI44({
      rows: [emptyI4TargetedRow({ debitAmount: 50, check3: '√', check5: '√' })],
      testReasons: ['大额'],
      riskFocus: emptyI4TargetedRiskFocus(),
      i44: {
        casItems: [
          { key: 'capitalize-boundary', label: '资本化与费用化边界', conclusion: '否', explanationIfNo: '存在不当资本化' },
          { key: 'benefit-period', label: '受益期限确定', conclusion: '是' },
          { key: 'estimate-change', label: '会计估计变更', conclusion: '是' },
          { key: 'amort-method', label: '摊销方法', conclusion: '是' },
          { key: 'amort-start', label: '摊销起始时点', conclusion: '是' },
        ],
        policyParams: [{ category: '装修费', hasChange: 'Y', changeReasonable: 'Y', meetsStandards: 'Y' }],
        overallConclusion: '政策基本恰当但资本化边界存疑',
      },
    })
    expect(gap.findings.some((f) => f.id === 'cap-gap')).toBe(true)
    expect(gap.findings.some((f) => f.id === 'change-gap')).toBe(true)
    expect(gap.hasWarning).toBe(true)

    const aligned = crossCheckI45WithI44({
      rows: [emptyI4TargetedRow({ check3: '×', isAbnormal: '资本化不当', selectionReason: '受益期变更' })],
      testReasons: ['受益期变更'],
      riskFocus: emptyI4TargetedRiskFocus({ benefitChangeConclusion: '已恰当处理' }),
      i44: {
        casItems: [
          { key: 'capitalize-boundary', label: '资本化与费用化边界', conclusion: '否' },
          { key: 'estimate-change', label: '会计估计变更', conclusion: '否' },
        ],
        policyParams: [{ category: '装修费', hasChange: 'Y', changeReasonable: 'N', meetsStandards: 'Y' }],
        overallConclusion: '需调整',
      },
    })
    expect(aligned.findings.some((f) => f.id === 'cap-aligned')).toBe(true)
    expect(aligned.findings.some((f) => f.id === 'change-aligned')).toBe(true)
    expect(aligned.summaryText).toContain('未见需跟进')

    const note = buildI44CrossNoteBlock(gap)
    expect(note).toContain('交叉印证')
    expect(parseI44PolicySnapshot(null)).toBeNull()
    const snap = parseI44PolicySnapshot(new Map([
      ['I4-4-cas-items', gap.findings],
      ['I4-4-overall-conclusion', '测试结论'],
    ]))
    expect(snap?.overallConclusion).toBe('测试结论')
  })
})
