/**
 * ArchivedBanner — 归档横幅组件单测
 *
 * 验证：
 * - isArchived=false 时不渲染
 * - isArchived=true 时渲染横幅
 * - 仅 admin/partner 角色显示「解除归档」按钮
 * - 点击按钮：填原因 → 输入项目名称 → 调解除归档接口 → 更新项目状态并刷新；任一步取消不发请求
 *   （spec attachment-archive-and-a-class-evidence ADR-AE-13：改造前只发一个没人监听的事件）
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
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

// ─── Mock 弹框 / 接口 ───
const mockPrompt = vi.fn()
const mockSuccess = vi.fn()
vi.mock('element-plus', async (orig) => ({
  ...(await orig<typeof import('element-plus')>()),
  ElMessageBox: { prompt: (...args: any[]) => mockPrompt(...args) },
  ElMessage: { success: (...args: any[]) => mockSuccess(...args), warning: vi.fn(), error: vi.fn() },
}))
const mockGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({ api: { get: (...args: any[]) => mockGet(...args) } }))
const mockUnarchive = vi.fn()
vi.mock('@/services/archiveApi', () => ({ unarchiveProject: (...args: any[]) => mockUnarchive(...args) }))
const mockHandleApiError = vi.fn()
vi.mock('@/utils/errorHandler', () => ({ handleApiError: (...args: any[]) => mockHandleApiError(...args) }))

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
    for (const m of [mockPrompt, mockSuccess, mockGet, mockUnarchive, mockHandleApiError]) m.mockReset()
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

  describe('解除归档流程', () => {
    let reloadSpy: ReturnType<typeof vi.fn>
    const originalLocation = window.location

    async function mountAsAdmin() {
      mockIsArchived.value = true
      const pinia = createPinia()
      setActivePinia(pinia)
      const { useRoleContextStore } = await import('@/stores/roleContext')
      useRoleContextStore().effectiveRole = 'admin'
      const wrapper = mount(ArchivedBanner, { global: { stubs: STUBS, plugins: [pinia] } })
      await nextTick()
      return wrapper
    }

    beforeEach(() => {
      vi.useFakeTimers()
      reloadSpy = vi.fn()
      Object.defineProperty(window, 'location', { value: { ...originalLocation, reload: reloadSpy }, writable: true })
      mockGet.mockResolvedValue({ name: '【测试】项目甲' })
    })
    afterEach(() => {
      vi.useRealTimers()
      Object.defineProperty(window, 'location', { value: originalLocation, writable: true })
    })

    it('填原因 → 输入项目名称 → 调接口，更新项目状态并刷新页面', async () => {
      mockPrompt.mockResolvedValueOnce({ value: '  补充程序 ' }).mockResolvedValueOnce({ value: '【测试】项目甲' })
      mockUnarchive.mockResolvedValue({ success: true, new_status: 'execution', workpapers_restored: 3 })
      const wrapper = await mountAsAdmin()
      await wrapper.find('.el-button-stub').trigger('click')
      await flushPromises()

      expect(mockPrompt).toHaveBeenCalledTimes(2)
      const nameValidator = mockPrompt.mock.calls[1][2].inputValidator
      expect(nameValidator('【测试】项目甲')).toBe(true)
      expect(nameValidator('项目甲')).toBe('项目名称不一致')
      expect(mockPrompt.mock.calls[0][2].inputValidator('  ')).toBe('请填写解除原因')
      expect(mockUnarchive).toHaveBeenCalledWith('proj-1', { reason: '补充程序', project_code: '【测试】项目甲' })
      const { useProjectStore } = await import('@/stores/project')
      expect(useProjectStore().projectStatus).toBe('execution')
      expect(mockSuccess.mock.calls[0][0]).toContain('3 张底稿恢复为归档前状态')
      expect(wrapper.emitted('unarchived')).toEqual([[3]])
      expect(reloadSpy).not.toHaveBeenCalled()
      vi.advanceTimersByTime(1500)
      expect(reloadSpy).toHaveBeenCalledTimes(1)
    })

    const cancel = () => Promise.reject(new Error('cancel'))
    it.each([
      ['原因', [cancel]],
      ['项目名称', [() => Promise.resolve({ value: '补充程序' }), cancel]],
    ])('在「%s」一步取消：不调接口、不刷新', async (_step, answers) => {
      for (const answer of answers) mockPrompt.mockImplementationOnce(answer)
      const wrapper = await mountAsAdmin()
      await wrapper.find('.el-button-stub').trigger('click')
      await flushPromises()
      vi.advanceTimersByTime(5000)
      expect(mockUnarchive).not.toHaveBeenCalled()
      expect(reloadSpy).not.toHaveBeenCalled()
      expect(wrapper.emitted('unarchived')).toBeUndefined()
    })

    it('接口拒绝（如项目名称不符 400）：提示原因、不刷新', async () => {
      mockPrompt.mockResolvedValueOnce({ value: '补充程序' }).mockResolvedValueOnce({ value: '【测试】项目甲' })
      const err = { response: { status: 400, data: { detail: '项目编码校验失败' } } }
      mockUnarchive.mockRejectedValue(err)
      const wrapper = await mountAsAdmin()
      await wrapper.find('.el-button-stub').trigger('click')
      await flushPromises()
      vi.advanceTimersByTime(5000)
      expect(mockHandleApiError).toHaveBeenCalledWith(err, '解除归档')
      expect(reloadSpy).not.toHaveBeenCalled()
    })
  })
})
