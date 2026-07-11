/**
 * NoteFormulaDialog.spec.ts — 附注公式管理弹窗 加载/编辑/持久化 单元测试
 *
 * spec acnr-consumer-wiring Task 20.3（组件由 Task 20.2 实现，后端 Task 20.1）
 *
 * 覆盖（**Validates: Requirements 15.1, 15.2, 15.4**）：
 *  1. onOpen 加载非空 —— watch(modelValue) 触发 GET `.../formulas`，formulas 被填充
 *  2. 编辑持久化跨重开 —— completeRow → PUT 当前集；重开（modelValue false→true）→ 再 GET 重填
 *  3. apply 执行持久集不重生成 —— onApply 先 PUT 持久化编辑集，再 POST apply-formulas
 *  4. 重新生成 —— onRegenerate 仅 POST apply-formulas（不要求 PUT 持久化）
 *  5. 悬空引用拦截 —— store.validate 返回 invalid → ElMessage.error，且不 PUT（不入库）
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

// ─── Hoisted mock fns（ES import 早于 const 初始化，须经 vi.hoisted 保证时序） ──
const {
  mockGet, mockPut, mockPost, mockValidate, mockRefresh,
  mockMsgError, mockMsgSuccess, mockMsgWarning,
} = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPut: vi.fn(),
  mockPost: vi.fn(),
  mockValidate: vi.fn(),
  mockRefresh: vi.fn(),
  mockMsgError: vi.fn(),
  mockMsgSuccess: vi.fn(),
  mockMsgWarning: vi.fn(),
}))

// ─── Mock apiProxy（受控 get/put/post） ────────────────────────────────────────
vi.mock('@/services/apiProxy', () => ({
  api: { get: mockGet, put: mockPut, post: mockPost },
}))

// ─── Mock addressRegistry store（validate = ACNR-backed 校验；refresh 无副作用） ─
vi.mock('@/stores/addressRegistry', () => ({
  useAddressRegistry: () => ({ validate: mockValidate, refresh: mockRefresh }),
}))

// ─── Mock errorHandler（避免真实全局提示副作用） ───────────────────────────────
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))

// ─── Mock ElMessage（断言 error/success/warning 调用） ─────────────────────────
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<typeof import('element-plus')>()
  return {
    ...actual,
    ElMessage: { error: mockMsgError, success: mockMsgSuccess, warning: mockMsgWarning, info: vi.fn() },
  }
})

// ─── Import after mocks ───────────────────────────────────────────────────────
import ElementPlus from 'element-plus'
import NoteFormulaDialog from '../NoteFormulaDialog.vue'

// ─── Fixtures ─────────────────────────────────────────────────────────────────
const PROJECT_ID = 'proj-1'
const YEAR = 2025
const NOTE = { note_section: '五、3', section_title: '应收账款', content_type: 'table' }

const FORMULAS_URL = `/api/disclosure-notes/${PROJECT_ID}/${YEAR}/${NOTE.note_section}/formulas`
const APPLY_URL = `/api/disclosure-notes/${PROJECT_ID}/${YEAR}/${NOTE.note_section}/apply-formulas`

function makeSavedFormula(overrides: Record<string, unknown> = {}) {
  return {
    target: 'R1',
    formula: "TB('1122','审定数')",
    description: '应收合计',
    category: 'auto_calc',
    source: 'TB',
    ...overrides,
  }
}

// ─── Stubs ────────────────────────────────────────────────────────────────────
// ElDialog：渲染 default + footer 插槽（内容/底部按钮可被测试访问）
const ElDialogStub = defineComponent({
  name: 'ElDialog',
  props: { modelValue: { type: Boolean, default: false } },
  template: '<div class="el-dialog-stub"><slot /><slot name="footer" /></div>',
})

const STUBS = { ElDialog: ElDialogStub, FormulaRefPicker: true } as const

function mountDialog(): VueWrapper {
  return mount(NoteFormulaDialog, {
    props: { modelValue: false, currentNote: NOTE, projectId: PROJECT_ID, year: YEAR },
    global: { plugins: [ElementPlus], stubs: STUBS },
  })
}

/** 打开弹窗（modelValue false→true）→ 触发 loadFormulas（watch） */
async function openDialog(wrapper: VueWrapper) {
  await wrapper.setProps({ modelValue: true })
  await flushPromises()
  await nextTick()
}

