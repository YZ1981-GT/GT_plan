/**
 * H4 披露 → disclosure_notes sync payload
 *
 * 上市：仅推送「（2）工程物资」分类子表至附注「五、23」
 * （依赖后端 sub_table_data 按 key 浅合并，不覆盖 H2 已推送的在建工程子表）
 */
import type { ColumnDef } from './disclosureColumnDefs'
import {
  H2_DISCLOSURE_SHEET_NAME,
  H2_LISTED_SUBTABLE,
  H2_NOTE_SECTION,
  isH2DisclosureApplicable,
  resolveH2CurrentStandard,
} from './h2NoteSectionMap'
import { buildH2ListedColumns } from './h2DisclosureSyncPayload'
import {
  h4ListedMaterialsGross,
  h4ListedMaterialsNet,
  num,
  type H4ListedMaterialRow,
} from './h4ListedDisclosureModel'

export interface H4SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  /**
   * 列头元数据（disclosure-columns-coverage-rollout R1）。
   *
   * 🔴 **复用 H2 的定义，不另造**：H4 推的是 H2 章节（五、23）里的子表
   * （`工程物资` 分类表 + 顺带勾稽 `在建工程` 汇总表的工程物资行），两处写同一张表；
   * 各造一份列头必然分叉（label 漂移 → 附注列头随最后一次同步跳变）。
   */
  columns?: Record<string, ColumnDef[]>
}

/**
 * 从 H2 上市列头里挑出本次实际推送的子表（Property 1：columns 键 ≡ 数据键）。
 *
 * `existingSubTableData` 里的键同样来自 H2 自己的推送，故都能在 H2 列头映射中找到；
 * 找不到定义的键**不臆造列头**（宁缺勿造），由覆盖守卫/契约测试暴露。
 */
function pickH4ListedColumns(sub: Record<string, unknown>): Record<string, ColumnDef[]> {
  const all = buildH2ListedColumns()
  const out: Record<string, ColumnDef[]> = {}
  for (const key of Object.keys(sub)) {
    if (key.startsWith('_')) continue
    const defs = all[key]
    if (defs) out[key] = defs
  }
  return out
}

export interface H4ListedSyncSnapshot {
  materials: H4ListedMaterialRow[]
  noteText?: string
}

/** 构建工程物资分类行（含小计空白行语义由附注模板处理；此处推送分类+减值+合计） */
export function buildH4ListedMaterialsSubTable(
  materials: H4ListedMaterialRow[],
): Record<string, unknown>[] {
  const rows: Record<string, unknown>[] = materials.map((r) => ({
    label: r.label,
    end_balance: r.isDeduction ? -num(r.endBalance) : num(r.endBalance),
    prior_balance: r.isDeduction ? -num(r.priorBalance) : num(r.priorBalance),
    is_deduction: !!r.isDeduction,
  }))
  const gross = h4ListedMaterialsGross(materials)
  rows.splice(materials.filter((r) => !r.isDeduction).length, 0, {
    label: '',
    end_balance: gross.endBalance,
    prior_balance: gross.priorBalance,
    is_subtotal: true,
  })
  const net = h4ListedMaterialsNet(materials)
  rows.push({
    label: '合计',
    end_balance: net.endBalance,
    prior_balance: net.priorBalance,
    is_total: true,
  })
  return rows
}

/**
 * 若已有「在建工程」汇总表，同步刷新其中「工程物资」行净值，
 * 与分类表合计勾稽。
 */
export function patchListedSummaryMaterialsRow(
  existingSub: Record<string, unknown>,
  materials: H4ListedMaterialRow[],
): Record<string, unknown> {
  const key = H2_LISTED_SUBTABLE.summary
  const raw = existingSub[key]
  if (!Array.isArray(raw)) return existingSub
  const net = h4ListedMaterialsNet(materials)
  const next = raw.map((row: any) => {
    const label = String(row?.label ?? row?.name ?? '')
    if (label.includes('工程物资') && !label.includes('减值')) {
      return {
        ...row,
        end_balance: net.endBalance,
        prior_balance: net.priorBalance,
      }
    }
    return row
  })
  return { ...existingSub, [key]: next }
}

export function buildH4ListedSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  state: H4ListedSyncSnapshot,
  opts?: { existingSubTableData?: Record<string, unknown> },
): H4SyncFromWorkpaperPayload[] {
  if (!isH2DisclosureApplicable('listed', applicableStandards)) return []
  const matKey = H2_LISTED_SUBTABLE.materials
  let sub: Record<string, unknown> = {
    ...(opts?.existingSubTableData || {}),
    [matKey]: buildH4ListedMaterialsSubTable(state.materials),
  }
  sub = patchListedSummaryMaterialsRow(sub, state.materials)
  if (state.noteText?.trim()) {
    sub._note_texts = [
      { section: 'h4-listed-materials', title: '（2）工程物资', text: state.noteText.trim() },
    ] as unknown as Record<string, unknown>[]
  }
  return [{
    wp_id: wpId,
    sheet_name: H2_DISCLOSURE_SHEET_NAME.listed,
    section_id: H2_NOTE_SECTION.listed,
    current_standard: resolveH2CurrentStandard('listed', applicableStandards),
    sub_table_data: sub as Record<string, Record<string, unknown>[]>,
    columns: pickH4ListedColumns(sub),
  }]
}
