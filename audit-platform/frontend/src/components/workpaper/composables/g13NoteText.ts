/**
 * G13 附注披露 — 从分项行生成附注模块叙述（省略空行与模板提示语）
 */
import {
  G13_DISCLOSURE_LISTED_ROWS,
  G13_DISCLOSURE_SOE_ROWS,
  G13_DISCLOSURE_TEMPLATE_HINT,
  type G13DisclosureRowDef,
} from './g13Constants'
import {
  filterG13DisclosureRows,
  hasG13DisclosureAmount,
  type G13DisclosureAmountRow,
} from './g13DisclosureVisibility'

export function formatG13NoteAmount(value: number): string {
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export interface G13NoteTextRow extends G13DisclosureAmountRow {
  label: string
  remark?: string
}

export interface BuildG13NoteTextOptions {
  includeEmpty?: boolean
  adjudicatedAmount?: number | null
}

function defsFor(variant: 'listed' | 'soe'): readonly G13DisclosureRowDef[] {
  return variant === 'listed' ? G13_DISCLOSURE_LISTED_ROWS : G13_DISCLOSURE_SOE_ROWS
}

export function buildG13NoteTextFromRows(
  rows: readonly G13NoteTextRow[],
  variant: 'listed' | 'soe',
  opts?: BuildG13NoteTextOptions,
): string {
  const defs = defsFor(variant)
  const visible = filterG13DisclosureRows(rows, defs, { includeEmpty: opts?.includeEmpty })
  const defByKey = new Map(defs.map((d) => [d.rowKey, d]))

  const currentTotal = visible
    .filter((r) => !defByKey.get(r.rowKey)?.ofWhich)
    .reduce((s, r) => s + r.currentAmount, 0)
  const priorTotal = visible
    .filter((r) => !defByKey.get(r.rowKey)?.ofWhich)
    .reduce((s, r) => s + r.priorAmount, 0)

  const lines: string[] = [
    `公允价值变动收益本期发生额合计 ${formatG13NoteAmount(currentTotal)} 元，`
    + `上期发生额合计 ${formatG13NoteAmount(priorTotal)} 元。`,
  ]

  if (opts?.adjudicatedAmount != null && hasG13DisclosureAmount({
    currentAmount: opts.adjudicatedAmount,
    priorAmount: 0,
  })) {
    const diff = currentTotal - opts.adjudicatedAmount
    if (Math.abs(diff) < 0.005) {
      lines.push(`与 G13-1 审定数 ${formatG13NoteAmount(opts.adjudicatedAmount)} 元勾稽一致。`)
    } else {
      lines.push(
        `G13-1 审定数为 ${formatG13NoteAmount(opts.adjudicatedAmount)} 元，`
        + `与附注分项合计差异 ${formatG13NoteAmount(diff)} 元。`,
      )
    }
  }

  if (visible.length > 0) {
    lines.push('明细如下：')
    for (const row of visible) {
      const def = defByKey.get(row.rowKey)
      const label = (row.label || def?.label || row.rowKey).trim()
      const prefix = def?.ofWhich ? '  ' : ''
      lines.push(
        `${prefix}${label}：本期 ${formatG13NoteAmount(row.currentAmount)} 元，`
        + `上期 ${formatG13NoteAmount(row.priorAmount)} 元。`,
      )
    }
  }

  for (const row of visible) {
    const remark = String(row.remark ?? '').trim()
    if (!remark || remark.includes(G13_DISCLOSURE_TEMPLATE_HINT)) continue
    const label = (row.label || defByKey.get(row.rowKey)?.label || row.rowKey).trim()
    lines.push('')
    lines.push(`${label}说明：${remark}`)
  }

  return lines.join('\n').trim()
}
