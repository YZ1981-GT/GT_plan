/**
 * useK9Cutoff — K9-6/K9-7 截止测试逻辑（双向）
 *
 * Spec: .kiro/specs/k9-admin-expenses/
 * Task: 3.4
 * Requirements: 5.1-5.6, 9.7
 *
 * 职责：
 * - 管理截止测试样本（K9-6记账→原始 / K9-7原始→记账）
 * - 使用 isCrossPeriod / autoSampleCutoff from K9CutoffEngine
 * - 两个方向：V2S (voucher-to-source) 和 S2V (source-to-voucher)
 * - 自动从序时账抽样期末±5天凭证 (useCutoffAutoSampling)
 * - 跨期项红色标记并提示调整
 * - 行级抽凭 support
 *
 * Item IDs: "K9-6-row-{idx}-{field}" / "K9-7-row-{idx}-{field}"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { parseNum } from './useK9FormulaEngine'
import { isCrossPeriod } from './useK9CutoffEngine'
import { deriveConclusion as canonicalDeriveConclusion } from './cutoffCanonical'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 截止测试方向 */
export type CutoffDirection = 'V2S' | 'S2V'

/** 截止测试样本行 */
export interface K9CutoffRow {
  rowKey: string
  /** 序号 */
  index: number
  /** 凭证号 */
  voucherNo: string
  /** 记账日期 YYYY-MM-DD */
  bookDate: string
  /** 摘要 */
  summary: string
  /** 金额 */
  amount: number
  /** 原始凭证日期 YYYY-MM-DD */
  sourceDate: string
  /** 科目编码 */
  accountCode: string
  /** 科目名称 */
  accountName: string
  /** 是否跨期（公式列：自动计算） */
  isCross: boolean
  /** 是否及时入账（S2V方向专用） */
  isTimely: boolean
  /** 审核结论 */
  conclusion: string
  /** 备注 */
  remark: string
}

export interface K9CutoffSummary {
  totalSamples: number
  crossPeriodCount: number
  /** 正常项数量（双侧证据齐全且同期；不含证据不完整） */
  normalCount: number
  /** 证据不完整项数量（缺记账侧或原始凭证侧独立证据，不得判正常/完成） */
  incompleteCount: number
  crossPeriodItems: Array<{ voucherNo: string; amount: number }>
}

