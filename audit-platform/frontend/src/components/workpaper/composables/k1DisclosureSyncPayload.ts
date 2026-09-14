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
  K1_NOTE_SUBTOTAL_LABEL_WIDE,
  K1_NOTE_TOTAL_LABEL,
  K1_NOTE_TOTAL_LABEL_WIDE,
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
  type K1SummaryFigures,
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
  // 源 xlsx `A32/A41/A51/A63/A72/A82` = 「类 别」（单空格，与国企侧「类  别」不同）。
  lbl('类 别'),
  amt('账面余额'),
  txtG('预期信用损失率', rateHeader),
  amt('坏账准备'),
  amt('账面价值'),
  txt('理由'),
])

/**
 * 三阶段变动表列头 —— **国企侧单级 5 列**。
 *
 * 源 xlsx 国企 `A63:E63`（坏账准备计提情况）/ `A77:E77`（账面余额变动）是**一行表头**，
 * 阶段名与 ECL 释义写在同一格里（`B63 = 第一阶段未来12个月预期信用损失`）→ 确为 `flat`。
 */
const stageMovementColumns = (labelHeader: string): ColumnDef[] => flat([
  lbl(labelHeader), amt('第一阶段'), amt('第二阶段'), amt('第三阶段'), amt('合计'),
])

/**
 * 三阶段变动表列头 —— **上市侧两级混合分组**。
 *
 * 🔴 源 xlsx 上市 `A91:E92` 是**两行表头**：`A91:A92`（坏账准备）与 `E91:E92`（合计）
 * 纵向合并 = rowspan=2；`B91/C91/D91` 是阶段名，`B92/C92/D92` 是各阶段 ECL 释义。
 * 模板与本载荷原先都压成单级 5 列 → 第二行释义整行丢失。
 *
 * 落法与 `methodColumns()` 同款：标签列与 `合计` 不带 `group`（且标签列**不打 `flat`**，
 * 打了会让 `_extract_column_groups` 返回 `[]` 判为显式单级）；`key` 保持既有中文数据键。
 */
const LISTED_STAGE_ECL_DESC = {
  s1: '未来12个月预期信用损失',
  s2: '整个存续期预期信用损失(未发生信用减值)',
  s3: '整个存续期预期信用损失(已发生信用减值)',
} as const

const listedStageMovementColumns = (labelHeader: string): ColumnDef[] => [
  lbl(labelHeader),
  amtG('第一阶段', LISTED_STAGE_ECL_DESC.s1, '第一阶段'),
  amtG('第二阶段', LISTED_STAGE_ECL_DESC.s2, '第二阶段'),
  amtG('第三阶段', LISTED_STAGE_ECL_DESC.s3, '第三阶段'),
  amt('合计'),
]

