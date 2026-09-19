/**
 * D5 应收款项融资披露 ↔ 附注章节冻结映射与 sync payload 构建
 *
 * 权威来源：note_template_listed.json 五、6 / note_template_soe.json 八、6「应收款项融资」
 * （表名/列头逐字对照模板；行数据来自 D5 底稿披露表）。
 *
 * 底稿 → 附注单向推送（sync_from_workpaper）：sub_table_data 各子表 + _note_texts → 附注。
 * 🔴 覆盖必须完整：note_sub_table_projector 只渲染推送过的子表，故逐张覆盖。
 *
 * 覆盖完整性（对照模板）：上市 五、6 共 4 张（分类 / 减值变动 / 已质押 / 已背书贴现）；
 * 国企 八、6 共 1 张（分类）。本文件全覆盖。
 *
 * 与模板字面值的偏差（渲染必需）：
 *  - 减值变动表模板为「单列纵向」（期初/计提/转回/核销/期末各一行），
 *    D5 披露表为横向多行明细，故按变动阶段汇总为纵向单列（与模板结构一致）。
 */
import type { ColumnDef } from './disclosureColumnDefs'

export type D5DisclosureVariant = 'listed' | 'soe'

export const D5_NOTE_SECTION = {
  listed: '五、6',
  soe: '八、6',
} as const satisfies Record<D5DisclosureVariant, string>

// 底稿披露 sheet 真实 tab 名（全角括号，见 workpaper_sheet_classification wp_code=D5）。
export const D5_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<D5DisclosureVariant, string>

export function resolveD5CurrentStandard(
  variant: D5DisclosureVariant,
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

// ─── 表名（逐字取自附注模板 五、6 / 八、6）─────────────────────────────────
const T = {
  listed: {
    main: '应收款项融资',
    impairment: '本期计提、收回或转回的减值准备情况',
    pledged: '期末本公司已质押的应收票据',
    endorsed: '期末本公司已背书或贴现但尚未到期的应收票据',
  },
  soe: {
    main: '应收款项融资',
  },
} as const

const AMT = 'amount' as const

// ─── 列头元数据（逐字取自附注模板 headers = 源模板字面）──────────────────────
// 🔴 四张表都是源模板单行表头 → 首列必须标 `flat` 抑制前缀推断。
// 最典型的是 `ENDORSED_COLUMNS`：两个数据列共前缀「期末」，未表态时
// `_infer_groups_from_headers` 会凭空造出「期末」父表头（seed 路径实证）。
const MAIN_COLUMNS_LISTED: ColumnDef[] = [
  { key: 'label', label: '项  目', is_label: true, flat: true },
  { key: 'end_amount', label: '期末余额', format: AMT },
  { key: 'prior_amount', label: '上年年末余额', format: AMT },
]
const MAIN_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '项  目', is_label: true, flat: true },
  { key: 'end_amount', label: '期末余额', format: AMT },
  { key: 'prior_amount', label: '期初余额', format: AMT },
]
// 减值变动：源模板 B20 单列（减值准备金额），行 = 变动阶段（A21-A27）
const IMPAIRMENT_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true, flat: true },
  { key: 'amount', label: '减值准备金额', format: AMT },
]
const PLEDGED_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '种  类', is_label: true, flat: true },
  { key: 'pledged_amount', label: '期末已质押金额', format: AMT },
]
const ENDORSED_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '种  类', is_label: true, flat: true },
  { key: 'derecognized', label: '期末终止确认金额', format: AMT },
  { key: 'not_derecognized', label: '期末未终止确认金额', format: AMT },
]

// ─── 快照行类型（组件层传入）─────────────────────────────────────────────────
export interface D5RowLike { label: string; endAmount: number; priorAmount: number }
export interface D5ImpairmentLike { priorBalance: number; provision: number; reversal: number; writeOff: number; endBalance: number }
export interface D5PledgedRowLike { label: string; pledgedAmount: number }
export interface D5EndorsedRowLike { label: string; derecognizedAmount: number; notDerecognizedAmount: number }

