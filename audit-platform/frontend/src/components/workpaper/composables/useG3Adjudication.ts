/**
 * useG3Adjudication — G3-1 审定表（借方科目 1131 应收股利）
 *
 * 借方公式链：
 *   期初审定 = 期初未审 + 期初AJE + 期初RJE
 *   期末未审 = 期初审定 + 本期宣告(借方) - 本期收回(贷方)
 *   期末审定 = 期末未审 + 期末AJE + 期末RJE
 *   变动额/率 = 期末审定 vs 期初审定；|变动率|>30% 原因分析必填
 *
 * 行结构：按被投资方逐行（动态增删）+ 合计 + 试算表数 + 差异
 * 账龄汇总：参照 G3-5 逾期≥365天拆分一年内/一年以上（对齐 Excel 模板口径）
 *
 * Spec: .kiro/specs/g3-dividend-receivable/ Task 4.1
 * Requirements: 3.1~3.10
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, inject, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import {
  parseNum,
  calcDebitBalance,
  calcAdjustedAmount,
  calcSubtotal,
  calcChangeAmount,
  calcChangeRate,
  isChangeRateExceeding,
} from './useG3DivRecFormulaEngine'
import {
  applyG3AdjustmentWriteback,
  parseG3AdjStore,
  computeG3AgingSummary,
  aggregateG3DetailByInvestee,
  applyG3DetailSyncToAdjStore,
  G3_CHANGE_RATE_THRESHOLD,
  G3_OVERDUE_STORAGE_KEY,
  type StoredG3AdjRow,
  type G3AgingSummary,
} from './g3AdjudicationItems'
import {
  G3_ACCOUNT_CODE,
  G3_ADJ_STORAGE_KEY,
  G3_ADJ_TB_KEY,
  G3_ADJ_NOTE_KEY,
  G3_ADJ_CONCLUSION_KEY,
  G3_WP_CODE,
  G3_DETAIL_ROWS_KEY,
} from './g3Constants'
import { G3SaveItemsKey, G3WritebackTbKey, G3DetailRevisionKey } from './g3InternalKeys'
import { useWorkpaperAuditYear, resolveAuditYearNumber } from './workpaperAuditYear'
import type { ChecklistResponse } from './useF1FormData'

/** 科目：应收股利 */
export { G3_ACCOUNT_CODE }

export { G3_CHANGE_RATE_THRESHOLD }

// ─── Types ───────────────────────────────────────────────────────────────────

export interface G3AdjudicationRow {
  id: string
  investeeName: string          // 被投资方
  shareholdingRatio: number     // 持股比例
  openingUnadjusted: number
  openingAJE: number
  openingRJE: number
  openingAdjusted: number       // 公式：期初未审 + AJE + RJE
  closingUnadjusted: number     // 借方公式：期初审定 + 本期宣告 - 本期收回
  closingAJE: number
  closingRJE: number
  closingAdjusted: number       // 公式：期末未审 + AJE + RJE
  currentDeclared: number       // 本期宣告(借方)
  currentReceived: number       // 本期收回(贷方)
  /** 期末审定 − 期初审定 */
  changeAmount: number
  /** (期末审定 − 期初审定) / 期初审定 */
  changeRate: number | '' | 'N/A'
  changeRateHighlight: boolean
  reasonRequired: boolean
  reasonAnalysis: string
  remark: string
  indexRef: string
}

// ─── Storage keys ────────────────────────────────────────────────────────────

