/**
 * useN2OtherTaxCalc — N2-8 其他税费测算表 (自动行 + 手工行 + 差额)
 *
 * 对齐源模板：各税种一行 (NOT 逐月)，列 =
 *   税种 | 应税项目 | 计税依据 | 适用税率 | 应交税额(测算) | 账面计提数 | 差额 | 备注
 *
 * 3 个 AUTO 行 (城建税及附加，随增值税+消费税自动测算)：
 *   - 城建税        计税依据 = 应交增值税(N2-6) + 消费税；税率 市区7%/县城5%/其他1%
 *   - 教育费附加    同计税依据；税率 3%
 *   - 地方教育附加  同计税依据；税率 2%
 *   应交税额(测算) = calcSurtax(增值税, 消费税, 税率)
 *
 * 4 个 MANUAL 行 (用户录入)：消费税 / 资源税 / 城镇土地使用税 / 车船税
 *   计税依据 + 税率/单位税额 手工录入；应交税额 手工 或 = 计税依据 × 税率
 *
 * 差额 = 应交税额(测算) − 账面计提数 (auto，≠0 时组件标红)。
 *
 * 联动：同步至 N2-1 审定表 + EventBus 'tax-accrual:updated' 供 N4 消费。
 *
 * 持久化：
 *   - N2-8-manual-rows       JSON 数组 (4 手工行，含账面计提数)  ← 进度检测键
 *   - N2-8-urban-area-type   城建税地区
 *   - N2-8-consumption-tax   消费税应交额 (驱动城建税及附加计税依据)
 *   - N2-8-auto-book         3 自动行账面计提数
 *
 * 引擎复用：calcSurtax (useN2MultiTaxEngine) / calcSubtotal / calcDiff (useN2FormulaEngine)。
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { calcSurtax } from './useN2MultiTaxEngine'
import { calcSubtotal, calcDiff } from './useN2FormulaEngine'
import type { ChecklistResponse } from './useN2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 城建税地区类型 */
export type UrbanAreaType = '市区' | '县城' | '其他'

/** 城建税地区→税率映射 */
export const URBAN_RATE_MAP: Record<UrbanAreaType, number> = {
  '市区': 0.07,
  '县城': 0.05,
  '其他': 0.01,
}

/** 免征月销售额阈值(元) — 保留导出兼容 */
export const EXEMPTION_THRESHOLD = 100000

/** 同比变动率高亮阈值 — 保留导出兼容 */
export const VARIANCE_THRESHOLD = 0.30

/** 测算行类型 */
export type CalcRowKind = 'auto' | 'manual'

/** 测算表单行 (合并后 allCalcRows 元素) */
export interface CalcRow {
  /** 稳定 key */
  key: string
  /** 税种名称 */
  taxType: string
  /** 应税项目 (auto行为固定文案；manual行可编辑) */
  taxItem: string
  /** 行类型 */
  kind: CalcRowKind
  /** 计税依据 */
  taxBase: number
  /** 适用税率 */
  rate: number
  /** 应交税额(测算) */
  computed: number
  /** 账面计提数 */
  bookAccrued: number
  /** 差额 = 应交税额(测算) − 账面计提数 */
  diff: number
  /** 备注 */
  remark: string
}

/** 手工行持久化模型 */
export interface ManualTaxRow {
  taxType: string
  taxItem: string
  taxBase: number
  rate: number
  /** 直接录入的应交额 (>0 时优先于 计税依据×税率) */
  amountManual: number
  bookAccrued: number
  remark: string
}

/** 3 自动行汇总 */
export interface SurtaxSummary {
  taxBase: number
  urbanTax: number
  educationTax: number
  localEducationTax: number
  totalSurtax: number
  total: number
}

// ─── Backward-compat type aliases (旧 12 月结构已移除) ─────────────────────────

