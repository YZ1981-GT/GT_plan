/**
 * P17：本期逐行 AJE/RJE 汇总 ≠ D4-4 调整分录汇总额 → 显式告警，不静默盖掉任一侧。
 *
 * spec: d4-html-to-oo-store-contract-alignment · Task 16
 * Requirements 7.1, 7.2 · Property 17
 *
 * 背景：小计本期 AJE/RJE 现改逐行汇总（与模板 C12=SUM 同口径，P16 后端已锁）。D4-4 是调整
 * 分录权威源，两者不等本身是审计师需要知道的事实——由 adjustmentTotalsValidation 告警，
 * 不由系统改任一侧。本判据用 effectScope 跑 useD4Adjudication（同 d4AdjudicationRowLinkage）。
 */
import { describe, it, expect } from 'vitest'
import { ref, effectScope, type Ref } from 'vue'
import { useD4Adjudication } from '../useD4Adjudication'
import type { ChecklistResponse } from '../useD4FormData'

function buildResponses(entries: Array<[string, unknown]>): Ref<Map<string, ChecklistResponse>> {
  const map = new Map<string, ChecklistResponse>()
  for (const [item, payload] of entries) {
    map.set(item, { item_id: item, conclusion: null, remark: JSON.stringify(payload) })
  }
  return ref(map)
}

function run(allResponses: Ref<Map<string, ChecklistResponse>>) {
  const scope = effectScope()
  const api = scope.run(() =>
    useD4Adjudication({
      wpId: ref('wp-test'),
      projectId: ref('proj-test'),
      allResponses,
      isReadonly: ref(false),
    }),
  )!
  return { api, dispose: () => scope.stop() }
}

const monthRow = (product: string, monthVal: number) => ({
  rowId: `r-${product}`,
  product,
  months: Array(12).fill(monthVal),
  auditAdjustment: 0,
  priorUnadjusted: 0,
  priorAdjustment: 0,
})

/** D4-4 调整分录行（accountName 含 6001 归主营；借-贷=amount）。 */
const d44Row = (accountName: string, category: 'AJE' | 'RJE', debit: number, credit = 0) => ({
  accountName,
  category,
  debitAmount: debit,
  creditAmount: credit,
})

describe('P17：D4-1 小计 vs D4-4 调整分录一致性告警', () => {
  it('无 D4-4 调整、无逐行调整 → 不告警（null）', () => {
    const responses = buildResponses([['D4-2-rows', [monthRow('产品A', 100)]]])
    const { api, dispose } = run(responses)
    try {
      expect(api.adjustmentTotalsValidation.value).toBeNull()
    } finally {
      dispose()
    }
  })

  it('D4-4 有主营调整但 D4-1 逐行未填 → 告警（差异可见，不静默盖掉）', () => {
    const responses = buildResponses([
      ['D4-2-rows', [monthRow('产品A', 100)]],
      // D4-4 有一笔主营 AJE 5000（借），但 D4-1 派生行/手工行都没填 AJE ⇒ 逐行汇总=0 ≠ 5000
      ['D4-4-rows', [d44Row('营业收入6001', 'AJE', 5000)]],
    ])
    const { api, dispose } = run(responses)
    try {
      const msg = api.adjustmentTotalsValidation.value
      expect(msg).not.toBeNull()
      expect(msg).toContain('D4-4')
      expect(msg).toContain('5000')
      // 关键：小计本期 AJE 仍是逐行汇总的 0（未被 D4-4 的 5000 静默盖掉）。
      const mainSub = api.sections.value.find((s) => s.sectionKey === 'main-revenue')!.subtotalRow
      expect(mainSub.currentAje).toBe(0)
    } finally {
      dispose()
    }
  })

  it('D4-4 与逐行调整一致 → 不告警', () => {
    // D4-4 主营 AJE 5000；D4-1 手工行也填 AJE 5000 ⇒ 逐行汇总 5000 == D4-4 5000。
    const responses = buildResponses([
      ['D4-2-rows', [monthRow('产品A', 100)]],
      ['D4-4-rows', [d44Row('营业收入6001', 'AJE', 5000)]],
      ['D4-1-rows', [{ rowId: 'm-manual', label: '手工调整行', source: 'manual', accountCode: '6001' }]],
      ['D4-1-m-manual-currentAje', 5000],
    ])
    // per-field 是纯文本，需单独 set（非 JSON）。
    responses.value.set('D4-1-m-manual-currentAje', {
      item_id: 'D4-1-m-manual-currentAje', conclusion: null, remark: '5000',
    })
    const { api, dispose } = run(responses)
    try {
      const mainSub = api.sections.value.find((s) => s.sectionKey === 'main-revenue')!.subtotalRow
      expect(mainSub.currentAje).toBe(5000) // 逐行汇总含手工行 5000
      expect(api.adjustmentTotalsValidation.value).toBeNull() // 与 D4-4 一致 → 不告警
    } finally {
      dispose()
    }
  })
})
