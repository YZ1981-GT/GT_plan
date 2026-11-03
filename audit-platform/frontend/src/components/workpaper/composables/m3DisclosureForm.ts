/**
 * M3 库存股披露表（仅上市 五、56）：表格行、期末重算、读回与同步快照（底稿披露 Tab 与附注页离屏同步共用，
 * spec note-pull-followup-closure R1 / ADR-1）。
 *
 * `M3TabDisclosureListed` 原先在组件里内联「默认行 → 挂载时读回 `M3-disclosure-listed-treasury-rows` 与三段说明 →
 * 重算期末 → 同步时拼 `buildM3SyncPayload` 入参」；原样抽到本模块后，Tab（onMounted / 审定刷新 / 编辑 / 带入后重算 /
 * 同步函数）与离屏 provider 调同一份计算。「从审定表 / 明细表带入」是用户按钮（含覆盖确认框），留在 Tab、离屏不做。
 */
import { calcContraEquityEndBalance } from './useM3FormulaEngine'
import { buildM3SyncPayload, type M3DisclosureRow, type M3SyncPayload } from './m3NoteSectionMap'

/** 项目 | 期初金额 | 本期回购增加 | 本期注销减少 | 期末金额 */
export interface M3TreasuryDisclosureRow {
  item: string
  beginAmount: number
  repurchaseIncrease: number
  cancelDecrease: number
  endAmount: number
}

export interface M3TreasuryDisclosureState {
  rows: M3TreasuryDisclosureRow[]
  purpose: string
  execution: string
  equityImpact: string
}

/** 底稿回复（只读 `remark`；Tab 的 `formData.allResponses` 与离屏框架的回复两种来源同口径） */
export type M3DisclosureResponses = ReadonlyMap<string, { remark?: string | null } | undefined>

/** 底稿回复条目（与 Tab 的保存键同名） */
const ITEM = {
  rows: 'M3-disclosure-listed-treasury-rows',
  purpose: 'M3-disclosure-listed-purpose',
  execution: 'M3-disclosure-listed-execution',
  equityImpact: 'M3-disclosure-listed-equity-impact',
} as const

const DEFAULT_ITEMS = ['一、库存股合计', '  其中：员工持股计划', '  市值管理/减少注册资本', '  股权激励', '  其他']

/** 默认行（全 0） */
export function createM3TreasuryRows(): M3TreasuryDisclosureRow[] {
  return DEFAULT_ITEMS.map((item) => ({ item, beginAmount: 0, repurchaseIncrease: 0, cancelDecrease: 0, endAmount: 0 }))
}

/** 期末 = 期初 + 回购增加 − 注销减少（库存股为权益备抵、借方余额；就地改行） */
export function recalcM3TreasuryRows(rows: M3TreasuryDisclosureRow[]): void {
  rows.forEach(row => {
    row.endAmount = calcContraEquityEndBalance(row.beginAmount, row.repurchaseIncrease, row.cancelDecrease)
  })
}

/**
 * 读回（Tab 挂载 / 审定刷新时）：有已保存行则原样取用并重算期末；说明有值才覆盖，否则保持 `current` 的值。
 * 返回新状态，不改 `current`。
 */
export function restoreM3TreasuryDisclosure(
  responses: M3DisclosureResponses,
  current: M3TreasuryDisclosureState,
): M3TreasuryDisclosureState {
  let rows = current.rows
  const remark = responses.get(ITEM.rows)?.remark
  if (remark) {
    try {
      const parsed = JSON.parse(remark)
      if (Array.isArray(parsed) && parsed.length > 0) {
        rows = parsed
        recalcM3TreasuryRows(rows)
      }
    } catch { /* ignore */ }
  }
  return {
    rows,
    purpose: responses.get(ITEM.purpose)?.remark || current.purpose,
    execution: responses.get(ITEM.execution)?.remark || current.execution,
    equityImpact: responses.get(ITEM.equityImpact)?.remark || current.equityImpact,
  }
}

/** 离屏同步 = Tab 挂载后的状态（默认行 + 空说明 → 读回） */
export function loadM3TreasuryDisclosure(responses: M3DisclosureResponses): M3TreasuryDisclosureState {
  return restoreM3TreasuryDisclosure(responses, { rows: createM3TreasuryRows(), purpose: '', execution: '', equityImpact: '' })
}

/** 快照：表格行逐行映射（期末由 builder 按期初 + 增加 − 减少推导） */
export function m3TreasurySyncRows(rows: readonly M3TreasuryDisclosureRow[]): M3DisclosureRow[] {
  return rows.map((r) => ({
    label: r.item,
    begin: r.beginAmount,
    increase: r.repurchaseIncrease,
    decrease: r.cancelDecrease,
  }))
}

/** 上市 五、56 载荷 */
export function buildM3TabSyncPayload(wpId: string, state: M3TreasuryDisclosureState): M3SyncPayload | null {
  return buildM3SyncPayload(
    wpId,
    m3TreasurySyncRows(state.rows),
    { purpose: state.purpose, execution: state.execution, equityImpact: state.equityImpact },
  )
}
