/**
 * useF2ProductionSales — F2-19 存货产销量变动分析表
 *
 * 对齐 xlsx：
 * 1) 库存商品各月产量 / 销量 / 产销比
 * 2) 原材料各月采购 / 耗用 / 采购产出比 / 产耗比
 * 3) 审计说明（5问）+ 审计结论；异常波动提示索引 F2-64
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { parseNum, calcSubtotal, calcChangeRate } from './useF2InvMaiFormulaEngine'
import type { ChecklistResponse } from './useF2FormData'

export type Month12 = [
  number, number, number, number, number, number,
  number, number, number, number, number, number,
]

export const F2_MONTH_LABELS = [
  '1月', '2月', '3月', '4月', '5月', '6月',
  '7月', '8月', '9月', '10月', '11月', '12月',
] as const

export interface F2PsProductRow {
  rowId: string
  name: string
  prodMonths: Month12
  salesMonths: Month12
  prodPrior: number
  salesPrior: number
}

/** @deprecated legacy shape; prefer F2PsProductRow */
export interface F2ProductionSalesRow {
  rowId: string
  productName: string
  currentProduction: number
  priorProduction: number
  currentSales: number
  priorSales: number
  openingStock: number
  inbound: number
  outbound: number
  closingStock: number
}

export interface F2PsMaterialRow {
  rowId: string
  name: string
  /** 关联库存商品名称（1:1 假设，用于采购/产出比与产耗比） */
  linkedProduct: string
  purchaseMonths: Month12
  consumeMonths: Month12
  purchasePrior: number
  consumePrior: number
}

export interface F2PsAuditQuestions {
  q1: string
  q2: string
  q3: string
  q4: string
  q5: string
}

export interface F2PsPack {
  version: 2
  products: F2PsProductRow[]
  materials: F2PsMaterialRow[]
  questions: F2PsAuditQuestions
  auditConclusion: string
}

const STORAGE_KEY = 'F2-19-pack'
const LEGACY_ROWS_KEY = 'F2-19-rows'
const LEGACY_CONCLUSION_KEY = 'F2-19-conclusion'
const LEGACY_NOTE_KEY = 'F2-production-sales-audit-note'
const LEGACY_AUDIT_CONCLUSION_KEY = 'F2-production-sales-audit-conclusion'

export const F2_PS_QUESTION_DEFS: ReadonlyArray<{ key: keyof F2PsAuditQuestions; label: string; placeholder: string }> = [
  { key: 'q1', label: '1. 各月产量波动原因', placeholder: '说明库存商品各月产量异常波动的原因…' },
  { key: 'q2', label: '2. 库存商品同比变动原因', placeholder: '说明库存商品产量/销量相对上年度重大变动原因…' },
  { key: 'q3', label: '3. 原材料同比变动原因', placeholder: '说明原材料采购/耗用相对上年度重大变动原因…' },
  { key: 'q4', label: '4. 耗用与产量勾稽差异', placeholder: '说明采购/耗用与产量勾稽差异的原因…' },
  { key: 'q5', label: '5. 进一步分析索引（如 F2-64）', placeholder: '对波动异常的产品，进一步执行生产成本及单耗分析，索引如 wp:F2-64…' },
]

