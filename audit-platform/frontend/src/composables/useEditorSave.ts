/**
 * useEditorSave — 底稿编辑器保存/导出/提交 composable
 *
 * 封装 7 个 action：onSave / onSubmitForReview / onSyncStructure /
 * onRefreshPrefill / onDownload / onExportPdf / onUpload
 *
 * spec: workpaper-editor-shrink-phase2, Task 3.1
 * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6
 */
import { ref, type Ref, type ComputedRef } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api as httpApi } from '@/services/apiProxy'
import { workpapers as P_wp } from '@/services/apiPaths'
import { eventBus, type WorkpaperSavedPayload } from '@/utils/eventBus'
import { getWorkpaper, downloadWorkpaper } from '@/services/workpaperApi'
import { rebuildWorkpaperStructure } from '@/services/commonApi'
import { handleApiError } from '@/utils/errorHandler'
import { confirmSubmitReview, confirmVersionConflict } from '@/utils/confirm'
import { logger } from '@/utils/logger'
import type { WorkpaperDetail } from '@/services/workpaperApi'
import type { useStaleImpact } from './useStaleImpact'
import type { useUserOverrides } from './useUserOverrides'
import type { useWorkpaperAutoSave } from './useWorkpaperAutoSave'
import { createSaveCoordinator, type SaveAttempt } from './saveCoordinator'

type StaleImpactAPI = ReturnType<typeof useStaleImpact>
type UserOverridesAPI = ReturnType<typeof useUserOverrides>
type WorkpaperAutoSaveAPI = ReturnType<typeof useWorkpaperAutoSave>
export interface UseEditorSaveOptions {
  projectId: ComputedRef<string>
  wpId: ComputedRef<string>
  /** 只读：保存后的最新详情经 setWpDetail 交回持有者（UniverEditorCore 传的是 props 的只读 computed）。 */
  wpDetail: Readonly<Ref<WorkpaperDetail | null>>
  setWpDetail: (detail: WorkpaperDetail) => void
  univerAPI: Ref<any>
  dirty: Ref<boolean>
  userOverrides: UserOverridesAPI
  staleImpact: StaleImpactAPI
  hasPrefillMapping: Ref<boolean>
  autoSave: WorkpaperAutoSaveAPI
  initUniver?: () => Promise<void>
  loading?: Ref<boolean>
  showStaleImpactPanel?: Ref<boolean>
  /** 项目审计年度（保存后的下游影响分析按它算；没有再看底稿详情的 year，都没有不分析） */
  year?: Readonly<Ref<number | null>>
}
/**
 * 已提示过「未能分析下游影响」的 (底稿, sheet)。
 * 放模块级 = 同一会话内只提示一次，编辑器重新挂载也不重复刷屏（design §10.2 / RV9.1-02）。
 */
const notifiedUnresolved = new Set<string>()

/** 仅测试用：重置本会话的提示去重记录。 */
export function __resetUnresolvedNotices() {
  notifiedUnresolved.clear()
}

