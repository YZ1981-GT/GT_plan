/**
 * G9-6 凭证检查 ↔ G9-2/G9-4/G9-5 跨表联动（纯函数）
 */
import { parseNum } from './useG9FormulaEngine'
import { G9_ACCOUNT_CODE } from './g9Constants'
import type { ChecklistResponse } from './useF1FormData'

export const G9_DETAIL_KEY = 'G9-detail-rows'
export const G9_FV_KEY = 'G9-fv-test-rows'
export const G9_L3_KEY = 'G9-l3-rows'

export function matchG9AssetKey(name: string): string {
  return (name || '').trim().toLowerCase()
}

export interface G9DetailOption {
  rowId: string
  assetName: string
  label: string
  classification: string
  fairValueLevel: string
  isRelatedParty: boolean
  impairmentLoss: number
}

export interface G9VoucherLinkHint {
  code:
    | 'no-detail'
    | 'fv-diff'
    | 'fv-level3'
    | 'detail-level3'
    | 'related-party'
    | 'impairment'
    | 'amortised-cost'
  level: 'info' | 'warning' | 'danger'
  text: string
  suggestCheckFairValueFail?: boolean
  suggestCheckImpairmentFail?: boolean
  suggestCheckClassificationFail?: boolean
}

export interface G9VoucherCrossSnapshot {
  details: G9DetailOption[]
  fvByAsset: Map<string, { name: string; diff: number; level: string }>
  l3ByAsset: Map<string, { name: string; variance: number }>
}

/** 联动所需的行最小字段 */
export interface G9VoucherLinkRow {
  source?: string
  assetName?: string
  detailRowId?: string
  isAbnormal: boolean
  forceAbnormal: boolean
  abnormalDesc: string
  checkOriginal: boolean | null
  checkAuthorized: boolean | null
  checkAccounting: boolean | null
  checkClassification: boolean | null
  checkFairValue: boolean | null
  checkImpairment: boolean | null
}

function parseJsonArray(raw: string | null | undefined): Record<string, unknown>[] {
  if (!raw) return []
  try {
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? arr : []
  } catch {
    return []
  }
}

export function buildG9VoucherCrossSnapshot(
  responses: Map<string, ChecklistResponse>,
): G9VoucherCrossSnapshot {
  const detailsRaw = parseJsonArray(responses.get(G9_DETAIL_KEY)?.remark)
  const details: G9DetailOption[] = detailsRaw
    .map((r, i) => {
      const name = String(r.assetName ?? '').trim()
      const rowId = String(r.rowId ?? r.id ?? `d-${i}`)
      return {
        rowId,
        assetName: name,
        label: name
          ? `${name}${r.classification ? `（${r.classification}）` : ''}`
          : `（未命名#${i + 1}）`,
        classification: String(r.classification ?? ''),
        fairValueLevel: String(r.fairValueLevel ?? ''),
        isRelatedParty: !!r.isRelatedParty,
        impairmentLoss: parseNum(r.impairmentLoss),
      }
    })
    .filter((d) => d.assetName)

  const fvByAsset = new Map<string, { name: string; diff: number; level: string }>()
  for (const r of parseJsonArray(responses.get(G9_FV_KEY)?.remark)) {
    const name = String(r.assetName ?? '').trim()
    if (!name) continue
    const unadj = parseNum(r.closingUnadjustedFV)
    const audited = parseNum(r.closingAuditedFV)
    const diff = r.fairValueDiff != null ? parseNum(r.fairValueDiff) : audited - unadj
    fvByAsset.set(matchG9AssetKey(name), {
      name,
      diff,
      level: String(r.fairValueLevel ?? ''),
    })
  }

  const l3ByAsset = new Map<string, { name: string; variance: number }>()
  for (const r of parseJsonArray(responses.get(G9_L3_KEY)?.remark)) {
    const name = String(r.assetName ?? '').trim()
    if (!name) continue
    l3ByAsset.set(matchG9AssetKey(name), {
      name,
      variance: parseNum(r.variance),
    })
  }

  return { details, fvByAsset, l3ByAsset }
}

