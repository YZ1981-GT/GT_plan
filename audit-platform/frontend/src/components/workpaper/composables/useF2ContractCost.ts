/**
 * useF2ContractCost — F2-55 合同履约成本明细
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  calcEndBalance,
  calcSubtotalByCategory,
  calcAuditedAmount,
  calcSubtotal,
} from './useF2SpecialFormulaEngine'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'
import {
  debouncedPublishF2SpeDisclosureNote,
  publishF2SpeSubstantiveAdjudicated,
} from './useF2SpeEventBus'

export type ContractCostSegment =
  | 'basic' | 'opening' | 'increase' | 'decrease' | 'end' | 'audit'

export interface ContractCostRow {
  id: string
  projectCode: string
  projectName: string
  contractName: string
  contractAmount: number
  opening_equipment: number
  opening_construction: number
  opening_labor: number
  opening_other: number
  increase_equipment: number
  increase_construction: number
  increase_labor: number
  increase_other: number
  decrease_equipment: number
  decrease_construction: number
  decrease_labor: number
  decrease_other: number
  isDirectlyRelated: '是' | '否'
  isRecoverable: '是' | '否'
  adj_equipment: number
  adj_construction: number
  adj_labor: number
  adj_other: number
  remark: string
}

const ROWS_KEY = 'F2-55-rows'
const NOTE_KEY = 'F2-55-note'

function emptyRow(id: string): ContractCostRow {
  return {
    id, projectCode: '', projectName: '', contractName: '', contractAmount: 0,
    opening_equipment: 0, opening_construction: 0, opening_labor: 0, opening_other: 0,
    increase_equipment: 0, increase_construction: 0, increase_labor: 0, increase_other: 0,
    decrease_equipment: 0, decrease_construction: 0, decrease_labor: 0, decrease_other: 0,
    isDirectlyRelated: '是', isRecoverable: '是',
    adj_equipment: 0, adj_construction: 0, adj_labor: 0, adj_other: 0,
    remark: '',
  }
}

function enrichRow(r: ContractCostRow) {
  const opening_subtotal = calcSubtotalByCategory(
    r.opening_equipment, r.opening_construction, r.opening_labor, r.opening_other,
  )
  const increase_subtotal = calcSubtotalByCategory(
    r.increase_equipment, r.increase_construction, r.increase_labor, r.increase_other,
  )
  const decrease_subtotal = calcSubtotalByCategory(
    r.decrease_equipment, r.decrease_construction, r.decrease_labor, r.decrease_other,
  )
  const end_equipment = calcEndBalance(r.opening_equipment, r.increase_equipment, r.decrease_equipment)
  const end_construction = calcEndBalance(r.opening_construction, r.increase_construction, r.decrease_construction)
  const end_labor = calcEndBalance(r.opening_labor, r.increase_labor, r.decrease_labor)
  const end_other = calcEndBalance(r.opening_other, r.increase_other, r.decrease_other)
  const end_subtotal = calcSubtotalByCategory(end_equipment, end_construction, end_labor, end_other)
  const adj_subtotal = calcSubtotalByCategory(r.adj_equipment, r.adj_construction, r.adj_labor, r.adj_other)
  const audited_equipment = calcAuditedAmount(end_equipment, r.adj_equipment)
  const audited_construction = calcAuditedAmount(end_construction, r.adj_construction)
  const audited_labor = calcAuditedAmount(end_labor, r.adj_labor)
  const audited_other = calcAuditedAmount(end_other, r.adj_other)
  const audited_subtotal = calcSubtotalByCategory(
    audited_equipment, audited_construction, audited_labor, audited_other,
  )
  const notRecoverable = r.isRecoverable === '否'
  return {
    ...r,
    opening_subtotal, increase_subtotal, decrease_subtotal,
    end_equipment, end_construction, end_labor, end_other, end_subtotal,
    adj_subtotal,
    audited_equipment, audited_construction, audited_labor, audited_other, audited_subtotal,
    notRecoverable,
  }
}

export function useF2ContractCost(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  const activeSegment = ref<ContractCostSegment>('basic')
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let adjudicatedTimer: ReturnType<typeof setTimeout> | null = null

  const rows = ref<ContractCostRow[]>([enrichRow(emptyRow('1'))])
  const auditNote = ref('')

  function load(): void {
    const raw = readSpeRowJson(opts.allResponses.value.get(ROWS_KEY))
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as ContractCostRow[]
        if (parsed.length) rows.value = parsed.map(enrichRow)
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const enrichedRows = computed(() => rows.value.map(enrichRow))

  const totals = computed(() => ({
    end_subtotal: calcSubtotal(enrichedRows.value.map((r) => r.end_subtotal)),
    audited_subtotal: calcSubtotal(enrichedRows.value.map((r) => r.audited_subtotal)),
  }))

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(ROWS_KEY),
      opts.allResponses.value.get(NOTE_KEY),
    ].filter(Boolean)
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items } }))
    }
  }

  function persist(): void {
    opts.allResponses.value.set(ROWS_KEY, {
      item_id: ROWS_KEY, conclusion: null, remark: JSON.stringify(rows.value),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function updateRow(id: string, patch: Partial<ContractCostRow>): void {
    if (readonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? enrichRow({ ...r, ...patch }) : r))
    persist()
  }

  async function addRow(): Promise<void> {
    if (readonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入项目名称', '新增合同履约成本', {
        confirmButtonText: '确定', cancelButtonText: '取消',
      })
      const id = String(Date.now())
      rows.value = [...rows.value, enrichRow({ ...emptyRow(id), projectName: value })]
      persist()
    } catch { /* cancelled */ }
  }

  function removeRow(id: string): void {
    if (readonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id)
    persist()
  }

  watch(auditNote, (val) => {
    if (readonly.value) return
    opts.allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    debouncedPublishF2SpeDisclosureNote('contract-cost', val)
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  })

  watch(
    () => totals.value.audited_subtotal,
    (amount) => {
      if (adjudicatedTimer) clearTimeout(adjudicatedTimer)
      adjudicatedTimer = setTimeout(() => {
        adjudicatedTimer = null
        publishF2SpeSubstantiveAdjudicated({
          wpCode: 'F2-special',
          accountCode: '1405',
          auditedAmount: amount,
        })
      }, 2000)
    },
    { immediate: true },
  )

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); flushSave() }
    if (adjudicatedTimer) clearTimeout(adjudicatedTimer)
  })

  return {
    activeSegment,
    enrichedRows,
    totals,
    auditNote,
    updateRow,
    addRow,
    removeRow,
  }
}

export default useF2ContractCost
