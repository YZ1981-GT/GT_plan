/**
 * useNoteRefresh — 从底稿刷新 / 手动重试 / stale 重算 + 差异化提示文案
 *
 * 从 DisclosureEditor.vue 抽取，保持原有语义不变。
 * 包含组① 的「已刷新 / 需手动重填」差异化提示逻辑（Req 2.8, 2.9, 1.4）。
 */
import { ref, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { refreshDisclosureFromWorkpapers, type RefreshFromWorkpapersResult } from '@/services/commonApi'
import { handleApiError } from '@/utils/errorHandler'

export interface UseNoteRefreshOptions {
  projectId: ComputedRef<string> | Ref<string>
  year: ComputedRef<number> | Ref<number>
  currentNote: Ref<{ note_section: string } | null>
  fetchDetail: (noteSection: string) => Promise<void>
  fetchTree: () => Promise<void>
  staleRecalc: () => Promise<void>
}

export interface UseNoteRefreshReturn {
  refreshLoading: Ref<boolean>
  syncError: Ref<boolean>
  onRefreshFromWP: () => Promise<void>
  onManualRefresh: () => Promise<void>
  onStaleRecalc: () => Promise<void>
  showRefreshResultMessage: (result: RefreshFromWorkpapersResult) => void
  onWorkpaperSaved: (payload: { projectId: string }) => void
}

export function useNoteRefresh(options: UseNoteRefreshOptions): UseNoteRefreshReturn {
  const { projectId, year, currentNote, fetchDetail, fetchTree, staleRecalc } = options

  const refreshLoading = ref(false)
  const syncError = ref(false)
  let syncDebounceTimer: ReturnType<typeof setTimeout> | null = null

  /**
   * 刷新结果差异化提示（Req 2.8, 2.9, 1.4）
   * GT 紫令牌通过 customClass: 'gt-msg-purple' 实现
   */
  function showRefreshResultMessage(result: RefreshFromWorkpapersResult) {
    const cellsUpdated = result?.cells_updated ?? 0
    const textOnlySections = result?.text_only_sections ?? []
    const errors = result?.errors ?? []

    // 有错误时优先提示错误
    if (errors.length > 0) {
      ElMessage({
        type: 'warning',
        message: `刷新完成，${errors.length} 个章节取数失败：${errors.slice(0, 3).join('；')}${errors.length > 3 ? '…' : ''}`,
        duration: 5000,
        customClass: 'gt-msg-purple',
      })
      return
    }

    // 有更新的单元格
    if (cellsUpdated > 0) {
      let msg = `已刷新 ${cellsUpdated} 个单元格`
      // 存在纯文本章节需手动重填
      if (textOnlySections.length > 0) {
        const sectionNames = textOnlySections.slice(0, 5).join('、')
        const suffix = textOnlySections.length > 5 ? '等' : ''
        msg += `；以下章节需手动重填：${sectionNames}${suffix}`
      }
      ElMessage({
        type: 'success',
        message: msg,
        duration: 4000,
        customClass: 'gt-msg-purple',
      })
      return
    }

    // 无更新但有纯文本章节
    if (textOnlySections.length > 0) {
      const sectionNames = textOnlySections.slice(0, 5).join('、')
      const suffix = textOnlySections.length > 5 ? '等' : ''
      ElMessage({
        type: 'info',
        message: `数据已是最新，无需刷新；以下章节需手动重填：${sectionNames}${suffix}`,
        duration: 4000,
        customClass: 'gt-msg-purple',
      })
      return
    }

    // 全无更新也无纯文本章节
    ElMessage({
      type: 'info',
      message: '数据已是最新，无需刷新',
      duration: 3000,
      customClass: 'gt-msg-purple',
    })
  }

  async function onRefreshFromWP() {
    refreshLoading.value = true
    try {
      const result = await refreshDisclosureFromWorkpapers(projectId.value, year.value)
      showRefreshResultMessage(result)
      if (currentNote.value) await fetchDetail(currentNote.value.note_section)
    } catch (e) { handleApiError(e, '刷新附注') }
    finally { refreshLoading.value = false }
  }

  async function onManualRefresh() {
    syncError.value = false
    try {
      const result = await refreshDisclosureFromWorkpapers(projectId.value, year.value)
      if (currentNote.value) await fetchDetail(currentNote.value.note_section)
      showRefreshResultMessage(result)
    } catch (e) {
      syncError.value = true
      handleApiError(e, '刷新附注')
    }
  }

  async function onStaleRecalc() {
    await staleRecalc()
    // 重算试算表后，再触发附注从底稿刷新获取差异化提示
    try {
      const result = await refreshDisclosureFromWorkpapers(projectId.value, year.value)
      showRefreshResultMessage(result)
    } catch { /* stale recalc 已完成，附注刷新失败静默 */ }
    await fetchTree()
  }

  /** 底稿保存事件监听（自动同步附注数据） */
  function onWorkpaperSaved(payload: { projectId: string }) {
    if (payload.projectId !== projectId.value) return
    if (syncDebounceTimer) clearTimeout(syncDebounceTimer)
    syncDebounceTimer = setTimeout(async () => {
      syncError.value = false
      try {
        await refreshDisclosureFromWorkpapers(projectId.value, year.value)
        if (currentNote.value) await fetchDetail(currentNote.value.note_section)
      } catch {
        syncError.value = true
      }
    }, 1000)
  }

  return {
    refreshLoading,
    syncError,
    onRefreshFromWP,
    onManualRefresh,
    onStaleRecalc,
    showRefreshResultMessage,
    onWorkpaperSaved,
  }
}
