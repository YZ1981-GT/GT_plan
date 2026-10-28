/**
 * ConsolBreakdownDialog 单测 — 报表页右键「查看合并明细」（spec consol-autotree-linkage-closure R8.2 / 任务 20）
 *
 * 新契约：报表行次读时计算（与合并报表差额表同一求值）——列 下级节点 / 来源 / 金额 / 占比；
 * 底部合并数取后端合计（不在前端求和）并列出本级抵销与调整；差额户整行高亮；取不到数的格显示「留空」带原因；
 * 纯数字科目码沿用已落库穿透（比例 → 百分数）。进入项目：单体 → 单体报表，下级合并 → 其合并报表，差额户不可进入；
 * 前端访问预检只用于提示（项目列表达到分页上限时不拦）。
 */
import fs from 'node:fs'
import path from 'node:path'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const { getConsolRowBreakdown, mockPush, mockNavPush, mockLoadProjectOptions, msg, store } = vi.hoisted(() => ({
  getConsolRowBreakdown: vi.fn(),
  mockPush: vi.fn(),
  mockNavPush: vi.fn(),
  mockLoadProjectOptions: vi.fn(),
  msg: { info: vi.fn(), warning: vi.fn() },
  store: { options: [] as Array<{ id: string; name: string }> },
}))
vi.mock('@/services/consolidationApi', () => ({ getConsolRowBreakdown: (...a: any[]) => getConsolRowBreakdown(...a) }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useRoute: () => ({ fullPath: '/projects/parent-001/reports', query: {} }),
}))
vi.mock('@/composables/useNavigationStack', () => ({ useNavigationStack: () => ({ push: mockNavPush }) }))
vi.mock('@/stores/project', () => ({
  useProjectStore: () => ({ loadProjectOptions: mockLoadProjectOptions, get projectOptions() { return store.options } }),
}))
vi.mock('element-plus', () => ({ ElMessage: msg }))

import ConsolBreakdownDialog from '../ConsolBreakdownDialog.vue'
import { PROJECT_OPTIONS_PAGE_SIZE } from '../composables/consolEntityView'

const stubs: Record<string, any> = {
  'el-dialog': {
    template: '<div class="el-dialog"><div class="title">{{ title }}</div><slot /><slot name="footer" /></div>',
    props: ['modelValue', 'title', 'width', 'appendToBody'],
  },
  'el-table': {
    template: '<table class="el-table"><slot /></table>',
    props: ['data', 'rowClassName'],
    provide() {
      const self = this as any
      return { getTableData: () => self.data, getRowClass: (row: any) => self.rowClassName?.({ row }) || '' }
    },
  },
  'el-table-column': {
    inject: ['getTableData', 'getRowClass'],
    props: ['label'],
    template: '<th class="el-table-column" :data-label="label"><span v-for="(row, i) in getTableData()" :key="i" class="cell" :class="getRowClass(row)"><slot :row="row" /></span></th>',
  },
  'el-empty': { template: '<div class="el-empty">{{ description }}</div>', props: ['description'] },
  'el-alert': { template: '<div class="el-alert" :data-testid="$attrs[\'data-testid\']">{{ title }}</div>', props: ['title'] },
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>', emits: ['click'] },
  // 与真实组件一致：只有 clickable 时才发 click
  GtAmountCell: {
    template: '<span class="gt-amount-cell" @click="clickable && $emit(\'click\')">{{ value }}</span>',
    props: ['value', 'clickable'],
    emits: ['click'],
  },
}

const READ_TIME = {
  account_code: 'BS-002', row_code: 'BS-002', row_name: '应收账款', report_type: 'balance_sheet',
  node_key: 'G:consol', node_label: '某集团（合并户）', basis: 'read_time', linear: true,
  consolidated: '3500.00', elimination: '-500.00', has_breakdown: true, message: null,
  by_company: [
    { company_code: 'G', company_name: '某集团（差额户）', amount: '-500.00', ratio: '-0.1429', pct: '-14.29',
      node_key: 'G:consol_elim', kind: 'elim', source: '抵销与调整', source_project_id: null, reason: null },
    { company_code: 'G', company_name: '某集团（单体母公司户）', amount: '1000.00', ratio: '0.2857', pct: '28.57',
      node_key: 'G:parent', kind: 'data', source: '个别数', source_project_id: 'proj-g', reason: null },
    { company_code: 'A', company_name: '甲公司（合并户）', amount: '3000.00', ratio: '0.8571', pct: '85.71',
      node_key: 'A:consol', kind: 'aggregate', source: '下级汇总', source_project_id: 'proj-a', reason: null },
    { company_code: 'B', company_name: '乙公司', amount: null, ratio: null, pct: null,
      node_key: 'B:subsidiary', kind: 'data', source: '个别数', source_project_id: 'proj-b', reason: '该企业本年度没有单体项目' },
  ],
}