/** 按资产名称生成 G9-2/G9-4/G9-5 联动提示 */
export function buildG9VoucherLinkHints(
  assetName: string,
  snap: G9VoucherCrossSnapshot,
): G9VoucherLinkHint[] {
  const name = (assetName || '').trim()
  const hints: G9VoucherLinkHint[] = []
  if (!name) {
    if (snap.details.length > 0) {
      hints.push({
        code: 'no-detail',
        level: 'info',
        text: '未挂接明细：建议选择 G9-2 资产名称',
      })
    }
    return hints
  }

  const key = matchG9AssetKey(name)
  const detail = snap.details.find((d) => matchG9AssetKey(d.assetName) === key)

  if (detail?.isRelatedParty) {
    hints.push({
      code: 'related-party',
      level: 'warning',
      text: 'G9-2 标记关联方，请加强授权与支持文件核对',
    })
  }

  if (detail && /摊余成本|amortised|amortized/i.test(detail.classification)) {
    hints.push({
      code: 'amortised-cost',
      level: 'info',
      text: '明细为摊余成本计量，请重点核对分类与减值',
      suggestCheckClassificationFail: false,
    })
  }

  if (detail && Math.abs(detail.impairmentLoss) > 0.01) {
    hints.push({
      code: 'impairment',
      level: 'warning',
      text: `G9-2 本期减值 ${detail.impairmentLoss.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}，建议复核减值核对项`,
      suggestCheckImpairmentFail: false,
    })
  }

  if (detail && /level\s*3|第三/i.test(detail.fairValueLevel)) {
    hints.push({
      code: 'detail-level3',
      level: 'info',
      text: 'G9-2 公允价值层次为 Level3，请核验估值与 G9-5 调节',
    })
  }

  const fv = snap.fvByAsset.get(key)
  if (fv) {
    if (Math.abs(fv.diff) > 0.01) {
      hints.push({
        code: 'fv-diff',
        level: Math.abs(fv.diff) > 1000 ? 'danger' : 'warning',
        text: `G9-4 公允差异 ${fv.diff.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}，建议复核公允价值核对`,
        suggestCheckFairValueFail: true,
      })
    }
    if (/level\s*3|第三/i.test(fv.level)) {
      hints.push({
        code: 'fv-level3',
        level: 'info',
        text: 'G9-4 为 Level3，请核验估值技术与不可观察输入值',
      })
    }
  }

  const l3 = snap.l3ByAsset.get(key)
  if (l3 && Math.abs(l3.variance) > 0.01) {
    hints.push({
      code: 'fv-diff',
      level: 'warning',
      text: `G9-5 L3 调节差异 ${l3.variance.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}，建议复核公允价值/减值`,
      suggestCheckFairValueFail: true,
    })
  }

  return hints
}

/** 应用联动建议：仅改「未测」项，不覆盖已明确「通过」 */
export function applyG9LinkHintSuggestions(
  row: G9VoucherLinkRow,
  hints: G9VoucherLinkHint[],
): Partial<G9VoucherLinkRow> {
  const patch: Partial<G9VoucherLinkRow> = {}
  const wantFv = hints.some((h) => h.suggestCheckFairValueFail)
  const wantImp = hints.some((h) => h.suggestCheckImpairmentFail)
  const wantCls = hints.some((h) => h.suggestCheckClassificationFail)
  if (wantFv && row.checkFairValue == null) patch.checkFairValue = false
  if (wantImp && row.checkImpairment == null) patch.checkImpairment = false
  if (wantCls && row.checkClassification == null) patch.checkClassification = false
  if (Object.keys(patch).length && !row.abnormalDesc) {
    patch.abnormalDesc = hints
      .filter((h) => h.suggestCheckFairValueFail || h.suggestCheckImpairmentFail || h.suggestCheckClassificationFail)
      .map((h) => h.text)
      .join('；')
  }
  return patch
}

export function selectG9QuantitativeAbnormals<T extends { isAbnormal: boolean; abnormalType?: string }>(
  rows: T[],
): T[] {
  return rows.filter(
    (r) => r.isAbnormal && (r.abnormalType === 'quantitative' || r.abnormalType === 'mixed'),
  )
}

