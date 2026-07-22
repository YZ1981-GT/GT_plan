/**
 * H4-2 行级 AJE ↔ H4-3 分录 双向同步（纯函数）
 *
 * 推送：按明细行 ajeBegin/ajeIncrease/ajeDecrease/ajeImpair 生成借贷平衡草稿，
 *       remark 标记 H4-2-aje-auto，重复推送先清旧自动行。
 * 回写：解析自动行，按 detailRowId+kind 回填明细 AJE 字段。
 *
 * 对方科目默认（可在 H4-3 手工改）：
 *   期初调整 → 4104 以前年度损益调整
 *   本期增加 → 2202 应付账款
 *   本期减少 → 1604 在建工程
 *   减值     → 6701 资产减值损失（借）/ 1605 工程物资减值准备（贷）
 */
export const H42_AJE_MARKER = 'H4-2-aje-auto'

export type H42AjeKind = 'begin' | 'increase' | 'decrease' | 'impair'

export interface H42AjeDetailSource {
  rowId: string
  name?: string
  category?: string
  ajeBegin?: number
  ajeIncrease?: number
  ajeDecrease?: number
  ajeImpair?: number
}

export interface H42AjeAdjDraft {
  rowId: string
  seq: number
  description: string
  category: '账项调整'
  entryType: 'AJE'
  reportItem: string
  accountCode: string
  accountName: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
  summary: string
}

const KIND_META: Record<
  H42AjeKind,
  { label: string; counterpart: { code: string; name: string; reportItem: string } }
> = {
  begin: {
    label: '期初',
    counterpart: { code: '4104', name: '以前年度损益调整', reportItem: '未分配利润' },
  },
  increase: {
    label: '本期增加',
    counterpart: { code: '2202', name: '应付账款', reportItem: '应付账款' },
  },
  decrease: {
    label: '本期减少',
    counterpart: { code: '1604', name: '在建工程', reportItem: '在建工程' },
  },
  impair: {
    label: '减值',
    counterpart: { code: '6701', name: '资产减值损失', reportItem: '资产减值损失' },
  },
}

