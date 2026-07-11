/**
 * GtFormulaPresetDialog.spec.ts — 公式预设库入口弹窗 说明文档单一源测试（Task 14.7 / P24）
 *
 * **Property 24: 说明文档单一源**
 *
 * **Validates: Requirements 23.6, 25.3**
 *
 * 命题：编报说明（导出模板首区块）与公式预设库弹窗说明文档**同源不分叉**——两处
 * 均经 useFormulaImportExport 的**同一后端端点** `/api/formula-management/reporting-instructions`
 * 取单一文档源，前端不存在第二套（硬编码/内联）说明来源。
 *
 * 用 vitest mock 端点断言：
 *  1. 弹窗说明文档经 reporting-instructions 端点拉取，且渲染内容 == 端点返回内容
 *     （无客户端改写/硬编码）。
 *  2. 端点是**唯一** doc 来源：端点返回 null 时弹窗显示空态占位，不回退任何硬编码
 *     文档（若有第二套源，此处会渲染出分叉内容）。
 *  3. useFormulaImportExport 暴露的 reporting-instructions 端点为单一常量，重复调用
 *     命中同一 URL；导出模板与说明文档同属 `/api/formula-management/` 单一后端模块。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'

// ─── ResizeObserver polyfill（Element Plus 部分组件在 jsdom 下需要） ────────────
if (!(globalThis as any).ResizeObserver) {
  ;(globalThis as any).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

// ─── 单一源说明文档 sentinel（模拟 reporting_instructions 后端返回） ────────────
const DOC_ENDPOINT = '/api/formula-management/reporting-instructions'
const INVENTORY_ENDPOINT = '/api/formula-management/presets/inventory'
const PAGE_ENDPOINT = '/api/formula-management/presets/page'
const EXPORT_TEMPLATE_ENDPOINT = '/api/formula-management/import-export/export-template'

const SINGLE_SOURCE_DOC = {
  title: '公式管理编报说明',
  version: '2025-R1',
  sections: [
    { key: 'overview', title: '一、总述', lines: ['单一源总述内容-SENTINEL'] },
    { key: 'types', title: '二、三类型', lines: ['auto_calc / logic_check / reasonability'] },
  ],
}

// ─── Hoisted mock http（按 URL 路由；记录所有 get/post 调用） ───────────────────
const { mockGet, mockPost, docReturnRef } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  docReturnRef: { value: null as unknown },
}))

vi.mock('@/utils/http', () => ({
  default: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
  },
}))

// ─── Mock ElMessage（避免噪声） ────────────────────────────────────────────────
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<typeof import('element-plus')>()
  return {
    ...actual,
    ElMessage: { error: vi.fn(), success: vi.fn(), warning: vi.fn(), info: vi.fn() },
  }
})

// ─── Import after mocks ───────────────────────────────────────────────────────
import ElementPlus from 'element-plus'
import GtFormulaPresetDialog from '../GtFormulaPresetDialog.vue'
import { useFormulaImportExport } from '@/composables/useFormulaImportExport'

// ─── Stubs：渲染插槽内联，规避 teleport / 复杂子组件 ────────────────────────────
const ElDialogStub = defineComponent({
  name: 'ElDialog',
  props: { modelValue: { type: Boolean, default: false } },
  template: '<div class="el-dialog-stub"><slot /></div>',
})
const ElTabsStub = defineComponent({
  name: 'ElTabs',
  props: { modelValue: { type: String, default: '' } },
  template: '<div class="el-tabs-stub"><slot /></div>',
})
const ElTabPaneStub = defineComponent({
  name: 'ElTabPane',
  props: { name: { type: String, default: '' }, label: { type: String, default: '' } },
  template: '<div class="el-tab-pane-stub"><slot /></div>',
})
// 统一编辑弹窗：stub 掉，避免 useAcnr / FormulaRefPicker 深依赖
const GtFormulaEditDialogStub = defineComponent({
  name: 'GtFormulaEditDialog',
  props: { modelValue: { type: Boolean, default: false } },
  template: '<div class="gt-formula-edit-dialog-stub" />',
})

const STUBS = {
  ElDialog: ElDialogStub,
  ElTabs: ElTabsStub,
  ElTabPane: ElTabPaneStub,
  GtFormulaEditDialog: GtFormulaEditDialogStub,
} as const

function routeGet(url: string) {
  if (url === DOC_ENDPOINT) {
    // 文档不可用场景：整个响应体为 null，使 composable 的
    // `response.data?.data ?? response.data` 归结为 null（模拟无文档源）。
    if (docReturnRef.value == null) {
      return Promise.resolve({ data: null })
    }
    return Promise.resolve({ data: { data: docReturnRef.value } })
  }
  if (url === INVENTORY_ENDPOINT) {
    return Promise.resolve({
      data: {
        data: {
          pages: [{ page_key: 'workpaper:D2', scope: 'workpaper', preset_status: 'presetted', formula_count: 1 }],
          coverage: { total_preset_pages: 1, total_preset_formulas: 1, by_status: { presetted: 1, pending: 0 }, by_scope: [] },
        },
      },
    })
  }
  if (url === PAGE_ENDPOINT) {
    return Promise.resolve({ data: { data: { page_key: 'workpaper:D2', presetted: true, presets: [] } } })
  }
  return Promise.resolve({ data: { data: null } })
}

function mountDialog(): VueWrapper {
  return mount(GtFormulaPresetDialog, {
    props: { modelValue: false, scope: 'workpaper' },
    global: { plugins: [ElementPlus], stubs: STUBS },
  })
}

async function openDialog(wrapper: VueWrapper) {
  await wrapper.setProps({ modelValue: true })
  await flushPromises()
  await nextTick()
}

// ══════════════════════════════════════════════════════════════════════════════
describe('GtFormulaPresetDialog — 说明文档单一源（P24 / Req 23.6, 25.3）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    docReturnRef.value = SINGLE_SOURCE_DOC
    mockGet.mockImplementation((url: string) => routeGet(url))
    mockPost.mockResolvedValue({ data: new Blob() })
  })

  // ── 1. 弹窗文档经 reporting-instructions 端点，渲染 == 端点返回 ───────────────
  it('弹窗说明文档经 reporting-instructions 单一端点拉取并原样渲染', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)

    // 命中 reporting-instructions 端点。
    const docCalls = mockGet.mock.calls.filter((c) => c[0] === DOC_ENDPOINT)
    expect(docCalls.length).toBeGreaterThan(0)

    // 渲染内容 == 端点返回的单一源内容（无客户端改写/硬编码）。
    const text = wrapper.text()
    expect(text).toContain(SINGLE_SOURCE_DOC.title)
    expect(text).toContain('单一源总述内容-SENTINEL')
    expect(text).toContain(SINGLE_SOURCE_DOC.version)
    wrapper.unmount()
  })

  // ── 2. 端点是唯一 doc 源：返回 null → 空态占位，不回退硬编码文档 ──────────────
  it('端点返回 null 时显示空态占位，不存在第二套硬编码文档源', async () => {
    docReturnRef.value = null
    const wrapper = mountDialog()
    await openDialog(wrapper)

    const text = wrapper.text()
    // 无分叉的硬编码文档内容渲染出来。
    expect(text).not.toContain('单一源总述内容-SENTINEL')
    expect(text).toContain('说明文档暂不可用')
    wrapper.unmount()
  })

  // ── 3. 弹窗仅从 reporting-instructions 取文档，无第二 doc 端点 ────────────────
  it('弹窗不从任何非 reporting-instructions 端点取说明文档', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)

    const getUrls = mockGet.mock.calls.map((c) => c[0] as string)
    // 文档只来自单一端点；其余 get 仅为预设清单/页详情（非文档源）。
    const docUrls = getUrls.filter((u) => u.includes('reporting-instructions'))
    expect(new Set(docUrls)).toEqual(new Set([DOC_ENDPOINT]))
    const allowed = new Set([DOC_ENDPOINT, INVENTORY_ENDPOINT, PAGE_ENDPOINT])
    for (const u of getUrls) {
      expect(allowed.has(u)).toBe(true)
    }
    wrapper.unmount()
  })

  // ── 4. composable 层：编报说明与说明文档同属单一后端模块，端点为单一常量 ──────
  it('useFormulaImportExport 的说明文档端点为单一常量，与导出模板同属一个后端模块', async () => {
    const ie = useFormulaImportExport()

    // 说明文档：重复调用命中同一 URL（单一常量，不分叉）。
    await ie.getReportingInstructions('json')
    await ie.getReportingInstructions('markdown')
    const docUrls = mockGet.mock.calls.map((c) => c[0] as string).filter((u) => u.includes('reporting-instructions'))
    expect(docUrls.length).toBe(2)
    expect(new Set(docUrls)).toEqual(new Set([DOC_ENDPOINT]))

    // 导出模板（编报说明首区块的产出方）与说明文档同属 /api/formula-management/ 单一模块。
    await ie.exportTemplate()
    const postUrls = mockPost.mock.calls.map((c) => c[0] as string)
    expect(postUrls).toContain(EXPORT_TEMPLATE_ENDPOINT)
    expect(EXPORT_TEMPLATE_ENDPOINT.startsWith('/api/formula-management/')).toBe(true)
    expect(DOC_ENDPOINT.startsWith('/api/formula-management/')).toBe(true)
  })
})
