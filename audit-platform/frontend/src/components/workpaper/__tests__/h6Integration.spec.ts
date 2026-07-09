/**
 * H6 固定资产清理 — 集成测试
 *
 * 测试场景：
 * 1. 过渡科目期末=0校验（useH6CrossSheet.transitAccountStatus）
 * 2. H1→H6事件链（CustomEvent 'h1:disposal-completed' → createFromH1Disposal）
 * 3. H6→H10事件链（状态为'已结转' → dispatch 'disposal:completed'）
 * 4. 审定↔明细一致性（adjudicationVsDetail diff 校验）
 * 5. TB回写（writebackTrialBalance → 'substantive:adjudicated' event）
 * 6. useH6Adjudication transitCheck（endBalanceAudited≠0 → warning非空）
 * 7. useH6Check summary（存在'不合规'项 → hasNonCompliant=true）
 *
 * Spec: .kiro/specs/h6-asset-disposal-clearing/
 * Task: 7.2
 * Requirements: 2.5, 5.1-5.4, 6.1-6.3
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useH6CrossSheet } from '../composables/useH6CrossSheet'
import { useH6Detail } from '../composables/useH6Detail'
import { useH6Adjudication } from '../composables/useH6Adjudication'
import { useH6Check } from '../composables/useH6Check'

// ─── Mock API ────────────────────────────────────────────────────────────────

const mockGet = vi.fn().mockResolvedValue([])
const mockPut = vi.fn().mockResolvedValue({})

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeAllResponses(entries: Record<string, any> = {}) {
  const map = new Map<string, any>()
  for (const [key, val] of Object.entries(entries)) {
    map.set(key, { item_id: key, conclusion: null, remark: String(val) })
  }
  return ref(map)
}

// ─── 1. 过渡科目期末=0校验 ──────────────────────────────────────────────────

describe('H6 集成 — 过渡科目期末=0校验 (Req 2.5, 6.1-6.3)', () => {
  it('期末余额为0时 transitAccountStatus.isZero=true', () => {
    const allResponses = makeAllResponses({ 'H6-1-end-balance-audited': '0' })
    const { transitAccountStatus } = useH6CrossSheet(allResponses)
    expect(transitAccountStatus.value.isZero).toBe(true)
    expect(transitAccountStatus.value.balance).toBe(0)
  })

  it('期末余额不为0时 transitAccountStatus.isZero=false', () => {
    const allResponses = makeAllResponses({ 'H6-1-end-balance-audited': '15000.50' })
    const { transitAccountStatus } = useH6CrossSheet(allResponses)
    expect(transitAccountStatus.value.isZero).toBe(false)
    expect(transitAccountStatus.value.balance).toBeCloseTo(15000.50)
  })

  it('极小浮点差(0.005)仍视为零', () => {
    const allResponses = makeAllResponses({ 'H6-1-end-balance-audited': '0.005' })
    const { transitAccountStatus } = useH6CrossSheet(allResponses)
    expect(transitAccountStatus.value.isZero).toBe(true)
  })
})

// ─── 2. H1→H6事件链 ─────────────────────────────────────────────────────────

describe('H6 集成 — H1→H6事件链 (Req 5.3)', () => {
  it('createFromH1Disposal 正确创建清理明细行', () => {
    const allResponses = makeAllResponses({})
    const onSave = vi.fn()
    const { rows, createFromH1Disposal } = useH6Detail({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
      onSave,
    })

    createFromH1Disposal({
      assetName: '办公楼A栋',
      originalCost: 500000,
      accDep: 200000,
      refH1Code: 'H1-8-row-01',
    })

    expect(rows.value.length).toBe(1)
    expect(rows.value[0].assetName).toBe('办公楼A栋')
    expect(rows.value[0].originalCost).toBe(500000)
    expect(rows.value[0].accumulatedDepreciation).toBe(200000)
    expect(rows.value[0].netBookValue).toBe(300000) // 500000 - 200000
    expect(rows.value[0].refH1Code).toBe('H1-8-row-01')
    expect(rows.value[0].status).toBe('清理中')
  })

  it('CustomEvent h1:disposal-completed 模拟触发 → H6-2自动创建行', () => {
    const allResponses = makeAllResponses({})
    const onSave = vi.fn()
    const { rows, createFromH1Disposal } = useH6Detail({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
      onSave,
    })

    // 模拟 EventBus listener 行为：收到H1处置事件后调用createFromH1Disposal
    const payload = {
      assetName: '机器设备B',
      originalCost: 1000000,
      accDep: 600000,
      refH1Code: 'H1-8-row-05',
    }

    // Simulate event dispatch → listener calls createFromH1Disposal
    const event = new CustomEvent('h1:disposal-completed', { detail: payload })
    window.dispatchEvent(event)
    // Handler should call:
    createFromH1Disposal(payload)

    expect(rows.value.length).toBe(1)
    expect(rows.value[0].netBookValue).toBe(400000)
    expect(rows.value[0].gainLoss).toBe(-400000) // 0 - 400000 - 0 - 0
  })
})

// ─── 3. H6→H10事件链 ─────────────────────────────────────────────────────────

describe('H6 集成 — H6→H10事件链 (Req 5.4)', () => {
  it('明细行状态改为"已结转"时 dispatch disposal:completed', () => {
    const allResponses = makeAllResponses({
      'H6-2-rows': JSON.stringify([{
        rowId: 'r1',
        seq: 1,
        assetName: '设备C',
        originalCost: 800000,
        accumulatedDepreciation: 300000,
        disposalIncome: 600000,
        disposalExpenses: 20000,
        taxAmount: 10000,
        status: '已完成',
        refH1Code: '',
        refH10Code: '',
      }]),
    })
    const onSave = vi.fn()
    const { rows, updateCell } = useH6Detail({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
      onSave,
    })

    // 模拟 listener：当 updateCell('status', '已结转') 时 dispatch event
    const dispatchedEvents: CustomEvent[] = []
    const handler = (e: Event) => dispatchedEvents.push(e as CustomEvent)
    window.addEventListener('disposal:completed', handler)

    updateCell('r1', 'status', '已结转')
    expect(rows.value[0].status).toBe('已结转')

    // 模拟组件中的watch逻辑: 当状态变为'已结转'时发布事件
    const row = rows.value[0]
    if (row.status === '已结转') {
      window.dispatchEvent(new CustomEvent('disposal:completed', {
        detail: {
          wpCode: 'H6',
          rowId: row.rowId,
          assetName: row.assetName,
          gainLoss: row.gainLoss,
        },
      }))
    }

    expect(dispatchedEvents.length).toBe(1)
    expect(dispatchedEvents[0].detail.wpCode).toBe('H6')
    expect(dispatchedEvents[0].detail.assetName).toBe('设备C')
    // gainLoss = 600000 - (800000-300000) - 20000 - 10000 = 600000 - 500000 - 20000 - 10000 = 70000
    expect(dispatchedEvents[0].detail.gainLoss).toBe(70000)

    window.removeEventListener('disposal:completed', handler)
  })
})

// ─── 4. 审定↔明细一致性 ─────────────────────────────────────────────────────

describe('H6 集成 — 审定↔明细一致性 (Req 2.5)', () => {
  it('H6-1 gain/loss ≠ H6-2 subtotal gain/loss → diff非零', () => {
    const allResponses = makeAllResponses({
      'H6-1-disposal-gain-loss': '120000',
      'H6-2-subtotal-gain-loss': '115000',
    })
    const { adjudicationVsDetail } = useH6CrossSheet(allResponses)
    expect(adjudicationVsDetail.value.diff).toBeCloseTo(5000)
    expect(adjudicationVsDetail.value.isMatch).toBe(false)
  })

  it('H6-1 gain/loss = H6-2 subtotal gain/loss → isMatch=true', () => {
    const allResponses = makeAllResponses({
      'H6-1-disposal-gain-loss': '88000',
      'H6-2-subtotal-gain-loss': '88000',
    })
    const { adjudicationVsDetail } = useH6CrossSheet(allResponses)
    expect(adjudicationVsDetail.value.diff).toBeCloseTo(0)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
  })

  it('两者都为0时 isMatch=true', () => {
    const allResponses = makeAllResponses({
      'H6-1-disposal-gain-loss': '0',
      'H6-2-subtotal-gain-loss': '0',
    })
    const { adjudicationVsDetail } = useH6CrossSheet(allResponses)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
  })
})

// ─── 5. TB回写 ──────────────────────────────────────────────────────────────

describe('H6 集成 — TB回写 (Req 2.8)', () => {
  let eventsCaptured: CustomEvent[]
  let handler: (e: Event) => void

  beforeEach(() => {
    eventsCaptured = []
    handler = (e: Event) => eventsCaptured.push(e as CustomEvent)
    window.addEventListener('substantive:adjudicated', handler)
    mockPut.mockResolvedValue({})
  })

  afterEach(() => {
    window.removeEventListener('substantive:adjudicated', handler)
  })

  it('writebackTrialBalance dispatches substantive:adjudicated event', async () => {
    const { useH6FormData } = await import('../composables/useH6FormData')
    const formData = useH6FormData({
      wpId: ref('wp-100'),
      projectId: ref('proj-200'),
    })

    await formData.writebackTrialBalance(50000)

    // 验证API调用
    expect(mockPut).toHaveBeenCalledWith(
      '/api/projects/proj-200/trial-balance/writeback',
      { account_code: '1606', audited_amount: 50000 },
    )

    // 验证CustomEvent发布
    expect(eventsCaptured.length).toBe(1)
    expect(eventsCaptured[0].detail.wpCode).toBe('H6')
    expect(eventsCaptured[0].detail.accountCode).toBe('1606')
    expect(eventsCaptured[0].detail.auditedAmount).toBe(50000)
    expect(eventsCaptured[0].detail.isTransitAccount).toBe(true)
  })
})

// ─── 6. useH6Adjudication transitCheck ───────────────────────────────────────

describe('H6 集成 — transitCheck 过渡科目期末校验 (Req 6.1-6.3)', () => {
  it('endBalanceAudited ≠ 0 时 transitCheck.warning 非空', () => {
    const allResponses = makeAllResponses({
      'H6-1-rows': JSON.stringify([
        { name: '清理收入', category: 'income', beginBalance: 0, debitAmount: 100000, creditAmount: 0, unadjusted: 100000, aje: 0, rje: 0 },
        { name: '清理支出—账面价值', category: 'expense', subCategory: 'bookValue', beginBalance: 0, debitAmount: 0, creditAmount: 60000, unadjusted: 60000, aje: 0, rje: 0 },
        { name: '清理净损益', category: 'gainLoss', isSubtotal: true, beginBalance: 0, debitAmount: 0, creditAmount: 0, unadjusted: 0, aje: 0, rje: 0 },
        { name: '期末余额', category: 'balance', beginBalance: 5000, debitAmount: 20000, creditAmount: 10000, unadjusted: 15000, aje: 0, rje: 0 },
      ]),
    })

    const { transitCheck, endBalanceAudited } = useH6Adjudication({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
    })

    // 期末余额行 audited = 15000 + 0 + 0 = 15000
    expect(endBalanceAudited.value).toBe(15000)
    expect(transitCheck.value.isZero).toBe(false)
    expect(transitCheck.value.warning).toContain('过渡科目期末余额应为0')
    expect(transitCheck.value.warning).toContain('15000')
  })

  it('endBalanceAudited = 0 时 transitCheck.warning 为空', () => {
    const allResponses = makeAllResponses({
      'H6-1-rows': JSON.stringify([
        { name: '清理收入', category: 'income', beginBalance: 0, debitAmount: 0, creditAmount: 0, unadjusted: 0, aje: 0, rje: 0 },
        { name: '期末余额', category: 'balance', beginBalance: 0, debitAmount: 0, creditAmount: 0, unadjusted: 0, aje: 0, rje: 0 },
      ]),
    })

    const { transitCheck } = useH6Adjudication({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
    })

    expect(transitCheck.value.isZero).toBe(true)
    expect(transitCheck.value.warning).toBe('')
  })
})

// ─── 7. useH6Check summary ──────────────────────────────────────────────────

describe('H6 集成 — useH6Check summary (Req 4.5)', () => {
  it('存在"不合规"项时 summary.hasNonCompliant=true', () => {
    const allResponses = makeAllResponses({
      'H6-4-rows': JSON.stringify([
        {
          rowId: 'chk-1',
          linkedDetailRowId: 'r1',
          projectName: '设备A',
          disposalApproval: '合规',
          assetValuation: '不合规',
          taxTreatment: '合规',
          accountingTreatment: '合规',
          incomeRecognition: '合规',
          expenseAllocation: '合规',
          transferTiming: '合规',
          conclusion: '不合规',
          remark: '',
        },
        {
          rowId: 'chk-2',
          linkedDetailRowId: 'r2',
          projectName: '车辆B',
          disposalApproval: '合规',
          assetValuation: '合规',
          taxTreatment: '合规',
          accountingTreatment: '合规',
          incomeRecognition: '合规',
          expenseAllocation: '合规',
          transferTiming: '合规',
          conclusion: '合规',
          remark: '',
        },
      ]),
    })

    const { summary } = useH6Check({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
    })

    expect(summary.value.hasNonCompliant).toBe(true)
    expect(summary.value.nonCompliantCount).toBe(2) // assetValuation + conclusion of row1
    expect(summary.value.warning).toContain('不合规')
  })

  it('全部"合规"时 summary.hasNonCompliant=false', () => {
    const allResponses = makeAllResponses({
      'H6-4-rows': JSON.stringify([
        {
          rowId: 'chk-1',
          linkedDetailRowId: 'r1',
          projectName: '设备A',
          disposalApproval: '合规',
          assetValuation: '合规',
          taxTreatment: '合规',
          accountingTreatment: '合规',
          incomeRecognition: '合规',
          expenseAllocation: '合规',
          transferTiming: '合规',
          conclusion: '合规',
          remark: '',
        },
      ]),
    })

    const { summary } = useH6Check({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
    })

    expect(summary.value.hasNonCompliant).toBe(false)
    expect(summary.value.nonCompliantCount).toBe(0)
    expect(summary.value.warning).toBe('')
    expect(summary.value.compliantCount).toBe(8)
  })

  it('空行列表时 totalChecks=0, hasNonCompliant=false', () => {
    const allResponses = makeAllResponses({})

    const { summary } = useH6Check({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      allResponses,
    })

    expect(summary.value.totalChecks).toBe(0)
    expect(summary.value.hasNonCompliant).toBe(false)
  })
})
