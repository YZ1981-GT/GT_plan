/**
 * i5AdjudicationModel 单元测试 — 对齐 I4-1 同构骨架 + Excel I5-1
 */
import { describe, it, expect } from 'vitest'
import {
  emptyI5AdjudicationRow,
  normalizeI5AdjudicationRow,
  summarizeI5Adjudication,
  seedI5AdjudicationFromDetail,
  applyAjeFromI53,
  buildI5AdjudicationCrossCheck,
  buildI5ExcelLeadSummary,
  buildI5LeadMatrixRows,
  buildI5ThreeLayerLeadFromDetail,
  extractI5LeadFromRoll,
  extractI5CurrentPortionCandidates,
  calcI5RemainingMonths,
  appendI5TbReconciliationToLead,
  buildI5VarianceNoteDraft,
  validateI5AdjudicationSave,
  recalcI5AdjudicationRow,
  formatI5VarianceRate,
  calcI5Variance,
  I5_DEFAULT_CATEGORIES,
} from '../i5AdjudicationModel'
import {
  buildI5CurrentPortionReclassDraft,
  buildI5ExpenseReclassDraft,
  entryTypeFromCategory,
  categoryFromLegacy,
} from '../useI5Adjustment'
import {
  buildI4CategorySummary,
  extractI4CurrentPortionCandidates,
  emptyI4AdjudicationRow,
} from '../i4AdjudicationModel'
import { buildI4CurrentPortionReclassDraft } from '../useI4Adjustment'

