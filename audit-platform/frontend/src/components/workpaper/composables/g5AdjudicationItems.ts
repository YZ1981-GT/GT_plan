/**
 * G5-1 审定表行定义 — 对齐致同 Excel「长期应收款审定表 G5-1」：
 *
 * （一）长期应收款余额
 *   其中：单项计提 / 按组合（业务类型·客户类型）/ 小计 / 减：1年内到期 / 一年以上
 * （二）坏账准备 — 同构
 * （三）净额 = 一年以上余额 − 一年以上坏账
 * 试算平衡表数 / 差异数
 *
 * 列：期初·期末 × 未审数 / 账项调整 / 重分类调整 / 审定数；变动额·变动率；原因分析
 * 审定 = 未审 + 账项调整 + 重分类调整
 */

export { G5_ACCOUNT_CODE, G5_ACCOUNT_NAME } from './g5Constants'

/** |变动率| 超过该阈值时原因分析必填（对齐 Excel「超过30%」） */
export const G5_CHANGE_RATE_THRESHOLD = 0.3

export type G5AdjSection = 'gross' | 'provision' | 'net' | 'tb'

export type G5AdjMethod = 'individual' | 'collective-business' | 'collective-customer'

export type G5AdjRowKind =
  | 'section_header'
  | 'group_header'
  | 'leaf'
  | 'section_subtotal'
  | 'deduction'
  | 'reportable'
  | 'net_row'
  | 'tb_amount'
  | 'tb_diff'

export interface G5AdjRowDef {
  rowKey: string
  label: string
  kind: G5AdjRowKind
  section?: G5AdjSection
  methodKey?: G5AdjMethod
  indent?: number
  editable?: boolean
}

export const G5_ADJ_WRITEBACK_ROW_KEY = 'gross-collective-business'

function buildBalanceSection(
  section: 'gross' | 'provision',
  headerLabel: string,
): G5AdjRowDef[] {
  return [
    {
      rowKey: `${section}__header`,
      label: headerLabel,
      kind: 'section_header',
      section,
      indent: 0,
    },
    {
      rowKey: `${section}-individual`,
      label: '其中：单项计提坏账准备的长期应收款',
      kind: 'leaf',
      section,
      methodKey: 'individual',
      indent: 1,
      editable: true,
    },
    {
      rowKey: `${section}-collective__header`,
      label: '按组合计提坏账准备的长期应收款',
      kind: 'group_header',
      section,
      indent: 1,
    },
    {
      rowKey: `${section}-collective-business`,
      label: '业务类型组合',
      kind: 'leaf',
      section,
      methodKey: 'collective-business',
      indent: 2,
      editable: true,
    },
    {
      rowKey: `${section}-collective-customer`,
      label: '客户类型组合',
      kind: 'leaf',
      section,
      methodKey: 'collective-customer',
      indent: 2,
      editable: true,
    },
    {
      rowKey: `${section}__subtotal`,
      label: '小计',
      kind: 'section_subtotal',
      section,
      indent: 0,
    },
    {
      rowKey: `${section}-one-year`,
      label: '减：1年内到期的长期应收款',
      kind: 'deduction',
      section,
      indent: 1,
      editable: true,
    },
    {
      rowKey: `${section}-reportable`,
      label: section === 'gross' ? '一年以上余额（报表列示）' : '一年以上坏账准备（报表列示）',
      kind: 'reportable',
      section,
      indent: 0,
    },
  ]
}

export const G5_ADJUDICATION_BODY: G5AdjRowDef[] = [
  ...buildBalanceSection('gross', '（一）长期应收款余额'),
  ...buildBalanceSection('provision', '（二）长期应收款坏账准备'),
  {
    rowKey: 'net__row',
    label: '（三）长期应收款净额',
    kind: 'net_row',
    section: 'net',
    indent: 0,
  },
]

export const G5_ADJUDICATION_FOOTER: G5AdjRowDef[] = [
  {
    rowKey: 'tb-amount',
    label: '试算平衡表数',
    kind: 'tb_amount',
    section: 'tb',
    indent: 0,
    editable: true,
  },
  {
    rowKey: 'tb-diff',
    label: '差异数',
    kind: 'tb_diff',
    section: 'tb',
    indent: 0,
  },
]

