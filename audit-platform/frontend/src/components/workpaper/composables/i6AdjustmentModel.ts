/**
 * i6AdjustmentModel — I6-3 调整分录 → I6-1 审定表 AJE/RJE 分摊逻辑
 */
import type { I6AdjudicationRow } from './useI6Adjudication'

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _round2(v: number): number {
  return Math.round(v * 100) / 100
}

function _str(v: unknown): string {
  return String(v ?? '').trim()
}

/** I6-2 / 附注项目别名 → I6-1 审定类别 */
export const I6_ADJ_CATEGORY_ALIASES: Record<string, string[]> = {
  人员人工费用: ['人工费', '人工', '职工薪酬', '工资'],
  直接投入费用: ['材料费', '材料', '直接投入'],
  折旧费用与长期待摊费用: ['制造费用分摊', '折旧', '长期待摊'],
  无形资产摊销费用: ['无形资产摊销', '摊销'],
  设计费用: ['设计费', '设计'],
  装备调试费用与试验费用: ['装备调试费', '调试费', '试验费'],
  委托外部研究开发费用: ['委外研发费', '委外', '委托外部'],
  其他费用: ['其他'],
}

export function isI6ExpenseAccount(code: string, name?: string): boolean {
  const c = String(code || '')
  const n = String(name || '')
  return c.startsWith('6602') || c.startsWith('5301') || c.startsWith('5602')
    || n.includes('研发费用') || n.includes('研发支出')
}

export function entryTypeFromCategory(category: string): 'AJE' | 'RJE' {
  return category === '报表调整' ? 'RJE' : 'AJE'
}

export function categoryFromLegacy(raw: { category?: string; entryType?: string }): string {
  const cat = _str(raw.category)
  if (cat === '报表调整' || cat === '账项调整' || cat === '其他') return cat
  if (cat === 'RJE' || cat === '重分类调整') return '报表调整'
  if (cat === 'AJE' || cat === '账项调整') return '账项调整'
  const et = _str(raw.entryType).toUpperCase()
  if (et === 'RJE') return '报表调整'
  return '账项调整'
}

function resolveAdjudicationCategory(noteItem: string, adjudicationNames: string[]): string | null {
  const hint = _str(noteItem)
  if (!hint) return null
  for (const name of adjudicationNames) {
    if (hint === name || hint.includes(name) || name.includes(hint)) return name
    const aliases = I6_ADJ_CATEGORY_ALIASES[name] || []
    if (aliases.some((a) => hint.includes(a) || a.includes(hint))) return name
  }
  return null
}

function allocateByUnadj(
  rows: I6AdjudicationRow[],
  ajeRem: number,
  rjeRem: number,
): I6AdjudicationRow[] {
  const base = rows.map((r) => Math.abs(_num(r.本期未审)))
  const sum = base.reduce((a, b) => a + b, 0)
  if (sum <= 0) {
    if (rows.length === 1) {
      return rows.map((r) => ({
        ...r,
        本期AJE: _round2(r.本期AJE + ajeRem),
        本期RJE: _round2(r.本期RJE + rjeRem),
      }))
    }
    return rows
  }
  let ajeLeft = ajeRem
  let rjeLeft = rjeRem
  return rows.map((r, i) => {
    const isLast = i === rows.length - 1
    const ajeAdd = isLast ? ajeLeft : _round2(ajeRem * base[i] / sum)
    const rjeAdd = isLast ? rjeLeft : _round2(rjeRem * base[i] / sum)
    ajeLeft = _round2(ajeLeft - ajeAdd)
    rjeLeft = _round2(rjeLeft - rjeAdd)
    return {
      ...r,
      本期AJE: _round2(r.本期AJE + ajeAdd),
      本期RJE: _round2(r.本期RJE + rjeAdd),
    }
  })
}

