/**
 * useEditorActions — 底稿编辑器业务操作（保存/提交复核/同步公式/刷新取数/下载/导出PDF/上传）
 *
 * 锚定 spec workpaper-editor-refactor Phase 2-3（useHybridFlow 设计文档对应）
 *
 * 把 WorkpaperEditor 中 ~220 行业务操作函数集中到此 composable。
 * 主组件只需 `const actions = useEditorActions(...)` 即可访问所有操作。
 */
import { ref, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { api as httpApi } from '@/services/apiProxy'
import { workpapers as P_wp } from '@/services/apiPaths'
import { eventBus, type WorkpaperSavedPayload } from '@/utils/eventBus'
import { getWorkpaper, downloadWorkpaper } from '@/services/workpaperApi'
import { rebuildWorkpaperStructure } from '@/services/commonApi'
import { handleApiError } from '@/utils/errorHandler'
import { confirmSubmitReview, confirmVersionConflict } from '@/utils/confirm'
import type { useStaleImpact } from './useStaleImpact'
import type { useUserOverrides } from './useUserOverrides'
import type { useWorkpaperAutoSave } from './useWorkpaperAutoSave'

export interface EditorActionsOptions {
  projectId: Ref<string>
  wpId: Ref<string>
  wpDetail: Ref<any>
  dirty: Ref<boolean>
  loading: Ref<boolean>
  univerAPI: () => any  // getter since it's a let variable
  univerInstance: () => any
  loadedFromXlsx: () => boolean
  fileOpenedAt: () => number
  hasPrefillMapping: ComputedRef<boolean>
  autoSave: ReturnType<typeof useWorkpaperAutoSave>
  userOverrides: ReturnType<typeof useUserOverrides>
  staleImpact: ReturnType<typeof useStaleImpact>
  showStaleImpactPanel: Ref<boolean>
  initUniver: () => Promise<void>
  setUniverInstance: (inst: any, api: any) => void
}

export function useEditorActions(opts: EditorActionsOptions) {
  const saving = ref(false)
  const submitting = ref(false)
  const syncLoading = ref(false)
  const prefillLoading = ref(false)
  const exportingPdf = ref(false)

  async function onSave(): Promise<boolean> {
    const univerAPI = opts.univerAPI()
    if (!univerAPI || !opts.wpDetail.value) return false
    saving.value = true
    try {
      const workbook = univerAPI.getActiveWorkbook()
      if (!workbook) throw new Error('无法获取工作簿数据')

      const snapshot = workbook.getSnapshot()

      // xlsx 回写
      if (opts.loadedFromXlsx()) {
        try {
          let xlsxBlob: Blob | null = null
          if (typeof univerAPI.exportXLSXBySnapshotAsync === 'function') {
            xlsxBlob = await univerAPI.exportXLSXBySnapshotAsync(snapshot)
          } else if (typeof univerAPI.exportWorkbookToXLSX === 'function') {
            xlsxBlob = await univerAPI.exportWorkbookToXLSX()
          }
          if (xlsxBlob && xlsxBlob.size > 0) {
            const formData = new FormData()
            formData.append('file', xlsxBlob, `${opts.wpId.value}.xlsx`)
            await fetch(
              `/api/projects/${opts.projectId.value}/workpapers/${opts.wpId.value}/template-file/upload-xlsx`,
              {
                method: 'POST',
                headers: {
                  Authorization: `Bearer ${localStorage.getItem('token') || ''}`,
                  'X-File-Opened-At': String(opts.fileOpenedAt()),
                },
                body: formData,
              },
            )
          }
        } catch (e) {
          console.warn('xlsx export failed (non-blocking):', e)
        }
      }

      // 调用完整保存 API
      const data = await httpApi.post(
        P_wp.univerSave(opts.projectId.value, opts.wpId.value),
        {
          snapshot,
          expected_version: opts.wpDetail.value.file_version,
          parsed_data_patch: { user_overrides: opts.userOverrides.serializeOverrides() },
        },
        { validateStatus: (s: number) => s < 600 },
      )

      // 版本冲突处理
      if (data?.detail?.error_code === 'VERSION_CONFLICT' || data?.error_code === 'VERSION_CONFLICT') {
        const detail = data.detail || data
        try {
          await confirmVersionConflict(detail.server_version, detail.expected_version)
          await opts.initUniver()
          return false
        } catch (action) {
          if (action === 'cancel') {
            const retryData = await httpApi.post(
              P_wp.univerSave(opts.projectId.value, opts.wpId.value),
              { snapshot },
            )
            opts.dirty.value = false
            opts.autoSave.clearDirty()
            ElMessage.success(retryData?.message || '已强制覆盖保存')
            eventBus.emit('workpaper:saved', { projectId: opts.projectId.value, wpId: opts.wpId.value } as WorkpaperSavedPayload)
            opts.wpDetail.value = await getWorkpaper(opts.projectId.value, opts.wpId.value)
            return true
          }
          return false
        }
      }

      opts.dirty.value = false
      opts.autoSave.clearDirty()
      ElMessage.success(data?.message || '保存成功')
      eventBus.emit('workpaper:saved', { projectId: opts.projectId.value, wpId: opts.wpId.value } as WorkpaperSavedPayload)

      // Stale impact 通知
      try {
        const activeSheet = workbook.getActiveSheet?.()
        const sheetName = activeSheet?.getSheetName?.() || activeSheet?.getName?.() || ''
        const impactResp = await opts.staleImpact.notify({
          sheet: sheetName,
          max_depth: 3,
          project_id: opts.projectId.value,
          year: opts.wpDetail.value?.year || new Date().getFullYear(),
        })
        if (impactResp && (impactResp.total || impactResp.total_affected) > 0) {
          const total = impactResp.total || impactResp.total_affected
          ElMessage.info({ message: `已识别 ${total} 个下游影响点（点击右侧"影响范围"查看）`, duration: 4000 })
          opts.showStaleImpactPanel.value = true
        }
      } catch (e) {
        console.warn('[stale-impact] notify failed (non-blocking):', e)
      }

      opts.wpDetail.value = await getWorkpaper(opts.projectId.value, opts.wpId.value)
      return true
    } catch (err: any) {
      handleApiError(err, '保存底稿')
      return false
    } finally {
      saving.value = false
    }
  }

  async function onSubmitForReview() {
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
      await httpApi.put(P_wp.status(opts.projectId.value, opts.wpId.value), { status: 'pending_review' })
      ElMessage.success('已提交复核，等待复核人审阅')
      opts.wpDetail.value = await getWorkpaper(opts.projectId.value, opts.wpId.value)
    } catch (err: any) {
      handleApiError(err, '提交复核')
    } finally {
      submitting.value = false
    }
  }

  async function onSyncStructure() {
    syncLoading.value = true
    try {
      if (opts.dirty.value) {
        const saveOk = await onSave()
        if (!saveOk) return
      }
      await rebuildWorkpaperStructure(opts.projectId.value, opts.wpId.value)
      opts.wpDetail.value = await getWorkpaper(opts.projectId.value, opts.wpId.value)
      ElMessage.success('公式坐标已同步')
    } catch (e: any) {
      handleApiError(e, '同步')
    } finally {
      syncLoading.value = false
    }
  }

  async function onRefreshPrefill() {
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
      const inst = opts.univerInstance()
      if (inst) {
        try { inst.dispose() } catch { /* ignore */ }
        opts.setUniverInstance(null, null)
      }
      opts.loading.value = true
      await opts.initUniver()

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

  async function onDownload() {
    try {
      await downloadWorkpaper(opts.projectId.value, opts.wpId.value)
    } catch (e: any) {
      handleApiError(e, '下载')
    }
  }

  async function onExportPdf() {
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

  return {
    saving,
    submitting,
    syncLoading,
    prefillLoading,
    exportingPdf,
    onSave,
    onSubmitForReview,
    onSyncStructure,
    onRefreshPrefill,
    onDownload,
    onExportPdf,
  }
}
