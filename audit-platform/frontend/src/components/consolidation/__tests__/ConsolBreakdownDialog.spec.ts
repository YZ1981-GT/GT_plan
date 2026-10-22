/**
 * ConsolBreakdownDialog 单测 — 合并报表行穿透弹窗
 *
 * 渲染契约（ADR-CONSOL-301）：列（子公司名称/金额/占比/抵销额）、数据行数、合并数底部。
 * 附注模式随 V2 汇总器于 2026-10-22 下线（consol-note-header-library-and-node-reaggregate R6.1），
 * 组件只调报表端点。
 *
 * 另测：空态/has_breakdown=false → el-empty 后端 message；report 404 → 友好降级；
 * 行点击有权 → emit jump + 跳转；缺 source_project_id → ElMessage.info 不跳；
 * 无访问权（EH2）→ ElMessage.warning 不跳。
 *
 * Validates: Requirements 1.1, 1.3, 1.4, 1.5（T1 / T3 / EH2）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const mockGet = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: { get: (...args: any[]) => mockGet(...args) },
}))

const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ fullPath: '/projects/parent-001/reports', query: {} }),
}))

const mockNavPush = vi.fn()
vi.mock('@/composables/useNavigationStack', () => ({
  useNavigationStack: () => ({ push: mockNavPush }),
}))

const mockLoadProjectOptions = vi.fn().mockResolvedValue(undefined)
let mockProjectOptions: Array<{ id: string; name: string }> = []
vi.mock('@/stores/project', () => ({
  useProjectStore: () => ({
    loadProjectOptions: mockLoadProjectOptions,
    get projectOptions() {
      return mockProjectOptions
    },
  }),
}))

const mockMsgInfo = vi.fn()
const mockMsgWarning = vi.fn()
vi.mock('element-plus', () => ({
  ElMessage: {
    info: (...a: any[]) => mockMsgInfo(...a),
    warning: (...a: any[]) => mockMsgWarning(...a),
  },
}))

import ConsolBreakdownDialog from '../ConsolBreakdownDialog.vue'

const stubs: Record<string, any> = {
  'el-dialog': {
    template: '<div class="el-dialog"><slot /><slot name="footer" /></div>',
    props: ['modelValue', 'title', 'width', 'appendToBody'],
    emits: ['update:modelValue', 'open'],
  },
  'el-table': {
    template: '<table class="el-table"><slot /></table>',
    props: ['data', 'border', 'size'],
    provide() {
      const self = this as any
      return { getTableData: () => self.data }
    },
  },
  'el-table-column': {
    inject: ['getTableData'],
    props: ['label', 'minWidth', 'align'],
    template:
      '<th class="el-table-column" :data-label="label">' +
      '<span v-for="(row, i) in getTableData()" :key="i" class="cell"><slot :row="row" /></span>' +
      '</th>',
  },
  'el-empty': {
    template:
      '<div class="el-empty"><div class="el-empty__description">{{ description }}</div></div>',
    props: ['description'],
  },
  'el-button': {
    template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>',
    emits: ['click'],
  },
  GtAmountCell: {
    template: '<span class="gt-amount-cell" @click="$emit(\'click\')">{{ value }}</span>',
    props: ['value', 'clickable'],
    emits: ['click'],
  },
}

const directives = { loading: {} }

function dataRowCount(wrapper: any): number {
  const cols = wrapper.findAll('.el-table-column')
  if (cols.length === 0) return 0
  return cols[0].findAll('.cell').length
}

function amountCellsOf(wrapper: any, label: string): any[] {
  const col = wrapper
    .findAll('.el-table-column')
    .find((c: any) => c.attributes('data-label') === label)
  return col ? col.findAll('.gt-amount-cell') : []
}

function columnLabels(wrapper: any): string[] {
  return wrapper.findAll('.el-table-column').map((c: any) => c.attributes('data-label'))
}

function amountBearingColumnCount(wrapper: any): number {
  return wrapper
    .findAll('.el-table-column')
    .filter((c: any) => c.findAll('.gt-amount-cell').length > 0).length
}

const SAME_BY_COMPANY = [
  { company_code: 'SUB001', company_name: '子公司A', amount: '1000.00', source_project_id: 'proj-a' },
  { company_code: 'SUB002', company_name: '子公司B', amount: '3000.00', source_project_id: 'proj-b' },
]

function mountDialog(props: Record<string, any>) {
  return mount(ConsolBreakdownDialog, {
    props: { modelValue: true, projectId: 'parent-001', year: 2024, accountCode: '1001', ...props },
    global: { stubs, directives },
  })
}

describe('ConsolBreakdownDialog — T1 统一渲染契约', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPush.mockReset()
    mockNavPush.mockReset()
    mockMsgInfo.mockReset()
    mockMsgWarning.mockReset()
    mockLoadProjectOptions.mockClear()
    mockProjectOptions = []
  })

  it('按 by_company 渲染：四列、逐子公司一行、金额 / 抵销额走金额单元格、底部合并数', async () => {
    mockGet.mockResolvedValue({ has_breakdown: true, by_company: SAME_BY_COMPANY })

    const wrapper = mountDialog({ accountCode: '1001' })
    await flushPromises()

    expect(columnLabels(wrapper)).toEqual(['子公司名称', '金额', '占比', '抵销额'])
    expect(dataRowCount(wrapper)).toBe(SAME_BY_COMPANY.length)
    expect(amountBearingColumnCount(wrapper)).toBe(1)
    expect(wrapper.find('.consol-breakdown-footer').text()).toContain('4000')
  })

  it('调报表行穿透端点', async () => {
    mockGet.mockResolvedValue({ has_breakdown: true, by_company: SAME_BY_COMPANY })

    mountDialog({ accountCode: '1001' })
    await flushPromises()
    expect(mockGet).toHaveBeenCalledWith(
      '/api/consolidation/report/parent-001/2024/1001/consol-breakdown',
    )
    expect(mockGet.mock.calls.every((call: any[]) => !String(call[0]).includes('/notes/'))).toBe(true)
  })
})

describe('ConsolBreakdownDialog — 空态与降级', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPush.mockReset()
    mockNavPush.mockReset()
    mockMsgInfo.mockReset()
    mockMsgWarning.mockReset()
    mockLoadProjectOptions.mockClear()
    mockProjectOptions = []
  })

  it('has_breakdown=false → el-empty 显示后端 message', async () => {
    mockGet.mockResolvedValue({
      has_breakdown: false,
      by_company: [],
      message: '该报表行暂无合并明细（未生成合并试算）',
    })
    const wrapper = mountDialog({ accountCode: '1001' })
    await flushPromises()

    const empty = wrapper.find('.el-empty')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('未生成合并试算')
    expect(wrapper.find('.el-table').exists()).toBe(false)
  })

  it('report 端点未就绪（抛错）→ 友好空态降级不崩溃', async () => {
    mockGet.mockRejectedValue(new Error('404 not found'))
    const wrapper = mountDialog({ accountCode: '1001' })
    await flushPromises()

    const empty = wrapper.find('.el-empty')
    expect(empty.exists()).toBe(true)
    expect(empty.text()).toContain('Phase 2')
  })
})

describe('ConsolBreakdownDialog — 行点击跳转与权限（T3 / EH2）', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPush.mockReset()
    mockNavPush.mockReset()
    mockMsgInfo.mockReset()
    mockMsgWarning.mockReset()
    mockLoadProjectOptions.mockClear()
    mockProjectOptions = []
  })

  it('点击子公司行（有 source_project_id 且有权）→ emit jump + push 返回栈 + router 跳转', async () => {
    mockGet.mockResolvedValue({ has_breakdown: true, by_company: SAME_BY_COMPANY })
    mockProjectOptions = [
      { id: 'proj-a', name: '子公司A' },
      { id: 'proj-b', name: '子公司B' },
    ]
    const wrapper = mountDialog({ accountCode: '1001' })
    await flushPromises()

    await amountCellsOf(wrapper, '金额')[0].trigger('click')
    await flushPromises()

    const jumpEvents = wrapper.emitted('jump')
    expect(jumpEvents).toBeTruthy()
    expect(jumpEvents![0][0]).toMatchObject({ source_project_id: 'proj-a' })
    expect(mockNavPush).toHaveBeenCalled()
    expect(mockPush).toHaveBeenCalledWith({
      path: '/projects/proj-a/reports',
      query: { year: '2024' },
    })
  })

  it('行缺 source_project_id → 仅 emit jump + ElMessage.info 不跳转', async () => {
    mockGet.mockResolvedValue({
      has_breakdown: true,
      by_company: [{ company_code: 'SUB001', company_name: '子公司A', amount: '1000.00' }],
    })
    const wrapper = mountDialog({ accountCode: '1001' })
    await flushPromises()

    await amountCellsOf(wrapper, '金额')[0].trigger('click')
    await flushPromises()

    expect(wrapper.emitted('jump')).toBeTruthy()
    expect(mockMsgInfo).toHaveBeenCalled()
    expect(mockPush).not.toHaveBeenCalled()
  })

  it('EH2：无目标子公司项目访问权 → ElMessage.warning 不跳转', async () => {
    mockGet.mockResolvedValue({ has_breakdown: true, by_company: SAME_BY_COMPANY })
    mockProjectOptions = [{ id: 'other-proj', name: '其他项目' }]
    const wrapper = mountDialog({ accountCode: '1001' })
    await flushPromises()

    await amountCellsOf(wrapper, '金额')[0].trigger('click')
    await flushPromises()

    expect(wrapper.emitted('jump')).toBeTruthy()
    expect(mockMsgWarning).toHaveBeenCalledWith('无权访问该子公司项目')
    expect(mockNavPush).not.toHaveBeenCalled()
    expect(mockPush).not.toHaveBeenCalled()
  })
})
