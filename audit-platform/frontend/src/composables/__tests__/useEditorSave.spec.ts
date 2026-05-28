/**
 * useEditorSave 单测 — workpaper-editor-shrink-phase2, Task 7.3
 *
 * 验证：
 *  - 核心返回值结构（saving, submitting, syncLoading, prefillLoading, exportingPdf 为 ref；7 个 action 函数存在）
 *  - onSave 主要行为：调用 univerAPI.getActiveWorkbook().getSnapshot()，httpApi.post 被调用，成功后 dirty=false
 *
 * Requirements: 12.2
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { computed, ref, isRef } from 'vue'

// Mock vue-router
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

// Mock httpApi — use vi.fn() inside factory (no top-level variable reference)
vi.mock('@/services/apiProxy', () => ({
  api: { post: vi.fn(), get: vi.fn() },
}))

// Mock apiPaths
vi.mock('@/services/apiPaths', () => ({
  workpapers: {
    univerSave: (projectId: string, wpId: string) => `/api/projects/${projectId}/workpapers/${wpId}/univer/save`,
    status: (projectId: string, wpId: string) => `/api/projects/${projectId}/workpapers/${wpId}/status`,
    exportPdf: (projectId: string, wpId: string) => `/api/projects/${projectId}/workpapers/${wpId}/export-pdf`,
  },
}))

// Mock eventBus
vi.mock('@/utils/eventBus', () => ({
  eventBus: { emit: vi.fn() },
}))

// Mock services
vi.mock('@/services/workpaperApi', () => ({
  getWorkpaper: vi.fn().mockResolvedValue({ wp_code: 'D2-1', wp_name: '应收账款', file_version: 2 }),
  downloadWorkpaper: vi.fn().mockResolvedValue(undefined),
}))
vi.mock('@/services/commonApi', () => ({
  rebuildWorkpaperStructure: vi.fn().mockResolvedValue(undefined),
}))

// Mock confirm utilities
vi.mock('@/utils/confirm', () => ({
  confirmSubmitReview: vi.fn().mockResolvedValue(undefined),
  confirmVersionConflict: vi.fn().mockResolvedValue(undefined),
}))

// Mock handleApiError
vi.mock('@/utils/errorHandler', () => ({
  handleApiError: vi.fn(),
}))

// Mock element-plus
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), info: vi.fn(), error: vi.fn() },
}))

// Mock logger
vi.mock('@/utils/logger', () => ({
  logger: { log: vi.fn(), warn: vi.fn(), error: vi.fn() },
}))

import { useEditorSave, type UseEditorSaveOptions } from '../useEditorSave'
import { api as httpApi } from '@/services/apiProxy'
import { getWorkpaper } from '@/services/workpaperApi'
import { eventBus } from '@/utils/eventBus'

function makeOptions(overrides: Partial<UseEditorSaveOptions> = {}): UseEditorSaveOptions {
  return {
    projectId: computed(() => 'proj-1'),
    wpId: computed(() => 'wp-1'),
    wpDetail: ref({ wp_code: 'D2-1', wp_name: '应收账款', file_version: 1 } as any),
    univerAPI: ref({
      getActiveWorkbook: () => ({
        getSnapshot: () => ({ id: 'wb1', sheets: { s1: {} } }),
        getActiveSheet: () => ({ getSheetName: () => 'Sheet1', getName: () => 'Sheet1' }),
      }),
    }),
    dirty: ref(false),
    userOverrides: {
      serializeOverrides: vi.fn().mockReturnValue({}),
      overrideCount: ref(0),
    } as any,
    staleImpact: {
      notify: vi.fn().mockResolvedValue({ total: 0 }),
    } as any,
    hasPrefillMapping: ref(true),
    autoSave: {
      clearDirty: vi.fn(),
    } as any,
    ...overrides,
  }
}

describe('useEditorSave — 核心返回值结构', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(httpApi.post).mockResolvedValue({ message: '保存成功' })
  })

  it('返回 5 个 loading ref + 7 个 action 函数', () => {
    const result = useEditorSave(makeOptions())

    // 5 个 loading ref
    expect(isRef(result.saving)).toBe(true)
    expect(isRef(result.submitting)).toBe(true)
    expect(isRef(result.syncLoading)).toBe(true)
    expect(isRef(result.prefillLoading)).toBe(true)
    expect(isRef(result.exportingPdf)).toBe(true)

    // 初始值均为 false
    expect(result.saving.value).toBe(false)
    expect(result.submitting.value).toBe(false)
    expect(result.syncLoading.value).toBe(false)
    expect(result.prefillLoading.value).toBe(false)
    expect(result.exportingPdf.value).toBe(false)

    // 7 个 action 函数
    expect(typeof result.onSave).toBe('function')
    expect(typeof result.onSubmitForReview).toBe('function')
    expect(typeof result.onSyncStructure).toBe('function')
    expect(typeof result.onRefreshPrefill).toBe('function')
    expect(typeof result.onDownload).toBe('function')
    expect(typeof result.onExportPdf).toBe('function')
    expect(typeof result.onUpload).toBe('function')
  })
})

describe('useEditorSave — onSave 主要行为', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(httpApi.post).mockResolvedValue({ message: '保存成功' })
    vi.mocked(getWorkpaper).mockResolvedValue({ wp_code: 'D2-1', wp_name: '应收账款', file_version: 2 } as any)
  })

  it('onSave 调用 httpApi.post 并在成功后将 dirty 设为 false', async () => {
    const opts = makeOptions({ dirty: ref(true) })
    const result = useEditorSave(opts)

    expect(opts.dirty.value).toBe(true)

    const success = await result.onSave()

    expect(success).toBe(true)
    expect(httpApi.post).toHaveBeenCalledTimes(1)
    expect(httpApi.post).toHaveBeenCalledWith(
      '/api/projects/proj-1/workpapers/wp-1/univer/save',
      expect.objectContaining({
        snapshot: { id: 'wb1', sheets: { s1: {} } },
        expected_version: 1,
      }),
      expect.any(Object),
    )
    expect(opts.dirty.value).toBe(false)
    expect(eventBus.emit).toHaveBeenCalledWith('workpaper:saved', { projectId: 'proj-1', wpId: 'wp-1' })
  })

  it('onSave 在 univerAPI 为 null 时返回 false 且不调用 httpApi', async () => {
    const opts = makeOptions({ univerAPI: ref(null) })
    const result = useEditorSave(opts)

    const success = await result.onSave()

    expect(success).toBe(false)
    expect(httpApi.post).not.toHaveBeenCalled()
  })
})
