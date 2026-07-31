/**
 * K1 披露 → disclosure_notes sync payload
 *
 * 子表名与列头逐字对齐 note_template_listed §五、8 / note_template_soe §八、9
 * （契约测试见 `__tests__/k1NoteSubtableContract.spec.ts`）。
 *
 * 上市披露表的「资金集中管理 / 应收政府补助 / 转移终止确认 / 继续涉入」四块
 * 附注真源不在 §五、8（分别为「计入其他应收款的政府补助」与 §七 金融工具章节），
 * 故不在本文件的 listed 映射内——底稿侧留存并在 UI 标注去向。
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
  K1_STAGE2_NONE_TEXT_END,
  K1_STAGE2_NONE_TEXT_PRIOR,
  summarizeContinuedInvolvement,
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
   * value 列 key 与 sub_table_data 行对象的中文键逐字一致；
   * label 列头取自各子表 note_template 首列。
   */
  columns?: Record<string, ColumnDef[]>
}

/**
 * 金额列（key 与 label 同名 —— 行对象的中文数据键）。
 * 单级表头的表用它 + `flat()`；两级表头用 `amtG` / `txtG` 显式给 `group`。
 */
const amt = (k: string): ColumnDef => ({ key: k, label: k, format: 'amount' })
/** 文本/比例列（原样） */
const txt = (k: string): ColumnDef => ({ key: k, label: k })
/** 标签列（行名，键恒为 label，表头取自 note_template 首列语义） */
const lbl = (header: string): ColumnDef => ({ key: 'label', label: header, is_label: true })

/**
 * 两级表头的金额子列：`key` 保留既有**带期别前缀的中文数据键**（行对象就是这些键，
 * 改 key 会让整表数据丢落点），`label` 只写**叶子列名**，父表头交给 `group`。
 */
const amtG = (key: string, label: string, group?: string): ColumnDef => ({
  key, label, ...(group ? { group } : {}), format: 'amount',
})
/** 两级表头的文本/比例子列 */
const txtG = (key: string, label: string, group?: string): ColumnDef => ({
  key, label, ...(group ? { group } : {}),
})

/**
 * 单级表头显式表态：在标签列打 `flat`。
 *
 * 🔴 必须打 —— 不打时后端 `_extract_column_groups` 返回 `None` → 退化到
 * `_infer_groups_from_headers` **前缀推断**，会给「期末账面余额/期末坏账准备/…」
 * 这类表头凭空造出父表头；契约 P3「group / flat 之间必须表态」也不满足。
 */
function flat(cols: ColumnDef[]): ColumnDef[] {
  return cols.map((c, i) => (i === 0 ? { ...c, flat: true } : c))
}

// ─── 列头定义（逐字对齐 buildK1*SubTableData 的行键 + note_template 列结构）───

/**
 * 三阶段快照表列头（源 xlsx 上市 `A32:F39` 等 —— **6 列，末列「理由」**）。
 * ECL 率列的**表头按阶段不同**（第一阶段 = 未来 12 个月内；第二/三阶段 = 整个存续期），
 * `key` 统一 `预期信用损失率`（既有行键真源，不随表头变）。
 */
const RATE_12M = '未来12个月内的预期信用损失率(%)'
const RATE_LIFETIME = '整个存续期预期信用损失率（%）'

const stageColumns = (rateHeader: string): ColumnDef[] => flat([
  lbl('类别'),
  amt('账面余额'),
  txtG('预期信用损失率', rateHeader),
  amt('坏账准备'),
  amt('账面价值'),
  txt('理由'),
])

/** 三阶段变动表共用列头（附注模版为单级 5 列；label 表头由各表首列决定） */
const stageMovementColumns = (labelHeader: string): ColumnDef[] => flat([
  lbl(labelHeader), amt('第一阶段'), amt('第二阶段'), amt('第三阶段'), amt('合计'),
])

