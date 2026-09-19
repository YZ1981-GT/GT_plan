/**
 * useCycleCutoff — 循环截止性测试通用 composable（I2/I6 等双向截止底稿）
 *
 * 对齐致同 Excel：审计目标 → 样本选取 → 截止日前后分段 → 说明 → 结论
 * 跨期判定：单据日与记账日分处截止日两侧（isCutoffPeriodCrossing）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import {
  calcDateDiffDays,
  isCrossPeriod as isLagAnomalyFn,
  calcCrossPeriodAmount,
} from './useI2FormulaEngine'
// 跨期判定收敛：委托 cutoffCanonical 单一真源（cutoff-boundary 模式），等价 isCutoffPeriodCrossing（P8）
import { crossesByCutoffBoundary } from './cutoffCanonical'
import {
  parseResponseArray,
  resolveDefaultCutoffDate,
  writeSheetCompletionMarker,
} from './i2EnhancementHelpers'
import { buildCutoffCrossCheck, type CutoffCrossCheckSummary } from './cutoffCrossCheck'
import { amountMismatch, priorPeriodCutoffDate } from './cutoffRowHelpers'

export type CutoffDirection = 'forward' | 'backward'

/** 截止测试行 */
export interface CutoffRow {
  side: 'before' | 'after' | 'unsorted'
  recordDate: string
  voucherNo: string
  amount: number
  description: string
  documentNo: string
  documentDate: string
  documentAmount: number
  recordPeriod: string
  belongPeriod: string
  dateDiff: number
  isLagAnomaly: boolean
  isCrossPeriod: boolean
  crossPeriodAmount: number
  conclusion: string
}

/** 样本选取标准 */
export interface CutoffSampleCriteria {
  cutoffDate: string
  daysBefore: number
  daysAfter: number
  amountThreshold: number
  firstYearClient: boolean
}

export interface CycleCutoffDraftDefaults {
  reportItem: string
  accountCode: string
  accountName: string
  defaultIndexRef: string
}

export interface CycleCutoffConfig {
  accountCode: string
  forwardRowsKey: string
  backwardRowsKey: string
  forwardCriteriaKey: string
  backwardCriteriaKey: string
  sharedCriteriaKey?: string
  forwardSheetCode: string
  backwardSheetCode: string
  adjustmentSheetCode: string
  adjustmentRowsKey: string
  draftDefaults: CycleCutoffDraftDefaults
  defaultThresholdDays?: number
}

const DEFAULT_CRITERIA_BASE: CutoffSampleCriteria = {
  cutoffDate: '',
  daysBefore: 5,
  daysAfter: 5,
  amountThreshold: 0,
  firstYearClient: false,
}

