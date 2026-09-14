/**
 * G7 四表库 → 审定表 / 披露表预填（零 Vue 依赖纯函数）。
 *
 * 两条链路共用本模块：
 * 1. G7-1 审定表「从四表库带入未审数」：render 下发 `adjudication_prefill` → 本模块 seed → 行内存值
 * 2. 披露主表「从四表库带入」：render 下发 `tb_leaf_categories.buckets` → 本模块 seed → 披露行
 *
 * **核心设计：手工优先**
 * - 已有非空值（手工/历史录入）**不被覆盖**（除显式 overwrite）
 * - 无数据的格子保持 null/0（宁缺勿造）
 * - 四表命中的格子标注 `source` 属性供 UI 展示来源
 *
 * spec: g7-four-table-extraction-and-disclosure-alignment R2.1~2.6 / R3.1~3.3，Property 5 / 6
 */

import type { G7DisclosureRow, G7DisclosureValue } from '../g7-long-term-equity-main/disclosure/g7ListedDisclosureModel'

// ─── Types ──────────────────────────────────────────────────────────────────

/** 后端 render 下发的单桶预填数据 */
export interface G7PrefillBucket {
  label: string
  opening: number
  increase: number
  decrease: number
  closing: number
  codes: string[]
  roll_forward_ok: boolean
  from_buckets?: string[]
}

/** 后端 render 下发的完整预填结构 */
export interface G7AdjudicationPrefill {
  gross?: Record<string, G7PrefillBucket>
  impairment?: Record<string, G7PrefillBucket>
}

/** 审定表一行的可填字段 */
export interface AdjRowLike {
  id: string
  item: string
  openingUnadjusted: number
  closingUnadjusted: number
  /** 可选标注来源 */
  _source?: string
  [key: string]: unknown
}

export interface SeedResult {
  /** 被填充的行数 */
  filled: number
  /** 未填充（已有值/无数据）的行数 */
  skipped: number
  /** roll-forward 不平的桶 */
  warnings: string[]
}

export interface SeedOptions {
  /** true = 覆盖已有非空值（用户显式选择覆盖） */
  overwrite?: boolean
}

// ─── 审定表预填 ─────────────────────────────────────────────────────────────

/** 审定表分组 id → 预填桶键的映射 */
const ADJUDICATION_GROUP_MAP: Record<string, string[]> = {
  subsidiary: ['subsidiary'],
  joint_venture: ['jv'],
  associate: ['associate'],
  impairment: ['impairment'],
}

/**
 * 预览：列出四表预填会改动的行/格子，供确认对话框展示。
 */
export function previewSeedG7Adjudication(
  groups: Array<{ id: string; rows: AdjRowLike[] }>,
  prefill: G7AdjudicationPrefill | null | undefined,
  options?: SeedOptions,
): Array<{ groupId: string; rowId: string; field: string; oldValue: number; newValue: number }> {
  if (!prefill) return []
  const preview: Array<{ groupId: string; rowId: string; field: string; oldValue: number; newValue: number }> = []
  const overwrite = options?.overwrite ?? false

  for (const group of groups) {
    const bucketKeys = ADJUDICATION_GROUP_MAP[group.id]
    if (!bucketKeys) continue
    const source = group.id === 'impairment' ? prefill.impairment : prefill.gross
    if (!source) continue

    for (const bucketKey of bucketKeys) {
      const bucket = source[bucketKey === 'impairment' ? 'total' : bucketKey]
      if (!bucket) continue
      // 填第一行（多行分配待后续 spec，宁缺不乱分）
      const row = group.rows[0]
      if (!row) continue
      for (const [field, value] of [
        ['openingUnadjusted', bucket.opening],
        ['closingUnadjusted', bucket.closing],
      ] as const) {
        const old = Number((row as any)[field]) || 0
        if (!overwrite && old !== 0) continue
        if (value !== old) {
          preview.push({ groupId: group.id, rowId: row.id, field, oldValue: old, newValue: value })
        }
      }
    }
  }
  return preview
}

/**
 * 执行：把四表预填数据写入审定表行。
 *
 * **手工优先**：已有非空值不覆盖（除 overwrite=true）。
 * **宁缺勿造**：prefill 为空返回 `{filled:0, skipped:0, warnings:[]}`。
 */
