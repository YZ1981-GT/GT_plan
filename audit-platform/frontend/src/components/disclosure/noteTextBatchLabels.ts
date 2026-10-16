/**
 * 附注正文批量写入：界面中文标签与分组判定（R-21：首版直接显示英文枚举与内部 source_id）。
 */
import type {
  ApplyMode, NoteTextSource, ParsedSection, PreviewItem, PreviewResponse, SourceKind, TargetSection,
} from '@/composables/useNoteTextBatch'
import type { ContentTemplateItem, ContentTemplateVersion } from '@/composables/useNoteContentTemplate'
import { fmtDate } from '@/utils/formatters'

/**
 * 后端时间是 UTC（timestamptz 序列化带 +00:00），按本地日期显示：
 * 直接截前 10 位会把北京时间 0~8 点保存 / 写入的记录显示成前一天。
 */
function localDate(iso: string | null | undefined): string {
  const text = iso ? fmtDate(iso) : ''
  return text === '-' ? '' : text
}

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
const SKIPPED_LABELS: Record<string, string> = {
  folded: '已并入上级章节', out_of_scope: '不在可填范围', anchor: '已定位到章',
}

/**
 * 手工对应下拉的两类目标（第 23 组，与后端 validate_tree_mappings 同口径）：
 * - anchors：章节树上有子节点的行 —— 只作定位锚点，选中后其下小标题在该章内定位（重新预览）；
 * - leaves：没有子节点、且在本次可写范围（上传 / 知识库只填叙述性章节，内容模板全套）的行。
 */
export function splitMappingTargets(targets: TargetSection[], sourceKind: SourceKind) {
  const parents = new Set(targets.map(t => t.parent_section_id).filter((v): v is string => !!v))
  const hasChildren = (t: TargetSection) => !!t.section_id && parents.has(t.section_id)
  const writable = sourceKind === 'content_template' ? ['narrative', 'account_explanation'] : ['narrative']
  return {
    anchors: targets.filter(hasChildren),
    leaves: targets.filter(t => !hasChildren(t) && writable.includes(t.section_kind)),
  }
}

/** 左栏缩进：按章节树深度（上级链长度），不按原始标题级别（国企 Word 章 H1 下节是 H3，按级别会空出一格） */
export function sourceDepths(sections: Array<Pick<ParsedSection, 'source_id' | 'parent_source_id' | 'level'>>) {
  const parentOf = new Map(sections.map(s => [s.source_id, s.parent_source_id ?? null]))
  const hasTree = sections.some(s => s.parent_source_id)
  const out = new Map<string, number>()
  for (const s of sections) {
    if (!hasTree) { out.set(s.source_id, Math.max(0, (s.level || 1) - 1)); continue }
    let depth = 0
    let parent = parentOf.get(s.source_id) ?? null
    while (parent && depth < 10) { depth += 1; parent = parentOf.get(parent) ?? null }
    out.set(s.source_id, depth)
  }
  return out
}

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
    out.set(s.source_id, { label: SKIPPED_LABELS[s.match_kind] ?? '未进入预览', type: s.match_kind === 'anchor' ? 'success' : 'info',
      hint: s.evidence ?? '' })
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
/** 保存人 / 时间（AC-8.2）：模板选择器与引用弹窗共用同一口径 */
export function savedByLabel(v: Pick<ContentTemplateVersion, 'created_by_name' | 'created_at'>): string {
  const date = localDate(v.created_at)
  if (v.created_by_name) return date ? `${v.created_by_name} 保存于 ${date}` : `保存人 ${v.created_by_name}`
  return date ? `保存于 ${date}` : ''
}

export interface AppliedHint { text: string; changed: boolean }

/**
 * 「本项目已引用」只读提示（AC-8.4）：模板发布新版本不会自动改已引用项目的正文，用户重新预览并确认后才写入。
 * changed = 模板当前版本与本项目最近一次引用的版本不同（含刻意引回旧版、模板内容回退两种情况）。
 */
export function appliedHint(item: Pick<ContentTemplateItem, 'current_version' | 'last_applied'>): AppliedHint | null {
  const applied = item.last_applied
  if (!applied) return null
  const current = item.current_version
  if (!current || current.id === applied.version_id) {
    return { text: `本项目已引用${current ? '当前版本' : ''} v${applied.version_no}`, changed: false }
  }
  const head = current.version_no > applied.version_no
    ? `有新版本 v${current.version_no}（本项目已引用 v${applied.version_no}）`
    : `模板当前为 v${current.version_no}（本项目已引用 v${applied.version_no}）`
  return { text: `${head}：已写入的正文不会自动更新，点「重新预览」核对后才会写入`, changed: true }
}

/**
 * 编辑器章节标题旁的来源标记（Task 50 / AC-11.3）：只在平台界面显示，不进附注正文与导出。
 * 写入后有人改过正文 ⇒ 标「之后有修改」，复核时据此判断是否仍是引用原样。
 */
export function sourceBadgeText(s: NoteTextSource): { text: string; hint: string; modified: boolean } {
  const what = s.source_kind === 'content_template'
    ? `📋 来自内容模板「${s.template_name || '未命名模板'}」${s.version_no != null ? `v${s.version_no}` : ''}`
    : s.source_kind === 'upload'
      ? `📄 来自上传文档「${s.file_name || '未命名文件'}」`
      : `📚 来自知识库「${describeSource('knowledge', { documents: s.documents ?? [] }).replace(/^知识库：/, '')}」`
  const mode = s.mode === 'append' ? '追加' : '替换'
  const hint = [localDate(s.applied_at), s.applied_by_name || '', `批量写入（${mode}）`]
    .filter(Boolean).join(' ')
  return { text: s.modified_after ? `${what}（之后有修改）` : what, hint, modified: s.modified_after }
}
