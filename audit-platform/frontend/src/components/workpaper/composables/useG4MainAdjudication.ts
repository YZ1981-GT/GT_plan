/**
 * useG4MainAdjudication — G4-1 审定表核心逻辑（借方/资产类科目 1501 债权投资）
 *
 * 三层数据结构：
 *   一、债权投资原值（单项计提/按组合计提/小计/减：一年内到期）
 *   二、债权投资减值准备（单项计提/按组合计提/小计）
 *   三、债权投资净值（= 原值小计 - 减值小计，即摊余成本）
 *   附加：一年内到期非流动资产列报数
 *
 * 借方公式链：
 *   期初审定 = 期初未审 + 期初AJE + 期初RJE
 *   期末未审 = 期初审定 + 借方发生额 - 贷方发生额
 *   期末审定 = 期末未审 + 期末AJE + 期末RJE
 *   摊余成本 = 原值小计 - 减值小计
 *   变动率 = (期末审定 - 期初审定) / 期初审定
 *
 * EventBus: publish substantive:adjudicated(accountCode='1501')
 *
 * Spec: .kiro/specs/g4-bond-investment-main/ Task 5.1
 * Requirements: 3.1~3.13
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcDebitBalance,
  calcAdjustedAmount,
  calcAmortizedCost,
  calcChangeRate,
} from '@/composables/useG4MainFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

// ═══ 常量 ═══

/** 科目：债权投资 */
export const G4_ACCOUNT_CODE = '1501'

/** 三大分组定义 */
export const G4_GROUPS_DEF = [
  {
    groupKey: 'original-value',
    groupName: '一、债权投资原值',
    rows: [
      { rowKey: 'ov-individual', label: '单项计提' },
      { rowKey: 'ov-portfolio', label: '按组合计提' },
    ],
    subtotalLabel: '原值小计',
    hasOneYearDeduct: true,  // 含"减：一年内到期"行
  },
  {
    groupKey: 'impairment',
    groupName: '二、债权投资减值准备',
    rows: [
      { rowKey: 'imp-individual', label: '单项计提' },
      { rowKey: 'imp-portfolio', label: '按组合计提' },
    ],
    subtotalLabel: '减值小计',
    hasOneYearDeduct: false,
  },
  {
    groupKey: 'amortized-cost',
    groupName: '三、债权投资净值（摊余成本）',
    rows: [],  // 自动计算：原值小计 - 减值小计
    subtotalLabel: '摊余成本',
    hasOneYearDeduct: false,
  },
] as const

// ═══ 存储 Key ═══

const GROUPS_STORAGE_KEY = 'G4-1-adj-groups'
const TB_STORAGE_KEY = 'G4-1-adj-tb-1501'
const NOTE_KEY = 'G4-1-adj-note'
const CONCLUSION_KEY = 'G4-1-adj-conclusion'
const ONE_YEAR_KEY = 'G4-1-adj-one-year'

// ═══ 类型定义 ═══

/** 审定表展示行（含公式计算字段） */
export interface G4AdjudicationRow {
  id: string
  item: string
  openingUnadjusted: number
  openingAJE: number
  openingRJE: number
  openingAdjusted: number        // 公式: 未审 + AJE + RJE
  closingUnadjusted: number      // 公式: 期初审定 + 借方 - 贷方
  closingAJE: number
  closingRJE: number
  closingAdjusted: number        // 公式: 未审 + AJE + RJE
  changeAmount: number           // 公式: 期末审定 - 期初审定
  changeRate: number | null      // 公式: (期末-期初)/期初, 期初=0时null
  reasonAnalysis: string         // |变动率|>20%时必填
  indexRef: string
  isEditable: boolean
  isSubtotal: boolean
}

/** 存储行（无公式字段） */
interface StoredG4AdjRow {
  rowKey: string
  label: string
  openingUnadjusted: number
  openingAJE: number
  openingRJE: number
  periodDebit: number            // 借方发生额
  periodCredit: number           // 贷方发生额
  closingAJE: number
  closingRJE: number
  reasonAnalysis: string
  indexRef: string
}

/** 分组数据 */
export interface AdjudicationGroup {
  groupKey: string
  groupName: string
  expanded: boolean
  rows: G4AdjudicationRow[]
  subtotal: G4AdjudicationRow
  oneYearDeduct?: G4AdjudicationRow  // 仅原值组有"减：一年内到期"
}

/** 一年内到期行存储 */
interface StoredOneYearRow {
  openingAdjusted: number
  closingAdjusted: number
}

/** composable 选项 */
export interface UseG4MainAdjudicationOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

