/**
 * a7-1UniverNavSmoke.spec.ts — A7-1 Univer 跳转 smoke 测试
 *
 * 验证 A7-1（汇总关联方交易及关联往来）不走弹窗路径，而是通过 GtIndexChip
 * 解析 wp_code → navigateToTarget → resolveAndNavigateToWp 跳转到底稿编辑页。
 *
 * A7-1 在 lite 阶段以 Univer（xlsx 默认渲染器）打开。
 * 它不在 INLINE_POPUP_WP_CODES 中，也不在前端 override 映射中。
 *
 * spec: a7-a15-completion-workpapers, Task 14
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { parseIndexRef } from '@/utils/parseIndexRef'
import { INLINE_POPUP_WP_CODES } from '@/components/workpaper/wpPopupDocxConfigs'
import GtIndexChip from '../GtIndexChip.vue'

// Mock vue-router
const mockPush = vi.fn()
const mockRoute = {
  params: { projectId: 'proj-a7' },
  path: '/projects/proj-a7/workpapers/wp-a7/edit',
  query: { wp_code: 'A7' },
}
vi.mock('vue-router', () => ({
  useRoute: () => mockRoute,
  useRouter: () => ({ push: mockPush }),
}))

// Mock apiProxy — resolveAndNavigateToWp calls /api/wp-index-resolve
const mockApiGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: { get: (...args: any[]) => mockApiGet(...args) },
}))

// Element Plus stubs
const ElTag = {
  name: 'ElTag',
  template: '<span class="el-tag-stub" @click="$emit(\'click\', $event)"><slot /></span>',
  props: ['type', 'effect', 'size'],
}
const ElTooltip = {
  name: 'ElTooltip',
  template: '<div class="el-tooltip-stub"><slot /></div>',
  props: ['content', 'disabled', 'placement'],
}
const ElDropdown = {
  name: 'ElDropdown',
  template: '<div class="el-dropdown-stub"><slot /></div>',
  props: ['trigger'],
}
const ElDropdownMenu = {
  name: 'ElDropdownMenu',
  template: '<div><slot /></div>',
}
const ElDropdownItem = {
  name: 'ElDropdownItem',
  template: '<div><slot /></div>',
  props: ['command'],
}

const globalConfig = {
  components: {
    'el-tag': ElTag,
    'el-tooltip': ElTooltip,
    'el-dropdown': ElDropdown,
    'el-dropdown-menu': ElDropdownMenu,
    'el-dropdown-item': ElDropdownItem,
  },
}

describe('A7-1 Univer 跳转 smoke', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('A7-1 不在 INLINE_POPUP_WP_CODES 中', () => {
    expect(INLINE_POPUP_WP_CODES.has('A7-1')).toBe(false)
  })

  it('parseIndexRef("A7-1") 解析为 wp 命名空间', () => {
    const result = parseIndexRef('A7-1')
    expect(result).toMatchObject({
      ns: 'wp',
      layer: 3,
      target: 'A7-1',
    })
  })

  it('GtIndexChip 点击 A7-1 触发导航（非弹窗）', async () => {
    mockApiGet.mockResolvedValue({ exists: true, wp_id: 'wp-a7-1-uuid' })

    const wrapper = mount(GtIndexChip, {
      props: { value: 'A7-1', validate: false },
      global: globalConfig,
    })
    await flushPromises()

    // chip 应该渲染为 tag（非纯文本）
    expect(wrapper.find('.el-tag-stub').exists()).toBe(true)

    // 点击 chip
    await wrapper.find('.el-tag-stub').trigger('click')
    await flushPromises()

    // 应该调用 resolveAndNavigateToWp → /api/wp-index-resolve
    expect(mockApiGet).toHaveBeenCalledWith(
      '/api/wp-index-resolve',
      expect.objectContaining({
        params: expect.objectContaining({ ref: 'A7-1', project_id: 'proj-a7' }),
      }),
    )

    // 应该导航到底稿编辑页
    expect(mockPush).toHaveBeenCalledWith({
      path: '/projects/proj-a7/workpapers/wp-a7-1-uuid/edit',
    })
  })

  it('GtIndexChip A7-1 的 preventNavigate 为 false', () => {
    // A7-1 不在 INLINE_POPUP_WP_CODES → preventNavigate 不应为 true
    // 在 GtAProgramConsole 中 :prevent-navigate="INLINE_POPUP_WP_CODES.has(ref)"
    const shouldPrevent = INLINE_POPUP_WP_CODES.has('A7-1')
    expect(shouldPrevent).toBe(false)
  })

  it('A7-1 wp_code 不存在时显示警告而非弹窗', async () => {
    mockApiGet.mockResolvedValue({ exists: false })

    const wrapper = mount(GtIndexChip, {
      props: { value: 'A7-1', validate: false },
      global: globalConfig,
    })
    await flushPromises()
    await wrapper.find('.el-tag-stub').trigger('click')
    await flushPromises()

    // 不应导航（底稿尚未生成时不跳转）
    expect(mockPush).not.toHaveBeenCalled()
  })
})
