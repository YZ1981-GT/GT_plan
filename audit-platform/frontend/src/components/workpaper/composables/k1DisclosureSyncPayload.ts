/**
 * K1 披露 → disclosure_notes sync payload
 * 子表名对齐 note_template_listed §五、8（其他应收款项部分）
 */
import type { K1DisclosureVariant } from './k1NoteSectionMap'
import {
  K1_DISCLOSURE_SHEET_NAME,
  K1_LISTED_SUBTABLE,
  K1_NOTE_SECTION,
  K1_SOE_SUBTABLE,
  isK1DisclosureApplicable,
  resolveK1CurrentStandard,
} from './k1NoteSectionMap'
import {
  summarizeNatureRows,
  type K1ListedDisclosurePayloadV2,
  type K1SoeDisclosurePayloadV2,
} from './k1DisclosureModel'
import type { K1StageMovementRow } from './useK1BadDebt'
import type { ColumnDef } from './disclosureColumnDefs'

export interface K1SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, Record<string, unknown>[]>
  /**
   * 列头元数据（disclosure-table-sync-convergence）。
   * 键=子表名（K1_LISTED_SUBTABLE / K1_SOE_SUBTABLE 值）。
   * value 列 key 与 sub_table_data 行对象的中文键逐字一致（行键即取自 note_template 列名）；
   * label 列头取自各子表 note_template 首列语义（账龄/款项性质/单位名称 等）。
   */
  columns?: Record<string, ColumnDef[]>
}

/** 金额列（格式化为金额） */
const amt = (k: string): ColumnDef => ({ key: k, label: k, format: 'amount' })
/** 文本/比例列（原样） */
const txt = (k: string): ColumnDef => ({ key: k, label: k })
/** 标签列（行名，键恒为 label，表头取自 note_template 首列语义） */
const lbl = (header: string): ColumnDef => ({ key: 'label', label: header, is_label: true })

// ─── 列头定义（逐字对齐 buildK1*SubTableData 的行键 + note_template 首列语义）───

const K1_LISTED_COLUMNS: Record<string, ColumnDef[]> = {
  [K1_LISTED_SUBTABLE.aging]: [lbl('账龄'), amt('期末余额'), amt('上年年末余额')],
  [K1_LISTED_SUBTABLE.nature]: [
    lbl('款项性质'),
    amt('期末账面余额'), amt('期末坏账准备'), amt('期末账面价值'),
    amt('上年年末账面余额'), amt('上年年末坏账准备'), amt('上年年末账面价值'),
  ],
  [K1_LISTED_SUBTABLE.stage1]: [
    lbl('项目'), amt('账面余额'), txt('预期信用损失率'), amt('坏账准备'), amt('账面价值'), txt('理由'),
  ],
  [K1_LISTED_SUBTABLE.stage2]: [
    lbl('项目'), amt('账面余额'), txt('预期信用损失率'), amt('坏账准备'), amt('账面价值'), txt('理由'),
  ],
  [K1_LISTED_SUBTABLE.stage3]: [
    lbl('项目'), amt('账面余额'), txt('预期信用损失率'), amt('坏账准备'), amt('账面价值'), txt('理由'),
  ],
  [K1_LISTED_SUBTABLE.stageMovement]: [
    lbl('项目'), amt('第一阶段'), amt('第二阶段'), amt('第三阶段'), amt('合计'),
  ],
  [K1_LISTED_SUBTABLE.reversal]: [
    lbl('单位名称'), txt('转回原因'), txt('收回方式'), txt('原确定坏账准备的依据'), amt('转回或收回金额'),
  ],
  [K1_LISTED_SUBTABLE.writeoffSummary]: [lbl('项目'), amt('核销金额')],
  [K1_LISTED_SUBTABLE.writeoffDetail]: [
    lbl('单位名称'), txt('其他应收款性质'), amt('核销金额'), txt('核销原因'), txt('履行的核销程序'), txt('是否由关联交易产生'),
  ],
  [K1_LISTED_SUBTABLE.top5]: [
    lbl('单位名称'), txt('款项性质'), amt('其他应收款期末余额'), txt('账龄'),
    txt('占其他应收款期末余额合计数的比例(%)'), amt('坏账准备期末余额'),
  ],
}

