/**
 * N1 递延所得税资产披露 ↔ 附注章节冻结映射与 sync payload 构建
 *
 * 权威来源：
 * - 章节号：`backend/data/note_template_variant_matrix.json` 的
 *   `di_yan_suo_de_shui_zi_chan_he_di_yan_suo_de` → listed 五、30 / soe 八、31
 * - 表名/列头：`note_template_listed.json` 五、30 / `note_template_soe.json` 八、31
 *   （逐字对照 tables[].name / tables[].headers，禁止自造）
 * - sheet 名：`workpaper_sheet_classification`（wp_code=N1）实测为全角括号
 *   `附注披露信息（上市公司）` / `附注披露信息（国企）`
 *
 * 🔴 共用章节所有权（spec n1-disclosure-note-linkage · Decision 1 · 方案 A）：
 * 五、30 / 八、31 由 **N1（递延所得税资产）与 N3（递延所得税负债）共用**，
 * 且第一/第二张子表在同一张表内混合资产段与负债段行；而 sync_from_workpaper 对
 * sub_table_data 是「按键浅合并、同名键整体覆盖」→ 若两边各推同名键必然互相冲掉。
 * 因此本章节**四张子表的 owner 统一为 N1**：N3 不得推送这两张共用表，
 * 只能发布跨底稿键（如 `N1-4-total-deferred-tax-liability`）供 N1 取用。
 * 负债段/互抵金额取不到时值为 `null`（不填 0，0 会被误读为"已核实为零"）。
 */
import type { ColumnDef } from './disclosureColumnDefs'

export type N1DisclosureVariant = 'listed' | 'soe'

/** 附注章节号（权威矩阵 di_yan_suo_de_shui_zi_chan_he_di_yan_suo_de） */
export const N1_NOTE_SECTION = {
  listed: '五、30',
  soe: '八、31',
} as const satisfies Record<N1DisclosureVariant, string>

/** 底稿披露 sheet 真实 tab 名（供 _last_sync_sheet 反向定位） */
export const N1_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<N1DisclosureVariant, string>

/** 子表键（逐字取自附注模板 tables[].name，按变体分别定义） */
export const N1_SUB_TABLE_KEYS = {
  listed: {
    unoffset: '未经抵销的递延所得税资产和递延所得税负债',
    netOffset: '以抵销后净额列示的递延所得税资产或负债',
    unrecognized: '未确认递延所得税资产的可抵扣暂时性差异及可抵扣亏损明细',
    lossExpiry: '未确认递延所得税资产的可抵扣亏损将于以下年度到期',
  },
  soe: {
    unoffset: '未经抵销的递延所得税资产和递延所得税负债',
    netOffset: '以抵销后净额列示的递延所得税资产或负债',
    unrecognized: '未确认递延所得税资产明细',
    lossExpiry: '未确认递延所得税资产的可抵扣亏损将于以下年度到期',
  },
} as const satisfies Record<N1DisclosureVariant, Record<string, string>>

/** 资产段/负债段分组标题行（逐字取自模板 rows） */
export const N1_GROUP_LABELS = {
  listed: { asset: '递延所得税资产：', liability: '递延所得税负债：' },
  soe: { asset: '一、递延所得税资产', liability: '二、递延所得税负债' },
} as const satisfies Record<N1DisclosureVariant, { asset: string; liability: string }>

export function resolveN1CurrentStandard(
  variant: N1DisclosureVariant,
  applicableStandards?: readonly string[] | null,
): string {
  const list = (applicableStandards || []).map((s) => String(s).toLowerCase())
  if (variant === 'listed') {
    if (list.some((s) => s === 'listed_consolidated' || (s.includes('listed') && s.includes('consol')))) {
      return 'listed_consolidated'
    }
    return 'listed_standalone'
  }
  if (list.some((s) => s === 'soe_consolidated' || (s.includes('soe') && s.includes('consol')))) {
    return 'soe_consolidated'
  }
  return 'soe_standalone'
}

// ─── 列头元数据（逐字取自模板 headers）──────────────────────────────────────

