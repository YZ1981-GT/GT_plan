/**
 * D7-4 Top10 债务人的账龄说明：现行明细行存嵌套 agingAudited，历史数据是扁平 endAging1~4，两种都要认。
 * 原先只读扁平字段 ⇒ 现行数据的账龄说明恒为「-」。
 */
import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { useD7Analysis } from '../useD7Analysis'

function top10(rows: unknown[]) {
  const allResponses = ref(new Map<string, any>([['D7-2-rows', { item_id: 'D7-2-rows', remark: JSON.stringify(rows) }]]))
  const a = useD7Analysis({
    allResponses, saveImmediate: vi.fn(async () => {}), debouncedSave: vi.fn(), wpId: ref('wp'), projectId: ref('p'),
  })
  return a.top10Rows.value
}

describe('useD7Analysis — Top10 账龄说明', () => {
  it('现行嵌套 agingAudited', () => {
    const [r] = top10([{ companyName: '甲', endAudited: 300, priorAudited: 100, agingAudited: { within1: 200, y2to3: 100 } }])
    expect(r.aging).toBe('1年以内、2-3年')
  })

  it('历史扁平 endAging1~4 仍认', () => {
    const [r] = top10([{ companyName: '乙', endAudited: 50, priorAudited: 0, endAging1: 0, endAging4: 50 }])
    expect(r.aging).toBe('3年以上')
  })
})
