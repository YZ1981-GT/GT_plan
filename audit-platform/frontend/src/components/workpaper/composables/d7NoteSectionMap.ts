/**
 * D7 合同负债披露 ↔ 附注章节冻结映射与 sync payload 构建
 *
 * 权威来源：note_template_listed.json 五、39 / note_template_soe.json 八、39「合同负债」
 * （表名逐字对照模板；行数据来自 D7 底稿「附注披露信息(上市公司)/(国企)」披露表）。
 *
 * 底稿 → 附注单向推送（sync_from_workpaper）：
 *  - sub_table_data 各子表 → 附注 table_data.sub_table_data（读时投影为 _tables 渲染）
 *  - sub_table_data._note_texts → 附注 text_content（文本框内容与披露表保持一致）
 *  - columns → _sub_table_columns（投影器据此产出扁平表头，附注模块渲染）
 *
 * 🔴 覆盖必须完整：note_sub_table_projector 对 `_source=workpaper` 的附注
 * **只渲染 sub_table_data 里推送过的子表**（不与模板 _tables 合并），故逐张覆盖。
 *
 * 覆盖完整性（对照模板 + useD7Disclosure）：
 *  - 上市 五、39 共 3 张（合同负债[按性质分类] / 账龄超过1年的重要合同负债 / 本期重大变动）
 *  - 国企 八、39 共 2 张（合同负债[按性质分类] / 合同负债（表2）[本期重大变动]）
 *
 * 与模板字面值的偏差（渲染必需，不新增/不删减数据列）：
 *  - 重大变动表模板列头为「变动金额」，D7 披露表按期末/期初两期录入（current/prior），
 *    故变动金额 = 期末 − 期初（保留披露表两期数据的净变动口径，与 D3 一致）。
 *
 * 🔴 sub_table_data 各子表键 ↔ columns 键必须相同（后端投影器按名匹配）。
 */
import type { ColumnDef } from './disclosureColumnDefs'

export type D7DisclosureVariant = 'listed' | 'soe'

export const D7_NOTE_SECTION = {
  listed: '五、39',
  soe: '八、39',
} as const satisfies Record<D7DisclosureVariant, string>

// 底稿披露 sheet 真实 tab 名（半角括号，见 workpaper_sheet_classification wp_code=D7）。
export const D7_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息(上市公司)',
  soe: '附注披露信息(国企)',
} as const satisfies Record<D7DisclosureVariant, string>

export function resolveD7CurrentStandard(
  variant: D7DisclosureVariant,
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

// ─── 表名（逐字取自附注模板 五、39 / 八、39）────────────────────────────────
const T = {
  listed: {
    main: '合同负债',
    longTerm: '账龄超过1年的重要合同负债',
    change: '本期合同负债账面价值的重大变动',
  },
  soe: {
    main: '合同负债',
    change: '合同负债（表2）',
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
  { key: 'label', label: '项目', is_label: true },
  { key: 'end_amount', label: '期末余额', format: AMT },
  { key: 'prior_amount', label: '期初余额', format: AMT },
]
const LONG_TERM_COLUMNS_LISTED: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'end_amount', label: '期末余额', format: AMT },
  { key: 'reason', label: '未偿还或未结转的原因', format: TXT },
]
const CHANGE_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'change_amount', label: '变动金额', format: AMT },
  { key: 'reason', label: '变动原因', format: TXT },
]

// ─── 快照行类型（组件层传入，字段与 useD7Disclosure DisclosureRow 对齐）──────────
export interface D7RowLike {
  label: string
  /** 期末数（current） */
  current: number
  /** 期初数 / 上年年末数（prior） */
  prior: number
  reason?: string
}

export interface D7DisclosureSnapshot {
  /** 主表明细行（不含合计；上市含「减：计入其他非流动负债的合同负债」扣减行） */
  mainRows: D7RowLike[]
  /** 主表合计行 */
  mainTotal: D7RowLike
  /** 上市：账龄超过1年的重要合同负债（明细，不含合计） */
  longTermRows?: D7RowLike[]
  /** 上市：账龄超过1年合计 */
  longTermTotal?: D7RowLike
  /** 本期重大变动明细（上市 listed-3 / 国企 soe-2，不含合计） */
  changeRows?: D7RowLike[]
  /** 各子节说明文本（文本框内容），与披露表保持一致后同步到附注 text_content */
  notes: Record<string, string>
}

