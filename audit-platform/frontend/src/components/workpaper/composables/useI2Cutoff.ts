/**
 * useI2Cutoff — 开发支出截止性测试双向 composable
 *
 * I2-13: 账→单据（发生/存在）：从账簿分录追查支出凭单，识别提前入账/跨期多记
 * I2-14: 单据→账（完整性）：从支出凭单追查账簿，识别推迟入账/跨期漏记
 *
 * 对齐致同 Excel 底稿结构：
 * 一、审计目标 → 二、样本选取标准与规模 → 三、测试（截止日前后分段）→ 四、说明 → 五、结论
 *
 * 跨期判定：单据日与记账日分处截止日两侧（isCutoffPeriodCrossing），非日期差>N天。
 *
 * Spec: .kiro/specs/i2-development-expenditure/ Req 8.1-8.4
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import {
  calcDateDiffDays,
  isCrossPeriod as isLagAnomalyFn,
  isCutoffPeriodCrossing,
  calcCrossPeriodAmount,
} from './useI2FormulaEngine'
import { resolveDefaultCutoffDate, appendI23DraftAje, writeSheetCompletionMarker } from './i2EnhancementHelpers'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 截止测试行（对齐 Excel：记账凭证 + 支出凭单 + 跨期分析） */
export interface CutoffRow {
  /** 侧：截止日前 / 截止日后（按追查起点日期相对截止日） */
  side: 'before' | 'after' | 'unsorted'
  /** 记账日期 YYYY-MM-DD */
  recordDate: string
  /** 凭证号 */
  voucherNo: string
  /** 记账金额 */
  amount: number
  /** 摘要 */
  description: string
  /** 支出凭单编号 */
  documentNo: string
  /** 单据日期 YYYY-MM-DD */
  documentDate: string
  /** 单据金额（缺省与记账金额一致） */
  documentAmount: number
  /** 记账期间 YYYY-MM（展示/手工覆盖） */
  recordPeriod: string
  /** 归属期间 YYYY-MM（通常取单据日） */
  belongPeriod: string
  /** 日期差（天）= |记账日-单据日|，辅助提示 */
  dateDiff: number
  /** 滞后天数异常（窗口外，非会计跨期） */
  isLagAnomaly: boolean
  /** 是否会计跨期（相对截止日两侧） */
  isCrossPeriod: boolean
  /** 跨期金额 */
  crossPeriodAmount: number
  /** 结论：正常 / 跨期多记 / 跨期漏记 / 跨期 */
  conclusion: string
}

/** 样本选取标准（对齐 Excel「二、样本选取标准与规模」） */
export interface CutoffSampleCriteria {
  /** 资产负债表日 / 截止日 */
  cutoffDate: string
  /** 截止日前抽样天数 */
  daysBefore: number
  /** 截止日后抽样天数 */
  daysAfter: number
  /** 金额门槛（大于，元） */
  amountThreshold: number
  /** 首年承接客户：是否同时做期初截止 */
  firstYearClient: boolean
}

export type CutoffDirection = 'forward' | 'backward'

// ─── Constants ───────────────────────────────────────────────────────────────

const FORWARD_ROWS_KEY = 'I2-13-rows'
const BACKWARD_ROWS_KEY = 'I2-14-rows'
const FORWARD_CRITERIA_KEY = 'I2-13-sample-criteria'
const BACKWARD_CRITERIA_KEY = 'I2-14-sample-criteria'

const DEFAULT_THRESHOLD_DAYS = 5
const ACCOUNT_CODE = '1717'

