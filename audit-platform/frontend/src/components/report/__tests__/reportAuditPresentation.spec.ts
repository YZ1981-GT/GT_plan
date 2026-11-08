import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, inject, provide, type PropType } from 'vue'
import { mount, type VueWrapper } from '@vue/test-utils'
vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
vi.mock('@/components/attachment/OutputAttachmentLinks.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/common/GtAmountCell.vue', () => ({ default: { props: ['value'], template: '<span class="amount">{{ value }}</span>' } }))
import { mapReportConsistencyCheck } from '@/services/auditPlatformApi'
import { getReportBalancePresentation } from '@/services/reportCheckPresentation'
import ReportBalanceBanner from '@/components/report/ReportBalanceBanner.vue'
import ReportTraceDialogs from '@/components/report/ReportTraceDialogs.vue'

// 只替换 UI 容器；默认/具名插槽仍按真实表格逐行渲染。
const Container = defineComponent({ setup: (_props, { slots }) => () => h('div', [slots.label?.(), slots.default?.()]) })
const Button = defineComponent({ setup: (_props, { slots, attrs }) => () => h('button', attrs, slots.default?.()) })
const Alert = defineComponent({
  props: { title: String, type: String },
  setup: props => () => h('aside', { 'data-alert-type': props.type }, props.title),
})
const reportRowKey = Symbol('synthetic-report-row')
const Row = defineComponent({
  props: { row: { type: Object as PropType<Record<string, unknown>>, required: true } },
  setup(props, { slots }) {
    provide(reportRowKey, props.row)
    return () => h('article', slots.default?.())
  },
})
const Column = defineComponent({ setup(_props, { slots }) {
  const row = inject<Record<string, unknown>>(reportRowKey)!
  return () => h('div', slots.default?.({ row }))
} })
const Table = defineComponent({
  props: { data: { type: Array as PropType<Record<string, unknown>[]>, default: () => [] }, rowClassName: { type: Function, default: () => '' } },
  setup: (props, { slots }) => () => h('section', props.data.map(row =>
    h(Row, { row, class: props.rowClassName({ row }) }, { default: () => slots.default?.() }),
  )),
})
const wrappers: VueWrapper[] = []
afterEach(() => { wrappers.splice(0).forEach(wrapper => { wrapper.unmount() }) })
const global = { stubs: { ElDialog: Container, ElTabs: Container, ElTabPane: Container,
  ElButton: Button, ElAlert: Alert, ElEmpty: Container, ElTable: Table, ElTableColumn: Column }, directives: { loading: () => {} } }
const synthetic = () => mapReportConsistencyCheck({ total: 999, failed_count: 0, hint_count: 1, checks: [
  { name: '通过项', status: 'passed', expected: 0, actual: 0, diff: 0 },
  { name: '利润表提示', status: 'failed', severity: 'warning', expected: 0, actual: null, reason: '请核对口径' },
  { name: '未执行项', status: 'not_executed', reason: '尚未生成' },
  { name: '不适用项', status: 'not_applicable' }, { name: '错误项', status: 'error', severity: 'error', message: '无法取数' },
] })

function renderAudit(result = synthetic()) {
  const wrapper = mount(ReportTraceDialogs, { props: { showAuditDialog: true, consistencyResult: result,
    auditTab: 'all', filteredAuditChecks: result.checks, showTraceSelectDialog: false, traceSelectOptions: [],
    traceSelectCheck: null, rvTraceDialogVisible: false, rvTraceLoading: false, rvTraceResult: null,
    parseTraceLocations: check => check.name === '利润表提示' ? [{ label: '利润表', tab: 'income_statement', rowCode: '' }] : [],
  }, global })
  wrappers.push(wrapper)
  return wrapper
}