export interface UseK9CutoffParams {
  /** 方向：V2S=记账→原始(K9-6)，S2V=原始→记账(K9-7) */
  direction: CutoffDirection
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  /** 会计期间截止日（如"2025-12-31"） */
  periodEnd?: Ref<string>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ACCOUNT_CODE_6602 = '6602'
const DEFAULT_THRESHOLD_DAYS = 5

function getKeys(direction: CutoffDirection) {
  const sheetId = direction === 'V2S' ? 'K9-6' : 'K9-7'
  return {
    sheetId,
    ROWS_KEY: `${sheetId}-rows`,
    CONCLUSION_KEY: `${sheetId}-conclusion`,
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK9Cutoff(params: UseK9CutoffParams) {
  const { direction, allResponses, projectId, wpId, periodEnd, isReadonly, onSave } = params
  const { sheetId, ROWS_KEY, CONCLUSION_KEY } = getKeys(direction)

  // ─── State ─────────────────────────────────────────────────────────────────

  const samples = ref<K9CutoffRow[]>([])
  const conclusion = ref('')
  const isChanged = ref(false)
  const isLoading = ref(false)

  // ─── Load ──────────────────────────────────────────────────────────────────

  function initFromResponses(): void {
    const raw = _getJson(ROWS_KEY)
    if (Array.isArray(raw) && raw.length > 0) {
      samples.value = raw.map((r: any, idx: number) => _normalizeSample(r, idx))
    } else {
      samples.value = []
    }
    conclusion.value = _getString(CONCLUSION_KEY)
  }

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  /**
   * 默认结论派生：截止测试须记账侧(bookDate)与原始单据侧(sourceDate)两份独立证据齐全
   * 才可下"正常/跨期"结论；任一侧缺失（自动提取仅得记账侧、原始凭证未取得）→ "证据不完整"，
   * 不得假绿为"正常"。审计师手工录入的 conclusion 优先。
   */
  function _defaultConclusion(bookDate: string, sourceDate: string, _isCross: boolean): string {
    // 委托 cutoffCanonical.deriveConclusion（natural-month 单一真源）：
    // 缺任一侧日期→证据不完整；双侧齐全按自然月跨期→跨期/正常。行为等价（非法日期边界更严格）。
    const end = periodEnd?.value ?? '2025-12-31'
    return canonicalDeriveConclusion({ bookDate, documentDate: sourceDate }, end, 'natural-month')
  }

  function _normalizeSample(raw: any, idx: number): K9CutoffRow {
    const bookDate = raw.bookDate ?? ''
    const sourceDate = raw.sourceDate ?? ''
    const end = periodEnd?.value ?? '2025-12-31'
    const isCross = isCrossPeriod(sourceDate, bookDate, end)

    return {
      rowKey: raw.rowKey ?? `row-${idx}`,
      index: idx + 1,
      voucherNo: raw.voucherNo ?? '',
      bookDate, summary: raw.summary ?? '',
      amount: parseNum(raw.amount),
      sourceDate,
      accountCode: raw.accountCode ?? ACCOUNT_CODE_6602,
      accountName: raw.accountName ?? '',
      isCross, isTimely: raw.isTimely ?? !isCross,
      conclusion: raw.conclusion ?? _defaultConclusion(bookDate, sourceDate, isCross),
      remark: raw.remark ?? '',
    }
  }

  // ─── Computed: 带公式列的完整行 ───────────────────────────────────────────

  const computedSamples: ComputedRef<K9CutoffRow[]> = computed(() => {
    const end = periodEnd?.value ?? '2025-12-31'
    return samples.value.map((row, idx) => {
      const isCross = isCrossPeriod(row.sourceDate, row.bookDate, end)
      return {
        ...row,
        index: idx + 1,
        isCross,
        isTimely: direction === 'S2V' ? !isCross : row.isTimely,
        conclusion: row.conclusion || _defaultConclusion(row.bookDate, row.sourceDate, isCross),
      }
    })
  })

  // ─── Computed: 汇总统计 ────────────────────────────────────────────────────

  const summary: ComputedRef<K9CutoffSummary> = computed(() => {
    const all = computedSamples.value
    const crossItems = all.filter(r => r.isCross)
    // 证据不完整单列，不计入 normalCount，与统一状态机+完成门禁一致
    const incompleteItems = all.filter(r => r.conclusion === '证据不完整')
    return {
      totalSamples: all.length,
      crossPeriodCount: crossItems.length,
      incompleteCount: incompleteItems.length,
      normalCount: all.length - crossItems.length - incompleteItems.length,
      crossPeriodItems: crossItems.map(r => ({ voucherNo: r.voucherNo, amount: r.amount })),
    }
  })

  // ─── 自动抽样（从序时账±5天） ─────────────────────────────────────────────

  async function autoSample(): Promise<void> {
    if (isReadonly?.value) return
    isLoading.value = true
    try {
      const { default: http } = await import('@/utils/http')
      const end = periodEnd?.value ?? '2025-12-31'
      const yr = Number(String(end).slice(0, 4)) || new Date().getFullYear()
      // 真实端点：POST /sampling/cutoff-test（提取期末±N天序时账交易）
      // 旧代码调 GET ledger/cutoff-samples 为不存在端点，导致「自动提取」恒失败。
      const res = await http.post(`/api/projects/${projectId.value}/sampling/cutoff-test`, {
        account_codes: [ACCOUNT_CODE_6602],
        year: yr,
        days_before: DEFAULT_THRESHOLD_DAYS,
        days_after: DEFAULT_THRESHOLD_DAYS,
        amount_threshold: 0, // 阈值0=窗口内全部非零凭证（管理费用逐笔）
        cutoff_date: end, // 显式截止基准日 = 资产负债表日，后端据此取窗口
      })
      const payload = (res as any).data?.data ?? (res as any).data ?? {}
      const entries: any[] = Array.isArray(payload.entries) ? payload.entries : []

      samples.value = entries.map((e, idx) => ({
        rowKey: `row-${idx}-${Date.now()}`,
        index: idx + 1,
        voucherNo: e.voucher_no ?? '',
        bookDate: e.voucher_date ?? '',
        summary: e.summary ?? '',
        amount: parseNum(e.debit_amount) || parseNum(e.credit_amount),
        // 端点仅返回记账凭证（无原始凭证日期）→ 由审计师追查补录 sourceDate 后判定跨期
        sourceDate: '',
        accountCode: e.account_code ?? ACCOUNT_CODE_6602,
        accountName: e.account_name ?? '',
        isCross: false,
        isTimely: true,
        conclusion: '',
        remark: '',
      }))

      isChanged.value = true
      _persist()
      if (samples.value.length > 0) {
        ElMessage.success(`已从序时账提取 ${samples.value.length} 条截止样本（期末±${DEFAULT_THRESHOLD_DAYS}天），请补充原始凭证日期后判定跨期`)
      } else {
        ElMessage.info('期末±5天窗口内未提取到管理费用凭证')
      }
    } catch {
      ElMessage.warning('截止样本自动提取失败，请手动录入')
    } finally {
      isLoading.value = false
    }
  }

  // ─── 手动新增样本 ─────────────────────────────────────────────────────────

  function addSample(data?: Partial<K9CutoffRow>): void {
    if (isReadonly?.value) return
    const idx = samples.value.length
    samples.value.push({
      rowKey: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      index: idx + 1,
      voucherNo: data?.voucherNo ?? '',
      bookDate: data?.bookDate ?? '',
      summary: data?.summary ?? '',
      amount: parseNum(data?.amount),
      sourceDate: data?.sourceDate ?? '',
      accountCode: data?.accountCode ?? ACCOUNT_CODE_6602,
      accountName: data?.accountName ?? '',
      isCross: false, isTimely: true,
      conclusion: '', remark: '',
    })
    isChanged.value = true
    _persist()
  }

  function removeSample(rowKey: string): void {
    if (isReadonly?.value) return
    const idx = samples.value.findIndex(r => r.rowKey === rowKey)
    if (idx >= 0) {
      samples.value.splice(idx, 1)
      isChanged.value = true
      _persist()
    }
  }

  // ─── Cell Update ───────────────────────────────────────────────────────────

  function updateCell(rowKey: string, field: string, value: any): void {
    if (isReadonly?.value) return
    const row = samples.value.find(r => r.rowKey === rowKey)
    if (!row) return
    ;(row as any)[field] = value

    // 日期变化时自动重算跨期
    if (field === 'bookDate' || field === 'sourceDate') {
      const end = periodEnd?.value ?? '2025-12-31'
      row.isCross = isCrossPeriod(row.sourceDate, row.bookDate, end)
      row.isTimely = !row.isCross
      if (!row.conclusion) row.conclusion = _defaultConclusion(row.bookDate, row.sourceDate, row.isCross)
    }

    isChanged.value = true
    _persist()
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    if (!onSave) return
    onSave(ROWS_KEY, samples.value)
  }

  function saveConclusion(text: string): void {
    conclusion.value = text
    onSave?.(CONCLUSION_KEY, text)
  }

  // ─── Watch init ────────────────────────────────────────────────────────────

  watch(allResponses, () => initFromResponses(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    samples: computedSamples,
    summary,
    conclusion,
    isChanged,
    isLoading,
    sheetId,
    direction,
    autoSample,
    addSample,
    removeSample,
    updateCell,
    saveConclusion,
    initFromResponses,
  }
}

export default useK9Cutoff