const DEFAULT_CRITERIA: CutoffSampleCriteria = {
  cutoffDate: '',
  daysBefore: DEFAULT_THRESHOLD_DAYS,
  daysAfter: DEFAULT_THRESHOLD_DAYS,
  amountThreshold: 0,
  firstYearClient: false,
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI2Cutoff(params: {
  allResponses: Ref<Map<string, any>>
  saveResponses: (sheetCode: string, data: Record<string, any>) => Promise<void>
  projectId: Ref<string>
  /** 默认窗口天数（兼容旧调用） */
  cutoffThresholdDays?: number
  /** 审计年度，用于默认同步截止日 */
  year?: Ref<number | string | undefined> | number | string
}): {
  forwardRows: Ref<CutoffRow[]>
  backwardRows: Ref<CutoffRow[]>
  forwardCriteria: Ref<CutoffSampleCriteria>
  backwardCriteria: Ref<CutoffSampleCriteria>
  forwardBeforeRows: ComputedRef<CutoffRow[]>
  forwardAfterRows: ComputedRef<CutoffRow[]>
  forwardUnsortedRows: ComputedRef<CutoffRow[]>
  backwardBeforeRows: ComputedRef<CutoffRow[]>
  backwardAfterRows: ComputedRef<CutoffRow[]>
  backwardUnsortedRows: ComputedRef<CutoffRow[]>
  forwardCrossPeriodCount: ComputedRef<number>
  backwardCrossPeriodCount: ComputedRef<number>
  forwardCrossPeriodAmount: ComputedRef<number>
  backwardCrossPeriodAmount: ComputedRef<number>
  addForwardRow: (data?: Partial<CutoffRow>) => void
  addBackwardRow: (data?: Partial<CutoffRow>) => void
  removeForwardRow: (index: number) => void
  removeBackwardRow: (index: number) => void
  updateForwardRow: (index: number, field: string, value: any) => void
  updateBackwardRow: (index: number, field: string, value: any) => void
  updateForwardCriteria: (patch: Partial<CutoffSampleCriteria>) => void
  updateBackwardCriteria: (patch: Partial<CutoffSampleCriteria>) => void
  loadFromAutoSampling: (direction: CutoffDirection) => Promise<void>
  save: (direction?: CutoffDirection) => Promise<void>
  syncCutoffDateFromProject: () => string
  expandTestWindow: (direction: CutoffDirection, days?: number) => void
  draftAjeFromCrossPeriod: (direction: CutoffDirection) => Promise<number>
  persistCompletion: (direction: CutoffDirection) => Promise<void>
  needsExpandHint: ComputedRef<boolean>
} {
  const { allResponses, saveResponses, projectId } = params
  const defaultDays = params.cutoffThresholdDays ?? DEFAULT_THRESHOLD_DAYS

  function _resolveYear(): number | string | undefined {
    const y = params.year
    if (y && typeof y === 'object' && 'value' in y) return (y as Ref<any>).value
    return y as number | string | undefined
  }

  const forwardRows = ref<CutoffRow[]>([])
  const backwardRows = ref<CutoffRow[]>([])
  const forwardCriteria = ref<CutoffSampleCriteria>({
    ...DEFAULT_CRITERIA,
    daysBefore: defaultDays,
    daysAfter: defaultDays,
  })
  const backwardCriteria = ref<CutoffSampleCriteria>({
    ...DEFAULT_CRITERIA,
    daysBefore: defaultDays,
    daysAfter: defaultDays,
  })

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _parseDate(dateStr: string): Date | null {
    if (!dateStr) return null
    const d = new Date(dateStr.includes('T') ? dateStr : `${dateStr}T00:00:00`)
    return Number.isNaN(d.getTime()) ? null : d
  }

  function _extractPeriod(dateStr: string): string {
    if (!dateStr || dateStr.length < 7) return ''
    return dateStr.substring(0, 7)
  }

  function _getJson(key: string): any {
    const item = allResponses.value.get(key)
    if (!item) return null
    const raw = (item as any).remark ?? (item as any).conclusion ?? item
    if (raw == null) return null
    if (typeof raw === 'object') return raw
    try { return JSON.parse(raw as string) } catch { return null }
  }

  function _resolveSide(
    direction: CutoffDirection,
    row: Pick<CutoffRow, 'recordDate' | 'documentDate'>,
    cutoffDate: string,
  ): CutoffRow['side'] {
    const anchor = direction === 'forward' ? row.recordDate : row.documentDate
    const a = _parseDate(anchor)
    const c = _parseDate(cutoffDate)
    if (!a || !c) return 'unsorted'
    return a.getTime() <= c.getTime() ? 'before' : 'after'
  }

  function _buildConclusion(
    direction: CutoffDirection,
    isCrossing: boolean,
    documentDate: Date | null,
    recordDate: Date | null,
    cutoffDate: Date | null,
  ): string {
    if (!isCrossing || !documentDate || !recordDate || !cutoffDate) return '正常'
    const c = cutoffDate.getTime()
    const docBefore = documentDate.getTime() <= c
    const recBefore = recordDate.getTime() <= c
    // 账已记本期、单据属下期 → 多记；单据属本期、账记下期 → 漏记
    if (recBefore && !docBefore) return direction === 'forward' ? '跨期多记' : '跨期'
    if (!recBefore && docBefore) return direction === 'backward' ? '跨期漏记' : '跨期'
    return '跨期'
  }

  function _recalcFormulas(
    row: CutoffRow,
    direction: CutoffDirection,
    criteria: CutoffSampleCriteria,
  ): void {
    const rd = _parseDate(row.recordDate)
    const dd = _parseDate(row.documentDate)
    const cd = _parseDate(criteria.cutoffDate)
    const windowDays = Math.max(criteria.daysBefore, criteria.daysAfter, DEFAULT_THRESHOLD_DAYS)

    if (rd && dd) {
      row.dateDiff = calcDateDiffDays(rd, dd)
      row.isLagAnomaly = isLagAnomalyFn(rd, dd, windowDays)
    } else {
      row.dateDiff = 0
      row.isLagAnomaly = false
    }

    if (!row.recordPeriod && row.recordDate) row.recordPeriod = _extractPeriod(row.recordDate)
    if (!row.belongPeriod && row.documentDate) row.belongPeriod = _extractPeriod(row.documentDate)

    if (rd && dd && cd) {
      row.isCrossPeriod = isCutoffPeriodCrossing(dd, rd, cd)
      const basisAmount = direction === 'forward'
        ? (row.amount || row.documentAmount)
        : (row.documentAmount || row.amount)
      row.crossPeriodAmount = calcCrossPeriodAmount(row.isCrossPeriod, basisAmount)
      row.conclusion = _buildConclusion(direction, row.isCrossPeriod, dd, rd, cd)
    } else {
      // 无截止日时降级：记账期间 ≠ 归属期间
      const periodCross = !!(row.recordPeriod && row.belongPeriod && row.recordPeriod !== row.belongPeriod)
      row.isCrossPeriod = periodCross
      const basisAmount = direction === 'forward'
        ? (row.amount || row.documentAmount)
        : (row.documentAmount || row.amount)
      row.crossPeriodAmount = calcCrossPeriodAmount(periodCross, basisAmount)
      row.conclusion = periodCross ? '跨期' : '正常'
    }

    row.side = _resolveSide(direction, row, criteria.cutoffDate)
  }

  function _createEmptyRow(
    direction: CutoffDirection,
    criteria: CutoffSampleCriteria,
    data?: Partial<CutoffRow>,
  ): CutoffRow {
    const row: CutoffRow = {
      side: 'unsorted',
      recordDate: data?.recordDate ?? '',
      voucherNo: data?.voucherNo ?? '',
      amount: data?.amount ?? 0,
      description: data?.description ?? '',
      documentNo: data?.documentNo ?? '',
      documentDate: data?.documentDate ?? '',
      documentAmount: data?.documentAmount ?? data?.amount ?? 0,
      recordPeriod: data?.recordPeriod ?? '',
      belongPeriod: data?.belongPeriod ?? '',
      dateDiff: 0,
      isLagAnomaly: false,
      isCrossPeriod: false,
      crossPeriodAmount: 0,
      conclusion: '正常',
    }
    _recalcFormulas(row, direction, criteria)
    return row
  }

  function _deserializeRows(
    data: any[],
    direction: CutoffDirection,
    criteria: CutoffSampleCriteria,
  ): CutoffRow[] {
    return data.map((raw: any) => {
      const amount = Number(raw.amount) || 0
      const row: CutoffRow = {
        side: 'unsorted',
        recordDate: String(raw.recordDate ?? ''),
        voucherNo: String(raw.voucherNo ?? ''),
        amount,
        description: String(raw.description ?? ''),
        documentNo: String(raw.documentNo ?? ''),
        documentDate: String(raw.documentDate ?? ''),
        documentAmount: Number(raw.documentAmount ?? amount) || 0,
        recordPeriod: String(raw.recordPeriod ?? ''),
        belongPeriod: String(raw.belongPeriod ?? ''),
        dateDiff: 0,
        isLagAnomaly: false,
        isCrossPeriod: false,
        crossPeriodAmount: 0,
        conclusion: '正常',
      }
      _recalcFormulas(row, direction, criteria)
      return row
    })
  }

  function _deserializeCriteria(raw: any, fallbackDays: number): CutoffSampleCriteria {
    if (!raw || typeof raw !== 'object') {
      return { ...DEFAULT_CRITERIA, daysBefore: fallbackDays, daysAfter: fallbackDays }
    }
    return {
      cutoffDate: String(raw.cutoffDate ?? ''),
      daysBefore: Math.max(1, Number(raw.daysBefore) || fallbackDays),
      daysAfter: Math.max(1, Number(raw.daysAfter) || fallbackDays),
      amountThreshold: Math.max(0, Number(raw.amountThreshold) || 0),
      firstYearClient: Boolean(raw.firstYearClient),
    }
  }

  function _persistShape(row: CutoffRow) {
    return {
      recordDate: row.recordDate,
      voucherNo: row.voucherNo,
      amount: row.amount,
      description: row.description,
      documentNo: row.documentNo,
      documentDate: row.documentDate,
      documentAmount: row.documentAmount,
      recordPeriod: row.recordPeriod,
      belongPeriod: row.belongPeriod,
    }
  }

  // ─── Load ──────────────────────────────────────────────────────────────────

  function _loadFromResponses(): void {
    const fc = _deserializeCriteria(_getJson(FORWARD_CRITERIA_KEY), defaultDays)
    const bc = _deserializeCriteria(_getJson(BACKWARD_CRITERIA_KEY), defaultDays)
    forwardCriteria.value = fc
    backwardCriteria.value = bc

    const forwardData = _getJson(FORWARD_ROWS_KEY)
    forwardRows.value = Array.isArray(forwardData) && forwardData.length > 0
      ? _deserializeRows(forwardData, 'forward', fc)
      : []

    const backwardData = _getJson(BACKWARD_ROWS_KEY)
    backwardRows.value = Array.isArray(backwardData) && backwardData.length > 0
      ? _deserializeRows(backwardData, 'backward', bc)
      : []
  }

  watch(allResponses, () => _loadFromResponses(), { immediate: true })

  // ─── Computed ──────────────────────────────────────────────────────────────

  function _filterSide(rows: CutoffRow[], side: CutoffRow['side']) {
    return rows.filter((r) => r.side === side)
  }

  const forwardBeforeRows = computed(() => _filterSide(forwardRows.value, 'before'))
  const forwardAfterRows = computed(() => _filterSide(forwardRows.value, 'after'))
  const forwardUnsortedRows = computed(() => _filterSide(forwardRows.value, 'unsorted'))
  const backwardBeforeRows = computed(() => _filterSide(backwardRows.value, 'before'))
  const backwardAfterRows = computed(() => _filterSide(backwardRows.value, 'after'))
  const backwardUnsortedRows = computed(() => _filterSide(backwardRows.value, 'unsorted'))

  const forwardCrossPeriodCount = computed(() => forwardRows.value.filter((r) => r.isCrossPeriod).length)
  const backwardCrossPeriodCount = computed(() => backwardRows.value.filter((r) => r.isCrossPeriod).length)
  const forwardCrossPeriodAmount = computed(() =>
    forwardRows.value.reduce((s, r) => s + (r.crossPeriodAmount || 0), 0),
  )
  const backwardCrossPeriodAmount = computed(() =>
    backwardRows.value.reduce((s, r) => s + (r.crossPeriodAmount || 0), 0),
  )

  // ─── Mutations ─────────────────────────────────────────────────────────────

  function addForwardRow(data?: Partial<CutoffRow>): void {
    forwardRows.value.push(_createEmptyRow('forward', forwardCriteria.value, data))
  }

  function addBackwardRow(data?: Partial<CutoffRow>): void {
    backwardRows.value.push(_createEmptyRow('backward', backwardCriteria.value, data))
  }

  function removeForwardRow(index: number): void {
    if (index < 0 || index >= forwardRows.value.length) return
    forwardRows.value.splice(index, 1)
  }

  function removeBackwardRow(index: number): void {
    if (index < 0 || index >= backwardRows.value.length) return
    backwardRows.value.splice(index, 1)
  }

  function _updateRow(
    row: CutoffRow,
    field: string,
    value: any,
    direction: CutoffDirection,
    criteria: CutoffSampleCriteria,
  ): void {
    switch (field) {
      case 'recordDate':
        row.recordDate = String(value ?? '')
        if (!row.recordPeriod) row.recordPeriod = _extractPeriod(row.recordDate)
        break
      case 'voucherNo':
        row.voucherNo = String(value ?? '')
        return
      case 'amount':
        row.amount = Number(value) || 0
        if (!row.documentAmount) row.documentAmount = row.amount
        break
      case 'description':
        row.description = String(value ?? '')
        return
      case 'documentNo':
        row.documentNo = String(value ?? '')
        return
      case 'documentDate':
        row.documentDate = String(value ?? '')
        if (!row.belongPeriod) row.belongPeriod = _extractPeriod(row.documentDate)
        break
      case 'documentAmount':
        row.documentAmount = Number(value) || 0
        break
      case 'recordPeriod':
        row.recordPeriod = String(value ?? '')
        break
      case 'belongPeriod':
        row.belongPeriod = String(value ?? '')
        break
      default:
        return
    }
    _recalcFormulas(row, direction, criteria)
  }

  function updateForwardRow(index: number, field: string, value: any): void {
    if (index < 0 || index >= forwardRows.value.length) return
    _updateRow(forwardRows.value[index], field, value, 'forward', forwardCriteria.value)
  }

  function updateBackwardRow(index: number, field: string, value: any): void {
    if (index < 0 || index >= backwardRows.value.length) return
    _updateRow(backwardRows.value[index], field, value, 'backward', backwardCriteria.value)
  }

  function _recalcAll(direction: CutoffDirection): void {
    if (direction === 'forward') {
      for (const row of forwardRows.value) _recalcFormulas(row, 'forward', forwardCriteria.value)
    } else {
      for (const row of backwardRows.value) _recalcFormulas(row, 'backward', backwardCriteria.value)
    }
  }

  function updateForwardCriteria(patch: Partial<CutoffSampleCriteria>): void {
    forwardCriteria.value = {
      ...forwardCriteria.value,
      ...patch,
      daysBefore: Math.max(1, Number(patch.daysBefore ?? forwardCriteria.value.daysBefore) || 1),
      daysAfter: Math.max(1, Number(patch.daysAfter ?? forwardCriteria.value.daysAfter) || 1),
      amountThreshold: Math.max(0, Number(patch.amountThreshold ?? forwardCriteria.value.amountThreshold) || 0),
    }
    _recalcAll('forward')
  }

  function updateBackwardCriteria(patch: Partial<CutoffSampleCriteria>): void {
    backwardCriteria.value = {
      ...backwardCriteria.value,
      ...patch,
      daysBefore: Math.max(1, Number(patch.daysBefore ?? backwardCriteria.value.daysBefore) || 1),
      daysAfter: Math.max(1, Number(patch.daysAfter ?? backwardCriteria.value.daysAfter) || 1),
      amountThreshold: Math.max(0, Number(patch.amountThreshold ?? backwardCriteria.value.amountThreshold) || 0),
    }
    _recalcAll('backward')
  }

  // ─── Auto sampling ─────────────────────────────────────────────────────────

  async function loadFromAutoSampling(direction: CutoffDirection): Promise<void> {
    if (!projectId.value) {
      ElMessage.warning('项目ID无效，无法自动提取样本')
      return
    }

    const criteria = direction === 'forward' ? forwardCriteria.value : backwardCriteria.value
    const daysBefore = criteria.daysBefore || DEFAULT_THRESHOLD_DAYS
    const daysAfter = criteria.daysAfter || DEFAULT_THRESHOLD_DAYS

    try {
      const res = await http.post(
        `/api/projects/${projectId.value}/ledger/cutoff-samples`,
        {
          direction,
          threshold_days: Math.max(daysBefore, daysAfter),
          days_before: daysBefore,
          days_after: daysAfter,
          amount_threshold: criteria.amountThreshold || 0,
          cutoff_date: criteria.cutoffDate || undefined,
          account_code: ACCOUNT_CODE,
        },
      )

      const data = res.data as any
      const items: any[] = Array.isArray(data) ? data : (data?.items ?? data?.data ?? [])

      if (items.length === 0) {
        ElMessage.info(`未找到截止日前后±${Math.max(daysBefore, daysAfter)}天内的序时账样本`)
        return
      }

      const newRows: CutoffRow[] = items.map((item: any) => {
        const amount = Number(item.amount ?? item.debit_amount ?? 0)
        return _createEmptyRow(direction, criteria, {
          recordDate: item.voucher_date ?? item.voucherDate ?? item.record_date ?? '',
          amount,
          recordPeriod: item.record_period ?? item.recordPeriod ?? _extractPeriod(item.voucher_date ?? item.voucherDate ?? ''),
          documentDate: item.document_date ?? item.documentDate ?? '',
          documentNo: item.document_no ?? item.documentNo ?? item.source_no ?? '',
          documentAmount: Number(item.document_amount ?? item.documentAmount ?? amount) || 0,
          belongPeriod: item.belong_period ?? item.belongPeriod ?? '',
          voucherNo: item.voucher_no ?? item.voucherNo ?? '',
          description: item.summary ?? item.description ?? '',
        })
      })

      if (direction === 'forward') {
        forwardRows.value = [...forwardRows.value, ...newRows]
        ElMessage.success(`账→单据：已导入 ${newRows.length} 笔样本`)
      } else {
        backwardRows.value = [...backwardRows.value, ...newRows]
        ElMessage.success(`单据→账：已导入 ${newRows.length} 笔样本`)
      }
    } catch (err: any) {
      ElMessage.error(err?.message || '自动提取样本失败，请降级手工输入')
    }
  }

  // ─── Save ──────────────────────────────────────────────────────────────────

  async function save(direction?: CutoffDirection): Promise<void> {
    const saveForward = !direction || direction === 'forward'
    const saveBackward = !direction || direction === 'backward'

    if (saveForward) {
      await saveResponses('I2-13', {
        [FORWARD_ROWS_KEY]: forwardRows.value.map(_persistShape),
        [FORWARD_CRITERIA_KEY]: { ...forwardCriteria.value },
      })
    }
    if (saveBackward) {
      await saveResponses('I2-14', {
        [BACKWARD_ROWS_KEY]: backwardRows.value.map(_persistShape),
        [BACKWARD_CRITERIA_KEY]: { ...backwardCriteria.value },
      })
    }
  }

  /** 从项目年度/响应同步默认截止日（两边同时写） */
  function syncCutoffDateFromProject(): string {
    const date = resolveDefaultCutoffDate({
      year: _resolveYear(),
      allResponses: allResponses.value,
    })
    if (!forwardCriteria.value.cutoffDate) updateForwardCriteria({ cutoffDate: date })
    else if (forwardCriteria.value.cutoffDate !== date && !forwardCriteria.value.cutoffDate) {
      updateForwardCriteria({ cutoffDate: date })
    }
    if (!backwardCriteria.value.cutoffDate) updateBackwardCriteria({ cutoffDate: date })
    // 若两边都空，上面已填；若一边有一边无，补齐另一边
    if (forwardCriteria.value.cutoffDate && !backwardCriteria.value.cutoffDate) {
      updateBackwardCriteria({ cutoffDate: forwardCriteria.value.cutoffDate })
    }
    if (backwardCriteria.value.cutoffDate && !forwardCriteria.value.cutoffDate) {
      updateForwardCriteria({ cutoffDate: backwardCriteria.value.cutoffDate })
    }
    if (!forwardCriteria.value.cutoffDate && !backwardCriteria.value.cutoffDate) {
      updateForwardCriteria({ cutoffDate: date })
      updateBackwardCriteria({ cutoffDate: date })
    }
    return forwardCriteria.value.cutoffDate || backwardCriteria.value.cutoffDate || date
  }

  /** 发现跨期时扩大测试窗口（默认扩至 30 天，或指定天数） */
  function expandTestWindow(direction: CutoffDirection, days = 30): void {
    const patch = {
      daysBefore: Math.max(days, DEFAULT_THRESHOLD_DAYS),
      daysAfter: Math.max(days, DEFAULT_THRESHOLD_DAYS),
    }
    if (direction === 'forward') updateForwardCriteria(patch)
    else updateBackwardCriteria(patch)
    ElMessage.success(`已将${direction === 'forward' ? '账→单据' : '单据→账'}测试窗口扩大至前后各 ${patch.daysBefore} 天，建议重新自动提取并扩展至报告日复核`)
  }

  const needsExpandHint = computed(() =>
    forwardCrossPeriodCount.value > 0 || backwardCrossPeriodCount.value > 0,
  )

  /** 跨期金额合计生成 I2-3 调整草稿 */
  async function draftAjeFromCrossPeriod(direction: CutoffDirection): Promise<number> {
    const rows = direction === 'forward' ? forwardRows.value : backwardRows.value
    const crossing = rows.filter((r) => r.isCrossPeriod)
    if (!crossing.length) {
      ElMessage.info('当前无跨期样本，无需生成调整')
      return 0
    }
    const amount = crossing.reduce((s, r) => s + (r.crossPeriodAmount || 0), 0)
    await appendI23DraftAje({
      allResponses: allResponses.value,
      saveResponse: saveResponses,
      draft: {
        description: `${direction === 'forward' ? 'I2-13账→单据' : 'I2-14单据→账'}截止测试发现跨期 ${crossing.length} 笔，合计 ${amount}`,
        debitAmount: amount > 0 ? amount : 0,
        creditAmount: 0,
        indexRef: direction === 'forward' ? 'I2-13' : 'I2-14',
        remark: '来源:截止跨期一键生成，请复核借贷方向与对方科目',
      },
    })
    ElMessage.success(`已向 I2-3 生成 ${crossing.length} 笔跨期相关调整草稿（金额 ${amount}）`)
    return crossing.length
  }

  async function persistCompletion(direction: CutoffDirection): Promise<void> {
    const count = direction === 'forward' ? forwardCrossPeriodCount.value : backwardCrossPeriodCount.value
    const total = direction === 'forward' ? forwardRows.value.length : backwardRows.value.length
    const progress = total > 0 ? Math.min(100, 40 + Math.round((total / Math.max(total, 5)) * 60)) : 10
    await writeSheetCompletionMarker({
      allResponses: allResponses.value,
      saveResponse: saveResponses,
      sheetCode: direction === 'forward' ? 'I2-13' : 'I2-14',
      progress: total > 0 ? progress : 5,
      ok: total > 0 && count === 0,
      detail: { sampleCount: total, crossPeriodCount: count },
    })
  }

  // 首次加载若无截止日则同步
  watch(allResponses, () => {
    if (!forwardCriteria.value.cutoffDate || !backwardCriteria.value.cutoffDate) {
      syncCutoffDateFromProject()
    }
  }, { immediate: true })

  return {
    forwardRows,
    backwardRows,
    forwardCriteria,
    backwardCriteria,
    forwardBeforeRows,
    forwardAfterRows,
    forwardUnsortedRows,
    backwardBeforeRows,
    backwardAfterRows,
    backwardUnsortedRows,
    forwardCrossPeriodCount,
    backwardCrossPeriodCount,
    forwardCrossPeriodAmount,
    backwardCrossPeriodAmount,
    addForwardRow,
    addBackwardRow,
    removeForwardRow,
    removeBackwardRow,
    updateForwardRow,
    updateBackwardRow,
    updateForwardCriteria,
    updateBackwardCriteria,
    loadFromAutoSampling,
    save,
    syncCutoffDateFromProject,
    expandTestWindow,
    draftAjeFromCrossPeriod,
    persistCompletion,
    needsExpandHint,
  }
}

export default useI2Cutoff
