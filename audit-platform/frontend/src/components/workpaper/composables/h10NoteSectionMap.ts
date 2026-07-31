/**
 * H10 资产处置损益（6115）↔ 附注章节映射
 *
 * note_template_listed：三、资产处置收益（chapter-03…zi-chan-chu-zhi-shou-yi）
 * note_template_soe / variant_matrix：八、75 资产处置收益
 */
export type H10DisclosureVariant = 'listed' | 'soe'

export const H10_SOE_NOTE_SECTION = '八、75'

/**
 * 🔴 上市章节号必须逐字等于模板 `section_number` —— `sync_from_workpaper` 按
 * `(project_id, year, note_section)` **精确匹配**定位，差一个字就会新建垃圾章节。
 *
 * listed 模板 `三、` 章的 `section_number` 被 md 重建截断为 10 字符
 * （`三、资产处置收益（损`），这是**既有真源形态**（全库 70+ 条同款，K11~K13 曾同款踩中）
 * → 修法是本常量对齐模板，不是改模板编号。
 */
/*
 * 🔴 章节号字面量必须**内联**在下面的对象里，且对象体内**不要写注释**：
 * `backend/scripts/gen_note_wp_sync_registry.py` 用正则从对象体抽 `listed: '…'`，
 * 写成标识符引用会让 H10 整条从 registry 消失；对象体内的注释若含 `listed: '…'`
 * 字样会被优先抓到（两种情况本 spec 都实测踩过）。
 */
export const H10_NOTE_SECTION = {
  listed: '三、资产处置收益（损',
  soe: H10_SOE_NOTE_SECTION,
} as const satisfies Record<H10DisclosureVariant, string>

/** 上市章节号（= `H10_NOTE_SECTION.listed`，单一真源在上面的对象里） */
export const H10_LISTED_NOTE_SECTION: string = H10_NOTE_SECTION.listed

/** 界面展示用章节名（截断的 section_number 直接显示不可读；定位一律用 H10_NOTE_SECTION） */
export const H10_NOTE_SECTION_DISPLAY = {
  listed: '三、资产处置收益',
  soe: '八、75 资产处置收益',
} as const satisfies Record<H10DisclosureVariant, string>

/** 逐字等于源 xlsx tab 名（H10 国企是「国企」不是「国有企业」，H7 才是「国有企业」） */
export const H10_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<H10DisclosureVariant, string>

/** 附注模板主表名（与 note_template tables[].name 一致） */
export const H10_MAIN_SUBTABLE = {
  listed: '资产处置收益（损失以“-”填列）',
  soe: '资产处置收益（损失以“-”号填列）',
} as const satisfies Record<H10DisclosureVariant, string>

/** 上市试运行销售明细子表名（第二张表，与模板 tables[1] 对齐） */
export const H10_TRIAL_SUBTABLE = '试运行销售损益'

/**
 * 改版前的旧表名 —— 上市两张表原本**同名** `项  目`（表头首格泄漏），
 * `sub_table_data` 以表名为键故后一张覆盖前一张、试运行明细永远丢失。
 * 正名后旧名须进 `_removed_table_keys`，防附注残留孤儿表。
 */
export const H10_LEGACY_OBSOLETE_TABLES: readonly string[] = ['项  目']

function isListedStandard(s: string): boolean {
  const x = String(s).toLowerCase()
  return x.includes('listed') || x.includes('上市') || x === 'listed_standalone' || x === 'listed_consolidated'
}

function isSoeStandard(s: string): boolean {
  const x = String(s).toLowerCase()
  return (
    x.includes('soe')
    || x.includes('state_owned')
    || x.includes('国企')
    || x.includes('国有')
    || x === 'soe_standalone'
    || x === 'soe_consolidated'
  )
}

export function isH10DisclosureApplicable(
  variant: H10DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = applicableStandards ?? []
  if (list.length === 0) return true
  const hasListed = list.some(isListedStandard)
  const hasSoe = list.some(isSoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveH10CurrentStandard(
  variant: H10DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): string {
  const list = (applicableStandards || []).map((s) => String(s).toLowerCase())
  if (variant === 'listed') {
    if (list.some((s) => s === 'listed_consolidated' || (s.includes('listed') && s.includes('consol')))) {
      return 'listed_consolidated'
    }
    return 'listed_standalone'
  }
  if (list.some((s) => s === 'soe_consolidated' || (s.includes('soe') && s.includes('consol')))) {
    return 'soe_consolidated'
  }
  return 'soe_standalone'
}

export function resolveH10NoteSectionTarget(
  variant: H10DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): { sectionId: string; sheetName: string; currentStandard: string; chipValue: string } | null {
  if (!isH10DisclosureApplicable(variant, applicableStandards)) return null
  const sectionId = H10_NOTE_SECTION[variant]
  return {
    sectionId,
    sheetName: H10_DISCLOSURE_SHEET_NAME[variant],
    currentStandard: resolveH10CurrentStandard(variant, applicableStandards),
    chipValue: `Note:${sectionId}`,
  }
}
