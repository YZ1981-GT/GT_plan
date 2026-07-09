/**
 * useI6Cutoff — 截止性测试双向 composable（I6-5/I6-6）
 *
 * I6-5: 截止性测试（账→单据）forward — 从账簿出发→核对原始单据（期末±5天）
 * I6-6: 截止性测试（单据→账）backward — 从单据出发→核对账簿记录（期末±5天）
 *
 * 列结构（Req 5.4）：
 * 序号 | 金额 | 费用类型 | 记账日期 | 单据日期 | 记账期间 | 归属期间 | 是否跨期 | 结论
 *
 * 公式引擎接入：
 * - isCutoffCrossover(bookingDate, documentDate, thresholdDays=5) — 跨期判定
 *
 * 集成 useCutoffAutoSampling：
 * - autoSample() 调用截止自动提取API获取期末±5天的序时账样本
 *
 * 持久化 key：'I6-5-rows'（正向）/ 'I6-6-rows'（反向）/ 'I6-5-conclusion' / 'I6-6-conclusion'
 *
 * Spec: .kiro/specs/i6-research-development-expense/
 * Task: 3.5
 * Requirements: 5.1-5.4
 */
import { ref, computed, type Ref, type ComputedRef, watch } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { isCutoffCrossover } from './useI6FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 截止测试样本行 */
export interface I6CutoffSample {
  /** 序号（自动编号） */
  index: number
  /** 金额 */
  amount: number
  /** 费用类型（如：人员费用/材料费/折旧等） */
  expenseType: string
  /** 记账日期 YYYY-MM-DD */
  bookingDate: string
  /** 单据日期 YYYY-MM-DD */
  documentDate: string
  /** 记账期间（如 2025-12） */
  bookingPeriod: string
  /** 归属期间（如 2025-12） */
  belongPeriod: string
  /** 是否跨期（公式列：isCutoffCrossover自动计算） */
  isCrossover: boolean
  /** 结论（公式列：跨期/正常） */
  conclusion: string
  /** 凭证号 */
  voucherNo: string
  /** 摘要/描述 */
  description: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 持久化 key */
const FORWARD_ROWS_KEY = 'I6-5-rows'
const BACKWARD_ROWS_KEY = 'I6-6-rows'
const FORWARD_CONCLUSION_KEY = 'I6-5-conclusion'
const BACKWARD_CONCLUSION_KEY = 'I6-6-conclusion'

/** 默认截止阈值天数 */
const DEFAULT_THRESHOLD_DAYS = 5

/** 科目编码（研发费用） */
const ACCOUNT_CODE = '6602'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI6Cutoff(options: {
  direction: 'forward' | 'backward' // I6-5=forward, I6-6=backward
  allResponses: Ref<Map<string, any>>
  projectId: Ref<string>
  wpId: Ref<string>
  isReadonly?: Ref<boolean>
  onSave?: (itemId: string, value: any) => void
}): {
  samples: Ref<I6CutoffSample[]>
  addSample: (data?: Partial<I6CutoffSample>) => void
  removeSample: (index: number) => void
  updateSample: (index: number, field: string, value: any) => void
  autoSample: () => Promise<void>
  isAutoSampling: Ref<boolean>
  crossoverCount: ComputedRef<number>
  crossoverAmount: ComputedRef<number>
  conclusion: Ref<string>
  saveConclusion: () => void
} {
  const { direction, allResponses, projectId, wpId, isReadonly, onSave } = options

  const rowsKey = direction === 'forward' ? FORWARD_ROWS_KEY : BACKWARD_ROWS_KEY
  const conclusionKey = direction === 'forward' ? FORWARD_CONCLUSION_KEY : BACKWARD_CONCLUSION_KEY

  // ─── State ─────────────────────────────────────────────────────────────────

  const samples = ref<I6CutoffSample[]>([])
  const isAutoSampling = ref(false)
  const conclusion = ref('')

  // ─── Helpers ───────────────────────────────────────────────────────────────

  /** 安全解析日期 */
  function _parseDate(dateStr: string): Date | null {
    if (!dateStr) return null
    const d = new Date(dateStr + 'T00:00:00')
    return isNaN(d.getTime()) ? null : d
  }

  /** 从 allResponses 获取 JSON 数据 */
  function _getJson(key: string): any {
    const item = allResponses.value.get(key)
    if (!item) return null
    const raw = (item as any).remark ?? (item as any).conclusion ?? item
    if (raw == null) return null
    if (typeof raw === 'object') return raw
    try { return JSON.parse(raw as string) } catch { return null }
  }

  /** 从 allResponses 获取字符串数据 */
  function _getString(key: string): string {
    const item = allResponses.value.get(key)
    if (!item) return ''
    const raw = (item as any).conclusion ?? (item as any).remark ?? item
    return typeof raw === 'string' ? raw : ''
  }

  /** 从日期字符串提取期间（YYYY-MM格式） */
  function _extractPeriod(dateStr: string): string {
    if (!dateStr || dateStr.length < 7) return ''
    return dateStr.substring(0, 7)
  }

  /** 重算单行公式列（isCrossover / conclusion） */
  function _recalcFormulas(row: I6CutoffSample): void {
    const bd = _parseDate(row.bookingDate)
    const dd = _parseDate(row.documentDate)

    if (bd && dd) {
      row.isCrossover = isCutoffCrossover(bd, dd, DEFAULT_THRESHOLD_DAYS)
      row.conclusion = row.isCrossover ? '跨期' : '正常'
    } else {
      row.isCrossover = false
      row.conclusion = '正常'
    }
  }

  /** 创建空行 */
  function _createSample(data?: Partial<I6CutoffSample>): I6CutoffSample {
    const row: I6CutoffSample = {
      index: samples.value.length + 1,
      amount: data?.amount ?? 0,
      expenseType: data?.expenseType ?? '',
      bookingDate: data?.bookingDate ?? '',
      documentDate: data?.documentDate ?? '',
      bookingPeriod: data?.bookingPeriod ?? '',
      belongPeriod: data?.belongPeriod ?? '',
      isCrossover: false,
      conclusion: '正常',
      voucherNo: data?.voucherNo ?? '',
      description: data?.description ?? '',
    }
    _recalcFormulas(row)
    return row
  }

  /** 重新编号所有行 */
  function _reindex(): void {
    samples.value.forEach((row, idx) => {
      row.index = idx + 1
    })
  }

  /** 反序列化行数据（从持久化恢复） */
  function _deserializeRows(data: any[]): I6CutoffSample[] {
    return data.map((raw: any, idx: number) => {
      const row: I6CutoffSample = {
        index: idx + 1,
        amount: Number(raw.amount) || 0,
        expenseType: String(raw.expenseType ?? ''),
        bookingDate: String(raw.bookingDate ?? ''),
        documentDate: String(raw.documentDate ?? ''),
        bookingPeriod: String(raw.bookingPeriod ?? ''),
        belongPeriod: String(raw.belongPeriod ?? ''),
        isCrossover: false,
        conclusion: '正常',
        voucherNo: String(raw.voucherNo ?? ''),
        description: String(raw.description ?? ''),
      }
      _recalcFormulas(row)
      return row
    })
  }

  // ─── Init / Load ───────────────────────────────────────────────────────────

  function _loadFromResponses(): void {
    const rowsData = _getJson(rowsKey)
    if (Array.isArray(rowsData) && rowsData.length > 0) {
      samples.value = _deserializeRows(rowsData)
    } else {
      samples.value = []
    }

    conclusion.value = _getString(conclusionKey)
  }

  // 监听 allResponses 变化自动加载
  watch(allResponses, () => _loadFromResponses(), { immediate: true })

  // ─── Computed: 跨期统计 ────────────────────────────────────────────────────

  /** 跨期笔数 */
  const crossoverCount: ComputedRef<number> = computed(() => {
    return samples.value.filter(row => row.isCrossover).length
  })

  /** 跨期金额合计 */
  const crossoverAmount: ComputedRef<number> = computed(() => {
    return samples.value
      .filter(row => row.isCrossover)
      .reduce((sum, row) => sum + row.amount, 0)
  })

  // ─── Actions: addSample ────────────────────────────────────────────────────

  /** 新增截止测试行 */
  function addSample(data?: Partial<I6CutoffSample>): void {
    if (isReadonly?.value) return
    samples.value.push(_createSample(data))
    _persist()
  }

  // ─── Actions: removeSample ─────────────────────────────────────────────────

  /** 删除指定行 */
  function removeSample(index: number): void {
    if (isReadonly?.value) return
    if (index < 0 || index >= samples.value.length) return
    samples.value.splice(index, 1)
    _reindex()
    _persist()
  }

  // ─── Actions: updateSample ─────────────────────────────────────────────────

  /**
   * 更新指定行字段值。
   * 可编辑字段：amount / expenseType / bookingDate / documentDate / bookingPeriod / belongPeriod / voucherNo / description
   * 公式列（isCrossover / conclusion）自动重算。
   */
  function updateSample(index: number, field: string, value: any): void {
    if (isReadonly?.value) return
    if (index < 0 || index >= samples.value.length) return
    const row = samples.value[index]

    switch (field) {
      case 'amount':
        row.amount = Number(value) || 0
        break
      case 'expenseType':
        row.expenseType = String(value ?? '')
        break
      case 'bookingDate':
        row.bookingDate = String(value ?? '')
        _recalcFormulas(row)
        break
      case 'documentDate':
        row.documentDate = String(value ?? '')
        _recalcFormulas(row)
        break
      case 'bookingPeriod':
        row.bookingPeriod = String(value ?? '')
        break
      case 'belongPeriod':
        row.belongPeriod = String(value ?? '')
        break
      case 'voucherNo':
        row.voucherNo = String(value ?? '')
        break
      case 'description':
        row.description = String(value ?? '')
        break
      default:
        // 公式列（isCrossover/conclusion/index）不可直接编辑
        return
    }

    _persist()
  }

  // ─── Actions: autoSample ───────────────────────────────────────────────────

  /**
   * 自动提取期末±5天序时账样本（useCutoffAutoSampling集成）
   * API: POST /api/projects/{projectId}/ledger/cutoff-samples
   * Body: { direction, threshold_days, account_code }
   *
   * Req 5.3: 支持 useCutoffAutoSampling 自动提取序时账样本
   */
  async function autoSample(): Promise<void> {
    if (isReadonly?.value) return
    if (!projectId.value) {
      ElMessage.warning('项目ID无效，无法自动提取样本')
      return
    }

    isAutoSampling.value = true
    try {
      const res = await http.post(
        `/api/projects/${projectId.value}/ledger/cutoff-samples`,
        {
          direction,
          threshold_days: DEFAULT_THRESHOLD_DAYS,
          account_code: ACCOUNT_CODE,
        },
      )

      const data = res.data as any
      const items: any[] = Array.isArray(data) ? data : (data?.items ?? data?.data ?? [])

      if (items.length === 0) {
        ElMessage.info('未找到期末±5天内的序时账样本')
        return
      }

      // 映射API返回数据为 I6CutoffSample
      const newSamples: I6CutoffSample[] = items.map((item: any, idx: number) => {
        const bookingDate = item.voucher_date ?? item.voucherDate ?? item.booking_date ?? item.record_date ?? ''
        const documentDate = item.document_date ?? item.documentDate ?? ''
        const row: I6CutoffSample = {
          index: samples.value.length + idx + 1,
          amount: Number(item.amount ?? item.debit_amount ?? 0),
          expenseType: item.expense_type ?? item.expenseType ?? item.account_name ?? '',
          bookingDate,
          documentDate: documentDate || bookingDate,
          bookingPeriod: item.booking_period ?? item.recordPeriod ?? _extractPeriod(bookingDate),
          belongPeriod: item.belong_period ?? item.belongPeriod ?? '',
          isCrossover: false,
          conclusion: '正常',
          voucherNo: item.voucher_no ?? item.voucherNo ?? '',
          description: item.summary ?? item.description ?? '',
        }
        _recalcFormulas(row)
        return row
      })

      // 追加到现有样本
      samples.value = [...samples.value, ...newSamples]
      _reindex()
      _persist()

      const dirLabel = direction === 'forward' ? '正向（账→单据）' : '反向（单据→账）'
      ElMessage.success(`${dirLabel}：已导入${newSamples.length}笔样本`)
    } catch (err: any) {
      ElMessage.error(err?.message || '自动提取样本失败，请降级手工输入')
    } finally {
      isAutoSampling.value = false
    }
  }

  // ─── Actions: saveConclusion ───────────────────────────────────────────────

  /** 保存结论 */
  function saveConclusion(): void {
    if (isReadonly?.value) return
    if (onSave) {
      onSave(conclusionKey, conclusion.value)
    }
  }

  // ─── Persistence ───────────────────────────────────────────────────────────

  /**
   * 持久化截止测试行数据。
   * 铁律：>100行的动态数据必须JSON打包存1条
   */
  function _persist(): void {
    if (!onSave) return

    // 序列化仅保存输入字段（公式列运行时重算）
    const persistData = samples.value.map(row => ({
      amount: row.amount,
      expenseType: row.expenseType,
      bookingDate: row.bookingDate,
      documentDate: row.documentDate,
      bookingPeriod: row.bookingPeriod,
      belongPeriod: row.belongPeriod,
      voucherNo: row.voucherNo,
      description: row.description,
    }))

    onSave(rowsKey, persistData)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    samples,
    addSample,
    removeSample,
    updateSample,
    autoSample,
    isAutoSampling,
    crossoverCount,
    crossoverAmount,
    conclusion,
    saveConclusion,
  }
}

export default useI6Cutoff
