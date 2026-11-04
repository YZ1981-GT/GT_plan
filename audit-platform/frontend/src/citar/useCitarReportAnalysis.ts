/**
 * 报表分析菜单的标签定义与数据整形（spec citar-report-analysis §3）。
 *
 * 纯函数（对比合并、变动率、权益矩阵取值、空态文案）单测直接覆盖；请求函数统一带 _silent，
 * 错误由面板内中文提示，不再叠全局弹窗。
 */
import { api } from '@/services/apiProxy'
import { reports as P_rpt } from '@/services/apiPaths'
import { projectFormula as P_formula } from '@/services/apiPaths/formula'

export type StatementKind =
  | 'balance_sheet' | 'income_statement' | 'cash_flow_statement'
  | 'equity_statement' | 'cash_flow_supplement' | 'impairment_provision'
export type AnalysisKind = 'cross_check' | 'multi_year' | 'trend' | 'indicators'
export type TabKey = StatementKind | AnalysisKind
export type StatementMode = 'audited' | 'unadjusted' | 'compare'

export interface TabDef { key: TabKey; label: string; group: 'report' | 'analysis'; hidden?: boolean }

/** 旧财务报表页 9 个标签：6 张报表 + 跨表核对 + 多年对比 + 分析（→ 财务指标）；变动分析是新接的 */
export const TABS: TabDef[] = [
  { key: 'balance_sheet', label: '资产负债表', group: 'report' },
  { key: 'income_statement', label: '利润表', group: 'report' },
  // 用户 2026-11-03：报表分析先不显示这四张表（定义保留，去掉 hidden 即恢复）
  { key: 'cash_flow_statement', label: '现金流量表', group: 'report', hidden: true },
  { key: 'equity_statement', label: '权益变动表', group: 'report', hidden: true },
  { key: 'cash_flow_supplement', label: '现金流附表', group: 'report', hidden: true },
  { key: 'impairment_provision', label: '减值准备表', group: 'report', hidden: true },
  { key: 'cross_check', label: '智能核对', group: 'analysis' },
  { key: 'multi_year', label: '多年对比', group: 'analysis' },
  { key: 'trend', label: '变动分析', group: 'analysis' },
  { key: 'indicators', label: '财务指标', group: 'analysis' },
]

/** 页面上显示的标签；?tab= 指向隐藏标签时回到资产负债表 */
export const VISIBLE_TABS: TabDef[] = TABS.filter(t => !t.hidden)

export const STATEMENT_TITLES: Record<StatementKind, string> = {
  balance_sheet: '资产负债表',
  income_statement: '利润表',
  cash_flow_statement: '现金流量表',
  equity_statement: '所有者权益变动表',
  cash_flow_supplement: '现金流量表补充资料',
  impairment_provision: '资产减值准备情况表',
}

/** 时点报表（期末 / 期初）与期间报表（本期 / 上期）的列名不同 */
export function periodLabels(kind: StatementKind): [string, string] {
  if (kind === 'balance_sheet') return ['期末数', '期初数']
  if (kind === 'impairment_provision') return ['期末账面余额', '年初账面余额']
  return ['本期金额', '上期金额']
}

export interface ReportRow {
  row_code: string
  row_name: string
  current_period_amount: string | number | null
  prior_period_amount: string | number | null
  indent_level?: number | null
  is_total_row?: boolean | null
  source_accounts?: unknown
}

export interface CompareRow extends ReportRow {
  unadjusted: number | null
  audited: number | null
  adjustment: number | null
  prior: number | null
  change: number | null
  change_rate: number | null
}

