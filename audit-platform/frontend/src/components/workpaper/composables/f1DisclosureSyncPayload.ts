/**
 * F1 披露 → disclosure_notes sync payload
 *
 * 子表名与 `note_template_listed.json` §五、7 / `note_template_soe.json` §八、7
 * 的 `tables[].name` **逐字一致**（对齐脚本：`backend/scripts/fix/fix_note_prepayment_structure.py`）。
 *
 * 列结构裁决（三源互证，详见 spec design §二）：
 * - 按账龄表 = 5 列（账龄 + 期末{金额,比例} + 期初{金额,比例}）+ 7 行
 *   （各账龄段 + 小计 + 减：减值准备 + 合计）——附注模版与校验预设 F7-6/F7-7/F7-8 一致；
 *   国企底稿保留的逐账龄段「减值准备」列在此**聚合**为「减：减值准备」行。
 * - 上市「账龄超过1年的重要预付款项」无「账龄」「未结算的原因」列（F7-9 listed）。
 * - 上市「前五名」无「减值准备」列（F7-13 listed）；国企前五名第 4 列名为「减值准备」（F7-13 soe）。
 *
 * spec: .kiro/specs/f1-prepayment-disclosure-template-alignment/ R4
 */
import type { F1DisclosureVariant } from './f1NoteSectionMap'
import {
  F1_DISCLOSURE_SHEET_NAME,
  F1_NOTE_SECTION,
  isF1DisclosureApplicable,
  resolveF1CurrentStandard,
} from './f1NoteSectionMap'

import type { ColumnDef } from './disclosureColumnDefs'

export interface F1SyncFromWorkpaperPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  /**
   * 审计年度（显式传入，不依赖后端兜底）。
   * 后端 `_resolve_target_year` 优先用 payload.year，其次 projects.audit_year，
   * 最后才是服务器自然年 —— 显式传 year 可避免跨年场景写到错误年度的附注。
   */
  year?: number
  sub_table_data: Record<string, unknown>
  /** 列头元数据（disclosure-table-sync-convergence）：label 取自源模板列头 */
  columns?: Record<string, ColumnDef[]>
}

// ─── 子表名常量（与 note_template_*.json tables[].name 逐字一致） ───────────────

export const F1_LISTED_SUBTABLE = {
  AGING: '预付款项按账龄披露',
  OVER1: '账龄超过1年的重要预付款项',
  TOP5: '按预付对象归集的预付款项期末余额前五名单位情况',
} as const

export const F1_SOE_SUBTABLE = {
  AGING: '预付款项按账龄列示',
  OVER1: '账龄超过1年的大额预付款项',
  TOP5: '按欠款方归集的期末余额前五名的预付款项',
} as const

/**
 * 旧实现遗留的上市版表名（原第 3 张表误用标签列列头「单位名称」当表名）。
 * 随同步载荷以 `_removed_table_keys` 上报，由后端从附注 `sub_table_data` /
 * `_sub_table_columns` 删除，避免附注永久残留一张空表。
 */
export const F1_LISTED_OBSOLETE_TABLE_KEYS = ['单位名称'] as const

// ─── 列头字面单一真源（源 xlsx 逐格实证，含空格；底稿 Tab 模板亦引用本组常量） ──────
//
// 🔴 空格必须逐字保留（与平台 `账  龄` / `小 计` / `合  计` 同族约定）：
//   上市 `A8=账  龄`（双空格）/ `B8=期末数` / `D8=上年年末数` / `B9=金  额`（双空格）/ `C9=比例%`
//   国企 `A8=账  龄`（双空格）/ `B8=期末数` / `E8=期初数` / `B10=金 额`（**单**空格）/ `C10=比例（%）`
//
// 数据 key（label / end_amount / end_pct / prior_amount / prior_pct）**逐字不变** ——
// 改 key 会让整表数据在附注侧丢落点。

