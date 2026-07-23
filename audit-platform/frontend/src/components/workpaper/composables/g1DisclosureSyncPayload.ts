/**
 * G1 披露 → disclosure_notes sync payload
 * 子表名对齐 note_template_soe §八、2 / §八、3（及上市五、2 / 五、3）
 */
import type { G1DisclosureVariant } from './g1NoteSectionMap'
import {
  G1_DISCLOSURE_SHEET_NAME,
  G1_NOTE_SECTION,
  isG1DisclosureApplicable,
  resolveG1CurrentStandard,
} from './g1NoteSectionMap'
import type { G1SoeDerivativeRow, G1SoeTradingRow } from './g1SoeDisclosureRows'
import { tradingTotal } from './g1SoeDisclosureRows'
import type {
  G1DiscAmountRow,
  G1DiscAmortRow,
  G1DiscHierarchyRow,
  G1DiscInputRow,
  G1DiscL3RollRow,
} from './g1DisclosureItems'
import type { ColumnDef } from './disclosureColumnDefs'

export interface G1SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  /** 列头元数据（disclosure-table-sync-convergence）：label 取自 G1TabDisclosure el-table-column */
  columns?: Record<string, ColumnDef[]>
}

// SOE 子表英文键 → 源对齐列头（取自 G1TabDisclosureSOE）
const G1_SOE_TRADING_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'end_fair_value', label: '期末公允价值', format: 'amount' },
  { key: 'prior_fair_value', label: '期初公允价值', format: 'amount' },
]
const G1_SOE_DERIVATIVE_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'end_balance', label: '期末余额', format: 'amount' },
  { key: 'prior_balance', label: '期初余额', format: 'amount' },
  { key: 'reason', label: '产生原因 / 备注' },
]

// 上市子表：行键即中文列名（项目/内容/说明为标签列），逐字对齐 buildG1ListedSubTableData
const G1_LISTED_COLUMNS: Record<string, ColumnDef[]> = {
  交易性金融资产分类: [
    { key: '项目', label: '项目', is_label: true },
    { key: '期末余额', label: '期末余额', format: 'amount' },
    { key: '上年年末余额', label: '上年年末余额', format: 'amount' },
    { key: '备注', label: '备注' },
  ],
  指定理由: [{ key: '说明', label: '说明', is_label: true }],
  衍生金融资产: [
    { key: '项目', label: '项目', is_label: true },
    { key: '期末余额', label: '期末余额', format: 'amount' },
    { key: '上年年末余额', label: '上年年末余额', format: 'amount' },
  ],
  衍生说明: [{ key: '说明', label: '说明', is_label: true }],
  公允价值层次: [
    { key: '项目', label: '项目', is_label: true },
    { key: '第一层次', label: '第一层次', format: 'amount' },
    { key: '第二层次', label: '第二层次', format: 'amount' },
    { key: '第三层次', label: '第三层次', format: 'amount' },
    { key: '合计', label: '合计', format: 'amount' },
  ],
  估值输入值: [
    { key: '内容', label: '内容', is_label: true },
    { key: '期末公允价值', label: '期末公允价值', format: 'amount' },
    { key: '估值技术', label: '估值技术' },
    { key: '输入值', label: '输入值' },
    { key: '范围', label: '范围' },
    { key: '层次', label: '层次' },
  ],
  第三层次调节: [
    { key: '项目', label: '项目', is_label: true },
    { key: '期初余额', label: '期初余额', format: 'amount' },
    { key: '转入', label: '转入', format: 'amount' },
    { key: '转出', label: '转出', format: 'amount' },
    { key: '计入损益', label: '计入损益', format: 'amount' },
    { key: '计入OCI', label: '计入OCI', format: 'amount' },
    { key: '购买', label: '购买', format: 'amount' },
    { key: '发行', label: '发行', format: 'amount' },
    { key: '出售', label: '出售', format: 'amount' },
    { key: '结算', label: '结算', format: 'amount' },
    { key: '期末余额', label: '期末余额', format: 'amount' },
    { key: '仍持有未实现损益', label: '仍持有未实现损益', format: 'amount' },
  ],
  非以公允价值计量项目: [
    { key: '项目', label: '项目', is_label: true },
    { key: '账面价值', label: '账面价值', format: 'amount' },
    { key: '第一层次', label: '第一层次', format: 'amount' },
    { key: '第二层次', label: '第二层次', format: 'amount' },
    { key: '第三层次', label: '第三层次', format: 'amount' },
    { key: '备注', label: '备注' },
  ],
  附注说明: [{ key: '说明', label: '说明', is_label: true }],
}

