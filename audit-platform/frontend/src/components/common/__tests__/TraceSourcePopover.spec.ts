import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import TraceSourcePopover from '../TraceSourcePopover.vue'
import type { TraceSourceData } from '../TraceSourcePopover.vue'

// Mock vue-router (useNavigationStack depends on it)
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useRoute: () => ({ params: { projectId: 'proj-001' } }),
}))

const sampleTraceData: TraceSourceData = {
  source_type: 'report_line',
  report_line: {
    line_code: 'BS-001',
    item_name: '货币资金',
    amount: 5000000,
  },
  tb_accounts: [
    { code: '1001', name: '库存现金', closing_balance: 50000, pct: 1.0 },
    { code: '1002', name: '银行存款', closing_balance: 4950000, pct: 99.0 },
  ],
}

describe('TraceSourcePopover', () => {
  const mountPopover = (props: Record<string, unknown> = {}) => {
    return mount(TraceSourcePopover, {
      props: {
        traceData: sampleTraceData,
        visible: true,
        loading: false,
        ...props,
      },
      slots: {
        default: '<span class="trigger">点击</span>',
      },
      global: {
        stubs: {
          'el-popover': {
            template: '<div class="el-popover-stub"><slot name="reference" /><slot /></div>',
            props: ['visible', 'trigger', 'placement', 'width', 'popperClass'],
          },
          'el-button': {
            template: '<button class="el-button-stub" @click="$emit(\'click\')"><slot /></button>',
            emits: ['click'],
          },
          'el-icon': {
            template: '<i class="el-icon-stub"><slot /></i>',
          },
        },
      },
    })
  }

  it('renders slot content as trigger', () => {
    const wrapper = mountPopover()
    expect(wrapper.find('.trigger').exists()).toBe(true)
    expect(wrapper.find('.trigger').text()).toBe('点击')
  })

  it('shows loading state when loading=true', () => {
    const wrapper = mountPopover({ loading: true })
    expect(wrapper.find('.gt-trace-loading').exists()).toBe(true)
    expect(wrapper.text()).toContain('加载来源数据')
  })

  it('shows empty state when traceData is null', () => {
    const wrapper = mountPopover({ traceData: null, loading: false })
    expect(wrapper.find('.gt-trace-empty').exists()).toBe(true)
    expect(wrapper.text()).toContain('暂无来源数据')
  })

  it('shows empty state when report_line is null', () => {
    const wrapper = mountPopover({
      traceData: { source_type: 'report_line', report_line: null, tb_accounts: [] },
      loading: false,
    })
    expect(wrapper.find('.gt-trace-empty').exists()).toBe(true)
  })

  it('renders report line info correctly', () => {
    const wrapper = mountPopover()
    expect(wrapper.text()).toContain('来源报表行')
    expect(wrapper.text()).toContain('货币资金')
    expect(wrapper.text()).toContain('¥5,000,000.00')
  })

  it('renders tb_accounts list with code, name, amount, pct', () => {
    const wrapper = mountPopover()
    expect(wrapper.text()).toContain('构成科目')
    // Account 1
    expect(wrapper.text()).toContain('1001')
    expect(wrapper.text()).toContain('库存现金')
    expect(wrapper.text()).toContain('¥50,000.00')
    expect(wrapper.text()).toContain('1.0%')
    // Account 2
    expect(wrapper.text()).toContain('1002')
    expect(wrapper.text()).toContain('银行存款')
    expect(wrapper.text()).toContain('¥4,950,000.00')
    expect(wrapper.text()).toContain('99.0%')
  })

  it('renders jump-to-tb button', () => {
    const wrapper = mountPopover()
    expect(wrapper.text()).toContain('跳转到试算表')
  })

  it('emits jump-to-tb with first account code when button clicked', async () => {
    const wrapper = mountPopover()
    const btn = wrapper.find('.el-button-stub')
    await btn.trigger('click')
    expect(wrapper.emitted('jump-to-tb')).toBeTruthy()
    expect(wrapper.emitted('jump-to-tb')![0]).toEqual(['1001'])
  })

  it('emits jump-to-tb with undefined when no accounts', async () => {
    const wrapper = mountPopover({
      traceData: {
        source_type: 'report_line',
        report_line: { line_code: 'BS-001', item_name: '货币资金', amount: 5000000 },
        tb_accounts: [],
      },
    })
    const btn = wrapper.find('.el-button-stub')
    await btn.trigger('click')
    expect(wrapper.emitted('jump-to-tb')![0]).toEqual([undefined])
  })

  it('uses .gt-amt class for amount columns', () => {
    const wrapper = mountPopover()
    const amtElements = wrapper.findAll('.gt-amt')
    // report_line amount + each account code + each account amount = 1 + 2 + 2 = 5
    expect(amtElements.length).toBeGreaterThanOrEqual(3)
  })

  it('does not show accounts section when tb_accounts is empty', () => {
    const wrapper = mountPopover({
      traceData: {
        source_type: 'report_line',
        report_line: { line_code: 'BS-001', item_name: '货币资金', amount: 5000000 },
        tb_accounts: [],
      },
    })
    expect(wrapper.find('.gt-trace-accounts').exists()).toBe(false)
  })
})