/** 从 I6-3 分录行汇总 6602 净额并写入 I6-1 各行 AJE/RJE */
export function applyAjeFromI63(
  rows: I6AdjudicationRow[],
  adjRows: any[],
): {
  rows: I6AdjudicationRow[]
  applied: number
  approx: boolean
  totalAje: number
  totalRje: number
  matchedByName: number
} {
  let totalAje = 0
  let totalRje = 0
  const namedAje = new Map<string, number>()
  const namedRje = new Map<string, number>()
  const adjudicationNames = rows.filter((r) => r.类别 !== '合  计').map((r) => r.类别)

  for (const line of adjRows || []) {
    const code = _str(line?.accountCode)
    const name = _str(line?.accountName)
    if (!isI6ExpenseAccount(code, name)) continue
    const debit = _num(line?.debitAmount ?? line?.debit)
    const credit = _num(line?.creditAmount ?? line?.credit)
    const net = _round2(debit - credit)
    const cat = categoryFromLegacy(line)
    const et = entryTypeFromCategory(cat)
    const matchName = resolveAdjudicationCategory(
      _str(line?.noteItem || line?.expenseCategory || line?.remark),
      adjudicationNames,
    )
    if (et === 'RJE') {
      totalRje = _round2(totalRje + net)
      if (matchName) namedRje.set(matchName, _round2((namedRje.get(matchName) || 0) + net))
    } else {
      totalAje = _round2(totalAje + net)
      if (matchName) namedAje.set(matchName, _round2((namedAje.get(matchName) || 0) + net))
    }
  }

  if ((Math.abs(totalAje) < 0.005 && Math.abs(totalRje) < 0.005) || !rows.length) {
    return { rows, applied: 0, approx: false, totalAje, totalRje, matchedByName: 0 }
  }

  const next = rows
    .filter((r) => r.类别 !== '合  计')
    .map((r) => ({ ...r, 本期AJE: 0, 本期RJE: 0 }))
  let matchedByName = 0
  let ajeNamed = 0
  let rjeNamed = 0

  for (const row of next) {
    const aje = namedAje.get(row.类别)
    if (aje != null && Math.abs(aje) > 0.005) {
      row.本期AJE = aje
      ajeNamed = _round2(ajeNamed + aje)
      matchedByName++
    }
    const rje = namedRje.get(row.类别)
    if (rje != null && Math.abs(rje) > 0.005) {
      row.本期RJE = rje
      rjeNamed = _round2(rjeNamed + rje)
      matchedByName++
    }
  }

  const ajeRem = _round2(totalAje - ajeNamed)
  const rjeRem = _round2(totalRje - rjeNamed)
  let approx = false
  let applied = matchedByName

  if (Math.abs(ajeRem) > 0.005 || Math.abs(rjeRem) > 0.005) {
    approx = true
    const allocated = allocateByUnadj(next, ajeRem, rjeRem)
    return {
      rows: allocated,
      applied: applied || allocated.length,
      approx,
      totalAje,
      totalRje,
      matchedByName,
    }
  }

  return { rows: next, applied, approx, totalAje, totalRje, matchedByName }
}

/** 构建 I6-1 回写用的 adjustments 数组 */
export function buildI63WritebackAdjustments(
  adjudicationRows: I6AdjudicationRow[],
): Array<{ 类别: string; AJE: number; RJE: number }> {
  return adjudicationRows
    .filter((r) => r.类别 && r.类别 !== '合  计')
    .map((r) => ({ 类别: r.类别, AJE: _num(r.本期AJE), RJE: _num(r.本期RJE) }))
}

export interface I62DetailAjeRow {
  id: string
  category: string
  expenseNature?: string
  aje: number
  rje: number
  priorUnadj?: number
}

