/**
 * useH8DisposalCheck — H8-12 减少检查表 composable
 *
 * 对齐致同「使用权资产/租赁负债减少检查表」：
 * 一、审计目标 → 二、样本选取 → 三、测试（原值/累计折旧/减值/净值 + 终止损益 + 核对1–5）
 * → 检查比例（勾稽 H8-1/H8-2，防 #DIV/0!）→ 四、审计说明 → 五、审计结论
 *
 * 平台增强：终止损益 CAS21；H9 同步终止；提前退租违约金提示
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  type H8DisposalCheckRow,
  type H8DisposalSamplingParams,
  type H8DisposalSummary,
  type LinkedRouDecrease,
  normalizeDisposalRow,
  normalizeSamplingParams,
  createEmptySamplingParams,
  recalcDisposalRow,
  calcDisposalSummary,
  sumLinkedRouDecrease,
  seedDisposalRowsFromH82,
  mapLiabilityFromH9,
  mergeSeededDisposalRows,
  buildNoteDraft,
  buildConclusionDraft,
  isCheckIncomplete,
} from './h8DisposalCheckModel'

export type {
  H8DisposalCheckRow,
  H8DisposalSamplingParams,
  H8DisposalSummary,
  LinkedRouDecrease,
  ReductionMethod,
} from './h8DisposalCheckModel'

export {
  REDUCTION_METHOD_OPTS,
  SAMPLING_METHOD_OPTS,
  H8_DISPOSAL_TEST_CONTENT_ITEMS,
  getEvidenceHint,
  calcRouNetValue,
  calcCoverageRate,
  isEarlyTermWithoutPenaltyNote,
  isMaturityNearZeroAnomaly,
} from './h8DisposalCheckModel'

const ROWS_KEY = 'H8-12-rows'
const GAIN_LOSS_TOTAL_KEY = 'H8-12-gain-loss-total'
const CHECKED_AMOUNT_KEY = 'H8-12-checked-amount'
const PARAMS_KEY = 'H8-12-sampling-params'
const NOTE_KEY = 'H8-disposal-audit-note'
const CONCLUSION_KEY = 'H8-disposal-audit-conclusion'
const DETAIL_ROWS_KEY = 'H8-2-rows'
const COST_CREDIT_KEY = 'H8-1-cost-credit-total'
const H9_ROWS_KEY = 'H9-2-rows'
const POP_MANUAL_KEY = 'H8-12-population-manual'

export function useH8DisposalCheck(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
  onSyncH9?: (contractNo: string, liabilityBalance: number) => void
}) {
  const { allResponses, onSave, onSyncH9 } = params

  const rows = ref<H8DisposalCheckRow[]>([])
  const samplingParams = ref<H8DisposalSamplingParams>(createEmptySamplingParams())
  const populationManual = ref(false)
  const auditNote = ref('')
  const auditConclusion = ref('')

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    if (!item) return ''
    const raw = item.remark ?? item.conclusion
    if (raw == null) return ''
    if (typeof raw === 'string') {
      try {
        const p = JSON.parse(raw)
        return typeof p === 'string' ? p : raw
      } catch {
        return raw
      }
    }
    return String(raw)
  }

  function _getNum(itemId: string): number {
    const item = allResponses.value.get(itemId)
    if (!item) return 0
    const raw = item.remark ?? item.conclusion
    const n = Number(raw)
    return Number.isFinite(n) ? n : 0
  }

  function load(): void {
    const data = _getJson(ROWS_KEY)
    rows.value = Array.isArray(data) && data.length > 0
      ? data.map((r, i) => normalizeDisposalRow(r, i))
      : []

    samplingParams.value = normalizeSamplingParams(_getJson(PARAMS_KEY))
    const manual = _getJson(POP_MANUAL_KEY)
    populationManual.value = manual === true || manual === 'true'

    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)

    // 未手工锁定时自动带入总体
    if (!populationManual.value) {
      const linked = linkedDecrease.value
      if (linked.amount > 0 && samplingParams.value.populationAmount <= 0) {
        samplingParams.value = {
          ...samplingParams.value,
          populationAmount: linked.amount,
        }
      }
    }
  }

  watch(allResponses, () => load(), { immediate: true })

  const linkedDecrease: ComputedRef<LinkedRouDecrease> = computed(() => {
    const detail = _getJson(DETAIL_ROWS_KEY)
    const credit = _getNum(COST_CREDIT_KEY)
    return sumLinkedRouDecrease(credit, Array.isArray(detail) ? detail : [])
  })

  const summary: ComputedRef<H8DisposalSummary> = computed(() =>
    calcDisposalSummary(
      rows.value,
      samplingParams.value.populationAmount,
      samplingParams.value.materialityLevel,
    ),
  )

  const unsyncedRows = computed(() => rows.value.filter(r => !r.h9Synced))
  const incompleteCheckRows = computed(() => rows.value.filter(isCheckIncomplete))

  const populationDrift: ComputedRef<boolean> = computed(() => {
    const linked = linkedDecrease.value
    const pop = samplingParams.value.populationAmount
    if (!linked.amount || !pop) return false
    return Math.abs(linked.amount - pop) >= 0.01
  })

  // 兼容旧 API
  const gainLossTotal = computed(() => summary.value.gainLossTotal)
  const gainCount = computed(() => summary.value.gainCount)
  const lossCount = computed(() => summary.value.lossCount)

  function _persistRows(): void {
    if (!onSave) return
    onSave(ROWS_KEY, rows.value.map((r, i) => ({
      rowId: r.rowId,
      seq: i + 1,
      assetCategory: r.assetCategory,
      contractNo: r.contractNo,
      assetName: r.assetName,
      reductionMethod: r.reductionMethod,
      terminationReason: r.reductionMethod,
      reductionDate: r.reductionDate,
      terminationDate: r.reductionDate,
      voucherNo: r.voucherNo,
      oppositeAccount: r.oppositeAccount,
      quantity: r.quantity,
      rouCost: r.rouCost,
      accDepreciation: r.accDepreciation,
      impairmentProvision: r.impairmentProvision,
      rouNetValue: r.rouNetValue,
      liabilityBalance: r.liabilityBalance,
      gainLoss: r.gainLoss,
      remainingMonths: r.remainingMonths,
      earlyTermPenalty: r.earlyTermPenalty,
      supportingDocs: r.supportingDocs,
      checks: { ...r.checks },
      indexRef: r.indexRef,
      isAbnormal: r.isAbnormal,
      isRelatedParty: r.isRelatedParty,
      relatedPartyName: r.relatedPartyName,
      h9Synced: r.h9Synced,
      approvalStatus: r.approvalStatus,
      approver: r.approver,
      remark: r.remark,
    })))
    onSave(GAIN_LOSS_TOTAL_KEY, summary.value.gainLossTotal)
    onSave(CHECKED_AMOUNT_KEY, summary.value.checkedAmount)
  }

  function _persistParams(): void {
    onSave?.(PARAMS_KEY, { ...samplingParams.value })
    onSave?.(POP_MANUAL_KEY, populationManual.value)
  }

  function addRow(contractNo = ''): void {
    rows.value.push(normalizeDisposalRow({
      contractNo: contractNo.trim(),
      seq: rows.value.length + 1,
    }, rows.value.length))
    _persistRows()
  }

  function deleteRow(rowId: string): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    rows.value.forEach((r, i) => { r.seq = i + 1 })
    _persistRows()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return

    if (field.startsWith('checks.')) {
      const key = field.slice(7) as keyof typeof row.checks
      if (key in row.checks) {
        row.checks[key] = Boolean(value)
        _persistRows()
      }
      return
    }

    if (field === 'h9Synced') {
      row.h9Synced = Boolean(value)
      _persistRows()
      return
    }

    const textFields = [
      'assetCategory', 'contractNo', 'assetName', 'reductionMethod', 'terminationReason',
      'reductionDate', 'voucherNo', 'oppositeAccount', 'supportingDocs', 'indexRef',
      'isAbnormal', 'isRelatedParty', 'relatedPartyName', 'approvalStatus', 'approver', 'remark',
    ]
    if (textFields.includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      if (field === 'reductionMethod' || field === 'terminationReason') {
        row.reductionMethod = (field === 'reductionMethod' ? value : row.reductionMethod) as any
        row.terminationReason = row.reductionMethod
      }
      recalcDisposalRow(row)
      _persistRows()
      return
    }

    const numFields = [
      'quantity', 'rouCost', 'accDepreciation', 'impairmentProvision',
      'liabilityBalance', 'remainingMonths', 'earlyTermPenalty',
    ]
    if (numFields.includes(field)) {
      ;(row as any)[field] = Number(value) || 0
      recalcDisposalRow(row)
      _persistRows()
    }
  }

  function updateSamplingParams(patch: Partial<H8DisposalSamplingParams>): void {
    samplingParams.value = { ...samplingParams.value, ...patch }
    if (patch.populationAmount != null) populationManual.value = true
    _persistParams()
  }

  function syncPopulationFromLinked(): void {
    const linked = linkedDecrease.value
    if (!(linked.amount > 0)) return
    samplingParams.value = {
      ...samplingParams.value,
      populationAmount: linked.amount,
    }
    populationManual.value = false
    _persistParams()
  }

  /** 从 H8-2 已终止行批量带入样本（按合同号合并，保留已有核对勾选） */
  function importFromH82(): { imported: number; totalTerminated: number } {
    const detail = _getJson(DETAIL_ROWS_KEY)
    const seeded = seedDisposalRowsFromH82(Array.isArray(detail) ? detail : [])
    if (seeded.length === 0) return { imported: 0, totalTerminated: 0 }
    rows.value = mergeSeededDisposalRows(rows.value, seeded)
    _persistRows()
    // 同步刷新总体（未手工锁定时）
    if (!populationManual.value) {
      const linked = linkedDecrease.value
      if (linked.amount > 0) {
        samplingParams.value = {
          ...samplingParams.value,
          populationAmount: linked.amount,
        }
        _persistParams()
      }
    }
    return { imported: seeded.length, totalTerminated: seeded.length }
  }

  /** 按合同号从 H9-2 填充⑦租赁负债余额 */
  function fillLiabilityFromH9(): { matched: number } {
    const h9 = _getJson(H9_ROWS_KEY)
    const { rows: next, matched } = mapLiabilityFromH9(
      rows.value,
      Array.isArray(h9) ? h9 : [],
    )
    if (matched > 0) {
      rows.value = next
      _persistRows()
    }
    return { matched }
  }

  /** 同步终止到 H9（通知租赁负债也应终止确认） */
  function syncToH9(rowId: string): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return
    row.h9Synced = true
    if (!row.checks.check5) row.checks.check5 = true
    onSyncH9?.(row.contractNo, row.liabilityBalance)
    window.dispatchEvent(new CustomEvent('h8:lease-terminated', {
      detail: {
        contractNo: row.contractNo,
        /** 兼容旧 H9 监听字段 */
        contractId: row.contractNo,
        liabilityBalance: row.liabilityBalance,
        rouNetValue: row.rouNetValue,
        gainLoss: row.gainLoss,
        reductionDate: row.reductionDate,
      },
    }))
    _persistRows()
  }

  /** 批量同步尚未标记的样本到 H9 */
  function syncAllToH9(): number {
    const targets = rows.value.filter(r => !r.h9Synced && r.contractNo.trim())
    for (const row of targets) {
      syncToH9(row.rowId)
    }
    return targets.length
  }

  function saveNote(val: string): void {
    auditNote.value = val
    onSave?.(NOTE_KEY, val)
  }

  function saveConclusion(val: string): void {
    auditConclusion.value = val
    onSave?.(CONCLUSION_KEY, val)
  }

  function draftNote(): void {
    saveNote(buildNoteDraft(summary.value, samplingParams.value.populationAmount))
  }

  function draftConclusion(): void {
    saveConclusion(buildConclusionDraft(summary.value))
  }

  function rowClassName({ row }: { row: H8DisposalCheckRow }): string {
    const classes: string[] = []
    if (row.isAbnormal === '是' || row.isAbnormal === 'Y') classes.push('row-abnormal')
    if (!row.h9Synced) classes.push('row-unsynced')
    if (isCheckIncomplete(row)) classes.push('row-incomplete')
    return classes.join(' ')
  }

  function save(): void {
    _persistRows()
    _persistParams()
  }

  return {
    rows,
    samplingParams,
    populationManual,
    auditNote,
    auditConclusion,
    linkedDecrease,
    summary,
    unsyncedRows,
    incompleteCheckRows,
    populationDrift,
    gainLossTotal,
    gainCount,
    lossCount,
    addRow,
    deleteRow,
    updateCell,
    updateSamplingParams,
    syncPopulationFromLinked,
    importFromH82,
    fillLiabilityFromH9,
    syncToH9,
    syncAllToH9,
    saveNote,
    saveConclusion,
    draftNote,
    draftConclusion,
    rowClassName,
    save,
    load,
  }
}

export default useH8DisposalCheck
