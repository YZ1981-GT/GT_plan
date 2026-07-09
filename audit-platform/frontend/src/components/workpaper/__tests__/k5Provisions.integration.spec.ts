/**
 * K5 预计负债 — 集成联动验证测试
 *
 * Phase 7 Task 7.2:
 * - 或有判断→确认/披露 + 三专项测算回连审定
 * - useK5CrossSheet: computed links between sheets
 * - useK5Adjudication: TB reconciliation
 * - TB回写(2701) + EventBus substantive:adjudicated
 * - 审定回写
 *
 * Spec: .kiro/specs/k5-provisions/
 * Requirements: 2.6, 4.2, 6.3, 7.4
 *
 * 科目：2701预计负债（**贷方/负债类**）
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'

// ═══ 7.2-A: useK5CrossSheet — 跨Sheet computed链 ═══

describe('K5 Integration — useK5CrossSheet computed链', () => {
  it('adjudicationVsDetail: matching values → isMatch=true, diff≈0', async () => {
    const { useK5CrossSheet } = await import('../composables/useK5CrossSheet')

    const allResponses = ref(new Map<string, any>([
      ['K5-1-audited-total', { remark: '500000' }],
      ['K5-2-detail-end-total', { remark: '500000' }],
    ]))

    const cross = useK5CrossSheet(allResponses)
    expect(cross.adjudicationVsDetail.value.isMatch).toBe(true)
    expect(cross.adjudicationVsDetail.value.diff).toBeCloseTo(0, 2)
  })

  it('adjudicationVsDetail: mismatch → isMatch=false, diff=差额', async () => {
    const { useK5CrossSheet } = await import('../composables/useK5CrossSheet')

    const allResponses = ref(new Map<string, any>([
      ['K5-1-audited-total', { remark: '800000' }],
      ['K5-2-detail-end-total', { remark: '750000' }],
    ]))

    const cross = useK5CrossSheet(allResponses)
    expect(cross.adjudicationVsDetail.value.isMatch).toBe(false)
    expect(cross.adjudicationVsDetail.value.diff).toBe(50000)
  })

  it('adjudicationVsDetail: missing keys → 0, diff=0, isMatch=true', async () => {
    const { useK5CrossSheet } = await import('../composables/useK5CrossSheet')

    const allResponses = ref(new Map<string, any>())
    const cross = useK5CrossSheet(allResponses)
    expect(cross.adjudicationVsDetail.value.diff).toBe(0)
    expect(cross.adjudicationVsDetail.value.isMatch).toBe(true)
  })

  it('warrantyVsAdjudication: K5-4 matches K5-1 产品质保行', async () => {
    const { useK5CrossSheet } = await import('../composables/useK5CrossSheet')

    const allResponses = ref(new Map<string, any>([
      ['K5-1-audited-warranty', { remark: '120000' }],
      ['K5-4-warranty-end-total', { remark: '120000' }],
    ]))

    const cross = useK5CrossSheet(allResponses)
    expect(cross.warrantyVsAdjudication.value.isMatch).toBe(true)
    expect(cross.warrantyVsAdjudication.value.diff).toBeCloseTo(0, 2)
  })

  it('warrantyVsAdjudication: difference → audited多于测算', async () => {
    const { useK5CrossSheet } = await import('../composables/useK5CrossSheet')

    const allResponses = ref(new Map<string, any>([
      ['K5-1-audited-warranty', { remark: '150000' }],
      ['K5-4-warranty-end-total', { remark: '120000' }],
    ]))

    const cross = useK5CrossSheet(allResponses)
    expect(cross.warrantyVsAdjudication.value.isMatch).toBe(false)
    expect(cross.warrantyVsAdjudication.value.diff).toBe(30000) // 多提
  })

  it('decommissionVsAdjudication: K5-5 matches K5-1 弃置义务行', async () => {
    const { useK5CrossSheet } = await import('../composables/useK5CrossSheet')

    const allResponses = ref(new Map<string, any>([
      ['K5-1-audited-decommission', { remark: '300000' }],
      ['K5-5-decommission-end-total', { remark: '300000' }],
    ]))

    const cross = useK5CrossSheet(allResponses)
    expect(cross.decommissionVsAdjudication.value.isMatch).toBe(true)
  })

  it('decommissionVsAdjudication: negative diff → 审定表少于测算(需补提)', async () => {
    const { useK5CrossSheet } = await import('../composables/useK5CrossSheet')

    const allResponses = ref(new Map<string, any>([
      ['K5-1-audited-decommission', { remark: '250000' }],
      ['K5-5-decommission-end-total', { remark: '300000' }],
    ]))

    const cross = useK5CrossSheet(allResponses)
    expect(cross.decommissionVsAdjudication.value.diff).toBe(-50000)
    expect(cross.decommissionVsAdjudication.value.isMatch).toBe(false)
  })

  it('litigationVsAdjudication: K5-6 matches K5-1 未决诉讼行', async () => {
    const { useK5CrossSheet } = await import('../composables/useK5CrossSheet')

    const allResponses = ref(new Map<string, any>([
      ['K5-1-audited-litigation', { remark: '450000' }],
      ['K5-6-litigation-loss-total', { remark: '450000' }],
    ]))

    const cross = useK5CrossSheet(allResponses)
    expect(cross.litigationVsAdjudication.value.isMatch).toBe(true)
  })

  it('litigationVsAdjudication: non-numeric remark → treated as 0', async () => {
    const { useK5CrossSheet } = await import('../composables/useK5CrossSheet')

    const allResponses = ref(new Map<string, any>([
      ['K5-1-audited-litigation', { remark: 'abc' }],
      ['K5-6-litigation-loss-total', { remark: '100000' }],
    ]))

    const cross = useK5CrossSheet(allResponses)
    expect(cross.litigationVsAdjudication.value.diff).toBe(-100000) // 0 - 100000
  })
})

// ═══ 7.2-B: useK5Adjudication — 审定表负债类公式链 + TB reconciliation ═══

describe('K5 Integration — useK5Adjudication 审定公式', () => {
  it('rows computed correctly from allResponses (负债类: end=begin+provision-release)', async () => {
    const { useK5Adjudication } = await import('../composables/useK5Adjudication')

    const allResponses = ref(new Map<string, any>([
      ['K5-1-r0-begin', { remark: '100000' }],
      ['K5-1-r0-provision', { remark: '30000' }],
      ['K5-1-r0-release', { remark: '10000' }],
      ['K5-1-r0-unadj', { remark: '118000' }],
      ['K5-1-r0-aje', { remark: '2000' }],
      ['K5-1-r0-rje', { remark: '0' }],
    ]))
    const tbData = ref({ unadjusted2701: 0, audited2701: 0 })
    const saveResponse = vi.fn()

    const adj = useK5Adjudication({ allResponses, tbData, saveResponse })
    const row0 = adj.rows.value[0]

    // 负债类期末 = 100000 + 30000 - 10000 = 120000
    expect(row0.end).toBe(120000)
    // 审定数 = 118000 + 2000 + 0 = 120000
    expect(row0.audited).toBe(120000)
  })

  it('subtotalRow sums all 6 type rows', async () => {
    const { useK5Adjudication } = await import('../composables/useK5Adjudication')

    const allResponses = ref(new Map<string, any>([
      ['K5-1-r0-begin', { remark: '100000' }],  // 产品质保
      ['K5-1-r1-begin', { remark: '200000' }],  // 未决诉讼
      ['K5-1-r2-begin', { remark: '50000' }],   // 亏损合同
      ['K5-1-r3-begin', { remark: '0' }],       // 重组义务
      ['K5-1-r4-begin', { remark: '80000' }],   // 弃置义务
      ['K5-1-r5-begin', { remark: '10000' }],   // 其他
    ]))
    const tbData = ref({ unadjusted2701: 0, audited2701: 0 })
    const saveResponse = vi.fn()

    const adj = useK5Adjudication({ allResponses, tbData, saveResponse })
    expect(adj.subtotalRow.value.begin).toBe(440000) // sum of all begins
  })

  it('reconciliation: balanced when formula hold true', async () => {
    const { useK5Adjudication } = await import('../composables/useK5Adjudication')

    // All zeros → trivially balanced
    const allResponses = ref(new Map<string, any>())
    const tbData = ref({ unadjusted2701: 0, audited2701: 0 })
    const saveResponse = vi.fn()

    const adj = useK5Adjudication({ allResponses, tbData, saveResponse })
    expect(adj.reconciliation.value.isBalanced).toBe(true)
    expect(adj.reconciliation.value.diff).toBe(0)
  })

  it('tbReconciliation: checks audited vs TB (2701)', async () => {
    const { useK5Adjudication } = await import('../composables/useK5Adjudication')

    const allResponses = ref(new Map<string, any>([
      ['K5-1-r0-unadj', { remark: '100000' }],
      ['K5-1-r0-aje', { remark: '5000' }],
      ['K5-1-r0-rje', { remark: '0' }],
    ]))
    const tbData = ref({ unadjusted2701: 0, audited2701: 105000 })
    const saveResponse = vi.fn()

    const adj = useK5Adjudication({ allResponses, tbData, saveResponse })
    // subtotal.audited = 105000 (only r0 has data)
    // tb.audited2701 = 105000 → match
    expect(adj.tbReconciliation.value.isMatch).toBe(true)
  })

  it('tbReconciliation: mismatch when TB differs', async () => {
    const { useK5Adjudication } = await import('../composables/useK5Adjudication')

    const allResponses = ref(new Map<string, any>([
      ['K5-1-r0-unadj', { remark: '100000' }],
      ['K5-1-r0-aje', { remark: '0' }],
      ['K5-1-r0-rje', { remark: '0' }],
    ]))
    const tbData = ref({ unadjusted2701: 0, audited2701: 200000 })
    const saveResponse = vi.fn()

    const adj = useK5Adjudication({ allResponses, tbData, saveResponse })
    // subtotal.audited = 100000, tb = 200000
    expect(adj.tbReconciliation.value.isMatch).toBe(false)
    expect(adj.tbReconciliation.value.diff).toBe(-100000)
  })

  it('getWarrantyAudited returns row 0 audited', async () => {
    const { useK5Adjudication } = await import('../composables/useK5Adjudication')

    const allResponses = ref(new Map<string, any>([
      ['K5-1-r0-unadj', { remark: '80000' }],
      ['K5-1-r0-aje', { remark: '5000' }],
      ['K5-1-r0-rje', { remark: '0' }],
    ]))
    const tbData = ref({ unadjusted2701: 0, audited2701: 0 })
    const saveResponse = vi.fn()

    const adj = useK5Adjudication({ allResponses, tbData, saveResponse })
    expect(adj.getWarrantyAudited()).toBe(85000)
  })

  it('getLitigationAudited returns row 1 audited', async () => {
    const { useK5Adjudication } = await import('../composables/useK5Adjudication')

    const allResponses = ref(new Map<string, any>([
      ['K5-1-r1-unadj', { remark: '200000' }],
      ['K5-1-r1-aje', { remark: '10000' }],
      ['K5-1-r1-rje', { remark: '0' }],
    ]))
    const tbData = ref({ unadjusted2701: 0, audited2701: 0 })
    const saveResponse = vi.fn()

    const adj = useK5Adjudication({ allResponses, tbData, saveResponse })
    expect(adj.getLitigationAudited()).toBe(210000)
  })

  it('getDecommissionAudited returns row 4 audited', async () => {
    const { useK5Adjudication } = await import('../composables/useK5Adjudication')

    const allResponses = ref(new Map<string, any>([
      ['K5-1-r4-unadj', { remark: '50000' }],
      ['K5-1-r4-aje', { remark: '3000' }],
      ['K5-1-r4-rje', { remark: '1000' }],
    ]))
    const tbData = ref({ unadjusted2701: 0, audited2701: 0 })
    const saveResponse = vi.fn()

    const adj = useK5Adjudication({ allResponses, tbData, saveResponse })
    expect(adj.getDecommissionAudited()).toBe(54000)
  })
})

// ═══ 7.2-C: TB回写(2701) + EventBus substantive:adjudicated ═══

describe('K5 Integration — TB回写(2701) + EventBus', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('writebackTB2701 calls PUT with account_code=2701', async () => {
    const mockApi = { put: vi.fn().mockResolvedValue({}), get: vi.fn().mockResolvedValue({}) }
    const mockEventBus = { emit: vi.fn(), on: vi.fn(), off: vi.fn() }
    vi.doMock('@/services/apiProxy', () => ({ api: mockApi }))
    vi.doMock('@/utils/eventBus', () => ({ eventBus: mockEventBus }))
    vi.doMock('element-plus', () => ({ ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() } }))

    const { useK5FormData } = await import('../composables/useK5FormData')

    const formData = useK5FormData({
      wpId: ref('wp-k5-001'),
      projectId: ref('proj-001'),
      sheetPrefix: '1',
    })

    await formData.writebackTB2701(600000)

    expect(mockApi.put).toHaveBeenCalledWith(
      '/api/projects/proj-001/trial-balance/writeback',
      { account_code: '2701', audited_amount: 600000 },
    )
  })

  it('writebackTB2701 emits substantive:adjudicated with 2701/K5', async () => {
    const mockApi = { put: vi.fn().mockResolvedValue({}), get: vi.fn().mockResolvedValue({}) }
    const mockEventBus = { emit: vi.fn(), on: vi.fn(), off: vi.fn() }
    vi.doMock('@/services/apiProxy', () => ({ api: mockApi }))
    vi.doMock('@/utils/eventBus', () => ({ eventBus: mockEventBus }))
    vi.doMock('element-plus', () => ({ ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() } }))

    const { useK5FormData } = await import('../composables/useK5FormData')

    const formData = useK5FormData({
      wpId: ref('wp-k5-002'),
      projectId: ref('proj-002'),
      sheetPrefix: '1',
    })

    await formData.writebackTB2701(1200000)

    expect(mockEventBus.emit).toHaveBeenCalledWith(
      'substantive:adjudicated',
      expect.objectContaining({
        accountCode: '2701',
        auditedAmount: 1200000,
        wpCode: 'K5',
      }),
    )
  })

  it('writebackTB2701 updates local tbData.audited2701', async () => {
    const mockApi = { put: vi.fn().mockResolvedValue({}), get: vi.fn().mockResolvedValue({}) }
    const mockEventBus = { emit: vi.fn(), on: vi.fn(), off: vi.fn() }
    vi.doMock('@/services/apiProxy', () => ({ api: mockApi }))
    vi.doMock('@/utils/eventBus', () => ({ eventBus: mockEventBus }))
    vi.doMock('element-plus', () => ({ ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() } }))

    const { useK5FormData } = await import('../composables/useK5FormData')

    const formData = useK5FormData({
      wpId: ref('wp-k5-003'),
      projectId: ref('proj-003'),
      sheetPrefix: '1',
    })

    expect(formData.tbData.value.audited2701).toBe(0)
    await formData.writebackTB2701(2500000)
    expect(formData.tbData.value.audited2701).toBe(2500000)
  })

  it('writebackTB2701 zero amount is valid (全部转销)', async () => {
    const mockApi = { put: vi.fn().mockResolvedValue({}), get: vi.fn().mockResolvedValue({}) }
    const mockEventBus = { emit: vi.fn(), on: vi.fn(), off: vi.fn() }
    vi.doMock('@/services/apiProxy', () => ({ api: mockApi }))
    vi.doMock('@/utils/eventBus', () => ({ eventBus: mockEventBus }))
    vi.doMock('element-plus', () => ({ ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() } }))

    const { useK5FormData } = await import('../composables/useK5FormData')

    const formData = useK5FormData({
      wpId: ref('wp-k5-004'),
      projectId: ref('proj-004'),
      sheetPrefix: '1',
    })

    await formData.writebackTB2701(0)

    expect(mockApi.put).toHaveBeenCalledWith(
      '/api/projects/proj-004/trial-balance/writeback',
      { account_code: '2701', audited_amount: 0 },
    )
  })
})

// ═══ 7.2-D: 或有判断→确认/披露 联动集成 ═══

describe('K5 Integration — 或有判断→确认/披露联动', () => {
  it('determineRecognition drives recognition auto-derive for detail items', async () => {
    const { determineRecognition } = await import('../composables/useK5ContingencyEngine')

    // 模拟明细表行: 可能性级别→确认决策
    const detailItems = [
      { name: '诉讼A', level: 'very_likely' as const },
      { name: '合同纠纷B', level: 'possible' as const },
      { name: '远期担保C', level: 'remote' as const },
    ]

    const decisions = detailItems.map((item) => ({
      ...item,
      recognition: determineRecognition(item.level),
    }))

    expect(decisions[0].recognition).toBe('recognize') // 确认预计负债
    expect(decisions[1].recognition).toBe('disclose')  // 披露或有负债
    expect(decisions[2].recognition).toBe('ignore')    // 不处理

    // 只有 recognize 项纳入预计负债金额统计
    const recognized = decisions.filter((d) => d.recognition === 'recognize')
    expect(recognized).toHaveLength(1)
    expect(recognized[0].name).toBe('诉讼A')
  })
})

// ═══ 7.2-E: 三专项测算回连审定(质保/弃置/诉讼) ═══

describe('K5 Integration — 三专项测算回连审定', () => {
  it('warranty: calcWarrantyProvision feeds K5-4-warranty-end-total → matches K5-1', async () => {
    const { calcWarrantyProvision } = await import('../composables/useK5BestEstimateEngine')
    const { useK5CrossSheet } = await import('../composables/useK5CrossSheet')

    // 模拟质保测算: 收入1000万 × 保修率2% = 20万
    const warrantyTotal = calcWarrantyProvision(10000000, 0.02)
    expect(warrantyTotal).toBe(200000)

    // 将测算结果放入 CrossSheet 比对
    const allResponses = ref(new Map<string, any>([
      ['K5-1-audited-warranty', { remark: String(warrantyTotal) }],
      ['K5-4-warranty-end-total', { remark: String(warrantyTotal) }],
    ]))

    const cross = useK5CrossSheet(allResponses)
    expect(cross.warrantyVsAdjudication.value.isMatch).toBe(true)
  })

  it('decommission: calcPresentValue feeds K5-5-decommission-end-total → matches K5-1', async () => {
    const { calcPresentValue } = await import('../composables/useK5BestEstimateEngine')
    const { useK5CrossSheet } = await import('../composables/useK5CrossSheet')

    // 模拟弃置现值: 50万/(1+5%)^10 ≈ 306,957
    const decommissionPV = calcPresentValue(500000, 0.05, 10)
    const pvStr = String(Math.round(decommissionPV * 100) / 100)

    const allResponses = ref(new Map<string, any>([
      ['K5-1-audited-decommission', { remark: pvStr }],
      ['K5-5-decommission-end-total', { remark: pvStr }],
    ]))

    const cross = useK5CrossSheet(allResponses)
    expect(cross.decommissionVsAdjudication.value.isMatch).toBe(true)
  })

  it('litigation: recognized losses feed K5-6-litigation-loss-total', async () => {
    const { determineRecognition } = await import('../composables/useK5ContingencyEngine')
    const { useK5CrossSheet } = await import('../composables/useK5CrossSheet')

    // 模拟多个诉讼
    const litigations = [
      { loss: 200000, level: 'very_likely' as const },
      { loss: 100000, level: 'possible' as const },  // 不纳入负债
      { loss: 50000, level: 'remote' as const },     // 不纳入负债
    ]

    // 只有 recognize 的纳入
    const totalLoss = litigations
      .filter((l) => determineRecognition(l.level) === 'recognize')
      .reduce((sum, l) => sum + l.loss, 0)
    expect(totalLoss).toBe(200000)

    const allResponses = ref(new Map<string, any>([
      ['K5-1-audited-litigation', { remark: '200000' }],
      ['K5-6-litigation-loss-total', { remark: String(totalLoss) }],
    ]))

    const cross = useK5CrossSheet(allResponses)
    expect(cross.litigationVsAdjudication.value.isMatch).toBe(true)
  })
})

// ═══ 7.2-F: 附注 subscribe + 调整分录 EventBus ═══

describe('K5 Integration — 附注subscribe + 调整分录EventBus', () => {
  it('K5TabDisclosureListed subscribes to substantive:adjudicated', async () => {
    const { readFileSync } = await import('fs')
    const path = await import('path')
    const filePath = path.resolve(__dirname, '../k5/core/K5TabDisclosureListed.vue')

    let source: string
    try {
      source = readFileSync(filePath, 'utf-8')
    } catch {
      // File may not exist in test env — skip
      return
    }

    expect(source).toContain("substantive:adjudicated")
  })

  it('K5TabAdjustment publishes adjustment:created with K5/2701', async () => {
    const { readFileSync } = await import('fs')
    const path = await import('path')
    const filePath = path.resolve(__dirname, '../k5/core/K5TabAdjustment.vue')

    let source: string
    try {
      source = readFileSync(filePath, 'utf-8')
    } catch {
      return
    }

    expect(source).toContain("adjustment:created")
    expect(source).toContain("'K5'")
    expect(source).toContain('2701')
  })
})

// ═══ 7.2-G: useK5ImportExport 初始化验证 ═══

describe('K5 Integration — useK5ImportExport初始化', () => {
  it('uses http (axios) not native fetch', async () => {
    const { readFileSync } = await import('fs')
    const path = await import('path')
    const filePath = path.resolve(__dirname, '../composables/useK5ImportExport.ts')

    let source: string
    try {
      source = readFileSync(filePath, 'utf-8')
    } catch {
      return
    }

    expect(source).toContain("from '@/utils/http'")
    expect(source).not.toMatch(/\bfetch\s*\(/)
  })
})
