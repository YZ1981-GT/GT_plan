/**
 * K1-1 审定表 — 致同 Excel 行结构定义
 *
 * 一、其他应收款（原值/坏账/净值）→ 单项 + 三组合
 * 二、账龄分布（原值/坏账/净值）→ **跟随项目账龄配置**（3年段 4 档 / 5年段 6 档 / 自定义 2~10 段）
 * 三、款项性质分布（原值/坏账/净值）→ 保证金/押金/备用金/往来款/其他
 *
 * 🔴 账龄段不再写死：`useAgingConfig(projectId,'K1')` 已是 K1-2 明细表、K1-10、两个披露
 * composable 的单一真源，但 K1-1 原先硬编码 `DEFAULT_K2_AGING_BUCKETS`（固定 6 档），
 * 且 `k1AdjudicationSync` 硬编码 5 年段的 6 个 segment key → 项目配 3 年段时 `over3`
 * 永远读不到（K1-1 凭空多 3 行空行、少一档金额）。现改为 `buildK1AgingRowDefs(segments)`。
 *
 * spec: .kiro/specs/k1-four-table-extraction-and-disclosure-alignment/ R5 / Property 5
 */
import { PRESET_SEGMENTS, type AgingSegment } from '@/composables/useAgingConfig'
import { DEFAULT_K2_AGING_BUCKETS } from './k1PolicyCrossHelpers'

export type K1AdjBlockKind = 'portfolio' | 'aging' | 'nature'

export interface K1AdjRowDef {
  rowKey: string
  label: string
  /** 从 K1-2 同步时的分类键 */
  syncKey?: string
  isSubtotal?: boolean
  linkSheet?: string
  linkHint?: string
}

export const K1_PORTFOLIO_ROW_DEFS: K1AdjRowDef[] = [
  { rowKey: 'r0', label: '单项计提', syncKey: 'individual' },
  { rowKey: 'r1', label: '账龄组合', syncKey: 'aging', linkSheet: 'K1-8', linkHint: '与 K1-8 账龄组合一致' },
  { rowKey: 'r2', label: '客户类型组合', syncKey: 'customer', linkSheet: 'K1-6', linkHint: '与 K1-6 组合划分一致' },
  { rowKey: 'r3', label: '其他组合', syncKey: 'other', linkSheet: 'K1-8' },
]

/** K1 默认账龄段（`DEFAULT_SUBJECT_PRESETS.K1 === 'FIVE_YEAR'`） */
export const K1_DEFAULT_AGING_SEGMENTS: AgingSegment[] = PRESET_SEGMENTS.FIVE_YEAR

/**
 * 由项目账龄段派生 K1-1「二、账龄分布」行定义。
 *
 * - `rowKey` 用 `a{index}`（历史 itemId 形态 `K1-1-aging-gross-a0-unadj`，不能改）
 * - `syncKey` = **段 key**（`within1` / `y1to2` / `over3` / `custom-0`…），
 *   聚合时按 key 取值而非按下标猜（Property 5）
 * - 段集合为空时回退 K1 默认 5 年段
 */
export function buildK1AgingRowDefs(
  segments?: readonly AgingSegment[] | null,
): K1AdjRowDef[] {
  const segs = segments && segments.length ? segments : K1_DEFAULT_AGING_SEGMENTS
  return [
    ...segs.map((seg, i) => ({
      rowKey: `a${i}`,
      label: seg.label,
      syncKey: seg.key,
    })),
    { rowKey: 'subtotal', label: '小计', isSubtotal: true },
  ]
}

/** 段 key 列表（供 `aggregateK12ForK11` 按 key 取值） */
export function k1AgingSegmentKeys(
  segments?: readonly AgingSegment[] | null,
): string[] {
  const segs = segments && segments.length ? segments : K1_DEFAULT_AGING_SEGMENTS
  return segs.map((s) => s.key)
}

/**
 * 默认账龄行定义（5 年段）。
 *
 * 保留为具名导出仅为兼容既有引用；**新代码请用 `buildK1AgingRowDefs(segments)`**，
 * 否则项目配 3 年段/自定义段时 K1-1 与 K1-2 档位不一致。
 */
export const K1_AGING_ROW_DEFS: K1AdjRowDef[] = buildK1AgingRowDefs(
  K1_DEFAULT_AGING_SEGMENTS,
)

export const K1_NATURE_ROW_DEFS: K1AdjRowDef[] = [
  { rowKey: 'n0', label: '保证金', syncKey: 'margin' },
  { rowKey: 'n1', label: '押金', syncKey: 'deposit' },
  { rowKey: 'n2', label: '备用金', syncKey: 'petty' },
  { rowKey: 'n3', label: '往来款', syncKey: 'intercompany' },
  { rowKey: 'n4', label: '其他', syncKey: 'other-nature' },
  { rowKey: 'subtotal', label: '小计', isSubtotal: true },
]

export const K1_PORTFOLIO_COUNT = K1_PORTFOLIO_ROW_DEFS.length
export const K1_AGING_COUNT = K1_AGING_ROW_DEFS.filter((r) => !r.isSubtotal).length
export const K1_NATURE_COUNT = K1_NATURE_ROW_DEFS.filter((r) => !r.isSubtotal).length

/**
 * 账龄档标签（默认 5 年段）。
 *
 * `DEFAULT_K2_AGING_BUCKETS` 是 K1-6 会计政策检查表的**损失率档位**常量，与项目账龄
 * 配置同为 5 年段字面 → 此处仅作默认值来源，实际渲染走 `buildK1AgingRowDefs`。
 */
export const K1_DEFAULT_AGING_LABELS: readonly string[] = DEFAULT_K2_AGING_BUCKETS

/** 款项性质 → 性质分布 syncKey */
export function classifyK1Nature(nature: string): string {
  const n = String(nature || '').trim()
  if (/保证金/.test(n)) return 'margin'
  if (/押金/.test(n)) return 'deposit'
  if (/备用金/.test(n)) return 'petty'
  if (/往来|代垫|关联/.test(n)) return 'intercompany'
  return 'other-nature'
}

/** K1-2 明细行 → 组合计提分类（无 AI 列时用 stage 近似） */
export function classifyK1Portfolio(stage: number): 'individual' | 'aging' {
  return stage === 3 ? 'individual' : 'aging'
}