export const G5_ADJUDICATION_ITEMS: G5AdjRowDef[] = [
  ...G5_ADJUDICATION_BODY,
  ...G5_ADJUDICATION_FOOTER,
]

/** 参与小计的 leaf keys（不含一年内扣除） */
export function leafKeysForSection(section: 'gross' | 'provision'): string[] {
  return [
    `${section}-individual`,
    `${section}-collective-business`,
    `${section}-collective-customer`,
  ]
}

export interface G5AdjStoredCell {
  openingUnadjusted?: number
  openingAJE?: number
  openingRJE?: number
  closingUnadjusted?: number
  closingAJE?: number
  closingRJE?: number
  reasonAnalysis?: string
}

export type G5AdjRowStore = Record<string, G5AdjStoredCell>

/** 旧版五层业务类型行 → 新结构映射 */
const LEGACY_ROW_KEY_MAP: Record<string, string> = {
  'finance-lease': 'gross-collective-business',
  installment: 'gross-collective-business',
  other: 'gross-collective-customer',
  'gross-total': 'gross-collective-business',
  'provision-total': 'provision-collective-business',
  'one-year': 'gross-one-year',
  'net-total': 'net__row',
  'report-amount': 'gross-reportable',
}

export function parseG5AdjStore(raw: string | null | undefined): G5AdjRowStore {
  if (!raw) return {}
  try {
    const parsed = JSON.parse(raw)
    // 新版 keyed：{ version, rows: { id: cell } }
    if (parsed && typeof parsed === 'object' && parsed.rows && typeof parsed.rows === 'object') {
      const out: G5AdjRowStore = {}
      for (const [k, v] of Object.entries(parsed.rows as Record<string, any>)) {
        const key = LEGACY_ROW_KEY_MAP[k] || k
        const prev = out[key] || {}
        out[key] = mergeCell(prev, v as G5AdjStoredCell)
      }
      // writeback 镜像
      if (parsed.writeback?.['gross-total'] || parsed.closingAJE != null) {
        const wb = parsed.writeback?.['gross-total'] || {}
        const target = out[G5_ADJ_WRITEBACK_ROW_KEY] || {}
        out[G5_ADJ_WRITEBACK_ROW_KEY] = {
          ...target,
          closingAJE: wb.closingAJE ?? parsed.closingAJE ?? target.closingAJE,
          closingRJE: wb.closingRJE ?? parsed.closingRJE ?? target.closingRJE,
        }
      }
      return out
    }
    // 扁平 keyed store
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      const out: G5AdjRowStore = {}
      for (const [k, v] of Object.entries(parsed as Record<string, any>)) {
        if (k === 'version' || k === 'writeback' || k === 'closingAJE' || k === 'closingRJE') continue
        if (v && typeof v === 'object') {
          const key = LEGACY_ROW_KEY_MAP[k] || k
          out[key] = mergeCell(out[key] || {}, v as G5AdjStoredCell)
        }
      }
      return out
    }
  } catch {
    /* ignore */
  }
  return {}
}

function mergeCell(a: G5AdjStoredCell, b: G5AdjStoredCell): G5AdjStoredCell {
  return {
    openingUnadjusted: numOr(b.openingUnadjusted, a.openingUnadjusted),
    openingAJE: numOr(b.openingAJE, a.openingAJE),
    openingRJE: numOr(b.openingRJE, a.openingRJE),
    closingUnadjusted: numOr(b.closingUnadjusted, a.closingUnadjusted),
    closingAJE: numOr(b.closingAJE, a.closingAJE),
    closingRJE: numOr(b.closingRJE, a.closingRJE),
    reasonAnalysis: b.reasonAnalysis ?? a.reasonAnalysis ?? '',
  }
}

function numOr(v: unknown, fallback?: number): number | undefined {
  if (v == null || v === '') return fallback
  const n = Number(v)
  return Number.isFinite(n) ? n : fallback
}

export function applyG5AdjustmentWriteback(
  store: G5AdjRowStore,
  netAje: number,
  netRje: number,
  rowKey = G5_ADJ_WRITEBACK_ROW_KEY,
): G5AdjRowStore {
  const prev = store[rowKey] || {}
  return {
    ...store,
    [rowKey]: {
      ...prev,
      closingAJE: netAje,
      closingRJE: netRje,
    },
  }
}
