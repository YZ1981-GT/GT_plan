/**
 * useF4Detail — F4-2 应付账款明细表（源表27列）
 *
 * 公式严格对齐 Excel：
 * H 期初审定余额 = E期初未审 + F期初AJE + G期初RJE
 * K 期末余额 = E期初未审 + J贷方发生 - I借方发生
 * M 期末未审余额 = K期末余额 + L被审计单位重分类
 * T 审定数 = M期末未审 + R账项调整 + S重分类调整
 * N:Q 未审账龄合计应等于 M；U:X 审定账龄合计应等于 T。
 */
import { ref, computed, watch, inject, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import {
  parseNum,
  calcCreditBalance,
  calcAuditedAmount,
  calcAgingCrossCheck,
  calcSubtotal,
} from './useF4AccPayFormulaEngine'
import { readRowJson, type ChecklistResponse } from './useF4FormData'
import { PRESET_SEGMENTS, useAgingConfig, type AgingSegment } from '@/composables/useAgingConfig'
import { migrateF4FlatToNested, remapRowAgingData, type AgingData } from '@/composables/useAgingMigration'
import {
  aggregateAgingBySegments,
  createEmptyF4Aging,
  f4AgingValue,
  projectLegacyFlatAging,
  sumRowAging,
  F4_AGING_FIELD,
  type F4AgingPeriod,
} from './f4AgingModel'

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

export interface APDetailRow {
  rowId: string
  seq: number
  // A:D 基础信息
  creditor: string
  companyCode: string
  relatedPartyType: string
  paymentNature: string
  // E:M 期初、本期发生及期末未审
  openingUnadjusted: number
  openingAje: number
  openingRje: number
  openingAdjusted: number
  currentDebit: number
  currentCredit: number
  closingBalance: number
  entityReclassification: number
  closingUnadjusted: number
  // N:Q 未审账龄（权威 = agingCurrent；以下扁平字段为 3 年段兼容派生，只读）
  agingCurrent: AgingData
  unadjustedAgingLt1: number
  unadjustedAging1to2: number
  unadjustedAging2to3: number
  unadjustedAgingGt3: number
  unadjustedAgingTotal: number
  // R:T 调整与审定
  closingAje: number
  closingRje: number
  closingAdjusted: number
  // U:X 审定账龄（权威 = agingAudited；以下扁平字段为兼容派生，只读）
  agingAudited: AgingData
  auditedAgingLt1: number
  auditedAging1to2: number
  auditedAging2to3: number
  auditedAgingGt3: number
  auditedAgingTotal: number
  // Y:AA 其他审计信息
  isConfirmed: string
  subsequentPayment: number
  remark: string
  unadjustedAgingMismatch: boolean
  auditedAgingMismatch: boolean
  subsequentPaymentExceedsBalance: boolean
}

export type F4DetailInputType = 'text' | 'number' | 'select'

export interface F4DetailColumn {
  prop: keyof APDetailRow | string
  label: string
  group: 'identity' | 'movement' | 'unadjusted-aging' | 'audit' | 'other'
  width?: number
  minWidth?: number
  formula?: string
  editable?: boolean
  inputType?: F4DetailInputType
  options?: readonly string[]
}

export const F4_RELATED_PARTY_OPTIONS = [
  '合并范围内关联方',
  '合并范围外关联方',
  '非关联方',
] as const

export const F4_PAYMENT_NATURE_OPTIONS = ['货款', '工程款', '设备款', '服务费', '其他'] as const
export const F4_CONFIRMATION_OPTIONS = ['是', '否', '不适用'] as const
/**
 * @deprecated 账龄档位改由项目账龄配置（`useAgingConfig(projectId,'F4')`）动态提供，
 * 本常量仅保留为 3 年段兼容别名映射（旧调用方 bucket → 段 key）。
 */
export const F4_AGING_BUCKET_OPTIONS = [
  { value: 'lt1', label: '1年以下' },
  { value: '1to2', label: '1～2年' },
  { value: '2to3', label: '2～3年' },
  { value: 'gt3', label: '3年以上' },
] as const
export type F4AgingBucket = typeof F4_AGING_BUCKET_OPTIONS[number]['value']

/** 旧 bucket → 段 key（兼容 `allocateAging(rowId, stage, 'lt1')` 这类历史调用） */
const LEGACY_BUCKET_TO_SEG: Record<string, string> = {
  lt1: 'within1',
  '1to2': 'y1to2',
  '2to3': 'y2to3',
  gt3: 'over3',
}

/** A:M 身份、期初及本期变动（13列） */
export const F4_DETAIL_BASIC_COLUMNS: F4DetailColumn[] = [
  { prop: 'creditor', label: '债权人名称', group: 'identity', minWidth: 150, editable: true, inputType: 'text' },
  { prop: 'companyCode', label: '公司代码', group: 'identity', minWidth: 110, editable: true, inputType: 'text' },
  { prop: 'relatedPartyType', label: '关联方类型', group: 'identity', minWidth: 150, editable: true, inputType: 'select', options: F4_RELATED_PARTY_OPTIONS },
  { prop: 'paymentNature', label: '款项性质', group: 'identity', minWidth: 110, editable: true, inputType: 'select', options: F4_PAYMENT_NATURE_OPTIONS },
  { prop: 'openingUnadjusted', label: '期初未审余额', group: 'movement', minWidth: 120, editable: true, inputType: 'number' },
  { prop: 'openingAje', label: '期初账项调整', group: 'movement', minWidth: 120, editable: true, inputType: 'number' },
  { prop: 'openingRje', label: '期初重分类调整', group: 'movement', minWidth: 130, editable: true, inputType: 'number' },
  { prop: 'openingAdjusted', label: '期初审定余额', group: 'movement', minWidth: 120, formula: '期初未审+期初AJE+期初RJE', editable: false },
  { prop: 'currentDebit', label: '借方发生', group: 'movement', minWidth: 110, editable: true, inputType: 'number' },
  { prop: 'currentCredit', label: '贷方发生', group: 'movement', minWidth: 110, editable: true, inputType: 'number' },
  { prop: 'closingBalance', label: '期末余额', group: 'movement', minWidth: 110, formula: '期初未审+贷方-借方', editable: false },
  { prop: 'entityReclassification', label: '被审计单位重分类调整', group: 'movement', minWidth: 160, editable: true, inputType: 'number' },
  { prop: 'closingUnadjusted', label: '期末未审余额', group: 'movement', minWidth: 120, formula: '期末余额+被审计单位重分类', editable: false },
]

/** N:Q + Y:AA 未审账龄及其他审计信息（7列） */
export const F4_DETAIL_AGING_COLUMNS: F4DetailColumn[] = [
  { prop: 'unadjustedAgingLt1', label: '未审账龄·1年以下', group: 'unadjusted-aging', minWidth: 125, editable: true, inputType: 'number' },
  { prop: 'unadjustedAging1to2', label: '未审账龄·1～2年', group: 'unadjusted-aging', minWidth: 125, editable: true, inputType: 'number' },
  { prop: 'unadjustedAging2to3', label: '未审账龄·2～3年', group: 'unadjusted-aging', minWidth: 125, editable: true, inputType: 'number' },
  { prop: 'unadjustedAgingGt3', label: '未审账龄·3年以上', group: 'unadjusted-aging', minWidth: 130, editable: true, inputType: 'number' },
  { prop: 'isConfirmed', label: '是否函证', group: 'other', minWidth: 100, editable: true, inputType: 'select', options: F4_CONFIRMATION_OPTIONS },
  { prop: 'subsequentPayment', label: '期后付款', group: 'other', minWidth: 115, editable: true, inputType: 'number' },
  { prop: 'remark', label: '备注', group: 'other', minWidth: 180, editable: true, inputType: 'text' },
]

/** Y:AA 其他审计信息（3列，与账龄段无关） */
export const F4_DETAIL_OTHER_COLUMNS: F4DetailColumn[] = [
  { prop: 'isConfirmed', label: '是否函证', group: 'other', minWidth: 100, editable: true, inputType: 'select', options: F4_CONFIRMATION_OPTIONS },
  { prop: 'subsequentPayment', label: '期后付款', group: 'other', minWidth: 115, editable: true, inputType: 'number' },
  { prop: 'remark', label: '备注', group: 'other', minWidth: 180, editable: true, inputType: 'text' },
]

/** R:T 调整与审定（3列，与账龄段无关） */
export const F4_DETAIL_ADJUST_COLUMNS: F4DetailColumn[] = [
  { prop: 'closingAje', label: '账项调整', group: 'audit', minWidth: 110, editable: true, inputType: 'number' },
  { prop: 'closingRje', label: '重分类调整', group: 'audit', minWidth: 120, editable: true, inputType: 'number' },
  { prop: 'closingAdjusted', label: '审定数', group: 'audit', minWidth: 115, formula: '期末未审+AJE+RJE', editable: false },
]

/**
 * 按项目账龄段动态生成「未审账龄 + 其他审计信息」列（取代固定 4 档）。
 * prop 形如 `agingCurrent.within1`（nested 权威字段）。
 */
export function buildF4AgingColumns(segments: readonly AgingSegment[]): F4DetailColumn[] {
  const agingCols: F4DetailColumn[] = (segments ?? []).map((seg) => ({
    prop: `agingCurrent.${seg.key}`,
    label: `未审账龄·${seg.label}`,
    group: 'unadjusted-aging',
    minWidth: 125,
    editable: true,
    inputType: 'number',
  }))
  return [...agingCols, ...F4_DETAIL_OTHER_COLUMNS]
}

/** 按项目账龄段动态生成「调整、审定及审定账龄」列 */
export function buildF4AuditColumns(segments: readonly AgingSegment[]): F4DetailColumn[] {
  const agingCols: F4DetailColumn[] = (segments ?? []).map((seg) => ({
    prop: `agingAudited.${seg.key}`,
    label: `审定账龄·${seg.label}`,
    group: 'audit',
    minWidth: 125,
    editable: true,
    inputType: 'number',
  }))
  return [...F4_DETAIL_ADJUST_COLUMNS, ...agingCols]
}

/** R:X 调整、审定及审定账龄（7列） */
export const F4_DETAIL_AUDIT_COLUMNS: F4DetailColumn[] = [
  { prop: 'closingAje', label: '账项调整', group: 'audit', minWidth: 110, editable: true, inputType: 'number' },
  { prop: 'closingRje', label: '重分类调整', group: 'audit', minWidth: 120, editable: true, inputType: 'number' },
  { prop: 'closingAdjusted', label: '审定数', group: 'audit', minWidth: 115, formula: '期末未审+AJE+RJE', editable: false },
  { prop: 'auditedAgingLt1', label: '审定账龄·1年以下', group: 'audit', minWidth: 125, editable: true, inputType: 'number' },
  { prop: 'auditedAging1to2', label: '审定账龄·1～2年', group: 'audit', minWidth: 125, editable: true, inputType: 'number' },
  { prop: 'auditedAging2to3', label: '审定账龄·2～3年', group: 'audit', minWidth: 125, editable: true, inputType: 'number' },
  { prop: 'auditedAgingGt3', label: '审定账龄·3年以上', group: 'audit', minWidth: 130, editable: true, inputType: 'number' },
]

/** 严格按 Excel A:AA 排列的27列。 */
export const F4_DETAIL_ALL_COLUMNS: F4DetailColumn[] = [
  ...F4_DETAIL_BASIC_COLUMNS,
  ...F4_DETAIL_AGING_COLUMNS.slice(0, 4),
  ...F4_DETAIL_AUDIT_COLUMNS,
  ...F4_DETAIL_AGING_COLUMNS.slice(4),
]

export interface StoredAPDetailRow {
  rowId: string
  seq: number
  creditor: string
  companyCode: string
  relatedPartyType: string
  paymentNature: string
  openingUnadjusted: number
  openingAje: number
  openingRje: number
  currentDebit: number
  currentCredit: number
  entityReclassification: number
  /** 期末未审账龄（nested keyed，权威） */
  agingCurrent: AgingData
  /** 期末审定账龄（nested keyed，权威） */
  agingAudited: AgingData
  closingAje: number
  closingRje: number
  isConfirmed: string
  subsequentPayment: number
  remark: string
  /** @deprecated 迁移前扁平账龄字段（只读兼容，序列化由 nested 派生） */
  unadjustedAgingLt1?: number
  unadjustedAging1to2?: number
  unadjustedAging2to3?: number
  unadjustedAgingGt3?: number
  auditedAgingLt1?: number
  auditedAging1to2?: number
  auditedAging2to3?: number
  auditedAgingGt3?: number
}

/** 迁移/计算的默认段（配置未加载时兜底，与 F4 默认预设 THREE_YEAR 一致） */
export const DEFAULT_F4_SEGMENTS = PRESET_SEGMENTS.THREE_YEAR as AgingSegment[]

export interface UseF4DetailOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

// ─── 工具函数 ─────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'F4-2-rows'

function generateRowId(): string {
  return `f4d-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function emptyStored(seq: number, segments: readonly AgingSegment[] = DEFAULT_F4_SEGMENTS): StoredAPDetailRow {
  return {
    rowId: generateRowId(),
    seq,
    creditor: '',
    companyCode: '',
    relatedPartyType: '',
    paymentNature: '',
    openingUnadjusted: 0,
    openingAje: 0,
    openingRje: 0,
    currentDebit: 0,
    currentCredit: 0,
    entityReclassification: 0,
    agingCurrent: createEmptyF4Aging(segments),
    agingAudited: createEmptyF4Aging(segments),
    closingAje: 0,
    closingRje: 0,
    isConfirmed: '',
    subsequentPayment: 0,
    remark: '',
  }
}

export function computeF4DetailRow(
  stored: StoredAPDetailRow,
  segmentsArg: readonly AgingSegment[] = DEFAULT_F4_SEGMENTS,
): APDetailRow {
  // 防御：允许 `rows.map(computeF4DetailRow)` 这类把 index 当第二参传入的旧调用方
  const segments: readonly AgingSegment[] = Array.isArray(segmentsArg) && segmentsArg.length
    ? segmentsArg
    : DEFAULT_F4_SEGMENTS
  const openingAdjusted = calcAuditedAmount(
    stored.openingUnadjusted,
    stored.openingAje,
    stored.openingRje,
  )
  // 源表 K 列以期初未审余额（E）为起点，而非期初审定余额（H）。
  const closingBalance = calcCreditBalance(
    stored.openingUnadjusted,
    stored.currentCredit,
    stored.currentDebit,
  )
  const closingUnadjusted = closingBalance + stored.entityReclassification
  const segKeys = (segments ?? DEFAULT_F4_SEGMENTS).map((s) => String(s.key))
  // 账龄合计按**生效段**求和（nested 优先，缺该段键回退 legacy 扁平字段）
  const unadjustedAgingTotal = sumRowAging(stored, 'current', segKeys)
  const closingAdjusted = calcAuditedAmount(
    closingUnadjusted,
    stored.closingAje,
    stored.closingRje,
  )
  const auditedAgingTotal = sumRowAging(stored, 'audited', segKeys)
  // nested 权威值（补齐生效段，缺段回退 legacy 扁平）
  const agingCurrent: AgingData = {}
  const agingAudited: AgingData = {}
  for (const key of segKeys) {
    agingCurrent[key] = f4AgingValue(stored, 'current', key)
    agingAudited[key] = f4AgingValue(stored, 'audited', key)
  }
  const flatCurrent = projectLegacyFlatAging({ agingCurrent }, 'current', segments ?? DEFAULT_F4_SEGMENTS)
  const flatAudited = projectLegacyFlatAging({ agingAudited }, 'audited', segments ?? DEFAULT_F4_SEGMENTS)
  return {
    ...stored,
    // 扁平字段为兼容派生（只读），nested 为权威
    ...flatCurrent,
    ...flatAudited,
    agingCurrent,
    agingAudited,
    openingAdjusted,
    closingBalance,
    closingUnadjusted,
    unadjustedAgingTotal,
    closingAdjusted,
    auditedAgingTotal,
    unadjustedAgingMismatch: !calcAgingCrossCheck(unadjustedAgingTotal, closingUnadjusted),
    auditedAgingMismatch: !calcAgingCrossCheck(auditedAgingTotal, closingAdjusted),
    subsequentPaymentExceedsBalance:
      stored.subsequentPayment - Math.abs(closingAdjusted) >= 0.01,
  }
}

function joinLegacyRemark(raw: any): string {
  const parts = [String(raw?.remark ?? '').trim()]
  if (raw?.confirmationResult) parts.push(`函证结果：${raw.confirmationResult}`)
  if (raw?.subsequentPaymentDate) parts.push(`期后付款日期：${raw.subsequentPaymentDate}`)
  if (raw?.indexRef) parts.push(`原索引：${raw.indexRef}`)
  return parts.filter(Boolean).join('；')
}

export function migrateF4DetailRows(
  jsonStr: string | null | undefined,
  segments: readonly AgingSegment[] = DEFAULT_F4_SEGMENTS,
): StoredAPDetailRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    const segs = (segments?.length ? segments : DEFAULT_F4_SEGMENTS) as AgingSegment[]
    return parsed.map((rawIn: any, i: number) => {
      // 扁平 → nested（nested 优先）→ 对齐当前项目账龄段
      const raw = remapRowAgingData(migrateF4FlatToNested(rawIn), segs, false) as any
      return {
        ...emptyStored(i + 1, segs),
        rowId: raw.rowId || raw.id || generateRowId(),
        seq: raw.seq ?? i + 1,
        creditor: raw.creditor || '',
        companyCode: raw.companyCode || '',
        relatedPartyType: raw.relatedPartyType || '',
        paymentNature: raw.paymentNature || '',
        openingUnadjusted: parseNum(raw.openingUnadjusted ?? raw.openingAdjusted),
        openingAje: parseNum(raw.openingAje),
        openingRje: parseNum(raw.openingRje),
        currentDebit: parseNum(raw.currentDebit ?? raw.debit),
        currentCredit: parseNum(raw.currentCredit ?? raw.credit),
        entityReclassification: parseNum(raw.entityReclassification),
        // 账龄权威 = nested（迁移函数已完成扁平/别名 → nested 与段对齐）
        agingCurrent: (raw.agingCurrent ?? createEmptyF4Aging(segs)) as AgingData,
        agingAudited: (raw.agingAudited ?? createEmptyF4Aging(segs)) as AgingData,
        closingAje: parseNum(raw.closingAje ?? raw.ajeAdjustment ?? raw.aje),
        closingRje: parseNum(raw.closingRje ?? raw.rjeReclassification ?? raw.rje),
        isConfirmed: raw.isConfirmed || '',
        subsequentPayment: parseNum(raw.subsequentPayment),
        remark: joinLegacyRemark(raw),
      }
    })
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useF4Detail(options: UseF4DetailOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const activeSegment = ref<'basic' | 'aging' | 'audit'>('basic')
  const storedData = ref<StoredAPDetailRow[]>([])
  const searchQuery = ref('')

  // ─── 账龄段（单一真源：主入口 provide 优先，其次自行加载配置，最后 F4 默认预设） ──
  const injectedSegments = inject<Ref<AgingSegment[]> | null>('f4AgingSegments', null)
  const injectedPreset = inject<Ref<string> | null>('f4AgingPreset', null)
  const ownConfig = injectedSegments ? null : useAgingConfig(options.projectId, 'F4')
  /** 生效段（未加载/为空时回退 F4 默认预设，避免"先 4 档后跳变"，Property 13） */
  const segments: ComputedRef<AgingSegment[]> = computed(() => {
    const raw = injectedSegments?.value ?? ownConfig?.segments.value ?? []
    return raw.length ? raw : DEFAULT_F4_SEGMENTS
  })
  const agingPreset = computed(() => injectedPreset?.value ?? ownConfig?.preset.value ?? 'THREE_YEAR')
  const segKeys = computed(() => segments.value.map((seg) => String(seg.key)))

  /** 按生效段动态生成的账龄列（取代固定 4 档） */
  const agingColumns = computed<F4DetailColumn[]>(() => buildF4AgingColumns(segments.value))
  const auditColumns = computed<F4DetailColumn[]>(() => buildF4AuditColumns(segments.value))
  const allColumns = computed<F4DetailColumn[]>(() => {
    const aging = agingColumns.value
    const agingOnly = aging.slice(0, segments.value.length)
    const others = aging.slice(segments.value.length)
    return [...F4_DETAIL_BASIC_COLUMNS, ...agingOnly, ...auditColumns.value, ...others]
  })

  // ─── 加载 ─────────────────────────────────────────────────────────────────

  function loadRows(): void {
    storedData.value = migrateF4DetailRows(
      readRowJson(allResponses.value.get(STORAGE_KEY)),
      segments.value,
    )
    if (storedData.value.length === 0) storedData.value = [emptyStored(1, segments.value)]
  }

  watch(() => readRowJson(allResponses.value.get(STORAGE_KEY)), () => {
    if (storedData.value.length === 0) loadRows()
  }, { immediate: true })

  // 账龄段变化：已有段保金额 / 新段补 0 / 废弃段丢弃（Property 3）
  watch(segKeys, (next, prev) => {
    if (!prev || next.join('|') === prev.join('|')) return
    if (storedData.value.length === 0) return
    storedData.value = storedData.value.map(
      (row) => remapRowAgingData(row, segments.value, false) as StoredAPDetailRow,
    )
    if (!readonly.value) persistRows()
  })

  // ─── 计算行 ───────────────────────────────────────────────────────────────

  const rows: ComputedRef<APDetailRow[]> = computed(() =>
    storedData.value.map((row) => computeF4DetailRow(row, segments.value)),
  )

  const filteredRows: ComputedRef<APDetailRow[]> = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return rows.value
    return rows.value.filter(
      (r) =>
        r.creditor.toLowerCase().includes(q) ||
        r.companyCode.toLowerCase().includes(q) ||
        r.paymentNature.toLowerCase().includes(q) ||
        r.relatedPartyType.toLowerCase().includes(q),
    )
  })

  // ─── 合计行 ───────────────────────────────────────────────────────────────

  const subtotalRow: ComputedRef<APDetailRow> = computed(() =>
    computeF4DetailRow({
      ...emptyStored(0, segments.value),
      rowId: 'subtotal',
      creditor: '合计',
      openingUnadjusted: calcSubtotal(rows.value.map((r) => r.openingUnadjusted)),
      openingAje: calcSubtotal(rows.value.map((r) => r.openingAje)),
      openingRje: calcSubtotal(rows.value.map((r) => r.openingRje)),
      currentDebit: calcSubtotal(rows.value.map((r) => r.currentDebit)),
      currentCredit: calcSubtotal(rows.value.map((r) => r.currentCredit)),
      entityReclassification: calcSubtotal(rows.value.map((r) => r.entityReclassification)),
      // 账龄合计按生效段聚合（Property 1）
      agingCurrent: aggregateAgingBySegments(rows.value, 'current', segKeys.value),
      agingAudited: aggregateAgingBySegments(rows.value, 'audited', segKeys.value),
      closingAje: calcSubtotal(rows.value.map((r) => r.closingAje)),
      closingRje: calcSubtotal(rows.value.map((r) => r.closingRje)),
      subsequentPayment: calcSubtotal(rows.value.map((r) => r.subsequentPayment)),
    }, segments.value),
  )

  const filledCount = computed(() => rows.value.filter((row) =>
    row.creditor.trim()
    || Math.abs(row.openingUnadjusted) >= 0.01
    || Math.abs(row.closingUnadjusted) >= 0.01,
  ).length)
  const abnormalCount = computed(() => rows.value.filter((row) =>
    row.unadjustedAgingMismatch
    || row.auditedAgingMismatch
    || row.subsequentPaymentExceedsBalance,
  ).length)

  // ─── 动态行操作 ───────────────────────────────────────────────────────────

  function addRow(): void {
    if (readonly.value) return
    storedData.value.push(emptyStored(storedData.value.length + 1, segments.value))
    persistRows()
  }

  function removeRow(rowId: string): void {
    if (readonly.value || storedData.value.length <= 1) return
    const idx = storedData.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    storedData.value.splice(idx, 1)
    storedData.value.forEach((r, i) => { r.seq = i + 1 })
    persistRows()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (readonly.value) return
    const row = storedData.value.find((r) => r.rowId === rowId)
    if (!row) return
    // nested 账龄字段（prop 形如 `agingCurrent.within1`）
    if (field.startsWith('agingCurrent.') || field.startsWith('agingAudited.')) {
      const [group, segKey] = field.split('.')
      const target = (row as any)[group] ?? {}
      target[segKey] = parseNum(value)
      ;(row as any)[group] = target
      persistRows()
      return
    }
    const strFields = [
      'creditor', 'companyCode', 'relatedPartyType', 'paymentNature',
      'isConfirmed', 'remark',
    ]
    if (strFields.includes(field)) (row as any)[field] = String(value ?? '')
    else (row as any)[field] = parseNum(value)
    persistRows()
  }

  /** 直接设置某期间某段账龄金额 */
  function updateAging(
    rowId: string,
    period: F4AgingPeriod,
    segKey: string,
    value: unknown,
  ): void {
    updateCell(rowId, `${F4_AGING_FIELD[period]}.${segKey}`, value)
  }

  /**
   * 把期末未审余额（或审定数）一键分配到指定账龄段：其余段清零。
   * `segKeyOrBucket` 兼容历史 bucket 值（lt1/1to2/2to3/gt3）。
   */
  function allocateAging(
    rowId: string,
    stage: 'unadjusted' | 'audited',
    segKeyOrBucket: string,
  ): void {
    if (readonly.value) return
    const row = storedData.value.find((item) => item.rowId === rowId)
    if (!row) return
    const period: F4AgingPeriod = stage === 'unadjusted' ? 'current' : 'audited'
    const field = F4_AGING_FIELD[period]
    const segKey = LEGACY_BUCKET_TO_SEG[segKeyOrBucket] ?? segKeyOrBucket
    if (!segKeys.value.includes(segKey)) return
    const next: AgingData = {}
    for (const key of segKeys.value) next[key] = 0
    ;(row as any)[field] = next
    const computedRow = computeF4DetailRow(row, segments.value)
    next[segKey] = period === 'current' ? computedRow.closingUnadjusted : computedRow.closingAdjusted
    persistRows()
  }

  // ─── 期后付款一键取数（从次年序时账 2202 借方按供应商归集） ──────────────

  async function importPostPaymentFromLedger(
    bsDate?: string,
    monthsAfter = 6,
  ): Promise<{ matched: number; filledAmount: number; unmatchedCount: number; unmatchedAmount: number }> {
    const empty = { matched: 0, filledAmount: 0, unmatchedCount: 0, unmatchedAmount: 0 }
    if (readonly.value) return empty
    if (storedData.value.length === 0) {
      ElMessage.info('请先录入或导入明细供应商后再取期后付款')
      return empty
    }
    const pid = options.projectId.value
    if (!pid) {
      ElMessage.warning('缺少项目信息，无法取数')
      return empty
    }

    const bs = (bsDate || '').trim()
    if (!/^\d{4}-\d{2}-\d{2}$/.test(bs)) {
      ElMessage.warning('资产负债表日无效，无法确定期后付款窗口')
      return empty
    }
    const start = new Date(`${bs}T00:00:00`)
    start.setDate(start.getDate() + 1)
    const end = new Date(start)
    end.setMonth(end.getMonth() + monthsAfter)
    const fmt = (d: Date) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
    const dateFrom = fmt(start)
    const dateTo = fmt(end)
    const postYear = start.getFullYear()

    try {
      const token = sessionStorage.getItem('token') || ''
      const authHeaders = { Authorization: `Bearer ${token}` }
      // 2202借方发生=付款(减少应付)
      const url = `/api/projects/${pid}/ledger/entries/2202?year=${postYear}`
        + `&date_from=${encodeURIComponent(dateFrom)}&date_to=${encodeURIComponent(dateTo)}&limit=2000`
      const resp = await fetch(url, { headers: authHeaders })
      if (!resp.ok) {
        ElMessage.info(`期后（${postYear}年）序时账无数据或未导入`)
        return empty
      }
      const result = await resp.json()
      const payload = result?.data ?? result
      const items: any[] = Array.isArray(payload)
        ? payload
        : Array.isArray(payload?.items)
          ? payload.items
          : Array.isArray(payload?.ledger?.items)
            ? payload.ledger.items
            : []

      if (items.length === 0) {
        ElMessage.info(`期后（${dateFrom} 至 ${dateTo}）无 2202 付款分录`)
        return empty
      }

      // 借方发生额 = 付款；按供应商名归集
      const normalizeName = (s: string) => s.replace(/\s+/g, '').toLowerCase()
      const rowSums = new Map<string, number>()
      let unmatchedCount = 0
      let unmatchedAmount = 0

      for (const it of items) {
        const debit = Number(it.debit_amount) || 0
        if (debit <= 0) continue
        const text = normalizeName(`${it.summary ?? ''} ${it.counterpart_account ?? ''} ${it.aux_name ?? ''}`)
        let hit: StoredAPDetailRow | null = null
        for (const row of storedData.value) {
          const name = normalizeName(row.creditor)
          if (name.length >= 2 && text.includes(name)) {
            hit = row
            break
          }
        }
        if (hit) {
          rowSums.set(hit.rowId, (rowSums.get(hit.rowId) || 0) + debit)
        } else {
          unmatchedCount++
          unmatchedAmount += debit
        }
      }

      const matched = rowSums.size
      const filledAmount = Array.from(rowSums.values()).reduce((s, v) => s + v, 0)

      // 回填(仅填空值)
      for (const [rowId, amount] of rowSums) {
        const row = storedData.value.find((r) => r.rowId === rowId)
        if (row && row.subsequentPayment === 0) {
          row.subsequentPayment = Math.round(amount * 100) / 100
        }
      }

      if (matched > 0) persistRows()
      return { matched, filledAmount: Math.round(filledAmount * 100) / 100, unmatchedCount, unmatchedAmount: Math.round(unmatchedAmount * 100) / 100 }
    } catch {
      ElMessage.warning('期后付款取数失败')
      return empty
    }
  }

  // ─── 持久化 ───────────────────────────────────────────────────────────────

  function persistRows(): void {
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      // 同时存入公式快照，保证导出和F4-1联动无需重复猜测公式。
      remark: JSON.stringify(storedData.value.map((row) => computeF4DetailRow(row, segments.value))),
    })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function flushSave(): void {
    const item = allResponses.value.get(STORAGE_KEY)
    if (item) window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items: [item] } }))
  }

  // ─── 样式 ─────────────────────────────────────────────────────────────────

  function rowClassName({ row }: { row: APDetailRow }): string {
    return row.unadjustedAgingMismatch || row.auditedAgingMismatch
      ? 'aging-mismatch-row'
      : row.subsequentPaymentExceedsBalance
        ? 'subsequent-warning-row'
        : ''
  }

  // ─── 清理 ─────────────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; flushSave() }
  })

  return {
    activeSegment,
    rows,
    filteredRows,
    subtotalRow,
    filledCount,
    abnormalCount,
    searchQuery,
    loadRows,
    addRow,
    removeRow,
    updateCell,
    updateAging,
    allocateAging,
    importPostPaymentFromLedger,
    rowClassName,
    // 账龄段（单一真源）
    segments,
    segKeys,
    agingPreset,
    basicColumns: F4_DETAIL_BASIC_COLUMNS,
    agingColumns,
    auditColumns,
    allColumns,
  }
}

export default useF4Detail
