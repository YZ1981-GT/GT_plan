/**
 * useF2RelatedPartyPricing — F2-65 询价函 / F2-66 市场价 关联方定价核查
 */
import { ref, computed, watch, onBeforeUnmount, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { calcPriceDeviation } from './useF2SpecialFormulaEngine'
import { readSpeRowJson, type ChecklistResponse } from './useF2SpecialFormData'

export type RelatedPartyPricingKind = 'inquiry' | 'market'

export const PRICING_CONCLUSIONS = ['公允', '基本公允', '不公允', '待核实'] as const
export type PricingConclusion = typeof PRICING_CONCLUSIONS[number]

export interface InquiryPricingRow {
  id: string
  relatedParty: string
  itemName: string
  relatedPrice: number
  thirdPartyName: string
  inquiryPrice: number
  conclusion: PricingConclusion | ''
  remark: string
}

export interface MarketPricingRow {
  id: string
  relatedParty: string
  itemName: string
  relatedPrice: number
  marketPrice: number
  conclusion: PricingConclusion | ''
  remark: string
}

export type RelatedPartyPricingRow = InquiryPricingRow | MarketPricingRow

export interface EnrichedInquiryRow extends InquiryPricingRow {
  spreadPct: number | 'N/A'
  isHighSpread: boolean
  highlight: boolean
}

export interface EnrichedMarketRow extends MarketPricingRow {
  spreadPct: number | 'N/A'
  isHighSpread: boolean
  highlight: boolean
}

const SPREAD_THRESHOLD = 0.1
const KEYS: Record<RelatedPartyPricingKind, { rows: string; note: string }> = {
  inquiry: { rows: 'F2-65-rows', note: 'F2-65-note' },
  market: { rows: 'F2-66-rows', note: 'F2-66-note' },
}

function emptyInquiry(id: string): InquiryPricingRow {
  return {
    id, relatedParty: '', itemName: '', relatedPrice: 0,
    thirdPartyName: '', inquiryPrice: 0, conclusion: '', remark: '',
  }
}

function emptyMarket(id: string): MarketPricingRow {
  return {
    id, relatedParty: '', itemName: '', relatedPrice: 0,
    marketPrice: 0, conclusion: '', remark: '',
  }
}

export function enrichInquiryRow(r: InquiryPricingRow): EnrichedInquiryRow {
  const spread = calcPriceDeviation(r.relatedPrice, r.inquiryPrice)
  const spreadPct = spread === 'N/A' ? 'N/A' : spread * 100
  const isHighSpread = typeof spread === 'number' && Math.abs(spread) > SPREAD_THRESHOLD
  return { ...r, spreadPct, isHighSpread, highlight: isHighSpread }
}

export function enrichMarketRow(r: MarketPricingRow): EnrichedMarketRow {
  const spread = calcPriceDeviation(r.relatedPrice, r.marketPrice)
  const spreadPct = spread === 'N/A' ? 'N/A' : spread * 100
  const isHighSpread = typeof spread === 'number' && Math.abs(spread) > SPREAD_THRESHOLD
  return { ...r, spreadPct, isHighSpread, highlight: isHighSpread }
}

export function useF2RelatedPartyPricing(opts: {
  kind: Ref<RelatedPartyPricingKind>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}) {
  const readonly = opts.isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const searchQuery = ref('')
  const inquiryRows = ref<InquiryPricingRow[]>([emptyInquiry('1')])
  const marketRows = ref<MarketPricingRow[]>([emptyMarket('1')])
  const auditNote = ref('')

  const storageKeys = computed(() => KEYS[opts.kind.value])

  function load(): void {
    const { rows: rowsKey, note: noteKey } = storageKeys.value
    const raw = readSpeRowJson(opts.allResponses.value.get(rowsKey))
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        if (opts.kind.value === 'inquiry' && parsed.length) inquiryRows.value = parsed
        if (opts.kind.value === 'market' && parsed.length) marketRows.value = parsed
      } catch { /* ignore */ }
    }
    auditNote.value = opts.allResponses.value.get(noteKey)?.remark || ''
  }

  watch(() => opts.allResponses.value.get(storageKeys.value.rows)?.remark, load, { immediate: true })
  watch(() => opts.kind.value, load)

  const enrichedInquiryRows = computed(() => inquiryRows.value.map(enrichInquiryRow))
  const enrichedMarketRows = computed(() => marketRows.value.map(enrichMarketRow))

  const enrichedRows = computed(() =>
    opts.kind.value === 'inquiry' ? enrichedInquiryRows.value : enrichedMarketRows.value,
  )

  const filteredRows = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return enrichedRows.value
    return enrichedRows.value.filter((r) =>
      r.relatedParty.toLowerCase().includes(q)
      || r.itemName.toLowerCase().includes(q),
    )
  })

  const abnormalCount = computed(() => enrichedRows.value.filter((r) => r.isHighSpread).length)

  const unfairCount = computed(() =>
    enrichedRows.value.filter((r) => r.conclusion === '不公允' || r.conclusion === '待核实').length,
  )

  function flushSave(): void {
    const { rows: rowsKey, note: noteKey } = storageKeys.value
    const items = [
      opts.allResponses.value.get(rowsKey),
      opts.allResponses.value.get(noteKey),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items } }))
  }

  function persist(): void {
    const { rows: rowsKey } = storageKeys.value
    const payload = opts.kind.value === 'inquiry'
      ? JSON.stringify(inquiryRows.value)
      : JSON.stringify(marketRows.value)
    opts.allResponses.value.set(rowsKey, { item_id: rowsKey, conclusion: null, remark: payload })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function updateInquiry(id: string, patch: Partial<InquiryPricingRow>): void {
    if (readonly.value) return
    inquiryRows.value = inquiryRows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
    persist()
  }

  function updateMarket(id: string, patch: Partial<MarketPricingRow>): void {
    if (readonly.value) return
    marketRows.value = marketRows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
    persist()
  }

  async function addRow(): Promise<void> {
    if (readonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入关联方名称', '新增核查行', {
        confirmButtonText: '确定', cancelButtonText: '取消',
      })
      if (opts.kind.value === 'inquiry') {
        inquiryRows.value = [...inquiryRows.value, { ...emptyInquiry(String(Date.now())), relatedParty: value }]
      } else {
        marketRows.value = [...marketRows.value, { ...emptyMarket(String(Date.now())), relatedParty: value }]
      }
      persist()
    } catch { /* cancelled */ }
  }

  function removeRow(id: string): void {
    if (readonly.value) return
    if (opts.kind.value === 'inquiry') {
      if (inquiryRows.value.length <= 1) return
      inquiryRows.value = inquiryRows.value.filter((r) => r.id !== id)
    } else {
      if (marketRows.value.length <= 1) return
      marketRows.value = marketRows.value.filter((r) => r.id !== id)
    }
    persist()
  }

  function fmtSpread(v: number | 'N/A'): string {
    if (v === 'N/A') return '—'
    return `${v.toFixed(1)}%`
  }

  watch(auditNote, (val) => {
    if (readonly.value) return
    const { note: noteKey } = storageKeys.value
    opts.allResponses.value.set(noteKey, { item_id: noteKey, conclusion: null, remark: val })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  })

  onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); flushSave() } })

  return {
    searchQuery,
    filteredRows,
    abnormalCount,
    unfairCount,
    auditNote,
    updateInquiry,
    updateMarket,
    addRow,
    removeRow,
    fmtSpread,
    PRICING_CONCLUSIONS,
  }
}

export default useF2RelatedPartyPricing
