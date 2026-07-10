/**
 * useD2PledgeCheck — 质押保理D2-12核心逻辑 composable
 *
 * Spec: .kiro/specs/d2-accounts-receivable-refactor/
 * Task: 14.1
 *
 * 职责：
 * - PledgeRow 类型（9列）+ FactoringRow 类型（8列含 riskTransferred/controlRetained）
 * - pledgeRows / factoringRows reactive
 * - pledgeTotal, pledgeRatio = pledged/total, pledgeRatioWarning(>0.5)
 * - CAS 23 自动终止确认：riskTransferred=Y→终止; !risk&&!control→终止; else→不终止
 * - addPledgeRow / addFactoringRow / removeRow / updateCell
 *
 * Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6
 */
import { ref, computed, watch, onBeforeUnmount, type ComputedRef } from 'vue'
import { parseNum, calculatePledgeRatio } from './useD2FormulaEngine'
import type { UseD2BaseOptions } from './useD2Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface PledgeRow {
  rowId: string
  debtorName: string           // 质押债务人
  pledgeAmount: number         // 质押金额
  pledgeDate: string           // 质押日期
  pledgee: string              // 质权人
  pledgePurpose: string        // 质押目的
  expiryDate: string           // 到期日
  status: string               // 状态（有效/已解除）
  remark: string               // 备注
  indexRef: string             // 索引号
}

export interface FactoringRow {
  rowId: string
  debtorName: string           // 债务人名称
  factoringAmount: number      // 保理金额
  factoringDate: string        // 保理日期
  factor: string               // 保理商
  riskTransferred: boolean     // 风险是否已转移 (CAS23)
  controlRetained: boolean     // 是否保留控制
  derecognition: string        // 终止确认结论（自动判定）
  remark: string               // 备注
}

// ─── Constants ───────────────────────────────────────────────────────────────

const PLEDGE_KEY = 'D2-pledge-rows'
const FACTORING_KEY = 'D2-factoring-rows'
const NOTE_KEY = 'D2-pledge-note'
const CONCLUSION_KEY = 'D2-pledge-conclusion'

