/**
 * useI1AdditionCheck — I1-5 无形资产增加检查表
 * 对齐源表 19 列分段检查 + 检查比例防 DIV/0 + I1-2 / I2 联动
 */
import { ref, computed, watch, onScopeDispose, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem } from './useI1FormData'
import {
  type I1AdditionCheckRow,
  type I1AdditionSummary,
  type YnNa,
  type I2CapitalizationTransferItem,
  type I1MethodColGroup,
  type I1TraceRow,
  emptyI1AdditionRow,
  emptyI1TraceRow,
  normalizeI1AdditionRow,
  normalizeI1TraceRow,
  summarizeI1Addition,
  seedI1AdditionFromDetail,
  seedI1AdditionFromI2Transfer,
  seedI1TraceFromCheckRows,
  calcI1TraceAmountDiff,
  rowToExportRecord,
  I1_ADDITION_EXPORT_HEADERS,
  I1_ADDITION_METHODS,
  I1_ADDITION_DEFAULT_COVERAGE_THRESHOLD,
  I1_TRACE_SOURCE_OPTS,
  collectActiveColGroups,
  shouldShowColGroup,
} from './i1AdditionCheckModel'

export {
  I1_ADDITION_METHODS,
  I1_ADDITION_EXPORT_HEADERS,
  I1_ADDITION_DEFAULT_COVERAGE_THRESHOLD,
  I1_TRACE_SOURCE_OPTS,
  type I1AdditionCheckRow,
  type I1AdditionSummary,
  type I1TraceRow,
  type YnNa,
  type I1MethodColGroup,
  shouldShowColGroup,
  collectActiveColGroups,
}

const ITEM_ROWS = 'I1-5-rows'
const ITEM_TRACE = 'I1-5-trace-rows'
const ITEM_PERIOD = 'I1-5-period-total'
const ITEM_COVERAGE = 'I1-5-coverage-threshold'
const ITEM_DETAIL = 'I1-2-rows'
const EVENT_I2_TRANSFER = 'development:capitalized-to-intangible'

function _safeParse(raw: unknown): any[] {
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string' && raw) {
    try {
      const p = JSON.parse(raw)
      return Array.isArray(p) ? p : []
    } catch { return [] }
  }
  return []
}

function _getNum(v: any): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _mergeSeededRows(
  current: I1AdditionCheckRow[],
  seeded: I1AdditionCheckRow[],
): { rows: I1AdditionCheckRow[]; count: number } {
  const byName = new Map(current.map((r) => [r.name.trim(), r]))
  let count = 0
  const next = [...current]
  for (const s of seeded) {
    const key = s.name.trim()
    const prev = byName.get(key)
    if (prev) {
      prev.entryAmount = s.entryAmount
      prev.entryDate = s.entryDate || prev.entryDate
      prev.acquisitionMethod = s.acquisitionMethod || prev.acquisitionMethod
      if (s.otherMethod) prev.otherMethod = s.otherMethod
      prev.sourceDetailRowId = s.sourceDetailRowId || prev.sourceDetailRowId
      if (s.remark && !prev.remark) prev.remark = s.remark
      count++
    } else {
      next.push(s)
      byName.set(key, s)
      count++
    }
  }
  return { rows: next, count }
}