export interface D5DisclosureSnapshot {
  /** 分类表行（上市 5 行含小计/OCI/公允价值合计；国企 2 行） */
  mainRows: D5RowLike[]
  /** 国企版分类合计（上市版最后一行即公允价值合计，无需单独合计行） */
  mainTotal?: D5RowLike
  /** 减值准备变动汇总（上市版） */
  impairment?: D5ImpairmentLike
  /** 已质押应收票据（上市版） */
  pledgedRows?: D5PledgedRowLike[]
  /** 已背书或贴现但尚未到期（上市版） */
  endorsedRows?: D5EndorsedRowLike[]
  /** 各子节说明文本 */
  notes: Record<string, string>
}

export interface D5SyncPayload {
  wp_id: string
  sheet_name: string
  section_id: string
  current_standard: string
  sub_table_data: Record<string, unknown>
  columns: Record<string, ColumnDef[]>
}

const num = (v: unknown): number => (typeof v === 'number' && Number.isFinite(v) ? v : 0)
const str = (v: unknown): string => String(v ?? '')

/**
 * 底稿行名 → 附注行名（源模板字面）。
 *
 * 底稿 UI 用的是自拟短名，源模板 A11/A13 分别是「小  计」（中间两空格）与
 * 「期末公允价值」。附注是交付物 → 行名随源模板；底稿 UI 字面不动。
 * 键按去空白后比对，避免「小计」/「小 计」两种写法漏配。
 */
const NOTE_ROW_LABELS: Record<string, string> = {
  小计: '小  计',
  应收款项融资公允价值合计: '期末公允价值',
  期末公允价值: '期末公允价值',
  合计: '合  计',
}

/** 合计行字面 = 源模板字面（D5 各表统一「合  计」，中间两个空格）。 */
export const D5_NOTE_TOTAL_LABEL = '合  计'

/** 子表名映射（供共享契约 helper 逐字校验）。 */
export const D5_LISTED_SUBTABLE = T.listed
export const D5_SOE_SUBTABLE = T.soe

/** 列定义：`{模板表名: ColumnDef[]}`（零参，供覆盖率 sweep 调用）。 */
export function buildD5ListedColumns(): Record<string, ColumnDef[]> {
  return {
    [T.listed.main]: MAIN_COLUMNS_LISTED,
    [T.listed.impairment]: IMPAIRMENT_COLUMNS,
    [T.listed.pledged]: PLEDGED_COLUMNS,
    [T.listed.endorsed]: ENDORSED_COLUMNS,
  }
}

export function buildD5SoeColumns(): Record<string, ColumnDef[]> {
  return { [T.soe.main]: MAIN_COLUMNS_SOE }
}

const bare = (label: string): string => label.replace(/\s+/g, '')

/** 🔴 行型判定必须先去空白：源模板写的是「小  计」「合  计」。 */
const isTotalLabel = (label: string): boolean => {
  const s = bare(label)
  return s === '合计' || s === '小计' || s === '期末公允价值' || s.includes('公允价值合计')
}

/** 底稿行名归一到附注行名（未登记的原样透传）。 */
export function toD5NoteRowLabel(label: string): string {
  return NOTE_ROW_LABELS[bare(label)] ?? label
}

/**
 * 构建 D5 → 附注 sync-from-workpaper 载荷。
 * 上市：五、6（分类 / 减值变动 / 已质押 / 已背书贴现 4 表）；国企：八、6（分类 1 表）。
 */
