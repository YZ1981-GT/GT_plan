/**
 * 附注选择对话框纯逻辑（spec: disclosure-notes-selective-generation）。
 *
 * 抽为纯函数便于 vitest 单测（不依赖 el-tree 实例）：
 * - buildGroupedTree：按顶层中文序号分组构建 el-tree data
 * - computePresetKeys：一键预设勾选集 = has_data=true 的叶子 note_section
 * - deriveSelectedSections：从 el-tree getCheckedKeys 结果剔除分组父节点，取叶子集
 */

/** 附注树服务 GET /api/disclosure-notes/{pid}/{year} 返回的单节点 */
export interface NotesTreeNode {
  id: string
  note_section: string
  section_title: string | null
  account_name?: string | null
  content_type?: string | null
  status?: string | null
  sort_order?: number
  /** 本功能后端新增：章节是否含数据（与 Word 导出 _has_content 同口径） */
  has_data?: boolean
}

/** el-tree 叶子节点 */
export interface TreeLeaf {
  key: string // = note_section
  note_section: string
  label: string // note_section + section_title
  has_data: boolean
  isGroup: false
}

/** el-tree 分组父节点 */
export interface TreeGroup {
  key: string // __group__{numeral}
  label: string
  isGroup: true
  children: TreeLeaf[]
}

export const GROUP_KEY_PREFIX = '__group__'

/** 取 note_section 顶层中文序号段（首个「、」之前）；无「、」则整串作为分组键。 */
export function topLevelKey(noteSection: string): string {
  const s = noteSection ?? ''
  const idx = s.indexOf('、')
  return idx >= 0 ? s.slice(0, idx) : s
}

/** 章级附注（note_section 恰为章号，如「八」）在勾选树里的称呼：章名已显示在分组上，叶子只说明它是什么。 */
export const CHAPTER_ROW_LABEL = '本章整体说明'

/** 章号（只有中文序号：「九」「十一」），与后端 note_template_export_fill._CHAPTER_ONLY_RE 同口径。 */
const CHAPTER_ONLY_RE = /^[一二三四五六七八九十]{1,3}$/

export function isChapterRow(noteSection: string | null | undefined): boolean {
  return CHAPTER_ONLY_RE.test((noteSection ?? '').trim())
}

/**
 * 叶子称呼：编号 + 标题。按名称编码的章节（「四、存货」）编号已含标题，不再重复成「四、存货 存货」
 * （与后端导出提醒 note_display_label 同口径）；章级附注显示为「八 本章整体说明」。
 */
export function leafLabel(n: Pick<NotesTreeNode, 'note_section' | 'section_title'>): string {
  const code = (n.note_section ?? '').trim()
  const title = (n.section_title ?? '').trim()
  if (isChapterRow(code)) return `${code} ${CHAPTER_ROW_LABEL}`
  if (!title || code.endsWith(title)) return code
  return `${code} ${title}`
}

/**
 * 按顶层中文序号分组构建 el-tree data。
 * 保持后端返回顺序（已按 sort_order 排序）：分组按首次出现顺序，叶子按原序。
 * 分组称呼取该章章级附注的标题（「一、公司（企业）基本情况」），没有章级附注只显示章号（「一、」）。
 */
export function buildGroupedTree(nodes: NotesTreeNode[]): TreeGroup[] {
  const groups: TreeGroup[] = []
  const byKey = new Map<string, TreeGroup>()
  const chapterTitle = new Map<string, string>()
  for (const n of nodes ?? []) {
    const code = (n.note_section ?? '').trim()
    const title = (n.section_title ?? '').trim()
    if (isChapterRow(code) && title && !chapterTitle.has(code)) chapterTitle.set(code, title)
  }
  for (const n of nodes ?? []) {
    const numeral = topLevelKey(n.note_section)
    const groupKey = GROUP_KEY_PREFIX + numeral
    let g = byKey.get(groupKey)
    if (!g) {
      g = { key: groupKey, label: `${numeral}、${chapterTitle.get(numeral.trim()) ?? ''}`, isGroup: true, children: [] }
      byKey.set(groupKey, g)
      groups.push(g)
    }
    g.children.push({
      key: n.note_section,
      note_section: n.note_section,
      label: leafLabel(n),
      has_data: n.has_data === true,
      isGroup: false,
    })
  }
  return groups
}

/** 一键预设勾选集：has_data=true 的叶子 note_section（不含分组父节点）。 */
export function computePresetKeys(nodes: NotesTreeNode[]): string[] {
  return (nodes ?? []).filter((n) => n.has_data === true).map((n) => n.note_section)
}

/**
 * 从 el-tree getCheckedKeys 结果派生最终 selected_sections：
 * 剔除分组父节点 key（__group__ 前缀），仅保留叶子 note_section。
 */
export function deriveSelectedSections(checkedKeys: string[]): string[] {
  return (checkedKeys ?? []).filter((k) => typeof k === 'string' && !k.startsWith(GROUP_KEY_PREFIX))
}
