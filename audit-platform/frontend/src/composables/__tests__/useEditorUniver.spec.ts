/**
 * useEditorUniver 单测 — workpaper-editor-shrink-phase2, Task 7.3
 *
 * 验证：
 *  - 核心返回值结构（univerAPI, loading, loadingHint, loadErrorState, loadErrorMessage, dirty, loadedFromXlsx, fileOpenedAt, initUniver, dispose）
 *  - initUniver 主要行为：调用 createUniver，完成后 loading=false
 *
 * Requirements: 12.2
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, isRef, computed } from 'vue'

// Mock @univerjs/presets — no top-level variable references
vi.mock('@univerjs/presets', () => ({
  createUniver: vi.fn(() => ({
    univerAPI: {
      createWorkbook: vi.fn(),
      onCommandExecuted: vi.fn(),
    },
    univer: { dispose: vi.fn() },
  })),
  LocaleType: { ZH_CN: 'zh-CN' },
  mergeLocales: vi.fn((locale: any) => locale),
}))

// Mock @univerjs/preset-sheets-core
vi.mock('@univerjs/preset-sheets-core', () => ({
  UniverSheetsCorePreset: vi.fn(() => ({})),
}))

// Mock locale file
vi.mock('@univerjs/preset-sheets-core/lib/locales/zh-CN', () => ({
  default: {},
}))

// Mock httpApi
vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn(), post: vi.fn() },
}))

// Mock apiPaths
vi.mock('@/services/apiPaths', () => ({
  workpapers: {
    univerData: (projectId: string, wpId: string) => `/api/projects/${projectId}/workpapers/${wpId}/univer/data`,
  },
}))

// Mock workpaperApi
vi.mock('@/services/workpaperApi', () => ({
  getWorkpaper: vi.fn().mockResolvedValue({
    wp_code: 'D2-1',
    wp_name: '应收账款',
    file_version: 1,
  }),
}))

// Mock logger
vi.mock('@/utils/logger', () => ({
  logger: { log: vi.fn(), warn: vi.fn(), error: vi.fn() },
}))

import { useEditorUniver, DIRTY_COMMAND_PATTERNS, type UseEditorUniverOptions } from '../useEditorUniver'
import { createUniver } from '@univerjs/presets'
import { api as httpApi } from '@/services/apiProxy'

function makeOptions(overrides: Partial<UseEditorUniverOptions> = {}): UseEditorUniverOptions {
  return {
    containerRef: ref(document.createElement('div')),
    projectId: computed(() => 'proj-1'),
    wpId: computed(() => '12345678-1234-1234-1234-123456789abc'),
    wpDetail: ref(null),
    sheetNavFacade: {
      refresh: vi.fn(),
    } as any,
    ...overrides,
  }
}

describe('useEditorUniver — 核心返回值结构', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('返回正确的属性和方法', () => {
    const result = useEditorUniver(makeOptions())

    // Refs
    expect(isRef(result.univerAPI)).toBe(true)
    expect(isRef(result.loading)).toBe(true)
    expect(isRef(result.loadingHint)).toBe(true)
    expect(isRef(result.loadErrorState)).toBe(true)
    expect(isRef(result.loadErrorMessage)).toBe(true)
    expect(isRef(result.dirty)).toBe(true)
    expect(isRef(result.loadedFromXlsx)).toBe(true)
    expect(isRef(result.fileOpenedAt)).toBe(true)

    // 初始值
    expect(result.univerAPI.value).toBe(null)
    expect(result.loading.value).toBe(true)
    expect(result.loadingHint.value).toBe('')
    expect(result.loadErrorState.value).toBe(null)
    expect(result.loadErrorMessage.value).toBe('')
    expect(result.dirty.value).toBe(false)
    expect(result.loadedFromXlsx.value).toBe(false)
    expect(result.fileOpenedAt.value).toBe(0)

    // 函数
    expect(typeof result.initUniver).toBe('function')
    expect(typeof result.dispose).toBe('function')
  })

  it('DIRTY_COMMAND_PATTERNS 包含核心命令模式', () => {
    expect(DIRTY_COMMAND_PATTERNS).toContain('set-range-values')
    expect(DIRTY_COMMAND_PATTERNS).toContain('set-cell')
    expect(DIRTY_COMMAND_PATTERNS).toContain('insert-row')
    expect(DIRTY_COMMAND_PATTERNS).toContain('merge-cells')
    expect(DIRTY_COMMAND_PATTERNS.length).toBeGreaterThanOrEqual(10)
  })
})

describe('useEditorUniver — initUniver 主要行为', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    // xlsx-to-json returns valid workbook data
    vi.mocked(httpApi.get).mockResolvedValue({
      id: 'wb1',
      sheets: { sheet0: { id: 'sheet0', name: 'Sheet1', rowCount: 100, columnCount: 20, cellData: {} } },
      sheetOrder: ['sheet0'],
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('initUniver 调用 createUniver 并在完成后设置 loading=false', async () => {
    const opts = makeOptions()
    const result = useEditorUniver(opts)

    expect(result.loading.value).toBe(true)

    await result.initUniver()

    // createUniver 被调用
    expect(createUniver).toHaveBeenCalledTimes(1)
    expect(createUniver).toHaveBeenCalledWith(
      expect.objectContaining({
        locale: 'zh-CN',
      }),
    )

    // univerAPI 被赋值
    expect(result.univerAPI.value).not.toBe(null)
    expect(result.univerAPI.value.createWorkbook).toBeDefined()

    // createWorkbook 被调用
    expect(result.univerAPI.value.createWorkbook).toHaveBeenCalledTimes(1)

    // loading 设为 false
    expect(result.loading.value).toBe(false)
    expect(result.loadingHint.value).toBe('')
  })

  it('initUniver 在 containerRef 为 null 时直接返回', async () => {
    const opts = makeOptions({ containerRef: ref(null) })
    const result = useEditorUniver(opts)

    await result.initUniver()

    expect(createUniver).not.toHaveBeenCalled()
    expect(result.loading.value).toBe(true) // 未改变
  })

  it('initUniver 在 wpId 非 UUID 格式时设置 loadErrorState', async () => {
    const opts = makeOptions({ wpId: computed(() => 'invalid-id') })
    const result = useEditorUniver(opts)

    await result.initUniver()

    expect(result.loadErrorState.value).toBe('invalid_id')
    expect(result.loadErrorMessage.value).toContain('UUID')
    expect(result.loading.value).toBe(false)
    expect(createUniver).not.toHaveBeenCalled()
  })
})
