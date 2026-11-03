/**
 * queryEntryContext.spec.ts — 打开高级查询时的入口上下文（advanced-query-linkage-closure 任务 27；ADR-AQL-15，R10.1~R10.3、R10.5）
 *
 * 纯函数：路由 → 预选源；模板库按钮的模板口径源 URI → 注册表源键（AQ-38，变异 #33）；弹窗打开时的项目 / 年度 / 预选源；
 * 模板库页只认路由明确带的项目，页面自取的演示项目不进弹窗（B11 评审 F1，变异 B11r-a / B11r-b / B11r-c）。
 */
import { describe, it, expect } from 'vitest'
import {
  TEMPLATE_LIBRARY_ROUTE,
  TEMPLATE_NOTE_NOTICE,
  resolveDialogOpenContext,
  resolveQueryEntryContext,
  resolveTemplateLibrarySource,
} from '../queryEntryContext'

const PID = '005a6f2d-cecd-4e30-bcbd-9fb01236c194'
const OTHER = '5942c12e-65fb-4187-ace3-79d45a90cb53'
// 不带项目传 null（传 undefined 会落到缺省值 PID）
const r = (name: string, query: Record<string, unknown> = {}, projectId: string | null = PID) =>
  ({ name, params: projectId ? { projectId } : {}, query })

describe('resolveQueryEntryContext — 各业务页预选的数据源（R10.3）', () => {
  it('试算表 / 调整分录 / 辅助汇总 / 底稿编辑器', () => {
    expect(resolveQueryEntryContext(r('TrialBalance', { year: '2025' }))).toEqual({ projectId: PID, year: 2025, source: 'tb_detail' })
    expect(resolveQueryEntryContext(r('Adjustments')).source).toBe('adj_aje')
    expect(resolveQueryEntryContext(r('AuxSummary')).source).toBe('aux_balance')
    expect(resolveQueryEntryContext(r('WorkpaperEditor')).source).toBe('workpaper')
  })

  it('报表页按 ?tab 取报表类型；非报表页签（跨表核对 / 多年对比）与缺省都是资产负债表', () => {
    expect(resolveQueryEntryContext(r('Reports', { tab: 'income_statement' })).source).toBe('report_income_statement')
    expect(resolveQueryEntryContext(r('Reports', { tab: 'cross_check' })).source).toBe('report_balance_sheet')
    expect(resolveQueryEntryContext(r('Reports')).source).toBe('report_balance_sheet')
  })

  it('附注编辑器：有 ?section 时落该章节，否则附注目录', () => {
    expect(resolveQueryEntryContext(r('DisclosureNotes', { section: '八、1' })).source).toBe('disclosure_note:八、1')
    expect(resolveQueryEntryContext(r('DisclosureNotes')).source).toBe('disclosure')
  })

  it('账簿查询按 ?level：序时账 / 凭证 → 序时账，辅助两级同名，其余科目余额', () => {
    expect(resolveQueryEntryContext(r('LedgerPenetration', { level: 'ledger' })).source).toBe('ledger_entries')
    expect(resolveQueryEntryContext(r('LedgerPenetration', { level: 'voucher' })).source).toBe('ledger_entries')
    expect(resolveQueryEntryContext(r('LedgerPenetration', { level: 'aux_balance' })).source).toBe('aux_balance')
    expect(resolveQueryEntryContext(r('LedgerPenetration', { level: 'aux_ledger' })).source).toBe('aux_ledger')
    expect(resolveQueryEntryContext(r('LedgerPenetration')).source).toBe('account_balance')
  })

  it('其余页面不预选；年度只认 2000~2100 的整数（数组取第一个）', () => {
    expect(resolveQueryEntryContext(r('ProjectDashboard', { year: '2025' }))).toEqual({ projectId: PID, year: 2025 })
    expect(resolveQueryEntryContext(r('TrialBalance', { year: 'abc' })).year).toBeUndefined()
    expect(resolveQueryEntryContext(r('TrialBalance', { year: '1999' })).year).toBeUndefined()
    expect(resolveQueryEntryContext(r('TrialBalance', { year: ['2024', '2025'] })).year).toBe(2024)
    expect(resolveQueryEntryContext(null)).toEqual({})
  })
})

describe('resolveTemplateLibrarySource — 模板库「📊 高级查询」三种载荷（AQ-38，R10.5）', () => {
  it('报表模板 report:<类型> → report_<类型>', () => {
    expect(resolveTemplateLibrarySource('report:balance_sheet')).toEqual({ source: 'report_balance_sheet' })
    expect(resolveTemplateLibrarySource('report:cash_flow_statement')).toEqual({ source: 'report_cash_flow_statement' })
    expect(resolveTemplateLibrarySource('report:no_such_type')).toEqual({})
  })

  it('附注模板 note:<模板章节号> → 附注目录 + 编号体系提示（不猜对应章节）', () => {
    expect(resolveTemplateLibrarySource('note:五-1-1')).toEqual({ source: 'disclosure', notice: TEMPLATE_NOTE_NOTICE })
    expect(TEMPLATE_NOTE_NOTICE).toBe('模板章节号与项目附注编号不同，请在目录中选择章节')
  })

  it('底稿模板与注册表源键原样；空值不预选', () => {
    expect(resolveTemplateLibrarySource('workpaper:D2')).toEqual({ source: 'workpaper:D2' })
    expect(resolveTemplateLibrarySource('workpaper:D2|审定表D2-1')).toEqual({ source: 'workpaper:D2|审定表D2-1' })
    expect(resolveTemplateLibrarySource('ledger_entries')).toEqual({ source: 'ledger_entries' })
    expect(resolveTemplateLibrarySource('  ')).toEqual({})
    expect(resolveTemplateLibrarySource(undefined)).toEqual({})
  })
})

