/**
 * 单体财务报表「其他问题」的数据源头 → 源头页链接（spec citar-fs-issue-source-locate）。
 * 后端只给语义（page + 编码），路由只在这里换算；源头页读 ?locate= 滚到该行并高亮（useCitarRowLocate）。
 */
import type { FsSourcePage } from './taxAssuranceApi'

export interface SourceLink {
  segment: string
  query: Record<string, string>
}

/** 源头页名称（按钮文字） */
export const SOURCE_PAGE_LABELS: Record<Exclude<FsSourcePage, 'statement'>, string> = {
  balance: '科目余额表',
  journal: '序时账',
  mapping: '底稿映射',
  trial_balance: '试算平衡表',
  adjustments: '调整分录',
  ledger_import: '数据导入',
  reports: '审定报表',
}

/** 页 + 编码 → 本项目菜单与查询参数；statement（本页格子）与 null 不跳页 */
export function sourceLink(page: FsSourcePage | null, code = ''): SourceLink | null {
  const locate: Record<string, string> = code ? { locate: code } : {}
  switch (page) {
    case 'balance':
      return { segment: 'ledger-query', query: { tab: 'balance', ...locate } }
    case 'journal':
      return { segment: 'ledger-query', query: code ? { tab: 'journal', account: code } : { tab: 'journal' } }
    case 'mapping':
      return { segment: 'mapping', query: { tab: 'standard', ...locate } }
    case 'trial_balance':
      return { segment: 'trial-balance', query: locate }
    case 'adjustments':
      return { segment: 'adjustments', query: {} }
    case 'ledger_import':
      return { segment: 'ledger-import', query: {} }
    case 'reports':
      return { segment: 'reports', query: {} }
    default:
      return null
  }
}
