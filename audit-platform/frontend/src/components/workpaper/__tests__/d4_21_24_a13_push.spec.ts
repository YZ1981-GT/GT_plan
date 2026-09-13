/**
 * D4-24 / D4-21 → A13 错报推送锁定（Wave 5 T5.2，Req 5.2）
 *
 * 锁定：A13 推送**只**经共享件 useD4InspectionWriteback（唯一消费者
 * useA13MisstatementBridge 落 unadjusted_misstatements），科目固定 6001/营业收入，
 * 不复制判据、不接错底稿。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const emitted: Array<{ event: string; payload: any }> = []
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: (event: string, payload: any) => { emitted.push({ event, payload }) },
    on: vi.fn(),
    off: vi.fn(),
  },
}))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

import { useD4InspectionWriteback } from '../composables/useD4InspectionWriteback'

function makeResponses() {
  return ref(new Map<string, any>())
}

describe('D4-24/D4-21 → A13 推送锁 6001/营业收入（共享件）', () => {
  beforeEach(() => { emitted.length = 0 })

  it('D4-24 第三方回款异常项 → 默认锁 accountCode=6001 / 营业收入', () => {
    const { pushToA13 } = useD4InspectionWriteback({ wpCode: 'D4-24', allResponses: makeResponses() })
    // 不显式传科目 → 走共享件默认锁 6001/营业收入
    const fired = pushToA13([
      { amount: 50000, description: '第三方回款无代付协议', indexRef: 'D4-24-3' },
    ])
    expect(fired).toBe(true)
    expect(emitted).toHaveLength(1)
    expect(emitted[0].event).toBe('a13:push-misstatement')
    expect(emitted[0].payload.wpCode).toBe('D4-24')       // 防接错底稿
    expect(emitted[0].payload.accountCode).toBe('6001')   // 锁营业收入
    expect(emitted[0].payload.accountName).toBe('营业收入')
    expect(emitted[0].payload.source).toBe('D4-24')
    expect(emitted[0].payload.items[0].amount).toBe(50000)
  })

  it('D4-21 关联方价格异常项 → 同样锁 6001（复用共享件，不另造判据）', () => {
    const { pushToA13 } = useD4InspectionWriteback({ wpCode: 'D4-21', allResponses: makeResponses() })
    const fired = pushToA13([
      { amount: 12000, description: '关联方销售价格显著低于非关联方（差异率>20%）', indexRef: 'D4-21-2' },
    ])
    expect(fired).toBe(true)
    expect(emitted[0].payload.wpCode).toBe('D4-21')
    expect(emitted[0].payload.accountCode).toBe('6001')
    expect(emitted[0].payload.accountName).toBe('营业收入')
  })

  it('无异常项 → 不 emit（错报汇总不接空推送）', () => {
    const { pushToA13 } = useD4InspectionWriteback({ wpCode: 'D4-24', allResponses: makeResponses() })
    expect(pushToA13([])).toBe(false)
    expect(emitted).toHaveLength(0)
  })
})
