/**
 * D2 应收账款 — 共享常量（从 legacy monolith 抽出供测试与 Tab 复用）
 */
import type { ChecklistResponse } from './useD2FormData'

export type TabStatus = 'completed' | 'in-progress' | 'not-started'

export const TAB_NAMES = [
  'directory', 'procedure', 'adjudication', 'disclosure',
  'detail-d2-2', 'bad-debt', 'cutoff-test', 'adjustment',
  'ecl-calculation', 'ecl-measurement', 'analysis',
  'related-party', 'factoring', 'general-check',
  'policy-check', 'writeoff-check', 'bizmodel-check',
] as const

export const PROCEDURE_STEPS_CONFIG: Array<{
  stepName: string
  description: string
  isRequired: boolean
  relatedTab: string | null
}> = [
  { stepName: '获取并核对明细', description: '获取应收账款明细表，检查与总账/明细账一致性', isRequired: true, relatedTab: 'detail-d2-2' },
  { stepName: '核对总账', description: '核对应收账款总账余额与明细账合计数', isRequired: true, relatedTab: 'adjudication' },
  { stepName: '函证', description: '对重要客户执行函证程序', isRequired: true, relatedTab: null },
  { stepName: '替代程序', description: '对未回函客户执行替代审计程序', isRequired: true, relatedTab: null },
  { stepName: '坏账准备', description: '评估应收账款预期信用损失计提充分性', isRequired: true, relatedTab: 'bad-debt' },
  { stepName: '截止测试', description: '检查收入确认截止日期的准确性', isRequired: true, relatedTab: 'cutoff-test' },
  { stepName: '结论', description: '汇总应收账款审计发现，形成整体结论', isRequired: false, relatedTab: null },
]

export const AGING_BANDS_CONFIG: Array<{ bandKey: string; label: string }> = [
  { bandKey: 'within-1y', label: '1年以内' },
  { bandKey: '1-2y', label: '1-2年' },
  { bandKey: '2-3y', label: '2-3年' },
  { bandKey: '3-4y', label: '3-4年' },
  { bandKey: '4-5y', label: '4-5年' },
  { bandKey: 'over-5y', label: '5年以上' },
]

export const ADJUDICATION_ROWS_CONFIG: Array<{ rowKey: string; label: string }> = [
  { rowKey: 'individual', label: '应收账款-单项计提' },
  { rowKey: 'aging-combo', label: '应收账款-账龄组合' },
  { rowKey: 'customer-combo', label: '应收账款-客户类型组合' },
  { rowKey: 'bad-debt', label: '坏账准备' },
  { rowKey: 'book-value', label: '账面价值' },
  { rowKey: 'total', label: '合计' },
]

export function getTabStatusFromResponses(tabResponses: ChecklistResponse[]): TabStatus {
  if (tabResponses.length === 0) return 'not-started'
  const hasValue = tabResponses.some(r => r.conclusion || r.remark)
  if (!hasValue) return 'not-started'
  const allComplete = tabResponses.every(r => r.conclusion || r.remark)
  return allComplete ? 'completed' : 'in-progress'
}

/**
 * D2 底稿 sheet 名 → 内部分发键（`GtD2AccountsReceivable.currentSheet` 唯一实现）。
 *
 * 🔴 判定顺序不可调换：附注披露 sheet 必须**先于** wp_code 后缀正则判定。
 * 源模板 tab 名形如 `附注披露信息（国企）D2-1` / `附注披露信息(上市公司）D2-1`
 * —— 尾部带 wp_code，若先跑 `/D2(?:-\d+)?[A-Z]?$/` 会被判成 `D2-1`（审定表），
 * 披露组件永远挂不上（2026-07-30 Playwright 实测：点「附注披露信息（国企）D2-1」
 * 渲染出「应收账款审定表 D2-1」，`get_diagnostics` 与 vitest 均查不出）。
 *
 * 「国企」与「国有企业」两种源模板写法都必须认（平台级铁律，见
 * `__tests__/disclosureSheetDispatch.spec.ts`）。
 */
export function normalizeD2SheetName(sheetName?: string | null): string {
  const name = sheetName || 'D2'
  if (name.includes('目录')) return '目录'
  if (name.includes('附注')) {
    if (name.includes('上市')) return '附注上市'
    if (name.includes('国企') || name.includes('国有')) return '附注国企'
  }
  const codeMatch = name.match(/D2(?:-\d+)?[A-Z]?$|D2A$/)
  if (codeMatch) return codeMatch[0]
  if (name.includes('上市')) return '附注上市'
  if (name.includes('国企') || name.includes('国有')) return '附注国企'
  if (name.includes('截止')) return '截止测试'
  if (name === 'D2' || name.startsWith('D2 ')) return 'D2'
  return name
}
