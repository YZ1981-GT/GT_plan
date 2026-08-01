/**
 * useN2VatSourceCalc — N2-6 增值税测算表「源模板四段」数据层
 *
 * Spec: .kiro/specs/n2-vat-calc-source-alignment/
 * Tasks: 2.1（一 申报表核对）/ 2.2（二 销项测算）/ 2.3（三 进项测算）/ 2.4（四 特殊情况 + R6 联动）
 * Requirements: 1.1-1.5, 2.1-2.6, 3.1-3.5, 4.1-4.3, 6.1-6.3
 *
 * 权威依据见 `useN2VatSourceEngine.ts` 头注释（源模板 `增值税测算表N2-6` A1:H48 逐格实证）。
 *
 * 设计要点：
 * - **派生列一律读时推导、禁持久化**：计税收入 D / 应计销项税 F / 测算数 F / 差异 E·F30·F39 /
 *   各合计 全部由 computed 现算；`_currentRaw()` 物化的落库形状只含录入列。
 * - **跨段引用显式化**：（二）（三）的差异依赖（一）的账面列（C17 / C18），
 *   由 `bookOutputTax` / `bookInputTax` 两个 computed 显式暴露并作为引擎入参，
 *   而非在组件里隐式取值 —— 使勾稽可单测（design Property 3）。
 * - **附加分析区完全隔离**：本 composable 不读写 `N2-6-vat-rows` / `N2-6-period-mode` /
 *   `N2-6-declared-payable-vat`（那三个键属既有 `useN2VatCalc`，Requirements 5.3）。
 *
 * 持久化键（`saveField(sheet, field)` → `N2-{sheet}-{field}`，本表 sheet 恒为 '6'）：
 * | item_id                   | 内容                          |
 * |---------------------------|-------------------------------|
 * | `N2-6-declaration-rows`   | （一）10 固定项录入列          |
 * | `N2-6-output-rows`        | （二）销项动态行录入列          |
 * | `N2-6-output-pending`     | （二）待转销项税额期末减期初 F29 |
 * | `N2-6-input-rows`         | （三）进项动态行录入列          |
 * | `N2-6-input-adjust`       | （三）三调节项 F36/F37/F38     |
 * | `N2-6-special-rows`       | （四）4 固定项金额              |
 * | `N2-6-vat-payable`        | 应交增值税（供 N2-8 计税依据）  |
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import {
  parseNum,
  sumAmounts,
  calcDeclarationDiff,
  calcTaxableRevenue,
  calcOutputTax,
  calcInputTax,
  calcOutputVariance,
  calcInputVariance,
  calcVatPayableFromDeclaration,
  buildVatVariance,
  N2_VAT_DECLARATION_ITEMS,
  N2_VAT_SPECIAL_ITEMS,
  N2_VAT_BOOK_OUTPUT_KEY,
  N2_VAT_BOOK_INPUT_KEY,
  N2_VAT_OUTPUT_VARIANCE_FORMULA,
  N2_VAT_INPUT_VARIANCE_FORMULA,
  type N2VatInputAdjust,
  type N2VatVariance,
} from './useN2VatSourceEngine'
import type { ChecklistResponse } from './useN2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** （一）申报表核对行（源模板 R11 列结构） */
export interface N2VatDeclarationRow {
  /** 固定项 key（持久化标识，不可变） */
  key: string
  /** 源模板逐字行名（不可变） */
  label: string
  /** 账面数据 C（录入） */
  book: number
  /** 纳税申报表数据 D（录入） */
  declared: number
  /** 差异 E = C − D（派生，不落库） */
  diff: number
  /** 原因 F（录入） */
  reason: string
}

/** （二）销项测算行（源模板 R23 列结构） */
export interface N2VatOutputRow {
  id: string
  /** 品种（录入，新增时 prompt 取名） */
  variety: string
  /** 销售额 B（录入） */
  sales: number
  /** 免税/扣除销售额 C（录入） */
  exemptSales: number
  /** 计税收入 D = B − C（派生，不落库） */
  taxableRevenue: number
  /** 税率 E（录入） */
  rate: number
  /** 应计销项税 F = D × E（派生，不落库） */
  outputTax: number
}

