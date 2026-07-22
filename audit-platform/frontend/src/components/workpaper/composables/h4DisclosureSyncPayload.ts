/**
 * H4 披露 → disclosure_notes sync payload
 *
 * 上市：仅推送「（2）工程物资」分类子表至附注「五、23」
 * （依赖后端 sub_table_data 按 key 浅合并，不覆盖 H2 已推送的在建工程子表）
 */
import {
  H2_DISCLOSURE_SHEET_NAME,
  H2_LISTED_SUBTABLE,
  H2_NOTE_SECTION,
  isH2DisclosureApplicable,
  resolveH2CurrentStandard,
} from './h2NoteSectionMap'
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
  }]
}
