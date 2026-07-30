/**
 * D3 预收账款披露 ↔ 附注章节冻结映射与 sync payload 构建
 *
 * 权威来源：note_template_listed.json 五、38 / note_template_soe.json 八、38「预收款项」
 * （表名/列头逐字对照模板；行数据来自 D3 底稿「附注披露信息(上市公司)/(国企)」披露表）。
 *
 * 底稿 → 附注单向推送（sync_from_workpaper）：
 *  - sub_table_data 各子表 → 附注 table_data.sub_table_data（读时投影为 _tables 渲染）
 *  - sub_table_data._note_texts → 附注 text_content（文本框内容与披露表保持一致）
 *  - columns → _sub_table_columns（投影器据此产出扁平表头，附注模块渲染）
 *
 * 🔴 覆盖必须完整：note_sub_table_projector 对 `_source=workpaper` 的附注
 * **只渲染 sub_table_data 里推送过的子表**（不与模板 _tables 合并），故逐张覆盖。
 *
 * 覆盖完整性（对照模板）：上市 五、38 共 3 张（预收款项 / 账龄超1年 / 重大变动）；
 * 国企 八、38 共 2 张（预收款项按账龄 / 账龄超1年）。本文件全覆盖。
 *
 * 与模板字面值的偏差（渲染必需，不新增/不删减数据列）：
 *  - 上市重大变动表模板列头为「变动金额」，D3 披露表按期末/期初两期录入，
 *    故变动金额 = 期末金额 − 期初金额（保留披露表两期数据的净变动口径）。
 */
import type { ColumnDef } from './disclosureColumnDefs'
import { SOE_AGING_OVERRIDES, toDisclosureAgingLabel } from './disclosureAgingLabels'

export type D3DisclosureVariant = 'listed' | 'soe'

export const D3_NOTE_SECTION = {
  listed: '五、38',
  soe: '八、38',
} as const satisfies Record<D3DisclosureVariant, string>

// 底稿披露 sheet 真实 tab 名（半角括号，见 workpaper_sheet_classification wp_code=D3）。
export const D3_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息(上市公司)',
  soe: '附注披露信息(国企)',
} as const satisfies Record<D3DisclosureVariant, string>

export function resolveD3CurrentStandard(
  variant: D3DisclosureVariant,
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

// ─── 表名（逐字取自附注模板 五、38 / 八、38）────────────────────────────────
const T = {
  listed: {
    main: '预收款项',
    longTerm: '账龄超过1年的重要预收款项',
    change: '本期预收账款账面价值的重大变动',
  },
  soe: {
    main: '预收款项',
    longTerm: '账龄超过1年的重要预收款项',
  },
} as const

const AMT = 'amount' as const
const TXT = 'text' as const

// ─── 列头元数据（逐字取自附注模板 headers）────────────────────────────────────
const MAIN_COLUMNS_LISTED: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'end_amount', label: '期末余额', format: AMT },
  { key: 'prior_amount', label: '上年年末余额', format: AMT },
]
const MAIN_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '账龄', is_label: true },
  { key: 'end_amount', label: '期末余额', format: AMT },
  { key: 'prior_amount', label: '期初余额', format: AMT },
]
const LONG_TERM_COLUMNS_LISTED: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'end_amount', label: '期末余额', format: AMT },
  { key: 'reason', label: '未偿还或未结转的原因', format: TXT },
]
const LONG_TERM_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '债权单位名称', is_label: true },
  { key: 'end_amount', label: '期末余额', format: AMT },
  { key: 'reason', label: '未结转原因', format: TXT },
]
const CHANGE_COLUMNS_LISTED: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'change_amount', label: '变动金额', format: AMT },
  { key: 'reason', label: '变动原因', format: TXT },
]

// ─── 快照行类型（组件层传入，字段与 useD3Disclosure* 行接口对齐）────────────────
export interface D3RowLike { label: string; endAmount: number; priorAmount: number; rowKey?: string }
export interface D3LongTermRowLike { label: string; endAmount: number; priorAmount?: number; reason?: string }
export interface D3ChangeRowLike { label: string; endAmount: number; priorAmount: number; reason?: string }

export interface D3DisclosureSnapshot {
  /** 上市：按性质分类；国企：按账龄分类（section1Rows） */
  mainRows: D3RowLike[]
  mainTotal: D3RowLike
  /** 账龄超过1年的重要预收（section2Rows，不含合计行；合计另传） */
  longTermRows: D3LongTermRowLike[]
  longTermTotal: D3RowLike
  /** 上市：本期账面价值重大变动（section3Rows）；国企无此表 */
  changeRows?: D3ChangeRowLike[]
  /** 各子节说明文本（文本框内容），与披露表保持一致后同步到附注 text_content */
  notes: Record<string, string>
}

