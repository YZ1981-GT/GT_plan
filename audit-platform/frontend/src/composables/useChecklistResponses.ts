/**
 * useChecklistResponses — 核对表响应填写 + 自动保存（spec workpaper-frontend-large-component-split, Req 2）
 *
 * 从 GtChecklistTable.vue 抽出：
 * - responses / pendingChanges / saving state
 * - getResponse / updateConclusion / updateRemark / updateWpRef
 * - 自动保存：scheduleSave / doSave（debounce 2s 不变）/ handleManualSave / handleReset
 * - hasDirtyData computed（保存/恢复按钮启用判定）
 * - flushBeacon（onBeforeUnmount 用 sendBeacon 可靠发送，行为不变）
 *
 * 铁律：行为零变更、保响应式（ref/computed）；不在 composable 内 emit（保存成功由主组件 emit，
 *       经 onSaved 回调通知）；依赖单向（主组件 → composable → api）；composable 之间不互相 import
 *       （sectionApplicability 由主组件持有并传入，reinit 为主组件 initFromProps）。
 */
import { ref, computed, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import type { ResponseData, ChecklistHtmlData } from '@/components/workpaper/checklistTypes'

export function useChecklistResponses(options: {
  /** 当前底稿 wpId 取值（getter，保持响应式） */
  wpId: () => string
  /** 项目 ID */
  projectId: Ref<string>
  /** htmlData 取值（getter，保持响应式） */
  htmlData: () => ChecklistHtmlData | undefined
  /** readonly 取值（getter，保持响应式） */
  readonly: () => boolean
  /** 章节适用性 state（主组件持有，由 useChecklistApplicability 提供） */
  sectionApplicability: Ref<Record<string, boolean>>
  /** 保存成功回调（主组件 emit('save')） */
  onSaved: () => void
  /** 恢复到初始数据（主组件 initFromProps） */
  reinit: () => void
}) {
  const { projectId, sectionApplicability, onSaved, reinit } = options

  // ─── State ───
  const responses = ref<Record<string, ResponseData>>({})
  const saving = ref(false)
  const saveTimer = ref<ReturnType<typeof setTimeout> | null>(null)
  const pendingChanges = ref<Set<string>>(new Set())

  // ─── Methods: Response handling ───
  function getResponse(itemId: string): ResponseData {
    if (!responses.value[itemId]) {
      responses.value[itemId] = { conclusion: null, remark: null, wp_ref: null }
    }
    return responses.value[itemId]
  }

  function updateConclusion(itemId: string, value: string | null) {
    if (options.readonly()) return
    const resp = getResponse(itemId)
    resp.conclusion = value || null
    pendingChanges.value.add(itemId)
    scheduleSave()
  }

  function updateRemark(itemId: string, value: string) {
    if (options.readonly()) return
    const resp = getResponse(itemId)
    resp.remark = value || null
    pendingChanges.value.add(itemId)
    scheduleSave()
  }

  function updateWpRef(itemId: string, value: string) {
    if (options.readonly()) return
    const resp = getResponse(itemId)
    resp.wp_ref = value || null
    pendingChanges.value.add(itemId)
    scheduleSave()
  }

  // ─── Methods: Autosave (debounce 2s) ───
  function scheduleSave() {
    if (saveTimer.value) {
      clearTimeout(saveTimer.value)
    }
    saveTimer.value = setTimeout(() => {
      doSave()
    }, 2000)
  }

  async function doSave() {
    if (pendingChanges.value.size === 0) return
    if (!projectId.value) {
      console.warn('[GtChecklistTable] projectId 为空，跳过保存')
      return
    }
    saving.value = true
    const items: Array<{ item_id: string; conclusion: string | null; remark: string | null; wp_ref: string | null }> = []

    for (const itemId of pendingChanges.value) {
      const resp = responses.value[itemId]
      if (resp) {
        items.push({
          item_id: itemId,
          conclusion: resp.conclusion,
          remark: resp.remark,
          wp_ref: resp.wp_ref,
        })
      }
    }

    // Also include section applicability changes
    for (const [sectionId, applicable] of Object.entries(sectionApplicability.value)) {
      const tocItemId = `TOC-${sectionId}`
      items.push({
        item_id: tocItemId,
        conclusion: applicable ? 'Y' : 'N',
        remark: null,
        wp_ref: null,
      })
    }

    if (items.length === 0) {
      pendingChanges.value.clear()
      saving.value = false
      return
    }

    try {
      await api.put(`/api/workpapers/${options.wpId()}/checklist-responses`, {
        project_id: projectId.value,
        items,
      })
      pendingChanges.value.clear()
      onSaved()
    } catch (err: any) {
      // 忽略因页面导航导致的请求取消
      const msg = err?.message || ''
      if (msg === 'canceled' || err?.code === 'ERR_CANCELED') return
      ElMessage.error('保存失败: ' + msg)
    } finally {
      saving.value = false
    }
  }

  // ─── Computed: dirty state (for save/reset buttons) ───
  const hasDirtyData = computed(() => {
    // 当前响应数据与初始数据不同则 dirty
    const initial = options.htmlData()?.responses || {}
    for (const [key, resp] of Object.entries(responses.value)) {
      if (key.startsWith('TOC-')) continue
      const orig = initial[key]
      if (!orig && resp.conclusion) return true
      if (orig && orig.conclusion !== resp.conclusion) return true
      if (orig && orig.remark !== resp.remark) return true
      if (orig && orig.wp_ref !== resp.wp_ref) return true
    }
    return pendingChanges.value.size > 0
  })

  // ─── Methods: Manual save / reset ───
  async function handleManualSave() {
    if (saveTimer.value) {
      clearTimeout(saveTimer.value)
      saveTimer.value = null
    }
    // 把所有有值的条目都加入 pending（全量保存）
    for (const [key, resp] of Object.entries(responses.value)) {
      if (resp.conclusion || resp.remark || resp.wp_ref) {
        pendingChanges.value.add(key)
      }
    }
    await doSave()
    ElMessage.success('保存成功')
  }

  function handleReset() {
    // 恢复到 props 中的初始数据
    if (saveTimer.value) {
      clearTimeout(saveTimer.value)
      saveTimer.value = null
    }
    pendingChanges.value.clear()
    reinit()
    ElMessage.info('已恢复到上次保存的状态')
  }

  // ─── Lifecycle helpers ───
  function clearSaveTimer() {
    if (saveTimer.value) {
      clearTimeout(saveTimer.value)
      saveTimer.value = null
    }
  }

  /** onBeforeUnmount：离开页面时用 sendBeacon 可靠发送未保存的更改 */
  function flushBeacon() {
    clearSaveTimer()
    const hasRealChanges = [...pendingChanges.value].some(id => !id.startsWith('TOC-'))
    if (hasRealChanges) {
      const items: Array<{ item_id: string; conclusion: string | null; remark: string | null; wp_ref: string | null }> = []
      for (const itemId of pendingChanges.value) {
        const resp = responses.value[itemId]
        if (resp) {
          items.push({ item_id: itemId, conclusion: resp.conclusion, remark: resp.remark, wp_ref: resp.wp_ref })
        }
      }
      for (const [sectionId, applicable] of Object.entries(sectionApplicability.value)) {
        items.push({ item_id: `TOC-${sectionId}`, conclusion: applicable ? 'Y' : 'N', remark: null, wp_ref: null })
      }
      if (items.length > 0 && projectId.value) {
        const payload = JSON.stringify({ project_id: projectId.value, items })
        const url = `/api/workpapers/${options.wpId()}/checklist-responses`
        // sendBeacon 可靠发送（页面卸载后请求仍能完成，不会被 cancel）
        if (navigator.sendBeacon) {
          navigator.sendBeacon(url, new Blob([payload], { type: 'application/json' }))
        }
      }
    }
  }

  return {
    // state
    responses,
    saving,
    pendingChanges,
    // computed
    hasDirtyData,
    // methods
    getResponse,
    updateConclusion,
    updateRemark,
    updateWpRef,
    scheduleSave,
    doSave,
    handleManualSave,
    handleReset,
    clearSaveTimer,
    flushBeacon,
  }
}