describe('真实审核横幅和弹窗', () => {
  it('横幅展开全部五态，0 不丢、缺数占位、原因严重度及后端 S2 计数可见', async () => {
    const wrapper = mount(ReportBalanceBanner, { props: { result: getReportBalancePresentation(synthetic()) }, global })
    wrappers.push(wrapper)
    expect(wrapper.get('[data-testid="report-balance-banner"]').classes()).toContain('gt-rv-balance-bar--error')
    await wrapper.findAll('button')[0].trigger('click')
    expect(wrapper.findAll('[data-check-status]').map(node => node.attributes('data-check-status'))).toEqual([
      'passed', 'failed', 'not_executed', 'not_applicable', 'error',
    ])
    expect(wrapper.text()).toContain('期望 0，实际 0，差 0')
    expect(wrapper.text()).toContain('实际 —')
    expect(wrapper.text()).toContain('原因：请核对口径')
    expect(wrapper.text()).toContain('严重度：警告')
    expect(wrapper.text()).toContain('后端汇总：失败 0 项，提示 1 项')
    await wrapper.findAll('button').find(button => button.text().includes('定位'))!.trigger('click')
    expect(wrapper.emitted('locate')?.[0]).toEqual(['通过项'])
  })

  it('弹窗显示五态各自计数；提示性失败仍未通过，但不使用阻断失败行', async () => {
    const wrapper = renderAudit()
    for (const status of ['passed', 'failed', 'not_executed', 'not_applicable', 'error']) {
      expect(wrapper.get(`[data-check-count="${status}"] .gt-rv-audit-stat-num`).text()).toBe('1')
    }
    expect(wrapper.get('.gt-rv-audit-hint-row').text()).toContain('未通过')
    expect(wrapper.get('.gt-rv-audit-hint-row').classes()).not.toContain('gt-rv-audit-fail-row')
    expect(wrapper.findAll('.gt-rv-audit-fail-row')).toHaveLength(1)
    expect(wrapper.findAll('.amount').map(node => node.text())).toEqual(['0', '0', '0', '0'])
    expect(wrapper.text()).toContain('请核对口径')
    expect(wrapper.text()).toContain('警告')
    expect(wrapper.text()).toContain('无法取数')
    const locate = wrapper.findAll('button').find(button => button.text().includes('📍 利润表'))!
    expect(locate).toBeDefined()
    await locate.trigger('click')
    expect(wrapper.emitted('trace-jump')?.[0]).toEqual([{ label: '利润表', tab: 'income_statement', rowCode: '' }])
    await wrapper.findAll('button').find(button => button.text().includes('导出审核报告'))!.trigger('click')
    expect(wrapper.emitted('audit-export-excel')).toHaveLength(1)
  })

  it('只有通过汇总没有明细时仍显示未验证，no_result 也不能隐藏真实明细', () => {
    const result = mapReportConsistencyCheck({ consistent: true, no_result: false, total: 7, checks: [] })
    const summary = renderAudit(result)
    expect(summary.get('[data-check-count="passed"] .gt-rv-audit-stat-num').text()).toBe('0')
    expect(summary.findAll('[data-check-status]')).toHaveLength(0)
    expect(summary.get('[data-alert-type]').attributes('data-alert-type')).toBe('info')
    expect(summary.get('[data-alert-type]').text()).toContain('未验证：暂无审核明细')
    const banner = mount(ReportBalanceBanner, { props: { result: getReportBalancePresentation(result) }, global })
    wrappers.push(banner)
    expect(banner.get('[data-testid="report-balance-banner"]').classes()).toContain('gt-rv-balance-bar--unverified')
    expect(banner.get('[data-testid="report-balance-banner"]').classes()).not.toContain('gt-rv-balance-bar--passed')
    expect(banner.text()).toContain('汇总信息不能证明检查通过')
    const withDetails = renderAudit({ ...synthetic(), noResult: true })
    expect(withDetails.findAll('[data-check-status]')).toHaveLength(5)
  })

  it('仅有提示性失败时横幅和弹窗保持提示态而非通过态；新结果会收起旧展开项', async () => {
    const result = mapReportConsistencyCheck({ failed_count: 0, hint_count: 1, checks: [
      { name: '提示项', status: 'failed', severity: 'info', reason: '需要人工核对' },
    ] })
    const audit = renderAudit(result)
    expect(audit.get('[data-check-count="failed"] .gt-rv-audit-stat-num').text()).toBe('1')
    expect(audit.get('[data-check-count="passed"] .gt-rv-audit-stat-num').text()).toBe('0')
    expect(audit.get('[data-alert-type]').attributes('data-alert-type')).toBe('warning')
    expect(audit.findAll('.gt-rv-audit-hint-row')).toHaveLength(1)
    expect(audit.findAll('.gt-rv-audit-fail-row')).toHaveLength(0)
    const banner = mount(ReportBalanceBanner, { props: { result: getReportBalancePresentation(result) }, global })
    wrappers.push(banner)
    expect(banner.get('[data-testid="report-balance-banner"]').classes()).toContain('gt-rv-balance-bar--hint')
    await banner.findAll('button')[0].trigger('click')
    expect(banner.get('[data-check-status="failed"]').text()).toContain('未通过')
    await banner.setProps({ result: getReportBalancePresentation(mapReportConsistencyCheck({ checks: [
      { name: '新结果', status: 'passed' },
    ] })) })
    expect(banner.findAll('[data-check-status]')).toHaveLength(0)
    expect(banner.text()).toContain('展开明细')
  })
})
