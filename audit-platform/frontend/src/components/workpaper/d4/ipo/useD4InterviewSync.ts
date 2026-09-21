import { inject, onBeforeUnmount, ref } from 'vue'

type SaveItem = { item_id: string; conclusion: string | null; remark: string | null }

export function useD4InterviewSave(getItems: () => SaveItem[]) {
  const saveItems = inject<((items: SaveItem[]) => Promise<void>) | null>('d4SaveItems', null)
  const saveError = ref('')
  let timer: ReturnType<typeof setTimeout> | null = null
  let pending: Promise<void> = Promise.resolve()
  function flush(): Promise<void> {
    if (timer) clearTimeout(timer)
    timer = null
    const items = getItems().map(item => ({ ...item }))
    pending = pending.catch(() => undefined).then(async () => {
      if (!saveItems) throw new Error('D4 保存宿主未注入，无法确认结构化数据已保存')
      await saveItems(items)
      saveError.value = ''
    })
    return pending
  }
  function backgroundSave() {
    void flush().catch(error => { saveError.value = String(error?.message || error) })
  }
  function schedule() {
    if (timer) clearTimeout(timer)
    timer = setTimeout(backgroundSave, 2000)
  }
  onBeforeUnmount(() => { if (timer) backgroundSave() })
  return { flush, schedule, saveError }
}

// `useD4InterviewMode`（旧的组件级 mode composable，不建桥/不管健康）已随 D4-30/31/32
// 迁移至 `../composables/useD4SyncMode` 而移除（2026-09-21 治本迁移收尾）。
