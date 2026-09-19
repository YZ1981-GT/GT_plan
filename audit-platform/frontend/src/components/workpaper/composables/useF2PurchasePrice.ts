/**
 * useF2PurchasePrice — F2-61 原材料采购价格分析（对齐致同源模板：四区块矩阵）
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'
import {
  defaultPurchasePriceSheet,
  enrichPurchaseMaterials,
  calcPurchasePriceTotals,
  migratePurchasePriceSheet,
  emptyPurchaseMaterial,
  isBlankPurchaseMaterial,
  PURCHASE_MONTH_LABELS,
  type PurchasePriceSheet,
  type PurchasePriceMaterial,
  type PurchaseMonthCell,
  type PurchasePriceTotals,
} from './useF2PurchasePriceFormulas'

export { PURCHASE_MONTH_LABELS }
export type {
  PurchasePriceMaterial,
  EnrichedPurchaseMaterial,
} from './useF2PurchasePriceFormulas'

const ROWS_KEY = 'F2-61-rows'
const NOTE_KEY = 'F2-61-note'
const NOTE_MARKET_KEY = 'F2-61-note-market'

export function useF2PurchasePrice(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const sheet = ref<PurchasePriceSheet>(defaultPurchasePriceSheet())
  /** 审计说明1：月度采购单价变动较大的原因 */
  const varianceNote = ref('')
  /** 审计说明2：采购单价与市场价格差异较大原因 */
  const marketNote = ref('')

  function flushSave(): void {
    const items = [
      opts.allResponses.value.get(ROWS_KEY),
      opts.allResponses.value.get(NOTE_KEY),
      opts.allResponses.value.get(NOTE_MARKET_KEY),
    ].filter(Boolean)
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items } }))
    }
  }

  function load(): void {
    const raw = readSpeRowJson(opts.allResponses.value.get(ROWS_KEY))
    // 自回声守卫：persist() 写回后 watcher 再次触发时内容一致则跳过，
    // 避免 migrate 的空行裁剪吃掉刚新增的空行。
    if (raw && raw === JSON.stringify(sheet.value)) return
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        const migrated = migratePurchasePriceSheet(parsed)
        const beforeCount = Array.isArray(parsed)
          ? parsed.length
          : (Array.isArray(parsed?.materials) ? parsed.materials.length : 0)
        sheet.value = migrated
        // 迁移裁掉历史预留空行或旧格式升级后立即写回，刷新不再出现
        const upgraded = Array.isArray(parsed)
        if (!readonly.value && (upgraded || beforeCount > migrated.materials.length)) {
          opts.allResponses.value.set(ROWS_KEY, {
            item_id: ROWS_KEY,
            conclusion: null,
            remark: JSON.stringify(migrated),
          })
          if (debounceTimer) clearTimeout(debounceTimer)
          debounceTimer = setTimeout(() => {
            debounceTimer = null
            flushSave()
          }, 300)
        }
      } catch { /* ignore */ }
    }
    varianceNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
    marketNote.value = opts.allResponses.value.get(NOTE_MARKET_KEY)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(ROWS_KEY)?.remark, load, { immediate: true })

  const enrichedMaterials = computed(() => enrichPurchaseMaterials(sheet.value.materials))

  const columnTotals = computed<PurchasePriceTotals>(() =>
    calcPurchasePriceTotals(enrichedMaterials.value),
  )

  const filledCount = computed(() =>
    sheet.value.materials.filter((r) => !isBlankPurchaseMaterial(r)).length,
  )
  const varianceCount = computed(() =>
    enrichedMaterials.value.filter((r) => r.hasMonthlyVariance).length,
  )
  const marketDiffCount = computed(() =>
    enrichedMaterials.value.filter((r) => r.hasMarketDiff).length,
  )

  function persist(): void {
    if (readonly.value) return
    opts.allResponses.value.set(ROWS_KEY, {
      item_id: ROWS_KEY,
      conclusion: null,
      remark: JSON.stringify(sheet.value),
    })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function updateMaterial(id: string, patch: Partial<PurchasePriceMaterial>): void {
    if (readonly.value) return
    sheet.value = {
      materials: sheet.value.materials.map((r) => (r.id === id ? { ...r, ...patch } : r)),
    }
    persist()
  }

  function updateMonth(id: string, monthIndex: number, patch: Partial<PurchaseMonthCell>): void {
    if (readonly.value) return
    sheet.value = {
      materials: sheet.value.materials.map((r) => {
        if (r.id !== id) return r
        const months = r.months.map((m, i) => (i === monthIndex ? { ...m, ...patch } : m))
        return { ...r, months }
      }),
    }
    persist()
  }

  function updatePriorEnd(id: string, patch: Partial<PurchaseMonthCell>): void {
    if (readonly.value) return
    sheet.value = {
      materials: sheet.value.materials.map((r) =>
        r.id === id ? { ...r, priorEnd: { ...r.priorEnd, ...patch } } : r,
      ),
    }
    persist()
  }

  function addMaterial(): void {
    if (readonly.value) return
    sheet.value = {
      materials: [...sheet.value.materials, emptyPurchaseMaterial()],
    }
    persist()
  }

  function removeMaterial(id: string): void {
    if (readonly.value || sheet.value.materials.length <= 1) return
    sheet.value = {
      materials: sheet.value.materials.filter((r) => r.id !== id),
    }
    persist()
  }

  function watchNote(source: Ref<string>, key: string): void {
    watch(source, (val) => {
      if (readonly.value) return
      opts.allResponses.value.set(key, { item_id: key, conclusion: null, remark: val })
      if (debounceTimer) clearTimeout(debounceTimer)
      debounceTimer = setTimeout(() => {
        debounceTimer = null
        flushSave()
      }, 2000)
    })
  }
  watchNote(varianceNote, NOTE_KEY)
  watchNote(marketNote, NOTE_MARKET_KEY)

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      flushSave()
    }
  })

  return {
    sheet,
    enrichedMaterials,
    columnTotals,
    filledCount,
    varianceCount,
    marketDiffCount,
    varianceNote,
    marketNote,
    updateMaterial,
    updateMonth,
    updatePriorEnd,
    addMaterial,
    removeMaterial,
  }
}

export default useF2PurchasePrice
