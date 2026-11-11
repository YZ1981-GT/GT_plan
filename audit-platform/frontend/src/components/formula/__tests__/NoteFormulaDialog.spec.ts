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
 *  5. 悬空引用拦截 —— 冻结上下文校验返回 invalid → ElMessage.error，且不 PUT（不入库）
 *  6. 异步隔离 —— 切项目/年度/章节、关闭/卸载后，迟到回执不改当前状态、提示或事件
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { defineComponent, nextTick, reactive } from 'vue'

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
  mockGet, mockPut, mockPost, mockValidate, mockResolve, mockRefresh, mockStoreValidate,
  mockFetchTrialRows, mockHandleApiError, mockMsgError, mockMsgSuccess, mockMsgWarning,
} = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPut: vi.fn(),
  mockPost: vi.fn(),
  mockValidate: vi.fn(),
  mockResolve: vi.fn(),
  mockRefresh: vi.fn(),
  mockStoreValidate: vi.fn(),
  mockFetchTrialRows: vi.fn(),
  mockHandleApiError: vi.fn(),
  mockMsgError: vi.fn(),
  mockMsgSuccess: vi.fn(),
  mockMsgWarning: vi.fn(),
}))

// 校验传输独立分流：既有 mockPost 只统计 apply，不把只读校验混入执行次数。
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (url: string, config?: unknown) => url === '/api/acnr/resolve'
      ? mockResolve(url, config) : mockGet(url, config),
    put: mockPut,
    post: (url: string, body?: unknown, config?: unknown) => url === '/api/address-registry/validate'
      ? mockValidate(url, body, config) : mockPost(url, body, config),
  },
}))
vi.mock('@/services/trialBalanceRows', () => ({ fetchTrialBalanceRows: mockFetchTrialRows }))

// 选择器继续刷新共享库，但保存绝不调用这个会变更绑定的 store.validate。
vi.mock('@/stores/addressRegistry', () => ({
  SINGLE_WP_REF: /^\s*WP\(\s*'[^']*'\s*(?:,\s*'[^']*'\s*){1,2}\)\s*$/,
  useAddressRegistry: () => ({ validate: mockStoreValidate, refresh: mockRefresh }),
}))

vi.mock('@/utils/errorHandler', () => ({ handleApiError: mockHandleApiError }))

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
import GtFormulaIssuePanel from '../GtFormulaIssuePanel.vue'

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

function mountDialog(extraProps: Record<string, any> = {}): VueWrapper {
  return mount(NoteFormulaDialog, {
    props: { modelValue: false, currentNote: NOTE, projectId: PROJECT_ID, year: YEAR, ...extraProps },
    global: { plugins: [ElementPlus], stubs: STUBS },
  })
}

