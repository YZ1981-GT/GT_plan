/**
 * useH5Impairment — H5-14/15 减值 composable
 *
 * OO渲染, DCF储量折现
 * H5-14 减值测算(34行32列15公式) + H5-15 可收回金额(64行28列12公式)
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/
 * Task: 3.4
 * Requirements: 8.1-8.2
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH5FormData'
import { calcNetValue, calcSubtotal } from './useH5FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ImpairmentTestRow {
  rowId: string
  assetGroup: string            // 资产组
  oilField: string              // 油田
  bookValue: number             // 账面价值
  recoverableAmount: number     // 可收回金额
  impairmentLoss: number        // 减值损失 = max(0, 账面-可收回)
  priorImpairment: number       // 已确认减值
  additionalImpairment: number  // 本期补提减值
  conclusion: string
}

export interface DcfAssumption {
  discountRate: number          // 折现率(%)
  projectionYears: number       // 预测年限
  terminalGrowthRate: number    // 终值增长率(%)
  oilPrice: number              // 油价假设(元/吨)
  productionDeclineRate: number // 产量递减率(%)
  reservesEstimate: number      // 储量估计(万吨)
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX_14 = 'H5-14'
const ITEM_PREFIX_15 = 'H5-15'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH5Impairment(opts: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  projectId: Ref<string>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = opts

  const testRows = ref<ImpairmentTestRow[]>([])
  const dcfAssumptions = ref<DcfAssumption>({
    discountRate: 10, projectionYears: 15, terminalGrowthRate: 0,
    oilPrice: 4500, productionDeclineRate: 5, reservesEstimate: 0,
  })
  const auditNote = ref('')
  const auditConclusion = ref('')
  /** OO渲染标记（复杂DCF由OnlyOffice承载） */
  const useOnlyOffice = ref(true)

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _load(): void {
    const raw14 = allResponses.value.get(`${ITEM_PREFIX_14}-rows`)?.remark
    if (raw14) {
      try { testRows.value = (JSON.parse(raw14) ?? []).map(_normalizeRow) } catch { testRows.value = [] }
    } else { testRows.value = [] }

    const raw15 = allResponses.value.get(`${ITEM_PREFIX_15}-dcf`)?.remark
    if (raw15) {
      try { dcfAssumptions.value = { ...dcfAssumptions.value, ...JSON.parse(raw15) } } catch { /* keep defaults */ }
    }

    auditNote.value = (allResponses.value.get(`${ITEM_PREFIX_14}-audit-note`)?.remark ?? '') as string
    auditConclusion.value = (allResponses.value.get(`${ITEM_PREFIX_14}-audit-conclusion`)?.remark ?? '') as string
  }

  function _normalizeRow(raw: any): ImpairmentTestRow {
    const bookValue = Number(raw.bookValue) || 0
    const recoverableAmount = Number(raw.recoverableAmount) || 0
    const impairmentLoss = Math.max(0, bookValue - recoverableAmount)
    const priorImpairment = Number(raw.priorImpairment) || 0
    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      assetGroup: raw.assetGroup ?? '',
      oilField: raw.oilField ?? '',
      bookValue,
      recoverableAmount,
      impairmentLoss,
      priorImpairment,
      additionalImpairment: Math.max(0, impairmentLoss - priorImpairment),
      conclusion: raw.conclusion ?? '',
    }
  }

  // ─── Computed ──────────────────────────────────────────────────────────────

  const totalImpairmentLoss = computed(() => calcSubtotal(testRows.value.map((r) => r.impairmentLoss)))
  const totalAdditionalImpairment = computed(() => calcSubtotal(testRows.value.map((r) => r.additionalImpairment)))
  const hasImpairment = computed(() => totalAdditionalImpairment.value > 0)

  // ─── Actions ───────────────────────────────────────────────────────────────

  function updateTestRow(rowId: string, field: keyof ImpairmentTestRow, value: any): void {
    const row = testRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    // 重算减值
    row.impairmentLoss = Math.max(0, row.bookValue - row.recoverableAmount)
    row.additionalImpairment = Math.max(0, row.impairmentLoss - row.priorImpairment)
    _persist14()
  }

  function updateDcfAssumption(field: keyof DcfAssumption, value: number): void {
    dcfAssumptions.value[field] = value
    _persist15()
  }

  function _persist14(): void { onSave?.(`${ITEM_PREFIX_14}-rows`, testRows.value) }
  function _persist15(): void { onSave?.(`${ITEM_PREFIX_15}-dcf`, dcfAssumptions.value) }
  function saveNote(note: string): void { auditNote.value = note; onSave?.(`${ITEM_PREFIX_14}-audit-note`, note) }
  function saveConclusion(conclusion: string): void { auditConclusion.value = conclusion; onSave?.(`${ITEM_PREFIX_14}-audit-conclusion`, conclusion) }

  watch(allResponses, () => _load(), { immediate: true })

  return {
    testRows, dcfAssumptions, auditNote, auditConclusion, useOnlyOffice,
    totalImpairmentLoss, totalAdditionalImpairment, hasImpairment,
    updateTestRow, updateDcfAssumption, saveNote, saveConclusion,
  }
}