export interface D7SyncPayload {
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
 * 构建 D7 → 附注 sync-from-workpaper 载荷。
 * 上市：五、39（合同负债 / 超1年 / 重大变动 3 表）；国企：八、39（合同负债 / 表2重大变动 2 表）。
 */
export function buildD7SyncPayload(
  variant: D7DisclosureVariant,
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snapshot: D7DisclosureSnapshot,
): D7SyncPayload {
  const isSoe = variant === 'soe'
  const names = isSoe ? T.soe : T.listed
  const sub: Record<string, unknown> = {}
  const columns: Record<string, ColumnDef[]> = {}
  const put = (name: string, rows: unknown, cols: ColumnDef[]) => {
    sub[name] = rows
    columns[name] = cols
  }

  // ① 主表（按性质分类；期末/期初两列）
  const mainRow = (r: D7RowLike, isTotal = false) => ({
    label: str(r.label),
    end_amount: num(r.current),
    prior_amount: num(r.prior),
    ...(isTotal ? { is_total: true } : {}),
  })
  put(
    names.main,
    [...snapshot.mainRows.map((r) => mainRow(r)), mainRow(snapshot.mainTotal, true)],
    isSoe ? MAIN_COLUMNS_SOE : MAIN_COLUMNS_LISTED,
  )

  // ② 账龄超过1年的重要合同负债（仅上市）
  if (!isSoe) {
    const longTermRows = snapshot.longTermRows ?? []
    put(
      T.listed.longTerm,
      [
        ...longTermRows.map((r) => ({
          label: str(r.label),
          end_amount: num(r.current),
          reason: str(r.reason),
        })),
        {
          label: snapshot.longTermTotal?.label || '合计',
          end_amount: num(snapshot.longTermTotal?.current),
          reason: '',
          is_total: true,
        },
      ],
      LONG_TERM_COLUMNS_LISTED,
    )
  }

  // ③ 本期账面价值重大变动（变动金额 = 期末 − 期初）
  const changeRows = snapshot.changeRows ?? []
  put(
    names.change,
    [
      ...changeRows.map((r) => ({
        label: str(r.label),
        change_amount: num(r.current) - num(r.prior),
        reason: str(r.reason),
      })),
      {
        label: '合计',
        change_amount: changeRows.reduce((s, r) => s + (num(r.current) - num(r.prior)), 0),
        reason: '',
        is_total: true,
      },
    ],
    CHANGE_COLUMNS,
  )

  // ④ 文本框内容
  sub._note_texts = buildD7NoteTexts(variant, snapshot.notes)

  return {
    wp_id: wpId,
    sheet_name: D7_DISCLOSURE_SHEET_NAME[variant],
    section_id: D7_NOTE_SECTION[variant],
    current_standard: resolveD7CurrentStandard(variant, applicableStandards),
    sub_table_data: sub,
    columns,
  }
}

/**
 * 说明文本子节（key = useD7Disclosure 的 NOTE_TEXT_KEYS；标题与披露表子节一致）。
 * 上市 3 节 / 国企 2 节。
 */
export const D7_NOTE_TEXT_SECTIONS: Record<D7DisclosureVariant, Array<{ key: string; title: string }>> = {
  listed: [
    { key: 'D7-note-listed-text-1', title: '按性质分类说明' },
    { key: 'D7-note-listed-text-2', title: '账龄超过1年的重要合同负债说明' },
    { key: 'D7-note-listed-text-3', title: '本期合同负债账面价值重大变动说明' },
  ],
  soe: [
    { key: 'D7-note-soe-text-1', title: '按性质分类说明' },
    { key: 'D7-note-soe-text-2', title: '本期账面价值重大变动说明' },
  ],
}

/** 各子节说明 → _note_texts（仅非空），保证附注 text_content 与披露表文本框一致。 */
export function buildD7NoteTexts(
  variant: D7DisclosureVariant,
  notes: Record<string, string>,
): Array<{ section: string; title: string; text: string }> {
  const out: Array<{ section: string; title: string; text: string }> = []
  for (const { key, title } of D7_NOTE_TEXT_SECTIONS[variant]) {
    const text = String(notes?.[key] ?? '').trim()
    if (text) out.push({ section: key, title, text })
  }
  return out
}
