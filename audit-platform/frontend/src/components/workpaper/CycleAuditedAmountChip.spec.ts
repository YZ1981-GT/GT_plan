import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CycleAuditedAmountChip from './CycleAuditedAmountChip.vue'
import GtAProgramLinkedChips from './GtAProgramLinkedChips.vue'
import { clearCycleAuditedAmountsCache } from './composables/useCycleAuditedAmounts'

const mockGet = vi.fn()
const mockPost = vi.fn()
const mockPut = vi.fn()
const mockPatch = vi.fn()
const mockDelete = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    put: (...args: unknown[]) => mockPut(...args),
    patch: (...args: unknown[]) => mockPatch(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
  },
}))

vi.mock('@/components/workpaper/GtIndexChip.vue', () => ({
  default: defineComponent({
    name: 'GtIndexChipStub',
    props: ['value', 'label', 'wpCode', 'target', 'validate', 'contextProjectId', 'preventNavigate', 'disabled', 'context', 'title'],
    emits: ['click'],
    template: '<button data-testid="index-chip">{{ value || wpCode || target || label }}</button>',
  }),
}))

const PopoverStub = defineComponent({
  name: 'ElPopoverStub',
  emits: ['show'],
  template: `
    <div data-testid="cycle-popover" @mouseenter="$emit('show')">
      <div data-testid="cycle-popover-reference"><slot name="reference" /></div>
      <div data-testid="cycle-popover-content"><slot /></div>
    </div>
  `,
})

const response = {
  summary: '资产 1,234.50 / 负债 200.00 / 收入 88.00',
  asset_total: 1234.5,
  liability_total: 200,
  equity_total: 30,
  revenue_total: 88,
  expense_total: 66.25,
}

function mountChip(props: Record<string, unknown>) {
  return mount(CycleAuditedAmountChip, {
    props,
    global: { stubs: { 'el-popover': PopoverStub } },
  })
}

describe('CycleAuditedAmountChip — S34/S35 外部 chip 只读联动', () => {
  beforeEach(() => {
    clearCycleAuditedAmountsCache()
    vi.clearAllMocks()
    mockGet.mockResolvedValue(response)
  })

  it.each([
    { cycleCode: 'S34' as const, value: 'D4-24', projectId: 'project-s34' },
    { cycleCode: 'S35' as const, value: 'B23-1', projectId: 'project-s35' },
  ])('悬停 $cycleCode 外部 chip 请求 registry resolver 并显示只读审定值', async ({ cycleCode, value, projectId }) => {
    const wrapper = mountChip({ cycleCode, value, projectId, year: 2025 })

    expect(wrapper.get('[data-testid="cycle-popover"]').exists()).toBe(true)
    await wrapper.get('[data-testid="cycle-popover"]').trigger('mouseenter')
    await flushPromises()

    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(mockGet).toHaveBeenCalledWith(
      `/api/projects/${projectId}/auto-data/cycle_audited_amounts`,
      { params: { year: 2025 }, _silent: true },
    )
    expect(wrapper.text()).toContain(`${cycleCode} 外部引用（只读审定/TB）`)
    expect(wrapper.text()).toContain('资产审定数')
    expect(wrapper.text()).toContain('1,234.50')
    expect(wrapper.text()).toContain('收入审定数')
  })

  it('内部 S34 chip 不请求外部审定额 resolver', async () => {
    const wrapper = mountChip({ cycleCode: 'S34', value: 'S34-3', projectId: 'project-s34', year: 2025 })

    expect(wrapper.find('[data-testid="cycle-popover"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="index-chip"]').text()).toContain('S34-3')
    await flushPromises()
    expect(mockGet).not.toHaveBeenCalled()
  })

  it('hover 合约只允许 GET，不写目标底稿或 trial_balance', async () => {
    const wrapper = mountChip({ cycleCode: 'S35', value: 'D4-24', projectId: 'project-s35', year: 2025 })
    await wrapper.get('[data-testid="cycle-popover"]').trigger('mouseenter')
    await flushPromises()

    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(mockPost).not.toHaveBeenCalled()
    expect(mockPut).not.toHaveBeenCalled()
    expect(mockPatch).not.toHaveBeenCalled()
    expect(mockDelete).not.toHaveBeenCalled()
    expect(mockGet.mock.calls[0][0]).not.toContain('trial-balance')
    expect(mockGet.mock.calls[0][0]).not.toContain('checklist-responses')
  })
})

const CycleChipStub = defineComponent({
  name: 'CycleAuditedAmountChip',
  props: ['value', 'cycleCode', 'projectId', 'year'],
  template: '<span data-testid="wired-cycle-chip">{{ value }}</span>',
})

describe('GtAProgramLinkedChips S34/S35 接线', () => {
  it('把真实外部关联值和项目/年度上下文传给只读 chip', () => {
    const wrapper = mount(GtAProgramLinkedChips, {
      props: {
        row: { linked_workpapers: 'D4-24' },
        inlinePopupWpCodes: new Set<string>(),
        popupCompletionStatus: {},
        a16RecommendedCode: '',
        a16OtherVersions: [],
        a16Expanded: false,
        a17Expanded: false,
        isA16Seq2Row: () => false,
        isRowChipDisabled: () => false,
        isA17Seq5Row: () => false,
        a17ApplicableRefs: () => [],
        a17InapplicableRefs: () => [],
        parseLinkedWorkpapers: (value: string) => value.split('/'),
        reviewChipDisplayValue: (value: string) => value,
        isA17_5ChipDisabled: () => false,
        isReviewChipDisabled: () => false,
        a17_5Badge: () => '',
        reviewChipBadge: () => '',
        chipCompletionKey: (value: string) => value,
        cycleCode: 'S35',
        projectId: 'project-s35',
        cycleAuditYear: 2025,
      },
      global: { stubs: { CycleAuditedAmountChip: CycleChipStub } },
    })

    expect(wrapper.get('[data-testid="wired-cycle-chip"]').text()).toBe('D4-24')
    const chip = wrapper.findComponent(CycleChipStub)
    expect(chip.props('cycleCode')).toBe('S35')
    expect(chip.props('projectId')).toBe('project-s35')
    expect(chip.props('year')).toBe(2025)
  })
})
