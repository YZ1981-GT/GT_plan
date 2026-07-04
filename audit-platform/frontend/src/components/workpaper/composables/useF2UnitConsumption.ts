/**
 * useF2UnitConsumption — F2-64 主要产品生产成本及单耗分析（232行×18列）
 * 按产品分组、公式联动、虚拟速览
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcChangeRate, calcSubtotal } from './useF2InvMaiFormulaEngine'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'

export type ConsumptionSegment = 'basic' | 'consumption' | 'io' | 'history' | 'audit'
export type ConsumptionViewMode = 'focus' | 'group' | 'flat'

export interface UnitConsumptionRow {
  id: string
  productName: string
  materialName: string
  spec: string
  unit: string
  standardConsumption: number
  actualConsumption: number
  inputQty: number
  outputQty: number
  priorConsumption: number
  consumptionT1: number
  consumptionT2: number
  materialUnitPrice: number
  rationalityNote: string
  auditFocus: string
  remark: string
}

export interface EnrichedUnitConsumptionRow extends UnitConsumptionRow {
  deviationPct: number
  ioRatio: number
  consumptionChangeRate: number | '' | 'N/A'
  amountImpact: number
  isHighDeviation: boolean
  isIoImbalance: boolean
  highlight: boolean
  warningLevel: 'none' | 'deviation' | 'io' | 'both'
}

export interface ProductGroup {
  productName: string
  rows: EnrichedUnitConsumptionRow[]
  materialCount: number
  abnormalCount: number
  totalAmountImpact: number
  maxDeviationPct: number
}

const ROWS_KEY = 'F2-64-rows'
const NOTE_KEY = 'F2-64-note'
const DEVIATION_THRESHOLD = 10
const IO_LOW = 0.9
const IO_HIGH = 1.1

function emptyRow(id: string, productName = ''): UnitConsumptionRow {
  return {
    id, productName, materialName: '', spec: '', unit: '',
    standardConsumption: 0, actualConsumption: 0,
    inputQty: 0, outputQty: 0,
    priorConsumption: 0, consumptionT1: 0, consumptionT2: 0,
    materialUnitPrice: 0,
    rationalityNote: '', auditFocus: '', remark: '',
  }
}

export function enrichUnitConsumptionRow(r: UnitConsumptionRow): EnrichedUnitConsumptionRow {
  const deviationPct = r.standardConsumption
    ? ((r.actualConsumption - r.standardConsumption) / r.standardConsumption) * 100
    : 0
  const ioRatio = r.outputQty ? r.inputQty / r.outputQty : 0
  const consumptionChangeRate = calcChangeRate(r.priorConsumption, r.actualConsumption)
  const amountImpact = (r.actualConsumption - r.standardConsumption) * r.outputQty * r.materialUnitPrice
  const isHighDeviation = Math.abs(deviationPct) > DEVIATION_THRESHOLD
  const isIoImbalance = r.outputQty > 0 && (ioRatio < IO_LOW || ioRatio > IO_HIGH)
  let warningLevel: EnrichedUnitConsumptionRow['warningLevel'] = 'none'
  if (isHighDeviation && isIoImbalance) warningLevel = 'both'
  else if (isHighDeviation) warningLevel = 'deviation'
  else if (isIoImbalance) warningLevel = 'io'
  return {
    ...r,
    deviationPct,
    ioRatio,
    consumptionChangeRate,
    amountImpact,
    isHighDeviation,
    isIoImbalance,
    highlight: isHighDeviation || isIoImbalance,
    warningLevel,
  }
}

function buildProductGroup(name: string, rows: EnrichedUnitConsumptionRow[]): ProductGroup {
  const abnormalCount = rows.filter((r) => r.highlight).length
  const deviations = rows.map((r) => Math.abs(r.deviationPct))
  return {
    productName: name,
    rows,
    materialCount: rows.length,
    abnormalCount,
    totalAmountImpact: calcSubtotal(rows.map((r) => r.amountImpact)),
    maxDeviationPct: deviations.length ? Math.max(...deviations) : 0,
  }
}

export function useF2UnitConsumption(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const activeSegment = ref<ConsumptionSegment>('basic')
  const viewMode = ref<ConsumptionViewMode>('focus')
  const searchQuery = ref('')
  const selectedProduct = ref<string>('')
  const collapsedProducts = ref<Set<string>>(new Set())
  const rows = ref<UnitConsumptionRow[]>([emptyRow('1', '产品A')])
  const auditNote = ref('')

  function load(): void {
    const raw = readSpeRowJson(opts.allResponses.value.get(ROWS_KEY))
    if (raw) {
      try {
        const parsed = JSON.parse(raw) as UnitConsumptionRow[]
        if (parsed.length) rows.value = parsed
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
    if (!selectedProduct.value && rows.value.length) {
      selectedProduct.value = rows.value[0].productName || '未分类'
    }
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const enrichedRows = computed(() => rows.value.map(enrichUnitConsumptionRow))

  const productNames = computed(() => {
    const names = new Set<string>()
    for (const r of enrichedRows.value) {
      names.add(r.productName || '未分类')
    }
    return [...names].sort((a, b) => a.localeCompare(b, 'zh-CN'))
  })

  const productGroups = computed(() => {
    const map = new Map<string, EnrichedUnitConsumptionRow[]>()
    for (const r of enrichedRows.value) {
      const key = r.productName || '未分类'
      if (!map.has(key)) map.set(key, [])
      map.get(key)!.push(r)
    }
    return productNames.value.map((name) =>
      buildProductGroup(name, map.get(name) ?? []),
    )
  })

  const filteredProductGroups = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return productGroups.value
    return productGroups.value
      .map((g) => ({
        ...g,
        rows: g.rows.filter((r) =>
          g.productName.toLowerCase().includes(q)
          || r.materialName.toLowerCase().includes(q)
          || r.spec.toLowerCase().includes(q),
        ),
      }))
      .filter((g) => g.rows.length > 0)
  })

  const activeProductGroup = computed(() =>
    productGroups.value.find((g) => g.productName === selectedProduct.value)
    ?? productGroups.value[0]
    ?? null,
  )

  const focusRows = computed(() => {
    const g = activeProductGroup.value
    if (!g) return []
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return g.rows
    return g.rows.filter((r) =>
      r.materialName.toLowerCase().includes(q)
      || r.spec.toLowerCase().includes(q),
    )
  })

  const flatRows = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    let list = enrichedRows.value
    if (q) {
      list = list.filter((r) =>
        r.productName.toLowerCase().includes(q)
        || r.materialName.toLowerCase().includes(q)
        || r.spec.toLowerCase().includes(q),
      )
    }
    return list
  })

  const globalSummary = computed(() => ({
    productCount: productGroups.value.length,
    materialCount: enrichedRows.value.length,
    abnormalCount: enrichedRows.value.filter((r) => r.highlight).length,
    totalAmountImpact: calcSubtotal(enrichedRows.value.map((r) => r.amountImpact)),
  }))

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(ROWS_KEY),
      opts.allResponses.value.get(NOTE_KEY),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items } }))
  }

  function persist(): void {
    opts.allResponses.value.set(ROWS_KEY, {
      item_id: ROWS_KEY, conclusion: null, remark: JSON.stringify(rows.value),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function updateRow(id: string, patch: Partial<UnitConsumptionRow>): void {
    if (readonly.value) return
    rows.value = rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
    if (patch.productName && patch.productName !== selectedProduct.value) {
      selectedProduct.value = patch.productName
    }
    persist()
  }

  async function addProduct(): Promise<void> {
    if (readonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入产品名称', '新增产品', {
        confirmButtonText: '确定', cancelButtonText: '取消',
      })
      const name = value.trim()
      if (!name) return
      selectedProduct.value = name
      rows.value = [...rows.value, emptyRow(String(Date.now()), name)]
      persist()
    } catch { /* cancelled */ }
  }

  async function addMaterial(productName?: string): Promise<void> {
    if (readonly.value) return
    const product = productName ?? selectedProduct.value ?? '未分类'
    try {
      const { value } = await ElMessageBox.prompt('请输入材料名称', `新增材料 · ${product}`, {
        confirmButtonText: '确定', cancelButtonText: '取消',
      })
      rows.value = [...rows.value, { ...emptyRow(String(Date.now()), product), materialName: value }]
      selectedProduct.value = product
      persist()
    } catch { /* cancelled */ }
  }

  function removeRow(id: string): void {
    if (readonly.value || rows.value.length <= 1) return
    rows.value = rows.value.filter((r) => r.id !== id)
    persist()
  }

  function selectProduct(name: string): void {
    selectedProduct.value = name
    viewMode.value = 'focus'
  }

  function jumpToRow(row: EnrichedUnitConsumptionRow): void {
    selectedProduct.value = row.productName || '未分类'
    viewMode.value = 'focus'
  }

  function toggleCollapse(productName: string): void {
    const next = new Set(collapsedProducts.value)
    if (next.has(productName)) next.delete(productName)
    else next.add(productName)
    collapsedProducts.value = next
  }

  function expandAllProducts(): void {
    collapsedProducts.value = new Set()
  }

  function collapseAllProducts(): void {
    collapsedProducts.value = new Set(productNames.value)
  }

  function isCollapsed(productName: string): boolean {
    return collapsedProducts.value.has(productName)
  }

  function fmtRate(rate: number | '' | 'N/A'): string {
    if (rate === '' || rate === 'N/A') return '—'
    return `${(rate * 100).toFixed(1)}%`
  }

  watch(auditNote, (val) => {
    if (readonly.value) return
    opts.allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  })

  onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); flushSave() } })

  return {
    activeSegment,
    viewMode,
    searchQuery,
    selectedProduct,
    collapsedProducts,
    auditNote,
    productGroups,
    filteredProductGroups,
    activeProductGroup,
    focusRows,
    flatRows,
    globalSummary,
    updateRow,
    addProduct,
    addMaterial,
    removeRow,
    selectProduct,
    jumpToRow,
    toggleCollapse,
    expandAllProducts,
    collapseAllProducts,
    isCollapsed,
    fmtRate,
  }
}

export default useF2UnitConsumption
