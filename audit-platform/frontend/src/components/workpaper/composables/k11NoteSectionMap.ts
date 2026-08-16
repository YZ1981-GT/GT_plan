/**
 * K11 资产减值损失 披露 ↔ 附注章节映射与 sync payload 构建
 *
 * 权威来源（实证 2026-07-30）：
 * - 源 xlsx `backend/wp_templates/K/K11 资产减值损失.xlsx` 的 `附注披露信息（上市公司）` /
 *   `附注披露信息（国企）`（**全角括号**）：两版都是「项目 / 本期发生额 / 上期发生额」，
 *   数据引 `'审定表K11-1'`；标题注「损失以“—”号填列，以下不存在的项目可以删除」，
 *   末行注「本科目明细表按照正数填列、披露表按照负数填列」。
 * - `note_template_soe.json` §八、74 表名「资产减值损失」。
 *
 * 🔴 **上市侧章节号是 `三、资产减值损失（损`** —— listed 模板 `三、` 整章的
 * `section_number` 都被 `rebuild_note_from_md.py` 截断为 10 字符（`三、重要性标准确定方` /
 * `三、投资性房地产【不` …），这是该章既有真源形态，**不是笔误、不要"修正"**。
 * 旧常量写 `资产减值损失`（连 `三、` 都没有）→ `sync_from_workpaper` 按
 * `(project_id, year, note_section)` 定位时落空，上市侧同步会新建垃圾章节。
 *
 * account_code: 6701
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

export type K11DisclosureVariant = KPlVariant

export const K11_NOTE_SECTION = {
  listed: '三、资产减值损失（损',
  soe: '八、74',
} as const satisfies Record<K11DisclosureVariant, string>

/** 源 xlsx 真实 tab 名 —— 全角括号（旧值为半角，属漂移） */
export const K11_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<K11DisclosureVariant, string>

export const K11_LISTED_SUBTABLE = { main: '资产减值损失' } as const
export const K11_SOE_SUBTABLE = { main: '资产减值损失' } as const

/** 上市侧模板旧表名是表头首格泄漏值，已由幂等脚本改名，须清理残留 */
export const K11_LEGACY_OBSOLETE_TABLES: readonly string[] = ['项  目']

export const K11_LISTED_ROWS: readonly string[] = [
  '合同资产减值损失',
  '存货跌价损失',
  '合同履约成本减值损失',
  '合同取得成本减值损失',
  '持有待售资产减值损失',
  '长期股权投资减值损失',
  '投资性房地产减值损失',
  '使用权资产减值损失',
  '固定资产减值损失',
  '工程物资减值损失',
  '在建工程减值损失',
  '生产性生物资产减值损失',
  '油气资产减值损失',
  '开发支出减值损失',
  '无形资产减值损失',
  '商誉减值损失',
  '其他',
]

export const K11_SOE_ROWS: readonly string[] = [
  '存货跌价损失',
  '合同资产减值损失',
  '持有待售资产减值损失',
  '合同取得成本相关资产减值损失',
  '合同履约成本相关资产减值损失',
  '长期股权投资减值损失',
  '投资性房地产减值损失',
  '固定资产减值损失',
  '在建工程减值损失',
  '生产性生物资产减值损失',
  '油气资产减值损失',
  '使用权资产减值损失',
  '无形资产减值损失',
  '商誉减值损失',
  '其他',
]

const SPEC: KPlColumnSpec = {
  labelHeader: '项目',
  currentLabel: '本期发生额',
  priorLabel: '上期发生额',
}

export function buildK11ListedColumns(): Record<string, ColumnDef[]> {
  return { [K11_LISTED_SUBTABLE.main]: plColumnsFor(SPEC) }
}

export function buildK11SoeColumns(): Record<string, ColumnDef[]> {
  return { [K11_SOE_SUBTABLE.main]: plColumnsFor(SPEC) }
}

export interface K11DisclosureRow {
  project: string
  currentAmount: number
  priorAmount: number
}

export type K11SyncPayload = KPlSyncPayload

/**
 * K11 披露表金额的符号口径：**明细表正数填列、披露表按负数填列**。
 *
 * 源 xlsx 两版末行注「本科目明细表按照正数填列、披露表按照负数填列」，标题注
 * 「损失以"—"号填列」。底稿（明细表 / 审定表 K11-1）里录的是**正数**，
 * 推附注时必须翻符号，否则附注里的资产减值损失会以正数出现 —— 与利润表口径相反。
 *
 * 🔴 单点翻转：只在本函数（唯一载荷构造口）做，绝不在组件里各翻一次
 * （两处都翻 = 翻回正数，且没有任何报错）。
 *
 * 三条边界：
 * - `0` 翻转后仍是 `0`（不得出现 `-0`：它会被 `JSON.stringify` 写成 `0` 但在
 *   `Object.is` 比较与 `Math.sign` 上行为不同，且界面可能显示「-0.00」）
 * - 非有限值（`NaN` / `Infinity`）原样返回，不伪造成 0（那是造数据）
 * - 已经是负数的输入照常翻成正数 —— 本函数是**口径转换**而不是「取负绝对值」，
 *   若底稿里录了负数，说明录入口径错了，应该在录入侧修，而不是这里悄悄吸收
 *
 * spec: Requirement 8.7
 */
export function k11DisclosureAmount(value: number): number {
  if (!Number.isFinite(value)) return value
  if (value === 0) return 0
  return -value
}

export function buildK11SyncPayload(
  variant: K11DisclosureVariant,
  wpId: string,
  rows: readonly K11DisclosureRow[],
  narrativeText: string,
): K11SyncPayload {
  const texts: KPlNoteText[] = [
    { section: 'k11-note', title: '资产减值损失说明', text: narrativeText },
  ]
  // Requirement 8.7：披露表按负数填列（底稿侧是正数）
  const disclosureRows: K11DisclosureRow[] = rows.map((r) => ({
    ...r,
    currentAmount: k11DisclosureAmount(r.currentAmount),
    priorAmount: k11DisclosureAmount(r.priorAmount),
  }))
  return buildPlPayload({
    wpId,
    sheetName: K11_DISCLOSURE_SHEET_NAME[variant],
    sectionId: K11_NOTE_SECTION[variant],
    variant,
    tableName: variant === 'listed' ? K11_LISTED_SUBTABLE.main : K11_SOE_SUBTABLE.main,
    spec: SPEC,
    rows: disclosureRows as readonly KPlRow[],
    texts,
    removedTableKeys: variant === 'listed' ? K11_LEGACY_OBSOLETE_TABLES : [],
  })
}
