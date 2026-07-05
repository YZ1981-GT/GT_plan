/**
 * D1 应收票据 — 共享常量（从 useD1NotesReceivable 拆出）
 */
export type TabStatus = 'completed' | 'in-progress' | 'not-started'

export const TAB_NAMES = [
  'directory', 'procedure', 'adjudication', 'disclosure',
  'detail-category', 'detail-customer', 'bad-debt', 'adjustment',
  'business-model', 'ledger-reconciliation', 'endorsement', 'interest',
  'inventory', 'related-party', 'pledge', 'general-check',
  'ecl-policy', 'ecl-test', 'writeoff',
] as const

export const PROCEDURE_STEPS_CONFIG: Array<{
  stepName: string
  description: string
  isRequired: boolean
  relatedTab: string | null
}> = [
  { stepName: '获取明细', description: '获取应收票据明细表，检查与总账/明细账一致性', isRequired: true, relatedTab: 'detail-category' },
  { stepName: '核对总账', description: '核对应收票据总账余额与明细账合计数', isRequired: true, relatedTab: 'adjudication' },
  { stepName: '备查簿核对', description: '核对备查簿与账面记录，关注已贴现/已背书票据', isRequired: true, relatedTab: 'memo' },
  { stepName: '票据验真', description: '对重要票据执行真伪验证程序', isRequired: true, relatedTab: 'general-check' },
  { stepName: '到期分析', description: '按到期日分组分析票据，关注逾期情况', isRequired: true, relatedTab: 'business-model' },
  { stepName: '背书贴现', description: '检查已背书/已贴现票据的终止确认处理', isRequired: true, relatedTab: 'endorsement' },
  { stepName: '减值评估', description: '评估应收票据预期信用损失计提充分性', isRequired: true, relatedTab: 'bad-debt' },
  { stepName: '监盘核查', description: '对重要应收票据实施监盘或替代程序', isRequired: true, relatedTab: 'inventory' },
  { stepName: 'ECL政策', description: '检查坏账准备会计政策与ECL模型一致性', isRequired: true, relatedTab: 'ecl-policy' },
  { stepName: 'ECL测试', description: '执行预期信用损失测算并分析差异', isRequired: true, relatedTab: 'ecl-test' },
  { stepName: '质押检查', description: '检查已质押票据的披露与列报', isRequired: false, relatedTab: 'pledge' },
  { stepName: '披露检查', description: '检查应收票据相关附注披露完整性和准确性', isRequired: true, relatedTab: 'disclosure' },
  { stepName: '结论', description: '汇总应收票据审计发现，形成整体结论', isRequired: false, relatedTab: null },
]

/** @deprecated 已迁移至 useD1Adjudication.ts，保留供测试向后兼容 */
export const ADJUDICATION_ROWS_CONFIG: Array<{ rowKey: string; label: string }> = [
  { rowKey: 'bank-acceptance', label: '应收票据-银行承兑汇票' },
  { rowKey: 'commercial-acceptance', label: '应收票据-商业承兑汇票' },
  { rowKey: 'bad-debt', label: '坏账准备' },
  { rowKey: 'book-value', label: '账面价值' },
]

/** @deprecated 已迁移至 useD1BadDebt.ts，保留供测试向后兼容 */
export const AGING_BANDS_CONFIG: Array<{ bandKey: string; label: string }> = [
  { bandKey: 'not-overdue', label: '未逾期' },
  { bandKey: 'overdue-1-30', label: '逾期1-30天' },
  { bandKey: 'overdue-31-90', label: '逾期31-90天' },
  { bandKey: 'overdue-91-180', label: '逾期91-180天' },
  { bandKey: 'overdue-181-365', label: '逾期181-365天' },
  { bandKey: 'overdue-1year', label: '逾期1年以上' },
]

export const LOCALSTORAGE_TAB_KEY = 'd1-notes-receivable-active-tab'
