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

import { useEditorSave, __resetUnresolvedNotices, type UseEditorSaveOptions } from '../useEditorSave'
import { api as httpApi } from '@/services/apiProxy'
import { getWorkpaper } from '@/services/workpaperApi'
import { eventBus } from '@/utils/eventBus'
import { ElMessage } from 'element-plus'

function makeOptions(overrides: Partial<UseEditorSaveOptions> = {}): UseEditorSaveOptions {
  return {
    projectId: computed(() => 'proj-1'),
    wpId: computed(() => 'wp-1'),
    wpDetail: ref({ wp_code: 'D2-1', wp_name: '应收账款', file_version: 1 } as any),
    setWpDetail: vi.fn(),
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

  it('保存后的影响分析按项目年度（spec post-push-residual-defect-closure 6.5.3：原先兜底今年）', async () => {
    const opts = makeOptions({ year: computed(() => 2025) })
    await useEditorSave(opts).onSave()
    expect(opts.staleImpact.notify).toHaveBeenCalledWith(expect.objectContaining({ year: 2025, project_id: 'proj-1' }))
  })

  it('项目没填年度、底稿详情也没有 year：影响分析传 null（由 useStaleImpact 跳过），不拿今年', async () => {
    const opts = makeOptions({ year: computed(() => null) })
    await useEditorSave(opts).onSave()
    expect(opts.staleImpact.notify).toHaveBeenCalledWith(expect.objectContaining({ year: null }))
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

  it('onSave 不导出 xlsx、不向 template-file/upload-xlsx 发任何请求（休眠覆盖回写已删除）', async () => {
    // 即便 Univer 提供导出能力，保存也只能走 univerSave：导出 xlsx 覆盖服务端原模板是有损且不可回滚的
    const exportXLSXBySnapshotAsync = vi.fn().mockResolvedValue(new Blob(['x']))
    const exportWorkbookToXLSX = vi.fn().mockResolvedValue(new Blob(['x']))
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true })
    const origFetch = globalThis.fetch
    globalThis.fetch = fetchSpy as any
    try {
      const opts = makeOptions({
        univerAPI: ref({
          exportXLSXBySnapshotAsync,
          exportWorkbookToXLSX,
          getActiveWorkbook: () => ({
            getSnapshot: () => ({ id: 'wb1', sheets: { s1: {} } }),
            getActiveSheet: () => ({ getSheetName: () => 'Sheet1' }),
          }),
        }),
        // 旧签名的调用方若还传这两个选项也不得重新激活回写
        ...({ loadedFromXlsx: ref(true), fileOpenedAt: ref(1) } as any),
      })
      const success = await useEditorSave(opts).onSave()
      expect(success).toBe(true)
      expect(exportXLSXBySnapshotAsync).not.toHaveBeenCalled()
      expect(exportWorkbookToXLSX).not.toHaveBeenCalled()
      expect(fetchSpy).not.toHaveBeenCalled()
      const urls = vi.mocked(httpApi.post).mock.calls.map((c) => String(c[0]))
      expect(urls).toEqual(['/api/projects/proj-1/workpapers/wp-1/univer/save'])
    } finally {
      globalThis.fetch = origFetch
    }
  })

  it('保存后的最新详情经 setWpDetail 交回持有者，不写只读详情（R1：版本号不再停在旧值）', async () => {
    const wpDetail = computed(() => ({ wp_code: 'D2-1', wp_name: '应收账款', file_version: 1 } as any))
    const setWpDetail = vi.fn()
    const success = await useEditorSave(makeOptions({ wpDetail, setWpDetail })).onSave()

    expect(success).toBe(true)
    expect(setWpDetail).toHaveBeenCalledTimes(1)
    expect(setWpDetail).toHaveBeenCalledWith({ wp_code: 'D2-1', wp_name: '应收账款', file_version: 2 })
  })

  it('onSave 在 univerAPI 为 null 时返回 false 且不调用 httpApi', async () => {
    const opts = makeOptions({ univerAPI: ref(null) })
    const result = useEditorSave(opts)

    const success = await result.onSave()

    expect(success).toBe(false)
    expect(httpApi.post).not.toHaveBeenCalled()
  })
})

describe('useEditorSave — 起点身份算不出时提示「未能分析下游影响」（design §10.2 / RV9.1-02）', () => {
  const REASON = '引用末段是语义标签、不是 A1 单元格坐标'
  const sheetName = ref('审定表D2-1')

  /** 走真实 onSave；staleImpact 只替换网络那一层（notify），原因由 unresolvedReason 给出。 */
  function optsWithReason(reason: string) {
    return makeOptions({
      year: computed(() => 2025),
      univerAPI: ref({
        getActiveWorkbook: () => ({
          getSnapshot: () => ({ id: 'wb1', sheets: { s1: {} } }),
          getActiveSheet: () => ({ getSheetName: () => sheetName.value }),
        }),
      }),
      staleImpact: { notify: vi.fn().mockResolvedValue({ total: 0 }), unresolvedReason: ref(reason) } as any,
    })
  }

  const unresolvedNotices = () => vi.mocked(ElMessage.info).mock.calls
    .map((c) => String((c[0] as any)?.message ?? c[0]))
    .filter((m) => m.startsWith('未能分析下游影响'))

  beforeEach(() => {
    vi.clearAllMocks()
    __resetUnresolvedNotices()
    sheetName.value = '审定表D2-1'
    vi.mocked(httpApi.post).mockResolvedValue({ message: '保存成功' })
    vi.mocked(getWorkpaper).mockResolvedValue({ wp_code: 'D2-1', wp_name: '应收账款', file_version: 2 } as any)
  })

  it('同一底稿同一 sheet 连存两次只提示一次、文案带后端原因；换 sheet 再提示一次', async () => {
    const save = useEditorSave(optsWithReason(REASON))
    expect(await save.onSave()).toBe(true)
    expect(await save.onSave()).toBe(true)
    expect(unresolvedNotices()).toEqual([`未能分析下游影响：${REASON}`])
    sheetName.value = '明细表D2-2'
    await save.onSave()
    expect(unresolvedNotices()).toHaveLength(2)
  })

  it('编辑器重新挂载（新的 useEditorSave 实例）后同一 (底稿, sheet) 不再提示', async () => {
    await useEditorSave(optsWithReason(REASON)).onSave()
    await useEditorSave(optsWithReason(REASON)).onSave()
    expect(unresolvedNotices()).toHaveLength(1)
  })

  it('后端能分析（原因为空或只有空白）时不提示', async () => {
    await useEditorSave(optsWithReason('')).onSave()
    await useEditorSave(optsWithReason('   ')).onSave()
    expect(unresolvedNotices()).toEqual([])
  })
})