/** （二）合计（源模板 R28，**无税率列合计**） */
export interface N2VatOutputTotal {
  sales: number
  exemptSales: number
  taxableRevenue: number
  outputTax: number
}

/** （三）进项测算行（源模板 R32 列结构） */
export interface N2VatInputRow {
  id: string
  /** 项目（录入） */
  project: string
  /** 购进货物/固定资产及接受劳务发生额 D（录入） */
  amount: number
  /** 税率 E（录入） */
  rate: number
  /** 测算数 F = D × E（派生，不落库） */
  inputTax: number
}

/** （三）合计（源模板 R35，仅发生额与测算数两列） */
export interface N2VatInputTotal {
  amount: number
  inputTax: number
}

/** （四）特殊情况检查行（源模板 R41 列结构） */
export interface N2VatSpecialRow {
  key: string
  label: string
  /** 金额 D（录入） */
  amount: number
}

/** （一）可编辑字段 */
export type N2VatDeclarationEditable = 'book' | 'declared' | 'reason'
/** （二）可编辑字段（派生列不可编辑） */
export type N2VatOutputEditable = 'variety' | 'sales' | 'exemptSales' | 'rate'
/** （三）可编辑字段 */
export type N2VatInputEditable = 'project' | 'amount' | 'rate'

// ─── Helpers ─────────────────────────────────────────────────────────────────

const SHEET = '6'

const FIELD = {
  declarationRows: 'declaration-rows',
  outputRows: 'output-rows',
  outputPending: 'output-pending',
  inputRows: 'input-rows',
  inputAdjust: 'input-adjust',
  specialRows: 'special-rows',
  vatPayable: 'vat-payable',
} as const

function generateRowId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function asArray(v: unknown): any[] {
  return Array.isArray(v) ? v : []
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseN2VatSourceCalcOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveField: (sheet: string, field: string, value: any) => Promise<void>
  getField: (sheet: string, field: string) => any
}

