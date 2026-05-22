/**
 * ReviewChainConfig unit tests
 * Validates: Requirements F8.3, F8.4, F8.9, F8.10
 *
 * Tests: render / level switch / save emit / disabled state
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('@/utils/http', () => ({
  default: {
    put: vi.fn(),
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
}))

import http from '@/utils/http'
import ReviewChainConfig from '@/components/ReviewChainConfig.vue'

const defaultStubs = {
  'el-alert': { template: '<div class="el-alert"><slot name="title" /></div>' },
  'el-select': {
    template: '<select :disabled="disabled" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>',
    props: ['modelValue', 'disabled', 'filterable', 'placeholder'],
  },
  'el-option': { template: '<option :value="value">{{ label }}</option>', props: ['value', 'label'] },
  'el-button': {
    template: '<button :disabled="disabled" :class="{ loading }" @click="$emit(\'click\')"><slot /></button>',
    props: ['disabled', 'loading', 'type'],
  },
  'el-tooltip': { template: '<div><slot /></div>', props: ['disabled', 'content', 'placement'] },
}

describe('ReviewChainConfig', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders with default 2-level config', () => {
    const wrapper = mount(ReviewChainConfig, {
      props: {
        projectId: 'proj-1',
        currentConfig: null,
      },
      global: { stubs: defaultStubs },
    })

    expect(wrapper.exists()).toBe(true)
    expect(wrapper.text()).toContain('复核链配置')
  })

  it('renders with provided 3-level config', () => {
    const wrapper = mount(ReviewChainConfig, {
      props: {
        projectId: 'proj-1',
        currentConfig: {
          levels: 3,
          level_roles: { L1: 'manager', L2: 'partner', L3: 'eqcr' },
        },
      },
      global: { stubs: defaultStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.localLevels).toBe(3)
    expect(vm.localRoles.L3).toBe('eqcr')
  })

  it('emits saved on successful save', async () => {
    vi.mocked(http.put).mockResolvedValue({ data: {} })

    const wrapper = mount(ReviewChainConfig, {
      props: {
        projectId: 'proj-1',
        currentConfig: { levels: 2, level_roles: { L1: 'manager', L2: 'partner' } },
      },
      global: { stubs: defaultStubs },
    })

    const vm = wrapper.vm as any
    await vm.handleSave()
    await flushPromises()

    expect(http.put).toHaveBeenCalledWith(
      '/api/projects/proj-1/review-config',
      { levels: 2, level_roles: { L1: 'manager', L2: 'partner' } },
    )

    const saved = wrapper.emitted('saved')
    expect(saved).toBeTruthy()
    expect(saved![0][0]).toEqual({ levels: 2, level_roles: { L1: 'manager', L2: 'partner' } })
  })

  it('shows disabled state when reviews in progress', () => {
    const wrapper = mount(ReviewChainConfig, {
      props: {
        projectId: 'proj-1',
        currentConfig: null,
        disabled: true,
      },
      global: { stubs: defaultStubs },
    })

    expect(wrapper.find('.el-alert').exists()).toBe(true)
    expect(wrapper.text()).toContain('当前有进行中的复核')
  })

  it('level switch updates localRoles with defaults', async () => {
    const wrapper = mount(ReviewChainConfig, {
      props: {
        projectId: 'proj-1',
        currentConfig: { levels: 2, level_roles: { L1: 'manager', L2: 'partner' } },
      },
      global: { stubs: defaultStubs },
    })

    const vm = wrapper.vm as any
    vm.localLevels = 4
    await flushPromises()

    // L3 and L4 should get defaults
    expect(vm.localRoles.L3).toBe('eqcr')
    expect(vm.localRoles.L4).toBe('qc')
  })
})
