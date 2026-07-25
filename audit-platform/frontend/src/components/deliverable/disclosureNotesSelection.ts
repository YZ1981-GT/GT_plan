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

/**
 * 按顶层中文序号分组构建 el-tree data。
 * 保持后端返回顺序（已按 sort_order 排序）：分组按首次出现顺序，叶子按原序。
 */
export function buildGroupedTree(nodes: NotesTreeNode[]): TreeGroup[] {
  const groups: TreeGroup[] = []
  const byKey = new Map<string, TreeGroup>()
  for (const n of nodes ?? []) {
    const numeral = topLevelKey(n.note_section)
    const groupKey = GROUP_KEY_PREFIX + numeral
    let g = byKey.get(groupKey)
    if (!g) {
      g = { key: groupKey, label: `${numeral}、`, isGroup: true, children: [] }
      byKey.set(groupKey, g)
      groups.push(g)
    }
    const title = n.section_title ? ` ${n.section_title}` : ''
    g.children.push({
      key: n.note_section,
      note_section: n.note_section,
      label: `${n.note_section}${title}`,
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
