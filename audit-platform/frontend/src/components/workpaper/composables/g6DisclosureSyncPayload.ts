/**
 * G6 其他债权投资披露（上市）→ `disclosure_notes` 同步载荷
 *
 * 列结构与表名逐字对齐 `note_template_listed.json §五、15`（由
 * `backend/scripts/fix/fix_note_g_cycle_structure.py` 按权威模板
 * `backend/wp_templates/G/G6 其他债权投资.xlsx` 重建）。
 *
 * 🔴 三处口径：
 * 1. **两级表头只有 3 张表**：期末重要（父表头「期末余额」）/ 续表（「上年年末余额」）/
 *    三阶段迁移表（父表头「第一/二/三阶段」，合计列为独立列）。其余 11 张是单级 → 标 `flat`。
 * 2. **阶段表末列只有「期末第一阶段」是「理由」**，其余 5 张是「划分依据」（权威模板逐格核对）。
 * 3. **减值准备在其他综合收益中确认，不冲减资产负债表账面价值** → 阶段表的「账面价值」
 *    属减值分析口径，不得与主表公允价值列示口径混同（权威模板编制说明第 2、3 条）。
 *
 * spec: .kiro/specs/disclosure-sync-path-buildout/ Task 2.3
 */
import type { ColumnDef } from './disclosureColumnDefs'
import { defineColumns } from './disclosureColumnDefs'
import {
  G6_DISCLOSURE_SHEET_NAME,
  G6_LISTED_STAGE_SUBTABLE,
  G6_LISTED_SUBTABLE,
  G6_NOTE_SECTION,
  isG6DisclosureApplicable,
  resolveG6CurrentStandard,
} from './g6NoteSectionMap'
import {
  G6_TOTAL_LABEL,
  G6_WRITEOFF_ROW_LABEL,
  provisionClosing,
  stageMoveTotal,
  type G6BalanceRow,
  type G6FairValueRow,
  type G6ImportantRow,
  type G6ListedDisclosureState,
  type G6ProvisionMovementRow,
  type G6StageMoveRow,
  type G6WriteoffRow,
} from './g6ListedDisclosureRows'
import {
  isPlaceholderStageDetail,
  methodTotals,
  stageTotals,
  type G4StageBlock,
} from './g4ListedStageDisclosure'

const AMOUNT = 'amount' as const
const PERCENT = 'percent' as const

/** 「其中：」结构标签行（父行与明细之间），与 G4 同口径 */
export const G6_WHICH_LABEL = '其中：'
export const G6_INDIVIDUAL_LABEL = '按单项计提减值准备'
export const G6_PORTFOLIO_LABEL = '按组合计提减值准备'

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function txt(v: unknown): string {
  return String(v ?? '').trim()
}

/** 比率：分母 0 → null（不写 0，避免「0% 损失率」误读） */
function ratio(part: number, whole: number): number | null {
  if (!Number.isFinite(whole) || Math.abs(whole) < 1e-9) return null
  return Number(((part / whole) * 100).toFixed(4))
}

/**
 * 行型：源模板写的是「小 计」「合 计」（**中间带空格**），必须先去空白再比，
 * 否则小计 / 合计行被当普通数据行推给附注，丢掉 `is_total` 与加粗、勾稽语义。
 */
function rowMeta(label: string): { row_type: string; is_total?: true } {
  const compact = label.replace(/\s+/g, '')
  if (compact.startsWith('小计')) return { row_type: 'subtotal', is_total: true }
  if (compact.startsWith('合计')) return { row_type: 'total', is_total: true }
  return { row_type: 'data' }
}

function flat(defs: Array<Partial<ColumnDef> & { key: string; label: string }>): ColumnDef[] {
  return defineColumns(defs.map((d, i) => (i === 0 ? { ...d, is_label: true, flat: true } : d)))
}

// ─────────────────────────── 列定义 ───────────────────────────

const BALANCE_COLUMNS = flat([
  { key: 'label', label: '项目' },
  { key: 'end_balance', label: '期末余额', format: AMOUNT, align: 'right' },
  { key: 'prior_balance', label: '上年年末余额', format: AMOUNT, align: 'right' },
])

