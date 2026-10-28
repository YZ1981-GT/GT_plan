/**
 * K3~K7「调整分录汇总」按模板补的列（spec oo-writeback-template-parity-closure R3 批 B2c）。
 *
 * 模板十列（六册逐字相同）：A 调整事项说明 / B 类别（报表调整/账项调整/其他）/ C 报表项目 / D 科目名称 /
 * E 附注项目 / F …… / G 借方调整金额 / H 贷方调整金额 / I 索引 / J 备注。契约逐列声明了，前端行模型
 * 原来缺 类别 / 报表项目 / 附注项目 / 索引（K5 另缺备注、K7 只缺类别），这几列 OO 侧填了回到 HTML、
 * 下一次保存就被擦掉（载入时只挑已知字段）。
 *
 * 「类别」与「类型（AJE / RJE）」是两回事：类型决定回写审定表的 AJE / RJE 合计与集中登记，
 * 类别是模板的分类。新行按类型给类别缺省：审计调整（AJE）调账 = 账项调整，重分类（RJE）只调报表 = 报表调整。
 */

export const K_ADJ_CATEGORY_OPTIONS = ['报表调整', '账项调整', '其他'] as const

/** 类别缺省（只用于新行、旧行缺键时，以及改类型时类别仍是旧缺省值的情形）。 */
export function defaultKAdjCategory(entryType: unknown): string {
  return entryType === 'RJE' ? '报表调整' : '账项调整'
}

export interface KAdjTemplateFields {
  category: string
  reportItem: string
  noteItem: string
  indexRef: string
}

/** 载入一行：类别缺键（旧行）按类型给缺省、空串视为用户清空照留；其余三列缺省空。 */
export function readKAdjTemplateFields(raw: any): KAdjTemplateFields {
  const category = raw?.category
  return {
    category: category === undefined || category === null ? defaultKAdjCategory(raw?.entryType) : String(category),
    reportItem: String(raw?.reportItem ?? ''),
    noteItem: String(raw?.noteItem ?? ''),
    indexRef: String(raw?.indexRef ?? ''),
  }
}

/** 新行的四列：类别按类型给缺省，报表项目可带本表科目对应的报表项目。 */
export function newKAdjTemplateFields(entryType: unknown, reportItem = ''): KAdjTemplateFields {
  return { category: defaultKAdjCategory(entryType), reportItem, noteItem: '', indexRef: '' }
}

/** 改类型时：类别若仍是旧类型的缺省值就跟着换（用户改过的不动）。 */
export function followEntryTypeCategory(entry: { category: string }, oldType: unknown, newType: unknown): void {
  if (entry.category === defaultKAdjCategory(oldType)) entry.category = defaultKAdjCategory(newType)
}