function _n(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _round2(n: number): number {
  return Math.round(n * 100) / 100
}

export function encodeH42AjeRemark(detailRowId: string, kind: H42AjeKind): string {
  return `${H42_AJE_MARKER}|detail=${detailRowId}|kind=${kind}`
}

export function parseH42AjeRemark(
  remark: unknown,
): { detailRowId: string; kind: H42AjeKind } | null {
  const s = String(remark ?? '')
  if (!s.includes(H42_AJE_MARKER)) return null
  const detail = /(?:^|\|)detail=([^|]+)/.exec(s)?.[1]?.trim()
  const kind = /(?:^|\|)kind=([^|]+)/.exec(s)?.[1]?.trim() as H42AjeKind | undefined
  if (!detail || !kind || !(kind in KIND_META)) return null
  return { detailRowId: detail, kind }
}

export function isH42AjeAutoRow(row: { remark?: string } | null | undefined): boolean {
  return String(row?.remark ?? '').includes(H42_AJE_MARKER)
}

/** 1605 侧对资产原值/减值的净影响（借−贷）；减值贷方增加准备时净影响为负 */
export function emSideSignedAmount(
  kind: H42AjeKind,
  ajeAmount: number,
): { debit: number; credit: number } {
  const amt = _round2(Math.abs(ajeAmount))
  if (amt < 0.005) return { debit: 0, credit: 0 }

  if (kind === 'impair') {
    // 补提减值：借 6701 / 贷 1605；冲回则相反
    return ajeAmount >= 0
      ? { debit: 0, credit: amt }
      : { debit: amt, credit: 0 }
  }
  if (kind === 'decrease') {
    // 调增减少：贷 1605；调减减少：借 1605
    return ajeAmount >= 0
      ? { debit: 0, credit: amt }
      : { debit: amt, credit: 0 }
  }
  // begin / increase：调增资产借 1605
  return ajeAmount >= 0
    ? { debit: amt, credit: 0 }
    : { debit: 0, credit: amt }
}

function _counterpartSide(
  kind: H42AjeKind,
  em: { debit: number; credit: number },
): { debit: number; credit: number } {
  // 对方科目与 1605 相反，保证成对平衡
  return { debit: em.credit, credit: em.debit }
}

export function buildH42AjePairsForRow(
  row: H42AjeDetailSource,
  seqStart: number,
): H42AjeAdjDraft[] {
  const name = String(row.name || '工程物资').trim() || '工程物资'
  const detailId = String(row.rowId || '').trim()
  if (!detailId) return []

  const fields: Array<{ kind: H42AjeKind; amount: number }> = [
    { kind: 'begin', amount: _n(row.ajeBegin) },
    { kind: 'increase', amount: _n(row.ajeIncrease) },
    { kind: 'decrease', amount: _n(row.ajeDecrease) },
    { kind: 'impair', amount: _n(row.ajeImpair) },
  ]

  const out: H42AjeAdjDraft[] = []
  let seq = seqStart
  for (const { kind, amount } of fields) {
    if (Math.abs(amount) < 0.005) continue
    const meta = KIND_META[kind]
    const desc = `H4-2明细调整-${meta.label}-${name}`
    const remark = encodeH42AjeRemark(detailId, kind)
    const em = emSideSignedAmount(kind, amount)
    const cp = _counterpartSide(kind, em)
    const baseId = `h42aje-${detailId}-${kind}`

    // 1605 行
    out.push({
      rowId: `${baseId}-1605`,
      seq: seq++,
      description: desc,
      category: '账项调整',
      entryType: 'AJE',
      reportItem: kind === 'impair' ? '工程物资' : '工程物资',
      accountCode: '1605',
      accountName: kind === 'impair' ? '工程物资减值准备' : '工程物资',
      noteItem: '',
      debitAmount: em.debit,
      creditAmount: em.credit,
      indexRef: 'H4-2',
      remark,
      summary: desc,
    })

    // 对方科目行
    out.push({
      rowId: `${baseId}-cp`,
      seq: seq++,
      description: desc,
      category: '账项调整',
      entryType: 'AJE',
      reportItem: meta.counterpart.reportItem,
      accountCode: meta.counterpart.code,
      accountName: meta.counterpart.name,
      noteItem: '',
      debitAmount: cp.debit,
      creditAmount: cp.credit,
      indexRef: 'H4-2',
      remark,
      summary: desc,
    })
  }
  return out
}

export function mergeH42AjeIntoH43(
  existingH43: any[],
  detailRows: H42AjeDetailSource[],
): { rows: any[]; added: number; cleared: number } {
  const keep = (Array.isArray(existingH43) ? existingH43 : []).filter((r) => !isH42AjeAutoRow(r))
  const cleared = (Array.isArray(existingH43) ? existingH43 : []).length - keep.length

  let seq = keep.reduce((m, r) => Math.max(m, _n(r.seq)), 0) + 1
  const created: H42AjeAdjDraft[] = []
  for (const d of detailRows) {
    const pairs = buildH42AjePairsForRow(d, seq)
    created.push(...pairs)
    seq += pairs.length
  }

  const merged = [...keep, ...created].map((r, i) => ({ ...r, seq: i + 1 }))
  return { rows: merged, added: created.length, cleared }
}

/**
 * 从 H4-3 自动行回写明细 AJE。
 * 仅处理带 H4-2-aje-auto 标记且科目为 1605 的行（避免对方科目重复计入）。
 */
export function applyH43AjeBackToDetails<T extends H42AjeDetailSource>(
  detailRows: T[],
  h43Rows: any[],
): { rows: T[]; updated: number; matchedLines: number } {
  const buckets = new Map<string, { begin: number; increase: number; decrease: number; impair: number }>()

  let matchedLines = 0
  for (const r of Array.isArray(h43Rows) ? h43Rows : []) {
    const parsed = parseH42AjeRemark(r?.remark)
    if (!parsed) continue
    const code = String(r.accountCode ?? '').trim()
    if (code !== '1605' && !code.startsWith('1605')) continue

    const debit = _n(r.debitAmount ?? r.debit)
    const credit = _n(r.creditAmount ?? r.credit)
    matchedLines++

    const cur = buckets.get(parsed.detailRowId) ?? {
      begin: 0, increase: 0, decrease: 0, impair: 0,
    }

    // 反解 emSideSignedAmount
    if (parsed.kind === 'impair') {
      cur.impair += credit - debit
    } else if (parsed.kind === 'decrease') {
      cur.decrease += credit - debit
    } else if (parsed.kind === 'begin') {
      cur.begin += debit - credit
    } else {
      cur.increase += debit - credit
    }
    buckets.set(parsed.detailRowId, cur)
  }

  let updated = 0
  const rows = detailRows.map((d) => {
    const id = String(d.rowId || '')
    const b = buckets.get(id)
    if (!b) {
      // 若该行曾有自动 AJE 但 H4-3 已删光，不清空手工值——仅当 remark 曾匹配才更新
      return d
    }
    const next = {
      ...d,
      ajeBegin: _round2(b.begin),
      ajeIncrease: _round2(b.increase),
      ajeDecrease: _round2(b.decrease),
      ajeImpair: _round2(b.impair),
    }
    if (
      _round2(_n(d.ajeBegin)) !== next.ajeBegin
      || _round2(_n(d.ajeIncrease)) !== next.ajeIncrease
      || _round2(_n(d.ajeDecrease)) !== next.ajeDecrease
      || _round2(_n(d.ajeImpair)) !== next.ajeImpair
    ) {
      updated++
    }
    return next
  })

  return { rows, updated, matchedLines }
}

/** 汇总明细侧 AJE 净影响（原值口径：begin+inc−dec；不含减值） */
export function sumDetailCostAjeNet(detailRows: H42AjeDetailSource[]): number {
  let net = 0
  for (const r of detailRows) {
    net += _n(r.ajeBegin) + _n(r.ajeIncrease) - _n(r.ajeDecrease)
  }
  return _round2(net)
}

export function sumDetailImpairAje(detailRows: H42AjeDetailSource[]): number {
  return _round2(detailRows.reduce((s, r) => s + _n(r.ajeImpair), 0))
}
