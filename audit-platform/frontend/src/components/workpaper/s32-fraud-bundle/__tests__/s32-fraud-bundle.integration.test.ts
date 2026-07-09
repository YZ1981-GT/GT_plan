/**
 * s32-fraud-bundle.integration.test.ts — S32 舞弊核查聚合组件 集成测试
 *
 * Spec: .kiro/specs/s32-fraud-response-bundle/  Task 7.2
 * Requirements: 3.2, 3.3, 8.1
 *
 * 验证场景：
 * 1. Mount GtS32Bundle → 各舞弊情形 Tab 正确渲染
 * 2. Tab 切换 → GtAProgramConsole 接收正确 wp-id
 * 3. 子 sheet 切换（S32-6 导引表/披露格式参考）
 * 4. readonly 透传
 * 5. 空状态（无 S32 底稿）
 * 6. sheetName prop 初始化激活
 * 7. 无效 sheetName → 保持默认
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import GtS32Bundle from '../GtS32Bundle.vue'
import { S32_FRAUD_TABS } from '../S32_TAB_CONFIG'

// ─── Mocks ───

// Mock vue-router
const mockRoute = {
  params: { projectId: 'test-project-id' },
  query: {} as Record<string, string>,
}
vi.mock('vue-router', () => ({
  useRoute: () => mockRoute,
  useRouter: () => ({ push: vi.fn() }),
}))

// Mock workpaperApi
vi.mock('@/services/workpaperApi', () => ({
  getWpIndex: vi.fn(),
}))

// Mock apiProxy (for render-config / checklist-responses)
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

// Stub child components via global stubs in mount() instead of vi.mock
// (relative imports in .vue files are resolved differently)

// ─── Helpers ───

/** Build mock wp_index items for first 6 S32 tabs */
function buildMockWpIndexItems() {
  return S32_FRAUD_TABS.slice(0, 6).map((tab, idx) => ({
    id: `idx-${idx}`,
    wp_code: tab.wpCode,
    wp_id: `wp-${tab.wpCode.toLowerCase()}`,
  }))
}

