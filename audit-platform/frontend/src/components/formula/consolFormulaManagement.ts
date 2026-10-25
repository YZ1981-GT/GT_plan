import type { ConsolNoteTemplateType } from '@/services/consolidationApi'

/** 公式中心六类合并报表节点 → report_config.report_type（不能靠缩写切字符串）。 */
export const CONSOL_REPORT_NODE_TYPES = {
  consol_report_bs: 'balance_sheet',
  consol_report_is: 'income_statement',
  consol_report_cfs: 'cash_flow_statement',
  consol_report_eq: 'equity_statement',
  consol_report_cfss: 'cash_flow_supplement',
  consol_report_imp: 'impairment_provision',
} as const

export type ConsolReportFormulaNode = keyof typeof CONSOL_REPORT_NODE_TYPES

export const CONSOL_REPORT_TREE_ITEMS: ReadonlyArray<{ key: ConsolReportFormulaNode; label: string }> = [
  { key: 'consol_report_bs', label: '合并资产负债表' },
  { key: 'consol_report_is', label: '合并利润表' },
  { key: 'consol_report_cfs', label: '合并现金流量表' },
  { key: 'consol_report_eq', label: '合并所有者权益变动表' },
  { key: 'consol_report_cfss', label: '合并现金流附表' },
  { key: 'consol_report_imp', label: '合并资产减值准备表' },
]

export function consolReportTypeOfNode(nodeKey: string): string {
  return CONSOL_REPORT_NODE_TYPES[nodeKey as ConsolReportFormulaNode] || ''
}

export function consolReportNodeOfType(reportType: string | null | undefined): ConsolReportFormulaNode {
  const found = (Object.entries(CONSOL_REPORT_NODE_TYPES) as Array<[ConsolReportFormulaNode, string]>)
    .find(([, value]) => value === reportType)
  return found?.[0] || 'consol_report_bs'
}

export function consolidatedStandard(templateType: string | null | undefined): `${ConsolNoteTemplateType}_consolidated` {
  return `${templateType === 'listed' ? 'listed' : 'soe'}_consolidated`
}
