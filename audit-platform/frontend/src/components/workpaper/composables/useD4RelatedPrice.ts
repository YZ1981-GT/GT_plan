/**
 * useD4RelatedPrice — D4-21 关联方价格公允性分析 composable
 *
 * Spec: .kiro/specs/d4-operating-revenue/
 * Task: 13.1
 *
 * 职责：
 * - 对比分析表（关联vs非关联单价+差异率+结论）
 * - >10%黄色/>20%红色阈值
 * - relatedSalesTotal + proportionToRevenue computed
 * - addRow / removeRow
 *
 * Requirements: 13.1-13.8
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcPriceDiffRate,
  calcSubtotal,
  calcProportion,
} from './useD4FormulaEngine'
import type { ChecklistResponse } from './useD4FormData'
import type { UseD4BaseOptions } from './useD4Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

/**
 * D4-21 行模型 —— 字段键与后端 phase5_d4_ipo_related_sheets 契约的 json_path 逐字对齐
 * （源模板 关联方销售情况及价格分析D4-21 的 12 个受管列 A/B/C/D/E/F/G/H/J/L/M/N）。
 * I/K 差异率是模板内部 OO 公式（FORMULA_MASK），前端本地派生仅供展示、不入 store、
 * 不参与双向 projection。旧字段（relatedPrice/nonRelatedPrice/reason/…）已废弃。
 */
export interface RelatedPriceRow {
  rowId: string             // 稳定行身份（ROW_IDENTITY_STORE_KEY_D421）
  partyName: string         // A 关联方客户名称
  relationship: string      // B 关联关系
  product: string           // C 产品名称
  qty: number               // D 销售数量
  salesAmount: number       // E 销售额
  salesRatio: number        // F 销售额占同类产品销售额比例
  avgPrice: number          // G 平均单价
  nonrelatedAvgPrice: number // H 非关联方销售平均单价
  fairPrice: number         // J 可比公允价格
  priorSalesRatio: number   // L 上年度销售额占比
  priorAvgPrice: number     // M 上年度销售平均单价
  remark: string            // N 备注
  // 展示派生（不持久化、不进 projection）：I=(G-H)/H、K=(G-J)/J
  priceDiffRate?: number
  fairDiffRate?: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'D4-21-rows'
const NOTE_KEY = 'D4-21-note'
const CONCLUSION_KEY = 'D4-21-conclusion'
const YELLOW_THRESHOLD = 10  // >10% 黄色
const RED_THRESHOLD = 20     // >20% 红色

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD4RelatedPrice(options: UseD4BaseOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Rows ─────────────────────────────────────────────────────────────

  const rows = ref<RelatedPriceRow[]>([])

  /** 差异率派生（I=(G-H)/H、K=(G-J)/J，展示用，不持久化）。 */
  function withDerived(r: RelatedPriceRow): RelatedPriceRow {
    return {
      ...r,
      priceDiffRate: calcPriceDiffRate(parseNum(r.avgPrice), parseNum(r.nonrelatedAvgPrice)),
      fairDiffRate: calcPriceDiffRate(parseNum(r.avgPrice), parseNum(r.fairPrice)),
    }
  }

  function loadRows(): void {
    const resp = allResponses.value.get(STORAGE_KEY)
    const parsed = safeParseRows<RelatedPriceRow>(resp?.remark)
    rows.value = parsed.map(withDerived)
  }

  watch(
    () => allResponses.value.get(STORAGE_KEY)?.remark,
    () => loadRows(),
    { immediate: true },
  )

  // ─── Thresholds ───────────────────────────────────────────────────────

  /** Get color class for a diff rate: >20% red, >10% yellow, else '' */
  function getDiffRateColor(rate: number): 'red' | 'yellow' | '' {
    const absRate = Math.abs(rate)
    if (absRate > RED_THRESHOLD) return 'red'
    if (absRate > YELLOW_THRESHOLD) return 'yellow'
    return ''
  }

  // ─── Computed: relatedSalesTotal + proportionToRevenue ────────────────

  const relatedSalesTotal = computed<number>(() => {
    // 关联方销售合计 = Σ 销售额（E 列 salesAmount）
    return calcSubtotal(rows.value.map(r => parseNum(r.salesAmount)))
  })

  const proportionToRevenue = computed<number>(() => {
    // 🔴 Req 3.3：不得读旧键 `D4-1-adj-tb-6001`。营业收入审定数改由 Wave4 的
    // wp_formula/four_table（D4-1 canonical snapshot，6001）下发到 allResponses 的
    // 规范键；此处先读规范键，缺失时返 0（宁缺勿造），不回退旧键。
    const auditedResp = allResponses.value.get('D4-21-revenue-audited')
    const totalRevenue = parseNum(auditedResp?.remark)
    return calcProportion(relatedSalesTotal.value, totalRevenue)
  })

  // ─── Audit Note / Conclusion ──────────────────────────────────────────

  const auditNote = ref('')
  const auditConclusion = ref('')

  watch(
    () => allResponses.value.get(NOTE_KEY)?.remark,
    (val) => { auditNote.value = val || '' },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(CONCLUSION_KEY)?.remark,
    (val) => { auditConclusion.value = val || '' },
    { immediate: true },
  )

  watch(auditNote, (val) => {
    allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    debounceSave()
  })

  watch(auditConclusion, (val) => {
    allResponses.value.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
    debounceSave()
  })

  // ─── Row Operations ───────────────────────────────────────────────────

  function addRow(): void {
    if (readonly.value) return
    rows.value.push({
      rowId: generateRowId(),
      partyName: '',
      relationship: '',
      product: '',
      qty: 0,
      salesAmount: 0,
      salesRatio: 0,
      avgPrice: 0,
      nonrelatedAvgPrice: 0,
      fairPrice: 0,
      priorSalesRatio: 0,
      priorAvgPrice: 0,
      remark: '',
      priceDiffRate: 0,
      fairDiffRate: 0,
    })
    persistRows()
  }

  function removeRow(rowId: string): void {
    if (readonly.value) return
    rows.value = rows.value.filter(r => r.rowId !== rowId)
    persistRows()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (readonly.value) return
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    // 单价类字段变化时重算差异率派生（I=(G-H)/H、K=(G-J)/J）
    if (field === 'avgPrice' || field === 'nonrelatedAvgPrice' || field === 'fairPrice') {
      row.priceDiffRate = calcPriceDiffRate(parseNum(row.avgPrice), parseNum(row.nonrelatedAvgPrice))
      row.fairDiffRate = calcPriceDiffRate(parseNum(row.avgPrice), parseNum(row.fairPrice))
    }
    persistRows()
  }

  // ─── Persistence ──────────────────────────────────────────────────────

  function persistRows(): void {
    // 派生字段（priceDiffRate/fairDiffRate = I/K 内部公式）不落 store：它们是模板
    // FORMULA_MASK 列，双向 projection 不覆盖，前端仅本地展示。
    const clean = rows.value.map(({ priceDiffRate: _p, fairDiffRate: _f, ...keep }) => keep)
    const json = JSON.stringify(clean)
    allResponses.value.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: json })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function flushSave(): void {
    try {
      const items = [STORAGE_KEY, NOTE_KEY, CONCLUSION_KEY]
        .map(k => allResponses.value.get(k))
        .filter(Boolean)
      window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items } }))
    } catch { /* silent */ }
  }

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    rows,
    relatedSalesTotal,
    proportionToRevenue,
    auditNote,
    auditConclusion,
    getDiffRateColor,
    addRow,
    removeRow,
    updateCell,
  }
}

export default useD4RelatedPrice
