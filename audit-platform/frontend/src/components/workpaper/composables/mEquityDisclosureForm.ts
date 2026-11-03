/**
 * M 循环权益类「变动表」披露 Tab 的表格行、读回与同步快照（底稿披露 Tab 与附注页离屏同步共用，
 * spec note-pull-followup-closure R1 / ADR-1）。范围与共享 builder `mEquityChangeNoteSectionMap` 相同：
 *
 * - M4 资本公积 / M5 盈余公积（`M4TabDisclosure{Listed,Soe}` / `M5TabDisclosure{Listed,Soe}`，四个 Tab 逐字同构）：
 *   原先在组件里内联「默认两行 → 挂载 / 审定刷新时按 `M{4,5}-disclosure-{版本}-{行号}-{字段}` 读回金额、按说明键读回
 *   说明 → 同步时把表格行拼成 `buildMEquitySyncPayload` 入参」；按「编码 × 版本」的表格声明参数化后原样抽到这里。
 *   期末不进快照（builder 按期初 + 增加 − 减少推导，与 Tab 显示用的 `calcEquityEndBalance` 同式）。
 * - M7 专项储备（`M7TabDisclosure{Listed,Soe}`）：默认四行 + 读回原因 / 计提依据与说明 + 按 M7-1 小计改期末（见下文）。
 * - M8 一般风险准备（`M8TabDisclosure{Listed,Soe}`，自有 builder `buildM8SyncPayload`、同为 5 列变动表）：见文末。
 *
 * Tab 的保存、提示、AI、事件订阅留在组件里；离屏 provider 只调这里的读回与载荷函数。
 */
import {
  buildMEquitySyncPayload,
  type MEquityRow,
  type MEquitySyncPayload,
  type MEquityVariant,
} from './mEquityChangeNoteSectionMap'
import { buildM8SyncPayload, type M8DisclosureRow, type M8SyncPayload } from './m8NoteSectionMap'

/** 底稿回复（只读 `remark`；Tab 的 `formData.allResponses` 与离屏框架的回复两种来源同口径） */
export type MEquityDisclosureResponses = ReadonlyMap<string, { remark?: string | null } | undefined>

// ─── M4 / M5：可录入的标准变动表 ─────────────────────────────────────────────

/** 项目 | 期初余额 | 本期增加 | 本期减少 | 期末余额（`_isTotal` 只出现在 Tab 显示用的合计行） */
export interface MEquityDisclosureRow {
  item: string
  beginBalance: number
  increase: number
  decrease: number
  endBalance: number
  _isTotal?: boolean
}

/** 一个披露 Tab 的表格声明（逐字取自原 Tab） */
export interface MEquityDisclosureForm {
  cycle: 'M4' | 'M5'
  variant: MEquityVariant
  /** 默认行（数据行，不含合计） */
  items: readonly string[]
  /** 金额回复键前缀：`${rowKeyPrefix}-${行号}-${字段}`（与 Tab 的保存键同名） */
  rowKeyPrefix: string
  /** 说明回复键，顺序 = 同步时拼接说明的顺序（与 Tab 的保存键同名） */
  noteKeys: readonly string[]
}

/** 表格状态：数据行 + 各段说明（与 `noteKeys` 一一对应） */
export interface MEquityDisclosureState {
  rows: MEquityDisclosureRow[]
  notes: string[]
}

export const M4_DISCLOSURE_FORM: Readonly<Record<MEquityVariant, MEquityDisclosureForm>> = {
  listed: {
    cycle: 'M4',
    variant: 'listed',
    items: ['资本溢价（股本溢价）', '其他资本公积'],
    rowKeyPrefix: 'M4-disclosure-listed',
    noteKeys: ['M4-disclosure-listed-premium-note', 'M4-disclosure-listed-other-note'],
  },
  soe: {
    cycle: 'M4',
    variant: 'soe',
    items: ['国有资本溢价', '其他资本公积'],
    rowKeyPrefix: 'M4-disclosure-soe',
    noteKeys: ['M4-disclosure-soe-premium-note', 'M4-disclosure-soe-other-note'],
  },
}

