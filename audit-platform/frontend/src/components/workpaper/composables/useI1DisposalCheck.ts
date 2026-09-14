/**
 * useI1DisposalCheck — I1-6 无形资产减少检查
 *
 * 对齐致同 Excel「无形资产减少检查表I1-6」：
 *   上区：定性合规（核销/出售/其他 + 对方科目/凭证/附件）
 *   下区：定量金额（原值/摊销/减值/净值 + 清理费用/收入/净损益 + 勾稽）
 * 公式：净值 E=B−C−D；清理净损益 I=H−G−E（收入−清理费用−净值）
 *
 * 实现上合并为一行模型，避免双表同名不同步。
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcNetValue } from './useI1FormulaEngine'

const ITEM_ID_ROWS = 'I1-6-rows'
const ITEM_ID_NOTE = 'I1-6-audit-note'
const ITEM_ID_CONCLUSION = 'I1-6-conclusion'
const ITEM_ID_DETAIL = 'I1-2-rows'

export const I1_DISPOSAL_METHODS = ['核销', '出售', '转让', '报废', '到期注销', '转入开发成本', '其他'] as const

export type I1DisposalMethod = (typeof I1_DISPOSAL_METHODS)[number] | ''

export interface I1DisposalCheckRow {
  rowId: string
  name: string
  /** 对方科目 */
  counterpartAccount: string
  /** 减少方式 */
  disposalMethod: I1DisposalMethod | string
  // ── 核销检查 ──
  writeOffApproved: 'Y' | 'N' | ''
  writeOffAmountCorrect: 'Y' | 'N' | ''
  writeOffEntryCorrect: 'Y' | 'N' | ''
  // ── 出售检查 ──
  saleApproved: 'Y' | 'N' | ''
  saleProceduresComplete: 'Y' | 'N' | ''
  salePriceFair: 'Y' | 'N' | ''
  // ── 其他方式 ──
  otherMethodDesc: string
  otherCompliant: 'Y' | 'N' | ''
  // ── 审计轨迹 ──
  voucherDate: string
  voucherNo: string
  attachmentIndex: string
  // ── 定量 ──
  originalCost: number
  accAmort: number
  impairment: number
  netBookValue: number
  disposalDate: string
  disposalCost: number
  disposalIncome: number
  /** 清理净损益 = 收入 − 费用 − 净值 */
  disposalGainLoss: number
  /** 是否与相关科目勾稽一致 */
  reconciled: 'Y' | 'N' | ''
  conclusion: string
  remark: string
  sourceDetailRowId?: string
  /** 兼容旧字段 */
  disposalType?: string
  approvalDoc?: string
}

export interface I1DisposalPrepValidation {
  ok: boolean
  messages: string[]
}

function _n(v: any): number {
  const x = Number(v)
  return Number.isFinite(x) ? x : 0
}

function _yn(v: any): 'Y' | 'N' | '' {
  const s = String(v ?? '').trim().toUpperCase()
  if (['Y', '是', '√', 'TRUE', '1', '正确', '公允', '完备', '合规'].includes(s)) return 'Y'
  if (['N', '否', '×', 'FALSE', '0', '不正确', '不公允', '不合规'].includes(s)) return 'N'
  return ''
}