/** 两版按账龄表的标签列列头（源 A8，双空格） */
export const F1_AGING_LABEL_COL = '账  龄'
/** 上市按账龄表两级表头父组名（源 B8 / D8） */
export const F1_LISTED_AGING_GROUPS = { end: '期末数', prior: '上年年末数' } as const
/** 国企按账龄表两级表头父组名（源 B8 / E8） */
export const F1_SOE_AGING_GROUPS = { end: '期末数', prior: '期初数' } as const
/** 上市金额列列头（源 B9，双空格） */
export const F1_LISTED_AMOUNT_LABEL = '金  额'
/** 国企金额列列头（源 B10，单空格） */
export const F1_SOE_AMOUNT_LABEL = '金 额'
/** 比例列列头（上市源 C9 / 国企源 C10） */
export const F1_LISTED_PCT_LABEL = '比例%'
export const F1_SOE_PCT_LABEL = '比例（%）'

// ─── 列定义（键与 build*SubTableData 行键、note_template columns 逐字一致） ─────

export const F1_LISTED_COLUMNS: Record<string, ColumnDef[]> = {
  [F1_LISTED_SUBTABLE.AGING]: [
    { key: 'label', label: F1_AGING_LABEL_COL, is_label: true },
    {
      key: 'end_amount',
      label: F1_LISTED_AMOUNT_LABEL,
      group: F1_LISTED_AGING_GROUPS.end,
      format: 'amount',
    },
    {
      key: 'end_pct',
      label: F1_LISTED_PCT_LABEL,
      group: F1_LISTED_AGING_GROUPS.end,
      format: 'percent',
    },
    {
      key: 'prior_amount',
      label: F1_LISTED_AMOUNT_LABEL,
      group: F1_LISTED_AGING_GROUPS.prior,
      format: 'amount',
    },
    {
      key: 'prior_pct',
      label: F1_LISTED_PCT_LABEL,
      group: F1_LISTED_AGING_GROUPS.prior,
      format: 'percent',
    },
  ],
  [F1_LISTED_SUBTABLE.OVER1]: [
    { key: 'label', label: '债务人名称', is_label: true, flat: true },
    { key: 'balance', label: '账面余额', format: 'amount' },
    { key: 'proportion_pct', label: '占预付款项合计的比例（%）', format: 'percent' },
    { key: 'impairment', label: '减值准备', format: 'amount' },
  ],
  [F1_LISTED_SUBTABLE.TOP5]: [
    { key: 'label', label: '单位名称', is_label: true, flat: true },
    { key: 'end_amount', label: '预付款项期末余额', format: 'amount' },
    { key: 'proportion_pct', label: '占预付款项期末余额合计数的比例%', format: 'percent' },
  ],
}

export const F1_SOE_COLUMNS: Record<string, ColumnDef[]> = {
  [F1_SOE_SUBTABLE.AGING]: [
    { key: 'label', label: F1_AGING_LABEL_COL, is_label: true },
    {
      key: 'end_amount',
      label: F1_SOE_AMOUNT_LABEL,
      group: F1_SOE_AGING_GROUPS.end,
      format: 'amount',
    },
    {
      key: 'end_pct',
      label: F1_SOE_PCT_LABEL,
      group: F1_SOE_AGING_GROUPS.end,
      format: 'percent',
    },
    {
      key: 'prior_amount',
      label: F1_SOE_AMOUNT_LABEL,
      group: F1_SOE_AGING_GROUPS.prior,
      format: 'amount',
    },
    {
      key: 'prior_pct',
      label: F1_SOE_PCT_LABEL,
      group: F1_SOE_AGING_GROUPS.prior,
      format: 'percent',
    },
  ],
  [F1_SOE_SUBTABLE.OVER1]: [
    { key: 'creditor_unit', label: '债权单位', is_label: true, flat: true },
    { key: 'debtor_unit', label: '债务单位' },
    { key: 'end_balance', label: '期末余额', format: 'amount' },
    { key: 'aging', label: '账龄' },
    { key: 'reason', label: '未结算的原因' },
  ],
  [F1_SOE_SUBTABLE.TOP5]: [
    { key: 'label', label: '债务人名称', is_label: true, flat: true },
    { key: 'end_amount', label: '账面余额', format: 'amount' },
    { key: 'proportion_pct', label: '占预付款项合计的比例（%）', format: 'percent' },
    { key: 'impairment', label: '减值准备', format: 'amount' },
  ],
}

