/**
 * I2 跨表增强辅助：委外合计、项目名单、调整草稿、完成度标记、截止日、行业模板、OCR
 */
import http from '@/utils/http'

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _str(v: unknown): string {
  return v == null ? '' : String(v)
}

/** 解析 checklist 中的 JSON 数组 */
export function parseResponseArray(raw: unknown): any[] {
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string' && raw) {
    try {
      const p = JSON.parse(raw)
      return Array.isArray(p) ? p : []
    } catch { return [] }
  }
  if (raw && typeof raw === 'object') {
    const remark = (raw as any).remark ?? (raw as any).conclusion
    if (remark != null) return parseResponseArray(remark)
  }
  return []
}

/** I2-7 本期委外发生额：优先 increase.outsource */
export function sumI27Outsource(raw: unknown): number {
  const rows = parseResponseArray(raw)
  const sum = rows.reduce((s, r) => {
    const staged = _num(r?.increase?.outsource)
      || _num(r?.audited?.outsource)
      || _num(r?.ending?.outsource)
    if (staged) return s + staged
    if (r?.outsourceSubtotal != null) return s + _num(r.outsourceSubtotal)
    if (r?.outsourceAmount != null) return s + _num(r.outsourceAmount)
    if (r?.outsourceFee != null) return s + _num(r.outsourceFee)
    const cat = _str(r?.category || r?.feeType || r?.expenseType)
    if (/委外/.test(cat)) return s + _num(r?.amount ?? r?.debitAmount ?? r?.totalAmount)
    return s
  }, 0)
  return Math.round(sum * 100) / 100
}

/** I2-7 项目名称列表 */
export function listI27ProjectNames(raw: unknown): string[] {
  const rows = parseResponseArray(raw)
  const names = rows.map((r) => _str(r?.projectName).trim()).filter(Boolean)
  return [...new Set(names)]
}

export interface I2DraftAjeInput {
  description: string
  debitAmount?: number
  creditAmount?: number
  indexRef?: string
  remark?: string
  accountCode?: string
  accountName?: string
  reportItem?: string
}

