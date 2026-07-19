/**
 * useG6MainDetail — G6-2 明细表（对齐 Excel A–AG → 4区段Tab）
 *
 * Template: backend/wp_templates/G/G6 其他债权投资.xlsx · 明细表G6-2
 *
 * 公式（Excel）：
 *   J  期初小计 = 成本+利息调整+应计利息
 *   O  期初审定 = 公允价值+调整数
 *   Q  期初报表数 = 审定数 − 减：期初超过一年到期的部分
 *   U  本期变动小计 = 成本变动+利息调整变动+应计利息变动
 *   V/W/X 期末分项 = 期初 + 本期变动
 *   Y  期末小计 = V+W+X
 *   AD 期末审定 = 期末公允价值+调整数
 *   AF 期末报表数 = 审定数 − 减：一年内到期余额
 *
 * 分类：按到期日 vs 资产负债表日 → 其他流动资产 / 超过一年
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  parseNum,
  calcSubtotal,
  calcPeriodEndComponent,
  calcFvAuditedAmount,
  calcDetailReportAmount,
} from '@/composables/useG6MainFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

const DATA_KEY = 'G6-2-rows'
const BALANCE_SHEET_DATE_KEY = 'G6-2-balance-sheet-date'
const NOTE_KEY = 'G6-2-detail-audit-note'
const CONCLUSION_KEY = 'G6-2-detail-audit-conclusion'
const MAX_ROWS = 500

export type G6InvestCategory = '企业债' | '国债' | '金融债' | '公司债' | '其他'

export interface OtherBondDetailRow {
  id: string
  seq: number
  // ══ A–F 基础信息 ══
  investCategory: string
  investProject: string
  faceValue: number
  couponRate: number
  effectiveRate: number
  maturityDate: string

  // ══ G–Q 期初余额 ══
  openingCost: number
  openingInterestAdj: number
  openingAccruedInterest: number
  openingSubtotal: number // J 公式
  openingFairValue: number
  openingPeriodFvChange: number // L 本期公允价值变动（期初区）
  openingCumulativeFvChange: number // M
  openingAdjustment: number // N
  openingAudited: number // O 公式 = K+N
  openingNonCurrentDeduct: number // P 减：期初超过一年到期的部分
  openingReportAmount: number // Q 公式 = O-P

  // ══ R–U 本期变动（借方发生填正数） ══
  periodCostChange: number
  periodInterestAdjChange: number
  periodAccruedInterestChange: number
  periodChangeSubtotal: number // U 公式

  // ══ V–AG 期末 ══
  closingCost: number // V 公式
  closingInterestAdj: number // W 公式
  closingAccruedInterest: number // X 公式
  closingSubtotal: number // Y 公式
  closingFairValue: number
  closingPeriodFvChange: number // AA
  closingCumulativeFvChange: number // AB
  closingAdjustment: number // AC
  closingAudited: number // AD 公式
  oneYearBalance: number // AE 减：一年内到期余额
  closingReportAmount: number // AF 公式
  correspondenceStatus: string // AG 发函情况

  /** 兼容旧字段 */
  indexRef: string
}

export interface G6DetailColumn {
  prop: keyof OtherBondDetailRow
  label: string
  width: number
  formula?: boolean
  type?: 'text' | 'number' | 'date' | 'select' | 'rate'
  tooltip?: string
}

export interface G6DetailSegment {
  key: string
  label: string
  columns: G6DetailColumn[]
}

export const G6_CATEGORY_LABELS: Record<'一年内到期' | '超过一年', string> = {
  一年内到期: '一、购入的一年内到期的其他债权投资（列报为“其他流动资产”）',
  超过一年: '二、购入的到期期限超过一年的其他债权投资',
}

export const G6_INVEST_CATEGORY_OPTIONS = ['企业债', '国债', '金融债', '公司债', '其他']

