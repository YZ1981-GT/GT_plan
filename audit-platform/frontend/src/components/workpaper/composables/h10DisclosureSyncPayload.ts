/**
 * H10 披露 → disclosure_notes sync payload
 * 主表对齐 note_template「资产处置收益」；上市另推试运行明细子表（净额=收入−成本）。
 * 空行不推送。
 */
import { parseNum } from './useH10FormulaEngine'
import {
  H10_DISCLOSURE_LISTED_ROWS,
  H10_DISCLOSURE_SOE_ROWS,
  H10_TRIAL_DETAIL_ROWS,
} from './h10Constants'
import {
  H10_DISCLOSURE_SHEET_NAME,
  H10_MAIN_SUBTABLE,
  H10_NOTE_SECTION,
  H10_TRIAL_SUBTABLE,
  isH10DisclosureApplicable,
  resolveH10CurrentStandard,
  type H10DisclosureVariant,
} from './h10NoteSectionMap'
import type { H10DisclosureRow, H10TrialDetailRow } from './useH10Disclosure'

import type { ColumnDef } from './disclosureColumnDefs'

export interface H10SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  /** 列头元数据（disclosure-table-sync-convergence）：label 取自 H10TabDisclosureBase el-table-column */
  columns?: Record<string, ColumnDef[]>
}

// 资产处置收益列头：逐字取自 H10TabDisclosureBase（项目/本期发生额/上期发生额[/非经常性损益]）
const H10_MAIN_BASE_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'current_amount', label: '本期发生额', format: 'amount' },
  { key: 'prior_amount', label: '上期发生额', format: 'amount' },
]
const H10_SOE_NONRECURRING: ColumnDef = {
  key: 'non_recurring_amount', label: '计入当期非经常性损益的金额', format: 'amount',
}
// 试运行销售明细（推送净额，本期/上期）
const H10_TRIAL_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'current_amount', label: '本期发生额', format: 'amount' },
  { key: 'prior_amount', label: '上期发生额', format: 'amount' },
]

/** 按 variant 构造 H10 各子表列头（键与 buildH10SubTableData 输出一致）。 */
export function buildH10SubTableColumns(
  variant: H10DisclosureVariant,
): Record<string, ColumnDef[]> {
  const mainCols = variant === 'soe'
    ? [...H10_MAIN_BASE_COLUMNS, H10_SOE_NONRECURRING]
    : [...H10_MAIN_BASE_COLUMNS]
  const cols: Record<string, ColumnDef[]> = {
    [H10_MAIN_SUBTABLE[variant]]: mainCols,
  }
  if (variant === 'listed') {
    // 第二张试运行明细表键 `项  目__trial`（_trial_detail 为 `_` 前缀元数据，投影器自动跳过）
    cols[`${H10_TRIAL_SUBTABLE}__trial`] = H10_TRIAL_COLUMNS
  }
  return cols
}

export interface H10SyncSnapshot {
  rows: H10DisclosureRow[]
  trialRows: H10TrialDetailRow[]
  noteText: string
  adjudicatedAmount?: number | null
}

/** 附注模板行标签（与 note_template_listed/soe 一致；债务重组为扩展行） */
export const H10_NOTE_TEMPLATE_LABEL: Record<string, { listed?: string; soe?: string }> = {
  hfs_disposal: {
    listed: '持有待售的非流动资产（处置组）处置利得（损失以“-”填列）',
    soe: '持有待售的非流动资产（处置组）处置利得',
  },
  fixed_asset_disposal: {
    listed: '固定资产处置利得（损失以“-”填列）',
    soe: '固定资产处置利得',
  },
  construction_disposal: {
    listed: '在建工程处置利得（损失以“-”填列）',
    soe: '在建工程处置利得',
  },
  productive_bio_disposal: {
    listed: '生产性生物资产处置利得（损失以“-”填列）',
    soe: '生产性生物资产处置利得',
  },
  intangible_disposal: {
    listed: '无形资产处置利得（损失以“-”填列）',
    soe: '无形资产处置利得',
  },
  debt_restructuring_disposal: {
    listed: '债务重组中因处置非流动资产产生的利得（损失以“-”填列）',
    soe: '债务重组中因处置非流动资产产生的利得',
  },
  non_monetary_exchange: {
    listed: '非货币性资产交换产生的利得（损失以“-”填列）',
    soe: '非货币性资产交换产生的利得',
  },
  rou_disposal: {
    listed: '使用权资产处置利得（损失以“-”填列）',
    soe: '使用权资产处置利得',
  },
  oil_gas_disposal: {
    listed: '油气资产处置利得（损失以“-”填列）',
    soe: '油气资产处置利得',
  },
  trial_operation_sales: {
    listed: '试运行销售损益',
    soe: '试运行销售损益',
  },
  fixed_asset_trial: { listed: '固定资产试运行销售' },
  rd_sample_sales: { listed: '研发样品销售' },
}

function hasAmount(current: number, prior: number, extra = 0): boolean {
  return Math.abs(current) > 0.005 || Math.abs(prior) > 0.005 || Math.abs(extra) > 0.005
}

export function resolveH10NoteTemplateLabel(
  rowKey: string,
  variant: H10DisclosureVariant,
  fallbackLabel?: string,
): string {
  const mapped = H10_NOTE_TEMPLATE_LABEL[rowKey]?.[variant]
  if (mapped) return mapped
  return String(fallbackLabel ?? rowKey).trim()
}

