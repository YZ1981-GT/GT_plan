import { computed, inject, onBeforeUnmount, ref } from 'vue'
import { WP_BRIDGE_IN_FLIGHT_STATES, type WorkpaperSyncBridge } from '../../sync/useWorkpaperSyncBridge'

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

export function useD4InterviewMode(bridge: WorkpaperSyncBridge, readonly: () => boolean, views: string[]) {
  const htmlView = ref(views[0])
  const switching = ref(false)
  const switchError = ref('')
  const busy = computed(() => switching.value || (WP_BRIDGE_IN_FLIGHT_STATES as readonly string[]).includes(bridge.state.value))
  async function switchMode(target: string) {
    if (busy.value) return
    switchError.value = ''
    switching.value = true
    try {
      if (target === '在线编辑') {
        if (readonly() || bridge.mode.value === 'oo') return
        await bridge.switchToOnlyOffice()
      } else if (views.includes(target)) {
        htmlView.value = target
        if (bridge.mode.value === 'oo') {
          if (bridge.state.value === 'applied') await bridge.reloadAfterApplied()
          else await bridge.switchToHtml()
        }
      }
    } catch (error) {
      switchError.value = String((error as Error)?.message || error)
    } finally { switching.value = false }
  }
  const editorMode = computed({
    get: () => bridge.mode.value === 'oo' ? '在线编辑' : htmlView.value,
    set: (target: string) => { void switchMode(target) },
  })
  const modeOptions = computed(() => [...views, '在线编辑'].map(value => ({ label: value, value, disabled: busy.value || (value === '在线编辑' && readonly()) })))
  const feedback = computed(() => switchError.value || bridge.feedback.value.message)
  return { editorMode, modeOptions, busy, feedback }
}