export const M5_DISCLOSURE_FORM: Readonly<Record<MEquityVariant, MEquityDisclosureForm>> = {
  listed: {
    cycle: 'M5',
    variant: 'listed',
    items: ['法定盈余公积', '任意盈余公积'],
    rowKeyPrefix: 'M5-disclosure-listed',
    noteKeys: ['M5-disclosure-listed-statutory-note', 'M5-disclosure-listed-discretionary-note'],
  },
  // 国企多「国有企业专项披露」一段说明
  soe: {
    cycle: 'M5',
    variant: 'soe',
    items: ['法定盈余公积', '任意盈余公积'],
    rowKeyPrefix: 'M5-disclosure-soe',
    noteKeys: ['M5-disclosure-soe-statutory-note', 'M5-disclosure-soe-discretionary-note', 'M5-disclosure-soe-special-note'],
  },
}

const AMOUNT_FIELDS = ['beginBalance', 'increase', 'decrease'] as const

/** 默认行（金额 0） */
export function createMEquityDisclosureRows(form: MEquityDisclosureForm): MEquityDisclosureRow[] {
  return form.items.map((item) => ({ item, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0 }))
}

/**
 * 读回（Tab 挂载 / 审定刷新时）：逐行逐字段按金额回复键覆盖（就地改 `current.rows`，无值 / 空串的格保持原值）；
 * 说明有值才覆盖，否则保持 `current.notes` 的值。返回新状态（行数组与 `current.rows` 是同一个）。
 */
export function restoreMEquityDisclosure(
  responses: MEquityDisclosureResponses,
  form: MEquityDisclosureForm,
  current: MEquityDisclosureState,
): MEquityDisclosureState {
  const rows = current.rows
  for (let i = 0; i < rows.length; i++) {
    for (const field of AMOUNT_FIELDS) {
      const resp = responses.get(`${form.rowKeyPrefix}-${i}-${field}`)
      if (resp?.remark) rows[i][field] = Number(resp.remark) || 0
    }
  }
  return { rows, notes: form.noteKeys.map((key, k) => responses.get(key)?.remark || current.notes[k]) }
}

/** 离屏同步 = Tab 挂载后的状态（默认行 + 空说明 → 读回） */
export function loadMEquityDisclosure(
  responses: MEquityDisclosureResponses,
  form: MEquityDisclosureForm,
): MEquityDisclosureState {
  return restoreMEquityDisclosure(responses, form, {
    rows: createMEquityDisclosureRows(form),
    notes: form.noteKeys.map(() => ''),
  })
}

/** 快照：表格数据行逐行映射（期末由 builder 推导，合计行由 builder 构建） */
export function mEquityDisclosureSyncRows(rows: readonly MEquityDisclosureRow[]): MEquityRow[] {
  return rows.map((r) => ({
    label: r.item,
    begin: Number(r.beginBalance) || 0,
    increase: Number(r.increase) || 0,
    decrease: Number(r.decrease) || 0,
  }))
}

/** 载荷（各段说明非空的按序以换行拼接，全空不带说明） */
export function buildMEquityTabSyncPayload(
  wpId: string,
  form: MEquityDisclosureForm,
  state: MEquityDisclosureState,
): MEquitySyncPayload | null {
  return buildMEquitySyncPayload(wpId, {
    cycle: form.cycle,
    variant: form.variant,
    rows: mEquityDisclosureSyncRows(state.rows),
    note: state.notes.filter(Boolean).join('\n') || undefined,
  })
}

// ─── M7：专项储备变动表（期末取 M7-1 审定小计） ────────────────────────────────
//
// `M7TabDisclosure{Listed,Soe}` 原在组件里内联「默认四行（含「合  计」行，builder 会剔掉）→ 挂载时读回说明与逐行原因 /
// 计提依据 → useNoteAutoFill 按 M7-1 小计改四行期末（合计或安全生产费非 0 才改）→ 同步时拼 builder 入参」，原样抽到这里。
// 期初 / 增加 / 减少底稿没有录入位置（恒 0），期末直接传给 builder；国企「本期减少」= 费用化 + 资本化两列之和、
// 计提依据 → 备注列。

/** M7-1 审定小计取数键（Tab 的 useNoteAutoFill 与离屏同一份） */
export const M7_AUTO_FILL_SOURCES = {
  safety: 'M7-1-safety-subtotal',
  maintenance: 'M7-1-maintenance-subtotal',
  other: 'M7-1-other-subtotal',
  total: 'M7-1-total-audited',
} as const