export function useI1AdditionCheck(
  wpId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: { onSave?: (itemId: string, value: any) => void },
) {
  const rows = ref<I1AdditionCheckRow[]>([])
  const traceRows = ref<I1TraceRow[]>([])
  /** 本期发生额（总体）— 优先 I1-2 / 审定表联动，可手工覆盖 */
  const periodTotal = ref(0)
  const periodManual = ref(false)
  /** 检查比例告警阈值 %（可配置，默认 20） */
  const coverageThreshold = ref(I1_ADDITION_DEFAULT_COVERAGE_THRESHOLD)
  /** EventBus 最近一次 I2 转入明细（跨底稿未合入 allResponses 时兜底） */
  const pendingI2Transfers = ref<I2CapitalizationTransferItem[]>([])
  const pendingI2Amount = ref(0)

  function _load() {
    const resp = allResponses.value.get(ITEM_ROWS)
    rows.value = _safeParse(resp?.remark ?? resp?.conclusion).map(normalizeI1AdditionRow)

    const tr = allResponses.value.get(ITEM_TRACE)
    traceRows.value = _safeParse(tr?.remark ?? tr?.conclusion).map(normalizeI1TraceRow)

    const pItem = allResponses.value.get(ITEM_PERIOD)
    const rawP = pItem?.remark ?? pItem?.conclusion
    if (rawP != null && rawP !== '') {
      try {
        const parsed = typeof rawP === 'string' ? JSON.parse(rawP) : rawP
        if (parsed && typeof parsed === 'object') {
          periodTotal.value = _getNum(parsed.periodTotal)
          periodManual.value = !!parsed.manual
        } else {
          periodTotal.value = _getNum(rawP)
        }
      } catch {
        periodTotal.value = _getNum(rawP)
      }
    }

    const thrItem = allResponses.value.get(ITEM_COVERAGE)
    const thrRaw = thrItem?.remark ?? thrItem?.conclusion
    if (thrRaw != null && thrRaw !== '') {
      let n = 0
      if (typeof thrRaw === 'string' && thrRaw.trim().startsWith('{')) {
        try { n = _getNum(JSON.parse(thrRaw).threshold) } catch { n = _getNum(thrRaw) }
      } else {
        n = _getNum(thrRaw)
      }
      if (n > 0) coverageThreshold.value = Math.min(100, n)
    }
  }

  function _persistRows() {
    options?.onSave?.(ITEM_ROWS, rows.value)
  }

  function _persistTrace() {
    options?.onSave?.(ITEM_TRACE, traceRows.value)
  }

  function _persistPeriod() {
    options?.onSave?.(ITEM_PERIOD, {
      periodTotal: periodTotal.value,
      manual: periodManual.value,
    })
  }

  function _persistCoverageThreshold() {
    options?.onSave?.(ITEM_COVERAGE, coverageThreshold.value)
  }

  const linkedPeriodTotal: ComputedRef<{ amount: number; source: string }> = computed(() => {
    for (const key of ['I1-adjudication-cost-addition-total', 'I1-adj-cost-increase-total']) {
      const item = allResponses.value.get(key)
      const amt = _getNum(item?.remark ?? item?.conclusion)
      if (amt > 0) return { amount: amt, source: 'I1审定表' }
    }

    const costRowsRaw = allResponses.value.get('I1-adj-cost-rows')
    const costRows = _safeParse(costRowsRaw?.remark ?? costRowsRaw?.conclusion)
    if (costRows.length) {
      const sum = costRows.reduce((s, r) => {
        if (r?.isSubtotal) return s
        return s + _getNum(r.increase)
      }, 0)
      if (sum > 0) return { amount: sum, source: 'I1审定表' }
    }

    const detail = allResponses.value.get(ITEM_DETAIL)
    const detailRows = _safeParse(detail?.remark ?? detail?.conclusion)
    if (detailRows.length) {
      const sum = detailRows.reduce((s, r) => s + _getNum(r.costIncrease ?? r.increase), 0)
      if (sum > 0) return { amount: sum, source: 'I1-2明细' }
    }
    return { amount: 0, source: '' }
  })

  const summary: ComputedRef<I1AdditionSummary> = computed(() =>
    summarizeI1Addition(rows.value, periodTotal.value, traceRows.value),
  )

  const coverageLow: ComputedRef<boolean> = computed(() =>
    summary.value.coverageRate != null
      && summary.value.coverageRate < coverageThreshold.value
      && summary.value.periodTotal > 0,
  )

  const activeColGroups: ComputedRef<Set<I1MethodColGroup>> = computed(() =>
    collectActiveColGroups(rows.value),
  )

  function setPeriodTotal(amount: number, manual = true) {
    periodTotal.value = Math.max(amount || 0, 0)
    periodManual.value = manual
    _persistPeriod()
  }

  function setCoverageThreshold(n: number) {
    const v = Math.min(100, Math.max(1, Math.round(_getNum(n) || I1_ADDITION_DEFAULT_COVERAGE_THRESHOLD)))
    coverageThreshold.value = v
    _persistCoverageThreshold()
  }

  function syncPeriodFromLinked(): { ok: boolean; message: string } {
    const linked = linkedPeriodTotal.value
    if (!(linked.amount > 0)) {
      return { ok: false, message: '未找到 I1-2/审定表本期增加，请先完善明细或审定表' }
    }
    setPeriodTotal(linked.amount, false)
    return { ok: true, message: `已从${linked.source}带入本期增加 ${linked.amount.toLocaleString('zh-CN')}` }
  }

  function seedFromDetail(): { ok: boolean; count: number; message: string } {
    const detail = allResponses.value.get(ITEM_DETAIL)
    const detailRows = _safeParse(detail?.remark ?? detail?.conclusion)
    const seeded = seedI1AdditionFromDetail(detailRows)
    if (!seeded.length) {
      return { ok: false, count: 0, message: 'I1-2 无本期增加>0 的明细可带入' }
    }
    const merged = _mergeSeededRows(rows.value, seeded)
    rows.value = merged.rows
    if (!periodManual.value || !(periodTotal.value > 0)) {
      const linked = linkedPeriodTotal.value
      if (linked.amount > 0) setPeriodTotal(linked.amount, false)
    }
    _persistRows()
    return { ok: true, count: merged.count, message: `已从 I1-2 带入/更新 ${merged.count} 行` }
  }

  /** 解析 I2 转入候选：allResponses 明细 > 审定表 > EventBus 缓存 */
  function _resolveI2TransferItems(): { items: I2CapitalizationTransferItem[]; source: string } {
    const detail = _safeParse(
      allResponses.value.get('I2-2-rows')?.remark
      ?? allResponses.value.get('I2-2-rows')?.conclusion,
    )
    const fromDetail: I2CapitalizationTransferItem[] = detail
      .filter((r: any) => _getNum(r.transferToIntangible) > 0)
      .map((r: any) => ({
        projectName: r.projectName || '',
        amount: _getNum(r.transferToIntangible),
        transferDate: r.transferDate || '',
        transferAssetName: r.transferAssetName || r.projectName || '',
        sourceRowId: r.rowId,
      }))
    if (fromDetail.length) return { items: fromDetail, source: 'I2-2明细' }

    const adj = _safeParse(
      allResponses.value.get('I2-1-rows')?.remark
      ?? allResponses.value.get('I2-1-rows')?.conclusion,
    )
    const fromAdj: I2CapitalizationTransferItem[] = adj
      .filter((r: any) => _getNum(r.decreaseTransfer) > 0)
      .map((r: any) => ({
        projectName: r.projectName || '',
        amount: _getNum(r.decreaseTransfer),
        transferAssetName: r.projectName || '',
        sourceRowId: r.rowId,
      }))
    if (fromAdj.length) return { items: fromAdj, source: 'I2-1审定表' }

    if (pendingI2Transfers.value.length) {
      return { items: pendingI2Transfers.value, source: 'I2 EventBus' }
    }
    return { items: [], source: '' }
  }

  function seedFromI2Transfer(): { ok: boolean; count: number; message: string; amount: number } {
    const resolved = _resolveI2TransferItems()
    const seeded = seedI1AdditionFromI2Transfer(resolved.items)
    if (!seeded.length) {
      return {
        ok: false,
        count: 0,
        amount: 0,
        message: '未找到 I2 资本化转入。请先在 I2 填写「转无形」并保存，或保持本页打开以接收联动事件。',
      }
    }
    const merged = _mergeSeededRows(rows.value, seeded)
    rows.value = merged.rows
    const amount = seeded.reduce((s, r) => s + (Number(r.entryAmount) || 0), 0)
    _persistRows()
    return {
      ok: true,
      count: merged.count,
      amount,
      message: `已从${resolved.source}带入/更新 ${merged.count} 行（合计 ${amount.toLocaleString('zh-CN')}）`,
    }
  }

  function addRow(partial?: Partial<I1AdditionCheckRow>): I1AdditionCheckRow {
    const row = emptyI1AdditionRow(partial)
    rows.value.push(row)
    _persistRows()
    return row
  }

  function removeRow(rowId: string) {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx < 0) return
    rows.value.splice(idx, 1)
    _persistRows()
  }

  function updateCell(rowId: string, field: keyof I1AdditionCheckRow, value: any) {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _persistRows()
  }

  function addTraceRow(partial?: Partial<I1TraceRow>): I1TraceRow {
    const row = emptyI1TraceRow({
      ...partial,
      seq: (partial?.seq ?? traceRows.value.length + 1),
    })
    traceRows.value.push(row)
    _persistTrace()
    return row
  }

  function removeTraceRow(rowId: string) {
    const idx = traceRows.value.findIndex((r) => r.rowId === rowId)
    if (idx < 0) return
    traceRows.value.splice(idx, 1)
    traceRows.value.forEach((r, i) => { r.seq = i + 1 })
    _persistTrace()
  }

  function updateTraceCell(rowId: string, field: keyof I1TraceRow, value: any) {
    const row = traceRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    if (field === 'sourceAmount' || field === 'bookAmount') {
      row.amountDiff = calcI1TraceAmountDiff(row.sourceAmount, row.bookAmount)
    }
    _persistTrace()
  }

  function seedTraceFromCheck(): { ok: boolean; count: number; message: string } {
    const seeded = seedI1TraceFromCheckRows(rows.value)
    if (!seeded.length) {
      return { ok: false, count: 0, message: '账→证样本为空，无法生成追查行' }
    }
    const existingKeys = new Set(
      traceRows.value.map((t) => `${t.bookAssetName}|${t.sourceRef}`),
    )
    let count = 0
    for (const s of seeded) {
      const key = `${s.bookAssetName}|${s.sourceRef}`
      if (existingKeys.has(key)) continue
      s.seq = traceRows.value.length + 1
      traceRows.value.push(s)
      existingKeys.add(key)
      count++
    }
    if (count) _persistTrace()
    return {
      ok: count > 0,
      count,
      message: count > 0 ? `已生成 ${count} 条证→账追查行` : '追查行已存在，未新增',
    }
  }

  function flushPersist() {
    _persistRows()
    _persistTrace()
  }

  function importRows(imported: Partial<I1AdditionCheckRow>[], replace = true) {
    const mapped = imported.map(normalizeI1AdditionRow)
    if (replace) rows.value = mapped
    else rows.value.push(...mapped)
    _persistRows()
  }

  async function exportXlsx(kind: 'template' | 'data' = 'data') {
    const XLSX = await import('xlsx')
    const headers = [...I1_ADDITION_EXPORT_HEADERS]
    const dataRows = kind === 'template' ? [] : rows.value.map(rowToExportRecord)
    const ws = kind === 'template'
      ? XLSX.utils.aoa_to_sheet([headers])
      : XLSX.utils.json_to_sheet(dataRows, { header: headers })
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'I1-5增加检查')
    const meta = XLSX.utils.aoa_to_sheet([
      ['检查合计(样本)', summary.value.checkedTotal],
      ['本期发生额(总体)', summary.value.periodTotal],
      ['检查比例%', summary.value.coverageRate ?? 'N/A（总体为0）'],
      ['告警阈值%', coverageThreshold.value],
    ])
    XLSX.utils.book_append_sheet(wb, meta, '检查比例')
    XLSX.writeFile(wb, `I1-5_增加检查_${kind === 'template' ? '模板' : '数据'}.xlsx`)
  }

  async function importXlsx(file: File, replace = true): Promise<{ imported: number }> {
    const XLSX = await import('xlsx')
    const buf = await file.arrayBuffer()
    const wb = XLSX.read(buf, { type: 'array' })
    const sheet = wb.Sheets[wb.SheetNames[0]]
    const raw = XLSX.utils.sheet_to_json<Record<string, any>>(sheet, { defval: '' })
    const mapped = raw.map((r) => normalizeI1AdditionRow({
      name: r['资产名称'] ?? r.name,
      entryAmount: r['入账金额'] ?? r.entryAmount,
      acquisitionMethod: r['取得方式'] ?? r.acquisitionMethod,
      entryDate: r['入账日期'] ?? r.entryDate,
      voucherNo: r['凭证号'] ?? r.voucherNo,
      purchaseContractComplete: r['购买-合同齐全'],
      purchasePaymentApproved: r['购买-支付审批'],
      purchaseEntryCorrect: r['购买-入账正确'],
      invoiceAmountExTax: r['购买-发票不含税'],
      inputVat: r['购买-进项税额'],
      vatSplitOk: r['购买-价税分离正确'],
      investApproval: r['投入-批复手续'],
      investProcedureComplete: r['投入-手续齐全'],
      investPriceFair: r['投入-价格公允'],
      financeBookAmount: r['融资-入账金额'],
      financeEffectiveRate: r['融资-实际利率'],
      financeCost: r['融资-融资费用'],
      financeEntryCorrect: r['融资-入账正确'],
      comboAmount: r['合并-合并金额'],
      comboRecognitionMet: r['合并-确认条件'],
      comboPpaIndex: r['合并-PPA索引'],
      otherMethod: r['其他-方式'],
      otherCompliant: r['其他-符合规定'],
      counterparty: r['交易对方'],
      isRelatedParty: r['关联方'],
      relatedPartyName: r['关联方名称'],
      fundOccupationRisk: r['资金占用风险'],
      checkConclusion: r['审查结论'],
      remark: r['备注'],
    })).filter((r) => r.name)
    importRows(mapped, replace)
    return { imported: mapped.length }
  }

  function _onI2Transfer(e: Event) {
    const detail = (e as CustomEvent).detail || {}
    const items = Array.isArray(detail.items) ? detail.items : []
    pendingI2Transfers.value = items
    pendingI2Amount.value = _getNum(detail.amount)
  }

  if (typeof window !== 'undefined') {
    window.addEventListener(EVENT_I2_TRANSFER, _onI2Transfer)
    onScopeDispose(() => window.removeEventListener(EVENT_I2_TRANSFER, _onI2Transfer))
  }

  watch(allResponses, () => _load(), { immediate: true })

  return {
    rows,
    traceRows,
    periodTotal,
    periodManual,
    linkedPeriodTotal,
    summary,
    coverageThreshold,
    coverageLow,
    activeColGroups,
    pendingI2Amount,
    setPeriodTotal,
    setCoverageThreshold,
    syncPeriodFromLinked,
    seedFromDetail,
    seedFromI2Transfer,
    addRow,
    removeRow,
    updateCell,
    addTraceRow,
    removeTraceRow,
    updateTraceCell,
    seedTraceFromCheck,
    flushPersist,
    importRows,
    exportXlsx,
    importXlsx,
  }
}

export default useI1AdditionCheck