function resolveDetailCategory(
  hint: string,
  detailRows: Array<{ category: string; expenseNature?: string }>,
): string | null {
  const h = _str(hint)
  if (!h) return null
  for (const r of detailRows) {
    const cat = _str(r.expenseNature || r.category)
    if (!cat) continue
    if (h === cat || h.includes(cat) || cat.includes(h)) return cat
    for (const [, aliases] of Object.entries(I6_ADJ_CATEGORY_ALIASES)) {
      const hitAlias = aliases.some((a) => cat.includes(a) || a.includes(cat))
      if (hitAlias && (aliases.some((a) => h.includes(a)) || h.includes(cat))) return cat
    }
  }
  for (const [adjName, aliases] of Object.entries(I6_ADJ_CATEGORY_ALIASES)) {
    if (!h.includes(adjName) && !aliases.some((a) => h.includes(a))) continue
    for (const r of detailRows) {
      const cat = _str(r.expenseNature || r.category)
      if (aliases.some((a) => cat.includes(a) || a.includes(cat))) return cat
    }
  }
  return null
}

/** 从 I6-3 分录汇总 6602 净额并写入 I6-2 各行 AJE/RJE */
export function applyAjeToI62Detail<T extends I62DetailAjeRow>(
  detailRows: T[],
  adjRows: any[],
): {
  rows: T[]
  applied: number
  approx: boolean
  totalAje: number
  totalRje: number
  matchedByName: number
} {
  let totalAje = 0
  let totalRje = 0
  const namedAje = new Map<string, number>()
  const namedRje = new Map<string, number>()

  for (const line of adjRows || []) {
    const code = _str(line?.accountCode)
    const name = _str(line?.accountName)
    if (!isI6ExpenseAccount(code, name)) continue
    const debit = _num(line?.debitAmount ?? line?.debit)
    const credit = _num(line?.creditAmount ?? line?.credit)
    const net = _round2(debit - credit)
    const cat = categoryFromLegacy(line)
    const et = entryTypeFromCategory(cat)
    const matchKey = resolveDetailCategory(
      _str(line?.noteItem || line?.expenseCategory || line?.remark),
      detailRows,
    )
    if (et === 'RJE') {
      totalRje = _round2(totalRje + net)
      if (matchKey) namedRje.set(matchKey, _round2((namedRje.get(matchKey) || 0) + net))
    } else {
      totalAje = _round2(totalAje + net)
      if (matchKey) namedAje.set(matchKey, _round2((namedAje.get(matchKey) || 0) + net))
    }
  }

  if ((Math.abs(totalAje) < 0.005 && Math.abs(totalRje) < 0.005) || !detailRows.length) {
    return { rows: detailRows, applied: 0, approx: false, totalAje, totalRje, matchedByName: 0 }
  }

  const next = detailRows.map((r) => ({ ...r, aje: 0, rje: 0 }))
  let matchedByName = 0
  let ajeNamed = 0
  let rjeNamed = 0

  for (const row of next) {
    const key = _str(row.expenseNature || row.category)
    const aje = namedAje.get(key)
    if (aje != null && Math.abs(aje) > 0.005) {
      row.aje = aje
      ajeNamed = _round2(ajeNamed + aje)
      matchedByName++
    }
    const rje = namedRje.get(key)
    if (rje != null && Math.abs(rje) > 0.005) {
      row.rje = rje
      rjeNamed = _round2(rjeNamed + rje)
      matchedByName++
    }
  }

  const ajeRem = _round2(totalAje - ajeNamed)
  const rjeRem = _round2(totalRje - rjeNamed)
  if (Math.abs(ajeRem) > 0.005 || Math.abs(rjeRem) > 0.005) {
    const base = next.map((r) => Math.abs(_num(r.priorUnadj)))
    const sum = base.reduce((a, b) => a + b, 0) || next.reduce((s, r) => s + Math.abs(_num((r as any).unadjTotal)), 0)
    if (sum > 0) {
      let ajeLeft = ajeRem
      let rjeLeft = rjeRem
      for (let i = 0; i < next.length; i++) {
        const isLast = i === next.length - 1
        const weight = sum > 0 ? (Math.abs(_num(next[i].priorUnadj)) || 1) / sum : 1 / next.length
        const ajeAdd = isLast ? ajeLeft : _round2(ajeRem * weight)
        const rjeAdd = isLast ? rjeLeft : _round2(rjeRem * weight)
        next[i].aje = _round2(next[i].aje + ajeAdd)
        next[i].rje = _round2(next[i].rje + rjeAdd)
        ajeLeft = _round2(ajeLeft - ajeAdd)
        rjeLeft = _round2(rjeLeft - rjeAdd)
      }
    } else if (next.length === 1) {
      next[0].aje = _round2(next[0].aje + ajeRem)
      next[0].rje = _round2(next[0].rje + rjeRem)
    }
    return {
      rows: next,
      applied: matchedByName || next.length,
      approx: true,
      totalAje,
      totalRje,
      matchedByName,
    }
  }

  return { rows: next, applied: matchedByName, approx: false, totalAje, totalRje, matchedByName }
}