function mountDialog(props: Record<string, any> = {}) {
  return mount(ConsolBreakdownDialog, {
    props: { modelValue: true, projectId: 'parent-001', year: 2024, accountCode: 'BS-002', ...props },
    global: { stubs, directives: { loading: {} } },
  })
}
const column = (w: any, label: string) => w.findAll('.el-table-column').find((c: any) => c.attributes('data-label') === label)

beforeEach(() => {
  getConsolRowBreakdown.mockReset().mockResolvedValue(READ_TIME)
  mockPush.mockReset()
  mockNavPush.mockReset()
  mockLoadProjectOptions.mockReset().mockResolvedValue(undefined)
  msg.info.mockReset()
  msg.warning.mockReset()
  store.options = [{ id: 'proj-g', name: '某集团' }, { id: 'proj-a', name: '甲公司' }]
})

describe('ConsolBreakdownDialog — 读时计算契约', () => {
  it('四列；合并数取后端合计（不是前端求和），列出本级抵销与调整；差额户高亮；留空带原因；占比用后端百分数', async () => {
    const wrapper = mountDialog()
    await flushPromises()
    expect(getConsolRowBreakdown).toHaveBeenCalledWith('parent-001', 2024, 'BS-002', undefined)
    expect(wrapper.findAll('.el-table-column').map((c: any) => c.attributes('data-label'))).toEqual(['下级节点', '来源', '金额', '占比'])
    expect(wrapper.find('.title').text()).toBe('查看合并明细 · 应收账款')
    expect(wrapper.find('[data-testid="cbd-node"]').text()).toBe('汇总节点：某集团（合并户）')
    const footer = wrapper.find('[data-testid="cbd-footer"]')
    expect(footer.text()).toContain('3500.00')
    expect(footer.text()).toContain('其中本级抵销与调整')
    expect(footer.text()).toContain('-500.00')
    const nameCells = column(wrapper, '下级节点').findAll('.cell')
    expect(nameCells[0].classes()).toContain('cbd-row-elim')
    expect(nameCells[1].classes()).not.toContain('cbd-row-elim')
    expect(column(wrapper, '来源').findAll('.cell').map((c: any) => c.text())).toEqual(['抵销与调整', '个别数', '下级汇总', '个别数'])
    const amountCells = column(wrapper, '金额').findAll('.cell')
    expect(amountCells[3].text()).toBe('留空')
    expect(amountCells[3].find('.cbd-blank').attributes('title')).toBe('该企业本年度没有单体项目')
    expect(column(wrapper, '占比').findAll('.cell').map((c: any) => c.text())).toEqual(['-14.29%', '28.57%', '85.71%', '—'])
  })

  it('按所选汇总节点读取；非线性说明显示在表上方', async () => {
    getConsolRowBreakdown.mockResolvedValueOnce({ ...READ_TIME, linear: false, elimination: null, message: '公式非线性，只给合计，不按企业分解' })
    const wrapper = mountDialog({ nodeKey: 'A:consol' })
    await flushPromises()
    expect(getConsolRowBreakdown).toHaveBeenCalledWith('parent-001', 2024, 'BS-002', 'A:consol')
    expect(wrapper.find('[data-testid="cbd-message"]').text()).toBe('公式非线性，只给合计，不按企业分解')
    expect(wrapper.find('[data-testid="cbd-footer"]').text()).not.toContain('其中本级抵销与调整')
  })

  it('纯数字科目码（已落库穿透）：比例换算为百分数', async () => {
    getConsolRowBreakdown.mockResolvedValueOnce({
      account_code: '1122', has_breakdown: true, message: null, consolidated: '4000.00', elimination: '0.00', individual_sum: '4000.00',
      by_company: [
        { company_code: 'SUB001', company_name: '子公司A', amount: '1000.00', ratio: '0.2500', source_project_id: 'proj-g' },
        { company_code: 'SUB002', company_name: '子公司B', amount: '3000.00', ratio: '0.7500' },
      ],
    })
    const wrapper = mountDialog({ accountCode: '1122' })
    await flushPromises()
    expect(column(wrapper, '占比').findAll('.cell').map((c: any) => c.text())).toEqual(['25.00%', '75.00%'])
    expect(column(wrapper, '来源').findAll('.cell').map((c: any) => c.text())).toEqual(['—', '—'])
    expect(wrapper.find('[data-testid="cbd-footer"]').text()).toContain('4000.00')
  })
})

