/**
 * F4 应付账款披露表 ↔ 附注章节映射与 sync payload 构建
 *
 * 权威来源（两段口径不同，不得混用）：
 * - 章节号 → `backend/data/note_template_variant_matrix.json`：上市 五、37 / 国企 八、37
 * - 表名 / 表头 / 行集合 → `backend/data/note_template_{listed,soe}.json` §应付账款
 *   （由 `backend/scripts/fix/fix_note_accounts_payable_structure.py` 对齐附注模版 md）
 * - 底稿列头文案 → `F4 应付账款.xlsx` 的 `附注披露信息(上市公司)` / `附注披露信息(国企)`
 *
 * 披露逻辑（源模板两种口径互为交叉核对）：
 * - 上市按**款项性质**（货款/工程款/设备款/服务费/其他）列示期末余额 + 上年年末余额；
 * - 国企按**账龄**列示期末余额 + 期初余额；
 * - 两者都附「账龄超过 1 年的重要应付账款」逐项披露（金额 + 未偿还/未结转原因），
 *   取自 F4-5 账龄1年以上的应付账款检查表。
 *
 * 🔴 子表名契约：`F4_LISTED_SUBTABLE` / `F4_SOE_SUBTABLE` 每个值必须与附注模板
 *   `tables[].name` **逐字一致**（含国企「账龄超过1 年」中「1」后的空格——附注模版 md
 *   原文如此）。不一致会同步出孤儿子表：附注 TAB 永空 + 底稿数据丢失。
 *   契约测试见 `__tests__/f4NoteSubtableContract.spec.ts`。
 */
import type { AgingSegment } from '@/composables/useAgingConfig'
import { defineColumns, type ColumnDef } from './disclosureColumnDefs'
import { buildDisclosureAgingLabelMap, SOE_AGING_OVERRIDES } from './disclosureAgingLabels'

export type F4DisclosureVariant = 'listed' | 'soe'

export const F4_ACCOUNT_CODE = '2202'
export const F4_WP_CODE = 'F4'

export const F4_NOTE_SECTION = {
  listed: '五、37',
  soe: '八、37',
} as const satisfies Record<F4DisclosureVariant, string>

/** 🔴 sheet_name = 源 xlsx 中文 tab 名（非 `F4-note-listed` 式 wp_code），全平台统一 */
export const F4_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息(上市公司)',
  soe: '附注披露信息(国企)',
} as const satisfies Record<F4DisclosureVariant, string>

/** 与 note_template_listed §五、37 tables[].name 逐字一致 */
export const F4_LISTED_SUBTABLE = {
  nature: '应付账款',
  over1y: '其中，账龄超过1年的重要应付账款',
} as const

/** 与 note_template_soe §八、37 tables[].name 逐字一致（「1 年」中的空格来自附注模版 md） */
export const F4_SOE_SUBTABLE = {
  aging: '应付账款',
  over1y: '账龄超过1 年的重要应付账款',
} as const

/**
 * 历史 seed 表名（md 重建误把首个表头单元格当表名）。
 * 已生成附注的项目里仍残留该空表 → 同步时上报删除（Requirement 8 / `_removed_table_keys`）。
 */
export const F4_LISTED_REMOVED_TABLE_KEYS = ['项  目'] as const

// ─── 列头（label 逐字对齐附注模板 headers 与底稿 el-table-column） ─────────────

export const F4_LISTED_NATURE_COLUMNS: ColumnDef[] = defineColumns([
  { key: 'label', label: '项目', is_label: true, flat: true },
  { key: 'end_amount', label: '期末余额', format: 'amount' },
  { key: 'prior_amount', label: '上年年末余额', format: 'amount' },
])

export const F4_LISTED_OVER1Y_COLUMNS: ColumnDef[] = defineColumns([
  { key: 'label', label: '项目', is_label: true, flat: true },
  { key: 'end_amount', label: '期末余额', format: 'amount' },
  { key: 'unsettled_reason', label: '未偿还或未结转的原因' },
])

export const F4_SOE_AGING_COLUMNS: ColumnDef[] = defineColumns([
  { key: 'label', label: '账龄', is_label: true, flat: true },
  { key: 'end_amount', label: '期末余额', format: 'amount' },
  { key: 'opening_amount', label: '期初余额', format: 'amount' },
])

export const F4_SOE_OVER1Y_COLUMNS: ColumnDef[] = defineColumns([
  { key: 'label', label: '债权单位名称', is_label: true, flat: true },
  { key: 'end_amount', label: '期末余额', format: 'amount' },
  { key: 'unsettled_reason', label: '未偿还原因' },
])

