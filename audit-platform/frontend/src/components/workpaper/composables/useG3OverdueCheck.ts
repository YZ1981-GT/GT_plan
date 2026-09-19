/**
 * useG3OverdueCheck — G3-5 长期未收回款项检查表
 *
 * 对齐致同 Excel 检查表滚动态，并保留股利专用字段以勾稽 G3-1 账龄：
 *   被投资方 | 期初 | 借方 | 贷方 | 期末(公式) | 账龄 | 业务说明 |
 *   未收回原因 | 是否无法收回 | 处理计划 | 审定余额 | 期后收款 |
 *   宣告日 | 约定付款日 | 逾期天数(公式) | 备注
 *
 * 公式：
 *   期末余额 = 期初 + 本期借方 − 本期贷方
 *   逾期天数 = MAX(0, asOf − 约定付款日)
 * G3-1：一年以上 = 逾期≥365 天金额合计（receivableAmount ← 期末/审定）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  parseNum,
  calcOverdueDays,
  calcSubtotal,
} from './useG3DivRecFormulaEngine'
import {
  useAgingConfig,
  PRESET_SEGMENTS,
  type AgingSegment,
  type AgingPreset,
} from '@/composables/useAgingConfig'
import { G3_DETAIL_ROWS_KEY } from './g3Constants'
import type { ChecklistResponse } from './useF1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

export type UncollectibleFlag = '' | '是' | '否' | '部分'

/** @deprecated 兼容旧 UI / 导入 */
export type Recoverability = 'full' | 'partial' | 'unlikely' | 'irrecoverable'
/** @deprecated 兼容旧 UI / 导入 */
export type RiskLevel = 'low' | 'medium' | 'high' | 'extreme'

export interface OverdueDividendRow {
  id: string
  seq: number
  investeeName: string
  openingBalance: number
  periodDebit: number
  periodCredit: number
  closingBalance: number
  aging: string
  businessDesc: string
  unrecoveredReason: string
  isUncollectible: UncollectibleFlag
  actionPlan: string
  auditedBalance: number
  postPeriodCollection: number
  declarationDate: string
  agreedPaymentDate: string
  overdueDays: number
  /** 供 G3-1 账龄勾稽（= 期末余额，迁移兼容） */
  receivableAmount: number
  remark: string
  /** @deprecated 旧字段 */
  overdueReason?: string
  investeeOperatingStatus?: string
  historicalDividendRecord?: string
  recoverability?: Recoverability
  riskLevel?: RiskLevel
  auditSuggestion?: string
}

interface StoredOverdueRow {
  id: string
  seq: number
  investeeName: string
  openingBalance: number
  periodDebit: number
  periodCredit: number
  aging: string
  businessDesc: string
  unrecoveredReason: string
  isUncollectible: UncollectibleFlag
  actionPlan: string
  auditedBalance: number
  postPeriodCollection: number
  declarationDate: string
  agreedPaymentDate: string
  remark: string
}

export interface OverdueSummary {
  openingBalance: number
  periodDebit: number
  periodCredit: number
  closingBalance: number
  auditedBalance: number
  postPeriodCollection: number
  /** 逾期笔数（逾期天数 > 0） */
  overdueCount: number
  /** 逾期总金额（期末余额合计） */
  overdueTotal: number
  /** 高风险：逾期>180 或无法收回/部分 */
  highRiskCount: number
  longTermCount: number
  uncollectibleCount: number
}

export const UNCOLLECTIBLE_OPTIONS: { value: UncollectibleFlag; label: string }[] = [
  { value: '', label: '（未选）' },
  { value: '是', label: '是' },
  { value: '否', label: '否' },
  { value: '部分', label: '部分' },
]

/** @deprecated 保留兼容 */
export const RECOVERABILITY_OPTIONS: { value: Recoverability; label: string }[] = [
  { value: 'full', label: '全额可收回' },
  { value: 'partial', label: '部分可收回' },
  { value: 'unlikely', label: '很可能无法收回' },
  { value: 'irrecoverable', label: '无法收回' },
]

/** @deprecated 保留兼容 */
export const RISK_LEVEL_OPTIONS: { value: RiskLevel; label: string }[] = [
  { value: 'low', label: '低' },
  { value: 'medium', label: '中' },
  { value: 'high', label: '高' },
  { value: 'extreme', label: '极高' },
]

