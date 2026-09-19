/**
 * useG0DiffNonSecurities — 三维差异计算 + 旧数据 hydrate + round-trip
 *   Property 4  三维计算规则（金额/比例带符号相减；条款不相减）
 *   Property 7  旧 diff-reconcile-v1 → 投资金额维 hydrate 不丢
 */
import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import {
  recalcRow,
  rowHasDiff,
  hydrateFromReconcile,
  useG0DiffNonSecurities,
} from '../useG0DiffNonSecurities'

describe('Property 4 — 三维差异计算规则', () => {
  it('金额差异 = 账面 − 回函（符号固定）', () => {
    const r = recalcRow({ booked_amount: 100, reply_amount: 90 })
    expect(r.amount_diff).toBe(10)
    const r2 = recalcRow({ booked_amount: 90, reply_amount: 100 })
    expect(r2.amount_diff).toBe(-10)
  })

  it('比例差异 = 账面 − 回函（百分点）', () => {
    const r = recalcRow({ booked_ratio: 30, reply_ratio: 25 })
    expect(r.ratio_diff).toBe(5)
  })

  it('条款维不做数值相减（recalcRow 不产生 term 数值差异）', () => {
    const r = recalcRow({ booked_term: '不得转让', reply_term: '可转让', term_match: '不一致' })
    expect((r as any).term_diff).toBeUndefined()
    expect(r.term_match).toBe('不一致')
  })

  it('fast-check: amount_diff/ratio_diff 恒等于账面−回函（两位精度）', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e6, max: 1e6, noNaN: true }),
        fc.double({ min: -1e6, max: 1e6, noNaN: true }),
        fc.double({ min: -100, max: 100, noNaN: true }),
        fc.double({ min: -100, max: 100, noNaN: true }),
        (ba, ra, br, rr) => {
          const r = recalcRow({ booked_amount: ba, reply_amount: ra, booked_ratio: br, reply_ratio: rr })
          expect(r.amount_diff).toBe(Math.round((ba - ra) * 100) / 100)
          expect(r.ratio_diff).toBe(Math.round((br - rr) * 100) / 100)
        },
      ),
      { numRuns: 40 },
    )
  })

  it('rowHasDiff：比例/金额差 或 条款不一致 → 有差异', () => {
    expect(rowHasDiff(recalcRow({ booked_amount: 100, reply_amount: 100 }))).toBe(false)
    expect(rowHasDiff(recalcRow({ booked_amount: 100, reply_amount: 90 }))).toBe(true)
    expect(rowHasDiff(recalcRow({ booked_ratio: 30, reply_ratio: 25 }))).toBe(true)
    expect(rowHasDiff(recalcRow({ term_match: '不一致' }))).toBe(true)
    expect(rowHasDiff(recalcRow({ term_match: '一致' }))).toBe(false)
  })
})

describe('Property 7 — 旧 diff-reconcile-v1 → 非证券投资金额维 hydrate', () => {
  const legacy = {
    _format: 'diff-reconcile-v1',
    rows: [
      { confirm_index: 'G0-201', entity_name: 'B公司', sent_amount: 500, reply_amount: 480, diff_note: '权益变动', needs_adjustment: true },
      { confirm_index: 'G0-202', entity_name: 'C公司', sent_amount: 300, reply_amount: 300 },
    ],
  }

  it('sent→booked_amount / reply→reply_amount / 差异到 amount_diff（不丢）', () => {
    const rows = hydrateFromReconcile(legacy)
    expect(rows.length).toBe(2)
    expect(rows[0].booked_amount).toBe(500)
    expect(rows[0].reply_amount).toBe(480)
    expect(rows[0].amount_diff).toBe(20)
    expect(rows[0].confirm_index).toBe('G0-201')
    expect(rows[0].need_adjust).toBe('是')
    expect(rows[0]._source).toBe('hydrated-from-reconcile')
    // 比例/条款维为空
    expect(rows[0].booked_ratio).toBeUndefined()
    expect(rows[0].booked_term).toBeUndefined()
  })

  it('非 diff-reconcile-v1 返回空数组', () => {
    expect(hydrateFromReconcile({ _format: 'diff-nonsecurities-v1', rows: [] })).toEqual([])
    expect(hydrateFromReconcile(null)).toEqual([])
  })

  it('composable initFromHtmlData 遇 diff-reconcile-v1 自动 hydrate', () => {
    const data = useG0DiffNonSecurities({ htmlData: () => legacy, readonly: false })
    expect(data.rows.value.length).toBe(2)
    expect(data.rows.value[0].booked_amount).toBe(500)
  })
})

describe('round-trip — diff-nonsecurities-v1 读→存→读不丢', () => {
  it('buildPayload 保留手工录入字段', () => {
    const payload = {
      _format: 'diff-nonsecurities-v1',
      rows: [
        {
          _row_id: 'x1', seq: 1, confirm_index: 'G0-301', entity_name: 'D公司',
          booked_ratio: 51, reply_ratio: 51, booked_amount: 1000, reply_amount: 950,
          booked_term: 'a', reply_term: 'b', term_match: '不一致', term_diff_note: '条款差',
          diff_reason: '协议条款理解差异', support_evidence: '协议', need_adjust: '待定', remark: 'r',
        },
      ],
      conclusion: '结论X',
      audit_note: '说明Y',
    }
    const data = useG0DiffNonSecurities({ htmlData: () => payload, readonly: false })
    const out = data.buildPayload()
    expect(out._format).toBe('diff-nonsecurities-v1')
    expect(out.rows[0].confirm_index).toBe('G0-301')
    expect(out.rows[0].term_match).toBe('不一致')
    expect(out.rows[0].term_diff_note).toBe('条款差')
    expect(out.rows[0].amount_diff).toBe(50)
    expect(out.rows[0].ratio_diff).toBe(0)
    expect(out.conclusion).toBe('结论X')
    expect(out.audit_note).toBe('说明Y')
  })
})
