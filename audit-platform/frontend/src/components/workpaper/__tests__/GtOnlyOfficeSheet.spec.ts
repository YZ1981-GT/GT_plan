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
  // 🔴 必须同时渲染**默认插槽**与 `title` 命名插槽：本组件把提示标题写在
  // `<template #title>` 里，只渲染默认插槽的桩会让 `wrapper.text()` 拿不到那段文字
  // （首版就是这样，断言恒空而看起来像「功能没实现」）。
  'el-alert': {
    template:
      '<div class="el-alert"><div class="el-alert__title"><slot name="title" /></div><slot /></div>',
    props: ['type', 'closable', 'showIcon', 'show-icon'],
  },
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


// ═══════════════════════════════════════════════════════════════════════════
// task 3.6：独立在线编辑必须**明确标注不同步**（Requirement 4.2 / 6.2）
//
// 🔴 为什么这是真需求而不是文案洁癖：`GtOnlyOfficeSheet` 是 pending / out_of_scope /
// custom / single_onlyoffice 入口的载体。这些入口的在线编辑**不与 HTML 双向同步**
// （它们走旧式 config，没有 room 协议）。不标注时用户会以为在编辑器里改的内容
// 会自动出现在左侧结构化表单里 —— 而那正是本 spec 要消灭的假状态。
// ═══════════════════════════════════════════════════════════════════════════

describe('task 3.6：独立在线编辑文案', () => {
  it('默认（缺 sync_mode）显示「独立在线编辑（不同步）」', async () => {
    mockHttpGet.mockImplementation((url: string) => {
      if (url.includes('/health')) {
        return Promise.resolve({ data: { data: { healthy: true } } })
      }
      // 故意不返回 sync_mode —— 默认必须按「不同步」处理
      return Promise.resolve({ data: { data: { config: {}, token: '', onlyoffice_url: '' } } })
    })
    const wrapper = mount(GtOnlyOfficeSheet, {
      props: { wpId: 'wp-001', sheetName: 'Sheet1' },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('独立在线编辑')
    expect(wrapper.text()).toContain('不同步')
  })

  it('config 请求失败时仍显示「独立在线编辑」（默认值必须是 independent）', async () => {
    // 🔴 这条与上一条**不是**重复：上一条的 config 响应成功，`syncMode.value` 在赋值时被
    // 显式设成 `'independent'`（`sync_mode` 为 undefined 走 else 分支）⇒ **默认值从未被验证**。
    // 实测把初始值改成 `'bound'` 时上一条仍绿（M3 存活）。
    //
    // 本条让 config 请求抛错 ⇒ 赋值语句不执行 ⇒ 读到的就是初始值。
    mockHttpGet.mockImplementation((url: string) => {
      if (url.includes('/health')) {
        return Promise.resolve({ data: { data: { healthy: true } } })
      }
      return Promise.reject(new Error('config failed'))
    })
    const wrapper = mount(GtOnlyOfficeSheet, {
      props: { wpId: 'wp-001', sheetName: 'Sheet1' },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('独立在线编辑')
  })

  it('sync_mode=bound 时不显示该提示', async () => {
    mockHttpGet.mockImplementation((url: string) => {
      if (url.includes('/health')) {
        return Promise.resolve({ data: { data: { healthy: true } } })
      }
      return Promise.resolve({
        data: {
          data: { config: {}, token: '', onlyoffice_url: '', sync_mode: 'bound' },
        },
      })
    })
    const wrapper = mount(GtOnlyOfficeSheet, {
      props: { wpId: 'wp-001', sheetName: 'Sheet1' },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    expect(wrapper.text()).not.toContain('独立在线编辑')
  })

  it('用户可见文案里**不得**出现「已同步」「双向回写」（假状态）', () => {
    // 🔴 判据只扫**用户可见的字符串**（模板文本 + 字符串字面量），不扫注释：
    // 注释里写「不得暗示已同步」是说明，不是文案。首版扫全文 ⇒ 抓到我自己的注释（假红）。
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const fs = require('node:fs')
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const path = require('node:path')
    const file = path.join(__dirname, '..', 'GtOnlyOfficeSheet.vue')
    const raw = fs.readFileSync(file, 'utf-8') as string

    // ① 模板文本节点（去掉 <!-- --> 注释）
    const tplStart = raw.indexOf('<template>')
    const tplEnd = raw.lastIndexOf('</template>')
    const tpl = raw.slice(tplStart, tplEnd).replace(/<!--[\s\S]*?-->/g, '')
    // ② 字符串字面量（单/双/反引号），排除注释行
    const codeLines = raw
      .split('\n')
      .filter((line) => {
        const s = line.trim()
        return !(s.startsWith('//') || s.startsWith('*') || s.startsWith('/*'))
      })
      .join('\n')
    const literals = [...codeLines.matchAll(/['"`]([^'"`\n]*)['"`]/g)]
      .map((m) => m[1])
      .join('\n')

    const haystack = `${tpl}\n${literals}`
    const offenders = haystack
      .split('\n')
      .filter((line) => /已同步|双向回写/.test(line))
      .filter((line) => !/不同步|未同步|不得|禁止|而不是|不是/.test(line))
    expect(
      offenders,
      `GtOnlyOfficeSheet 的用户可见文案声称了已同步：\n${offenders.join('\n')}`,
    ).toEqual([])
  })
})