const AMT = 'amount' as const
const TXT = 'text' as const

/** 表一/表三：项目 + 期末余额 + （listed 上年年末余额 / soe 期初余额） */
function twoPeriodColumns(variant: N1DisclosureVariant, labelHeader = '项目'): ColumnDef[] {
  return [
    { key: 'item', label: labelHeader, is_label: true },
    { key: 'end', label: '期末余额', format: AMT },
    { key: 'prior', label: variant === 'listed' ? '上年年末余额' : '期初余额', format: AMT },
  ]
}

/**
 * 表二（抵销后净额）：listed 5 列（含互抵金额），soe 仅 3 列（期末/期初）。
 * 🔴 两变体列结构本质不同，不可按 variant 只换 label 硬套。
 */
function netOffsetColumns(variant: N1DisclosureVariant): ColumnDef[] {
  if (variant === 'listed') {
    return [
      { key: 'item', label: '项目', is_label: true },
      { key: 'offsetEnd', label: '递延所得税资产和负债期末互抵金额', format: AMT },
      { key: 'netEnd', label: '抵销后递延所得税资产或负债期末余额', format: AMT },
      { key: 'offsetPrior', label: '递延所得税资产和负债上年年末互抵金额', format: AMT },
      { key: 'netPrior', label: '抵销后递延所得税资产或负债上年年末余额', format: AMT },
    ]
  }
  return [
    { key: 'item', label: '项目', is_label: true },
    { key: 'end', label: '期末', format: AMT },
    { key: 'prior', label: '期初', format: AMT },
  ]
}

/** 表四（亏损到期）：年份 + 期末 + （上年年末 / 期初）+ 备注 */
function lossExpiryColumns(variant: N1DisclosureVariant): ColumnDef[] {
  return [
    { key: 'year', label: '年份', is_label: true },
    { key: 'end', label: '期末余额', format: AMT },
    { key: 'prior', label: variant === 'listed' ? '上年年末余额' : '期初余额', format: AMT },
    { key: 'remark', label: '备注', format: TXT },
  ]
}

// ─── Snapshot 类型（由披露组件组装）─────────────────────────────────────────

/** 可空金额：`null` 表示"未取到"（禁止用 0 冒充） */
export type NullableAmount = number | null

export interface N1AssetItemRow {
  item: string
  /** 递延税资产期末余额（审定） */
  endBalance: NullableAmount
  /** 期初/上年年末余额 */
  priorBalance: NullableAmount
}

export interface N1UnrecognizedRowLike {
  item: string
  amount: NullableAmount
  priorAmount?: NullableAmount
}

export interface N1LossExpiryRowLike {
  /** 到期年度（如 "2027"），构造时补「年」字 */
  expiryYear: string
  unrecovered: NullableAmount
  priorUnrecovered?: NullableAmount
  remark?: string
}

export interface N1NetOffsetSnapshot {
  assetOffsetEnd?: NullableAmount
  assetNetEnd?: NullableAmount
  assetOffsetPrior?: NullableAmount
  assetNetPrior?: NullableAmount
  liabOffsetEnd?: NullableAmount
  liabNetEnd?: NullableAmount
  liabOffsetPrior?: NullableAmount
  liabNetPrior?: NullableAmount
}

export interface N1DisclosureSnapshot {
  /** 已确认递延所得税资产逐项（不含合计行，合计由本模块生成小计行） */
  assetRows: N1AssetItemRow[]
  /** 负债段逐项（业务上属 N3；无数据时留空 → 只出分组标题 + null 小计） */
  liabilityRows?: N1AssetItemRow[]
  /** 负债段小计（取自 N1-4 测算表负债部分或 N3 发布键；取不到 null） */
  liabilitySubtotal?: { endBalance: NullableAmount; priorBalance: NullableAmount }
  netOffset?: N1NetOffsetSnapshot
  unrecognizedRows: N1UnrecognizedRowLike[]
  lossExpiryRows: N1LossExpiryRowLike[]
  /** 说明/结论文本（按子节，值为空串则不同步） */
  notes?: Record<string, string>
}