export function useCycleCutoff(params: {
  config: CycleCutoffConfig
  allResponses: Ref<Map<string, any>>
  saveResponses: (sheetCode: string, data: Record<string, any>) => Promise<void>
  projectId: Ref<string>
  cutoffThresholdDays?: number
  year?: Ref<number | string | undefined> | number | string
  /** 是否 criteria 变更时自动同步对向底稿，默认 true */
  syncCriteriaPeer?: boolean
  /** 行/标准变更 debounce 自动保存(ms)，0=关闭，默认 400 */
  autoSaveMs?: number
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
  amountMismatchCount: ComputedRef<number>
  lagAnomalyCount: ComputedRef<number>
  crossCheckSummary: ComputedRef<CutoffCrossCheckSummary>
  priorPeriodCutoffDate: ComputedRef<string>
  addForwardRow: (data?: Partial<CutoffRow>) => void
  addBackwardRow: (data?: Partial<CutoffRow>) => void
  removeForwardRow: (index: number) => void
  removeBackwardRow: (index: number) => void
  updateForwardRow: (index: number, field: string, value: any) => void
  updateBackwardRow: (index: number, field: string, value: any) => void
  updateForwardCriteria: (patch: Partial<CutoffSampleCriteria>) => void
  updateBackwardCriteria: (patch: Partial<CutoffSampleCriteria>) => void
  syncCriteriaToPeer: (source: CutoffDirection) => void
  loadFromAutoSampling: (direction: CutoffDirection) => Promise<void>
  importExtractedVouchers: (direction: CutoffDirection, items: any[], opts?: { fillDocumentDate?: boolean }) => void
  save: (direction?: CutoffDirection) => Promise<void>
  syncCutoffDateFromProject: () => string
  expandTestWindow: (direction: CutoffDirection, days?: number) => void
  draftAjeFromCrossPeriod: (direction: CutoffDirection) => Promise<number>
  persistCompletion: (direction: CutoffDirection) => Promise<void>
  needsExpandHint: ComputedRef<boolean>
  flushAutoSave: () => Promise<void>
} {
  const {
    config,
    allResponses,
    saveResponses,
    projectId,
    syncCriteriaPeer = true,
    autoSaveMs = 400,
  } = params
  const defaultDays = params.cutoffThresholdDays ?? config.defaultThresholdDays ?? 5

  function _resolveYear(): number | string | undefined {
    const y = params.year
    if (y && typeof y === 'object' && 'value' in y) return (y as Ref<any>).value
    return y as number | string | undefined
  }

  const forwardRows = ref<CutoffRow[]>([])
  const backwardRows = ref<CutoffRow[]>([])
  const forwardCriteria = ref<CutoffSampleCriteria>({
    ...DEFAULT_CRITERIA_BASE,
    daysBefore: defaultDays,
    daysAfter: defaultDays,
  })
  const backwardCriteria = ref<CutoffSampleCriteria>({
    ...DEFAULT_CRITERIA_BASE,
    daysBefore: defaultDays,
    daysAfter: defaultDays,
  })

  let autoSaveTimer: ReturnType<typeof setTimeout> | null = null
  let pendingSaveDirections = new Set<CutoffDirection>()

  function _scheduleAutoSave(direction?: CutoffDirection): void {
    if (autoSaveMs <= 0) return
    if (direction) pendingSaveDirections.add(direction)
    else {
      pendingSaveDirections.add('forward')
      pendingSaveDirections.add('backward')
    }
    if (autoSaveTimer) clearTimeout(autoSaveTimer)
    autoSaveTimer = setTimeout(() => {
      void flushAutoSave()
    }, autoSaveMs)
  }

  async function flushAutoSave(): Promise<void> {
    if (autoSaveTimer) {
      clearTimeout(autoSaveTimer)
      autoSaveTimer = null
    }
    const dirs = [...pendingSaveDirections]
    pendingSaveDirections = new Set()
    for (const d of dirs) {
      await save(d)
    }
  }

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
    const windowDays = Math.max(criteria.daysBefore, criteria.daysAfter, defaultDays)

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
      // cutoff-boundary：记账日与单据日分处截止日两侧即跨期（canonical 单一真源）
      row.isCrossPeriod = crossesByCutoffBoundary(row.recordDate, row.documentDate, criteria.cutoffDate)
      const basisAmount = direction === 'forward'
        ? (row.amount || row.documentAmount)
        : (row.documentAmount || row.amount)
      row.crossPeriodAmount = calcCrossPeriodAmount(row.isCrossPeriod, basisAmount)
      row.conclusion = _buildConclusion(direction, row.isCrossPeriod, dd, rd, cd)
    } else {
      // 缺少记账日/原始单据日无法按日期判定 → 退化为所属期间比较。
      // 但只有当记账期间与所属期间【两侧证据齐全】时才可下"正常/跨期"结论；
      // 任一侧缺失（如自动提取仅得记账侧、原始单据未取得）一律判"证据不完整"，
      // 不得假绿为"正常"（自动提取到记账凭证 ≠ 截止测试完成）。
      const bothPeriods = !!(row.recordPeriod && row.belongPeriod)
      if (bothPeriods) {
        const periodCross = row.recordPeriod !== row.belongPeriod
        row.isCrossPeriod = periodCross
        const basisAmount = direction === 'forward'
          ? (row.amount || row.documentAmount)
          : (row.documentAmount || row.amount)
        row.crossPeriodAmount = calcCrossPeriodAmount(periodCross, basisAmount)
        row.conclusion = periodCross ? '跨期' : '正常'
      } else {
        row.isCrossPeriod = false
        row.crossPeriodAmount = 0
        row.conclusion = '证据不完整'
      }
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
      // 原始单据金额不得自动复制账面金额（会制造天然一致=审计假绿），仅显式传入时采用
      documentAmount: data?.documentAmount ?? 0,
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
        recordDate: String(raw.recordDate ?? raw.bookingDate ?? ''),
        voucherNo: String(raw.voucherNo ?? ''),
        amount,
        description: String(raw.description ?? raw.expenseType ?? ''),
        documentNo: String(raw.documentNo ?? ''),
        documentDate: String(raw.documentDate ?? ''),
        // 反序列化同样不回退账面金额，缺原始单据金额则为 0（证据不完整）
        documentAmount: Number(raw.documentAmount ?? 0) || 0,
        recordPeriod: String(raw.recordPeriod ?? raw.period ?? raw.bookingPeriod ?? ''),
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
      return { ...DEFAULT_CRITERIA_BASE, daysBefore: fallbackDays, daysAfter: fallbackDays }
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

  function _persistSharedCriteria(): void {
    if (!config.sharedCriteriaKey) return
    const shared = {
      cutoffDate: forwardCriteria.value.cutoffDate || backwardCriteria.value.cutoffDate,
      daysBefore: forwardCriteria.value.daysBefore,
      daysAfter: forwardCriteria.value.daysAfter,
      amountThreshold: forwardCriteria.value.amountThreshold,
      firstYearClient: forwardCriteria.value.firstYearClient,
    }
    allResponses.value.set(config.sharedCriteriaKey, {
      item_id: config.sharedCriteriaKey,
      conclusion: null,
      remark: JSON.stringify(shared),
    })
  }

  function _loadFromResponses(): void {
    const sharedRaw = config.sharedCriteriaKey ? _getJson(config.sharedCriteriaKey) : null
    const fc = _deserializeCriteria(_getJson(config.forwardCriteriaKey) ?? sharedRaw, defaultDays)
    const bc = _deserializeCriteria(_getJson(config.backwardCriteriaKey) ?? sharedRaw, defaultDays)
    forwardCriteria.value = fc
    backwardCriteria.value = bc

    const forwardData = _getJson(config.forwardRowsKey)
    forwardRows.value = Array.isArray(forwardData) && forwardData.length > 0
      ? _deserializeRows(forwardData, 'forward', fc)
      : []

    const backwardData = _getJson(config.backwardRowsKey)
    backwardRows.value = Array.isArray(backwardData) && backwardData.length > 0
      ? _deserializeRows(backwardData, 'backward', bc)
      : []
  }

  watch(allResponses, () => _loadFromResponses(), { immediate: true })

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

  const amountMismatchCount = computed(() =>
    [...forwardRows.value, ...backwardRows.value].filter((r) => amountMismatch(r)).length,
  )
  const lagAnomalyCount = computed(() =>
    [...forwardRows.value, ...backwardRows.value].filter((r) => r.isLagAnomaly).length,
  )
  const crossCheckSummary = computed(() =>
    buildCutoffCrossCheck(forwardRows.value, backwardRows.value),
  )
  const priorPeriodCutoffDateVal = computed(() =>
    priorPeriodCutoffDate(forwardCriteria.value.cutoffDate || backwardCriteria.value.cutoffDate),
  )

  function addForwardRow(data?: Partial<CutoffRow>): void {
    forwardRows.value.push(_createEmptyRow('forward', forwardCriteria.value, data))
    _scheduleAutoSave('forward')
  }

  function addBackwardRow(data?: Partial<CutoffRow>): void {
    backwardRows.value.push(_createEmptyRow('backward', backwardCriteria.value, data))
    _scheduleAutoSave('backward')
  }

  function removeForwardRow(index: number): void {
    if (index < 0 || index >= forwardRows.value.length) return
    forwardRows.value.splice(index, 1)
    _scheduleAutoSave('forward')
  }

  function removeBackwardRow(index: number): void {
    if (index < 0 || index >= backwardRows.value.length) return
    backwardRows.value.splice(index, 1)
    _scheduleAutoSave('backward')
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
        _scheduleAutoSave(direction)
        return
      case 'amount':
        // 仅更新账面金额；原始单据金额需审计师独立录入，不自动同步（避免假绿）
        row.amount = Number(value) || 0
        break
      case 'description':
        row.description = String(value ?? '')
        _scheduleAutoSave(direction)
        return
      case 'documentNo':
        row.documentNo = String(value ?? '')
        _scheduleAutoSave(direction)
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
    _scheduleAutoSave(direction)
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

  function _applyCriteria(
    target: 'forward' | 'backward',
    patch: Partial<CutoffSampleCriteria>,
    skipPeerSync: boolean,
  ): void {
    const refObj = target === 'forward' ? forwardCriteria : backwardCriteria
    refObj.value = {
      ...refObj.value,
      ...patch,
      daysBefore: Math.max(1, Number(patch.daysBefore ?? refObj.value.daysBefore) || 1),
      daysAfter: Math.max(1, Number(patch.daysAfter ?? refObj.value.daysAfter) || 1),
      amountThreshold: Math.max(0, Number(patch.amountThreshold ?? refObj.value.amountThreshold) || 0),
    }
    _recalcAll(target)
    _persistSharedCriteria()
    _scheduleAutoSave(target)
    if (syncCriteriaPeer && !skipPeerSync) {
      syncCriteriaToPeer(target, true)
    }
  }

  function updateForwardCriteria(patch: Partial<CutoffSampleCriteria>): void {
    _applyCriteria('forward', patch, false)
  }

  function updateBackwardCriteria(patch: Partial<CutoffSampleCriteria>): void {
    _applyCriteria('backward', patch, false)
  }

  function syncCriteriaToPeer(source: CutoffDirection, silent = false): void {
    const src = source === 'forward' ? forwardCriteria.value : backwardCriteria.value
    const patch: Partial<CutoffSampleCriteria> = {
      cutoffDate: src.cutoffDate,
      daysBefore: src.daysBefore,
      daysAfter: src.daysAfter,
      amountThreshold: src.amountThreshold,
      firstYearClient: src.firstYearClient,
    }
    if (source === 'forward') _applyCriteria('backward', patch, true)
    else _applyCriteria('forward', patch, true)
    _persistSharedCriteria()
    _scheduleAutoSave()
    if (!silent) ElMessage.success('样本选取标准已同步至对向截止底稿')
  }

  async function loadFromAutoSampling(direction: CutoffDirection): Promise<void> {
    if (!projectId.value) {
      ElMessage.warning('项目ID无效，无法自动提取样本')
      return
    }

    const criteria = direction === 'forward' ? forwardCriteria.value : backwardCriteria.value
    const daysBefore = criteria.daysBefore || defaultDays
    const daysAfter = criteria.daysAfter || defaultDays
    // year 从截止日推导，回退项目年度；截止方向（forward/backward）由客户端分段处理，
    // 后端只需返回窗口内凭证，故不再传 direction。
    const yr =
      Number(String(criteria.cutoffDate || '').slice(0, 4)) ||
      Number(_resolveYear()) ||
      new Date().getFullYear()

    try {
      // 真实端点：POST /sampling/cutoff-test（提取期末±N天序时账交易）。
      // 旧代码调 POST /ledger/cutoff-samples 为不存在端点，导致 I2/I6「自动提取」恒 404 失败。
      const res = await http.post(
        `/api/projects/${projectId.value}/sampling/cutoff-test`,
        {
          account_codes: [config.accountCode],
          year: yr,
          days_before: daysBefore,
          days_after: daysAfter,
          amount_threshold: criteria.amountThreshold || 0,
          // 传显式截止基准日，后端据此取窗口（期中/短期/非自然年度项目）；
          // 缺省时后端回退 year-12-31。
          cutoff_date: criteria.cutoffDate || undefined,
        },
      )

      const payload = (res as any).data?.data ?? (res as any).data ?? {}
      const rawEntries: any[] = Array.isArray(payload)
        ? payload
        : Array.isArray(payload.entries)
          ? payload.entries
          : Array.isArray(payload.items)
            ? payload.items
            : []

      if (rawEntries.length === 0) {
        ElMessage.info(`未找到截止日前后±${Math.max(daysBefore, daysAfter)}天内的序时账样本`)
        return
      }

      // 归一化金额（借优先取贷）供 importExtractedVouchers 读取
      const items = rawEntries.map((e: any) => ({
        ...e,
        amount: Number(e.amount ?? e.debit_amount ?? 0) || Number(e.credit_amount ?? 0) || 0,
      }))

      importExtractedVouchers(direction, items, { fillDocumentDate: false })
      const dirLabel = direction === 'forward' ? '账→单据' : '单据→账'
      ElMessage.success(`${dirLabel}：已导入 ${items.length} 笔样本（期末±${Math.max(daysBefore, daysAfter)}天，请补录单据日期后判定跨期）`)
    } catch (err: any) {
      ElMessage.error(err?.message || '自动提取样本失败，请降级手工输入')
    }
  }

  function importExtractedVouchers(
    direction: CutoffDirection,
    items: any[],
    opts?: { fillDocumentDate?: boolean },
  ): void {
    const fillDoc = opts?.fillDocumentDate ?? false
    const criteria = direction === 'forward' ? forwardCriteria.value : backwardCriteria.value
    const newRows: CutoffRow[] = items.map((item: any) => {
      const amount = Number(item.amount ?? item.debit_amount ?? item.debitAmount ?? 0)
      const explicitDocDate = item.document_date ?? item.documentDate ?? ''
      return _createEmptyRow(direction, criteria, {
        recordDate: item.voucher_date ?? item.voucherDate ?? item.record_date ?? item.bookingDate ?? '',
        amount,
        recordPeriod: item.record_period ?? item.recordPeriod ?? _extractPeriod(item.voucher_date ?? ''),
        documentDate: fillDoc ? explicitDocDate : '',
        documentNo: item.document_no ?? item.documentNo ?? item.source_no ?? '',
        documentAmount: fillDoc ? (Number(item.document_amount ?? item.documentAmount ?? amount) || 0) : 0,
        belongPeriod: item.belong_period ?? item.belongPeriod ?? '',
        voucherNo: item.voucher_no ?? item.voucherNo ?? '',
        description: item.summary ?? item.description ?? '',
      })
    })

    if (direction === 'forward') {
      forwardRows.value = [...forwardRows.value, ...newRows]
    } else {
      backwardRows.value = [...backwardRows.value, ...newRows]
    }
    _scheduleAutoSave(direction)
  }

  async function save(direction?: CutoffDirection): Promise<void> {
    const saveForward = !direction || direction === 'forward'
    const saveBackward = !direction || direction === 'backward'

    if (saveForward) {
      await saveResponses(config.forwardSheetCode, {
        [config.forwardRowsKey]: forwardRows.value.map(_persistShape),
        [config.forwardCriteriaKey]: { ...forwardCriteria.value },
        ...(config.sharedCriteriaKey ? { [config.sharedCriteriaKey]: { ...forwardCriteria.value } } : {}),
      })
    }
    if (saveBackward) {
      await saveResponses(config.backwardSheetCode, {
        [config.backwardRowsKey]: backwardRows.value.map(_persistShape),
        [config.backwardCriteriaKey]: { ...backwardCriteria.value },
        ...(config.sharedCriteriaKey ? { [config.sharedCriteriaKey]: { ...backwardCriteria.value } } : {}),
      })
    }
  }

  function syncCutoffDateFromProject(): string {
    const date = resolveDefaultCutoffDate({
      year: _resolveYear(),
      allResponses: allResponses.value,
    })
    if (!forwardCriteria.value.cutoffDate && !backwardCriteria.value.cutoffDate) {
      updateForwardCriteria({ cutoffDate: date })
      updateBackwardCriteria({ cutoffDate: date })
    } else if (forwardCriteria.value.cutoffDate && !backwardCriteria.value.cutoffDate) {
      updateBackwardCriteria({ cutoffDate: forwardCriteria.value.cutoffDate })
    } else if (backwardCriteria.value.cutoffDate && !forwardCriteria.value.cutoffDate) {
      updateForwardCriteria({ cutoffDate: backwardCriteria.value.cutoffDate })
    }
    return forwardCriteria.value.cutoffDate || backwardCriteria.value.cutoffDate || date
  }

  function expandTestWindow(direction: CutoffDirection, days = 30): void {
    const patch = {
      daysBefore: Math.max(days, defaultDays),
      daysAfter: Math.max(days, defaultDays),
    }
    if (direction === 'forward') updateForwardCriteria(patch)
    else updateBackwardCriteria(patch)
    ElMessage.success(`已将${direction === 'forward' ? '账→单据' : '单据→账'}测试窗口扩大至前后各 ${patch.daysBefore} 天`)
  }

  const needsExpandHint = computed(() =>
    forwardCrossPeriodCount.value > 0 || backwardCrossPeriodCount.value > 0,
  )

  async function _appendDraftRow(draft: {
    description: string
    debitAmount?: number
    creditAmount?: number
    indexRef?: string
    remark?: string
  }): Promise<void> {
    const existing = parseResponseArray(allResponses.value.get(config.adjustmentRowsKey))
    const rowId = `${config.adjustmentSheetCode.toLowerCase()}-draft-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
    const debit = Number(draft.debitAmount) || 0
    const credit = Number(draft.creditAmount) || 0
    const next = [
      ...existing,
      {
        rowId,
        seq: existing.length + 1,
        description: draft.description,
        category: '账项调整',
        entryType: 'AJE',
        reportItem: config.draftDefaults.reportItem,
        accountCode: config.draftDefaults.accountCode,
        accountName: config.draftDefaults.accountName,
        noteItem: '',
        debitAmount: debit,
        creditAmount: credit,
        indexRef: draft.indexRef ?? config.draftDefaults.defaultIndexRef,
        remark: draft.remark ?? '来源:截止跨期一键生成，请复核借贷方向与对方科目',
      },
    ]
    const payload = JSON.stringify(next)
    allResponses.value.set(config.adjustmentRowsKey, { item_id: config.adjustmentRowsKey, conclusion: null, remark: payload })
    await saveResponses(config.adjustmentSheetCode, { [config.adjustmentRowsKey]: payload })
  }

  async function draftAjeFromCrossPeriod(direction: CutoffDirection): Promise<number> {
    const rows = direction === 'forward' ? forwardRows.value : backwardRows.value
    const crossing = rows.filter((r) => r.isCrossPeriod)
    if (!crossing.length) {
      ElMessage.info('当前无跨期样本，无需生成调整')
      return 0
    }

    const groups = new Map<string, CutoffRow[]>()
    for (const row of crossing) {
      const key = row.conclusion || '跨期'
      if (!groups.has(key)) groups.set(key, [])
      groups.get(key)!.push(row)
    }

    let added = 0
    const sheetLabel = direction === 'forward' ? config.forwardSheetCode : config.backwardSheetCode
    for (const [conclusion, group] of groups) {
      const amount = group.reduce((s, r) => s + (r.crossPeriodAmount || 0), 0)
      const isUnderstatement = /漏记|少计/.test(conclusion)
      await _appendDraftRow({
        description: `${sheetLabel} ${conclusion} ${group.length}笔，合计 ${amount}`,
        debitAmount: isUnderstatement ? amount : 0,
        creditAmount: isUnderstatement ? 0 : amount,
        indexRef: sheetLabel,
        remark: `结论类型:${conclusion}；来源:截止跨期分组生成；请复核对方科目(应付/库存/在建等)`,
      })
      added += 1
    }

    // 跨期既落 AJE 草稿，也推送 A13 错报汇总（对齐 K9-6/7；crossWpEventBridge 白名单事件）。
    // wpCode 从科目所属循环推导（adjustmentSheetCode 如 'I2-3' → 'I2'）。
    const cycleWp = String(config.adjustmentSheetCode || sheetLabel).split('-')[0] || sheetLabel
    try {
      eventBus.emit('a13:push-misstatement' as any, {
        wpCode: cycleWp,
        accountCode: config.accountCode,
        projectId: projectId.value,
        source: sheetLabel,
        items: crossing.map((r) => ({
          voucherNo: r.voucherNo || '',
          amount: Number(r.crossPeriodAmount || r.amount || 0),
          description: `截止跨期（记账${r.recordDate || '-'}/单据${r.documentDate || '-'}）${r.description || '截止性异常'}`.trim(),
          indexRef: sheetLabel,
        })),
        timestamp: Date.now(),
      })
    } catch {
      // 推送失败不阻塞 AJE 草稿生成
    }

    ElMessage.success(`已向 ${config.adjustmentSheetCode} 生成 ${added} 条分组调整草稿（共 ${crossing.length} 笔跨期），并推送 A13 错报汇总`)
    return added
  }

  async function persistCompletion(direction: CutoffDirection): Promise<void> {
    const rows = direction === 'forward' ? forwardRows.value : backwardRows.value
    const count = direction === 'forward' ? forwardCrossPeriodCount.value : backwardCrossPeriodCount.value
    const total = rows.length
    // 证据不完整行数：缺记账侧/原始单据侧独立证据的样本，未闭环不得判完成
    const incompleteCount = rows.filter((r) => r.conclusion === '证据不完整').length
    const hasConclusion = Boolean(allResponses.value.get(`${direction === 'forward' ? config.forwardSheetCode : config.backwardSheetCode}-audit-conclusion`)?.remark)
    const progress = total > 0
      ? Math.min(100, (hasConclusion ? 90 : 50) + Math.min(10, total))
      : 5
    const sheetCode = direction === 'forward' ? config.forwardSheetCode : config.backwardSheetCode
    await writeSheetCompletionMarker({
      allResponses: allResponses.value,
      saveResponse: saveResponses,
      sheetCode,
      // 证据不完整时压低进度，避免"看似接近完成"误导
      progress: total > 0 ? (incompleteCount > 0 ? Math.min(progress, 70) : progress) : 5,
      // 完成门禁：有样本 + 无跨期未决 + 无证据不完整 + 已填审计结论
      ok: total > 0 && count === 0 && incompleteCount === 0 && hasConclusion,
      detail: {
        sampleCount: total,
        crossPeriodCount: count,
        amountMismatchCount: amountMismatchCount.value,
        incompleteEvidenceCount: incompleteCount,
      },
    })
  }

  watch(allResponses, () => {
    if (!forwardCriteria.value.cutoffDate && !backwardCriteria.value.cutoffDate) {
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
    amountMismatchCount,
    lagAnomalyCount,
    crossCheckSummary,
    priorPeriodCutoffDate: priorPeriodCutoffDateVal,
    addForwardRow,
    addBackwardRow,
    removeForwardRow,
    removeBackwardRow,
    updateForwardRow,
    updateBackwardRow,
    updateForwardCriteria,
    updateBackwardCriteria,
    syncCriteriaToPeer,
    loadFromAutoSampling,
    importExtractedVouchers,
    save,
    syncCutoffDateFromProject,
    expandTestWindow,
    draftAjeFromCrossPeriod,
    persistCompletion,
    needsExpandHint,
    flushAutoSave,
  }
}

export default useCycleCutoff
