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
    // 通知宿主（公式管理中心据此重取本章节公式，formula-governance-coverage-closure R4）
    expect(wrapper.emitted('saved')).toHaveLength(1)

    // 重开：modelValue false→true → 再次 GET 重填（跨重开存活）
    const getCallsBefore = mockGet.mock.calls.length
    await wrapper.setProps({ modelValue: false })
    await openDialog(wrapper)
    expect(mockGet.mock.calls.length).toBe(getCallsBefore + 1)
    expect((wrapper.vm as any).formulas).toHaveLength(1)
    wrapper.unmount()
  })

  // ── 2b. 载入版本令牌（formula-global-settings-sync）：原样带回、保存后换新 ─────────
  it('PUT 带回 GET 给的 loaded；第二次保存改用上次 PUT 返回的新令牌；层级字段不入库', async () => {
    const slot = '五、1|R1C1'
    mockGet.mockResolvedValue({
      formulas: [{ ...makeSavedFormula(), slot_key: slot, layer: 'global', layer_label: '全局', pending: false }],
      loaded: { [slot]: 'G3' },
    })
    mockPut.mockResolvedValueOnce({
      formulas: [{ ...makeSavedFormula(), slot_key: slot, layer: 'project', layer_label: '本项目', pending: false }],
      loaded: { [slot]: 'L1' }, saved_count: 1,
    })
    const wrapper = mountDialog()
    await openDialog(wrapper)
    const row = (wrapper.vm as any).formulas[0]
    row._editing = true
    await (wrapper.vm as any).completeRow(row)
    expect(mockPut.mock.calls[0][1].loaded).toEqual({ [slot]: 'G3' })
    expect(mockPut.mock.calls[0][1].formulas[0]).not.toHaveProperty('layer_label')
    expect(row._editing).toBe(false)
    expect(row.layer_label).toBe('本项目')

    row._editing = true
    await (wrapper.vm as any).completeRow(row)
    expect(mockPut.mock.calls[1][1].loaded).toEqual({ [slot]: 'L1' })
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

// ══════════════════════════════════════════════════════════════════════════════
// spec formula-fetch-followup-defect-closure 7.2 浏览器实测：提示只列引用、不说原因（原因在问题的 message 里）
describe('NoteFormulaDialog — 悬空引用提示写明原因', () => {
  /** 后端 `validate_formula_refs` 的真实形状：原因在 message，status 是状态码 */
  const ISSUE = {
    ref: "NOTE('货币资金','合计','期末')", uri: 'note://货币资金/合计#期末', status: 'not_found',
    message: '本年度（2025）附注没有章节 货币资金（第一参须是章节编号，如「五、1」，不是标题）',
  }

  beforeEach(() => {
    vi.clearAllMocks()
    mockGet.mockResolvedValue({ formulas: [makeSavedFormula()] })
    mockPut.mockResolvedValue({ saved_count: 1 })
    mockValidate.mockResolvedValue({ valid: true, issues: [] })
  })

  async function completeFirstRow() {
    const wrapper = mountDialog()
    await openDialog(wrapper)
    const row = (wrapper.vm as any).formulas[0]
    row._editing = true
    await (wrapper.vm as any).completeRow(row)
    await flushPromises()
    return { wrapper, row }
  }

  it('保存前校验：提示「引用：原因」，不只列引用', async () => {
    mockValidate.mockResolvedValue({ valid: false, issues: [ISSUE] })
    const { wrapper } = await completeFirstRow()
    expect(mockMsgError).toHaveBeenCalledTimes(1)
    expect(String(mockMsgError.mock.calls[0][0])).toContain(`${ISSUE.ref}：${ISSUE.message}`)
    expect(mockPut).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('服务端 422：逐条列「【单元格】引用：原因」，请求带 _silent（全局提示不再先弹一次）', async () => {
    mockPut.mockRejectedValue({ response: { status: 422, data: { detail: {
      error_code: 'FORMULA_DANGLING_REFS', message: '公式含悬空引用，拒绝保存', issues: [{ ...ISSUE, target: 'R1' }],
    } } } })
    const { wrapper, row } = await completeFirstRow()
    expect(mockPut.mock.calls[0][2]).toMatchObject({ _silent: true })
    expect(mockMsgError).toHaveBeenCalledTimes(1)
    expect(String(mockMsgError.mock.calls[0][0])).toContain(`【R1】${ISSUE.ref}：${ISSUE.message}`)
    expect(row._editing, '没保存成功不能退出编辑态').toBe(true)
    wrapper.unmount()
  })

  it('428 缺版本令牌：显示后端说明（handleApiError 不认 428，会落进「系统错误」分支）', async () => {
    mockPut.mockRejectedValue({ response: { status: 428, data: { detail: { message: '缺少载入版本，请刷新后重试' } } } })
    const { wrapper } = await completeFirstRow()
    expect(mockMsgWarning).toHaveBeenCalledWith('缺少载入版本，请刷新后重试')
    wrapper.unmount()
  })
})
