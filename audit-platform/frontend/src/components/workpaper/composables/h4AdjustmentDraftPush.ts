/**
 * H4-3 调整分录草稿推送 — 共用工具
 *
 * 各检查表（H4-4/5/6/7/9）生成借贷成对草稿，按 marker 幂等替换后写入 H4-3-rows。
 */
export const H43_ROWS_KEY = 'H4-3-rows'

export const H44_AJE_MARKER = 'H4-4-aje-auto'
export const H45_AJE_MARKER = 'H4-5-aje-auto'
export const H46_AJE_MARKER = 'H4-6-aje-auto'
export const H47_AJE_MARKER = 'H4-7-aje-auto'
export const H49_AJE_MARKER = 'H4-9-aje-auto'

export interface H43DraftLineInput {
  description: string
  amount: number
  debitCode: string
  debitName: string
  creditCode: string
  creditName: string
  indexRef: string
  marker: string
  reportItemDebit?: string
  reportItemCredit?: string
  noteItem?: string
  category?: '账项调整' | '报表调整' | '其他'
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _round2(n: number): number {
  return Math.round(n * 100) / 100
}

function _newId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

/** 解析 H4-3-rows 存档 */
export function parseH43Rows(raw: unknown): any[] {
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string' && raw) {
    try {
      const p = JSON.parse(raw)
      return Array.isArray(p) ? p : []
    } catch {
      return []
    }
  }
  return []
}

/** 生成借贷成对草稿行（账项调整） */
export function buildBalancedAjePair(
  input: H43DraftLineInput,
  seqStart: number,
): Array<Record<string, any>> {
  const amt = _round2(Math.abs(_num(input.amount)))
  if (amt < 0.005) return []
  const cat = input.category || '账项调整'
  const entryType = cat === '报表调整' ? 'RJE' : 'AJE'
  const baseId = _newId('h4-aje')
  const desc = (input.description || '拟调整').trim()
  return [
    {
      rowId: `${baseId}-dr`,
      seq: seqStart,
      description: desc,
      category: cat,
      entryType,
      reportItem: input.reportItemDebit || '',
      accountCode: input.debitCode,
      accountName: input.debitName,
      noteItem: input.noteItem || '',
      summary: desc,
      debitAmount: amt,
      creditAmount: 0,
      debit: amt,
      credit: 0,
      indexRef: input.indexRef,
      refIndex: input.indexRef,
      remark: input.marker,
    },
    {
      rowId: `${baseId}-cr`,
      seq: seqStart + 1,
      description: desc,
      category: cat,
      entryType,
      reportItem: input.reportItemCredit || '',
      accountCode: input.creditCode,
      accountName: input.creditName,
      noteItem: input.noteItem || '',
      summary: desc,
      debitAmount: 0,
      creditAmount: amt,
      debit: 0,
      credit: amt,
      indexRef: input.indexRef,
      refIndex: input.indexRef,
      remark: input.marker,
    },
  ]
}

/**
 * 按 marker 幂等合并：先移除同 marker 旧行，再追加 newRows，重排 seq。
 */
export function mergeH43DraftByMarker(existing: any[], marker: string, newRows: any[]): any[] {
  const kept = (existing || []).filter((r: any) => r?.remark !== marker)
  const merged = [...kept, ...newRows]
  return merged.map((r, i) => ({ ...r, seq: i + 1 }))
}

/** 从 allResponses 取 H4-3 行并合并写入 */
export function pushDraftPairsToH43(opts: {
  allResponses: Map<string, any>
  marker: string
  pairs: H43DraftLineInput[]
  onSave?: (itemId: string, value: any) => void
}): { ok: boolean; added: number; amount: number; message: string } {
  const { allResponses, marker, pairs, onSave } = opts
  const item = allResponses.get(H43_ROWS_KEY)
  const existing = parseH43Rows(item?.remark ?? item?.conclusion)
  const newRows: any[] = []
  let seq = existing.reduce((m: number, r: any) => Math.max(m, _num(r.seq)), 0) + 1
  let amount = 0
  for (const p of pairs) {
    const pair = buildBalancedAjePair(p, seq)
    if (!pair.length) continue
    newRows.push(...pair)
    seq += pair.length
    amount += Math.abs(_num(p.amount))
  }
  if (!newRows.length) {
    // 仍清理同 marker 旧草稿
    const cleaned = mergeH43DraftByMarker(existing, marker, [])
    if (cleaned.length !== existing.length) {
      onSave?.(H43_ROWS_KEY, cleaned)
      allResponses.set(H43_ROWS_KEY, {
        item_id: H43_ROWS_KEY,
        remark: JSON.stringify(cleaned),
        conclusion: null,
      })
    }
    return { ok: false, added: 0, amount: 0, message: '无可推送的拟调整事项' }
  }

  // 先去掉旧 marker，再追加（seq 以 kept 为准）
  const kept = existing.filter((r: any) => r?.remark !== marker)
  let seq2 = kept.reduce((m: number, r: any) => Math.max(m, _num(r.seq)), 0) + 1
  const renumbered = newRows.map((r) => {
    const copy = { ...r, seq: seq2 }
    seq2 += 1
    return copy
  })
  // 修复成对 seq
  for (let i = 0; i < renumbered.length; i += 2) {
    renumbered[i].seq = kept.length + i + 1
    if (renumbered[i + 1]) renumbered[i + 1].seq = kept.length + i + 2
  }
  const merged = mergeH43DraftByMarker(existing, marker, renumbered)
  onSave?.(H43_ROWS_KEY, merged)
  allResponses.set(H43_ROWS_KEY, {
    item_id: H43_ROWS_KEY,
    remark: JSON.stringify(merged),
    conclusion: null,
  })
  return {
    ok: true,
    added: renumbered.length,
    amount: _round2(amount),
    message: `已向 H4-3 推送 ${renumbered.length} 条草稿（合计 ${_round2(amount).toLocaleString('zh-CN', { maximumFractionDigits: 2 })}）`,
  }
}

/** 是否减值相关 1605 行（供 H4-1 分段回写） */
export function isImpairmentEmLine(row: {
  accountName?: string
  description?: string
  reportItem?: string
}): boolean {
  const blob = `${row.accountName || ''}${row.description || ''}${row.reportItem || ''}`
  return /减值/.test(blob)
}