describe('i5AdjudicationModel', () => {
  it('期末 = 期初 + 增加 − 减少；审定 = 未审 + AJE + RJE', () => {
    const row = recalcI5AdjudicationRow(emptyI5AdjudicationRow({
      beginBalance: 1000,
      increase: 200,
      decrease: 50,
      unadjusted: 1150,
      aje: 10,
      rje: -5,
    }))
    expect(row.endBalance).toBe(1150)
    expect(row.audited).toBe(1155)
    expect(row.hasError).toBe(false)
  })

  it('变动率上期为 0 时 N/A（避免 #DIV/0!）', () => {
    expect(calcI5Variance(100, 0).varianceRate).toBeNull()
    expect(formatI5VarianceRate(null)).toBe('N/A')
  })

  it('默认分类对齐 Excel I5-1', () => {
    expect(I5_DEFAULT_CATEGORIES).toContain('预付土地出让金')
    expect(I5_DEFAULT_CATEGORIES).toContain('合同履约成本')
  })

  it('兼容旧中文键', () => {
    const row = normalizeI5AdjudicationRow({
      项目: '预付设备款',
      期初: 100,
      增加: 20,
      减少: 10,
      未审: 110,
    })
    expect(row.projectName).toBe('预付设备款')
    expect(row.endBalance).toBe(110)
  })

  it('从 I5-2 带入（name 字段）', () => {
    const rows = seedI5AdjudicationFromDetail([
      { name: 'A', beginBalance: 80, increase: 20, decrease: 0, endBalance: 100 },
      { name: '合计', beginBalance: 999 },
    ], [emptyI5AdjudicationRow({ projectName: 'A', aje: 5 })])
    expect(rows).toHaveLength(1)
    expect(rows[0].unadjusted).toBe(100)
    expect(rows[0].aje).toBe(5)
    expect(rows[0].fromDetail).toBe(true)
  })

  it('从 I5-2 嵌套原值/减值带入净值 + 期初/期末调整列', () => {
    const rows = seedI5AdjudicationFromDetail([{
      projectName: '合同资产',
      gross: {
        unadjOpening: 200, unadjIncrease: 50, unadjDecrease: 10,
        openingAje: 5, openingRje: 0,
        ajeIncrease: 0, ajeDecrease: 0, rjeIncrease: 0, rjeDecrease: 0,
        auditedOpening: 205, auditedIncrease: 50, auditedDecrease: 10, auditedEnding: 245,
      },
      impairment: {
        unadjOpening: 20, unadjIncrease: 5, unadjDecrease: 0,
        openingAje: 0, openingRje: 0,
        ajeIncrease: 0, ajeDecrease: 0, rjeIncrease: 0, rjeDecrease: 0,
        auditedOpening: 20, auditedIncrease: 5, auditedDecrease: 0, auditedEnding: 25,
      },
      endBalance: 220,
    }])
    expect(rows).toHaveLength(1)
    expect(rows[0].beginBalance).toBe(185)
    expect(rows[0].endBalance).toBe(220)
    expect(rows[0].openingAje).toBe(5)
    expect(rows[0].endAje).toBe(5)
  })

  it('Excel 期末账项=F+H−I；三层矩阵含原值/减值/净值', () => {
    const lead = extractI5LeadFromRoll({
      unadjOpening: 100, unadjIncrease: 40, unadjDecrease: 10,
      openingAje: 2, openingRje: 1,
      ajeIncrease: 5, ajeDecrease: 1, rjeIncrease: 3, rjeDecrease: 0,
    })
    expect(lead.endAje).toBe(6)
    expect(lead.endRje).toBe(4)
    expect(lead.endUnadj + lead.endAje + lead.endRje).toBe(lead.endAudited)

    const matrix = buildI5ThreeLayerLeadFromDetail([{
      projectName: '预付工程款',
      gross: {
        unadjOpening: 100, unadjIncrease: 40, unadjDecrease: 10,
        openingAje: 2, openingRje: 1,
        ajeIncrease: 5, ajeDecrease: 1, rjeIncrease: 3, rjeDecrease: 0,
        unadjEnding: 130, auditedOpening: 103, auditedIncrease: 48, auditedDecrease: 11, auditedEnding: 140,
      },
      impairment: {
        unadjOpening: 10, unadjIncrease: 0, unadjDecrease: 0,
        openingAje: 0, openingRje: 0, ajeIncrease: 0, ajeDecrease: 0, rjeIncrease: 0, rjeDecrease: 0,
        unadjEnding: 10, auditedOpening: 10, auditedIncrease: 0, auditedDecrease: 0, auditedEnding: 10,
      },
    }])
    expect(matrix.some((r) => r.isSection && String(r.label).includes('原值'))).toBe(true)
    expect(matrix.some((r) => r.isSection && String(r.label).includes('减值'))).toBe(true)
    expect(matrix.some((r) => r.isSection && String(r.label).includes('净值'))).toBe(true)
    const netRow = matrix.find((r) => r.layer === 'net' && r.label === '预付工程款')
    expect(netRow?.endAudited).toBe(130)
  })

  it('三层矩阵末追加 TB 勾稽行', () => {
    const base = buildI5ThreeLayerLeadFromDetail([{
      projectName: '预付工程款',
      gross: { unadjOpening: 100, unadjIncrease: 0, unadjDecrease: 0, unadjEnding: 100, auditedOpening: 100, auditedIncrease: 0, auditedDecrease: 0, auditedEnding: 100 },
      impairment: { unadjOpening: 0, unadjIncrease: 0, unadjDecrease: 0, unadjEnding: 0, auditedOpening: 0, auditedIncrease: 0, auditedDecrease: 0, auditedEnding: 0 },
    }])
    const withTb = appendI5TbReconciliationToLead(base, 100)
    expect(withTb.some((r) => r.label === 'TB数据(1911)')).toBe(true)
    const diffRow = withTb.find((r) => r.label === '差异')
    expect(diffRow?.endAudited).toBe(0)
    expect(diffRow?.tbMismatch).toBe(false)
    const mismatch = appendI5TbReconciliationToLead(base, 90)
    expect(mismatch.find((r) => r.label === '差异')?.tbMismatch).toBe(true)
  })

  it('到期日/剩余月数筛选一年内到期候选', () => {
    expect(calcI5RemainingMonths('2026-06-30', 2025)).toBe(6)
    expect(calcI5RemainingMonths('2025-08-01', 2025)).toBeNull()
    const cands = extractI5CurrentPortionCandidates([
      {
        projectName: '预付工程款',
        maturityDate: '2026-03-15',
        gross: { auditedEnding: 500 },
        impairment: { auditedEnding: 0 },
      },
      {
        projectName: '委托贷款',
        remainingMonths: 18,
        endBalance: 200,
      },
      { projectName: '合计', endBalance: 999 },
    ], 2025)
    expect(cands).toHaveLength(1)
    expect(cands[0].projectName).toBe('预付工程款')
    expect(cands[0].remainingMonths).toBe(3)
    expect(cands[0].amount).toBe(500)
  })

  it('I5-3 AJE 精确匹配 projectName + 未指名走近似', () => {
    const result = applyAjeFromI53(
      [
        emptyI5AdjudicationRow({ projectName: 'A', unadjusted: 100 }),
        emptyI5AdjudicationRow({ projectName: 'B', unadjusted: 100 }),
      ],
      [
        { accountCode: '1911', entryType: 'AJE', projectName: 'A', debit: 20, credit: 0 },
        { accountCode: '1911', category: '账项调整', description: '未指名', debit: 10, credit: 0 },
      ],
    )
    expect(result.matchedByName).toBe(1)
    expect(result.approx).toBe(true)
    // 20 精确到 A + 10 按未审各半分摊 → A=25
    expect(result.rows.find((r) => r.projectName === 'A')?.aje).toBe(25)
  })

  it('类别「报表调整」映射为 RJE', () => {
    const result = applyAjeFromI53(
      [emptyI5AdjudicationRow({ projectName: '预付工程款', unadjusted: 100 })],
      [{ accountCode: '1911', category: '报表调整', projectName: '预付工程款', debit: 0, credit: 30 }],
    )
    expect(result.totalRje).toBe(-30)
    expect(result.rows[0].rje).toBe(-30)
  })

  it('Excel 审定矩阵分列账项/重分类', () => {
    const L = buildI5ExcelLeadSummary([
      emptyI5AdjudicationRow({
        projectName: 'A', beginBalance: 100, unadjusted: 120, aje: 10, rje: -5, priorAudited: 100,
      }),
    ])
    expect(L.endAje).toBe(10)
    expect(L.endRje).toBe(-5)
    expect(L.endAdj).toBe(5)
    expect(L.endAudited).toBe(125)
  })

  it('按项目展开矩阵末行合计', () => {
    const matrix = buildI5LeadMatrixRows([
      emptyI5AdjudicationRow({ projectName: 'A', beginBalance: 10, unadjusted: 10, aje: 1 }),
      emptyI5AdjudicationRow({ projectName: 'B', beginBalance: 20, unadjusted: 20, rje: 2 }),
    ])
    expect(matrix).toHaveLength(3)
    expect(matrix[2].label).toBe('合计')
    expect(matrix[2].isTotal).toBe(true)
    expect(matrix[2].endAje).toBe(1)
    expect(matrix[2].endRje).toBe(2)
  })

  it('变动说明草稿：上期为 0 写 N/A，超阈值列项目', () => {
    const note = buildI5VarianceNoteDraft([
      emptyI5AdjudicationRow({
        projectName: '预付工程款', unadjusted: 200, priorAudited: 100,
      }),
      emptyI5AdjudicationRow({
        projectName: '委托贷款', unadjusted: 50, priorAudited: 0,
      }),
    ])
    expect(note).toContain('主要原因（比例超过30%的）')
    expect(note).toContain('预付工程款')
    expect(note).not.toContain('#DIV/0!')
  })

  it('保存闸门：TB 差异阻断', () => {
    const ok = recalcI5AdjudicationRow(emptyI5AdjudicationRow({
      projectName: '好',
      beginBalance: 100,
      unadjusted: 100,
    }))
    expect(validateI5AdjudicationSave({ rows: [ok], tbDiff: 0 }).ok).toBe(true)
    expect(validateI5AdjudicationSave({ rows: [ok], tbDiff: 2 }).ok).toBe(false)
  })

  it('与明细交叉检查', () => {
    const cc = buildI5AdjudicationCrossCheck(
      [emptyI5AdjudicationRow({ projectName: 'A', beginBalance: 100, unadjusted: 100 })],
      { beginBalance: 90, endBalance: 80 },
    )
    expect(cc.hasWarning).toBe(true)
  })

  it('summarize 合计', () => {
    const sub = summarizeI5Adjudication([
      emptyI5AdjudicationRow({ projectName: 'A', beginBalance: 10, increase: 5, decrease: 1, unadjusted: 14 }),
      emptyI5AdjudicationRow({ projectName: 'B', beginBalance: 20, increase: 0, decrease: 2, unadjusted: 18 }),
    ])
    expect(sub.beginBalance).toBe(30)
    expect(sub.decrease).toBe(3)
  })
})

