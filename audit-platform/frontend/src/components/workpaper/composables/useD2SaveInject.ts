/**
 * useD2SaveInject — D2 子 tab 通用保存注入
 *
 * 提供 saveItems 函数给子组件使用。
 * 优先使用 inject（类型安全、组件隔离），回退到 window event（兼容过渡期）。
 *
 * 注：原 writeback 旁路（d2:writeback-trial-balance → 旧 PUT /trial-balance/writeback）
 * 已随 TB 回写显式发布门改造移除（spec: tb-writeback-explicit-publish-gate Task 2）——
 * TB 回写现由审定表 publishToTb（显式二次确认 → publish-to-tb 端点）承载。
 *
 * Usage:
 *   const { saveItems } = useD2SaveInject()
 *   saveItems([{ item_id: 'D2-xxx', conclusion: null, remark: 'value' }])
 */
import { inject } from 'vue'
import { D2_SAVE_ITEMS_KEY, type D2SaveItemsFn } from './d2InjectionKeys'
import type { ChecklistResponse } from './useD2FormData'

export function useD2SaveInject() {
  const injectedSave = inject<D2SaveItemsFn | undefined>(D2_SAVE_ITEMS_KEY, undefined)

  /**
   * 保存 checklist items。
   * 优先走 inject（父组件 provide），回退到 window event（过渡兼容）。
   */
  async function saveItems(items: ChecklistResponse[]): Promise<void> {
    if (!items || items.length === 0) return
    if (injectedSave) {
      await injectedSave(items)
    } else {
      // 回退：旧 window event 模式（过渡期，逐步迁移完后可移除）
      window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items } }))
    }
  }

  return { saveItems }
}

export default useD2SaveInject
