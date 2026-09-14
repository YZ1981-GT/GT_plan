/**
 * K7 递延收益 — 集成联动验证测试
 *
 * Phase 7 Task 7.2:
 * - useK7AmortizationCalc 测算分摊→更新 allResponses K7-4-calc-amort-total
 * - useK7Detail 期末合计→更新 allResponses K7-2-detail-end-total / K7-2-amort-total
 * - useK7CrossSheet.adjudicationVsDetail 正确计算
 * - useK7CrossSheet.detailVsCalc 正确计算
 * - useK7Adjudication.reconciliation 检测不平
 * - K7 contract: 所有7个wp_code_overrides映射到'k7-deferred-income'
 *
 * Spec: .kiro/specs/k7-deferred-income/
 * Requirements: 2.5, 4.5, 6.3
 *
 * 科目：2401递延收益（**贷方/负债类**）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import * as fs from 'node:fs'
import * as path from 'node:path'

// ═══ 7.2-1: useK7AmortizationCalc → allResponses K7-4-calc-amort-total ═══

describe('K7 Integration — useK7AmortizationCalc 分摊测算→allResponses更新', () => {
  it('addRow后recalc → saveResponse写入K7-4-calc-amort-total', async () => {
    const { useK7AmortizationCalc } = await import('../composables/useK7AmortizationCalc')

    const saved = new Map<string, any>()
    const allResponses = ref(new Map<string, any>())
    const saveResponse = vi.fn((key: string, val: any) => {
      saved.set(key, val)
      allResponses.value.set(key, val)
    })

    const calc = useK7AmortizationCalc({
      allResponses,
      saveResponse,
    })

    // 添加行并设置数据
    calc.addRow('设备购置补助', '与资产相关')
    calc.updateCell(calc.calcRows.value[0].rowId, 'grantTotal', 1200000)
    calc.updateCell(calc.calcRows.value[0].rowId, 'totalPeriods', 120)
    calc.updateCell(calc.calcRows.value[0].rowId, 'currentPeriods', 12)
    calc.updateCell(calc.calcRows.value[0].rowId, 'enterpriseAmort', 100000)

    // 验证 saveResponse 被调用写入 K7-4-calc-amort-total
    expect(saveResponse).toHaveBeenCalledWith(
      'K7-4-calc-amort-total',
      expect.objectContaining({ remark: expect.any(String) }),
    )

    // 验证测算分摊 = 1200000 / 120 × 12 = 120000
    const totalVal = saved.get('K7-4-calc-amort-total')
    expect(Number(totalVal?.remark)).toBeCloseTo(120000, 0)
  })

  it('多行测算合计正确', async () => {
    const { useK7AmortizationCalc } = await import('../composables/useK7AmortizationCalc')

    const saved = new Map<string, any>()
    const rows = [
      { rowId: 'r1', project: '设备', grantTotal: 600000, relatedType: '与资产相关', amortMethod: '直线法', totalPeriods: 60, currentPeriods: 12, accumulatedAmort: 0, enterpriseAmort: 100000 },
      { rowId: 'r2', project: '研发', grantTotal: 300000, relatedType: '与收益相关', amortMethod: '直线法', totalPeriods: 36, currentPeriods: 12, accumulatedAmort: 0, enterpriseAmort: 100000 },
    ]
    const allResponses = ref(new Map<string, any>([
      ['K7-4-rows', { remark: JSON.stringify(rows) }],
    ]))
    const saveResponse = vi.fn((key: string, val: any) => {
      saved.set(key, val)
    })

    const calc = useK7AmortizationCalc({ allResponses, saveResponse })

    // 设备：600000/60×12=120000; 研发：300000/36×12=100000; 合计=220000
    expect(calc.subtotals.value.calculatedAmort).toBeCloseTo(220000, 0)
  })
})

// ═══ 7.2-2: useK7Detail → allResponses K7-2-detail-end-total / K7-2-amort-total ═══

describe('K7 Integration — useK7Detail 明细表→allResponses更新', () => {
  it('addRow后 → saveResponse写入K7-2-detail-end-total和K7-2-amort-total', async () => {
    const { useK7Detail } = await import('../composables/useK7Detail')

    const saved = new Map<string, any>()
    const allResponses = ref(new Map<string, any>())
    const saveResponse = vi.fn((key: string, val: any) => {
      saved.set(key, val)
      allResponses.value.set(key, val)
    })

    const detail = useK7Detail({ allResponses, saveResponse })

    // 直接添加行(跳过ElMessageBox prompt)
    await detail.addRow('设备购置补助')

    // 更新行数据
    const rowId = detail.detailRows.value[0].rowId
    detail.updateCell(rowId, 'beginBalance', 500000)
    detail.updateCell(rowId, 'receivedAmount', 200000)
    detail.updateCell(rowId, 'currentAmort', 100000)

    // 验证 期末=期初+收到-分摊 = 500000+200000-100000 = 600000
    expect(detail.detailRows.value[0].endBalance).toBe(600000)

    // 验证 saveResponse 写入汇总
    expect(saveResponse).toHaveBeenCalledWith(
      'K7-2-detail-end-total',
      expect.objectContaining({ remark: '600000' }),
    )
    expect(saveResponse).toHaveBeenCalledWith(
      'K7-2-amort-total',
      expect.objectContaining({ remark: '100000' }),
    )
  })

  it('多行期末合计正确写入', async () => {
    const { useK7Detail } = await import('../composables/useK7Detail')

    const saved = new Map<string, any>()
    const rows = [
      { rowId: 'r1', project: '设备', beginBalance: 500000, receivedAmount: 0, currentAmort: 50000 },
      { rowId: 'r2', project: '研发', beginBalance: 300000, receivedAmount: 100000, currentAmort: 80000 },
    ]
    const allResponses = ref(new Map<string, any>([
      ['K7-2-rows', { remark: JSON.stringify(rows) }],
    ]))
    const saveResponse = vi.fn((key: string, val: any) => {
      saved.set(key, val)
    })

    const detail = useK7Detail({ allResponses, saveResponse })

    // r1期末=500000+0-50000=450000; r2期末=300000+100000-80000=320000
    // 合计期末=770000; 合计分摊=130000
    expect(detail.subtotals.value.endBalance).toBe(770000)
    expect(detail.subtotals.value.currentAmort).toBe(130000)
  })
})

// ═══ 7.2-3: useK7CrossSheet.adjudicationVsDetail ═══

describe('K7 Integration — useK7CrossSheet.adjudicationVsDetail', () => {
  it('审定合计=明细期末合计 → isMatch=true, diff≈0', async () => {
    const { useK7CrossSheet } = await import('../composables/useK7CrossSheet')

    const allResponses = ref(new Map<string, any>([
      ['K7-1-audited-total', { remark: '800000' }],
      ['K7-2-detail-end-total', { remark: '800000' }],
    ]))

    const cross = useK7CrossSheet(allResponses)
    expect(cross.adjudicationVsDetail.value.isMatch).toBe(true)
    expect(cross.adjudicationVsDetail.value.diff).toBeCloseTo(0, 2)
  })

  it('审定合计>明细合计 → diff>0(明细少计负债)', async () => {
    const { useK7CrossSheet } = await import('../composables/useK7CrossSheet')

    const allResponses = ref(new Map<string, any>([
      ['K7-1-audited-total', { remark: '1000000' }],
      ['K7-2-detail-end-total', { remark: '950000' }],
    ]))

    const cross = useK7CrossSheet(allResponses)
    expect(cross.adjudicationVsDetail.value.isMatch).toBe(false)
    expect(cross.adjudicationVsDetail.value.diff).toBe(50000)
  })

  it('all missing → diff=0, isMatch=true', async () => {
    const { useK7CrossSheet } = await import('../composables/useK7CrossSheet')

    const allResponses = ref(new Map<string, any>())
    const cross = useK7CrossSheet(allResponses)
    expect(cross.adjudicationVsDetail.value.diff).toBe(0)
    expect(cross.adjudicationVsDetail.value.isMatch).toBe(true)
  })
})

// ═══ 7.2-4: useK7CrossSheet.detailVsCalc ═══

describe('K7 Integration — useK7CrossSheet.detailVsCalc', () => {
  it('企业分摊=测算分摊 → isMatch=true', async () => {
    const { useK7CrossSheet } = await import('../composables/useK7CrossSheet')

    const allResponses = ref(new Map<string, any>([
      ['K7-2-amort-total', { remark: '120000' }],
      ['K7-4-calc-amort-total', { remark: '120000' }],
    ]))

    const cross = useK7CrossSheet(allResponses)
    expect(cross.detailVsCalc.value.isMatch).toBe(true)
    expect(cross.detailVsCalc.value.diff).toBeCloseTo(0, 2)
  })

  it('企业多摊 → diff>0', async () => {
    const { useK7CrossSheet } = await import('../composables/useK7CrossSheet')

    const allResponses = ref(new Map<string, any>([
      ['K7-2-amort-total', { remark: '150000' }],
      ['K7-4-calc-amort-total', { remark: '120000' }],
    ]))

    const cross = useK7CrossSheet(allResponses)
    expect(cross.detailVsCalc.value.isMatch).toBe(false)
    expect(cross.detailVsCalc.value.diff).toBe(30000) // 企业多摊3万
  })

  it('企业少摊 → diff<0', async () => {
    const { useK7CrossSheet } = await import('../composables/useK7CrossSheet')

    const allResponses = ref(new Map<string, any>([
      ['K7-2-amort-total', { remark: '100000' }],
      ['K7-4-calc-amort-total', { remark: '130000' }],
    ]))

    const cross = useK7CrossSheet(allResponses)
    expect(cross.detailVsCalc.value.diff).toBe(-30000) // 企业少摊3万，需补摊
  })
})

// ═══ 7.2-5: useK7Adjudication.reconciliation 三角勾稽 ═══

describe('K7 Integration — useK7Adjudication.reconciliation 三角勾稽', () => {
  it('审定合计与明细期末一致 → isBalanced=true', async () => {
    const { useK7Adjudication } = await import('../composables/useK7Adjudication')

    const rows = [
      { rowKey: 'r1', project: '设备补助', group: '与资产相关', beginBalance: 500000, received: 200000, amortized: 100000, unadj: 600000, aje: 0, rje: 0, priorAudited: 550000, changeReason: '' },
    ]
    const allResponses = ref(new Map<string, any>([
      ['K7-1-rows', { remark: JSON.stringify(rows) }],
      ['K7-2-detail-end-total', { remark: '600000' }], // matches audited=600000
    ]))
    const saveResponse = vi.fn()

    const adj = useK7Adjudication({ allResponses, saveResponse })

    // 审定数=未审+AJE+RJE=600000+0+0=600000; 明细期末=600000
    expect(adj.reconciliation.value.isBalanced).toBe(true)
    expect(adj.reconciliation.value.diff).toBeCloseTo(0, 2)
  })

  it('审定合计>明细期末 → isBalanced=false, diff>0', async () => {
    const { useK7Adjudication } = await import('../composables/useK7Adjudication')

    const rows = [
      { rowKey: 'r1', project: '设备补助', group: '与资产相关', beginBalance: 500000, received: 200000, amortized: 100000, unadj: 700000, aje: 0, rje: 0, priorAudited: 0, changeReason: '' },
    ]
    const allResponses = ref(new Map<string, any>([
      ['K7-1-rows', { remark: JSON.stringify(rows) }],
      ['K7-2-detail-end-total', { remark: '600000' }],
    ]))
    const saveResponse = vi.fn()

    const adj = useK7Adjudication({ allResponses, saveResponse })

    // 审定数=700000; 明细期末=600000; diff=100000
    expect(adj.reconciliation.value.isBalanced).toBe(false)
    expect(adj.reconciliation.value.diff).toBe(100000)
  })

  it('无明细数据 → 审定数-0=审定数', async () => {
    const { useK7Adjudication } = await import('../composables/useK7Adjudication')

    const rows = [
      { rowKey: 'r1', project: '补助', group: '与收益相关', beginBalance: 0, received: 0, amortized: 0, unadj: 300000, aje: 0, rje: 0, priorAudited: 0, changeReason: '' },
    ]
    const allResponses = ref(new Map<string, any>([
      ['K7-1-rows', { remark: JSON.stringify(rows) }],
      // 无 K7-2-detail-end-total
    ]))
    const saveResponse = vi.fn()

    const adj = useK7Adjudication({ allResponses, saveResponse })

    expect(adj.reconciliation.value.diff).toBe(300000) // 审定-0=300000
    expect(adj.reconciliation.value.isBalanced).toBe(false)
  })
})

// ═══ 7.2-6: K7 contract — wp_code_overrides映射验证 ═══

describe('K7 Integration — wp_code_overrides contract', () => {
  it('K7全部7个wp_code映射到k7-deferred-income', () => {
    const overridesPath = path.resolve(
      __dirname, '../../../../../../backend/app/data/wp_code_overrides.json',
    )
    const overrides = JSON.parse(fs.readFileSync(overridesPath, 'utf-8'))

    const expectedCodes = ['K7', 'K7-1', 'K7-2', 'K7-3', 'K7-4', 'K7-5', 'K7A']
    for (const code of expectedCodes) {
      expect(overrides[code], `wp_code '${code}' should map to 'k7-deferred-income'`)
        .toBe('k7-deferred-income')
    }
  })

  it('wp_code_overrides中K7映射数量恰好为7个', () => {
    const overridesPath = path.resolve(
      __dirname, '../../../../../../backend/app/data/wp_code_overrides.json',
    )
    const overrides = JSON.parse(fs.readFileSync(overridesPath, 'utf-8'))

    const k7Entries = Object.entries(overrides).filter(
      ([_, v]) => v === 'k7-deferred-income',
    )
    expect(k7Entries.length).toBe(7)
  })
})