/** 两版账龄表共用的行标签（附注模版口径） */
export const F1_AGING_SUBTOTAL_LABEL = '小计'
export const F1_AGING_IMPAIRMENT_LABEL = '减：减值准备'
export const F1_AGING_NET_LABEL = '合计'

// ─── 上市 ─────────────────────────────────────────────────────────────────────

export interface F1ListedSyncSnapshot {
  agingRows: Array<{
    label: string
    endAmount: number
    endPct: number
    priorAmount: number
    priorPct: number
  }>
  /** 各账龄段合计 → 附注「小计」行 */
  agingTotal: {
    label: string
    endAmount: number
    endPct: number
    priorAmount: number
    priorPct: number
  }
  /** 期末减值准备 */
  impairmentProvision: number
  /** 上年年末减值准备（F7-7 要求期末/期初各独立校验） */
  impairmentPrior: number
  /** 小计 − 减值准备 → 附注「合计」行 */
  agingNet: {
    label: string
    endAmount: number
    priorAmount: number
  }
  over1YearRows: Array<{
    debtorName: string
    endBalance: number
    proportionPct: number
    impairment: number
    reason: string
  }>
  over1YearTotal: {
    endBalance: number
    proportionPct: number
    impairment: number
  }
  top5Rows: Array<{
    entityName: string
    endBalance: number
    proportionPct: number
  }>
  top5Total: {
    endBalance: number
    proportionPct: number
  }
  top5SummaryText: string
  /**
   * 前五名披露格式（源模板 `A23=（…汇总**或**分别披露…）` + `A24=汇总披露格式：`
   * + `A26=分别披露格式：` → **二选一**，不能两者同时进附注）。
   *
   * - `'separate'`（默认，与改造前行为一致）：推③表，不推汇总句；
   * - `'summary'`：推汇总句，③表进 `_removed_table_keys`（否则用户切换后附注永久残留过时明细）。
   */
  top5Mode?: F1Top5Mode
  noteAging: string
  noteOver1Year: string
  noteTop5: string
}

/** 上市③前五名披露格式（源模板「汇总或分别披露」二选一） */
export type F1Top5Mode = 'separate' | 'summary'

export const F1_TOP5_MODE_DEFAULT: F1Top5Mode = 'separate'

/** 前五名披露格式选项（UI 全中文化；label 取源模板 A24 / A26 字面） */
export const F1_TOP5_MODE_OPTIONS: ReadonlyArray<{ value: F1Top5Mode; label: string }> = [
  { value: 'separate', label: '分别披露格式' },
  { value: 'summary', label: '汇总披露格式' },
]

export function normalizeF1Top5Mode(raw: unknown): F1Top5Mode {
  return String(raw ?? '').trim() === 'summary' ? 'summary' : F1_TOP5_MODE_DEFAULT
}

export interface F1NoteTextRow {
  section: string
  title: string
  text: string
}

/**
 * 说明文本 → `_note_texts`（后端 `_format_note_texts` 渲染为 `【title】\n正文`）。
 *
 * 🔴 `title` 必填中文：缺省时后端用 `section` 兜底，附注正文会出现
 * `【listed-note-aging】` 这类英文键（违反 UI 全中文化）。空文本直接丢弃，
 * 避免用空段落覆盖附注既有正文。
 *
 * title 取源 = 源 xlsx 小节标题（上市「（1）预付款项按账龄披露」/
 * 「（2）账龄超过1年的重要预付款项」/「（3）按预付对象归集的预付款项期末余额前五名单位情况」；
 * 国企「（1）预付款项按账龄列示」/「（2）账龄超过1年的大额预付款项」/
 * 「（3）按欠款方归集的期末余额前五名的预付款项情况」）。
 */
export function buildF1NoteTexts(
  entries: ReadonlyArray<readonly [section: string, title: string, text: string]>,
): F1NoteTextRow[] {
  const out: F1NoteTextRow[] = []
  for (const [section, title, text] of entries) {
    const body = String(text ?? '').trim()
    if (!body) continue
    out.push({ section, title, text: body })
  }
  return out
}

