/**
 * 附注正文批量写入：界面中文标签与分组判定（R-21：首版直接显示英文枚举与内部 source_id）。
 */
import type { ApplyMode, PreviewItem, PreviewResponse, SourceKind } from '@/composables/useNoteTextBatch'

/** 后端 note_quality_scanner.QualityFlag + build_preview 的 cross_standard */
export const QUALITY_FLAG_LABELS: Record<string, string> = {
  empty: '空白',
  placeholder: '含占位文本',
  draft: '来源为草稿',
  stale: '来源待刷新',
  source_entity: '含来源企业名称',
  date: '含具体日期',
  amount: '含具体金额',
  entity_specific: '企业特有内容',
  account_explanation: '报表科目解释',
  cross_standard: '跨标准/口径',
}

/** 与后端 summary.high_risk 同口径：这些风险必须在差异弹窗逐项确认后才能采用 */
export const HIGH_RISK_FLAGS = new Set(['source_entity', 'entity_specific', 'account_explanation', 'cross_standard'])

export const CONFIDENCE_LABELS: Record<string, string> = {
  confirmed: '已确认',
  candidate: '候选（需人工确认）',
  manual_required: '需人工选择',
}

export const TEMPLATE_TYPE_LABELS: Record<string, string> = { soe: '国企版', listed: '上市版' }
export const REPORT_SCOPE_LABELS: Record<string, string> = { standalone: '单体', consolidated: '合并' }

export function flagLabel(flag: string): string {
  return QUALITY_FLAG_LABELS[flag] ?? '其他风险'
}

export function highRiskFlags(item: PreviewItem): string[] {
  return item.quality_flags.filter(f => HIGH_RISK_FLAGS.has(f))
}

/** 目标章节显示名：编号 + 标题；未匹配显示「未匹配」 */
export function targetLabel(item: Pick<PreviewItem, 'target_note_section' | 'target_section_title'>): string {
  if (!item.target_note_section) return '未匹配'
  return [item.target_note_section, item.target_section_title].filter(Boolean).join(' ')
}

export interface SourceMatchStatus { label: string; type: 'success' | 'warning' | 'info'; hint: string }
const SKIPPED_LABELS: Record<string, string> = { folded: '已并入上级章节', out_of_scope: '不在可填范围' }

/**
 * 左栏来源的匹配状态（AC-2.2），与右栏三分组同口径：未预览时为空；
 * 预览后每个来源要么是预览项（推荐 / 需复核 / 不可用 / 未匹配），要么被服务端跳过（带原因）。
 */
export function sourceMatchStatuses(
  preview: Pick<PreviewResponse, 'items' | 'skipped_sources'> | null | undefined,
): Map<string, SourceMatchStatus> {
  const out = new Map<string, SourceMatchStatus>()
  if (!preview) return out
  for (const s of preview.skipped_sources ?? []) {
    out.set(s.source_id, { label: SKIPPED_LABELS[s.match_kind] ?? '未进入预览', type: 'info', hint: '' })
  }
  for (const item of preview.items) {
    const target = targetLabel(item)
    if (item.category === 'recommended') out.set(item.source_id, { label: '推荐引用', type: 'success', hint: target })
    else if (item.category === 'review') out.set(item.source_id, { label: '需复核', type: 'warning', hint: target })
    else out.set(item.source_id, { label: item.target_note_id ? '不可用' : '未匹配', type: 'info',
      hint: item.unavailable_reason || target })
  }
  return out
}

/** 勾选摘要（AC-9.6）：总数、新增、替换、追加、高风险、未映射 */
export function selectionSummary(items: PreviewItem[], selected: Set<string>, modes: Record<string, ApplyMode>) {
  const chosen = items.filter(i => selected.has(i.source_id))
  return {
    total: chosen.length,
    new: chosen.filter(i => i.append_html === null).length,
    replace: chosen.filter(i => i.append_html !== null && (modes[i.source_id] ?? 'replace') === 'replace').length,
    append: chosen.filter(i => i.append_html !== null && modes[i.source_id] === 'append').length,
    highRisk: chosen.filter(i => highRiskFlags(i).length > 0).length,
    unmapped: items.filter(i => !i.target_note_id).length,
  }
}

interface SourceDocMeta { document_name?: string | null; doc_version?: number | null }
interface SourceMeta { file_name?: string | null; documents?: SourceDocMeta[] }

/** 上传弹窗顶部的来源说明；知识库显示文档名称与版本（AC-5.1，首版只显示名称） */
export function describeSource(kind: SourceKind, meta: SourceMeta | null | undefined): string {
  if (!meta) return ''
  if (kind === 'upload') return `文件：${meta.file_name ?? ''}`
  const docs = (meta.documents ?? []).map(d => (d.doc_version != null
    ? `${d.document_name ?? '未命名文档'}（v${d.doc_version}）` : (d.document_name ?? '未命名文档')))
  return `知识库：${docs.join('、')}`
}
