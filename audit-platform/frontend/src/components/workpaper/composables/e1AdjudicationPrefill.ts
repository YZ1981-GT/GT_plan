/**
 * e1AdjudicationPrefill — E1-1 审定表「从四表库带入未审数」（纯函数）
 *
 * 数据来源：后端 `_e1_monetary_fund.build_e1_adjudication_prefill` 下发的
 * `html_data.adjudication_prefill`，形态 `{slot_key: {opening, closing, accountCode,
 * accountCodes, found}}`（槽 key 与 `four_table/e_cycle_specs` 逐字一致）。
 *
 * **写入目标是跨 sheet 聚合键，不是审定表自己的键**：
 * E1-1 的「未审数」列本来就由 E1-2/E1-3/E1-4 明细表经跨 sheet 键喂进来
 * （`useE1Adjudication` 的 `cashUnaudited` / `bankUnaudited` / … 都读这些键）。
 * 所以四表带入必须写同一批键，否则审定表读不到 —— 写 `E1-adj-*` 只会静默无效。
 *
 * 🔴 三条硬约束：
 * 1. `found === false` 的槽**完全跳过**（本项目无该科目 ≠ 该科目为 0）。
 *    「存放财务公司款项」「数字货币」按准则解释 15 号是「可增设」项目，
 *    多数项目没有 —— 写 0 会把「不适用」伪装成「已核实为零」。
 * 2. 已有非空值且与四表不同 → 计入 `conflicts` 交调用方弹确认，**不静默覆盖**
 *    （明细表已编制的数据优先于四表原始取数）。
 * 3. 纯函数：不碰 Vue、不发请求，便于单测与 PBT。
 *
 * spec: .kiro/specs/e1-four-table-extraction-and-disclosure-alignment/
 *       Requirements 2.4, 2.7 / Task 10
 */

/** 单槽预填（镜像后端 `build_e1_adjudication_prefill` 的字段名） */
export interface E1SlotPrefill {
  opening?: number
  closing?: number
  accountCode?: string
  accountCodes?: string[]
  found?: boolean
}

export type E1AdjudicationPrefill = Record<string, E1SlotPrefill>

/** 槽 → 审定表未审数所依赖的跨 sheet 聚合键（期初 / 期末） */
interface SlotKeyBinding {
  label: string
  /** 期初键（可多个 —— `bank` 同时喂「本金」与「银行机构存款」两行，沿用四表 seed 口径） */
  openingKeys: string[]
  endingKeys: string[]
}

/**
 * 槽 → 跨 sheet 键绑定。
 *
 * 键名逐字取自 `useE1Adjudication` 的 `getVal(...)` 调用 —— 那里是真源，
 * 改一侧必改另一侧（守卫 `e1AdjudicationPrefill.spec.ts` 从 composable 源码反查）。
 */
export const E1_SLOT_CROSS_SHEET_KEYS: Readonly<Record<string, SlotKeyBinding>> = Object.freeze({
  cash: {
    label: '库存现金',
    openingKeys: ['E1-cash-detail-opening-unaudited'],
    endingKeys: ['E1-cash-detail-total-unaudited'],
  },
  bank: {
    label: '银行存款',
    openingKeys: [
      'E1-bank-detail-principal-opening-unaudited',
      'E1-bank-detail-institution-opening-unaudited',
    ],
    endingKeys: [
      'E1-bank-detail-principal-total-unaudited',
      'E1-bank-detail-institution-total-unaudited',
    ],
  },
  other: {
    label: '其他货币资金',
    openingKeys: ['E1-bank-detail-other-opening-unaudited'],
    endingKeys: ['E1-bank-detail-other-total-unaudited'],
  },
  finance_co: {
    label: '存放财务公司款项',
    openingKeys: ['E1-bank-detail-finance-opening-unaudited'],
    endingKeys: ['E1-bank-detail-finance-total-unaudited'],
  },
  digital: {
    label: '数字货币',
    openingKeys: ['E1-digital-opening-unaudited'],
    endingKeys: ['E1-digital-total-unaudited'],
  },
})

/** 槽展示顺序（与源模板 E1-1 行序、语义槽声明顺序一致） */
export const E1_SLOT_ORDER: readonly string[] = Object.freeze([
  'cash',
  'bank',
  'other',
  'finance_co',
  'digital',
])

export interface E1PrefillWrite {
  itemId: string
  /** 落库形态：`checklist_responses.remark` 存字符串 */
  value: string
  numeric: number
  slotKey: string
  label: string
  period: 'opening' | 'ending'
  accountCodes: string[]
}

