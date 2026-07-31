/**
 * D6 合同资产披露 ↔ 附注章节冻结映射与 sync payload 构建
 *
 * 权威来源：源 xlsx `backend/wp_templates/D/D6 合同资产.xlsx` 的两个披露 sheet
 * （openpyxl 逐格 + 合并区读出），模板 JSON 五、10 / 八、11 已由
 * `backend/scripts/fix/fix_note_d_cycle_rest_structure.py` 按源模板对齐。
 *
 * 🔴 2026-07-30 修订（`.kiro/specs/d-cycle-remaining-disclosure-alignment/` Task 6）：
 *
 * 1. **两级表头改走 `ColumnDef.group`**。旧实现把两级表头拍平成「期末账面余额」式
 *    组合列名 → 附注渲染成单级 7 列，源模板的期间父表头丢失。
 * 2. **补回上年年末段**。旧载荷的「减值准备计提情况」只有期末 4 列（缺账面价值 +
 *    整个上年年末段 5 列）、「按单项计提」与「组合计提」也只有期末 → 附注比较期整段空缺。
 * 3. **表名逐字对齐模板**。旧表名（`按单项计提坏账准备的合同资产` /
 *    `按组合计提坏账准备的合同资产：X` / `合同资产减值准备计提情况`）与模板不一致，
 *    产出孤儿子表 → 现按源模板命名，旧名进 `_removed_table_keys`。
 * 4. **源模板三级表头 → 顶层期间提到表名**。平台附注只支持两级
 *    （前端 `DisclosureEditor.activeTableColumns` 只认扁平 `{group,start,span}`），
 *    源模板 (2) 表是「期末余额 > 账面余额·减值准备 > 金额·比例」三级 →
 *    拆成 `（期末余额）` / `（续：上年年末余额）` 两张表，与 D1 国企分类表同范式。
 *
 * 底稿 → 附注单向推送（sync_from_workpaper）：sub_table_data 各子表 + _note_texts → 附注。
 * 🔴 覆盖必须完整：`note_sub_table_projector` 对 `_source=workpaper` 只渲染推送过的子表
 * （不与模板 `_tables` 合并），故逐张覆盖。
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

/** 合计行 / 小计行字面 = 源模板字面（A16 `小  计` / A18 `合  计` / A54 `合 计`）。 */
export const D6_NOTE_TOTAL_LABEL = {
  main: '合  计',
  mainSubtotal: '小  计',
  impairment: '合 计',
  other: '合  计',
} as const

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

// ─── 表名（🔴 逐字取自附注模板 五、10 / 八、11 = 源 xlsx 字面）────────────────
const T = {
  listed: {
    main: '合同资产',
    majorChange: '本期合同资产账面价值的重大变动',
    impairmentEnd: '合同资产减值准备计提情况（期末余额）',
    impairmentPrior: '合同资产减值准备计提情况（续：上年年末余额）',
    singleEnd: '按单项计提减值准备（期末余额）',
    singlePrior: '按单项计提减值准备（续：上年年末余额）',
    groupPrefix: '组合计提项目：',
    change: '本期计提、收回或转回的合同资产减值准备情况',
  },
  soe: {
    main: '合同资产情况',
    impairment: '合同资产减值准备',
    majorChange: '本期合同资产账面价值的重大变动',
  },
} as const

/**
 * 子表名映射（供共享契约 helper 逐字校验）。
 *
 * 🔴 只放**固定表名**：组合明细表名是「组合计提项目：{组名}」动态生成
 * （模板里的「工程施工」「质量保证金」只是源模板示例骨架），前缀单独导出，
 * 否则契约 helper 会把前缀当表名去模板里找，必然找不到。
 */
export const D6_LISTED_SUBTABLE = {
  main: T.listed.main,
  majorChange: T.listed.majorChange,
  impairmentEnd: T.listed.impairmentEnd,
  impairmentPrior: T.listed.impairmentPrior,
  singleEnd: T.listed.singleEnd,
  singlePrior: T.listed.singlePrior,
  change: T.listed.change,
} as const
export const D6_GROUP_TABLE_PREFIX = T.listed.groupPrefix
export const D6_SOE_SUBTABLE = T.soe

/**
 * 改版前推送过的旧子表名 → 随载荷上报 `_removed_table_keys`（后端删旧键）。
 *
 * 组合明细旧名带动态组名（`按组合计提坏账准备的合同资产：{组名}`），无法穷举 →
 * 载荷侧按当前组名逐个推导旧名一并清理（见 `buildD6SyncPayload`）。
 */
