/**
 * useReportRouteFocus.ts — 报表页深链：`?tab=` 选报表页签、`?highlight=` 定位行次（advanced-query-linkage-closure 任务 32；
 * R7.1 报表行，ADR-AQL-01，design §4.1）
 *
 * 高级查询结果行「打开」、地址库 `build_jump_route`、`useResolveLinkageRoute` 生成的都是
 * `/projects/{项目}/reports?year=&tab=<报表类型>&highlight=<行次>`，而报表页原先只读 `?year`：页签停在资产负债表、不定位行。
 *
 * 两段接线（报表页的年度要先于取数器给出，表格 ref 与行在取数器之后才有）：
 * - `useReportRouteFocus(route)` 在取数器之前调用，给出 `routeYear`（原 ReportView 内联的同一判定）与 `initialTab`
 *   （`?tab` 是报表页签名时作初始页签，否则资产负债表）；
 * - `attach({...})` 在表格 ref 声明之后调用：首次加载完行后读 `?highlight`——矩阵报表（权益变动表、减值准备表）只提示
 *   「该报表为矩阵格式，已打开对应报表」；对比模式在对比表、其余在普通表上按行次 `setCurrentRow`，滚动居中并闪烁标出该行；
 *   找不到提示「未找到行次 {code}」。
 * - 执行次数：同一路由（fullPath）下每种报表模式（已审 / 未审 / 对比）各一次，且只在深链指向的页签上。报表页按 fullPath
 *   重新挂载、报表模式不随路由，深链落地时恒为「已审」；对比表只有用户切到「对比」才出现，切过去时在对比表上标出同一行次。
 *   之后重新取数、来回切回已定位过的模式都不再跳回；切到别的页签不找（免得在别的报表里报「未找到行次」）。
 */
import { computed, nextTick, watch } from 'vue'
import type { RouteLocationNormalizedLoaded } from 'vue-router'
import { ElMessage } from 'element-plus'

/** 报表页的页签名（六张报表 + 跨表核对 / 多年对比 / 分析） */
export const REPORT_VIEW_TABS: ReadonlySet<string> = new Set([
  'balance_sheet', 'income_statement', 'cash_flow_statement', 'equity_statement', 'cash_flow_supplement',
  'impairment_provision', 'cross_check', 'multi_year_compare', 'report_analysis',
])
/** 矩阵格式的报表：没有逐行的行次表格，只打开对应报表 */
export const MATRIX_REPORT_TABS: ReadonlySet<string> = new Set(['equity_statement', 'impairment_provision'])
export const MATRIX_REPORT_NOTICE = '该报表为矩阵格式，已打开对应报表'
export const rowNotFoundNotice = (code: string) => `未找到行次 ${code}`

interface FocusTable {
  setCurrentRow?: (row?: unknown) => void
  $el?: Element | null
}
type ReportRow = { row_code?: string | null }
/** 只读的 ref（报表页传进来的是可写 ref，这里只读其值） */
type ReadRef<T> = { readonly value: T }

export interface ReportFocusTarget {
  activeTab: ReadRef<string>
  reportMode: ReadRef<string>
  rows: ReadRef<readonly ReportRow[]>
  compareRows: ReadRef<readonly ReportRow[]>
  rvTableRef: ReadRef<FocusTable | null>
  compareTableRef: ReadRef<FocusTable | null>
  loading: ReadRef<boolean>
}
export interface FocusNotify {
  info: (message: string) => void
  warning: (message: string) => void
}

function first(v: unknown): string {
  const x = Array.isArray(v) ? v[0] : v
  return x === undefined || x === null ? '' : String(x).trim()
}

export function useReportRouteFocus(route: RouteLocationNormalizedLoaded, notify: FocusNotify = ElMessage) {
  const routeYear = computed(() => {
    const value = Number(route.query.year)
    return Number.isFinite(value) && value > 2000 ? value : null
  })
  const tab = first(route.query.tab)
  const initialTab = REPORT_VIEW_TABS.has(tab) ? tab : 'balance_sheet'
  /** 已执行过的（路由, 模式）；矩阵报表按（路由, 矩阵）只提示一次 */
  const done = new Set<string>()

  async function focus(t: ReportFocusTarget): Promise<void> {
    const code = first(route.query.highlight)
    // 只在深链指向的页签上找（用户切到别的报表时不报「未找到」）；加载中等结果
    if (!code || t.loading.value || t.activeTab.value !== initialTab) return
    const matrix = MATRIX_REPORT_TABS.has(t.activeTab.value)
    const key = `${route.fullPath}|${matrix ? 'matrix' : t.reportMode.value}`
    if (done.has(key)) return
    if (matrix) {
      done.add(key)
      notify.info(MATRIX_REPORT_NOTICE)
      return
    }
    const compare = t.reportMode.value === 'compare'
    const rows = compare ? t.compareRows.value : t.rows.value
    if (!rows.length) return // 行还没加载：等下一次
    done.add(key)
    const index = rows.findIndex((r) => String(r?.row_code ?? '') === code)
    if (index < 0) {
      notify.warning(rowNotFoundNotice(code))
      return
    }
    await nextTick() // 等表格把这批行渲染出来
    const table = (compare ? t.compareTableRef : t.rvTableRef).value
    table?.setCurrentRow?.(rows[index])
    const tr = table?.$el?.querySelectorAll?.('.el-table__body-wrapper tbody tr.el-table__row')?.[index] as HTMLElement | undefined
    tr?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
    tr?.classList?.add('gt-highlight-row')
    if (tr) setTimeout(() => tr.classList.remove('gt-highlight-row'), 3000)
  }

  /** 接上定位（表格 ref 与行声明之后调用）；行到达、模式 / 页签变化、路由变化时尝试一次 */
  function attach(t: ReportFocusTarget): void {
    watch(
      () => [t.loading.value, t.rows.value.length, t.compareRows.value.length, t.activeTab.value, t.reportMode.value,
        route.fullPath] as const,
      () => { void focus(t) },
      { immediate: true },
    )
  }

  return { routeYear, initialTab, attach }
}
