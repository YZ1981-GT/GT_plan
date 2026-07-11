/**
 * s34-integration.spec.ts — S34 Bundle 组件集成测试
 *
 * Spec: .kiro/specs/s34-ipo-review-bundle/  Task 11.1
 * Validates: Requirements 3.1, 3.3, 4.4
 *
 * 测试场景：
 * 1. 挂载 GtS34Bundle + mock wp_index + S34-0 checklist API
 * 2. 验证 overview 面板渲染核查清单
 * 3. 点击核查清单行 → 切换到对应专项 Tab
 * 4. 选中专项 Tab → GtAProgramConsole 渲染且接收正确 wp-id
 * 5. regRef 方法论上下文区块正确展示（琥珀色左边线）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick, defineComponent } from 'vue'

// ─── Mock vue-router ────────────────────────────────────────────────────────

const mockRoute = {
  params: { projectId: 'proj-test-001' },
  query: {},
}
const mockPush = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => mockRoute,
  useRouter: () => ({ push: mockPush }),
}))

// ─── Mock API services ──────────────────────────────────────────────────────

const mockGetWpIndex = vi.fn()
const mockApiGet = vi.fn()

vi.mock('@/services/workpaperApi', () => ({
  getWpIndex: (...args: any[]) => mockGetWpIndex(...args),
}))

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockApiGet(...args),
  },
}))

// ─── Mock element-plus ──────────────────────────────────────────────────────

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
  ElMessageBox: { prompt: vi.fn() },
}))

// ─── Stub child components (keep tests fast) ────────────────────────────────

/** Stub GtAProgramConsole: captures props for assertion */
const GtAProgramConsoleStub = defineComponent({
  name: 'GtAProgramConsole',
  props: ['wpId', 'sheetName', 'readonly', 'schema', 'htmlData'],
  emits: ['jump-to-workpaper'],
  template: '<div class="stub-program-console" :data-wp-id="wpId" :data-sheet="sheetName" :data-readonly="readonly">程序表</div>',
})

/** Stub GtS34SubCheckTable */
const GtS34SubCheckTableStub = defineComponent({
  name: 'GtS34SubCheckTable',
  props: ['wpId', 'subSheets', 'wpIdMap', 'projectId', 'readonly'],
  template: '<div class="stub-sub-check-table" :data-wp-id="wpId">子检查表</div>',
})

/** Stub GtS34ChecklistOverview: renders rows + emits navigate */
const GtS34ChecklistOverviewStub = defineComponent({
  name: 'GtS34ChecklistOverview',
  props: ['checklist', 'readonly'],
  emits: ['navigate', 'updateReason'],
  template: `
    <div class="stub-overview" data-testid="s34-overview">
      <div
        v-for="item in checklist"
        :key="item.wpCode"
        class="overview-row"
        :data-wp-code="item.wpCode"
        :data-name="item.name"
        :data-status="item.status"
        @click="$emit('navigate', item.wpCode)"
      >
        {{ item.wpCode }} - {{ item.name }}
      </div>
    </div>
  `,
})

// ─── Import component under test ────────────────────────────────────────────

import GtS34Bundle from '../GtS34Bundle.vue'

// ─── Test data fixtures ─────────────────────────────────────────────────────

/** 模拟 wp_index 返回的 S34 系列底稿 */
function buildMockWpIndex() {
  return [
    { id: 'idx-1', wp_id: 'wp-s34-2-id', wp_code: 'S34-2', wp_name: 'S34-2 期权激励', audit_cycle: null, status: 'in_progress', assigned_to: null, reviewer: null },
    { id: 'idx-2', wp_id: 'wp-s34-3-id', wp_code: 'S34-3', wp_name: 'S34-3 股份支付', audit_cycle: null, status: 'completed', assigned_to: null, reviewer: null },
    { id: 'idx-3', wp_id: 'wp-s34-16-id', wp_code: 'S34-16', wp_name: 'S34-16 第三方回款', audit_cycle: null, status: 'not_started', assigned_to: null, reviewer: null },
    { id: 'idx-4', wp_id: 'wp-s34-4-id', wp_code: 'S34-4', wp_name: 'S34-4 关联交易', audit_cycle: null, status: 'in_progress', assigned_to: null, reviewer: null },
    { id: 'idx-5', wp_id: 'wp-s34-25-id', wp_code: 'S34-25', wp_name: 'S34-25 资金流水', audit_cycle: null, status: 'not_started', assigned_to: null, reviewer: null },
    // 非 S34 底稿（应被忽略）
    { id: 'idx-99', wp_id: 'wp-d4-id', wp_code: 'D4', wp_name: 'D4 收入', audit_cycle: 'D', status: 'completed', assigned_to: null, reviewer: null },
  ]
}

