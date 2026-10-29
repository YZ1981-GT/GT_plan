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

function deferred<T = any>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
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
    expect(formulas[0]._editing).toBeUndefined()
    expect(wrapper.text()).toContain('双击公式 / 说明格修改，提交后自动保存')
    // 设置校验上下文
    expect(mockRefresh).toHaveBeenCalledWith(PROJECT_ID, YEAR)
    wrapper.unmount()
  })

  // ── 2. 编辑持久化 + 跨重开 ──────────────────────────────────────────────────
  it('completeRow 持久化当前集（PUT），且重开后再次 GET 重填', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)

    await (wrapper.vm as any).completeRow()
    await flushPromises()

    // PUT 携带持久化 shape（不混入前端本地字段）
    expect(mockPut).toHaveBeenCalledTimes(1)
    const [url, body] = mockPut.mock.calls[0]
    expect(url).toBe(FORMULAS_URL)
    expect(body.formulas).toHaveLength(1)
    expect(body.formulas[0]).not.toHaveProperty('_editing')
    expect(body.formulas[0].formula).toBe("TB('1122','审定数')")
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
    await (wrapper.vm as any).completeRow()
    expect(mockPut.mock.calls[0][1].loaded).toEqual({ [slot]: 'G3' })
    expect(mockPut.mock.calls[0][1].formulas[0]).not.toHaveProperty('layer_label')
    expect(row.layer_label).toBe('本项目')

    await (wrapper.vm as any).completeRow()
    expect(mockPut.mock.calls[1][1].loaded).toEqual({ [slot]: 'L1' })
    wrapper.unmount()
  })

  it('格内提交自动保存，失败时只还原该格', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)
    const vm = wrapper.vm as any
    const row = vm.formulas[0]

    await vm.onFormulaCellCommit(row, 'description', '新说明')
    expect(mockPut).toHaveBeenCalledTimes(1)
    expect(mockPut.mock.calls[0][1].formulas[0].description).toBe('新说明')
    expect(row.description).toBe('新说明')

    mockPut.mockRejectedValueOnce(new Error('保存失败'))
    const saved = await vm.onFormulaCellCommit(row, 'description', '失败值')
    expect(saved).toBe(false)
    expect(row.description).toBe('新说明')
    wrapper.unmount()
  })

  it('未选完目标的新行不阻塞既有格自动保存，也不被旧回执从列表抹掉', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)
    const vm = wrapper.vm as any
    vm.addFormula()
    const draft = vm.formulas[1]
    await vm.onFormulaCellCommit(draft, 'formula', 'SUM(0:1, 0)')
    expect(mockPut).not.toHaveBeenCalled()

    mockPut.mockResolvedValue({
      formulas: [makeSavedFormula({ description: '既有行新说明', layer: 'project', layer_label: '本项目' })],
      loaded: { R1: 'L1' },
    })
    await vm.onFormulaCellCommit(vm.formulas[0], 'description', '既有行新说明')
    expect(mockPut).toHaveBeenCalledTimes(1)
    expect(mockPut.mock.calls[0][1].formulas).toHaveLength(1)
    expect(vm.formulas).toContain(draft)
    expect(draft._isNew).toBe(true)
    wrapper.unmount()
  })

  it('同一微任务内相邻格提交合并成一次 PUT', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)
    const vm = wrapper.vm as any
    const row = vm.formulas[0]

    const formulaSave = vm.onFormulaCellCommit(row, 'formula', "TB('1122','期末数')")
    const descriptionSave = vm.onFormulaCellCommit(row, 'description', '合并保存')
    await Promise.all([formulaSave, descriptionSave])

    expect(mockPut).toHaveBeenCalledTimes(1)
    expect(mockPut.mock.calls[0][1].formulas[0]).toMatchObject({
      formula: "TB('1122','期末数')",
      description: '合并保存',
    })
    wrapper.unmount()
  })

  it('保存中继续提交会串行发下一批，并使用上一批返回的新令牌', async () => {
    const first = deferred<any>()
    const second = deferred<any>()
    mockGet.mockResolvedValue({ formulas: [makeSavedFormula()], loaded: { R1: 'G1' } })
    mockPut.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const wrapper = mountDialog()
    await openDialog(wrapper)
    const vm = wrapper.vm as any
    const row = vm.formulas[0]

    const p1 = vm.onFormulaCellCommit(row, 'formula', "TB('1122','期末数')")
    await flushPromises()
    expect(mockPut).toHaveBeenCalledTimes(1)
    const p2 = vm.onFormulaCellCommit(row, 'description', '第二批')
    await flushPromises()
    expect(mockPut).toHaveBeenCalledTimes(1)

    first.resolve({ formulas: [makeSavedFormula({ formula: "TB('1122','期末数')" })], loaded: { R1: 'L1' } })
    await p1
    await flushPromises()
    expect(mockPut).toHaveBeenCalledTimes(2)
    expect(mockPut.mock.calls[1][1].loaded).toEqual({ R1: 'L1' })
    expect(mockPut.mock.calls[1][1].formulas[0].description).toBe('第二批')
    second.resolve({ formulas: [makeSavedFormula({ formula: "TB('1122','期末数')", description: '第二批' })], loaded: { R1: 'L2' } })
    await p2
    wrapper.unmount()
  })

  it('显式保存期间仍可继续格内编辑，后续自动保存串行等待新令牌', async () => {
    const first = deferred<any>()
    const second = deferred<any>()
    mockGet.mockResolvedValue({ formulas: [makeSavedFormula()], loaded: { R1: 'G1' } })
    mockPut.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const wrapper = mountDialog()
    await openDialog(wrapper)
    const vm = wrapper.vm as any
    const row = vm.formulas[0]

    const explicit = vm.completeRow()
    await flushPromises()
    expect(mockPut).toHaveBeenCalledTimes(1)
    const automatic = vm.onFormulaCellCommit(row, 'description', '保存中仍可编辑')
    await flushPromises()
    expect(mockPut).toHaveBeenCalledTimes(1)

    first.resolve({ formulas: [makeSavedFormula()], loaded: { R1: 'L1' } })
    await explicit
    await flushPromises()
    expect(mockPut).toHaveBeenCalledTimes(2)
    expect(mockPut.mock.calls[1][1].loaded).toEqual({ R1: 'L1' })
    second.resolve({ formulas: [makeSavedFormula({ description: '保存中仍可编辑' })], loaded: { R1: 'L2' } })
    await automatic
    wrapper.unmount()
  })

  it('引用选择器向既有行插入引用后也自动保存', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)
    const vm = wrapper.vm as any
    const row = vm.formulas[0]
    vm.editingRow = row

    vm.onInsertRef(" + NOTE('五、1','合计','期末')", '')
    await vm.flushScheduledSaves()

    expect(mockPut).toHaveBeenCalledTimes(1)
    expect(mockPut.mock.calls[0][1].formulas[0].formula).toContain("NOTE('五、1','合计','期末')")
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

    await (wrapper.vm as any).completeRow()
    await flushPromises()

    expect(mockMsgError).toHaveBeenCalled()
    expect(mockPut).not.toHaveBeenCalled()
    expect(mockMsgSuccess).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// spec note-pull-header-formula-closure R3：新增公式选目标（表 / 行 / 列）、可读目标、没目标不保存
