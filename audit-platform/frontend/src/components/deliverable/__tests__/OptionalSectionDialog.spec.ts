/**
 * OptionalSectionDialog 前端测试
 * Validates: Requirements 4.3, 4.8, 4.9, 4.11
 *
 * 覆盖：
 * - 勾选默认逻辑（default_keep 被尊重；initialSelections 优先）
 * - missing_fields 不阻断 confirm（confirm 仍 emit，即使有缺失字段）
 * - 按 group 分组渲染
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import OptionalSectionDialog from '../OptionalSectionDialog.vue'
import type { OptionalSection } from '@/services/deliverableApi'

const stubs = {
  'el-dialog': {
    template: '<div class="dialog"><slot /><slot name="footer" /></div>',
    props: ['modelValue', 'title'],
  },
  'el-alert': {
    template: '<div class="alert"><slot name="title" /></div>',
    props: ['type', 'closable', 'showIcon'],
  },
  'el-tag': { template: '<span class="tag"><slot /></span>' },
  'el-empty': { template: '<div class="empty"></div>', props: ['description'] },
  'el-checkbox': {
    template: '<label class="checkbox" @click="$emit(\'update:modelValue\', !modelValue)"><slot /></label>',
    props: ['modelValue'],
  },
  'el-button': {
    template: '<button @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'link', 'loading', 'size'],
  },
}

const SECTIONS: OptionalSection[] = [
  { section_id: 'emphasis', description: '强调事项段', preview: '我们提醒...', default_keep: false, group: '报告正文段落' },
  { section_id: 'key_audit_matters', description: '关键审计事项段', preview: 'KAM 预览', default_keep: true, group: '报告正文段落' },
  { section_id: 'comparative', description: '比较数据段', preview: '比较预览', default_keep: true, group: '补充信息段落' },
]

function mountDialog(props: Record<string, any> = {}) {
  return mount(OptionalSectionDialog, {
    props: {
      visible: true,
      optionalSections: SECTIONS,
      ...props,
    },
    global: { stubs },
  })
}

describe('OptionalSectionDialog', () => {
  let wrapper: ReturnType<typeof mountDialog>

  beforeEach(() => {
    wrapper = mountDialog()
  })

  it('honors default_keep for initial selections', () => {
    const vm = wrapper.vm as any
    expect(vm.selections.emphasis).toBe(false)
    expect(vm.selections.key_audit_matters).toBe(true)
    expect(vm.selections.comparative).toBe(true)
  })

  it('prefers initialSelections (上次勾选) over default_keep when provided', () => {
    const w = mountDialog({
      initialSelections: { emphasis: true, key_audit_matters: false },
    })
    const vm = w.vm as any
    // 上次选择覆盖 default_keep
    expect(vm.selections.emphasis).toBe(true)
    expect(vm.selections.key_audit_matters).toBe(false)
    // 无上次记录的回退 default_keep
    expect(vm.selections.comparative).toBe(true)
  })

  it('groups sections by group field', () => {
    const vm = wrapper.vm as any
    expect(vm.groups.length).toBe(2)
    expect(vm.groups[0].name).toBe('报告正文段落')
    expect(vm.groups[0].items.map((i: OptionalSection) => i.section_id)).toEqual(['emphasis', 'key_audit_matters'])
    expect(vm.groups[1].name).toBe('补充信息段落')
    expect(vm.groups[1].items.map((i: OptionalSection) => i.section_id)).toEqual(['comparative'])
  })

  it('emits confirm with current selections', () => {
    const vm = wrapper.vm as any
    vm.onConfirm()
    const emitted = wrapper.emitted('confirm')
    expect(emitted).toBeTruthy()
    expect(emitted![0][0]).toEqual({
      emphasis: false,
      key_audit_matters: true,
      comparative: true,
    })
  })

  it('does NOT block confirm when missing_fields is non-empty', () => {
    const w = mountDialog({ missingFields: ['signing_partner', 'report_date'] })
    const vm = w.vm as any
    // 警告条展示，但 confirm 仍可触发并 emit
    expect(vm.missingFields).toEqual(['signing_partner', 'report_date'])
    vm.onConfirm()
    const emitted = w.emitted('confirm')
    expect(emitted).toBeTruthy()
    expect(emitted!.length).toBe(1)
  })

  it('emits cancel on cancel (does not confirm)', () => {
    const vm = wrapper.vm as any
    vm.onCancel()
    expect(wrapper.emitted('cancel')).toBeTruthy()
    expect(wrapper.emitted('confirm')).toBeFalsy()
  })

  it('renders empty state when no optional sections', () => {
    const w = mountDialog({ optionalSections: [] })
    const vm = w.vm as any
    expect(vm.groups.length).toBe(0)
  })
})
