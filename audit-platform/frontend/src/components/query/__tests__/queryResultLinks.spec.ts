/**
 * queryResultLinks.spec.ts — 结果行下钻与公式引用（advanced-query-linkage-closure 任务 27；ADR-AQL-01 / 18，R7.1~R7.3）
 *
 * - ADR-AQL-01 表每一行一条用例（业务视图数据源 + 构建器白名单表），深链键与目标页现有读取契约一致；
 * - 底稿单元格经 wp-id-by-code 取实例后带 `?sheet=&cell=`（不是 `?highlight=`，变异 #15）；
 * - 四种引用语法；批量校验按返回问题的 `ref` 回填（与顺序无关，变异 B9-a）、WP 未登记文案、请求失败全部不可用。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const apiMocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ default: apiMocks, api: apiMocks }))

import {
  REF_BATCH_SIZE,
  REF_CHECK_UNAVAILABLE,
  TB_REF_COLUMNS,
  WP_REF_NOT_REGISTERED,
  buildFormulaRef,
  buildRowDrill,
  openRowDrill,
  resolveRowDrill,
  validatePageRefs,
  type DrillContext,
} from '../queryResultLinks'

const PID = '005a6f2d-cecd-4e30-bcbd-9fb01236c194'
const WP_ID = 'e982a010-1ce7-4d29-a097-9e4398bb23a5'
const src = (key: string, extra: Partial<DrillContext> = {}): DrillContext => ({ kind: 'source', key, projectId: PID, year: 2025, ...extra })
const tbl = (key: string, extra: Partial<DrillContext> = {}): DrillContext => ({ kind: 'table', key, projectId: PID, year: 2025, ...extra })
const loc = (drill: ReturnType<typeof buildRowDrill>) => (drill && 'location' in drill ? drill.location : null)

beforeEach(() => {
  apiMocks.get.mockReset()
  apiMocks.post.mockReset()
})

describe('buildRowDrill — ADR-AQL-01 每类结果的目标页与深链', () => {
  it('科目余额（含合并单位）→ 账簿查询 ?year=&level=ledger&account=', () => {
    const expected = { name: 'LedgerPenetration', params: { projectId: PID }, query: { year: '2025', level: 'ledger', account: '1002' } }
    expect(loc(buildRowDrill(src('account_balance'), { account_code: '1002' }))).toEqual(expected)
    expect(loc(buildRowDrill(src('consol_unit:C01:account_balance'), { account_code: '1002' }))).toEqual(expected)
  })

  it('序时账 → 账簿查询凭证层级 ?level=voucher&account=&voucher=&voucherDate=', () => {
    const row = { account_code: '1002', voucher_no: '记-0223', voucher_date: '2025-03-31T00:00:00' }
    expect(loc(buildRowDrill(src('ledger_entries'), row))?.query).toEqual({
      year: '2025', level: 'voucher', account: '1002', voucher: '记-0223', voucherDate: '2025-03-31',
    })
  })

  it('辅助余额 / 辅助明细 → 账簿查询 ?level=aux_ledger&account=&auxType=&auxCode=', () => {
    const row = { account_code: '1122', aux_type: '客户', aux_code: 'C001' }
    for (const key of ['aux_balance', 'aux_ledger']) {
      expect(loc(buildRowDrill(src(key), row))?.query).toEqual({
        year: '2025', level: 'aux_ledger', account: '1122', auxType: '客户', auxCode: 'C001',
      })
    }
  })

  it('试算表 → 账簿查询 ?year=&account=<标准科目码>（与试算表页穿透同口径，不带 level）', () => {
    expect(loc(buildRowDrill(src('tb_detail'), { standard_account_code: '1001', account_name: '库存现金' }))).toEqual({
      name: 'LedgerPenetration', params: { projectId: PID }, query: { year: '2025', account: '1001' },
    })
  })

  it('报表行 → 报表页 ?year=&tab=<报表类型>&highlight=<行次>（矩阵报表同一深链，由报表页提示）', () => {
    expect(loc(buildRowDrill(src('report_balance_sheet'), { row_code: 'BS-002' }))).toEqual({
      name: 'Reports', params: { projectId: PID }, query: { year: '2025', tab: 'balance_sheet', highlight: 'BS-002' },
    })
    expect(loc(buildRowDrill(src('report_equity_statement'), { row_code: 'EQ-001' }))?.query?.tab).toBe('equity_statement')
  })

  it('附注表格行 → 附注编辑器 ?year=&section=&table_index=（当前显示的表）；附注目录按行的章节与表序号', () => {
    expect(loc(buildRowDrill(src('disclosure_note:八、1', { tableIndex: 1 }), { 项目: '库存现金' }))).toEqual({
      name: 'DisclosureNotes', params: { projectId: PID }, query: { year: '2025', section: '八、1', table_index: '1' },
    })
    expect(loc(buildRowDrill(src('disclosure_note:八、1'), {}))?.query?.table_index).toBe('0')
    expect(loc(buildRowDrill(src('disclosure'), { note_section: '八、3', table_index: 0 }))?.query)
      .toEqual({ year: '2025', section: '八、3', table_index: '0' })
    expect(loc(buildRowDrill(src('disclosure'), { note_section: '八、3' }))?.query).toEqual({ year: '2025', section: '八、3' })
  })

  it('调整分录（各类型键与旧键 adj_rcl）→ 调整分录页 ?year=&group=<分录组>', () => {
    for (const key of ['adj_aje', 'adj_rje', 'adj_rcl', 'adjustment', 'consol_unit:C01:adjustment']) {
      expect(loc(buildRowDrill(src(key), { entry_group_id: 'g-1', adjustment_no: 'AJE-001' }))).toEqual({
        name: 'Adjustments', params: { projectId: PID }, query: { year: '2025', focus: 'g-1' },
      })
    }
  })

  it('底稿清单：隐藏列 id 即底稿实例，直接打开编辑器；没有 id 时按编码解析', () => {
    expect(loc(buildRowDrill(src('workpaper'), { id: WP_ID, wp_code: 'C1-1' }))).toEqual({
      name: 'WorkpaperEditor', params: { projectId: PID, wpId: WP_ID },
    })
    expect(buildRowDrill(src('workpaper'), { wp_code: 'C1-1' })).toMatchObject({ workpaper: { projectId: PID, wpCode: 'C1-1' } })
  })

  it('底稿单元格 → wp-id-by-code 取实例后打开编辑器并带 ?sheet=&cell=（不是 ?highlight=）', async () => {
    apiMocks.get.mockResolvedValue({ wp_id: WP_ID })
    const drill = buildRowDrill(src('workpaper:D2|审定表D2-1|A1:C5'), { wp_code: 'D2', sheet_name: '审定表D2-1', cell_ref: 'B5' })
    expect(drill).not.toBeNull()
    const resolved = await resolveRowDrill(drill!)
    expect(apiMocks.get).toHaveBeenCalledWith('/api/custom-query/wp-id-by-code',
      expect.objectContaining({ params: { project_id: PID, wp_code: 'D2' } }))
    expect(resolved).toEqual({ ok: true, location: {
      name: 'WorkpaperEditor', params: { projectId: PID, wpId: WP_ID }, query: { sheet: '审定表D2-1', cell: 'B5' },
    } })
  })

  it('报表行次配置 / 工时 / 合并工作底稿 / 合并试算不下钻', () => {
    for (const key of ['report_lines', 'workhours', 'tb_summary', 'worksheet', 'ws_consol_tb']) {
      expect(buildRowDrill(src(key), { row_code: 'BS-002', account_code: '1001', standard_account_code: '1001' })).toBeNull()
    }
  })

  it('没有项目上下文（跨项目结果）或缺定位键时不下钻', () => {
    expect(buildRowDrill(src('tb_detail', { projectId: '' }), { standard_account_code: '1001' })).toBeNull()
    expect(buildRowDrill(src('tb_detail', { projectId: null }), { standard_account_code: '1001' })).toBeNull()
    expect(buildRowDrill(src('tb_detail'), { account_name: '库存现金' })).toBeNull()
    expect(buildRowDrill(src('adj_aje'), { adjustment_no: 'AJE-001' })).toBeNull()
    expect(buildRowDrill(src('report_balance_sheet'), { row_name: '货币资金' })).toBeNull()
  })

  it('构建器白名单表映射到同一目标页；行自带年度时优先用行的年度', () => {
    expect(loc(buildRowDrill(tbl('trial_balance', { year: null }), { standard_account_code: '1001', year: 2024 }))?.query)
      .toEqual({ year: '2024', account: '1001' })
    expect(loc(buildRowDrill(tbl('tb_balance'), { account_code: '1002' }))?.query).toEqual({ year: '2025', level: 'ledger', account: '1002' })
    expect(loc(buildRowDrill(tbl('tb_ledger'), { account_code: '1002', voucher_no: '记-1', voucher_date: '2025-01-02' }))?.query?.level).toBe('voucher')
    expect(loc(buildRowDrill(tbl('tb_aux_ledger'), { account_code: '1122', aux_type: '客户', aux_code: 'C1' }))?.query?.level).toBe('aux_ledger')
    expect(loc(buildRowDrill(tbl('adjustments'), { entry_group_id: 'g-2' }))?.name).toBe('Adjustments')
    expect(loc(buildRowDrill(tbl('disclosure_notes'), { note_section: '八、1' }))?.query).toEqual({ year: '2025', section: '八、1' })
    expect(loc(buildRowDrill(tbl('financial_report'), { report_type: 'income_statement', row_code: 'IS-001' }))?.query)
      .toEqual({ year: '2025', tab: 'income_statement', highlight: 'IS-001' })
    expect(loc(buildRowDrill(tbl('working_paper'), { id: WP_ID }))?.params).toEqual({ projectId: PID, wpId: WP_ID })
    expect(buildRowDrill(tbl('wp_index'), { wp_code: 'E1' })).toMatchObject({ workpaper: { wpCode: 'E1' } })
    for (const key of ['projects', 'staff_members', 'work_hours', 'account_chart', 'report_config']) {
      expect(buildRowDrill(tbl(key), { id: WP_ID, account_code: '1001', row_code: 'BS-002' })).toBeNull()
    }
  })
})

describe('openRowDrill — 新标签打开（不加 noopener，保留登录态）', () => {
  let openSpy: any
  const router = { resolve: vi.fn((to: any) => ({ href: `/projects/${to.params.projectId}/x?${new URLSearchParams(to.query ?? {})}` })) }
  beforeEach(() => {
    openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    router.resolve.mockClear()
  })
  afterEach(() => { openSpy.mockRestore() })

  it('目标已知：按 router.resolve 的 href 打开，只传 _blank', async () => {
    const reason = await openRowDrill(buildRowDrill(src('tb_detail'), { standard_account_code: '1001' })!, router)
    expect(reason).toBeNull()
    expect(openSpy).toHaveBeenCalledTimes(1)
    expect(openSpy.mock.calls[0]).toEqual([`/projects/${PID}/x?year=2025&account=1001`, '_blank'])
  })

  it('底稿编码取不到实例：不打开，返回中文原因', async () => {
    apiMocks.get.mockRejectedValue(Object.assign(new Error('Request failed with status code 404'), { response: { status: 404 } }))
    const reason = await openRowDrill(buildRowDrill(src('workpaper:D2|审定表D2-1|A1:C5'), { wp_code: 'D2', sheet_name: 's', cell_ref: 'A1' })!, router)
    expect(reason).toBe('底稿 D2 在当前项目不存在')
    expect(openSpy).not.toHaveBeenCalled()
  })
})

describe('buildFormulaRef — 四种引用语法（ADR-AQL-18）', () => {
  it('试算表：TB(标准码, 列名)，列名取地址库词表，缺省审定数', () => {
    const row = { standard_account_code: '1001' }
    expect(buildFormulaRef('tb_detail', row)).toBe("TB('1001','审定数')")
    expect(buildFormulaRef('trial_balance', row, 'rje_adjustment')).toBe("TB('1001','RJE调整')")
    expect(Object.values(TB_REF_COLUMNS)).toEqual(['审定数', '未审数', 'AJE调整', 'RJE调整', '期初余额'])
    expect(buildFormulaRef('tb_detail', row, 'account_name')).toBeNull()
  })

  it('报表：ROW(行次)；上期金额列没有 ROW 写法', () => {
    expect(buildFormulaRef('report_balance_sheet', { row_code: 'BS-002' })).toBe("ROW('BS-002')")
    expect(buildFormulaRef('report_balance_sheet', { row_code: 'BS-002' }, 'current_period_amount')).toBe("ROW('BS-002')")
    expect(buildFormulaRef('report_balance_sheet', { row_code: 'BS-002' }, 'prior_period_amount')).toBeNull()
    expect(buildFormulaRef('report_lines', { row_code: 'BS-002' })).toBeNull()
  })

  it('附注：NOTE(章节, 行标签, 列表头)；缺行标签列或取值列不生成', () => {
    const row = { 项目: '库存现金', 期末余额: '100.00' }
    expect(buildFormulaRef('disclosure_note:八、1', row, '期末余额', { labelKey: '项目' })).toBe("NOTE('八、1','库存现金','期末余额')")
    expect(buildFormulaRef('disclosure_note:八、1', row, '期末余额')).toBeNull()
    expect(buildFormulaRef('disclosure_note:八、1', row, null, { labelKey: '项目' })).toBeNull()
  })

  it("底稿单元格：WP(编码, sheet, 单元格)；值含单引号不生成（语法没有转义）", () => {
    const row = { wp_code: 'D2', sheet_name: '审定表D2-1', cell_ref: 'E10' }
    expect(buildFormulaRef('workpaper:D2|审定表D2-1|A1:F20', row)).toBe("WP('D2','审定表D2-1','E10')")
    expect(buildFormulaRef('workpaper:D2|审定表D2-1|A1:F20', { ...row, sheet_name: "D2'1" })).toBeNull()
    expect(buildFormulaRef('ledger_entries', { account_code: '1001' })).toBeNull()
  })
})

describe('validatePageRefs — 批量校验与回填', () => {
  const CTX = { projectId: PID, year: 2025, templateType: 'soe' }

  it('按返回问题的 ref 回填（与顺序无关）：只有出问题的那条不可用', async () => {
    const refs = ["TB('1001','审定数')", "TB('1002','审定数')", "TB('9999','审定数')"]
    apiMocks.post.mockResolvedValue({ valid: false, issues: [
      { ref: "TB('9999','审定数')", status: 'not_found', message: '试算表没有科目 9999' },
    ] })
    const out = await validatePageRefs(refs, CTX)
    expect(apiMocks.post).toHaveBeenCalledTimes(1)
    expect(apiMocks.post.mock.calls[0][0]).toBe('/api/address-registry/validate')
    expect(apiMocks.post.mock.calls[0][1]).toEqual({ formula: refs.join('+'), project_id: PID, year: 2025, template_type: 'soe' })
    expect(apiMocks.post.mock.calls[0][2]).toMatchObject({ _silent: true })
    expect(out.get(refs[0])).toEqual({ ok: true })
    expect(out.get(refs[1])).toEqual({ ok: true })
    expect(out.get(refs[2])).toEqual({ ok: false, reason: '试算表没有科目 9999' })
  })

  it('每批不超过 200 个，去重后分批', async () => {
    const refs = Array.from({ length: 450 }, (_, i) => `TB('${1000 + i}','审定数')`)
    apiMocks.post.mockResolvedValue({ valid: true, issues: [] })
    const out = await validatePageRefs([...refs, refs[0], null, undefined, ''], CTX)
    expect(REF_BATCH_SIZE).toBe(200)
    expect(apiMocks.post.mock.calls.map((c) => String(c[1].formula).split('+').length)).toEqual([200, 200, 50])
    expect(out.size).toBe(450)
  })

  it('底稿单元格未登记显示「该单元格未登记为可引用地址」', async () => {
    const ref = "WP('D2','审定表D2-1','Z99')"
    apiMocks.post.mockResolvedValue({ valid: false, issues: [{ ref, status: 'not_found', message: '引用地址 wp://… 在当前项目中不存在' }] })
    expect((await validatePageRefs([ref], CTX)).get(ref)).toEqual({ ok: false, reason: WP_REF_NOT_REGISTERED })
  })

  it('校验请求失败：本页全部不可用并提示「引用校验暂不可用」', async () => {
    apiMocks.post.mockResolvedValueOnce({ issues: [] }).mockRejectedValueOnce(new Error('Network Error'))
    const refs = Array.from({ length: 250 }, (_, i) => `ROW('BS-${i}')`)
    const out = await validatePageRefs(refs, CTX)
    expect([...out.values()].every((v) => !v.ok && v.reason === REF_CHECK_UNAVAILABLE)).toBe(true)
    expect(out.size).toBe(250)
  })

  it('缺项目或年度：不发请求，全部不可用', async () => {
    const out = await validatePageRefs(["TB('1001','审定数')"], { projectId: PID, year: null })
    expect(apiMocks.post).not.toHaveBeenCalled()
    expect(out.get("TB('1001','审定数')")?.ok).toBe(false)
  })
})