const FAIR_VALUE_COLUMNS = flat([
  { key: 'label', label: '项目' },
  { key: 'opening_fv', label: '期初余额', format: AMOUNT, align: 'right' },
  { key: 'accrued_interest', label: '应计利息', format: AMOUNT, align: 'right' },
  { key: 'fv_change_current', label: '本期公允价值变动', format: AMOUNT, align: 'right' },
  { key: 'closing_fv', label: '期末余额', format: AMOUNT, align: 'right' },
  { key: 'cost', label: '成本', format: AMOUNT, align: 'right' },
  { key: 'fv_change_cumulative', label: '累计公允价值变动', format: AMOUNT, align: 'right' },
  {
    key: 'oci_impairment',
    label: '累计在其他综合收益中确认的减值准备',
    format: AMOUNT,
    align: 'right',
  },
])

const PROVISION_COLUMNS = flat([
  { key: 'label', label: '项目' },
  { key: 'opening', label: '期初余额', format: AMOUNT, align: 'right' },
  { key: 'increase', label: '本期增加', format: AMOUNT, align: 'right' },
  { key: 'decrease', label: '本期减少', format: AMOUNT, align: 'right' },
  { key: 'closing', label: '期末余额', format: AMOUNT, align: 'right' },
])

/** 期末重要（两级表头，父表头是期间） */
function importantColumns(group: string, prefix: 'end' | 'prior'): ColumnDef[] {
  return defineColumns([
    { key: 'label', label: '项目', is_label: true },
    { key: `${prefix}_face_value`, label: '面值', group, format: AMOUNT, align: 'right' },
    { key: `${prefix}_coupon_rate`, label: '票面利率', group },
    { key: `${prefix}_effective_rate`, label: '实际利率', group },
    { key: `${prefix}_maturity_date`, label: '到期日', group },
    { key: `${prefix}_overdue_principal`, label: '逾期本金', group, format: AMOUNT, align: 'right' },
  ])
}

/** 三阶段减值表（单级表头）；末列名两种（理由 / 划分依据）由调用方给定 */
export function g6StageColumnsFor(rateLabel: string, reasonHeader: string): ColumnDef[] {
  return flat([
    { key: 'label', label: '类别' },
    { key: 'gross', label: '账面余额', format: AMOUNT, align: 'right' },
    { key: 'loss_rate', label: rateLabel, format: PERCENT, align: 'right' },
    { key: 'provision', label: '减值准备', format: AMOUNT, align: 'right' },
    { key: 'net', label: '账面价值', format: AMOUNT, align: 'right' },
    { key: 'reason', label: reasonHeader },
  ])
}

/** 三阶段迁移表（两级：第一/二/三阶段 → 具体损失口径；减值准备与合计为独立列） */
const STAGE_MOVE_COLUMNS: ColumnDef[] = defineColumns([
  { key: 'label', label: '减值准备', is_label: true },
  { key: 'stage1', label: '未来12个月预期信用损失', group: '第一阶段', format: AMOUNT, align: 'right' },
  {
    key: 'stage2',
    label: '整个存续期预期信用损失（未发生信用减值）',
    group: '第二阶段',
    format: AMOUNT,
    align: 'right',
  },
  {
    key: 'stage3',
    label: '整个存续期预期信用损失（已发生信用减值）',
    group: '第三阶段',
    format: AMOUNT,
    align: 'right',
  },
  { key: 'total', label: '合计', format: AMOUNT, align: 'right' },
])

const WRITEOFF_COLUMNS = flat([
  { key: 'label', label: '项目' },
  { key: 'writeoff_amount', label: '核销金额', format: AMOUNT, align: 'right' },
])

const WRITEOFF_DETAIL_COLUMNS = flat([
  { key: 'label', label: '项目' },
  { key: 'nature', label: '其他债权投资性质' },
  { key: 'amount', label: '核销金额', format: AMOUNT, align: 'right' },
  { key: 'reason', label: '核销原因' },
  { key: 'procedure', label: '履行的核销程序' },
  { key: 'related_party', label: '是否由关联交易产生' },
])

export function buildG6ListedColumns(
  stageBlocks: readonly G4StageBlock[] = [],
): Record<string, ColumnDef[]> {
  const out: Record<string, ColumnDef[]> = {
    [G6_LISTED_SUBTABLE.balance]: BALANCE_COLUMNS,
    [G6_LISTED_SUBTABLE.fairValue]: FAIR_VALUE_COLUMNS,
    [G6_LISTED_SUBTABLE.provision]: PROVISION_COLUMNS,
    [G6_LISTED_SUBTABLE.importantEnd]: importantColumns('期末余额', 'end'),
    [G6_LISTED_SUBTABLE.importantPrior]: importantColumns('上年年末余额', 'prior'),
    [G6_LISTED_SUBTABLE.stageMove]: STAGE_MOVE_COLUMNS,
    [G6_LISTED_SUBTABLE.writeoff]: WRITEOFF_COLUMNS,
    [G6_LISTED_SUBTABLE.writeoffDetail]: WRITEOFF_DETAIL_COLUMNS,
  }
  const blocks = stageBlocks.length ? stageBlocks : []
  G6_LISTED_STAGE_SUBTABLE.forEach((name, i) => {
    const b = blocks[i]
    out[name] = g6StageColumnsFor(
      b?.rateLabel ?? (i === 0 || i === 3 ? '未来12个月内预期信用损失率(%)' : '整个存续期预期信用损失率(%)'),
      b?.reasonHeader ?? (i === 0 ? '理由' : '划分依据'),
    )
  })
  return out
}

