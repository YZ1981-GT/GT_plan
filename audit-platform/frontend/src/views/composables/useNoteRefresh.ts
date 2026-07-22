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
  onDisclosureNoteTextUpdated: (payload: Record<string, unknown>) => void
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

  /** 底稿披露 tab 同步/改叙述后：若当前正在看对应附注节，刷新详情（不整树重拉） */
  function onDisclosureNoteTextUpdated(payload: Record<string, unknown>) {
    if (!payload || !currentNote.value) return
    const pid = String(payload.projectId ?? payload.project_id ?? '')
    if (pid && pid !== projectId.value) return

    const current = String(currentNote.value.note_section || '')
    if (!current) return

    const sectionIds: string[] = []
    const single = payload.sectionId ?? payload.section_id
    if (typeof single === 'string' && single.trim()) sectionIds.push(single.trim())
    if (Array.isArray(payload.sectionIds)) {
      for (const id of payload.sectionIds) {
        if (typeof id === 'string' && id.trim()) sectionIds.push(id.trim())
      }
    }
    if (Array.isArray(payload.payloads)) {
      for (const item of payload.payloads as Array<Record<string, unknown>>) {
        const id = item?.noteSectionId ?? item?.section_id
        if (typeof id === 'string' && id.trim()) sectionIds.push(id.trim())
      }
    }

    const matched = sectionIds.some(id =>
      current === id || current.startsWith(id) || id.startsWith(current),
    )
    // 1511 长期股权投资：上市五、18 / 国企八、18 及合并范围「七」
    const isG7Lte = String(payload.accountCode || '') === '1511'
      && (current.includes('18') || current.startsWith('七'))
    // 2101 交易性金融负债：五、34/35 / 八、34/35
    const isG10Tfl = String(payload.accountCode || '') === '2101'
      && (current.includes('34') || current.includes('35'))
    // 6101 公允价值变动收益：三、公允价值变动收益 / 八、72
    const isG13Fvc = String(payload.accountCode || '') === '6101'
      && (
        current.includes('公允价值变动')
        || current.startsWith('三、公允')
        || current.startsWith('八、72')
        || current === '八、72'
      )
    if (!matched && !isG7Lte && !isG10Tfl && !isG13Fvc) return

    if (syncDebounceTimer) clearTimeout(syncDebounceTimer)
    syncDebounceTimer = setTimeout(async () => {
      try {
        await fetchDetail(current)
      } catch {
        /* 静默：用户可手动刷新 */
      }
    }, 400)
  }

  return {
    refreshLoading,
    syncError,
    onRefreshFromWP,
    onManualRefresh,
    onStaleRecalc,
    showRefreshResultMessage,
    onWorkpaperSaved,
    onDisclosureNoteTextUpdated,
  }
}
