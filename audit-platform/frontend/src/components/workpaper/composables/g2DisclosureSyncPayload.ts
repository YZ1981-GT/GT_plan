/**
 * G2 披露 → disclosure_notes sync payload
 * 子表名对齐 note_template：应收利息分类 / 重要逾期利息 / 坏账准备计提情况
 *   国企 §八、9 · 上市 §五、8
 */
import type { G2DisclosureVariant } from './g2NoteSectionMap'
import {
  G2_DISCLOSURE_SHEET_NAME,
  G2_NOTE_SECTION,
  isG2DisclosureApplicable,
  resolveG2CurrentStandard,
} from './g2NoteSectionMap'
import {
  eclRowTotal,
  overdueTotal,
  recomputeClassDerived,
  recomputeEclClosing,
  type G2SoeClassRow,
  type G2SoeEclRow,
  type G2SoeOverdueRow,
} from './g2SoeDisclosureRows'

import type { ColumnDef } from './disclosureColumnDefs'

export interface G2SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  /** 列头元数据（disclosure-table-sync-convergence）：label 取自 G2TabDisclosure el-table-column */
  columns?: Record<string, ColumnDef[]>
}

// G2 三张子表列头：逐字取自 G2TabDisclosureSOE/Listed el-table-column（源对齐）
const G2_COLUMNS: Record<string, ColumnDef[]> = {
  应收利息分类: [
    { key: 'label', label: '项目', is_label: true },
    { key: 'end_balance', label: '期末余额', format: 'amount' },
    { key: 'prior_balance', label: '期初余额', format: 'amount' },
  ],
  重要逾期利息: [
    { key: 'borrower', label: '借款单位', is_label: true },
    { key: 'end_balance', label: '期末余额', format: 'amount' },
    { key: 'overdue_months', label: '逾期时间（月）' },
    { key: 'overdue_reason', label: '逾期原因' },
    { key: 'impairment_basis', label: '是否发生减值及判断依据' },
  ],
  坏账准备计提情况: [
    { key: 'label', label: '坏账准备', is_label: true },
    { key: 'stage1', label: '第一阶段', format: 'amount' },
    { key: 'stage2', label: '第二阶段', format: 'amount' },
    { key: 'stage3', label: '第三阶段', format: 'amount' },
    { key: 'total', label: '合计', format: 'amount' },
  ],
}

export interface G2SoeSyncSnapshot {
  classRows: G2SoeClassRow[]
  overdueRows: G2SoeOverdueRow[]
  eclRows: G2SoeEclRow[]
  auditNote: string
}

export function buildG2SoeSubTableData(
  snap: G2SoeSyncSnapshot,
): Record<string, Record<string, unknown>[]> {
  const classRows = recomputeClassDerived(snap.classRows)
  const eclRows = recomputeEclClosing(snap.eclRows)
  const overdueRows = snap.overdueRows.filter((r) => r.borrower || r.endAmount)

  return {
    应收利息分类: classRows.map((r) => ({
      label: r.label,
      end_balance: r.endAmount,
      prior_balance: r.priorAmount,
      row_key: r.rowKey,
      row_type: r.kind,
      is_total: r.kind === 'total' || r.kind === 'subtotal',
    })),
    重要逾期利息: [
      ...overdueRows.map((r) => ({
        borrower: r.borrower || '（未命名）',
        end_balance: r.endAmount,
        overdue_months: r.overdueMonths === '' ? null : r.overdueMonths,
        overdue_reason: r.overdueReason,
        impairment_basis: r.impairmentBasis,
      })),
      {
        label: '合计',
        end_balance: overdueTotal(overdueRows),
        is_total: true,
      },
    ],
    坏账准备计提情况: eclRows
      .filter((r) => r.kind !== 'header')
      .map((r) => ({
        label: r.label,
        stage1: r.stage1,
        stage2: r.stage2,
        stage3: r.stage3,
        total: eclRowTotal(r),
        row_key: r.rowKey,
        is_closing: r.rowKey === 'closing',
      })),
    _note_texts: [{ section: 'soe-audit-note', text: snap.auditNote }],
  }
}

export function buildG2SoeSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snap: G2SoeSyncSnapshot,
): G2SyncFromWorkpaperPayload[] {
  const variant: G2DisclosureVariant = 'soe'
  if (!isG2DisclosureApplicable(variant, applicableStandards)) return []
  return [
    {
      wp_id: wpId,
      sheet_name: G2_DISCLOSURE_SHEET_NAME.soe,
      section_id: G2_NOTE_SECTION.soe,
      current_standard: resolveG2CurrentStandard(variant, applicableStandards),
      sub_table_data: buildG2SoeSubTableData(snap),
      columns: G2_COLUMNS,
    },
  ]
}

/** 上市：子表结构与国企相同（应收利息分类 + 重要逾期利息），但**不含**「坏账准备计提情况」
 * —— 该表只存在于国企 §八、9，上市 §五、8 模板无此表（推了会成孤儿子表）。
 * 🔴 同时用 `_removed_table_keys` 清理曾经误推的历史数据（spec: g-cycle Task 6.2）。
 */
export function buildG2ListedSubTableData(
  snap: G2SoeSyncSnapshot,
): Record<string, Record<string, unknown>[]> {
  const data = buildG2SoeSubTableData(snap)
  // 从国企构建结果中移除「坏账准备计提情况」（listed 模板无此表）
  const { '坏账准备计提情况': _removed, ...withoutEcl } = data
  return {
    ...withoutEcl,
    _note_texts: [{ section: 'listed-audit-note', text: snap.auditNote }],
    _removed_table_keys: ['坏账准备计提情况'],
  } as any
}

export function buildG2ListedSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snap: G2SoeSyncSnapshot,
): G2SyncFromWorkpaperPayload[] {
  const variant: G2DisclosureVariant = 'listed'
  if (!isG2DisclosureApplicable(variant, applicableStandards)) return []
  return [
    {
      wp_id: wpId,
      sheet_name: G2_DISCLOSURE_SHEET_NAME.listed,
      section_id: G2_NOTE_SECTION.listed,
      current_standard: resolveG2CurrentStandard(variant, applicableStandards),
      sub_table_data: buildG2ListedSubTableData(snap),
      columns: G2_COLUMNS,
    },
  ]
}