export function useN2VatSourceCalc(options: UseN2VatSourceCalcOptions) {
  const { allResponses, saveField, getField } = options

  /**
   * 🔴 computed 内必须经本函数读 `allResponses`（而非 `getField`）才能建立响应式依赖。
   *
   * `useN2FormData.getField` 内部虽也访问 `allResponses.value`，但它是**普通函数**：
   * 在 computed 中调用它无法保证依赖被 Vue 追踪到（且单测桩常直接操作底层 Map）。
   * 平台既有范式（`useN2Detail16.rows` / `useN2Adjudication14`）同样在 computed 内
   * 直读 `allResponses.value.get(itemId)` —— 本函数即该范式的收敛封装。
   *
   * `getField` 仅用于**非响应式**路径（`_xxxRaw()` 取当前落库快照）。
   */
  function readField(sheet: string, field: string): any {
    const resp = allResponses.value.get(`N2-${sheet}-${field}`)
    if (!resp?.conclusion) return null
    try {
      return JSON.parse(resp.conclusion)
    } catch {
      return resp.conclusion
    }
  }

  // ═══ （一）增值税纳税申报表核对 ══════════════════════════════════════════

  /**
   * 10 固定项 + 录入值 merge，`diff` 读时派生。
   * 固定项清单来自源模板，不可增删改名 → 始终以 `N2_VAT_DECLARATION_ITEMS` 为骨架遍历，
   * 存储值仅按 key 匹配填充（旧数据缺 key 时退化为 0，不会丢行）。
   */
  const declarationRows: ComputedRef<N2VatDeclarationRow[]> = computed(() => {
    const stored = asArray(readField(SHEET, FIELD.declarationRows))
    const byKey = new Map<string, any>()
    for (const r of stored) {
      if (r && typeof r.key === 'string') byKey.set(r.key, r)
    }
    return N2_VAT_DECLARATION_ITEMS.map((item) => {
      const raw = byKey.get(item.key) ?? {}
      const book = parseNum(raw.book)
      const declared = parseNum(raw.declared)
      return {
        key: item.key,
        label: item.label,
        book,
        declared,
        diff: calcDeclarationDiff(book, declared),
        reason: typeof raw.reason === 'string' ? raw.reason : '',
      }
    })
  })

  /** （一）合计（账面/申报表/差异三列，供 UI 合计行） */
  const declarationTotal = computed(() => {
    const rows = declarationRows.value
    return {
      book: sumAmounts(rows.map(r => r.book)),
      declared: sumAmounts(rows.map(r => r.declared)),
      diff: sumAmounts(rows.map(r => r.diff)),
    }
  })

  /** 存在差异的行数（差异 ≠ 0，供 UI 异常提示） */
  const declarationDiffCount = computed(
    () => declarationRows.value.filter(r => Math.abs(r.diff) > 0.005).length,
  )

  /**
   * （一）第 6 项「6.销项税额」账面数据 = 源模板 C17。
   * 🔴 被（二）差异公式 F30 跨段引用（design Property 3）。
   */
  const bookOutputTax: ComputedRef<number> = computed(
    () => declarationRows.value.find(r => r.key === N2_VAT_BOOK_OUTPUT_KEY)?.book ?? 0,
  )

  /**
   * （一）第 7 项「7.进项税额」账面数据 = 源模板 C18。
   * 🔴 被（三）差异公式 F39 跨段引用。
   */
  const bookInputTax: ComputedRef<number> = computed(
    () => declarationRows.value.find(r => r.key === N2_VAT_BOOK_INPUT_KEY)?.book ?? 0,
  )

  /** （一）落库形状：只含录入列（key 为标识，label 由常量提供不落库） */
  function _declarationRaw(): any[] {
    return declarationRows.value.map(r => ({
      key: r.key,
      book: r.book,
      declared: r.declared,
      reason: r.reason,
    }))
  }

  async function updateDeclaration(
    key: string,
    field: N2VatDeclarationEditable,
    value: any,
  ): Promise<void> {
    const raw = _declarationRaw()
    const idx = raw.findIndex(r => r.key === key)
    if (idx < 0) return
    raw[idx] = { ...raw[idx], [field]: field === 'reason' ? String(value ?? '') : parseNum(value) }
    await saveField(SHEET, FIELD.declarationRows, raw)
  }

  // ═══ （二）增值税销项税金测算 ════════════════════════════════════════════

  /** 动态行 + 派生列（D = B − C；F = D × E） */
  const outputRows: ComputedRef<N2VatOutputRow[]> = computed(() =>
    asArray(readField(SHEET, FIELD.outputRows)).map((r: any) => {
      const sales = parseNum(r.sales)
      const exemptSales = parseNum(r.exemptSales)
      const rate = parseNum(r.rate)
      const taxableRevenue = calcTaxableRevenue(sales, exemptSales)
      return {
        id: typeof r.id === 'string' && r.id ? r.id : generateRowId('out'),
        variety: typeof r.variety === 'string' ? r.variety : '',
        sales,
        exemptSales,
        taxableRevenue,
        rate,
        outputTax: calcOutputTax(taxableRevenue, rate),
      }
    }),
  )

  /** （二）合计（源模板 R28：B/C/D/F 四列，无税率合计） */
  const outputTotal: ComputedRef<N2VatOutputTotal> = computed(() => {
    const rows = outputRows.value
    return {
      sales: sumAmounts(rows.map(r => r.sales)),
      exemptSales: sumAmounts(rows.map(r => r.exemptSales)),
      taxableRevenue: sumAmounts(rows.map(r => r.taxableRevenue)),
      outputTax: sumAmounts(rows.map(r => r.outputTax)),
    }
  })

  /** （二）待转销项税额期末减期初金额（源模板 F29） */
  const pendingOutputTax: ComputedRef<number> = computed(
    () => parseNum(readField(SHEET, FIELD.outputPending)),
  )

  /** （二）差异（源模板 F30 = C17 − F28 − F29） */
  const outputVariance: ComputedRef<N2VatVariance> = computed(() =>
    buildVatVariance(
      calcOutputVariance(bookOutputTax.value, outputTotal.value.outputTax, pendingOutputTax.value),
      N2_VAT_OUTPUT_VARIANCE_FORMULA,
    ),
  )

  function _outputRaw(): any[] {
    return outputRows.value.map(r => ({
      id: r.id,
      variety: r.variety,
      sales: r.sales,
      exemptSales: r.exemptSales,
      rate: r.rate,
    }))
  }

  async function addOutputRow(variety: string): Promise<void> {
    const raw = _outputRaw()
    raw.push({
      id: generateRowId('out'),
      variety: String(variety ?? '').trim(),
      sales: 0,
      exemptSales: 0,
      rate: 0,
    })
    await saveField(SHEET, FIELD.outputRows, raw)
  }

  async function removeOutputRow(id: string): Promise<void> {
    await saveField(SHEET, FIELD.outputRows, _outputRaw().filter(r => r.id !== id))
  }

  async function updateOutputRow(
    id: string,
    field: N2VatOutputEditable,
    value: any,
  ): Promise<void> {
    const raw = _outputRaw()
    const idx = raw.findIndex(r => r.id === id)
    if (idx < 0) return
    raw[idx] = { ...raw[idx], [field]: field === 'variety' ? String(value ?? '') : parseNum(value) }
    await saveField(SHEET, FIELD.outputRows, raw)
  }

  async function setPendingOutputTax(value: any): Promise<void> {
    await saveField(SHEET, FIELD.outputPending, parseNum(value))
  }

  // ═══ （三）增值税进项税测算 ══════════════════════════════════════════════

  /** 动态行 + 派生列（F = D × E） */
  const inputRows: ComputedRef<N2VatInputRow[]> = computed(() =>
    asArray(readField(SHEET, FIELD.inputRows)).map((r: any) => {
      const amount = parseNum(r.amount)
      const rate = parseNum(r.rate)
      return {
        id: typeof r.id === 'string' && r.id ? r.id : generateRowId('in'),
        project: typeof r.project === 'string' ? r.project : '',
        amount,
        rate,
        inputTax: calcInputTax(amount, rate),
      }
    }),
  )

  /** （三）合计（源模板 R35：D/F 两列） */
  const inputTotal: ComputedRef<N2VatInputTotal> = computed(() => {
    const rows = inputRows.value
    return {
      amount: sumAmounts(rows.map(r => r.amount)),
      inputTax: sumAmounts(rows.map(r => r.inputTax)),
    }
  })

  /** （三）三调节项（源模板 F36/F37/F38，均「期末减期初」） */
  const inputAdjust: ComputedRef<N2VatInputAdjust> = computed(() => {
    const raw = readField(SHEET, FIELD.inputAdjust) ?? {}
    return {
      deductible: parseNum(raw.deductible),
      uncertified: parseNum(raw.uncertified),
      retained: parseNum(raw.retained),
    }
  })

  /** （三）差异（源模板 F39 = F35 − F36 − F37 − F38 − C18） */
  const inputVariance: ComputedRef<N2VatVariance> = computed(() =>
    buildVatVariance(
      calcInputVariance(inputTotal.value.inputTax, inputAdjust.value, bookInputTax.value),
      N2_VAT_INPUT_VARIANCE_FORMULA,
    ),
  )

  function _inputRaw(): any[] {
    return inputRows.value.map(r => ({
      id: r.id,
      project: r.project,
      amount: r.amount,
      rate: r.rate,
    }))
  }

  async function addInputRow(project: string): Promise<void> {
    const raw = _inputRaw()
    raw.push({
      id: generateRowId('in'),
      project: String(project ?? '').trim(),
      amount: 0,
      rate: 0,
    })
    await saveField(SHEET, FIELD.inputRows, raw)
  }

  async function removeInputRow(id: string): Promise<void> {
    await saveField(SHEET, FIELD.inputRows, _inputRaw().filter(r => r.id !== id))
  }

  async function updateInputRow(id: string, field: N2VatInputEditable, value: any): Promise<void> {
    const raw = _inputRaw()
    const idx = raw.findIndex(r => r.id === id)
    if (idx < 0) return
    raw[idx] = { ...raw[idx], [field]: field === 'project' ? String(value ?? '') : parseNum(value) }
    await saveField(SHEET, FIELD.inputRows, raw)
  }

  async function setInputAdjust(field: keyof N2VatInputAdjust, value: any): Promise<void> {
    await saveField(SHEET, FIELD.inputAdjust, {
      ...inputAdjust.value,
      [field]: parseNum(value),
    })
  }

  // ═══ （四）特殊情况检查 ══════════════════════════════════════════════════

  /** 4 固定项 + 录入金额（骨架恒取自常量，不可增删改名） */
  const specialRows: ComputedRef<N2VatSpecialRow[]> = computed(() => {
    const stored = asArray(readField(SHEET, FIELD.specialRows))
    const byKey = new Map<string, any>()
    for (const r of stored) {
      if (r && typeof r.key === 'string') byKey.set(r.key, r)
    }
    return N2_VAT_SPECIAL_ITEMS.map(item => ({
      key: item.key,
      label: item.label,
      amount: parseNum(byKey.get(item.key)?.amount),
    }))
  })

  /** （四）金额非 0 的项（须在审计说明中说明其会计处理，Requirements 4.3） */
  const specialFlagged = computed(
    () => specialRows.value.filter(r => Math.abs(r.amount) > 0.005).map(r => r.label),
  )

  async function updateSpecialRow(key: string, amount: any): Promise<void> {
    const raw = specialRows.value.map(r => ({ key: r.key, amount: r.amount }))
    const idx = raw.findIndex(r => r.key === key)
    if (idx < 0) return
    raw[idx] = { ...raw[idx], amount: parseNum(amount) }
    await saveField(SHEET, FIELD.specialRows, raw)
  }

  // ═══ R6：应交增值税口径 → N2-8 城建税及附加计税依据 ═══════════════════════

  /**
   * 应交增值税（Requirements R6.2）=（一）销项税额账面 C17 −（一）进项税额账面 C18。
   *
   * 🔴 口径取自源模板（一）段，**不回退附加分析区**（R6.3）：
   *    （一）无数据时 C17/C18 均为 0 → 本值为 0，不抛错、也不改用按月/季矩阵口径，
   *    以免 N2-8 计税依据在两套口径间静默漂移。
   */
  const vatPayable: ComputedRef<number> = computed(
    () => calcVatPayableFromDeclaration(bookOutputTax.value, bookInputTax.value),
  )

  /**
   * 写入 `N2-6-vat-payable`，供 `useN2CrossSheet.vatToSurtax` 读作 N2-8 计税依据（R6.1）。
   * 由组件在（一）数据变化后调用（watch 实际数据，禁用一次性挂载防护）。
   */
  async function syncVatPayable(): Promise<void> {
    await saveField(SHEET, FIELD.vatPayable, parseFloat(vatPayable.value.toFixed(2)))
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // （一）
    declarationRows,
    declarationTotal,
    declarationDiffCount,
    bookOutputTax,
    bookInputTax,
    updateDeclaration,
    // （二）
    outputRows,
    outputTotal,
    pendingOutputTax,
    outputVariance,
    addOutputRow,
    removeOutputRow,
    updateOutputRow,
    setPendingOutputTax,
    // （三）
    inputRows,
    inputTotal,
    inputAdjust,
    inputVariance,
    addInputRow,
    removeInputRow,
    updateInputRow,
    setInputAdjust,
    // （四）
    specialRows,
    specialFlagged,
    updateSpecialRow,
    // R6
    vatPayable,
    syncVatPayable,
  }
}

export default useN2VatSourceCalc