export interface N1SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  year: number
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

// ─── helpers ─────────────────────────────────────────────────────────────────

const nz = (v: unknown): NullableAmount =>
  typeof v === 'number' && Number.isFinite(v) ? v : null

/** 可空求和：全为 null 时返回 null（不塌成 0） */
function sumNullable(vals: readonly NullableAmount[]): NullableAmount {
  let has = false
  let total = 0
  for (const v of vals) {
    if (v === null || v === undefined) continue
    has = true
    total += v
  }
  return has ? Math.round(total * 100) / 100 : null
}

const NOTE_TITLES: Record<string, string> = {
  conclusion: '披露说明与结论',
  sufficiency: '确认充足性判断说明',
  n3: '与递延所得税负债的抵销/分列说明',
  unrecognized: '未确认递延所得税资产说明',
}

/** 各子节说明 → `_note_texts`（仅非空；全空则调用方不写该键） */
export function buildN1NoteTexts(
  notes?: Record<string, string>,
): Array<{ section: string; title: string; text: string }> {
  if (!notes) return []
  const order = ['conclusion', 'sufficiency', 'n3', 'unrecognized']
  const keys = [...order.filter((k) => k in notes), ...Object.keys(notes).filter((k) => !order.includes(k))]
  const out: Array<{ section: string; title: string; text: string }> = []
  for (const k of keys) {
    const text = String(notes[k] ?? '').trim()
    if (!text) continue
    out.push({ section: `n1-disclosure-${k}`, title: NOTE_TITLES[k] || k, text })
  }
  return out
}

// ─── payload 构造（纯函数）───────────────────────────────────────────────────

/**
 * 构造 N1 披露表 → 附注 sync 请求体。
 *
 * 覆盖该章节全部 4 张子表（owner=N1）；`sub_table_data` 与 `columns` 的键集合恒相同
 * （投影器按键名匹配，键不一致则附注端渲染不出列头）。
 */
