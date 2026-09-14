/**
 * Integration Tests — L1/L3→L2 计提核对 + L2→L8 联动
 *
 * Spec: .kiro/specs/l2-interest-payable/
 * Task: 7.2
 * Requirements: 4.1-4.6
 *
 * 验证：
 * 1. L1→L2 计提核对：eventBus 'l1:interest-calculated' → accrualVsL1L3 反映 L1 利息
 * 2. L3→L2 计提核对：eventBus 'l3:interest-calculated' → accrualVsL1L3 反映 L3 利息
 * 3. L2→L8 联动：明细行 accrued 变化 → eventBus 'l2:accrual-calculated' 发布
 * 4. L2→TB 回写联动：writebackTB → eventBus 'substantive:adjudicated'
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick, effectScope, type EffectScope } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { useL2CrossSheet } from '../useL2CrossSheet'
import { useL2Detail } from '../useL2Detail'
import type { ChecklistResponse } from '../useL2FormData'

// Mock api module (used by useL2FormData.writebackTB)
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ data: [] }),
    put: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
  },
}))

// Mock element-plus
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

// ─── L1→L2 计提核对 ─────────────────────────────────────────────────────────

describe('L1→L2 计提核对 (Req 4.1)', () => {
  let scope: EffectScope

  beforeEach(() => {
    scope = effectScope()
  })

  afterEach(() => {
    scope.stop()
  })

  it('eventBus l1:interest-calculated → accrualVsL1L3 反映 L1 利息（一致场景）', async () => {
    await scope.run(async () => {
      // 准备：allResponses 中 L2-2 明细行总计提 = 5000
      const allResponses = ref<Map<string, ChecklistResponse>>(new Map([
        ['L2-L2-2-rows', {
          item_id: 'L2-L2-2-rows',
          conclusion: null,
          remark: JSON.stringify([
            { accrued: 3000 },
            { accrued: 2000 },
          ]),
        }],
      ]))

      const crossSheet = useL2CrossSheet(allResponses)

      // 初始：L1 未推送，accrualVsL1L3.diff = 0 - 5000 = -5000
      expect(crossSheet.l1InterestData.value).toBeNull()

      // 触发 L1 利息测算事件（totalInterest = 5000）
      eventBus.emit('l1:interest-calculated', {
        wpCode: 'L1',
        totalInterest: 5000,
        financialExpenseInterest: 5000,
        byContract: [{ contractNo: 'C001', interest: 5000 }],
        timestamp: Date.now(),
      })
      await nextTick()

      // 验证：L1 数据已接收
      expect(crossSheet.l1InterestData.value).not.toBeNull()
      expect(crossSheet.l1EstimatedInterest.value).toBe(5000)

      // 一致场景：L1(5000) + L3(0) - booked(5000) = 0
      expect(crossSheet.accrualVsL1L3.value.diff).toBe(0)
      expect(crossSheet.accrualVsL1L3.value.isConsistent).toBe(true)
    })
  })

  it('eventBus l1:interest-calculated → accrualVsL1L3 不一致场景（大差异）', async () => {
    await scope.run(async () => {
      // 准备：明细表总计提 = 1000
      const allResponses = ref<Map<string, ChecklistResponse>>(new Map([
        ['L2-L2-2-rows', {
          item_id: 'L2-L2-2-rows',
          conclusion: null,
          remark: JSON.stringify([{ accrued: 1000 }]),
        }],
      ]))

      const crossSheet = useL2CrossSheet(allResponses)

      // 触发 L1 利息测算事件（totalInterest = 5000，大于账面）
      eventBus.emit('l1:interest-calculated', {
        wpCode: 'L1',
        totalInterest: 5000,
        financialExpenseInterest: 5000,
        byContract: [{ contractNo: 'C001', interest: 5000 }],
        timestamp: Date.now(),
      })
      await nextTick()

      // 不一致：L1(5000) + L3(0) - booked(1000) = 4000 >> 1.0 阈值
      expect(crossSheet.accrualVsL1L3.value.diff).toBe(4000)
      expect(crossSheet.accrualVsL1L3.value.isConsistent).toBe(false)
    })
  })
})

// ─── L3→L2 计提核对 ─────────────────────────────────────────────────────────

describe('L3→L2 计提核对 (Req 4.2)', () => {
  let scope: EffectScope

  beforeEach(() => {
    scope = effectScope()
  })

  afterEach(() => {
    scope.stop()
  })

  it('eventBus l3:interest-calculated → accrualVsL1L3 反映 L3 利息', async () => {
    await scope.run(async () => {
      // 准备：明细表总计提 = 3000
      const allResponses = ref<Map<string, ChecklistResponse>>(new Map([
        ['L2-L2-2-rows', {
          item_id: 'L2-L2-2-rows',
          conclusion: null,
          remark: JSON.stringify([{ accrued: 3000 }]),
        }],
      ]))

      const crossSheet = useL2CrossSheet(allResponses)

      // 触发 L3 长期借款利息测算事件
      eventBus.emit('l3:interest-calculated', {
        wpCode: 'L3',
        totalInterest: 3000,
        financialExpenseInterest: 3000,
        byContract: [{ contractNo: 'LT-001', interest: 3000 }],
        timestamp: Date.now(),
      })
      await nextTick()

      // 验证：L3 数据已接收
      expect(crossSheet.l3InterestData.value).not.toBeNull()
      expect(crossSheet.l3EstimatedInterest.value).toBe(3000)

      // 一致：L1(0) + L3(3000) - booked(3000) = 0
      expect(crossSheet.accrualVsL1L3.value.diff).toBe(0)
      expect(crossSheet.accrualVsL1L3.value.isConsistent).toBe(true)
    })
  })

  it('L1+L3 共同推送 → accrualVsL1L3 合计', async () => {
    await scope.run(async () => {
      // 明细表总计提 = 7500
      const allResponses = ref<Map<string, ChecklistResponse>>(new Map([
        ['L2-L2-2-rows', {
          item_id: 'L2-L2-2-rows',
          conclusion: null,
          remark: JSON.stringify([{ accrued: 4500 }, { accrued: 3000 }]),
        }],
      ]))

      const crossSheet = useL2CrossSheet(allResponses)

      // L1 推送
      eventBus.emit('l1:interest-calculated', {
        wpCode: 'L1',
        totalInterest: 5000,
        financialExpenseInterest: 5000,
        byContract: [],
        timestamp: Date.now(),
      })

      // L3 推送
      eventBus.emit('l3:interest-calculated', {
        wpCode: 'L3',
        totalInterest: 3000,
        financialExpenseInterest: 3000,
        byContract: [],
        timestamp: Date.now(),
      })
      await nextTick()

      // L1(5000) + L3(3000) - booked(7500) = 500，超阈值1.0
      expect(crossSheet.accrualVsL1L3.value.diff).toBe(500)
      expect(crossSheet.accrualVsL1L3.value.isConsistent).toBe(false)
    })
  })
})

// ─── L2→L8 联动 ─────────────────────────────────────────────────────────────

describe('L2→L8 联动 (Req 4.6)', () => {
  let scope: EffectScope
  let emitSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    scope = effectScope()
    emitSpy = vi.spyOn(eventBus, 'emit')
  })

  afterEach(() => {
    scope.stop()
    emitSpy.mockRestore()
  })

  it('明细行 accrued 变化 → 发布 l2:accrual-calculated 含正确载荷', async () => {
    await scope.run(async () => {
      const allResponses = ref<Map<string, ChecklistResponse>>(new Map([
        ['L2-L2-2-rows', {
          item_id: 'L2-L2-2-rows',
          conclusion: null,
          remark: JSON.stringify([
            { rowId: 'r1', source: '短期借款利息', accrued: 1000, beginBalance: 0, paid: 0 },
            { rowId: 'r2', source: '长期借款利息', accrued: 2000, beginBalance: 0, paid: 0 },
          ]),
        }],
      ]))

      const wpId = ref('wp-test-1')
      const projectId = ref('proj-test-1')
      const wpCode = ref('L2')
      const debouncedSave = vi.fn()
      const saveField = vi.fn()

      useL2Detail({
        allResponses,
        wpId,
        projectId,
        wpCode,
        debouncedSave,
        saveField,
      })

      // 等待 watch immediate 触发
      await nextTick()
      // 清除初始化触发的 emit 调用
      emitSpy.mockClear()

      // 模拟 accrued 变化：修改 allResponses 触发重载
      allResponses.value.set('L2-L2-2-rows', {
        item_id: 'L2-L2-2-rows',
        conclusion: null,
        remark: JSON.stringify([
          { rowId: 'r1', source: '短期借款利息', accrued: 1500, beginBalance: 0, paid: 0 },
          { rowId: 'r2', source: '长期借款利息', accrued: 2500, beginBalance: 0, paid: 0 },
        ]),
      })
      // 触发 Map 引用变化
      allResponses.value = new Map(allResponses.value)
      await nextTick()
      await nextTick() // 双层 watch 需要两轮 nextTick

      // 验证发布了 l2:accrual-calculated
      const accrualCalls = emitSpy.mock.calls.filter(
        (c) => c[0] === 'l2:accrual-calculated',
      )
      expect(accrualCalls.length).toBeGreaterThanOrEqual(1)

      // 验证载荷结构
      const lastPayload = accrualCalls[accrualCalls.length - 1][1] as any
      expect(lastPayload).toMatchObject({
        wpCode: 'L2',
        totalAccrued: expect.any(Number),
        bySource: expect.any(Array),
        timestamp: expect.any(Number),
      })
      expect(lastPayload.totalAccrued).toBe(4000) // 1500 + 2500
      expect(lastPayload.bySource).toEqual(
        expect.arrayContaining([
          { source: '短期借款利息', amount: 1500 },
          { source: '长期借款利息', amount: 2500 },
        ]),
      )
    })
  })
})

// ─── L2→TB 回写联动 ─────────────────────────────────────────────────────────

describe('L2→TB 回写联动 (Req 2.6)', () => {
  let emitSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    emitSpy = vi.spyOn(eventBus, 'emit')
  })

  afterEach(() => {
    emitSpy.mockRestore()
  })

  it('writebackTB 成功后发布 substantive:adjudicated', async () => {
    // 直接测试 useL2FormData.writebackTB 行为
    // writebackTB 调用 api.put 成功后 emit substantive:adjudicated
    const { api } = await import('@/services/apiProxy')
    ;(api.put as any).mockResolvedValueOnce({ data: {} })

    const scope = effectScope()
    await scope.run(async () => {
      const { useL2FormData } = await import('../useL2FormData')
      const formData = useL2FormData({
        wpId: ref('wp-tb-test'),
        projectId: ref('proj-tb-test'),
      })

      emitSpy.mockClear()

      await formData.writebackTB(12345.67)

      // 验证发布 substantive:adjudicated
      const adjCalls = emitSpy.mock.calls.filter(
        (c) => c[0] === 'substantive:adjudicated',
      )
      expect(adjCalls.length).toBe(1)

      const payload = adjCalls[0][1] as any
      expect(payload).toMatchObject({
        accountCode: '2231',
        auditedAmount: 12345.67,
        wpCode: 'L2',
        timestamp: expect.any(Number),
      })
    })
    scope.stop()
  })
})
