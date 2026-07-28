/**
 * D6 合同资产披露 ↔ 附注章节冻结映射与 sync payload 构建
 *
 * 权威来源：note_template_listed.json 五、10 / note_template_soe.json 八、11「合同资产」
 * （表名取自模板；列头对齐披露表实际结构 — 模板 五、10 为自动抽取产物含
 *  「续：/项 目/''」等杂散表名与不匹配列数，故列头/结构以披露表为准，保证
 *  「附注表结构跟披露表格式一致」；行数据来自 D6 底稿披露表）。
 *
 * 底稿 → 附注单向推送（sync_from_workpaper）：sub_table_data 各子表 + _note_texts → 附注。
 * 🔴 覆盖必须完整：note_sub_table_projector 对 `_source=workpaper` 只渲染推送过的子表
 * （不与模板 _tables 合并），故逐张覆盖。
 *
 * 覆盖完整性（对照披露组件 useD6Disclosure）：
 *  - 上市 五、10 共 6 张（分类 / 重大变动 / 减值计提情况 / 单项明细 / 组合明细[逐组] / 计提转回核销）
 *  - 国企 八、11 共 3 张（合同资产情况 / 减值准备 / 重大变动）
 *
 * 与模板字面值的偏差（渲染必需，不新增/不删减数据列）：
 *  - 分类表/合同资产情况：披露表为 6 列（期末/上年 各 账面余额/减值准备/账面价值），
 *    模板 table0 简化为 3 列，此处以披露表 6 列为准（多级表头拍平为组合列名）。
 *  - 组合明细：模板按组分表（组合计提项目：工程施工/质量保证金），故逐组输出一张子表。
 */
import type { ColumnDef } from './disclosureColumnDefs'

export type D6DisclosureVariant = 'listed' | 'soe'

export const D6_NOTE_SECTION = {
  listed: '五、10',
  soe: '八、11',
} as const satisfies Record<D6DisclosureVariant, string>

// 底稿披露 sheet 真实 tab 名（🔴 上市为半角左括号+全角右括号混合，见
// workpaper_sheet_classification wp_code=D6，错一字符 ?sheet= 精确匹配失败回退底稿目录）。
export const D6_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息(上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<D6DisclosureVariant, string>

export function resolveD6CurrentStandard(
  variant: D6DisclosureVariant,
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

// ─── 表名（取自附注模板 五、10 / 八、11）──────────────────────────────────────
const T = {
  listed: {
    main: '合同资产',
    majorChange: '本期合同资产账面价值的重大变动',
    impairmentProvision: '合同资产减值准备计提情况',
    singleItem: '按单项计提坏账准备的合同资产',
    groupPrefix: '按组合计提坏账准备的合同资产',
    change: '本期计提、收回或转回的合同资产减值准备情况',
  },
  soe: {
    main: '合同资产情况',
    impairment: '合同资产减值准备',
    majorChange: '本期合同资产账面价值的重大变动',
  },
} as const

const AMT = 'amount' as const
const PCT = 'percent' as const
const TXT = 'text' as const

// ─── 列头元数据（列头对齐披露表实际列，多级表头拍平为组合列名）───────────────
const CLASS_COLUMNS_LISTED: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'end_book_balance', label: '期末账面余额', format: AMT },
  { key: 'end_impairment', label: '期末减值准备', format: AMT },
  { key: 'end_book_value', label: '期末账面价值', format: AMT },
  { key: 'prior_book_balance', label: '上年账面余额', format: AMT },
  { key: 'prior_impairment', label: '上年减值准备', format: AMT },
  { key: 'prior_book_value', label: '上年账面价值', format: AMT },
]
const CLASS_COLUMNS_SOE: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'end_book_balance', label: '期末账面余额', format: AMT },
  { key: 'end_impairment', label: '期末减值准备', format: AMT },
  { key: 'end_book_value', label: '期末账面价值', format: AMT },
  { key: 'prior_book_balance', label: '期初账面余额', format: AMT },
  { key: 'prior_impairment', label: '期初减值准备', format: AMT },
  { key: 'prior_book_value', label: '期初账面价值', format: AMT },
]
const MAJOR_CHANGE_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'amount', label: '变动金额', format: AMT },
  { key: 'reason', label: '变动原因', format: TXT },
]
const IMPAIRMENT_PROVISION_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '类别', is_label: true },
  { key: 'end_balance', label: '期末余额', format: AMT },
  { key: 'end_percentage', label: '比例%', format: PCT },
  { key: 'end_amount', label: '减值金额', format: AMT },
  { key: 'end_loss_rate', label: '损失率%', format: PCT },
]
const SINGLE_ITEM_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '名称', is_label: true },
  { key: 'balance', label: '账面余额', format: AMT },
  { key: 'provision', label: '坏账准备', format: AMT },
  { key: 'loss_rate', label: '损失率%', format: PCT },
  { key: 'reason', label: '计提理由', format: TXT },
]
const GROUP_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '账龄', is_label: true },
  { key: 'balance', label: '合同资产', format: AMT },
  { key: 'provision', label: '坏账准备', format: AMT },
  { key: 'loss_rate', label: '损失率%', format: PCT },
]
const CHANGE_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'provision', label: '本期计提', format: AMT },
  { key: 'reversal', label: '本期转回', format: AMT },
  { key: 'write_off', label: '本期核销', format: AMT },
  { key: 'reason', label: '原因', format: TXT },
]
const SOE_IMPAIRMENT_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项目', is_label: true },
  { key: 'prior_balance', label: '期初数', format: AMT },
  { key: 'provision', label: '本期计提', format: AMT },
  { key: 'reversal', label: '本期转回', format: AMT },
  { key: 'write_off', label: '本期转销/核销', format: AMT },
  { key: 'end_balance', label: '期末数', format: AMT },
  { key: 'reason', label: '原因', format: TXT },
]