function emptyMonths(): Month12 {
  return [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
}

function rid(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

function emptyProduct(): F2PsProductRow {
  return {
    rowId: rid('f2ps-p'),
    name: '',
    prodMonths: emptyMonths(),
    salesMonths: emptyMonths(),
    prodPrior: 0,
    salesPrior: 0,
  }
}

function emptyMaterial(): F2PsMaterialRow {
  return {
    rowId: rid('f2ps-m'),
    name: '',
    linkedProduct: '',
    purchaseMonths: emptyMonths(),
    consumeMonths: emptyMonths(),
    purchasePrior: 0,
    consumePrior: 0,
  }
}

function emptyQuestions(): F2PsAuditQuestions {
  return { q1: '', q2: '', q3: '', q4: '', q5: '' }
}

function defaultPack(): F2PsPack {
  return {
    version: 2,
    products: [emptyProduct()],
    materials: [emptyMaterial()],
    questions: emptyQuestions(),
    auditConclusion: '',
  }
}

function parseMonths(raw: unknown): Month12 {
  const base = emptyMonths()
  if (!Array.isArray(raw)) return base
  for (let i = 0; i < 12; i++) base[i] = parseNum(raw[i])
  return base
}

function monthTotal(m: Month12): number {
  return calcSubtotal([...m])
}

function changePct(prior: number, current: number): number | null {
  const r = calcChangeRate(prior, current)
  if (r === '' || r === 'N/A') return null
  return r * 100
}

function safeRatio(num: number, den: number): number | null {
  if (!den) return den === 0 && num === 0 ? 0 : null
  return (num / den) * 100
}

function migrateLegacy(rowsJson: string | null | undefined, conclusion: string, note: string): F2PsPack {
  const pack = defaultPack()
  pack.auditConclusion = conclusion || ''
  if (note) pack.questions.q1 = note
  if (!rowsJson) return pack
  try {
    const arr = JSON.parse(rowsJson)
    if (!Array.isArray(arr) || !arr.length) return pack
    pack.products = arr.map((r: any) => {
      const p = emptyProduct()
      p.rowId = r.rowId || p.rowId
      p.name = String(r.productName || r.name || '')
      p.prodPrior = parseNum(r.priorProduction)
      p.salesPrior = parseNum(r.priorSales)
      // collapse annual totals into Dec as a simple migration
      p.prodMonths[11] = parseNum(r.currentProduction)
      p.salesMonths[11] = parseNum(r.currentSales)
      return p
    })
  } catch { /* ignore */ }
  return pack
}

function parsePack(jsonStr: string | null | undefined): F2PsPack | null {
  if (!jsonStr) return null
  try {
    const parsed = JSON.parse(jsonStr)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
    const base = defaultPack()
    if (Array.isArray(parsed.products) && parsed.products.length) {
      base.products = parsed.products.map((r: any) => ({
        rowId: r.rowId || rid('f2ps-p'),
        name: String(r.name || ''),
        prodMonths: parseMonths(r.prodMonths),
        salesMonths: parseMonths(r.salesMonths),
        prodPrior: parseNum(r.prodPrior),
        salesPrior: parseNum(r.salesPrior),
      }))
    }
    if (Array.isArray(parsed.materials) && parsed.materials.length) {
      base.materials = parsed.materials.map((r: any) => ({
        rowId: r.rowId || rid('f2ps-m'),
        name: String(r.name || ''),
        linkedProduct: String(r.linkedProduct || r.name || ''),
        purchaseMonths: parseMonths(r.purchaseMonths),
        consumeMonths: parseMonths(r.consumeMonths),
        purchasePrior: parseNum(r.purchasePrior),
        consumePrior: parseNum(r.consumePrior),
      }))
    }
    if (parsed.questions && typeof parsed.questions === 'object') {
      for (const k of Object.keys(base.questions) as (keyof F2PsAuditQuestions)[]) {
        if (parsed.questions[k] != null) base.questions[k] = String(parsed.questions[k])
      }
    }
    base.auditConclusion = parsed.auditConclusion != null ? String(parsed.auditConclusion) : ''
    return base
  } catch {
    return null
  }
}

export function useF2ProductionSales(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let hydrating = false
  let writing = false

  const pack = ref<F2PsPack>(defaultPack())

  function hydrate(): void {
    hydrating = true
    const fromPack = parsePack(allResponses.value.get(STORAGE_KEY)?.remark)
    if (fromPack) {
      pack.value = fromPack
    } else {
      pack.value = migrateLegacy(
        allResponses.value.get(LEGACY_ROWS_KEY)?.remark,
        allResponses.value.get(LEGACY_AUDIT_CONCLUSION_KEY)?.remark
          || allResponses.value.get(LEGACY_CONCLUSION_KEY)?.remark
          || '',
        allResponses.value.get(LEGACY_NOTE_KEY)?.remark || '',
      )
    }
    hydrating = false
  }

  watch(
    () => allResponses.value.get(STORAGE_KEY)?.remark,
    () => { if (!writing) hydrate() },
    { immediate: true },
  )

  const productViews = computed(() =>
    pack.value.products.map((r) => {
      const prodTotal = monthTotal(r.prodMonths)
      const salesTotal = monthTotal(r.salesMonths)
      const ratioMonths = r.prodMonths.map((p, i) => safeRatio(r.salesMonths[i], p)) as (number | null)[]
      const ratioTotal = safeRatio(salesTotal, prodTotal)
      const ratioPrior = safeRatio(r.salesPrior, r.prodPrior)
      return {
        ...r,
        prodTotal,
        salesTotal,
        prodChange: changePct(r.prodPrior, prodTotal),
        salesChange: changePct(r.salesPrior, salesTotal),
        ratioMonths,
        ratioTotal,
        ratioPrior,
        ratioChange: ratioPrior == null || ratioTotal == null
          ? null
          : changePct(ratioPrior, ratioTotal),
        isProdAbnormal: Math.abs(changePct(r.prodPrior, prodTotal) ?? 0) > 20,
        isSalesAbnormal: Math.abs(changePct(r.salesPrior, salesTotal) ?? 0) > 20,
      }
    }),
  )

  const materialViews = computed(() => {
    const prodByName = new Map(
      pack.value.products.map((p) => [p.name.trim(), p] as const).filter(([n]) => n),
    )
    return pack.value.materials.map((r) => {
      const purchaseTotal = monthTotal(r.purchaseMonths)
      const consumeTotal = monthTotal(r.consumeMonths)
      const linked = prodByName.get((r.linkedProduct || r.name).trim())
      const fgProd = linked?.prodMonths ?? emptyMonths()
      const fgProdTotal = linked ? monthTotal(linked.prodMonths) : 0
      const fgProdPrior = linked?.prodPrior ?? 0
      const purchaseOutRatioMonths = fgProd.map((p, i) => safeRatio(r.purchaseMonths[i], p))
      const yieldRatioMonths = r.consumeMonths.map((c, i) => safeRatio(fgProd[i], c))
      return {
        ...r,
        purchaseTotal,
        consumeTotal,
        purchaseChange: changePct(r.purchasePrior, purchaseTotal),
        consumeChange: changePct(r.consumePrior, consumeTotal),
        purchaseOutRatioMonths,
        purchaseOutRatioTotal: safeRatio(purchaseTotal, fgProdTotal),
        purchaseOutRatioPrior: safeRatio(r.purchasePrior, fgProdPrior),
        yieldRatioMonths,
        yieldRatioTotal: safeRatio(fgProdTotal, consumeTotal),
        yieldRatioPrior: safeRatio(fgProdPrior, r.consumePrior),
        isPurchaseAbnormal: Math.abs(changePct(r.purchasePrior, purchaseTotal) ?? 0) > 20,
        isConsumeAbnormal: Math.abs(changePct(r.consumePrior, consumeTotal) ?? 0) > 20,
      }
    })
  })

  const abnormalCount = computed(() => {
    let n = 0
    for (const r of productViews.value) {
      if (r.isProdAbnormal || r.isSalesAbnormal) n++
    }
    for (const r of materialViews.value) {
      if (r.isPurchaseAbnormal || r.isConsumeAbnormal) n++
    }
    return n
  })

  /** legacy aliases */
  const conclusion = computed({
    get: () => pack.value.auditConclusion,
    set: (v: string) => { if (!readonly.value) { pack.value.auditConclusion = v; persist() } },
  })
  const enrichedRows = productViews
  const activeSegment = ref<'production' | 'sales' | 'inventory'>('production')
  const useVirtualScroll = computed(() => pack.value.products.length > 100)

  function flushSave(): void {
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null }
    const item = allResponses.value.get(STORAGE_KEY)
    if (item) window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function persist(): void {
    if (hydrating || readonly.value) return
    writing = true
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: JSON.stringify(pack.value),
    })
    allResponses.value.set(LEGACY_CONCLUSION_KEY, {
      item_id: LEGACY_CONCLUSION_KEY,
      conclusion: null,
      remark: pack.value.auditConclusion,
    })
    writing = false
    debounceSave()
  }

  function addProduct(): void {
    if (readonly.value) return
    pack.value.products.push(emptyProduct())
    persist()
  }

  function removeProduct(rowId: string): void {
    if (readonly.value || pack.value.products.length <= 1) return
    pack.value.products = pack.value.products.filter((r) => r.rowId !== rowId)
    persist()
  }

  function updateProduct(
    rowId: string,
    field: 'name' | 'prodPrior' | 'salesPrior',
    value: string | number,
  ): void {
    if (readonly.value) return
    const idx = pack.value.products.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const row = { ...pack.value.products[idx] }
    if (field === 'name') row.name = String(value)
    else row[field] = parseNum(value)
    pack.value.products.splice(idx, 1, row)
    persist()
  }

  function updateProductMonth(
    rowId: string,
    kind: 'prod' | 'sales',
    monthIdx: number,
    value: number,
  ): void {
    if (readonly.value || monthIdx < 0 || monthIdx > 11) return
    const idx = pack.value.products.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const row = { ...pack.value.products[idx] }
    const key = kind === 'prod' ? 'prodMonths' : 'salesMonths'
    const months = [...row[key]] as Month12
    months[monthIdx] = parseNum(value)
    row[key] = months
    pack.value.products.splice(idx, 1, row)
    persist()
  }

  function addMaterial(): void {
    if (readonly.value) return
    pack.value.materials.push(emptyMaterial())
    persist()
  }

  function removeMaterial(rowId: string): void {
    if (readonly.value || pack.value.materials.length <= 1) return
    pack.value.materials = pack.value.materials.filter((r) => r.rowId !== rowId)
    persist()
  }

  function updateMaterial(
    rowId: string,
    field: 'name' | 'linkedProduct' | 'purchasePrior' | 'consumePrior',
    value: string | number,
  ): void {
    if (readonly.value) return
    const idx = pack.value.materials.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const row = { ...pack.value.materials[idx] }
    if (field === 'name' || field === 'linkedProduct') row[field] = String(value)
    else row[field] = parseNum(value)
    pack.value.materials.splice(idx, 1, row)
    persist()
  }

  function updateMaterialMonth(
    rowId: string,
    kind: 'purchase' | 'consume',
    monthIdx: number,
    value: number,
  ): void {
    if (readonly.value || monthIdx < 0 || monthIdx > 11) return
    const idx = pack.value.materials.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const row = { ...pack.value.materials[idx] }
    const key = kind === 'purchase' ? 'purchaseMonths' : 'consumeMonths'
    const months = [...row[key]] as Month12
    months[monthIdx] = parseNum(value)
    row[key] = months
    pack.value.materials.splice(idx, 1, row)
    persist()
  }

  function updateQuestion(key: keyof F2PsAuditQuestions, value: string): void {
    if (readonly.value) return
    pack.value.questions = { ...pack.value.questions, [key]: value }
    persist()
  }

  /** legacy API used by old UI */
  function addRow(): void { addProduct() }
  function removeRow(rowId: string): void { removeProduct(rowId) }
  function updateCell(rowId: string, field: string, value: any): void {
    if (field === 'productName') updateProduct(rowId, 'name', value)
    else if (field === 'currentProduction') updateProductMonth(rowId, 'prod', 11, value)
    else if (field === 'currentSales') updateProductMonth(rowId, 'sales', 11, value)
    else if (field === 'priorProduction') updateProduct(rowId, 'prodPrior', value)
    else if (field === 'priorSales') updateProduct(rowId, 'salesPrior', value)
  }

  function aiContext(): Record<string, unknown> {
    return {
      products: productViews.value.map((r) => ({
        name: r.name,
        prodTotal: r.prodTotal,
        salesTotal: r.salesTotal,
        prodChange: r.prodChange,
        salesChange: r.salesChange,
        ratioTotal: r.ratioTotal,
      })),
      materials: materialViews.value.map((r) => ({
        name: r.name,
        purchaseTotal: r.purchaseTotal,
        consumeTotal: r.consumeTotal,
        purchaseChange: r.purchaseChange,
        consumeChange: r.consumeChange,
      })),
      abnormalCount: abnormalCount.value,
      questions: { ...pack.value.questions },
    }
  }

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); flushSave() }
  })

  return {
    pack,
    productViews,
    materialViews,
    abnormalCount,
    questions: computed(() => pack.value.questions),
    auditConclusion: conclusion,
    conclusion,
    enrichedRows,
    activeSegment,
    useVirtualScroll,
    addProduct,
    removeProduct,
    updateProduct,
    updateProductMonth,
    addMaterial,
    removeMaterial,
    updateMaterial,
    updateMaterialMonth,
    updateQuestion,
    addRow,
    removeRow,
    updateCell,
    aiContext,
    flushSave,
    persist,
    F2_MONTH_LABELS,
    F2_PS_QUESTION_DEFS,
  }
}

export default useF2ProductionSales
