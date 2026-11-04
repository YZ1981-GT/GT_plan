/**
 * 报表金额格的未保存修改（审定报表 / 单体财务报表共用，spec citar-table-manual-edit R6 / R7）。
 * 键由调用方定（如「资产负债表|BS-001|current」）；草稿 null = 清空成空白；restored = 已保存的手工值点了「恢复」。
 */
import { computed, ref } from 'vue'

export function useCitarAmountDrafts() {
  const drafts = ref<Record<string, number | null>>({})
  const restored = ref<Set<string>>(new Set())

  const count = computed(() => Object.keys(drafts.value).length + restored.value.size)
  const dirty = computed(() => count.value > 0)

  function draftOf(key: string): number | null | undefined {
    return key in drafts.value ? drafts.value[key] : undefined
  }

  function isRestored(key: string): boolean {
    return restored.value.has(key)
  }

  function edit(key: string, value: number | null) {
    drafts.value = { ...drafts.value, [key]: value }
    if (restored.value.has(key)) {
      const next = new Set(restored.value)
      next.delete(key)
      restored.value = next
    }
  }

  /** 去掉草稿；``saved`` = 该格已有保存过的手工值，记进 restored，保存时提交「恢复」 */
  function restore(key: string, saved: boolean) {
    if (key in drafts.value) {
      const next = { ...drafts.value }
      delete next[key]
      drafts.value = next
    }
    if (saved) restored.value = new Set([...restored.value, key])
  }

  function clear() {
    drafts.value = {}
    restored.value = new Set()
  }

  return { drafts, restored, count, dirty, draftOf, isRestored, edit, restore, clear }
}
