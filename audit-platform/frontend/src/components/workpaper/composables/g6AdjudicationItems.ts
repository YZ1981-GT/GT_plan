/**
 * G6-1 审定表行定义 — 对齐 Excel 模板《审定表G6-1》
 *
 * 列：期初/期末 ×（未审数 | 账项调整 | 审定数）+ 变动额/变动率 + 原因分析
 * 行：
 *   一、公允价值 → 小计 → 减一年内到期 → 公允价值合计
 *   二、摊余成本
 *     （一）投资成本 / （二）利息调整 / （三）账面余额(=成本+利息)
 *     （四）减值准备 / （五）账面价值(=账面余额-减值)
 *   试算平衡表数 / 差异数
 *
 * Template: backend/wp_templates/G/G6 其他债权投资.xlsx
 *
 * 改进点（相对源模板）：
 * 1. 去掉组合下无名空行（原 R19–R21 / R28–R30 等占位行）
 * 2. 「单项/按组合计提坏账准备」在成本/利息层表示按 ECL 评估方式归类的余额，非减值本身
 * 3. 账面余额、账面价值及对应一年内到期由公式自动勾稽，避免手工重复填报
 * 4. 变动率阈值 30%（与编制说明一致）
 */

/**
 * G6 其他债权投资科目码 —— **委托 `g6AccountScope` 单一真源**。
 *
 * 🔴 本常量原写死 `'1505'`，依据是 `report_config` 的 `BS-022 = TB('1505')`，
 * 但 `account_chart` + `trial_balance.account_name` 双证 **`1505` 实为「债权投资减值准备」**
 * （G4 的备抵科目），其他债权投资真值是 **`1506`**（`report_config` 该行连续偏移一位：
 * BS-022→1505 / BS-025→1506 / BS-026→1507，真值 1506 / 1507 / 1519）。
 *
 * 错码不是「只是显示不对」—— 本常量同时用于
 * ① `useG6MainAdjudication` 发布 `substantive:adjudicated` 的 `accountCode`
 *   （审定数会被记到债权投资减值准备名下）
 * ② `/api/trial-balance/query?account_code=` 的 TB 核对取数（查的是别的科目）。
 *
 * 注：AJE 回写分类逻辑里的 `'150302'/'150304'/'150305'` 是**客户原始子科目编码**
 * （`account_mapping` 映射前），EventBus 调整分录汇总传的是原始码不是标准码，保持不变。
 */
export { G6_GROSS_FALLBACK_STANDARD as G6_ACCOUNT_CODE } from './g6AccountScope'

/** Excel 编制说明：变动比例超过 30% 需分析 */
export const G6_CHANGE_RATE_THRESHOLD = 0.3

export type G6AdjSection =
  | 'fv'
  | 'cost'
  | 'interest'
  | 'book'
  | 'impairment'
  | 'carrying'

export type G6AdjRowKind =
  | 'section_header'
  | 'subsection_header'
  | 'leaf'
  | 'subtotal'
  | 'one_year_deduct'
  | 'section_net'
  | 'footer'

export interface G6AdjRowDef {
  rowKey: string
  label: string
  kind: G6AdjRowKind
  section?: G6AdjSection
  indent?: number
  /** 可手工录入（未审/调整/原因） */
  editable?: boolean
}

/** 摊余成本子层：单项 + 组合 + 小计 + 一年内到期 + 层小计 */
function amortizedBody(
  section: Exclude<G6AdjSection, 'fv'>,
  subsectionLabel: string,
  netLabel: string,
  opts: { editableLeaves: boolean; editableOneYear: boolean },
): G6AdjRowDef[] {
  return [
    {
      rowKey: `${section}__subheader`,
      label: subsectionLabel,
      kind: 'subsection_header',
      section,
      indent: 0,
    },
    {
      rowKey: `${section}-individual`,
      label: '单项计提坏账准备',
      kind: 'leaf',
      section,
      indent: 1,
      editable: opts.editableLeaves,
    },
    {
      rowKey: `${section}-portfolio`,
      label: '按组合计提坏账准备',
      kind: 'leaf',
      section,
      indent: 1,
      editable: opts.editableLeaves,
    },
    { rowKey: `${section}__subtotal`, label: '小计', kind: 'subtotal', section, indent: 0 },
    {
      rowKey: `${section}__one-year`,
      label: '减：一年内到期的部分',
      kind: 'one_year_deduct',
      section,
      indent: 0,
      editable: opts.editableOneYear,
    },
    { rowKey: `${section}__net`, label: netLabel, kind: 'section_net', section, indent: 0 },
  ]
}