describe('useI5Adjustment drafts', () => {
  it('类别映射', () => {
    expect(entryTypeFromCategory('报表调整')).toBe('RJE')
    expect(entryTypeFromCategory('账项调整')).toBe('AJE')
    expect(categoryFromLegacy({ entryType: 'RJE' })).toBe('报表调整')
  })

  it('一年内到期 RJE 草稿借贷平衡', () => {
    const lines = buildI5CurrentPortionReclassDraft({ projectName: '预付工程款', amount: 1000 })
    expect(lines).toHaveLength(2)
    expect(lines[0].accountCode).toBe('1461')
    expect(lines[1].accountCode).toBe('1911')
    expect(lines.reduce((s, r) => s + r.debitAmount, 0)).toBe(
      lines.reduce((s, r) => s + r.creditAmount, 0),
    )
  })

  it('费用化 AJE 草稿借贷平衡', () => {
    const lines = buildI5ExpenseReclassDraft({ projectName: '预付投资款', amount: 500 })
    expect(lines[0].category).toBe('账项调整')
    expect(lines.reduce((s, r) => s + r.debitAmount, 0)).toBe(500)
    expect(lines.reduce((s, r) => s + r.creditAmount, 0)).toBe(500)
  })
})

describe('i4 category + current-portion helpers', () => {
  it('按 expenseType 聚合类别汇总', () => {
    const rows = [
      emptyI4AdjudicationRow({ projectName: '装修A', beginBalance: 100, increase: 0, amortization: 10, audited: 90 }),
      emptyI4AdjudicationRow({ projectName: '开办B', beginBalance: 50, increase: 0, amortization: 5, audited: 45 }),
    ]
    const cats = buildI4CategorySummary(rows, [
      { projectName: '装修A', expenseType: '装修费' },
      { projectName: '开办B', expenseType: '开办费' },
    ])
    expect(cats.find((c) => c.category === '装修费')?.begin).toBe(100)
  })

  it('一年内到期候选抽取', () => {
    const cands = extractI4CurrentPortionCandidates([
      { projectName: 'A', endBalance: 100, remainingMonths: 6 },
      { projectName: 'B', endBalance: 50, remainingMonths: 18 },
    ])
    expect(cands).toHaveLength(1)
    expect(cands[0].projectName).toBe('A')
  })

  it('I4 一年内到期草稿', () => {
    const lines = buildI4CurrentPortionReclassDraft({ projectName: 'X', amount: 80, remainingMonths: 3 })
    expect(lines[0].category).toBe('报表调整')
  })
})