function resetTransportMocks() {
  for (const mock of [mockGet, mockPut, mockPost, mockValidate, mockResolve, mockRefresh,
    mockStoreValidate, mockFetchTrialRows, mockHandleApiError, mockMsgError, mockMsgSuccess,
    mockMsgWarning]) mock.mockReset()
  mockResolve.mockResolvedValue({ found: false })
  mockValidate.mockResolvedValue({ valid: true, issues: [] })
  mockFetchTrialRows.mockResolvedValue({ rows: [] })
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
    resetTransportMocks()
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

    expect(mockGet).toHaveBeenCalledWith(FORMULAS_URL, { _silent: true, _dedupe: false })
    const formulas = (wrapper.vm as any).formulas
    expect(formulas).toHaveLength(1)
    expect(formulas[0].formula).toBe("TB('1122','审定数')")
    expect(formulas[0]._editing).toBeUndefined()
    expect(wrapper.text()).toContain('双击公式 / 说明格修改，提交后自动保存')
    // 设置校验上下文
    expect(mockRefresh).toHaveBeenCalledWith(PROJECT_ID, YEAR, 'soe')
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
    expect(mockGet).toHaveBeenCalledWith(FORMULAS_URL, { _silent: true, _dedupe: false })
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
    resetTransportMocks()
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
    expect(mockPost.mock.calls.at(-1)?.[2]).toEqual({ params: { regenerate: true }, _silent: true })
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
    resetTransportMocks()
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

// ══════════════════════════════════════════════════════════════════════════════
// S2 ADR-CCN-02：问题清单（logic_check / reasonability checks 展示）
describe('NoteFormulaDialog — 问题清单（S2 ADR-CCN-02）', () => {
  beforeEach(() => {
    resetTransportMocks()
    mockGet.mockResolvedValue({ formulas: [makeSavedFormula()] })
    mockPut.mockResolvedValue({ saved_count: 1 })
    mockValidate.mockResolvedValue({ valid: true, issues: [] })
  })

  it('apply-formulas 返回 checks → lastChecks 填充，面板出现', async () => {
    mockPost.mockResolvedValue({
      executed: 2,
      updated: 0,
      results: [],
      checks: [
        { status: 'failed', reason: '合计勾稽不通过', left: 100.0, right: 99.0, diff: 1.0, rule_id: '2:0', source: 'logic_check' },
      ],
    })
    const wrapper = mountDialog()
    await openDialog(wrapper)

    const vm = wrapper.vm as any
    await vm.onApply()
    await flushPromises()

    // lastChecks 填充
    expect(vm.lastChecks).toHaveLength(1)
    expect(vm.lastChecks[0].status).toBe('failed')
    // lastCheckedAt 设置
    expect(vm.lastCheckedAt).not.toBeNull()
    // checkIssues 计算：failed → 1 条
    expect(vm.checkIssues).toHaveLength(1)
    expect(vm.checkIssues[0].description).toBe('合计勾稽不通过')
    expect(vm.checkOutcomes[0]).toMatchObject({ description: '合计勾稽不通过', reason: '合计勾稽不通过', status: 'failed' })
    wrapper.unmount()
  })

  it.each([
    { check: { description: '业务规则说明', label: '未通过', reason: '实际失败原因' }, issue: '业务规则说明', outcome: '业务规则说明' },
    { check: { label: '检查标签', reason: '实际失败原因' }, issue: '检查标签', outcome: '检查标签' },
    { check: { reason: '' }, issue: '校对未完成', outcome: '' },
  ])('checks 名称兼容不覆盖说明/标签，空原因仍兜底：$issue', async ({ check, issue, outcome }) => {
    mockPost.mockResolvedValue({ executed: 1, updated: 0, checks: [
      { rule_id: 'name-priority', status: 'failed', severity: 'blocking', ...check },
    ] })
    const wrapper = mountDialog()
    await openDialog(wrapper)
    const vm = wrapper.vm as any
    await vm.onApply()
    await flushPromises()
    expect(vm.checkIssues).toHaveLength(1)
    expect(vm.checkOutcomes).toHaveLength(1)
    expect(vm.checkIssues[0]).toMatchObject({ description: issue, reason: check.reason, severity: 'blocking', status: 'failed' })
    expect(vm.checkOutcomes[0]).toMatchObject({ description: outcome, reason: check.reason, severity: 'blocking', status: 'failed' })
    wrapper.unmount()
  })

  it('apply-formulas 返回 checks 全部 passed → checkIssues 为空，outcomes 有条目', async () => {
    mockPost.mockResolvedValue({
      executed: 1,
      updated: 0,
      results: [],
      checks: [
        { status: 'passed', reason: '', rule_id: '2:0', source: 'logic_check' },
      ],
    })
    const wrapper = mountDialog()
    await openDialog(wrapper)

    await (wrapper.vm as any).onApply()
    await flushPromises()

    const vm = wrapper.vm as any
    expect(vm.checkIssues).toHaveLength(0)
    expect(vm.checkOutcomes).toHaveLength(1)
    expect(vm.checkOutcomes[0].passed).toBe(true)
    wrapper.unmount()
  })

  it('apply-formulas 保留五态：未执行/异常进入问题清单，不适用只进入概览', async () => {
    mockPost.mockResolvedValue({
      executed: 3,
      updated: 0,
      results: [],
      checks: [
        { status: 'not_executed', label: '未执行（原因）', reason: '目标单元格没有可比较数值', rule_id: '2:0' },
        { status: 'error', label: '检查异常', reason: '公式解析失败', rule_id: '3:0' },
        { status: 'not_applicable', label: '不适用', reason: '本表无该业务场景', rule_id: '4:0' },
      ],
    })
    const wrapper = mountDialog()
    await openDialog(wrapper)

    await (wrapper.vm as any).onApply()
    await flushPromises()

    const vm = wrapper.vm as any
    expect(vm.checkIssues.map((item: any) => item.status)).toEqual(['not_executed', 'error'])
    expect(vm.checkOutcomes.map((item: any) => item.status)).toEqual([
      'not_executed', 'error', 'not_applicable',
    ])
    expect(vm.checkOutcomes.map((item: any) => item.passed)).toEqual([false, false, false])
    wrapper.unmount()
  })

  it('apply-formulas 未返回 checks → lastChecks 为空数组', async () => {
    mockPost.mockResolvedValue({ executed: 1, updated: 1, results: [] })
    const wrapper = mountDialog()
    await openDialog(wrapper)

    await (wrapper.vm as any).onApply()
    await flushPromises()

    const vm = wrapper.vm as any
    expect(vm.lastChecks).toEqual([])
    expect(vm.checkIssues).toHaveLength(0)
    wrapper.unmount()
  })
})
describe('NoteFormulaDialog — S2 检查回执', () => {
  const CHECKS = [
    { rule_id: 'ok', status: 'passed', label: '通过', severity: 'info', left: 0, right: 0 },
    { rule_id: 'fail', status: 'failed', label: '未通过', severity: 'blocking', left: 0, right: 2,
      reason: '左右金额不一致', source: 'note:五、3' },
    { rule_id: 'missing', status: 'not_executed', label: '未执行', severity: 'warning', left: null,
      right: 0, reason: '缺少期初数' },
    { rule_id: 'na', status: 'not_applicable', label: '不适用', severity: 'info', reason: '本节没有表格' },
    { rule_id: 'error', status: 'error', label: '检查异常', severity: 'warning', reason: '引用解析失败' },
  ]

  beforeEach(() => {
    resetTransportMocks()
    mockGet.mockResolvedValue({ formulas: [makeSavedFormula()], loaded: { R1: 'G1' } })
    mockPut.mockResolvedValue({ saved_count: 1, loaded: { R1: 'L1' } })
    mockPost.mockResolvedValue({ executed: 1, updated: 0, checks: CHECKS })
    mockValidate.mockResolvedValue({ valid: true, issues: [] })
  })

  it.each(['onApply', 'onRegenerate'] as const)('%s 显示五态并保留严重程度，非适用项不进入问题清单', async (action) => {
    const w = mountDialog()
    await openDialog(w)
    expect(w.findComponent(GtFormulaIssuePanel).exists()).toBe(false)
    await (w.vm as any)[action]()
    await flushPromises()
    const panel = w.findComponent(GtFormulaIssuePanel)
    expect(panel.exists()).toBe(true)
    expect(panel.props('issues').map((c: any) => c.formula_id)).toEqual(['fail', 'missing', 'error'])
    expect(panel.props('issues')[0]).toMatchObject({ left_value: '0', right_value: '2',
      status: 'failed', severity: 'blocking', label: '未通过', addr_id: 'note:五、3' })
    expect(panel.props('issues')[1]).toMatchObject({ left_value: null, right_value: '0' })
    expect(panel.props('outcomes').map((c: any) => c.status)).toEqual(CHECKS.map((c) => c.status))
    expect(panel.props('outcomes').map((c: any) => c.severity)).toEqual(CHECKS.map((c) => c.severity))
    expect(panel.props('outcomes').map((c: any) => c.passed)).toEqual([true, false, false, false, false])
    expect(panel.props('lastComputedAt')).toEqual(expect.any(String))
    expect(panel.props('showRefresh')).toBe(false)
    expect(panel.text()).toContain('3 项待处理')
    w.unmount()
  })

  it.each([
    ['章节', { currentNote: { ...NOTE, note_section: '五、4' } }],
    ['项目', { projectId: 'proj-2' }], ['年度', { year: 2026 }],
    ['关闭后重开', { modelValue: false }],
  ] as const)('切换%s 清旧结果，晚到回执不重新显示', async (_name, changedProps) => {
    const w = mountDialog()
    await openDialog(w)
    await (w.vm as any).onApply()
    await flushPromises()
    expect(w.findComponent(GtFormulaIssuePanel).exists()).toBe(true)
    const pending = deferred<any>()
    mockPost.mockReturnValueOnce(pending.promise)
    const request = (w.vm as any).onApply()
    await flushPromises()
    expect(mockPost).toHaveBeenCalledTimes(2)
    await w.setProps(changedProps)
    await flushPromises()
    expect(w.findComponent(GtFormulaIssuePanel).exists()).toBe(false)
    if ('modelValue' in changedProps) await openDialog(w)
    pending.resolve({ executed: 1, updated: 0, checks: CHECKS })
    await request
    await flushPromises()
    expect(w.findComponent(GtFormulaIssuePanel).exists()).toBe(false)
    expect((w.vm as any).lastCheckedAt).toBeNull()
    w.unmount()
  })
})
// R3：挂起传输只控制 await 边界，不替换生产组件实现。
const CONTEXT_CHANGES = [
  { name: '项目', props: { projectId: 'proj-2' } },
  { name: '年度', props: { year: 2026 } },
  { name: '章节', props: { currentNote: { ...NOTE, note_section: '五、4' } } },
  { name: '同章节新对象', props: { currentNote: { ...NOTE } } },
  { name: '关闭重开', props: { modelValue: false } },
] as const
const LATE_RESULT = { executed: 1, updated: 1, checks: [
  { rule_id: 'late', status: 'failed', label: '未通过', severity: 'blocking', left: 0, right: 2 },
] }
function listing(label: string, token = label) {
  return { formulas: [makeSavedFormula({ description: label, target_label: label })], loaded: { R1: token },
    targets: [{ index: 0, name: label, rows: [label], columns: ['期末数'] }] }
}
function dialogUrl(props: Record<string, any>, suffix = 'formulas') {
  return `/api/disclosure-notes/${props.projectId}/${props.year}/${props.currentNote.note_section}/${suffix}`
}
async function changeDialog(wrapper: VueWrapper, props: Record<string, any>) {
  await wrapper.setProps(props)
  if ('modelValue' in props) await wrapper.setProps({ modelValue: true })
  await flushPromises()
}
function expectListing(vm: any, expected: ReturnType<typeof listing>) {
  expect(vm.formulas).toEqual(expected.formulas)
  expect(vm.loadedTokens).toEqual(expected.loaded)
  expect(vm.targetTables).toEqual(expected.targets)
}
function clearFeedback() {
  for (const mock of [mockMsgError, mockMsgSuccess, mockMsgWarning, mockHandleApiError]) mock.mockClear()
}
function expectNoFeedback() {
  for (const mock of [mockMsgError, mockMsgSuccess, mockMsgWarning, mockHandleApiError]) expect(mock).not.toHaveBeenCalled()
}

describe('NoteFormulaDialog — R3 异步上下文隔离', () => {
  beforeEach(() => {
    resetTransportMocks()
    mockGet.mockResolvedValue(listing('初始', 'G1'))
    mockPut.mockResolvedValue({ formulas: [makeSavedFormula()], loaded: { R1: 'L1' } })
    mockPost.mockResolvedValue(LATE_RESULT)
  })
  it.each(CONTEXT_CHANGES.flatMap(change => ['成功', '失败'].map(outcome => ({ ...change, outcome }))))(
    '加载中切换$name，旧$outcome 不覆盖列表/目标/令牌或刷新共享库', async ({ props, outcome }) => {
      const old = deferred<any>(), fresh = listing('新上下文', 'G-new')
      mockGet.mockReturnValueOnce(old.promise).mockResolvedValue(fresh)
      const w = mountDialog(); await openDialog(w)
      const vm = w.vm as any
      expect(vm.loading).toBe(true)
      expect(mockGet.mock.calls[0]).toEqual([FORMULAS_URL, { _silent: true, _dedupe: false }])
      await changeDialog(w, props)
      expectListing(vm, fresh); expect(vm.loading).toBe(false)
      expect(mockGet).toHaveBeenCalledTimes(2)
      expect(mockGet.mock.calls[1][0]).toBe(dialogUrl(w.props()))
      expect(mockRefresh).toHaveBeenCalledTimes(1)
      expect(mockRefresh).toHaveBeenCalledWith(w.props('projectId'), w.props('year'), 'soe')
      clearFeedback()
      if (outcome === '成功') old.resolve(listing('旧上下文', 'G-old'))
      else old.reject(new Error('旧加载失败'))
      await flushPromises()
      expectListing(vm, fresh); expect(vm.loading).toBe(false)
      expect(mockRefresh).toHaveBeenCalledTimes(1); expectNoFeedback()
      expect(w.emitted('saved')).toBeUndefined(); expect(w.emitted('applied')).toBeUndefined()
      w.unmount()
    },
  )
  it.each(['先发先回', '后发先回'])('同代双 GET %s，仅最后发起者拥有数据和 loading', async order => {
    const w = mountDialog(); await openDialog(w)
    const vm = w.vm as any, first = deferred<any>(), second = deferred<any>()
    mockGet.mockClear(); mockRefresh.mockClear()
    mockGet.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const p1 = vm.loadFormulas(), p2 = vm.loadFormulas()
    if (order === '先发先回') {
      first.resolve(listing('过期 GET')); expect(await p1).toBe(false)
      expect(vm.loading).toBe(true); expectListing(vm, listing('初始', 'G1'))
      expect(mockRefresh).not.toHaveBeenCalled()
    }
    second.resolve(listing('最后发起', 'G2')); expect(await p2).toBe(true)
    if (order === '后发先回') { first.resolve(listing('过期 GET')); expect(await p1).toBe(false) }
    expectListing(vm, listing('最后发起', 'G2')); expect(vm.loading).toBe(false)
    expect(mockRefresh).toHaveBeenCalledTimes(1)
    expect(mockGet.mock.calls.every(([, config]) => config._dedupe === false && config._silent)).toBe(true)
    expectNoFeedback(); w.unmount()
  })
  it('A→B→A 同值返回也建新代，旧加载不能复活', async () => {
    const old = deferred<any>()
    mockGet.mockReturnValueOnce(old.promise).mockResolvedValueOnce(listing('B')).mockResolvedValue(listing('新 A'))
    const w = mountDialog(); await openDialog(w)
    await changeDialog(w, { projectId: 'proj-2' }); await changeDialog(w, { projectId: PROJECT_ID })
    expectListing(w.vm as any, listing('新 A'))
    old.resolve(listing('旧 A')); await flushPromises(); expectListing(w.vm as any, listing('新 A'))
    expect(mockGet).toHaveBeenCalledTimes(3); expect(mockRefresh).toHaveBeenCalledTimes(2); w.unmount()
  })
  it('旧加载 finally 不清除新上下文尚在加载的 busy', async () => {
    const old = deferred<any>(), fresh = deferred<any>()
    mockGet.mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise)
    const w = mountDialog(); await openDialog(w); await changeDialog(w, { year: 2026 })
    old.reject(new Error('旧加载失败')); await flushPromises()
    expect((w.vm as any).loading).toBe(true); expect((w.vm as any).formulas).toEqual([]); expectNoFeedback()
    fresh.resolve(listing('新年度')); await flushPromises()
    expectListing(w.vm as any, listing('新年度')); expect((w.vm as any).loading).toBe(false); w.unmount()
  })
  it.each(['成功', '失败'])('卸载后旧 GET %s 不刷新地址库或提示', async outcome => {
    const old = deferred<any>(); mockGet.mockReturnValueOnce(old.promise)
    const w = mountDialog(); await openDialog(w); w.unmount()
    if (outcome === '成功') old.resolve(listing('卸载后返回'))
    else old.reject(new Error('卸载后失败'))
    await flushPromises(); expect(mockRefresh).not.toHaveBeenCalled(); expectNoFeedback()
    expect(w.emitted('saved')).toBeUndefined(); expect(w.emitted('applied')).toBeUndefined()
  })
  it.each(CONTEXT_CHANGES.flatMap(change => ['flush', 'validate', 'PUT'].map(phase => ({ ...change, phase }))))(
    'apply 等待 $phase 时切换$name，不续发旧保存/执行', async ({ props, phase }) => {
      const w = mountDialog(); await openDialog(w)
      const vm = w.vm as any, blocked = deferred<any>()
      let automatic: Promise<boolean> | undefined
      if (phase === 'validate') mockValidate.mockReturnValueOnce(blocked.promise)
      else mockPut.mockReturnValueOnce(blocked.promise)
      if (phase === 'flush') {
        automatic = vm.onFormulaCellCommit(vm.formulas[0], 'description', '旧自动保存')
        await flushPromises(); expect(mockPut).toHaveBeenCalledTimes(1)
      }
      let finished = false
      const applying = vm.onApply().then(() => { finished = true })
      await flushPromises(); expect(vm.applying).toBe(true)
      const sentPuts = phase === 'validate' ? 0 : 1
      expect(mockPut).toHaveBeenCalledTimes(sentPuts); expect(mockPost).not.toHaveBeenCalled()
      expect(mockValidate.mock.calls[0]).toEqual(['/api/address-registry/validate', {
        formula: "TB('1122','审定数')", project_id: PROJECT_ID, year: YEAR, template_type: 'soe',
      }, { _silent: true }])
      const fresh = listing('切换后的模型', 'G-new'); mockGet.mockResolvedValue(fresh)
      await changeDialog(w, props)
      expect(finished, '旧等待应在失效时结算，不能依赖旧传输返回').toBe(true)
      expect(vm.applying).toBe(false); clearFeedback()
      blocked.resolve(phase === 'validate' ? { valid: true, issues: [] } : listing('旧回执', 'L-old'))
      await applying
      if (automatic) expect(await automatic).toBe(false)
      await flushPromises(); expectListing(vm, fresh)
      expect(mockPut).toHaveBeenCalledTimes(sentPuts); expect(mockPost).not.toHaveBeenCalled()
      expect(w.emitted('saved')).toBeUndefined(); expect(w.emitted('applied')).toBeUndefined()
      expect(vm.lastCheckedAt).toBeNull(); expectNoFeedback(); w.unmount()
    },
  )
  it('flush 不只等待入口瞬间的 tail，期间新增的一批也必须落定', async () => {
    const w = mountDialog(); await openDialog(w)
    const vm = w.vm as any, first = deferred<any>(), second = deferred<any>(), row = vm.formulas[0]
    mockPut.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const firstSave = vm.onFormulaCellCommit(row, 'formula', "TB('1122','期末数')"); await flushPromises()
    let flushed = false
    const flushing = vm.flushScheduledSaves().then((ok: boolean) => { flushed = true; return ok })
    const secondSave = vm.onFormulaCellCommit(row, 'description', 'flush 期间新增的第二批')
    first.resolve({ formulas: [makeSavedFormula()], loaded: { R1: 'L1' } })
    expect(await firstSave).toBe(true); await flushPromises()
    expect(mockPut).toHaveBeenCalledTimes(2)
    expect(mockPut.mock.calls[1][1].loaded).toEqual({ R1: 'L1' })
    expect(mockPut.mock.calls[1][1].formulas[0].description).toBe('flush 期间新增的第二批')
    expect(flushed).toBe(false)
    second.resolve({ formulas: [makeSavedFormula()], loaded: { R1: 'L2' } })
    expect(await secondSave).toBe(true); expect(await flushing).toBe(true)
    expect(vm.loadedTokens).toEqual({ R1: 'L2' }); w.unmount()
  })
  it.each(['onApply', 'onRegenerate'] as const)('%s 执行中再次点击两个入口都不重入', async action => {
    const w = mountDialog(); await openDialog(w)
    const vm = w.vm as any, post = deferred<any>(); mockPost.mockReturnValueOnce(post.promise)
    const work = vm[action](); await flushPromises(); await vm.onApply(); await vm.onRegenerate()
    expect(mockPost).toHaveBeenCalledTimes(1); expect(mockPut).toHaveBeenCalledTimes(action === 'onApply' ? 1 : 0)
    post.resolve(LATE_RESULT); await work; w.unmount()
  })
  it.each((['onApply', 'onRegenerate'] as const).flatMap(action =>
    CONTEXT_CHANGES.flatMap(change => ['成功', '失败'].map(outcome => ({ ...change, action, outcome }))),
  ))('$action POST 已发后切换$name，旧$outcome 不提示/emit/reload 或清新 busy', async ({ action, props, outcome }) => {
    const w = mountDialog(); await openDialog(w)
    const vm = w.vm as any, old = deferred<any>(), freshPost = deferred<any>()
    mockPost.mockReturnValueOnce(old.promise).mockReturnValueOnce(freshPost.promise)
    const work = vm[action](); await flushPromises()
    expect(mockPost).toHaveBeenCalledTimes(1); expect(mockPost.mock.calls[0][0]).toBe(APPLY_URL)
    expect(mockPost.mock.calls[0][2]).toEqual(action === 'onApply'
      ? { _silent: true } : { params: { regenerate: true }, _silent: true })
    const fresh = listing('新执行上下文', 'G-new'); mockGet.mockResolvedValue(fresh)
    await changeDialog(w, props)
    const savedBefore = w.emitted('saved')?.length ?? 0, appliedBefore = w.emitted('applied')?.length ?? 0
    const getsBefore = mockGet.mock.calls.length, refreshBefore = mockRefresh.mock.calls.length
    const newWork = vm.onRegenerate(); await flushPromises()
    expect(mockPost.mock.calls[1][0]).toBe(dialogUrl(w.props(), 'apply-formulas'))
    expect(vm.regenerating).toBe(true); clearFeedback()
    if (outcome === '成功') old.resolve(LATE_RESULT)
    else old.reject(new Error('旧执行失败'))
    await work; await flushPromises(); expectListing(vm, fresh)
    expect(vm.regenerating).toBe(true); expect(vm.applying).toBe(false); expect(vm.lastCheckedAt).toBeNull()
    expect(vm.checkIssues).toEqual([])
    expect(w.emitted('saved')?.length ?? 0).toBe(savedBefore)
    expect(w.emitted('applied')?.length ?? 0).toBe(appliedBefore)
    expect(mockGet).toHaveBeenCalledTimes(getsBefore); expect(mockRefresh).toHaveBeenCalledTimes(refreshBefore)
    expectNoFeedback(); freshPost.resolve({ executed: 1, updated: 0, checks: [] }); await newWork
    expect(w.emitted('applied')).toHaveLength(appliedBefore + 1); w.unmount()
  })
  it.each((['onApply', 'onRegenerate'] as const).flatMap(action =>
    ['成功', '失败'].map(outcome => ({ action, outcome })),
  ))('卸载后的 $action POST $outcome 不发通知/事件/重载', async ({ action, outcome }) => {
    const onSaved = vi.fn(), onApplied = vi.fn()
    const w = mountDialog({ onSaved, onApplied }); await openDialog(w)
    const old = deferred<any>(); mockPost.mockReturnValueOnce(old.promise)
    const work = (w.vm as any)[action](); await flushPromises()
    // VTU.unmount 会清 emitted 历史，使用跨卸载持续存在的真实事件监听器。
    const savedBefore = action === 'onApply' ? 1 : 0
    expect(onSaved).toHaveBeenCalledTimes(savedBefore); expect(onApplied).not.toHaveBeenCalled()
    const getsBefore = mockGet.mock.calls.length, refreshBefore = mockRefresh.mock.calls.length
    w.unmount(); clearFeedback()
    if (outcome === '成功') old.resolve(LATE_RESULT)
    else old.reject(new Error('卸载后执行失败'))
    await work; await flushPromises()
    expect(mockGet).toHaveBeenCalledTimes(getsBefore); expect(mockRefresh).toHaveBeenCalledTimes(refreshBefore)
    expect(onSaved).toHaveBeenCalledTimes(savedBefore)
    expect(onApplied).not.toHaveBeenCalled(); expectNoFeedback()
  })

  it.each(CONTEXT_CHANGES.flatMap(change => ['成功', '失败'].map(outcome => ({ ...change, outcome }))))(
    'regenerate reload 中切换$name，旧 GET $outcome 不发布执行结果', async ({ props, outcome }) => {
      const w = mountDialog(); await openDialog(w)
      const vm = w.vm as any, reload = deferred<any>(); mockGet.mockReturnValueOnce(reload.promise)
      const work = vm.onRegenerate(); await flushPromises()
      expect(mockGet).toHaveBeenCalledTimes(2)
      expect(mockGet.mock.calls[1]).toEqual([FORMULAS_URL, { _silent: true, _dedupe: false }])
      expect(vm.loading).toBe(true)
      const fresh = listing('重载期间的新上下文'); mockGet.mockResolvedValue(fresh)
      await changeDialog(w, props); clearFeedback()
      if (outcome === '成功') reload.resolve(listing('旧生成列表'))
      else reload.reject(new Error('旧重载失败'))
      await work; await flushPromises(); expectListing(vm, fresh)
      expect(vm.loading).toBe(false); expect(vm.regenerating).toBe(false); expect(vm.lastCheckedAt).toBeNull()
      expect(w.emitted('applied')).toBeUndefined(); expect(mockRefresh).toHaveBeenCalledTimes(2)
      expect(mockPut).not.toHaveBeenCalled(); expectNoFeedback(); w.unmount()
    },
  )

  it('当前 regenerate 的 reload 失败只提示加载失败，不声称完成或 emit applied', async () => {
    const w = mountDialog(); await openDialog(w)
    const error = new Error('重载失败'); mockGet.mockRejectedValueOnce(error)
    await (w.vm as any).onRegenerate()
    expect(mockHandleApiError).toHaveBeenCalledWith(error, '加载公式失败')
    expect(mockMsgSuccess).not.toHaveBeenCalled(); expect(w.emitted('applied')).toBeUndefined()
    expect((w.vm as any).lastCheckedAt).toBeNull(); expect((w.vm as any).regenerating).toBe(false); w.unmount()
  })
  it.each(['成功', '失败'])('旧 PUT 在途，新代独立保存；旧%s 不串 CAS/元数据/busy 或补发队列', async outcome => {
    const w = mountDialog(); await openDialog(w)
    const vm = w.vm as any, row = vm.formulas[0], old = deferred<any>(), fresh = deferred<any>()
    mockPut.mockReturnValueOnce(old.promise).mockReturnValueOnce(fresh.promise)
    const oldSave = vm.onFormulaCellCommit(row, 'description', '旧代已发'); await flushPromises()
    const pendingCell = vm.onFormulaCellCommit(row, 'formula', "TB('1122','期末数')")
    const pendingExplicit = vm.persistFormulas(), pendingFlush = vm.flushScheduledSaves()
    let cellSettled = false, explicitSettled = false, flushSettled = false
    void pendingCell.then((ok: boolean) => { cellSettled = !ok })
    void pendingExplicit.then((ok: boolean) => { explicitSettled = !ok })
    void pendingFlush.then((ok: boolean) => { flushSettled = !ok })
    const newProps = { projectId: 'proj-2', year: 2026, currentNote: { ...NOTE, note_section: '五、4' } }
    mockGet.mockResolvedValue(listing('新代原值', 'G-new')); await changeDialog(w, newProps)
    expect(cellSettled && explicitSettled && flushSettled, '不用等旧 PUT 即结算待发任务').toBe(true)
    expect(await oldSave).toBe(false)
    const currentRow = vm.formulas[0], currentSave = vm.onFormulaCellCommit(currentRow, 'description', '新代编辑')
    await flushPromises(); expect(mockPut).toHaveBeenCalledTimes(2)
    expect(mockPut.mock.calls[0][0]).toBe(FORMULAS_URL)
    expect(mockPut.mock.calls[0][1]).toMatchObject({ loaded: { R1: 'G1' }, formulas: [{ description: '旧代已发' }] })
    expect(mockPut.mock.calls[1][0]).toBe(dialogUrl(newProps))
    expect(mockPut.mock.calls[1][1]).toMatchObject({ loaded: { R1: 'G-new' }, formulas: [{ description: '新代编辑' }] })
    expect(vm.persisting).toBe(true); clearFeedback()
    if (outcome === '成功') old.resolve(listing('旧回执', 'L-old'))
    else old.reject(new Error('旧代保存失败'))
    await flushPromises(); expect(mockPut).toHaveBeenCalledTimes(2)
    expect(vm.loadedTokens).toEqual({ R1: 'G-new' }); expect(vm.formulas[0]).toBe(currentRow)
    expect(currentRow.description).toBe('新代编辑'); expect(currentRow.target_label).toBe('新代原值')
    expect(row.description).toBe('旧代已发'); expect(vm.persisting).toBe(true)
    expect(w.emitted('saved')).toBeUndefined(); expectNoFeedback()
    fresh.resolve({ formulas: [makeSavedFormula({ description: '新代编辑', layer_label: '本项目' })], loaded: { R1: 'L-new' } })
    expect(await currentSave).toBe(true); expect(vm.loadedTokens).toEqual({ R1: 'L-new' })
    expect(currentRow.layer_label).toBe('本项目'); expect(w.emitted('saved')).toHaveLength(1)
    expect(vm.persisting).toBe(false); w.unmount()
  })

  it('本地关闭立即失效，父开关尚未回传时排队的 props watcher 不能重开', async () => {
    const w = mountDialog(); await openDialog(w)
    const vm = w.vm as any, changing = w.setProps({ year: 2026 }); vm.visible = false
    await changing; await flushPromises()
    expect(w.props('modelValue')).toBe(true); expect(w.emitted('update:modelValue')).toEqual([[false]])
    expect(vm.formulas).toEqual([]); expect(vm.loadedTokens).toBeNull(); expect(vm.targetTables).toEqual([])
    expect(mockGet).toHaveBeenCalledTimes(1)
    vm.addFormula(); await vm.completeRow(); await vm.onApply(); await vm.onRegenerate()
    expect(vm.formulas).toEqual([]); expect(mockPut).not.toHaveBeenCalled(); expect(mockPost).not.toHaveBeenCalled()
    expectNoFeedback(); await w.setProps({ modelValue: false }); await openDialog(w)
    expect(mockGet).toHaveBeenCalledTimes(2); expect(mockGet.mock.calls[1][0]).toBe(dialogUrl(w.props()))
    expectListing(vm, listing('初始', 'G1')); w.unmount()
  })
  it.each(['关闭', '卸载'])('格内保存尚未出队即%s，等待结算 false 且不校验/PUT/回滚旧行', async end => {
    const w = mountDialog(); await openDialog(w)
    const vm = w.vm as any, row = vm.formulas[0]
    const save = vm.onFormulaCellCommit(row, 'description', '未发送的编辑'), flushing = vm.flushScheduledSaves()
    if (end === '关闭') vm.visible = false
    else w.unmount()
    await flushPromises(); expect(await save).toBe(false); expect(await flushing).toBe(false)
    expect(row.description).toBe('未发送的编辑'); expect(mockValidate).not.toHaveBeenCalled()
    expect(mockPut).not.toHaveBeenCalled(); expect(w.emitted('saved')).toBeUndefined(); expectNoFeedback()
    if (end === '关闭') w.unmount()
  })
  it('换代后旧行事件不能修改目标/公式、排队保存或打开选择器', async () => {
    const w = mountDialog(); await openDialog(w)
    const vm = w.vm as any, oldRow = vm.formulas[0], before = { ...oldRow }
    mockGet.mockResolvedValue(listing('新行', 'G-new'))
    await changeDialog(w, { currentNote: { ...NOTE, note_section: '五、4' } })
    const currentRow = vm.formulas[0]; vm.setCell(oldRow, { table: 0, row: 0, col: 0 })
    expect(await vm.onFormulaCellCommit(oldRow, 'formula', '旧行不应写入')).toBe(false)
    vm.editingRow = oldRow; vm.onInsertRef("NOTE('五、1','合计','期末')", ''); await vm.openRefPicker(oldRow)
    await flushPromises(); expect(oldRow).toEqual(before); expect(vm.formulas[0]).toBe(currentRow)
    expectListing(vm, listing('新行', 'G-new')); expect(vm.showRefPicker).toBe(false)
    expect(mockGet).toHaveBeenCalledTimes(2); expect(mockFetchTrialRows).not.toHaveBeenCalled()
    expect(mockValidate).not.toHaveBeenCalled(); expect(mockPut).not.toHaveBeenCalled(); expectNoFeedback(); w.unmount()
  })
  it('同一 note 对象原地换章节也失效，不让旧 GET 借对象身份复活', async () => {
    const note = reactive({ ...NOTE }), old = deferred<any>()
    mockGet.mockReturnValueOnce(old.promise).mockResolvedValue(listing('新章节'))
    const w = mountDialog({ currentNote: note }); await openDialog(w)
    note.note_section = '五、4'; await nextTick(); await flushPromises()
    expect(mockGet.mock.calls[1][0]).toBe(dialogUrl(w.props())); expectListing(w.vm as any, listing('新章节'))
    old.resolve(listing('原章节')); await flushPromises(); expectListing(w.vm as any, listing('新章节'))
    expect(mockRefresh).toHaveBeenCalledTimes(1); w.unmount()
  })
  it.each([undefined, 'listed'] as const)('显式校验口径 %s 不读取共享 validate 的可变绑定', async templateType => {
    const shared = { projectId: '其他项目', year: 2040, templateType: '其他口径' }
    mockRefresh.mockImplementation(() => { Object.assign(shared, { projectId: '共享绑定已变化', year: 2041 }) })
    mockStoreValidate.mockRejectedValue(new Error('不应调用共享校验'))
    const w = mountDialog({ templateType }); await openDialog(w); expect(shared.projectId).toBe('共享绑定已变化')
    await (w.vm as any).completeRow()
    expect(mockValidate.mock.calls[0]).toEqual(['/api/address-registry/validate', {
      formula: "TB('1122','审定数')", project_id: PROJECT_ID, year: YEAR, template_type: templateType || 'soe',
    }, { _silent: true }])
    expect(mockRefresh).toHaveBeenCalledWith(PROJECT_ID, YEAR, templateType || 'soe')
    expect(mockStoreValidate).not.toHaveBeenCalled(); expect(mockPut).toHaveBeenCalledTimes(1); w.unmount()
  })
  it('切模板口径使旧校验失效，新保存显式使用新口径', async () => {
    const w = mountDialog({ templateType: 'soe' }); await openDialog(w)
    const vm = w.vm as any, pending = deferred<any>(); mockValidate.mockReturnValueOnce(pending.promise)
    let settled = false
    const oldSave = vm.persistFormulas().then((ok: boolean) => { settled = !ok }); await flushPromises()
    await changeDialog(w, { templateType: 'listed' }); expect(settled).toBe(true); await vm.completeRow()
    expect(mockValidate.mock.calls.map(([, body]) => body.template_type)).toEqual(['soe', 'listed'])
    expect(mockPut).toHaveBeenCalledTimes(1)
    const savedBefore = w.emitted('saved')?.length ?? 0; clearFeedback()
    pending.resolve({ valid: true, issues: [] }); await oldSave; await flushPromises()
    expect(mockPut).toHaveBeenCalledTimes(1); expect(w.emitted('saved')?.length ?? 0).toBe(savedBefore)
    expect(mockStoreValidate).not.toHaveBeenCalled(); expectNoFeedback(); w.unmount()
  })
  it('列表加载失败后新建行仍属于本代响应式行集，目标选择不会被误拒绝', async () => {
    mockGet.mockRejectedValueOnce(new Error('列表暂不可达'))
    const w = mountDialog(); await openDialog(w); const vm = w.vm as any
    expect(vm.formulas).toEqual([]); expect(vm.loadedTokens).toBeNull(); expect(vm.loading).toBe(false)
    vm.addFormula(); const row = vm.formulas[0]; vm.setCell(row, { table: 0, row: 0, col: 0 })
    expect(row.target).toBe('0:0'); expect(await vm.onFormulaCellCommit(row, 'formula', 'cell(0,0)')).toBe(true)
    expect(row.formula).toBe('cell(0,0)'); expect(mockPut).not.toHaveBeenCalled()
    expect(mockValidate).not.toHaveBeenCalled(); w.unmount()
  })
  const WP_FORMULA = "WP('D2','D2-1','R1C1')"
  it('整条单 WP 经 ACNR 命中即短路，不调用 legacy 或共享校验', async () => {
    mockGet.mockResolvedValue({ formulas: [makeSavedFormula({ formula: WP_FORMULA })], loaded: { R1: 'G1' } })
    mockResolve.mockResolvedValue({ found: true, addr_id: 'D2/D2-1/R1C1' })
    const w = mountDialog({ templateType: 'listed' }); await openDialog(w); await (w.vm as any).completeRow()
    expect(mockResolve.mock.calls[0]).toEqual(['/api/acnr/resolve', {
      params: { formula_ref: WP_FORMULA, project_id: PROJECT_ID }, _silent: true, _dedupe: false,
    }])
    expect(mockValidate).not.toHaveBeenCalled(); expect(mockStoreValidate).not.toHaveBeenCalled()
    expect(mockPut.mock.calls[0][1].formulas[0].formula).toBe(WP_FORMULA); w.unmount()
  })
  it.each(['普通未命中', '请求失败'])('ACNR %s 才 fallback，legacy body 保持冻结上下文', async outcome => {
    mockGet.mockResolvedValue({ formulas: [makeSavedFormula({ formula: WP_FORMULA })], loaded: { R1: 'G1' } })
    if (outcome === '普通未命中') mockResolve.mockResolvedValue({ found: false, error: 'ref_not_found' })
    else mockResolve.mockRejectedValue(new Error('目录暂不可达'))
    const w = mountDialog({ templateType: 'listed' }); await openDialog(w); await (w.vm as any).completeRow()
    expect(mockResolve).toHaveBeenCalledTimes(1)
    expect(mockValidate.mock.calls[0]).toEqual(['/api/address-registry/validate', {
      formula: WP_FORMULA, project_id: PROJECT_ID, year: YEAR, template_type: 'listed',
    }, { _silent: true }])
    expect(mockStoreValidate).not.toHaveBeenCalled(); expect(mockPut).toHaveBeenCalledTimes(1); w.unmount()
  })
  const REGISTRY_FAILURES = [
    { code: 'snapshot_missing', wire: 'ACNR_REGISTRY_SNAPSHOT_MISSING', reason: '地址目录快照缺失' },
    { code: 'snapshot_invalid', wire: 'ACNR_REGISTRY_SNAPSHOT_INVALID', reason: '地址目录快照校验失败' },
    { code: 'lock_failed', wire: 'ACNR_REGISTRY_LOCK_FAILED', reason: '地址目录版本锁不可用' },
  ] as const
  it.each(REGISTRY_FAILURES.flatMap(failure => ['正常回执', '409 顶层', '409 detail'].map(shape => ({ ...failure, shape }))))(
    'ACNR $code 的 $shape 保留原因且禁止 legacy fallback', async ({ code, wire, reason, shape }) => {
      mockGet.mockResolvedValue({ formulas: [makeSavedFormula({ formula: WP_FORMULA })], loaded: { R1: 'G1' } })
      if (shape === '正常回执') mockResolve.mockResolvedValue({ found: false, error: code, reason })
      else mockResolve.mockRejectedValue({ response: { status: 409, data: shape === '409 顶层'
        ? { error_code: wire, message: reason } : { detail: { error_code: wire, message: reason } } } })
      const w = mountDialog(); await openDialog(w); await (w.vm as any).onApply()
      expect(mockResolve).toHaveBeenCalledTimes(1)
      expect(mockValidate).not.toHaveBeenCalled(); expect(mockStoreValidate).not.toHaveBeenCalled()
      expect(mockPut).not.toHaveBeenCalled(); expect(mockPost).not.toHaveBeenCalled()
      expect(mockMsgError).toHaveBeenCalledTimes(1)
      expect(String(mockMsgError.mock.calls[0][0])).toContain(`${WP_FORMULA}：${reason}`)
      expect(w.emitted('applied')).toBeUndefined(); w.unmount()
    },
  )

  it('legacy 校验请求失败不能当作合法公式保存，保留中文失败原因', async () => {
    mockValidate.mockRejectedValue(new Error('校验暂不可达'))
    const w = mountDialog(); await openDialog(w); await (w.vm as any).onApply()
    expect(mockMsgError).toHaveBeenCalledTimes(1)
    expect(String(mockMsgError.mock.calls[0][0])).toContain('校验请求失败')
    expect(mockPut).not.toHaveBeenCalled(); expect(mockPost).not.toHaveBeenCalled()
    expect(w.emitted('saved')).toBeUndefined(); expect(w.emitted('applied')).toBeUndefined(); w.unmount()
  })

  it.each(CONTEXT_CHANGES.flatMap(change => [
    'ACNR 命中', 'ACNR 未命中', 'ACNR 异常', 'legacy 合法', 'legacy 非法', 'legacy 异常',
  ].map(boundary => ({ ...change, boundary }))))(
    '$boundary 挂起后切换$name，不续发 fallback/PUT/apply 或展示旧校验错误', async ({ props, boundary }) => {
      const w = mountDialog({ templateType: 'listed' }); await openDialog(w)
      const vm = w.vm as any, pending = deferred<any>(), isAcnr = boundary.startsWith('ACNR')
      if (isAcnr) { vm.formulas[0].formula = WP_FORMULA; mockResolve.mockReturnValueOnce(pending.promise) }
      else mockValidate.mockReturnValueOnce(pending.promise)
      let finished = false
      const work = vm.onApply().then(() => { finished = true })
      await flushPromises()
      expect(mockResolve).toHaveBeenCalledTimes(isAcnr ? 1 : 0)
      expect(mockValidate).toHaveBeenCalledTimes(isAcnr ? 0 : 1)
      if (isAcnr) expect(mockResolve.mock.calls[0][1]).toEqual({
        params: { formula_ref: WP_FORMULA, project_id: PROJECT_ID }, _silent: true, _dedupe: false,
      })
      else expect(mockValidate.mock.calls[0]).toEqual(['/api/address-registry/validate', {
        formula: "TB('1122','审定数')", project_id: PROJECT_ID, year: YEAR, template_type: 'listed',
      }, { _silent: true }])
      const fresh = listing('校验后切换', 'G-new'); mockGet.mockResolvedValue(fresh)
      await changeDialog(w, props)
      expect(finished, '旧调用方不等校验传输返回').toBe(true); clearFeedback()
      if (boundary.endsWith('异常')) pending.reject(new Error('迟到的校验失败'))
      else if (isAcnr) pending.resolve({ found: boundary === 'ACNR 命中', error: 'ref_not_found' })
      else pending.resolve({ valid: boundary === 'legacy 合法', issues: [{ ref: '旧引用', message: '旧校验错误' }] })
      await work; await flushPromises()
      expectListing(vm, fresh)
      expect(vm.applying).toBe(false); expect(vm.persisting).toBe(false)
      expect(mockValidate).toHaveBeenCalledTimes(isAcnr ? 0 : 1)
      expect(mockStoreValidate).not.toHaveBeenCalled(); expect(mockPut).not.toHaveBeenCalled(); expect(mockPost).not.toHaveBeenCalled()
      expect(w.emitted('saved')).toBeUndefined(); expect(w.emitted('applied')).toBeUndefined()
      expectNoFeedback(); w.unmount()
    },
  )

  it.each(CONTEXT_CHANGES.flatMap(change => ['成功', '失败'].map(outcome => ({ ...change, outcome }))))(
    '引用选择器并行取数后切换$name，旧$outcome 不覆盖新数据或弹出窗口', async ({ props, outcome }) => {
      const w = mountDialog(); await openDialog(w)
      const vm = w.vm as any, oldReport = deferred<any>(), oldTb = deferred<any>()
      mockGet.mockReturnValueOnce(oldReport.promise); mockFetchTrialRows.mockReturnValueOnce(oldTb.promise)
      const oldWork = vm.openRefPicker(vm.formulas[0])
      expect(mockGet.mock.calls[1]).toEqual([
        `/api/reports/${PROJECT_ID}/${YEAR}/balance_sheet`, { _silent: true, _dedupe: false },
      ])
      expect(mockFetchTrialRows.mock.calls[0]).toEqual([PROJECT_ID, { year: YEAR }])
      mockGet.mockResolvedValue(listing('选择器新上下文')); await changeDialog(w, props)
      expect(vm.editingRow).toBeNull(); expect(vm.showRefPicker).toBe(false)
      expect(vm.refPickerData).toEqual({ reportRows: [], tbRows: [], noteRows: [] })
      const freshReport = [{ name: '新报表' }], freshTb = [{ standard_account_code: '1001', audited_amount: '0' }]
      mockGet.mockResolvedValueOnce(freshReport); mockFetchTrialRows.mockResolvedValueOnce({ rows: freshTb })
      await vm.openRefPicker(vm.formulas[0])
      expect(mockGet.mock.calls.at(-1)).toEqual([
        `/api/reports/${w.props('projectId')}/${w.props('year')}/balance_sheet`, { _silent: true, _dedupe: false },
      ])
      expect(mockFetchTrialRows.mock.calls[1]).toEqual([w.props('projectId'), { year: w.props('year') }])
      expect(vm.showRefPicker).toBe(true); vm.showRefPicker = false
      const currentRow = vm.formulas[0]; clearFeedback()
      if (outcome === '成功') {
        oldReport.resolve([{ name: '旧报表' }]); oldTb.resolve({ rows: [{ standard_account_code: '旧科目' }] })
      } else {
        oldReport.reject(new Error('旧报表失败')); oldTb.reject(new Error('旧试算表失败'))
      }
      await oldWork; await flushPromises()
      expect(vm.showRefPicker).toBe(false); expect(vm.editingRow).toBe(currentRow)
      expect(vm.refPickerData).toEqual({ reportRows: freshReport, tbRows: freshTb, noteRows: [] })
      expect(mockPut).not.toHaveBeenCalled(); expectNoFeedback(); w.unmount()
    },
  )

  it.each(['关闭', '卸载'].flatMap(end => ['成功', '失败'].map(outcome => ({ end, outcome }))))(
    '选择器挂起后$end，旧$outcome 不再打开或回填', async ({ end, outcome }) => {
      const w = mountDialog(); await openDialog(w)
      const vm = w.vm as any, report = deferred<any>(), tb = deferred<any>()
      mockGet.mockReturnValueOnce(report.promise); mockFetchTrialRows.mockReturnValueOnce(tb.promise)
      const work = vm.openRefPicker(vm.formulas[0])
      if (end === '关闭') vm.visible = false
      else w.unmount()
      clearFeedback()
      if (outcome === '成功') {
        report.resolve([{ name: '迟到报表' }]); tb.resolve({ rows: [{ standard_account_code: '迟到科目' }] })
      } else { report.reject(new Error('迟到报表失败')); tb.reject(new Error('迟到试算表失败')) }
      await work; await flushPromises()
      expect(vm.showRefPicker).toBe(false); expect(vm.editingRow).toBeNull()
      expect(vm.refPickerData).toEqual({ reportRows: [], tbRows: [], noteRows: [] })
      expect(w.emitted('saved')).toBeUndefined(); expect(w.emitted('applied')).toBeUndefined()
      expectNoFeedback(); if (end === '关闭') w.unmount()
    },
  )

  it('同代 reload 已替换行集，旧行的选择器回执也不得打开或回填', async () => {
    const w = mountDialog(); await openDialog(w)
    const vm = w.vm as any, report = deferred<any>(), tb = deferred<any>(), oldRow = vm.formulas[0]
    mockGet.mockReturnValueOnce(report.promise); mockFetchTrialRows.mockReturnValueOnce(tb.promise)
    const picker = vm.openRefPicker(oldRow)
    mockGet.mockResolvedValueOnce(listing('同代重载'))
    expect(await vm.loadFormulas()).toBe(true); expect(vm.formulas[0]).not.toBe(oldRow)
    report.resolve([{ name: '已被替换行的报表' }]); tb.resolve({ rows: [{ standard_account_code: '1001', audited_amount: '0' }] })
    await picker
    expect(vm.showRefPicker).toBe(false)
    expect(vm.refPickerData).toEqual({ reportRows: [], tbRows: [], noteRows: [] })
    expectListing(vm, listing('同代重载'))
    expect(mockPut).not.toHaveBeenCalled(); expectNoFeedback(); w.unmount()
  })

  it('同代切换引用编辑行，仅最后选中的行可以接收取数结果', async () => {
    const w = mountDialog(); await openDialog(w)
    const vm = w.vm as any, oldReport = deferred<any>(), oldTb = deferred<any>(), firstRow = vm.formulas[0]
    vm.addFormula(); const secondRow = vm.formulas[1]
    mockGet.mockReturnValueOnce(oldReport.promise).mockResolvedValueOnce([{ name: '第二行报表' }])
    mockFetchTrialRows.mockReturnValueOnce(oldTb.promise).mockResolvedValueOnce({ rows: [{ standard_account_code: '第二行科目' }] })
    const firstWork = vm.openRefPicker(firstRow); await vm.openRefPicker(secondRow)
    expect(vm.editingRow).toBe(secondRow); expect(vm.showRefPicker).toBe(true)
    oldReport.resolve([{ name: '第一行旧报表' }]); oldTb.resolve({ rows: [{ standard_account_code: '第一行旧科目' }] })
    await firstWork
    expect(vm.editingRow).toBe(secondRow)
    expect(vm.refPickerData.reportRows).toEqual([{ name: '第二行报表' }])
    expect(vm.refPickerData.tbRows).toEqual([{ standard_account_code: '第二行科目' }])
    expect(mockPut).not.toHaveBeenCalled(); w.unmount()
  })
})