const K1_SOE_COLUMNS: Record<string, ColumnDef[]> = {
  [K1_SOE_SUBTABLE.aging]: [lbl('账龄'), amt('期末数'), amt('期初数')],
  [K1_SOE_SUBTABLE.methodEnd]: [
    lbl('类别'), amt('账面余额'), txt('比例(%)'), amt('坏账准备'), txt('预期信用损失率(%)'), amt('账面价值'),
  ],
  [K1_SOE_SUBTABLE.methodPrior]: [
    lbl('类别'), amt('账面余额'), txt('比例(%)'), amt('坏账准备'), txt('预期信用损失率(%)'), amt('账面价值'),
  ],
  [K1_SOE_SUBTABLE.individualDetail]: [
    lbl('债务人'), amt('账面余额'), amt('坏账准备'), txt('预期信用损失率(%)'), txt('计提理由'),
  ],
  [K1_SOE_SUBTABLE.portfolioOther]: [
    lbl('账龄'), amt('期末账面余额'), txt('期末比例(%)'), amt('期末坏账准备'),
    amt('期初账面余额'), txt('期初比例(%)'), amt('期初坏账准备'),
  ],
  [K1_SOE_SUBTABLE.eclMovement]: [
    lbl('项目'), amt('第一阶段'), amt('第二阶段'), amt('第三阶段'), amt('合计'),
  ],
  [K1_SOE_SUBTABLE.balanceMovement]: [
    lbl('项目'), amt('第一阶段'), amt('第二阶段'), amt('第三阶段'), amt('合计'),
  ],
  [K1_SOE_SUBTABLE.reversal]: [
    lbl('债务人'), txt('转回原因'), txt('收回方式'), txt('原确定坏账准备的依据'), amt('转回或收回金额'),
  ],
  [K1_SOE_SUBTABLE.writeoff]: [
    lbl('债务人'), txt('其他应收款项性质'), amt('核销金额'), txt('核销原因'), txt('履行的核销程序'), txt('是否由关联交易产生'),
  ],
  [K1_SOE_SUBTABLE.top5]: [
    lbl('单位名称'), txt('款项性质'), amt('期末余额'), txt('账龄'),
    txt('占其他应收款项合计数的比例(%)'), amt('坏账准备'),
  ],
  [K1_SOE_SUBTABLE.govGrant]: [
    lbl('单位名称'), txt('政府补助项目名称'), amt('期末余额'), txt('期末账龄'), txt('预计收取的时间_金额及依据'),
  ],
  [K1_SOE_SUBTABLE.transfer]: [
    lbl('项目'), amt('终止确认金额'), amt('与终止确认相关的利得或损失'), txt('转移方式'), amt('金额'),
  ],
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function stageMovementTotal(row: K1StageMovementRow): number {
  return _num(row.stage1) + _num(row.stage2) + _num(row.stage3)
}

export function buildK1ListedSubTableData(
  snap: K1ListedDisclosurePayloadV2,
  auditNote = '',
): Record<string, Record<string, unknown>[]> {
  const natureTotal = summarizeNatureRows(snap.natureRows || [])

  return {
    [K1_LISTED_SUBTABLE.aging]: (snap.agingRows || []).map((r) => ({
      label: r.label,
      期末余额: r.endAmount,
      上年年末余额: r.priorAmount,
      row_kind: r.kind,
      segment_key: r.segmentKey,
      is_total: r.kind === 'total' || r.kind === 'subtotal',
    })),
    [K1_LISTED_SUBTABLE.nature]: [
      ...(snap.natureRows || []).map((r) => ({
        label: r.label,
        期末账面余额: r.endGross,
        期末坏账准备: r.endProvision,
        期末账面价值: r.endBookValue,
        上年年末账面余额: r.priorGross,
        上年年末坏账准备: r.priorProvision,
        上年年末账面价值: r.priorBookValue,
      })),
      {
        label: '合计',
        期末账面余额: natureTotal.endGross,
        期末坏账准备: natureTotal.endProvision,
        期末账面价值: natureTotal.endBookValue,
        上年年末账面余额: natureTotal.priorGross,
        上年年末坏账准备: natureTotal.priorProvision,
        上年年末账面价值: natureTotal.priorBookValue,
        is_total: true,
      },
    ],
    [K1_LISTED_SUBTABLE.stage1]: mapStageRows(snap.stage1Rows),
    [K1_LISTED_SUBTABLE.stage2]: mapStageRows(snap.stage2Rows),
    [K1_LISTED_SUBTABLE.stage3]: mapStageRows(snap.stage3Rows),
    [K1_LISTED_SUBTABLE.stageMovement]: (snap.stageMovements || []).map((r) => ({
      label: r.label,
      第一阶段: r.stage1,
      第二阶段: r.stage2,
      第三阶段: r.stage3,
      合计: stageMovementTotal(r),
      row_key: r.key,
    })),
    [K1_LISTED_SUBTABLE.reversal]: [
      ...(snap.reversalRows || []).map((r) => ({
        label: r.unitName || '（未命名）',
        转回原因: r.reason,
        收回方式: r.method,
        原确定坏账准备的依据: r.basis,
        转回或收回金额: r.amount,
      })),
      {
        label: '合计',
        转回或收回金额: (snap.reversalRows || []).reduce((s, r) => s + _num(r.amount), 0),
        is_total: true,
      },
    ],
    [K1_LISTED_SUBTABLE.writeoffSummary]: [
      {
        label: '实际核销的其他应收款',
        核销金额: snap.writeoffSummaryAmount,
      },
    ],
    [K1_LISTED_SUBTABLE.writeoffDetail]: [
      ...(snap.writeoffDetailRows || []).map((r) => ({
        label: r.unitName || '（未命名）',
        其他应收款性质: r.nature,
        核销金额: r.amount,
        核销原因: r.reason,
        履行的核销程序: r.procedure,
        是否由关联交易产生: r.relatedParty,
      })),
      {
        label: '合计',
        核销金额: (snap.writeoffDetailRows || []).reduce((s, r) => s + _num(r.amount), 0),
        is_total: true,
      },
    ],
    [K1_LISTED_SUBTABLE.top5]: [
      ...(snap.top5Rows || []).map((r) => ({
        label: r.unitName || '（未命名）',
        款项性质: r.nature,
        其他应收款期末余额: r.endBalance,
        账龄: r.aging,
        '占其他应收款期末余额合计数的比例(%)': r.proportionPct,
        坏账准备期末余额: r.provision,
      })),
      {
        label: '合计',
        其他应收款期末余额: (snap.top5Rows || []).reduce((s, r) => s + _num(r.endBalance), 0),
        '占其他应收款期末余额合计数的比例(%)': (snap.top5Rows || []).reduce((s, r) => s + _num(r.proportionPct), 0),
        坏账准备期末余额: (snap.top5Rows || []).reduce((s, r) => s + _num(r.provision), 0),
        is_total: true,
      },
    ],
    _note_texts: [
      { section: 'listed-audit-note', text: auditNote },
      { section: 'listed-fund-centralization', text: snap.fundCentralizationNote || '' },
      ...(snap.notes
        ? Object.entries(snap.notes).map(([section, text]) => ({ section, text }))
        : []),
    ] as unknown as Record<string, unknown>[],
  }
}

function mapStageRows(rows: K1ListedDisclosurePayloadV2['stage1Rows']) {
  return (rows || [])
    .filter((r) => r.kind !== 'header')
    .map((r) => ({
      label: r.label,
      账面余额: r.balance,
      预期信用损失率: r.eclRate,
      坏账准备: r.provision,
      账面价值: r.bookValue,
      理由: r.reason,
      row_key: r.rowKey,
      is_total: r.kind === 'total' || r.kind === 'subtotal',
    }))
}

export function buildK1ListedSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snap: K1ListedDisclosurePayloadV2,
  auditNote = '',
): K1SyncFromWorkpaperPayload[] {
  const variant: K1DisclosureVariant = 'listed'
  if (!isK1DisclosureApplicable(variant, applicableStandards)) return []
  return [
    {
      wp_id: wpId,
      sheet_name: K1_DISCLOSURE_SHEET_NAME.listed,
      section_id: K1_NOTE_SECTION.listed,
      current_standard: resolveK1CurrentStandard(variant, applicableStandards),
      sub_table_data: buildK1ListedSubTableData(snap, auditNote),
      columns: K1_LISTED_COLUMNS,
    },
  ]
}