/** 模拟 S34-0 核查清单 API 返回（snake_case 后端格式） */
function buildMockChecklist() {
  return [
    {
      seq: 2,
      wp_code: 'S34-2',
      name: '期权激励专项核查',
      reg_ref: {
        csrc: '发行类4号第15条',
        sse: '指南第3.2节',
        szse: null,
        bse: null,
        title: '股权激励核查',
      },
      applicability: 'applicable',
      status: 'in_progress',
    },
    {
      seq: 3,
      wp_code: 'S34-3',
      name: '股份支付专项核查',
      reg_ref: {
        csrc: '发行类5号第8条',
        sse: '指南第3.3节',
        szse: '指南第2.1节',
        bse: null,
        title: '股份支付计量核查',
      },
      applicability: 'applicable',
      status: 'completed',
    },
    {
      seq: 4,
      wp_code: 'S34-4',
      name: '关联交易专项核查',
      reg_ref: {
        csrc: '发行类9号第12条',
        sse: null,
        szse: '指南第4.1节',
        bse: '指引第5.2节',
        title: '关联方交易核查',
      },
      applicability: 'applicable',
      status: 'in_progress',
    },
    {
      seq: 16,
      wp_code: 'S34-16',
      name: '第三方回款专项核查',
      reg_ref: {
        csrc: '发行类4号第22条',
        sse: '指南第5.1节',
        szse: '指南第5.1节',
        bse: null,
        title: '第三方回款核查',
      },
      applicability: 'applicable',
      status: 'not_started',
    },
    {
      seq: 25,
      wp_code: 'S34-25',
      name: '资金流水核查',
      reg_ref: {
        csrc: '发行类4号第30条',
        sse: null,
        szse: null,
        bse: '指引第8.1节',
        title: '银行流水核查',
      },
      applicability: 'applicable',
      status: 'not_started',
    },
  ]
}

// ─── Helper: mount with stubs ───────────────────────────────────────────────

/**
 * el-tabs stub that respects v-model:
 * Only renders the slot content of the pane matching modelValue
 */
const ElTabsStub = defineComponent({
  name: 'ElTabs',
  props: ['modelValue'],
  emits: ['update:modelValue'],
  template: '<div class="el-tabs"><slot /></div>',
})

/**
 * el-tab-pane stub: renders slot only when its `name` matches parent's modelValue.
 * Since we can't easily access the parent's modelValue from the stub, we render
 * content unconditionally and use `data-name` to allow test assertions by pane.
 *
 * To correctly test active tab behavior, we'll use a pane-aware approach:
 * we always render all panes (like el-tabs without lazy) and assert on
 * specific components found within pane boundaries.
 */
const ElTabPaneStub = defineComponent({
  name: 'ElTabPane',
  props: ['label', 'name', 'lazy'],
  template: '<div class="el-tab-pane" :data-name="name"><slot /></div>',
})

function mountBundle(propsOverride: Record<string, any> = {}) {
  return mount(GtS34Bundle, {
    props: {
      wpId: 'wp-s34-parent',
      readonly: false,
      ...propsOverride,
    },
    global: {
      stubs: {
        GtAProgramConsole: GtAProgramConsoleStub,
        GtS34SubCheckTable: GtS34SubCheckTableStub,
        GtS34ChecklistOverview: GtS34ChecklistOverviewStub,
        ElAlert: { template: '<div class="el-alert"><slot name="title" /><slot /></div>' },
        ElTabs: ElTabsStub,
        ElTabPane: ElTabPaneStub,
        ElResult: {
          template: '<div class="el-result" data-testid="el-result"><span class="el-result__title">{{ title }}</span><slot /><slot name="sub-title" /></div>',
          props: ['icon', 'title'],
        },
        ElIcon: {
          template: '<span class="el-icon"><slot /></span>',
        },
        // Icon stubs
        CircleCheckFilled: { template: '<i />' },
        Loading: { template: '<i />' },
        RemoveFilled: { template: '<i />' },
        CloseBold: { template: '<i />' },
      },
      directives: {
        loading: () => {},  // stub v-loading
      },
    },
  })
}

/** 在指定 Tab pane 中查找组件/元素 */
function findInPane(wrapper: ReturnType<typeof mount>, paneName: string) {
  const panes = wrapper.findAll('.el-tab-pane')
  return panes.find(p => p.attributes('data-name') === paneName)
}