const DATA_KEY = 'G3-5-overdue-rows'
const AGING_PRESET_KEY = 'G3-5-aging-preset'
const AGING_CUSTOM_KEY = 'G3-5-aging-custom-segments'
const DETAIL_KEY = G3_DETAIL_ROWS_KEY

function generateId(): string {
  return `od-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function labelsToCustomSegments(labels: string[]): AgingSegment[] {
  return labels.map((label, i) => ({
    key: `custom-${i}`,
    label,
    dayFrom: 0,
    dayTo: null,
  }))
}

function parseCustomLabels(raw: string | null | undefined): string[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.map((x) => String(x || '').trim()).filter(Boolean)
  } catch {
    return []
  }
}

function isLongTermAging(aging: string): boolean {
  const a = String(aging || '').trim()
  if (!a) return false
  if (/^1年以内|一年以内|within\s*1/i.test(a)) return false
  return true
}

function mapRecoverability(v: unknown): UncollectibleFlag {
  if (v === '是' || v === '否' || v === '部分') return v
  if (v === 'irrecoverable') return '是'
  if (v === 'unlikely' || v === 'partial') return '部分'
  return ''
}

function createEmptyStored(seq: number): StoredOverdueRow {
  return {
    id: generateId(),
    seq,
    investeeName: '',
    openingBalance: 0,
    periodDebit: 0,
    periodCredit: 0,
    aging: '',
    businessDesc: '',
    unrecoveredReason: '',
    isUncollectible: '',
    actionPlan: '',
    auditedBalance: 0,
    postPeriodCollection: 0,
    declarationDate: '',
    agreedPaymentDate: '',
    remark: '',
  }
}

/** 旧版股利专用列 → Excel 滚动态 */
export function migrateLegacyOverdueRow(row: any, seq: number): StoredOverdueRow {
  if (row && ('openingBalance' in row || 'periodDebit' in row || 'periodCredit' in row)) {
    const bizParts = [
      String(row.businessDesc || ''),
      String(row.investeeOperatingStatus || ''),
      String(row.historicalDividendRecord || ''),
    ].filter(Boolean)
    return {
      id: String(row.id || generateId()),
      seq: Number(row.seq) || seq,
      investeeName: String(row.investeeName || ''),
      openingBalance: parseNum(row.openingBalance),
      periodDebit: parseNum(row.periodDebit),
      periodCredit: parseNum(row.periodCredit),
      aging: String(row.aging || ''),
      businessDesc: bizParts.join('；') || String(row.businessDesc || ''),
      unrecoveredReason: String(row.unrecoveredReason || row.overdueReason || ''),
      isUncollectible: mapRecoverability(row.isUncollectible ?? row.recoverability),
      actionPlan: String(row.actionPlan || row.auditSuggestion || ''),
      auditedBalance: parseNum(
        row.auditedBalance ?? row.receivableAmount ?? row.closingBalance,
      ),
      postPeriodCollection: parseNum(row.postPeriodCollection),
      declarationDate: String(row.declarationDate || ''),
      agreedPaymentDate: String(row.agreedPaymentDate || ''),
      remark: String(row.remark || ''),
    }
  }

  const amount = parseNum(row?.receivableAmount)
  const bizParts = [
    String(row?.investeeOperatingStatus || ''),
    String(row?.historicalDividendRecord || ''),
  ].filter(Boolean)
  return {
    id: String(row?.id || generateId()),
    seq: Number(row?.seq) || seq,
    investeeName: String(row?.investeeName || ''),
    openingBalance: amount,
    periodDebit: 0,
    periodCredit: 0,
    aging: String(row?.aging || ''),
    businessDesc: bizParts.join('；'),
    unrecoveredReason: String(row?.overdueReason || row?.unrecoveredReason || ''),
    isUncollectible: mapRecoverability(row?.recoverability ?? row?.isUncollectible),
    actionPlan: String(row?.auditSuggestion || row?.actionPlan || ''),
    auditedBalance: amount,
    postPeriodCollection: parseNum(row?.postPeriodCollection),
    declarationDate: String(row?.declarationDate || ''),
    agreedPaymentDate: String(row?.agreedPaymentDate || ''),
    remark: String(row?.remark || ''),
  }
}

function enrich(
  stored: StoredOverdueRow,
  asOf: Date = new Date(),
): OverdueDividendRow {
  const closingBalance =
    stored.openingBalance + stored.periodDebit - stored.periodCredit
  const agreedDate = stored.agreedPaymentDate
    ? new Date(stored.agreedPaymentDate)
    : null
  const overdueDays =
    agreedDate && !Number.isNaN(agreedDate.getTime())
      ? calcOverdueDays(asOf, agreedDate)
      : 0

  return {
    ...stored,
    closingBalance,
    overdueDays,
    receivableAmount: closingBalance,
    overdueReason: stored.unrecoveredReason,
    auditSuggestion: stored.actionPlan,
  }
}

function safeParseRows(jsonStr: string | null | undefined): StoredOverdueRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r, i) => migrateLegacyOverdueRow(r, i + 1))
  } catch {
    return []
  }
}

function agingLabelFromDays(days: number, segments: AgingSegment[]): string {
  if (days <= 0) {
    return segments.find((s) => /^1年以内|一年以内/i.test(s.label))?.label || segments[0]?.label || ''
  }
  for (const seg of segments) {
    const to = seg.dayTo ?? Number.POSITIVE_INFINITY
    if (days >= seg.dayFrom && days <= to) return seg.label
  }
  return segments[segments.length - 1]?.label || '1年以上'
}

/**
 * 行风险高亮：>180 红 / >90 橙；无法收回优先红
 */
export function getOverdueRiskClass(row: OverdueDividendRow): string {
  if (row.id === '__subtotal__') return 'row-subtotal'
  if (row.isUncollectible === '是') return 'overdue-danger'
  if (row.overdueDays > 180) return 'overdue-danger'
  if (row.isUncollectible === '部分' || row.overdueDays > 90 || isLongTermAging(row.aging)) {
    return 'overdue-warning'
  }
  return ''
}

export function isOverdueDanger(row: OverdueDividendRow): boolean {
  return row.overdueDays > 180 || row.isUncollectible === '是'
}

export function isOverdueWarning(row: OverdueDividendRow): boolean {
  return (
    !isOverdueDanger(row) &&
    (row.overdueDays > 90 || row.isUncollectible === '部分' || isLongTermAging(row.aging))
  )
}

export function useG3OverdueCheck(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
  projectId?: Ref<string>
  /** 账龄/逾期计算基准日，默认当前日期 */
  asOf?: Ref<Date>
}) {
  const readonly = opts.isReadonly
  const projectId = opts.projectId ?? ref('')
  const asOf = opts.asOf ?? ref(new Date())

  const { segments: projectSegments, preset: projectPreset } = useAgingConfig(
    projectId,
    'G3',
  )
  const sheetAgingPreset = ref<'' | AgingPreset>('')
  const customSegments = ref<AgingSegment[]>([])

  watch(
    () => opts.allResponses.value.get(AGING_PRESET_KEY)?.remark,
    (v) => {
      const raw = String(v || '').trim().toUpperCase()
      sheetAgingPreset.value =
        raw === 'THREE_YEAR' || raw === 'FIVE_YEAR' || raw === 'CUSTOM' ? raw : ''
    },
    { immediate: true },
  )
  watch(
    () => opts.allResponses.value.get(AGING_CUSTOM_KEY)?.remark,
    (v) => {
      const labels = parseCustomLabels(v)
      customSegments.value = labels.length >= 2 ? labelsToCustomSegments(labels) : []
    },
    { immediate: true },
  )

  const agingPreset: ComputedRef<AgingPreset> = computed(() => {
    if (sheetAgingPreset.value) return sheetAgingPreset.value
    const p = projectPreset.value
    if (p === 'THREE_YEAR' || p === 'FIVE_YEAR' || p === 'CUSTOM') return p
    return 'THREE_YEAR'
  })

  const segments: ComputedRef<AgingSegment[]> = computed(() => {
    if (sheetAgingPreset.value === 'CUSTOM') {
      if (customSegments.value.length >= 2) return customSegments.value
      if (projectPreset.value === 'CUSTOM' && projectSegments.value.length >= 2) {
        return projectSegments.value
      }
      return PRESET_SEGMENTS.THREE_YEAR
    }
    if (sheetAgingPreset.value === 'THREE_YEAR' || sheetAgingPreset.value === 'FIVE_YEAR') {
      return PRESET_SEGMENTS[sheetAgingPreset.value]
    }
    if (projectSegments.value.length) return projectSegments.value
    return PRESET_SEGMENTS.THREE_YEAR
  })

  const agingOptions: ComputedRef<string[]> = computed(() =>
    segments.value.map((s) => s.label),
  )

  const dataRows = ref<OverdueDividendRow[]>([])

  function reloadFromStore() {
    const stored = safeParseRows(opts.allResponses.value.get(DATA_KEY)?.conclusion)
    dataRows.value = stored.length
      ? stored.map((r) => enrich(r, asOf.value))
      : [enrich(createEmptyStored(1), asOf.value)]
  }

  reloadFromStore()

  watch(
    () => opts.allResponses.value.get(DATA_KEY)?.conclusion,
    () => reloadFromStore(),
  )

  const summary = computed<OverdueSummary>(() => {
    const list = dataRows.value
    const overdueRows = list.filter((r) => r.overdueDays > 0)
    const longTermCount = list.filter(
      (r) => r.overdueDays >= 365 || isLongTermAging(r.aging),
    ).length
    const uncollectibleCount = list.filter(
      (r) => r.isUncollectible === '是' || r.isUncollectible === '部分',
    ).length
    return {
      openingBalance: calcSubtotal(list.map((r) => r.openingBalance)),
      periodDebit: calcSubtotal(list.map((r) => r.periodDebit)),
      periodCredit: calcSubtotal(list.map((r) => r.periodCredit)),
      closingBalance: calcSubtotal(list.map((r) => r.closingBalance)),
      auditedBalance: calcSubtotal(list.map((r) => r.auditedBalance)),
      postPeriodCollection: calcSubtotal(list.map((r) => r.postPeriodCollection)),
      overdueCount: overdueRows.length,
      overdueTotal: calcSubtotal(overdueRows.map((r) => r.closingBalance)),
      highRiskCount: list.filter(
        (r) => r.overdueDays > 180 || r.isUncollectible === '是' || r.isUncollectible === '部分',
      ).length,
      longTermCount,
      uncollectibleCount,
    }
  })

  const displayRows = computed<OverdueDividendRow[]>(() => {
    const rows = dataRows.value
    if (!rows.length) return rows
    const t = summary.value
    return [
      ...rows,
      {
        id: '__subtotal__',
        seq: 0,
        investeeName: '合计',
        openingBalance: t.openingBalance,
        periodDebit: t.periodDebit,
        periodCredit: t.periodCredit,
        closingBalance: t.closingBalance,
        aging: '',
        businessDesc: '',
        unrecoveredReason: '',
        isUncollectible: '',
        actionPlan: '',
        auditedBalance: t.auditedBalance,
        postPeriodCollection: t.postPeriodCollection,
        declarationDate: '',
        agreedPaymentDate: '',
        overdueDays: 0,
        receivableAmount: t.closingBalance,
        remark: '',
      },
    ]
  })

  /** @deprecated 兼容旧调用点：等价 dataRows */
  const rows = dataRows

  function persistAll() {
    if (readonly.value) return
    const payload: StoredOverdueRow[] = dataRows.value.map((r, i) => ({
      id: r.id,
      seq: i + 1,
      investeeName: r.investeeName,
      openingBalance: r.openingBalance,
      periodDebit: r.periodDebit,
      periodCredit: r.periodCredit,
      aging: r.aging,
      businessDesc: r.businessDesc,
      unrecoveredReason: r.unrecoveredReason,
      isUncollectible: r.isUncollectible,
      actionPlan: r.actionPlan,
      auditedBalance: r.auditedBalance,
      postPeriodCollection: r.postPeriodCollection,
      declarationDate: r.declarationDate,
      agreedPaymentDate: r.agreedPaymentDate,
      remark: r.remark,
    }))
    // 顺带写入 receivableAmount，保证后端 IE / G3-1 解析兼容
    const withCompat = payload.map((s) => {
      const closing = s.openingBalance + s.periodDebit - s.periodCredit
      return { ...s, receivableAmount: closing, overdueDays: enrich(s, asOf.value).overdueDays }
    })
    opts.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(withCompat) })
  }

  function isMetaRow(row: OverdueDividendRow): boolean {
    return row.id === '__subtotal__'
  }

  function isLongTerm(row: OverdueDividendRow): boolean {
    return row.overdueDays >= 365 || isLongTermAging(row.aging)
  }

  function updateRow(id: string, patch: Partial<OverdueDividendRow>) {
    if (readonly.value || id === '__subtotal__') return
    dataRows.value = dataRows.value.map((r) => {
      if (r.id !== id) return r
      const next = { ...r, ...patch }
      // 金额字段用 stored 再 enrich
      const stored: StoredOverdueRow = {
        id: next.id,
        seq: next.seq,
        investeeName: next.investeeName,
        openingBalance: parseNum(next.openingBalance),
        periodDebit: parseNum(next.periodDebit),
        periodCredit: parseNum(next.periodCredit),
        aging: next.aging,
        businessDesc: next.businessDesc,
        unrecoveredReason: next.unrecoveredReason || next.overdueReason || '',
        isUncollectible: next.isUncollectible,
        actionPlan: next.actionPlan || next.auditSuggestion || '',
        auditedBalance: parseNum(next.auditedBalance),
        postPeriodCollection: parseNum(next.postPeriodCollection),
        declarationDate: next.declarationDate,
        agreedPaymentDate: next.agreedPaymentDate,
        remark: next.remark,
      }
      return enrich(stored, asOf.value)
    })
    persistAll()
  }

  /** 兼容旧 API */
  function updateCell(rowId: string, field: string, value: string | number) {
    updateRow(rowId, { [field]: value } as Partial<OverdueDividendRow>)
  }

  async function addRow() {
    if (readonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入被投资方名称', '新增检查行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '被投资方名称不能为空',
      })
      const seq = dataRows.value.length + 1
      const stored = { ...createEmptyStored(seq), investeeName: value.trim() }
      dataRows.value = [...dataRows.value, enrich(stored, asOf.value)]
      persistAll()
    } catch {
      /* cancelled */
    }
  }

  function removeRow(id: string) {
    if (readonly.value || dataRows.value.length <= 1 || id === '__subtotal__') return
    dataRows.value = dataRows.value
      .filter((r) => r.id !== id)
      .map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
  }

  function syncAuditedFromClosing(rowId: string) {
    if (readonly.value) return
    const row = dataRows.value.find((r) => r.id === rowId)
    if (!row) return
    updateRow(rowId, { auditedBalance: row.closingBalance })
  }

  function setAgingPreset(preset: AgingPreset, customLabels?: string[]): boolean {
    if (readonly.value) return false
    if (preset === 'CUSTOM') {
      const labels = (customLabels || customSegments.value.map((s) => s.label))
        .map((x) => String(x || '').trim())
        .filter(Boolean)
      if (labels.length < 2) return false
      if (labels.length > 10) labels.length = 10
      sheetAgingPreset.value = 'CUSTOM'
      customSegments.value = labelsToCustomSegments(labels)
      opts.debouncedSave(AGING_PRESET_KEY, { conclusion: null, remark: 'CUSTOM' })
      opts.debouncedSave(AGING_CUSTOM_KEY, {
        conclusion: null,
        remark: JSON.stringify(labels),
      })
    } else {
      sheetAgingPreset.value = preset
      customSegments.value = []
      opts.debouncedSave(AGING_PRESET_KEY, { conclusion: null, remark: preset })
      opts.debouncedSave(AGING_CUSTOM_KEY, { conclusion: null, remark: '[]' })
    }
    return true
  }

  /**
   * 从 G3-2 导入：期末应收 > 0 且（已逾期或标记逾期）。
   * 按被投资方合并；保留已有原因/计划/约定付款日等手工字段。
   */
  function importFromDetail(): { imported: number; updated: number } {
    if (readonly.value) return { imported: 0, updated: 0 }
    const raw = opts.allResponses.value.get(DETAIL_KEY)?.conclusion
    if (!raw) return { imported: 0, updated: 0 }

    let details: any[] = []
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) return { imported: 0, updated: 0 }
      details = parsed
    } catch {
      return { imported: 0, updated: 0 }
    }

    const candidates = details.filter((d) => {
      const netRec =
        parseNum(d.netReceivable) ||
        Math.max(0, parseNum(d.dividendReceivable) - parseNum(d.receivedAmount))
      let calcDays = parseNum(d.overdueDays)
      if (!calcDays && d.recordDate) {
        calcDays = calcOverdueDays(asOf.value, new Date(String(d.recordDate)))
      }
      const isOverdue = String(d.isOverdue || '') === '是' || calcDays > 0
      return netRec > 0.005 && isOverdue
    })

    if (!candidates.length) return { imported: 0, updated: 0 }

    const byName = new Map(dataRows.value.map((r) => [r.investeeName.trim(), r]))
    // 清空默认空行
    let working = dataRows.value.filter(
      (r) => r.investeeName.trim() || r.closingBalance !== 0 || r.agreedPaymentDate,
    )
    let imported = 0
    let updated = 0
    let nextSeq = working.length ? Math.max(...working.map((r) => r.seq)) + 1 : 1

    for (const src of candidates) {
      const name = String(src.investeeName || '').trim()
      if (!name) continue
      const dividendReceivable = parseNum(src.dividendReceivable)
      const receivedAmount = parseNum(src.receivedAmount)
      const netReceivable =
        parseNum(src.netReceivable) || Math.max(0, dividendReceivable - receivedAmount)
      let days = parseNum(src.overdueDays)
      if (!days && src.recordDate) {
        days = calcOverdueDays(asOf.value, new Date(String(src.recordDate)))
      }
      const aging = agingLabelFromDays(days, segments.value)
      const declarationDate = String(src.declarationDate || '')
      const agreedPaymentDate = String(src.agreedPaymentDate || src.recordDate || '')
      const businessDesc = String(src.dividendPlan || src.remark || '')

      const existing = byName.get(name)
      if (existing) {
        const idx = working.findIndex((r) => r.id === existing.id)
        if (idx === -1) continue
        const stored: StoredOverdueRow = {
          id: existing.id,
          seq: existing.seq,
          investeeName: name,
          openingBalance: 0,
          periodDebit: dividendReceivable || netReceivable,
          periodCredit: receivedAmount,
          aging: existing.aging || aging,
          businessDesc: existing.businessDesc || businessDesc,
          unrecoveredReason: existing.unrecoveredReason,
          isUncollectible: existing.isUncollectible,
          actionPlan: existing.actionPlan,
          auditedBalance: existing.auditedBalance || netReceivable,
          postPeriodCollection: existing.postPeriodCollection,
          declarationDate: existing.declarationDate || declarationDate,
          agreedPaymentDate: existing.agreedPaymentDate || agreedPaymentDate,
          remark: existing.remark || '来自G3-2逾期',
        }
        working[idx] = enrich(stored, asOf.value)
        byName.set(name, working[idx])
        updated += 1
      } else {
        const stored: StoredOverdueRow = {
          id: generateId(),
          seq: nextSeq++,
          investeeName: name,
          openingBalance: 0,
          periodDebit: dividendReceivable || netReceivable,
          periodCredit: receivedAmount,
          aging,
          businessDesc,
          unrecoveredReason: '',
          isUncollectible: '',
          actionPlan: '',
          auditedBalance: netReceivable,
          postPeriodCollection: 0,
          declarationDate,
          agreedPaymentDate,
          remark: '来自G3-2逾期',
        }
        const row = enrich(stored, asOf.value)
        working.push(row)
        byName.set(name, row)
        imported += 1
      }
    }

    dataRows.value = working.map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
    return { imported, updated }
  }

  function loadAll() {
    reloadFromStore()
  }

  return {
    rows,
    dataRows,
    displayRows,
    summary,
    segments,
    agingOptions,
    agingPreset,
    customSegments,
    isMetaRow,
    isLongTerm,
    loadAll,
    persistAll,
    updateRow,
    updateCell,
    addRow,
    removeRow,
    syncAuditedFromClosing,
    setAgingPreset,
    importFromDetail,
    getOverdueRiskClass,
    isOverdueDanger,
    isOverdueWarning,
    UNCOLLECTIBLE_OPTIONS,
    RECOVERABILITY_OPTIONS,
    RISK_LEVEL_OPTIONS,
  }
}

export default useG3OverdueCheck