// ═══ 工具函数 ═══

function safeParseJson<T>(jsonStr: string | null | undefined): T | null {
  if (!jsonStr) return null
  try {
    return JSON.parse(jsonStr) as T
  } catch {
    return null
  }
}

function getDefaultStoredRows(groupKey: string): StoredG4AdjRow[] {
  const groupDef = G4_GROUPS_DEF.find((g) => g.groupKey === groupKey)
  if (!groupDef || groupDef.rows.length === 0) return []
  return groupDef.rows.map((r) => ({
    rowKey: r.rowKey,
    label: r.label,
    openingUnadjusted: 0,
    openingAJE: 0,
    openingRJE: 0,
    periodDebit: 0,
    periodCredit: 0,
    closingAJE: 0,
    closingRJE: 0,
    reasonAnalysis: '',
    indexRef: '',
  }))
}

/** 从存储行计算展示行（借方公式） */
function computeRow(stored: StoredG4AdjRow): G4AdjudicationRow {
  const openingAdjusted = calcAdjustedAmount(
    stored.openingUnadjusted,
    stored.openingAJE,
    stored.openingRJE,
  )
  // 借方科目：期末未审 = 期初审定 + 借方 - 贷方
  const closingUnadjusted = calcDebitBalance(
    openingAdjusted,
    stored.periodDebit,
    stored.periodCredit,
  )
  const closingAdjusted = calcAdjustedAmount(
    closingUnadjusted,
    stored.closingAJE,
    stored.closingRJE,
  )
  const changeAmount = closingAdjusted - openingAdjusted
  const changeRate = calcChangeRate(openingAdjusted, closingAdjusted)

  return {
    id: stored.rowKey,
    item: stored.label,
    openingUnadjusted: stored.openingUnadjusted,
    openingAJE: stored.openingAJE,
    openingRJE: stored.openingRJE,
    openingAdjusted,
    closingUnadjusted,
    closingAJE: stored.closingAJE,
    closingRJE: stored.closingRJE,
    closingAdjusted,
    changeAmount,
    changeRate,
    reasonAnalysis: stored.reasonAnalysis,
    indexRef: stored.indexRef,
    isEditable: true,
    isSubtotal: false,
  }
}

/** 计算小计行（汇总多行） */
function computeSubtotalFromRows(rows: G4AdjudicationRow[], label: string, rowKey: string): G4AdjudicationRow {
  const sumField = (field: keyof G4AdjudicationRow) =>
    rows.reduce((acc, r) => acc + parseNum((r as any)[field]), 0)

  const openingAdjusted = sumField('openingAdjusted')
  const closingAdjusted = sumField('closingAdjusted')
  const changeAmount = closingAdjusted - openingAdjusted
  const changeRate = calcChangeRate(openingAdjusted, closingAdjusted)

  return {
    id: rowKey,
    item: label,
    openingUnadjusted: sumField('openingUnadjusted'),
    openingAJE: sumField('openingAJE'),
    openingRJE: sumField('openingRJE'),
    openingAdjusted,
    closingUnadjusted: sumField('closingUnadjusted'),
    closingAJE: sumField('closingAJE'),
    closingRJE: sumField('closingRJE'),
    closingAdjusted,
    changeAmount,
    changeRate,
    reasonAnalysis: '',
    indexRef: '',
    isEditable: false,
    isSubtotal: true,
  }
}

// ═══ Composable ═══