/** 汇总 I6-3 中 6602 行的 AJE/RJE 净额（用于与 I6-2 勾稽） */
export function aggregateI63Nets(adjRows: any[]): { ajeNet: number; rjeNet: number } {
  let ajeNet = 0
  let rjeNet = 0
  for (const line of adjRows || []) {
    if (!isI6ExpenseAccount(_str(line?.accountCode), _str(line?.accountName))) continue
    const net = _round2(_num(line?.debitAmount ?? line?.debit) - _num(line?.creditAmount ?? line?.credit))
    const et = entryTypeFromCategory(categoryFromLegacy(line))
    if (et === 'RJE') rjeNet = _round2(rjeNet + net)
    else ajeNet = _round2(ajeNet + net)
  }
  return { ajeNet, rjeNet }
}

function _appendBalancedI63Pair(
  drafts: any[],
  opts: {
    nature: string
    signedAmount: number
    category: '账项调整' | '报表调整'
    entryType: 'AJE' | 'RJE'
    ts: number
  },
): void {
  const abs = Math.abs(opts.signedAmount)
  if (abs < 0.005) return
  const desc = opts.category === '报表调整'
    ? `明细表重分类-${opts.nature}`
    : `明细表调整-${opts.nature}`
  const increaseExpense = opts.signedAmount > 0
  drafts.push(
    {
      rowId: `i63-from-i62-${opts.entryType.toLowerCase()}-${opts.ts}-${drafts.length}`,
      description: desc,
      category: opts.category,
      entryType: opts.entryType,
      reportItem: '研发费用',
      accountCode: '6602',
      accountName: '研发费用',
      noteItem: opts.nature,
      debitAmount: increaseExpense ? abs : 0,
      creditAmount: increaseExpense ? 0 : abs,
      indexRef: 'I6-2',
      remark: `来源:I6-2明细${opts.entryType}`,
    },
    {
      rowId: `i63-from-i62-${opts.entryType.toLowerCase()}-c-${opts.ts}-${drafts.length}`,
      description: desc,
      category: opts.category,
      entryType: opts.entryType,
      reportItem: '其他应付款',
      accountCode: '2241',
      accountName: '其他应付款',
      noteItem: opts.nature,
      debitAmount: increaseExpense ? 0 : abs,
      creditAmount: increaseExpense ? abs : 0,
      indexRef: 'I6-2',
      remark: '对方科目（请按实际业务替换）',
    },
  )
}

/** 自 I6-2 明细行生成 I6-3 平衡借贷分录对 */
export function buildI63DraftsFromDetail(
  detailRows: Array<{ category: string; expenseNature?: string; aje: number; rje: number }>,
): any[] {
  const drafts: any[] = []
  const ts = Date.now()
  for (const row of detailRows) {
    const nature = _str(row.expenseNature || row.category)
    if (!nature) continue
    if (Math.abs(row.aje) > 0.005) {
      _appendBalancedI63Pair(drafts, {
        nature,
        signedAmount: row.aje,
        category: '账项调整',
        entryType: 'AJE',
        ts,
      })
    }
    if (Math.abs(row.rje) > 0.005) {
      _appendBalancedI63Pair(drafts, {
        nature,
        signedAmount: row.rje,
        category: '报表调整',
        entryType: 'RJE',
        ts,
      })
    }
  }
  return drafts
}