/** 质押比例警告阈值 */
const PLEDGE_RATIO_WARNING = 0.5

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `pl-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function createEmptyPledgeRow(): PledgeRow {
  return {
    rowId: generateRowId(),
    debtorName: '',
    pledgeAmount: 0,
    pledgeDate: '',
    pledgee: '',
    pledgePurpose: '',
    expiryDate: '',
    status: '有效',
    remark: '',
    indexRef: '',
  }
}

function createEmptyFactoringRow(): FactoringRow {
  return {
    rowId: generateRowId(),
    debtorName: '',
    factoringAmount: 0,
    factoringDate: '',
    factor: '',
    riskTransferred: false,
    controlRetained: false,
    derecognition: '',
    remark: '',
  }
}

/**
 * CAS 23 自动终止确认判定
 * - 风险已转移 → 终止确认
 * - 风险未转移 且 未保留控制 → 终止确认
 * - 其他 → 不终止确认
 */
function determineDerecognition(riskTransferred: boolean, controlRetained: boolean): string {
  if (riskTransferred) return '终止确认'
  if (!riskTransferred && !controlRetained) return '终止确认'
  return '不终止确认'
}

function parsePledgeRows(jsonStr: string | null | undefined): PledgeRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any) => ({
      rowId: raw.rowId || generateRowId(),
      debtorName: raw.debtorName || '',
      pledgeAmount: parseNum(raw.pledgeAmount),
      pledgeDate: raw.pledgeDate || '',
      pledgee: raw.pledgee || '',
      pledgePurpose: raw.pledgePurpose || '',
      expiryDate: raw.expiryDate || '',
      status: raw.status || '有效',
      remark: raw.remark || '',
      indexRef: raw.indexRef || '',
    }))
  } catch {
    return []
  }
}

function parseFactoringRows(jsonStr: string | null | undefined): FactoringRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any) => {
      const risk = raw.riskTransferred === true || raw.riskTransferred === 'true'
      const control = raw.controlRetained === true || raw.controlRetained === 'true'
      return {
        rowId: raw.rowId || generateRowId(),
        debtorName: raw.debtorName || '',
        factoringAmount: parseNum(raw.factoringAmount),
        factoringDate: raw.factoringDate || '',
        factor: raw.factor || '',
        riskTransferred: risk,
        controlRetained: control,
        derecognition: determineDerecognition(risk, control),
        remark: raw.remark || '',
      }
    })
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2PledgeCheck(options: UseD2BaseOptions) {
  const { allResponses, isReadonly } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const pledgeRows = ref<PledgeRow[]>([])
  const factoringRows = ref<FactoringRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Load from allResponses ────────────────────────────────────────────

  function loadData(): void {
    const pledgeResp = allResponses.value.get(PLEDGE_KEY)
    pledgeRows.value = parsePledgeRows(pledgeResp?.remark)

    const factResp = allResponses.value.get(FACTORING_KEY)
    factoringRows.value = parseFactoringRows(factResp?.remark)

    auditNote.value = allResponses.value.get(NOTE_KEY)?.remark ?? ''
    auditConclusion.value = allResponses.value.get(CONCLUSION_KEY)?.remark ?? ''
  }

  watch(
    () => [
      allResponses.value.get(PLEDGE_KEY)?.remark,
      allResponses.value.get(FACTORING_KEY)?.remark,
    ],
    () => {
      if (pledgeRows.value.length === 0 && factoringRows.value.length === 0) {
        loadData()
      }
    },
    { immediate: true }
  )

  // ─── Computed ──────────────────────────────────────────────────────────

  const pledgeTotal: ComputedRef<number> = computed(() => {
    return pledgeRows.value.reduce((sum, r) => sum + r.pledgeAmount, 0)
  })

  /**
   * 质押比例 = 质押总额 / 应收账款审定总额
   * 从 allResponses 读取 D2-adj-total 审定数
   */
  const pledgeRatio: ComputedRef<number> = computed(() => {
    return calculatePledgeRatio(pledgeTotal.value, auditedTotal.value)
  })

  /** 审定表应收账款审定总额（跨 sheet 联动） */
  const auditedTotal: ComputedRef<number> = computed(() => {
    return parseNum(allResponses.value.get('D2-adj-total-audited')?.remark)
  })

  /** 审定表数据是否已加载（用于核对区 ⚠️ 提示） */
  const adjDataLoaded: ComputedRef<boolean> = computed(() => {
    return allResponses.value.get('D2-adj-total-audited')?.remark != null
      && auditedTotal.value > 0
  })

  /** 保理终止确认合计（终止确认笔数） */
  const factoringDerecognizedCount: ComputedRef<number> = computed(() => {
    return factoringRows.value.filter(r => r.derecognition === '终止确认').length
  })

  /**
   * 质押比例>50%警告
   */
  const pledgeRatioWarning: ComputedRef<string | null> = computed(() => {
    if (pledgeRatio.value > PLEDGE_RATIO_WARNING) {
      return `质押比例${(pledgeRatio.value * 100).toFixed(1)}%超过50%，需关注应收账款可用性`
    }
    return null
  })

  // ─── Row Management ────────────────────────────────────────────────────

  function addPledgeRow(): void {
    if (isReadonly.value) return
    pledgeRows.value.push(createEmptyPledgeRow())
    debounceSave()
  }

  function addFactoringRow(): void {
    if (isReadonly.value) return
    factoringRows.value.push(createEmptyFactoringRow())
    debounceSave()
  }

  function removeRow(rowId: string): void {
    if (isReadonly.value) return

    let idx = pledgeRows.value.findIndex(r => r.rowId === rowId)
    if (idx !== -1) {
      pledgeRows.value.splice(idx, 1)
      debounceSave()
      return
    }

    idx = factoringRows.value.findIndex(r => r.rowId === rowId)
    if (idx !== -1) {
      factoringRows.value.splice(idx, 1)
      debounceSave()
      return
    }
  }

  // ─── Update Cell ───────────────────────────────────────────────────────

  function updateCell(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return

    // Try pledge rows
    const pledgeRow = pledgeRows.value.find(r => r.rowId === rowId)
    if (pledgeRow) {
      const key = field as keyof PledgeRow
      if (key === 'rowId') return
      if (key === 'pledgeAmount') {
        pledgeRow.pledgeAmount = parseNum(value)
      } else {
        ;(pledgeRow as any)[key] = String(value)
      }
      debounceSave()
      return
    }

    // Try factoring rows
    const factRow = factoringRows.value.find(r => r.rowId === rowId)
    if (factRow) {
      const key = field as keyof FactoringRow
      if (key === 'rowId' || key === 'derecognition') return

      if (key === 'factoringAmount') {
        factRow.factoringAmount = parseNum(value)
      } else if (key === 'riskTransferred') {
        factRow.riskTransferred = value === true || value === 'true' || value === 'Y'
        factRow.derecognition = determineDerecognition(factRow.riskTransferred, factRow.controlRetained)
      } else if (key === 'controlRetained') {
        factRow.controlRetained = value === true || value === 'true' || value === 'Y'
        factRow.derecognition = determineDerecognition(factRow.riskTransferred, factRow.controlRetained)
      } else {
        ;(factRow as any)[key] = String(value)
      }
      debounceSave()
      return
    }
  }

  // ─── Serialization & Save ──────────────────────────────────────────────

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function flushSave(): void {
    const items = [
      { item_id: PLEDGE_KEY, conclusion: null, remark: JSON.stringify(pledgeRows.value) },
      { item_id: FACTORING_KEY, conclusion: null, remark: JSON.stringify(factoringRows.value) },
    ]
    for (const item of items) {
      allResponses.value.set(item.item_id, item)
    }
    dispatchSaveEvent(items)
  }

  function saveText(key: string, value: string): void {
    if (isReadonly.value) return
    const item = { item_id: key, conclusion: null, remark: value }
    allResponses.value.set(key, item)
    dispatchSaveEvent([item])
  }

  function saveAuditNote(value: string): void {
    auditNote.value = value
    saveText(NOTE_KEY, value)
  }

  function saveAuditConclusion(value: string): void {
    auditConclusion.value = value
    saveText(CONCLUSION_KEY, value)
  }

  function dispatchSaveEvent(items: any[]): void {
    try {
      window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items } }))
    } catch {
      // silent
    }
  }

  // ─── Lifecycle ─────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    pledgeRows,
    factoringRows,
    pledgeTotal,
    pledgeRatio,
    pledgeRatioWarning,
    auditedTotal,
    adjDataLoaded,
    factoringDerecognizedCount,
    auditNote,
    auditConclusion,
    addPledgeRow,
    addFactoringRow,
    removeRow,
    updateCell,
    saveAuditNote,
    saveAuditConclusion,
  }
}

export default useD2PledgeCheck