export function useG4MainAdjudication(options: UseG4MainAdjudicationOptions) {
  const { wpId, projectId, allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── 从 allResponses 解析原值组行数据 ────────────────────────────────────
  const storedOriginalRows = computed<StoredG4AdjRow[]>(() => {
    const key = `${GROUPS_STORAGE_KEY}-original-value`
    const resp = allResponses.value.get(key)
    const parsed = safeParseJson<StoredG4AdjRow[]>(resp?.remark)
    return parsed && parsed.length > 0 ? parsed : getDefaultStoredRows('original-value')
  })

  // ─── 从 allResponses 解析减值组行数据 ────────────────────────────────────
  const storedImpairmentRows = computed<StoredG4AdjRow[]>(() => {
    const key = `${GROUPS_STORAGE_KEY}-impairment`
    const resp = allResponses.value.get(key)
    const parsed = safeParseJson<StoredG4AdjRow[]>(resp?.remark)
    return parsed && parsed.length > 0 ? parsed : getDefaultStoredRows('impairment')
  })

  // ─── 一年内到期存储 ──────────────────────────────────────────────────────
  const storedOneYear = computed<StoredOneYearRow>(() => {
    const resp = allResponses.value.get(ONE_YEAR_KEY)
    const parsed = safeParseJson<StoredOneYearRow>(resp?.remark)
    return parsed ?? { openingAdjusted: 0, closingAdjusted: 0 }
  })

  // ─── 原值组计算行 ────────────────────────────────────────────────────────
  const originalValueRows: ComputedRef<G4AdjudicationRow[]> = computed(() =>
    storedOriginalRows.value.map(computeRow),
  )

  const originalValueSubtotal: ComputedRef<G4AdjudicationRow> = computed(() =>
    computeSubtotalFromRows(originalValueRows.value, '原值小计', 'ov-subtotal'),
  )

  /** 减：一年内到期行（原值组附属） */
  const oneYearDeductRow: ComputedRef<G4AdjudicationRow> = computed(() => {
    const data = storedOneYear.value
    const changeAmount = data.closingAdjusted - data.openingAdjusted
    const changeRate = calcChangeRate(data.openingAdjusted, data.closingAdjusted)
    return {
      id: 'ov-one-year-deduct',
      item: '减：一年内到期',
      openingUnadjusted: 0,
      openingAJE: 0,
      openingRJE: 0,
      openingAdjusted: data.openingAdjusted,
      closingUnadjusted: 0,
      closingAJE: 0,
      closingRJE: 0,
      closingAdjusted: data.closingAdjusted,
      changeAmount,
      changeRate,
      reasonAnalysis: '',
      indexRef: '',
      isEditable: true,
      isSubtotal: false,
    }
  })

  // ─── 减值组计算行 ────────────────────────────────────────────────────────
  const impairmentRows: ComputedRef<G4AdjudicationRow[]> = computed(() =>
    storedImpairmentRows.value.map(computeRow),
  )

  const impairmentSubtotal: ComputedRef<G4AdjudicationRow> = computed(() =>
    computeSubtotalFromRows(impairmentRows.value, '减值小计', 'imp-subtotal'),
  )

  // ─── 摊余成本（三、净值 = 原值小计 - 减值小计） ──────────────────────────
  const amortizedCostRow: ComputedRef<G4AdjudicationRow> = computed(() => {
    const ovSub = originalValueSubtotal.value
    const impSub = impairmentSubtotal.value

    const openingAdjusted = calcAmortizedCost(ovSub.openingAdjusted, impSub.openingAdjusted)
    const closingAdjusted = calcAmortizedCost(ovSub.closingAdjusted, impSub.closingAdjusted)
    const changeAmount = closingAdjusted - openingAdjusted
    const changeRate = calcChangeRate(openingAdjusted, closingAdjusted)

    return {
      id: 'amortized-cost',
      item: '三、债权投资净值（摊余成本）',
      openingUnadjusted: calcAmortizedCost(ovSub.openingUnadjusted, impSub.openingUnadjusted),
      openingAJE: ovSub.openingAJE - impSub.openingAJE,
      openingRJE: ovSub.openingRJE - impSub.openingRJE,
      openingAdjusted,
      closingUnadjusted: calcAmortizedCost(ovSub.closingUnadjusted, impSub.closingUnadjusted),
      closingAJE: ovSub.closingAJE - impSub.closingAJE,
      closingRJE: ovSub.closingRJE - impSub.closingRJE,
      closingAdjusted,
      changeAmount,
      changeRate,
      reasonAnalysis: '',
      indexRef: '',
      isEditable: false,
      isSubtotal: true,
    }
  })

  // ─── 一年内到期非流动资产列报数 ─────────────────────────────────────────
  const oneYearMaturityRow: ComputedRef<G4AdjudicationRow> = computed(() => {
    const data = storedOneYear.value
    const changeAmount = data.closingAdjusted - data.openingAdjusted
    const changeRate = calcChangeRate(data.openingAdjusted, data.closingAdjusted)
    return {
      id: 'one-year-maturity',
      item: '一年内到期非流动资产列报数',
      openingUnadjusted: 0,
      openingAJE: 0,
      openingRJE: 0,
      openingAdjusted: data.openingAdjusted,
      closingUnadjusted: 0,
      closingAJE: 0,
      closingRJE: 0,
      closingAdjusted: data.closingAdjusted,
      changeAmount,
      changeRate,
      reasonAnalysis: '',
      indexRef: '',
      isEditable: true,
      isSubtotal: false,
    }
  })

  // ─── 三大分组汇总结构（供模板渲染） ──────────────────────────────────────
  const groups: ComputedRef<AdjudicationGroup[]> = computed(() => [
    {
      groupKey: 'original-value',
      groupName: '一、债权投资原值',
      expanded: true,
      rows: originalValueRows.value,
      subtotal: originalValueSubtotal.value,
      oneYearDeduct: oneYearDeductRow.value,
    },
    {
      groupKey: 'impairment',
      groupName: '二、债权投资减值准备',
      expanded: true,
      rows: impairmentRows.value,
      subtotal: impairmentSubtotal.value,
    },
    {
      groupKey: 'amortized-cost',
      groupName: '三、债权投资净值（摊余成本）',
      expanded: true,
      rows: [],
      subtotal: amortizedCostRow.value,
    },
  ])

  // ─── 试算表取数（科目1501） ──────────────────────────────────────────────
  const trialBalanceAmount: ComputedRef<number> = computed(() =>
    parseNum(allResponses.value.get(TB_STORAGE_KEY)?.remark),
  )

  /** 差异 = 摊余成本审定 - 试算表数 */
  const variance: ComputedRef<number> = computed(() =>
    amortizedCostRow.value.closingAdjusted - trialBalanceAmount.value,
  )

  /** 差异≠0红色标记 */
  const hasVarianceHighlight: ComputedRef<boolean> = computed(() =>
    Math.abs(variance.value) > 0.005,
  )

  // ─── 审计备注/结论同步 ──────────────────────────────────────────────────
  watch(
    () => allResponses.value.get(NOTE_KEY)?.remark,
    (v) => { auditNote.value = v || '' },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get(CONCLUSION_KEY)?.remark,
    (v) => { auditConclusion.value = v || '' },
    { immediate: true },
  )

  // ─── TB取数（从后端 trial_balance 端点获取） ─────────────────────────────
  async function fetchTrialBalance(): Promise<void> {
    if (!projectId.value) return
    try {
      const resp = await (await import('@/services/apiProxy')).api.get(
        `/api/projects/${projectId.value}/trial-balance`,
        { params: { account_code: G4_ACCOUNT_CODE }, _silent: true } as any,
      )
      const data = resp?.data?.data ?? resp?.data
      if (data) {
        // trial_balance 返回 audited_amount 或 unadjusted_amount
        const tbAmount = parseNum(data.audited_amount ?? data.unadjusted_amount ?? 0)
        setTrialBalance(tbAmount)
      }
    } catch {
      /* TB取数失败不阻塞编辑 */
    }
  }

  // ─── EventBus: publish substantive:adjudicated（科目1501）───────────────
  function publishAdjudicated(): void {
    const amount = amortizedCostRow.value.closingAdjusted
    const payload = {
      wpCode: 'G4',
      accountCode: G4_ACCOUNT_CODE,
      adjudicatedAmount: amount,
      auditedAmount: amount,
    }
    try {
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', { detail: payload }))
    } catch { /* EventBus publish 失败不阻塞编辑 */ }
  }

  // 审定数变化时自动发布
  watch(
    () => amortizedCostRow.value.closingAdjusted,
    () => { publishAdjudicated() },
  )

  // ─── 单元格编辑 ─────────────────────────────────────────────────────────
  function updateCell(groupKey: string, rowKey: string, field: string, value: number | string): void {
    if (readonly.value) return
    const storageKey = `${GROUPS_STORAGE_KEY}-${groupKey}`
    const defaults = getDefaultStoredRows(groupKey)
    const parsed = safeParseJson<StoredG4AdjRow[]>(allResponses.value.get(storageKey)?.remark)
    const stored = parsed && parsed.length > 0 ? parsed : defaults.map((r) => ({ ...r }))
    const idx = stored.findIndex((r) => r.rowKey === rowKey)
    if (idx === -1) return

    if (field === 'indexRef' || field === 'reasonAnalysis') {
      ;(stored[idx] as any)[field] = String(value ?? '')
    } else {
      ;(stored[idx] as any)[field] = typeof value === 'number' ? value : parseNum(value)
    }
    persistGroupRows(storageKey, stored)
  }

  /** 更新一年内到期行 */
  function updateOneYearRow(field: 'openingAdjusted' | 'closingAdjusted', value: number | string): void {
    if (readonly.value) return
    const current = { ...storedOneYear.value }
    current[field] = typeof value === 'number' ? value : parseNum(value)
    allResponses.value.set(ONE_YEAR_KEY, {
      item_id: ONE_YEAR_KEY,
      conclusion: null,
      remark: JSON.stringify(current),
    })
    debounceSave()
  }

  /** 设置试算表取数值 */
  function setTrialBalance(amount: number): void {
    allResponses.value.set(TB_STORAGE_KEY, {
      item_id: TB_STORAGE_KEY,
      conclusion: null,
      remark: String(amount),
    })
    debounceSave()
  }

  // ─── 动态行增删（调用方需先 ElMessageBox.prompt 获取名称） ──────────────
  function addRow(groupKey: string, label: string): void {
    if (readonly.value || !label?.trim()) return
    const storageKey = `${GROUPS_STORAGE_KEY}-${groupKey}`
    const defaults = getDefaultStoredRows(groupKey)
    const parsed = safeParseJson<StoredG4AdjRow[]>(allResponses.value.get(storageKey)?.remark)
    const stored = parsed && parsed.length > 0 ? parsed : defaults.map((r) => ({ ...r }))
    stored.push({
      rowKey: `${groupKey}-${Date.now()}`,
      label: label.trim(),
      openingUnadjusted: 0,
      openingAJE: 0,
      openingRJE: 0,
      periodDebit: 0,
      periodCredit: 0,
      closingAJE: 0,
      closingRJE: 0,
      reasonAnalysis: '',
      indexRef: '',
    })
    persistGroupRows(storageKey, stored)
  }

  function removeRow(groupKey: string, rowKey: string): void {
    if (readonly.value) return
    const storageKey = `${GROUPS_STORAGE_KEY}-${groupKey}`
    const parsed = safeParseJson<StoredG4AdjRow[]>(allResponses.value.get(storageKey)?.remark)
    if (!parsed) return
    const stored = parsed.filter((r) => r.rowKey !== rowKey)
    persistGroupRows(storageKey, stored)
  }

  // ─── 持久化 ─────────────────────────────────────────────────────────────
  function persistGroupRows(storageKey: string, rows: StoredG4AdjRow[]): void {
    allResponses.value.set(storageKey, {
      item_id: storageKey,
      conclusion: null,
      remark: JSON.stringify(rows),
    })
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
      const keys = [
        `${GROUPS_STORAGE_KEY}-original-value`,
        `${GROUPS_STORAGE_KEY}-impairment`,
        TB_STORAGE_KEY,
        ONE_YEAR_KEY,
        NOTE_KEY,
        CONCLUSION_KEY,
      ]
      const items = keys
        .map((k) => allResponses.value.get(k))
        .filter(Boolean)
      window.dispatchEvent(new CustomEvent('g4:save-items', { detail: { items } }))
    } catch { /* silent */ }
  }

  // 审计备注/结论变更持久化
  watch(auditNote, (val) => {
    allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    debounceSave()
  })
  watch(auditConclusion, (val) => {
    allResponses.value.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
    debounceSave()
  })

  // ─── 序列化/反序列化 ─────────────────────────────────────────────────────
  function serialize(): Record<string, string> {
    return {
      [`${GROUPS_STORAGE_KEY}-original-value`]: JSON.stringify(storedOriginalRows.value),
      [`${GROUPS_STORAGE_KEY}-impairment`]: JSON.stringify(storedImpairmentRows.value),
      [TB_STORAGE_KEY]: String(trialBalanceAmount.value),
      [ONE_YEAR_KEY]: JSON.stringify(storedOneYear.value),
      [NOTE_KEY]: auditNote.value,
      [CONCLUSION_KEY]: auditConclusion.value,
    }
  }

  function deserialize(data: Record<string, string>): void {
    for (const key of [
      `${GROUPS_STORAGE_KEY}-original-value`,
      `${GROUPS_STORAGE_KEY}-impairment`,
      TB_STORAGE_KEY,
      ONE_YEAR_KEY,
    ]) {
      if (data[key] !== undefined) {
        allResponses.value.set(key, { item_id: key, conclusion: null, remark: data[key] })
      }
    }
    if (data[NOTE_KEY] !== undefined) auditNote.value = data[NOTE_KEY]
    if (data[CONCLUSION_KEY] !== undefined) auditConclusion.value = data[CONCLUSION_KEY]
  }

  // ─── 生命周期清理 ───────────────────────────────────────────────────────
  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    // 分组数据
    groups,
    originalValueRows,
    originalValueSubtotal,
    oneYearDeductRow,
    impairmentRows,
    impairmentSubtotal,
    amortizedCostRow,
    oneYearMaturityRow,
    // 试算表+差异
    trialBalanceAmount,
    variance,
    hasVarianceHighlight,
    // 审计备注
    auditNote,
    auditConclusion,
    // 操作
    updateCell,
    updateOneYearRow,
    setTrialBalance,
    fetchTrialBalance,
    addRow,
    removeRow,
    publishAdjudicated,
    serialize,
    deserialize,
  }
}

export default useG4MainAdjudication