export const G6_DETAIL_SEGMENTS: G6DetailSegment[] = [
  {
    key: 'basic',
    label: '基础信息',
    columns: [
      { prop: 'investCategory', label: '投资种类', width: 110, type: 'select' },
      { prop: 'investProject', label: '投资项目', width: 160, type: 'text' },
      { prop: 'faceValue', label: '面值', width: 120, type: 'number' },
      { prop: 'couponRate', label: '票面利率', width: 110, type: 'rate' },
      { prop: 'effectiveRate', label: '实际利率', width: 110, type: 'rate' },
      { prop: 'maturityDate', label: '到期日', width: 130, type: 'date' },
    ],
  },
  {
    key: 'opening',
    label: '期初余额',
    columns: [
      { prop: 'openingCost', label: '成本', width: 110, type: 'number' },
      { prop: 'openingInterestAdj', label: '利息调整（贷方余额填负数）', width: 160, type: 'number' },
      { prop: 'openingAccruedInterest', label: '应计利息', width: 110, type: 'number' },
      {
        prop: 'openingSubtotal',
        label: '小计',
        width: 110,
        formula: true,
        tooltip: '期初小计 = 成本 + 利息调整 + 应计利息',
      },
      { prop: 'openingFairValue', label: '公允价值', width: 120, type: 'number' },
      { prop: 'openingPeriodFvChange', label: '本期公允价值变动', width: 130, type: 'number' },
      { prop: 'openingCumulativeFvChange', label: '累计公允价值变动', width: 130, type: 'number' },
      { prop: 'openingAdjustment', label: '调整数', width: 100, type: 'number' },
      {
        prop: 'openingAudited',
        label: '审定数',
        width: 110,
        formula: true,
        tooltip: '期初审定 = 公允价值 + 调整数',
      },
      {
        prop: 'openingNonCurrentDeduct',
        label: '减：期初超过一年到期的部分',
        width: 170,
        type: 'number',
      },
      {
        prop: 'openingReportAmount',
        label: '期初报表数',
        width: 120,
        formula: true,
        tooltip: '期初报表数 = 审定数 − 超过一年到期的部分',
      },
    ],
  },
  {
    key: 'period',
    label: '本期变动',
    columns: [
      { prop: 'periodCostChange', label: '成本（借方正数）', width: 130, type: 'number' },
      { prop: 'periodInterestAdjChange', label: '利息调整', width: 110, type: 'number' },
      { prop: 'periodAccruedInterestChange', label: '应计利息', width: 110, type: 'number' },
      {
        prop: 'periodChangeSubtotal',
        label: '小计',
        width: 110,
        formula: true,
        tooltip: '本期变动小计 = 成本 + 利息调整 + 应计利息',
      },
    ],
  },
  {
    key: 'closing',
    label: '期末+报表',
    columns: [
      {
        prop: 'closingCost',
        label: '成本',
        width: 110,
        formula: true,
        tooltip: '期末成本 = 期初成本 + 本期成本变动',
      },
      {
        prop: 'closingInterestAdj',
        label: '利息调整（贷方余额填负数）',
        width: 160,
        formula: true,
        tooltip: '期末利息调整 = 期初 + 本期变动',
      },
      {
        prop: 'closingAccruedInterest',
        label: '应计利息',
        width: 110,
        formula: true,
        tooltip: '期末应计利息 = 期初 + 本期变动',
      },
      {
        prop: 'closingSubtotal',
        label: '小计',
        width: 110,
        formula: true,
        tooltip: '期末小计 = 成本 + 利息调整 + 应计利息',
      },
      { prop: 'closingFairValue', label: '公允价值', width: 120, type: 'number' },
      { prop: 'closingPeriodFvChange', label: '本期公允价值变动', width: 130, type: 'number' },
      { prop: 'closingCumulativeFvChange', label: '累计公允价值变动', width: 130, type: 'number' },
      { prop: 'closingAdjustment', label: '调整数', width: 100, type: 'number' },
      {
        prop: 'closingAudited',
        label: '审定数',
        width: 110,
        formula: true,
        tooltip: '期末审定 = 公允价值 + 调整数',
      },
      { prop: 'oneYearBalance', label: '减：一年内到期余额', width: 140, type: 'number' },
      {
        prop: 'closingReportAmount',
        label: '期末报表数',
        width: 120,
        formula: true,
        tooltip: '期末报表数 = 审定数 − 一年内到期余额',
      },
      { prop: 'correspondenceStatus', label: '发函情况', width: 110, type: 'text' },
    ],
  },
]