function _genId(): string {
  return `i1d6-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function _safeParse(raw: unknown): any[] {
  if (raw == null) return []
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string') {
    try {
      const p = JSON.parse(raw)
      return Array.isArray(p) ? p : []
    } catch {
      return []
    }
  }
  if (typeof raw === 'object' && raw !== null) {
    const o = raw as any
    return _safeParse(o.remark ?? o.conclusion ?? o.value)
  }
  return []
}

/** 净值 E = B − C − D */
export function calcI1DisposalNet(cost: number, accAmort: number, impairment: number): number {
  return calcNetValue(_n(cost), _n(accAmort), _n(impairment))
}

/**
 * 清理净损益 I = H − G − E（Excel）
 * = 清理收入 − 清理费用 − 账面价值
 */
export function calcI1DisposalGainLoss(
  income: number,
  disposalCost: number,
  netBookValue: number,
): number {
  return _n(income) - _n(disposalCost) - _n(netBookValue)
}

export function recomputeI1DisposalRow(row: I1DisposalCheckRow): I1DisposalCheckRow {
  const originalCost = _n(row.originalCost)
  const accAmort = _n(row.accAmort)
  const impairment = _n(row.impairment)
  const disposalCost = _n(row.disposalCost)
  const disposalIncome = _n(row.disposalIncome)
  const netBookValue = calcI1DisposalNet(originalCost, accAmort, impairment)
  const disposalGainLoss = calcI1DisposalGainLoss(disposalIncome, disposalCost, netBookValue)
  const method = String(row.disposalMethod || row.disposalType || '')

  return {
    ...row,
    disposalMethod: method,
    originalCost,
    accAmort,
    impairment,
    netBookValue,
    disposalCost,
    disposalIncome,
    disposalGainLoss,
    writeOffApproved: _yn(row.writeOffApproved),
    writeOffAmountCorrect: _yn(row.writeOffAmountCorrect),
    writeOffEntryCorrect: _yn(row.writeOffEntryCorrect),
    saleApproved: _yn(row.saleApproved),
    saleProceduresComplete: _yn(row.saleProceduresComplete),
    salePriceFair: _yn(row.salePriceFair),
    otherCompliant: _yn(row.otherCompliant),
    reconciled: _yn(row.reconciled),
  }
}

export function emptyI1DisposalRow(partial?: Partial<I1DisposalCheckRow>): I1DisposalCheckRow {
  return recomputeI1DisposalRow({
    rowId: partial?.rowId ?? _genId(),
    name: '',
    counterpartAccount: '',
    disposalMethod: '',
    writeOffApproved: '',
    writeOffAmountCorrect: '',
    writeOffEntryCorrect: '',
    saleApproved: '',
    saleProceduresComplete: '',
    salePriceFair: '',
    otherMethodDesc: '',
    otherCompliant: '',
    voucherDate: '',
    voucherNo: '',
    attachmentIndex: '',
    originalCost: 0,
    accAmort: 0,
    impairment: 0,
    netBookValue: 0,
    disposalDate: '',
    disposalCost: 0,
    disposalIncome: 0,
    disposalGainLoss: 0,
    reconciled: '',
    conclusion: '',
    remark: '',
    ...partial,
  })
}

export function normalizeI1DisposalRow(raw: any): I1DisposalCheckRow {
  const method = String(raw.disposalMethod || raw.disposalType || '')
  return recomputeI1DisposalRow({
    rowId: raw.rowId ?? _genId(),
    name: String(raw.name ?? ''),
    counterpartAccount: String(raw.counterpartAccount ?? ''),
    disposalMethod: method,
    writeOffApproved: raw.writeOffApproved,
    writeOffAmountCorrect: raw.writeOffAmountCorrect,
    writeOffEntryCorrect: raw.writeOffEntryCorrect,
    saleApproved: raw.saleApproved,
    saleProceduresComplete: raw.saleProceduresComplete,
    salePriceFair: raw.salePriceFair,
    otherMethodDesc: String(raw.otherMethodDesc ?? ''),
    otherCompliant: raw.otherCompliant,
    voucherDate: String(raw.voucherDate || raw.disposalDate || ''),
    voucherNo: String(raw.voucherNo ?? ''),
    attachmentIndex: String(raw.attachmentIndex || raw.approvalDoc || ''),
    originalCost: _n(raw.originalCost ?? raw.cost),
    accAmort: _n(raw.accAmort),
    impairment: _n(raw.impairment),
    netBookValue: 0,
    disposalDate: String(raw.disposalDate || raw.voucherDate || ''),
    disposalCost: _n(raw.disposalCost),
    disposalIncome: _n(raw.disposalIncome),
    disposalGainLoss: 0,
    reconciled: raw.reconciled,
    conclusion: String(raw.conclusion ?? ''),
    remark: String(raw.remark ?? ''),
    sourceDetailRowId: raw.sourceDetailRowId ? String(raw.sourceDetailRowId) : undefined,
  })
}

export function validateI1DisposalPrep(rows: I1DisposalCheckRow[]): I1DisposalPrepValidation {
  const messages: string[] = []
  for (const r of rows) {
    if (!r.name?.trim() && r.originalCost <= 0) continue
    const label = r.name || r.rowId
    if (!r.disposalMethod) {
      messages.push(`「${label}」未选择减少方式`)
      continue
    }
    const m = r.disposalMethod
    if (m === '核销' || m === '报废' || m === '到期注销') {
      if (r.writeOffApproved !== 'Y') messages.push(`「${label}」核销/报废须确认是否经审批`)
      if (r.writeOffAmountCorrect === 'N' || r.writeOffEntryCorrect === 'N') {
        messages.push(`「${label}」核销金额或入账存在异常`)
      }
    }
    if (m === '出售' || m === '转让') {
      if (r.saleApproved !== 'Y') messages.push(`「${label}」出售/转让须确认是否经审批`)
      if (r.saleProceduresComplete === 'N') messages.push(`「${label}」出售手续不完备`)
      if (r.salePriceFair === 'N') messages.push(`「${label}」出售协议金额可能不公允`)
      if (r.disposalIncome <= 0) messages.push(`「${label}」出售/转让未填清理收入`)
    }
    if (m === '其他' || m === '转入开发成本') {
      if (!r.otherMethodDesc?.trim()) messages.push(`「${label}」其他减少须说明方式`)
      if (r.otherCompliant === 'N') messages.push(`「${label}」其他减少方式不合规`)
    }
    if (!r.voucherNo?.trim() && !r.attachmentIndex?.trim()) {
      messages.push(`「${label}」缺少凭证编号或附件索引`)
    }
    if (r.reconciled === 'N') {
      messages.push(`「${label}」与相关科目勾稽不一致`)
    }
  }
  return { ok: messages.length === 0, messages }
}

/** 从 I1-2 带入有减少的行 */
export function seedI1DisposalFromDetail(detailRows: any[]): I1DisposalCheckRow[] {
  const out: I1DisposalCheckRow[] = []
  for (const r of detailRows ?? []) {
    const name = String(r?.name || '').trim()
    if (!name) continue
    const costDec = _n(r.costDecrease ?? r.costDec ?? r.decreaseCost)
    const amortOut = _n(r.amortTransferOut ?? r.accAmortDecrease)
    const impairOut = _n(r.impairmentReversal ?? r.impairmentDecrease)
    // 有减少原值，或备注/类型含减少
    const hasDecrease = costDec > 0
      || String(r.decreaseType || r.disposalType || '').trim() !== ''
    if (!hasDecrease) continue

    out.push(emptyI1DisposalRow({
      name,
      originalCost: costDec || _n(r.costEnd ?? r.cost),
      accAmort: amortOut || _n(r.accAmortEnd ?? r.accAmort),
      impairment: impairOut || _n(r.impairmentEnd ?? r.impairment),
      disposalMethod: String(r.decreaseType || r.disposalType || '其他'),
      sourceDetailRowId: String(r.rowId ?? ''),
      remark: '自I1-2带入减少',
    }))
  }
  return out
}

export function buildI1DisposalConclusionDraft(rows: I1DisposalCheckRow[]): string {
  const n = rows.length
  const cost = rows.reduce((s, r) => s + r.originalCost, 0)
  const net = rows.reduce((s, r) => s + r.netBookValue, 0)
  const income = rows.reduce((s, r) => s + r.disposalIncome, 0)
  const gain = rows.reduce((s, r) => s + r.disposalGainLoss, 0)
  const anomalies = rows.filter((r) => r.conclusion === '有异常' || r.reconciled === 'N').length
  const sales = rows.filter((r) => r.disposalMethod === '出售' || r.disposalMethod === '转让').length
  const writeOffs = rows.filter((r) =>
    ['核销', '报废', '到期注销'].includes(String(r.disposalMethod)),
  ).length

  return [
    `经检查本期无形资产减少 ${n} 项（出售/转让 ${sales}、核销/报废/注销 ${writeOffs}）：`,
    `原值合计 ${cost.toFixed(2)} 元，账面价值合计 ${net.toFixed(2)} 元，`,
    `清理收入 ${income.toFixed(2)} 元，清理净损益 ${gain.toFixed(2)} 元；`,
    `异常/勾稽不一致 ${anomalies} 项；`,
    `净值=原值−摊销−减值，净损益=收入−清理费用−净值已复核；`,
    `减少事项在重大方面${anomalies ? '尚需关注上述异常' : '未见异常'}。`,
  ].join('')
}

export function useI1DisposalCheck(options: {
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
  onPublishEvent?: (event: string, payload: any) => void
}) {
  const rows = ref<I1DisposalCheckRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  function _load() {
    const map = options.allResponses.value
    const raw = map.get(ITEM_ID_ROWS)
    rows.value = _safeParse(raw?.remark ?? raw?.conclusion ?? raw).map(normalizeI1DisposalRow)
    const n = map.get(ITEM_ID_NOTE)
    auditNote.value = String(n?.remark ?? n?.conclusion ?? n?.value ?? '')
    const c = map.get(ITEM_ID_CONCLUSION)
    auditConclusion.value = String(c?.remark ?? c?.conclusion ?? c?.value ?? '')
  }

  function _persist() {
    options.onSave?.(ITEM_ID_ROWS, rows.value)
  }

  watch(options.allResponses, () => _load(), { immediate: true, deep: true })

  const totalCost = computed(() => rows.value.reduce((s, r) => s + r.originalCost, 0))
  const totalAccAmort = computed(() => rows.value.reduce((s, r) => s + r.accAmort, 0))
  const totalImpairment = computed(() => rows.value.reduce((s, r) => s + r.impairment, 0))
  const totalNet = computed(() => rows.value.reduce((s, r) => s + r.netBookValue, 0))
  const totalDisposalCost = computed(() => rows.value.reduce((s, r) => s + r.disposalCost, 0))
  const totalIncome = computed(() => rows.value.reduce((s, r) => s + r.disposalIncome, 0))
  const totalGainLoss = computed(() => rows.value.reduce((s, r) => s + r.disposalGainLoss, 0))
  const anomalyCount = computed(() =>
    rows.value.filter((r) => r.conclusion === '有异常' || r.reconciled === 'N').length,
  )
  const prepValidation = computed(() => validateI1DisposalPrep(rows.value))

  function addRow(name: string): I1DisposalCheckRow {
    const row = emptyI1DisposalRow({ name: name.trim() })
    rows.value.push(row)
    _persist()
    return row
  }

  function removeRow(rowId: string): void {
    const i = rows.value.findIndex((r) => r.rowId === rowId)
    if (i < 0) return
    rows.value.splice(i, 1)
    _persist()
  }

  function updateField(rowId: string, field: keyof I1DisposalCheckRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    Object.assign(row, recomputeI1DisposalRow(row))
    _persist()
  }

  function saveNote(text: string): void {
    auditNote.value = text
    options.onSave?.(ITEM_ID_NOTE, text)
  }

  function saveConclusion(text: string): void {
    auditConclusion.value = text
    options.onSave?.(ITEM_ID_CONCLUSION, text)
  }

  function fillConclusionDraft(): string {
    const draft = buildI1DisposalConclusionDraft(rows.value)
    auditConclusion.value = draft
    saveConclusion(draft)
    return draft
  }

  function seedFromDetail(): { ok: boolean; message: string; count: number } {
    const raw = options.allResponses.value.get(ITEM_ID_DETAIL)
    const detail = _safeParse(raw?.remark ?? raw?.conclusion ?? raw)
    const seeded = seedI1DisposalFromDetail(detail)
    if (!seeded.length) {
      return { ok: false, count: 0, message: 'I1-2 未识别到减少行（需有原值减少或减少类型）' }
    }
    const byName = new Map(rows.value.map((r) => [r.name.trim(), r]))
    let count = 0
    for (const s of seeded) {
      const prev = byName.get(s.name.trim())
      if (prev) {
        prev.originalCost = s.originalCost
        prev.accAmort = s.accAmort
        prev.impairment = s.impairment
        if (!prev.disposalMethod) prev.disposalMethod = s.disposalMethod
        prev.sourceDetailRowId = s.sourceDetailRowId
        Object.assign(prev, recomputeI1DisposalRow(prev))
        count++
      } else {
        rows.value.push(s)
        byName.set(s.name.trim(), s)
        count++
      }
    }
    if (count) _persist()
    return { ok: count > 0, count, message: `已从 I1-2 带入/更新 ${count} 行减少` }
  }

  function appendFromSamples(samples: any[]): number {
    let n = 0
    for (const s of samples ?? []) {
      const row = emptyI1DisposalRow({
        name: String(s.summary || s.description || '处置项').trim() || '处置项',
        originalCost: _n(s.amount),
        disposalIncome: _n(s.disposalIncome),
        voucherNo: String(s.voucherNo || s.voucher_no || ''),
        voucherDate: String(s.voucherDate || s.voucher_date || ''),
        disposalDate: String(s.voucherDate || s.voucher_date || ''),
        counterpartAccount: String(s.counterpartAccount || ''),
      })
      rows.value.push(row)
      n++
    }
    if (n) _persist()
    return n
  }

  /**
   * 发布处置结果至 H10（disposal:source-updated）。
   * H10 按 sourceWp=I1 归入 intangible_disposal 行。
   * 仅走 onPublishEvent / eventBus；crossWpEventBridge 会转发到 window，避免双次入库。
   */
  function publishDisposalToH10(): { ok: boolean; message: string; count: number } {
    const publishable = rows.value.filter((r) => (r.name || '').trim() && (Math.abs(r.disposalGainLoss) > 0.005 || r.originalCost > 0))
    if (!publishable.length) {
      return { ok: false, count: 0, message: '无可发布处置行（需有名称且有账面/损益）' }
    }
    try {
      for (const r of publishable) {
        const payload = {
          linkageId: `I1-6-${r.rowId}`,
          sourceWp: 'I1',
          sourceIndex: 'I1-6',
          assetName: r.name,
          disposalGainLoss: r.disposalGainLoss,
          disposalIncome: r.disposalIncome,
          originalCost: r.originalCost,
          netBookValue: r.netBookValue,
          disposalMethod: r.disposalMethod,
          disposalDate: r.disposalDate,
        }
        if (options.onPublishEvent) {
          options.onPublishEvent('disposal:source-updated', payload)
        } else if (typeof window !== 'undefined') {
          window.dispatchEvent(new CustomEvent('disposal:source-updated', { detail: payload }))
        }
      }
      return {
        ok: true,
        count: publishable.length,
        message: `已发布 ${publishable.length} 项处置至 H10（sourceWp=I1 / intangible_disposal）`,
      }
    } catch (e: any) {
      return { ok: false, count: 0, message: e?.message || '发布失败' }
    }
  }

  return {
    rows,
    auditNote,
    auditConclusion,
    totalCost,
    totalAccAmort,
    totalImpairment,
    totalNet,
    totalDisposalCost,
    totalIncome,
    totalGainLoss,
    anomalyCount,
    prepValidation,
    addRow,
    removeRow,
    updateField,
    saveNote,
    saveConclusion,
    fillConclusionDraft,
    seedFromDetail,
    appendFromSamples,
    publishDisposalToH10,
  }
}

export default useI1DisposalCheck
