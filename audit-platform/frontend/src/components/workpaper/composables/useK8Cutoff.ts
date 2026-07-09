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
import { isCrossPeriod, autoSampleCutoff, type LedgerEntry, type CutoffSample } from './useK8CutoffEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 截止测试方向 */
export type CutoffDirection = 'V2S' | 'S2V'

/** 截止测试样本行（前端展示结构） */
export interface K8CutoffRow {
  rowKey: string
  /** 序号（自动编号） */
  index: number
  /** 凭证号 */
  voucherNo: string
  /** 记账日期 YYYY-MM-DD */
  bookDate: string
  /** 摘要 */
  summary: string
  /** 金额（借方或贷方） */
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

export interface K8CutoffSummary {
  /** 总样本数 */
  totalSamples: number
  /** 跨期项数量 */
  crossPeriodCount: number
  /** 正常项数量 */
  normalCount: number
  /** 需要调整的跨期项目列表 */
  crossPeriodItems: Array<{ voucherNo: string; amount: number }>
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

  function _normalizeSample(raw: any, idx: number): K8CutoffRow {
    const bookDate = raw.bookDate ?? ''
    const sourceDate = raw.sourceDate ?? ''
    const end = periodEnd?.value ?? '2025-12-31'
    const isCross = isCrossPeriod(sourceDate, bookDate, end)

    return {
      rowKey: raw.rowKey ?? `row-${idx}`,
      index: idx + 1,
      voucherNo: raw.voucherNo ?? '',
      bookDate,
      summary: raw.summary ?? '',
      amount: parseNum(raw.amount),
      sourceDate,
      accountCode: raw.accountCode ?? ACCOUNT_CODE_6601,
      accountName: raw.accountName ?? '',
      isCross,
      isTimely: raw.isTimely ?? !isCross,
      conclusion: raw.conclusion ?? (isCross ? '跨期' : '正常'),
      remark: raw.remark ?? '',
    }
  }

  // ─── Computed: 带公式列的完整行 ───────────────────────────────────────────

  const computedSamples: ComputedRef<K8CutoffRow[]> = computed(() => {
    const end = periodEnd?.value ?? '2025-12-31'
    return samples.value.map((row, idx) => {
      const isCross = isCrossPeriod(row.sourceDate, row.bookDate, end)
      return {
        ...row,
        index: idx + 1,
        isCross,
        isTimely: direction === 'S2V' ? !isCross : row.isTimely,
        conclusion: row.conclusion || (isCross ? '跨期' : '正常'),
      }
    })
  })

  // ─── Computed: 汇总统计 ────────────────────────────────────────────────────

  const summary: ComputedRef<K8CutoffSummary> = computed(() => {
    const all = computedSamples.value
    const crossItems = all.filter(r => r.isCross)
    return {
      totalSamples: all.length,
      crossPeriodCount: crossItems.length,
      normalCount: all.length - crossItems.length,
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
      // 调用序时账API获取期末±5天凭证
      const { data } = await http.get(`/api/projects/${projectId.value}/ledger/cutoff-samples`, {
        params: {
          period_end: end,
          days: DEFAULT_THRESHOLD_DAYS,
          account_code: ACCOUNT_CODE_6601,
        },
      })
      const ledgerEntries: LedgerEntry[] = data?.data ?? data ?? []
      const cutoffSamples = autoSampleCutoff(ledgerEntries, end, DEFAULT_THRESHOLD_DAYS)

      samples.value = cutoffSamples.map((s, idx) => ({
        rowKey: `row-${idx}-${Date.now()}`,
        index: idx + 1,
        voucherNo: s.voucherNo,
        bookDate: s.bookDate,
        summary: s.summary ?? '',
        amount: parseNum(s.debitAmount ?? s.creditAmount),
        sourceDate: s.sourceDate ?? '',
        accountCode: s.accountCode,
        accountName: s.accountName ?? '',
        isCross: s.isCrossPeriod,
        isTimely: !s.isCrossPeriod,
        conclusion: s.isCrossPeriod ? '跨期' : '正常',
        remark: '',
      }))

      isChanged.value = true
      _persist()
      ElMessage.success(`已从序时账自动提取 ${samples.value.length} 条截止样本`)
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
      isCross: false,
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
      if (!row.conclusion) row.conclusion = row.isCross ? '跨期' : '正常'
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

export default useK8Cutoff
