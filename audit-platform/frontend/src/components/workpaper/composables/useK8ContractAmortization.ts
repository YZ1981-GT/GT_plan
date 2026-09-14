/**
 * useK8ContractAmortization — K8-5 销售费用合同检查表（合同费用摊销核对）
 *
 * 🔴 修复 K8 复盘发现：原 K8-5 用通用「合规检查」模型（金额匹配/审批/真实性），
 * 与致同源模板完全不符。源模板 K8-5 实为**合同费用摊销核对表**：
 *   项目|对方单位|合同内容|合同金额|实际开票方|支付条件|支付时间|
 *   合同开始日期|合同结束日期|合同总月份|本期应计月份|本期应计损益|
 *   本期已计损益|差异|合同索引|凭证检查索引|审计结论
 * 典型对象：律师费/咨询费/租赁费/保险费/物业费等按合同期摊销的费用。
 *
 * 核心公式：
 *   合同总月份 = 合同期间跨月数（含首尾月）
 *   本期应计月份 = 合同期 ∩ 摊销期（期初~期末）的跨月数
 *   本期应计损益 = 合同金额 / 合同总月份 × 本期应计月份
 *   差异 = 本期应计损益 − 本期已计损益（|差异|>容差 高亮）
 *
 * 纯计算函数导出供单测。Item IDs: K8-5-amort-rows / K8-5-amort-period / K8-5-conclusion
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'

// ─── 纯计算函数（可单测）────────────────────────────────────────────────────

function parseNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 解析 YYYY-MM-DD → {y, m}（1-based month），失败返回 null */
export function parseYm(dateStr: string): { y: number; m: number } | null {
  if (!dateStr) return null
  const m = String(dateStr).match(/^(\d{4})-(\d{1,2})/)
  if (!m) return null
  const year = Number(m[1])
  const month = Number(m[2])
  if (!Number.isFinite(year) || !Number.isFinite(month) || month < 1 || month > 12) return null
  return { y: year, m: month }
}

/** 含首尾月的跨月数：(ey-sy)*12 + (em-sm) + 1，非法/逆序返回 0 */
export function monthsInclusive(startDate: string, endDate: string): number {
  const s = parseYm(startDate)
  const e = parseYm(endDate)
  if (!s || !e) return 0
  const diff = (e.y - s.y) * 12 + (e.m - s.m) + 1
  return diff > 0 ? diff : 0
}

/** 合同期 ∩ 摊销期 的本期应计月份 */
export function accrualMonthsInPeriod(
  contractStart: string,
  contractEnd: string,
  periodStart: string,
  periodEnd: string,
): number {
  const cs = parseYm(contractStart)
  const ce = parseYm(contractEnd)
  const ps = parseYm(periodStart)
  const pe = parseYm(periodEnd)
  if (!cs || !ce || !ps || !pe) return 0
  const csIdx = cs.y * 12 + cs.m
  const ceIdx = ce.y * 12 + ce.m
  const psIdx = ps.y * 12 + ps.m
  const peIdx = pe.y * 12 + pe.m
  const lo = Math.max(csIdx, psIdx)
  const hi = Math.min(ceIdx, peIdx)
  const diff = hi - lo + 1
  return diff > 0 ? diff : 0
}

/** 本期应计损益 = 合同金额 / 合同总月份 × 本期应计月份 */
export function calcAccruedPL(contractAmount: number, totalMonths: number, accrualMonths: number): number {
  const amt = parseNum(contractAmount)
  const total = parseNum(totalMonths)
  const accrual = parseNum(accrualMonths)
  if (total <= 0) return 0
  return (amt / total) * accrual
}

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K8AmortRow {
  rowKey: string
  /** 项目（费用性质：律师费/咨询费/租赁费/保险费/物业费等） */
  projectName: string
  /** 对方单位 */
  counterparty: string
  /** 合同/协议内容 */
  contractContent: string
  /** 合同/协议金额 */
  contractAmount: number
  /** 实际开票方 */
  invoiceParty: string
  /** 支付条件 */
  paymentTerm: string
  /** 支付时间 */
  paymentTime: string
  /** 合同开始日期 YYYY-MM-DD */
  startDate: string
  /** 合同结束日期 YYYY-MM-DD */
  endDate: string
  /** 合同总月份（公式，含首尾月） */
  totalMonths: number
  /** 本期应计月份（公式，合同期∩摊销期；可手工覆盖） */
  accrualMonths: number
  /** 本期应计损益（公式：金额/总月份×应计月份） */
  accruedPL: number
  /** 本期已计损益（手工/账面） */
  bookedPL: number
  /** 差异（公式：应计−已计） */
  diff: number
  /** 合同索引 */
  contractIndex: string
  /** 凭证检查索引 */
  voucherIndex: string
  /** 审计结论 */
  conclusion: string
  /** OCR 附件名 */
  ocrAttachment: string
}