// ─────────────────────────── 行构建 ───────────────────────────

export function buildG6BalanceRows(rows: readonly G6BalanceRow[]): Record<string, unknown>[] {
  return rows.map((r) => ({
    label: txt(r.label),
    end_balance: num(r.endBalance),
    prior_balance: num(r.priorBalance),
    ...rowMeta(txt(r.label)),
  }))
}

export function buildG6FairValueRows(rows: readonly G6FairValueRow[]): Record<string, unknown>[] {
  return rows.map((r) => ({
    label: txt(r.label),
    opening_fv: num(r.openingFv),
    accrued_interest: num(r.accruedInterest),
    fv_change_current: num(r.fvChangeCurrent),
    closing_fv: num(r.closingFv),
    cost: num(r.cost),
    fv_change_cumulative: num(r.fvChangeCumulative),
    oci_impairment: num(r.ociImpairment),
    ...rowMeta(txt(r.label)),
  }))
}

export function buildG6ProvisionRows(
  rows: readonly G6ProvisionMovementRow[],
): Record<string, unknown>[] {
  return rows.map((r) => ({
    label: txt(r.label),
    opening: num(r.opening),
    increase: num(r.increase),
    decrease: num(r.decrease),
    closing: provisionClosing(r),
    ...rowMeta(txt(r.label)),
  }))
}

export function buildG6ImportantRows(
  rows: readonly G6ImportantRow[],
  period: 'end' | 'prior',
): Record<string, unknown>[] {
  return rows.map((r) => {
    const label = txt(r.label)
    const meta = rowMeta(label)
    const isTotal = meta.row_type === 'total'
    return {
      label,
      [`${period}_face_value`]: num(r.faceValue),
      // 源模板合计行的票面利率 / 实际利率 / 到期日列示为「--」→ 用 null 表达「不加总」
      [`${period}_coupon_rate`]: isTotal ? null : txt(r.couponRate),
      [`${period}_effective_rate`]: isTotal ? null : txt(r.effectiveRate),
      [`${period}_maturity_date`]: isTotal ? null : txt(r.maturityDate),
      [`${period}_overdue_principal`]: num(r.overduePrincipal),
      ...meta,
    }
  })
}

function stageRow(
  label: string,
  gross: number,
  provision: number,
  reason: string,
  extra: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    label,
    gross,
    loss_rate: ratio(provision, gross),
    provision,
    net: Number((gross - provision).toFixed(2)),
    reason,
    row_type: 'data',
    ...extra,
  }
}

/**
 * 单张阶段表的行：按单项 → 其中： → 逐项明细 → 按组合 → 其中： → 逐项明细 → 合计。
 *
 * 🔴「其中：」结构行不能省：附注是交付物，缺了读者看不出下面的明细是上一行的拆分。
 * 空值列写 null 以保持列键齐备（不破坏 columns 键集契约）。
 */
export function buildG6StageRows(block: G4StageBlock): Record<string, unknown>[] {
  const out: Record<string, unknown>[] = []
  for (const [label, method] of [
    [G6_INDIVIDUAL_LABEL, block.individual],
    [G6_PORTFOLIO_LABEL, block.portfolio],
  ] as const) {
    const t = methodTotals(method)
    out.push(stageRow(label, t.bookBalance, t.impairment, ''))
    out.push({
      label: G6_WHICH_LABEL,
      gross: null,
      loss_rate: null,
      provision: null,
      net: null,
      reason: '',
      row_type: 'data',
    })
    for (const d of method.details) {
      // 空白骨架行不推（否则附注多出一行全零、名字还叫「其中：」的幽灵数据行）
      if (isPlaceholderStageDetail(d)) continue
      out.push(stageRow(txt(d.name), num(d.bookBalance), num(d.impairment), txt(d.reason)))
    }
  }
  const total = stageTotals(block)
  out.push(
    stageRow(G6_TOTAL_LABEL.replace(/\s+/g, ''), total.bookBalance, total.impairment, '', {
      is_total: true,
      row_type: 'total',
    }),
  )
  return out
}