export function buildD5SyncPayload(
  variant: D5DisclosureVariant,
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snapshot: D5DisclosureSnapshot,
): D5SyncPayload {
  const isSoe = variant === 'soe'
  const sub: Record<string, unknown> = {}
  const columns: Record<string, ColumnDef[]> = {}
  const put = (name: string, rows: unknown, cols: ColumnDef[]) => {
    sub[name] = rows
    columns[name] = cols
  }

  // ① 分类表
  const mainRow = (r: D5RowLike) => ({
    label: toD5NoteRowLabel(str(r.label)),
    end_amount: num(r.endAmount),
    prior_amount: num(r.priorAmount),
    ...(isTotalLabel(str(r.label)) ? { is_total: true } : {}),
  })
  const mainRows = snapshot.mainRows.map(mainRow)
  if (isSoe && snapshot.mainTotal) {
    mainRows.push({ ...mainRow(snapshot.mainTotal), is_total: true })
  }
  put(isSoe ? T.soe.main : T.listed.main, mainRows, isSoe ? MAIN_COLUMNS_SOE : MAIN_COLUMNS_LISTED)

  if (isSoe) {
    sub._note_texts = buildD5NoteTexts(snapshot.notes)
    return {
      wp_id: wpId,
      sheet_name: D5_DISCLOSURE_SHEET_NAME.soe,
      section_id: D5_NOTE_SECTION.soe,
      current_standard: resolveD5CurrentStandard('soe', applicableStandards),
      sub_table_data: sub,
      columns,
    }
  }

  // ② 减值准备变动（纵向单列）
  const imp = snapshot.impairment ?? { priorBalance: 0, provision: 0, reversal: 0, writeOff: 0, endBalance: 0 }
  put(
    T.listed.impairment,
    [
      // 源模板 A21 字面为「上年年末余额」（非「期初余额」）；A25/A26 的
      // `[本期转销]` `[其他]` 是可选项标记，无发生额时不推送
      { label: '上年年末余额', amount: num(imp.priorBalance) },
      { label: '本期计提', amount: num(imp.provision) },
      { label: '本期收回或转回', amount: num(imp.reversal) },
      { label: '本期核销', amount: num(imp.writeOff) },
      { label: '期末余额', amount: num(imp.endBalance), is_total: true },
    ],
    IMPAIRMENT_COLUMNS,
  )

  // ③ 已质押
  const pledged = snapshot.pledgedRows ?? []
  put(
    T.listed.pledged,
    [
      ...pledged.map((r) => ({ label: str(r.label), pledged_amount: num(r.pledgedAmount) })),
      {
        label: D5_NOTE_TOTAL_LABEL,
        pledged_amount: pledged.reduce((s, r) => s + num(r.pledgedAmount), 0),
        is_total: true,
      },
    ],
    PLEDGED_COLUMNS,
  )

  // ④ 已背书或贴现但尚未到期
  const endorsed = snapshot.endorsedRows ?? []
  put(
    T.listed.endorsed,
    [
      ...endorsed.map((r) => ({
        label: str(r.label),
        derecognized: num(r.derecognizedAmount),
        not_derecognized: num(r.notDerecognizedAmount),
      })),
      {
        label: D5_NOTE_TOTAL_LABEL,
        derecognized: endorsed.reduce((s, r) => s + num(r.derecognizedAmount), 0),
        not_derecognized: endorsed.reduce((s, r) => s + num(r.notDerecognizedAmount), 0),
        is_total: true,
      },
    ],
    ENDORSED_COLUMNS,
  )

  // ⑤ 文本框内容
  sub._note_texts = buildD5NoteTexts(snapshot.notes)

  return {
    wp_id: wpId,
    sheet_name: D5_DISCLOSURE_SHEET_NAME.listed,
    section_id: D5_NOTE_SECTION.listed,
    current_standard: resolveD5CurrentStandard('listed', applicableStandards),
    sub_table_data: sub,
    columns,
  }
}

/** 说明文本子节顺序与标题（与披露表文本框一一对应）。 */
export const D5_NOTE_TEXT_SECTIONS: Array<{ key: string; title: string }> = [
  { key: 'listed-1', title: '应收款项融资分类说明' },
  { key: 'listed-2', title: '减值准备变动说明' },
  { key: 'listed-3', title: '质押/背书贴现说明' },
  { key: 'soe-1', title: '国企版分类说明' },
]

/** 各子节说明 → _note_texts（仅非空）。 */
export function buildD5NoteTexts(notes: Record<string, string>): Array<{ section: string; title: string; text: string }> {
  const out: Array<{ section: string; title: string; text: string }> = []
  for (const { key, title } of D5_NOTE_TEXT_SECTIONS) {
    const text = String(notes?.[key] ?? '').trim()
    if (text) out.push({ section: `note-${key}`, title, text })
  }
  return out
}