export function buildF1ListedSubTableData(
  snap: F1ListedSyncSnapshot,
): Record<string, unknown> {
  const top5Mode = normalizeF1Top5Mode(snap.top5Mode)
  const sub: Record<string, unknown> = {
    [F1_LISTED_SUBTABLE.AGING]: [
      ...snap.agingRows.map((r) => ({
        label: r.label,
        end_amount: r.endAmount,
        end_pct: r.endPct,
        prior_amount: r.priorAmount,
        prior_pct: r.priorPct,
      })),
      {
        label: F1_AGING_SUBTOTAL_LABEL,
        end_amount: snap.agingTotal.endAmount,
        end_pct: snap.agingTotal.endPct,
        prior_amount: snap.agingTotal.priorAmount,
        prior_pct: snap.agingTotal.priorPct,
        is_total: true,
      },
      {
        label: F1_AGING_IMPAIRMENT_LABEL,
        end_amount: snap.impairmentProvision,
        end_pct: null,
        prior_amount: snap.impairmentPrior,
        prior_pct: null,
      },
      {
        label: snap.agingNet.label || F1_AGING_NET_LABEL,
        end_amount: snap.agingNet.endAmount,
        end_pct: null,
        prior_amount: snap.agingNet.priorAmount,
        prior_pct: null,
        is_total: true,
      },
    ],
    [F1_LISTED_SUBTABLE.OVER1]: [
      ...snap.over1YearRows.map((r) => ({
        label: r.debtorName,
        balance: r.endBalance,
        proportion_pct: r.proportionPct,
        impairment: r.impairment,
      })),
      {
        label: '合计',
        balance: snap.over1YearTotal.endBalance,
        proportion_pct: snap.over1YearTotal.proportionPct,
        impairment: snap.over1YearTotal.impairment,
        is_total: true,
      },
    ],
    _note_texts: buildF1NoteTexts([
      ['listed-note-aging', '预付款项按账龄披露说明', snap.noteAging],
      ['listed-note-over1', '账龄超过1年的重要预付款项说明', snap.noteOver1Year],
      ['listed-note-top5', '按预付对象归集的前五名预付款项说明', snap.noteTop5],
      // 汇总披露格式的正文句只在该模式下进附注（与③表互斥）
      ...(top5Mode === 'summary'
        ? ([['listed-top5-summary', '前五名预付款项汇总披露', snap.top5SummaryText]] as const)
        : []),
    ]),
  }

  // ③前五名：源模板「汇总或分别披露」二选一
  if (top5Mode === 'separate') {
    sub[F1_LISTED_SUBTABLE.TOP5] = [
      ...snap.top5Rows.map((r) => ({
        label: r.entityName,
        end_amount: r.endBalance,
        proportion_pct: r.proportionPct,
      })),
      {
        label: '合计',
        end_amount: snap.top5Total.endBalance,
        proportion_pct: snap.top5Total.proportionPct,
        is_total: true,
      },
    ]
  }

  // 孤儿子表清理：旧表名 + 汇总模式下的③表（不含本次推送的键）
  const removedCandidates: string[] = [...F1_LISTED_OBSOLETE_TABLE_KEYS]
  if (top5Mode === 'summary') removedCandidates.push(F1_LISTED_SUBTABLE.TOP5)
  const removed = removedCandidates.filter((k) => !(k in sub))
  if (removed.length) sub._removed_table_keys = removed
  return sub
}

// ─── 国企 ─────────────────────────────────────────────────────────────────────

export interface F1SoeSyncSnapshot {
  agingRows: Array<{
    label: string
    endAmount: number
    endPct: number
    endBadDebt: number
    priorAmount: number
    priorPct: number
    priorBadDebt: number
  }>
  /** 各账龄段合计 → 附注「小计」行 */
  agingTotal: {
    label: string
    endAmount: number
    endPct: number
    endBadDebt: number
    priorAmount: number
    priorPct: number
    priorBadDebt: number
  }
  /** 小计 − 逐段减值准备合计 → 附注「合计」行 */
  agingNet: {
    label: string
    endAmount: number
    priorAmount: number
  }
  over1YearRows: Array<{
    creditorUnit: string
    debtorUnit: string
    endBalance: number
    agingLabel: string
    reason: string
  }>
  over1YearTotal: { endBalance: number }
  top5Rows: Array<{
    debtorName: string
    endBalance: number
    proportionPct: number
    badDebt: number
  }>
  top5Total: {
    endBalance: number
    proportionPct: number
    badDebt: number
  }
  noteAging: string
  noteOver1Year: string
  noteTop5: string
}

