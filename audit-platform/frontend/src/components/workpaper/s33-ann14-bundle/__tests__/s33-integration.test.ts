/**
 * s33-integration.test.ts — S33 应对14号公告核查程序聚合组件 集成测试
 *
 * Spec: .kiro/specs/s33-announcement14-bundle/  Task 7.2
 * Requirements: 3.4 (隐藏变体切换), 8.1 (只读模式)
 *
 * 验证场景：
 * 1. Mount GtS33Bundle → 各核查底稿 Tab 正确渲染
 * 2. Tab 切换 → GtAProgramConsole 接收正确 wp-id / sheetName
 * 3. S33-4 隐藏变体切换（默认精简版 → 切换完整版 → sheetName 变为隐藏 sheet 名）
 * 4. readonly 透传给所有子组件
 * 5. 空状态（无 S33 底稿）
 * 6. sheetName prop 初始化激活
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import GtS33Bundle from '../GtS33Bundle.vue'
import { S33_ANN14_TABS } from '../S33_TAB_CONFIG'

// ─── Mocks ───

const mockRoute = {
  params: { projectId: 'test-project-id' },
  query: {} as Record<string, string>,
}
vi.mock('vue-router', () => ({
  useRoute: () => mockRoute,
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/services/workpaperApi', () => ({
  getWpIndex: vi.fn(),
}))

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn().mockImplementation((url: string) => {
      if (url.includes('render-config')) {
        return Promise.resolve({
          sheets: [{ sheet_name: '提示', html_data: { tip_text: '测试提示内容' } }],
        })
      }
      if (url.includes('checklist-responses')) {
        return Promise.resolve([])
      }
      return Promise.resolve({})
    }),
  },
}))

// ─── Helpers ───

/** Build mock wp_index items for all 9 S33 tabs */
function buildMockWpIndexItems(codes?: string[]) {
  const targetCodes = codes ?? S33_ANN14_TABS.map(t => t.wpCode)
  return targetCodes.map((code, idx) => ({
    id: `idx-${idx}`,
    wp_code: code,
    wp_id: `wp-${code.toLowerCase()}`,
  }))
}

function createWrapper(props: Record<string, unknown> = {}) {
  return mount(GtS33Bundle, {
    props: {
      wpId: 'wp-s33-bundle',
      ...props,
    },
    global: {
      stubs: {
        GtAProgramConsole: {
          template: '<div class="mock-program-console" :data-wp-id="wpId" :data-readonly="readonly" :data-sheet="sheetName">ProgramConsole</div>',
          props: ['wpId', 'sheetName', 'readonly'],
        },
        'el-alert': { template: '<div class="el-alert"><slot name="title" /><slot /></div>' },
        'el-tabs': {
          template: '<div class="el-tabs"><slot /></div>',
          props: ['modelValue'],
          emits: ['update:modelValue'],
        },
        'el-tab-pane': {
          template: '<div class="el-tab-pane" :data-name="name"><slot /></div>',
          props: ['label', 'name', 'lazy'],
        },
        'el-switch': {
          template: '<div class="el-switch" :data-active="modelValue" @click="$emit(\'change\')"></div>',
          props: ['modelValue', 'size', 'inlinePrompt', 'activeText', 'inactiveText'],
          emits: ['change'],
        },
        'el-result': {
          template: '<div class="el-result"><slot /><slot name="sub-title" /></div>',
          props: ['icon', 'title'],
        },
      },
      directives: {
        loading: () => {},
      },
    },
  })
}

// ─── Tests ───

