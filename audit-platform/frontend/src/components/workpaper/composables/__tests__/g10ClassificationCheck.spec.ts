import { describe, it, expect } from 'vitest'
import {
  emptyClassificationRow,
  hasClassificationBasis,
  classifyBasisLabel,
  G10_YN_OPTIONS,
} from '../g10ClassificationModel'
import {
  prefillBasisFromDetail,
  getCategoryMismatchReason,
  buildReclassificationDraftPair,
  mergeReclassificationDraftsIntoAdj,
  collectClassificationIssues,
  isG10ClassificationAdjDraft,
  isPendingG10ClassificationAdjDraft,
  countG10ClassificationDraftProjects,
  countPendingG10ClassificationDraftProjects,
  markClassificationDraftsConfirmed,
  resolveReclassStatusForClassificationRow,
} from '../g10ClassificationCross'

describe('G10-4 分类适当性检查', () => {
  it('是/否/不适用选项', () => {
    expect(G10_YN_OPTIONS.map((o) => o.value)).toEqual(['yes', 'no', 'na'])
  })

  it('交易性任一勾选即具备分类依据', () => {
    const row = emptyClassificationRow('1', 1)
    expect(hasClassificationBasis(row)).toBe(false)
    row.tradingNearTermSale = 'yes'
    expect(hasClassificationBasis(row)).toBe(true)
    expect(classifyBasisLabel(row)).toContain('交易性')
  })

  it('初始指定勾选具备分类依据', () => {
    const row = emptyClassificationRow('1', 1)
    row.designatedMismatch = 'yes'
    expect(hasClassificationBasis(row)).toBe(true)
    expect(classifyBasisLabel(row)).toContain('消除会计错配')
  })

  it('按 G10-2 负债类型与类别预填', () => {
    expect(prefillBasisFromDetail('衍生金融负债', true).tradingDerivative).toBe('yes')
    expect(prefillBasisFromDetail('卖出回购', false).tradingNearTermSale).toBe('yes')
    expect(prefillBasisFromDetail('交易性债券', false).tradingPortfolioShortTerm).toBe('yes')
    expect(prefillBasisFromDetail('其他', false, '指定类').designatedMismatch).toBe('yes')
  })

  it('G10-2 指定类与勾选不一致', () => {
    const row = emptyClassificationRow('1', 1)
    row.liabilityName = '测试债'
    row.tradingNearTermSale = 'yes'
    expect(getCategoryMismatchReason(row, '指定类')).toContain('指定类')
  })

  it('生成重分类 RJE 草稿并去重合并', () => {
    const issue = {
      rowId: '1',
      liabilityName: '短期融资券',
      closingBookValue: 100,
      reason: '未勾选任一 FVTPL 分类依据',
      liabilityType: '交易性债券',
      liabilityCategory: '交易类',
    }
    const pair = buildReclassificationDraftPair(issue, 1)
    expect(pair).toHaveLength(2)
    expect(pair[0].debitAmount).toBe(100)
    expect(pair[1].creditAmount).toBe(100)
    expect(pair[0].entryType).toBe('RJE')
    expect(pair[0].classificationSourceId).toBe('1')
    expect(pair[0].draftReviewStatus).toBe('pending')

    const { merged, added } = mergeReclassificationDraftsIntoAdj('[]', pair)
    expect(added).toBe(2)
    const again = mergeReclassificationDraftsIntoAdj(merged, pair)
    expect(again.added).toBe(0)
  })

  it('收集缺依据项目', () => {
    const row = emptyClassificationRow('1', 1)
    row.liabilityName = '融券'
    row.closingBookValue = 50
    row.liabilityCategory = '交易类'
    const issues = collectClassificationIssues([row], new Map())
    expect(issues).toHaveLength(1)
    expect(issues[0].reason).toContain('未勾选')
  })

  it('识别 G10-4 推送的调整分录草稿', () => {
    const row = {
      summary: 'G10-4 重分类—短期融资券：未勾选任一 FVTPL 分类依据',
      remark: '由 G10-4 分类检查生成',
      indexRef: 'G10-4',
      classificationSourceId: 'cl-1',
      draftReviewStatus: 'pending' as const,
    }
    expect(isG10ClassificationAdjDraft(row)).toBe(true)
    expect(isPendingG10ClassificationAdjDraft(row)).toBe(true)
    expect(countG10ClassificationDraftProjects([row, { ...row }])).toBe(1)
    expect(countPendingG10ClassificationDraftProjects([row, { ...row }])).toBe(1)
  })

  it('标记已复核后不再计入待复核', () => {
    const rows = [
      {
        summary: 'G10-4 重分类—A：缺依据',
        indexRef: 'G10-4',
        classificationSourceId: 'a1',
        draftReviewStatus: 'pending',
      },
      {
        summary: 'G10-4 重分类—A：缺依据',
        indexRef: 'G10-4',
        classificationSourceId: 'a1',
        draftReviewStatus: 'pending',
      },
    ]
    const next = markClassificationDraftsConfirmed(rows, { allPending: true })
    expect(next.every((r: { draftReviewStatus?: string }) => r.draftReviewStatus === 'confirmed')).toBe(true)
    expect(countPendingG10ClassificationDraftProjects(next)).toBe(0)
  })

  it('G10-4 行重分类状态映射', () => {
    const row = emptyClassificationRow('cl-1', 1)
    row.liabilityName = '短期融资券'
    const adj = [
      {
        summary: 'G10-4 重分类—短期融资券：缺依据',
        indexRef: 'G10-4',
        classificationSourceId: 'cl-1',
        draftReviewStatus: 'pending',
      },
    ]
    expect(resolveReclassStatusForClassificationRow(row, adj)).toBe('pending')
  })
})