export function buildF1SoeSubTableData(
  snap: F1SoeSyncSnapshot,
): Record<string, unknown> {
  return {
    // 底稿侧逐账龄段「减值准备」列 → 附注侧聚合为「减：减值准备」行（5 列 7 行）
    [F1_SOE_SUBTABLE.AGING]: [
      ...snap.agingRows.map((r) => ({
        label: r.label,
        end_amount: r.endAmount,
        end_pct: r.endPct,
        prior_amount: r.priorAmount,
        prior_pct: r.priorPct,
      })),
      {
        label: F1_AGING_SUBTOTAL_LABEL,
        end_amount: snap.agingTotal.endAmount,
        end_pct: snap.agingTotal.endPct,
        prior_amount: snap.agingTotal.priorAmount,
        prior_pct: snap.agingTotal.priorPct,
        is_total: true,
      },
      {
        label: F1_AGING_IMPAIRMENT_LABEL,
        end_amount: snap.agingTotal.endBadDebt,
        end_pct: null,
        prior_amount: snap.agingTotal.priorBadDebt,
        prior_pct: null,
      },
      {
        label: snap.agingNet.label || F1_AGING_NET_LABEL,
        end_amount: snap.agingNet.endAmount,
        end_pct: null,
        prior_amount: snap.agingNet.priorAmount,
        prior_pct: null,
        is_total: true,
      },
    ],
    [F1_SOE_SUBTABLE.OVER1]: [
      ...snap.over1YearRows.map((r) => ({
        creditor_unit: r.creditorUnit,
        debtor_unit: r.debtorUnit,
        end_balance: r.endBalance,
        aging: r.agingLabel,
        reason: r.reason,
      })),
      {
        creditor_unit: '合计',
        label: '合计',
        end_balance: snap.over1YearTotal.endBalance,
        aging: '——',
        reason: '——',
        is_total: true,
      },
    ],
    [F1_SOE_SUBTABLE.TOP5]: [
      ...snap.top5Rows.map((r) => ({
        label: r.debtorName,
        end_amount: r.endBalance,
        proportion_pct: r.proportionPct,
        impairment: r.badDebt,
      })),
      {
        label: '合计',
        end_amount: snap.top5Total.endBalance,
        proportion_pct: snap.top5Total.proportionPct,
        impairment: snap.top5Total.badDebt,
        is_total: true,
      },
    ],
    _note_texts: buildF1NoteTexts([
      ['soe-note-aging', '预付款项按账龄列示说明', snap.noteAging],
      ['soe-note-over1', '账龄超过1年的大额预付款项说明', snap.noteOver1Year],
      ['soe-note-top5', '按欠款方归集的前五名预付款项说明', snap.noteTop5],
    ]),
  }
}

export function buildF1SyncPayload(
  variant: F1DisclosureVariant,
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  subTableData: Record<string, unknown>,
  year?: number | null,
): F1SyncFromWorkpaperPayload | null {
  if (!isF1DisclosureApplicable(variant, applicableStandards)) return null
  // 🔴 列元数据只发**本次实际推送**的表：上市③在「汇总披露格式」下不推表且进
  //   `_removed_table_keys`，若仍发它的 columns 会在附注留一条无数据的列元数据残片。
  const allColumns = variant === 'listed' ? F1_LISTED_COLUMNS : F1_SOE_COLUMNS
  const columns: Record<string, ColumnDef[]> = {}
  for (const [name, cols] of Object.entries(allColumns)) {
    if (name in subTableData) columns[name] = cols
  }

  const payload: F1SyncFromWorkpaperPayload = {
    wp_id: wpId,
    sheet_name: F1_DISCLOSURE_SHEET_NAME[variant],
    section_id: F1_NOTE_SECTION[variant],
    current_standard: resolveF1CurrentStandard(variant, applicableStandards),
    sub_table_data: subTableData,
    columns,
  }
  const y = Number(year ?? 0)
  if (y > 0) payload.year = y
  return payload
}
