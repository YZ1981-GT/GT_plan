/**
 * useEditorUniver — Univer 引擎生命周期管理 composable
 *
 * 封装 initUniver / dispose / workbook 创建 / DIRTY_COMMAND_PATTERNS 监听 / sheet 切换监听
 *
 * spec: workpaper-editor-shrink-phase2, Task 3.2
 * Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6
 */
import { ref, type Ref, type ComputedRef } from 'vue'
import { createUniver, LocaleType, mergeLocales } from '@univerjs/presets'
import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core'
// @ts-ignore - locale file has no type declarations
import UniverPresetSheetsCoreZhCN from '@univerjs/preset-sheets-core/lib/locales/zh-CN'
import { api as httpApi } from '@/services/apiProxy'
import { workpapers as P_wp } from '@/services/apiPaths'
import { getWorkpaper, type WorkpaperDetail } from '@/services/workpaperApi'
import { logger } from '@/utils/logger'
import type { SheetNavFacadeAPI } from './useSheetNavFacade'

/** 标记 workbook 为 dirty 的命令模式列表 */
export const DIRTY_COMMAND_PATTERNS = [
  'set-range-values', 'set-cell',
  'set-formula', 'formula.', 'array-formula',
  'set-style', 'set-border', 'set-number-format', 'set-font',
  'clear-selection', 'delete-range',
  'insert-row', 'insert-col', 'remove-row', 'remove-col',
  'merge-cells', 'unmerge-cells',
]

export interface UseEditorUniverOptions {
  containerRef: Ref<HTMLElement | null>
  projectId: ComputedRef<string>
  wpId: ComputedRef<string>
  wpDetail: Ref<WorkpaperDetail | null>
  sheetNavFacade: SheetNavFacadeAPI
}

export interface UseEditorUniverReturn {
  univerAPI: Ref<any>
  loading: Ref<boolean>
  loadingHint: Ref<string>
  loadErrorState: Ref<'no_file' | 'no_index' | 'invalid_id' | 'error' | null>
  loadErrorMessage: Ref<string>
  dirty: Ref<boolean>
  loadedFromXlsx: Ref<boolean>
  fileOpenedAt: Ref<number>
  initUniver: () => Promise<void>
  dispose: () => void
}