// ─── 账龄文案：底稿用词 → 附注模版用词 ────────────────────────────────────────

/**
 * 段 key → 附注披露账龄文案。
 *
 * 底稿（F4-1/F4-2/F4-5）沿用源 xlsx 用词「1至2年（含2年）」「2至3年（含3年）」；
 * **附注模版 md 不带括注**（`国企报表附注.md` §应付账款 原文为 1年以内（含1年）/
 * 1至2年 / 2至3年 / 3年以上）。同步进附注时按附注模版投影，避免附注行名漂移。
 *
 * 5 年段沿用同一「X至Y年」构词（附注模版仅给出 3 年段行名，此处为构词延伸，非自造披露内容）；
 * 自定义段无对应约定 → 直接用配置段 label。
 */
// F4 的按账龄表只在国企（八、37）出现 → 首档取国企口径
export const F4_NOTE_AGING_LABEL: Record<string, string> =
  buildDisclosureAgingLabelMap(SOE_AGING_OVERRIDES)

/** F4-1 既有 rowKey（3 年段沿用迁移前存储键）→ 附注披露账龄文案 */
const F4_NOTE_AGING_LABEL_BY_ROWKEY: Record<string, string> = {
  within1year: F4_NOTE_AGING_LABEL.within1,
  '1to2year': F4_NOTE_AGING_LABEL.y1to2,
  '2to3year': F4_NOTE_AGING_LABEL.y2to3,
  '3yearplus': F4_NOTE_AGING_LABEL.over3,
}

/** 段 → 附注披露账龄文案（未覆盖段回落配置 label） */
export function f4NoteAgingLabel(seg: AgingSegment): string {
  return F4_NOTE_AGING_LABEL[String(seg?.key)] ?? String(seg?.label ?? '')
}

/**
 * F4-1 按账龄行（rowKey + 底稿 label）→ 附注披露账龄文案。
 * 3 年段命中 rowKey 映射；其它段 rowKey 即段 key，命中段映射；均未命中用底稿 label。
 */
export function f4NoteAgingLabelByRowKey(rowKey: string, fallbackLabel: string): string {
  return (
    F4_NOTE_AGING_LABEL_BY_ROWKEY[rowKey]
    ?? F4_NOTE_AGING_LABEL[rowKey]
    ?? fallbackLabel
  )
}

// ─── current_standard ────────────────────────────────────────────────────────

export function resolveF4CurrentStandard(
  variant: F4DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
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

// ─── payload ─────────────────────────────────────────────────────────────────

export interface F4SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, unknown>
  columns?: Record<string, ColumnDef[]>
}

/** 上市按性质行（来自披露表，期末=F4-1 期末审定、上年年末=F4-1 期初审定） */
export interface F4NoteNatureRow {
  label: string
  endAmount: number
  priorAmount: number
}

/** 国企按账龄行（来自 F4-1 按账龄审定数） */
export interface F4NoteAgingRow {
  rowKey: string
  label: string
  endAmount: number
  openingAmount: number
}

/** 账龄超过 1 年的重要应付账款逐项行（来自 F4-5） */
export interface F4NoteOver1YRow {
  creditor: string
  amount: number
  reason: string
}

const TOLERANCE = 0.005

function isBlank(row: F4NoteOver1YRow): boolean {
  return !String(row.creditor || '').trim()
    && Math.abs(Number(row.amount) || 0) < TOLERANCE
    && !String(row.reason || '').trim()
}

function sum(values: readonly number[]): number {
  return values.reduce((acc, v) => acc + (Number(v) || 0), 0)
}

function over1yRows(
  rows: readonly F4NoteOver1YRow[],
  reasonKey: 'unsettled_reason',
): Record<string, unknown>[] {
  // 空白骨架行不推送（避免附注出现无内容的占位行）
  const kept = rows.filter((row) => !isBlank(row))
  return [
    ...kept.map((row) => ({
      label: row.creditor,
      end_amount: row.amount,
      [reasonKey]: row.reason,
    })),
    {
      label: '合计',
      end_amount: sum(kept.map((row) => row.amount)),
      [reasonKey]: '',
      is_total: true,
    },
  ]
}

export interface F4NoteTextRow {
  section: string
  title: string
  text: string
}

/** 披露正文标题（源 xlsx 小节名：上市「应付账款附注披露信息」/ 国企同名） */
const F4_NOTE_TITLE = '应付账款披露说明'