export function buildN1SyncPayload(
  variant: N1DisclosureVariant,
  snapshot: N1DisclosureSnapshot,
  ctx: { wpId: string; year: number; applicableStandards?: readonly string[] | null },
): N1SyncPayload {
  const K = N1_SUB_TABLE_KEYS[variant]
  const G = N1_GROUP_LABELS[variant]

  const subTableData: Record<string, unknown> = {}
  const columns: Record<string, ColumnDef[]> = {}

  // ① 未经抵销的递延所得税资产和递延所得税负债（资产段 + 负债段，owner=N1）
  const assetRows = snapshot.assetRows || []
  const unoffsetRows: Array<Record<string, unknown>> = [
    { item: G.asset, label: G.asset, end: null, prior: null },
    ...assetRows.map((r) => ({
      item: String(r.item ?? ''),
      label: String(r.item ?? ''),
      end: nz(r.endBalance),
      prior: nz(r.priorBalance),
    })),
    {
      item: '小计',
      label: '小计',
      end: sumNullable(assetRows.map((r) => nz(r.endBalance))),
      prior: sumNullable(assetRows.map((r) => nz(r.priorBalance))),
      is_total: true,
    },
    { item: G.liability, label: G.liability, end: null, prior: null },
    ...(snapshot.liabilityRows || []).map((r) => ({
      item: String(r.item ?? ''),
      label: String(r.item ?? ''),
      end: nz(r.endBalance),
      prior: nz(r.priorBalance),
    })),
    {
      item: '小计',
      label: '小计',
      // 负债段取不到 → null（Property 10：不填 0）
      end: snapshot.liabilityRows?.length
        ? sumNullable(snapshot.liabilityRows.map((r) => nz(r.endBalance)))
        : nz(snapshot.liabilitySubtotal?.endBalance),
      prior: snapshot.liabilityRows?.length
        ? sumNullable(snapshot.liabilityRows.map((r) => nz(r.priorBalance)))
        : nz(snapshot.liabilitySubtotal?.priorBalance),
      is_total: true,
    },
  ]
  subTableData[K.unoffset] = unoffsetRows
  columns[K.unoffset] = twoPeriodColumns(variant)

  // ② 以抵销后净额列示的递延所得税资产或负债（owner=N1；缺失 null）
  const off = snapshot.netOffset || {}
  if (variant === 'listed') {
    subTableData[K.netOffset] = [
      {
        item: '递延所得税资产', label: '递延所得税资产',
        offsetEnd: nz(off.assetOffsetEnd), netEnd: nz(off.assetNetEnd),
        offsetPrior: nz(off.assetOffsetPrior), netPrior: nz(off.assetNetPrior),
      },
      {
        item: '递延所得税负债', label: '递延所得税负债',
        offsetEnd: nz(off.liabOffsetEnd), netEnd: nz(off.liabNetEnd),
        offsetPrior: nz(off.liabOffsetPrior), netPrior: nz(off.liabNetPrior),
      },
    ]
  } else {
    subTableData[K.netOffset] = [
      {
        item: G.asset, label: G.asset,
        end: nz(off.assetNetEnd), prior: nz(off.assetNetPrior),
      },
      {
        item: G.liability, label: G.liability,
        end: nz(off.liabNetEnd), prior: nz(off.liabNetPrior),
      },
    ]
  }
  columns[K.netOffset] = netOffsetColumns(variant)

  // ③ 未确认递延所得税资产明细（纯资产侧）
  const unrec = snapshot.unrecognizedRows || []
  subTableData[K.unrecognized] = [
    ...unrec.map((r) => ({
      item: String(r.item ?? ''),
      label: String(r.item ?? ''),
      end: nz(r.amount),
      prior: nz(r.priorAmount),
    })),
    {
      item: '合计', label: '合计',
      end: sumNullable(unrec.map((r) => nz(r.amount))),
      prior: sumNullable(unrec.map((r) => nz(r.priorAmount))),
      is_total: true,
    },
  ]
  columns[K.unrecognized] = twoPeriodColumns(variant)

  // ④ 未确认递延所得税资产的可抵扣亏损将于以下年度到期（按到期年度聚合）
  const lossRows = snapshot.lossExpiryRows || []
  const byYear = new Map<string, { end: NullableAmount[]; prior: NullableAmount[]; remarks: string[] }>()
  for (const r of lossRows) {
    const y = String(r.expiryYear ?? '').trim()
    if (!y || y === '—') continue
    const key = /年$/.test(y) ? y : `${y}年`
    const slot = byYear.get(key) || { end: [], prior: [], remarks: [] }
    slot.end.push(nz(r.unrecovered))
    slot.prior.push(nz(r.priorUnrecovered))
    const rm = String(r.remark ?? '').trim()
    if (rm) slot.remarks.push(rm)
    byYear.set(key, slot)
  }
  const expiryRows = [...byYear.entries()]
    .sort((a, b) => a[0].localeCompare(b[0], 'zh-CN'))
    .map(([year, slot]) => ({
      year, label: year,
      end: sumNullable(slot.end),
      prior: sumNullable(slot.prior),
      remark: slot.remarks.join('；'),
    }))
  subTableData[K.lossExpiry] = [
    ...expiryRows,
    {
      year: '合计', label: '合计',
      end: sumNullable(expiryRows.map((r) => r.end)),
      prior: sumNullable(expiryRows.map((r) => r.prior)),
      remark: '',
      is_total: true,
    },
  ]
  columns[K.lossExpiry] = lossExpiryColumns(variant)

  // ⑤ 说明文本（空则不写 `_note_texts`，避免覆盖附注既有正文）
  const texts = buildN1NoteTexts(snapshot.notes)
  if (texts.length > 0) subTableData._note_texts = texts

  return {
    wp_id: ctx.wpId,
    sheet_name: N1_DISCLOSURE_SHEET_NAME[variant],
    section_id: N1_NOTE_SECTION[variant],
    current_standard: resolveN1CurrentStandard(variant, ctx.applicableStandards),
    year: ctx.year,
    sub_table_data: subTableData,
    columns,
  }
}

export default buildN1SyncPayload
