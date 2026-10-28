/**
 * K5 预计负债披露 Tab 的预计负债表 + 附注说明（底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1 / ADR-1）。
 *
 * 由 `K5TabDisclosureListed` / `K5TabDisclosureSoe` 原样抽出：挂载时读回已保存的预计负债表（没有 / 解析失败用默认分类 + 合计行）
 * 与附注说明，再按 `K5-1-audited-total` 自动取数（改行内金额、重算合计）；「同步到附注」把非合计行映射成 builder 行（形成原因：
 * 上市取「变动说明」`remark`，国企取「确认依据」`basis`）。Tab 与离屏 provider 调同一份计算 ⇒ 两条路径发出逐字节相同的载荷。
 * 或有负债表、会计政策、分项明细（都不进载荷）、保存、提示、AI、事件留在 Tab。
 *
 * 行身份由调用方注入（`newRow`）：Tab 传共享工厂 `newRowIdentity('row')`；离屏 provider 的行只进载荷、不落库，传空串即可。
 */
import type { K5DisclosureRow, K5DisclosureVariant } from './k5NoteSectionMap'

interface K5ProvisionRowBase {
  id: string
  category: string
  beginBalance: number
  increase: number
  decrease: number
  endBalance: number
  isTotal: boolean
  isAutoFill: boolean
}

/** 上市预计负债表行（整表存在 `K5-disclosure-listed-provision-table` 的 remark） */
export interface K5ListedProvisionRow extends K5ProvisionRowBase {
  remark: string
}

/** 国企预计负债表行（整表存在 `K5-disclosure-soe-provision-table` 的 remark；`riskLevel` 是审计列，附注无落点） */
export interface K5SoeProvisionRow extends K5ProvisionRowBase {
  basis: string
  riskLevel: string
}

export type K5ProvisionRow = K5ListedProvisionRow | K5SoeProvisionRow

export type K5NewRowId = () => string

export const K5_DISCLOSURE_ITEM_KEYS = {
  listed: { table: 'K5-disclosure-listed-provision-table', narrative: 'K5-disclosure-listed-narrative' },
  soe: { table: 'K5-disclosure-soe-provision-table', narrative: 'K5-disclosure-soe-narrative' },
} as const satisfies Record<K5DisclosureVariant, { table: string; narrative: string }>

/** 无保存表时的默认分类（两版不同：国企多「担保」「环保义务」） */
export const K5_DEFAULT_CATEGORIES: Readonly<Record<K5DisclosureVariant, readonly string[]>> = {
  listed: ['产品质量保证', '未决诉讼', '亏损合同', '重组义务', '弃置义务', '其他'],
  soe: ['产品质量保证', '未决诉讼', '亏损合同', '重组义务', '弃置义务', '担保', '环保义务', '其他'],
}

type Responses = ReadonlyMap<string, any>

export function k5DefaultProvisionTable(variant: 'listed', newRow: K5NewRowId): K5ListedProvisionRow[]
export function k5DefaultProvisionTable(variant: 'soe', newRow: K5NewRowId): K5SoeProvisionRow[]
export function k5DefaultProvisionTable(variant: K5DisclosureVariant, newRow: K5NewRowId): K5ProvisionRow[]
export function k5DefaultProvisionTable(variant: K5DisclosureVariant, newRow: K5NewRowId): K5ProvisionRow[] {
  if (variant === 'listed') {
    return [
      ...K5_DEFAULT_CATEGORIES.listed.map((cat) => ({
        id: newRow(),
        category: cat,
        beginBalance: 0,
        increase: 0,
        decrease: 0,
        endBalance: 0,
        remark: '',
        isTotal: false,
        isAutoFill: false,
      })),
      {
        id: 'row-total',
        category: '合计',
        beginBalance: 0,
        increase: 0,
        decrease: 0,
        endBalance: 0,
        remark: '',
        isTotal: true,
        isAutoFill: false,
      },
    ]
  }
  return [
    ...K5_DEFAULT_CATEGORIES.soe.map((cat) => ({
      id: newRow(),
      category: cat,
      beginBalance: 0,
      increase: 0,
      decrease: 0,
      endBalance: 0,
      basis: '',
      riskLevel: '',
      isTotal: false,
      isAutoFill: false,
    })),
    {
      id: 'row-total',
      category: '合计',
      beginBalance: 0,
      increase: 0,
      decrease: 0,
      endBalance: 0,
      basis: '',
      riskLevel: '',
      isTotal: true,
      isAutoFill: false,
    },
  ]
}

