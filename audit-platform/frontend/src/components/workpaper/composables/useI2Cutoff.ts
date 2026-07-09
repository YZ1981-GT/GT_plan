/**
 * useI2Cutoff — 截止性测试双向 composable
 *
 * I2-13: 截止性测试（账到单据）— 从账簿出发→核对原始单据（期末±5天）
 * I2-14: 截止性测试（单据到账）— 从单据出发→核对账簿记录（期末±5天）
 *
 * 列结构（Req 8.4）：
 * 日期 | 金额 | 记账期间 | 单据日期 | 归属期间 | 是否跨期 | 结论
 *
 * 公式引擎接入：
 * - dateDiff = calcDateDiffDays(recordDate, documentDate)
 * - isCrossPeriod = isCrossPeriod(recordDate, documentDate, thresholdDays)
 *
 * 集成 useCutoffAutoSampling（Req 8.3）：
 * - loadFromAutoSampling(direction) 调用截止自动提取API获取期末±5天样本
 *
 * 持久化 key：'I2-13-rows'（正向）/ 'I2-14-rows'（反向）
 *
 * Spec: .kiro/specs/i2-development-expenditure/
 * Task: 3.6
 * Requirements: 8.1-8.4
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import {
  calcDateDiffDays,
  isCrossPeriod as isCrossPeriodFn,
} from './useI2FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 截止测试行数据 */
export interface CutoffRow {
  /** 记账日期 YYYY-MM-DD */
  recordDate: string
  /** 金额 */
  amount: number
  /** 记账期间（如 2025-12） */
  recordPeriod: string
  /** 单据日期 YYYY-MM-DD */
  documentDate: string
  /** 归属期间（如 2025-12） */
  belongPeriod: string
  /** 日期差（天）= |recordDate - documentDate| */
  dateDiff: number
  /** 是否跨期 = dateDiff > threshold */
  isCrossPeriod: boolean
  /** 结论：正常/跨期 */
  conclusion: string
  /** 凭证号 */
  voucherNo: string
  /** 摘要 */
  description: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 持久化 key（JSON打包） */
const FORWARD_ROWS_KEY = 'I2-13-rows'
const BACKWARD_ROWS_KEY = 'I2-14-rows'

/** 默认截止阈值天数 */
const DEFAULT_THRESHOLD_DAYS = 5

/** 科目编码（开发支出） */
const ACCOUNT_CODE = '1717'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI2Cutoff(params: {
  allResponses: Ref<Map<string, any>>
  saveResponses: (sheetCode: string, data: Record<string, any>) => Promise<void>
  projectId: Ref<string>
  cutoffThresholdDays?: number
}): {
  forwardRows: Ref<CutoffRow[]>
  backwardRows: Ref<CutoffRow[]>
  forwardCrossPeriodCount: ComputedRef<number>
  backwardCrossPeriodCount: ComputedRef<number>
  addForwardRow: (data?: Partial<CutoffRow>) => void
  addBackwardRow: (data?: Partial<CutoffRow>) => void
  removeForwardRow: (index: number) => void
  removeBackwardRow: (index: number) => void
  updateForwardRow: (index: number, field: string, value: any) => void
  updateBackwardRow: (index: number, field: string, value: any) => void
  loadFromAutoSampling: (direction: 'forward' | 'backward') => Promise<void>
  save: () => Promise<void>
} {
  const { allResponses, saveResponses, projectId } = params
  const thresholdDays = params.cutoffThresholdDays ?? DEFAULT_THRESHOLD_DAYS

  // ─── State ─────────────────────────────────────────────────────────────────

  const forwardRows = ref<CutoffRow[]>([])
  const backwardRows = ref<CutoffRow[]>([])

  // ─── Helpers ───────────────────────────────────────────────────────────────

  /** 安全解析 Date */
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

  /** 创建空行 */
  function _createEmptyRow(data?: Partial<CutoffRow>): CutoffRow {
    const row: CutoffRow = {
      recordDate: data?.recordDate ?? '',
      amount: data?.amount ?? 0,
      recordPeriod: data?.recordPeriod ?? '',
      documentDate: data?.documentDate ?? '',
      belongPeriod: data?.belongPeriod ?? '',
      dateDiff: 0,
      isCrossPeriod: false,
      conclusion: '正常',
      voucherNo: data?.voucherNo ?? '',
      description: data?.description ?? '',
    }
    _recalcFormulas(row)
    return row
  }

  /** 重算单行公式列（dateDiff / isCrossPeriod / conclusion） */
  function _recalcFormulas(row: CutoffRow): void {
    const rd = _parseDate(row.recordDate)
    const dd = _parseDate(row.documentDate)

    if (rd && dd) {
      row.dateDiff = calcDateDiffDays(rd, dd)
      row.isCrossPeriod = isCrossPeriodFn(rd, dd, thresholdDays)
      row.conclusion = row.isCrossPeriod ? '跨期' : '正常'
    } else {
      row.dateDiff = 0
      row.isCrossPeriod = false
      row.conclusion = '正常'
    }
  }

  /** 反序列化行数据（从持久化恢复） */
  function _deserializeRows(data: any[]): CutoffRow[] {
    return data.map((raw: any) => {
      const row: CutoffRow = {
        recordDate: String(raw.recordDate ?? ''),
        amount: Number(raw.amount) || 0,
        recordPeriod: String(raw.recordPeriod ?? ''),
        documentDate: String(raw.documentDate ?? ''),
        belongPeriod: String(raw.belongPeriod ?? ''),
        dateDiff: 0,
        isCrossPeriod: false,
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
    const forwardData = _getJson(FORWARD_ROWS_KEY)
    if (Array.isArray(forwardData) && forwardData.length > 0) {
      forwardRows.value = _deserializeRows(forwardData)
    } else {
      forwardRows.value = []
    }

    const backwardData = _getJson(BACKWARD_ROWS_KEY)
    if (Array.isArray(backwardData) && backwardData.length > 0) {
      backwardRows.value = _deserializeRows(backwardData)
    } else {
      backwardRows.value = []
    }
  }

  // 监听 allResponses 变化自动加载
  watch(allResponses, () => _loadFromResponses(), { immediate: true })

  // ─── Computed: 跨期统计 ────────────────────────────────────────────────────

  /** I2-13 正向截止跨期笔数 */
  const forwardCrossPeriodCount: ComputedRef<number> = computed(() => {
    return forwardRows.value.filter(row => row.isCrossPeriod).length
  })

  /** I2-14 反向截止跨期笔数 */
  const backwardCrossPeriodCount: ComputedRef<number> = computed(() => {
    return backwardRows.value.filter(row => row.isCrossPeriod).length
  })

  // ─── Actions: addRow ───────────────────────────────────────────────────────

  /** 新增 I2-13 正向截止行 */
  function addForwardRow(data?: Partial<CutoffRow>): void {
    forwardRows.value.push(_createEmptyRow(data))
  }

  /** 新增 I2-14 反向截止行 */
  function addBackwardRow(data?: Partial<CutoffRow>): void {
    backwardRows.value.push(_createEmptyRow(data))
  }

  // ─── Actions: removeRow ────────────────────────────────────────────────────

  /** 删除 I2-13 正向截止指定行 */
  function removeForwardRow(index: number): void {
    if (index < 0 || index >= forwardRows.value.length) return
    forwardRows.value.splice(index, 1)
  }

  /** 删除 I2-14 反向截止指定行 */
  function removeBackwardRow(index: number): void {
    if (index < 0 || index >= backwardRows.value.length) return
    backwardRows.value.splice(index, 1)
  }

  // ─── Actions: updateRow ────────────────────────────────────────────────────

  /**
   * 更新 I2-13 正向截止指定行字段值。
   *
   * 可编辑字段：recordDate / amount / recordPeriod / documentDate / belongPeriod / voucherNo / description
   * 公式列（dateDiff / isCrossPeriod / conclusion）自动重算。
   */
  function updateForwardRow(index: number, field: string, value: any): void {
    if (index < 0 || index >= forwardRows.value.length) return
    _updateRow(forwardRows.value[index], field, value)
  }

  /**
   * 更新 I2-14 反向截止指定行字段值。
   */
  function updateBackwardRow(index: number, field: string, value: any): void {
    if (index < 0 || index >= backwardRows.value.length) return
    _updateRow(backwardRows.value[index], field, value)
  }

  function _updateRow(row: CutoffRow, field: string, value: any): void {
    switch (field) {
      case 'recordDate':
        row.recordDate = String(value ?? '')
        break
      case 'amount':
        row.amount = Number(value) || 0
        return // 金额变更不触发公式重算（公式仅依赖日期）
      case 'recordPeriod':
        row.recordPeriod = String(value ?? '')
        return
      case 'documentDate':
        row.documentDate = String(value ?? '')
        break
      case 'belongPeriod':
        row.belongPeriod = String(value ?? '')
        return
      case 'voucherNo':
        row.voucherNo = String(value ?? '')
        return
      case 'description':
        row.description = String(value ?? '')
        return
      default:
        // 公式列不可直接编辑
        return
    }

    // recordDate 或 documentDate 变更时重算公式
    _recalcFormulas(row)
  }

  // ─── Actions: loadFromAutoSampling ─────────────────────────────────────────

  /**
   * 从截止自动提取API加载期末±5天的序时账样本。
   * API: POST /api/projects/{projectId}/ledger/cutoff-samples
   * Body: { direction, threshold_days, account_code }
   *
   * Req 8.3: 支持 useCutoffAutoSampling 自动提取序时账样本
   */
  async function loadFromAutoSampling(direction: 'forward' | 'backward'): Promise<void> {
    if (!projectId.value) {
      ElMessage.warning('项目ID无效，无法自动提取样本')
      return
    }

    try {
      const res = await http.post(
        `/api/projects/${projectId.value}/ledger/cutoff-samples`,
        {
          direction,
          threshold_days: thresholdDays,
          account_code: ACCOUNT_CODE,
        },
      )

      const data = res.data as any
      const items: any[] = Array.isArray(data) ? data : (data?.items ?? data?.data ?? [])

      if (items.length === 0) {
        ElMessage.info('未找到期末±5天内的序时账样本')
        return
      }

      // 映射API返回数据为 CutoffRow
      const newRows: CutoffRow[] = items.map((item: any) => {
        const row = _createEmptyRow({
          recordDate: item.voucher_date ?? item.voucherDate ?? item.record_date ?? '',
          amount: Number(item.amount ?? item.debit_amount ?? 0),
          recordPeriod: item.record_period ?? item.recordPeriod ?? _extractPeriod(item.voucher_date ?? item.voucherDate ?? ''),
          documentDate: item.document_date ?? item.documentDate ?? item.voucher_date ?? '',
          belongPeriod: item.belong_period ?? item.belongPeriod ?? '',
          voucherNo: item.voucher_no ?? item.voucherNo ?? '',
          description: item.summary ?? item.description ?? '',
        })
        return row
      })

      if (direction === 'forward') {
        forwardRows.value = [...forwardRows.value, ...newRows]
        ElMessage.success(`正向截止：已导入${newRows.length}笔样本`)
      } else {
        backwardRows.value = [...backwardRows.value, ...newRows]
        ElMessage.success(`反向截止：已导入${newRows.length}笔样本`)
      }
    } catch (err: any) {
      ElMessage.error(err?.message || '自动提取样本失败，请降级手工输入')
    }
  }

  /** 从日期字符串提取期间（YYYY-MM格式） */
  function _extractPeriod(dateStr: string): string {
    if (!dateStr || dateStr.length < 7) return ''
    return dateStr.substring(0, 7)
  }

  // ─── Actions: save ─────────────────────────────────────────────────────────

  /**
   * 持久化截止测试行数据。
   * 正向 I2-13 → key 'I2-13-rows'（sheetCode='13'）
   * 反向 I2-14 → key 'I2-14-rows'（sheetCode='14'）
   * 铁律：>100行的动态数据必须JSON打包存1条
   */
  async function save(): Promise<void> {
    // 序列化仅保存输入字段（公式列运行时重算）
    const forwardPersist = forwardRows.value.map(row => ({
      recordDate: row.recordDate,
      amount: row.amount,
      recordPeriod: row.recordPeriod,
      documentDate: row.documentDate,
      belongPeriod: row.belongPeriod,
      voucherNo: row.voucherNo,
      description: row.description,
    }))

    const backwardPersist = backwardRows.value.map(row => ({
      recordDate: row.recordDate,
      amount: row.amount,
      recordPeriod: row.recordPeriod,
      documentDate: row.documentDate,
      belongPeriod: row.belongPeriod,
      voucherNo: row.voucherNo,
      description: row.description,
    }))

    // 保存正向（sheetCode='13'）和反向（sheetCode='14'）
    await saveResponses('13', { [FORWARD_ROWS_KEY]: forwardPersist })
    await saveResponses('14', { [BACKWARD_ROWS_KEY]: backwardPersist })
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    forwardRows,
    backwardRows,
    forwardCrossPeriodCount,
    backwardCrossPeriodCount,
    addForwardRow,
    addBackwardRow,
    removeForwardRow,
    removeBackwardRow,
    updateForwardRow,
    updateBackwardRow,
    loadFromAutoSampling,
    save,
  }
}

export default useI2Cutoff
