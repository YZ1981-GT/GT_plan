/**
 * K11 资产减值损失披露 Tab 的表格行 + 附注说明（底稿披露 Tab 与附注页离屏同步共用，spec note-pull-followup-closure R1 / ADR-1）。
 *
 * 由 `K11TabDisclosureListed` / `K11TabDisclosureSoe` 原样抽出（两版只差条目键）：挂载时读回已保存行（没有则按 K11-1
 * 审定表行构建，再没有用 18 项默认分类）与附注说明，再按 `K11-1-audited-by-category` 自动取数；「同步到附注」把行映射成
 * builder 行。Tab 与离屏 provider 调同一份计算 ⇒ 两条路径发出逐字节相同的载荷。保存、提示、事件留在 Tab。
 *
 * 行身份由调用方注入（`newRow`）：Tab 传共享工厂 `newRowIdentity('row')`（K 循环位置化身份修复的唯一出口，守卫要求
 * Tab 自己 import 它）；离屏 provider 的行只进载荷、不落库，身份不参与载荷，传空串即可。
 */
import { normalizeImpairmentCategory } from './useK11Adjudication'
import type { K11DisclosureRow, K11DisclosureVariant } from './k11NoteSectionMap'

/** Tab 披露行（整表存在 `K11-disclosure-{variant}-rows` 的 remark） */
export interface K11DisclosureTabRow {
  id: string
  category: string
  currentProvision: number
  currentReversal: number
  priorAmount: number
  remark: string
  isTotal?: boolean
  noReversal?: boolean
}

export const K11_DISCLOSURE_ITEM_KEYS = {
  listed: { rows: 'K11-disclosure-listed-rows', narrative: 'K11-disclosure-listed-narrative' },
  soe: { rows: 'K11-disclosure-soe-rows', narrative: 'K11-disclosure-soe-narrative' },
} as const satisfies Record<K11DisclosureVariant, { rows: string; narrative: string }>

/** P1 对齐源模板 18 项 canonical 分类（两版相同；仅无保存行、无 K11-1 数据时的回退） */
export const K11_DEFAULT_CATEGORIES: ReadonlyArray<{ name: string; noReversal: boolean }> = [
  { name: '合同资产减值损失', noReversal: false },
  { name: '存货跌价损失', noReversal: false },
  { name: '合同取得成本减值损失', noReversal: false },
  { name: '合同履约成本减值损失', noReversal: false },
  { name: '持有待售资产减值损失', noReversal: false },
  { name: '其他权益工具投资减值损失', noReversal: false },
  { name: '其他非流动金融资产减值损失', noReversal: false },
  { name: '长期股权投资减值损失', noReversal: false },
  { name: '投资性房地产减值损失', noReversal: false },
  { name: '固定资产减值损失', noReversal: false },
  { name: '工程物资减值损失', noReversal: false },
  { name: '在建工程减值损失', noReversal: false },
  { name: '生产性生物资产减值损失', noReversal: false },
  { name: '油气资产减值损失', noReversal: false },
  { name: '使用权资产减值损失', noReversal: false },
  { name: '无形资产减值损失', noReversal: false },
  { name: '商誉减值损失', noReversal: true },
  { name: '其他', noReversal: false },
]

type Responses = ReadonlyMap<string, any>
/** 新行身份工厂（Tab 传 `() => newRowIdentity('row')`） */
export type K11NewRowId = () => string

export function k11DefaultDisclosureRows(newRow: K11NewRowId): K11DisclosureTabRow[] {
  return K11_DEFAULT_CATEGORIES.map((item) => ({
    id: newRow(),
    category: item.name,
    currentProvision: 0,
    currentReversal: 0,
    priorAmount: 0,
    remark: '',
    noReversal: item.noReversal,
  }))
}

/** 按 K11-1 审定表行动态构建披露行（对齐源模板"附注引用审定表"设计） */
export function k11RowsFromAdjudication(responses: Responses, newRow: K11NewRowId): K11DisclosureTabRow[] {
  const item = responses.get('K11-1-rows')
  const raw = item?.remark ?? item?.conclusion
  if (!raw) return []
  try {
    const arr = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (!Array.isArray(arr)) return []
    return arr
      .filter((r: any) => r && r.projectName)
      .map((r: any) => {
        const audited = Number(
          r.audited ?? (Number(r.currentOccurrence || 0) + Number(r.aje || 0) + Number(r.rje || 0)),
        )
        return {
          id: newRow(),
          category: String(r.projectName),
          currentProvision: audited,
          currentReversal: 0,
          priorAmount: Number(r.priorAudited ?? r.priorOccurrence ?? 0),
          remark: '',
          noReversal: String(r.projectName).includes('商誉'),
        }
      })
  } catch {
    return []
  }
}

/**
 * 挂载时读回：已保存行（非空数组）→ K11-1 审定表行 → 默认分类；附注说明没有（remark 为空）时为 null（Tab 保持原值）。
 */
export function loadK11DisclosureState(
  responses: Responses,
  variant: K11DisclosureVariant,
  newRow: K11NewRowId,
): { rows: K11DisclosureTabRow[]; narrative: string | null } {
  const keys = K11_DISCLOSURE_ITEM_KEYS[variant]
  let rows: K11DisclosureTabRow[] | null = null
  const saved = responses.get(keys.rows)
  if (saved?.remark) {
    try {
      const parsed = JSON.parse(saved.remark)
      if (Array.isArray(parsed) && parsed.length > 0) rows = parsed
    } catch { /* fallthrough */ }
  }
  if (!rows) {
    // 无手工保存 → 优先按 K11-1 审定表行动态构建（避免硬编码类别与审定表不一致），否则回退默认
    const fromK11 = k11RowsFromAdjudication(responses, newRow)
    rows = fromK11.length > 0 ? fromK11 : k11DefaultDisclosureRows(newRow)
  }
  const savedNarrative = responses.get(keys.narrative)
  return { rows, narrative: savedNarrative?.remark ? savedNarrative.remark : null }
}

/**
 * 自动取数（从 K11-1 审定表）：按归一化资产类别名匹配（"存货跌价损失"↔"存货跌价准备"），改行内金额。
 * 返回匹配到的行数；没有数据 / 解析失败回 0（Tab 据此显示「已自动取数」提示）。
 */
export function applyK11AutoFill(rows: K11DisclosureTabRow[], responses: Responses): number {
  const adjData = responses.get('K11-1-audited-by-category')
  const raw = adjData?.remark ?? adjData?.conclusion
  if (!raw) return 0
  try {
    const data = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (!data || typeof data !== 'object') return 0
    let matched = 0
    for (const row of rows) {
      const src = data[normalizeImpairmentCategory(row.category)]
      if (src) {
        row.currentProvision = Number(src.currentProvision ?? src.provision ?? src.occurrence ?? 0)
        row.currentReversal = Number(src.currentReversal ?? src.reversal ?? 0)
        row.priorAmount = Number(src.priorAmount ?? src.prior ?? 0)
        matched++
      }
    }
    return matched
  } catch {
    return 0
  }
}

/** 「同步到附注」的 builder 行：剔合计行，本期发生额 = 计提 − 转回（符号翻转在 builder 单点做） */
export function k11DisclosureSyncRows(rows: readonly K11DisclosureTabRow[]): K11DisclosureRow[] {
  return rows
    .filter((r) => !r.isTotal)
    .map((r) => ({ project: r.category, currentAmount: r.currentProvision - r.currentReversal, priorAmount: r.priorAmount }))
}
