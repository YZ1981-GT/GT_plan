/** G9 科目码匹配 — 全链路统一（审定/TB/调整/抽凭/辅助核算） */
import { G9_ACCOUNT_ALIASES, G9_ACCOUNT_CODE, G9_ACCOUNT_NAME } from './g9Constants'

/** 科目代码是否属于 G9「其他非流动金融资产」（含别名前缀） */
export function isG9AccountCode(code: string | null | undefined): boolean {
  const c = String(code ?? '').trim()
  if (!c) return false
  return G9_ACCOUNT_ALIASES.some((prefix) => c === prefix || c.startsWith(prefix))
}

/** 分录默认科目码（新建行） */
export function g9DefaultAccountCode(): string {
  return G9_ACCOUNT_CODE
}

/** UI 展示：其他非流动金融资产(1519) 或别名列表 */
export function g9AccountLabel(resolvedCode?: string | null): string {
  const code = resolvedCode?.trim() || G9_ACCOUNT_ALIASES.join('/')
  return `${G9_ACCOUNT_NAME}(${code})`
}