/** @deprecated 旧逐月结构已移除，使用 CalcRow */
export type MonthlyTaxRow = CalcRow
/** @deprecated 旧季度汇总已移除 */
export type QuarterSummary = CalcRow
/** @deprecated 旧年度汇总已移除，使用 SurtaxSummary */
export type AnnualSummary = SurtaxSummary
/** @deprecated 旧同比预警已移除 */
export interface VarianceWarning {
  taxType: string
  rate: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const EDUCATION_RATE = 0.03
const LOCAL_EDUCATION_RATE = 0.02

const MANUAL_ROWS_ITEM_ID = 'N2-8-manual-rows'
const AUTO_BOOK_ITEM_ID = 'N2-8-auto-book'
const CONSUMPTION_TAX_ITEM_ID = 'N2-8-consumption-tax'
const URBAN_AREA_ITEM_ID = 'N2-8-urban-area-type'

/** 4 个默认手工行税种 */
const DEFAULT_MANUAL_TAX_TYPES = ['消费税', '资源税', '城镇土地使用税', '车船税'] as const

const SURTAX_TYPES = ['城建税', '教育费附加', '地方教育附加'] as const
type SurtaxBookKey = 'urban' | 'education' | 'localEducation'
const SURTAX_BOOK_KEY: Record<string, SurtaxBookKey> = {
  '城建税': 'urban',
  '教育费附加': 'education',
  '地方教育附加': 'localEducation',
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function round2(v: number): number {
  return parseFloat((Number.isFinite(v) ? v : 0).toFixed(2))
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseN2OtherTaxCalcOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  /** 通用 itemId 保存 (formData.saveField) */
  saveField: (itemId: string, value: { conclusion?: string; remark?: string }) => Promise<void>
  /** 按 sheet+field 读取 (formData.getField) */
  getField: (sheet: string, field: string) => any
}

export function useN2OtherTaxCalc(options: UseN2OtherTaxCalcOptions) {
  const { allResponses, saveField, getField } = options

  // ─── 读取 JSON conclusion 辅助 ─────────────────────────────────────────────
  function readJson(itemId: string): any {
    const resp = allResponses.value.get(itemId)
    if (!resp?.conclusion) return null
    try { return JSON.parse(resp.conclusion) } catch { return resp.conclusion }
  }

  // ─── 1. 城建税地区 ─────────────────────────────────────────────────────────
  const urbanAreaType: ComputedRef<UrbanAreaType> = computed(() => {
    const stored = getField('8', 'urban-area-type')
    if (stored === '县城' || stored === '其他') return stored
    return '市区'
  })

  const urbanRate: ComputedRef<number> = computed(() => URBAN_RATE_MAP[urbanAreaType.value])

  // ─── 2. 增值税应交 (from N2-6) ────────────────────────────────────────────
  const vatPayable: ComputedRef<number> = computed(() => {
    const resp = allResponses.value.get('N2-6-vat-payable')
    if (resp?.conclusion) {
      try { return parseNum(JSON.parse(resp.conclusion)) } catch { return parseNum(resp.conclusion) }
    }
    if (resp?.remark != null) return parseNum(resp.remark)
    return 0
  })

  // ─── 3. 手工行 (4 行) ──────────────────────────────────────────────────────
  const manualRows: ComputedRef<ManualTaxRow[]> = computed(() => {
    let stored: any[] = []
    const parsed = readJson(MANUAL_ROWS_ITEM_ID)
    if (Array.isArray(parsed)) stored = parsed

    // 以默认税种为骨架合并保存值；保存值中多出的行 (addManualRow) 追加保留
    const base = DEFAULT_MANUAL_TAX_TYPES.map((taxType, idx) => {
      const saved = stored[idx] || stored.find(r => r?.taxType === taxType)
      return normalizeManualRow(saved, taxType)
    })
    const extras = stored
      .slice(DEFAULT_MANUAL_TAX_TYPES.length)
      .map(r => normalizeManualRow(r, r?.taxType || '其他税种'))
    return [...base, ...extras]
  })

  function normalizeManualRow(saved: any, taxType: string): ManualTaxRow {
    return {
      taxType: (saved?.taxType as string) || taxType,
      taxItem: (saved?.taxItem as string) ?? '',
      taxBase: parseNum(saved?.taxBase),
      rate: parseNum(saved?.rate),
      amountManual: parseNum(saved?.amountManual),
      bookAccrued: parseNum(saved?.bookAccrued),
      remark: (saved?.remark as string) ?? '',
    }
  }

  // ─── 4. 自动行账面计提 ─────────────────────────────────────────────────────
  const autoBook: ComputedRef<{ urban: number; education: number; localEducation: number }> = computed(() => {
    const parsed = readJson(AUTO_BOOK_ITEM_ID)
    if (parsed && typeof parsed === 'object') {
      return {
        urban: parseNum(parsed.urban),
        education: parseNum(parsed.education),
        localEducation: parseNum(parsed.localEducation),
      }
    }
    return { urban: 0, education: 0, localEducation: 0 }
  })

  // ─── 5. 消费税 (驱动城建税及附加计税依据) ──────────────────────────────────
  /** 消费税应交额：优先 N2-8-consumption-tax，回退 消费税 手工行的应交测算 */
  const consumptionTaxAmount: ComputedRef<number> = computed(() => {
    const dedicated = readJson(CONSUMPTION_TAX_ITEM_ID)
    if (dedicated != null && dedicated !== '') return parseNum(dedicated)
    const row = manualRows.value.find(r => r.taxType === '消费税')
    if (!row) return 0
    return row.amountManual > 0 ? round2(row.amountManual) : round2(row.taxBase * row.rate)
  })

  /** 城建税及附加计税依据 = 应交增值税 + 消费税 */
  const taxBase: ComputedRef<number> = computed(() => round2(vatPayable.value + consumptionTaxAmount.value))
  /** 兼容旧命名 */
  const surtaxBase = taxBase

  // ─── 6. 自动行 (3 行) ──────────────────────────────────────────────────────
  const autoRows: ComputedRef<CalcRow[]> = computed(() => {
    const base = taxBase.value
    const book = autoBook.value
    const vat = vatPayable.value
    const consumption = consumptionTaxAmount.value
    const defs: Array<{ key: string; taxType: string; rate: number; book: number }> = [
      { key: 'auto-urban', taxType: '城建税', rate: urbanRate.value, book: book.urban },
      { key: 'auto-education', taxType: '教育费附加', rate: EDUCATION_RATE, book: book.education },
      { key: 'auto-local-education', taxType: '地方教育附加', rate: LOCAL_EDUCATION_RATE, book: book.localEducation },
    ]
    return defs.map(d => {
      const computedAmt = round2(calcSurtax(vat, consumption, d.rate))
      return {
        key: d.key,
        taxType: d.taxType,
        taxItem: '应交增值税＋消费税',
        kind: 'auto' as const,
        taxBase: base,
        rate: d.rate,
        computed: computedAmt,
        bookAccrued: d.book,
        diff: round2(calcDiff(computedAmt, d.book)),
        remark: '',
      }
    })
  })

  // ─── 7. 手工行 → CalcRow ───────────────────────────────────────────────────
  const manualCalcRows: ComputedRef<CalcRow[]> = computed(() => {
    return manualRows.value.map((r, idx) => {
      const computedAmt = r.amountManual > 0 ? round2(r.amountManual) : round2(r.taxBase * r.rate)
      return {
        key: `manual-${idx}`,
        taxType: r.taxType,
        taxItem: r.taxItem,
        kind: 'manual' as const,
        taxBase: r.taxBase,
        rate: r.rate,
        computed: computedAmt,
        bookAccrued: r.bookAccrued,
        diff: round2(calcDiff(computedAmt, r.bookAccrued)),
        remark: r.remark,
      }
    })
  })

  // ─── 8. 合并行 ─────────────────────────────────────────────────────────────
  const allCalcRows: ComputedRef<CalcRow[]> = computed(() => [...autoRows.value, ...manualCalcRows.value])

  // ─── 9. 汇总 (3 自动行) ────────────────────────────────────────────────────
  const annualSummary: ComputedRef<SurtaxSummary> = computed(() => {
    const urban = autoRows.value.find(r => r.taxType === '城建税')?.computed ?? 0
    const education = autoRows.value.find(r => r.taxType === '教育费附加')?.computed ?? 0
    const localEducation = autoRows.value.find(r => r.taxType === '地方教育附加')?.computed ?? 0
    const totalSurtax = calcSubtotal([urban, education, localEducation])
    const total = calcSubtotal(allCalcRows.value.map(r => r.computed))
    return {
      taxBase: taxBase.value,
      urbanTax: urban,
      educationTax: education,
      localEducationTax: localEducation,
      totalSurtax: round2(totalSurtax),
      total: round2(total),
    }
  })
  /** 兼容别名 */
  const summary = annualSummary

  /** 存在差额的行 */
  const diffRows: ComputedRef<CalcRow[]> = computed(() =>
    allCalcRows.value.filter(r => Math.abs(r.diff) > 0.01),
  )

  // ─── 10. Actions ───────────────────────────────────────────────────────────
  /** 设置城建税地区 */
  async function setUrbanAreaType(area: UrbanAreaType): Promise<void> {
    await saveField(URBAN_AREA_ITEM_ID, { conclusion: JSON.stringify(area) })
  }

  /** 录入消费税应交额 (写专用键 + 同步 消费税 手工行) */
  async function setConsumptionTax(value: number): Promise<void> {
    const v = parseNum(value)
    await saveField(CONSUMPTION_TAX_ITEM_ID, { conclusion: JSON.stringify(v) })
    // 同步到 消费税 手工行的 amountManual，保持表格一致
    const idx = manualRows.value.findIndex(r => r.taxType === '消费税')
    if (idx >= 0) {
      await updateManualRow(idx, 'amountManual', v)
    }
  }

  /** 更新账面计提数 (按税种路由：3 自动行 → auto-book；手工行 → manual bookAccrued) */
  async function setBookAccrual(taxType: string, value: number): Promise<void> {
    const bookKey = SURTAX_BOOK_KEY[taxType]
    if (bookKey) {
      const next = { ...autoBook.value, [bookKey]: parseNum(value) }
      await saveField(AUTO_BOOK_ITEM_ID, { conclusion: JSON.stringify(next) })
      return
    }
    const idx = manualRows.value.findIndex(r => r.taxType === taxType)
    if (idx >= 0) await updateManualRow(idx, 'bookAccrued', value)
  }

  /** 更新手工行字段 */
  async function updateManualRow(index: number, field: keyof ManualTaxRow, value: any): Promise<void> {
    const current = manualRows.value.map(r => ({ ...r }))
    if (!current[index]) return
    if (field === 'taxType' || field === 'taxItem' || field === 'remark') {
      current[index][field] = String(value ?? '')
    } else {
      current[index][field] = parseNum(value) as never
    }
    await saveField(MANUAL_ROWS_ITEM_ID, { conclusion: JSON.stringify(current) })
  }

  /** @deprecated 旧命名，使用 updateManualRow */
  const setManualRow = updateManualRow

  /** 追加一个手工行 */
  async function addManualRow(taxType = '其他税种'): Promise<void> {
    const current = manualRows.value.map(r => ({ ...r }))
    current.push({ taxType, taxItem: '', taxBase: 0, rate: 0, amountManual: 0, bookAccrued: 0, remark: '' })
    await saveField(MANUAL_ROWS_ITEM_ID, { conclusion: JSON.stringify(current) })
  }

  /** 触发从 N2-6 重新读取 (vatPayable 为响应式 computed，此处仅占位) */
  function importFromN26(): void {
    // vatPayable 通过 allResponses 响应式获取，无需手动同步
  }

  /** 同步城建税及附加至 N2-1 审定表 + emit tax-accrual:updated 供 N4 */
  async function syncToAdjudication(): Promise<void> {
    const s = annualSummary.value
    await saveField('N2-8-surtax-urban', { conclusion: JSON.stringify(s.urbanTax) })
    await saveField('N2-8-surtax-education', { conclusion: JSON.stringify(s.educationTax) })
    await saveField('N2-8-surtax-local-education', { conclusion: JSON.stringify(s.localEducationTax) })
    await saveField('N2-8-surtax-total', { conclusion: JSON.stringify(s.totalSurtax) })
    eventBus.emit('tax-accrual:updated', {
      wpCode: 'N2',
      source: 'N2-8',
      urbanTax: s.urbanTax,
      educationTax: s.educationTax,
      localEducationTax: s.localEducationTax,
      total: s.totalSurtax,
    })
  }

  // ─── Return ────────────────────────────────────────────────────────────────
  return {
    // State
    urbanAreaType,
    urbanRate,
    vatPayable,
    taxBase,
    surtaxBase,
    consumptionTaxAmount,
    // Rows
    autoRows,
    manualRows,
    manualCalcRows,
    allCalcRows,
    autoBook,
    // Summary
    annualSummary,
    summary,
    diffRows,
    // Actions
    setUrbanAreaType,
    setConsumptionTax,
    setBookAccrual,
    updateManualRow,
    setManualRow,
    addManualRow,
    importFromN26,
    syncToAdjudication,
  }
}

export default useN2OtherTaxCalc
