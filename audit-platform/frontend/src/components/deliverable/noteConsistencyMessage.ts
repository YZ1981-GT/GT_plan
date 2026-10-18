/**
 * 附注导出前一致性闸门：确认框正文（纯函数，供 DeliverableCenter 使用）
 *
 * Spec: deliverable-writeback-and-online-edit-integrity US-4（design §4.4）
 *
 * 🔴 确认框开了 `dangerouslyUseHTMLString`，章节标题、底稿编码来自库里的数据 ——
 *    原实现把它们原样拼进 HTML，字段里只要出现 `<` 就会被当成标签解析。这里统一转义后再拼。
 */
import type { NoteConsistency, NoteConsistencyItem } from '@/services/deliverableApi'

/** HTML 转义（元素内容与属性值两种位置都安全） */
export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function itemLine(item: NoteConsistencyItem): string {
  const name = escapeHtml(item.section_title || item.note_section || '')
  const codes = item.wp_codes?.length ? `（底稿 ${escapeHtml(item.wp_codes.join('、'))}）` : ''
  return `<p style="margin:2px 0;">• ${name}${codes}</p>`
}

/** 一致性闸门确认框正文（HTML）：从未同步 / 已过期两组，各带章节数 */
export function buildNoteConsistencyMessage(consistency: NoteConsistency | null | undefined): string {
  const neverSynced = consistency?.never_synced ?? []
  const stale = consistency?.stale ?? []
  const parts: string[] = [
    '<p style="margin-bottom:8px;font-weight:600;">⚠️ 以下附注章节与底稿披露表不一致，建议先回底稿同步后再导出：</p>',
  ]
  if (neverSynced.length) {
    parts.push(`<p style="color:#e74c3c;margin:6px 0 2px;font-weight:600;">从未从底稿同步（${neverSynced.length} 章）：</p>`)
    parts.push(neverSynced.map(itemLine).join(''))
  }
  if (stale.length) {
    parts.push(`<p style="color:#e6a23c;margin:6px 0 2px;font-weight:600;">底稿已更新、附注陈旧（${stale.length} 章）：</p>`)
    parts.push(stale.map(itemLine).join(''))
  }
  parts.push('<p style="margin-top:10px;color:#666;font-size:12px;">附注数据由底稿披露表单项推送。请到底稿披露表重新同步这些章节；如确需带不一致导出，可选「仍要导出」。</p>')
  return parts.join('')
}
