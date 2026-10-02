/**
 * nCycleCanaryRowIdentity.spec.ts — N 循环 canary（N4-1）行身份 + 双列载荷往返
 *
 * spec: n-cycle-sync-foundation-and-first-canary · Task 10 / 14 / 15 / 16
 *
 * 覆盖：
 * 1. stableRowIdentity：采纳已落库身份 / 语义键 / 熵键 / 位置化反向判据 / 按身份增删改
 * 2. checklistPayload：remark 空串 + conclusion 有载荷时**不丢**（旧 `??` 写法的缺陷）
 * 3. useN4Adjudication canary 往返：读 → 删中间行 → 写 → 再读，历史数据不串行
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'

import {
  adoptRowKey,
  duplicateRowKeys,
  findRowByKey,
  generatedRowKey,
  isPositionalRowKey,
  removeRowByKey,
  semanticRowKey,
  updateRowByKey,
} from '../shared/stableRowIdentity'
import { payloadJson, pickPayload } from '../shared/checklistPayload'
import { useN4Adjudication } from '../useN4Adjudication'

vi.mock('element-plus', () => ({
  ElMessageBox: { confirm: vi.fn(async () => 'confirm') },
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

describe('stableRowIdentity', () => {
  it('已落库身份优先，不重新生成', () => {
    expect(adoptRowKey({ rowKey: 'row-abc' }, '消费税')).toBe('row-abc')
    expect(adoptRowKey({ id: 'x-1' })).toBe('x-1')
  })

  it('缺失身份时用语义键，语义为空才退熵键', () => {
    expect(adoptRowKey({}, '消费税')).toBe('row-消费税')
    const k = adoptRowKey({}, '')
    expect(k.startsWith('row-')).toBe(true)
    expect(isPositionalRowKey(k)).toBe(false)
  })

  it('semanticRowKey 不偷偷兜底熵键', () => {
    expect(semanticRowKey('  ')).toBe('')
    expect(semanticRowKey(null)).toBe('')
  })

  it('熵键同一 tick 内不碰撞', () => {
    const keys = new Set(Array.from({ length: 200 }, () => generatedRowKey()))
    expect(keys.size).toBe(200)
  })

  it('反向判据：下标伪装成身份必须被识别', () => {
    for (const k of ['row-0', 'row-12', 'manual-3', '7']) expect(isPositionalRowKey(k)).toBe(true)
    for (const k of ['row-消费税', generatedRowKey(), 'custom-1696-ab12cd']) {
      expect(isPositionalRowKey(k)).toBe(false)
    }
  })

  it('按身份增删改，不按下标', () => {
    const rows = [{ rowKey: 'a', v: 1 }, { rowKey: 'b', v: 2 }, { rowKey: 'c', v: 3 }]
    expect(removeRowByKey(rows, 'b').map(r => r.rowKey)).toEqual(['a', 'c'])
    expect(removeRowByKey(rows, 'zz')).toHaveLength(3)
    expect(updateRowByKey(rows, 'c', r => ({ ...r, v: 9 }))[2].v).toBe(9)
    expect(findRowByKey(rows, 'a')?.v).toBe(1)
    expect(duplicateRowKeys([...rows, { rowKey: 'a', v: 0 }])).toEqual(['a'])
  })
})

describe('checklistPayload（NC-34 双列映射）', () => {
  it('remark 空串 + conclusion 有载荷 ⇒ 取 conclusion（旧 ?? 写法会丢）', () => {
    const item = { remark: '', conclusion: '[{"x":1}]' }
    // 旧写法的缺陷现形：
    expect(item.remark ?? item.conclusion).toBe('')
    expect(pickPayload('N4-1-rows', item).column).toBe('conclusion')
    expect(payloadJson('N4-1-rows', item)).toEqual([{ x: 1 }])
  })

  it('只有一列非空时不看后缀（防 N1-5-rows 后缀例外丢载荷）', () => {
    expect(pickPayload('N1-5-rows', { remark: null, conclusion: 'abc' }).column).toBe('conclusion')
  })

  it('两列都非空时按后缀裁决，无法裁决记冲突不猜', () => {
    expect(pickPayload('N4-1-rows', { remark: 'r', conclusion: 'c' }).column).toBe('remark')
    expect(pickPayload('N1-disclosure-soe-x', { remark: 'r', conclusion: 'c' }).column).toBe('conclusion')
    const p = pickPayload('N4-1-audit-note', { remark: 'r', conclusion: 'c' })
    expect(p.conflict).toBe(true)
    expect(p.text).toBe('')
  })

  it('AI 复核会话键在解析前排除', () => {
    const p = pickPayload('N2-review-session-abc', { remark: '{"messages":[]}' })
    expect(p.excluded).toBe(true)
    expect(payloadJson('N2-review-session-abc', { remark: '{"messages":[]}' })).toBeNull()
  })

  it('解析失败保留原文不覆盖', () => {
    expect(payloadJson('N4-1-rows', { remark: 'not json' })).toBe('not json')
  })
})

describe('canary N4-1 往返（Task 15 / 16）', () => {
  function makeAdj(initial: Map<string, any>) {
    const all = ref(initial)
    const saved: Record<string, any> = {}
    const adj = useN4Adjudication({
      allResponses: all as any,
      projectId: ref('proj-001'),
      wpId: ref('wp-001'),
      isReadonly: ref(false),
      onSave: (itemId: string, value: any) => { saved[itemId] = value },
      writebackTB: async () => {},
    } as any)
    return { adj, all, saved }
  }

  it('默认行身份是税种语义键，非下标', () => {
    const { adj } = makeAdj(new Map())
    const keys = adj.rows.value.map((r: any) => r.rowKey)
    expect(keys).toContain('row-消费税')
    expect(keys.some((k: string) => isPositionalRowKey(k))).toBe(false)
    expect(duplicateRowKeys(adj.rows.value)).toEqual([])
  })

  it('载荷在 conclusion 列时能读回（canary 读路径）', () => {
    const payload = [
      { rowKey: 'row-消费税', taxType: '消费税', unadjusted: 100, aje: 0, rje: 0, prior: 0, remark: '甲' },
      { rowKey: 'row-城建税', taxType: '城建税', unadjusted: 7, aje: 0, rje: 0, prior: 0, remark: '乙' },
    ]
    const { adj } = makeAdj(new Map([['N4-1-rows', { item_id: 'N4-1-rows', remark: '', conclusion: JSON.stringify(payload) }]]))
    expect(adj.rows.value.map((r: any) => r.rowKey)).toEqual(['row-消费税', 'row-城建税'])
    expect(adj.rows.value[0].unadjusted).toBe(100)
  })

  it('删中间行后写回，再读回：历史 remark 不串到相邻行', () => {
    const payload = ['消费税', '城建税', '印花税'].map((t, i) => ({
      rowKey: `row-${t}`, taxType: t, unadjusted: i + 1, aje: 0, rje: 0, prior: 0, remark: `备注-${t}`,
    }))
    const { adj, saved } = makeAdj(new Map([['N4-1-rows', { remark: JSON.stringify(payload) }]]))
    adj.removeRow('row-城建税')
    const written = saved['N4-1-rows']
    expect(written.map((r: any) => r.rowKey)).toEqual(['row-消费税', 'row-印花税'])

    const { adj: again } = makeAdj(new Map([['N4-1-rows', { remark: JSON.stringify(written) }]]))
    const yin = again.rows.value.find((r: any) => r.rowKey === 'row-印花税')
    expect(yin.remark).toBe('备注-印花税')
    expect(yin.unadjusted).toBe(3)
  })

  it('同税种新增两次不产生重复身份', () => {
    const { adj } = makeAdj(new Map())
    adj.addRow('消费税')
    adj.addRow('消费税')
    expect(duplicateRowKeys(adj.rows.value)).toEqual([])
  })
})
