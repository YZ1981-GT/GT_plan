/**
 * useK8Cutoff — K8-6/K8-7 截止测试逻辑（各44行）
 *
 * Spec: .kiro/specs/k8-selling-expenses/
 * Task: 3.4
 * Requirements: 5.1-5.6, 9.7
 *
 * 职责：
 * - 管理截止测试样本（K8-6记账→原始 / K8-7原始→记账，各44行）
 * - 使用 isCrossPeriod / autoSampleCutoff from CutoffEngine
 * - 两个方向：V2S (voucher-to-source) 和 S2V (source-to-voucher)
 * - 自动从序时账抽样期末±5天凭证 (useCutoffAutoSampling)
 * - 跨期项红色标记并提示调整
 *
 * Item IDs: "K8-6-row-{idx}-{field}" / "K8-7-row-{idx}-{field}"
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { parseNum } from './useK8FormulaEngine'
import { isCrossPeriod } from './useK8CutoffEngine'
import { deriveConclusion as canonicalDeriveConclusion } from './cutoffCanonical'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 截止测试方向 */
export type CutoffDirection = 'V2S' | 'S2V'

/** 截止测试样本行（前端展示结构） */
export interface K8CutoffRow {
  rowKey: string
  /** 序号（自动编号） */
  index: number
  /** 凭证号（记账凭证编号） */
  voucherNo: string
  /** 记账日期 YYYY-MM-DD */
  bookDate: string
  /** 摘要 */
  summary: string
  /** 金额（记账凭证金额） */
  amount: number
  /** 原始凭证日期 YYYY-MM-DD（支出凭单日期） */
  sourceDate: string
  /** 科目编码 */
  accountCode: string
  /** 科目名称 */
  accountName: string
  // ── 对齐源模板 K8-7 双组列（支出凭单 / 记账凭证）──────────────────
  /** 支出凭单编号（源 B 列） */
  sourceVoucherNo: string
  /** 支出凭单金额（源 D 列） */
  sourceAmount: number
  /** 业务内容（记账凭证 G 列） */
  businessContent: string
  /** 对方科目（记账凭证 H 列） */
  offsetAccount: string
  /** 是否跨期（公式列：自动计算） */
  isCross: boolean
  /** 跨期金额（公式列：跨期时取金额） */
  crossAmount: number
  /** 支出凭单金额 vs 记账凭证金额 是否不符（公式列） */
  amountMismatch: boolean
  /** 是否及时入账（S2V方向专用） */
  isTimely: boolean
  /** 审核结论 */
  conclusion: string
  /** 备注 */
  remark: string
}

export interface K8CutoffSummary {
  /** 总样本数 */
  totalSamples: number
  /** 跨期项数量 */
  crossPeriodCount: number
  /** 正常项数量（双侧证据齐全且同期；不含证据不完整） */
  normalCount: number
  /** 证据不完整项数量（缺记账侧或原始单据侧独立证据，不得判正常/完成） */
  incompleteCount: number
  /** 需要调整的跨期项目列表 */
  crossPeriodItems: Array<{ voucherNo: string; amount: number }>
  /** 跨期金额合计 */
  crossAmountTotal: number
  /** 支出凭单/记账凭证金额不符笔数 */
  mismatchCount: number
}