export const G6_ADJUDICATION_ITEMS: G6AdjRowDef[] = [
  // ═══ 一、公允价值 ═══
  { rowKey: 'fv__header', label: '一、公允价值', kind: 'section_header', section: 'fv', indent: 0 },
  {
    rowKey: 'fv-item-1',
    label: '投资项目1',
    kind: 'leaf',
    section: 'fv',
    indent: 1,
    editable: true,
  },
  {
    rowKey: 'fv-item-2',
    label: '投资项目2',
    kind: 'leaf',
    section: 'fv',
    indent: 1,
    editable: true,
  },
  {
    rowKey: 'fv-item-3',
    label: '投资项目3',
    kind: 'leaf',
    section: 'fv',
    indent: 1,
    editable: true,
  },
  {
    rowKey: 'fv-item-4',
    label: '投资项目4',
    kind: 'leaf',
    section: 'fv',
    indent: 1,
    editable: true,
  },
  { rowKey: 'fv__subtotal', label: '小计', kind: 'subtotal', section: 'fv', indent: 0 },
  {
    rowKey: 'fv__one-year',
    label: '减：一年内到期的部分',
    kind: 'one_year_deduct',
    section: 'fv',
    indent: 0,
    editable: true,
  },
  {
    rowKey: 'fv__net',
    label: '其他债权投资公允价值合计',
    kind: 'section_net',
    section: 'fv',
    indent: 0,
  },

  // ═══ 二、摊余成本 ═══
  {
    rowKey: 'amortized__header',
    label: '二、摊余成本',
    kind: 'section_header',
    indent: 0,
  },
  ...amortizedBody('cost', '（一）投资成本', '投资成本小计', {
    editableLeaves: true,
    editableOneYear: true,
  }),
  ...amortizedBody('interest', '（二）利息调整（贷方余额填负数）', '利息调整小计', {
    editableLeaves: true,
    editableOneYear: true,
  }),
  // 账面余额 = 成本 + 利息（公式，不可手工改叶子）
  ...amortizedBody('book', '（三）账面余额', '账面余额小计', {
    editableLeaves: false,
    editableOneYear: false,
  }),
  ...amortizedBody('impairment', '（四）减值准备（正数填列）', '减值准备小计', {
    editableLeaves: true,
    editableOneYear: true,
  }),
  // 账面价值 = 账面余额 − 减值（公式）
  ...amortizedBody(
    'carrying',
    '（五）账面价值/摊余成本（账面余额扣除累计计提的损失准备）',
    '其他债权投资账面价值合计',
    { editableLeaves: false, editableOneYear: false },
  ),

  // ═══ 勾稽 ═══
  { rowKey: 'footer-tb', label: '试算平衡表数', kind: 'footer', indent: 0, editable: true },
  { rowKey: 'footer-variance', label: '差异数', kind: 'footer', indent: 0 },
]

export interface G6AdjStoredCell {
  openingUnadjusted?: number
  openingAdjustment?: number
  closingUnadjusted?: number
  closingAdjustment?: number
  reasonAnalysis?: string
  /** 公允价值明细行项目名（可改） */
  itemLabel?: string
}

export type G6AdjRowStore = Record<string, G6AdjStoredCell>

/** 默认回写至投资成本·按组合 */
export const G6_ADJ_WRITEBACK_ROW_KEY = 'cost-portfolio'

export function parseG6AdjStore(raw: string | null | undefined): G6AdjRowStore {
  if (!raw) return {}
  try {
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return migrateLegacyStore(parsed as Record<string, any>)
    }
    if (Array.isArray(parsed)) {
      return migrateLegacyArray(parsed)
    }
  } catch {
    /* ignore */
  }
  return {}
}

function migrateCell(raw: Record<string, any>): G6AdjStoredCell {
  const openingAJE = Number(raw.openingAJE ?? 0) || 0
  const openingRJE = Number(raw.openingRJE ?? 0) || 0
  const closingAJE = Number(raw.closingAJE ?? 0) || 0
  const closingRJE = Number(raw.closingRJE ?? 0) || 0
  const openingAdjustment =
    raw.openingAdjustment != null
      ? Number(raw.openingAdjustment) || 0
      : openingAJE + openingRJE
  const closingAdjustment =
    raw.closingAdjustment != null
      ? Number(raw.closingAdjustment) || 0
      : closingAJE + closingRJE

  return {
    openingUnadjusted: Number(raw.openingUnadjusted ?? raw.opening_unadjusted ?? 0) || 0,
    openingAdjustment,
    closingUnadjusted: Number(raw.closingUnadjusted ?? raw.closing_unadjusted ?? 0) || 0,
    closingAdjustment,
    reasonAnalysis: String(raw.reasonAnalysis ?? raw.reason_analysis ?? ''),
    itemLabel: raw.itemLabel ?? raw.item ?? raw.name,
  }
}