/**
 * 挂载时读回：已保存表（remark 能解析就用，原样不校验）→ 默认分类；附注说明没有（remark 为空）时为 null（Tab 保持原值）。
 */
export function loadK5DisclosureState(responses: Responses, variant: 'listed', newRow: K5NewRowId):
  { rows: K5ListedProvisionRow[]; narrative: string | null }
export function loadK5DisclosureState(responses: Responses, variant: 'soe', newRow: K5NewRowId):
  { rows: K5SoeProvisionRow[]; narrative: string | null }
export function loadK5DisclosureState(responses: Responses, variant: K5DisclosureVariant, newRow: K5NewRowId):
  { rows: K5ProvisionRow[]; narrative: string | null }
export function loadK5DisclosureState(
  responses: Responses,
  variant: K5DisclosureVariant,
  newRow: K5NewRowId,
): { rows: K5ProvisionRow[]; narrative: string | null } {
  const keys = K5_DISCLOSURE_ITEM_KEYS[variant]
  let rows: K5ProvisionRow[]
  const saved = responses.get(keys.table)
  if (saved?.remark) {
    try { rows = JSON.parse(saved.remark) } catch { rows = k5DefaultProvisionTable(variant, newRow) }
  } else {
    rows = k5DefaultProvisionTable(variant, newRow)
  }
  const savedNarrative = responses.get(keys.narrative)
  return { rows, narrative: savedNarrative?.remark ? savedNarrative.remark : null }
}

/**
 * 从 K5-1 审定表自动取数（按类别名匹配，改行内金额、标自动填充、重算合计行）。
 * 返回是否有 `K5-1-audited-total`（Tab 据此显示「已自动取数」；解析失败也算有，与原 Tab 一致）。
 */
export function applyK5ProvisionAutoFill(rows: K5ProvisionRow[], responses: Responses): boolean {
  const adjTotal = responses.get('K5-1-audited-total')
  if (!adjTotal?.remark) return false
  try {
    const data = JSON.parse(adjTotal.remark)
    if (data && typeof data === 'object') {
      for (const row of rows) {
        if (!row.isTotal && data[row.category]) {
          const d = data[row.category]
          row.beginBalance = Number(d.beginBalance ?? 0)
          row.increase = Number(d.increase ?? 0)
          row.decrease = Number(d.decrease ?? 0)
          row.endBalance = Number(d.endBalance ?? 0)
          row.isAutoFill = true
        }
      }
      const totalRow = rows.find((r) => r.isTotal)
      if (totalRow) {
        const dataRows = rows.filter((r) => !r.isTotal)
        totalRow.beginBalance = dataRows.reduce((s, r) => s + r.beginBalance, 0)
        totalRow.increase = dataRows.reduce((s, r) => s + r.increase, 0)
        totalRow.decrease = dataRows.reduce((s, r) => s + r.decrease, 0)
        totalRow.endBalance = dataRows.reduce((s, r) => s + r.endBalance, 0)
      }
    }
  } catch { /* silent */ }
  return true
}

/**
 * 「同步到附注」的 builder 行：剔合计行。附注 五、50 / 八、55 只有「期末余额 / 上年年末（期初）余额 / 形成原因」三列，
 * 本期增加 / 减少不进附注；形成原因上市取 `remark`、国企取 `basis`。
 */
export function k5DisclosureSyncRows(rows: readonly K5ProvisionRow[], variant: K5DisclosureVariant): K5DisclosureRow[] {
  return rows.filter((r) => !r.isTotal).map((r) => ({
    project: r.category,
    endAmount: r.endBalance ?? 0,
    priorAmount: r.beginBalance ?? 0,
    reason: (variant === 'listed' ? (r as K5ListedProvisionRow).remark : (r as K5SoeProvisionRow).basis) ?? '',
  }))
}
