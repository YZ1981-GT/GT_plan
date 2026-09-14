/**
 * K13 营业外支出 披露 ↔ 附注章节映射与 sync payload 构建
 *
 * 权威来源（实证 2026-07-30）：
 * - 源 xlsx `backend/wp_templates/K/K13 营业外支出.xlsx` 的 `附注披露信息（上市公司）` /
 *   `附注披露信息（国企）`（**全角括号**）：两版都是**四列** ——
 *   「项 目 / 本期发生额 / 上期发生额 / 计入当期非经常性损益的金额」，
 *   数据引 `'审定表K13-1'` 与 `'明细表K13-2'!R*`。
 * - `note_template_soe.json` §八、77 表名「营业外支出」，同为 4 列。
 *
 * 🔴 **上市侧章节号是 `三、营业外支出（注：`** —— listed 模板 `三、` 整章
 * `section_number` 被 md 重建截断为 10 字符，是既有真源形态，**不要"修正"**。
 * 旧常量写 `营业外支出` → 上市侧同步落不到章节。
 *
 * 🔴 旧常量只声明 3 列 → 第 4 列「计入当期非经常性损益的金额」组件已录入却从未推送。
 *
 * account_code: 6711
 *
 * spec: .kiro/specs/k-cycle-disclosure-alignment/ Task 2
 */
import type { ColumnDef } from './disclosureColumnDefs'
import {
  plColumnsFor,
  buildPlPayload,
  type KPlColumnSpec,
  type KPlNoteText,
  type KPlRow,
  type KPlSyncPayload,
  type KPlVariant,
} from './kPlDisclosureShared'

export type K13DisclosureVariant = KPlVariant

export const K13_NOTE_SECTION = {
  listed: '三、营业外支出（注：',
  soe: '八、77',
} as const satisfies Record<K13DisclosureVariant, string>

/** 源 xlsx 真实 tab 名 —— 全角括号（旧值为半角，属漂移） */
export const K13_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<K13DisclosureVariant, string>

export const K13_LISTED_SUBTABLE = { main: '营业外支出' } as const
export const K13_SOE_SUBTABLE = { main: '营业外支出' } as const

/** 上市侧模板旧表名是表头首格泄漏值，已由幂等脚本改名，须清理残留 */
export const K13_LEGACY_OBSOLETE_TABLES: readonly string[] = ['项  目']

export const K13_LISTED_ROWS: readonly string[] = [
  '公益性捐赠支出',
  '非常损失',
  '盘亏损失',
  '非流动资产毁损报废损失',
  '碳排放配额使用、注销或交易',
]

export const K13_SOE_ROWS: readonly string[] = [
  '非流动资产毁损报废损失',
  '公益性捐赠支出',
  '行政性罚款、滞纳金',
  '非常损失',
  '盘亏损失',
  '碳排放配额交易',
]

const SPEC: KPlColumnSpec = {
  labelHeader: '项目',
  currentLabel: '本期发生额',
  priorLabel: '上期发生额',
  extra: { key: 'non_recurring_amount', label: '计入当期非经常性损益的金额', format: 'amount' },
}

export function buildK13ListedColumns(): Record<string, ColumnDef[]> {
  return { [K13_LISTED_SUBTABLE.main]: plColumnsFor(SPEC) }
}

export function buildK13SoeColumns(): Record<string, ColumnDef[]> {
  return { [K13_SOE_SUBTABLE.main]: plColumnsFor(SPEC) }
}

export interface K13DisclosureRow {
  project: string
  currentAmount: number
  priorAmount: number
  /** 计入当期非经常性损益的金额（源模板必填列） */
  nonRecurringAmount?: number
}

export type K13SyncPayload = KPlSyncPayload

export function buildK13SyncPayload(
  variant: K13DisclosureVariant,
  wpId: string,
  rows: readonly K13DisclosureRow[],
  narrativeText: string,
): K13SyncPayload {
  const mapped: KPlRow[] = rows.map(r => ({
    project: r.project,
    currentAmount: r.currentAmount,
    priorAmount: r.priorAmount,
    extraValue: r.nonRecurringAmount ?? 0,
  }))
  const texts: KPlNoteText[] = [
    { section: 'k13-note', title: '营业外支出说明', text: narrativeText },
  ]
  return buildPlPayload({
    wpId,
    sheetName: K13_DISCLOSURE_SHEET_NAME[variant],
    sectionId: K13_NOTE_SECTION[variant],
    variant,
    tableName: variant === 'listed' ? K13_LISTED_SUBTABLE.main : K13_SOE_SUBTABLE.main,
    spec: SPEC,
    rows: mapped,
    texts,
    removedTableKeys: variant === 'listed' ? K13_LEGACY_OBSOLETE_TABLES : [],
  })
}
