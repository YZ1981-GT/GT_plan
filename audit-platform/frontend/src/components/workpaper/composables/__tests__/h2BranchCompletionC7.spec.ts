/**
 * H2 利息分支互斥 / 目录完成度 / C7 前置 — 单元测试
 */
import { describe, it, expect, vi } from 'vitest'
import { ref, nextTick } from 'vue'
import {
  resolveInterestCapBranch,
  resolveActiveInterestCapResult,
  inactiveInterestCapResultKey,
  H2_INTEREST_BRANCH_KEY,
  H2_10_CAP_RESULT_KEY,
  H2_11_CAP_RESULT_KEY,
} from '../h2InterestCapBranch'
import {
  resolveH2SheetStatus,
  summarizeH2IndexProgress,
} from '../h2IndexCompletion'
import { useH2C7Prerequisite, H2A_C7_PREREQ_KEY } from '../useH2C7Prerequisite'

function makeMap(entries: Record<string, unknown> = {}) {
  const m = new Map<string, any>()
  for (const [k, v] of Object.entries(entries)) {
    if (v && typeof v === 'object' && 'remark' in (v as any)) {
      m.set(k, { item_id: k, ...(v as any) })
    } else {
      m.set(k, {
        item_id: k,
        conclusion: null,
        remark: typeof v === 'string' ? v : JSON.stringify(v),
      })
    }
  }
  return m
}

describe('h2InterestCapBranch', () => {
  it('显式分支优先，避免 H2-10 非零结果抢占 H2-11', () => {
    const map = makeMap({
      [H2_INTEREST_BRANCH_KEY]: 'withBorrow',
      [H2_10_CAP_RESULT_KEY]: { totalCap: 999, branch: 'noBorrow' },
      [H2_11_CAP_RESULT_KEY]: { totalCap: 100, branch: 'withBorrow' },
    })
    expect(resolveInterestCapBranch(map)).toBe('withBorrow')
    expect(resolveActiveInterestCapResult(map)?.totalCap).toBe(100)
  })

  it('无显式分支时按 cap-result.branch 推断', () => {
    const map = makeMap({
      [H2_11_CAP_RESULT_KEY]: { totalCap: 50, branch: 'withBorrow' },
    })
    expect(resolveInterestCapBranch(map)).toBe('withBorrow')
    expect(resolveActiveInterestCapResult(map)?.totalCap).toBe(50)
  })

  it('inactiveInterestCapResultKey 互斥', () => {
    expect(inactiveInterestCapResultKey('noBorrow')).toBe(H2_11_CAP_RESULT_KEY)
    expect(inactiveInterestCapResultKey('withBorrow')).toBe(H2_10_CAP_RESULT_KEY)
  })
})

describe('h2IndexCompletion', () => {
  it('H2-10/11 互斥标 N/A', () => {
    const map = makeMap({ [H2_INTEREST_BRANCH_KEY]: 'noBorrow' })
    expect(resolveH2SheetStatus('H2-10', map).status).toBe('pending')
    expect(resolveH2SheetStatus('H2-11', map).status).toBe('na')
  })

  it('减值迹象<2 且无 H2-16 数据 → N/A', () => {
    const map = makeMap({
      'H2-15-impairment-signs': [
        { exists: '是' },
        { exists: '否' },
      ],
    })
    expect(resolveH2SheetStatus('H2-16', map).status).toBe('na')
  })

  it('有结论视为完成；关键表仅有数据仍 pending', () => {
    const pending = makeMap({
      'H2-1-rows': [{ name: 'A', endAudited: 1 }],
    })
    expect(resolveH2SheetStatus('H2-1', pending).status).toBe('pending')

    const done = makeMap({
      'H2-1-rows': [{ name: 'A', endAudited: 1 }],
      'H2-1-audit-conclusion': '未见异常',
    })
    expect(resolveH2SheetStatus('H2-1', done).status).toBe('completed')
  })

  it('进度分母排除 N/A', () => {
    const map = makeMap({ [H2_INTEREST_BRANCH_KEY]: 'withBorrow' })
    const codes = ['H2', 'H2-10', 'H2-11']
    const s = summarizeH2IndexProgress(codes, map)
    // H2 completed, H2-10 na, H2-11 pending → applicable=2, completed=1
    expect(s.applicable).toBe(2)
    expect(s.completed).toBe(1)
  })
})

describe('useH2C7Prerequisite', () => {
  it('applyPayload(C7) 写入前置并标记扩大程序', async () => {
    const allResponses = ref(makeMap())
    const onPersist = vi.fn((id: string, value: any, opts?: any) => {
      const next = new Map(allResponses.value)
      next.set(id, {
        item_id: id,
        conclusion: opts?.conclusion ?? null,
        remark: JSON.stringify(value),
      })
      allResponses.value = next
    })

    const { state, applyPayload } = useH2C7Prerequisite({
      allResponses: allResponses as any,
      onPersist,
      isReadonly: ref(false),
    })

    applyPayload({
      wpCode: 'C7',
      conclusion: '控制失效',
      deviationSummary: {
        totalControlPoints: 3,
        effectiveCount: 1,
        deviationAcceptableCount: 0,
        ineffectiveCount: 2,
        maxDeviationRate: 0.15,
      },
    })
    await nextTick()

    expect(onPersist).toHaveBeenCalled()
    expect(onPersist.mock.calls[0][0]).toBe(H2A_C7_PREREQ_KEY)
    expect(state.value.completed).toBe(true)
    expect(state.value.needsExtended).toBe(true)
    expect(state.value.ineffectiveCount).toBe(2)
  })

  it('applyPayload 忽略非 C7', async () => {
    const allResponses = ref(makeMap())
    const onPersist = vi.fn()
    const { applyPayload } = useH2C7Prerequisite({
      allResponses: allResponses as any,
      onPersist,
      isReadonly: ref(false),
    })
    applyPayload({ wpCode: 'C6', conclusion: '全部有效' })
    await nextTick()
    expect(onPersist).not.toHaveBeenCalled()
  })
})