export interface E1PrefillConflict extends E1PrefillWrite {
  /** 当前已有值（非空且与四表不同） */
  current: number
}

export interface E1PrefillPlan {
  /** 当前为空 → 直接写入 */
  writes: E1PrefillWrite[]
  /** 已有值且不同 → 需用户确认 */
  conflicts: E1PrefillConflict[]
  /** `found === false` 被跳过的槽（面板/提示里如实说明「本项目无此科目」） */
  skippedSlots: Array<{ slotKey: string; label: string }>
}

export function normalizeE1AdjudicationPrefill(raw: unknown): E1AdjudicationPrefill {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  const out: E1AdjudicationPrefill = {}
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    if (!v || typeof v !== 'object') continue
    const s = v as Record<string, unknown>
    out[k] = {
      opening: Number(s.opening) || 0,
      closing: Number(s.closing) || 0,
      accountCode: typeof s.accountCode === 'string' ? s.accountCode : '',
      accountCodes: Array.isArray(s.accountCodes) ? s.accountCodes.map(String) : [],
      found: !!s.found,
    }
  }
  return out
}

/** 当前值读取器（组件传 `allResponses` 的读函数；返回 `null`/`''` 视为未填） */
export type CurrentValueReader = (itemId: string) => string | null | undefined

const TOLERANCE = 0.005

function isBlank(v: string | null | undefined): boolean {
  return v === null || v === undefined || String(v).trim() === ''
}

/**
 * 生成带入计划（不执行）。
 *
 * @param prefill render 下发的 `adjudication_prefill`
 * @param read 当前值读取器
 * @param order 槽顺序（默认 `E1_SLOT_ORDER`）
 */
export function planE1AdjudicationPrefill(
  prefill: E1AdjudicationPrefill,
  read: CurrentValueReader,
  order: readonly string[] = E1_SLOT_ORDER,
): E1PrefillPlan {
  const plan: E1PrefillPlan = { writes: [], conflicts: [], skippedSlots: [] }
  for (const slotKey of order) {
    const binding = E1_SLOT_CROSS_SHEET_KEYS[slotKey]
    if (!binding) continue
    const slot = prefill[slotKey]
    if (!slot || !slot.found) {
      plan.skippedSlots.push({ slotKey, label: binding.label })
      continue
    }
    const periods: Array<{ period: 'opening' | 'ending'; keys: string[]; amount: number }> = [
      { period: 'opening', keys: binding.openingKeys, amount: Number(slot.opening) || 0 },
      { period: 'ending', keys: binding.endingKeys, amount: Number(slot.closing) || 0 },
    ]
    for (const { period, keys, amount } of periods) {
      for (const itemId of keys) {
        const entry: E1PrefillWrite = {
          itemId,
          value: String(amount),
          numeric: amount,
          slotKey,
          label: binding.label,
          period,
          accountCodes: slot.accountCodes || [],
        }
        const cur = read(itemId)
        if (isBlank(cur)) {
          plan.writes.push(entry)
          continue
        }
        const curNum = Number(cur)
        if (!Number.isFinite(curNum) || Math.abs(curNum - amount) > TOLERANCE) {
          plan.conflicts.push({ ...entry, current: Number.isFinite(curNum) ? curNum : 0 })
        }
        // 相等 → 无需写入（幂等）
      }
    }
  }
  return plan
}

/**
 * 计划 → 实际写入项。
 *
 * @param mode `'fill-blank'` 只补空值（默认，永不覆盖已录入）；`'overwrite'` 连冲突项一起覆盖
 */
export function resolveE1PrefillWrites(
  plan: E1PrefillPlan,
  mode: 'fill-blank' | 'overwrite' = 'fill-blank',
): E1PrefillWrite[] {
  return mode === 'overwrite' ? [...plan.writes, ...plan.conflicts] : [...plan.writes]
}

/** 计划摘要（toast 文案，中文化） */
export function describeE1PrefillPlan(plan: E1PrefillPlan): string {
  const parts: string[] = []
  if (plan.writes.length) parts.push(`补填 ${plan.writes.length} 项`)
  if (plan.conflicts.length) parts.push(`${plan.conflicts.length} 项与现有数据不一致`)
  if (plan.skippedSlots.length) {
    parts.push(`${plan.skippedSlots.map((s) => s.label).join('、')} 本项目无此科目（已跳过）`)
  }
  return parts.length ? parts.join('；') : '四表数据与当前未审数一致，无需带入'
}