// ══════════════════════════════════════════════════════════════════════════════
describe('NoteFormulaDialog — 加载/编辑/持久化（Req 15.1/15.2/15.4）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // 默认：GET 返回一条已保存公式；PUT/POST 成功；校验通过
    mockGet.mockResolvedValue({ formulas: [makeSavedFormula()] })
    mockPut.mockResolvedValue({ saved_count: 1 })
    mockPost.mockResolvedValue({ executed: 1, updated: 2 })
    mockValidate.mockResolvedValue({ valid: true, issues: [] })
  })

  // ── 1. onOpen 加载非空 ──────────────────────────────────────────────────────
  it('onOpen 从后端加载公式并填充列表（非空）', async () => {
    const wrapper = mountDialog()
    expect(mockGet).not.toHaveBeenCalled() // 未打开不加载

    await openDialog(wrapper)

    expect(mockGet).toHaveBeenCalledWith(FORMULAS_URL)
    const formulas = (wrapper.vm as any).formulas
    expect(formulas).toHaveLength(1)
    expect(formulas[0].formula).toBe("TB('1122','审定数')")
    expect(formulas[0]._editing).toBe(false)
    // 设置校验上下文
    expect(mockRefresh).toHaveBeenCalledWith(PROJECT_ID, YEAR)
    wrapper.unmount()
  })

  // ── 2. 编辑持久化 + 跨重开 ──────────────────────────────────────────────────
  it('completeRow 持久化当前集（PUT），且重开后再次 GET 重填', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)

    const row = (wrapper.vm as any).formulas[0]
    row._editing = true
    await (wrapper.vm as any).completeRow(row)
    await flushPromises()

    // PUT 携带持久化 shape（剔除 _editing）
    expect(mockPut).toHaveBeenCalledTimes(1)
    const [url, body] = mockPut.mock.calls[0]
    expect(url).toBe(FORMULAS_URL)
    expect(body.formulas).toHaveLength(1)
    expect(body.formulas[0]).not.toHaveProperty('_editing')
    expect(body.formulas[0].formula).toBe("TB('1122','审定数')")
    // 成功后退出编辑态 + 成功提示
    expect(row._editing).toBe(false)
    expect(mockMsgSuccess).toHaveBeenCalled()

    // 重开：modelValue false→true → 再次 GET 重填（跨重开存活）
    const getCallsBefore = mockGet.mock.calls.length
    await wrapper.setProps({ modelValue: false })
    await openDialog(wrapper)
    expect(mockGet.mock.calls.length).toBe(getCallsBefore + 1)
    expect((wrapper.vm as any).formulas).toHaveLength(1)
    wrapper.unmount()
  })

  // ── 3. apply 执行持久集（先 PUT 再 apply-formulas） ─────────────────────────
  it('onApply 先 PUT 持久化编辑集，再 POST apply-formulas（不重生成丢编辑）', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)

    await (wrapper.vm as any).onApply()
    await flushPromises()

    expect(mockPut).toHaveBeenCalledTimes(1)
    expect(mockPut.mock.calls[0][0]).toBe(FORMULAS_URL)
    expect(mockPost).toHaveBeenCalledTimes(1)
    expect(mockPost.mock.calls[0][0]).toBe(APPLY_URL)
    // 顺序：PUT 先于 POST
    expect(mockPut.mock.invocationCallOrder[0]).toBeLessThan(
      mockPost.mock.invocationCallOrder[0],
    )
    wrapper.unmount()
  })

  it('onApply 悬空引用时不 PUT 也不 apply（校验拦截）', async () => {
    mockValidate.mockResolvedValue({ valid: false, issues: [{ ref: "WP('X','Y','Z')" }] })
    const wrapper = mountDialog()
    await openDialog(wrapper)

    await (wrapper.vm as any).onApply()
    await flushPromises()

    expect(mockMsgError).toHaveBeenCalled()
    expect(mockPut).not.toHaveBeenCalled()
    expect(mockPost).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  // ── 4. 重新生成：仅 apply-formulas，不要求 PUT ─────────────────────────────
  it('onRegenerate 仅 POST apply-formulas（不持久化编辑集，不 PUT）', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)
    mockPut.mockClear()
    mockPost.mockClear()
    mockGet.mockClear()

    await (wrapper.vm as any).onRegenerate()
    await flushPromises()

    expect(mockPost).toHaveBeenCalledTimes(1)
    expect(mockPost.mock.calls[0][0]).toBe(APPLY_URL)
    expect(mockPut).not.toHaveBeenCalled()
    // 重新生成后刷新列表展示最新预设
    expect(mockGet).toHaveBeenCalledWith(FORMULAS_URL)
    wrapper.unmount()
  })

  // ── 5. 悬空引用拦截（completeRow 路径）：ElMessage.error + 不 PUT ────────────
  it('completeRow 悬空引用 → ElMessage.error 且不 PUT（不入库）', async () => {
    mockValidate.mockResolvedValue({
      valid: false,
      issues: [{ ref: "WP('无','效','引用')" }],
    })
    const wrapper = mountDialog()
    await openDialog(wrapper)

    const row = (wrapper.vm as any).formulas[0]
    row._editing = true
    await (wrapper.vm as any).completeRow(row)
    await flushPromises()

    expect(mockMsgError).toHaveBeenCalled()
    expect(mockPut).not.toHaveBeenCalled()
    // 拦截后保持编辑态（未成功保存）
    expect(row._editing).toBe(true)
    expect(mockMsgSuccess).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