export function toNumber(v: unknown): number | null {
  if (v === null || v === undefined || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? n : null
}

const round2 = (n: number) => Math.round(n * 100) / 100

/** 变动率（%）：上期为空或 0 时没有变动率 */
export function changeRate(current: number | null, prior: number | null): number | null {
  if (current === null || prior === null || prior === 0) return null
  return round2(((current - prior) / Math.abs(prior)) * 100)
}

/** 对比视图：审定行为骨架，按 row_code 合并未审数（与旧 useReportData 同口径） */
export function mergeCompare(audited: ReportRow[], unadjusted: ReportRow[]): CompareRow[] {
  const uMap = new Map(unadjusted.map(r => [r.row_code, r]))
  return audited.map(r => {
    const a = toNumber(r.current_period_amount)
    const u = toNumber(uMap.get(r.row_code)?.current_period_amount)
    const prior = toNumber(r.prior_period_amount)
    const adjustment = a !== null && u !== null ? round2(a - u) : null
    const change = a !== null && prior !== null ? round2(a - prior) : null
    return { ...r, unadjusted: u, audited: a, adjustment, prior, change, change_rate: changeRate(a, prior) }
  })
}

/** 后端未生成时返回模板行次、金额全空 */
export function isGenerated(rows: ReportRow[]): boolean {
  return rows.some(r => r.current_period_amount !== null || r.prior_period_amount !== null)
}

// ─── 权益变动表矩阵 ─────────────────────────────────────────────────────────

/** 列键 = 后端 eq_matrix 键（report_engine 输出），标签照致同模板 */
export const EQUITY_COLUMNS: { key: string; label: string }[] = [
  { key: 'share_capital', label: '实收资本' },
  { key: 'preferred_stock', label: '优先股' },
  { key: 'perpetual_bond', label: '永续债' },
  { key: 'other_equity_instrument', label: '其他权益工具' },
  { key: 'capital_reserve', label: '资本公积' },
  { key: 'treasury_stock', label: '减：库存股' },
  { key: 'other_comprehensive_income', label: '其他综合收益' },
  { key: 'special_reserve', label: '专项储备' },
  { key: 'surplus_reserve', label: '盈余公积' },
  { key: 'general_risk_reserve', label: '一般风险准备' },
  { key: 'retained_earnings', label: '未分配利润' },
  { key: 'total_equity', label: '所有者权益合计' },
]

/**
 * 权益变动表单元格：取行上 source_accounts.eq_matrix.current_year[列]；
 * 没有矩阵的行只有合计列用本行金额，其余列留空（不写 0 冒充有数）。
 */
export function equityCell(row: ReportRow, colKey: string): number | null {
  const sa = row.source_accounts as any
  const block = sa && typeof sa === 'object' && !Array.isArray(sa) ? sa.eq_matrix?.current_year : null
  if (block && typeof block === 'object' && colKey in block) return toNumber(block[colKey])
  if (colKey === 'total_equity') return toNumber(row.current_period_amount)
  return null
}

// ─── 请求 ─────────────────────────────────────────────────────────────────

const SILENT = { _silent: true } as any

export async function fetchStatement(pid: string, year: number, kind: StatementKind, unadjusted: boolean): Promise<ReportRow[]> {
  const data = await api.get(P_rpt.get(pid, year, kind), {
    params: unadjusted ? { unadjusted: true } : {},
    ...SILENT,
  })
  return Array.isArray(data) ? (data as ReportRow[]) : []
}

export interface CrossCheckRow {
  formula_id: string
  description: string
  passed: boolean
  /** 参与比较的数（内置勾稽来自 inputs；用户规则来自 Issue 左右值） */
  values: { key: string; label: string; amount: number | null }[]
}

/** 内置勾稽取数键 → 中文名（键见后端 logic_check._CROSS_CHECK_SEEDS） */
const CROSS_CHECK_REF_LABELS: Record<string, string> = {
  assets_total: '资产总计',
  liabilities_total: '负债合计',
  equity_total: '所有者权益合计',
  'BS-001': '货币资金',
  'IS-001': '营业收入',
  'IS-002': '营业成本',
  'IS-003': '毛利',
  'IS-017': '利润总额',
  'IS-018': '所得税费用',
  'IS-019': '净利润',
  'EQ-ENDING': '权益变动表本年年末余额',
}

export async function fetchCrossCheck(pid: string, year: number): Promise<{ rows: CrossCheckRow[]; noResult: boolean }> {
  const data: any = await api.get(P_formula.reportCrossCheck(pid), { params: { year }, ...SILENT })
  return { rows: mapCrossCheck(data), noResult: Boolean(data?.no_result) }
}

export function mapCrossCheck(data: any): CrossCheckRow[] {
  const issues = new Map<string, any>()
  for (const i of data?.issue_list ?? []) if (i?.formula_id && !issues.has(i.formula_id)) issues.set(i.formula_id, i)
  const inputs: Record<string, unknown> = data?.inputs ?? {}
  return (data?.results ?? []).map((r: any) => {
    const refs: string[] = Array.isArray(r.refs) ? r.refs : []
    let values = refs.map(key => ({
      key,
      label: CROSS_CHECK_REF_LABELS[key] ?? key,
      amount: toNumber(inputs[key]),
    }))
    if (!values.length) {
      const issue = issues.get(r.formula_id)
      if (issue) {
        values = [
          { key: 'left', label: '左侧', amount: toNumber(issue.left_value) },
          { key: 'right', label: '右侧', amount: toNumber(issue.right_value) },
        ]
      }
    }
    return { formula_id: r.formula_id, description: r.description, passed: Boolean(r.passed), values }
  })
}

export const silent = SILENT

/** 后端错误 → 中文提示（detail 字符串优先） */
export function errorText(e: any, fallback: string): string {
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string' && detail) return detail
  if (detail?.message) return String(detail.message)
  if (e?.response?.status === 404) return '报表格式未配置，无法显示'
  if (e?.response?.status === 403) return '没有本项目的查看权限'
  return fallback
}
