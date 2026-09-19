/**
 * G1-1 审定表行定义 — 对齐 Excel 模板：
 * (一)投资成本 / (二)累计公允价值变动 / (三)账面余额（公允价值）
 * × 交易性 / 划分为FVTPL / 指定为FVTPL
 * × 债务/权益/衍生/理财/结构性存款/基金/其他
 */

import { G1_GROSS_FALLBACK_STANDARD } from './g1AccountScope'

export const G1_ACCOUNT_CODE = G1_GROSS_FALLBACK_STANDARD

/** |变动率| 超过该阈值时原因分析必填（模板分析性复核口径） */
export const G1_CHANGE_RATE_THRESHOLD = 0.3

export type G1AdjSection = 'cost' | 'fv' | 'carrying'
export type G1AdjClass = 'trading' | 'classified' | 'designated'
export type G1AdjAsset =
  | 'debt'
  | 'equity'
  | 'derivative'
  | 'wealth'
  | 'structured'
  | 'fund'
  | 'other'

export type G1AdjRowKind =
  | 'section_header'
  | 'class_header'
  | 'leaf'
  | 'section_subtotal'
  | 'footer'

export interface G1AdjRowDef {
  rowKey: string
  label: string
  kind: G1AdjRowKind
  section?: G1AdjSection
  classKey?: G1AdjClass
  assetKey?: G1AdjAsset
  /** 缩进层级（展示） */
  indent?: number
  /** 可编辑未审/调整（leaf 或 footer 特殊行） */
  editable?: boolean
}

export const G1_ADJ_ASSETS: { key: G1AdjAsset; label: string }[] = [
  { key: 'debt', label: '债务工具投资' },
  { key: 'equity', label: '权益工具投资' },
  { key: 'derivative', label: '衍生金融资产' },
  { key: 'wealth', label: '理财产品' },
  { key: 'structured', label: '结构性存款' },
  { key: 'fund', label: '基金' },
  { key: 'other', label: '其他' },
]

export const G1_ADJ_CLASSES: { key: G1AdjClass; label: string }[] = [
  { key: 'trading', label: '交易性金融资产' },
  {
    key: 'classified',
    label: '划分为以公允价值计量且其变动计入当期损益的金融资产',
  },
  {
    key: 'designated',
    label: '指定为以公允价值计量且其变动计入当期损益的金融资产',
  },
]

export const G1_ADJ_SECTIONS: { key: G1AdjSection; label: string }[] = [
  { key: 'cost', label: '（一）投资成本' },
  { key: 'fv', label: '（二）累计公允价值变动' },
  { key: 'carrying', label: '（三）账面余额（公允价值）' },
]

