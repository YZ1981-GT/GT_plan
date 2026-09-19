/**
 * GtOnlyOfficeSheet.spec.ts — OnlyOffice 健康预检降级测试
 *
 * Validates: Requirements R9
 *
 * 验证：
 * 1. mounted 时先调 GET /api/workpapers/onlyoffice/health（Step 0）
 * 2. health 返回 healthy:false → 不加载 api.js → 直接降级 emit('fallback')
 * 3. health 请求网络异常 → 进 catch → 降级
 * 4. health 返回 healthy:true → 继续正常流程（Step 1 config fetch）
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// ─── Mock http ───
const mockHttpGet = vi.fn()
vi.mock('@/utils/http', () => ({
  default: {
    get: (...args: any[]) => mockHttpGet(...args),
  },
}))

// ─── Stub element-plus icons ───
vi.mock('@element-plus/icons-vue', () => ({
  Loading: { name: 'Loading', template: '<i class="loading-icon" />' },
}))

// ─── Import component after mocks ───
import GtOnlyOfficeSheet from '../GtOnlyOfficeSheet.vue'

// ─── Global stubs ───
const globalStubs = {
  'el-icon': { template: '<span class="el-icon"><slot /></span>', props: ['size'] },
  'el-alert': { template: '<div class="el-alert"><slot /></div>', props: ['type', 'closable'] },
}

describe('GtOnlyOfficeSheet - 健康预检 (R9)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('mounted 时首先调 GET /api/workpapers/onlyoffice/health', async () => {
    // health 返回 unhealthy 以阻止后续流程
    mockHttpGet.mockResolvedValueOnce({ data: { healthy: false } })

    mount(GtOnlyOfficeSheet, {
      props: { wpId: 'wp-001', sheetName: 'Sheet1' },
      global: { stubs: globalStubs },
    })

    await flushPromises()

    // 第一次 http.get 调用应为 health 端点
    expect(mockHttpGet).toHaveBeenCalledWith(
      '/api/workpapers/onlyoffice/health',
      { _silent: true },
    )
  })

  it('health 返回 healthy:false → emit fallback，不请求 config', async () => {
    mockHttpGet.mockResolvedValueOnce({ data: { healthy: false } })

    const wrapper = mount(GtOnlyOfficeSheet, {
      props: { wpId: 'wp-001', sheetName: 'Sheet1' },
      global: { stubs: globalStubs },
    })

    await flushPromises()

    // 应只有 1 次 http.get（health），不应有第 2 次（config）
    expect(mockHttpGet).toHaveBeenCalledTimes(1)
    expect(mockHttpGet).toHaveBeenCalledWith(
      '/api/workpapers/onlyoffice/health',
      { _silent: true },
    )

    // 组件应 emit fallback
    expect(wrapper.emitted('fallback')).toBeTruthy()
  })

  it('health 请求网络异常 → 降级 emit fallback', async () => {
    mockHttpGet.mockRejectedValueOnce(new Error('Network Error'))

    const wrapper = mount(GtOnlyOfficeSheet, {
      props: { wpId: 'wp-001', sheetName: 'Sheet1' },
      global: { stubs: globalStubs },
    })

    await flushPromises()

    expect(wrapper.emitted('fallback')).toBeTruthy()
    // 不应有 config 请求
    expect(mockHttpGet).toHaveBeenCalledTimes(1)
  })

  it('health 返回 healthy:true → 继续请求 config（Step 1）', async () => {
    // Step 0: health → healthy
    mockHttpGet.mockResolvedValueOnce({ data: { healthy: true, active_sessions: 3, max_sessions: 10 } })
    // Step 1: config → 返回配置（后续 loadScript 会失败但我们只验证 config 被调用）
    mockHttpGet.mockResolvedValueOnce({
      data: {
        config: { document: {}, editorConfig: {} },
        token: 'test-token',
        onlyoffice_url: 'http://localhost:9980',
      },
    })

    mount(GtOnlyOfficeSheet, {
      props: { wpId: 'wp-001', sheetName: 'Sheet1' },
      global: { stubs: globalStubs },
    })

    await flushPromises()

    // 应有 2 次 http.get：health + config
    expect(mockHttpGet).toHaveBeenCalledTimes(2)
    expect(mockHttpGet.mock.calls[0][0]).toBe('/api/workpapers/onlyoffice/health')
    expect(mockHttpGet.mock.calls[1][0]).toContain('/api/workpapers/wp-001/sheets/Sheet1/onlyoffice-config')
  })

  it('health.data 为 null/undefined → 降级', async () => {
    mockHttpGet.mockResolvedValueOnce({ data: null })

    const wrapper = mount(GtOnlyOfficeSheet, {
      props: { wpId: 'wp-001', sheetName: 'Sheet1' },
      global: { stubs: globalStubs },
    })

    await flushPromises()

    expect(wrapper.emitted('fallback')).toBeTruthy()
    expect(mockHttpGet).toHaveBeenCalledTimes(1)
  })
})


/**
 * 只读模式 type:embedded 测试
 *
 * Validates: Requirements R10
 *
 * 验证：
 * 1. props.readonly=true → editorConfig.type='embedded' + mode='view'
 * 2. 后端返回 config.editorConfig.mode='view' → editorConfig.type='embedded'
 * 3. 编辑模式（readonly=false + mode='edit'）→ editorConfig.type='desktop'
 */
