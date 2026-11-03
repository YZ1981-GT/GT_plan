/**
 * ACNR sheet 显示名 — 前端只排序、不拼名（spec acnr-foundation-defect-closure T30，design §13.2~13.3）
 *
 * sheet / cell 的显示名由后端 `services/acnr/display.py` 统一计算、生成器写进目录的 `display_label`
 * （cell 另有 `cell_label`），`/api/acnr/entries`、`/anchors`、resolve 原样返回；前端三棵树
 * （公式选址器 / 高级查询选字段 `useAcnr.buildAddressTree`、公式管理树 `FormulaManagerDialog.buildWpDomainTree`、
 * 公式编辑数据源树 `FormulaEditDialog`）只按编码自然序排列并读 `display_label`，不再自己拼名。
 *
 * 树的父节点标题「{父级码} {科目简称}」不是某个 addr_id 的显示名，留在本文件 `groupHeaderLabel`。
 */

export interface SheetLabelInput {
  sheet_code?: string
  addr_id?: string
  display_label?: string
  /** 科目简称（取父底稿）— 后端 list_sheets 注入；只供 groupHeaderLabel 用 */
  account_name?: string
}

export interface SortedSheetLabel<T extends SheetLabelInput> {
  entry: T
  /** 目录统一显示名（`display_label`；缺字段时退回编码） */
  label: string
}

/**
 * 底稿编码自然排序：拆 letter/number/-number/suffix，数字段按数值比。
 * 修复 localeCompare 字符串排序导致 D2-10 排在 D2-2 之前的问题。
 */
export function wpCodeNaturalCompare(a: string, b: string): number {
  const parse = (code: string) => {
    const m = /^([A-Za-z]+)(\d+)?(?:-(\d+))?(.*)$/.exec((code || '').trim())
    if (!m) return { letter: code || '', n1: Number.MAX_SAFE_INTEGER, n2: -1, rest: '' }
    return {
      letter: m[1] || '',
      n1: m[2] ? parseInt(m[2], 10) : -1,
      n2: m[3] ? parseInt(m[3], 10) : -1,
      rest: m[4] || '',
    }
  }
  const pa = parse(a)
  const pb = parse(b)
  if (pa.letter !== pb.letter) return pa.letter.localeCompare(pb.letter)
  if (pa.n1 !== pb.n1) return pa.n1 - pb.n1
  if (pa.n2 !== pb.n2) return pa.n2 - pb.n2
  return pa.rest.localeCompare(pb.rest)
}

/** 一组 sheet 按编码自然序排列，标签取目录 `display_label`（缺字段退回 sheet_code / addr_id）。 */
export function sortSheetsForGroup<T extends SheetLabelInput>(group: T[]): Array<SortedSheetLabel<T>> {
  return group
    .slice()
    .sort((a, b) => wpCodeNaturalCompare(a.sheet_code || '', b.sheet_code || ''))
    .map((entry) => ({ entry, label: entry.display_label || entry.sheet_code || entry.addr_id || '' }))
}

/** 树的父节点标题：「{父级码} {科目简称}」（组内首个有简称的 sheet），无简称只显示父级码。 */
export function groupHeaderLabel(parentCode: string, group: SheetLabelInput[]): string {
  const subjectAbbr = group.find((s) => s.account_name)?.account_name || ''
  return subjectAbbr ? `${parentCode} ${subjectAbbr}` : parentCode
}
