/**
 * i4AdjudicationModel 单元测试 — 对齐 Excel I4-1
 */
import { describe, it, expect } from 'vitest'
import {
  emptyI4AdjudicationRow,
  normalizeI4AdjudicationRow,
  summarizeI4Adjudication,
  seedI4AdjudicationFromDetail,
  applyAjeFromI43,
  applyAmortFromI46,
  buildI4AdjudicationCrossCheck,
  buildI4ExcelLeadSummary,
  buildI4AdjudicationConclusionDraft,
  validateI4AdjudicationSave,
  recalcI4AdjudicationRow,
  formatI4VarianceRate,
  calcI4Variance,
} from '../i4AdjudicationModel'

describe('i4AdjudicationModel', () => {
  it('期末 = 期初 + 增加 − 摊销 − 减少；审定 = 未审 + AJE + RJE', () => {
    const row = recalcI4AdjudicationRow(emptyI4AdjudicationRow({
      beginBalance: 1000,
      increase: 200,
      amortization: 150,
      decrease: 50,
      unadjusted: 1000,
      aje: 10,
      rje: -5,
    }))
    expect(row.endBalance).toBe(1000)
    expect(row.audited).toBe(1005)
    expect(row.hasError).toBe(false)
  })

  it('摊销负数被钳制为 0', () => {
    const row = recalcI4AdjudicationRow(emptyI4AdjudicationRow({
      beginBalance: 100,
      amortization: -20,
    }))
    expect(row.amortization).toBe(0)
    expect(row.endBalance).toBe(100)
  })

  it('变动率：上期为 0 时 N/A（避免 #DIV/0!）', () => {
    expect(calcI4Variance(100, 0).varianceRate).toBeNull()
    expect(formatI4VarianceRate(null)).toBe('N/A')
    const v = calcI4Variance(120, 100)
    expect(v.varianceAmount).toBe(20)
    expect(v.varianceRate).toBe(20)
    expect(formatI4VarianceRate(20)).toBe('20.00%')
  })

  it('兼容旧中文键规范化', () => {
    const row = normalizeI4AdjudicationRow({
      项目: '装修费',
      期初: 500,
      增加: 100,
      摊销: 50,
      减少: 0,
      未审: 550,
      AJE: 0,
      RJE: 0,
      上期审定: 500,
    })
    expect(row.projectName).toBe('装修费')
    expect(row.endBalance).toBe(550)
    expect(row.varianceAmount).toBe(50)
  })

  it('从 I4-2 带入并保留已有 AJE', () => {
    const prev = [emptyI4AdjudicationRow({ projectName: '装修A', aje: 30, rje: -10 })]
    const rows = seedI4AdjudicationFromDetail([
      {
        projectName: '装修A',
        beginBalance: 800,
        currentIncrease: 200,
        currentAmortization: 100,
        currentDecrease: 0,
        endBalance: 900,
      },
      { projectName: '合计', beginBalance: 9999 },
    ], prev)
    expect(rows).toHaveLength(1)
    expect(rows[0].increase).toBe(200)
    expect(rows[0].amortization).toBe(100)
    expect(rows[0].unadjusted).toBe(900)
    expect(rows[0].aje).toBe(30)
    expect(rows[0].rje).toBe(-10)
    expect(rows[0].fromDetail).toBe(true)
  })

  it('I4-3 AJE 按项目名精确匹配；剩余分摊标近似', () => {
    const base = [
      emptyI4AdjudicationRow({ projectName: 'A', unadjusted: 100 }),
      emptyI4AdjudicationRow({ projectName: 'B', unadjusted: 100 }),
    ]
    const result = applyAjeFromI43(base, [
      { accountCode: '1801', entryType: 'AJE', projectName: 'A', debit: 20, credit: 0 },
      { accountCode: '1801', entryType: 'AJE', description: '未指名', debit: 10, credit: 0 },
    ])
    expect(result.matchedByName).toBe(1)
    expect(result.rows.find((r) => r.projectName === 'A')!.aje).toBeGreaterThanOrEqual(20)
    expect(result.approx).toBe(true)
    expect(result.rows.some((r) => r.ajeApprox)).toBe(true)
  })

  it('从 I4-6 按名称同步摊销', () => {
    const rows = applyAmortFromI46(
      [emptyI4AdjudicationRow({ projectName: '装修A', beginBalance: 1000 })],
      [{ name: '装修A', yearTotal: 240 }],
    )
    expect(rows[0].amortization).toBe(240)
  })

  it('Excel 只读汇总含期末未审/调整/审定与变动', () => {
    const L = buildI4ExcelLeadSummary([
      emptyI4AdjudicationRow({
        projectName: 'A',
        beginBalance: 100,
        increase: 0,
        amortization: 0,
        decrease: 0,
        unadjusted: 100,
        aje: 5,
        priorAudited: 80,
      }),
    ])
    expect(L.beginAudited).toBe(100)
    expect(L.endUnadj).toBe(100)
    expect(L.endAdj).toBe(5)
    expect(L.endAudited).toBe(105)
    expect(L.varianceAmount).toBe(25)
  })

  it('保存闸门：三角不平或 TB 差异阻断', () => {
    const bad = emptyI4AdjudicationRow({ projectName: '坏行', beginBalance: 100 })
    // 人为制造不平：改 endBalance 后不走 recalc 的路径——用 hasError
    const forced = { ...bad, endBalance: 999, triangleDiff: 100, hasError: true }
    const gate = validateI4AdjudicationSave({ rows: [forced], tbDiff: 0 })
    expect(gate.ok).toBe(false)
    expect(gate.blockers.some((b) => b.includes('三角'))).toBe(true)

    const okRow = recalcI4AdjudicationRow(emptyI4AdjudicationRow({
      projectName: '好',
      beginBalance: 100,
      unadjusted: 100,
    }))
    expect(validateI4AdjudicationSave({ rows: [okRow], tbDiff: 1 }).ok).toBe(false)
    expect(validateI4AdjudicationSave({ rows: [okRow], tbDiff: 0 }).ok).toBe(true)
  })

  it('结论草稿包含样本量与 TB 勾稽语', () => {
    const text = buildI4AdjudicationConclusionDraft({
      sampleCount: 3,
      auditedTotal: 1000,
      tbDiff: 0,
      hasAje: false,
      crossWarning: false,
    })
    expect(text).toContain('3 个项目')
    expect(text).toContain('TB(1801)')
  })

  it('与明细交叉检查能标出差异', () => {
    const rows = [emptyI4AdjudicationRow({ projectName: 'A', beginBalance: 100, unadjusted: 100 })]
    const cc = buildI4AdjudicationCrossCheck(rows, { beginBalance: 90, endBalance: 80, amortization: 0 })
    expect(cc.hasWarning).toBe(true)
    expect(Math.abs(cc.beginDiff)).toBeGreaterThan(0.01)
  })

  it('summarize 合计行正确', () => {
    const sub = summarizeI4Adjudication([
      emptyI4AdjudicationRow({ projectName: 'A', beginBalance: 100, increase: 50, amortization: 20, unadjusted: 130 }),
      emptyI4AdjudicationRow({ projectName: 'B', beginBalance: 200, increase: 0, amortization: 40, unadjusted: 160 }),
    ])
    expect(sub.projectName).toBe('合计')
    expect(sub.beginBalance).toBe(300)
    expect(sub.amortization).toBe(60)
    expect(sub.unadjusted).toBe(290)
  })
})
