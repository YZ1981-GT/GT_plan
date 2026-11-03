/**
 * useReportRouteFocus.spec.ts — 报表页深链 `?tab=&highlight=`（advanced-query-linkage-closure 任务 32；R7.1 报表行）
 *
 * 普通模式在普通表上定位、对比模式在对比表上定位（变异 B11-d：对比模式也用普通表 ⇒ 对比例红）、矩阵报表只提示、
 * 找不到行次给提示；同一路由只定位一次；`?tab` 只认报表页签名；`?year` 判定与报表页原内联写法相同。
 */
import { describe, it, expect, vi } from 'vitest'
import { nextTick, ref } from 'vue'
import {
  MATRIX_REPORT_NOTICE, rowNotFoundNotice, useReportRouteFocus, type ReportFocusTarget,
} from '../useReportRouteFocus'

function fakeRoute(query: Record<string, string>) {
  const search = new URLSearchParams(query).toString()
  return { query, fullPath: `/projects/p1/reports${search ? `?${search}` : ''}` } as any
}

/** 假表格：setCurrentRow 记下行，$el 里放与数据同数的 tr（有 scrollIntoView / classList） */
function fakeTable(rowCount: number) {
  const trs = Array.from({ length: rowCount }, () => ({
    scrollIntoView: vi.fn(),
    classList: { add: vi.fn(), remove: vi.fn() },
  }))
  return {
    setCurrentRow: vi.fn(),
    $el: { querySelectorAll: vi.fn(() => trs) },
    trs,
  }
}

const ROWS = [{ row_code: 'BS-001' }, { row_code: 'BS-002' }, { row_code: 'BS-003' }]

function setup(query: Record<string, string>, opts: { mode?: string; tab?: string } = {}) {
  const notify = { info: vi.fn(), warning: vi.fn() }
  const focus = useReportRouteFocus(fakeRoute(query), notify)
  const rv = fakeTable(ROWS.length)
  const cmp = fakeTable(ROWS.length)
  const target = {
    activeTab: ref(opts.tab ?? focus.initialTab),
    reportMode: ref(opts.mode ?? 'audited'),
    rows: ref<{ row_code: string }[]>([]),
    compareRows: ref<{ row_code: string }[]>([]),
    rvTableRef: ref(rv),
    compareTableRef: ref(cmp),
    loading: ref(false),
  }
  focus.attach(target as unknown as ReportFocusTarget)
  return { focus, notify, rv, cmp, target }
}

async function settle() {
  await nextTick()
  await nextTick()
  await nextTick()
}

describe('useReportRouteFocus — ?tab 与 ?year', () => {
  it('?tab 是报表页签名时作初始页签，其余为资产负债表；?year 只认 2001 起的数字', () => {
    expect(useReportRouteFocus(fakeRoute({ tab: 'income_statement' })).initialTab).toBe('income_statement')
    expect(useReportRouteFocus(fakeRoute({ tab: 'cross_check' })).initialTab).toBe('cross_check')
    expect(useReportRouteFocus(fakeRoute({ tab: 'nope' })).initialTab).toBe('balance_sheet')
    expect(useReportRouteFocus(fakeRoute({})).initialTab).toBe('balance_sheet')
    expect(useReportRouteFocus(fakeRoute({ year: '2025' })).routeYear.value).toBe(2025)
    expect(useReportRouteFocus(fakeRoute({ year: '1999' })).routeYear.value).toBeNull()
    expect(useReportRouteFocus(fakeRoute({ year: 'abc' })).routeYear.value).toBeNull()
  })
})

