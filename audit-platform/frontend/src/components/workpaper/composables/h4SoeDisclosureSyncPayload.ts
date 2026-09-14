/**
 * H4 国企披露 → disclosure_notes sync payload
 *
 * 推送到 §八、23 在建工程（与 H2 共享章节）：
 * - 子表「在建工程」的汇总行（在建工程 / 工程物资 / 合计）
 * - 列定义复用 H2 SOE 章节的列结构（6 列两级表头：期末/期初 × 账面余额/减值准备/账面价值）
 *
 * 依赖后端 sub_table_data 按 key 浅合并，不覆盖 H2 已推送的（1）（2）（3）明细子表。
 */
import {
  H2_DISCLOSURE_SHEET_NAME,
  H2_NOTE_SECTION,
  H2_SOE_SUBTABLE,
  isH2DisclosureApplicable,
  resolveH2CurrentStandard,
} from './h2NoteSectionMap'
import { buildH2SoeColumns } from './h2DisclosureSyncPayload'
import {
  h4SoeSummaryTotal,
  num,
  soeCarrying,
  type H4SoeSummaryRow,
} from './h4SoeDisclosureModel'
import type { ColumnDef } from './disclosureColumnDefs'

export interface H4SoeSyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  columns?: Record<string, ColumnDef[]>
  _note_texts?: Array<{ section: string; title: string; text: string }>
}

/**
 * §八、23 汇总表列定义（两级表头：期末余额/期初余额 × 账面余额·减值准备·账面价值）。
 *
 * 🔴 **直接复用 H2 的定义，不另造一份**：H2 与 H4 推的是**同一张**子表
 * （`H2_SOE_SUBTABLE.summary`，H2 负责「在建工程」行、H4 负责「工程物资」行），
 * 而 `_sub_table_columns` 由最后一次同步整体覆盖 —— 各造一份必然分叉
 * （曾实测差异：H4 这份缺 `format:'amount'` → 附注列格式随最后同步方跳变）。
 * 上市侧早已是这个做法（`pickH4ListedColumns` 从 `buildH2ListedColumns()` 取）。
 */
export function buildH4SoeColumns(): Record<string, ColumnDef[]> {
  const key = H2_SOE_SUBTABLE.summary
  return { [key]: buildH2SoeColumns()[key] }
}

/** 构建汇总表行（在建工程 / 工程物资 / 合  计） */
function buildSummarySubTable(rows: H4SoeSummaryRow[]): Record<string, unknown>[] {
  const result: Record<string, unknown>[] = rows.map((r) => ({
    label: r.label,
    end_book: num(r.endBook),
    end_impairment: num(r.endImpairment),
    end_carrying: soeCarrying(r.endBook, r.endImpairment),
    begin_book: num(r.beginBook),
    begin_impairment: num(r.beginImpairment),
    begin_carrying: soeCarrying(r.beginBook, r.beginImpairment),
  }))
  const tot = h4SoeSummaryTotal(rows)
  result.push({
    // 🔴 附注模板 §八、23 汇总表合计行字面是「合计」（无空格），H2 载荷亦推「合计」。
    //    源模板底稿 UI 写「合  计」（两空格）属底稿侧字面，不可带进附注 ——
    //    H2/H4 推同一张表，字面不一致会让合计行随最后同步方跳变。
    label: '合计',
    end_book: tot.endBook,
    end_impairment: tot.endImpairment,
    end_carrying: tot.endCarrying,
    begin_book: tot.beginBook,
    begin_impairment: tot.beginImpairment,
    begin_carrying: tot.beginCarrying,
    is_total: true,
  })
  return result
}

export interface H4SoeSyncSnapshot {
  summary: H4SoeSummaryRow[]
  noteText?: string
}

export function buildH4SoeSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  state: H4SoeSyncSnapshot,
): H4SoeSyncPayload[] {
  if (!isH2DisclosureApplicable('soe', applicableStandards)) return []

  const sub: Record<string, Record<string, unknown>[]> = {
    [H2_SOE_SUBTABLE.summary]: buildSummarySubTable(state.summary),
  }

  const payload: H4SoeSyncPayload = {
    wp_id: wpId,
    sheet_name: H2_DISCLOSURE_SHEET_NAME.soe,
    section_id: H2_NOTE_SECTION.soe,
    current_standard: resolveH2CurrentStandard('soe', applicableStandards),
    sub_table_data: sub,
    columns: buildH4SoeColumns(),
  }

  if (state.noteText?.trim()) {
    ;(payload as any)._note_texts = [
      { section: 'h4-soe-cip', title: '在建工程说明', text: state.noteText.trim() },
    ]
  }

  return [payload]
}
