/**
 * useI3Disclosure — I3 商誉附注披露 composable
 *
 * Variant 双版本（上市公司41×8 / 国有企业31×7），根据 projectContext.business_category 自动选择。
 * - 从审定表+减值测试自动取数（via useI3CrossSheet.disclosureAutoFill）(Req 9.2)
 * - AI 辅助生成文字描述 (Req 9.3)
 * - EventBus: subscribe 'substantive:adjudicated' 刷新 + publish 'disclosure:note-text-updated' (Req 9.3)
 * - Persistence: "I3-disc-listed-*" / "I3-disc-soe-*" item_ids
 *
 * 商誉附注特殊：无摊销相关矩阵！仅原值+减值+净额+减值测试过程描述
 *
 * Spec: .kiro/specs/i3-goodwill/
 * Task: 3.6
 * Requirements: 9.1-9.3
 */
import { ref, computed, watch, onMounted, onUnmounted, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
// ─── Types ───────────────────────────────────────────────────────────────────

export type I3DisclosureVariant = 'listed' | 'soe'

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** 附注子节定义 */
export interface I3DisclosureSection {
  key: string
  title: string
  hasTable: boolean
  hasDynamicRows: boolean
  hasNoteText: boolean
}

/** 附注商誉变动矩阵行（原值/减值）
 * 上市底稿可按 Excel 细列填增减分项；increase/decrease 为汇总，同步附注时用汇总列。
 */
export interface I3DisclosureMatrixRow {
  rowId: string
  investee: string              // 被投资单位(CGU)
  beginBalance: number          // 期初余额
  /** 汇总：本期增加（= 分项之和） */
  increase: number
  /** 汇总：本期减少（= 分项之和） */
  decrease: number
  endBalance: number            // 期末余额
  isAutoFilled: boolean         // 是否跨sheet自动取数
  /** 合计行且无明细拆分时需提示补 I3-2 */
  needsDetailSplit?: boolean
  // ── 上市原值细列（企业合并 / 合营 / 其他）──
  incBusinessCombination?: number
  incJoint?: number
  incOther?: number
  decDisposal?: number
  decOther?: number
  // ── 上市减值细列（计提 / 其他增加 / 处置 / 其他减少）──
  // increase 对应计提；以下为补充分项
  impIncOther?: number
  impDecDisposal?: number
  impDecOther?: number
}

/** 上市：关键假设参数行（毛利率/增长率/折现率） */
export interface I3AssumptionParamRow {
  rowId: string
  /** 资产组 / 业务名称 */
  label: string
  grossMargin: string
  growthRate: string
  discountRate: string
  remark: string
}

/** 原值行：分项汇总 → increase/decrease/endBalance */
export function recalcBookValueRow(row: I3DisclosureMatrixRow): void {
  const incBc = Number(row.incBusinessCombination) || 0
  const incJ = Number(row.incJoint) || 0
  const incO = Number(row.incOther) || 0
  const decD = Number(row.decDisposal) || 0
  const decO = Number(row.decOther) || 0
  const hasDetail = [incBc, incJ, incO, decD, decO].some((x) => Math.abs(x) > 0.0005)
  if (hasDetail) {
    row.increase = Math.round((incBc + incJ + incO) * 100) / 100
    row.decrease = Math.round((decD + decO) * 100) / 100
  }
  row.endBalance = Math.round((Number(row.beginBalance) + Number(row.increase) - Number(row.decrease)) * 100) / 100
}

/** 减值行：increase=计提；细列其他增加/处置/其他减少；期末含细列 */
export function recalcImpairmentRow(row: I3DisclosureMatrixRow): void {
  const provision = Number(row.increase) || 0
  const incO = Number(row.impIncOther) || 0
  const decD = Number(row.impDecDisposal) || 0
  const decO = Number(row.impDecOther) || 0
  const hasDecDetail = [decD, decO].some((x) => Math.abs(x) > 0.0005)
  if (hasDecDetail) {
    row.decrease = Math.round((decD + decO) * 100) / 100
  }
  const totalInc = provision + incO
  const totalDec = Number(row.decrease) || 0
  row.endBalance = Math.round((Number(row.beginBalance) + totalInc - totalDec) * 100) / 100
}

/** 同步用：原值/减值行的汇总增减（含细列） */
export function matrixRowSyncAmounts(
  row: I3DisclosureMatrixRow,
  layer: 'bookValue' | 'impairment',
): { increase: number; decrease: number; endBalance: number } {
  if (layer === 'bookValue') {
    recalcBookValueRow(row)
    return {
      increase: Number(row.increase) || 0,
      decrease: Number(row.decrease) || 0,
      endBalance: Number(row.endBalance) || 0,
    }
  }
  const provision = Number(row.increase) || 0
  const incO = Number(row.impIncOther) || 0
  recalcImpairmentRow(row)
  return {
    increase: Math.round((provision + incO) * 100) / 100,
    decrease: Number(row.decrease) || 0,
    endBalance: Number(row.endBalance) || 0,
  }
}

/** 附注动态行（通用） */
export interface I3DisclosureDynamicRow {
  rowId: string
  name: string
  amount: number
  description: string
  remark: string
}

/** 上市附注：业绩承诺完成及对应商誉减值（对齐 note_template 子表） */
export interface I3PerformanceRow {
  rowId: string
  /** 项目 / 被投资单位 */
  name: string
  /** 业绩承诺完成情况 */
  commitmentStatus: string
  /** 商誉减值金额 */
  impairmentAmount: number
  /** 承诺期 / 备注 */
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX_LISTED = 'I3-disc-listed'
const ITEM_PREFIX_SOE = 'I3-disc-soe'

/** 上市公司版本子节（41×8） */
export const LISTED_SECTIONS: I3DisclosureSection[] = [
  { key: 'goodwill_book_value', title: '(1) 商誉账面价值', hasTable: true, hasDynamicRows: false, hasNoteText: false },
  { key: 'goodwill_impairment', title: '(2) 商誉减值准备', hasTable: true, hasDynamicRows: false, hasNoteText: false },
  { key: 'impairment_test_process', title: '(3) 商誉减值测试过程及方法', hasTable: false, hasDynamicRows: false, hasNoteText: true },
  { key: 'cgu_allocation', title: '(4) 商誉分摊至资产组(组合)情况', hasTable: true, hasDynamicRows: true, hasNoteText: true },
  { key: 'key_assumptions', title: '(5) 减值测试关键假设', hasTable: false, hasDynamicRows: false, hasNoteText: true },
  { key: 'sensitivity_analysis', title: '(6) 敏感性分析', hasTable: true, hasDynamicRows: false, hasNoteText: true },
  { key: 'impairment_result', title: '(7) 减值测试结论', hasTable: true, hasDynamicRows: false, hasNoteText: true },
  { key: 'other_disclosure', title: '(8) 其他说明', hasTable: false, hasDynamicRows: false, hasNoteText: true },
]

/** 国企版本子节（31×7） */
export const SOE_SECTIONS: I3DisclosureSection[] = [
  { key: 'goodwill_book_value', title: '(一) 商誉账面价值', hasTable: true, hasDynamicRows: false, hasNoteText: false },
  { key: 'goodwill_impairment', title: '(二) 商誉减值准备', hasTable: true, hasDynamicRows: false, hasNoteText: false },
  { key: 'impairment_test_process', title: '(三) 商誉减值测试过程', hasTable: false, hasDynamicRows: false, hasNoteText: true },
  { key: 'cgu_allocation', title: '(四) 商誉分摊至资产组情况', hasTable: true, hasDynamicRows: true, hasNoteText: true },
  { key: 'key_assumptions', title: '(五) 减值测试关键假设及敏感性', hasTable: false, hasDynamicRows: false, hasNoteText: true },
  { key: 'impairment_result', title: '(六) 减值测试结论', hasTable: true, hasDynamicRows: false, hasNoteText: true },
  { key: 'other_disclosure', title: '(七) 其他说明', hasTable: false, hasDynamicRows: false, hasNoteText: true },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI3Disclosure(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    variant?: Ref<I3DisclosureVariant>
    crossSheetAutoFill?: Ref<Record<string, number>>
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const variant = computed<I3DisclosureVariant>(() => options?.variant?.value ?? 'listed')
  const itemPrefix = computed(() => variant.value === 'listed' ? ITEM_PREFIX_LISTED : ITEM_PREFIX_SOE)
  const isAiGenerating = ref(false)

  /** 子节1: 商誉账面价值矩阵（原值-减值=净额） */
  const bookValueRows = ref<I3DisclosureMatrixRow[]>([])

  /** 子节2: 商誉减值准备变动矩阵 */
  const impairmentRows = ref<I3DisclosureMatrixRow[]>([])

  /** 动态行子节（CGU分摊） */
  const sectionRows = ref<Record<string, I3DisclosureDynamicRow[]>>({
    cgu_allocation: [],
  })

  /** 上市：业绩承诺子表 */
  const performanceRows = ref<I3PerformanceRow[]>([])

  /** 上市：关键假设参数子表 */
  const assumptionParamRows = ref<I3AssumptionParamRow[]>([])

  /** 各子节说明文本（AI生成/手工填写） */
  const sectionNotes = ref<Record<string, string>>({})

  // ─── Computed: 子节列表 ────────────────────────────────────────────────────

  const sections = computed(() =>
    variant.value === 'listed' ? LISTED_SECTIONS : SOE_SECTIONS,
  )

  // ─── Computed: 跨sheet自动取数 (Req 9.2) ──────────────────────────────────

  const autoFilledData = computed(() => options?.crossSheetAutoFill?.value ?? {})

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const bookValueTotal = computed(() => {
    const rows = bookValueRows.value
    let beginBalance = 0
    let increase = 0
    let decrease = 0
    let endBalance = 0
    for (const r of rows) {
      const a = matrixRowSyncAmounts(r, 'bookValue')
      beginBalance += Number(r.beginBalance) || 0
      increase += a.increase
      decrease += a.decrease
      endBalance += a.endBalance
    }
    return { beginBalance, increase, decrease, endBalance }
  })

  const impairmentTotal = computed(() => {
    let beginBalance = 0
    let increase = 0
    let decrease = 0
    let endBalance = 0
    for (const r of impairmentRows.value) {
      const a = matrixRowSyncAmounts(r, 'impairment')
      beginBalance += Number(r.beginBalance) || 0
      increase += a.increase
      decrease += a.decrease
      endBalance += a.endBalance
    }
    return { beginBalance, increase, decrease, endBalance }
  })

  /** 净值合计 = 商誉原值期末 - 减值准备期末（商誉无摊销！） */
  const netValueTotal = computed(() =>
    bookValueTotal.value.endBalance - impairmentTotal.value.endBalance,
  )

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadData(): void {
    const prefix = itemPrefix.value

    // 矩阵行（兼容旧 key: bookValue-matrix / book-value-matrix）
    bookValueRows.value = _loadMatrixRows(`${prefix}-book-value-matrix`)
    if (!bookValueRows.value.length) {
      bookValueRows.value = _loadMatrixRows(`${prefix}-bookValue-matrix`)
    }
    impairmentRows.value = _loadMatrixRows(`${prefix}-impairment-matrix`)
    if (!impairmentRows.value.length) {
      // 旧版误用 bookValue 风格 key
      impairmentRows.value = _loadMatrixRows(`${prefix}-impairmentValue-matrix`)
    }

    // 动态行
    for (const key of Object.keys(sectionRows.value)) {
      const item = allResponses.value.get(`${prefix}-${key}-rows`)
      if (item?.remark) {
        try {
          const parsed = JSON.parse(item.remark)
          sectionRows.value[key] = Array.isArray(parsed) ? parsed : []
        } catch { sectionRows.value[key] = [] }
      } else {
        sectionRows.value[key] = []
      }
    }

    // 说明文本
    for (const sect of sections.value) {
      if (sect.hasNoteText) {
        const noteItem = allResponses.value.get(`${prefix}-${sect.key}-note`)
        sectionNotes.value[sect.key] = (noteItem?.remark ?? '') as string
      }
    }

    // 业绩承诺 + 关键假设参数（仅上市）
    if (variant.value === 'listed') {
      const perfItem = allResponses.value.get(`${prefix}-performance-rows`)
      if (perfItem?.remark) {
        try {
          const parsed = JSON.parse(perfItem.remark)
          performanceRows.value = Array.isArray(parsed) ? parsed.map(_normalizePerformanceRow) : []
        } catch {
          performanceRows.value = []
        }
      } else {
        performanceRows.value = []
      }
      const assumeItem = allResponses.value.get(`${prefix}-assumption-params`)
      if (assumeItem?.remark) {
        try {
          const parsed = JSON.parse(assumeItem.remark)
          assumptionParamRows.value = Array.isArray(parsed) ? parsed.map(_normalizeAssumptionRow) : []
        } catch {
          assumptionParamRows.value = []
        }
      } else {
        assumptionParamRows.value = []
      }
    } else {
      performanceRows.value = []
      assumptionParamRows.value = []
    }
  }

  function _normalizePerformanceRow(raw: any): I3PerformanceRow {
    return {
      rowId: String(raw?.rowId || `perf-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`),
      name: String(raw?.name || ''),
      commitmentStatus: String(raw?.commitmentStatus || ''),
      impairmentAmount: Number(raw?.impairmentAmount) || 0,
      remark: String(raw?.remark || ''),
    }
  }

  function _normalizeAssumptionRow(raw: any): I3AssumptionParamRow {
    return {
      rowId: String(raw?.rowId || `ap-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`),
      label: String(raw?.label || ''),
      grossMargin: String(raw?.grossMargin || ''),
      growthRate: String(raw?.growthRate || ''),
      discountRate: String(raw?.discountRate || ''),
      remark: String(raw?.remark || ''),
    }
  }

  function _loadMatrixRows(itemId: string): I3DisclosureMatrixRow[] {
    const item = allResponses.value.get(itemId)
    if (!item?.remark) return []
    try {
      const parsed = JSON.parse(item.remark)
      return Array.isArray(parsed) ? parsed : []
    } catch { return [] }
  }

  // ─── Auto-fill from cross-sheet (Req 9.2) ─────────────────────────────────

  /**
   * 从审定表+减值测试自动取数填入附注对应位置。
   * 用户可手工覆盖自动值。
   * 注意：原值减少 ≠ 减值；减值计入减值准备「本期增加(计提)」。
   */
  function applyAutoFill(): void {
    const data = autoFilledData.value
    if (!data || Object.keys(data).length === 0) return

    // 优先尝试从 I3-2 明细行按被投资单位展开
    const pulled = pullFromDetailRows({ overwrite: false })
    if (pulled.count > 0) return

    if (bookValueRows.value.length === 0 && data['disc_goodwill_original'] != null) {
      const end = Number(data['disc_goodwill_original']) || 0
      bookValueRows.value = [{
        rowId: 'auto-goodwill-total',
        investee: '商誉合计（无明细分项—请从 I3-2 取数）',
        beginBalance: 0, // 无明细时不臆造期初=期末
        increase: 0,
        decrease: 0,
        endBalance: end,
        isAutoFilled: true,
        needsDetailSplit: true,
      }]
      _persistMatrix('bookValue')
    }

    if (impairmentRows.value.length === 0 && data['disc_goodwill_impairment'] != null) {
      const end = Number(data['disc_goodwill_impairment']) || 0
      const cur = Number(data['disc_goodwill_current_impairment']) || 0
      impairmentRows.value = [{
        rowId: 'auto-impairment-total',
        investee: '商誉减值准备合计（无明细分项—请从 I3-2 取数）',
        beginBalance: cur > 0 ? Math.max(0, end - cur) : 0,
        increase: cur,
        decrease: 0, // 商誉减值不可转回；减少仅限处置
        endBalance: end,
        isAutoFilled: true,
        needsDetailSplit: true,
      }]
      _persistMatrix('impairment')
    }
  }

  /**
   * 从 I3-2 明细表按被投资单位拉取原值/减值滚动，并回填 CGU 分摊。
   */
  function pullFromDetailRows(opts?: { overwrite?: boolean }): { count: number; message: string } {
    const overwrite = opts?.overwrite !== false
    const raw = allResponses.value.get('I3-2-rows')
    const remark = typeof raw === 'string' ? raw : raw?.remark
    let detail: any[] = []
    try {
      const parsed = typeof remark === 'string' ? JSON.parse(remark) : remark
      detail = Array.isArray(parsed) ? parsed : []
    } catch {
      return { count: 0, message: 'I3-2 明细无可解析数据' }
    }
    if (!detail.length) return { count: 0, message: 'I3-2 明细为空' }

    if (!overwrite && bookValueRows.value.length > 0) {
      return { count: 0, message: '已有披露矩阵，未覆盖（可点「从 I3-2 取数」强制覆盖）' }
    }

    const n = (v: any) => {
      const x = Number(v)
      return Number.isFinite(x) ? x : 0
    }

    bookValueRows.value = detail.map((r, i) => {
      const begin = n(r.costOpening ?? r.goodwillOriginal)
      const increase = n(r.costIncrease)
      const decrease = n(r.costDecrease)
      const method = String(r.costIncreaseMethod || r.mergerType || '')
      const row: I3DisclosureMatrixRow = {
        rowId: `bv-${r.rowId || i}`,
        investee: String(r.investee || `项目${i + 1}`),
        beginBalance: begin,
        increase,
        decrease,
        endBalance: r.costEnding != null ? n(r.costEnding) : begin + increase - decrease,
        isAutoFilled: true,
        incBusinessCombination: /合营|共同/.test(method) ? 0 : increase,
        incJoint: /合营|共同/.test(method) ? increase : 0,
        incOther: 0,
        decDisposal: decrease,
        decOther: 0,
      }
      recalcBookValueRow(row)
      return row
    })

    impairmentRows.value = detail.map((r, i) => {
      const begin = n(r.impOpening ?? r.accImpairmentBegin)
      const increase = n(r.impIncrease ?? r.currentImpairment)
      const decrease = n(r.impDecrease)
      const row: I3DisclosureMatrixRow = {
        rowId: `imp-${r.rowId || i}`,
        investee: String(r.investee || `项目${i + 1}`),
        beginBalance: begin,
        increase,
        decrease,
        endBalance: r.impEnding != null
          ? n(r.impEnding)
          : (r.accImpairmentEnd != null ? n(r.accImpairmentEnd) : begin + increase - decrease),
        isAutoFilled: true,
        impIncOther: 0,
        impDecDisposal: decrease,
        impDecOther: 0,
      }
      recalcImpairmentRow(row)
      return row
    })

    // CGU 分摊：按 cguName 聚合期末净额或原值
    const byCgu = new Map<string, number>()
    for (const r of detail) {
      const cgu = String(r.cguName || '').trim() || '未分配资产组'
      const amt = n(r.goodwillNetValue ?? (n(r.costAudited || r.goodwillOriginal) - n(r.impAudited || r.accImpairmentEnd)))
      byCgu.set(cgu, (byCgu.get(cgu) || 0) + amt)
    }
    sectionRows.value.cgu_allocation = Array.from(byCgu.entries()).map(([name, amount], i) => ({
      rowId: `cgu-${i}`,
      name,
      amount,
      description: '自 I3-2 明细按 CGU 汇总',
      remark: '',
    }))

    _persistMatrix('bookValue')
    _persistMatrix('impairment')
    _persistSection('cgu_allocation')

    // 上市：按被投资单位预填业绩承诺行（已有内容不覆盖）
    if (variant.value === 'listed' && performanceRows.value.length === 0) {
      performanceRows.value = detail
        .map((r, i) => ({
          rowId: `perf-${r.rowId || i}`,
          name: String(r.investee || `项目${i + 1}`),
          commitmentStatus: '',
          impairmentAmount: Number(r.impIncrease ?? r.currentImpairment) || 0,
          remark: '',
        }))
      _persistPerformance()
    }

    return { count: detail.length, message: `已从 I3-2 取入 ${detail.length} 个被投资单位` }
  }

  // ─── CRUD: 动态行 ─────────────────────────────────────────────────────────

  function addDynamicRow(sectionKey: string, name: string): void {
    const rows = sectionRows.value[sectionKey]
    if (!rows) return
    rows.push({
      rowId: `i3disc-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      name,
      amount: 0,
      description: '',
      remark: '',
    })
    _persistSection(sectionKey)
  }

  function removeDynamicRow(sectionKey: string, rowId: string): void {
    const rows = sectionRows.value[sectionKey]
    if (!rows) return
    const idx = rows.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      rows.splice(idx, 1)
      _persistSection(sectionKey)
    }
  }

  function updateDynamicRow(sectionKey: string, rowId: string, field: keyof I3DisclosureDynamicRow, value: any): void {
    const rows = sectionRows.value[sectionKey]
    if (!rows) return
    const row = rows.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _persistSection(sectionKey)
  }

  // ─── Update: 矩阵行 ───────────────────────────────────────────────────────

  function updateMatrixCell(
    layer: 'bookValue' | 'impairment',
    rowId: string,
    field: keyof I3DisclosureMatrixRow,
    value: any,
  ): void {
    const target = layer === 'bookValue' ? bookValueRows : impairmentRows
    const row = target.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    row.isAutoFilled = false
    if (layer === 'bookValue') recalcBookValueRow(row)
    else recalcImpairmentRow(row)
    _persistMatrix(layer)
  }

  function addMatrixRow(layer: 'bookValue' | 'impairment', investee = ''): void {
    const target = layer === 'bookValue' ? bookValueRows : impairmentRows
    const row: I3DisclosureMatrixRow = {
      rowId: `i3disc-m-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      investee: investee || '',
      beginBalance: 0,
      increase: 0,
      decrease: 0,
      endBalance: 0,
      isAutoFilled: false,
      ...(layer === 'bookValue'
        ? { incBusinessCombination: 0, incJoint: 0, incOther: 0, decDisposal: 0, decOther: 0 }
        : { impIncOther: 0, impDecDisposal: 0, impDecOther: 0 }),
    }
    target.value.push(row)
    _persistMatrix(layer)
  }

  function removeMatrixRow(layer: 'bookValue' | 'impairment', rowId: string): void {
    const target = layer === 'bookValue' ? bookValueRows : impairmentRows
    const idx = target.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      target.value.splice(idx, 1)
      _persistMatrix(layer)
    }
  }

  /** 供同步附注组装快照 */
  function getSyncSnapshot() {
    return {
      bookValueRows: bookValueRows.value.map((r) => ({ ...r })),
      impairmentRows: impairmentRows.value.map((r) => ({ ...r })),
      cguRows: (sectionRows.value.cgu_allocation || []).map((r) => ({ ...r })),
      performanceRows: performanceRows.value.map((r) => ({
        name: r.name,
        commitmentStatus: r.commitmentStatus,
        impairmentAmount: r.impairmentAmount,
      })),
      assumptionParams: assumptionParamRows.value.map((r) => ({
        label: r.label,
        grossMargin: r.grossMargin,
        growthRate: r.growthRate,
        discountRate: r.discountRate,
      })),
      noteProcess: sectionNotes.value.impairment_test_process || '',
      noteAssumptions: sectionNotes.value.key_assumptions || '',
      noteSensitivity: sectionNotes.value.sensitivity_analysis || '',
      noteResult: sectionNotes.value.impairment_result || '',
      noteOther: sectionNotes.value.other_disclosure || '',
      noteCgu: sectionNotes.value.cgu_allocation || '',
    }
  }

  // ─── 业绩承诺子表 CRUD（上市） ─────────────────────────────────────────────

  function _persistPerformance(): void {
    if (variant.value !== 'listed') return
    options?.onSave?.(`${itemPrefix.value}-performance-rows`, performanceRows.value)
  }

  function addPerformanceRow(name = ''): void {
    performanceRows.value.push({
      rowId: `perf-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      name,
      commitmentStatus: '',
      impairmentAmount: 0,
      remark: '',
    })
    _persistPerformance()
  }

  function removePerformanceRow(rowId: string): void {
    const idx = performanceRows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      performanceRows.value.splice(idx, 1)
      _persistPerformance()
    }
  }

  function updatePerformanceRow(rowId: string, field: keyof I3PerformanceRow, value: any): void {
    const row = performanceRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _persistPerformance()
  }

  /** 从原值矩阵项目名预填业绩承诺行（不覆盖已有） */
  function seedPerformanceFromBookValue(): { count: number; message: string } {
    if (variant.value !== 'listed') {
      return { count: 0, message: '仅上市公司附注需要业绩承诺表' }
    }
    const existing = new Set(performanceRows.value.map((r) => r.name.trim()).filter(Boolean))
    let added = 0
    for (const r of bookValueRows.value) {
      const name = (r.investee || '').trim()
      if (!name || name.includes('合计') || existing.has(name)) continue
      const imp = impairmentRows.value.find((x) => x.investee === name)
      performanceRows.value.push({
        rowId: `perf-${Date.now()}-${added}`,
        name,
        commitmentStatus: '',
        impairmentAmount: Number(imp?.increase) || 0,
        remark: '',
      })
      existing.add(name)
      added += 1
    }
    if (added) _persistPerformance()
    return {
      count: added,
      message: added ? `已从原值矩阵预填 ${added} 行业绩承诺` : '无需预填（已有行或原值矩阵为空）',
    }
  }

  // ─── 关键假设参数子表 CRUD（上市） ─────────────────────────────────────────

  function _persistAssumptionParams(): void {
    if (variant.value !== 'listed') return
    options?.onSave?.(`${itemPrefix.value}-assumption-params`, assumptionParamRows.value)
  }

  function addAssumptionParamRow(label = ''): void {
    assumptionParamRows.value.push({
      rowId: `ap-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      label,
      grossMargin: '',
      growthRate: '',
      discountRate: '',
      remark: '',
    })
    _persistAssumptionParams()
  }

  function removeAssumptionParamRow(rowId: string): void {
    const idx = assumptionParamRows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      assumptionParamRows.value.splice(idx, 1)
      _persistAssumptionParams()
    }
  }

  function updateAssumptionParamRow(rowId: string, field: keyof I3AssumptionParamRow, value: any): void {
    const row = assumptionParamRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    _persistAssumptionParams()
  }

  function seedAssumptionFromCgu(): { count: number; message: string } {
    if (variant.value !== 'listed') {
      return { count: 0, message: '仅上市公司附注需要关键假设参数表' }
    }
    const existing = new Set(assumptionParamRows.value.map((r) => r.label.trim()).filter(Boolean))
    let added = 0
    for (const cgu of sectionRows.value.cgu_allocation || []) {
      const label = (cgu.name || '').trim()
      if (!label || existing.has(label)) continue
      assumptionParamRows.value.push({
        rowId: `ap-${Date.now()}-${added}`,
        label,
        grossMargin: '',
        growthRate: '',
        discountRate: '',
        remark: '',
      })
      existing.add(label)
      added += 1
    }
    if (added) _persistAssumptionParams()
    return {
      count: added,
      message: added ? `已从 CGU 预填 ${added} 行关键假设` : '无需预填（已有行或 CGU 为空）',
    }
  }

  // ─── Section Note (手工编辑) ───────────────────────────────────────────────

  function saveSectionNote(sectionKey: string, note: string): void {
    sectionNotes.value[sectionKey] = note
    const prefix = itemPrefix.value
    options?.onSave?.(`${prefix}-${sectionKey}-note`, note)

    // EventBus发布 'disclosure:note-text-updated' (Req 9.3)
    _publishNoteEvent(sectionKey, note)
  }

  // ─── AI辅助生成文字描述 (Req 9.3) ─────────────────────────────────────────

  /**
   * 调用AI端点生成附注文字描述。
   * 后端 POST /api/workpapers/{wp_id}/ai/generate-text
   */
  async function generateNoteText(sectionKey: string, existingContent?: string): Promise<string | null> {
    if (!wpId.value) return null
    isAiGenerating.value = true
    try {
      const context = _buildAiContext(sectionKey)
      const res = await api.post(`/api/workpapers/${wpId.value}/ai/generate-text`, {
        section: `i3-disclosure-${variant.value}-${sectionKey}`,
        prompt: `请为商誉附注"${_getSectionTitle(sectionKey)}"生成披露文字描述`,
        context,
        existingContent: existingContent || sectionNotes.value[sectionKey] || '',
      })

      const data = res?.data ?? res
      const generated = data?.content ?? data?.text ?? ''
      if (generated) {
        return generated
      }
      ElMessage.warning('AI未返回内容，请手工编写')
      return null
    } catch (err: any) {
      const msg = err?.response?.data?.message || err?.message || 'AI生成失败'
      ElMessage.error(msg)
      return null
    } finally {
      isAiGenerating.value = false
    }
  }

  /**
   * AI生成并确认后写入
   */
  async function applyAiGeneratedNote(sectionKey: string, text: string): Promise<void> {
    sectionNotes.value[sectionKey] = text
    const prefix = itemPrefix.value
    options?.onSave?.(`${prefix}-${sectionKey}-note`, text)
    _publishNoteEvent(sectionKey, text)
  }

  // ─── EventBus 订阅 + 发布 (Req 9.3) ──────────────────────────────────────

  /** 已变更的section集合（用于批量事件通知） */
  const changedSections = ref<Set<string>>(new Set())
  let publishTimer: ReturnType<typeof setTimeout> | null = null

  function _publishNoteEvent(sectionKey: string, _text: string): void {
    changedSections.value.add(sectionKey)

    // 防抖：300ms内的多次变更合并为一次事件
    if (publishTimer) clearTimeout(publishTimer)
    publishTimer = setTimeout(() => {
      const sectionsArr = Array.from(changedSections.value)
      changedSections.value.clear()

      const payload = {
        wpCode: 'I3',
        variant: variant.value,
        sections: sectionsArr,
      }

      // 全局 CustomEvent（标准D~N附注EventBus模式）
      window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
        detail: payload,
      }))
    }, 300)
  }

  /**
   * 订阅 'substantive:adjudicated' 事件，审定表确认后刷新附注数据
   */
  function _onSubstantiveAdjudicated(event: Event): void {
    const detail = (event as CustomEvent).detail
    // 仅响应 I3 相关事件
    if (detail?.wpCode === 'I3' || detail?.accountCode === '1711') {
      applyAutoFill()
    }
  }

  onMounted(() => {
    window.addEventListener('substantive:adjudicated', _onSubstantiveAdjudicated)
  })

  onUnmounted(() => {
    window.removeEventListener('substantive:adjudicated', _onSubstantiveAdjudicated)
  })

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _buildAiContext(sectionKey: string): string {
    const data = autoFilledData.value
    const parts: string[] = [
      `科目: 商誉(1711)，商誉不摊销！仅年度减值测试`,
      `版本: ${variant.value === 'listed' ? '上市公司' : '国有企业'}`,
    ]
    if (data['disc_goodwill_original'] != null) parts.push(`商誉原值合计: ${data['disc_goodwill_original']}`)
    if (data['disc_goodwill_impairment'] != null) parts.push(`累计减值合计: ${data['disc_goodwill_impairment']}`)
    if (data['disc_goodwill_net'] != null) parts.push(`净额合计: ${data['disc_goodwill_net']}`)
    if (data['disc_goodwill_current_impairment'] != null) parts.push(`本期减值: ${data['disc_goodwill_current_impairment']}`)
    if (data['disc_cgu_count'] != null) parts.push(`资产组(CGU)数量: ${data['disc_cgu_count']}`)
    if (data['disc_total_impairment'] != null) parts.push(`商誉减值总额: ${data['disc_total_impairment']}`)
    if (data['disc_total_recoverable'] != null) parts.push(`可收回金额合计: ${data['disc_total_recoverable']}`)
    if (data['disc_investee_count'] != null) parts.push(`被投资单位数: ${data['disc_investee_count']}`)
    return parts.join('; ')
  }

  function _getSectionTitle(sectionKey: string): string {
    const sect = sections.value.find((s) => s.key === sectionKey)
    return sect?.title ?? sectionKey
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persistSection(sectionKey: string): void {
    const prefix = itemPrefix.value
    options?.onSave?.(`${prefix}-${sectionKey}-rows`, sectionRows.value[sectionKey])
  }

  function _persistMatrix(layer: string): void {
    const prefix = itemPrefix.value
    const target = layer === 'bookValue' ? bookValueRows : impairmentRows
    // 统一 kebab key，与 _loadData 对齐
    const key = layer === 'bookValue' ? 'book-value-matrix' : 'impairment-matrix'
    options?.onSave?.(`${prefix}-${key}`, target.value)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadData(), { immediate: true })
  watch(variant, () => _loadData())

  // ─── Cleanup ───────────────────────────────────────────────────────────────

  function dispose(): void {
    if (publishTimer) {
      clearTimeout(publishTimer)
      publishTimer = null
    }
    changedSections.value.clear()
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    variant,
    isAiGenerating,
    bookValueRows,
    impairmentRows,
    sectionRows,
    sectionNotes,
    performanceRows,
    assumptionParamRows,
    // Computed
    sections,
    autoFilledData,
    bookValueTotal,
    impairmentTotal,
    netValueTotal,
    needsDetailSplitWarning: computed(() =>
      [...bookValueRows.value, ...impairmentRows.value].some((r) => r.needsDetailSplit),
    ),
    // Actions
    applyAutoFill,
    pullFromDetailRows,
    addDynamicRow,
    removeDynamicRow,
    updateDynamicRow,
    updateMatrixCell,
    addMatrixRow,
    removeMatrixRow,
    addPerformanceRow,
    removePerformanceRow,
    updatePerformanceRow,
    seedPerformanceFromBookValue,
    addAssumptionParamRow,
    removeAssumptionParamRow,
    updateAssumptionParamRow,
    seedAssumptionFromCgu,
    saveSectionNote,
    getSyncSnapshot,
    // AI
    generateNoteText,
    applyAiGeneratedNote,
    // Lifecycle
    dispose,
  }
}

export default useI3Disclosure
