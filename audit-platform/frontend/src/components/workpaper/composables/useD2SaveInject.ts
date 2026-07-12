/**
 * useD2SaveInject — D2 子 tab 通用保存注入
 *
 * 提供 saveItems / writeback 两个函数给子组件使用。
 * 优先使用 inject（类型安全、组件隔离），回退到 window event（兼容过渡期）。
 *
 * Usage:
 *   const { saveItems, writeback } = useD2SaveInject()
 *   saveItems([{ item_id: 'D2-xxx', conclusion: null, remark: 'value' }])
 */
import { inject } from 'vue'
import { D2_SAVE_ITEMS_KEY, D2_WRITEBACK_KEY, type D2SaveItemsFn, type D2WritebackFn } from './d2InjectionKeys'
import type { ChecklistResponse } from './useD2FormData'

export function useD2SaveInject() {
  const injectedSave = inject<D2SaveItemsFn | undefined>(D2_SAVE_ITEMS_KEY, undefined)
  const injectedWriteback = inject<D2WritebackFn | undefined>(D2_WRITEBACK_KEY, undefined)

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

  /**
   * 回写审定数到 trial_balance。
   * 优先走 inject，回退到 window event。
   */
  function writeback(accountCode: string, auditedAmount: number): void {
    if (injectedWriteback) {
      injectedWriteback(accountCode, auditedAmount)
    } else {
      window.dispatchEvent(new CustomEvent('d2:writeback-trial-balance', {
        detail: { accountCode, auditedAmount },
      }))
    }
  }

  return { saveItems, writeback }
}

export default useD2SaveInject