export function mapG9VoucherToMisstatementBody(
  row: G9VoucherLinkRow & {
    voucherNo?: string
    businessContent?: string
    debitAmount?: number
    creditAmount?: number
    rowId?: string
    abnormalType?: string
  },
  year: number,
  accountCode = G9_ACCOUNT_CODE,
): Record<string, unknown> {
  const amount = Math.max(Math.abs(row.debitAmount || 0), Math.abs(row.creditAmount || 0))
  const descParts = [
    row.voucherNo ? `凭证 ${row.voucherNo}` : '',
    row.assetName || '',
    row.abnormalDesc || row.businessContent || 'G9-6 凭证检查金额类异常',
  ].filter(Boolean)
  return {
    year,
    misstatement_type: 'factual',
    misstatement_description: descParts.join('｜'),
    affected_account_code: accountCode,
    affected_account_name: '其他非流动金融资产',
    misstatement_amount: String(amount),
    auditor_evaluation: `来源 G9-6；类型=${row.abnormalType || 'quantitative'}；rowId=${row.rowId || ''}`,
  }
}

export function mapG9VoucherToA13PushItem(
  row: G9VoucherLinkRow & {
    voucherNo?: string
    businessContent?: string
    debitAmount?: number
    creditAmount?: number
  },
): Record<string, unknown> {
  return {
    wpCode: 'G9-6',
    entryType: 'AJE',
    description: row.abnormalDesc || row.businessContent || 'G9-6 金额类异常',
    reportItem: '其他非流动金融资产',
    accountName: row.assetName || '其他非流动金融资产',
    debitAmount: row.debitAmount || 0,
    creditAmount: row.creditAmount || 0,
    indexRef: `G9-6/${row.voucherNo || ''}`,
  }
}

// ─── 行级 OCR ───────────────────────────────────────────────────────────────

export const G9_OCR_CONFIDENCE_THRESHOLD = 0.8

export type G9OcrTargetField =
  | 'voucherDate'
  | 'voucherNo'
  | 'businessContent'
  | 'counterAccount'
  | 'debitAmount'
  | 'creditAmount'
  | 'assetName'
  | 'supportDoc'

export const G9_OCR_FIELD_MAP: Record<string, G9OcrTargetField> = {
  date: 'voucherDate',
  日期: 'voucherDate',
  凭证日期: 'voucherDate',
  voucher_date: 'voucherDate',
  voucherDate: 'voucherDate',
  voucher_no: 'voucherNo',
  voucherNo: 'voucherNo',
  凭证号: 'voucherNo',
  凭证编号: 'voucherNo',
  summary: 'businessContent',
  摘要: 'businessContent',
  business_content: 'businessContent',
  businessContent: 'businessContent',
  业务内容: 'businessContent',
  counter_account: 'counterAccount',
  counterAccount: 'counterAccount',
  对方科目: 'counterAccount',
  debit_amount: 'debitAmount',
  借方金额: 'debitAmount',
  借方: 'debitAmount',
  credit_amount: 'creditAmount',
  贷方金额: 'creditAmount',
  贷方: 'creditAmount',
  amount: 'debitAmount',
  金额: 'debitAmount',
  资产名称: 'assetName',
  被投资单位: 'assetName',
  对方单位: 'assetName',
  assetName: 'assetName',
  支持性文件: 'supportDoc',
  supporting_doc: 'supportDoc',
  supportDoc: 'supportDoc',
}

const G9_OCR_FIELD_LABELS: Record<G9OcrTargetField, string> = {
  voucherDate: '日期',
  voucherNo: '凭证编号',
  businessContent: '业务内容',
  counterAccount: '对方科目',
  debitAmount: '借方金额',
  creditAmount: '贷方金额',
  assetName: '资产名称',
  supportDoc: '支持性文件',
}

