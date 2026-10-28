/**
 * 「合并」总览页拖拽改上级的结果提示（spec consol-autotree-linkage-closure R3.3）。
 *
 * 后端 `PATCH /api/projects/{id}/parent-code` 把同企业同年度的合并项目与单户项目一起改（上级代码、上级名称、
 * 与上级关系、补齐最终控制方、向导回填数据），返回同步了哪些项目的哪些字段与说明；这里拼成一句给用户看。
 */

export interface ReparentSyncedItem {
  id: string
  name: string
  report_scope: string
  /** 变化了的字段（中文名，后端 FIELD_LABELS） */
  fields: string[]
}

export interface ReparentResult {
  parent_company_code?: string | null
  parent_company_name?: string | null
  synced?: ReparentSyncedItem[]
  notices?: string[]
}

const SCOPE_LABELS: Record<string, string> = { consolidated: '合并项目', standalone: '单户项目' }

/** 「已同步 甲公司（单户项目）的上级企业代码、上级企业名称；甲公司（合并项目）的…。上级企业 X 本年度尚未建项…。」 */
export function reparentSummary(result: ReparentResult | null | undefined): string {
  const changed = (result?.synced || []).filter((s) => Array.isArray(s.fields) && s.fields.length)
  const parts = [changed.length
    ? `已同步 ${changed.map((s) => `${s.name}（${SCOPE_LABELS[s.report_scope] || '项目'}）的${s.fields.join('、')}`).join('；')}`
    : '项目信息没有变化']
  for (const notice of result?.notices || []) if (notice) parts.push(notice.replace(/[。.]$/, ''))
  return `${parts.join('。')}。`
}