const M7_ITEMS = ['安全生产费', '维简费', '其他专项储备', '合  计'] as const

/** 上市专项储备行（`reason` = 变动原因，附注无落点） */
export interface M7ListedDisclosureRow {
  item: string
  beginBalance: number
  increase: number
  decrease: number
  endBalance: number
  reason: string
}

/** 国企专项储备行（`policyBasis` = 计提依据 → 备注列） */
export interface M7SoeDisclosureRow {
  item: string
  beginBalance: number
  increase: number
  expenseDecrease: number
  capitalDecrease: number
  endBalance: number
  policyBasis: string
}

export function createM7ListedDisclosureRows(): M7ListedDisclosureRow[] {
  return M7_ITEMS.map((item) => ({ item, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0, reason: '' }))
}

export function createM7SoeDisclosureRows(): M7SoeDisclosureRow[] {
  return M7_ITEMS.map((item) => ({
    item, beginBalance: 0, increase: 0, expenseDecrease: 0, capitalDecrease: 0, endBalance: 0, policyBasis: '',
  }))
}

/**
 * Tab 挂载时的读回：逐行原因（上市 `M7-disclosure-listed-row-{i}-reason`）/ 计提依据（国企 `M7-disclosure-soe-row-{i}-policy`）
 * 有值才覆盖（就地改 `rows`）；返回附注说明（没有为 null，Tab 保持原值）。
 */
export function restoreM7Disclosure(
  responses: MEquityDisclosureResponses,
  variant: MEquityVariant,
  rows: Array<M7ListedDisclosureRow | M7SoeDisclosureRow>,
): string | null {
  rows.forEach((row, i) => {
    if (variant === 'listed') {
      const resp = responses.get(`M7-disclosure-listed-row-${i}-reason`)
      if (resp?.remark) (row as M7ListedDisclosureRow).reason = resp.remark
    } else {
      const resp = responses.get(`M7-disclosure-soe-row-${i}-policy`)
      if (resp?.remark) (row as M7SoeDisclosureRow).policyBasis = resp.remark
    }
  })
  const noteResp = responses.get(variant === 'listed' ? 'M7-disclosure-listed-note' : 'M7-disclosure-soe-note')
  return noteResp?.remark ? noteResp.remark : null
}

/** Tab 的 useNoteAutoFill.onRefresh：合计或安全生产费非 0 才按顺序改四行期末；返回是否改了（Tab 据此记刷新时间、排程自动同步） */
export function applyM7AutoFill(
  rows: Array<{ endBalance: number }>,
  v: Readonly<Record<string, number | null | undefined>>,
): boolean {
  if ((v.total ?? 0) === 0 && (v.safety ?? 0) === 0) return false
  rows[0].endBalance = v.safety ?? 0
  rows[1].endBalance = v.maintenance ?? 0
  rows[2].endBalance = v.other ?? 0
  rows[3].endBalance = v.total ?? 0
  return true
}

/** 载荷（五、58 / 八、61；国企带备注列） */
export function buildM7TabSyncPayload(
  wpId: string,
  variant: MEquityVariant,
  rows: ReadonlyArray<M7ListedDisclosureRow | M7SoeDisclosureRow>,
  note: string,
): MEquitySyncPayload | null {
  const snapshotRows: MEquityRow[] = variant === 'listed'
    ? (rows as M7ListedDisclosureRow[]).map((r) => ({
      label: r.item,
      begin: Number(r.beginBalance) || 0,
      increase: Number(r.increase) || 0,
      decrease: Number(r.decrease) || 0,
      end: Number(r.endBalance) || 0,
    }))
    : (rows as M7SoeDisclosureRow[]).map((r) => ({
      label: r.item,
      begin: Number(r.beginBalance) || 0,
      increase: Number(r.increase) || 0,
      decrease: (Number(r.expenseDecrease) || 0) + (Number(r.capitalDecrease) || 0),
      end: Number(r.endBalance) || 0,
      remark: r.policyBasis || '',
    }))
  return buildMEquitySyncPayload(wpId, { cycle: 'M7', variant, rows: snapshotRows, note: note?.trim() || undefined })
}

