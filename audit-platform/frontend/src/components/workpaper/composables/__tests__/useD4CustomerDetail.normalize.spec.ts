/**
 * D4-29 客户信息检查表 fields 归一守卫（本会话 D4 双向回写前端修复）。
 *
 * 🔴 根因（真栈 chrome-devtools console 实证）：后端 store 里一条客户行可能只有 {id,name}
 *    而无 fields 子对象（合法半成品，与后端 phase5_d4_ipo_interview_sheets「缺 fields 段 → None」
 *    容差同源）。此前 loadData 直接 `customers.value = p`，模板 `activeCustomer.fields[field.key]` /
 *    矩阵 `cust.fields[row.key]` / relatedCount / completionRate 访问 `c.fields[...]` 时 fields 为
 *    undefined → `Cannot read properties of undefined` 打挂整个组件渲染（ErrorBoundary 捕获 →
 *    子组件不挂载 → 在线编辑切换器不可达）。修复 = loadData 用 normalizeCustomers 归一 fields 为对象。
 *
 * 本守卫钉住行为：载入缺 fields 的客户行 → fields 归一为 {} + 派生计算不抛。
 * 变异反证：把 loadData 改回 `customers.value = p`（不归一）本测试即打红（fields undefined）。
 */
import { describe, it, expect } from 'vitest'
import { effectScope, ref, nextTick } from 'vue'
import { useD4CustomerDetail } from '../useD4CustomerDetail'

function makeResponses(remark: string) {
  const m = new Map<string, any>()
  m.set('D4-29-customers', { item_id: 'D4-29-customers', conclusion: null, remark })
  return ref(m)
}

describe('useD4CustomerDetail fields 归一（缺 fields 段容差）', () => {
  it('缺 fields 的客户行载入后 fields 归一为对象，不抛', async () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = makeResponses(
        JSON.stringify([
          { id: 'c-1', name: '客户甲' },                 // 缺 fields（半成品）
          { id: 'c-2', name: '客户乙', fields: { isRelated: '是' } },
        ]),
      )
      const api = useD4CustomerDetail({
        wpId: ref('wp'), projectId: ref('p'), allResponses, isReadonly: ref(false),
      })
      // 两行都进 + 缺 fields 的那行归一为 {}
      expect(api.customers.value).toHaveLength(2)
      expect(api.customers.value[0].fields).toEqual({})
      expect(api.customers.value[1].fields.isRelated).toBe('是')
      // 派生计算访问 c.fields[...] 不抛（此前 fields undefined 会崩）
      expect(() => api.relatedCount.value).not.toThrow()
      expect(api.relatedCount.value).toBe(1)
      expect(() => api.completionRate.value).not.toThrow()
    })
    scope.stop()
    await nextTick()
  })

  it('非数组 / 脏 JSON → 空列表，不抛', () => {
    const scope = effectScope()
    scope.run(() => {
      const allResponses = makeResponses('not-json{{{')
      const api = useD4CustomerDetail({
        wpId: ref('wp'), projectId: ref('p'), allResponses, isReadonly: ref(false),
      })
      expect(api.customers.value).toEqual([])
    })
    scope.stop()
  })
})
