/**
 * M1 应付股利（利润）披露表：表格行、读回与同步快照（底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1 / ADR-1）。
 *
 * `M1TabDisclosureSoe` / `M1TabDisclosureListed` 原先在组件里内联「默认行 → 挂载时按 `M1-disclosure-{版本}-{行号}-{字段}`
 * 读回金额 → 同步时把表格行拼成 `buildM1SyncPayload` 入参」；抽到本模块后，Tab（onMounted / 同步函数）与离屏 provider
 * 调同一份计算。说明文本框不进载荷，读回仍留在 Tab。
 *
 * 快照缺陷修复（2026-10-27，Tab 与离屏同受益）：
 * - 原快照按 `endAmount / priorAmount` 取值：国企行的字段是 `beginBalance / endBalance`、上市行的上年数是 `priorYearEnd`
 *   ⇒ 国企「期末余额 / 期初余额」两列、上市「上年年末余额」列在载荷里恒为 0。现按表格真实字段取值。
 * - 表格末行「合计」是输入行，原样当明细发出后 builder 又追加自算的「合计」⇒ 附注里两行合计、自算合计把它再加一遍。
 *   现与同表 K3 / M2 同口径：合计行由 builder 构建，快照不发表格的合计行。
 */
import { buildM1SyncPayload, type M1DividendRow, type M1SyncPayload } from './m1NoteSectionMap'

/** 国企：项目 | 年初余额 | 期末余额 */
export interface M1SoeDisclosureRow {
  item: string
  beginBalance: number
  endBalance: number
}

/** 上市：股东名称/项目 | 期末数 | 上年年末数 */
export interface M1ListedDisclosureRow {
  item: string
  endAmount: number
  priorYearEnd: number
}

/** 底稿回复（只读 `remark`；Tab 的 `formData.allResponses` 与离屏框架的回复两种来源同口径） */
export type M1DisclosureResponses = ReadonlyMap<string, { remark?: string | null } | undefined>

const TOTAL_LABEL = '合计'
const SOE_ITEMS = ['应付国有股东股利', '应付法人股东股利', '应付其他股东股利', TOTAL_LABEL]
const LISTED_ITEMS = ['股东A（境内法人）', '股东B（境内自然人）', '股东C（境外法人）', '股东D（其他）', TOTAL_LABEL]

/** 国企默认行（金额 0，末行合计） */
export function createM1SoeDisclosureRows(): M1SoeDisclosureRow[] {
  return SOE_ITEMS.map((item) => ({ item, beginBalance: 0, endBalance: 0 }))
}

/** 上市默认行（金额 0，末行合计） */
export function createM1ListedDisclosureRows(): M1ListedDisclosureRow[] {
  return LISTED_ITEMS.map((item) => ({ item, endAmount: 0, priorYearEnd: 0 }))
}

/** 读回：逐行按 `M1-disclosure-soe-{行号}-{字段}` 覆盖金额（就地改行；无值 / 空串的格保持原值） */
export function restoreM1SoeDisclosureRows(responses: M1DisclosureResponses, rows: M1SoeDisclosureRow[]): void {
  for (let i = 0; i < rows.length; i++) {
    const beginResp = responses.get(`M1-disclosure-soe-${i}-beginBalance`)
    const endResp = responses.get(`M1-disclosure-soe-${i}-endBalance`)
    if (beginResp?.remark) rows[i].beginBalance = Number(beginResp.remark) || 0
    if (endResp?.remark) rows[i].endBalance = Number(endResp.remark) || 0
  }
}

/** 读回：逐行按 `M1-disclosure-listed-{行号}-{字段}` 覆盖金额（就地改行；无值 / 空串的格保持原值） */
export function restoreM1ListedDisclosureRows(responses: M1DisclosureResponses, rows: M1ListedDisclosureRow[]): void {
  for (let i = 0; i < rows.length; i++) {
    const endResp = responses.get(`M1-disclosure-listed-${i}-endAmount`)
    const priorResp = responses.get(`M1-disclosure-listed-${i}-priorYearEnd`)
    if (endResp?.remark) rows[i].endAmount = Number(endResp.remark) || 0
    if (priorResp?.remark) rows[i].priorYearEnd = Number(priorResp.remark) || 0
  }
}

/** 默认行 + 读回（离屏同步 = Tab 挂载后的表格） */
export function loadM1SoeDisclosureRows(responses: M1DisclosureResponses): M1SoeDisclosureRow[] {
  const rows = createM1SoeDisclosureRows()
  restoreM1SoeDisclosureRows(responses, rows)
  return rows
}

/** 默认行 + 读回（离屏同步 = Tab 挂载后的表格） */
export function loadM1ListedDisclosureRows(responses: M1DisclosureResponses): M1ListedDisclosureRow[] {
  const rows = createM1ListedDisclosureRows()
  restoreM1ListedDisclosureRows(responses, rows)
  return rows
}

/** 表格行 → `buildM1SyncPayload` 的应付股利行（期末 / 上期两列按各版真实字段取；合计行由 builder 构建） */
export function m1SoeDividendRows(rows: readonly M1SoeDisclosureRow[]): M1DividendRow[] {
  return rows
    .filter((r) => r.item !== TOTAL_LABEL)
    .map((r) => ({
      label: r.item || '',
      endAmount: Number(r.endBalance) || 0,
      priorAmount: Number(r.beginBalance) || 0,
    }))
}

/** 表格行 → `buildM1SyncPayload` 的应付股利行（期末 / 上期两列按各版真实字段取；合计行由 builder 构建） */
export function m1ListedDividendRows(rows: readonly M1ListedDisclosureRow[]): M1DividendRow[] {
  return rows
    .filter((r) => r.item !== TOTAL_LABEL)
    .map((r) => ({
      label: r.item || '',
      endAmount: Number(r.endAmount) || 0,
      priorAmount: Number(r.priorYearEnd) || 0,
    }))
}

/** 国企 八、42「应付股利」载荷（浅合并进 K3 章节） */
export function buildM1SoeTabSyncPayload(wpId: string, rows: readonly M1SoeDisclosureRow[]): M1SyncPayload | null {
  return buildM1SyncPayload(wpId, 'soe', m1SoeDividendRows(rows))
}

/** 上市 五、42「应付股利」载荷（「超过 1 年未支付」表暂无录入区块 ⇒ 不推，与原 Tab 一致） */
export function buildM1ListedTabSyncPayload(wpId: string, rows: readonly M1ListedDisclosureRow[]): M1SyncPayload | null {
  return buildM1SyncPayload(wpId, 'listed', m1ListedDividendRows(rows), [])
}