export const K1_LISTED_COLUMNS: Record<string, ColumnDef[]> = {
  [K1_LISTED_SUBTABLE.summary]: flat([lbl('项目'), amt('期末余额'), amt('上年年末余额')]),
  // 源 xlsx `A7` = 「账 龄」（单空格）。
  [K1_LISTED_SUBTABLE.aging]: flat([lbl('账 龄'), amt('期末余额'), amt('上年年末余额')]),
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
  [K1_LISTED_SUBTABLE.stageMovement]: listedStageMovementColumns('坏账准备'),
  [K1_LISTED_SUBTABLE.reversal]: flat([
    lbl('单位名称'), txt('转回原因'), txt('收回方式'), txt('原确定坏账准备的依据'), amt('转回或收回金额'),
  ]),
  // 源 xlsx `A113` = 「项  目」（双空格）。
  [K1_LISTED_SUBTABLE.writeoffSummary]: flat([lbl('项  目'), amt('核销金额')]),
  [K1_LISTED_SUBTABLE.writeoffDetail]: flat([
    lbl('单位名称'), txt('其他应收款性质'), amt('核销金额'), txt('核销原因'), txt('履行的核销程序'),
    // 源 xlsx `F116` = 「款项是否由关联交易产生」（比原「是否由关联交易产生」多「款项」）；
    // `key` 保持既有行数据键不变，只改显示 `label`（改 key 会让整表数据丢落点）。
    { key: '是否由关联交易产生', label: '款项是否由关联交易产生' },
  ]),
  [K1_LISTED_SUBTABLE.top5]: flat([
    lbl('单位名称'), txt('款项性质'), amt('其他应收款期末余额'), txt('账龄'),
    txt('占其他应收款期末余额合计数的比例(%)'), amt('坏账准备期末余额'),
  ]),
  // 源 xlsx 上市 ⑧ `A137:E137`
  [K1_LISTED_SUBTABLE.govGrant]: flat([
    lbl('单位名称（注：政府补助的发文单位）'), txt('政府补助项目名称'),
    amt('期末余额'), txt('账龄'), txt('预计收取的时间、金额及依据'),
  ]),
  // 源 xlsx 上市 ⑨ `A146:D146`（比国企版多「转移方式」列）
  [K1_LISTED_SUBTABLE.transfer]: flat([
    lbl('项  目'), txt('转移方式'), amt('终止确认金额'),
    amt('与终止确认相关的利得或损失'),
  ]),
  // 源 xlsx 上市 ⑩ `A153:B153`（国企版列名是「期末金额」，上市版是「期末数」）
  [K1_LISTED_SUBTABLE.continuedInvolvement]: flat([lbl('项  目'), amt('期末数')]),
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
  /**
   * 🔴 源 xlsx 国企 `A6:C15` 是**单级 3 列**（`账  龄` / `期末数` / `期初数`），
   * 行 = 账龄档 + `小  计` + `减：坏账准备` + `合  计`。
   *
   * 原先模板与本载荷都是 5 列（期末数/期初数 各含账面余额+坏账准备），那套结构不在
   * 源模板里 → 载荷不得不把「小计 + 减：坏账准备」两行压进合计行的额外两列。
   * 现按源模板还原为 3 列，载荷改为忠实推 subtotal / provision / total 三种 kind。
   */
  [K1_SOE_SUBTABLE.summary]: flat([lbl('项目'), amt('期末余额'), amt('期初余额')]),
  [K1_SOE_SUBTABLE.aging]: flat([lbl('账  龄'), amt('期末数'), amt('期初数')]),
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
  // 源 xlsx `A126` = "单位名称\n（注：政府补助的发文单位）"（换行）→ 括注纯文本。
  [K1_SOE_SUBTABLE.govGrant]: flat([
    lbl('单位名称（注：政府补助的发文单位）'), txt('政府补助项目名称'), amt('期末余额'), txt('期末账龄'), txt('预计收取的时间、金额及依据'),
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

/**
 * 继续涉入：资产区 → 资产小计 → 负债区 → 负债小计（对齐源模板行序）。
 *
 * 金额列名两版不同：国企 §八、9 是「期末金额」（源 xlsx `B117`），
 * 上市 §五、8 是「期末数」（源 xlsx `B153`）→ 由 `amountKey` 区分，不能共用一个键。
 */
function mapContinuedInvolvement(
  snap: { continuedInvolvementRows?: K1ListedDisclosurePayloadV2['continuedInvolvementRows'] },
  amountKey: '期末金额' | '期末数' = '期末金额',
): Record<string, unknown>[] {
  const rows = snap.continuedInvolvementRows || []
  const totals = summarizeContinuedInvolvement(rows)
  const cell = (label: string, amount?: number, extra?: Record<string, unknown>) => ({
    label,
    ...(amount === undefined ? {} : { [amountKey]: amount }),
    ...(extra || {}),
  })
  const out: Record<string, unknown>[] = [cell('资产：', undefined, { row_kind: 'header' })]
  for (const r of rows.filter((x) => x.side === 'asset')) {
    out.push(cell(r.item || '（未命名）', r.amount))
  }
  out.push(cell('资产小计', totals.assets, { is_total: true }))
  out.push(cell('负债：', undefined, { row_kind: 'header' }))
  for (const r of rows.filter((x) => x.side === 'liability')) {
    out.push(cell(r.item || '（未命名）', r.amount))
  }
  out.push(cell('负债小计', totals.liabilities, { is_total: true }))
  return out
}

/**
 * 汇总表「其他应收款」三行 + 合计（条件表：三项全为 0/缺失时返回 `null` 不推送）。
 *
 * Requirement 4.1, 4.4 / Property 9：K1-1「与经审计的财务报表核对」区无值时，
 * 该表可能由 G2（应收利息）/ G3（应收股利）底稿承载 —— 调用方须据此判断是否
 * 进 `_removed_table_keys`（本函数只负责判断是否推送，不管理 removed 语义）。
 */
function buildK1SummaryRows(
  fs: K1SummaryFigures,
  endKey: string,
  otherLabel: string,
): Record<string, unknown>[] | null {
  const nonZero = [fs.interest, fs.dividend, fs.otherReceivable, fs.total]
    .some((v) => Math.abs(_num(v)) >= 0.005)
  if (!nonZero) return null
  // K1-1「与经审计的财务报表核对」区仅追踪当期，无上年年末/期初对应值 → 只填期末列，
  // 上年年末/期初列留空（该表若由 G2/G3 底稿承载，两处底稿各自补齐自己那两行的期初列）。
  return [
    { label: '应收利息', [endKey]: fs.interest },
    { label: '应收股利', [endKey]: fs.dividend },
    { label: otherLabel, [endKey]: fs.otherReceivable },
    { label: '合计', [endKey]: fs.total, is_total: true },
  ]
}

/**
 * 构造 `_note_texts` 条目（`[section, title, text]` 三元组）。
 *
 * 🔴 必须带中文 `title` —— 后端 `_format_note_texts` 缺 title 时回退到英文
 * `section` 键，附注正文会渲染成 `【listed-audit-note】` 这类英文键（K1 两版原全部
 * 缺失）。空文本过滤；全部为空时不产生 `_note_texts` 键（Property 8）。
 */
function noteTextRows(entries: Array<[string, string, string]>): Record<string, unknown>[] {
  return entries
    .filter(([, , text]) => String(text ?? '').trim())
    .map(([section, title, text]) => ({ section, title, text })) as unknown as Record<string, unknown>[]
}

// ─── 上市同步 ─────────────────────────────────────────────────────────────────

export function buildK1ListedSubTableData(
  snap: K1ListedDisclosurePayloadV2,
  auditNote = '',
  fs: K1SummaryFigures = { interest: 0, dividend: 0, otherReceivable: 0, total: 0 },
): Record<string, Record<string, unknown>[]> {
  const natureTotal = summarizeNatureRows(snap.natureRows || [])
  const notes = snap.notes || {}
  const summaryRows = buildK1SummaryRows(fs, '期末余额', '其他应收款')

  return {
    // 条件表：K1-1「与经审计的财务报表核对」区无值时不推送（可能由 G2/G3 承载）。
    ...(summaryRows ? { [K1_LISTED_SUBTABLE.summary]: summaryRows } : {}),
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
    // ⑧ 应收政府补助情况（源模板逐项披露；合计只对期末余额求和，账龄/时间列为 `--`）
    [K1_LISTED_SUBTABLE.govGrant]: [
      ...(snap.govGrantRows || []).map((r) => ({
        label: r.unitName || '（未命名）',
        政府补助项目名称: r.projectName,
        期末余额: r.endBalance,
        账龄: r.aging,
        '预计收取的时间、金额及依据': r.expectedCollection,
      })),
      {
        label: K1_NOTE_TOTAL_LABEL,
        期末余额: (snap.govGrantRows || []).reduce((s, r) => s + _num(r.endBalance), 0),
        is_total: true,
      },
    ],
    // ⑨ 因金融资产转移而终止确认（上市版比国企版多「转移方式」列）
    [K1_LISTED_SUBTABLE.transfer]: [
      ...(snap.transferRows || []).map((r) => ({
        label: r.item || '（未命名）',
        转移方式: r.method,
        终止确认金额: r.derecognizedAmount,
        与终止确认相关的利得或损失: r.gainLoss,
      })),
      {
        label: K1_NOTE_TOTAL_LABEL,
        终止确认金额: (snap.transferRows || []).reduce((s, r) => s + _num(r.derecognizedAmount), 0),
        与终止确认相关的利得或损失: (snap.transferRows || []).reduce((s, r) => s + _num(r.gainLoss), 0),
        is_total: true,
      },
    ],
    // ⑩ 转移且继续涉入形成的资产、负债（上市金额列名是「期末数」）
    [K1_LISTED_SUBTABLE.continuedInvolvement]: mapContinuedInvolvement(snap, '期末数'),
    _note_texts: noteTextRows([
      ['listed-audit-note', '审计说明', auditNote],
      ['listed-fund-centralization', '资金集中管理', snap.fundCentralizationNote || ''],
      ['listed-balance-change', '本期账面余额显著变动说明', notes.balanceChange || ''],
      ['listed-ecl-basis', '坏账准备计提金额及信用风险显著增加评估依据', notes.eclBasis || ''],
      ['listed-writeoff-note', '核销说明', notes.writeoffNote || ''],
      ['listed-transfer-note', '金融资产转移说明', notes.transferNote || ''],
      ['listed-stage2-none-end', '期末第二阶段说明', snap.stage2NoneEnd ? K1_STAGE2_NONE_TEXT_END : ''],
      ['listed-stage2-none-prior', '上年年末第二阶段说明', snap.stage2NonePrior ? K1_STAGE2_NONE_TEXT_PRIOR : ''],
    ]),
  }
}

export function buildK1ListedSyncPayloads(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snap: K1ListedDisclosurePayloadV2,
  auditNote = '',
  fs?: K1SummaryFigures,
): K1SyncFromWorkpaperPayload[] {
  const variant: K1DisclosureVariant = 'listed'
  if (!isK1DisclosureApplicable(variant, applicableStandards)) return []
  return [
    {
      wp_id: wpId,
      sheet_name: K1_DISCLOSURE_SHEET_NAME.listed,
      section_id: K1_NOTE_SECTION.listed,
      current_standard: resolveK1CurrentStandard(variant, applicableStandards),
      sub_table_data: buildK1ListedSubTableData(snap, auditNote, fs),
      columns: K1_LISTED_COLUMNS,
    },
  ]
}

// ─── SOE 国企同步 ─────────────────────────────────────────────────────────────

export function buildK1SoeSubTableData(
  snap: K1SoeDisclosurePayloadV2,
  auditNote = '',
  fs: K1SummaryFigures = { interest: 0, dividend: 0, otherReceivable: 0, total: 0 },
): Record<string, Record<string, unknown>[]> {
  const methodTotal = snap.methodRows.find((r) => r.rowKey === 'total')
  const notes = snap.notes || {}
  const agingRows = snap.agingRows || []
  const summaryRows = buildK1SummaryRows(fs, '期末余额', '其他应收款项')

  return {
    // 条件表：K1-1「与经审计的财务报表核对」区无值时不推送（可能由 G2/G3 承载）。
    ...(summaryRows ? { [K1_SOE_SUBTABLE.summary]: summaryRows } : {}),
    /**
     * 附注「按账龄披露其他应收款项」= 源模板单级 3 列（账 龄 / 期末数 / 期初数），
     * 行含账龄档 + `小  计` + `减：坏账准备` + `合  计`。
     *
     * 底稿账龄表本来就有这三行（`kind` 为 `subtotal` / `provision` / `total`），
     * 旧实现把它们过滤掉再压进合计行的额外两列 —— 现忠实推送，结构与源模板一致。
     * 合计行字面按源 xlsx A13/A15 用**双空格**「小  计」「合  计」。
     */
    [K1_SOE_SUBTABLE.aging]: agingRows.map((r) => ({
      label:
        r.kind === 'subtotal'
          ? K1_NOTE_SUBTOTAL_LABEL_WIDE
          : r.kind === 'total'
            ? K1_NOTE_TOTAL_LABEL_WIDE
            : r.label,
      期末数: r.endAmount,
      期初数: r.priorAmount,
      row_kind: r.kind,
      segment_key: r.segmentKey,
      is_total: r.kind === 'total' || r.kind === 'subtotal' || r.kind === 'subtotal1y',
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
    [K1_SOE_SUBTABLE.continuedInvolvement]: mapContinuedInvolvement(snap, '期末金额'),
    _note_texts: noteTextRows([
      ['soe-audit-note', '审计说明', auditNote],
      ['soe-balance-change', '本期账面余额显著变动说明', notes.balanceChange || ''],
      ['soe-ecl-basis', '坏账准备计提金额及信用风险显著增加评估依据', notes.eclBasis || ''],
      ['soe-transfer-note', '继续涉入说明', notes.transferNote || ''],
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
  fs?: K1SummaryFigures,
): K1SyncFromWorkpaperPayload[] {
  const variant: K1DisclosureVariant = 'soe'
  if (!isK1DisclosureApplicable(variant, applicableStandards)) return []
  return [
    {
      wp_id: wpId,
      sheet_name: K1_DISCLOSURE_SHEET_NAME.soe,
      section_id: K1_NOTE_SECTION.soe,
      current_standard: resolveK1CurrentStandard(variant, applicableStandards),
      sub_table_data: buildK1SoeSubTableData(snap, auditNote, fs),
      columns: K1_SOE_COLUMNS,
    },
  ]
}