export const D6_OBSOLETE_TABLE_NAMES: Record<D6DisclosureVariant, string[]> = {
  listed: [
    '合同资产减值准备计提情况',
    '按单项计提减值准备：',
    '按单项计提减值准备',
    '按单项计提坏账准备的合同资产',
    '续：',
    '项  目',
  ],
  soe: [],
}

/** 旧组合子表名（改版前前缀），用于按当前组名清理孤儿表。 */
const LEGACY_GROUP_PREFIX = '按组合计提坏账准备的合同资产：'

const AMT = 'amount' as const
const PCT = 'percent' as const
const TXT = 'text' as const

// ─── 列头元数据（🔴 两级表头走 group，单级表头必须显式 flat）───────────────────

const MAIN_GROUPS: Record<D6DisclosureVariant, readonly [string, string]> = {
  listed: ['期末余额', '上年年末余额'],
  soe: ['期末数', '期初数'],
}

const BOOK_SUBS = [
  ['book_balance', '账面余额'],
  ['impairment', '减值准备'],
  ['book_value', '账面价值'],
] as const

const GROUP_SUBS = [
  ['balance', '合同资产'],
  ['provision', '坏账准备'],
  ['loss_rate', '预期信用损失率(%)'],
] as const

/** 双期同构两级表头（构造保证两期子列名相等）。 */
function twoPeriodColumns(
  labelHeader: string,
  groups: readonly [string, string],
  subs: readonly (readonly [string, string])[],
  formatOf: (suffix: string) => string,
): ColumnDef[] {
  const out: ColumnDef[] = [{ key: 'label', label: labelHeader, is_label: true }]
  ;(['end', 'prior'] as const).forEach((prefix, i) => {
    for (const [suffix, label] of subs) {
      out.push({ key: `${prefix}_${suffix}`, label, group: groups[i], format: formatOf(suffix) })
    }
  })
  return out
}

const amountOrPercent = (suffix: string): string => (suffix === 'loss_rate' ? PCT : AMT)

export function d6MainColumns(variant: D6DisclosureVariant): ColumnDef[] {
  return twoPeriodColumns('项  目', MAIN_GROUPS[variant], BOOK_SUBS, () => AMT)
}

function d6GroupColumns(): ColumnDef[] {
  return twoPeriodColumns('账  龄', MAIN_GROUPS.listed, GROUP_SUBS, amountOrPercent)
}

/**
 * 主表披露格式（源模板 A20「或：披露格式如下」= 二选一表组）。
 *
 * - `detailed`：源模板 A7-A18，双期各「账面余额 / 减值准备 / 账面价值」两级表头（7 列）
 * - `simple`：源模板 A21-A26，单级 3 列（项目 / 期末余额 / 上年年末余额），
 *   行为「合同资产 / 减：合同资产减值准备 / 小计 / 减：列示于其他非流动资产的合同资产 / 合计」
 *
 * 两者**同名同表**（附注 `合同资产`），故切换时不需要 `_removed_table_keys`，
 * 只是 `columns` 与 `rows` 形态不同。
 */
export type D6MainFormat = 'detailed' | 'simple'

/** 简化格式的列（源模板 A21 单行表头 → 必须显式 flat）。 */
const MAIN_SIMPLE_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项  目', is_label: true, flat: true },
  { key: 'end_amount', label: '期末余额', format: AMT },
  { key: 'prior_amount', label: '上年年末余额', format: AMT },
]

/** 简化格式的固定行名（逐字取自源模板 A22-A26）。 */
export const D6_SIMPLE_MAIN_LABELS = {
  asset: '合同资产',
  impairment: '减：合同资产减值准备',
  subtotal: '小  计',
  nonCurrent: '减：列示于其他非流动资产的合同资产',
  total: '合  计',
} as const

const MAJOR_CHANGE_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项  目', is_label: true, flat: true },
  { key: 'change_amount', label: '变动金额', format: AMT },
  { key: 'reason', label: '变动原因', format: TXT },
]

/**
 * 减值准备计提情况（单期）：源模板 B44:C44「账面余额」{金额, 比例(%)} /
 * D44:E44「减值准备」{金额, 预期信用损失率(%)} / F44:F45「账面价值」（rowspan=2 独立列）。
 */
const IMPAIRMENT_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '类别', is_label: true },
  { key: 'balance_amount', label: '金额', group: '账面余额', format: AMT },
  { key: 'balance_ratio', label: '比例(%)', group: '账面余额', format: PCT },
  { key: 'provision_amount', label: '金额', group: '减值准备', format: AMT },
  { key: 'provision_loss_rate', label: '预期信用损失率(%)', group: '减值准备', format: PCT },
  { key: 'book_value', label: '账面价值', format: AMT },
]