describe('useReportRouteFocus — ?highlight 定位行次', () => {
  it('普通模式：行加载完后在普通表上选中该行并滚动居中、闪烁标出', async () => {
    const { rv, cmp, notify, target } = setup({ tab: 'balance_sheet', highlight: 'BS-002' })
    target.loading.value = true
    target.rows.value = ROWS
    await settle()
    expect(rv.setCurrentRow, '加载中不定位').not.toHaveBeenCalled()
    target.loading.value = false
    await settle()
    expect(rv.setCurrentRow).toHaveBeenCalledWith(ROWS[1])
    expect(rv.trs[1].scrollIntoView).toHaveBeenCalledWith({ behavior: 'smooth', block: 'center' })
    expect(rv.trs[1].classList.add).toHaveBeenCalledWith('gt-highlight-row')
    expect(cmp.setCurrentRow).not.toHaveBeenCalled()
    expect(notify.warning).not.toHaveBeenCalled()
  })

  it('对比模式：在对比表上定位（不是普通表）', async () => {
    const { rv, cmp, target } = setup({ tab: 'income_statement', highlight: 'BS-003' }, { mode: 'compare' })
    target.compareRows.value = ROWS
    await settle()
    expect(cmp.setCurrentRow).toHaveBeenCalledWith(ROWS[2])
    expect(cmp.trs[2].scrollIntoView).toHaveBeenCalled()
    expect(rv.setCurrentRow).not.toHaveBeenCalled()
  })

  it('矩阵报表（权益变动表 / 减值准备表）：只提示已打开对应报表，不找行', async () => {
    for (const tab of ['equity_statement', 'impairment_provision']) {
      const { rv, notify } = setup({ tab, highlight: 'EQ-001' })
      await settle()
      expect(notify.info).toHaveBeenCalledWith(MATRIX_REPORT_NOTICE)
      expect(MATRIX_REPORT_NOTICE).toBe('该报表为矩阵格式，已打开对应报表')
      expect(rv.setCurrentRow).not.toHaveBeenCalled()
    }
  })

  it('找不到该行次：提示「未找到行次 {code}」', async () => {
    const { rv, notify, target } = setup({ highlight: 'BS-999' })
    target.rows.value = ROWS
    await settle()
    expect(notify.warning).toHaveBeenCalledWith(rowNotFoundNotice('BS-999'))
    expect(rowNotFoundNotice('BS-999')).toBe('未找到行次 BS-999')
    expect(rv.setCurrentRow).not.toHaveBeenCalled()
  })

  it('同一路由同一模式只定位一次：之后重新取数不再跳回该行；没有 ?highlight 不动', async () => {
    const { rv, target } = setup({ highlight: 'BS-001' })
    target.rows.value = ROWS
    await settle()
    expect(rv.setCurrentRow).toHaveBeenCalledTimes(1)
    target.loading.value = true
    target.rows.value = [...ROWS]
    await settle()
    target.loading.value = false
    await settle()
    expect(rv.setCurrentRow).toHaveBeenCalledTimes(1)
    const plain = setup({})
    plain.target.rows.value = ROWS
    await settle()
    expect(plain.rv.setCurrentRow).not.toHaveBeenCalled()
    expect(plain.notify.warning).not.toHaveBeenCalled()
  })

  it('深链落地后切到「对比」：在对比表上标出同一行次；再切回「已审」不再跳回', async () => {
    const { rv, cmp, target } = setup({ tab: 'balance_sheet', highlight: 'BS-002' })
    target.rows.value = ROWS
    await settle()
    expect(rv.setCurrentRow).toHaveBeenCalledTimes(1)
    target.reportMode.value = 'compare'
    target.compareRows.value = ROWS
    await settle()
    expect(cmp.setCurrentRow).toHaveBeenCalledWith(ROWS[1])
    target.reportMode.value = 'audited'
    target.compareRows.value = []
    await settle()
    expect(rv.setCurrentRow).toHaveBeenCalledTimes(1)
    expect(cmp.setCurrentRow).toHaveBeenCalledTimes(1)
  })

  it('用户切到别的报表页签：不在那张报表里找该行次、不报「未找到」', async () => {
    const { rv, notify, target } = setup({ tab: 'balance_sheet', highlight: 'BS-002' })
    target.activeTab.value = 'income_statement'
    target.rows.value = [{ row_code: 'IS-001' }, { row_code: 'IS-002' }]
    await settle()
    expect(rv.setCurrentRow).not.toHaveBeenCalled()
    expect(notify.warning).not.toHaveBeenCalled()
    target.activeTab.value = 'balance_sheet'
    target.rows.value = ROWS
    await settle()
    expect(rv.setCurrentRow).toHaveBeenCalledWith(ROWS[1])
  })
})
