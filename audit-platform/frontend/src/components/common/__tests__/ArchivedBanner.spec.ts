/**
 * ArchivedBanner — 归档横幅组件单测
 *
 * 验证：
 * - isArchived=false 时不渲染
 * - isArchived=true 时渲染横幅
 * - 仅 admin/partner 角色显示「解除归档」按钮
 * - 点击按钮触发 unarchive 事件
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick, ref, computed } from 'vue'
import ArchivedBanner from '../ArchivedBanner.vue'

// ─── Mock useAuditContext ───
const mockIsArchived = ref(false)
vi.mock('@/composables/useAuditContext', () => ({
  useAuditContext: () => ({
    isArchived: mockIsArchived,
    projectId: computed(() => 'proj-1'),
    year: computed(() => 2024),
    applicableStandard: computed(() => 'soe'),
    canEdit: computed(() => true),
    onContextChange: () => () => {},
  }),
}))

// ─── Mock confirm ───
const mockConfirmDangerous = vi.fn().mockResolvedValue(undefined)
vi.mock('@/utils/confirm', () => ({
  confirmDangerous: (...args: any[]) => mockConfirmDangerous(...args),
}))

// ─── Stubs ───
const STUBS = {
  'el-button': {
    name: 'ElButton',
    inheritAttrs: true,
    template: '<button class="el-button-stub" v-bind="$attrs"><slot /></button>',
    props: ['size'],
  },
}

describe('ArchivedBanner', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockIsArchived.value = false
    mockConfirmDangerous.mockClear()
  })

  it('isArchived=false 时不渲染', () => {
    mockIsArchived.value = false
    const wrapper = mount(ArchivedBanner, {
      global: { stubs: STUBS },
    })
    expect(wrapper.find('.archived-banner').exists()).toBe(false)
  })

  it('isArchived=true 时渲染横幅', () => {
    mockIsArchived.value = true
    const wrapper = mount(ArchivedBanner, {
      global: { stubs: STUBS },
    })
    expect(wrapper.find('.archived-banner').exists()).toBe(true)
    expect(wrapper.text()).toContain('项目已归档（只读）')
  })

  it('非 admin/partner 角色不显示解除归档按钮', async () => {
    mockIsArchived.value = true
    const pinia = createPinia()
    setActivePinia(pinia)

    const wrapper = mount(ArchivedBanner, {
      global: { stubs: STUBS, plugins: [pinia] },
    })

    // 默认 effectiveRole 为空，isPartner 为 false
    const { useRoleContextStore } = await import('@/stores/roleContext')
    const roleStore = useRoleContextStore()
    roleStore.effectiveRole = 'auditor'
    await nextTick()

    expect(wrapper.find('.el-button-stub').exists()).toBe(false)
  })

  it('admin 角色显示解除归档按钮', async () => {
    mockIsArchived.value = true
    const pinia = createPinia()
    setActivePinia(pinia)

    const { useRoleContextStore } = await import('@/stores/roleContext')
    const roleStore = useRoleContextStore()
    roleStore.effectiveRole = 'admin'

    const wrapper = mount(ArchivedBanner, {
      global: { stubs: STUBS, plugins: [pinia] },
    })
    await nextTick()

    expect(wrapper.find('.el-button-stub').exists()).toBe(true)
    expect(wrapper.find('.el-button-stub').text()).toContain('解除归档')
  })

  it('partner 角色显示解除归档按钮', async () => {
    mockIsArchived.value = true
    const pinia = createPinia()
    setActivePinia(pinia)

    const { useRoleContextStore } = await import('@/stores/roleContext')
    const roleStore = useRoleContextStore()
    roleStore.effectiveRole = 'partner'

    const wrapper = mount(ArchivedBanner, {
      global: { stubs: STUBS, plugins: [pinia] },
    })
    await nextTick()

    expect(wrapper.find('.el-button-stub').exists()).toBe(true)
  })

  it('点击解除归档按钮触发 unarchive 事件', async () => {
    mockIsArchived.value = true
    mockConfirmDangerous.mockResolvedValue(undefined)
    const pinia = createPinia()
    setActivePinia(pinia)

    const { useRoleContextStore } = await import('@/stores/roleContext')
    const roleStore = useRoleContextStore()
    roleStore.effectiveRole = 'admin'

    const wrapper = mount(ArchivedBanner, {
      global: { stubs: STUBS, plugins: [pinia] },
    })
    await nextTick()

    await wrapper.find('.el-button-stub').trigger('click')
    await nextTick()

    expect(mockConfirmDangerous).toHaveBeenCalled()
    expect(wrapper.emitted('unarchive')).toHaveLength(1)
  })

  it('用户取消确认弹窗时不触发 unarchive 事件', async () => {
    mockIsArchived.value = true
    mockConfirmDangerous.mockRejectedValue('cancel')
    const pinia = createPinia()
    setActivePinia(pinia)

    const { useRoleContextStore } = await import('@/stores/roleContext')
    const roleStore = useRoleContextStore()
    roleStore.effectiveRole = 'admin'

    const wrapper = mount(ArchivedBanner, {
      global: { stubs: STUBS, plugins: [pinia] },
    })
    await nextTick()

    await wrapper.find('.el-button-stub').trigger('click')
    await nextTick()

    expect(mockConfirmDangerous).toHaveBeenCalled()
    expect(wrapper.emitted('unarchive')).toBeUndefined()
  })
})
