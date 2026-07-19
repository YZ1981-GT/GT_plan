/**
 * G2-1 审定表行定义 — 对齐致同 Excel 模板：
 * （一）应收利息原值 / （二）坏账准备 / （三）净值 = 原值 − 坏账
 * × 单项计提 / 按组合计提
 */

export const G2_ACCOUNT_CODE = '1132'

/** |变动率| 超过该阈值时差异分析必填 */
export const G2_CHANGE_RATE_THRESHOLD = 0.3

export type G2AdjSection = 'gross' | 'provision' | 'net'

export type G2AdjMethod = 'individual' | 'collective'

export type G2AdjRowKind =
  | 'section_header'
  | 'leaf'
  | 'section_subtotal'
  | 'net_row'
  | 'footer'

export interface G2AdjRowDef {
  rowKey: string
  label: string
  kind: G2AdjRowKind
  section?: G2AdjSection
  methodKey?: G2AdjMethod
  indent?: number
  editable?: boolean
}

export const G2_ADJ_METHODS: { key: G2AdjMethod; label: string }[] = [
  { key: 'individual', label: '其中：单项计提坏账准备' },
  { key: 'collective', label: '按组合计提坏账准备' },
]

export const G2_ADJ_SECTIONS: { key: G2AdjSection; label: string }[] = [
  { key: 'gross', label: '一、应收利息原值' },
  { key: 'provision', label: '二、应收利息坏账准备' },
  { key: 'net', label: '三、应收利息净值' },
]

function buildSectionRows(section: 'gross' | 'provision', sectionLabel: string): G2AdjRowDef[] {
  const rows: G2AdjRowDef[] = [
    {
      rowKey: `${section}__header`,
      label: sectionLabel,
      kind: 'section_header',
      section,
      indent: 0,
    },
  ]
  for (const method of G2_ADJ_METHODS) {
    rows.push({
      rowKey: `${section}-${method.key}`,
      label: method.label,
      kind: 'leaf',
      section,
      methodKey: method.key,
      indent: 1,
      editable: true,
    })
  }
  rows.push({
    rowKey: `${section}__subtotal`,
    label: '小计',
    kind: 'section_subtotal',
    section,
    indent: 0,
  })
  return rows
}

export const G2_ADJUDICATION_BODY: G2AdjRowDef[] = [
  ...buildSectionRows('gross', '一、应收利息原值'),
  ...buildSectionRows('provision', '二、应收利息坏账准备'),
  {
    rowKey: 'net__row',
    label: '三、应收利息净值',
    kind: 'net_row',
    section: 'net',
    indent: 0,
  },
]

export const G2_ADJUDICATION_FOOTER: G2AdjRowDef[] = [
  {
    rowKey: 'footer-total',
    label: '合计',
    kind: 'footer',
    indent: 0,
  },
]

export const G2_ADJUDICATION_ITEMS: G2AdjRowDef[] = [
  ...G2_ADJUDICATION_BODY,
  ...G2_ADJUDICATION_FOOTER,
]

/** 持久化字段（仅 leaf 行） */
export interface G2AdjStoredCell {
  openingUnadjusted?: number
  openingAdjustment?: number
  closingUnadjusted?: number
  closingAdjustment?: number
  reasonAnalysis?: string
}

export type G2AdjRowStore = Record<string, G2AdjStoredCell>

const LEGACY_ROW_KEY_MAP: Record<string, string> = {
  'bond-interest': 'gross-collective',
  'other-bond-interest': 'gross-individual',
  'deposit-interest': 'provision-collective',
  other: 'provision-individual',
}

/** 解析 keyed store；兼容旧版数组格式（投资类型行） */
export function parseG2AdjStore(raw: string | null | undefined): G2AdjRowStore {
  if (!raw) return {}
  try {
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as G2AdjRowStore
    }
    if (Array.isArray(parsed)) {
      const store: G2AdjRowStore = {}
      for (const row of parsed) {
        const legacyKey = String(row?.rowKey || '')
        const mapped = LEGACY_ROW_KEY_MAP[legacyKey]
        if (!mapped) continue
        const openingAdj =
          Number(row.openingAJE || 0) + Number(row.openingRJE || 0)
        const closingAdj =
          Number(row.closingAJE || 0) + Number(row.closingRJE || 0)
        // 旧版期末未审由发生额推导；迁移时尽量保留期末审定痕迹
        const openingUnadjusted = Number(row.openingUnadjusted || 0)
        const openingAdjusted = openingUnadjusted + openingAdj
        const closingUnadjusted =
          openingAdjusted + Number(row.periodDebit || 0) - Number(row.periodCredit || 0)
        store[mapped] = {
          openingUnadjusted,
          openingAdjustment: openingAdj,
          closingUnadjusted,
          closingAdjustment: closingAdj,
          reasonAnalysis: String(row.indexRef || ''),
        }
      }
      return store
    }
  } catch {
    /* ignore */
  }
  return {}
}

export function leafKeysForSection(section: 'gross' | 'provision'): string[] {
  return G2_ADJ_METHODS.map((m) => `${section}-${m.key}`)
}

/** G2-4 确认调整默认回写行：原值 · 按组合计提 */
export const G2_ADJ_WRITEBACK_ROW_KEY = 'gross-collective'

/** 将净调整写入 G2-1 行存储（期末账项调整；资产借−贷为正） */
export function applyG2AdjustmentWriteback(
  store: G2AdjRowStore,
  netAdjustment: number,
  rowKey: string = G2_ADJ_WRITEBACK_ROW_KEY,
): G2AdjRowStore {
  const prev = store[rowKey] ?? {}
  const net = Number(netAdjustment)
  const safeNet = Number.isFinite(net) ? net : 0
  const note = '来自 G2-4 调整分录确认回写'
  const prevReason = String(prev.reasonAnalysis || '')
  return {
    ...store,
    [rowKey]: {
      ...prev,
      closingAdjustment: safeNet,
      reasonAnalysis: prevReason.includes('G2-4')
        ? prevReason
        : [prevReason, note].filter(Boolean).join('；'),
    },
  }
}