describe('GtOnlyOfficeSheet - 只读模式 type:embedded (R10)', () => {
  let mockDocEditor: any
  let capturedConfig: any

  beforeEach(() => {
    vi.clearAllMocks()
    capturedConfig = null

    // Mock DocEditor constructor to capture the config passed to it
    mockDocEditor = vi.fn().mockImplementation((_id: string, config: any) => {
      capturedConfig = config
      // Simulate onDocumentReady
      if (config.events?.onDocumentReady) {
        setTimeout(() => config.events.onDocumentReady(), 0)
      }
      return { destroyEditor: vi.fn() }
    })

    // Set up DocsAPI on window
    ;(window as any).DocsAPI = { DocEditor: mockDocEditor }
  })

  afterEach(() => {
    vi.restoreAllMocks()
    delete (window as any).DocsAPI
  })

  function setupHealthyAndConfig(configEditorMode: string = 'edit') {
    // Step 0: health → healthy
    mockHttpGet.mockResolvedValueOnce({ data: { healthy: true, active_sessions: 1, max_sessions: 10 } })
    // Step 1: config → 返回正常配置
    mockHttpGet.mockResolvedValueOnce({
      data: {
        config: {
          document: { fileType: 'xlsx', key: 'abc123', title: 'test.xlsx', url: 'http://test/wopi' },
          documentType: 'cell',
          editorConfig: { mode: configEditorMode, lang: 'zh-CN' },
        },
        token: 'jwt-token',
        onlyoffice_url: 'http://localhost:9980',
      },
    })
  }

  // Stub loadScript to succeed (script already "loaded" via window.DocsAPI mock)
  function stubLoadScript() {
    // The component's loadScript creates a script tag; we need to simulate it resolving
    // Since DocsAPI is already on window, the existing check should resolve
    const originalCreateElement = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = originalCreateElement(tag)
      if (tag === 'script') {
        // Simulate successful load
        setTimeout(() => {
          el.onload?.call(el, new Event('load'))
        }, 0)
      }
      return el
    })
  }

  it('props.readonly=true → type="embedded" + mode="view"', async () => {
    setupHealthyAndConfig('edit')
    stubLoadScript()

    mount(GtOnlyOfficeSheet, {
      props: { wpId: 'wp-001', sheetName: 'Sheet1', readonly: true },
      global: { stubs: globalStubs },
      attachTo: document.createElement('div'),
    })

    await flushPromises()
    // Allow onload to fire
    await new Promise(r => setTimeout(r, 10))
    await flushPromises()

    expect(mockDocEditor).toHaveBeenCalled()
    expect(capturedConfig.type).toBe('embedded')
    expect(capturedConfig.editorConfig.mode).toBe('view')
  })

  it('后端返回 mode="view" → type="embedded"', async () => {
    setupHealthyAndConfig('view')  // Backend returns mode=view (review_passed/archived)
    stubLoadScript()

    mount(GtOnlyOfficeSheet, {
      props: { wpId: 'wp-001', sheetName: 'Sheet1', readonly: false },
      global: { stubs: globalStubs },
      attachTo: document.createElement('div'),
    })

    await flushPromises()
    await new Promise(r => setTimeout(r, 10))
    await flushPromises()

    expect(mockDocEditor).toHaveBeenCalled()
    expect(capturedConfig.type).toBe('embedded')
    expect(capturedConfig.editorConfig.mode).toBe('view')
  })

  it('编辑模式（readonly=false + mode="edit"）→ type="desktop"', async () => {
    setupHealthyAndConfig('edit')
    stubLoadScript()

    mount(GtOnlyOfficeSheet, {
      props: { wpId: 'wp-001', sheetName: 'Sheet1', readonly: false },
      global: { stubs: globalStubs },
      attachTo: document.createElement('div'),
    })

    await flushPromises()
    await new Promise(r => setTimeout(r, 10))
    await flushPromises()

    expect(mockDocEditor).toHaveBeenCalled()
    expect(capturedConfig.type).toBe('desktop')
  })
})
