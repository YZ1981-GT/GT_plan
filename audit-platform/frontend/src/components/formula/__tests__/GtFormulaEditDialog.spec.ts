/**
 * GtFormulaEditDialog.spec.ts — 三类型统一公式编辑弹窗 示例测试
 *
 * spec formula-management-library Task 12.4（组件由 Task 12.1 实现）
 *
 * 覆盖（**Validates: Requirements 8.1, 8.2, 8.3, 8.4**）：
 *  1. 三类型可选（Req 8.1）—— auto_calc / logic_check / reasonability 三个单选按钮均可选
 *  2. 类型差异字段条件渲染（Req 8.2）——
 *       auto_calc → 目标单元 + 计算表达式；
 *       logic_check → 判断条件 + 问题描述；
 *       reasonability → 触发条件 + 提示文案
 *  3. 选址器数据源为 ACNR（Req 8.3）—— 挂载 FormulaRefPicker 并接收候选地址；
 *       插入引用登记到 refs/表达式；提交校验经 useAcnr.resolveFormula（ACNR full_resolve）
 *  4. 悬空提交不保存（Req 8.4）—— resolveFormula found=false → ElMessage.error 且不 emit save
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
const { mockResolveFormula, mockMsgError, mockMsgSuccess } = vi.hoisted(() => ({
  mockResolveFormula: vi.fn(),
  mockMsgError: vi.fn(),
  mockMsgSuccess: vi.fn(),
}))

// ─── Mock useAcnr（受控 resolveFormula = ACNR full_resolve 校验路径） ───────────
vi.mock('@/services/acnr/useAcnr', () => ({
  useAcnr: () => ({ resolveFormula: mockResolveFormula }),
}))

// ─── Mock ElMessage（断言 error/success 调用；保留其余真实导出） ────────────────
vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<typeof import('element-plus')>()
  return {
    ...actual,
    ElMessage: { error: mockMsgError, success: mockMsgSuccess, warning: vi.fn(), info: vi.fn() },
  }
})

// ─── Import after mocks ───────────────────────────────────────────────────────
import ElementPlus from 'element-plus'
import GtFormulaEditDialog from '../GtFormulaEditDialog.vue'

// ─── Fixtures：ACNR 选址器候选地址（模拟 store/props 供给的三域行数据） ─────────
const REPORT_ROWS = [{ row_code: 'BS-001', row_name: '货币资金' }]
const TB_ROWS = [{ standard_account_code: '1001', account_name: '库存现金' }]
const NOTE_ROWS = [{ note_section: '五、1', section_title: '货币资金' }]

// ─── Stubs ────────────────────────────────────────────────────────────────────
// ElDialog：渲染 default + footer 插槽内联（避免 teleport 到 body 后测试不可见）
const ElDialogStub = defineComponent({
  name: 'ElDialog',
  props: { modelValue: { type: Boolean, default: false }, title: { type: String, default: '' } },
  template: '<div class="el-dialog-stub"><slot /><slot name="footer" /></div>',
})

// FormulaRefPicker：可捕获 props（验证 ACNR 候选地址透传）并可主动 emit insert
const FormulaRefPickerStub = defineComponent({
  name: 'FormulaRefPicker',
  props: {
    modelValue: { type: Boolean, default: false },
    reportRows: { type: Array, default: () => [] },
    tbRows: { type: Array, default: () => [] },
    noteRows: { type: Array, default: () => [] },
  },
  emits: ['update:modelValue', 'insert'],
  template: '<div class="formula-ref-picker-stub" />',
})

// ElInput：轻量 stub，规避 el-textarea autosize 在 jsdom 下访问 offsetHeight(null) 的
// 未处理拒绝；表单值经 vm.form 读写、字段可见性经 el-form-item label 判定，均不依赖真实输入框。
const ElInputStub = defineComponent({
  name: 'ElInput',
  props: { modelValue: { type: [String, Number], default: '' } },
  emits: ['update:modelValue'],
  template:
    '<textarea class="el-input-stub" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
})

const STUBS = {
  ElDialog: ElDialogStub,
  FormulaRefPicker: FormulaRefPickerStub,
  ElInput: ElInputStub,
} as const

function mountDialog(props: Record<string, unknown> = {}): VueWrapper {
  return mount(GtFormulaEditDialog, {
    props: {
      modelValue: false,
      scope: 'workpaper',
      reportRows: REPORT_ROWS,
      tbRows: TB_ROWS,
      noteRows: NOTE_ROWS,
      ...props,
    },
    global: { plugins: [ElementPlus], stubs: STUBS },
  })
}

/** 打开弹窗（modelValue false→true）→ 触发 watch 初始化表单 */
async function openDialog(wrapper: VueWrapper) {
  await wrapper.setProps({ modelValue: true })
  await flushPromises()
  await nextTick()
}

/** 切换公式类型并等待条件渲染更新 */
async function setType(wrapper: VueWrapper, type: 'auto_calc' | 'logic_check' | 'reasonability') {
  ;(wrapper.vm as any).form.formula_type = type
  await nextTick()
}

