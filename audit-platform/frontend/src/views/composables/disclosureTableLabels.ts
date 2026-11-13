import { isEmptyTable, type EmptyTableColumnDef, type EmptyTableRow } from './disclosureEmptyTable'

const GENERIC_NAMES = new Set([
  '项  目', '项 目', '项目', '类  别', '类 别', '类别', '账  龄', '账 龄', '账龄',
  '债务人名称', '组合名称', '',
])
const TABLE_SUFFIX_RE = /[（(]表\d+[）)]/
const AUTO_INDEX_RE = /前[五十5]名|前\d+名/

export function getSingleTableTitle(tables: any[], sectionTitle: string): string {
  if (tables.length !== 1 || !tables[0]) return ''
  const name = String(tables[0].name || '').trim()
  if (!name || name === sectionTitle.trim() || GENERIC_NAMES.has(name)) return ''
  return name
}

export function shouldShowTableAutoIndex(table: any): boolean {
  if (!table) return false
  return !!table.auto_index || AUTO_INDEX_RE.test(String(table.name || '').trim())
}

export function getTableTabFullName(table: any, index: number): string {
  const name = String(table?.name || '').trim()
  if (name && !GENERIC_NAMES.has(name) && !TABLE_SUFFIX_RE.test(name)) return name
  const headers = table?.headers || []
  if (headers.length > 1) {
    const header = String(headers[1] || '').trim()
    if (header && header.length <= 8 && !GENERIC_NAMES.has(header.replace(/\s+/g, ''))) {
      return `表${index + 1}·${header}`
    }
  }
  return `表${index + 1}`
}

export function getTableTabLabel(table: any, index: number): string {
  const full = getTableTabFullName(table, index)
  return full.length > 14 ? `${full.slice(0, 14)}…` : full
}

export function isDisclosureTableEmpty(table: any, enabled: boolean): boolean {
  if (!enabled) return false
  return isEmptyTable(table?.rows as EmptyTableRow[], table?.columns as EmptyTableColumnDef[] ?? null)
}