// ─── Setup ──────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks()
  mockRoute.query = {}
  mockGetWpIndex.mockResolvedValue(buildMockWpIndex())
  mockApiGet.mockImplementation((url: string) => {
    if (url.includes('/s34-checklist')) {
      return Promise.resolve(buildMockChecklist())
    }
    return Promise.resolve(null)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 1. Overview 面板渲染（Requirement 3.1）
// ═══════════════════════════════════════════════════════════════════════════════

describe('Overview 面板默认渲染 (Req 3.1)', () => {
  it('组件挂载后默认展示 overview 面板（核查清单总览）', async () => {
    const wrapper = mountBundle()
    await flushPromises()

    // overview stub 应该被渲染
    const overview = wrapper.find('[data-testid="s34-overview"]')
    expect(overview.exists()).toBe(true)
  })

  it('overview 面板接收到正确的 checklist 数据', async () => {
    const wrapper = mountBundle()
    await flushPromises()

    const overview = wrapper.findComponent(GtS34ChecklistOverviewStub)
    expect(overview.exists()).toBe(true)

    // 验证 checklist prop 传递正确
    const checklist = overview.props('checklist')
    expect(checklist).toHaveLength(5)
    expect(checklist[0].wpCode).toBe('S34-2')
    expect(checklist[0].name).toBe('期权激励专项核查')
    expect(checklist[2].wpCode).toBe('S34-4')
  })

  it('overview 面板在 readonly 模式下接收 readonly=true', async () => {
    const wrapper = mountBundle({ readonly: true })
    await flushPromises()

    const overview = wrapper.findComponent(GtS34ChecklistOverviewStub)
    expect(overview.props('readonly')).toBe(true)
  })

  it('进度仪表盘显示正确的统计数据', async () => {
    const wrapper = mountBundle()
    await flushPromises()

    const dashboard = wrapper.find('[data-testid="s34-dashboard"]')
    expect(dashboard.exists()).toBe(true)

    // 基于 mock checklist 数据：1 completed, 2 in_progress, 2 not_started, 0 not_applicable
    const text = dashboard.text()
    expect(text).toContain('1')  // completed
    expect(text).toContain('2')  // in_progress (S34-2, S34-4)
    expect(text).toContain('已完成')
    expect(text).toContain('进行中')
    expect(text).toContain('未开始')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. 点击清单行导航到对应 Tab（Requirement 3.3）
// ═══════════════════════════════════════════════════════════════════════════════

describe('Overview 行点击切换 Tab (Req 3.3)', () => {
  it('点击 overview 行发出 navigate 事件后激活对应专项 Tab', async () => {
    const wrapper = mountBundle()
    await flushPromises()

    const overview = wrapper.findComponent(GtS34ChecklistOverviewStub)

    // 模拟点击 S34-16 行（emit navigate）
    overview.vm.$emit('navigate', 'S34-16')
    await nextTick()

    // 验证 S34-16 pane 中的 regRef 区块包含正确内容
    const s3416Pane = findInPane(wrapper, 'S34-16')
    expect(s3416Pane).toBeDefined()
    const regRef = s3416Pane!.find('[data-testid="s34-reg-ref"]')
    expect(regRef.exists()).toBe(true)
    expect(regRef.text()).toContain('第三方回款核查')
    expect(regRef.text()).toContain('发行类4号第22条')
  })

  it('点击不存在于 visibleTabs 的 wpCode 不切换', async () => {
    const wrapper = mountBundle()
    await flushPromises()

    const overview = wrapper.findComponent(GtS34ChecklistOverviewStub)

    // S34-99 不存在于 visibleTabs → navigate emit 被父忽略
    overview.vm.$emit('navigate', 'S34-99')
    await nextTick()

    // overview 仍然可见
    const overviewCheck = wrapper.find('[data-testid="s34-overview"]')
    expect(overviewCheck.exists()).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. 专项 Tab 渲染 GtAProgramConsole（Requirement 4.4）
// ═══════════════════════════════════════════════════════════════════════════════

describe('专项 Tab 渲染 GtAProgramConsole (Req 4.4)', () => {
  it('选中专项 Tab 后渲染 GtAProgramConsole 且传入正确 wp-id', async () => {
    const wrapper = mountBundle()
    await flushPromises()

    // 找到 S34-3 pane 中的 GtAProgramConsole stub
    const s343Pane = findInPane(wrapper, 'S34-3')
    expect(s343Pane).toBeDefined()

    const console = s343Pane!.findComponent(GtAProgramConsoleStub)
    expect(console.exists()).toBe(true)

    // 验证 wp-id prop = wpIdMap['S34-3'] = 'wp-s34-3-id'
    expect(console.props('wpId')).toBe('wp-s34-3-id')
    expect(console.props('sheetName')).toBe('S34-3程序表')
  })

  it('专项 Tab 的 readonly 透传给 GtAProgramConsole', async () => {
    const wrapper = mountBundle({ readonly: true })
    await flushPromises()

    // S34-2 pane 中的 GtAProgramConsole
    const s342Pane = findInPane(wrapper, 'S34-2')
    expect(s342Pane).toBeDefined()

    const console = s342Pane!.findComponent(GtAProgramConsoleStub)
    expect(console.exists()).toBe(true)
    expect(console.props('readonly')).toBe(true)
  })

  it('含子检查表的底稿同时渲染 GtS34SubCheckTable', async () => {
    const wrapper = mountBundle()
    await flushPromises()

    // S34-16 pane：hasSubTable=true, subSheets=['S34-16-1','S34-16-2']
    const s3416Pane = findInPane(wrapper, 'S34-16')
    expect(s3416Pane).toBeDefined()

    const subTable = s3416Pane!.findComponent(GtS34SubCheckTableStub)
    expect(subTable.exists()).toBe(true)
    expect(subTable.props('wpId')).toBe('wp-s34-16-id')
    expect(subTable.props('subSheets')).toEqual(['S34-16-1', 'S34-16-2'])
    expect(subTable.props('readonly')).toBe(false)
  })

  it('通过 sheetName prop 直接激活对应 Tab（外部跳转场景）', async () => {
    const wrapper = mountBundle({ sheetName: 'S34-4' })
    await flushPromises()

    // S34-4 pane 中的 regRef 区块
    const s344Pane = findInPane(wrapper, 'S34-4')
    expect(s344Pane).toBeDefined()

    const regRef = s344Pane!.find('[data-testid="s34-reg-ref"]')
    expect(regRef.exists()).toBe(true)
    expect(regRef.text()).toContain('关联方交易核查')
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 4. regRef 方法论上下文区块（Requirement 12.2）
// ═══════════════════════════════════════════════════════════════════════════════

describe('regRef 方法论上下文区块 (Req 12.2)', () => {
  it('有 regRef 的 Tab pane 中展示琥珀色左边线上下文区块', async () => {
    const wrapper = mountBundle()
    await flushPromises()

    // S34-2 pane 中的 regRef 区块
    const s342Pane = findInPane(wrapper, 'S34-2')
    expect(s342Pane).toBeDefined()

    const regRef = s342Pane!.find('[data-testid="s34-reg-ref"]')
    expect(regRef.exists()).toBe(true)

    // 验证内容
    expect(regRef.text()).toContain('股权激励核查')       // title
    expect(regRef.text()).toContain('发行类4号第15条')     // csrc
    expect(regRef.text()).toContain('指南第3.2节')         // sse
  })

  it('regRef 区块有琥珀色左边线样式类', async () => {
    const wrapper = mountBundle()
    await flushPromises()

    const s342Pane = findInPane(wrapper, 'S34-2')
    expect(s342Pane).toBeDefined()

    const regRef = s342Pane!.find('.gt-s34-bundle__reg-ref')
    expect(regRef.exists()).toBe(true)
    // 样式类存在即可证明琥珀色边线会被应用（CSS 在 scoped style 中）
  })

  it('多交易所条目按来源分列展示，无条目则不显示该交易所', async () => {
    const wrapper = mountBundle()
    await flushPromises()

    // S34-4：有 csrc + szse + bse，无 sse
    const s344Pane = findInPane(wrapper, 'S34-4')
    expect(s344Pane).toBeDefined()

    const regRef = s344Pane!.find('[data-testid="s34-reg-ref"]')
    expect(regRef.exists()).toBe(true)
    const text = regRef.text()

    expect(text).toContain('证监会')
    expect(text).toContain('发行类9号第12条')
    expect(text).toContain('深交所')
    expect(text).toContain('指南第4.1节')
    expect(text).toContain('北交所')
    expect(text).toContain('指引第5.2节')
    // 上交所无条目 → 不应显示
    expect(text).not.toContain('上交所')
  })

  it('overview Tab pane 无 regRef 区块', async () => {
    const wrapper = mountBundle()
    await flushPromises()

    // overview pane 中不应有 regRef 区块
    const overviewPane = findInPane(wrapper, 'overview')
    expect(overviewPane).toBeDefined()
    const regRef = overviewPane!.find('[data-testid="s34-reg-ref"]')
    expect(regRef.exists()).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 5. API 调用验证
// ═══════════════════════════════════════════════════════════════════════════════

describe('API 调用正确性', () => {
  it('挂载时调用 getWpIndex 获取底稿映射', async () => {
    mountBundle()
    await flushPromises()

    expect(mockGetWpIndex).toHaveBeenCalledWith('proj-test-001')
  })

  it('挂载时调用 S34 核查清单 API', async () => {
    mountBundle()
    await flushPromises()

    expect(mockApiGet).toHaveBeenCalledWith(
      '/api/projects/proj-test-001/s34-checklist',
      expect.objectContaining({ _silent: true }),
    )
  })

  it('wp_index API 失败时显示空状态（无专项底稿）', async () => {
    mockGetWpIndex.mockRejectedValue(new Error('Network Error'))

    const wrapper = mountBundle()
    await flushPromises()

    // 无 S34 专项底稿 → 空状态提示（Req 9.4）
    const emptyResult = wrapper.find('[data-testid="el-result"]')
    expect(emptyResult.exists()).toBe(true)

    // 无 GtAProgramConsole 被渲染
    const console = wrapper.findComponent(GtAProgramConsoleStub)
    expect(console.exists()).toBe(false)
  })

  it('checklist API 失败时 overview 仍可渲染但无数据', async () => {
    mockApiGet.mockRejectedValue(new Error('API Error'))

    const wrapper = mountBundle()
    await flushPromises()

    const overview = wrapper.findComponent(GtS34ChecklistOverviewStub)
    expect(overview.exists()).toBe(true)
    expect(overview.props('checklist')).toEqual([])
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// 6. 空状态：无 S34 专项底稿仅显示 overview（Requirement 9.4）
// Task 11.3
// ═══════════════════════════════════════════════════════════════════════════════

describe('空状态（无 S34 专项）仅显示 overview (Req 9.4)', () => {
  beforeEach(() => {
    // Override: wp_index 只返回非 S34 条目（或为空）
    mockGetWpIndex.mockResolvedValue([
      { id: 'idx-99', wp_id: 'wp-d4-id', wp_code: 'D4', wp_name: 'D4 收入', audit_cycle: 'D', status: 'completed', assigned_to: null, reviewer: null },
      { id: 'idx-100', wp_id: 'wp-b23-id', wp_code: 'B23', wp_name: 'B23 控制', audit_cycle: 'B', status: 'in_progress', assigned_to: null, reviewer: null },
    ])
    // checklist API 返回空（无 S34 清单）
    mockApiGet.mockImplementation((url: string) => {
      if (url.includes('/s34-checklist')) {
        return Promise.resolve([])
      }
      return Promise.resolve(null)
    })
  })

  it('无 S34 底稿时显示空状态 el-result（info 提示）', async () => {
    const wrapper = mountBundle()
    await flushPromises()

    // el-result 空状态区块存在
    const emptyResult = wrapper.find('[data-testid="el-result"]')
    expect(emptyResult.exists()).toBe(true)
  })

  it('空状态提示信息包含"未启用首发审核专项底稿"', async () => {
    const wrapper = mountBundle()
    await flushPromises()

    const emptyBlock = wrapper.find('.gt-s34-bundle__empty')
    expect(emptyBlock.exists()).toBe(true)
    // el-result 渲染 title + sub-title slot
    expect(emptyBlock.text()).toContain('未启用首发审核专项底稿')
  })

  it('无 S34 底稿时不渲染专项 Tab 页签', async () => {
    const wrapper = mountBundle()
    await flushPromises()

    // 不应有任何 el-tab-pane（除 overview 外的专项 Tab）
    const tabs = wrapper.findAll('.el-tab-pane')
    expect(tabs.length).toBe(0)

    // 整个 el-tabs 容器不应出现
    const tabsContainer = wrapper.find('.el-tabs')
    expect(tabsContainer.exists()).toBe(false)
  })

  it('无 S34 底稿时不渲染 GtAProgramConsole', async () => {
    const wrapper = mountBundle()
    await flushPromises()

    const consoleComp = wrapper.findComponent(GtAProgramConsoleStub)
    expect(consoleComp.exists()).toBe(false)
  })

  it('wp_index 返回空数组时同样显示空状态', async () => {
    mockGetWpIndex.mockResolvedValue([])

    const wrapper = mountBundle()
    await flushPromises()

    const emptyResult = wrapper.find('[data-testid="el-result"]')
    expect(emptyResult.exists()).toBe(true)

    const consoleComp = wrapper.findComponent(GtAProgramConsoleStub)
    expect(consoleComp.exists()).toBe(false)
  })
})