// ─── 快照行类型（组件层传入，字段与 useD6Disclosure 行接口对齐）───────────────
export interface D6ClassRowLike {
  label: string
  endBookBalance: number; endImpairment: number; endBookValue: number
  priorBookBalance: number; priorImpairment: number; priorBookValue: number
}
export interface D6MajorChangeRowLike { label: string; amount: number; reason?: string }
export interface D6ImpairmentProvisionRowLike {
  label: string; endBalance: number; endPercentage: number; endAmount: number; endLossRate: number
}
export interface D6SingleItemRowLike { label: string; balance: number; provision: number; lossRate: number; reason?: string }
export interface D6GroupLike {
  groupName: string
  rows: Array<{ label: string; balance: number; provision: number; lossRate: number }>
}
export interface D6ChangeRowLike { label: string; provision: number; reversal: number; writeOff: number; reason?: string }
export interface D6SoeImpairmentRowLike {
  label: string; priorBalance: number; provision: number; reversal: number; writeOff: number; endBalance: number; reason?: string
}

export interface D6DisclosureSnapshot {
  /** 分类表（上市）/ 合同资产情况（国企），6 列同构 */
  classRows: D6ClassRowLike[]
  /** 本期账面价值重大变动（上市 + 国企均有） */
  majorChangeRows?: D6MajorChangeRowLike[]
  /** 减值计提情况（仅上市） */
  impairmentProvisionRows?: D6ImpairmentProvisionRowLike[]
  /** 单项明细（仅上市） */
  singleItems?: D6SingleItemRowLike[]
  /** 组合明细（仅上市，逐组一张子表） */
  groups?: D6GroupLike[]
  /** 计提转回核销（仅上市） */
  changeRows?: D6ChangeRowLike[]
  /** 减值准备变动（仅国企，横向明细行） */
  soeImpairmentRows?: D6SoeImpairmentRowLike[]
  /** 各子节说明文本 */
  notes: Record<string, string>
}