const SINGLE_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '名 称', is_label: true, flat: true },
  { key: 'balance', label: '账面余额', format: AMT },
  { key: 'provision', label: '坏账准备', format: AMT },
  { key: 'loss_rate', label: '预期信用损失率(%)', format: PCT },
  { key: 'reason', label: '计提理由', format: TXT },
]

const CHANGE_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项  目', is_label: true, flat: true },
  { key: 'provision', label: '本期计提', format: AMT },
  { key: 'reversal', label: '本期转回', format: AMT },
  { key: 'write_off', label: '本期转销/核销', format: AMT },
  { key: 'reason', label: '原因', format: TXT },
]

/** 国企减值准备变动：源 C19:E19 合并为「本期变动金额」，期初/期末/原因为独立列。 */
const SOE_IMPAIRMENT_COLUMNS: ColumnDef[] = [
  { key: 'label', label: '项  目', is_label: true },
  { key: 'prior_balance', label: '期初数', format: AMT },
  { key: 'provision', label: '计提', group: '本期变动金额', format: AMT },
  { key: 'reversal', label: '转回', group: '本期变动金额', format: AMT },
  { key: 'write_off', label: '转销/核销', group: '本期变动金额', format: AMT },
  { key: 'end_balance', label: '期末数', format: AMT },
  { key: 'reason', label: '原因', format: TXT },
]

/** 列定义：`{模板表名: ColumnDef[]}`（零参，供覆盖率 sweep 与契约 helper 调用）。 */
export function buildD6ListedColumns(): Record<string, ColumnDef[]> {
  return {
    [T.listed.main]: d6MainColumns('listed'),
    [T.listed.majorChange]: MAJOR_CHANGE_COLUMNS,
    [T.listed.impairmentEnd]: IMPAIRMENT_COLUMNS,
    [T.listed.impairmentPrior]: IMPAIRMENT_COLUMNS,
    [T.listed.singleEnd]: SINGLE_COLUMNS,
    [T.listed.singlePrior]: SINGLE_COLUMNS,
    [T.listed.change]: CHANGE_COLUMNS,
  }
}

export function buildD6SoeColumns(): Record<string, ColumnDef[]> {
  return {
    [T.soe.main]: d6MainColumns('soe'),
    [T.soe.impairment]: SOE_IMPAIRMENT_COLUMNS,
    [T.soe.majorChange]: MAJOR_CHANGE_COLUMNS,
  }
}

// ─── 快照行类型（组件层传入，字段与 useD6Disclosure 行接口对齐）───────────────

export interface D6ClassRowLike {
  label: string
  endBookBalance: number; endImpairment: number; endBookValue: number
  priorBookBalance: number; priorImpairment: number; priorBookValue: number
}
export interface D6MajorChangeRowLike { label: string; amount: number; reason?: string }
/** 减值准备计提情况的单期行（期末段与上年段各一组，列结构同构）。 */
export interface D6ImpairmentProvisionRowLike {
  label: string
  balance: number
  ratio: number
  provision: number
  lossRate: number
  bookValue?: number
}
export interface D6SingleItemRowLike {
  label: string; balance: number; provision: number; lossRate: number; reason?: string
}
export interface D6GroupRowLike {
  label: string
  balance: number; provision: number; lossRate: number
  priorBalance?: number; priorProvision?: number; priorLossRate?: number
}
export interface D6GroupLike { groupName: string; rows: D6GroupRowLike[] }
export interface D6ChangeRowLike {
  label: string; provision: number; reversal: number; writeOff: number; reason?: string
}
export interface D6SoeImpairmentRowLike {
  label: string; priorBalance: number; provision: number; reversal: number
  writeOff: number; endBalance: number; reason?: string
}