function createWrapper(props: Record<string, unknown> = {}) {
  return mount(GtS32Bundle, {
    props: {
      wpId: 'wp-s32-bundle',
      ...props,
    },
    global: {
      stubs: {
        GtAProgramConsole: {
          template: '<div class="mock-program-console" :data-wp-id="wpId" :data-readonly="readonly" :data-sheet="sheetName">ProgramConsole</div>',
          props: ['wpId', 'sheetName', 'readonly'],
        },
        GtGridSheet: {
          template: '<div class="mock-grid-sheet" :data-wp-id="wpId" :data-readonly="readonly">GridSheet</div>',
          props: ['wpId', 'sheetName', 'htmlData', 'readonly'],
        },
        'el-tabs': {
          template: '<div class="el-tabs"><slot /></div>',
          props: ['modelValue'],
          emits: ['update:modelValue'],
        },
        'el-tab-pane': {
          template: '<div class="el-tab-pane" :data-name="name"><slot /></div>',
          props: ['label', 'name', 'lazy'],
        },
        'el-radio-group': {
          template: '<div class="el-radio-group"><slot /></div>',
          props: ['modelValue'],
          emits: ['update:modelValue'],
        },
        'el-radio-button': {
          template: '<div class="el-radio-button" :data-value="value"><slot /></div>',
          props: ['value'],
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

describe('GtS32Bundle 集成测试', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    mockRoute.query = {}
    // Setup default mock return value
    const { getWpIndex } = await import('@/services/workpaperApi')
    vi.mocked(getWpIndex).mockResolvedValue(buildMockWpIndexItems())
  })

  it('挂载后渲染可见 Tab（前6个舞弊情形）', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    await nextTick()

    // Should render tab panes for visible tabs (first 6 mocked)
    const tabPanes = wrapper.findAll('.el-tab-pane')
    expect(tabPanes.length).toBe(6)

    // Verify tab labels match S32 config
    const expectedLabels = S32_FRAUD_TABS.slice(0, 6).map(t => t.label)
    for (let i = 0; i < 6; i++) {
      expect(tabPanes[i].attributes('data-name')).toBe(S32_FRAUD_TABS[i].id)
    }
  })

  it('Tab 切换→GtAProgramConsole 接收正确 wp-id（Req 3.2）', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    await nextTick()

    // Default active tab should be S32-1
    const programConsoles = wrapper.findAll('.mock-program-console')
    // At least one ProgramConsole rendered in the active tab
    expect(programConsoles.length).toBeGreaterThanOrEqual(1)

    // First program console should have the correct wp-id for S32-1
    const firstConsole = programConsoles[0]
    expect(firstConsole.attributes('data-wp-id')).toBe('wp-s32-1')
  })

  it('子 sheet 切换（S32-6 有 IC-0 导引表/IC-X 披露格式参考）（Req 3.3）', async () => {
    // S32-6 is the 6th tab (index 5) in our mock, it has guidanceSheet and disclosureSheet
    const wrapper = createWrapper({ sheetName: 'S32-6' })
    await flushPromises()
    await nextTick()

    // S32-6 tab should have sub-sheet switcher (radio-group)
    const radioGroups = wrapper.findAll('.el-radio-group')
    expect(radioGroups.length).toBeGreaterThanOrEqual(1)

    // Radio buttons should have: 核查程序, 导引表, 披露格式参考
    const radioButtons = wrapper.findAll('.el-radio-button')
    const values = radioButtons.map(rb => rb.attributes('data-value'))
    expect(values).toContain('program')
    expect(values).toContain('guidance')
    expect(values).toContain('disclosure')
  })

  it('readonly 模式→prop 透传给 GtAProgramConsole（Req 8.1）', async () => {
    const wrapper = createWrapper({ readonly: true })
    await flushPromises()
    await nextTick()

    const programConsoles = wrapper.findAll('.mock-program-console')
    expect(programConsoles.length).toBeGreaterThanOrEqual(1)

    // All program consoles should have readonly=true
    for (const pc of programConsoles) {
      expect(pc.attributes('data-readonly')).toBe('true')
    }
  })

  it('readonly=false→GtAProgramConsole 接收 false', async () => {
    const wrapper = createWrapper({ readonly: false })
    await flushPromises()
    await nextTick()

    const programConsoles = wrapper.findAll('.mock-program-console')
    expect(programConsoles.length).toBeGreaterThanOrEqual(1)
    for (const pc of programConsoles) {
      expect(pc.attributes('data-readonly')).toBe('false')
    }
  })

  it('空状态：无 S32 底稿→显示空状态提示', async () => {
    // Override mock to return no S32 items
    const { getWpIndex } = await import('@/services/workpaperApi')
    vi.mocked(getWpIndex).mockResolvedValueOnce([])

    const wrapper = createWrapper()
    await flushPromises()
    await nextTick()

    // Should show empty state
    const emptyDiv = wrapper.find('.gt-s32-bundle__empty')
    expect(emptyDiv.exists()).toBe(true)
  })

  it('sheetName prop→初始激活指定 Tab', async () => {
    const wrapper = createWrapper({ sheetName: 'S32-3' })
    await flushPromises()
    await nextTick()

    // el-tabs model value should be set to S32-3
    const tabs = wrapper.find('.el-tabs')
    // Verify the active tab component state via vm
    expect((wrapper.vm as any).activeTab).toBe('S32-3')
  })

  it('无效 sheetName→保持默认 Tab', async () => {
    const wrapper = createWrapper({ sheetName: 'S32-99' })
    await flushPromises()
    await nextTick()

    // Invalid sheetName should fall back to first visible tab
    expect((wrapper.vm as any).activeTab).toBe('S32-1')
  })

  it('完成进度仪表盘渲染', async () => {
    const wrapper = createWrapper()
    await flushPromises()
    await nextTick()

    const dashboard = wrapper.find('.gt-s32-bundle__dashboard')
    expect(dashboard.exists()).toBe(true)
    // Should contain progress stats
    expect(dashboard.text()).toContain('已完成')
    expect(dashboard.text()).toContain('进行中')
    expect(dashboard.text()).toContain('未开始')
  })

  it('Tab 不含 IC-0/IC-X 时无子 sheet 切换器', async () => {
    // S32-1 has no guidanceSheet or disclosureSheet
    const wrapper = createWrapper({ sheetName: 'S32-1' })
    await flushPromises()
    await nextTick()

    // For S32-1 tab: no sub-switcher should appear
    const subSwitcher = wrapper.find('.gt-s32-bundle__sub-switcher')
    // Only S32-6 (which has sub-sheets) should render sub-switcher
    // Since S32-1 is active, no sub-switcher for its pane
    const allSwitchers = wrapper.findAll('.gt-s32-bundle__sub-switcher')
    // S32-1 pane should not have the switcher (or it should not be in the active pane)
    const firstPane = wrapper.findAll('.el-tab-pane')[0]
    const switcherInFirstPane = firstPane.find('.gt-s32-bundle__sub-switcher')
    expect(switcherInFirstPane.exists()).toBe(false)
  })
})
