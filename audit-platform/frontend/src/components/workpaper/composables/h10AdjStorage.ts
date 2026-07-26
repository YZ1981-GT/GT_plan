/** H10-1 审定表 rowStore 读写辅助 */
import { H10_ADJUDICATION_ITEMS, H10_ADJ_WRITEBACK_ROW_KEY } from './h10Constants'
import { parseNum } from './useH10FormulaEngine'

export { H10_ADJ_WRITEBACK_ROW_KEY }

export type H10AdjRowStore = Record<string, {
  currentUnadjusted?: number
  currentAje?: number
  currentRje?: number
  priorUnadjusted?: number
  priorAje?: number
  priorRje?: number
  reasonAnalysis?: string
  indexRef?: string
}>

export interface H10AdjustmentWriteback {
  rowKey: string
  currentAje: number
  currentRje: number
}

export interface H10AdjustmentEntryLike {
  entryType?: string
  accountCode?: string
  debitAmount?: number
  creditAmount?: number
}

export function defaultH10AdjStore(): H10AdjRowStore {
  const s: H10AdjRowStore = {}
  for (const def of H10_ADJUDICATION_ITEMS) {
    s[def.rowKey] = {
      currentUnadjusted: 0,
      currentAje: 0,
      currentRje: 0,
      priorUnadjusted: 0,
      priorAje: 0,
      priorRje: 0,
      reasonAnalysis: '',
      indexRef: '',
    }
  }
  return s
}

export function parseH10AdjStore(json: string | null | undefined): H10AdjRowStore {
  if (!json) return defaultH10AdjStore()
  try {
    return { ...defaultH10AdjStore(), ...JSON.parse(json) as H10AdjRowStore }
  } catch {
    return defaultH10AdjStore()
  }
}

export function patchH10AdjRow(
  store: H10AdjRowStore,
  rowKey: string,
  patch: Partial<H10AdjRowStore[string]>,
): H10AdjRowStore {
  return {
    ...store,
    [rowKey]: { ...(store[rowKey] ?? {}), ...patch },
  }
}

/** 6115 贷方科目：调整净额 = 贷方 − 借方 */
export function calcH10AdjustmentNet(
  rows: Array<{ accountCode?: string; debitAmount?: number; creditAmount?: number }>,
): number {
  return rows
    .filter((r) => String(r.accountCode ?? '6115').startsWith('6115'))
    .reduce((s, r) => s + parseNum(r.creditAmount) - parseNum(r.debitAmount), 0)
}

/** 按 AJE/RJE 分别汇总 6115 科目净额（贷−借），用于回写 H10-1 */
export function aggregateH10AdjustmentAjeRje(
  rows: H10AdjustmentEntryLike[],
  rowKey = H10_ADJ_WRITEBACK_ROW_KEY,
): H10AdjustmentWriteback {
  let currentAje = 0
  let currentRje = 0
  for (const row of rows) {
    if (!String(row.accountCode ?? '6115').startsWith('6115')) continue
    const net = parseNum(row.creditAmount) - parseNum(row.debitAmount)
    if (row.entryType === 'RJE') currentRje += net
    else currentAje += net
  }
  return { rowKey, currentAje, currentRje }
}

/**
 * 按对方科目/摘要推断每笔调整应归入哪个审定分类行。
 * 推断规则（对方科目前缀优先 → 摘要关键词 → 默认 fixed_asset_disposal）：
 */
const _COUNTER_ACCOUNT_TO_ROW: Array<[string, string]> = [
  ['1604', 'construction_disposal'],    // 在建工程
  ['1701', 'intangible_disposal'],      // 无形资产
  ['1702', 'intangible_disposal'],      // 累计摊销
  ['1901', 'rou_disposal'],             // 使用权资产
  ['1631', 'oil_gas_disposal'],         // 油气资产
  ['1632', 'oil_gas_disposal'],         // 累计折耗
  ['1621', 'productive_bio_disposal'],  // 生产性生物资产
  ['1481', 'hfs_disposal'],             // 持有待售资产
  ['1601', 'fixed_asset_disposal'],     // 固定资产
  ['1602', 'fixed_asset_disposal'],     // 累计折旧
]

const _KEYWORD_TO_ROW: Array<[string, string]> = [
  ['在建工程', 'construction_disposal'],
  ['无形资产', 'intangible_disposal'],
  ['使用权', 'rou_disposal'],
  ['油气', 'oil_gas_disposal'],
  ['生物资产', 'productive_bio_disposal'],
  ['持有待售', 'hfs_disposal'],
  ['债务重组', 'debt_restructuring_disposal'],
  ['非货币', 'non_monetary_exchange'],
  ['试运行', 'trial_operation_sales'],
]

export interface H10AdjEntryWithContext extends H10AdjustmentEntryLike {
  summary?: string
  counterAccountCode?: string
  /** 用户显式指定的目标行（优先级最高） */
  targetRowKey?: string
}

/** 推断单笔调整分录应归入的审定分类行 */
export function inferH10AdjTargetRow(entry: H10AdjEntryWithContext): string {
  // 用户显式指定优先
  if (entry.targetRowKey && H10_ADJUDICATION_ITEMS.some(d => d.rowKey === entry.targetRowKey)) {
    return entry.targetRowKey
  }
  // 对方科目前缀匹配
  const counter = String(entry.counterAccountCode ?? '').trim()
  if (counter) {
    for (const [prefix, rowKey] of _COUNTER_ACCOUNT_TO_ROW) {
      if (counter.startsWith(prefix)) return rowKey
    }
  }
  // 摘要关键词匹配
  const summary = String(entry.summary ?? '').toLowerCase()
  if (summary) {
    for (const [kw, rowKey] of _KEYWORD_TO_ROW) {
      if (summary.includes(kw)) return rowKey
    }
  }
  return H10_ADJ_WRITEBACK_ROW_KEY
}

/** 分组聚合：按推断的目标行分别汇总 AJE/RJE 净额 */
export function aggregateH10AdjustmentByRow(
  rows: H10AdjEntryWithContext[],
): H10AdjustmentWriteback[] {
  const grouped: Record<string, { aje: number; rje: number }> = {}
  for (const row of rows) {
    if (!String(row.accountCode ?? '6115').startsWith('6115')) continue
    const targetRow = inferH10AdjTargetRow(row)
    if (!grouped[targetRow]) grouped[targetRow] = { aje: 0, rje: 0 }
    const net = parseNum(row.creditAmount) - parseNum(row.debitAmount)
    if (row.entryType === 'RJE') grouped[targetRow].rje += net
    else grouped[targetRow].aje += net
  }
  return Object.entries(grouped).map(([rowKey, { aje, rje }]) => ({
    rowKey,
    currentAje: aje,
    currentRje: rje,
  }))
}

export function applyH10AdjustmentWriteback(
  store: H10AdjRowStore,
  writeback: H10AdjustmentWriteback,
): H10AdjRowStore {
  return patchH10AdjRow(store, writeback.rowKey, {
    currentAje: writeback.currentAje,
    currentRje: writeback.currentRje,
  })
}
