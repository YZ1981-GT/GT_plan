/**
 * I6 审定表审计说明草稿（变动率超阈值自动生成）
 */
export interface I6AdjudicationNoteRow {
  类别: string
  上期审定: number
  本期审定: number
  变动额: number
  变动率: number | null
  changeRateHighlight?: boolean
}

const CHANGE_RATE_THRESHOLD_PCT = 30

function _fmtAmt(n: number): string {
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function _fmtRate(rate: number | null): string {
  if (rate == null) return '-'
  return (rate * 100).toFixed(1) + '%'
}

/** 筛选变动率超阈值的明细行（排除合计/控制行） */
export function pickI6HighChangeRateRows(
  rows: I6AdjudicationNoteRow[],
  thresholdPct = CHANGE_RATE_THRESHOLD_PCT,
): I6AdjudicationNoteRow[] {
  return rows.filter((r) => {
    if (r.changeRateHighlight) return true
    if (r.变动率 == null) return false
    return Math.abs(r.变动率 * 100) > thresholdPct
  })
}

/** 生成审计说明草稿（对齐 Excel「变动率超30%须说明主要原因」） */
export function buildI6AdjudicationAuditNoteDraft(
  rows: I6AdjudicationNoteRow[],
  options?: { thresholdPct?: number; existingNote?: string },
): string {
  const threshold = options?.thresholdPct ?? CHANGE_RATE_THRESHOLD_PCT
  const highlights = pickI6HighChangeRateRows(rows, threshold)
  if (!highlights.length) return ''

  const lines: string[] = [
    '1. 研发费用本期发生额较上期变动情况：',
    `本期审定合计 ${_fmtAmt(rows.reduce((s, r) => s + (r.本期审定 || 0), 0))} 元。`,
    '',
    '以下类别变动率超过30%，须说明主要原因：',
  ]

  for (const r of highlights) {
    const direction = r.变动额 >= 0 ? '增加' : '减少'
    lines.push(
      `·【${r.类别}】上期审定 ${_fmtAmt(r.上期审定)} 元，本期审定 ${_fmtAmt(r.本期审定)} 元，`
      + `${direction} ${_fmtAmt(Math.abs(r.变动额))} 元（变动率 ${_fmtRate(r.变动率)}）。`
      + '主要原因：__________',
    )
  }

  lines.push('', '2. 重大/异常事项：', '__________')

  const draft = lines.join('\n')
  const existing = (options?.existingNote || '').trim()
  if (!existing) return draft
  if (existing.includes('变动率超过30%') || existing.includes('变动率超30%')) return existing
  return `${existing}\n\n${draft}`
}

export function hasI6HighChangeRateRows(
  rows: I6AdjudicationNoteRow[],
  thresholdPct = CHANGE_RATE_THRESHOLD_PCT,
): boolean {
  return pickI6HighChangeRateRows(rows, thresholdPct).length > 0
}