describe('GtS33Bundle 集成测试', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    mockRoute.query = {}
    const { getWpIndex } = await import('@/services/workpaperApi')
    vi.mocked(getWpIndex).mockResolvedValue(buildMockWpIndexItems())
  })

  describe('Tab 渲染与切换', () => {
    it('挂载后渲染全部9个核查底稿 Tab', async () => {
      const wrapper = createWrapper()
      await flushPromises()
      await nextTick()

      const tabPanes = wrapper.findAll('.el-tab-pane')
      expect(tabPanes.length).toBe(9)

      // Verify tab names match S33 config
      for (let i = 0; i < 9; i++) {
        expect(tabPanes[i].attributes('data-name')).toBe(S33_ANN14_TABS[i].id)
      }
    })

    it('部分底稿存在时仅渲染对应 Tab', async () => {
      const { getWpIndex } = await import('@/services/workpaperApi')
      vi.mocked(getWpIndex).mockResolvedValueOnce(
        buildMockWpIndexItems(['S33-1', 'S33-4', 'S33-9']),
      )

      const wrapper = createWrapper()
      await flushPromises()
      await nextTick()

      const tabPanes = wrapper.findAll('.el-tab-pane')
      expect(tabPanes.length).toBe(3)
      expect(tabPanes[0].attributes('data-name')).toBe('S33-1')
      expect(tabPanes[1].attributes('data-name')).toBe('S33-4')
      expect(tabPanes[2].attributes('data-name')).toBe('S33-9')
    })

    it('默认激活第一个可见 Tab → GtAProgramConsole 接收正确 wp-id', async () => {
      const wrapper = createWrapper()
      await flushPromises()
      await nextTick()

      const programConsoles = wrapper.findAll('.mock-program-console')
      expect(programConsoles.length).toBeGreaterThanOrEqual(1)

      // First console should have wp-id for S33-1
      expect(programConsoles[0].attributes('data-wp-id')).toBe('wp-s33-1')
    })

    it('sheetName prop → 初始激活指定 Tab', async () => {
      const wrapper = createWrapper({ sheetName: 'S33-5' })
      await flushPromises()
      await nextTick()

      expect((wrapper.vm as any).activeTab).toBe('S33-5')
    })

    it('无效 sheetName → 保持默认第一个 Tab', async () => {
      const wrapper = createWrapper({ sheetName: 'S33-99' })
      await flushPromises()
      await nextTick()

      expect((wrapper.vm as any).activeTab).toBe('S33-1')
    })
  })

  describe('隐藏变体切换 (Req 3.4)', () => {
    it('S33-4 Tab 渲染变体切换入口', async () => {
      const wrapper = createWrapper({ sheetName: 'S33-4' })
      await flushPromises()
      await nextTick()

      // S33-4 pane should have variant toggle
      const variantToggle = wrapper.find('.gt-s33-bundle__variant-toggle')
      expect(variantToggle.exists()).toBe(true)
    })

    it('默认状态为精简版（可见版）', async () => {
      const wrapper = createWrapper({ sheetName: 'S33-4' })
      await flushPromises()
      await nextTick()

      // showHiddenVariant['S33-4'] should be false/undefined initially
      const vm = wrapper.vm as any
      expect(vm.showHiddenVariant['S33-4']).toBeFalsy()

      // GtAProgramConsole should receive the visible sheet name
      const s34Pane = wrapper.findAll('.el-tab-pane').find(
        p => p.attributes('data-name') === 'S33-4',
      )
      const console = s34Pane?.find('.mock-program-console')
      expect(console?.attributes('data-sheet')).toBe('S33-4(IB4)程序表')
    })

    it('切换到完整版 → sheetName 变为隐藏变体 sheet 名', async () => {
      const wrapper = createWrapper({ sheetName: 'S33-4' })
      await flushPromises()
      await nextTick()

      // Trigger variant toggle
      const vm = wrapper.vm as any
      vm.toggleVariant('S33-4')
      await nextTick()

      expect(vm.showHiddenVariant['S33-4']).toBe(true)

      // GtAProgramConsole should now receive hidden variant sheet name
      const s34Pane = wrapper.findAll('.el-tab-pane').find(
        p => p.attributes('data-name') === 'S33-4',
      )
      const console = s34Pane?.find('.mock-program-console')
      expect(console?.attributes('data-sheet')).toBe('S33-4(IB4)程序表-隐')
    })

    it('切换回精简版 → sheetName 恢复为可见版', async () => {
      const wrapper = createWrapper({ sheetName: 'S33-4' })
      await flushPromises()
      await nextTick()

      const vm = wrapper.vm as any
      // Toggle to full version
      vm.toggleVariant('S33-4')
      await nextTick()
      expect(vm.showHiddenVariant['S33-4']).toBe(true)

      // Toggle back to compact version
      vm.toggleVariant('S33-4')
      await nextTick()
      expect(vm.showHiddenVariant['S33-4']).toBe(false)

      const s34Pane = wrapper.findAll('.el-tab-pane').find(
        p => p.attributes('data-name') === 'S33-4',
      )
      const console = s34Pane?.find('.mock-program-console')
      expect(console?.attributes('data-sheet')).toBe('S33-4(IB4)程序表')
    })

    it('非 S33-4 Tab 无变体切换入口', async () => {
      const wrapper = createWrapper({ sheetName: 'S33-1' })
      await flushPromises()
      await nextTick()

      const s31Pane = wrapper.findAll('.el-tab-pane').find(
        p => p.attributes('data-name') === 'S33-1',
      )
      const variantToggle = s31Pane?.find('.gt-s33-bundle__variant-toggle')
      expect(variantToggle?.exists()).toBe(false)
    })
  })

  describe('只读模式透传 (Req 8.1)', () => {
    it('readonly=true → 所有 GtAProgramConsole 接收 readonly=true', async () => {
      const wrapper = createWrapper({ readonly: true })
      await flushPromises()
      await nextTick()

      const programConsoles = wrapper.findAll('.mock-program-console')
      expect(programConsoles.length).toBeGreaterThanOrEqual(1)

      for (const pc of programConsoles) {
        expect(pc.attributes('data-readonly')).toBe('true')
      }
    })

    it('readonly=false → 所有 GtAProgramConsole 接收 readonly=false', async () => {
      const wrapper = createWrapper({ readonly: false })
      await flushPromises()
      await nextTick()

      const programConsoles = wrapper.findAll('.mock-program-console')
      expect(programConsoles.length).toBeGreaterThanOrEqual(1)

      for (const pc of programConsoles) {
        expect(pc.attributes('data-readonly')).toBe('false')
      }
    })

    it('readonly 模式下变体切换入口仍存在（只读可浏览）', async () => {
      const wrapper = createWrapper({ sheetName: 'S33-4', readonly: true })
      await flushPromises()
      await nextTick()

      // 变体切换入口在只读模式下仍可见（用于浏览不同版本）
      const variantToggle = wrapper.find('.gt-s33-bundle__variant-toggle')
      expect(variantToggle.exists()).toBe(true)
    })
  })

  describe('空状态与仪表盘', () => {
    it('无任何 S33 底稿 → 显示空状态提示', async () => {
      const { getWpIndex } = await import('@/services/workpaperApi')
      vi.mocked(getWpIndex).mockResolvedValueOnce([])

      const wrapper = createWrapper()
      await flushPromises()
      await nextTick()

      const emptyDiv = wrapper.find('.gt-s33-bundle__empty')
      expect(emptyDiv.exists()).toBe(true)
    })

    it('有底稿时 → 完成进度仪表盘渲染', async () => {
      const wrapper = createWrapper()
      await flushPromises()
      await nextTick()

      const dashboard = wrapper.find('[data-testid="s33-dashboard"]')
      expect(dashboard.exists()).toBe(true)
      expect(dashboard.text()).toContain('已完成')
      expect(dashboard.text()).toContain('进行中')
      expect(dashboard.text()).toContain('未开始')
    })
  })
})
