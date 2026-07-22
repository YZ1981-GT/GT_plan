/**
 * G14 附注披露 — 从分项行生成附注模块叙述（省略空行）
 */
import {
  G14_DISCLOSURE_LISTED_ROWS,
  G14_DISCLOSURE_SOE_ROWS,
} from './g14Constants'
import {
  filterG14DisclosureRows,
  hasG14DisclosureAmount,
  type G14DisclosureAmountRow,
} from './g14DisclosureVisibility'

export function formatG14NoteAmount(value: number): string {
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export interface G14NoteTextRow extends G14DisclosureAmountRow {
  label: string
  remark?: string
}

export interface BuildG14NoteTextOptions {
  includeEmpty?: boolean
  adjudicatedAmount?: number | null
}

function defsFor(variant: 'listed' | 'soe') {
  return variant === 'listed' ? G14_DISCLOSURE_LISTED_ROWS : G14_DISCLOSURE_SOE_ROWS
}

export function buildG14NoteTextFromRows(
  rows: readonly G14NoteTextRow[],
  variant: 'listed' | 'soe',
  opts?: BuildG14NoteTextOptions,
): string {
  const defs = defsFor(variant)
  const defByKey = new Map(defs.map((d) => [d.rowKey, d]))
  const visible = filterG14DisclosureRows(rows, { includeEmpty: opts?.includeEmpty })

  const currentTotal = visible.reduce((s, r) => s + r.currentAmount, 0)
  const priorTotal = visible.reduce((s, r) => s + r.priorAmount, 0)

  const lines: string[] = [
    `信用减值损失本期发生额合计 ${formatG14NoteAmount(currentTotal)} 元，`
    + `上期发生额合计 ${formatG14NoteAmount(priorTotal)} 元（损失以「—」号填列）。`,
  ]

  if (opts?.adjudicatedAmount != null && hasG14DisclosureAmount({
    currentAmount: opts.adjudicatedAmount,
    priorAmount: 0,
  })) {
    const diff = currentTotal - opts.adjudicatedAmount
    if (Math.abs(diff) < 0.005) {
      lines.push(`与 G14-1 审定数 ${formatG14NoteAmount(opts.adjudicatedAmount)} 元勾稽一致。`)
    } else {
      lines.push(
        `G14-1 审定数为 ${formatG14NoteAmount(opts.adjudicatedAmount)} 元，`
        + `与附注分项合计差异 ${formatG14NoteAmount(diff)} 元。`,
      )
    }
  }

  if (visible.length > 0) {
    lines.push('明细如下：')
    for (const row of visible) {
      const label = (row.label || defByKey.get(row.rowKey)?.label || row.rowKey).trim()
      lines.push(
        `${label}：本期 ${formatG14NoteAmount(row.currentAmount)} 元，`
        + `上期 ${formatG14NoteAmount(row.priorAmount)} 元。`,
      )
    }
  }

  for (const row of visible) {
    const remark = String(row.remark ?? '').trim()
    if (!remark) continue
    const label = (row.label || defByKey.get(row.rowKey)?.label || row.rowKey).trim()
    lines.push('')
    lines.push(`${label}说明：${remark}`)
  }

  return lines.join('\n').trim()
}