function mapAmountRow(
  label: string,
  rowKey: string,
  currentAmount: number,
  priorAmount: number,
  extra?: Record<string, unknown>,
): Record<string, unknown> {
  return {
    label: label.trim(),
    row_key: rowKey,
    current_amount: currentAmount,
    prior_amount: priorAmount,
    row_type: 'data',
    ...extra,
  }
}

export function buildH10MainSubTableRows(
  rows: readonly H10DisclosureRow[],
  variant: H10DisclosureVariant,
): Record<string, unknown>[] {
  const dataRows = rows
    .filter((r) => hasAmount(r.currentAmount, r.priorAmount, parseNum(r.nonRecurringAmount)))
    .map((r) => {
      const label = resolveH10NoteTemplateLabel(r.rowKey, variant, r.label)
      return mapAmountRow(
        label,
        r.rowKey,
        parseNum(r.currentAmount),
        parseNum(r.priorAmount),
        {
          ...(variant === 'soe'
            ? { non_recurring_amount: parseNum(r.nonRecurringAmount) }
            : {}),
          ...(r.remark?.trim() ? { remark: r.remark.trim() } : {}),
        },
      )
    })

  const currentTotal = rows.reduce((s, r) => s + parseNum(r.currentAmount), 0)
  const priorTotal = rows.reduce((s, r) => s + parseNum(r.priorAmount), 0)
  const nonRecurringTotal = variant === 'soe'
    ? rows.reduce((s, r) => s + parseNum(r.nonRecurringAmount), 0)
    : undefined

  return [
    ...dataRows,
    {
      label: '合计',
      current_amount: currentTotal,
      prior_amount: priorTotal,
      ...(nonRecurringTotal != null ? { non_recurring_amount: nonRecurringTotal } : {}),
      is_total: true,
      row_type: 'total' as const,
    },
  ]
}

/** 试运行明细：附注模板仅本期/上期，推送净额=收入−成本 */
export function buildH10TrialSubTableRows(
  trialRows: readonly H10TrialDetailRow[],
): Record<string, unknown>[] {
  const dataRows = trialRows
    .map((r) => {
      const current = parseNum(r.currentIncome) - parseNum(r.currentCost)
      const prior = parseNum(r.priorIncome) - parseNum(r.priorCost)
      return { r, current, prior }
    })
    .filter(({ current, prior }) => hasAmount(current, prior))
    .map(({ r, current, prior }) =>
      mapAmountRow(
        resolveH10NoteTemplateLabel(r.rowKey, 'listed', r.label),
        r.rowKey,
        current,
        prior,
        {
          current_income: parseNum(r.currentIncome),
          current_cost: parseNum(r.currentCost),
          prior_income: parseNum(r.priorIncome),
          prior_cost: parseNum(r.priorCost),
        },
      ),
    )

  if (!dataRows.length) return []

  const currentTotal = trialRows.reduce(
    (s, r) => s + parseNum(r.currentIncome) - parseNum(r.currentCost),
    0,
  )
  const priorTotal = trialRows.reduce(
    (s, r) => s + parseNum(r.priorIncome) - parseNum(r.priorCost),
    0,
  )

  return [
    ...dataRows,
    {
      label: '合计',
      current_amount: currentTotal,
      prior_amount: priorTotal,
      is_total: true,
      row_type: 'total' as const,
    },
  ]
}

function buildNoteTexts(snap: H10SyncSnapshot): Array<Record<string, string>> {
  const note = snap.noteText.trim()
  if (!note) return []
  return [{ section: 'disclosure-note', text: note }]
}

export function buildH10SubTableData(
  snap: H10SyncSnapshot,
  variant: H10DisclosureVariant,
): Record<string, Record<string, unknown>[]> {
  const result: Record<string, Record<string, unknown>[]> = {
    [H10_MAIN_SUBTABLE[variant]]: buildH10MainSubTableRows(snap.rows, variant),
  }

  if (variant === 'listed') {
    const trial = buildH10TrialSubTableRows(snap.trialRows)
    // 模板两张表同名「项  目」：第二张用 trial 后缀键，后端按数组顺序消费时可并存
    if (trial.length) {
      result[`${H10_TRIAL_SUBTABLE}__trial`] = trial
      // 兼容仅识别「项  目」的消费者：若主表已占用，附加 _trial_detail
      result._trial_detail = trial
    }
  }

  const noteTexts = buildNoteTexts(snap)
  if (noteTexts.length) result._note_texts = noteTexts
  return result
}

export function buildH10SyncPayloads(
  wpId: string,
  variant: H10DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
  snap: H10SyncSnapshot,
): H10SyncFromWorkpaperPayload[] {
  if (!isH10DisclosureApplicable(variant, applicableStandards)) return []
  return [{
    wp_id: wpId,
    sheet_name: H10_DISCLOSURE_SHEET_NAME[variant],
    section_id: H10_NOTE_SECTION[variant],
    current_standard: resolveH10CurrentStandard(variant, applicableStandards),
    sub_table_data: buildH10SubTableData(snap, variant),
    columns: buildH10SubTableColumns(variant),
  }]
}

export function h10DisclosureDefKeys(variant: H10DisclosureVariant): string[] {
  const defs = variant === 'listed' ? H10_DISCLOSURE_LISTED_ROWS : H10_DISCLOSURE_SOE_ROWS
  return defs.map((d) => d.rowKey)
}

export function h10TrialDefKeys(): string[] {
  return H10_TRIAL_DETAIL_ROWS.map((d) => d.rowKey)
}