export interface D6SyncPayload {
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
 * 构建 D6 → 附注 sync-from-workpaper 载荷。
 * 上市：五、10（6 表）；国企：八、11（3 表）。
 */
export function buildD6SyncPayload(
  variant: D6DisclosureVariant,
  wpId: string,
  applicableStandards: readonly string[] | null | undefined,
  snapshot: D6DisclosureSnapshot,
): D6SyncPayload {
  const isSoe = variant === 'soe'
  const sub: Record<string, unknown> = {}
  const columns: Record<string, ColumnDef[]> = {}
  const put = (name: string, rows: unknown, cols: ColumnDef[]) => {
    sub[name] = rows
    columns[name] = cols
  }

  const classRow = (r: D6ClassRowLike) => ({
    label: str(r.label),
    end_book_balance: num(r.endBookBalance),
    end_impairment: num(r.endImpairment),
    end_book_value: num(r.endBookValue),
    prior_book_balance: num(r.priorBookBalance),
    prior_impairment: num(r.priorImpairment),
    prior_book_value: num(r.priorBookValue),
  })

  // ① 分类表 / 合同资产情况（6 列同构）
  put(
    isSoe ? T.soe.main : T.listed.main,
    snapshot.classRows.map(classRow),
    isSoe ? CLASS_COLUMNS_SOE : CLASS_COLUMNS_LISTED,
  )

  // ② 本期账面价值重大变动（上市 + 国企均有）
  const majorChange = snapshot.majorChangeRows ?? []
  put(
    isSoe ? T.soe.majorChange : T.listed.majorChange,
    [
      ...majorChange.map((r) => ({ label: str(r.label), amount: num(r.amount), reason: str(r.reason) })),
      { label: '合计', amount: majorChange.reduce((s, r) => s + num(r.amount), 0), reason: '', is_total: true },
    ],
    MAJOR_CHANGE_COLUMNS,
  )

  if (isSoe) {
    // ③ 国企减值准备变动
    const impRows = snapshot.soeImpairmentRows ?? []
    put(
      T.soe.impairment,
      [
        ...impRows.map((r) => ({
          label: str(r.label),
          prior_balance: num(r.priorBalance),
          provision: num(r.provision),
          reversal: num(r.reversal),
          write_off: num(r.writeOff),
          end_balance: num(r.endBalance),
          reason: str(r.reason),
        })),
        {
          label: '合计',
          prior_balance: impRows.reduce((s, r) => s + num(r.priorBalance), 0),
          provision: impRows.reduce((s, r) => s + num(r.provision), 0),
          reversal: impRows.reduce((s, r) => s + num(r.reversal), 0),
          write_off: impRows.reduce((s, r) => s + num(r.writeOff), 0),
          end_balance: impRows.reduce((s, r) => s + num(r.endBalance), 0),
          reason: '',
          is_total: true,
        },
      ],
      SOE_IMPAIRMENT_COLUMNS,
    )
    sub._note_texts = buildD6NoteTexts(snapshot.notes, 'soe')
    return {
      wp_id: wpId,
      sheet_name: D6_DISCLOSURE_SHEET_NAME.soe,
      section_id: D6_NOTE_SECTION.soe,
      current_standard: resolveD6CurrentStandard('soe', applicableStandards),
      sub_table_data: sub,
      columns,
    }
  }

  // ③ 减值计提情况（上市）
  const provRows = snapshot.impairmentProvisionRows ?? []
  put(
    T.listed.impairmentProvision,
    provRows.map((r) => ({
      label: str(r.label),
      end_balance: num(r.endBalance),
      end_percentage: num(r.endPercentage),
      end_amount: num(r.endAmount),
      end_loss_rate: num(r.endLossRate),
    })),
    IMPAIRMENT_PROVISION_COLUMNS,
  )

  // ④ 单项明细（上市）
  const single = snapshot.singleItems ?? []
  put(
    T.listed.singleItem,
    single.map((r) => ({
      label: str(r.label),
      balance: num(r.balance),
      provision: num(r.provision),
      loss_rate: num(r.lossRate),
      reason: str(r.reason),
    })),
    SINGLE_ITEM_COLUMNS,
  )

  // ⑤ 组合明细（逐组一张子表；同名兜底避免键冲突）
  const groups = snapshot.groups ?? []
  const usedNames = new Set<string>()
  groups.forEach((g, gi) => {
    const base = `${T.listed.groupPrefix}：${str(g.groupName).trim() || `组合${gi + 1}`}`
    let name = base
    let dup = 2
    while (usedNames.has(name)) name = `${base}（${dup++}）`
    usedNames.add(name)
    const rows = g.rows ?? []
    put(
      name,
      [
        ...rows.map((r) => ({
          label: str(r.label),
          balance: num(r.balance),
          provision: num(r.provision),
          loss_rate: num(r.lossRate),
        })),
        {
          label: '合计',
          balance: rows.reduce((s, r) => s + num(r.balance), 0),
          provision: rows.reduce((s, r) => s + num(r.provision), 0),
          loss_rate: 0,
          is_total: true,
        },
      ],
      GROUP_COLUMNS,
    )
  })

  // ⑥ 计提转回核销（上市）
  const changeRows = snapshot.changeRows ?? []
  put(
    T.listed.change,
    [
      ...changeRows.map((r) => ({
        label: str(r.label),
        provision: num(r.provision),
        reversal: num(r.reversal),
        write_off: num(r.writeOff),
        reason: str(r.reason),
      })),
      {
        label: '合计',
        provision: changeRows.reduce((s, r) => s + num(r.provision), 0),
        reversal: changeRows.reduce((s, r) => s + num(r.reversal), 0),
        write_off: changeRows.reduce((s, r) => s + num(r.writeOff), 0),
        reason: '',
        is_total: true,
      },
    ],
    CHANGE_COLUMNS,
  )

  sub._note_texts = buildD6NoteTexts(snapshot.notes, 'listed')

  return {
    wp_id: wpId,
    sheet_name: D6_DISCLOSURE_SHEET_NAME.listed,
    section_id: D6_NOTE_SECTION.listed,
    current_standard: resolveD6CurrentStandard('listed', applicableStandards),
    sub_table_data: sub,
    columns,
  }
}

/**
 * 说明文本子节（key = useD6Disclosure 的 NOTE_TEXT_KEYS；标题与披露表子节一致）。
 * 上市 6 节 / 国企 3 节（soe-3 重大变动国资委未要求，仍保留以防手工填写）。
 */
export const D6_NOTE_TEXT_SECTIONS: Record<D6DisclosureVariant, Array<{ key: string; title: string }>> = {
  listed: [
    { key: 'D6-note-listed-text-1', title: '合同资产分类说明' },
    { key: 'D6-note-listed-text-major-change', title: '重大变动说明' },
    { key: 'D6-note-listed-text-2', title: '减值计提情况说明' },
    { key: 'D6-note-listed-text-3', title: '单项计提明细说明' },
    { key: 'D6-note-listed-text-4', title: '组合计提明细说明' },
    { key: 'D6-note-listed-text-5', title: '计提、收回或转回说明' },
  ],
  soe: [
    { key: 'D6-note-soe-text-1', title: '合同资产情况说明' },
    { key: 'D6-note-soe-text-2', title: '减值准备变动说明' },
    { key: 'D6-note-soe-text-3', title: '重大变动说明' },
  ],
}

/** 各子节说明 → _note_texts（仅非空）。 */
export function buildD6NoteTexts(
  notes: Record<string, string>,
  variant: D6DisclosureVariant,
): Array<{ section: string; title: string; text: string }> {
  const out: Array<{ section: string; title: string; text: string }> = []
  for (const { key, title } of D6_NOTE_TEXT_SECTIONS[variant]) {
    const text = String(notes?.[key] ?? '').trim()
    if (text) out.push({ section: key, title, text })
  }
  return out
}