function buildSectionRows(section: G1AdjSection, sectionLabel: string): G1AdjRowDef[] {
  const rows: G1AdjRowDef[] = [
    {
      rowKey: `${section}__header`,
      label: sectionLabel,
      kind: 'section_header',
      section,
      indent: 0,
    },
  ]
  for (const cls of G1_ADJ_CLASSES) {
    rows.push({
      rowKey: `${section}-${cls.key}__class`,
      label: cls.label,
      kind: 'class_header',
      section,
      classKey: cls.key,
      indent: 1,
    })
    for (const asset of G1_ADJ_ASSETS) {
      rows.push({
        rowKey: `${section}-${cls.key}-${asset.key}`,
        label: asset.label,
        kind: 'leaf',
        section,
        classKey: cls.key,
        assetKey: asset.key,
        indent: 2,
        editable: section !== 'carrying',
      })
    }
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

/** 主表行（含三大部分） */
export const G1_ADJUDICATION_BODY: G1AdjRowDef[] = [
  ...buildSectionRows('cost', '（一）投资成本'),
  ...buildSectionRows('fv', '（二）累计公允价值变动'),
  ...buildSectionRows('carrying', '（三）账面余额（公允价值）'),
]

/** 表尾行 */
export const G1_ADJUDICATION_FOOTER: G1AdjRowDef[] = [
  {
    rowKey: 'footer-over-one-year',
    label: '减：超过一年到期的部分',
    kind: 'footer',
    indent: 0,
    editable: true,
  },
  {
    rowKey: 'footer-book-total',
    label: '账面余额（公允价值）合计',
    kind: 'footer',
    indent: 0,
  },
]

export const G1_ADJUDICATION_ITEMS: G1AdjRowDef[] = [
  ...G1_ADJUDICATION_BODY,
  ...G1_ADJUDICATION_FOOTER,
]

/** 持久化字段（leaf / over-one-year） */
export interface G1AdjStoredCell {
  openingUnadjusted?: number
  openingAdjustment?: number
  closingUnadjusted?: number
  closingAdjustment?: number
  reasonAnalysis?: string
}

export type G1AdjRowStore = Record<string, G1AdjStoredCell>

export function parseG1AdjStore(raw: string | null | undefined): G1AdjRowStore {
  if (!raw) return {}
  try {
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as G1AdjRowStore
    }
  } catch {
    /* ignore */
  }
  return {}
}

/** G1-3 确认调整默认回写行：投资成本 · 交易性 · 其他 */
export const G1_ADJ_WRITEBACK_ROW_KEY = 'cost-trading-other'

/** 将净调整写入 G1-1 行存储（期末账项调整） */
export function applyG1AdjustmentWriteback(
  store: G1AdjRowStore,
  netAdjustment: number,
  rowKey: string = G1_ADJ_WRITEBACK_ROW_KEY,
): G1AdjRowStore {
  const prev = store[rowKey] ?? {}
  const net = Number(netAdjustment)
  const safeNet = Number.isFinite(net) ? net : 0
  const note = '来自 G1-3 调整分录确认回写'
  const prevReason = String(prev.reasonAnalysis || '')
  return {
    ...store,
    [rowKey]: {
      ...prev,
      closingAdjustment: safeNet,
      reasonAnalysis: prevReason.includes('G1-3')
        ? prevReason
        : [prevReason, note].filter(Boolean).join('；'),
    },
  }
}

/** 可选分摊目标：投资成本 × 交易性 × 各品种 */
export function listG1WritebackAllocTargets(): Array<{ rowKey: string; label: string }> {
  return G1_ADJ_ASSETS.map((a) => ({
    rowKey: `cost-trading-${a.key}`,
    label: `投资成本 · 交易性 · ${a.label}`,
  }))
}

/**
 * 将已回写净额从默认行清零并按金额分摊到多个叶子行。
 * allocations 合计应等于 netAdjustment（容差 0.01）。
 */
export function allocateG1WritebackAcrossRows(
  store: G1AdjRowStore,
  netAdjustment: number,
  allocations: Array<{ rowKey: string; amount: number }>,
  options?: { clearDefault?: boolean; defaultRowKey?: string },
): G1AdjRowStore {
  const clearDefault = options?.clearDefault !== false
  const defaultKey = options?.defaultRowKey || G1_ADJ_WRITEBACK_ROW_KEY
  const net = Number.isFinite(Number(netAdjustment)) ? Number(netAdjustment) : 0
  let next: G1AdjRowStore = { ...store }

  if (clearDefault && next[defaultKey]) {
    const prev = next[defaultKey]
    next = {
      ...next,
      [defaultKey]: {
        ...prev,
        closingAdjustment: 0,
        reasonAnalysis: String(prev.reasonAnalysis || '')
          .replace(/；?来自 G1-3 调整分录确认回写/g, '')
          .trim(),
      },
    }
  }

  const note = '来自 G1-3 回写后手工/引导分摊'
  for (const a of allocations) {
    const amt = Number(a.amount)
    if (!a.rowKey || !Number.isFinite(amt) || Math.abs(amt) < 1e-9) continue
    const prev = next[a.rowKey] ?? {}
    const prevReason = String(prev.reasonAnalysis || '')
    next = {
      ...next,
      [a.rowKey]: {
        ...prev,
        closingAdjustment: amt,
        reasonAnalysis: prevReason.includes('分摊')
          ? prevReason
          : [prevReason, note].filter(Boolean).join('；'),
      },
    }
  }

  // 若未把净额分完，余数留在默认行，避免丢失
  const allocated = allocations.reduce((s, a) => s + (Number(a.amount) || 0), 0)
  const residual = Math.round((net - allocated) * 100) / 100
  if (Math.abs(residual) >= 0.01) {
    const prev = next[defaultKey] ?? {}
    next = {
      ...next,
      [defaultKey]: {
        ...prev,
        closingAdjustment: residual,
        reasonAnalysis: [String(prev.reasonAnalysis || ''), '分摊余数'].filter(Boolean).join('；'),
      },
    }
  }

  return next
}

export function leafKeysForClass(section: G1AdjSection, classKey: G1AdjClass): string[] {
  return G1_ADJ_ASSETS.map((a) => `${section}-${classKey}-${a.key}`)
}

export function leafKeysForSection(section: G1AdjSection): string[] {
  return G1_ADJ_CLASSES.flatMap((c) => leafKeysForClass(section, c.key))
}