export interface D6DisclosureSnapshot {
  /** 分类表（上市）/ 合同资产情况（国企），双期各 3 列 */
  classRows: D6ClassRowLike[]
  /** 上市主表披露格式（源模板 A20「或：」二选一），缺省 `detailed` */
  mainFormat?: D6MainFormat
  /** 本期账面价值重大变动（上市 + 国企均有） */
  majorChangeRows?: D6MajorChangeRowLike[]
  /** 减值计提情况 —— 期末段（仅上市） */
  impairmentProvisionRows?: D6ImpairmentProvisionRowLike[]
  /** 减值计提情况 —— 上年年末段（仅上市，源模板 G43:K54） */
  impairmentProvisionPriorRows?: D6ImpairmentProvisionRowLike[]
  /** 单项明细 —— 期末段（仅上市） */
  singleItems?: D6SingleItemRowLike[]
  /** 单项明细 —— 上年年末段（仅上市，源模板 A61「续：」） */
  singleItemsPrior?: D6SingleItemRowLike[]
  /** 组合明细（仅上市，逐组一张子表，双期同表并列） */
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

/** 结构标签行（「其中：」）不参与合计。 */
const isStructuralLabel = (label: string): boolean => label.replace(/\s+/g, '') === '其中：'

/** 小计 / 合计 / 「减：」等派生行不参与再次汇总（🔴 判定先去空白：源模板写「小  计」）。 */
function isDerivedMainRow(label: string): boolean {
  const s = String(label ?? '').replace(/\s+/g, '')
  return s === '小计' || s === '合计' || s.startsWith('减：') || s === '其中：'
}

/**
 * 简化格式的行由明细行派生（纯函数，载荷与底稿 UI 共用，避免双真源）。
 *
 * 「减：列示于其他非流动资产的合同资产」若明细里已有同名行则取其金额，否则为 0。
 */
export function buildD6SimpleMainRows(
  classRows: readonly D6ClassRowLike[],
): Array<{ label: string; end_amount: number; prior_amount: number; is_total?: boolean }> {
  const detail = classRows.filter((r) => !isDerivedMainRow(r.label))
  const sum = (pick: (r: D6ClassRowLike) => number) =>
    detail.reduce((s, r) => s + num(pick(r)), 0)
  const nonCurrentRow = classRows.find(
    (r) => String(r.label ?? '').replace(/\s+/g, '') ===
      D6_SIMPLE_MAIN_LABELS.nonCurrent.replace(/\s+/g, ''),
  )
  const endAsset = sum((r) => r.endBookBalance)
  const priorAsset = sum((r) => r.priorBookBalance)
  const endImp = sum((r) => r.endImpairment)
  const priorImp = sum((r) => r.priorImpairment)
  const endNonCurrent = num(nonCurrentRow?.endBookValue)
  const priorNonCurrent = num(nonCurrentRow?.priorBookValue)
  return [
    { label: D6_SIMPLE_MAIN_LABELS.asset, end_amount: endAsset, prior_amount: priorAsset },
    { label: D6_SIMPLE_MAIN_LABELS.impairment, end_amount: endImp, prior_amount: priorImp },
    {
      label: D6_SIMPLE_MAIN_LABELS.subtotal,
      end_amount: endAsset - endImp,
      prior_amount: priorAsset - priorImp,
      is_total: true,
    },
    {
      label: D6_SIMPLE_MAIN_LABELS.nonCurrent,
      end_amount: endNonCurrent,
      prior_amount: priorNonCurrent,
    },
    {
      label: D6_SIMPLE_MAIN_LABELS.total,
      end_amount: endAsset - endImp - endNonCurrent,
      prior_amount: priorAsset - priorImp - priorNonCurrent,
      is_total: true,
    },
  ]
}

/**
 * 构建 D6 → 附注 sync-from-workpaper 载荷。
 * 上市：五、10（7 表 + 逐组组合表）；国企：八、11（3 表）。
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

  // ① 分类表 / 合同资产情况（双期两级表头；上市可切源模板 A20「或」的简化格式）
  const simpleMain = !isSoe && snapshot.mainFormat === 'simple'
  put(
    isSoe ? T.soe.main : T.listed.main,
    simpleMain ? buildD6SimpleMainRows(snapshot.classRows) : snapshot.classRows.map(classRow),
    simpleMain ? MAIN_SIMPLE_COLUMNS : d6MainColumns(variant),
  )

  // ② 本期账面价值重大变动（上市 + 国企均有）
  const majorChange = snapshot.majorChangeRows ?? []
  put(
    isSoe ? T.soe.majorChange : T.listed.majorChange,
    [
      ...majorChange.map((r) => ({
        label: str(r.label),
        change_amount: num(r.amount),
        reason: str(r.reason),
      })),
      {
        label: D6_NOTE_TOTAL_LABEL.other,
        change_amount: majorChange.reduce((s, r) => s + num(r.amount), 0),
        reason: '',
        is_total: true,
      },
    ],
    MAJOR_CHANGE_COLUMNS,
  )

  if (isSoe) {
    // ③ 国企减值准备变动（本期变动金额 3 列一组）
    const impRows = snapshot.soeImpairmentRows ?? []
    const sum = (pick: (r: D6SoeImpairmentRowLike) => number) =>
      impRows.reduce((s, r) => s + num(pick(r)), 0)
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
          label: D6_NOTE_TOTAL_LABEL.other,
          prior_balance: sum((r) => r.priorBalance),
          provision: sum((r) => r.provision),
          reversal: sum((r) => r.reversal),
          write_off: sum((r) => r.writeOff),
          end_balance: sum((r) => r.endBalance),
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

  // ③ 减值计提情况（上市，期末段 + 上年年末段两张同构表）
  const impairmentRow = (r: D6ImpairmentProvisionRowLike) => ({
    label: str(r.label),
    balance_amount: num(r.balance),
    balance_ratio: num(r.ratio),
    provision_amount: num(r.provision),
    provision_loss_rate: num(r.lossRate),
    book_value: r.bookValue === undefined ? num(r.balance) - num(r.provision) : num(r.bookValue),
  })
  const impairmentTable = (rows: D6ImpairmentProvisionRowLike[]) => {
    const data = rows.filter((r) => !isStructuralLabel(str(r.label)))
    const totalBalance = data.reduce((s, r) => s + num(r.balance), 0)
    const totalProvision = data.reduce((s, r) => s + num(r.provision), 0)
    return [
      ...rows.map(impairmentRow),
      {
        label: D6_NOTE_TOTAL_LABEL.impairment,
        balance_amount: totalBalance,
        balance_ratio: totalBalance === 0 ? 0 : 100,
        provision_amount: totalProvision,
        provision_loss_rate: totalBalance === 0 ? 0 : (totalProvision / totalBalance) * 100,
        book_value: totalBalance - totalProvision,
        is_total: true,
      },
    ]
  }
  put(T.listed.impairmentEnd, impairmentTable(snapshot.impairmentProvisionRows ?? []), IMPAIRMENT_COLUMNS)
  put(
    T.listed.impairmentPrior,
    impairmentTable(snapshot.impairmentProvisionPriorRows ?? []),
    IMPAIRMENT_COLUMNS,
  )

  // ④ 单项明细（期末段 + 上年年末段）
  const singleTable = (rows: D6SingleItemRowLike[]) => [
    ...rows.map((r) => ({
      label: str(r.label),
      balance: num(r.balance),
      provision: num(r.provision),
      loss_rate: num(r.lossRate),
      reason: str(r.reason),
    })),
    {
      label: D6_NOTE_TOTAL_LABEL.other,
      balance: rows.reduce((s, r) => s + num(r.balance), 0),
      provision: rows.reduce((s, r) => s + num(r.provision), 0),
      loss_rate: 0,
      reason: '',
      is_total: true,
    },
  ]
  put(T.listed.singleEnd, singleTable(snapshot.singleItems ?? []), SINGLE_COLUMNS)
  put(T.listed.singlePrior, singleTable(snapshot.singleItemsPrior ?? []), SINGLE_COLUMNS)

  // ⑤ 组合明细（逐组一张子表，双期同表并列；同名兜底避免键冲突）
  const groups = snapshot.groups ?? []
  const usedNames = new Set<string>()
  const legacyGroupNames: string[] = []
  const groupCols = d6GroupColumns()
  groups.forEach((g, gi) => {
    const rawName = str(g.groupName).trim() || `组合${gi + 1}`
    const base = `${T.listed.groupPrefix}${rawName}`
    let name = base
    let dup = 2
    while (usedNames.has(name)) name = `${base}（${dup++}）`
    usedNames.add(name)
    legacyGroupNames.push(`${LEGACY_GROUP_PREFIX}${rawName}`)
    const rows = g.rows ?? []
    const sum = (pick: (r: D6GroupRowLike) => number | undefined) =>
      rows.reduce((s, r) => s + num(pick(r)), 0)
    put(
      name,
      [
        ...rows.map((r) => ({
          label: str(r.label),
          end_balance: num(r.balance),
          end_provision: num(r.provision),
          end_loss_rate: num(r.lossRate),
          prior_balance: num(r.priorBalance),
          prior_provision: num(r.priorProvision),
          prior_loss_rate: num(r.priorLossRate),
        })),
        {
          label: D6_NOTE_TOTAL_LABEL.other,
          end_balance: sum((r) => r.balance),
          end_provision: sum((r) => r.provision),
          end_loss_rate: 0,
          prior_balance: sum((r) => r.priorBalance),
          prior_provision: sum((r) => r.priorProvision),
          prior_loss_rate: 0,
          is_total: true,
        },
      ],
      groupCols,
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
        label: D6_NOTE_TOTAL_LABEL.other,
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

  // ⑦ 清理改版前推送过的旧子表（静态旧名 + 按当前组名推导的旧组合表名）
  const obsolete = [...D6_OBSOLETE_TABLE_NAMES.listed, ...legacyGroupNames].filter(
    (n) => !(n in sub),
  )
  if (obsolete.length) sub._removed_table_keys = obsolete

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
