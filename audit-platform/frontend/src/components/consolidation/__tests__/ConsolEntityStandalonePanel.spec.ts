/**
 * 数据节点显示单体项目的报表与附注（spec consol-autotree-linkage-closure R6，ADR-CAL-007）
 *
 * - 读单体项目已有接口（报表 /api/reports/{pid}/{year}/{type}、附注 /api/disclosure-notes/{pid}/{year}[/{section}]），只读；
 * - 没有单体项目 / 无权查看 / 尚未生成（含接口返回金额全空的模板行次）时给中文说明，不拿合并口径冒充；
 * - 附注按单体模板表头呈现：多级表头（rowspan / colspan）、续表并入主表、合计行加粗、正文只显示纯文字；
 * - 「进入该企业项目」交给合并页跳转。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

const { get, store } = vi.hoisted(() => ({
  get: vi.fn(),
  store: { loadProjectOptions: vi.fn(), projectOptions: [] as Array<{ id: string; name: string }> },
}))
vi.mock('@/services/apiProxy', () => ({ api: { get: (...a: any[]) => get(...a) } }))
vi.mock('@/stores/project', () => ({ useProjectStore: () => store }))

import ConsolEntityStandalonePanel from '../ConsolEntityStandalonePanel.vue'
import ConsolNodeContextBar from '../ConsolNodeContextBar.vue'
import {
  headerRows,
  noteCellText,
  plainText,
  reportNotGenerated,
  stateFromError,
} from '../composables/consolEntityView'
import { buildColumnTree } from '../composables/consolNoteColumns'

const Btn = defineComponent({
  inheritAttrs: false,
  emits: ['click'],
  setup(_, { slots, emit, attrs }) {
    return () => h('button', { 'data-testid': (attrs as any)['data-testid'], onClick: () => emit('click') }, slots.default?.())
  },
})
const STUBS = { 'el-button': Btn, 'el-input': true, 'el-empty': true, 'el-tag': { template: '<span><slot /></span>' } }

const ENTITY = { projectId: 'p-a', name: '甲公司', companyCode: 'A', nodeKey: 'A:subsidiary' }

function mountPanel(props: Record<string, unknown>) {
  return mount(ConsolEntityStandalonePanel, {
    props: { mode: 'report', entity: ENTITY, year: 2025, reportType: 'balance_sheet', ...props },
    global: { stubs: STUBS, directives: { loading: {} } },
  })
}

const MH_TABLE = {
  name: '按账龄披露',
  headers: ['账龄', '金额', '比例', '金额', '比例'],
  multi_header: [['账龄', '期末数', '', '期初数', ''], ['', '金额', '比例', '金额', '比例']],
  rows: [
    { label: '1年以内', values: [100, '60%', 80, '50%'] },
    { label: '合计', values: [166.5, '100%', 160, '100%'], is_total: true },
  ],
}

describe('consolEntityView 纯逻辑', () => {
  it('多级表头：分组跨列、叶子跨到最底行；单元格数字千分位两位小数、文字原样、空值为空', () => {
    const rows = headerRows(buildColumnTree(MH_TABLE))
    expect(rows.map((r) => r.map((c) => [c.label, c.colspan, c.rowspan]))).toEqual([
      [['账龄', 1, 2], ['期末数', 2, 1], ['期初数', 2, 1]],
      [['金额', 1, 1], ['比例', 1, 1], ['金额', 1, 1], ['比例', 1, 1]],
    ])
    expect(noteCellText(MH_TABLE.rows[1], 0)).toBe('合计')
    expect(noteCellText(MH_TABLE.rows[1], 1)).toBe('166.50')
    expect(noteCellText({ label: 'x', values: ['1,234.5'] }, 1)).toBe('1,234.50')
    expect(noteCellText(MH_TABLE.rows[0], 2)).toBe('60%')
    expect(noteCellText({ label: 'x', values: [null] }, 1)).toBe('')
  })

  it('正文只取纯文字；报表金额全空视为未生成；接口状态码 → 中文状态', () => {
    expect(plainText('<p>第一段</p><p>第二段<script>alert(1)</script></p>')).toBe('第一段\n第二段alert(1)')
    expect(plainText('纯文字')).toBe('纯文字')
    expect(reportNotGenerated([{ current_period_amount: null, prior_period_amount: null }])).toBe(true)
    expect(reportNotGenerated([{ current_period_amount: '0.00', prior_period_amount: null }])).toBe(false)
    expect([stateFromError({ response: { status: 403 } }), stateFromError({ response: { status: 404 } }), stateFromError(new Error('x'))])
      .toEqual(['forbidden', 'not_generated', 'failed'])
  })
})

describe('ConsolEntityStandalonePanel', () => {
  beforeEach(() => {
    get.mockReset()
    store.loadProjectOptions.mockReset()
    store.projectOptions = [{ id: 'p-a', name: '甲公司' }, { id: 'p-g', name: '某集团' }]
  })

  it('报表：读单体项目报表（静默错误，自己给说明），显示本期 / 上期；「进入该企业项目」交给合并页', async () => {
    get.mockResolvedValue([
      { row_code: 'BS-001', row_name: '流动资产：', indent_level: 0, current_period_amount: null, prior_period_amount: null },
      { row_code: 'BS-002', row_name: '货币资金', indent_level: 1, current_period_amount: '400.00', prior_period_amount: '300.00' },
    ])
    const wrapper = mountPanel({})
    await flushPromises()
    expect(get).toHaveBeenCalledWith('/api/reports/p-a/2025/balance_sheet', { _silent: true })
    expect(wrapper.find('[data-testid="cesp-title"]').text()).toContain('甲公司 · 单体项目报表（只读）')
    expect(wrapper.find('[data-testid="cesp-cur-BS-002"]').text()).toBe('400.00')
    await wrapper.find('[data-testid="cesp-enter"]').trigger('click')
    expect(wrapper.emitted('enter-project')).toHaveLength(1)

    get.mockResolvedValue([{ row_code: 'BS-002', row_name: '货币资金', current_period_amount: null, prior_period_amount: null }])
    await wrapper.setProps({ reportType: 'income_statement' })
    await flushPromises()
    expect(get).toHaveBeenLastCalledWith('/api/reports/p-a/2025/income_statement', { _silent: true })
    expect(wrapper.find('[data-testid="cesp-state"]').text()).toBe('该企业单体项目尚未生成报表')
  })

  it('没有单体项目 / 不在本人可见项目 / 接口 403 / 矩阵报表：中文说明，不请求或不显示数据', async () => {
    const none = mountPanel({ entity: { ...ENTITY, projectId: null } })
    await flushPromises()
    expect(none.find('[data-testid="cesp-state"]').text()).toBe('该企业本年度没有单体项目，无法显示单体报表与附注')
    expect(none.find('[data-testid="cesp-enter"]').exists()).toBe(false)
    expect(get).not.toHaveBeenCalled()

    store.projectOptions = [{ id: 'p-g', name: '某集团' }]
    const hidden = mountPanel({})
    await flushPromises()
    expect(hidden.find('[data-testid="cesp-state"]').text()).toContain('无权查看')
    expect(hidden.find('[data-testid="cesp-enter"]').exists()).toBe(false)
    expect(get).not.toHaveBeenCalled()

    store.projectOptions = [{ id: 'p-a', name: '甲公司' }]
    get.mockRejectedValue({ response: { status: 403 } })
    const denied = mountPanel({ mode: 'note' })
    await flushPromises()
    expect(denied.find('[data-testid="cesp-state"]').text()).toContain('无权查看')

    get.mockReset()
    const matrix = mountPanel({ reportType: 'equity_statement' })
    await flushPromises()
    expect(matrix.find('[data-testid="cesp-state"]').text()).toContain('请进入该企业项目查看')
    expect(get).not.toHaveBeenCalled()
  })

  it('附注：目录按模板顺序，默认打开第一个有数据的章节；多级表头、续表并入、合计加粗、正文纯文字', async () => {
    get.mockImplementation((url: string) => {
      if (url === '/api/disclosure-notes/p-a/2025') {
        return Promise.resolve([
          { note_section: '五、2', section_title: '应收账款', sort_order: 20, has_data: true },
          { note_section: '五、1', section_title: '货币资金', sort_order: 10, has_data: false },
        ])
      }
      return Promise.resolve({
        note_section: '五、2', section_title: '应收账款', text_content: '<p>期末无单项计提。</p>',
        table_data: { _tables: [
          MH_TABLE,
          { name: '前五名', headers: ['单位', '期末余额'], rows: [{ label: '乙公司', values: [30] }] },
          { name: '前五名（续）', headers: ['单位', '占比'], rows: [{ label: '乙公司', values: ['18%'] }] },
        ] },
      })
    })
    const wrapper = mountPanel({ mode: 'note' })
    await flushPromises()
    const items = wrapper.findAll('[data-testid^="cesp-section-"]')
    expect(items.map((i) => i.attributes('data-testid'))).toEqual(['cesp-section-五、1', 'cesp-section-五、2'])
    expect(items[0].classes()).toContain('is-empty')
    expect(get).toHaveBeenLastCalledWith('/api/disclosure-notes/p-a/2025/五、2', { _silent: true })
    expect(wrapper.find('[data-testid="ntr-title"]').text()).toBe('五、2 应收账款')
    const table = wrapper.find('[data-testid="ntr-table-0"]')
    expect(table.findAll('thead tr')).toHaveLength(2)
    expect(table.findAll('thead th').map((th) => th.attributes('colspan'))).toEqual(['1', '2', '2', '1', '1', '1', '1'])
    expect(table.findAll('thead th')[0].attributes('rowspan')).toBe('2')
    const total = table.findAll('tbody tr')[1]
    expect(total.classes()).toContain('gt-ntr-total')
    expect(total.findAll('td').map((td) => td.text())).toEqual(['合计', '166.50', '100%', '160.00', '100%'])
    // 续表并入同名主表右侧（与附注编辑器同一投影）：三张源表 ⇒ 两张
    expect(wrapper.findAll('table.gt-ntr-table')).toHaveLength(2)
    expect(wrapper.find('[data-testid="ntr-table-1"]').findAll('thead th').map((th) => th.text())).toEqual(['单位', '期末余额', '占比'])
    expect(wrapper.find('[data-testid="ntr-table-1"]').findAll('tbody td').map((td) => td.text())).toEqual(['乙公司', '30.00', '18%'])
    expect(wrapper.find('[data-testid="ntr-text"]').text()).toBe('期末无单项计提。')

    get.mockImplementation(() => Promise.reject({ response: { status: 404 } }))
    const empty = mountPanel({ mode: 'note' })
    await flushPromises()
    expect(empty.find('[data-testid="cesp-state"]').text()).toBe('该企业单体项目尚未生成附注')
  })
})

describe('ConsolNodeContextBar', () => {
  const node = (key: string, kind: string, extra: Record<string, unknown> = {}) => {
    const [code, role] = key.split(':')
    return { node_key: key, company_code: code, company_name: '某集团', display_name: `某集团（${role}）`, role, kind, project_id: null, children: [], ...extra } as any
  }

  it('显示当前节点与口径；差额户给「📝 差额分录」，有项目的数据节点给「进入该企业项目」，非根节点可回到合并户', async () => {
    const elim = mount(ConsolNodeContextBar, { props: { node: node('G:consol_elim', 'elim'), isRoot: false }, global: { stubs: STUBS } })
    expect(elim.find('[data-testid="consol-node-bar-basis"]').text()).toBe('口径：本级调整与抵销')
    await elim.find('[data-testid="consol-node-bar-elim"]').trigger('click')
    expect(elim.emitted('open-elim')).toHaveLength(1)
    await elim.find('[data-testid="consol-node-bar-root"]').trigger('click')
    expect(elim.emitted('go-root')).toHaveLength(1)

    const data = mount(ConsolNodeContextBar, { props: { node: node('G:hq', 'data', { project_id: 'p-gs' }), isRoot: false }, global: { stubs: STUBS } })
    expect(data.find('[data-testid="consol-node-bar-basis"]').text()).toBe('口径：单体项目')
    expect(data.find('[data-testid="consol-node-bar-elim"]').exists()).toBe(false)
    await data.find('[data-testid="consol-node-bar-enter"]').trigger('click')
    expect(data.emitted('enter-project')).toHaveLength(1)

    const root = mount(ConsolNodeContextBar, { props: { node: node('G:consol', 'aggregate'), isRoot: true }, global: { stubs: STUBS } })
    expect(root.find('[data-testid="consol-node-bar-basis"]').text()).toBe('口径：合并口径')
    expect(root.find('[data-testid="consol-node-bar-root"]').exists()).toBe(false)
    expect(root.find('[data-testid="consol-node-bar-enter"]').exists()).toBe(false)
  })
})
