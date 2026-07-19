/**
 * G4-1 审定表行定义 — 对齐 Excel 模板《审定表G4-1》：
 * 列：期初/期末 ×（未审数 | 账项调整 | 审定数）+ 变动额/变动率 + 原因分析
 * 行：一、原值 → 二、减值准备 → 三、净值 → 试算平衡表数/差异数
 *
 * Template: backend/wp_templates/G/G4 债权投资.xlsx
 */

export const G4_ACCOUNT_CODE = '1501'

/** Excel 编制说明：变动比例超过 30% 需分析 */
export const G4_CHANGE_RATE_THRESHOLD = 0.3

export type G4AdjSection = 'original' | 'impairment' | 'net'

export type G4AdjRowKind =
  | 'section_header'
  | 'leaf'
  | 'subtotal'
  | 'one_year_deduct'
  | 'section_net'
  | 'footer'

export interface G4AdjRowDef {
  rowKey: string
  label: string
  kind: G4AdjRowKind
  section?: G4AdjSection
  indent?: number
  editable?: boolean
}

function sectionBody(section: G4AdjSection, header: string, netLabel: string): G4AdjRowDef[] {
  return [
    { rowKey: `${section}__header`, label: header, kind: 'section_header', section, indent: 0 },
    {
      rowKey: `${section}-individual`,
      label: '单项计提坏账准备',
      kind: 'leaf',
      section,
      indent: 1,
      editable: section !== 'net',
    },
    {
      rowKey: `${section}-portfolio`,
      label: '按组合计提坏账准备',
      kind: 'leaf',
      section,
      indent: 1,
      editable: section !== 'net',
    },
    { rowKey: `${section}__subtotal`, label: '小计', kind: 'subtotal', section, indent: 0 },
    {
      rowKey: `${section}__one-year`,
      label: '减：一年内到期的部分',
      kind: 'one_year_deduct',
      section,
      indent: 0,
      editable: true,
    },
    { rowKey: `${section}__net`, label: netLabel, kind: 'section_net', section, indent: 0 },
  ]
}

export const G4_ADJUDICATION_ITEMS: G4AdjRowDef[] = [
  ...sectionBody('original', '一、债权投资原值', '债权投资原值小计'),
  ...sectionBody('impairment', '二、债权投资减值准备', '债权投资减值准备小计'),
  ...sectionBody('net', '三、债权投资净值', '债权投资净值合计'),
  {
    rowKey: 'footer-tb',
    label: '试算平衡表数',
    kind: 'footer',
    indent: 0,
    editable: true,
  },
  {
    rowKey: 'footer-variance',
    label: '差异数',
    kind: 'footer',
    indent: 0,
  },
]

export interface G4AdjStoredCell {
  openingUnadjusted?: number
  openingAdjustment?: number
  closingUnadjusted?: number
  closingAdjustment?: number
  reasonAnalysis?: string
}

export type G4AdjRowStore = Record<string, G4AdjStoredCell>

/** 默认回写至原值·按组合计提坏账准备 */
export const G4_ADJ_WRITEBACK_ROW_KEY = 'original-portfolio'

export function parseG4AdjStore(raw: string | null | undefined): G4AdjRowStore {
  if (!raw) return {}
  try {
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return migrateLegacyStore(parsed as Record<string, any>)
    }
    // 兼容旧版分组数组：G4-1-adj-groups-*
    if (Array.isArray(parsed)) {
      return migrateLegacyArray(parsed)
    }
  } catch {
    /* ignore */
  }
  return {}
}

/** 将旧 AJE/RJE 字段合并为单一账项调整 */
function migrateCell(raw: Record<string, any>): G4AdjStoredCell {
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

  // 旧版期末未审由借方贷方推导；新模型直接存期末未审
  let closingUnadjusted = Number(raw.closingUnadjusted ?? NaN)
  if (!Number.isFinite(closingUnadjusted)) {
    const openingUnadjusted = Number(raw.openingUnadjusted ?? 0) || 0
    const openingAdj = openingAdjustment
    const openingAudited = openingUnadjusted + openingAdj
    const debit = Number(raw.periodDebit ?? 0) || 0
    const credit = Number(raw.periodCredit ?? 0) || 0
    closingUnadjusted = openingAudited + debit - credit
  }

  return {
    openingUnadjusted: Number(raw.openingUnadjusted ?? 0) || 0,
    openingAdjustment,
    closingUnadjusted,
    closingAdjustment,
    reasonAnalysis: String(raw.reasonAnalysis ?? ''),
  }
}

function migrateLegacyArray(arr: any[]): G4AdjRowStore {
  const store: G4AdjRowStore = {}
  for (const item of arr) {
    if (!item?.rowKey) continue
    // ov-individual → original-individual
    const key = String(item.rowKey)
      .replace(/^ov-/, 'original-')
      .replace(/^imp-/, 'impairment-')
    store[key] = migrateCell(item)
  }
  return store
}

function migrateLegacyStore(obj: Record<string, any>): G4AdjRowStore {
  const store: G4AdjRowStore = {}
  for (const [k, v] of Object.entries(obj)) {
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      store[k] = migrateCell(v as Record<string, any>)
    }
  }
  return store
}

export function applyG4AdjustmentWriteback(
  store: G4AdjRowStore,
  netAdjustment: number,
  rowKey: string = G4_ADJ_WRITEBACK_ROW_KEY,
): G4AdjRowStore {
  const prev = store[rowKey] ?? {}
  const net = Number(netAdjustment)
  const safeNet = Number.isFinite(net) ? net : 0
  const note = '来自 G4-3 调整分录确认回写'
  const prevReason = String(prev.reasonAnalysis || '')
  return {
    ...store,
    [rowKey]: {
      ...prev,
      closingAdjustment: safeNet,
      reasonAnalysis: prevReason.includes('G4-3')
        ? prevReason
        : [prevReason, note].filter(Boolean).join('；'),
    },
  }
}

/**
 * 分离回写：1501* → 原值组合行（借−贷）；1502* → 减值组合行（贷−借 = 准备增加为正）。
 * RJE/报表调整不计入。
 */
export function applyG4SplitAdjustmentWriteback(
  store: G4AdjRowStore,
  originalNet: number,
  impairmentNet: number,
): G4AdjRowStore {
  let next = applyG4AdjustmentWriteback(store, originalNet, 'original-portfolio')
  // 减值准备：贷方增加准备 → closingAdjustment 为正；传入已换算的净额
  next = applyG4AdjustmentWriteback(next, impairmentNet, 'impairment-portfolio')
  return next
}

export function listG4WritebackAllocTargets(): Array<{ rowKey: string; label: string }> {
  return [
    { rowKey: 'original-individual', label: '原值 · 单项计提坏账准备' },
    { rowKey: 'original-portfolio', label: '原值 · 按组合计提坏账准备' },
    { rowKey: 'impairment-individual', label: '减值 · 单项计提坏账准备' },
    { rowKey: 'impairment-portfolio', label: '减值 · 按组合计提坏账准备' },
  ]
}