export interface G1SoeSyncSnapshot {
  tradingRows: G1SoeTradingRow[]
  derivativeRows: G1SoeDerivativeRow[]
  fvBasisNote: string
  derivativeTipNote: string
  auditNote: string
}

export function buildG1SoeTradingSubTableData(
  snap: G1SoeSyncSnapshot,
): Record<string, Record<string, unknown>[]> {
  const total = tradingTotal(snap.tradingRows)
  return {
    交易性金融资产: [
      ...snap.tradingRows.map((r) => ({
        label: r.label,
        end_fair_value: r.endAmount,
        prior_fair_value: r.priorAmount,
        row_key: r.rowKey,
        indent: r.indent,
      })),
      {
        label: '合计',
        end_fair_value: total.endAmount,
        prior_fair_value: total.priorAmount,
        is_total: true,
      },
    ],
    _note_texts: [
      { section: 'soe-fv-basis', text: snap.fvBasisNote },
      { section: 'soe-audit-note', text: snap.auditNote },
    ],
  }
}

export function buildG1SoeDerivativeSubTableData(
  snap: G1SoeSyncSnapshot,
): Record<string, Record<string, unknown>[]> {
  const endAmount = snap.derivativeRows.reduce((s, r) => s + r.endAmount, 0)
  const priorAmount = snap.derivativeRows.reduce((s, r) => s + r.priorAmount, 0)
  return {
    衍生金融资产: [
      ...snap.derivativeRows.map((r) => ({
        label: r.label || '（未命名）',
        end_balance: r.endAmount,
        prior_balance: r.priorAmount,
        reason: r.reason,
      })),
      {
        label: '合计',
        end_balance: endAmount,
        prior_balance: priorAmount,
        is_total: true,
      },
    ],
    _note_texts: [
      { section: 'soe-derivative-tip', text: snap.derivativeTipNote },
    ],
  }
}

export function buildG1SoeSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snap: G1SoeSyncSnapshot,
): G1SyncFromWorkpaperPayload[] {
  if (!isG1DisclosureApplicable('soe', applicableStandards)) return []
  const standard = resolveG1CurrentStandard('soe', applicableStandards)
  const sheet = G1_DISCLOSURE_SHEET_NAME.soe
  const sections = G1_NOTE_SECTION.soe
  return [
    {
      wp_id: wpId,
      sheet_name: sheet,
      section_id: sections.trading,
      current_standard: standard,
      sub_table_data: buildG1SoeTradingSubTableData(snap),
      columns: { 交易性金融资产: G1_SOE_TRADING_COLUMNS },
    },
    {
      wp_id: wpId,
      sheet_name: sheet,
      section_id: sections.derivative,
      current_standard: standard,
      sub_table_data: buildG1SoeDerivativeSubTableData(snap),
      columns: { 衍生金融资产: G1_SOE_DERIVATIVE_COLUMNS },
    },
  ]
}

/** 上市六段披露 → 附注子表 */
export interface G1ListedSyncSnapshot {
  classificationRows: G1DiscAmountRow[]
  designatedReason: string
  derivativeRows: G1DiscAmountRow[]
  derivativeNote: string
  fvRows: G1DiscHierarchyRow[]
  inputRows: G1DiscInputRow[]
  l3Rows: G1DiscL3RollRow[]
  amortRows: G1DiscAmortRow[]
  generalNote: string
}