describe('ConsolBreakdownDialog — 空态与失败', () => {
  it('合并数留空（has_breakdown=false）→ 空态显示后端原因，不显示表格', async () => {
    getConsolRowBreakdown.mockResolvedValueOnce({ ...READ_TIME, by_company: [], consolidated: null, has_breakdown: false, message: '该行合并数留空：公式引用了年初余额' })
    const wrapper = mountDialog()
    await flushPromises()
    expect(wrapper.find('.el-empty').text()).toContain('该行合并数留空：公式引用了年初余额')
    expect(wrapper.find('.el-table').exists()).toBe(false)
  })

  it('读取失败：有后端说明就显示说明，否则通用中文提示（不显示英文错误）', async () => {
    getConsolRowBreakdown.mockRejectedValueOnce({ response: { status: 404, data: { detail: '报表行 BS-999 不存在' } } })
    const wrapper = mountDialog({ accountCode: 'BS-999' })
    await flushPromises()
    expect(wrapper.find('.el-empty').text()).toBe('读取合并明细失败：报表行 BS-999 不存在')

    getConsolRowBreakdown.mockRejectedValueOnce(new Error('Request failed with status code 500'))
    const other = mountDialog()
    await flushPromises()
    expect(other.find('.el-empty').text()).toBe('读取合并明细失败，请稍后重试')
  })
})

describe('ConsolBreakdownDialog — 进入项目', () => {
  it('单体数据节点 → 单体报表；下级合并节点 → 其合并报表；均入返回栈并关闭弹窗', async () => {
    const wrapper = mountDialog()
    await flushPromises()
    const links = wrapper.findAll('[data-testid="cbd-enter"]')
    expect(links.map((l: any) => l.text())).toEqual(['某集团（单体母公司户）', '甲公司（合并户）', '乙公司'])
    await links[0].trigger('click')
    await flushPromises()
    expect(mockPush).toHaveBeenLastCalledWith({ path: '/projects/proj-g/reports', query: { year: '2024' } })
    expect(mockNavPush).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([false])
    await links[1].trigger('click')
    await flushPromises()
    expect(mockPush).toHaveBeenLastCalledWith({ path: '/projects/proj-a/consolidation', query: { year: '2024', tab: 'report' } })
  })

  it('差额户不可进入；不在可见项目内 ⇒ 无权提示不跳；项目列表达到分页上限时不拦', async () => {
    const wrapper = mountDialog()
    await flushPromises()
    // 差额户：名称不是链接、金额不可点
    await column(wrapper, '金额').findAll('.gt-amount-cell')[0].trigger('click')
    await flushPromises()
    expect(wrapper.emitted('jump')).toBeFalsy()
    expect(mockPush).not.toHaveBeenCalled()

    await wrapper.findAll('[data-testid="cbd-enter"]')[2].trigger('click') // 乙公司 proj-b 不在可见列表
    await flushPromises()
    expect(wrapper.emitted('jump')?.[0][0]).toMatchObject({ source_project_id: 'proj-b' })
    expect(msg.warning).toHaveBeenCalledWith('无权访问该企业项目')
    expect(mockPush).not.toHaveBeenCalled()

    store.options = Array.from({ length: PROJECT_OPTIONS_PAGE_SIZE }, (_, i) => ({ id: `p-${i}`, name: `项目${i}` }))
    await wrapper.findAll('[data-testid="cbd-enter"]')[2].trigger('click')
    await flushPromises()
    expect(mockPush).toHaveBeenLastCalledWith({ path: '/projects/proj-b/reports', query: { year: '2024' } })
  })

  it('分页上限与项目下拉的 page_size 一致（截断判断才成立）', () => {
    const src = fs.readFileSync(path.resolve(__dirname, '../../../stores/project.ts'), 'utf-8')
    expect(src).toContain(`params: { page_size: ${PROJECT_OPTIONS_PAGE_SIZE} }`)
  })
})
