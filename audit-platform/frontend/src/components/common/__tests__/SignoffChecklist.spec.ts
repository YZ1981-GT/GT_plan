/**
 * SignoffChecklist 组件测试（P2-2）
 *
 * 覆盖：
 * - P2-2.1 签发页显示一致性清单
 * - P2-2.2 blocking 项阻断签发
 * - P2-2.3 warning 项允许合伙人显式确认
 * - P2-2.4 确认动作记录审计日志
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import SignoffChecklist from '../SignoffChecklist.vue'

// Mock vue-router
vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: vi.fn(),
  }),
}))

// Mock apiProxy
const mockGet = vi.fn()
const mockPost = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
  },
}))

// Mock element-plus icons
vi.mock('@element-plus/icons-vue', () => ({
  Loading: { template: '<i />' },
  CircleCloseFilled: { template: '<i />' },
  WarningFilled: { template: '<i />' },
  InfoFilled: { template: '<i />' },
}))

function createWrapper(props = {}) {
  return mount(SignoffChecklist, {
    props: {
      projectId: 'test-project-id',
      year: 2025,
      userId: 'user-001',
      autoLoad: false,
      ...props,
    },
    global: {
      stubs: {
        'el-button': {
          template: '<button :disabled="$attrs.disabled" @click="$emit(\'click\')"><slot /></button>',
          inheritAttrs: false,
        },
        'el-tag': {
          template: '<span><slot /></span>',
        },
        'el-icon': {
          template: '<i><slot /></i>',
        },
        'el-alert': {
          template: '<div class="el-alert"><slot /></div>',
        },
        'el-empty': {
          template: '<div class="el-empty"></div>',
        },
      },
    },
  })
}

describe('SignoffChecklist', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('P2-2.1 签发页显示一致性清单', () => {
    it('渲染清单标题', () => {
      const wrapper = createWrapper()
      expect(wrapper.text()).toContain('签发一致性清单')
    })

    it('autoLoad=false 时显示空态', () => {
      const wrapper = createWrapper({ autoLoad: false })
      expect(wrapper.find('.gt-signoff-checklist__empty').exists()).toBe(true)
    })

    it('加载清单数据后展示结果', async () => {
      mockGet.mockResolvedValueOnce({
        project_id: 'test-project-id',
        year: 2025,
        items: [
          { severity: 'info', category: 'report', message: '审计报告已生成', route: '/projects/test/report' },
        ],
        can_signoff: true,
        has_warnings: false,
      })

      const wrapper = createWrapper({ autoLoad: true })
      await flushPromises()

      expect(wrapper.text()).toContain('审计报告已生成')
    })
  })

  describe('P2-2.2 blocking 项阻断签发', () => {
    it('存在 blocking 项时签发按钮禁用', async () => {
      mockGet.mockResolvedValueOnce({
        project_id: 'test-project-id',
        year: 2025,
        items: [
          { severity: 'blocking', category: 'trial_balance', message: '试算表科目 1001 过期', route: '/projects/test/trial-balance' },
        ],
        can_signoff: false,
        has_warnings: false,
      })

      const wrapper = createWrapper({ autoLoad: true })
      await flushPromises()

      // 签发按钮应该禁用
      const buttons = wrapper.findAll('button')
      const signoffBtn = buttons.find((b) => b.text().includes('无法签发'))
      expect(signoffBtn).toBeTruthy()
      expect(signoffBtn?.attributes('disabled')).toBeDefined()
    })

    it('blocking 项显示跳转定位按钮', async () => {
      mockGet.mockResolvedValueOnce({
        project_id: 'test-project-id',
        year: 2025,
        items: [
          { severity: 'blocking', category: 'adjustment', message: 'AJE-001 未审批', route: '/projects/test/adjustments' },
        ],
        can_signoff: false,
        has_warnings: false,
      })

      const wrapper = createWrapper({ autoLoad: true })
      await flushPromises()

      expect(wrapper.text()).toContain('跳转定位')
    })
  })

  describe('P2-2.3 warning 项允许合伙人显式确认', () => {
    it('warning 项显示确认放行按钮', async () => {
      mockGet.mockResolvedValueOnce({
        project_id: 'test-project-id',
        year: 2025,
        items: [
          { severity: 'warning', category: 'workpaper', message: '底稿存在降级记录', route: '/projects/test/workpapers/wp1' },
        ],
        can_signoff: true,
        has_warnings: true,
      })

      const wrapper = createWrapper({ autoLoad: true })
      await flushPromises()

      expect(wrapper.text()).toContain('确认放行')
    })

    it('无 blocking + warning 全确认后可签发', async () => {
      mockGet.mockResolvedValueOnce({
        project_id: 'test-project-id',
        year: 2025,
        items: [
          { severity: 'info', category: 'report', message: '审计报告已生成', route: '/projects/test/report' },
        ],
        can_signoff: true,
        has_warnings: false,
      })

      const wrapper = createWrapper({ autoLoad: true })
      await flushPromises()

      const buttons = wrapper.findAll('button')
      const signoffBtn = buttons.find((b) => b.text().includes('确认签发'))
      expect(signoffBtn).toBeTruthy()
      expect(signoffBtn?.attributes('disabled')).toBeUndefined()
    })
  })

  describe('P2-2.4 确认动作记录审计日志', () => {
    it('确认 warning 时调用后端 API', async () => {
      mockGet.mockResolvedValueOnce({
        project_id: 'test-project-id',
        year: 2025,
        items: [
          { severity: 'warning', category: 'note', message: '附注过期', route: '/projects/test/notes' },
        ],
        can_signoff: true,
        has_warnings: true,
      })
      mockPost.mockResolvedValueOnce({ status: 'confirmed' })

      const wrapper = createWrapper({ autoLoad: true })
      await flushPromises()

      // 点击确认放行按钮
      const confirmBtn = wrapper.findAll('button').find((b) => b.text().includes('确认放行'))
      expect(confirmBtn).toBeTruthy()
      await confirmBtn!.trigger('click')
      await flushPromises()

      expect(mockPost).toHaveBeenCalledWith(
        '/api/projects/test-project-id/signoff/confirm-warning',
        expect.objectContaining({
          item_index: expect.any(Number),
          item_message: '附注过期',
          item_category: 'note',
        }),
      )
    })
  })

  describe('错误处理', () => {
    it('API 错误时显示错误信息', async () => {
      mockGet.mockRejectedValueOnce(new Error('网络错误'))

      const wrapper = createWrapper({ autoLoad: true })
      await flushPromises()

      // 应该显示错误态
      expect(wrapper.find('.gt-signoff-checklist__error').exists()).toBe(true)
    })
  })
})