export function useEditorSave(opts: UseEditorSaveOptions) {
  const router = useRouter()
  const saving = ref(false)
  const submitting = ref(false)
  const syncLoading = ref(false)
  const prefillLoading = ref(false)
  const exportingPdf = ref(false)
  const saveCoordinator = createSaveCoordinator<string>()
  let activeSave: Promise<boolean> | null = null
  let versionDocumentKey = ''
  let nextExpectedVersion: number | null = null

  function documentKey(): string {
    return `${opts.projectId.value}:${opts.wpId.value}`
  }

  /** Univer 每条写命令都调用，不能依赖 dirty 的 false→true 边沿。 */
  function markEdited(): number {
    return saveCoordinator.markEdited(documentKey())
  }

  /** 重取详情交回持有者（🔴 原先直接写只读 computed，写入被丢弃 ⇒ 版本号停在旧值，下次保存误报版本冲突）。 */
  async function refreshDetail(): Promise<void> {
    opts.setWpDetail(await getWorkpaper(opts.projectId.value, opts.wpId.value))
  }

  function versionConflictOf(data: any): any | null {
    return [data?.detail, data?.message, data]
      .find(detail => detail?.error_code === 'VERSION_CONFLICT') ?? null
  }

  async function saveRevision(
    attempt: SaveAttempt<string>,
    saved: { data: any; workbook: any },
  ): Promise<boolean> {
    if (attempt.documentKey !== documentKey()) return false
    const api = opts.univerAPI.value
    const detail = opts.wpDetail.value
    if (!api || !detail) return false
    const workbook = api.getActiveWorkbook()
    if (!workbook) throw new Error('无法获取工作簿数据')
    const snapshot = workbook.getSnapshot()

    if (versionDocumentKey !== attempt.documentKey) {
      versionDocumentKey = attempt.documentKey
      nextExpectedVersion = null
    }
    const expectedVersion = nextExpectedVersion ?? detail.file_version
    const data = await httpApi.post(
      P_wp.univerSave(opts.projectId.value, opts.wpId.value),
      {
        snapshot,
        expected_version: expectedVersion,
        parsed_data_patch: { user_overrides: opts.userOverrides.serializeOverrides() },
      },
      { validateStatus: (status: number) => (status >= 200 && status < 300) || status === 409 },
    )

    const conflict = versionConflictOf(data)
    if (conflict) {
      try {
        await confirmVersionConflict(conflict.server_version, conflict.expected_version)
        const serverVersion = Number(conflict.server_version)
        if (Number.isFinite(serverVersion)) nextExpectedVersion = serverVersion
        if (opts.initUniver) await opts.initUniver()
      } catch { /* 取消时保留本地修改，不再绕过 CAS 强制覆盖。 */ }
      return false
    }
    if (data?.success === false) return false

    const responseVersion = Number(data?.version)
    if (Number.isFinite(responseVersion)) nextExpectedVersion = responseVersion
    else {
      const prior = Number(expectedVersion)
      if (Number.isFinite(prior)) nextExpectedVersion = prior + 1
    }
    saved.data = data
    saved.workbook = workbook
    return true
  }

  async function notifyStaleImpact(workbook: any): Promise<void> {
    try {
      const activeSheet = workbook?.getActiveSheet?.()
      const sheetName = activeSheet?.getSheetName?.() || activeSheet?.getName?.() || ''
      const impactResp = await opts.staleImpact.notify({
        sheet: sheetName,
        max_depth: 3,
        project_id: opts.projectId.value,
        year: opts.year?.value ?? opts.wpDetail.value?.year ?? null,
      })
      if (impactResp && (impactResp.total || impactResp.total_affected) > 0) {
        const total = impactResp.total || impactResp.total_affected
        ElMessage.info({ message: `已识别 ${total} 个下游影响点（点击右侧"影响范围"查看）`, duration: 4000 })
        if (opts.showStaleImpactPanel) opts.showStaleImpactPanel.value = true
      }
      const unresolved = String(opts.staleImpact.unresolvedReason?.value || '').trim()
      if (unresolved) {
        const noticeKey = `${opts.wpDetail.value?.wp_code || opts.wpId.value}|${sheetName}`
        if (!notifiedUnresolved.has(noticeKey)) {
          notifiedUnresolved.add(noticeKey)
          ElMessage.info({ message: `未能分析下游影响：${unresolved}`, duration: 5000 })
        }
      }
    } catch (error) {
      logger.warn('[stale-impact] notify failed (non-blocking):', error)
    }
  }

  async function performSave(): Promise<boolean> {
    if (!opts.univerAPI.value || !opts.wpDetail.value) return false
    const key = documentKey()
    const saved = { data: null as any, workbook: null as any }
    saving.value = true
    try {
      // 后处理期间仍允许编辑；若代际又前进，继续串行补存后再做最终清脏与提示。
      while (true) {
        const ok = await saveCoordinator.run(key, attempt => saveRevision(attempt, saved))
        if (!ok) return false
        await notifyStaleImpact(saved.workbook)
        await refreshDetail()
        if (saveCoordinator.isDirty(key)) continue

        opts.dirty.value = false
        opts.autoSave.clearDirty()
        ElMessage.success(saved.data?.message || '保存成功')
        eventBus.emit('workpaper:saved', {
          projectId: opts.projectId.value,
          wpId: opts.wpId.value,
        } as WorkpaperSavedPayload)
        return true
      }
    } catch (err: any) {
      handleApiError(err, '保存底稿')
      return false
    } finally {
      saving.value = false
    }
  }

  function onSave(): Promise<boolean> {
    if (activeSave) return activeSave
    let tracked!: Promise<boolean>
    tracked = performSave().finally(() => {
      if (activeSave === tracked) activeSave = null
    })
    activeSave = tracked
    return tracked
  }

  async function onSubmitForReview(): Promise<void> {
    if (!opts.wpDetail.value) return
    if (opts.dirty.value) {
      ElMessage.warning('请先保存当前修改')
      return
    }
    try {
      await confirmSubmitReview(opts.wpDetail.value?.wp_code || '', opts.wpDetail.value?.wp_name || '')
    } catch { return }

    submitting.value = true
    try {
      // 只能走专用提交入口：后端在此统一执行 edit_complete、SoD、QC、批注、AI 等门禁，
      // 不能再直接把状态改成 pending_review，否则会绕过 fail-closed 的复核编排。
      const result = await httpApi.post<{
        can_submit?: boolean
        blocking_reasons?: string[]
      }>(P_wp.submitReview(opts.projectId.value, opts.wpId.value))
      if (result?.can_submit === false) {
        const reason = result.blocking_reasons?.filter(Boolean).join('；')
        ElMessage.warning(reason || '当前底稿未满足提交复核条件')
        return
      }
      ElMessage.success('已提交复核，等待复核人审阅')
      await refreshDetail()
    } catch (err: any) {
      handleApiError(err, '提交复核')
    } finally {
      submitting.value = false
    }
  }

  async function onSyncStructure(): Promise<void> {
    syncLoading.value = true
    try {
      if (opts.dirty.value) {
        const saveOk = await onSave()
        if (!saveOk) return
      }
      await rebuildWorkpaperStructure(opts.projectId.value, opts.wpId.value)
      await refreshDetail()
      ElMessage.success('公式坐标已同步')
    } catch (e: any) {
      handleApiError(e, '同步')
    } finally {
      syncLoading.value = false
    }
  }

  async function onRefreshPrefill(): Promise<void> {
    if (!opts.hasPrefillMapping.value) return
    prefillLoading.value = true
    try {
      if (opts.dirty.value) {
        const saveOk = await onSave()
        if (!saveOk) return
      }
      const overrides = opts.userOverrides.serializeOverrides()
      const overrideCount = opts.userOverrides.overrideCount.value

      const result = await httpApi.post(
        `/api/projects/${opts.projectId.value}/workpapers/${opts.wpId.value}/template-file/init`,
        { user_overrides: overrides },
      )

      // 重新加载 Univer
      const currentAPI = opts.univerAPI.value
      if (currentAPI) {
        try { currentAPI.dispose?.() } catch { /* ignore */ }
        opts.univerAPI.value = null
      }
      if (opts.loading) opts.loading.value = true
      if (opts.initUniver) await opts.initUniver()

      const filledCount = result?.filled_count ?? result?.prefill_count ?? 0
      const skippedCount = overrideCount
      if (filledCount > 0 || skippedCount > 0) {
        ElMessage.success(`已刷新 ${filledCount} 个单元格，跳过 ${skippedCount} 个手动修改的单元格`)
      } else {
        ElMessage.success('取数刷新完成，已从试算表重新填入最新数据')
      }
    } catch (e: any) {
      handleApiError(e, '刷新取数')
    } finally {
      prefillLoading.value = false
    }
  }

  async function onDownload(): Promise<void> {
    try {
      await downloadWorkpaper(opts.projectId.value, opts.wpId.value)
    } catch (e: any) {
      handleApiError(e, '下载')
    }
  }

  async function onExportPdf(): Promise<void> {
    if (!opts.wpDetail.value) return
    exportingPdf.value = true
    try {
      const http = (await import('@/utils/http')).default
      const response = await http.get(
        P_wp.exportPdf(opts.projectId.value, opts.wpId.value),
        { responseType: 'blob', validateStatus: (s: number) => s < 600 },
      )
      const blob: Blob = response.data
      if (blob.type && blob.type.includes('application/json')) {
        const txt = await blob.text()
        let msg = 'PDF 导出失败'
        try { msg = JSON.parse(txt)?.detail || msg } catch { /* ignore */ }
        handleApiError({ response: { status: 500, data: { detail: msg } } }, 'PDF 导出')
        return
      }
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${opts.wpDetail.value.wp_code || 'workpaper'}_${opts.wpDetail.value.wp_name || ''}.pdf`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      URL.revokeObjectURL(url)
    } catch (err: any) {
      handleApiError(err, 'PDF 导出')
    } finally {
      exportingPdf.value = false
    }
  }

  function onUpload(): void {
    router.push({
      name: 'WorkpaperList',
      params: { projectId: opts.projectId.value },
      query: { upload: opts.wpId.value },
    })
  }

  return {
    saving,
    submitting,
    syncLoading,
    prefillLoading,
    exportingPdf,
    markEdited,
    onSave,
    onSubmitForReview,
    onSyncStructure,
    onRefreshPrefill,
    onDownload,
    onExportPdf,
    onUpload,
  }
}