describe('resolveDialogOpenContext — 弹窗每次打开的项目、年度与预选源（R10.1、R10.2）', () => {
  it('侧栏打开（无事件）：项目随路由、年度取 ?year、按当前页预选源', () => {
    expect(resolveDialogOpenContext({ route: r('TrialBalance', { year: '2025' }) })).toEqual({
      projectId: PID, year: 2025, initialTab: 'basic', initialSource: 'tb_detail',
    })
  })

  it('非项目页：不预选项目、不预选源（不取列表第一项）', () => {
    expect(resolveDialogOpenContext({ route: r('Dashboard', {}, null) })).toEqual({ projectId: '', initialTab: 'basic' })
  })

  it('事件带的项目优先于路由；路由 ?year 不套到另一个项目上', () => {
    const ctx = resolveDialogOpenContext({ route: r('TrialBalance', { year: '2025' }), eventPayload: { project_id: OTHER } })
    expect(ctx).toEqual({ projectId: OTHER, initialTab: 'basic' })
    const same = resolveDialogOpenContext({ route: r('TrialBalance', { year: '2025' }), eventPayload: { project_id: PID } })
    expect(same.year).toBe(2025)
  })

  it('事件带的模板口径源经映射，附注模板带出提示；页签按事件', () => {
    const ctx = resolveDialogOpenContext({
      route: r(TEMPLATE_LIBRARY_ROUTE, { project_id: PID }, null),
      eventPayload: { source: 'note:五-1-1', project_id: PID, tab: 'advanced' },
    })
    expect(ctx).toEqual({ projectId: PID, initialTab: 'advanced', initialSource: 'disclosure', initialNotice: TEMPLATE_NOTE_NOTICE })
    expect(resolveDialogOpenContext({ route: r('Reports'), eventPayload: { source: 'report:balance_sheet' } }).initialSource)
      .toBe('report_balance_sheet')
  })

  it('模板库页 URL 不带项目：事件里的项目（页面自取的演示项目）不采纳，弹窗项目为空、年度不给（R10.1，AQ-37）', () => {
    expect(TEMPLATE_LIBRARY_ROUTE).toBe('TemplateLibraryMgmt')
    const ctx = resolveDialogOpenContext({
      route: r(TEMPLATE_LIBRARY_ROUTE, {}, null), eventPayload: { tab: 'basic', source: 'workpaper:E1', project_id: PID },
    })
    expect(ctx, '演示项目不应成为弹窗项目').toEqual({ projectId: '', initialTab: 'basic', initialSource: 'workpaper:E1' })
    const report = resolveDialogOpenContext({
      route: r(TEMPLATE_LIBRARY_ROUTE, { tab: 'report-config' }, null),
      eventPayload: { source: 'report:balance_sheet', project_id: OTHER },
    })
    expect(report.projectId, '报表模板同样不带演示项目').toBe('')
    expect(report.initialSource).toBe('report_balance_sheet')
  })

  it('模板库页 URL 带 ?project_id：事件项目与它一致才采纳，不一致取路由的；事件不带项目时为空', () => {
    const same = resolveDialogOpenContext({
      route: r(TEMPLATE_LIBRARY_ROUTE, { project_id: OTHER }, null), eventPayload: { source: 'workpaper:E1', project_id: OTHER },
    })
    expect(same.projectId, '路由明确带的项目').toBe(OTHER)
    expect(same.year, '模板库页不是该项目的项目页：年度交弹窗取该项目审计年度').toBeUndefined()
    const mismatch = resolveDialogOpenContext({
      route: r(TEMPLATE_LIBRARY_ROUTE, { project_id: OTHER }, null), eventPayload: { source: 'workpaper:E1', project_id: PID },
    })
    expect(mismatch.projectId, '路由项目与事件项目不一致时取路由的').toBe(OTHER)
    const byParam = resolveDialogOpenContext({
      route: { name: TEMPLATE_LIBRARY_ROUTE, params: { projectId: PID }, query: { project_id: OTHER } },
      eventPayload: { project_id: PID },
    })
    expect(byParam.projectId, 'params.projectId 先于 ?project_id（与模板库页 currentProjectId 同序）').toBe(PID)
    const noEventProject = resolveDialogOpenContext({
      route: r(TEMPLATE_LIBRARY_ROUTE, { project_id: OTHER }, null), eventPayload: { source: 'report:balance_sheet' },
    })
    expect(noEventProject.projectId, '报表 / 附注模板按钮不带项目：照旧不预选').toBe('')
    expect(resolveDialogOpenContext({ route: r(TEMPLATE_LIBRARY_ROUTE, { project_id: OTHER }, null) }).projectId,
      '侧栏打开：照旧不预选').toBe('')
  })

  it('事件不带源（如工作台快捷入口）：不按路由预选', () => {
    expect(resolveDialogOpenContext({ route: r('TrialBalance'), eventPayload: { tab: 'basic' } }).initialSource).toBeUndefined()
  })
})