export function buildG1ListedSubTableData(
  snap: G1ListedSyncSnapshot,
): Record<string, Record<string, unknown>[]> {
  const classLeaves = snap.classificationRows.filter((r) => r.kind === 'leaf')
  const derivLeaves = snap.derivativeRows.filter((r) => r.kind === 'leaf')
  const fvLeaves = snap.fvRows.filter((r) => r.kind === 'leaf')
  const l3Leaves = snap.l3Rows.filter((r) => r.kind === 'leaf')

  return {
    交易性金融资产分类: classLeaves.map((r) => ({
      项目: r.label,
      期末余额: r.endAmount,
      上年年末余额: r.priorAmount,
      备注: r.remark || '',
    })),
    指定理由: snap.designatedReason ? [{ 说明: snap.designatedReason }] : [],
    衍生金融资产: derivLeaves.map((r) => ({
      项目: r.label,
      期末余额: r.endAmount,
      上年年末余额: r.priorAmount,
    })),
    衍生说明: snap.derivativeNote ? [{ 说明: snap.derivativeNote }] : [],
    公允价值层次: fvLeaves.map((r) => ({
      项目: r.label,
      第一层次: r.l1,
      第二层次: r.l2,
      第三层次: r.l3,
      合计: (Number(r.l1) || 0) + (Number(r.l2) || 0) + (Number(r.l3) || 0),
    })),
    估值输入值: snap.inputRows.map((r) => ({
      内容: r.content,
      期末公允价值: r.endFv,
      估值技术: r.technique,
      输入值: r.inputs || r.selectedIndicators.join('、'),
      范围: r.range,
      层次: r.level,
    })),
    第三层次调节: l3Leaves.map((r) => ({
      项目: r.label,
      期初余额: r.opening,
      转入: r.transferIn,
      转出: r.transferOut,
      计入损益: r.gainPl,
      计入OCI: r.gainOci,
      购买: r.purchase,
      发行: r.issue,
      出售: r.sale,
      结算: r.settlement,
      期末余额: r.closing,
      仍持有未实现损益: r.unrealizedHeld,
    })),
    非以公允价值计量项目: snap.amortRows.map((r) => ({
      项目: r.label,
      账面价值: r.bookValue,
      第一层次: r.l1,
      第二层次: r.l2,
      第三层次: r.l3,
      备注: r.remark || '',
    })),
    附注说明: snap.generalNote ? [{ 说明: snap.generalNote }] : [],
    _note_texts: [
      { section: 'listed-designated-reason', text: snap.designatedReason },
      { section: 'listed-derivative-note', text: snap.derivativeNote },
      { section: 'listed-audit-note', text: snap.generalNote },
    ],
  }
}

/** 上市同步：主章节五、2；衍生单独写入五、3（若有衍生数据） */
export function buildG1SyncPayload(
  variant: G1DisclosureVariant,
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  subTableData: Record<string, Record<string, unknown>[]>,
): G1SyncFromWorkpaperPayload | null {
  if (variant !== 'listed') return null
  if (!isG1DisclosureApplicable('listed', applicableStandards)) return null
  return {
    wp_id: wpId,
    sheet_name: G1_DISCLOSURE_SHEET_NAME.listed,
    section_id: G1_NOTE_SECTION.listed.trading,
    current_standard: resolveG1CurrentStandard('listed', applicableStandards),
    sub_table_data: subTableData,
    columns: G1_LISTED_COLUMNS,
  }
}

export function buildG1ListedSyncPayload(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  subTableData: Record<string, Record<string, unknown>[]>,
): G1SyncFromWorkpaperPayload | null {
  return buildG1SyncPayload('listed', wpId, applicableStandards, subTableData)
}

export type { G1DisclosureVariant }
