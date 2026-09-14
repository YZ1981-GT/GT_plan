/**
 * H1 固定资产分类映射（TB 子科目名 / 调整分录科目 → 审定表五类）
 * 供 H1-1 预填、H1-3 分摊、前后端共用口径。
 */

export const H1_FA_CATEGORIES = [
  '房屋及建筑物',
  '机器设备',
  '运输设备',
  '办公设备',
  '其他设备',
] as const

export type H1FaCategory = (typeof H1_FA_CATEGORIES)[number]

export type H1FaBlock = 'cost' | 'dep' | 'impair'

/** 科目前缀 → 审定区块 */
export function classifyFaBlock(accountCode: string): H1FaBlock | null {
  const code = String(accountCode || '').trim().replace(/\s/g, '')
  if (!code) return null
  // 1601/1602/1603 互斥前缀（含 1601.01、160101 等子码）
  if (code.startsWith('1601')) return 'cost'
  if (code.startsWith('1602')) return 'dep'
  if (code.startsWith('1603')) return 'impair'
  return null
}

/**
 * 由科目名称 / 附注 / 摘要等文本映射到五类。
 * 未命中返回 null（调用方再决定是否归入「其他设备」）。
 * 关键词按特异性排序：房屋 → 运输 → 办公/电子 → 机器 → 显式其他。
 * 办公在机器之前判断，避免「办公设备」被「设备」误归机器。
 */
export function classifyFaCategory(...texts: Array<string | null | undefined>): H1FaCategory | null {
  const s = texts.filter(Boolean).join(' ').replace(/\s+/g, '')
  if (!s) return null
  if (/房屋|建筑|厂房|仓库|构筑物|不动产|房产|土地/.test(s)) return '房屋及建筑物'
  if (/运输|车辆|汽车|客车|货车|专用车|挂车|叉车|拖拉机|船舶|飞机|机动车/.test(s)) return '运输设备'
  if (/办公|电子设备|电脑|计算机|打印|复印|服务器|网络|监控|摄像|空调|家具|器具/.test(s)) return '办公设备'
  if (/机器|机械|生产|生产线|流水线|机组|专用设备|通用设备|锅炉|电机|装置|仪器|仪表/.test(s) && !/办公|电子|运输/.test(s)) {
    return '机器设备'
  }
  if (/其他|未分类|低值/.test(s)) return '其他设备'
  // 泛化设备/机床/工具 → 机器设备（同后端逻辑）
  if (/设备|机床|工具/.test(s)) return '机器设备'
  return null
}

/** 分类名归一（电子设备→办公设备；裸「其他/未分类」→其他设备） */
export function normalizeFaCategory(name: string): H1FaCategory | string {
  const n = String(name || '').trim()
  if (n === '电子设备') return '办公设备'
  if (n === '其他' || n === '未分类') return '其他设备'
  const hit = classifyFaCategory(n)
  if (hit) return hit
  if ((H1_FA_CATEGORIES as readonly string[]).includes(n)) return n
  return n || '其他设备'
}

/** 审定五类 → 上市附注列 label（国有企业「房屋、建筑物」等另表映射） */
export function toListedDisclosureCategoryLabel(name: string): string {
  const n = normalizeFaCategory(name)
  if (n === '其他设备') return '其他设备'
  return String(n)
}

/** 审定五类 → 国企附注 shortLabel */
export function toSoeDisclosureCategoryLabel(name: string): string {
  const n = String(name || '').trim()
  if (n === '房屋及建筑物' || n === '房屋、建筑物') return '房屋、建筑物'
  if (n === '运输设备' || n === '运输工具') return '运输工具'
  if (n === '办公设备' || n === '电子设备') return '电子设备'
  if (n === '其他设备' || n === '其他') return '其他'
  return n || '其他'
}

/** TB 子科目一行 → 分类（优先名称，其次代码段启发式） */
export function classifyTbFaRow(accountCode: string, accountName: string): H1FaCategory {
  const byName = classifyFaCategory(accountName)
  if (byName) return byName

  // 常见二级码约定：01房屋 02机器 03运输 04办公/电子 05其他
  const m = String(accountCode || '').match(/^160[123][.\-]?0?([1-5])/)
  if (m) {
    const map: Record<string, H1FaCategory> = {
      '1': '房屋及建筑物',
      '2': '机器设备',
      '3': '运输设备',
      '4': '办公设备',
      '5': '其他设备',
    }
    return map[m[1]] || '其他设备'
  }
  return '其他设备'
}

/** 单分类预填金额 */
export interface H1CategoryPrefillAmounts {
  begin: number
  debit: number
  credit: number
  end: number
  unadjusted: number
}

export interface H1CategoryPrefillRow {
  category: H1FaCategory | string
  cost: H1CategoryPrefillAmounts
  dep: H1CategoryPrefillAmounts
  impair: H1CategoryPrefillAmounts
}

export interface H1CategoryPrefillPayload {
  categories: H1CategoryPrefillRow[]
  totals: { cost1601: number; dep1602: number; impair1603: number }
}

