/**
 * useF4SupplierFinancing — F4-9 供应商融资检查
 *
 * Spec: .kiro/specs/f4-accounts-payable/ Task 6.5
 * 3区域：保理融资/票据融资/供应链融资，各自独立动态行增删+小计
 * "应重分类"/"未终止确认" 橙色高亮
 * 底部总结textarea(AI) + 虚拟滚动(84行) + 导入导出
 * Requirements: 12.1~12.6
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useF4AccPayFormulaEngine'
import type { ChecklistResponse } from './useF4FormData'

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

export interface FactoringRow {
  rowId: string
  seq: number
  supplier: string
  factoringCompany: string
  amount: number
  date: string
  dueDate: string
  feeRate: number
  hasRecourse: string
  isDerecognized: string
  reportingAccount: string
  auditEvaluation: string
  remark: string
  // 高亮标记
  isHighlight: boolean
}

export interface NoteFinancingRow {
  rowId: string
  seq: number
  supplier: string
  noteType: string
  amount: number
  issueDate: string
  dueDate: string
  discountAmount: number
  discountRate: number
  isEndorsed: string
  reportingAdequacy: string
  auditEvaluation: string
  remark: string
  // 高亮标记
  isHighlight: boolean
}

export interface SupplyChainFinanceRow {
  rowId: string
  seq: number
  supplier: string
  coreEnterprise: string
  amount: number
  date: string
  dueDate: string
  rate: number
  platform: string
  hasModifiedTerms: string
  shouldReclassify: string
  auditEvaluation: string
  remark: string
  // 高亮标记
  isHighlight: boolean
}

export type FinancingRegion = 'factoring' | 'note' | 'supplyChain'

export interface FinancingRegionConfig {
  key: FinancingRegion
  label: string
  storageKey: string
}

export const FINANCING_REGION_CONFIGS: FinancingRegionConfig[] = [
  { key: 'factoring', label: '保理融资', storageKey: 'F4-9-factoring' },
  { key: 'note', label: '票据融资', storageKey: 'F4-9-note' },
  { key: 'supplyChain', label: '供应链融资', storageKey: 'F4-9-supplychain' },
]

// ─── 内部存储类型 ─────────────────────────────────────────────────────────────

interface StoredFactoringRow {
  rowId: string; seq: number; supplier: string; factoringCompany: string
  amount: number; date: string; dueDate: string; feeRate: number
  hasRecourse: string; isDerecognized: string; reportingAccount: string
  auditEvaluation: string; remark: string
}

interface StoredNoteRow {
  rowId: string; seq: number; supplier: string; noteType: string
  amount: number; issueDate: string; dueDate: string; discountAmount: number
  discountRate: number; isEndorsed: string; reportingAdequacy: string
  auditEvaluation: string; remark: string
}

interface StoredSupplyChainRow {
  rowId: string; seq: number; supplier: string; coreEnterprise: string
  amount: number; date: string; dueDate: string; rate: number
  platform: string; hasModifiedTerms: string; shouldReclassify: string
  auditEvaluation: string; remark: string
}

export interface UseF4SupplierFinancingOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

// ─── 常量 ─────────────────────────────────────────────────────────────────────

const NOTE_KEY = 'F4-9-note-conclusion'

// ─── 工具函数 ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `f4sf-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function emptyFactoring(seq: number): StoredFactoringRow {
  return {
    rowId: generateRowId(), seq, supplier: '', factoringCompany: '',
    amount: 0, date: '', dueDate: '', feeRate: 0,
    hasRecourse: '有', isDerecognized: '是', reportingAccount: '',
    auditEvaluation: '', remark: '',
  }
}

function emptyNote(seq: number): StoredNoteRow {
  return {
    rowId: generateRowId(), seq, supplier: '', noteType: '银行承兑',
    amount: 0, issueDate: '', dueDate: '', discountAmount: 0,
    discountRate: 0, isEndorsed: '否', reportingAdequacy: '',
    auditEvaluation: '', remark: '',
  }
}

function emptySupplyChain(seq: number): StoredSupplyChainRow {
  return {
    rowId: generateRowId(), seq, supplier: '', coreEnterprise: '',
    amount: 0, date: '', dueDate: '', rate: 0,
    platform: '', hasModifiedTerms: '否', shouldReclassify: '否',
    auditEvaluation: '', remark: '',
  }
}

function computeFactoring(stored: StoredFactoringRow): FactoringRow {
  const isHighlight = stored.isDerecognized === '否'
  return { ...stored, isHighlight }
}

function computeNote(stored: StoredNoteRow): NoteFinancingRow {
  const isHighlight = stored.isEndorsed === '是' && stored.reportingAdequacy !== '充分'
  return { ...stored, isHighlight }
}

function computeSupplyChain(stored: StoredSupplyChainRow): SupplyChainFinanceRow {
  const isHighlight = stored.shouldReclassify === '是' || stored.hasModifiedTerms === '是'
  return { ...stored, isHighlight }
}

function safeParseFactoring(jsonStr: string | null | undefined): StoredFactoringRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any, i: number) => ({
      ...emptyFactoring(i + 1),
      rowId: raw.rowId || generateRowId(),
      seq: raw.seq ?? i + 1,
      supplier: raw.supplier || '',
      factoringCompany: raw.factoringCompany || '',
      amount: parseNum(raw.amount),
      date: raw.date || '',
      dueDate: raw.dueDate || '',
      feeRate: parseNum(raw.feeRate),
      hasRecourse: raw.hasRecourse || '有',
      isDerecognized: raw.isDerecognized || '是',
      reportingAccount: raw.reportingAccount || '',
      auditEvaluation: raw.auditEvaluation || '',
      remark: raw.remark || '',
    }))
  } catch { return [] }
}

function safeParseNote(jsonStr: string | null | undefined): StoredNoteRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any, i: number) => ({
      ...emptyNote(i + 1),
      rowId: raw.rowId || generateRowId(),
      seq: raw.seq ?? i + 1,
      supplier: raw.supplier || '',
      noteType: raw.noteType || '银行承兑',
      amount: parseNum(raw.amount),
      issueDate: raw.issueDate || '',
      dueDate: raw.dueDate || '',
      discountAmount: parseNum(raw.discountAmount),
      discountRate: parseNum(raw.discountRate),
      isEndorsed: raw.isEndorsed || '否',
      reportingAdequacy: raw.reportingAdequacy || '',
      auditEvaluation: raw.auditEvaluation || '',
      remark: raw.remark || '',
    }))
  } catch { return [] }
}

function safeParseSupplyChain(jsonStr: string | null | undefined): StoredSupplyChainRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any, i: number) => ({
      ...emptySupplyChain(i + 1),
      rowId: raw.rowId || generateRowId(),
      seq: raw.seq ?? i + 1,
      supplier: raw.supplier || '',
      coreEnterprise: raw.coreEnterprise || '',
      amount: parseNum(raw.amount),
      date: raw.date || '',
      dueDate: raw.dueDate || '',
      rate: parseNum(raw.rate),
      platform: raw.platform || '',
      hasModifiedTerms: raw.hasModifiedTerms || '否',
      shouldReclassify: raw.shouldReclassify || '否',
      auditEvaluation: raw.auditEvaluation || '',
      remark: raw.remark || '',
    }))
  } catch { return [] }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useF4SupplierFinancing(options: UseF4SupplierFinancingOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const factoringStored = ref<StoredFactoringRow[]>([])
  const noteStored = ref<StoredNoteRow[]>([])
  const supplyChainStored = ref<StoredSupplyChainRow[]>([])
  const auditConclusion = ref('')

  // ─── 加载 ─────────────────────────────────────────────────────────────────

  watch(() => allResponses.value.get('F4-9-factoring')?.remark, () => {
    if (factoringStored.value.length === 0) {
      factoringStored.value = safeParseFactoring(allResponses.value.get('F4-9-factoring')?.remark)
      if (factoringStored.value.length === 0) factoringStored.value = [emptyFactoring(1)]
    }
  }, { immediate: true })

  watch(() => allResponses.value.get('F4-9-note')?.remark, () => {
    if (noteStored.value.length === 0) {
      noteStored.value = safeParseNote(allResponses.value.get('F4-9-note')?.remark)
      if (noteStored.value.length === 0) noteStored.value = [emptyNote(1)]
    }
  }, { immediate: true })

  watch(() => allResponses.value.get('F4-9-supplychain')?.remark, () => {
    if (supplyChainStored.value.length === 0) {
      supplyChainStored.value = safeParseSupplyChain(allResponses.value.get('F4-9-supplychain')?.remark)
      if (supplyChainStored.value.length === 0) supplyChainStored.value = [emptySupplyChain(1)]
    }
  }, { immediate: true })

  watch(() => allResponses.value.get(NOTE_KEY)?.remark, (v) => {
    auditConclusion.value = v || ''
  }, { immediate: true })

  // ─── 计算行 ───────────────────────────────────────────────────────────────

  const factoringRows: ComputedRef<FactoringRow[]> = computed(() => factoringStored.value.map(computeFactoring))
  const noteRows: ComputedRef<NoteFinancingRow[]> = computed(() => noteStored.value.map(computeNote))
  const supplyChainRows: ComputedRef<SupplyChainFinanceRow[]> = computed(() => supplyChainStored.value.map(computeSupplyChain))

  // ─── 各区域小计 ───────────────────────────────────────────────────────────

  const factoringSubtotal = computed(() => calcSubtotal(factoringRows.value.map((r) => r.amount)))
  const noteSubtotal = computed(() => calcSubtotal(noteRows.value.map((r) => r.amount)))
  const supplyChainSubtotal = computed(() => calcSubtotal(supplyChainRows.value.map((r) => r.amount)))

  const overallTotal = computed(() => factoringSubtotal.value + noteSubtotal.value + supplyChainSubtotal.value)

  const reclassifySummary = computed(() => {
    const factoringRec = factoringRows.value.filter((r) => r.isDerecognized === '否')
    const scRec = supplyChainRows.value.filter((r) => r.shouldReclassify === '是')
    return {
      factoringNotDerecognized: calcSubtotal(factoringRec.map((r) => r.amount)),
      supplyChainReclassify: calcSubtotal(scRec.map((r) => r.amount)),
      total: calcSubtotal(factoringRec.map((r) => r.amount)) + calcSubtotal(scRec.map((r) => r.amount)),
    }
  })

  // ─── 动态行操作 ───────────────────────────────────────────────────────────

  function addFactoringRow(): void {
    if (readonly.value) return
    factoringStored.value.push(emptyFactoring(factoringStored.value.length + 1))
    persistRegion('factoring')
  }

  function addNoteRow(): void {
    if (readonly.value) return
    noteStored.value.push(emptyNote(noteStored.value.length + 1))
    persistRegion('note')
  }

  function addSupplyChainRow(): void {
    if (readonly.value) return
    supplyChainStored.value.push(emptySupplyChain(supplyChainStored.value.length + 1))
    persistRegion('supplyChain')
  }

  function removeFactoringRow(rowId: string): void {
    if (readonly.value || factoringStored.value.length <= 1) return
    const idx = factoringStored.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    factoringStored.value.splice(idx, 1)
    factoringStored.value.forEach((r, i) => { r.seq = i + 1 })
    persistRegion('factoring')
  }

  function removeNoteRow(rowId: string): void {
    if (readonly.value || noteStored.value.length <= 1) return
    const idx = noteStored.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    noteStored.value.splice(idx, 1)
    noteStored.value.forEach((r, i) => { r.seq = i + 1 })
    persistRegion('note')
  }

  function removeSupplyChainRow(rowId: string): void {
    if (readonly.value || supplyChainStored.value.length <= 1) return
    const idx = supplyChainStored.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    supplyChainStored.value.splice(idx, 1)
    supplyChainStored.value.forEach((r, i) => { r.seq = i + 1 })
    persistRegion('supplyChain')
  }

  function updateFactoringCell(rowId: string, field: string, value: any): void {
    if (readonly.value) return
    const row = factoringStored.value.find((r) => r.rowId === rowId)
    if (!row) return
    const numFields = ['amount', 'feeRate']
    if (numFields.includes(field)) (row as any)[field] = parseNum(value)
    else (row as any)[field] = String(value ?? '')
    persistRegion('factoring')
  }

  function updateNoteCell(rowId: string, field: string, value: any): void {
    if (readonly.value) return
    const row = noteStored.value.find((r) => r.rowId === rowId)
    if (!row) return
    const numFields = ['amount', 'discountAmount', 'discountRate']
    if (numFields.includes(field)) (row as any)[field] = parseNum(value)
    else (row as any)[field] = String(value ?? '')
    persistRegion('note')
  }

  function updateSupplyChainCell(rowId: string, field: string, value: any): void {
    if (readonly.value) return
    const row = supplyChainStored.value.find((r) => r.rowId === rowId)
    if (!row) return
    const numFields = ['amount', 'rate']
    if (numFields.includes(field)) (row as any)[field] = parseNum(value)
    else (row as any)[field] = String(value ?? '')
    persistRegion('supplyChain')
  }

  // ─── 持久化 ───────────────────────────────────────────────────────────────

  function persistRegion(region: FinancingRegion): void {
    const cfg = FINANCING_REGION_CONFIGS.find((c) => c.key === region)!
    const data = region === 'factoring' ? factoringStored.value
      : region === 'note' ? noteStored.value
        : supplyChainStored.value
    allResponses.value.set(cfg.storageKey, {
      item_id: cfg.storageKey,
      conclusion: null,
      remark: JSON.stringify(data),
    })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function flushSave(): void {
    const items: ChecklistResponse[] = []
    for (const cfg of FINANCING_REGION_CONFIGS) {
      const item = allResponses.value.get(cfg.storageKey)
      if (item) items.push(item)
    }
    const noteItem = allResponses.value.get(NOTE_KEY)
    if (noteItem) items.push(noteItem)
    if (items.length) window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items } }))
  }

  watch(auditConclusion, (val) => {
    allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    debounceSave()
  })

  // ─── 样式 ─────────────────────────────────────────────────────────────────

  function factoringRowClassName({ row }: { row: FactoringRow }): string {
    return row.isHighlight ? 'financing-highlight' : ''
  }

  function noteRowClassName({ row }: { row: NoteFinancingRow }): string {
    return row.isHighlight ? 'financing-highlight' : ''
  }

  function supplyChainRowClassName({ row }: { row: SupplyChainFinanceRow }): string {
    return row.isHighlight ? 'financing-highlight' : ''
  }

  // ─── 清理 ─────────────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; flushSave() }
  })

  return {
    factoringRows,
    noteRows,
    supplyChainRows,
    factoringSubtotal,
    noteSubtotal,
    supplyChainSubtotal,
    overallTotal,
    reclassifySummary,
    auditConclusion,
    addFactoringRow,
    addNoteRow,
    addSupplyChainRow,
    removeFactoringRow,
    removeNoteRow,
    removeSupplyChainRow,
    updateFactoringCell,
    updateNoteCell,
    updateSupplyChainCell,
    factoringRowClassName,
    noteRowClassName,
    supplyChainRowClassName,
  }
}

export default useF4SupplierFinancing