export const K1_LISTED_COLUMNS: Record<string, ColumnDef[]> = {
  [K1_LISTED_SUBTABLE.aging]: flat([lbl('账龄'), amt('期末余额'), amt('上年年末余额')]),
  // 源 xlsx `A22:G28`：`B22:D22`（期末数）/ `E22:G22`（上年年末数）跨列合并 = 真两级表头；
  // 父表头取附注模版口径「期末金额」/「上年年末金额」（附注是交付物）。
  [K1_LISTED_SUBTABLE.nature]: [
    lbl('项  目'),
    amtG('期末账面余额', '账面余额', '期末金额'),
    amtG('期末坏账准备', '坏账准备', '期末金额'),
    amtG('期末账面价值', '账面价值', '期末金额'),
    amtG('上年年末账面余额', '账面余额', '上年年末金额'),
    amtG('上年年末坏账准备', '坏账准备', '上年年末金额'),
    amtG('上年年末账面价值', '账面价值', '上年年末金额'),
  ],
  [K1_LISTED_SUBTABLE.stage1]: stageColumns(RATE_12M),
  [K1_LISTED_SUBTABLE.stage2]: stageColumns(RATE_LIFETIME),
  [K1_LISTED_SUBTABLE.stage3]: stageColumns(RATE_LIFETIME),
  [K1_LISTED_SUBTABLE.priorStage1]: stageColumns(RATE_12M),
  [K1_LISTED_SUBTABLE.priorStage2]: stageColumns(RATE_LIFETIME),
  [K1_LISTED_SUBTABLE.priorStage3]: stageColumns(RATE_LIFETIME),
  [K1_LISTED_SUBTABLE.stageMovement]: stageMovementColumns('坏账准备'),
  [K1_LISTED_SUBTABLE.reversal]: flat([
    lbl('单位名称'), txt('转回原因'), txt('收回方式'), txt('原确定坏账准备的依据'), amt('转回或收回金额'),
  ]),
  [K1_LISTED_SUBTABLE.writeoffSummary]: flat([lbl('项目'), amt('核销金额')]),
  [K1_LISTED_SUBTABLE.writeoffDetail]: flat([
    lbl('单位名称'), txt('其他应收款性质'), amt('核销金额'), txt('核销原因'), txt('履行的核销程序'), txt('是否由关联交易产生'),
  ]),
  [K1_LISTED_SUBTABLE.top5]: flat([
    lbl('单位名称'), txt('款项性质'), amt('其他应收款期末余额'), txt('账龄'),
    txt('占其他应收款期末余额合计数的比例(%)'), amt('坏账准备期末余额'),
  ]),
}

/**
 * 国企「按坏账准备计提方法分类」列头（主表 / 续表共用）。
 *
 * 源 xlsx `A19:F26` 是**三级表头**：`期末余额` > `账面余额`/`坏账准备`/`账面价值`
 * > `金额`/`比例(%)`/`预期信用损失率(%)`。顶层期别已由「主表 + 续表」两张表承载
 * （D1/D6 同款范式：把顶层期间提到表名），剩下两级用 `group`；`账面价值` 是
 * rowspan=2 的独立列 → 不给 `group`（混合分组，前后端均支持）。
 */
const methodColumns = (): ColumnDef[] => [
  lbl('类  别'),
  amtG('账面余额', '金额', '账面余额'),
  txtG('比例(%)', '比例(%)', '账面余额'),
  amtG('坏账准备', '金额', '坏账准备'),
  txtG('预期信用损失率(%)', '预期信用损失率(%)', '坏账准备'),
  amtG('账面价值', '账面价值'),
]