export function useEditorUniver(opts: UseEditorUniverOptions): UseEditorUniverReturn {
  const univerAPI = ref<any>(null)
  const loading = ref(true)
  const loadingHint = ref('')
  const loadErrorState = ref<'no_file' | 'no_index' | 'invalid_id' | 'error' | null>(null)
  const loadErrorMessage = ref('')
  const dirty = ref(false)
  const loadedFromXlsx = ref(false)
  const fileOpenedAt = ref(0)

  // 内部 Univer 实例引用（用于 dispose）
  let univerInstance: any = null

  async function initUniver(): Promise<void> {
    if (!opts.containerRef.value) return

    // UUID 格式校验（提前拦截，避免后端 404 误导）
    const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
    if (!opts.wpId.value || !UUID_RE.test(opts.wpId.value)) {
      loadErrorState.value = 'invalid_id'
      loadErrorMessage.value = '底稿 ID 格式不合法（不是 UUID）'
      loading.value = false
      loadingHint.value = ''
      return
    }

    // 1. 加载底稿详情
    loadingHint.value = '加载底稿详情'
    try {
      opts.wpDetail.value = await getWorkpaper(opts.projectId.value, opts.wpId.value)
      if (!opts.wpDetail.value) {
        loadErrorState.value = 'no_file'
        loadErrorMessage.value = '底稿数据为空，可能尚未生成文件。请先在生命周期中执行"一键生成底稿"。'
        loading.value = false
        loadingHint.value = ''
        return
      }
    } catch (e: any) {
      const status = e?.response?.status
      if (status === 404) {
        loadErrorState.value = 'no_index'
        loadErrorMessage.value = '该底稿不在当前项目中（可能编码已变更或被删除）。请回到底稿列表选择有效的底稿。'
      } else {
        loadErrorState.value = 'error'
        loadErrorMessage.value = e?.message || '加载底稿时发生错误'
      }
      loading.value = false
      loadingHint.value = ''
      return
    }

    // 2. 从后端加载工作簿数据（xlsx-to-json 优先，降级到 univerData）
    loadingHint.value = '加载工作簿数据'
    let workbookData: any = null
    loadedFromXlsx.value = false
    try {
      const jsonData = await httpApi.get(
        `/api/projects/${opts.projectId.value}/workpapers/${opts.wpId.value}/template-file/xlsx-to-json`,
      )
      if (jsonData && jsonData.sheets && Object.keys(jsonData.sheets).length > 0) {
        workbookData = jsonData
        loadedFromXlsx.value = true
        fileOpenedAt.value = Date.now() / 1000
        logger.log(`[useEditorUniver] xlsx-to-json loaded: ${Object.keys(jsonData.sheets).length} sheets`)
      }
    } catch (e: any) {
      logger.warn('[useEditorUniver] xlsx-to-json failed, trying univerData fallback:', e?.message || e)
    }

    // 2b. 降级：从后端加载 Univer JSON 数据（parsed_data 存储的 snapshot）
    if (!workbookData) {
      try {
        const data = await httpApi.get(
          P_wp.univerData(opts.projectId.value, opts.wpId.value),
          { validateStatus: (s: number) => s < 600 },
        )
        workbookData = data
      } catch {
        workbookData = null
      }
    }

    if (!workbookData || !workbookData.sheets) {
      // 兜底：创建空白工作簿
      const wpCode = opts.wpDetail.value.wp_code || 'wp'
      const wpName = opts.wpDetail.value.wp_name || 'Sheet1'
      workbookData = {
        id: wpCode,
        name: `${wpCode} ${wpName}`,
        sheetOrder: ['sheet0'],
        sheets: {
          sheet0: { id: 'sheet0', name: wpName, rowCount: 100, columnCount: 20, cellData: {} },
        },
      }
    }

    // 3. 初始化 Univer 引擎
    loadingHint.value = '初始化 Univer 引擎'
    const { univerAPI: api, univer } = createUniver({
      locale: LocaleType.ZH_CN,
      locales: { [LocaleType.ZH_CN]: mergeLocales(UniverPresetSheetsCoreZhCN) },
      presets: [
        UniverSheetsCorePreset({ container: opts.containerRef.value }),
      ],
    })

    univerInstance = univer
    univerAPI.value = api

    // 4. 创建工作簿
    if (workbookData && workbookData.sheets && Object.keys(workbookData.sheets).length > 0) {
      api.createWorkbook(workbookData)
    } else {
      logger.error('[useEditorUniver] No workbook data available, creating empty workbook')
      const wpCode = opts.wpDetail.value.wp_code || 'wp'
      const wpName = opts.wpDetail.value.wp_name || 'Sheet1'
      api.createWorkbook({
        id: wpCode,
        name: `${wpCode} ${wpName}`,
        sheetOrder: ['sheet0'],
        sheets: { sheet0: { id: 'sheet0', name: 'Sheet1', rowCount: 100, columnCount: 20, cellData: {} } },
      })
    }

    // 5. 监听数据变化（dirty 标记 + sheet 切换）
    api.onCommandExecuted((command: any) => {
      if (DIRTY_COMMAND_PATTERNS.some(p => command.id?.includes(p))) {
        dirty.value = true
      }
      // 监听 sheet 切换/增删，刷新 Sheet 导航
      if (
        command.id?.includes('set-worksheet-activate') ||
        command.id?.includes('insert-sheet') ||
        command.id?.includes('remove-sheet') ||
        command.id?.includes('set-worksheet-name')
      ) {
        opts.sheetNavFacade.refresh()
      }
    })

    // 初次刷新 sheet 导航（workbook 创建完毕）
    loadingHint.value = '渲染工作表'
    setTimeout(() => {
      opts.sheetNavFacade.refresh()
    }, 100)

    loading.value = false
    loadingHint.value = ''
  }

  function dispose(): void {
    if (univerInstance) {
      try { univerInstance.dispose() } catch { /* ignore */ }
      univerInstance = null
      univerAPI.value = null
    }
  }

  return {
    univerAPI,
    loading,
    loadingHint,
    loadErrorState,
    loadErrorMessage,
    dirty,
    loadedFromXlsx,
    fileOpenedAt,
    initUniver,
    dispose,
  }
}