const SUM_FIELDS: (keyof OtherBondDetailRow)[] = [
  'faceValue',
  'openingCost', 'openingInterestAdj', 'openingAccruedInterest', 'openingSubtotal',
  'openingFairValue', 'openingPeriodFvChange', 'openingCumulativeFvChange',
  'openingAdjustment', 'openingAudited', 'openingNonCurrentDeduct', 'openingReportAmount',
  'periodCostChange', 'periodInterestAdjChange', 'periodAccruedInterestChange', 'periodChangeSubtotal',
  'closingCost', 'closingInterestAdj', 'closingAccruedInterest', 'closingSubtotal',
  'closingFairValue', 'closingPeriodFvChange', 'closingCumulativeFvChange',
  'closingAdjustment', 'closingAudited', 'oneYearBalance', 'closingReportAmount',
]

function generateId(): string {
  return `g6d-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function emptyRow(id: string, seq: number, name = ''): OtherBondDetailRow {
  return {
    id,
    seq,
    investCategory: '',
    investProject: name,
    faceValue: 0,
    couponRate: 0,
    effectiveRate: 0,
    maturityDate: '',
    openingCost: 0,
    openingInterestAdj: 0,
    openingAccruedInterest: 0,
    openingSubtotal: 0,
    openingFairValue: 0,
    openingPeriodFvChange: 0,
    openingCumulativeFvChange: 0,
    openingAdjustment: 0,
    openingAudited: 0,
    openingNonCurrentDeduct: 0,
    openingReportAmount: 0,
    periodCostChange: 0,
    periodInterestAdjChange: 0,
    periodAccruedInterestChange: 0,
    periodChangeSubtotal: 0,
    closingCost: 0,
    closingInterestAdj: 0,
    closingAccruedInterest: 0,
    closingSubtotal: 0,
    closingFairValue: 0,
    closingPeriodFvChange: 0,
    closingCumulativeFvChange: 0,
    closingAdjustment: 0,
    closingAudited: 0,
    oneYearBalance: 0,
    closingReportAmount: 0,
    correspondenceStatus: '',
    indexRef: '',
  }
}

/** 公式链重算 — 对齐 Excel G6-2 */
export function enrichG6DetailRow(r: OtherBondDetailRow): OtherBondDetailRow {
  const openingSubtotal = calcSubtotal(
    r.openingCost,
    r.openingInterestAdj,
    r.openingAccruedInterest,
  )
  const openingAudited = calcFvAuditedAmount(r.openingFairValue, r.openingAdjustment)
  const openingReportAmount = calcDetailReportAmount(openingAudited, r.openingNonCurrentDeduct)

  const periodChangeSubtotal = calcSubtotal(
    r.periodCostChange,
    r.periodInterestAdjChange,
    r.periodAccruedInterestChange,
  )

  const closingCost = calcPeriodEndComponent(r.openingCost, r.periodCostChange)
  const closingInterestAdj = calcPeriodEndComponent(r.openingInterestAdj, r.periodInterestAdjChange)
  const closingAccruedInterest = calcPeriodEndComponent(
    r.openingAccruedInterest,
    r.periodAccruedInterestChange,
  )
  const closingSubtotal = calcSubtotal(closingCost, closingInterestAdj, closingAccruedInterest)
  const closingAudited = calcFvAuditedAmount(r.closingFairValue, r.closingAdjustment)
  const closingReportAmount = calcDetailReportAmount(closingAudited, r.oneYearBalance)

  return {
    ...r,
    openingSubtotal,
    openingAudited,
    openingReportAmount,
    periodChangeSubtotal,
    closingCost,
    closingInterestAdj,
    closingAccruedInterest,
    closingSubtotal,
    closingAudited,
    closingReportAmount,
  }
}

function classifyByMaturity(
  row: OtherBondDetailRow,
  balanceSheetDate: string,
): '一年内到期' | '超过一年' {
  if (!row.maturityDate || !balanceSheetDate) return '超过一年'
  const maturity = new Date(row.maturityDate)
  const bsDate = new Date(balanceSheetDate)
  if (isNaN(maturity.getTime()) || isNaN(bsDate.getTime())) return '超过一年'
  const oneYearLater = new Date(bsDate)
  oneYearLater.setFullYear(oneYearLater.getFullYear() + 1)
  return maturity <= oneYearLater ? '一年内到期' : '超过一年'
}

export type G6MaturityAlertLevel = 'overdue' | 'expiring_soon' | 'normal'

export interface G6MaturityAlert {
  rowId: string
  message: string
  alertLevel: G6MaturityAlertLevel
}

function migrateLegacyRow(raw: any, seq: number): OtherBondDetailRow {
  const base = emptyRow(String(raw.id || generateId()), seq, raw.investProject || raw.invest_project || '')
  const merged: OtherBondDetailRow = {
    ...base,
    investCategory: raw.investCategory || raw.invest_category || raw.investType || raw.invest_type || '',
    faceValue: parseNum(raw.faceValue ?? raw.face_value),
    couponRate: parseNum(raw.couponRate ?? raw.coupon_rate),
    effectiveRate: parseNum(raw.effectiveRate ?? raw.effective_rate),
    maturityDate: raw.maturityDate || raw.maturity_date || '',
    openingCost: parseNum(raw.openingCost ?? raw.opening_cost),
    openingInterestAdj: parseNum(raw.openingInterestAdj ?? raw.opening_interest_adj),
    openingAccruedInterest: parseNum(raw.openingAccruedInterest ?? raw.opening_accrued_interest),
    openingFairValue: parseNum(raw.openingFairValue ?? raw.opening_fair_value),
    openingPeriodFvChange: parseNum(
      raw.openingPeriodFvChange ?? raw.fvChange ?? raw.fv_change ?? raw.opening_period_fv_change,
    ),
    openingCumulativeFvChange: parseNum(
      raw.openingCumulativeFvChange ?? raw.openingOci ?? raw.opening_oci ?? raw.opening_cumulative_fv_change,
    ),
    openingAdjustment: parseNum(raw.openingAdjustment ?? raw.opening_adjustment),
    openingNonCurrentDeduct: parseNum(
      raw.openingNonCurrentDeduct ?? raw.opening_non_current_deduct,
    ),
    periodCostChange: parseNum(
      raw.periodCostChange ?? raw.increase ?? raw.period_cost_change,
    ),
    periodInterestAdjChange: parseNum(raw.periodInterestAdjChange ?? raw.period_interest_adj_change),
    periodAccruedInterestChange: parseNum(
      raw.periodAccruedInterestChange ?? raw.interestIncome ?? raw.period_accrued_interest_change,
    ),
    closingFairValue: parseNum(raw.closingFairValue ?? raw.closing_fair_value),
    closingPeriodFvChange: parseNum(raw.closingPeriodFvChange ?? raw.closing_period_fv_change),
    closingCumulativeFvChange: parseNum(
      raw.closingCumulativeFvChange ?? raw.closingOci ?? raw.closing_oci ?? raw.closing_cumulative_fv_change,
    ),
    closingAdjustment: parseNum(
      raw.closingAdjustment ?? raw.auditAdjustment ?? raw.closing_adjustment ?? raw.audit_adjustment,
    ),
    oneYearBalance: parseNum(raw.oneYearBalance ?? raw.one_year_balance),
    correspondenceStatus: String(raw.correspondenceStatus ?? raw.correspondence_status ?? ''),
    indexRef: String(raw.indexRef ?? raw.index_ref ?? ''),
  }
  // 旧版把期末成本手填；若无 period 变动但有 closing，反推变动
  const legacyClosingCost = parseNum(raw.closingCost ?? raw.closing_cost)
  if (
    !raw.periodCostChange &&
    !raw.increase &&
    legacyClosingCost &&
    Math.abs(legacyClosingCost - merged.openingCost) > 0.005
  ) {
    merged.periodCostChange = Math.round((legacyClosingCost - merged.openingCost) * 100) / 100
  }
  return enrichG6DetailRow(merged)
}

export interface UseG6MainDetailOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly: Ref<boolean>
  htmlData?: Ref<Record<string, any> | null>
}

export function useG6MainDetail(opts: UseG6MainDetailOptions) {
  const rows = ref<OtherBondDetailRow[]>([])
  const segment = ref('basic')
  const balanceSheetDate = ref('')
  const auditNote = ref('')
  const auditConclusion = ref('')
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  function persistRows(): void {
    if (opts.isReadonly.value) return
    const json = JSON.stringify(rows.value.map((r) => ({ ...r })))
    opts.allResponses.value.set(DATA_KEY, {
      item_id: DATA_KEY,
      conclusion: json,
      remark: json,
    })
    debounceFlush()
  }

  function debounceFlush(): void {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      try {
        const items: ChecklistResponse[] = []
        for (const key of [DATA_KEY, BALANCE_SHEET_DATE_KEY, NOTE_KEY, CONCLUSION_KEY]) {
          const it = opts.allResponses.value.get(key)
          if (it) items.push(it)
        }
        if (items.length) {
          window.dispatchEvent(new CustomEvent('g6:save-items', { detail: { items } }))
        }
      } catch { /* silent */ }
    }, 500)
  }

  function loadFromStore(): void {
    const raw = opts.allResponses.value.get(DATA_KEY)?.conclusion
      || opts.allResponses.value.get(DATA_KEY)?.remark
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        if (Array.isArray(parsed) && parsed.length) {
          rows.value = parsed.map((r: any, i: number) => migrateLegacyRow(r, i + 1))
          return
        }
      } catch { /* fallthrough */ }
    }
    const hd = opts.htmlData?.value
    const items = hd?.detail_rows || hd?.rows || hd?.detail?.rows
    if (Array.isArray(items) && items.length) {
      rows.value = items.map((r: any, i: number) => migrateLegacyRow(r, i + 1))
      return
    }
    rows.value = Array.from({ length: 3 }, (_, i) => enrichG6DetailRow(emptyRow(generateId(), i + 1)))
  }

  function loadMeta(): void {
    balanceSheetDate.value =
      opts.allResponses.value.get(BALANCE_SHEET_DATE_KEY)?.conclusion
      || opts.allResponses.value.get(BALANCE_SHEET_DATE_KEY)?.remark
      || ''
    auditNote.value = opts.allResponses.value.get(NOTE_KEY)?.remark || ''
    auditConclusion.value = opts.allResponses.value.get(CONCLUSION_KEY)?.remark || ''
  }

  watch(
    () => opts.allResponses.value,
    () => {
      if (rows.value.length === 0) {
        loadFromStore()
        loadMeta()
      }
    },
    { immediate: true, deep: false },
  )

  const activeColumns = computed(() => {
    const seg = G6_DETAIL_SEGMENTS.find((s) => s.key === segment.value)
    return seg?.columns ?? G6_DETAIL_SEGMENTS[0].columns
  })

  const categoryGroups = computed(() => {
    const within: OtherBondDetailRow[] = []
    const over: OtherBondDetailRow[] = []
    for (const r of rows.value) {
      if (classifyByMaturity(r, balanceSheetDate.value) === '一年内到期') within.push(r)
      else over.push(r)
    }
    return [
      { category: '一年内到期' as const, label: G6_CATEGORY_LABELS['一年内到期'], rows: within },
      { category: '超过一年' as const, label: G6_CATEGORY_LABELS['超过一年'], rows: over },
    ]
  })

  function sumRows(list: OtherBondDetailRow[]): Record<string, number> {
    const t: Record<string, number> = {}
    for (const f of SUM_FIELDS) t[f] = 0
    for (const r of list) {
      for (const f of SUM_FIELDS) t[f] = Math.round((t[f] + parseNum(r[f] as number)) * 100) / 100
    }
    return t
  }

  const grandTotal = computed(() => sumRows(rows.value))

  const maturityAlerts = computed<G6MaturityAlert[]>(() => {
    if (!balanceSheetDate.value) return []
    const bs = new Date(balanceSheetDate.value)
    if (isNaN(bs.getTime())) return []
    const alerts: G6MaturityAlert[] = []
    const soon = new Date(bs)
    soon.setMonth(soon.getMonth() + 3)
    for (const r of rows.value) {
      if (!r.maturityDate || !r.investProject) continue
      const m = new Date(r.maturityDate)
      if (isNaN(m.getTime())) continue
      if (m < bs) {
        alerts.push({
          rowId: r.id,
          message: `${r.investProject}（到期日 ${r.maturityDate}）已逾期`,
          alertLevel: 'overdue',
        })
      } else if (m <= soon) {
        alerts.push({
          rowId: r.id,
          message: `${r.investProject}（到期日 ${r.maturityDate}）将于3个月内到期`,
          alertLevel: 'expiring_soon',
        })
      }
    }
    return alerts
  })

  const hasOverdueItems = computed(() => maturityAlerts.value.some((a) => a.alertLevel === 'overdue'))
  const hasExpiringSoonItems = computed(() =>
    maturityAlerts.value.some((a) => a.alertLevel === 'expiring_soon'),
  )

  /** 供 G6-1 回写的公允价值合计（期末审定） */
  const fvAuditedTotal = computed(() => grandTotal.value.closingAudited ?? 0)
  const fvReportTotal = computed(() => grandTotal.value.closingReportAmount ?? 0)

  function updateRow(id: string, field: keyof OtherBondDetailRow, value: unknown): void {
    if (opts.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.id === id)
    if (idx < 0) return
    const next = { ...rows.value[idx], [field]: value } as OtherBondDetailRow
    rows.value[idx] = enrichG6DetailRow(next)
    persistRows()
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    if (rows.value.length >= MAX_ROWS) return
    try {
      const { value } = await ElMessageBox.prompt('请输入投资项目名称', '新增投资项目', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '项目名称不能为空',
      })
      if (!value?.trim()) return
      const row = enrichG6DetailRow(emptyRow(generateId(), rows.value.length + 1, value.trim()))
      rows.value = [...rows.value, row]
      persistRows()
    } catch { /* cancel */ }
  }

  function removeRow(id: string): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value
      .filter((r) => r.id !== id)
      .map((r, i) => ({ ...r, seq: i + 1 }))
    persistRows()
  }

  function setBalanceSheetDate(date: string): void {
    if (opts.isReadonly.value) return
    balanceSheetDate.value = date
    opts.allResponses.value.set(BALANCE_SHEET_DATE_KEY, {
      item_id: BALANCE_SHEET_DATE_KEY,
      conclusion: date,
      remark: date,
    })
    debounceFlush()
  }

  watch(auditNote, (val) => {
    if (opts.isReadonly.value) return
    opts.allResponses.value.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
    debounceFlush()
  })
  watch(auditConclusion, (val) => {
    if (opts.isReadonly.value) return
    opts.allResponses.value.set(CONCLUSION_KEY, {
      item_id: CONCLUSION_KEY,
      conclusion: null,
      remark: val,
    })
    debounceFlush()
  })

  function reload(): void {
    loadFromStore()
    loadMeta()
  }

  return {
    rows,
    segment,
    balanceSheetDate,
    auditNote,
    auditConclusion,
    activeColumns,
    categoryGroups,
    grandTotal,
    maturityAlerts,
    hasOverdueItems,
    hasExpiringSoonItems,
    fvAuditedTotal,
    fvReportTotal,
    updateRow,
    addRow,
    removeRow,
    setBalanceSheetDate,
    reload,
    sumRows,
  }
}

export default useG6MainDetail