export interface UseK8CutoffParams {
  /** 方向：V2S=记账→原始(K8-6)，S2V=原始→记账(K8-7) */
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

const ACCOUNT_CODE_6601 = '6601'
/** 默认截止阈值天数 */
const DEFAULT_THRESHOLD_DAYS = 5

function getKeys(direction: CutoffDirection) {
  const sheetId = direction === 'V2S' ? 'K8-6' : 'K8-7'
  return {
    sheetId,
    ROWS_KEY: `${sheetId}-rows`,
    CONCLUSION_KEY: `${sheetId}-conclusion`,
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useK8Cutoff(params: UseK8CutoffParams) {
  const { direction, allResponses, projectId, wpId, periodEnd, isReadonly, onSave } = params
  const { sheetId, ROWS_KEY, CONCLUSION_KEY } = getKeys(direction)

  // ─── State ─────────────────────────────────────────────────────────────────

  const samples = ref<K8CutoffRow[]>([])
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
   * 才可下"正常/跨期"结论；任一侧缺失（如自动提取仅得记账侧、原始单据未取得）→ "证据不完整"，
   * 不得假绿为"正常"。审计师手工录入的 conclusion 优先，本函数仅作缺省回退。
   */
  function _defaultConclusion(bookDate: string, sourceDate: string, _isCross: boolean): string {
    // 委托 cutoffCanonical.deriveConclusion（natural-month 单一真源）：
    // 缺任一侧日期→证据不完整；双侧齐全按自然月跨期→跨期/正常。行为等价（非法日期边界更严格：判证据不完整而非假绿正常）。
    const end = periodEnd?.value ?? '2025-12-31'
    return canonicalDeriveConclusion({ bookDate, documentDate: sourceDate }, end, 'natural-month')
  }

  function _normalizeSample(raw: any, idx: number): K8CutoffRow {
    const bookDate = raw.bookDate ?? ''
    const sourceDate = raw.sourceDate ?? ''
    const end = periodEnd?.value ?? '2025-12-31'
    const isCross = isCrossPeriod(sourceDate, bookDate, end)

    const amount = parseNum(raw.amount)
    const sourceAmount = parseNum(raw.sourceAmount)
    return {
      rowKey: raw.rowKey ?? `row-${idx}`,
      index: idx + 1,
      voucherNo: raw.voucherNo ?? '',
      bookDate,
      summary: raw.summary ?? '',
      amount,
      sourceDate,
      accountCode: raw.accountCode ?? ACCOUNT_CODE_6601,
      accountName: raw.accountName ?? '',
      sourceVoucherNo: raw.sourceVoucherNo ?? '',
      sourceAmount,
      businessContent: raw.businessContent ?? '',
      offsetAccount: raw.offsetAccount ?? '',
      isCross,
      crossAmount: isCross ? (amount || sourceAmount) : 0,
      amountMismatch: amount > 0 && sourceAmount > 0 && Math.abs(amount - sourceAmount) > 0.01,
      isTimely: raw.isTimely ?? !isCross,
      conclusion: raw.conclusion ?? _defaultConclusion(bookDate, sourceDate, isCross),
      remark: raw.remark ?? '',
    }
  }

  // ─── Computed: 带公式列的完整行 ───────────────────────────────────────────

  const computedSamples: ComputedRef<K8CutoffRow[]> = computed(() => {
    const end = periodEnd?.value ?? '2025-12-31'
    return samples.value.map((row, idx) => {
      const isCross = isCrossPeriod(row.sourceDate, row.bookDate, end)
      const amount = parseNum(row.amount)
      const sourceAmount = parseNum(row.sourceAmount)
      return {
        ...row,
        index: idx + 1,
        isCross,
        crossAmount: isCross ? (amount || sourceAmount) : 0,
        amountMismatch: amount > 0 && sourceAmount > 0 && Math.abs(amount - sourceAmount) > 0.01,
        isTimely: direction === 'S2V' ? !isCross : row.isTimely,
        conclusion: row.conclusion || _defaultConclusion(row.bookDate, row.sourceDate, isCross),
      }
    })
  })

  // ─── Computed: 汇总统计 ────────────────────────────────────────────────────

  const summary: ComputedRef<K8CutoffSummary> = computed(() => {
    const all = computedSamples.value
    const crossItems = all.filter(r => r.isCross)
    // 证据不完整（缺任一侧独立证据）单列，不计入 normalCount，与统一状态机+完成门禁一致
    const incompleteItems = all.filter(r => r.conclusion === '证据不完整')
    return {
      totalSamples: all.length,
      crossPeriodCount: crossItems.length,
      incompleteCount: incompleteItems.length,
      normalCount: all.length - crossItems.length - incompleteItems.length,
      crossPeriodItems: crossItems.map(r => ({ voucherNo: r.voucherNo, amount: r.amount })),
      crossAmountTotal: crossItems.reduce((s, r) => s + (r.crossAmount || 0), 0),
      mismatchCount: all.filter(r => r.amountMismatch).length,
    }
  })

  // ─── 资产负债表日前/后分段（对齐源模板"截止日期"分隔线）────────────────────
  function _sideOf(row: K8CutoffRow): 'pre' | 'post' {
    const end = periodEnd?.value ?? '2025-12-31'
    // S2V：以支出凭单日期判断所属期；V2S：以记账日期
    const d = (direction === 'S2V' ? row.sourceDate : row.bookDate) || row.bookDate || row.sourceDate
    if (!d) return 'pre'
    return d <= end ? 'pre' : 'post' // YYYY-MM-DD 字符串可直接比较
  }
  const preCutoffSamples = computed(() => computedSamples.value.filter(r => _sideOf(r) === 'pre'))
  const postCutoffSamples = computed(() => computedSamples.value.filter(r => _sideOf(r) === 'post'))

  // ─── 自动抽样（从序时账±5天） ─────────────────────────────────────────────

  async function autoSample(): Promise<void> {
    if (isReadonly?.value) return
    isLoading.value = true
    try {
      const { default: http } = await import('@/utils/http')
      const end = periodEnd?.value ?? '2025-12-31'
      const yr = Number(String(end).slice(0, 4)) || new Date().getFullYear()
      // 真实端点：POST /sampling/cutoff-test（提取期末±N天序时账交易）。
      // 旧代码调 GET /ledger/cutoff-samples 为不存在端点，导致「自动提取」恒 404 失败。
      const res = await http.post(`/api/projects/${projectId.value}/sampling/cutoff-test`, {
        account_codes: [ACCOUNT_CODE_6601],
        year: yr,
        days_before: DEFAULT_THRESHOLD_DAYS,
        days_after: DEFAULT_THRESHOLD_DAYS,
        amount_threshold: 0, // 阈值0=窗口内全部非零凭证（销售费用逐笔）
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
        // 端点仅返回记账凭证（无支出凭单日期）→ 由审计师追查补录 sourceDate 后判定跨期
        sourceDate: '',
        accountCode: e.account_code ?? ACCOUNT_CODE_6601,
        accountName: e.account_name ?? '',
        sourceVoucherNo: '',
        sourceAmount: 0,
        businessContent: e.summary ?? '',
        offsetAccount: '',
        isCross: false,
        crossAmount: 0,
        amountMismatch: false,
        isTimely: true,
        conclusion: '',
        remark: '',
      }))

      isChanged.value = true
      _persist()
      if (samples.value.length > 0) {
        ElMessage.success(`已从序时账提取 ${samples.value.length} 条截止样本（期末±${DEFAULT_THRESHOLD_DAYS}天），请补充支出凭单日期后判定跨期`)
      } else {
        ElMessage.info(`期末±${DEFAULT_THRESHOLD_DAYS}天窗口内未提取到销售费用凭证`)
      }
    } catch {
      ElMessage.warning('截止样本自动提取失败，请手动录入')
    } finally {
      isLoading.value = false
    }
  }

  // ─── 手动新增样本 ─────────────────────────────────────────────────────────

  function addSample(data?: Partial<K8CutoffRow>): void {
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
      accountCode: data?.accountCode ?? ACCOUNT_CODE_6601,
      accountName: data?.accountName ?? '',
      sourceVoucherNo: data?.sourceVoucherNo ?? '',
      sourceAmount: parseNum(data?.sourceAmount),
      businessContent: data?.businessContent ?? '',
      offsetAccount: data?.offsetAccount ?? '',
      isCross: false,
      crossAmount: 0,
      amountMismatch: false,
      isTimely: true,
      conclusion: '',
      remark: '',
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
    preCutoffSamples,
    postCutoffSamples,
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

export default useK8Cutoff