const ADJ_STORAGE_KEY = G3_ADJ_STORAGE_KEY
const TB_STORAGE_KEY = G3_ADJ_TB_KEY
const NOTE_KEY = G3_ADJ_NOTE_KEY
const CONCLUSION_KEY = G3_ADJ_CONCLUSION_KEY

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 从存储行计算展示行（含公式字段） */
function computeRow(stored: StoredG3AdjRow): G3AdjudicationRow {
  const openingAdjusted = calcAdjustedAmount(stored.openingUnadjusted, stored.openingAJE, stored.openingRJE)
  // 借方科目：期末未审 = 期初审定 + 本期宣告(借方) - 本期收回(贷方)
  const closingUnadjusted = calcDebitBalance(openingAdjusted, stored.currentDeclared, stored.currentReceived)
  const closingAdjusted = calcAdjustedAmount(closingUnadjusted, stored.closingAJE, stored.closingRJE)
  const changeAmount = calcChangeAmount(closingAdjusted, openingAdjusted)
  const changeRate = calcChangeRate(openingAdjusted, closingAdjusted)
  const changeRateHighlight = isChangeRateExceeding(changeRate, G3_CHANGE_RATE_THRESHOLD)
  return {
    id: stored.id,
    investeeName: stored.investeeName,
    shareholdingRatio: stored.shareholdingRatio,
    openingUnadjusted: stored.openingUnadjusted,
    openingAJE: stored.openingAJE,
    openingRJE: stored.openingRJE,
    openingAdjusted,
    closingUnadjusted,
    closingAJE: stored.closingAJE,
    closingRJE: stored.closingRJE,
    closingAdjusted,
    currentDeclared: stored.currentDeclared,
    currentReceived: stored.currentReceived,
    changeAmount,
    changeRate,
    changeRateHighlight,
    reasonRequired: changeRateHighlight,
    reasonAnalysis: stored.reasonAnalysis ?? '',
    remark: stored.remark,
    indexRef: stored.indexRef,
  }
}

function makeEmptyStoredRow(id: string, investeeName: string): StoredG3AdjRow {
  return {
    id,
    investeeName,
    shareholdingRatio: 0,
    openingUnadjusted: 0,
    openingAJE: 0,
    openingRJE: 0,
    currentDeclared: 0,
    currentReceived: 0,
    closingAJE: 0,
    closingRJE: 0,
    remark: '',
    indexRef: '',
    reasonAnalysis: '',
  }
}

// ─── Composable options ──────────────────────────────────────────────────────

