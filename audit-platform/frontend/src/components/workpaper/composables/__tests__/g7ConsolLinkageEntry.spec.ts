import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

// ─── mocks ───
const apiMocks = vi.hoisted(() => ({
  previewG7Linkage: vi.fn(),
  importG7Linkage: vi.fn(),
}))
vi.mock('@/services/consolWorksheetDataApi', () => ({
  previewG7Linkage: apiMocks.previewG7Linkage,
  importG7Linkage: apiMocks.importG7Linkage,
}))

const httpMocks = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: httpMocks }))

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn(() => Promise.resolve()) }) }))

const elMsg = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn(), error: vi.fn() }))
vi.mock('element-plus', () => ({ ElMessage: elMsg }))

import { useG7ConsolLinkageEntry } from '../g7ConsolLinkageEntry'

function mkPreview(overrides = {}) {
  return {
    available_companies: [{ company_code: 'C1', company_name: '子公司甲' }],
    unresolved_companies: [],
    counts: { info: { candidate: 1, importable: 1 } },
    importable: { info: [{}] },
    targets: {},
    sources_used: [],
    item_versions: { 'G7-1-rows': 'v1' },
    suggestions: [{ id: 's1', selected_default: true }],
    ...overrides,
  }
}

describe('useG7ConsolLinkageEntry', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('openPreview 成功填充 preview 与 stale 状态', async () => {
    apiMocks.previewG7Linkage.mockResolvedValue(mkPreview({ linkage_stale: true, stale_sheets: ['cost'] }))
    const e = useG7ConsolLinkageEntry(ref('p1'), ref(2025))
    const ok = await e.openPreview()
    expect(ok).toBe(true)
    expect(e.preview.value).toBeTruthy()
    expect(e.stale.value).toBe(true)
    expect(e.staleSheets.value).toEqual(['cost'])
    expect(e.suggestionCount.value).toBe(1)
  })

  it('422 → 显示后端 detail 原文并禁用（configError 非空）', async () => {
    apiMocks.previewG7Linkage.mockRejectedValue({
      response: { status: 422, data: { detail: '存在多个 G7 主表实例' } },
    })
    const e = useG7ConsolLinkageEntry(ref('p1'), ref(2025))
    const ok = await e.openPreview()
    expect(ok).toBe(false)
    expect(e.configError.value).toContain('多个 G7 主表实例')
    expect(e.preview.value).toBeNull()
  })

  it('Property 11：import 409 → 不重试写入，自动重新 preview', async () => {
    apiMocks.previewG7Linkage.mockResolvedValue(mkPreview())
    const e = useG7ConsolLinkageEntry(ref('p1'), ref(2025))
    await e.openPreview()
    apiMocks.previewG7Linkage.mockClear()

    apiMocks.importG7Linkage.mockRejectedValue({ response: { status: 409, data: { detail: '源已变更' } } })
    const ok = await e.confirmImport()
    expect(ok).toBe(false)
    // 只调用一次 import（不重试写入）
    expect(apiMocks.importG7Linkage).toHaveBeenCalledTimes(1)
    // 自动重新 preview
    expect(apiMocks.previewG7Linkage).toHaveBeenCalledTimes(1)
    expect(elMsg.warning).toHaveBeenCalled()
  })

  it('import 透传最近一次 preview 的 item_versions 作为 expected_versions', async () => {
    apiMocks.previewG7Linkage.mockResolvedValue(mkPreview({ item_versions: { k: 'ver9' } }))
    apiMocks.importG7Linkage.mockResolvedValue({ imported: { info: 1 }, unresolved_companies: [] })
    const e = useG7ConsolLinkageEntry(ref('p1'), ref(2025))
    await e.openPreview()
    await e.confirmImport()
    const payload = apiMocks.importG7Linkage.mock.calls[0][2]
    expect(payload.expected_versions).toEqual({ k: 'ver9' })
    expect(payload.apply_suggestion_ids).toContain('s1')
  })

  it('Property 12：/stale 请求失败静默降级不抛错', async () => {
    httpMocks.get.mockRejectedValue(new Error('network'))
    const e = useG7ConsolLinkageEntry(ref('p1'), ref(2025))
    await expect(e.refreshStale()).resolves.toBeUndefined()
    expect(e.stale.value).toBe(false)
  })

  it('缺项目/年度上下文时 openPreview 返回 false 并给配置错误', async () => {
    const e = useG7ConsolLinkageEntry(ref(''), ref(0))
    const ok = await e.openPreview()
    expect(ok).toBe(false)
    expect(e.configError.value).toContain('上下文')
  })
})