// ══════════════════════════════════════════════════════════════════════════════
describe('GtFormulaEditDialog — 三类型统一编辑弹窗（Req 8.1/8.2/8.3/8.4）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // 默认校验通过（found=true）
    mockResolveFormula.mockResolvedValue({ found: true })
  })

  // ── 1. 三类型可选（Req 8.1） ────────────────────────────────────────────────
  it('渲染 auto_calc / logic_check / reasonability 三个可选类型', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)

    // 弹窗含「公式来源」(3) + 「公式类型」(3) 两组 radio-button；此处校验类型三项齐全
    const radios = wrapper.findAll('.el-radio-button')
    expect(radios.length).toBeGreaterThanOrEqual(3)
    const text = wrapper.text()
    expect(text).toContain('自动运算')
    expect(text).toContain('逻辑判断')
    expect(text).toContain('合理性提示')

    // 默认类型 auto_calc
    expect((wrapper.vm as any).form.formula_type).toBe('auto_calc')
    wrapper.unmount()
  })

  // ── 2. 类型差异字段条件渲染（Req 8.2） ──────────────────────────────────────
  it('auto_calc 显示目标单元 + 计算表达式，隐藏问题描述/提示文案', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)
    await setType(wrapper, 'auto_calc')

    const text = wrapper.text()
    expect(text).toContain('目标单元')
    expect(text).toContain('计算表达式')
    // 其他类型专属字段不渲染
    expect(text).not.toContain('问题描述')
    expect(text).not.toContain('提示文案')
    wrapper.unmount()
  })

  it('logic_check 显示判断条件 + 问题描述，隐藏计算表达式/提示文案', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)
    await setType(wrapper, 'logic_check')

    const text = wrapper.text()
    expect(text).toContain('判断条件')
    expect(text).toContain('问题描述')
    expect(text).not.toContain('计算表达式')
    expect(text).not.toContain('提示文案')
    wrapper.unmount()
  })

  it('reasonability 显示触发条件 + 提示文案，隐藏计算表达式/问题描述', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)
    await setType(wrapper, 'reasonability')

    const text = wrapper.text()
    expect(text).toContain('触发条件')
    expect(text).toContain('提示文案')
    expect(text).not.toContain('计算表达式')
    expect(text).not.toContain('问题描述')
    wrapper.unmount()
  })

  // ── 3. 选址器数据源为 ACNR（Req 8.3） ───────────────────────────────────────
  it('挂载 FormulaRefPicker 并透传 ACNR 候选地址（report/tb/note 三域）', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)

    const picker = wrapper.findComponent(FormulaRefPickerStub)
    expect(picker.exists()).toBe(true)
    expect(picker.props('reportRows')).toEqual(REPORT_ROWS)
    expect(picker.props('tbRows')).toEqual(TB_ROWS)
    expect(picker.props('noteRows')).toEqual(NOTE_ROWS)
    wrapper.unmount()
  })

  it('点击"插入引用"打开选址器；选址器 insert 事件登记引用到 refs 与表达式', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)
    await setType(wrapper, 'auto_calc')

    // 点击插入引用按钮 → 打开选址器
    const pickBtn = wrapper.findAll('button').find((b) => b.text().includes('插入引用'))
    expect(pickBtn).toBeTruthy()
    await pickBtn!.trigger('click')
    expect((wrapper.vm as any).showRefPicker).toBe(true)

    // 选址器（ACNR 数据源）emit insert → 组件登记引用
    const picker = wrapper.findComponent(FormulaRefPickerStub)
    picker.vm.$emit('insert', "TB('1001','审定数')")
    await nextTick()

    expect((wrapper.vm as any).refs).toContain("TB('1001','审定数')")
    expect((wrapper.vm as any).form.expression).toContain("TB('1001','审定数')")
    wrapper.unmount()
  })

  it('提交时经 useAcnr.resolveFormula（ACNR full_resolve）校验引用', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)
    await setType(wrapper, 'auto_calc')
    ;(wrapper.vm as any).form.expression = "TB('1001','审定数')"
    await nextTick()

    await (wrapper.vm as any).onSubmit()
    await flushPromises()

    expect(mockResolveFormula).toHaveBeenCalledWith("TB('1001','审定数')")
    wrapper.unmount()
  })

  // ── 4. 悬空提交不保存（Req 8.4） ────────────────────────────────────────────
  it('悬空引用（resolveFormula found=false）→ ElMessage.error 且不 emit save', async () => {
    mockResolveFormula.mockResolvedValue({ found: false })
    const wrapper = mountDialog()
    await openDialog(wrapper)
    await setType(wrapper, 'auto_calc')
    ;(wrapper.vm as any).form.expression = "TB('9999','审定数')"
    await nextTick()

    await (wrapper.vm as any).onSubmit()
    await flushPromises()

    expect(mockMsgError).toHaveBeenCalled()
    expect(wrapper.emitted('save')).toBeFalsy()
    // 弹窗未关闭（未 emit update:modelValue=false）
    const closeEvents = (wrapper.emitted('update:modelValue') || []).filter((e) => e[0] === false)
    expect(closeEvents).toHaveLength(0)
    wrapper.unmount()
  })

  it('引用全部有效（found=true）→ emit save 携带规范化载荷并关闭弹窗', async () => {
    mockResolveFormula.mockResolvedValue({ found: true })
    const wrapper = mountDialog()
    await openDialog(wrapper)
    await setType(wrapper, 'auto_calc')
    ;(wrapper.vm as any).form.target_cell = 'BS-027·期末'
    ;(wrapper.vm as any).form.expression = "TB('1001','审定数')"
    await nextTick()

    await (wrapper.vm as any).onSubmit()
    await flushPromises()

    const saved = wrapper.emitted('save')
    expect(saved).toBeTruthy()
    const payload = saved![0][0] as any
    expect(payload.formula_type).toBe('auto_calc')
    expect(payload.target_cell).toBe('BS-027·期末')
    expect(payload.expression).toBe("TB('1001','审定数')")
    expect(payload.refs).toContain("TB('1001','审定数')")
    // 弹窗关闭
    const closeEvents = (wrapper.emitted('update:modelValue') || []).filter((e) => e[0] === false)
    expect(closeEvents.length).toBeGreaterThan(0)
    wrapper.unmount()
  })
})