export const K1_SOE_COLUMNS: Record<string, ColumnDef[]> = {
  // 源 xlsx `A46:G55`：`B46:D46`（期末数）/ `E46:G46`（期初数）跨列合并
  [K1_SOE_SUBTABLE.aging]: [
    lbl('账  龄'),
    amtG('期末账面余额', '账面余额', '期末数'),
    amtG('期末坏账准备', '坏账准备', '期末数'),
    amtG('期初账面余额', '账面余额', '期初数'),
    amtG('期初坏账准备', '坏账准备', '期初数'),
  ],
  [K1_SOE_SUBTABLE.methodEnd]: methodColumns(),
  [K1_SOE_SUBTABLE.methodPrior]: methodColumns(),
  // 源 xlsx `A38:E39`：`B38:E38`（期末余额）跨列合并，下辖 4 个子列
  [K1_SOE_SUBTABLE.individualDetail]: [
    lbl('债务人名称'),
    amtG('账面余额', '账面余额', '期末余额'),
    amtG('坏账准备', '坏账准备', '期末余额'),
    txtG('预期信用损失率(%)', '预期信用损失率(%)', '期末余额'),
    txtG('计提理由', '计提理由', '期末余额'),
  ],
  [K1_SOE_SUBTABLE.portfolioAging]: [
    lbl('账  龄'),
    amtG('期末账面余额', '账面余额', '期末数'),
    txtG('期末比例(%)', '比例(%)', '期末数'),
    amtG('期末坏账准备', '坏账准备', '期末数'),
    amtG('期初账面余额', '账面余额', '期初数'),
    txtG('期初比例(%)', '比例(%)', '期初数'),
    amtG('期初坏账准备', '坏账准备', '期初数'),
  ],
  [K1_SOE_SUBTABLE.portfolioOther]: [
    lbl('组合名称'),
    amtG('期末账面余额', '账面余额', '期末数'),
    txtG('期末计提比例(%)', '计提比例(%)', '期末数'),
    amtG('期末坏账准备', '坏账准备', '期末数'),
    amtG('期初账面余额', '账面余额', '期初数'),
    txtG('期初计提比例(%)', '计提比例(%)', '期初数'),
    amtG('期初坏账准备', '坏账准备', '期初数'),
  ],
  [K1_SOE_SUBTABLE.eclMovement]: stageMovementColumns('坏账准备'),
  [K1_SOE_SUBTABLE.balanceMovement]: stageMovementColumns('账面余额'),
  [K1_SOE_SUBTABLE.reversal]: flat([
    lbl('债务人名称'),
    amt('转回或收回金额'),
    amt('转回或收回前累计已计提坏账准备金额'),
    txt('转回或收回原因、方式'),
  ]),
  [K1_SOE_SUBTABLE.writeoff]: flat([
    lbl('债务人名称'), txt('其他应收款项性质'), amt('核销金额'), txt('核销原因'), txt('履行的核销程序'), txt('是否因关联交易产生'),
  ]),
  [K1_SOE_SUBTABLE.top5]: flat([
    lbl('债务人名称'), txt('款项性质'), amt('账面余额'), txt('账龄'),
    txt('占其他应收款项合计的比例（%）'), amt('坏账准备'),
  ]),
  [K1_SOE_SUBTABLE.govGrant]: flat([
    lbl('单位名称'), txt('政府补助项目名称'), amt('期末余额'), txt('期末账龄'), txt('预计收取的时间、金额及依据'),
  ]),
  [K1_SOE_SUBTABLE.transfer]: flat([
    lbl('债务人名称'), amt('终止确认金额'), amt('与终止确认相关的利得或损失'),
  ]),
  [K1_SOE_SUBTABLE.continuedInvolvement]: flat([lbl('项  目'), amt('期末金额')]),
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function stageMovementTotal(row: K1StageMovementRow): number {
  return _num(row.stage1) + _num(row.stage2) + _num(row.stage3)
}

function mapStageMovements(
  rows: K1StageMovementRow[] | undefined,
): Record<string, unknown>[] {
  return (rows || []).map((r) => ({
    label: r.label,
    第一阶段: r.stage1,
    第二阶段: r.stage2,
    第三阶段: r.stage3,
    合计: stageMovementTotal(r),
    row_key: r.key,
    is_total: r.key === 'closing',
  }))
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

/** 继续涉入：资产区 → 资产小计 → 负债区 → 负债小计（对齐源模板行序） */
function mapContinuedInvolvement(
  snap: { continuedInvolvementRows?: K1ListedDisclosurePayloadV2['continuedInvolvementRows'] },
): Record<string, unknown>[] {
  const rows = snap.continuedInvolvementRows || []
  const totals = summarizeContinuedInvolvement(rows)
  const out: Record<string, unknown>[] = [{ label: '资产：', row_kind: 'header' }]
  for (const r of rows.filter((x) => x.side === 'asset')) {
    out.push({ label: r.item || '（未命名）', 期末金额: r.amount })
  }
  out.push({ label: '资产小计', 期末金额: totals.assets, is_total: true })
  out.push({ label: '负债：', row_kind: 'header' })
  for (const r of rows.filter((x) => x.side === 'liability')) {
    out.push({ label: r.item || '（未命名）', 期末金额: r.amount })
  }
  out.push({ label: '负债小计', 期末金额: totals.liabilities, is_total: true })
  return out
}

function noteTextRows(entries: Array<[string, string]>): Record<string, unknown>[] {
  return entries
    .filter(([, text]) => String(text ?? '').trim())
    .map(([section, text]) => ({ section, text })) as unknown as Record<string, unknown>[]
}

// ─── 上市同步 ─────────────────────────────────────────────────────────────────

export function buildK1ListedSubTableData(
  snap: K1ListedDisclosurePayloadV2,
  auditNote = '',
): Record<string, Record<string, unknown>[]> {
  const natureTotal = summarizeNatureRows(snap.natureRows || [])
  const notes = snap.notes || {}

  return {
    [K1_LISTED_SUBTABLE.aging]: (snap.agingRows || []).map((r) => ({
      label: r.label,
      期末余额: r.endAmount,
      上年年末余额: r.priorAmount,
      row_kind: r.kind,
      segment_key: r.segmentKey,
      is_total: r.kind === 'total' || r.kind === 'subtotal' || r.kind === 'subtotal1y',
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
        label: '合  计',
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
    [K1_LISTED_SUBTABLE.stage2]: snap.stage2NoneEnd ? [] : mapStageRows(snap.stage2Rows),
    [K1_LISTED_SUBTABLE.stage3]: mapStageRows(snap.stage3Rows),
    [K1_LISTED_SUBTABLE.priorStage1]: mapStageRows(snap.priorStage1Rows),
    [K1_LISTED_SUBTABLE.priorStage2]: snap.stage2NonePrior ? [] : mapStageRows(snap.priorStage2Rows),
    [K1_LISTED_SUBTABLE.priorStage3]: mapStageRows(snap.priorStage3Rows),
    [K1_LISTED_SUBTABLE.stageMovement]: mapStageMovements(snap.stageMovements),
    [K1_LISTED_SUBTABLE.reversal]: [
      ...(snap.reversalRows || []).map((r) => ({
        label: r.unitName || '（未命名）',
        转回原因: r.reason,
        收回方式: r.method,
        原确定坏账准备的依据: r.basis,
        转回或收回金额: r.amount,
      })),
      {
        label: '合  计',
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
        label: '合  计',
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
        label: '合  计',
        其他应收款期末余额: (snap.top5Rows || []).reduce((s, r) => s + _num(r.endBalance), 0),
        '占其他应收款期末余额合计数的比例(%)': (snap.top5Rows || []).reduce((s, r) => s + _num(r.proportionPct), 0),
        坏账准备期末余额: (snap.top5Rows || []).reduce((s, r) => s + _num(r.provision), 0),
        is_total: true,
      },
    ],
    _note_texts: noteTextRows([
      ['listed-audit-note', auditNote],
      ['listed-fund-centralization', snap.fundCentralizationNote || ''],
      ['listed-balance-change', notes.balanceChange || ''],
      ['listed-ecl-basis', notes.eclBasis || ''],
      ['listed-writeoff-note', notes.writeoffNote || ''],
      ['listed-transfer-note', notes.transferNote || ''],
      ['listed-stage2-none-end', snap.stage2NoneEnd ? K1_STAGE2_NONE_TEXT_END : ''],
      ['listed-stage2-none-prior', snap.stage2NonePrior ? K1_STAGE2_NONE_TEXT_PRIOR : ''],
    ]),
  }
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
  const notes = snap.notes || {}
  const agingRows = snap.agingRows || []
  const agingSubtotal = agingRows.find((r) => r.kind === 'subtotal')
  const agingProvision = agingRows.find((r) => r.kind === 'provision')

  return {
    // 附注「按账龄披露其他应收款项」为「账面余额 + 坏账准备」双列口径，
    // 底稿账龄表为「金额 + 减：坏账准备行」口径 → 明细行填账面余额，合计行补坏账准备总额。
    [K1_SOE_SUBTABLE.aging]: [
      ...agingRows
        .filter((r) => r.kind === 'data' || r.kind === 'sub')
        .map((r) => ({
          label: r.label,
          期末账面余额: r.endAmount,
          期初账面余额: r.priorAmount,
          row_kind: r.kind,
          segment_key: r.segmentKey,
        })),
      {
        label: '合  计',
        期末账面余额: _num(agingSubtotal?.endAmount),
        期末坏账准备: _num(agingProvision?.endAmount),
        期初账面余额: _num(agingSubtotal?.priorAmount),
        期初坏账准备: _num(agingProvision?.priorAmount),
        is_total: true,
      },
    ],
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
    [K1_SOE_SUBTABLE.portfolioAging]: [
      ...(snap.portfolioAgingRows || []).map((r) => ({
        label: r.label,
        期末账面余额: r.endBalance,
        '期末比例(%)': r.endBalancePct,
        期末坏账准备: r.endProvision,
        期初账面余额: r.priorBalance,
        '期初比例(%)': r.priorBalancePct,
        期初坏账准备: r.priorProvision,
      })),
      {
        label: '合  计',
        期末账面余额: (snap.portfolioAgingRows || []).reduce((s, r) => s + _num(r.endBalance), 0),
        期末坏账准备: (snap.portfolioAgingRows || []).reduce((s, r) => s + _num(r.endProvision), 0),
        期初账面余额: (snap.portfolioAgingRows || []).reduce((s, r) => s + _num(r.priorBalance), 0),
        期初坏账准备: (snap.portfolioAgingRows || []).reduce((s, r) => s + _num(r.priorProvision), 0),
        is_total: true,
      },
    ],
    [K1_SOE_SUBTABLE.portfolioOther]: [
      ...(snap.otherPortfolioRows || []).map((r) => ({
        label: r.label || '（未命名）',
        期末账面余额: r.endBalance,
        '期末计提比例(%)': r.endRatePct,
        期末坏账准备: r.endProvision,
        期初账面余额: r.priorBalance,
        '期初计提比例(%)': r.priorRatePct,
        期初坏账准备: r.priorProvision,
      })),
      {
        label: '合  计',
        期末账面余额: (snap.otherPortfolioRows || []).reduce((s, r) => s + _num(r.endBalance), 0),
        期末坏账准备: (snap.otherPortfolioRows || []).reduce((s, r) => s + _num(r.endProvision), 0),
        期初账面余额: (snap.otherPortfolioRows || []).reduce((s, r) => s + _num(r.priorBalance), 0),
        期初坏账准备: (snap.otherPortfolioRows || []).reduce((s, r) => s + _num(r.priorProvision), 0),
        is_total: true,
      },
    ],
    [K1_SOE_SUBTABLE.eclMovement]: mapStageMovements(snap.stageMovements),
    [K1_SOE_SUBTABLE.balanceMovement]: mapStageMovements(snap.balanceStageMovements),
    [K1_SOE_SUBTABLE.reversal]: [
      ...(snap.reversalRows || []).map((r) => ({
        label: r.unitName || '（未命名）',
        转回或收回金额: r.amount,
        转回或收回前累计已计提坏账准备金额: _num(r.cumulativeProvision),
        '转回或收回原因、方式': [r.reason, r.method].filter(Boolean).join('；'),
      })),
      {
        label: '合计',
        转回或收回金额: (snap.reversalRows || []).reduce((s, r) => s + _num(r.amount), 0),
        转回或收回前累计已计提坏账准备金额: (snap.reversalRows || []).reduce(
          (s, r) => s + _num(r.cumulativeProvision), 0,
        ),
        is_total: true,
      },
    ],
    [K1_SOE_SUBTABLE.writeoff]: [
      ...(snap.writeoffDetailRows || []).map((r) => ({
        label: r.unitName || '（未命名）',
        其他应收款项性质: r.nature,
        核销金额: r.amount,
        核销原因: r.reason,
        履行的核销程序: r.procedure,
        是否因关联交易产生: r.relatedParty,
      })),
      {
        label: '合  计',
        核销金额: snap.writeoffSummaryAmount,
        is_total: true,
      },
    ],
    [K1_SOE_SUBTABLE.top5]: [
      ...(snap.top5Rows || []).map((r) => ({
        label: r.unitName || '（未命名）',
        款项性质: r.nature,
        账面余额: r.endBalance,
        账龄: r.aging,
        '占其他应收款项合计的比例（%）': r.proportionPct,
        坏账准备: r.provision,
      })),
      {
        label: '合  计',
        账面余额: (snap.top5Rows || []).reduce((s, r) => s + _num(r.endBalance), 0),
        '占其他应收款项合计的比例（%）': (snap.top5Rows || []).reduce((s, r) => s + _num(r.proportionPct), 0),
        坏账准备: (snap.top5Rows || []).reduce((s, r) => s + _num(r.provision), 0),
        is_total: true,
      },
    ],
    [K1_SOE_SUBTABLE.govGrant]: [
      ...(snap.govGrantRows || []).map((r) => ({
        label: r.unitName || '（未命名）',
        政府补助项目名称: r.projectName,
        期末余额: r.endBalance,
        期末账龄: r.aging,
        '预计收取的时间、金额及依据': r.expectedCollection,
      })),
      {
        label: '合  计',
        期末余额: (snap.govGrantRows || []).reduce((s, r) => s + _num(r.endBalance), 0),
        is_total: true,
      },
    ],
    [K1_SOE_SUBTABLE.transfer]: [
      ...(snap.transferRows || []).map((r) => ({
        label: r.item || '（未命名）',
        终止确认金额: r.derecognizedAmount,
        与终止确认相关的利得或损失: r.gainLoss,
      })),
      {
        label: '合  计',
        终止确认金额: (snap.transferRows || []).reduce((s, r) => s + _num(r.derecognizedAmount), 0),
        与终止确认相关的利得或损失: (snap.transferRows || []).reduce((s, r) => s + _num(r.gainLoss), 0),
        is_total: true,
      },
    ],
    [K1_SOE_SUBTABLE.continuedInvolvement]: mapContinuedInvolvement(snap),
    _note_texts: noteTextRows([
      ['soe-audit-note', auditNote],
      ['soe-balance-change', notes.balanceChange || ''],
      ['soe-ecl-basis', notes.eclBasis || ''],
      ['soe-transfer-note', notes.transferNote || ''],
    ]),
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
