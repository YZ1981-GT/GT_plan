/**
 * K9 管理费用披露表：表单状态（读已保存行 / 默认费用性质清单 / 按 K9-1 审定表回填）与同步快照
 * （底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1 / ADR-1）。
 *
 * `K9TabDisclosureListed` / `K9TabDisclosureSoe` 原先在组件里内联这几步；抽成本模块的纯函数后 Tab（onMounted / 同步按钮）
 * 与离屏 provider 调同一份计算 ⇒ 两条路径发出逐字节相同的载荷。行身份由调用方经 `K9RowIdentity` 传入（Tab：值化身份工厂；
 * 载荷不含身份）。
 */
import { K9_FEE_NATURES, K9_FEE_NATURES_SOE } from './k9FeeNatures'
import type { K9DisclosureVariant } from './k9NoteSectionMap'

/** 披露行（`remark` 说明列不进附注） */
export interface K9DisclosureFormRow {
  id: string
  project: string
  currentAmount: number
  priorAmount: number
  remark: string
  isTotal?: boolean
}

export interface K9DisclosureFormState {
  rows: K9DisclosureFormRow[]
  narrativeText: string
}

/** 行身份：默认行的身份前缀 `row` */
export interface K9RowIdentity {
  newRow: (kind: 'row') => string
}

/** 离屏同步：载荷不含行身份 */
export const K9_HEADLESS_ROW_IDENTITY: K9RowIdentity = { newRow: () => '' }

/** 底稿回复（只读 `remark`，与 Tab / 离屏框架两种来源同口径） */
export type K9DisclosureResponses = ReadonlyMap<string, { remark?: string | null } | undefined>

const ITEM = {
  listed: { rows: 'K9-disclosure-listed-rows', narrative: 'K9-disclosure-listed-narrative' },
  soe: { rows: 'K9-disclosure-soe-rows', narrative: 'K9-disclosure-soe-narrative' },
} as const satisfies Record<K9DisclosureVariant, { rows: string; narrative: string }>
/** K9-1 审定表按费用性质的审定数（审定表 `_persistAuditedByItem` 写，{费用性质:{audited,prior}}） */
const AUDITED_BY_ITEM = 'K9-1-audited-by-item'

/** 默认费用性质清单：单一枚举源 k9FeeNatures（上市通用项 / 国企含特有项） */
const DEFAULT_PROJECTS: Record<K9DisclosureVariant, readonly string[]> = {
  listed: K9_FEE_NATURES,
  soe: K9_FEE_NATURES_SOE,
}

function defaultRows(variant: K9DisclosureVariant, ids: K9RowIdentity): K9DisclosureFormRow[] {
  return DEFAULT_PROJECTS[variant].map((name) => ({
    id: ids.newRow('row'),
    project: name,
    currentAmount: 0,
    priorAmount: 0,
    remark: '',
  }))
}

/** 读已保存的披露表（Tab onMounted 的 loadSavedData）：有保存的行用它（损坏 ⇒ 默认清单），没有 ⇒ 默认清单。 */
export function loadK9DisclosureState(
  responses: K9DisclosureResponses,
  variant: K9DisclosureVariant,
  ids: K9RowIdentity,
): K9DisclosureFormState {
  let rows: K9DisclosureFormRow[]
  const saved = responses.get(ITEM[variant].rows)
  if (saved?.remark) {
    try {
      rows = JSON.parse(saved.remark)
    } catch { rows = defaultRows(variant, ids) }
  } else {
    rows = defaultRows(variant, ids)
  }
  const savedNarrative = responses.get(ITEM[variant].narrative)
  return { rows, narrativeText: savedNarrative?.remark ? savedNarrative.remark : '' }
}

/** 归一化费用项目名以提升 K9-1 ↔ 附注名称匹配率（去尾差：费用/费/摊销/空格） */
export function normalizeK9FeeName(s: string): string {
  return String(s || '').replace(/\s+/g, '').replace(/(费用|摊销)$/, '').replace(/费$/, '')
}

/**
 * 按 K9-1 审定表回填本期 / 上期（精确名优先，再按归一化名，兼容 K9-1 与附注费用性质命名差异；就地改行）。
 * 返回匹配行数；没有数据 / 解析失败 / 不是对象 ⇒ null（Tab 此时不改「已自动取数」提示）。
 */
export function applyK9AutoFill(responses: K9DisclosureResponses, rows: K9DisclosureFormRow[]): number | null {
  const adjData = responses.get(AUDITED_BY_ITEM)
  if (!adjData?.remark) return null
  try {
    const data = JSON.parse(adjData.remark)
    if (!data || typeof data !== 'object') return null
    const normIndex: Record<string, any> = {}
    for (const [k, v] of Object.entries(data)) normIndex[normalizeK9FeeName(k)] = v
    let matched = 0
    for (const row of rows) {
      const src = data[row.project] ?? normIndex[normalizeK9FeeName(row.project)]
      if (src) {
        row.currentAmount = Number(src.currentAmount ?? src.audited ?? 0)
        row.priorAmount = Number(src.priorAmount ?? src.prior ?? 0)
        matched++
      }
    }
    return matched
  } catch { return null }
}

/** 披露表 → `buildK9SyncPayload` 的行：合计行由载荷层统一派生，这里只给明细行（避免双合计） */
export function k9DisclosureSyncRows(rows: readonly K9DisclosureFormRow[]): K9DisclosureFormRow[] {
  return rows.filter((r) => !r.isTotal)
}