/** 向 I2-3 追加一条账项调整草稿（写入 allResponses + 可选 save） */
export async function appendI23DraftAje(opts: {
  allResponses: Map<string, any>
  saveResponse?: (sheetCode: string, data: Record<string, any>) => Promise<void>
  draft: I2DraftAjeInput
}): Promise<{ rowId: string; total: number }> {
  const KEY = 'I2-3-rows'
  const existing = parseResponseArray(opts.allResponses.get(KEY))
  const rowId = `i23-draft-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
  const debit = _num(opts.draft.debitAmount)
  const credit = _num(opts.draft.creditAmount)
  const next = [
    ...existing,
    {
      rowId,
      seq: existing.length + 1,
      description: opts.draft.description,
      category: '账项调整',
      entryType: 'AJE',
      reportItem: opts.draft.reportItem || '开发支出',
      accountCode: opts.draft.accountCode || '1717',
      accountName: opts.draft.accountName || '开发支出',
      noteItem: '',
      debitAmount: debit,
      creditAmount: credit || (debit > 0 ? 0 : 0),
      indexRef: opts.draft.indexRef || 'I2',
      remark: opts.draft.remark || '来源:检查异常一键生成',
    },
  ]
  const payload = JSON.stringify(next)
  opts.allResponses.set(KEY, { item_id: KEY, conclusion: null, remark: payload })
  if (opts.saveResponse) {
    await opts.saveResponse('I2-3', { [KEY]: payload })
  }
  return { rowId, total: next.length }
}

/** 完成度标记：供 I2 目录扫描（多字段抬高进度） */
export async function writeSheetCompletionMarker(opts: {
  allResponses: Map<string, any>
  saveResponse?: (sheetCode: string, data: Record<string, any>) => Promise<void>
  sheetCode: string
  progress: number
  ok: boolean
  detail?: Record<string, any>
}): Promise<void> {
  const prefix = opts.sheetCode
  const keys = [
    `${prefix}-completion`,
    `${prefix}-completion-progress`,
    `${prefix}-completion-ok`,
    `${prefix}-completion-detail`,
  ]
  const progress = Math.max(0, Math.min(100, Math.round(opts.progress)))
  const map = opts.allResponses
  map.set(keys[0], { item_id: keys[0], conclusion: opts.ok ? '已完成' : '进行中', remark: String(progress) })
  map.set(keys[1], { item_id: keys[1], conclusion: null, remark: String(progress) })
  map.set(keys[2], { item_id: keys[2], conclusion: opts.ok ? 'Y' : 'N', remark: opts.ok ? 'Y' : 'N' })
  map.set(keys[3], {
    item_id: keys[3],
    conclusion: null,
    remark: JSON.stringify({ progress, ok: opts.ok, ...(opts.detail || {}), at: new Date().toISOString() }),
  })
  if (opts.saveResponse) {
    await opts.saveResponse(prefix, {
      [keys[0]]: String(progress),
      [keys[1]]: String(progress),
      [keys[2]]: opts.ok ? 'Y' : 'N',
      [keys[3]]: JSON.stringify({ progress, ok: opts.ok, ...(opts.detail || {}) }),
    })
  }
}

/** 默认资产负债表日 */
export function resolveDefaultCutoffDate(opts?: {
  year?: number | string | null
  allResponses?: Map<string, any>
  projectContext?: Record<string, any> | null
}): string {
  const ctx = opts?.projectContext
  const fromCtx = _str(ctx?.bs_date || ctx?.period_end || ctx?.audit_period_end)
  if (/^\d{4}-\d{2}-\d{2}/.test(fromCtx)) return fromCtx.slice(0, 10)

  const map = opts?.allResponses
  if (map) {
    for (const key of ['I6-cutoff-date', 'I2-cutoff-date', 'I2-bs-date', 'project-bs-date']) {
      const raw = map.get(key)
      const text = typeof raw === 'string' ? raw : _str(raw?.remark ?? raw?.conclusion)
      if (/^\d{4}-\d{2}-\d{2}/.test(text)) return text.slice(0, 10)
    }
  }

  const y = Number(opts?.year)
  if (Number.isFinite(y) && y >= 2000 && y <= 2100) return `${y}-12-31`
  const nowY = new Date().getFullYear()
  return `${nowY - 1}-12-31`
}

/** I2-4 同业行业模板 */
export interface I2IndustryPeerTemplate {
  id: string
  label: string
  peers: Array<{
    companyName: string
    source: string
    capitalizationPolicy: string
    costAggregation: string
    staffAllocation: string
  }>
}

export const I2_INDUSTRY_PEER_TEMPLATES: I2IndustryPeerTemplate[] = [
  {
    id: 'software',
    label: '软件 / 互联网',
    peers: [
      {
        companyName: '同业软件A（示意）',
        source: '年报会计政策',
        capitalizationPolicy: '内部开发软件满足五条件后资本化，研究阶段费用化',
        costAggregation: '按项目归集人工/外购技术/云资源',
        staffAllocation: '非全时按工时系统占比分摊',
      },
      {
        companyName: '同业软件B（示意）',
        source: '招股书',
        capitalizationPolicy: '产品化阶段资本化，定制项目费用化',
        costAggregation: '人工为主，材料较少',
        staffAllocation: '研发工时占比≥50%认定',
      },
    ],
  },
  {
    id: 'pharma',
    label: '医药 / 生物',
    peers: [
      {
        companyName: '同业医药A（示意）',
        source: '年报',
        capitalizationPolicy: '临床III期或取得关键批件后资本化（行业惯例）',
        costAggregation: '临床试验费、材料、委外CRO',
        staffAllocation: '专职研发+项目工时',
      },
    ],
  },
  {
    id: 'manufacturing',
    label: '先进制造',
    peers: [
      {
        companyName: '同业制造A（示意）',
        source: '年报',
        capitalizationPolicy: '样机验证通过且具备量产意图后资本化',
        costAggregation: '材料、折旧、人工、委外加工',
        staffAllocation: '工时表分摊兼职人员',
      },
    ],
  },
]

/** 委外加计扣除提示（80%） */
export function buildOutsourceSuperDeductionTip(bookAmount: number): string {
  if (!(bookAmount > 0)) {
    return '委外研发加计扣除通常按实际发生额的 80% 计入可加计基数；请与 I6 加计口径交叉核对。'
  }
  const base = Math.round(bookAmount * 0.8 * 100) / 100
  return `本期委外账面约 ${bookAmount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}，加计口径参考基数（×80%）约 ${base.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}；请与 I6 加计扣除计算交叉核对。`
}

/** 通用 OCR：复用 D4 contract-ocr；可选 attachment 回流 */
export async function runWorkpaperOcr(
  wpId: string,
  file: File,
  opts?: { projectId?: string; attachmentId?: string; forceReocr?: boolean },
): Promise<Record<string, any>> {
  const { buildLinkedOcrFormData } = await import('./ocrAttachmentLinkage')
  const { form: fd } = await buildLinkedOcrFormData(file, {
    projectId: opts?.projectId,
    wpId,
    attachmentId: opts?.attachmentId,
    forceReocr: opts?.forceReocr,
  })
  const res = await http.post(`/api/workpapers/${wpId}/d4/contract-ocr`, fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
    _silent: true,
  } as any)
  const data = res.data?.data ?? res.data ?? {}
  return (data.extracted_fields || data.fields || data) as Record<string, any>
}

export function pickOcrField(fields: Record<string, any>, ...keys: string[]): string {
  for (const k of keys) {
    const v = fields[k]
    if (v != null && String(v).trim()) return String(v).trim()
  }
  // 模糊匹配
  const lower = Object.fromEntries(Object.entries(fields).map(([k, v]) => [k.toLowerCase(), v]))
  for (const k of keys) {
    const v = lower[k.toLowerCase()]
    if (v != null && String(v).trim()) return String(v).trim()
  }
  return ''
}
