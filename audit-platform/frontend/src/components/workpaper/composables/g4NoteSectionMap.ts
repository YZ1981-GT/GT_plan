/**
 * G4 债权投资披露表 ↔ 附注章节映射
 *
 * 权威：`backend/data/note_template_variant_matrix.json`
 *   zhai_quan_tou_zi → listed 五、14 / soe 八、15
 *
 * 🔴 sheet 名常量必须是**源 xlsx 的中文 tab 名**（非 wp_code 形态合成标识、非短名），
 *    已逐字核对权威模板 `backend/wp_templates/G/G4 债权投资.xlsx`。
 *
 * spec: .kiro/specs/disclosure-sync-path-buildout/ Task 2.1
 */
export type G4DisclosureVariant = 'listed' | 'soe'

export const G4_NOTE_SECTION = {
  listed: '五、14',
  soe: '八、15',
} as const satisfies Record<G4DisclosureVariant, string>

export const G4_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<G4DisclosureVariant, string>

/** 主表子表名（与 note_template `tables[].name` 逐字一致，两版不同） */
export const G4_MAIN_SUBTABLE = {
  listed: '债权投资',
  soe: '债权投资情况',
} as const satisfies Record<G4DisclosureVariant, string>

/**
 * 三阶段减值准备表名 —— 与底稿 `G4StageBlock.title` 一一对应。
 *
 * 🔴 国企侧底稿 title 带尾部「：」（`buildDefaultSoeStageBlocks`），模板表名**无冒号**
 *    → 同步前必须归一（见 `normalizeG4StageTableName`），否则产出孤儿子表。
 */
export const G4_STAGE_SUBTABLE = {
  listed: [
    '期末处于第一阶段的债权投资的减值准备',
    '期末处于第二阶段的债权投资的减值准备',
    '期末处于第三阶段的债权投资的减值准备',
    '上年年末处于第一阶段的债权投资的减值准备',
    '上年年末处于第二阶段的债权投资的减值准备',
    '上年年末处于第三阶段的债权投资的减值准备',
  ],
  soe: [
    '期末，处于第一阶段的债权投资的减值准备',
    '期末，处于第二阶段的债权投资的减值准备',
    '期末，处于第三阶段的债权投资的减值准备',
  ],
} as const satisfies Record<G4DisclosureVariant, readonly string[]>

/** 去掉底稿 title 的尾部冒号 / 全角冒号，对齐模板表名 */
export function normalizeG4StageTableName(title: string): string {
  return String(title ?? '').trim().replace(/[：:]+$/, '')
}

/**
 * 🔴 **底稿字段暂不支持、本轮不推送**的模板表（每条写明原因）。
 *
 * G4 披露组件把这几个 section 塞进了与主表共用的 6 列行模型
 * （`DisclosureRow` = item + 期末{账面余额,减值准备,账面价值} + 上年年末{…}），
 * 而源模板这几张表的列完全不同 → 强推会把主表口径的数字灌进错位的列。
 * 按「宁缺勿造」只同步字段真实存在的表；补齐需先给组件加列（独立工作量）。
 */
export const G4_NOT_SYNCED_TABLES: Readonly<Record<string, string>> = {
  债权投资减值准备本期变动情况:
    '源模板列为 期初余额/本期增加/本期减少/期末余额；底稿该 section 复用主表 6 列模型，无对应字段',
  期末重要的债权投资:
    '源模板列为 面值/票面利率/实际利率/到期日/逾期本金（两级表头）；底稿无这些字段',
  '期末重要的债权投资（续：上年年末余额）': '同上（续表）',
  '本期计提、收回或转回的减值准备情况':
    '源模板为 第一/二/三阶段 + 合计 的两级表头迁移表；底稿该 section 仍是主表 6 列模型',
  本期实际核销的债权投资: '源模板列为 项目/核销金额；底稿该 section 复用主表 6 列模型',
  '重要的债权投资核销情况（逐项披露）':
    '源模板列为 项目/债权投资性质/核销金额/核销原因/履行的核销程序/是否由关联交易产生；底稿无这些字段',
}

function isListedStandard(s: string): boolean {
  const x = String(s).toLowerCase()
  return x.includes('listed') || x.includes('上市')
}

function isSoeStandard(s: string): boolean {
  const x = String(s).toLowerCase()
  return (
    x.includes('soe') || x.includes('state_owned') || x.includes('国企') || x.includes('国有')
  )
}

/** 未声明适用准则时两个变体都放行（与 G5/G11 同口径） */
export function isG4DisclosureApplicable(
  variant: G4DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = applicableStandards ?? []
  if (list.length === 0) return true
  const hasListed = list.some(isListedStandard)
  const hasSoe = list.some(isSoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveG4CurrentStandard(
  variant: G4DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): string {
  const list = (applicableStandards || []).map((s) => String(s).toLowerCase())
  if (variant === 'listed') {
    return list.some((s) => s.includes('listed') && s.includes('consol'))
      ? 'listed_consolidated'
      : 'listed_standalone'
  }
  return list.some((s) => s.includes('soe') && s.includes('consol'))
    ? 'soe_consolidated'
    : 'soe_standalone'
}

export interface G4NoteSectionTarget {
  variant: G4DisclosureVariant
  sectionId: string
  sheetName: string
  currentStandard: string
  chipValue: string
}

export function resolveG4NoteSectionTarget(
  variant: G4DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): G4NoteSectionTarget | null {
  if (!isG4DisclosureApplicable(variant, applicableStandards)) return null
  const sectionId = G4_NOTE_SECTION[variant]
  return {
    variant,
    sectionId,
    sheetName: G4_DISCLOSURE_SHEET_NAME[variant],
    currentStandard: resolveG4CurrentStandard(variant, applicableStandards),
    chipValue: `Note:${sectionId}`,
  }
}

/** 报表科目（债权投资） */
export const G4_ACCOUNT_CODE = '1501'