export function mapG9OcrToVoucherFields(
  fields: Record<string, unknown>,
  confidence?: number,
): { patch: Partial<Record<G9OcrTargetField, string | number>>; lowConfidence: G9OcrTargetField[] } {
  const patch: Partial<Record<G9OcrTargetField, string | number>> = {}
  const lowConfidence: G9OcrTargetField[] = []
  if (!fields || typeof fields !== 'object') return { patch, lowConfidence }

  for (const [ocrKey, raw] of Object.entries(fields)) {
    const target = G9_OCR_FIELD_MAP[ocrKey] ?? G9_OCR_FIELD_MAP[ocrKey.toLowerCase()]
    if (!target) continue

    let val: unknown = raw
    let conf: number | undefined = confidence
    if (raw && typeof raw === 'object' && 'value' in (raw as object)) {
      val = (raw as { value?: unknown; confidence?: number }).value
      conf = (raw as { confidence?: number }).confidence ?? confidence
    }
    if (val == null || String(val).trim() === '') continue

    if (target === 'debitAmount' || target === 'creditAmount') {
      const num = parseNum(String(val).replace(/,/g, ''))
      if (num === 0) continue
      patch[target] = num
    } else {
      patch[target] = String(val).trim()
    }

    if (conf != null && conf < G9_OCR_CONFIDENCE_THRESHOLD && !lowConfidence.includes(target)) {
      lowConfidence.push(target)
    }
  }
  return { patch, lowConfidence }
}

export function computeG9OcrMergePatch(
  row: Partial<Record<G9OcrTargetField, string | number>>,
  patch: Partial<Record<G9OcrTargetField, string | number>>,
): Partial<Record<G9OcrTargetField, string | number>> {
  const merged: Partial<Record<G9OcrTargetField, string | number>> = {}
  for (const [key, val] of Object.entries(patch)) {
    const cur = row[key as G9OcrTargetField]
    const isEmpty = cur == null || cur === '' || (typeof cur === 'number' && cur === 0)
    if (isEmpty) merged[key as G9OcrTargetField] = val
  }
  return merged
}

export function renderG9OcrPreview(
  patch: Partial<Record<G9OcrTargetField, string | number>>,
  lowConfidence: G9OcrTargetField[],
  confidence: number,
): string {
  const lines = Object.entries(patch).map(([key, val]) => {
    const label = G9_OCR_FIELD_LABELS[key as G9OcrTargetField] || key
    const low = lowConfidence.includes(key as G9OcrTargetField)
    const tag = low ? '<span style="color:#e6a23c;margin-left:6px">⚠ 需人工复核</span>' : ''
    return `<div style="margin:4px 0"><strong>${label}：</strong>${val}${tag}</div>`
  })
  const confPct = (confidence * 100).toFixed(0)
  const confColor = confidence >= G9_OCR_CONFIDENCE_THRESHOLD ? '#67c23a' : '#e6a23c'
  return `
    <div style="font-size:13px">
      <div style="margin-bottom:8px;color:${confColor}">
        整体置信度：${confPct}%${confidence < G9_OCR_CONFIDENCE_THRESHOLD ? '（建议人工核对）' : ''}
      </div>
      ${lines.length ? lines.join('') : '<div style="color:#909399">未提取到有效字段</div>'}
    </div>
  `.trim()
}

export function isG9AllowedOcrAttachment(file: File): boolean {
  const type = file.type || ''
  if (type.startsWith('image/') || type === 'application/pdf') return true
  return /\.(jpe?g|png|gif|bmp|webp|pdf)$/i.test(file.name || '')
}

export function extractG9OcrPayload(resData: unknown): {
  fields: Record<string, unknown>
  confidence: number
} {
  const data = (resData as { data?: unknown })?.data ?? resData ?? {}
  const root = data as Record<string, unknown>
  const extracted = (root.extracted_fields ?? root.fields ?? {}) as Record<string, unknown>
  const fields: Record<string, unknown> = { ...extracted }
  if (!Object.keys(fields).length && root.summary) {
    fields.summary = root.summary
  }
  const confidence = typeof root.confidence === 'number' ? root.confidence : 1
  return { fields, confidence }
}