function _emptyAmt(): H1CategoryPrefillAmounts {
  return { begin: 0, debit: 0, credit: 0, end: 0, unadjusted: 0 }
}

/** 将后端/扁平 TB 行聚合成按分类预填包 */
export function aggregateTbRowsToCategoryPrefill(
  rows: Array<{
    account_code?: string
    accountCode?: string
    account_name?: string
    accountName?: string
    opening_balance?: number
    openingBalance?: number
    closing_balance?: number
    closingBalance?: number
    debit_amount?: number
    debitAmount?: number
    credit_amount?: number
    creditAmount?: number
  }>,
): H1CategoryPrefillPayload {
  const map = new Map<string, H1CategoryPrefillRow>()
  const ensure = (cat: string): H1CategoryPrefillRow => {
    let row = map.get(cat)
    if (!row) {
      row = { category: cat, cost: _emptyAmt(), dep: _emptyAmt(), impair: _emptyAmt() }
      map.set(cat, row)
    }
    return row
  }

  for (const r of rows) {
    const code = String(r.account_code ?? r.accountCode ?? '').trim()
    const name = String(r.account_name ?? r.accountName ?? '').trim()
    const block = classifyFaBlock(code)
    if (!block) continue
    const cat = classifyTbFaRow(code, name)
    const target = ensure(cat)[block]
    const begin = Number(r.opening_balance ?? r.openingBalance ?? 0) || 0
    const end = Number(r.closing_balance ?? r.closingBalance ?? 0) || 0
    const debit = Number(r.debit_amount ?? r.debitAmount ?? 0) || 0
    const credit = Number(r.credit_amount ?? r.creditAmount ?? 0) || 0
    // 备抵科目余额在 TB 中可能为贷方正数或借方负数，统一取绝对值计入备抵余额口径
    const beginAbs = block === 'cost' ? begin : Math.abs(begin)
    const endAbs = block === 'cost' ? end : Math.abs(end)
    target.begin += beginAbs
    target.debit += debit
    target.credit += credit
    target.end += endAbs
    target.unadjusted += endAbs
  }

  // 保证五类齐全
  for (const cat of H1_FA_CATEGORIES) ensure(cat)

  const categories = H1_FA_CATEGORIES.map((c) => map.get(c)!)
  const sumUnadj = (key: 'cost' | 'dep' | 'impair') =>
    categories.reduce((s, r) => s + r[key].unadjusted, 0)

  return {
    categories,
    totals: {
      cost1601: sumUnadj('cost'),
      dep1602: sumUnadj('dep'),
      impair1603: sumUnadj('impair'),
    },
  }
}

/** H1-3 分录 → 按区块×分类累计的 AJE/RJE */
export interface H1AdjAllocation {
  cost: Record<string, { aje: number; rje: number }>
  dep: Record<string, { aje: number; rje: number }>
  impair: Record<string, { aje: number; rje: number }>
  skipped: number
  applied: number
}

function _emptyCatMap(): Record<string, { aje: number; rje: number }> {
  const m: Record<string, { aje: number; rje: number }> = {}
  for (const c of H1_FA_CATEGORIES) m[c] = { aje: 0, rje: 0 }
  return m
}

/**
 * 按科目码分摊 H1-3：
 * - 1601 净额 = 借 − 贷（资产增加为正）
 * - 1602/1603 净额 = 贷 − 借（备抵增加为正）
 * - 类别：账项/其他→AJE，报表→RJE
 * - 分类：科目名/附注/说明/报表项目关键词，未命中→其他设备
 */
export function allocateH3AdjustmentsByAccount(
  rows: Array<{
    accountCode?: string
    accountName?: string
    category?: string
    entryType?: string
    noteItem?: string
    description?: string
    reportItem?: string
    debitAmount?: number
    creditAmount?: number
  }>,
): H1AdjAllocation {
  const out: H1AdjAllocation = {
    cost: _emptyCatMap(),
    dep: _emptyCatMap(),
    impair: _emptyCatMap(),
    skipped: 0,
    applied: 0,
  }

  for (const r of rows) {
    const block = classifyFaBlock(String(r.accountCode || ''))
    if (!block) {
      out.skipped++
      continue
    }
    const cat = classifyFaCategory(
      r.accountName,
      r.noteItem,
      r.description,
      r.reportItem,
    ) || '其他设备'

    const debit = Number(r.debitAmount) || 0
    const credit = Number(r.creditAmount) || 0
    const net = block === 'cost' ? debit - credit : credit - debit

    const catKey = (H1_FA_CATEGORIES as readonly string[]).includes(cat) ? cat : '其他设备'
    const isRje = r.category === '报表调整' || r.entryType === 'RJE'
    const bucket = out[block][catKey] || (out[block][catKey] = { aje: 0, rje: 0 })
    if (isRje) bucket.rje += net
    else bucket.aje += net
    out.applied++
  }

  return out
}