// ─── M8：一般风险准备变动表（自有 builder `buildM8SyncPayload`，同为「期初 | 增加 | 减少 | 期末」变动表） ────
//
// `M8TabDisclosure{Listed,Soe}` 原在组件里内联「默认三行 → 挂载 / 审定刷新时按 `M8-disclosure-{版本}-row-{i}-{字段}`
// 读回、期初为 0 时取 M8-2 明细期初合计、读回说明 → 同步时拼 builder 入参」，原样抽到这里。
// 🔴 原同步函数按 `beginAmount / increaseAmount / decreaseAmount` 取值，而表格行字段是 `beginBalance / currentIncrease /
// currentDecrease` ⇒ 载荷恒为 0（这条同步路径从未被调用过：自动同步传参错误、页面没有手动同步按钮）。快照改按表格行字段取。

/** 一般风险准备表格行（合计行由组件显示用 computed 与 builder 各自构建） */
export interface M8DisclosureDataRow {
  item: string
  beginBalance: number
  currentIncrease: number
  currentDecrease: number
}

const M8_ITEMS = ['一般风险准备—信贷资产', '一般风险准备—投资资产', '一般风险准备—其他'] as const
const M8_AMOUNT_FIELDS = ['beginBalance', 'currentIncrease', 'currentDecrease'] as const

/** useM8FormData.getField 的取值口径：读 conclusion，能按 JSON 解析就解析，否则原样；没有 / 空为 null */
export function readM8FieldValue(resp: { conclusion?: string | null } | null | undefined): any {
  if (!resp) return null
  if (resp.conclusion) {
    try {
      return JSON.parse(resp.conclusion)
    } catch {
      return resp.conclusion
    }
  }
  return null
}

export function createM8DisclosureRows(): M8DisclosureDataRow[] {
  return M8_ITEMS.map((item) => ({ item, beginBalance: 0, currentIncrease: 0, currentDecrease: 0 }))
}

/**
 * Tab 的 `_restoreData`：逐行逐字段按金额回复键覆盖（就地改 `rows`）；M8-2 明细期初合计（`detailBeginTotal` = Tab 的
 * `formData.getField('2', 'total-beginBalance')`）非 0 且首行期初为 0 时填首行期初；返回说明（国企另有「专项说明」，不进载荷）。
 */
export function restoreM8Disclosure(
  responses: MEquityDisclosureResponses,
  variant: MEquityVariant,
  rows: M8DisclosureDataRow[],
  detailBeginTotal: unknown,
): { note: string | null; special: string | null } {
  for (let i = 0; i < rows.length; i++) {
    for (const field of M8_AMOUNT_FIELDS) {
      const resp = responses.get(`M8-disclosure-${variant}-row-${i}-${field}`)
      if (resp?.remark) rows[i][field] = Number(resp.remark) || 0
    }
  }
  if (detailBeginTotal !== null && detailBeginTotal !== undefined) {
    const numVal = Number(detailBeginTotal)
    if (!isNaN(numVal) && numVal !== 0 && rows[0].beginBalance === 0) rows[0].beginBalance = numVal
  }
  const note = responses.get(`M8-disclosure-${variant}-note`)?.remark || null
  const special = variant === 'soe' ? responses.get('M8-disclosure-soe-special')?.remark || null : null
  return { note, special }
}

/** 快照（按表格行字段取值；期末由 builder 推导，合计行由 builder 构建） */
export function m8DisclosureSyncRows(rows: readonly M8DisclosureDataRow[]): M8DisclosureRow[] {
  return rows.map((r) => ({
    label: r.item || '',
    begin: Number(r.beginBalance) || 0,
    increase: Number(r.currentIncrease) || 0,
    decrease: Number(r.currentDecrease) || 0,
  }))
}

/** 载荷（五、60 / 八、94；说明只取附注说明，国企专项说明不进载荷，与原 Tab 一致） */
export function buildM8TabSyncPayload(
  wpId: string,
  variant: MEquityVariant,
  rows: readonly M8DisclosureDataRow[],
  note: string,
): M8SyncPayload | null {
  return buildM8SyncPayload(wpId, variant, m8DisclosureSyncRows(rows), note)
}
