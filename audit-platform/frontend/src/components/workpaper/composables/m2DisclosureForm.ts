/**
 * M2 实收资本（股本）披露表：表格行、期末 / 占比重算、读回与同步快照（底稿披露 Tab 与附注页离屏同步共用，
 * spec note-pull-followup-closure R1 / ADR-1）。
 *
 * `M2TabDisclosureListed` / `M2TabDisclosureSoe` 原先在组件里内联「默认行 → 挂载时读回 `M2-disclosure-{版本}-capital-rows`
 * 与三段说明 → 重算期末 / 占比 → 同步时拼 `buildM2ListedSyncPayload` / `buildM2SoeSyncPayload` 入参」；原样抽到本模块后，
 * Tab（onMounted / 审定刷新 / 编辑重算 / 同步函数）与离屏 provider 调同一份计算。保存、提示、AI 留在 Tab。
 */
import {
  buildM2ListedSyncPayload,
  buildM2SoeSyncPayload,
  type M2ListedRow,
  type M2SoeRow,
  type M2SyncPayload,
} from './m2NoteSectionMap'

/** 上市（万股）：股份性质 | 期初 | 发行新股 | 送股 | 公积金转股 | 其他 | 期末 | 占比 */
export interface M2ListedCapitalRow {
  item: string
  beginShares: number
  issueNew: number
  bonusShares: number
  reserveToShares: number
  otherChange: number
  endShares: number
  ratio: number
}

/** 国企（元）：出资人 / 出资方式 | 期初 | 本期增加 | 本期减少 | 期末 | 出资比例 */
export interface M2SoeCapitalRow {
  item: string
  beginAmount: number
  increaseAmount: number
  decreaseAmount: number
  endAmount: number
  ratio: number
}

export interface M2ListedDisclosureState {
  rows: M2ListedCapitalRow[]
  restricted: string
  changeReason: string
  eps: string
}

export interface M2SoeDisclosureState {
  rows: M2SoeCapitalRow[]
  stateCapital: string
  method: string
  registration: string
}

/** 底稿回复（只读 `remark`；Tab 的 `formData.allResponses` 与离屏框架的回复两种来源同口径） */
export type M2DisclosureResponses = ReadonlyMap<string, { remark?: string | null } | undefined>

/** 底稿回复条目（与 Tab 的保存键同名） */
const ITEM = {
  listed: {
    rows: 'M2-disclosure-listed-capital-rows',
    restricted: 'M2-disclosure-listed-restricted',
    changeReason: 'M2-disclosure-listed-change-reason',
    eps: 'M2-disclosure-listed-eps',
  },
  soe: {
    rows: 'M2-disclosure-soe-capital-rows',
    stateCapital: 'M2-disclosure-soe-state-capital',
    method: 'M2-disclosure-soe-method',
    registration: 'M2-disclosure-soe-registration',
  },
} as const

const LISTED_ITEMS = [
  '一、有限售条件股份', '  1.国家持股', '  2.国有法人持股', '  3.其他内资持股', '  4.外资持股',
  '二、无限售条件股份', '  1.人民币普通股（A股）', '  2.境内上市外资股（B股）', '  3.境外上市外资股（H股）', '  4.其他',
  '三、股份总数',
]
const SOE_ITEMS = [
  '一、国家资本', '  中央国有资本', '  地方国有资本', '二、集体资本', '三、法人资本', '  国有法人资本', '  民营法人资本',
  '  外商法人资本', '四、个人资本', '五、外商资本', '合计',
]

/** 上市默认行（全 0） */
export function createM2ListedCapitalRows(): M2ListedCapitalRow[] {
  return LISTED_ITEMS.map((item) => ({
    item, beginShares: 0, issueNew: 0, bonusShares: 0, reserveToShares: 0, otherChange: 0, endShares: 0, ratio: 0,
  }))
}

/** 国企默认行（全 0） */
export function createM2SoeCapitalRows(): M2SoeCapitalRow[] {
  return SOE_ITEMS.map((item) => ({ item, beginAmount: 0, increaseAmount: 0, decreaseAmount: 0, endAmount: 0, ratio: 0 }))
}

/** 上市：期末 = 期初 + 发行新股 + 送股 + 公积金转股 + 其他；占比 = 期末 / 全部行期末之和（就地改行） */
export function recalcM2ListedRows(rows: M2ListedCapitalRow[]): void {
  const totalEnd = rows.reduce((sum, row) => {
    const end = row.beginShares + row.issueNew + row.bonusShares + row.reserveToShares + row.otherChange
    return sum + end
  }, 0)

  rows.forEach(row => {
    row.endShares = row.beginShares + row.issueNew + row.bonusShares + row.reserveToShares + row.otherChange
    row.ratio = totalEnd > 0 ? row.endShares / totalEnd : 0
  })
}

/** 国企：期末 = 期初 + 本期增加 − 本期减少；比例 = 期末 / 全部行期末之和（就地改行） */
export function recalcM2SoeRows(rows: M2SoeCapitalRow[]): void {
  const totalEnd = rows.reduce((sum, row) => {
    const end = row.beginAmount + row.increaseAmount - row.decreaseAmount
    return sum + end
  }, 0)

  rows.forEach(row => {
    row.endAmount = row.beginAmount + row.increaseAmount - row.decreaseAmount
    row.ratio = totalEnd > 0 ? row.endAmount / totalEnd : 0
  })
}