export interface UseG3AdjudicationOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
  /** 审计年度；取试算平衡表必填 Query year */
  auditYear?: Ref<number | string | null | undefined>
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG3Adjudication(options: UseG3AdjudicationOptions) {
  const { projectId, allResponses, isReadonly, auditYear } = options
  const readonly = isReadonly ?? ref(false)
  const saveItemsFn = inject(G3SaveItemsKey, null)
  const writebackTbFn = inject(G3WritebackTbKey, null)
  const detailRevision = inject(G3DetailRevisionKey, null)
  const runtimeYear = useWorkpaperAuditYear(auditYear)
  /** 已跟进的 G3-2 修订号（热更新用） */
  let lastDetailRevSeen = -1

  function resolveAuditYear(): number | null {
    return resolveAuditYearNumber(auditYear, runtimeYear.value)
  }

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── 从 allResponses 解析行数据 ────────────────────────────────────────
  const storedRows = computed<StoredG3AdjRow[]>(() =>
    parseG3AdjStore(allResponses.value.get(ADJ_STORAGE_KEY)?.remark),
  )

  /** 数据行（公式自动计算） */
  const dataRows: ComputedRef<G3AdjudicationRow[]> = computed(() =>
    storedRows.value.map((s) => computeRow(s)),
  )

  /** 合计行 */
  const subtotalRow: ComputedRef<G3AdjudicationRow> = computed(() => {
    const rows = dataRows.value
    const stored: StoredG3AdjRow = {
      id: 'subtotal',
      investeeName: '合计',
      shareholdingRatio: 0,
      openingUnadjusted: calcSubtotal(rows.map((r) => r.openingUnadjusted)),
      openingAJE: calcSubtotal(rows.map((r) => r.openingAJE)),
      openingRJE: calcSubtotal(rows.map((r) => r.openingRJE)),
      currentDeclared: calcSubtotal(rows.map((r) => r.currentDeclared)),
      currentReceived: calcSubtotal(rows.map((r) => r.currentReceived)),
      closingAJE: calcSubtotal(rows.map((r) => r.closingAJE)),
      closingRJE: calcSubtotal(rows.map((r) => r.closingRJE)),
      remark: '',
      indexRef: '',
      reasonAnalysis: '',
    }
    return computeRow(stored)
  })

  /** 是否存在非零期初 AJE/RJE（前期差错/重述） */
  const hasOpeningAdjustments: ComputedRef<boolean> = computed(() =>
    dataRows.value.some(
      (r) => Math.abs(r.openingAJE) > 0.005 || Math.abs(r.openingRJE) > 0.005,
    ),
  )

  /** 账龄一年内/一年以上汇总（参照 G3-5） */
  const agingSummary: ComputedRef<G3AgingSummary> = computed(() =>
    computeG3AgingSummary(
      subtotalRow.value.closingAdjusted,
      allResponses.value.get(G3_OVERDUE_STORAGE_KEY)?.conclusion,
    ),
  )

  /** 是否存在需填原因分析的行 */
  const hasReasonGaps: ComputedRef<boolean> = computed(() =>
    dataRows.value.some((r) => r.reasonRequired && !String(r.reasonAnalysis || '').trim()),
  )

  /** 试算表取数（科目1131） */
  const trialBalanceAmount: ComputedRef<number> = computed(() =>
    parseNum(allResponses.value.get(TB_STORAGE_KEY)?.remark),
  )

  /** 差异 = 期末审定合计 - 试算表数 */
  const variance: ComputedRef<number> = computed(() =>
    subtotalRow.value.closingAdjusted - trialBalanceAmount.value,
  )

  /** 差异≠0红色标记 */
  const hasVarianceHighlight: ComputedRef<boolean> = computed(() =>
    Math.abs(variance.value) > 0.005,
  )

  // ─── 审计备注/结论 同步 ─────────────────────────────────────────────
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

  // ─── EventBus: publish substantive:adjudicated + TB writeback（科目1131）──
  function publishAdjudicated(): void {
    const amount = subtotalRow.value.closingAdjusted
    try {
      eventBus.emit('substantive:adjudicated', {
        wpCode: G3_WP_CODE,
        accountCode: G3_ACCOUNT_CODE,
        auditedAmount: amount,
        timestamp: Date.now(),
      })
      if (writebackTbFn) {
        void writebackTbFn(amount)
      }
    } catch { /* EventBus publish 失败不阻塞编辑 */ }
  }

  // 审定合计变化时自动发布
  watch(
    () => subtotalRow.value.closingAdjusted,
    () => { publishAdjudicated() },
  )

  // ─── 单元格编辑 ─────────────────────────────────────────────────────
  function updateCell(rowId: string, field: string, value: number | string): void {
    if (readonly.value) return
    const stored = parseG3AdjStore(allResponses.value.get(ADJ_STORAGE_KEY)?.remark)
    const idx = stored.findIndex((r) => r.id === rowId)
    if (idx === -1) return
    if (
      field === 'indexRef'
      || field === 'remark'
      || field === 'investeeName'
      || field === 'reasonAnalysis'
    ) {
      ;(stored[idx] as Record<string, unknown>)[field] = String(value ?? '')
    } else {
      ;(stored[idx] as Record<string, unknown>)[field] =
        typeof value === 'number' ? value : parseNum(value)
    }
    persistRows(stored)
  }

  // ─── 动态行增删（新增弹ElMessageBox.prompt输入被投资方名称）────────────
  async function addRow(): Promise<void> {
    if (readonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入被投资方名称', '新增被投资方', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '名称不能为空',
      })
      const stored = parseG3AdjStore(allResponses.value.get(ADJ_STORAGE_KEY)?.remark)
      const newRow = makeEmptyStoredRow(String(Date.now()), value.trim())
      stored.push(newRow)
      persistRows(stored)
    } catch { /* 用户取消 */ }
  }

  function removeRow(rowId: string): void {
    if (readonly.value) return
    const stored = parseG3AdjStore(allResponses.value.get(ADJ_STORAGE_KEY)?.remark)
    const filtered = stored.filter((r) => r.id !== rowId)
    persistRows(filtered)
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

  /** 拉取试算 1131（优先 audited_amount / unadjusted_amount；year 必填） */
  async function fetchTrialBalance(): Promise<number | null> {
    const pid = projectId.value
    const year = resolveAuditYear()
    if (!pid || year == null) return null
    try {
      const res = await api.get(`/api/projects/${pid}/trial-balance`, {
        params: { year, account_prefix: G3_ACCOUNT_CODE },
        _silent: true,
      } as any)
      const list = Array.isArray(res?.data ?? res)
        ? (res?.data ?? res)
        : (res?.data?.items ?? [])
      const hit = list.find((r: any) =>
        String(r.standard_account_code ?? r.account_code ?? '').startsWith(G3_ACCOUNT_CODE),
      )
      if (!hit) return null
      const amount = parseNum(
        hit.audited_amount ?? hit.unadjusted_amount ?? hit.ending_balance
          ?? ((Number(hit.debit_amount ?? 0) - Number(hit.credit_amount ?? 0))),
      )
      setTrialBalance(amount)
      return amount
    } catch {
      return null
    }
  }

  function applyAdjustmentWriteback(netAJE: number, netRJE: number): void {
    if (readonly.value) return
    const stored = parseG3AdjStore(allResponses.value.get(ADJ_STORAGE_KEY)?.remark)
    persistRows(applyG3AdjustmentWriteback(stored, netAJE, netRJE))
    publishAdjudicated()
  }

  /**
   * 从 G3-2 按被投资方汇总本期宣告/收回 → G3-1。
   * 保留期初未审与 AJE/RJE（含账项调整汇总行）；缺行则新建。
   */
  function syncFromDetail(opts?: { quiet?: boolean }): { added: number; updated: number } {
    if (readonly.value) return { added: 0, updated: 0 }
    const raw = allResponses.value.get(G3_DETAIL_ROWS_KEY)?.conclusion
    const aggs = aggregateG3DetailByInvestee(raw)
    if (!aggs.length) return { added: 0, updated: 0 }
    const stored = parseG3AdjStore(allResponses.value.get(ADJ_STORAGE_KEY)?.remark)
    const { next, added, updated } = applyG3DetailSyncToAdjStore(stored, aggs)
    persistRows(next)
    publishAdjudicated()
    if (detailRevision) lastDetailRevSeen = detailRevision.value
    void opts
    return { added, updated }
  }

  /** G3-2 变更后：若已有审定行则静默刷新宣告/收回；无行不自动新建 */
  function softSyncFromDetailIfNeeded(): void {
    if (readonly.value || !detailRevision) return
    const rev = detailRevision.value
    if (rev <= lastDetailRevSeen) return
    lastDetailRevSeen = rev
    const hasInvestee = parseG3AdjStore(allResponses.value.get(ADJ_STORAGE_KEY)?.remark)
      .some((r) => r.investeeName.trim() && r.investeeName !== '账项调整汇总' && r.id !== 'g3-adj-writeback')
    if (!hasInvestee) return
    // 已有行：完整 sync（含新建缺失被投资方），保持与按钮一致但无 UI 提示
    syncFromDetail({ quiet: true })
  }

  function handleAdjustmentConfirmed(d: {
    accountCode: string
    netAJE: number
    netRJE: number
    rowCount?: number
  }): void {
    if (!d || d.accountCode !== G3_ACCOUNT_CODE) return
    applyAdjustmentWriteback(Number(d.netAJE ?? 0), Number(d.netRJE ?? 0))
  }

  // ─── 持久化 ─────────────────────────────────────────────────────────
  function persistRows(rows: StoredG3AdjRow[]): void {
    const json = JSON.stringify(rows)
    allResponses.value.set(ADJ_STORAGE_KEY, {
      item_id: ADJ_STORAGE_KEY,
      conclusion: null,
      remark: json,
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
      const items = [
        allResponses.value.get(ADJ_STORAGE_KEY),
        allResponses.value.get(NOTE_KEY),
        allResponses.value.get(CONCLUSION_KEY),
        allResponses.value.get(TB_STORAGE_KEY),
      ].filter(Boolean) as ChecklistResponse[]
      if (saveItemsFn) void saveItemsFn(items)
    } catch { /* silent */ }
  }

  watch(auditNote, (val) => {
    allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    debounceSave()
  })

  watch(auditConclusion, (val) => {
    allResponses.value.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
    debounceSave()
  })

  onMounted(() => {
    eventBus.on('g3:adjustment-confirmed', handleAdjustmentConfirmed)
    softSyncFromDetailIfNeeded()
  })

  if (detailRevision) {
    watch(detailRevision, () => softSyncFromDetailIfNeeded())
  }

  onBeforeUnmount(() => {
    eventBus.off('g3:adjustment-confirmed', handleAdjustmentConfirmed)
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    dataRows,
    subtotalRow,
    trialBalanceAmount,
    variance,
    hasVarianceHighlight,
    hasOpeningAdjustments,
    agingSummary,
    hasReasonGaps,
    auditNote,
    auditConclusion,
    updateCell,
    addRow,
    removeRow,
    setTrialBalance,
    fetchTrialBalance,
    syncFromDetail,
    applyAdjustmentWriteback,
    publishAdjudicated,
  }
}

export default useG3Adjudication