export function seedG7AdjudicationFromPrefill(
  groups: Array<{ id: string; rows: AdjRowLike[] }>,
  prefill: G7AdjudicationPrefill | null | undefined,
  options?: SeedOptions,
): SeedResult {
  if (!prefill) return { filled: 0, skipped: 0, warnings: [] }
  const overwrite = options?.overwrite ?? false
  let filled = 0
  let skipped = 0
  const warnings: string[] = []

  for (const group of groups) {
    const bucketKeys = ADJUDICATION_GROUP_MAP[group.id]
    if (!bucketKeys) continue
    const source = group.id === 'impairment' ? prefill.impairment : prefill.gross
    if (!source) continue

    for (const bucketKey of bucketKeys) {
      const bucket = source[bucketKey === 'impairment' ? 'total' : bucketKey]
      if (!bucket) continue
      const row = group.rows[0]
      if (!row) continue
      let anyFilled = false
      for (const [field, value] of [
        ['openingUnadjusted', bucket.opening],
        ['closingUnadjusted', bucket.closing],
      ] as const) {
        const old = Number((row as any)[field]) || 0
        if (!overwrite && old !== 0) {
          skipped += 1
          continue
        }
        ;(row as any)[field] = value
        anyFilled = true
      }
      if (anyFilled) {
        row._source = `四表库 tb_balance ${bucket.codes.join('/')}`
        filled += 1
      }
      if (!bucket.roll_forward_ok) {
        warnings.push(`${bucket.label}: roll-forward 不平，请核对`)
      }
    }
  }
  // other 桶（变动性质汇总）→ 如果第 4 行（id 以 `-4` 结尾的第一组行 / 尾行）可用，填进去
  const otherBucket = prefill.gross?.other
  if (otherBucket) {
    const targetGroups = groups.filter(
      g => !['impairment', 'total'].includes(g.id),
    )
    // 找各分类组里的「第 4 行」（源模板第 4 行空白可扩行，其他循环用不到的占位行）
    for (const g of targetGroups) {
      // 简单策略：最后一行（不是小计/合计的数据行）
      const dataRows = g.rows.filter(r => !(r as any)._isSubtotal)
      const lastRow = dataRows[dataRows.length - 1]
      if (!lastRow) continue
      // 只写入第一个找到的空行
      if ((Number(lastRow.openingUnadjusted) || 0) === 0 && (Number(lastRow.closingUnadjusted) || 0) === 0) {
        if (otherBucket.opening !== 0 || otherBucket.closing !== 0) {
          lastRow.openingUnadjusted = otherBucket.opening
          lastRow.closingUnadjusted = otherBucket.closing
          lastRow.item = lastRow.item || otherBucket.label
          lastRow._source = `四表库 tb_balance ${otherBucket.codes.join('/')}`
          filled += 1
        }
        break
      }
    }
    if (!otherBucket.roll_forward_ok) {
      warnings.push(`${otherBucket.label}: roll-forward 不平，请核对`)
    }
  }
  return { filled, skipped, warnings }
}

// ─── 披露主表四表带入 ─────────────────────────────────────────────────────

/** 后端 `tb_leaf_categories.buckets` 中的单桶 */
export interface G7LeafBucketSlot {
  bucket: string
  label: string
  opening: number
  closing: number
  increase: number
  decrease: number
  codes: string[]
}

/**
 * 把四表库叶子桶写入披露主表行的指定列。
 *
 * 列映射（源模板主表 `A8:M23` / `A210:M222` 的列义与桶的对应）：
 * - `openingBook` / `opening`       ← bucket.opening
 * - `closingBook` / `closing`       ← bucket.closing
 * - `equityProfit`                  ← equity_profit.closing（变动性质桶，只填对应列）
 * - `oci`                           ← oci.closing
 * - `otherEquity`                   ← other_equity.closing
 * - `openingImpairment` / `closingImpairment` ← impairment bucket（单独段）
 *
 * **手工优先**：已有非空值不覆盖（除 overwrite）。
 * **只填四表能确定的列**：`追加投资`/`减少投资`/`宣告分派`/`其他` 四表推不出 → 不动。
 */
export function seedG7MovementFromLeafCategories(
  rows: G7DisclosureRow[],
  buckets: Record<string, G7LeafBucketSlot> | null | undefined,
  options?: SeedOptions,
): { filled: number; skipped: number } {
  if (!buckets || !rows?.length) return { filled: 0, skipped: 0 }
  const overwrite = options?.overwrite ?? false
  let filled = 0
  let skipped = 0

  function tryWrite(row: G7DisclosureRow, key: string, value: number | null): boolean {
    if (value == null || value === 0) return false
    const old = row.values[key]
    if (!overwrite && old != null && old !== 0 && old !== '') {
      skipped += 1
      return false
    }
    row.values[key] = value
    return true
  }

  // 备抵桶 → 期初/期末列（不管在哪行，直接找合计行或最后一行）
  const impairment = buckets.impairment
  if (impairment) {
    const totalRow = rows.find(r => r.kind === 'total') ?? rows[rows.length - 1]
    if (totalRow) {
      // 减值准备期初/期末是独立列
      if (tryWrite(totalRow, 'openingImpairment', impairment.opening)) filled += 1
      if (tryWrite(totalRow, 'closingImpairment', impairment.closing)) filled += 1
      totalRow.source = totalRow.source || `四表库 ${impairment.codes.join('/')}`
    }
  }

  // 类别桶 → 对应分组的期初/期末
  for (const [bucket, slot] of Object.entries(buckets)) {
    if (bucket === 'impairment') continue
    if (slot.opening === 0 && slot.closing === 0) continue
    // 按桶名/label 找行
    const targetRow = rows.find(
      r => r.kind === 'data' && (
        (r as any)._bucket === bucket
        || r.label.includes(slot.label)
        || r.source?.includes(bucket)
      ),
    ) ?? rows.find(r => r.kind === 'data' && !r.label && !r.values?.openingBook)
    if (!targetRow) { skipped += 1; continue }
    let anyFilled = false
    // 主表 key: listed=openingBook/closingBook; soe=opening/closing
    for (const k of ['openingBook', 'opening']) {
      if (k in targetRow.values && tryWrite(targetRow, k, slot.opening)) anyFilled = true
    }
    for (const k of ['closingBook', 'closing']) {
      if (k in targetRow.values && tryWrite(targetRow, k, slot.closing)) anyFilled = true
    }
    if (anyFilled) {
      targetRow.source = `四表库 tb_balance ${slot.codes.join('/')}`
      filled += 1
    }
  }

  // 变动性质桶 → 主表对应变动列（不落行、落列）
  const equityProfit = buckets.equity_profit
  const oci = buckets.oci
  const otherEquity = buckets.other_equity
  const totalRow = rows.find(r => r.kind === 'total')
  if (totalRow) {
    if (equityProfit && tryWrite(totalRow, 'equityProfit', equityProfit.closing)) filled += 1
    if (oci && tryWrite(totalRow, 'oci', oci.closing)) filled += 1
    if (otherEquity && tryWrite(totalRow, 'otherEquity', otherEquity.closing)) filled += 1
  }

  return { filled, skipped }
}