function savedArray(responses: M2DisclosureResponses, itemId: string): any[] | null {
  const remark = responses.get(itemId)?.remark
  if (!remark) return null
  const parsed = JSON.parse(remark)
  return Array.isArray(parsed) && parsed.length > 0 ? parsed : null
}

/**
 * 读回（Tab 挂载 / 审定刷新时）：有已保存行则取保存行（旧字段 increaseShares 兜底映射到发行新股）并重算；
 * 说明有值才覆盖，否则保持 `current` 的值。返回新状态，不改 `current`。
 */
export function restoreM2ListedDisclosure(
  responses: M2DisclosureResponses,
  current: M2ListedDisclosureState,
): M2ListedDisclosureState {
  let rows = current.rows
  try {
    const parsed = savedArray(responses, ITEM.listed.rows)
    if (parsed) {
      rows = parsed.map((r: any) => ({
        item: r.item ?? '',
        beginShares: r.beginShares ?? 0,
        issueNew: r.issueNew ?? r.increaseShares ?? 0,
        bonusShares: r.bonusShares ?? 0,
        reserveToShares: r.reserveToShares ?? 0,
        otherChange: r.otherChange ?? 0,
        endShares: r.endShares ?? 0,
        ratio: r.ratio ?? 0,
      }))
      recalcM2ListedRows(rows)
    }
  } catch { /* ignore */ }
  return {
    rows,
    restricted: responses.get(ITEM.listed.restricted)?.remark || current.restricted,
    changeReason: responses.get(ITEM.listed.changeReason)?.remark || current.changeReason,
    eps: responses.get(ITEM.listed.eps)?.remark || current.eps,
  }
}

/** 读回（同上）：已保存行原样取用后重算；说明有值才覆盖。返回新状态，不改 `current`。 */
export function restoreM2SoeDisclosure(
  responses: M2DisclosureResponses,
  current: M2SoeDisclosureState,
): M2SoeDisclosureState {
  let rows = current.rows
  try {
    const parsed = savedArray(responses, ITEM.soe.rows)
    if (parsed) {
      rows = parsed
      recalcM2SoeRows(rows)
    }
  } catch { /* ignore */ }
  return {
    rows,
    stateCapital: responses.get(ITEM.soe.stateCapital)?.remark || current.stateCapital,
    method: responses.get(ITEM.soe.method)?.remark || current.method,
    registration: responses.get(ITEM.soe.registration)?.remark || current.registration,
  }
}

/** 离屏同步 = Tab 挂载后的状态（默认行 + 空说明 → 读回） */
export function loadM2ListedDisclosure(responses: M2DisclosureResponses): M2ListedDisclosureState {
  return restoreM2ListedDisclosure(responses, { rows: createM2ListedCapitalRows(), restricted: '', changeReason: '', eps: '' })
}

export function loadM2SoeDisclosure(responses: M2DisclosureResponses): M2SoeDisclosureState {
  return restoreM2SoeDisclosure(responses, { rows: createM2SoeCapitalRows(), stateCapital: '', method: '', registration: '' })
}

/** 上市快照：去掉「三、股份总数」（合计行由载荷构建） */
export function m2ListedSyncRows(rows: readonly M2ListedCapitalRow[]): M2ListedRow[] {
  return rows
    .filter((r) => r.item !== '三、股份总数') // 合计行由载荷构建
    .map((r) => ({
      label: r.item,
      beginShares: r.beginShares,
      issueNew: r.issueNew ?? 0,
      bonusShares: r.bonusShares ?? 0,
      reserveToShares: r.reserveToShares ?? 0,
      otherChange: r.otherChange ?? 0,
    }))
}

/** 国企快照：去掉「合计」（合计行由载荷构建） */
export function m2SoeSyncRows(rows: readonly M2SoeCapitalRow[]): M2SoeRow[] {
  return rows
    .filter((r) => r.item !== '合计') // 合计行由载荷构建
    .map((r) => ({
      label: r.item,
      beginAmount: r.beginAmount,
      beginRatio: r.ratio ? (r.ratio * 100).toFixed(2) : '',
      increase: r.increaseAmount,
      decrease: r.decreaseAmount,
    }))
}

/** 上市 五、53 载荷 */
export function buildM2ListedTabSyncPayload(wpId: string, state: M2ListedDisclosureState): M2SyncPayload | null {
  return buildM2ListedSyncPayload(wpId, m2ListedSyncRows(state.rows), {
    restricted: state.restricted,
    changeReason: state.changeReason,
    eps: state.eps,
  })
}

/** 国企 八、58 载荷 */
export function buildM2SoeTabSyncPayload(wpId: string, state: M2SoeDisclosureState): M2SyncPayload | null {
  return buildM2SoeSyncPayload(wpId, m2SoeSyncRows(state.rows), {
    stateCapital: state.stateCapital,
    method: state.method,
    registration: state.registration,
  })
}