describe('NoteFormulaDialog — 公式目标（表 / 行 / 列）', () => {
  const TARGETS = [
    { index: 0, name: '（1）按账龄披露应收账款', rows: ['1年以内', '1至2年', '合 计'], columns: ['期末数', '期初数'] },
    { index: 1, name: '（3）坏账准备变动', rows: ['按单项', '按组合', '合 计'], columns: ['期初数', '本期计提', '期末数'] },
  ]
  const PRESET = { target: '2:0', target_label: '（1）按账龄披露应收账款 · 合 计 · 期末数', formula: 'SUM(0:1, 0)',
    category: 'auto_calc', source: 'preset.total', layer: 'preset', layer_label: '系统预设' }

  beforeEach(() => {
    vi.clearAllMocks()
    mockGet.mockResolvedValue({ formulas: [PRESET], loaded: {}, targets: TARGETS })
    mockPut.mockResolvedValue({ formulas: [PRESET, { target: 't1:2:1', target_label: '（3）坏账准备变动 · 合 计 · 本期计提',
      formula: 'cell(0,1) + cell(1,1)', category: 'auto_calc', layer: 'project', layer_label: '本项目' }], loaded: {} })
    mockPost.mockResolvedValue({ executed: 3, updated: 1, results: [
      { cell: 't1:2:0', status: 'skipped', reason: '引用的单元格都没有数' },
      { cell: 't1:2:2', status: 'skipped', reason: '引用的单元格都没有数' },
      { cell: '2:0', status: 'ok' },
    ] })
    mockValidate.mockResolvedValue({ valid: true, issues: [] })
  })

  it('列表显示「表名 · 行名 · 列名」', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)
    expect(wrapper.text()).toContain('（1）按账龄披露应收账款 · 合 计 · 期末数')
    expect((wrapper.vm as any).targetTables).toHaveLength(2)
    wrapper.unmount()
  })

  it('新增公式选齐表 / 行 / 列后保存，目标按表维度写成 t1:2:1、本地字段不入库', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)
    const vm = wrapper.vm as any
    vm.addFormula()
    const row = vm.formulas[1]
    vm.setCell(row, { table: 1 })
    expect(row.target, '没选齐不写目标').toBe('')
    vm.setCell(row, { table: 1, row: 2 })
    vm.setCell(row, { table: 1, row: 2, col: 1 })
    expect(row.target).toBe('t1:2:1')
    expect(row.target_label).toBe('（3）坏账准备变动 · 合 计 · 本期计提')
    row.formula = 'cell(0,1) + cell(1,1)'
    await vm.completeRow()
    await flushPromises()
    const sent = mockPut.mock.calls[0][1].formulas
    expect(sent.map((f: any) => f.target)).toEqual(['2:0', 't1:2:1'])
    for (const f of sent) {
      for (const k of ['_editing', '_isNew', '_cell', 'target_label', 'layer_label']) expect(f).not.toHaveProperty(k)
    }
    expect(row._isNew).toBe(false)
    expect(row.layer_label).toBe('本项目')
    wrapper.unmount()
  })

  it('有公式没选目标：提示且不保存（原先被当空行丢掉、仍提示已保存）', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)
    const vm = wrapper.vm as any
    vm.addFormula()
    const row = vm.formulas[1]
    row.formula = 'SUM(0:1, 0)'
    await vm.completeRow()
    await flushPromises()
    expect(mockPut).not.toHaveBeenCalled()
    expect(mockMsgWarning).toHaveBeenCalledWith('有 1 条公式没有选择目标单元格（表 / 行 / 列），未保存')
    expect(row._isNew).toBe(true)
    expect(mockMsgSuccess).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('服务端 422 目标无效：逐条列「【目标】原因」', async () => {
    mockPut.mockRejectedValue({ response: { status: 422, data: { detail: {
      error_code: 'FORMULA_TARGET_INVALID', message: '公式目标单元格无效，未保存',
      issues: [{ target: 't1:9:0', message: '超出「（3）坏账准备变动」（3 行 × 3 列）' }],
    } } } })
    const wrapper = mountDialog()
    await openDialog(wrapper)
    const vm = wrapper.vm as any
    await vm.completeRow()
    await flushPromises()
    expect(String(mockMsgError.mock.calls[0][0])).toContain('【t1:9:0】超出「（3）坏账准备变动」（3 行 × 3 列）')
    wrapper.unmount()
  })

  it('应用 / 重新生成：提示写明没写入的原因；重新生成带 regenerate', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)
    const vm = wrapper.vm as any
    await vm.onApply()
    await flushPromises()
    expect(mockMsgSuccess).toHaveBeenLastCalledWith('公式已应用：执行 3 个，更新 1 个单元格；2 个未写入（引用的单元格都没有数 2 个）')
    await vm.onRegenerate()
    await flushPromises()
    expect(mockPost.mock.calls.at(-1)?.[2]).toEqual({ params: { regenerate: true } })
    expect(String(mockMsgSuccess.mock.calls.at(-1)?.[0])).toMatch(/^已重新生成：/)
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
    await (wrapper.vm as any).completeRow()
    await flushPromises()
    return { wrapper }
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
    const { wrapper } = await completeFirstRow()
    expect(mockPut.mock.calls[0][2]).toMatchObject({ _silent: true })
    expect(mockMsgError).toHaveBeenCalledTimes(1)
    expect(String(mockMsgError.mock.calls[0][0])).toContain(`【R1】${ISSUE.ref}：${ISSUE.message}`)
    wrapper.unmount()
  })

  it('428 缺版本令牌：显示后端说明（handleApiError 不认 428，会落进「系统错误」分支）', async () => {
    mockPut.mockRejectedValue({ response: { status: 428, data: { detail: { message: '缺少载入版本，请刷新后重试' } } } })
    const { wrapper } = await completeFirstRow()
    expect(mockMsgWarning).toHaveBeenCalledWith('缺少载入版本，请刷新后重试')
    wrapper.unmount()
  })
})