/** 兼容旧 8 层分组数组：cost / interestAdj / accrued / fvChange / impairment / reclass */
function migrateLegacyArray(arr: any[]): G6AdjRowStore {
  const store: G6AdjRowStore = {}
  for (const item of arr) {
    if (!item?.rowKey && !item?.item) continue
    const key = String(item.rowKey || item.item)
    store[key] = migrateCell(item)
  }
  return store
}

function migrateLegacyStore(obj: Record<string, any>): G6AdjRowStore {
  const store: G6AdjRowStore = {}

  // 旧版按 section 数组存：{ cost: [...], interestAdj: [...], ... }
  const sectionMap: Record<string, string> = {
    cost: 'cost',
    interestAdj: 'interest',
    interest: 'interest',
    accrued: 'cost', // 应计利息并入成本层提示，金额落到 portfolio 追加行不再单独建模
    fvChange: 'fv',
    fv: 'fv',
    impairment: 'impairment',
    reclass: 'fv', // 一年内到期重分类 → 公允价值一年内到期
  }

  for (const [k, v] of Object.entries(obj)) {
    if (Array.isArray(v) && sectionMap[k]) {
      const section = sectionMap[k]
      v.forEach((row: any, i: number) => {
        if (section === 'fv') {
          const rowKey = i < 4 ? `fv-item-${i + 1}` : `fv-item-${i + 1}`
          store[rowKey] = migrateCell({ ...row, itemLabel: row.item || row.name })
        } else if (k === 'reclass' && i === 0) {
          store['fv__one-year'] = migrateCell(row)
        } else {
          const leaf = i === 0 ? `${section}-individual` : `${section}-portfolio`
          if (!store[leaf] || i < 2) store[leaf] = migrateCell(row)
        }
      })
      continue
    }
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      store[k] = migrateCell(v as Record<string, any>)
    }
  }
  return store
}

export function applyG6AdjustmentWriteback(
  store: G6AdjRowStore,
  netAdjustment: number,
  rowKey: string = G6_ADJ_WRITEBACK_ROW_KEY,
): G6AdjRowStore {
  const prev = store[rowKey] ?? {}
  const net = Number(netAdjustment)
  const safeNet = Number.isFinite(net) ? net : 0
  const note = '来自 G6-4 调整分录确认回写'
  const prevReason = String(prev.reasonAnalysis || '')
  return {
    ...store,
    [rowKey]: {
      ...prev,
      closingAdjustment: safeNet,
      reasonAnalysis: prevReason.includes('G6-4')
        ? prevReason
        : [prevReason, note].filter(Boolean).join('；'),
    },
  }
}

/**
 * 分离回写：1503 原值类 → 成本组合行；减值类 → 减值组合行
 */
export function applyG6SplitAdjustmentWriteback(
  store: G6AdjRowStore,
  costNet: number,
  impairmentNet: number,
): G6AdjRowStore {
  let next = applyG6AdjustmentWriteback(store, costNet, 'cost-portfolio')
  next = applyG6AdjustmentWriteback(next, impairmentNet, 'impairment-portfolio')
  return next
}

/**
 * 多维回写：成本 / 利息调整 / 减值 / 公允价值 → 各组合（或 FV 叶子）行
 */
export function applyG6MultiAdjustmentWriteback(
  store: G6AdjRowStore,
  nets: { cost?: number; interest?: number; impairment?: number; fv?: number },
): G6AdjRowStore {
  let next = store
  if (nets.cost != null) {
    next = applyG6AdjustmentWriteback(next, nets.cost, 'cost-portfolio')
  }
  if (nets.interest != null) {
    next = applyG6AdjustmentWriteback(next, nets.interest, 'interest-portfolio')
  }
  if (nets.impairment != null) {
    next = applyG6AdjustmentWriteback(next, nets.impairment, 'impairment-portfolio')
  }
  if (nets.fv != null) {
    next = applyG6AdjustmentWriteback(next, nets.fv, 'fv-item-1')
  }
  return next
}

export function listG6WritebackAllocTargets(): Array<{ rowKey: string; label: string }> {
  return [
    { rowKey: 'cost-individual', label: '投资成本 · 单项' },
    { rowKey: 'cost-portfolio', label: '投资成本 · 按组合' },
    { rowKey: 'interest-individual', label: '利息调整 · 单项' },
    { rowKey: 'interest-portfolio', label: '利息调整 · 按组合' },
    { rowKey: 'impairment-individual', label: '减值 · 单项' },
    { rowKey: 'impairment-portfolio', label: '减值 · 按组合' },
    { rowKey: 'fv-item-1', label: '公允价值 · 投资项目1' },
  ]
}

/** 公允价值叶子行 keys */
export const G6_FV_LEAF_KEYS = ['fv-item-1', 'fv-item-2', 'fv-item-3', 'fv-item-4'] as const

/** 摊余成本可录入叶子 section */
export const G6_EDITABLE_AMORT_SECTIONS: G6AdjSection[] = ['cost', 'interest', 'impairment']
