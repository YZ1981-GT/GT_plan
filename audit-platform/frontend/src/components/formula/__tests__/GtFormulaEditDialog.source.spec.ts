/**
 * GtFormulaEditDialog.source.spec.ts — 三来源选择流 示例测试
 *
 * spec formula-management-library Task 21.2（Req 25.1-25.6）
 *
 * 覆盖（不得假绿）：
 *  ① 三来源可选（Req 25.1）—— preset / custom / reference 三个来源单选按钮均渲染
 *  ② reference 选源公式后保存带 reference_formula_id（Req 25.5）——
 *     选中参照源公式 → 复用其表达式 → 提交 payload 携带 reference_formula_id + formula_source='reference'
 *  ③ custom 恢复预设调 restore 端点（Req 25.4）——
 *     custom 覆盖 + cellKey → 「恢复预设」按钮 → 调 sourceApi.restorePreset → emit restore-preset
 *  ④ formula_source 回显（Req 25.6）—— initial.formula_source 打开时回显到表单
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'

if (!(globalThis as any).ResizeObserver) {
  ;(globalThis as any).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

// ─── Hoisted mock fns（不引用 vue，用轻量 fake-ref 规避 hoist 时序） ────────────
const {
  mockResolveFormula,
  mockMsgError,
  mockMsgSuccess,
  mockRestorePreset,
  mockLoadCandidates,
  candidatesRef,
} = vi.hoisted(() => {
  const holder = { items: [] as any[] }
  // 轻量 fake-ref：组件只读/写 `.value`，getter/setter 足以模拟 Vue ref
  const candidatesRef = {
    get value() {
      return holder.items
    },
    set value(v: any[]) {
      holder.items = v
    },
  }
  return {
    mockResolveFormula: vi.fn(),
    mockMsgError: vi.fn(),
    mockMsgSuccess: vi.fn(),
    mockRestorePreset: vi.fn(),
    mockLoadCandidates: vi.fn(),
    candidatesRef,
  }
})

vi.mock('@/services/acnr/useAcnr', () => ({
  useAcnr: () => ({ resolveFormula: mockResolveFormula }),
}))

vi.mock('../useFormulaSource', () => ({
  useFormulaSource: () => ({
    candidates: candidatesRef,
    candidatesLoading: { value: false },
    restoring: { value: false },
    loadReferenceCandidates: mockLoadCandidates,
    restorePreset: mockRestorePreset,
  }),
}))

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<typeof import('element-plus')>()
  return {
    ...actual,
    ElMessage: { error: mockMsgError, success: mockMsgSuccess, warning: vi.fn(), info: vi.fn() },
  }
})

import ElementPlus from 'element-plus'
import GtFormulaEditDialog from '../GtFormulaEditDialog.vue'

// ─── Stubs ────────────────────────────────────────────────────────────────────
const ElDialogStub = defineComponent({
  name: 'ElDialog',
  props: { modelValue: { type: Boolean, default: false }, title: { type: String, default: '' } },
  template: '<div class="el-dialog-stub"><slot /><slot name="footer" /></div>',
})
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
const ElInputStub = defineComponent({
  name: 'ElInput',
  props: { modelValue: { type: [String, Number], default: '' } },
  emits: ['update:modelValue'],
  template:
    '<textarea class="el-input-stub" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
})
const ElSelectStub = defineComponent({
  name: 'ElSelect',
  props: { modelValue: { type: [String, Number, Object], default: null } },
  emits: ['update:modelValue', 'change'],
  template: '<div class="el-select-stub"><slot /></div>',
})
const ElOptionStub = defineComponent({
  name: 'ElOption',
  props: { value: { type: [String, Number, Object], default: null }, label: { type: String, default: '' } },
  template: '<div class="el-option-stub">{{ label }}</div>',
})

const STUBS = {
  ElDialog: ElDialogStub,
  FormulaRefPicker: FormulaRefPickerStub,
  ElInput: ElInputStub,
  ElSelect: ElSelectStub,
  ElOption: ElOptionStub,
} as const

function mountDialog(props: Record<string, unknown> = {}): VueWrapper {
  return mount(GtFormulaEditDialog, {
    props: { modelValue: false, scope: 'workpaper', ...props },
    global: { plugins: [ElementPlus], stubs: STUBS },
  })
}

async function openDialog(wrapper: VueWrapper) {
  await wrapper.setProps({ modelValue: true })
  await flushPromises()
  await nextTick()
}

// ══════════════════════════════════════════════════════════════════════════════
describe('GtFormulaEditDialog — 三来源选择流（Req 25.1-25.6）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockResolveFormula.mockResolvedValue({ found: true })
    mockRestorePreset.mockResolvedValue(true)
    candidatesRef.value = []
  })

  // ── ① 三来源可选（Req 25.1） ────────────────────────────────────────────────
  it('渲染 preset / custom / reference 三个可选来源', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)

    const text = wrapper.text()
    expect(text).toContain('预设')
    expect(text).toContain('自定义')
    expect(text).toContain('参照已有')
    // 默认来源 custom
    expect((wrapper.vm as any).form.formula_source).toBe('custom')
    wrapper.unmount()
  })

  // ── ④ formula_source 回显（Req 25.6） ───────────────────────────────────────
  it('打开时按 initial.formula_source 回显来源（preset）', async () => {
    const wrapper = mountDialog({
      initial: { formula_type: 'auto_calc', expression: "TB('1001')", formula_source: 'preset' },
    })
    await openDialog(wrapper)
    expect((wrapper.vm as any).form.formula_source).toBe('preset')
    wrapper.unmount()
  })

  it('打开时按 initial.formula_source 回显来源（reference）并回显 reference_formula_id', async () => {
    const wrapper = mountDialog({
      wpId: 'wp-1',
      initial: {
        formula_type: 'auto_calc',
        expression: "TB('1001')",
        formula_source: 'reference',
        reference_formula_id: 'f9',
      },
    })
    await openDialog(wrapper)
    expect((wrapper.vm as any).form.formula_source).toBe('reference')
    expect((wrapper.vm as any).form.reference_formula_id).toBe('f9')
    // reference 来源 + wpId → 懒加载候选源公式
    expect(mockLoadCandidates).toHaveBeenCalledWith('wp-1')
    wrapper.unmount()
  })

  // ── ② reference 选源公式后保存带 reference_formula_id（Req 25.5） ────────────
  it('reference 选中参照源公式 → 复用表达式 + 提交携带 reference_formula_id', async () => {
    candidatesRef.value = [
      { id: 'src-1', sheet_name: '审定表', target_cell: 'B7', expression: "TB('1001','审定数')", formula_type: 'auto_calc' },
    ]
    const wrapper = mountDialog({ wpId: 'wp-1' })
    await openDialog(wrapper)

    // 切到 reference 来源
    ;(wrapper.vm as any).form.formula_source = 'reference'
    await nextTick()

    // 选中参照源公式（等价于 el-select change）
    ;(wrapper.vm as any).onSelectReference('src-1')
    await nextTick()

    // 复用源公式表达式
    expect((wrapper.vm as any).form.expression).toBe("TB('1001','审定数')")
    expect((wrapper.vm as any).form.reference_formula_id).toBe('src-1')

    await (wrapper.vm as any).onSubmit()
    await flushPromises()

    const saved = wrapper.emitted('save')
    expect(saved).toBeTruthy()
    const payload = saved![0][0] as any
    expect(payload.formula_source).toBe('reference')
    expect(payload.reference_formula_id).toBe('src-1')
    expect(payload.expression).toBe("TB('1001','审定数')")
    wrapper.unmount()
  })

  it('非 reference 来源提交时 reference_formula_id 归空', async () => {
    const wrapper = mountDialog()
    await openDialog(wrapper)
    ;(wrapper.vm as any).form.formula_source = 'custom'
    ;(wrapper.vm as any).form.expression = "TB('1001')"
    await nextTick()

    await (wrapper.vm as any).onSubmit()
    await flushPromises()

    const payload = wrapper.emitted('save')![0][0] as any
    expect(payload.formula_source).toBe('custom')
    expect(payload.reference_formula_id).toBeNull()
    wrapper.unmount()
  })

  // ── ③ custom 恢复预设调 restore 端点（Req 25.4） ─────────────────────────────
  it('custom 覆盖 + cellKey + isPresetOverride → 显示「恢复预设」按钮', async () => {
    const wrapper = mountDialog({
      wpId: 'wp-1',
      cellKey: '审定表!B7',
      isPresetOverride: true,
      initial: { formula_source: 'custom', expression: "TB('1001')" },
    })
    await openDialog(wrapper)
    expect((wrapper.vm as any).showRestorePreset).toBe(true)
    const btn = wrapper.findAll('button').find((b) => b.text().includes('恢复预设'))
    expect(btn).toBeTruthy()
    wrapper.unmount()
  })

  it('点击「恢复预设」→ 调 restorePreset(restore 端点) 并 emit restore-preset', async () => {
    const wrapper = mountDialog({
      wpId: 'wp-1',
      cellKey: '审定表!B7',
      isPresetOverride: true,
      initial: { formula_source: 'custom', expression: "TB('1001')" },
    })
    await openDialog(wrapper)

    await (wrapper.vm as any).onRestorePreset()
    await flushPromises()

    expect(mockRestorePreset).toHaveBeenCalledWith('wp-1', '审定表!B7')
    expect(mockMsgSuccess).toHaveBeenCalled()
    const restored = wrapper.emitted('restore-preset')
    expect(restored).toBeTruthy()
    expect(restored![0][0]).toBe('审定表!B7')
    wrapper.unmount()
  })

  it('非预设覆盖 → 不显示「恢复预设」按钮', async () => {
    const wrapper = mountDialog({
      wpId: 'wp-1',
      cellKey: '审定表!B7',
      isPresetOverride: false,
      initial: { formula_source: 'custom' },
    })
    await openDialog(wrapper)
    expect((wrapper.vm as any).showRestorePreset).toBe(false)
    wrapper.unmount()
  })
})
