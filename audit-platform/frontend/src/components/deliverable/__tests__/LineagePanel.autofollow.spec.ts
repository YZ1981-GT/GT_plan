/**
 * LineagePanel 自动跟随锚点匹配鲁棒性 — deliverable-lineage-content-control Task 4 增强
 *
 * 验证 onBookmarkDetected 优先与已加载章节列表（section-states）精确匹配，
 * 避免 anchor→section_code 逆映射对多分隔符章节（如「五、12·1」）失真；
 * 未匹配/未加载时回退逆映射（单顿号章节可靠）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import LineagePanel from '../LineagePanel.vue'

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))

vi.mock('element-plus', async () => {
  const real = await vi.importActual<any>('element-plus')
  return {
    ...real,
    ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
    ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  }
})

const mockApiGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: { get: (...a: any[]) => mockApiGet(...a), post: vi.fn() },
}))

vi.mock('@/services/sse/projectEventStream', () => ({
  subscribeProjectEvent: () => ({ close: vi.fn() }),
}))

const baseProps = { projectId: 'proj-001', wordExportTaskId: 'task-001', year: 2025 }

function setupApi(sections: Array<{ section_code: string; is_stale: boolean }>) {
  mockApiGet.mockImplementation((url: string) => {
    if (url.includes('section-states')) return Promise.resolve({ sections })
    if (url.includes('/trace')) return Promise.resolve({ contracts: [], section_state: null })
    return Promise.resolve({})
  })
}

function traceCalls(): string[] {
  return mockApiGet.mock.calls
    .map((c) => c[0] as string)
    .filter((u) => u.includes('/trace'))
    .map((u) => decodeURIComponent(u))
}

describe('LineagePanel onBookmarkDetected — 权威章节匹配', () => {
  beforeEach(() => {
    mockApiGet.mockReset()
  })

  it('多分隔符章节：精确匹配 section-states，不受逆映射失真影响', async () => {
    setupApi([{ section_code: '五、12·1', is_stale: false }])
    const wrapper = mount(LineagePanel, { props: baseProps })
    await flushPromises() // onMounted loadSections

    ;(wrapper.vm as any).onBookmarkDetected('sec_五_12_1')
    await flushPromises()

    const calls = traceCalls()
    // 精确命中真实章节码「五、12·1」，而非逆映射产出的「五、12_1」
    expect(calls.some((u) => u.includes('section_code=五、12·1'))).toBe(true)
    expect(calls.some((u) => u.includes('section_code=五、12_1'))).toBe(false)
  })

  it('未加载章节列表时回退逆映射（单顿号可靠）', async () => {
    setupApi([]) // section-states 空
    const wrapper = mount(LineagePanel, { props: baseProps })
    await flushPromises()

    ;(wrapper.vm as any).onBookmarkDetected('sec_八_1')
    await flushPromises()

    expect(traceCalls().some((u) => u.includes('section_code=八、1'))).toBe(true)
  })

  it('杂散 Tag（非本文档章节）回退逆映射，不误命中列表', async () => {
    setupApi([{ section_code: '八、1', is_stale: false }])
    const wrapper = mount(LineagePanel, { props: baseProps })
    await flushPromises()

    ;(wrapper.vm as any).onBookmarkDetected('sec_五_9')
    await flushPromises()

    // 未匹配「八、1」→ 回退逆映射解析为「五、9」
    expect(traceCalls().some((u) => u.includes('section_code=五、9'))).toBe(true)
  })
})