export interface D3SyncPayload {
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
 * 构建 D3 → 附注 sync-from-workpaper 载荷。
 * 上市：五、38（预收款项 / 超1年 / 重大变动 3 表）；国企：八、38（预收款项按账龄 / 超1年 2 表）。
 */
export function buildD3SyncPayload(
  variant: D3DisclosureVariant,
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snapshot: D3DisclosureSnapshot,
): D3SyncPayload {
  const isSoe = variant === 'soe'
  const names = isSoe ? T.soe : T.listed
  const sub: Record<string, unknown> = {}
  const columns: Record<string, ColumnDef[]> = {}
  const put = (name: string, rows: unknown, cols: ColumnDef[]) => {
    sub[name] = rows
    columns[name] = cols
  }

  // ① 主表（上市按性质分类 / 国企按账龄）
  //
  // 🔴 合计行标签**不做**结构行映射：D3 附注模板（五、38 / 八、38）合计行字面为
  // `合计`（无空格），与 D2 §五、5 / §八、5 的 `合 计` 不同 —— 按附注模板逐字照抄，
  // 不套 `DISCLOSURE_TOTAL_LABEL`，否则反而制造漂移。
  const mainRow = (r: D3RowLike, isTotal = false) => ({
    label: isTotal || !isSoe ? str(r.label) : toDisclosureAgingLabel(r, SOE_AGING_OVERRIDES),
    end_amount: num(r.endAmount),
    prior_amount: num(r.priorAmount),
    ...(isTotal ? { is_total: true } : {}),
  })
  put(
    names.main,
    [...snapshot.mainRows.map((r) => mainRow(r)), mainRow(snapshot.mainTotal, true)],
    isSoe ? MAIN_COLUMNS_SOE : MAIN_COLUMNS_LISTED,
  )

  // ② 账龄超过1年的重要预收款项
  put(
    names.longTerm,
    [
      ...snapshot.longTermRows.map((r) => ({
        label: str(r.label),
        end_amount: num(r.endAmount),
        reason: str(r.reason),
      })),
      {
        label: snapshot.longTermTotal.label || '合计',
        end_amount: num(snapshot.longTermTotal.endAmount),
        reason: '',
        is_total: true,
      },
    ],
    isSoe ? LONG_TERM_COLUMNS_SOE : LONG_TERM_COLUMNS_LISTED,
  )

  // ③ 上市：本期账面价值重大变动（变动金额 = 期末 − 期初）
  if (!isSoe) {
    const changeRows = snapshot.changeRows ?? []
    put(
      T.listed.change,
      [
        ...changeRows.map((r) => ({
          label: str(r.label),
          change_amount: num(r.endAmount) - num(r.priorAmount),
          reason: str(r.reason),
        })),
        {
          label: '合计',
          change_amount: changeRows.reduce((s, r) => s + (num(r.endAmount) - num(r.priorAmount)), 0),
          reason: '',
          is_total: true,
        },
      ],
      CHANGE_COLUMNS_LISTED,
    )
  }

  // ④ 文本框内容
  sub._note_texts = buildD3NoteTexts(snapshot.notes)

  return {
    wp_id: wpId,
    sheet_name: D3_DISCLOSURE_SHEET_NAME[variant],
    section_id: D3_NOTE_SECTION[variant],
    current_standard: resolveD3CurrentStandard(variant, applicableStandards),
    sub_table_data: sub,
    columns,
  }
}

/** 说明文本子节顺序与标题（与披露表文本框一一对应，仅上市版有说明文本）。 */
export const D3_NOTE_TEXT_SECTIONS: Array<{ key: string; title: string }> = [
  { key: 'nature', title: '按性质分类说明' },
  { key: 'longTerm', title: '账龄超过1年的重要预收说明' },
  { key: 'change', title: '重大变动说明' },
]

/** 各子节说明 → _note_texts（仅非空），保证附注 text_content 与披露表文本框一致。 */
export function buildD3NoteTexts(notes: Record<string, string>): Array<{ section: string; title: string; text: string }> {
  const out: Array<{ section: string; title: string; text: string }> = []
  for (const { key, title } of D3_NOTE_TEXT_SECTIONS) {
    const text = String(notes?.[key] ?? '').trim()
    if (text) out.push({ section: `note-${key}`, title, text })
  }
  return out
}