// ─── SOE 国企同步 ─────────────────────────────────────────────────────────────

export function buildK1SoeSubTableData(
  snap: K1SoeDisclosurePayloadV2,
  auditNote = '',
): Record<string, Record<string, unknown>[]> {
  const methodTotal = snap.methodRows.find((r) => r.rowKey === 'total')
  return {
    [K1_SOE_SUBTABLE.aging]: (snap.agingRows || []).map((r) => ({
      label: r.label,
      期末数: r.endAmount,
      期初数: r.priorAmount,
      row_kind: r.kind,
      is_total: r.kind === 'total' || r.kind === 'subtotal',
    })),
    [K1_SOE_SUBTABLE.methodEnd]: (snap.methodRows || []).map((r) => ({
      label: r.label,
      账面余额: r.endBalance,
      '比例(%)': r.endBalancePct,
      坏账准备: r.endProvision,
      '预期信用损失率(%)': r.endEclRate,
      账面价值: r.endBookValue,
      row_key: r.rowKey,
      is_total: r.rowKey === 'total',
    })),
    [K1_SOE_SUBTABLE.methodPrior]: (snap.methodRows || []).map((r) => ({
      label: r.label,
      账面余额: r.priorBalance,
      '比例(%)': r.priorBalancePct,
      坏账准备: r.priorProvision,
      '预期信用损失率(%)': r.priorEclRate,
      账面价值: r.priorBookValue,
      row_key: r.rowKey,
      is_total: r.rowKey === 'total',
    })),
    [K1_SOE_SUBTABLE.individualDetail]: [
      ...(snap.individualDetailRows || []).map((r) => ({
        label: r.debtorName || '（未命名）',
        账面余额: r.balance,
        坏账准备: r.provision,
        '预期信用损失率(%)': r.eclRate,
        计提理由: r.reason,
      })),
      {
        label: '合计',
        账面余额: (snap.individualDetailRows || []).reduce((s, r) => s + _num(r.balance), 0),
        坏账准备: (snap.individualDetailRows || []).reduce((s, r) => s + _num(r.provision), 0),
        is_total: true,
      },
    ],
    [K1_SOE_SUBTABLE.portfolioOther]: (snap.portfolioAgingRows || []).map((r) => ({
      label: r.label,
      期末账面余额: r.endBalance,
      '期末比例(%)': r.endBalancePct,
      期末坏账准备: r.endProvision,
      期初账面余额: r.priorBalance,
      '期初比例(%)': r.priorBalancePct,
      期初坏账准备: r.priorProvision,
    })),
    [K1_SOE_SUBTABLE.eclMovement]: (snap.stageMovements || []).map((r) => ({
      label: r.label,
      第一阶段: r.stage1,
      第二阶段: r.stage2,
      第三阶段: r.stage3,
      合计: stageMovementTotal(r),
      row_key: r.key,
    })),
    [K1_SOE_SUBTABLE.balanceMovement]: (snap.balanceStageMovements || []).map((r) => ({
      label: r.label,
      第一阶段: r.stage1,
      第二阶段: r.stage2,
      第三阶段: r.stage3,
      合计: stageMovementTotal(r),
      row_key: r.key,
      is_closing: r.key === 'closing',
    })),
    [K1_SOE_SUBTABLE.reversal]: [
      ...(snap.reversalRows || []).map((r) => ({
        label: r.unitName || '（未命名）',
        转回原因: r.reason,
        收回方式: r.method,
        原确定坏账准备的依据: r.basis,
        转回或收回金额: r.amount,
      })),
      {
        label: '合计',
        转回或收回金额: (snap.reversalRows || []).reduce((s, r) => s + _num(r.amount), 0),
        is_total: true,
      },
    ],
    [K1_SOE_SUBTABLE.writeoff]: [
      ...(snap.writeoffDetailRows || []).map((r) => ({
        label: r.unitName || '（未命名）',
        '其他应收款项性质': r.nature,
        核销金额: r.amount,
        核销原因: r.reason,
        履行的核销程序: r.procedure,
        是否由关联交易产生: r.relatedParty,
      })),
      {
        label: '合计',
        核销金额: snap.writeoffSummaryAmount,
        is_total: true,
      },
    ],
    [K1_SOE_SUBTABLE.top5]: [
      ...(snap.top5Rows || []).map((r) => ({
        label: r.unitName || '（未命名）',
        款项性质: r.nature,
        期末余额: r.endBalance,
        账龄: r.aging,
        '占其他应收款项合计数的比例(%)': r.proportionPct,
        坏账准备: r.provision,
      })),
      {
        label: '合计',
        期末余额: (snap.top5Rows || []).reduce((s, r) => s + _num(r.endBalance), 0),
        '占其他应收款项合计数的比例(%)': (snap.top5Rows || []).reduce((s, r) => s + _num(r.proportionPct), 0),
        坏账准备: (snap.top5Rows || []).reduce((s, r) => s + _num(r.provision), 0),
        is_total: true,
      },
    ],
    [K1_SOE_SUBTABLE.govGrant]: (snap.govGrantRows || []).map((r) => ({
      label: r.unitName || '（未命名）',
      政府补助项目名称: r.projectName,
      期末余额: r.endBalance,
      期末账龄: r.aging,
      预计收取的时间_金额及依据: r.expectedCollection,
    })),
    [K1_SOE_SUBTABLE.transfer]: [
      ...(snap.transferRows || []).map((r) => ({
        label: r.item || '（未命名）',
        终止确认金额: r.derecognizedAmount,
        与终止确认相关的利得或损失: r.gainLoss,
        转移方式: r.method,
      })),
      {
        label: '继续涉入形成的资产',
        金额: snap.continuedInvolvementAssets,
      },
      {
        label: '继续涉入形成的负债',
        金额: snap.continuedInvolvementLiabilities,
      },
    ],
    _note_texts: [
      { section: 'soe-audit-note', text: auditNote },
      ...(snap.notes
        ? Object.entries(snap.notes).map(([section, text]) => ({ section, text }))
        : []),
    ] as unknown as Record<string, unknown>[],
    _tie_out: [{
      method_total_balance: methodTotal?.endBalance ?? 0,
      method_total_provision: methodTotal?.endProvision ?? 0,
    }],
  }
}

export function buildK1SoeSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snap: K1SoeDisclosurePayloadV2,
  auditNote = '',
): K1SyncFromWorkpaperPayload[] {
  const variant: K1DisclosureVariant = 'soe'
  if (!isK1DisclosureApplicable(variant, applicableStandards)) return []
  return [
    {
      wp_id: wpId,
      sheet_name: K1_DISCLOSURE_SHEET_NAME.soe,
      section_id: K1_NOTE_SECTION.soe,
      current_standard: resolveK1CurrentStandard(variant, applicableStandards),
      sub_table_data: buildK1SoeSubTableData(snap, auditNote),
      columns: K1_SOE_COLUMNS,
    },
  ]
}
