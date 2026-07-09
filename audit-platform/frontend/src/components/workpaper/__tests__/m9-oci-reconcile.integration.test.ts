/**
 * 集成测试 — M9 其他综合收益：G8/J2→M9 OCI核对
 *
 * 覆盖：
 * 1. EventBus G8 event → 更新 g8FairValueAmount in CrossSheet
 * 2. EventBus J2 event → 更新 j2RemeasuredAmount in CrossSheet
 * 3. ociVsG8 computed 在G8事件后返回正确差异
 * 4. ociVsJ2 computed 在J2事件后返回正确差异
 * 5. adjudicationVsDetail 计算M9-1与M9-2合计差异
 *
 * Spec: .kiro/specs/m9-other-comprehensive-income/ Task 7.2
 * Requirements: 4.1-4.8
 *
 * 科目：4103 其他综合收益（**贷方/权益类！期末=期初+贷方-借方**）
 * OCI核对是M9底稿的核心功能，验证OCI完整性与准确性。
 * 来源：G8其他权益工具投资公允价值变动（不可重分类）+ J2设定受益计划重计量（不可重分类）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, effectScope } from 'vue'
import { useM9CrossSheet } from '../composables/useM9CrossSheet'
import type { ChecklistResponse } from '../composables/useM9FormData'
import { calcReconcileDiff, calcAfterTaxNet, aggregateOci } from '../composables/useM9OciEngine'
import { calcSubtotal } from '../composables/useM9FormulaEngine'

// ─── Mock EventBus ───────────────────────────────────────────────────────────
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

import { eventBus } from '@/utils/eventBus'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function createResponses(entries: [string, string | null][]) {
  const map = new Map<string, ChecklistResponse>()
  for (const [itemId, remark] of entries) {
    map.set(itemId, { item_id: itemId, conclusion: null, remark })
  }
  return ref(map)
}


// ═══════════════════════════════════════════════════════════════════════════════
// Section 1: EventBus G8 event → 更新 g8FairValueAmount (Req 4.2, 4.8)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — EventBus g8:fair-value-changed → M9 CrossSheet (Req 4.2)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('G8发布公允变动事件 → _g8FairValueAmount 更新为afterTaxAmount', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { _g8FairValueAmount } = useM9CrossSheet(responses)

      // 初始为0
      expect(_g8FairValueAmount.value).toBe(0)

      // G8发布公允价值变动事件
      eventBus.emit('g8:fair-value-changed' as any, {
        wpCode: 'G8',
        afterTaxAmount: 750000,
        preTaxAmount: 1000000,
        taxEffect: 250000,
        timestamp: Date.now(),
      })

      // 更新
      expect(_g8FairValueAmount.value).toBe(750000)
    })
    scope.stop()
  })

  it('G8 payload降级兼容：amount字段', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { _g8FairValueAmount } = useM9CrossSheet(responses)

      eventBus.emit('g8:fair-value-changed' as any, {
        amount: 500000,
      })

      expect(_g8FairValueAmount.value).toBe(500000)
    })
    scope.stop()
  })

  it('G8 payload降级兼容：fairValueChange字段', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { _g8FairValueAmount } = useM9CrossSheet(responses)

      eventBus.emit('g8:fair-value-changed' as any, {
        fairValueChange: 320000,
      })

      expect(_g8FairValueAmount.value).toBe(320000)
    })
    scope.stop()
  })

  it('G8事件接收后持久化到 allResponses（防刷新丢失）', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      useM9CrossSheet(responses)

      eventBus.emit('g8:fair-value-changed' as any, {
        afterTaxAmount: 1200000,
      })

      // 持久化到 allResponses
      const persisted = responses.value.get('M9-cross-g8-fair-value-amount')
      expect(persisted).toBeDefined()
      expect(persisted!.remark).toBe('1200000')
    })
    scope.stop()
  })

  it('从allResponses恢复已持久化的G8金额', () => {
    const responses = createResponses([
      ['M9-cross-g8-fair-value-amount', '880000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { _g8FairValueAmount } = useM9CrossSheet(responses)

      // 应从 allResponses 恢复
      expect(_g8FairValueAmount.value).toBe(880000)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 2: EventBus J2 event → 更新 j2RemeasuredAmount (Req 4.3, 4.8)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — EventBus j2:remeasured → M9 CrossSheet (Req 4.3)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('J2发布重计量事件 → _j2RemeasuredAmount 更新为afterTaxAmount', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { _j2RemeasuredAmount } = useM9CrossSheet(responses)

      // 初始为0
      expect(_j2RemeasuredAmount.value).toBe(0)

      // J2发布重计量事件
      eventBus.emit('j2:remeasured' as any, {
        wpCode: 'J2',
        afterTaxAmount: 450000,
        preTaxAmount: 600000,
        taxEffect: 150000,
        timestamp: Date.now(),
      })

      // 更新
      expect(_j2RemeasuredAmount.value).toBe(450000)
    })
    scope.stop()
  })

  it('J2 payload降级兼容：amount字段', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { _j2RemeasuredAmount } = useM9CrossSheet(responses)

      eventBus.emit('j2:remeasured' as any, {
        amount: 300000,
      })

      expect(_j2RemeasuredAmount.value).toBe(300000)
    })
    scope.stop()
  })

  it('J2 payload降级兼容：remeasuredAmount字段', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { _j2RemeasuredAmount } = useM9CrossSheet(responses)

      eventBus.emit('j2:remeasured' as any, {
        remeasuredAmount: 220000,
      })

      expect(_j2RemeasuredAmount.value).toBe(220000)
    })
    scope.stop()
  })

  it('J2事件接收后持久化到 allResponses', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      useM9CrossSheet(responses)

      eventBus.emit('j2:remeasured' as any, {
        afterTaxAmount: 680000,
      })

      const persisted = responses.value.get('M9-cross-j2-remeasured-amount')
      expect(persisted).toBeDefined()
      expect(persisted!.remark).toBe('680000')
    })
    scope.stop()
  })

  it('从allResponses恢复已持久化的J2金额', () => {
    const responses = createResponses([
      ['M9-cross-j2-remeasured-amount', '560000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { _j2RemeasuredAmount } = useM9CrossSheet(responses)

      expect(_j2RemeasuredAmount.value).toBe(560000)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 3: ociVsG8 computed — G8事件后核对差异 (Req 4.2, 4.5)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — ociVsG8 核对差异 (Req 4.2, 4.5)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('G8来源=账面OCI → isConsistent=true, diff=0', () => {
    const responses = createResponses([
      ['M9-cross-g8-fair-value-amount', '750000'],
      ['M9-M9-4-g8-booked-oci', '750000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { ociVsG8 } = useM9CrossSheet(responses)
      expect(ociVsG8.value.isConsistent).toBe(true)
      expect(ociVsG8.value.diff).toBe(0)
    })
    scope.stop()
  })

  it('G8来源>账面OCI → diff>0（OCI可能漏记）', () => {
    const responses = createResponses([
      ['M9-cross-g8-fair-value-amount', '1000000'],
      ['M9-M9-4-g8-booked-oci', '800000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { ociVsG8 } = useM9CrossSheet(responses)
      expect(ociVsG8.value.isConsistent).toBe(false)
      expect(ociVsG8.value.diff).toBe(200000)
    })
    scope.stop()
  })

  it('G8事件实时更新后 ociVsG8 重新计算', () => {
    const responses = createResponses([
      ['M9-M9-4-g8-booked-oci', '500000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { ociVsG8, _g8FairValueAmount } = useM9CrossSheet(responses)

      // 初始：G8未就绪，来源=0
      expect(ociVsG8.value.diff).toBe(-500000)
      expect(ociVsG8.value.isConsistent).toBe(false)

      // G8发布事件
      eventBus.emit('g8:fair-value-changed' as any, { afterTaxAmount: 500000 })

      // 更新后核对一致
      expect(_g8FairValueAmount.value).toBe(500000)
      expect(ociVsG8.value.diff).toBe(0)
      expect(ociVsG8.value.isConsistent).toBe(true)
    })
    scope.stop()
  })

  it('差异在OCI_DIFF_THRESHOLD(0.01)内 → isConsistent=true', () => {
    const responses = createResponses([
      ['M9-cross-g8-fair-value-amount', '1000000.005'],
      ['M9-M9-4-g8-booked-oci', '1000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { ociVsG8 } = useM9CrossSheet(responses)
      expect(ociVsG8.value.isConsistent).toBe(true)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 4: ociVsJ2 computed — J2事件后核对差异 (Req 4.3, 4.5)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — ociVsJ2 核对差异 (Req 4.3, 4.5)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('J2来源=账面OCI → isConsistent=true, diff=0', () => {
    const responses = createResponses([
      ['M9-cross-j2-remeasured-amount', '450000'],
      ['M9-M9-4-j2-booked-oci', '450000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { ociVsJ2 } = useM9CrossSheet(responses)
      expect(ociVsJ2.value.isConsistent).toBe(true)
      expect(ociVsJ2.value.diff).toBe(0)
    })
    scope.stop()
  })

  it('J2来源<账面OCI → diff<0（OCI可能多记）', () => {
    const responses = createResponses([
      ['M9-cross-j2-remeasured-amount', '300000'],
      ['M9-M9-4-j2-booked-oci', '450000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { ociVsJ2 } = useM9CrossSheet(responses)
      expect(ociVsJ2.value.isConsistent).toBe(false)
      expect(ociVsJ2.value.diff).toBe(-150000)
    })
    scope.stop()
  })

  it('J2事件实时更新后 ociVsJ2 重新计算', () => {
    const responses = createResponses([
      ['M9-M9-4-j2-booked-oci', '600000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { ociVsJ2, _j2RemeasuredAmount } = useM9CrossSheet(responses)

      // 初始：J2未就绪
      expect(ociVsJ2.value.diff).toBe(-600000)

      // J2发布事件
      eventBus.emit('j2:remeasured' as any, { afterTaxAmount: 600000 })

      expect(_j2RemeasuredAmount.value).toBe(600000)
      expect(ociVsJ2.value.diff).toBe(0)
      expect(ociVsJ2.value.isConsistent).toBe(true)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 5: adjudicationVsDetail — M9-1审定 vs M9-2明细 (Req 2.5)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — adjudicationVsDetail M9-1 vs M9-2 (Req 2.5)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('审定表合计 === 明细表合计 → isMatch=true, diff=0', () => {
    const responses = createResponses([
      ['M9-M9-1-total-end-audited', '5000000'],
      ['M9-M9-2-total-end-amount', '5000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useM9CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBe(0)
    })
    scope.stop()
  })

  it('审定表合计 > 明细表合计 → isMatch=false, diff>0', () => {
    const responses = createResponses([
      ['M9-M9-1-total-end-audited', '5000000'],
      ['M9-M9-2-total-end-amount', '4800000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useM9CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(false)
      expect(adjudicationVsDetail.value.diff).toBe(200000)
    })
    scope.stop()
  })

  it('明细行降级累加：无汇总行时遍历row-*-end', () => {
    const responses = createResponses([
      ['M9-M9-1-total-end-audited', '3000000'],
      // 无 M9-M9-2-total-end-amount 汇总行
      ['M9-M9-2-row-1-end', '1200000'],
      ['M9-M9-2-row-2-end', '800000'],
      ['M9-M9-2-row-3-end', '1000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useM9CrossSheet(responses)
      // 明细行累加：1200000+800000+1000000=3000000
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBe(0)
    })
    scope.stop()
  })

  it('差额在MATCH_THRESHOLD(1元)内 → isMatch=true', () => {
    const responses = createResponses([
      ['M9-M9-1-total-end-audited', '5000000.5'],
      ['M9-M9-2-total-end-amount', '5000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useM9CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
    })
    scope.stop()
  })

  it('两侧均为空 → isMatch=true, diff=0', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useM9CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBe(0)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 6: E2E — G8+J2事件→核对→审定勾稽 完整闭环 (Req 4.1-4.8)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — E2E: G8+J2→OCI核对→审定勾稽闭环 (Req 4.1-4.8)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('完整业务流程：G8公允变动+J2重计量→OCI核对→审定vs明细', () => {
    // 初始：M9-1审定表有期末合计，M9-2明细有合计，M9-4有账面OCI
    const responses = createResponses([
      ['M9-M9-1-total-end-audited', '2000000'],
      ['M9-M9-2-total-end-amount', '2000000'],
      ['M9-M9-4-g8-booked-oci', '750000'],
      ['M9-M9-4-j2-booked-oci', '450000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const crossSheet = useM9CrossSheet(responses)

      // Step 1: 审定 vs 明细一致
      expect(crossSheet.adjudicationVsDetail.value.isMatch).toBe(true)

      // Step 2: G8发布公允价值变动事件
      eventBus.emit('g8:fair-value-changed' as any, {
        wpCode: 'G8',
        afterTaxAmount: 750000,
        timestamp: Date.now(),
      })
      expect(crossSheet._g8FairValueAmount.value).toBe(750000)
      expect(crossSheet.ociVsG8.value.isConsistent).toBe(true)
      expect(crossSheet.ociVsG8.value.diff).toBe(0)

      // Step 3: J2发布重计量事件
      eventBus.emit('j2:remeasured' as any, {
        wpCode: 'J2',
        afterTaxAmount: 450000,
        timestamp: Date.now(),
      })
      expect(crossSheet._j2RemeasuredAmount.value).toBe(450000)
      expect(crossSheet.ociVsJ2.value.isConsistent).toBe(true)
      expect(crossSheet.ociVsJ2.value.diff).toBe(0)

      // Step 4: 两项持久化已保存
      expect(responses.value.get('M9-cross-g8-fair-value-amount')!.remark).toBe('750000')
      expect(responses.value.get('M9-cross-j2-remeasured-amount')!.remark).toBe('450000')
    })
    scope.stop()
  })

  it('cross_wp_references 包含G8和J2引用', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { crossWpReferences } = useM9CrossSheet(responses)

      expect(crossWpReferences.length).toBeGreaterThanOrEqual(2)

      const fromG8 = crossWpReferences.find(r => r.targetWpCode === 'G8')
      expect(fromG8).toBeDefined()
      expect(fromG8!.direction).toBe('from')
      expect(fromG8!.label).toContain('G8')

      const fromJ2 = crossWpReferences.find(r => r.targetWpCode === 'J2')
      expect(fromJ2).toBeDefined()
      expect(fromJ2!.direction).toBe('from')
      expect(fromJ2!.label).toContain('J2')
    })
    scope.stop()
  })

  it('OCI纯函数验证：calcReconcileDiff+calcAfterTaxNet+aggregateOci联动', () => {
    // G8 公允变动 税前100万、税额25万 → 税后75万
    const g8AfterTax = calcAfterTaxNet(1000000, 250000)
    expect(g8AfterTax).toBe(750000)

    // J2 重计量 税前60万、税额15万 → 税后45万
    const j2AfterTax = calcAfterTaxNet(600000, 150000)
    expect(j2AfterTax).toBe(450000)

    // 其他债权投资 税前40万、税额10万 → 税后30万
    const debtFvAfterTax = calcAfterTaxNet(400000, 100000)
    expect(debtFvAfterTax).toBe(300000)

    // OCI汇总
    const result = aggregateOci([
      { amount: g8AfterTax, category: 'nonReclass' },
      { amount: j2AfterTax, category: 'nonReclass' },
      { amount: debtFvAfterTax, category: 'reclass' },
    ])
    expect(result.nonReclass).toBe(1200000) // 75万+45万
    expect(result.reclass).toBe(300000)      // 30万
    expect(result.total).toBe(1500000)       // 120万+30万
    expect(result.total).toBe(result.nonReclass + result.reclass)

    // 核对差异：来源=75万，账面=75万 → 差异0
    expect(calcReconcileDiff(750000, 750000)).toBe(0)
    // 核对差异：来源=75万，账面=70万 → 差异5万
    expect(calcReconcileDiff(750000, 700000)).toBe(50000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 7: EventBus cleanup — scope dispose (Req 4.2-4.3)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — EventBus cleanup on scope dispose', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('scope.stop() 后 eventBus.off 被调用', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      useM9CrossSheet(responses)
    })

    expect(eventBus.on).toHaveBeenCalledWith('g8:fair-value-changed', expect.any(Function))
    expect(eventBus.on).toHaveBeenCalledWith('j2:remeasured', expect.any(Function))

    scope.stop()

    expect(eventBus.off).toHaveBeenCalledWith('g8:fair-value-changed', expect.any(Function))
    expect(eventBus.off).toHaveBeenCalledWith('j2:remeasured', expect.any(Function))
  })

  it('scope.stop() 后事件不再触发更新', () => {
    const responses = createResponses([])

    const scope = effectScope()
    let crossSheet: ReturnType<typeof useM9CrossSheet> | undefined
    scope.run(() => {
      crossSheet = useM9CrossSheet(responses)
    })

    // scope active 时事件有效
    eventBus.emit('g8:fair-value-changed' as any, { afterTaxAmount: 500000 })
    expect(crossSheet!._g8FairValueAmount.value).toBe(500000)

    // 停止 scope
    scope.stop()

    // 再次 emit 不应更新
    eventBus.emit('g8:fair-value-changed' as any, { afterTaxAmount: 9999999 })
    expect(crossSheet!._g8FairValueAmount.value).toBe(500000) // 值不变
  })
})
