/**
 * 集成测试 — M6 未分配利润：M6→M5/M1驱动 + 反向核对闭环
 *
 * 覆盖：
 * 1. M6→M5 联动测试: useM6CrossSheet publishes 'm6:net-profit' with correct payload
 * 2. M6→M1 联动测试: useM6CrossSheet publishes 'm6:profit-distributed' with correct payload
 * 3. M5→M6 反向核对: simulate 'm5:surplus-accrual' → surplusVsM5 updates correctly
 * 4. M1→M6 反向核对: simulate 'm1:declared-confirmed' → dividendVsM1 updates correctly
 * 5. 审定表vs明细表交叉验证: adjudicationVsDetail diff calculation
 * 6. 联动一致: 当M6=M5值时 isConsistent=true, 差异>threshold时 isConsistent=false
 * 7. 持久化恢复: CrossSheet从allResponses读取已保存的联动数据
 * 8. TB回写: useM6FormData.writebackTB(amount) calls correct API + publishes event
 *
 * Spec: .kiro/specs/m6-retained-earnings/ Task 7.2
 * Requirements: 4.1-4.7
 *
 * 科目：4104 利润分配-未分配利润（**贷方/权益类！期末=期初+贷方-借方**）
 * 核心公式链：期末=期初+本年净利润-提取盈余公积-分配股利
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, effectScope } from 'vue'
import { useM6CrossSheet, DIFF_THRESHOLD } from '../composables/useM6CrossSheet'
import { calcRetainedEnd, calcDistributable, calcLinkageDiff } from '../composables/useM6DistributionEngine'
import type { ChecklistResponse } from '../composables/useM6FormData'

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

// Mock api for backend endpoint verification
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ data: [] }),
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
// Section 1: M6→M5 联动测试 (Req 4.1)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — M6→M5 联动: publishNetProfitToM5 (Req 4.1)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('publishNetProfitToM5 发布 m6:net-profit 事件携带正确载荷', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { publishNetProfitToM5 } = useM6CrossSheet(responses)

      publishNetProfitToM5(8000000, 7500000)

      expect(eventBus.emit).toHaveBeenCalledWith(
        'm6:net-profit',
        expect.objectContaining({
          wpCode: 'M6',
          netProfit: 8000000,
          accrualBase: 7500000,
          timestamp: expect.any(Number),
        }),
      )
    })
    scope.stop()
  })

  it('publishNetProfitToM5 无accrualBase时默认等于netProfit', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { publishNetProfitToM5 } = useM6CrossSheet(responses)

      publishNetProfitToM5(5000000)

      expect(eventBus.emit).toHaveBeenCalledWith(
        'm6:net-profit',
        expect.objectContaining({
          wpCode: 'M6',
          netProfit: 5000000,
          accrualBase: 5000000,
        }),
      )
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 2: M6→M1 联动测试 (Req 4.2)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — M6→M1 联动: publishDividendToM1 (Req 4.2)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('publishDividendToM1 发布 m6:profit-distributed 事件携带正确载荷', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { publishDividendToM1 } = useM6CrossSheet(responses)

      publishDividendToM1(2000000, 1800000, 200000)

      expect(eventBus.emit).toHaveBeenCalledWith(
        'm6:profit-distributed',
        expect.objectContaining({
          wpCode: 'M6',
          dividendAmount: 2000000,
          cashDividend: 1800000,
          stockDividend: 200000,
          timestamp: expect.any(Number),
        }),
      )
    })
    scope.stop()
  })

  it('publishDividendToM1 无明细时 cashDividend=全额, stockDividend=0', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { publishDividendToM1 } = useM6CrossSheet(responses)

      publishDividendToM1(3000000)

      expect(eventBus.emit).toHaveBeenCalledWith(
        'm6:profit-distributed',
        expect.objectContaining({
          wpCode: 'M6',
          dividendAmount: 3000000,
          cashDividend: 3000000,
          stockDividend: 0,
        }),
      )
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 3: M5→M6 反向核对 (Req 4.3)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — M5→M6 反向核对: m5:surplus-accrual → surplusVsM5 (Req 4.3)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('接收 m5:surplus-accrual → _m5AccrualConfirmed 更新', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { _m5AccrualConfirmed } = useM6CrossSheet(responses)

      expect(_m5AccrualConfirmed.value).toBe(0)

      eventBus.emit('m5:surplus-accrual', {
        totalAccrual: 1500000,
      })

      expect(_m5AccrualConfirmed.value).toBe(1500000)
    })
    scope.stop()
  })

  it('接收 m5:surplus-accrual → 自动持久化到 allResponses', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      useM6CrossSheet(responses)

      eventBus.emit('m5:surplus-accrual', {
        totalAccrual: 980000,
      })

      const persisted = responses.value.get('M6-cross-m5-accrual-confirmed')
      expect(persisted).toBeDefined()
      expect(persisted!.remark).toBe('980000')
    })
    scope.stop()
  })

  it('M5 payload 降级兼容：使用 amount 字段', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { _m5AccrualConfirmed } = useM6CrossSheet(responses)

      eventBus.emit('m5:surplus-accrual', { amount: 770000 })

      expect(_m5AccrualConfirmed.value).toBe(770000)
    })
    scope.stop()
  })

  it('surplusVsM5 正确反映M6记录vs M5确认的差异', () => {
    const responses = createResponses([
      ['M6-M6-2-surplus-accrual', '1000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { surplusVsM5 } = useM6CrossSheet(responses)

      // M5尚未确认 → diff = M6值-0 = 1000000
      expect(surplusVsM5.value.diff).toBe(1000000)
      expect(surplusVsM5.value.isConsistent).toBe(false)

      // M5确认计提金额
      eventBus.emit('m5:surplus-accrual', { totalAccrual: 1000000 })

      // 现在一致
      expect(surplusVsM5.value.diff).toBe(0)
      expect(surplusVsM5.value.isConsistent).toBe(true)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 4: M1→M6 反向核对 (Req 4.4)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — M1→M6 反向核对: m1:declared-confirmed → dividendVsM1 (Req 4.4)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('接收 m1:declared-confirmed → _m1DeclaredConfirmed 更新', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { _m1DeclaredConfirmed } = useM6CrossSheet(responses)

      expect(_m1DeclaredConfirmed.value).toBe(0)

      eventBus.emit('m1:declared-confirmed', {
        declaredAmount: 2000000,
      })

      expect(_m1DeclaredConfirmed.value).toBe(2000000)
    })
    scope.stop()
  })

  it('接收 m1:declared-confirmed → 自动持久化到 allResponses', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      useM6CrossSheet(responses)

      eventBus.emit('m1:declared-confirmed', {
        declaredAmount: 3500000,
      })

      const persisted = responses.value.get('M6-cross-m1-declared-confirmed')
      expect(persisted).toBeDefined()
      expect(persisted!.remark).toBe('3500000')
    })
    scope.stop()
  })

  it('M1 payload 降级兼容：使用 amount 字段', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { _m1DeclaredConfirmed } = useM6CrossSheet(responses)

      eventBus.emit('m1:declared-confirmed', { amount: 1200000 })

      expect(_m1DeclaredConfirmed.value).toBe(1200000)
    })
    scope.stop()
  })

  it('dividendVsM1 正确反映M6记录vs M1确认的差异', () => {
    const responses = createResponses([
      ['M6-M6-2-dividend', '2500000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { dividendVsM1 } = useM6CrossSheet(responses)

      // M1尚未确认 → diff = 2500000-0
      expect(dividendVsM1.value.diff).toBe(2500000)
      expect(dividendVsM1.value.isConsistent).toBe(false)

      // M1确认宣告金额
      eventBus.emit('m1:declared-confirmed', { declaredAmount: 2500000 })

      // 一致
      expect(dividendVsM1.value.diff).toBe(0)
      expect(dividendVsM1.value.isConsistent).toBe(true)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 5: 审定表vs明细表交叉验证 (Req 2.5)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — adjudicationVsDetail 审定表M6-1 vs 明细表M6-2 (Req 2.5)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('审定表期末 === 明细表期末 → isMatch=true, diff=0', () => {
    const responses = createResponses([
      ['M6-M6-1-end-audited', '15000000'],
      ['M6-M6-2-retained-end', '15000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useM6CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBe(0)
    })
    scope.stop()
  })

  it('审定表期末与明细表期末差异>1元 → isMatch=false', () => {
    const responses = createResponses([
      ['M6-M6-1-end-audited', '15000000'],
      ['M6-M6-2-retained-end', '14500000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useM6CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(false)
      expect(adjudicationVsDetail.value.diff).toBe(500000)
    })
    scope.stop()
  })

  it('两侧均为空(未填写) → isMatch=true, diff=0', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { adjudicationVsDetail } = useM6CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBe(0)
    })
    scope.stop()
  })

  it('diff计算使用calcLinkageDiff纯函数', () => {
    // 验证差异计算逻辑与DistributionEngine一致
    const adjEnd = 12000000
    const detailEnd = 11800000
    const diff = calcLinkageDiff(adjEnd, detailEnd)
    expect(diff).toBe(200000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 6: 联动一致性 (Req 4.5-4.6)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 联动一致性: isConsistent判断逻辑 (Req 4.5-4.6)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('M6盈余公积 === M5计提(差异<=DIFF_THRESHOLD) → isConsistent=true', () => {
    const responses = createResponses([
      ['M6-M6-2-surplus-accrual', '1500000'],
      ['M6-cross-m5-accrual-confirmed', '1500000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { surplusVsM5 } = useM6CrossSheet(responses)
      expect(surplusVsM5.value.isConsistent).toBe(true)
      expect(surplusVsM5.value.diff).toBe(0)
    })
    scope.stop()
  })

  it('M6盈余公积 !== M5计提(差异>DIFF_THRESHOLD) → isConsistent=false', () => {
    const responses = createResponses([
      ['M6-M6-2-surplus-accrual', '1500000'],
      ['M6-cross-m5-accrual-confirmed', '1400000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { surplusVsM5 } = useM6CrossSheet(responses)
      expect(surplusVsM5.value.isConsistent).toBe(false)
      expect(surplusVsM5.value.diff).toBe(100000)
    })
    scope.stop()
  })

  it('M6股利 === M1宣告(差异<=DIFF_THRESHOLD) → isConsistent=true', () => {
    const responses = createResponses([
      ['M6-M6-2-dividend', '2000000'],
      ['M6-cross-m1-declared-confirmed', '2000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { dividendVsM1 } = useM6CrossSheet(responses)
      expect(dividendVsM1.value.isConsistent).toBe(true)
      expect(dividendVsM1.value.diff).toBe(0)
    })
    scope.stop()
  })

  it('M6股利 !== M1宣告(差异>DIFF_THRESHOLD) → isConsistent=false', () => {
    const responses = createResponses([
      ['M6-M6-2-dividend', '2000000'],
      ['M6-cross-m1-declared-confirmed', '1800000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { dividendVsM1 } = useM6CrossSheet(responses)
      expect(dividendVsM1.value.isConsistent).toBe(false)
      expect(dividendVsM1.value.diff).toBe(200000)
    })
    scope.stop()
  })

  it('利润分配结转公式链闭环：分配额之和影响期末一致性', () => {
    // 验证分配额作用于结转引擎的一致性
    const begin = 10000000
    const netProfit = 5000000
    const surplusAccrual = 500000
    const dividend = 2000000

    const retained = calcRetainedEnd(begin, netProfit, surplusAccrual, dividend)
    const distributable = calcDistributable(begin, netProfit)

    // P7: calcRetainedEnd === calcDistributable - sa - d
    expect(retained).toBe(distributable - surplusAccrual - dividend)
    expect(retained).toBe(12500000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 7: 持久化恢复 (Req 4.7)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 持久化恢复: CrossSheet从allResponses恢复联动数据 (Req 4.7)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('从allResponses恢复M5计提确认值', () => {
    const responses = createResponses([
      ['M6-cross-m5-accrual-confirmed', '980000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { _m5AccrualConfirmed } = useM6CrossSheet(responses)
      expect(_m5AccrualConfirmed.value).toBe(980000)
    })
    scope.stop()
  })

  it('从allResponses恢复M1宣告确认值', () => {
    const responses = createResponses([
      ['M6-cross-m1-declared-confirmed', '2500000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { _m1DeclaredConfirmed } = useM6CrossSheet(responses)
      expect(_m1DeclaredConfirmed.value).toBe(2500000)
    })
    scope.stop()
  })

  it('恢复后surplusVsM5正确计算（无需再次EventBus）', () => {
    const responses = createResponses([
      ['M6-M6-2-surplus-accrual', '1500000'],
      ['M6-cross-m5-accrual-confirmed', '1500000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { surplusVsM5 } = useM6CrossSheet(responses)
      // 直接从持久化恢复，无需EventBus事件
      expect(surplusVsM5.value.isConsistent).toBe(true)
      expect(surplusVsM5.value.diff).toBe(0)
    })
    scope.stop()
  })

  it('恢复后dividendVsM1正确计算（无需再次EventBus）', () => {
    const responses = createResponses([
      ['M6-M6-2-dividend', '2000000'],
      ['M6-cross-m1-declared-confirmed', '2000000'],
    ])

    const scope = effectScope()
    scope.run(() => {
      const { dividendVsM1 } = useM6CrossSheet(responses)
      expect(dividendVsM1.value.isConsistent).toBe(true)
      expect(dividendVsM1.value.diff).toBe(0)
    })
    scope.stop()
  })

  it('allResponses无持久化数据时默认值为0', () => {
    const responses = createResponses([])

    const scope = effectScope()
    scope.run(() => {
      const { _m5AccrualConfirmed, _m1DeclaredConfirmed } = useM6CrossSheet(responses)
      expect(_m5AccrualConfirmed.value).toBe(0)
      expect(_m1DeclaredConfirmed.value).toBe(0)
    })
    scope.stop()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 8: TB回写 (Req 2.6)
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — TB回写: useM6FormData.writebackTB (Req 2.6)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    onHandlers.clear()
  })

  it('writebackTB 调用正确的API端点+科目4104', async () => {
    // 直接测试 writebackTB 的 API 调用逻辑
    const { useM6FormData } = await import('../composables/useM6FormData')

    const scope = effectScope()
    await scope.run(async () => {
      const formData = useM6FormData({
        wpId: ref('wp-123'),
        projectId: ref('proj-456'),
      })

      await formData.writebackTB(15000000)

      expect(api.put).toHaveBeenCalledWith(
        '/api/projects/proj-456/trial-balance/writeback',
        {
          account_code: '4104',
          audited_amount: 15000000,
        },
      )
    })
    scope.stop()
  })

  it('writebackTB 成功后发布 substantive:adjudicated 事件', async () => {
    const { useM6FormData } = await import('../composables/useM6FormData')

    const scope = effectScope()
    await scope.run(async () => {
      const formData = useM6FormData({
        wpId: ref('wp-789'),
        projectId: ref('proj-101'),
      })

      await formData.writebackTB(8500000)

      expect(eventBus.emit).toHaveBeenCalledWith(
        'substantive:adjudicated',
        expect.objectContaining({
          accountCode: '4104',
          auditedAmount: 8500000,
          wpCode: 'M6',
          timestamp: expect.any(Number),
        }),
      )
    })
    scope.stop()
  })

  it('writebackTB projectId为空时不发起请求', async () => {
    const { useM6FormData } = await import('../composables/useM6FormData')

    const scope = effectScope()
    await scope.run(async () => {
      const formData = useM6FormData({
        wpId: ref('wp-123'),
        projectId: ref(''),
      })

      await formData.writebackTB(5000000)

      expect(api.put).not.toHaveBeenCalled()
    })
    scope.stop()
  })
})
