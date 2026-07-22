import type { G7DisclosureRow, G7DisclosureTable } from './g7ListedDisclosureModel'

export interface G7DisclosureLabeledSource {
  label: string
  source: string
}

export function uniqueRowSources(
  rows: G7DisclosureRow[],
): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const row of rows) {
    const source = String(row.source ?? '').trim()
    if (source && !seen.has(source)) {
      seen.add(source)
      out.push(source)
    }
  }
  return out
}

export function labeledRowSources(
  rows: G7DisclosureRow[],
): G7DisclosureLabeledSource[] {
  return rows
    .filter(row => row.kind === 'data' && String(row.source ?? '').trim())
    .map(row => ({
      label: String(row.label ?? '').trim() || '（未命名）',
      source: String(row.source ?? '').trim(),
    }))
}

/** 单一来源且行数不多时，表头 meta 标签即可；否则展示可折叠明细 */
export function showRowSourceDetail(rows: G7DisclosureRow[]): boolean {
  const labeled = labeledRowSources(rows)
  if (labeled.length === 0) return false
  const unique = uniqueRowSources(rows)
  return unique.length > 1 || labeled.length > 3
}

export function tableMetaSources(table: G7DisclosureTable, rows: G7DisclosureRow[]): {
  excel: string
  unique: string[]
  labeled: G7DisclosureLabeledSource[]
  showDetail: boolean
} {
  const labeled = labeledRowSources(rows)
  return {
    excel: table.sourceRows,
    unique: uniqueRowSources(rows),
    labeled,
    showDetail: showRowSourceDetail(rows),
  }
}