export function buildG6StageMoveRows(
  rows: readonly G6StageMoveRow[],
): Record<string, unknown>[] {
  return rows.map((r) => ({
    label: txt(r.label),
    row_key: r.rowKey,
    stage1: num(r.stage1),
    stage2: num(r.stage2),
    stage3: num(r.stage3),
    total: stageMoveTotal(r),
    ...(r.rowKey === 'closing' ? { is_total: true, row_type: 'total' } : { row_type: 'data' }),
  }))
}

export function buildG6WriteoffRows(
  detailRows: readonly G6WriteoffRow[],
  writeoffTotal: number,
): Record<string, unknown>[] {
  const detailSum = detailRows.reduce((s, r) => s + num(r.amount), 0)
  return [
    {
      label: G6_WRITEOFF_ROW_LABEL,
      // 手工填的总额优先（含不重要款项）；未填则回退明细之和
      writeoff_amount: num(writeoffTotal) || detailSum,
      row_type: 'data',
    },
  ]
}

export function buildG6WriteoffDetailRows(
  rows: readonly G6WriteoffRow[],
): Record<string, unknown>[] {
  const data = rows
    .filter((r) => txt(r.label) || num(r.amount) !== 0)
    .map((r) => ({
      label: txt(r.label),
      nature: txt(r.nature),
      amount: num(r.amount),
      reason: txt(r.reason),
      procedure: txt(r.procedure),
      related_party: r.relatedParty ? '是' : '否',
      row_type: 'data',
    }))
  return [
    ...data,
    {
      label: G6_TOTAL_LABEL.replace(/\s+/g, ''),
      nature: '',
      amount: data.reduce((s, r) => s + num(r.amount), 0),
      reason: '',
      procedure: '',
      related_party: '',
      is_total: true,
      row_type: 'total',
    },
  ]
}

// ─────────────────────────── 载荷装配 ───────────────────────────

export interface G6SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

function pushText(out: Array<Record<string, string>>, section: string, text: string): void {
  const t = txt(text)
  if (t) out.push({ section, text: t })
}

export function buildG6ListedSubTableData(
  state: G6ListedDisclosureState,
): Record<string, unknown> {
  const out: Record<string, unknown> = {
    [G6_LISTED_SUBTABLE.balance]: buildG6BalanceRows(state.balanceRows),
    [G6_LISTED_SUBTABLE.fairValue]: buildG6FairValueRows(state.fairValueRows),
    [G6_LISTED_SUBTABLE.provision]: buildG6ProvisionRows(state.provisionRows),
    [G6_LISTED_SUBTABLE.importantEnd]: buildG6ImportantRows(state.importantEndRows, 'end'),
    [G6_LISTED_SUBTABLE.importantPrior]: buildG6ImportantRows(state.importantPriorRows, 'prior'),
    [G6_LISTED_SUBTABLE.stageMove]: buildG6StageMoveRows(state.stageMoveRows),
    [G6_LISTED_SUBTABLE.writeoff]: buildG6WriteoffRows(state.writeoffRows, state.writeoffTotal),
    [G6_LISTED_SUBTABLE.writeoffDetail]: buildG6WriteoffDetailRows(state.writeoffRows),
  }
  G6_LISTED_STAGE_SUBTABLE.forEach((name, i) => {
    const block = state.stageBlocks[i]
    if (block) out[name] = buildG6StageRows(block)
  })
  const texts: Array<Record<string, string>> = []
  pushText(texts, 'listed-fair-value-note', state.fvNote)
  pushText(texts, 'listed-significant-change', state.significantChangeNote)
  pushText(texts, 'listed-judgement-basis', state.judgementBasisNote)
  if (texts.length) out._note_texts = texts
  return out
}

/** @returns null=该变体不适用 / 缺 wpId */
export function buildG6ListedSyncPayload(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  state: G6ListedDisclosureState,
): G6SyncFromWorkpaperPayload | null {
  if (!wpId || !isG6DisclosureApplicable('listed', applicableStandards)) return null
  return {
    wp_id: wpId,
    sheet_name: G6_DISCLOSURE_SHEET_NAME.listed,
    section_id: G6_NOTE_SECTION.listed,
    current_standard: resolveG6CurrentStandard('listed', applicableStandards),
    sub_table_data: buildG6ListedSubTableData(state),
    columns: buildG6ListedColumns(state.stageBlocks),
  }
}
