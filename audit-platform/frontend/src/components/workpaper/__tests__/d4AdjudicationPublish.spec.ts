/**
 * useD4Adjudication.publishAdjudicated — 人工 TB 发布：差异阈值二次确认 + 幂等 + 显式触发
 *
 * Spec: d4-1-adjudication-bidirectional-writeback-and-formula-io Task 4.2 / Req 4.2, 5.1
 * （亦为 d4-dual-mode-formula-governance C3 「TB/A13 显式发布边界」的运行判据面）
 *
 * 覆盖：
 * - 差异 ≤ 阈值 → published，广播 substantive:adjudicated + 两笔 d4:writeback-trial-balance
 * - 差异 > 阈值 → needs_confirm（不回写），confirmed:true 后才 published
 * - 同值重复发布 → skipped_idempotent（不重复回写）
 * - 无 projectId → no_project
 * - 值变化后再发布 → 再次 published（幂等签名随值更新）
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { ref, effectScope } from 'vue'

import { useD4Adjudication } from '../composables/useD4Adjudication'
import { D4_MAIN_REVENUE_STANDARD, D4_OTHER_REVENUE_STANDARD } from '../composables/d4AccountScope'

type Resp = { item_id: string; conclusion: string | null; remark: string }

function seedResponses(opts: {
  mainAudited: number
  otherAudited: number
  tb6001: number
  tb6051: number
}): Map<string, Resp> {
  const m = new Map<string, Resp>()
  const set = (id: string, remark: string) =>
    m.set(id, { item_id: id, conclusion: null, remark })
  // 两行：一主营(6001族) 一其他(6051族)，用 currentUnadjusted 承载审定额（AJE/RJE=0 → 审定=未审）
  set(
    'D4-1-rows',
    JSON.stringify([
      { rowId: 'r-main', label: '批发', source: 'manual', accountCode: '600101', sectionKey: 'main-revenue' },
      { rowId: 'r-other', label: '废料', source: 'manual', accountCode: '605101', sectionKey: 'other-revenue' },
    ]),
  )
  set('D4-1-r-main-currentUnadjusted', String(opts.mainAudited))
  set('D4-1-r-other-currentUnadjusted', String(opts.otherAudited))
  // TB 核对行
  set('D4-1-adj-tb-6001', String(opts.tb6001))
  set('D4-1-adj-tb-6051', String(opts.tb6051))
  return m
}

function makeAdj(responses: Map<string, Resp>, projectId = 'proj-1') {
  return useD4Adjudication({
    wpId: ref('wp-1'),
    projectId: ref(projectId),
    allResponses: ref(responses) as any,
    isReadonly: ref(false),
    adjudicationPrefill: ref(null),
  })
}

describe('useD4Adjudication.publishAdjudicated — 人工 TB 发布', () => {
  let events: { type: string; detail: any }[]
  let listener: (e: Event) => void

  beforeEach(() => {
    events = []
    listener = (e: Event) => events.push({ type: e.type, detail: (e as CustomEvent).detail })
    window.addEventListener('substantive:adjudicated', listener)
    window.addEventListener('d4:writeback-trial-balance', listener)
  })
  afterEach(() => {
    window.removeEventListener('substantive:adjudicated', listener)
    window.removeEventListener('d4:writeback-trial-balance', listener)
    vi.restoreAllMocks()
  })

  it('差异≤阈值 → published，广播 adjudicated + 两笔 writeback', () => {
    const scope = effectScope()
    scope.run(() => {
      // 审定合计 = 1000 + 500 = 1500；TB = 1000 + 500 = 1500 → 差异 0
      const adj = makeAdj(seedResponses({ mainAudited: 1000, otherAudited: 500, tb6001: 1000, tb6051: 500 }))
      const r = adj.publishAdjudicated()
      expect(r.verdict).toBe('published')
      expect(r.mainAudited).toBe(1000)
      expect(r.otherAudited).toBe(500)

      const adjudicated = events.filter((e) => e.type === 'substantive:adjudicated')
      const writebacks = events.filter((e) => e.type === 'd4:writeback-trial-balance')
      expect(adjudicated).toHaveLength(1)
      expect(writebacks).toHaveLength(2)
      const codes = writebacks.map((w) => w.detail.accountCode).sort()
      expect(codes).toEqual([D4_MAIN_REVENUE_STANDARD, D4_OTHER_REVENUE_STANDARD].sort())
    })
    scope.stop()
  })

  it('差异>阈值 → needs_confirm（不回写）；confirmed:true 后才 published', () => {
    const scope = effectScope()
    scope.run(() => {
      // 审定合计 1500；TB 1000 → 差异 500 > 阈值 1
      const adj = makeAdj(seedResponses({ mainAudited: 1000, otherAudited: 500, tb6001: 700, tb6051: 300 }))
      const first = adj.publishAdjudicated()
      expect(first.verdict).toBe('needs_confirm')
      expect(Math.abs(first.difference)).toBeGreaterThan(1)
      // 未确认 → 没有任何回写事件
      expect(events).toHaveLength(0)

      const confirmed = adj.publishAdjudicated({ confirmed: true })
      expect(confirmed.verdict).toBe('published')
      expect(events.filter((e) => e.type === 'd4:writeback-trial-balance')).toHaveLength(2)
    })
    scope.stop()
  })

  it('同值重复发布 → skipped_idempotent（不重复回写）', () => {
    const scope = effectScope()
    scope.run(() => {
      const adj = makeAdj(seedResponses({ mainAudited: 1000, otherAudited: 500, tb6001: 1000, tb6051: 500 }))
      expect(adj.publishAdjudicated().verdict).toBe('published')
      const afterFirst = events.length
      // 再点一次，值没变
      const second = adj.publishAdjudicated()
      expect(second.verdict).toBe('skipped_idempotent')
      expect(events.length).toBe(afterFirst) // 无新事件
    })
    scope.stop()
  })

  it('无 projectId → no_project（不回写）', () => {
    const scope = effectScope()
    scope.run(() => {
      const adj = makeAdj(
        seedResponses({ mainAudited: 1000, otherAudited: 500, tb6001: 1000, tb6051: 500 }),
        '', // 空 projectId
      )
      expect(adj.publishAdjudicated().verdict).toBe('no_project')
      expect(events).toHaveLength(0)
    })
    scope.stop()
  })

  it('反向自检：值变化后再发布 → 再次 published（幂等签名随值更新，非恒 skip）', () => {
    const scope = effectScope()
    scope.run(() => {
      // 用外层 ref 承载 allResponses，模拟宿主保存后「重建整个 Map」触发 watch → initRows
      const responses = ref(seedResponses({ mainAudited: 1000, otherAudited: 500, tb6001: 1000, tb6051: 500 }))
      const adj = useD4Adjudication({
        wpId: ref('wp-1'),
        projectId: ref('proj-1'),
        allResponses: responses as any,
        isReadonly: ref(false),
        adjudicationPrefill: ref(null),
      })
      expect(adj.publishAdjudicated().verdict).toBe('published')
      // 改审定额（主营 1000 → 1200），TB 同步保持差异≤阈值；重建 Map 触发响应式
      responses.value = seedResponses({ mainAudited: 1200, otherAudited: 500, tb6001: 1200, tb6051: 500 })
      const r2 = adj.publishAdjudicated()
      expect(r2.verdict).toBe('published') // 值变了 → 不该被幂等吞掉
      expect(r2.mainAudited).toBe(1200)
    })
    scope.stop()
  })
})
