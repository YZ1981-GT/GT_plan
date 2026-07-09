/**
 * K3 其他应付款 — 集成测试
 *
 * Spec: .kiro/specs/k3-other-payables/ Task 7.2
 * Validates: Requirements 2.5, 2.6, 5.4
 *
 * 三大验证域：
 * 1. 负债类回写（writebackTB 2241 + EventBus substantive:adjudicated）
 * 2. 长期挂账联动（K3-2 明细3年以上 → K3-5 联动 longOutstandingVsDetail）
 * 3. 账龄勾稽（aging buckets sum ≡ period-end balance + adjudicationVsDetail）
 *
 * 科目：2241 其他应付款（贷方/负债类）
 * ⚠️ 负债类方向：期末 = 期初 + 贷方 - 借方
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import {
  calcLiabilityEndBalance,
  calcSubtotal,
  calcTriangleReconciliation,
  calcAuditedAmount,
} from '../composables/useK3FormulaEngine'
import { useK3CrossSheet } from '../composables/useK3CrossSheet'

// ═══════════════════════════════════════════════════════════════════════════════
// 1. 负债类回写 (Liability TB Writeback) — Req 2.6
// ═══════════════════════════════════════════════════════════════════════════════

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ data: [] }),
    put: vi.fn().mockResolvedValue({ data: { success: true } }),
  },
}))

vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), error: vi.fn(), success: vi.fn() },
}))

describe('K3 集成 — 负债类回写（Req 2.6）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('writebackTB 调用 trial-balance/writeback 端点，科目=2241', async () => {
    const { api } = await import('@/services/apiProxy')
    const { useK3FormData } = await import('../composables/useK3FormData')

    const wpId = ref('wp-001')
    const projectId = ref('proj-001')
    const formData = useK3FormData({ wpId, projectId, sheetPrefix: 'K3-1' })

    await formData.writebackTB(50000)

    expect(api.put).toHaveBeenCalledWith(
      '/api/projects/proj-001/trial-balance/writeback',
      expect.objectContaining({
        account_code: '2241',
        audited_amount: 50000,
      }),
    )
  })

  it('writebackTB 成功后 emit substantive:adjudicated 含负债科目2241', async () => {
    const { eventBus } = await import('@/utils/eventBus')
    const { useK3FormData } = await import('../composables/useK3FormData')

    const wpId = ref('wp-001')
    const projectId = ref('proj-001')
    const formData = useK3FormData({ wpId, projectId, sheetPrefix: 'K3-1' })

    await formData.writebackTB(123456.78)

    expect(eventBus.emit).toHaveBeenCalledWith(
      'substantive:adjudicated',
      expect.objectContaining({
        accountCode: '2241',
        auditedAmount: 123456.78,
        wpCode: 'K3',
      }),
    )
  })

  it('负债类方向校验：贷方增加/借方减少 体现在 calcLiabilityEndBalance', () => {
    // 负债类：期末 = 期初 + 贷方(增加) - 借方(减少)
    const begin = 100000
    const credit = 30000 // 贷方发生（增加负债）
    const debit = 10000 // 借方发生（减少负债）
    const end = calcLiabilityEndBalance(begin, credit, debit)
    expect(end).toBe(120000) // 100000 + 30000 - 10000

    // 与资产类方向相反验证：
    // 资产类：期末 = 期初 + 借方 - 贷方
    // 负债类：期末 = 期初 + 贷方 - 借方
    const endAssetDirection = begin + debit - credit // 假设按资产类计算
    expect(endAssetDirection).not.toBe(end) // 方向相反，结果不同
  })

  it('writebackTB 同步更新本地 tbData.audited2241', async () => {
    const { useK3FormData } = await import('../composables/useK3FormData')

    const wpId = ref('wp-001')
    const projectId = ref('proj-001')
    const formData = useK3FormData({ wpId, projectId, sheetPrefix: 'K3-1' })

    expect(formData.tbData.value.audited2241).toBe(0)
    await formData.writebackTB(88888)
    expect(formData.tbData.value.audited2241).toBe(88888)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. 长期挂账联动 (Long Outstanding Linkage) — Req 5.4
// ═══════════════════════════════════════════════════════════════════════════════

describe('K3 集成 — 长期挂账联动（Req 5.4）', () => {
  it('longOutstandingVsDetail 正确读取 K3-2 3年以上账龄笔数和金额', () => {
    const allResponses = ref(new Map<string, any>([
      ['K3-2-aging-over3y-count', { item_id: 'K3-2-aging-over3y-count', remark: '5', conclusion: null }],
      ['K3-2-aging-over3y-total', { item_id: 'K3-2-aging-over3y-total', remark: '250000', conclusion: null }],
    ]))

    const { longOutstandingVsDetail } = useK3CrossSheet(allResponses)
    expect(longOutstandingVsDetail.value.count).toBe(5)
    expect(longOutstandingVsDetail.value.total).toBe(250000)
  })

  it('无3年以上账龄数据时 count=0, total=0', () => {
    const allResponses = ref(new Map<string, any>())
    const { longOutstandingVsDetail } = useK3CrossSheet(allResponses)
    expect(longOutstandingVsDetail.value.count).toBe(0)
    expect(longOutstandingVsDetail.value.total).toBe(0)
  })

  it('K3-2 明细数据变化时 longOutstandingVsDetail 响应式联动更新', () => {
    const allResponses = ref(new Map<string, any>())
    const { longOutstandingVsDetail } = useK3CrossSheet(allResponses)

    // 初始为空
    expect(longOutstandingVsDetail.value.count).toBe(0)
    expect(longOutstandingVsDetail.value.total).toBe(0)

    // 模拟 K3-2 明细数据写入（新增3年以上款项）
    allResponses.value = new Map<string, any>([
      ['K3-2-aging-over3y-count', { item_id: 'K3-2-aging-over3y-count', remark: '3', conclusion: null }],
      ['K3-2-aging-over3y-total', { item_id: 'K3-2-aging-over3y-total', remark: '180000', conclusion: null }],
    ])

    // 联动更新
    expect(longOutstandingVsDetail.value.count).toBe(3)
    expect(longOutstandingVsDetail.value.total).toBe(180000)
  })

  it('remark 为非数字字符串时降级为 0', () => {
    const allResponses = ref(new Map<string, any>([
      ['K3-2-aging-over3y-count', { item_id: 'K3-2-aging-over3y-count', remark: 'N/A', conclusion: null }],
      ['K3-2-aging-over3y-total', { item_id: 'K3-2-aging-over3y-total', remark: '', conclusion: null }],
    ]))

    const { longOutstandingVsDetail } = useK3CrossSheet(allResponses)
    expect(longOutstandingVsDetail.value.count).toBe(0)
    expect(longOutstandingVsDetail.value.total).toBe(0)
  })

  it('conclusion 作为降级数据源（remark 为 null 时读 conclusion）', () => {
    const allResponses = ref(new Map<string, any>([
      ['K3-2-aging-over3y-count', { item_id: 'K3-2-aging-over3y-count', remark: null, conclusion: '2' }],
      ['K3-2-aging-over3y-total', { item_id: 'K3-2-aging-over3y-total', remark: null, conclusion: '95000' }],
    ]))

    const { longOutstandingVsDetail } = useK3CrossSheet(allResponses)
    expect(longOutstandingVsDetail.value.count).toBe(2)
    expect(longOutstandingVsDetail.value.total).toBe(95000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. 账龄勾稽 (Aging Reconciliation) — Req 2.5
// ═══════════════════════════════════════════════════════════════════════════════

describe('K3 集成 — 账龄勾稽（Req 2.5）', () => {
  it('4区间账龄合计 === calcSubtotal 结果', () => {
    // 1年内 / 1-2年 / 2-3年 / 3年以上
    const agingBuckets = [80000, 30000, 15000, 5000]
    const agingTotal = calcSubtotal(agingBuckets)
    expect(agingTotal).toBe(130000)
  })

  it('账龄合计 === calcLiabilityEndBalance 期末余额（勾稽平衡）', () => {
    const begin = 100000
    const credit = 50000 // 贷方（负债增加）
    const debit = 20000 // 借方（负债减少）
    const endBalance = calcLiabilityEndBalance(begin, credit, debit) // 130000

    // 账龄区间分布
    const aging1y = 80000 // 1年内
    const aging1to2 = 30000 // 1-2年
    const aging2to3 = 15000 // 2-3年
    const aging3plus = 5000 // 3年以上
    const agingTotal = calcSubtotal([aging1y, aging1to2, aging2to3, aging3plus])

    // 勾稽：账龄合计 === 期末余额
    expect(agingTotal).toBe(endBalance)
  })

  it('三角勾稽差额为0时，账龄合计与期末一致', () => {
    const begin = 200000
    const inc = 80000 // 增加（贷方）
    const dec = 30000 // 减少（借方）
    const end = begin + inc - dec // 250000

    // 三角勾稽验证
    const reconciliation = calcTriangleReconciliation(begin, inc, dec, end)
    expect(reconciliation).toBe(0)

    // 账龄分布（总和应等于 end）
    const agingBuckets = [150000, 60000, 25000, 15000]
    const agingTotal = calcSubtotal(agingBuckets)
    expect(agingTotal).toBe(end)
  })

  it('adjudicationVsDetail 审定表合计 vs 明细合计：匹配场景', () => {
    const allResponses = ref(new Map<string, any>([
      ['K3-1-audited-total', { item_id: 'K3-1-audited-total', remark: '500000', conclusion: null }],
      ['K3-2-detail-total', { item_id: 'K3-2-detail-total', remark: '500000', conclusion: null }],
    ]))

    const { adjudicationVsDetail } = useK3CrossSheet(allResponses)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
    expect(adjudicationVsDetail.value.diff).toBeCloseTo(0)
  })

  it('adjudicationVsDetail 审定表合计 vs 明细合计：不匹配场景', () => {
    const allResponses = ref(new Map<string, any>([
      ['K3-1-audited-total', { item_id: 'K3-1-audited-total', remark: '500000', conclusion: null }],
      ['K3-2-detail-total', { item_id: 'K3-2-detail-total', remark: '480000', conclusion: null }],
    ]))

    const { adjudicationVsDetail } = useK3CrossSheet(allResponses)
    expect(adjudicationVsDetail.value.isMatch).toBe(false)
    expect(adjudicationVsDetail.value.diff).toBe(20000) // 审定 - 明细
  })

  it('审定数公式联动：未审+AJE+RJE → 审定 → 回写对象', () => {
    const unadj = 480000
    const aje = 15000
    const rje = 5000
    const audited = calcAuditedAmount(unadj, aje, rje)
    expect(audited).toBe(500000)

    // 审定数与明细匹配时，adjudicationVsDetail.isMatch = true
    const allResponses = ref(new Map<string, any>([
      ['K3-1-audited-total', { item_id: 'K3-1-audited-total', remark: String(audited), conclusion: null }],
      ['K3-2-detail-total', { item_id: 'K3-2-detail-total', remark: '500000', conclusion: null }],
    ]))

    const { adjudicationVsDetail } = useK3CrossSheet(allResponses)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
  })

  it('全零场景：期初=0, 贷方=0, 借方=0 → 期末=0, 账龄合计=0', () => {
    const end = calcLiabilityEndBalance(0, 0, 0)
    expect(end).toBe(0)

    const agingTotal = calcSubtotal([0, 0, 0, 0])
    expect(agingTotal).toBe(0)
    expect(agingTotal).toBe(end)
  })

  it('adjudicationVsDetail 双方均为0时 isMatch=true', () => {
    const allResponses = ref(new Map<string, any>([
      ['K3-1-audited-total', { item_id: 'K3-1-audited-total', remark: '0', conclusion: null }],
      ['K3-2-detail-total', { item_id: 'K3-2-detail-total', remark: '0', conclusion: null }],
    ]))

    const { adjudicationVsDetail } = useK3CrossSheet(allResponses)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
    expect(adjudicationVsDetail.value.diff).toBe(0)
  })

  it('微小浮点差异(<0.01)视为匹配', () => {
    const allResponses = ref(new Map<string, any>([
      ['K3-1-audited-total', { item_id: 'K3-1-audited-total', remark: '500000.005', conclusion: null }],
      ['K3-2-detail-total', { item_id: 'K3-2-detail-total', remark: '500000', conclusion: null }],
    ]))

    const { adjudicationVsDetail } = useK3CrossSheet(allResponses)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
  })
})
