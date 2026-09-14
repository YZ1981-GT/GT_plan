/**
 * noteScopeTargeting.ts — 附注域「公式管理」定位与筛选的单一真源
 *
 * 背景（修复）：附注编辑页点「⚙️ 公式管理」时，弹窗默认停在「报表 > 资产负债表」，
 * 不是当前页面对应的附注章节。根因两条：
 *   1. DisclosureEditor 未传 scope='note'，且传入的 rows 是附注表格行（row_code 形如
 *      「五、1-R1」），被 FormulaManagerDialog 的报表启发式（BS-/IS-/CFS- 前缀判定）
 *      兜底成 balance_sheet；
 *   2. watch(visible) 没有附注分支，selectedNodeKey 保持初始值 'report_balance_sheet'。
 *
 * 本模块把「章节 → 树节点 key」与「章节 → 预设公式子集」两条规则收敛为纯函数，
 * 由 FormulaManagerDialog 唯一消费（树构建 + 打开定位 + 行筛选共用），避免各处各抄一份。
 */

/** 附注预设公式条目（来自 GET /api/note-templates/preset-formulas/{soe|listed}）。 */
export interface NotePresetFormula {
  id?: string
  /** 章节编号，如「五、1」。不同模板版本编号体系可能偏移，不可作为唯一匹配键。 */
  note_section?: string
  /** 章节标题，如「货币资金」。跨版本稳定，是首选匹配键。 */
  section_title?: string
  table_name?: string
  category?: string
  formula?: string
  description?: string
  source?: string
  [k: string]: unknown
}

/** 章节定位上下文：编号 + 标题，二者任一可用。 */
export interface NoteSectionRef {
  /** note_section，如「五、1」 */
  sectionId?: string
  /** section_title，如「货币资金」 */
  sectionTitle?: string
}

/**
 * note_section → 附注树节点 key。
 *
 * 与 FormulaManagerDialog 动态附注树 / 静态降级树的 key 规则保持一致：
 * 去掉中文顿号、逗号、句号与空白后加 `note_` 前缀（「五、1」→ `note_五_1`）。
 */
export function noteSectionToNodeKey(sectionId: string): string {
  return `note_${String(sectionId ?? '').replace(/[、，。\s]/g, '_')}`
}

/**
 * 判定树节点 key 是否属于附注域。
 *
 * 附注域根节点 key 是 `note`（无下划线），章节/章 key 是 `note_*`。仅判 `note_` 前缀会把
 * 域根节点漏掉 —— 章节未在树中命中时定位会退到域根，此时公式列表必须照样按附注域取数。
 */
export function isNoteDomainNodeKey(key: string): boolean {
  const k = String(key ?? '')
  return k === 'note' || k.startsWith('note_')
}

/**
 * 从附注预设公式全集中筛出属于指定章节的公式。
 *
 * 匹配优先级（先命中即返回，避免降级规则把他章公式带进来）：
 *   1. section_title 精确相等 —— 跨模板版本稳定，首选。
 *   2. section_title 双向 includes —— 标题被裁剪（如带序号前缀）时的兜底。
 *   3. note_section 精确相等 —— 仅在**没有传标题**时启用。
 *
 * 为什么编号只在无标题时才用：项目实测上市版「五、17」是「设定受益计划净资产」，而预设集
 * 「五、17」是「其他综合收益」，编号体系存在偏移。若标题匹配不上再退编号，会把他章公式
 * 挂到本章（张冠李戴），比返回空更糟 —— 宁缺勿造。
 *
 * 为什么 includes 不能当首选：直接用 includes 会让「债权投资」把「其他债权投资」的公式
 * 一并带出（实测 soe 3 组 / listed 5 组标题互含）。
 */
export function filterNotePresetsForSection<T extends NotePresetFormula>(
  presets: readonly T[],
  ref: NoteSectionRef,
): T[] {
  const list = Array.isArray(presets) ? presets : []
  if (!list.length) return []

  const title = (ref.sectionTitle || '').trim()
  const sectionId = (ref.sectionId || '').trim()
  if (!title && !sectionId) return []

  if (title) {
    const exactTitle = list.filter((f) => (f.section_title || '').trim() === title)
    if (exactTitle.length) return exactTitle

    const loose = list.filter((f) => {
      const t = (f.section_title || '').trim()
      if (!t) return false
      return t.includes(title) || title.includes(t)
    })
    if (loose.length) return loose

    // 有标题但匹配不上 → 返回空，不退编号（编号体系可能偏移，见上）
    return []
  }

  if (sectionId) {
    return list.filter((f) => (f.note_section || '').trim() === sectionId)
  }

  return []
}

/** 公式管理表格行（FormulaManagerDialog 主表消费的形态）。 */
export interface NoteFormulaRow {
  id: string
  row_code?: string
  row_name?: string
  formula?: string
  formula_category?: string
  formula_description?: string
  formula_source?: string
}

/**
 * 章节 → 公式管理表格行。
 *
 * 命中本章节则只列本章节公式；章级节点或无章节上下文（筛不出）时列全部，
 * 让用户仍可搜索/浏览，而不是给一张空表。
 */
export function buildNoteFormulaRows(
  presets: readonly NotePresetFormula[],
  ref: NoteSectionRef,
): NoteFormulaRow[] {
  const list = Array.isArray(presets) ? presets : []
  const scoped = filterNotePresetsForSection(list, ref)
  const source = scoped.length ? scoped : list
  return source.map((f, i) => ({
    id: `note_preset_${i}`,
    row_code: f.note_section,
    row_name: f.section_title,
    formula: f.formula,
    formula_category: f.category,
    formula_description: f.description,
    formula_source: f.source,
  }))
}