/**
 * 说明文本 → `_note_texts`（后端 `_format_note_texts` 渲染为 `【title】\n正文`）。
 *
 * 🔴 原实现是 `[{ text }]` —— 既无 `section` 也无 `title`：正文虽不会渲染出英文键，
 * 但附注侧无从判断这段正文来自哪个披露 Tab，与平台其它循环（D1/D2/F1/F2/F3）不一致。
 * 现补齐中文 `title` + 变体 `section`，空文本仍然过滤（不用空段落覆盖附注既有正文）。
 */
export function buildF4NoteTexts(
  variant: 'listed' | 'soe',
  noteText: string,
): F4NoteTextRow[] {
  const body = String(noteText ?? '').trim()
  if (!body) return []
  return [{ section: `${variant}-disclosure-note`, title: F4_NOTE_TITLE, text: body }]
}

/**
 * 上市（五、37）同步载荷：按性质表 + 账龄超 1 年重要应付账款表 + 披露正文。
 *
 * 行集合按底稿披露表整表覆盖（含手工添加行）；合计行由此处计算，
 * 不依赖附注 seed 的固定行数。
 */
export function buildF4ListedSyncPayload(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  natureRows: readonly F4NoteNatureRow[],
  over1y: readonly F4NoteOver1YRow[],
  noteText: string,
): F4SyncPayload {
  const kept = natureRows.filter(
    (row) =>
      String(row.label || '').trim()
      || Math.abs(Number(row.endAmount) || 0) >= TOLERANCE
      || Math.abs(Number(row.priorAmount) || 0) >= TOLERANCE,
  )
  return {
    wp_id: wpId,
    sheet_name: F4_DISCLOSURE_SHEET_NAME.listed,
    section_id: F4_NOTE_SECTION.listed,
    current_standard: resolveF4CurrentStandard('listed', applicableStandards),
    sub_table_data: {
      [F4_LISTED_SUBTABLE.nature]: [
        ...kept.map((row) => ({
          label: row.label,
          end_amount: row.endAmount,
          prior_amount: row.priorAmount,
        })),
        {
          label: '合计',
          end_amount: sum(kept.map((row) => row.endAmount)),
          prior_amount: sum(kept.map((row) => row.priorAmount)),
          is_total: true,
        },
      ],
      [F4_LISTED_SUBTABLE.over1y]: over1yRows(over1y, 'unsettled_reason'),
      _note_texts: buildF4NoteTexts('listed', noteText),
      _removed_table_keys: [...F4_LISTED_REMOVED_TABLE_KEYS],
    },
    columns: {
      [F4_LISTED_SUBTABLE.nature]: F4_LISTED_NATURE_COLUMNS,
      [F4_LISTED_SUBTABLE.over1y]: F4_LISTED_OVER1Y_COLUMNS,
    },
  }
}

/**
 * 国企（八、37）同步载荷：按账龄表 + 账龄超 1 年重要应付账款表 + 披露正文。
 *
 * 账龄行数跟随项目账龄配置（3 年段 4 档 / 5 年段 6 档 / 自定义）；
 * F4 特有的「其他/未分类」残差行**不进附注**（不是账龄段），但其金额已含在合计中，
 * 故合计取按账龄区全部行之和（含残差），与 F4-1 按性质合计保持勾稽。
 */
export function buildF4SoeSyncPayload(
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  agingRows: readonly F4NoteAgingRow[],
  over1y: readonly F4NoteOver1YRow[],
  noteText: string,
  residualRowKey = 'aging-other',
): F4SyncPayload {
  const segmentRows = agingRows.filter((row) => row.rowKey !== residualRowKey)
  return {
    wp_id: wpId,
    sheet_name: F4_DISCLOSURE_SHEET_NAME.soe,
    section_id: F4_NOTE_SECTION.soe,
    current_standard: resolveF4CurrentStandard('soe', applicableStandards),
    sub_table_data: {
      [F4_SOE_SUBTABLE.aging]: [
        ...segmentRows.map((row) => ({
          label: f4NoteAgingLabelByRowKey(row.rowKey, row.label),
          end_amount: row.endAmount,
          opening_amount: row.openingAmount,
        })),
        {
          label: '合计',
          // 含残差行：合计口径须与 F4-1 按性质合计一致
          end_amount: sum(agingRows.map((row) => row.endAmount)),
          opening_amount: sum(agingRows.map((row) => row.openingAmount)),
          is_total: true,
        },
      ],
      [F4_SOE_SUBTABLE.over1y]: over1yRows(over1y, 'unsettled_reason'),
      _note_texts: buildF4NoteTexts('soe', noteText),
    },
    columns: {
      [F4_SOE_SUBTABLE.aging]: F4_SOE_AGING_COLUMNS,
      [F4_SOE_SUBTABLE.over1y]: F4_SOE_OVER1Y_COLUMNS,
    },
  }
}