export interface UseK8ContractAmortizationParams {
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  /** 审计年度（用于默认摊销期 {year}-01-01 ~ {year}-12-31） */
  year?: Ref<number | undefined>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}

const ROWS_KEY = 'K8-5-amort-rows'
const PERIOD_KEY = 'K8-5-amort-period'
const CONCLUSION_KEY = 'K8-5-conclusion'
/** 差异容差（元） */
const DIFF_TOLERANCE = 1

export function useK8ContractAmortization(params: UseK8ContractAmortizationParams) {
  const { allResponses, year, isReadonly, onSave } = params

  const rows = ref<K8AmortRow[]>([])
  const conclusion = ref('')
  const amortStart = ref('')
  const amortEnd = ref('')

  function _defaultYear(): number {
    return year?.value ?? new Date().getFullYear()
  }

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function initFromResponses(): void {
    const raw = _getJson(ROWS_KEY)
    rows.value = Array.isArray(raw) ? raw.map(_normalizeRow) : []
    conclusion.value = _getString(CONCLUSION_KEY)
    const period = _getJson(PERIOD_KEY)
    if (period && typeof period === 'object') {
      amortStart.value = period.start || `${_defaultYear()}-01-01`
      amortEnd.value = period.end || `${_defaultYear()}-12-31`
    } else {
      amortStart.value = `${_defaultYear()}-01-01`
      amortEnd.value = `${_defaultYear()}-12-31`
    }
  }

  function _normalizeRow(raw: any): K8AmortRow {
    return {
      rowKey: raw.rowKey ?? `amort-${Math.random().toString(36).slice(2, 10)}`,
      projectName: raw.projectName ?? '',
      counterparty: raw.counterparty ?? '',
      contractContent: raw.contractContent ?? '',
      contractAmount: parseNum(raw.contractAmount),
      invoiceParty: raw.invoiceParty ?? '',
      paymentTerm: raw.paymentTerm ?? '',
      paymentTime: raw.paymentTime ?? '',
      startDate: raw.startDate ?? '',
      endDate: raw.endDate ?? '',
      totalMonths: parseNum(raw.totalMonths),
      accrualMonths: parseNum(raw.accrualMonths),
      accruedPL: parseNum(raw.accruedPL),
      bookedPL: parseNum(raw.bookedPL),
      diff: parseNum(raw.diff),
      contractIndex: raw.contractIndex ?? '',
      voucherIndex: raw.voucherIndex ?? '',
      conclusion: raw.conclusion ?? '',
      ocrAttachment: raw.ocrAttachment ?? '',
      // 应计月份是否手工覆盖标记（用 __manualAccrual 隐藏字段）
      ...(raw.__manualAccrual ? { __manualAccrual: true } : {}),
    } as K8AmortRow
  }

  /** 带公式列的完整行 */
  const computedRows: ComputedRef<K8AmortRow[]> = computed(() =>
    rows.value.map((row) => {
      const totalMonths = monthsInclusive(row.startDate, row.endDate)
      const autoAccrual = accrualMonthsInPeriod(row.startDate, row.endDate, amortStart.value, amortEnd.value)
      // 若用户手工填了 accrualMonths（>0 且标记）则用手工值，否则用自动
      const accrualMonths = (row as any).__manualAccrual ? row.accrualMonths : autoAccrual
      const accruedPL = calcAccruedPL(row.contractAmount, totalMonths, accrualMonths)
      const diff = accruedPL - parseNum(row.bookedPL)
      return { ...row, totalMonths, accrualMonths, accruedPL, diff }
    }),
  )

  /** 差异超容差行数（供告警） */
  const diffWarnings = computed(() =>
    computedRows.value.filter((r) => Math.abs(r.diff) > DIFF_TOLERANCE),
  )

  const totals = computed(() => ({
    contractAmount: computedRows.value.reduce((s, r) => s + parseNum(r.contractAmount), 0),
    accruedPL: computedRows.value.reduce((s, r) => s + parseNum(r.accruedPL), 0),
    bookedPL: computedRows.value.reduce((s, r) => s + parseNum(r.bookedPL), 0),
    diff: computedRows.value.reduce((s, r) => s + parseNum(r.diff), 0),
  }))

  /** 摊销差异 → K8-3 调整分录建议草稿（差异行：应计 vs 已计不一致） */
  const diffAdjustmentDrafts = computed(() =>
    diffWarnings.value.map((r) => {
      const diff = parseNum(r.diff)
      // diff>0：应计>已计 → 少计费用，应调增销售费用（借销售费用）
      // diff<0：应计<已计 → 多计费用，应调减销售费用（贷销售费用）
      return {
        contractName: r.projectName || r.contractContent || '（未命名合同）',
        category: '账项调整' as const,
        summary: `【K8-5摊销差异】${r.projectName || r.contractContent || ''} 本期应计${r.accruedPL.toFixed(2)} vs 已计${r.bookedPL.toFixed(2)}`.trim(),
        reportItem: '销售费用',
        accountName: '销售费用',
        noteItem: '',
        debitAmount: diff > 0 ? Math.abs(diff) : 0,
        creditAmount: diff < 0 ? Math.abs(diff) : 0,
        indexRef: r.contractIndex || 'K8-5',
        remark: `合同费用摊销差异，应计损益=合同金额÷总月份×应计月份=${r.accruedPL.toFixed(2)}，账面已计=${r.bookedPL.toFixed(2)}，差异=${diff.toFixed(2)}`,
      }
    }),
  )

  function _persist(): void {
    if (!onSave) return
    onSave(ROWS_KEY, rows.value)
  }

  function addRow(projectName: string): void {
    if (isReadonly?.value) return
    rows.value.push(_normalizeRow({ projectName, rowKey: `amort-${Date.now()}-${Math.random().toString(36).slice(2, 8)}` }))
    _persist()
  }

  /** 新增空行并返回 rowKey（供引导式弹窗新增流程） */
  function addRowReturnKey(projectName = ''): string {
    if (isReadonly?.value) return ''
    const rowKey = `amort-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    rows.value.push(_normalizeRow({ projectName, rowKey }))
    _persist()
    return rowKey
  }

  /** 批量应用行补丁（引导式弹窗一次性提交，避免逐字段多次持久化） */
  function applyRowPatch(rowKey: string, patch: Partial<K8AmortRow> & { __manualAccrual?: boolean }): boolean {
    if (isReadonly?.value) return false
    const row = rows.value.find((r) => r.rowKey === rowKey)
    if (!row) return false
    for (const [k, v] of Object.entries(patch)) {
      if (k === 'rowKey') continue
      if (k === '__manualAccrual') { (row as any).__manualAccrual = !!v; continue }
      if (['contractAmount', 'bookedPL', 'totalMonths', 'accrualMonths', 'sourceAmount'].includes(k)) {
        ;(row as any)[k] = parseNum(v)
      } else {
        ;(row as any)[k] = v
      }
    }
    // 若补丁显式给了 accrualMonths 且标记手工覆盖，置 __manualAccrual
    if (Object.prototype.hasOwnProperty.call(patch, 'accrualMonths') && patch.__manualAccrual !== false) {
      ;(row as any).__manualAccrual = true
    }
    _persist()
    return true
  }

  function removeRow(rowKey: string): void {
    if (isReadonly?.value) return
    const idx = rows.value.findIndex((r) => r.rowKey === rowKey)
    if (idx >= 0) { rows.value.splice(idx, 1); _persist() }
  }

  function updateCell(rowKey: string, field: keyof K8AmortRow, value: unknown): void {
    if (isReadonly?.value) return
    const row = rows.value.find((r) => r.rowKey === rowKey)
    if (!row) return
    if (field === 'accrualMonths') {
      ;(row as any).__manualAccrual = true
      ;(row as any).accrualMonths = parseNum(value)
    } else if (['contractAmount', 'bookedPL', 'totalMonths'].includes(field as string)) {
      ;(row as any)[field] = parseNum(value)
    } else {
      ;(row as any)[field] = value
    }
    _persist()
  }

  function setAmortPeriod(start: string, end: string): void {
    if (isReadonly?.value) return
    amortStart.value = start
    amortEnd.value = end
    onSave?.(PERIOD_KEY, { start, end })
  }

  function saveConclusion(text: string): void {
    conclusion.value = text
    onSave?.(CONCLUSION_KEY, text)
  }

  watch(allResponses, () => initFromResponses(), { immediate: true })

  return {
    rows: computedRows,
    conclusion,
    amortStart,
    amortEnd,
    diffWarnings,
    diffAdjustmentDrafts,
    totals,
    addRow,
    addRowReturnKey,
    applyRowPatch,
    removeRow,
    updateCell,
    setAmortPeriod,
    saveConclusion,
    initFromResponses,
  }
}

export default useK8ContractAmortization
