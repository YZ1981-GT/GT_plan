/**
 * useEditorUniver 单测 — workpaper-editor-shrink-phase2, Task 7.3
 *
 * 验证：
 *  - 核心返回值结构（univerAPI, loading, loadingHint, loadErrorState, loadErrorMessage, dirty, initUniver, dispose）
 *    —— loadedFromXlsx / fileOpenedAt 随休眠的 xlsx 覆盖回写一并删除（2026-09-29）
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

// Mock workpaperApi（首屏取详情走 getWorkpaperSettled：并发共享在途 + 取消重取一次）
vi.mock('@/services/workpaperApi', () => ({
  getWorkpaperSettled: vi.fn().mockResolvedValue({
    id: '12345678-1234-1234-1234-123456789abc',
    wp_code: 'D2-1',
    wp_name: '应收账款',
    file_version: 1,
  }),
}))

// Mock logger
vi.mock('@/utils/logger', () => ({
  logger: { log: vi.fn(), warn: vi.fn(), error: vi.fn() },
}))

import { useEditorUniver, DIRTY_COMMAND_PATTERNS, WP_UNAVAILABLE_MESSAGE, type UseEditorUniverOptions } from '../useEditorUniver'
import { createUniver } from '@univerjs/presets'
import { api as httpApi } from '@/services/apiProxy'
import { getWorkpaperSettled } from '@/services/workpaperApi'
import axios from 'axios'

function makeOptions(overrides: Partial<UseEditorUniverOptions> = {}): UseEditorUniverOptions {
  return {
    containerRef: ref(document.createElement('div')),
    projectId: computed(() => 'proj-1'),
    wpId: computed(() => '12345678-1234-1234-1234-123456789abc'),
    wpDetail: ref(null),
    sheetNavFacade: {
      refresh: vi.fn(),
      bindUniverApi: vi.fn(),
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
    // 已删除的 xlsx 回写状态不得再暴露（否则调用方会以为回写还在）
    expect('loadedFromXlsx' in result).toBe(false)
    expect('fileOpenedAt' in result).toBe(false)

    // 初始值
    expect(result.univerAPI.value).toBe(null)
    expect(result.loading.value).toBe(true)
    expect(result.loadingHint.value).toBe('')
    expect(result.loadErrorState.value).toBe(null)
    expect(result.loadErrorMessage.value).toBe('')
    expect(result.dirty.value).toBe(false)

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

    // createWorkbook 被调用，且 Shell 的导航 facade 绑定到同一真实 API。
    expect(result.univerAPI.value.createWorkbook).toHaveBeenCalledTimes(1)
    expect(opts.sheetNavFacade.bindUniverApi).toHaveBeenCalledWith(result.univerAPI.value)

    // loading 设为 false
    expect(result.loading.value).toBe(false)
    expect(result.loadingHint.value).toBe('')
  })

  it('dispose 同时释放 composable 与导航 facade 的 API 引用', async () => {
    const opts = makeOptions()
    const result = useEditorUniver(opts)
    await result.initUniver()

    result.dispose()

    expect(result.univerAPI.value).toBeNull()
    expect(opts.sheetNavFacade.bindUniverApi).toHaveBeenLastCalledWith(null)
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


describe('useEditorUniver — 原生 sheet tab 事件', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    vi.mocked(httpApi.get).mockResolvedValue({
      id: 'wb-native-tab',
      sheets: { sheet0: { id: 'sheet0', name: 'Sheet1', rowCount: 10, columnCount: 10, cellData: {} } },
      sheetOrder: ['sheet0'],
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('Univer set-worksheet-activate 命令会刷新 facade active sheet', async () => {
    const opts = makeOptions()
    const result = useEditorUniver(opts)
    await result.initUniver()

    const commandHandler = vi.mocked(result.univerAPI.value.onCommandExecuted).mock.calls[0][0]
    expect(commandHandler).toBeTypeOf('function')
    commandHandler({ id: 'sheet.command.set-worksheet-activate' })

    expect(opts.sheetNavFacade.refresh).toHaveBeenCalledTimes(1)
    expect(result.dirty.value).toBe(false)
  })
})

describe('useEditorUniver — 详情只读、不误判无文件（spec procedure-chain-hardening-and-java-contracts R1）', () => {
  const WP_ID = '12345678-1234-1234-1234-123456789abc'
  const detail = { id: WP_ID, wp_code: 'H1A', wp_name: '固定资产', file_version: 3 }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    vi.mocked(httpApi.get).mockResolvedValue({
      id: 'wb1',
      sheets: { sheet0: { id: 'sheet0', name: 'Sheet1', rowCount: 10, columnCount: 10, cellData: {} } },
      sheetOrder: ['sheet0'],
    })
    vi.mocked(getWorkpaperSettled).mockResolvedValue(detail as any)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('选项是只读 computed（与 UniverEditorCore 同形态）：取到详情经回调交回，不判 no_file', async () => {
    const onDetailLoaded = vi.fn()
    const result = useEditorUniver(makeOptions({ wpDetail: computed(() => null), onDetailLoaded }))

    await result.initUniver()

    expect(result.loadErrorState.value).toBeNull()
    expect(onDetailLoaded).toHaveBeenCalledWith(detail)
    expect(createUniver).toHaveBeenCalledTimes(1)
  })

  it('Shell 已有同一底稿的详情 ⇒ 直接用，不再另取、不回调', async () => {
    const onDetailLoaded = vi.fn()
    const result = useEditorUniver(makeOptions({ wpDetail: computed(() => detail as any), onDetailLoaded }))

    await result.initUniver()

    expect(getWorkpaperSettled).not.toHaveBeenCalled()
    expect(onDetailLoaded).not.toHaveBeenCalled()
    expect(result.loadErrorState.value).toBeNull()
  })

  it('取消（重取后仍被取消）⇒ 「被中断」错误可重试，不判 no_file', async () => {
    vi.mocked(getWorkpaperSettled).mockRejectedValue(new axios.CanceledError())
    const result = useEditorUniver(makeOptions({ wpDetail: computed(() => null) }))

    await result.initUniver()

    expect(result.loadErrorState.value).toBe('error')
    expect(result.loadErrorMessage.value).toBe('加载底稿被中断，请重试')
    expect(createUniver).not.toHaveBeenCalled()
  })

  it('404 ⇒ 中性文案（不区分无权 / 已删 / 不存在）', async () => {
    vi.mocked(getWorkpaperSettled).mockRejectedValue({ response: { status: 404 } })
    const result = useEditorUniver(makeOptions({ wpDetail: computed(() => null) }))

    await result.initUniver()

    expect(result.loadErrorState.value).toBe('no_index')
    expect(result.loadErrorMessage.value).toBe(WP_UNAVAILABLE_MESSAGE)
    expect(WP_UNAVAILABLE_MESSAGE).not.toMatch(/[A-Za-z_]{6,}/)
  })

  it('403 同 404；其余错误给中文文案、不显示 axios 英文（R10）', async () => {
    vi.mocked(getWorkpaperSettled).mockRejectedValueOnce({ response: { status: 403 } })
    const forbidden = useEditorUniver(makeOptions({ wpDetail: computed(() => null) }))
    await forbidden.initUniver()
    expect([forbidden.loadErrorState.value, forbidden.loadErrorMessage.value]).toEqual(['no_index', WP_UNAVAILABLE_MESSAGE])

    vi.mocked(getWorkpaperSettled).mockRejectedValueOnce(Object.assign(new Error('Request failed with status code 500'), {
      response: { status: 500 },
    }))
    const broken = useEditorUniver(makeOptions({ wpDetail: computed(() => null) }))
    await broken.initUniver()
    expect(broken.loadErrorState.value).toBe('error')
    expect(broken.loadErrorMessage.value).toBe('加载底稿失败：网络或服务暂时异常，请重试')
  })

  it('详情为空对象（没有 id）才判 no_file', async () => {
    vi.mocked(getWorkpaperSettled).mockResolvedValue({ status: 'not_started' } as any)
    const result = useEditorUniver(makeOptions({ wpDetail: computed(() => null) }))

    await result.initUniver()

    expect(result.loadErrorState.value).toBe('no_file')
  })
})
