/**
 * 集成测试 — M4 资本公积：J3→M4 + M2→M4 + 审定回写
 *
 * 覆盖：
 * 1. EventBus J3→M4 linkage: 'j3:equity-settled' → useM4CrossSheet.shareBasedVsJ3 更新
 * 2. EventBus M2→M4 linkage: 'm2:fx-diff' → useM4CrossSheet.fxDiffVsM2 更新
 * 3. TB writeback: writebackTB(auditedAmount) → PUT /trial-balance/writeback + EventBus 'substantive:adjudicated'
 * 4. Cross-sheet validation: adjudicationVsDetail.isMatch 审定表 vs 明细表勾稽
 * 5. Share-based diff threshold: shareBasedVsJ3.isConsistent 阈值逻辑
 * 6. EventBus cleanup: onScopeDispose 取消订阅
 *
 * Spec: .kiro/specs/m4-capital-reserve/ Task 7.2
 * Requirements: 4.1-4.6
 *
 * 科目：4002 资本公积（**贷方/权益类！期末=期初+贷方-借方**）
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, effectScope } from 'vue'
import { useM4CrossSheet, DIFF_THRESHOLD } from '../composables/useM4CrossSheet'
import type { ChecklistResponse } from '../composables/useM4FormData'

// Mock eventBus — 保留 on/off/emit 函数引用以便测试中模拟事件触发
const onHandlers = new Map<string, Function[]>()
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: vi.fn((event: string, payload: any) => {
      const handlers = onHandlers.get(event)
      if (handlers) {
        handlers.forEach((h) => h(payload))
      }
    }),
    on: vi.fn((event: string, handler: Function) => {
      if (!onHandlers.has(event)) onHandlers.set(event, [])
      onHandlers.get(event)!.push(handler)
    }),
    off: vi.fn((event: string, handler: Function) => {
      const handlers = onHandlers.get(event)
      if (handlers) {
        const idx = handlers.indexOf(handler)
        if (idx >= 0) handlers.splice(idx, 1)
      }
    }),
  },
}))

// Mock api for writebackTB test
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn().mockResolvedValue([]),
    put: vi.fn().mockResolvedValue({ code: 200 }),
    post: vi.fn().mockResolvedValue({ code: 200 }),
  },
}))

import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function createResponses(entries: [string, string | null][]) {
  const map = new Map<string, ChecklistResponse>()
  for (const [itemId, remark] of entries) {
    map.set(itemId, { item_id: itemId, conclusion: null, remark })
  }
  return ref(map)
}

// ═══════════════════════════════════════════════════════════════════════════════
// Section 1: EventBus J3→M4 linkage — 'j3:equity-settled' → shareBasedVsJ3
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — EventBus J3→M4 linkage (Req 4.1-4.3)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('emit j3:equity-settled → shareBasedVsJ3 computed 更新', () => {
    const responses = createResponses([
      ['M4-M4-2-other-share-based-increase', '5000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { shareBasedVsJ3 } = useM4CrossSheet(responses)

      // 初始: J3金额=0, 账面=5000 → diff=-5000
      expect(shareBasedVsJ3.value.diff).toBe(-5000)
      expect(shareBasedVsJ3.value.isConsistent).toBe(false)

      // 模拟 J3 发出 equity-settled 事件
      eventBus.emit('j3:equity-settled' as any, { equitySettledAmount: 5000 })

      // 更新后: J3金额=5000, 账面=5000 → diff=0
      expect(shareBasedVsJ3.value.diff).toBe(0)
      expect(shareBasedVsJ3.value.isConsistent).toBe(true)
    })
    scope.stop()
  })

  it('J3金额与账面有差异时 isConsistent=false', () => {
    const responses = createResponses([
      ['M4-M4-2-other-share-based-increase', '4800'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { shareBasedVsJ3 } = useM4CrossSheet(responses)

      // 模拟 J3 事件发送 5000
      eventBus.emit('j3:equity-settled' as any, { equitySettledAmount: 5000 })

      // diff = 5000 - 4800 = 200 > DIFF_THRESHOLD
      expect(shareBasedVsJ3.value.diff).toBe(200)
      expect(shareBasedVsJ3.value.isConsistent).toBe(false)
    })
    scope.stop()
  })

  it('J3 payload 使用 amount 字段(降级兼容)', () => {
    const responses = createResponses([
      ['M4-M4-2-other-share-based-increase', '3000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { shareBasedVsJ3 } = useM4CrossSheet(responses)

      // 使用 amount 字段（降级兼容路径）
      eventBus.emit('j3:equity-settled' as any, { amount: 3000 })

      expect(shareBasedVsJ3.value.diff).toBe(0)
      expect(shareBasedVsJ3.value.isConsistent).toBe(true)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 2: EventBus M2→M4 linkage — 'm2:fx-diff' → fxDiffVsM2
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — EventBus M2→M4 linkage (Req 4.5)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('emit m2:fx-diff → fxDiffVsM2 computed 更新', () => {
    const responses = createResponses([
      ['M4-M4-2-premium-fx-diff-change', '1200'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { fxDiffVsM2 } = useM4CrossSheet(responses)

      // 初始: M2金额=0, M4资本溢价变动=1200 → diff=-1200
      expect(fxDiffVsM2.value.diff).toBe(-1200)
      expect(fxDiffVsM2.value.isConsistent).toBe(false)

      // 模拟 M2 发出 fx-diff 事件
      eventBus.emit('m2:fx-diff' as any, { fxDiffAmount: 1200 })

      // 更新后: M2金额=1200, M4变动=1200 → diff=0
      expect(fxDiffVsM2.value.diff).toBe(0)
      expect(fxDiffVsM2.value.isConsistent).toBe(true)
    })
    scope.stop()
  })

  it('M2外币折算差异与M4溢价变动不一致时 isConsistent=false', () => {
    const responses = createResponses([
      ['M4-M4-2-premium-fx-diff-change', '1000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { fxDiffVsM2 } = useM4CrossSheet(responses)

      eventBus.emit('m2:fx-diff' as any, { fxDiffAmount: 1500 })

      // diff = 1500 - 1000 = 500 > DIFF_THRESHOLD
      expect(fxDiffVsM2.value.diff).toBe(500)
      expect(fxDiffVsM2.value.isConsistent).toBe(false)
    })
    scope.stop()
  })

  it('M2 payload 使用 amount 字段(降级兼容)', () => {
    const responses = createResponses([
      ['M4-M4-2-premium-fx-diff-change', '800'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { fxDiffVsM2 } = useM4CrossSheet(responses)

      eventBus.emit('m2:fx-diff' as any, { amount: 800 })

      expect(fxDiffVsM2.value.diff).toBe(0)
      expect(fxDiffVsM2.value.isConsistent).toBe(true)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 3: TB writeback — writebackTB 回写 + EventBus 'substantive:adjudicated'
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — TB writeback (Req 2.6)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('writebackTB 调用正确端点 account_code=4002', async () => {
    // 直接测试 useM4FormData 的 writebackTB
    const { useM4FormData } = await import('../composables/useM4FormData')

    const scope = effectScope()
    await scope.run(async () => {
      const formData = useM4FormData({
        wpId: ref('wp-123'),
        projectId: ref('proj-456'),
      })

      await formData.writebackTB(88000)

      expect(api.put).toHaveBeenCalledWith(
        '/api/projects/proj-456/trial-balance/writeback',
        {
          account_code: '4002',
          audited_amount: 88000,
        },
      )
    })
    scope.stop()
  })

  it('writebackTB 成功后发布 substantive:adjudicated 事件', async () => {
    const { useM4FormData } = await import('../composables/useM4FormData')

    const scope = effectScope()
    await scope.run(async () => {
      const formData = useM4FormData({
        wpId: ref('wp-123'),
        projectId: ref('proj-456'),
      })

      await formData.writebackTB(120000)

      expect(eventBus.emit).toHaveBeenCalledWith(
        'substantive:adjudicated',
        expect.objectContaining({
          accountCode: '4002',
          auditedAmount: 120000,
          wpCode: 'M4',
        }),
      )
    })
    scope.stop()
  })

  it('writebackTB payload 包含 timestamp', async () => {
    const { useM4FormData } = await import('../composables/useM4FormData')

    const scope = effectScope()
    await scope.run(async () => {
      const formData = useM4FormData({
        wpId: ref('wp-123'),
        projectId: ref('proj-456'),
      })

      const before = Date.now()
      await formData.writebackTB(50000)
      const after = Date.now()

      const emitCall = (eventBus.emit as any).mock.calls.find(
        (c: any[]) => c[0] === 'substantive:adjudicated',
      )
      expect(emitCall).toBeDefined()
      expect(emitCall[1].timestamp).toBeGreaterThanOrEqual(before)
      expect(emitCall[1].timestamp).toBeLessThanOrEqual(after)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 4: Cross-sheet validation — adjudicationVsDetail 审定表 vs 明细表勾稽
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — Cross-sheet validation adjudicationVsDetail (Req 2.5)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('审定表合计 === 明细表合计 → isMatch=true, diff=0', () => {
    const responses = createResponses([
      ['M4-M4-1-total-end-audited', '15000000'],
      ['M4-M4-2-total-end-amount', '15000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useM4CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBe(0)
    })
    scope.stop()
  })

  it('差异>1元 → isMatch=false', () => {
    const responses = createResponses([
      ['M4-M4-1-total-end-audited', '15000000'],
      ['M4-M4-2-total-end-amount', '14990000'], // 差10000
    ])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useM4CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(false)
      expect(adjudicationVsDetail.value.diff).toBe(10000)
    })
    scope.stop()
  })

  it('差异<1元(容差内) → isMatch=true', () => {
    const responses = createResponses([
      ['M4-M4-1-total-end-audited', '5000000.50'],
      ['M4-M4-2-total-end-amount', '5000000.10'], // 差0.40 < 1
    ])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useM4CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(Math.abs(adjudicationVsDetail.value.diff)).toBeLessThan(1)
    })
    scope.stop()
  })

  it('明细行降级累加: 无汇总行时遍历 premium-*-end + other-*-end', () => {
    const responses = createResponses([
      ['M4-M4-1-total-end-audited', '10000000'],
      // 无 M4-M4-2-total-end-amount（汇总行为空），降级到明细行累加
      ['M4-M4-2-premium-item1-end', '4000000'],
      ['M4-M4-2-premium-item2-end', '2000000'],
      ['M4-M4-2-other-share-based-end', '3000000'],
      ['M4-M4-2-other-fx-end', '1000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useM4CrossSheet(responses)
      // 明细累加: 4000000+2000000+3000000+1000000=10000000
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBe(0)
    })
    scope.stop()
  })

  it('两侧均为空 → isMatch=true, diff=0', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useM4CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBe(0)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 5: Share-based diff threshold — shareBasedVsJ3.isConsistent 逻辑
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — Share-based diff threshold (Req 4.4)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it(`|diff| <= DIFF_THRESHOLD(${DIFF_THRESHOLD}) → isConsistent=true`, () => {
    const responses = createResponses([
      ['M4-M4-2-other-share-based-increase', '5000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { shareBasedVsJ3 } = useM4CrossSheet(responses)

      // 发送与账面完全一致的J3金额
      eventBus.emit('j3:equity-settled' as any, { equitySettledAmount: 5000 })

      expect(shareBasedVsJ3.value.diff).toBe(0)
      expect(shareBasedVsJ3.value.isConsistent).toBe(true)
    })
    scope.stop()
  })

  it(`|diff| <= DIFF_THRESHOLD(${DIFF_THRESHOLD}) 边界内 → isConsistent=true`, () => {
    const responses = createResponses([
      ['M4-M4-2-other-share-based-increase', '5000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { shareBasedVsJ3 } = useM4CrossSheet(responses)

      // 精确控制: 设 J3 = 5000.005, diff = 0.005 < DIFF_THRESHOLD(0.01)
      eventBus.emit('j3:equity-settled' as any, { equitySettledAmount: 5000.005 })

      expect(Math.abs(shareBasedVsJ3.value.diff)).toBeLessThanOrEqual(DIFF_THRESHOLD)
      expect(shareBasedVsJ3.value.isConsistent).toBe(true)
    })
    scope.stop()
  })

  it(`|diff| > DIFF_THRESHOLD → isConsistent=false（红色高亮场景）`, () => {
    const responses = createResponses([
      ['M4-M4-2-other-share-based-increase', '5000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { shareBasedVsJ3 } = useM4CrossSheet(responses)

      // diff = 5100 - 5000 = 100 >> DIFF_THRESHOLD
      eventBus.emit('j3:equity-settled' as any, { equitySettledAmount: 5100 })

      expect(shareBasedVsJ3.value.diff).toBe(100)
      expect(shareBasedVsJ3.value.isConsistent).toBe(false)
    })
    scope.stop()
  })

  it('J3金额为0(未就绪) + 账面有值 → isConsistent 由阈值决定', () => {
    const responses = createResponses([
      ['M4-M4-2-other-share-based-increase', '500'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { shareBasedVsJ3 } = useM4CrossSheet(responses)

      // 初始 J3=0，diff = 0 - 500 = -500
      expect(shareBasedVsJ3.value.diff).toBe(-500)
      expect(shareBasedVsJ3.value.isConsistent).toBe(false)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 6: EventBus cleanup — onScopeDispose 取消订阅
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — EventBus cleanup on scope dispose (Req 4.6)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('scope.stop() 后 eventBus.off 被调用', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      useM4CrossSheet(responses)
    })

    // 确认 on 被调用了两次（j3:equity-settled + m2:fx-diff）
    expect(eventBus.on).toHaveBeenCalledTimes(2)
    expect(eventBus.on).toHaveBeenCalledWith('j3:equity-settled', expect.any(Function))
    expect(eventBus.on).toHaveBeenCalledWith('m2:fx-diff', expect.any(Function))

    // 停止 scope → 触发 onScopeDispose
    scope.stop()

    // off 应该也被调用两次
    expect(eventBus.off).toHaveBeenCalledTimes(2)
    expect(eventBus.off).toHaveBeenCalledWith('j3:equity-settled', expect.any(Function))
    expect(eventBus.off).toHaveBeenCalledWith('m2:fx-diff', expect.any(Function))
  })

  it('scope.stop() 后事件不再响应', () => {
    const responses = createResponses([
      ['M4-M4-2-other-share-based-increase', '1000'],
    ])

    const scope = effectScope()
    let crossSheet: ReturnType<typeof useM4CrossSheet> | undefined
    scope.run(() => {
      crossSheet = useM4CrossSheet(responses)
    })

    // scope active 时事件触发有效
    eventBus.emit('j3:equity-settled' as any, { equitySettledAmount: 2000 })
    expect(crossSheet!.shareBasedVsJ3.value.diff).toBe(1000) // 2000-1000

    // 停止 scope（off 会从 onHandlers 移除 handler）
    scope.stop()

    // 此时再 emit 不应触发更新（handler 已移除）
    eventBus.emit('j3:equity-settled' as any, { equitySettledAmount: 9999 })

    // diff 应仍为之前的值（handler 被移除了，不会再更新）
    expect(crossSheet!.shareBasedVsJ3.value.diff).toBe(1000)
  })
})
