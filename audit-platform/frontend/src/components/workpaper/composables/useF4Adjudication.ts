/**
 * useF4Adjudication — F4-1 应付账款审定表
 *
 * 对齐源工作簿：
 * 1. 按性质（货款、工程款、设备款、服务费、其他）；
 * 2. 按账龄（1年以内、1至2年、2至3年、3年以上、其他/未分类）；
 * 3. 每种口径均为“期初未审+AJE+RJE=期初审定；期末未审+AJE+RJE=期末审定”；
 * 4. 比较本期与上期审定数，自动计算变动额、变动率并分析重大变动；
 * 5. 期末数按源表逻辑从 F4-2 明细表汇总，期初/期末分别与试算平衡表勾稽。
 */
import { computed, inject, onBeforeUnmount, ref, watch, type ComputedRef, type Ref } from 'vue'
import { calcAdjustedAmount, calcCreditBalance, calcSubtotal, parseNum } from './useF4AccPayFormulaEngine'
import type { ChecklistResponse } from './useF4FormData'
import { eventBus } from '@/utils/eventBus'
import {
  PRESET_SEGMENTS,
  useAgingConfig,
  DEFAULT_SUBJECT_PRESETS,
  type AgingSegment,
} from '@/composables/useAgingConfig'
import {
  F4_RESIDUAL_ROW_KEY,
  F4_RESIDUAL_ROW_LABEL,
  f4AgingRowKey,
  f4AgingValue,
} from './f4AgingModel'

export type F4AdjudicationSection = 'nature' | 'aging'

export interface UseF4AdjudicationOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
  /** 后端 render 输出的 2202 应付账款 TB 核对标量（trial_balance 期末，取绝对值）。
   *  无持久化时作「试算平衡表数·期末」只读回退 seed（trial_balance v2 无期初，故不 seed 期初）。 */
  tbAmountSeed?: Ref<number | null | undefined>
}

export interface StoredF4AdjRow {
  rowKey: string
  label: string
  isFixed: boolean
  openingUnadjusted: number
  openingAje: number
  openingRje: number
  closingUnadjusted: number
  closingAje: number
  closingRje: number
  reasonAnalysis: string
}

export interface F4AdjudicationRow extends StoredF4AdjRow {
  openingAdjusted: number
  closingAdjusted: number
  changeAmount: number
  changeRate: number
  isEditable: boolean
  closingFromDetail: boolean
}

export interface F4DetailAggregation {
  hasData: boolean
  nature: Record<string, Pick<StoredF4AdjRow, 'closingUnadjusted' | 'closingAje' | 'closingRje'>>
  aging: Record<string, Pick<StoredF4AdjRow, 'closingUnadjusted' | 'closingAje' | 'closingRje'>>
  openingAdjusted: number
  closingAdjusted: number
}

export interface F4TrialBalance {
  opening: number
  closing: number
}

export const F4_NATURE_DEFAULTS: StoredF4AdjRow[] = [
  createStoredRow('goods', '货款'),
  createStoredRow('construction', '工程款'),
  createStoredRow('equipment', '设备款'),
  createStoredRow('service', '服务费'),
  createStoredRow('other', '其他'),
]

/**
 * 3 年段（迁移前固定 4 档 + 残差行）默认行，作为账龄配置未加载时的回退常量。
 * 段驱动请用 `buildF4AgingDefaults(segments)`。
 */
export const F4_AGING_DEFAULTS: StoredF4AdjRow[] = [
  createStoredRow('within1year', '1年以内（含1年）'),
  createStoredRow('1to2year', '1至2年（含2年）'),
  createStoredRow('2to3year', '2至3年（含3年）'),
  createStoredRow('3yearplus', '3年以上'),
  createStoredRow(F4_RESIDUAL_ROW_KEY, F4_RESIDUAL_ROW_LABEL),
]

/**
 * 段 key/rowKey → F4 底稿账龄行名。
 *
 * 前 4 项为 3 年段迁移前 label（零回归文案，逐字取自源 xlsx `审定表F4-1` 二、按照账龄分类）。
 * 后 3 项为 5 年段按源模板同一「X至Y年（含Y年）」构词的延伸——不加会退回账龄配置的
 * `seg.label`（「3-4年」半角连字符），与前 4 档用词分裂（实测 5 年段项目已出现）。
 * 附注侧另有一套不带括注的用词，见 `f4NoteSectionMap.F4_NOTE_AGING_LABEL`。
 */
const LEGACY_AGING_LABEL: Record<string, string> = {
  within1year: '1年以内（含1年）',
  '1to2year': '1至2年（含2年）',
  '2to3year': '2至3年（含3年）',
  '3yearplus': '3年以上',
  y3to4: '3至4年（含4年）',
  y4to5: '4至5年（含5年）',
  over5: '5年以上',
}

/**
 * 按账龄段生成 F4-1「按账龄」区块默认行：
 * rowKey 走 `LEGACY_AGING_ROWKEY`（3 年段沿用既有存储键，零数据迁移），末尾恒为残差行。
 */
export function buildF4AgingDefaults(segments: readonly AgingSegment[]): StoredF4AdjRow[] {
  const segs = segments?.length ? segments : (PRESET_SEGMENTS.THREE_YEAR as AgingSegment[])
  const rows = segs.map((seg) => {
    const rowKey = f4AgingRowKey(String(seg.key))
    return createStoredRow(rowKey, LEGACY_AGING_LABEL[rowKey] ?? seg.label)
  })
  rows.push(createStoredRow(F4_RESIDUAL_ROW_KEY, F4_RESIDUAL_ROW_LABEL))
  return rows
}

const NATURE_STORAGE_KEY = 'F4-1-adj-nature-rows'
const AGING_STORAGE_KEY = 'F4-1-adj-aging-rows'
const TB_STORAGE_KEY = 'F4-1-adj-tb-2202'
const NOTE_STORAGE_KEY = 'F4-1-adj-note'
const CONCLUSION_STORAGE_KEY = 'F4-1-adj-conclusion'
const DETAIL_STORAGE_KEY = 'F4-2-rows'
const BALANCE_TOLERANCE = 0.005

function createStoredRow(rowKey: string, label: string): StoredF4AdjRow {
  return {
    rowKey,
    label,
    isFixed: true,
    openingUnadjusted: 0,
    openingAje: 0,
    openingRje: 0,
    closingUnadjusted: 0,
    closingAje: 0,
    closingRje: 0,
    reasonAnalysis: '',
  }
}

export function calcF4ChangeRate(openingAdjusted: number, changeAmount: number): number {
  if (Math.abs(openingAdjusted) < BALANCE_TOLERANCE) {
    if (Math.abs(changeAmount) < BALANCE_TOLERANCE) return 0
    return changeAmount > 0 ? 1 : -1
  }
  return changeAmount / openingAdjusted
}

export function computeF4AdjudicationRow(
  stored: StoredF4AdjRow,
  detail?: Pick<StoredF4AdjRow, 'closingUnadjusted' | 'closingAje' | 'closingRje'>,
): F4AdjudicationRow {
  const closing = detail ?? stored
  const openingAdjusted = calcAdjustedAmount(
    stored.openingUnadjusted,
    stored.openingAje,
    stored.openingRje,
  )
  const closingAdjusted = calcAdjustedAmount(
    closing.closingUnadjusted,
    closing.closingAje,
    closing.closingRje,
  )
  const changeAmount = closingAdjusted - openingAdjusted
  return {
    ...stored,
    closingUnadjusted: closing.closingUnadjusted,
    closingAje: closing.closingAje,
    closingRje: closing.closingRje,
    openingAdjusted,
    closingAdjusted,
    changeAmount,
    changeRate: calcF4ChangeRate(openingAdjusted, changeAmount),
    isEditable: true,
    closingFromDetail: !!detail,
  }
}

function subtotal(rows: F4AdjudicationRow[], rowKey: string): F4AdjudicationRow {
  const row = computeF4AdjudicationRow({
    rowKey,
    label: '合计',
    isFixed: true,
    openingUnadjusted: calcSubtotal(rows.map((item) => item.openingUnadjusted)),
    openingAje: calcSubtotal(rows.map((item) => item.openingAje)),
    openingRje: calcSubtotal(rows.map((item) => item.openingRje)),
    closingUnadjusted: calcSubtotal(rows.map((item) => item.closingUnadjusted)),
    closingAje: calcSubtotal(rows.map((item) => item.closingAje)),
    closingRje: calcSubtotal(rows.map((item) => item.closingRje)),
    reasonAnalysis: '',
  })
  row.isEditable = false
  row.closingFromDetail = rows.some((item) => item.closingFromDetail)
  return row
}

function safeJsonArray(value: string | null | undefined): any[] {
  if (!value) return []
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function migrateF4AdjRows(
  value: string | null | undefined,
  defaults: StoredF4AdjRow[],
): StoredF4AdjRow[] {
  const parsed = safeJsonArray(value)
  const aliases: Record<string, string> = {
    services: 'service',
    within1: 'within1year',
    '1to2': '1to2year',
    '2to3': '2to3year',
    '3plus': '3yearplus',
  }
  const migrated = parsed.map((raw: any, index) => {
    const key = aliases[String(raw?.rowKey ?? '')] ?? String(raw?.rowKey ?? defaults[index]?.rowKey ?? `custom-${index}`)
    const openingUnadjusted = parseNum(raw?.openingUnadjusted)
    const openingAje = parseNum(raw?.openingAje)
    const openingRje = parseNum(raw?.openingRje)
    const openingAdjusted = calcAdjustedAmount(openingUnadjusted, openingAje, openingRje)
    // 旧模型没有期末直接输入列，以“期初审定+贷方-借方”迁移，确保历史数据不丢失。
    const legacyClosing = calcCreditBalance(
      openingAdjusted,
      parseNum(raw?.periodCredit),
      parseNum(raw?.periodDebit),
    )
    return {
      rowKey: key,
      label: String(raw?.label ?? defaults[index]?.label ?? ''),
      isFixed: raw?.isFixed !== false,
      openingUnadjusted,
      openingAje,
      openingRje,
      closingUnadjusted: raw?.closingUnadjusted == null
        ? legacyClosing
        : parseNum(raw.closingUnadjusted),
      closingAje: parseNum(raw?.closingAje),
      closingRje: parseNum(raw?.closingRje),
      reasonAnalysis: String(raw?.reasonAnalysis ?? raw?.reason ?? ''),
    }
  })

  const byKey = new Map(migrated.map((row) => [row.rowKey, row]))
  return defaults.map((item) => ({ ...item, ...(byKey.get(item.rowKey) ?? {}) }))
}

function classifyNature(value: unknown): string {
  const text = String(value ?? '').trim()
  if (text.includes('工程')) return 'construction'
  if (text.includes('设备')) return 'equipment'
  if (text.includes('服务') || text.includes('劳务')) return 'service'
  if (text.includes('货') || text.includes('材料') || text.includes('采购')) return 'goods'
  return 'other'
}

function emptyAggregate(keys: string[]): F4DetailAggregation['nature'] {
  return Object.fromEntries(keys.map((key) => [
    key,
    { closingUnadjusted: 0, closingAje: 0, closingRje: 0 },
  ]))
}

function addAggregate(
  target: Pick<StoredF4AdjRow, 'closingUnadjusted' | 'closingAje' | 'closingRje'>,
  closingUnadjusted: number,
  closingAje: number,
  closingRje: number,
): void {
  target.closingUnadjusted += closingUnadjusted
  target.closingAje += closingAje
  target.closingRje += closingRje
}

/**
 * 模拟源表 SUMIF / 明细表链接：
 * - 按性质：由 F4-2 款项性质汇总期末未审、AJE、RJE；
 * - 按账龄：未审账龄取 F4-2 四段账龄，审定账龄取四段审定账龄，
 *   AJE = 审定账龄 - 未审账龄 - RJE（与源表 G=I-F-H 一致）。
 */
export function aggregateF4Detail(
  value: string | null | undefined,
  segments?: readonly AgingSegment[],
): F4DetailAggregation {
  const segs = (segments?.length ? segments : PRESET_SEGMENTS.THREE_YEAR) as AgingSegment[]
  const rows = safeJsonArray(value)
  const meaningful = rows.filter((raw) =>
    String(raw?.creditor ?? '').trim()
    || parseNum(raw?.openingUnadjusted ?? raw?.openingAdjusted)
    || parseNum(raw?.currentDebit ?? raw?.debit)
    || parseNum(raw?.currentCredit ?? raw?.credit)
    || parseNum(raw?.closingUnadjusted ?? raw?.closingBalance)
    || parseNum(raw?.closingAdjusted ?? raw?.adjustedBalance ?? raw?.auditedBalance),
  )
  const nature = emptyAggregate(F4_NATURE_DEFAULTS.map((row) => row.rowKey))
  const segKeys = segs.map((seg) => String(seg.key))
  const agingRowKeys = segKeys.map(f4AgingRowKey)
  const aging = emptyAggregate([...agingRowKeys, F4_RESIDUAL_ROW_KEY])
  let openingAdjusted = 0
  let closingAdjusted = 0

  for (const raw of meaningful) {
    const openingUnadjusted = parseNum(raw?.openingUnadjusted ?? raw?.openingAdjusted)
    const opening = raw?.openingAdjusted == null
      ? calcAdjustedAmount(
        openingUnadjusted,
        parseNum(raw?.openingAje),
        parseNum(raw?.openingRje),
      )
      : parseNum(raw.openingAdjusted)
    const debit = parseNum(raw?.currentDebit ?? raw?.debit)
    const credit = parseNum(raw?.currentCredit ?? raw?.credit)
    const ledgerClosing = raw?.closingBalance == null
      ? calcCreditBalance(openingUnadjusted, credit, debit)
      : parseNum(raw.closingBalance)
    const closing = raw?.closingUnadjusted == null
      ? ledgerClosing + parseNum(raw?.entityReclassification)
      : parseNum(raw.closingUnadjusted)
    const aje = parseNum(raw?.closingAje ?? raw?.ajeAdjustment ?? raw?.aje)
    const rje = parseNum(raw?.closingRje ?? raw?.rjeReclassification ?? raw?.rje)
    const audited = raw?.closingAdjusted == null
      && raw?.adjustedBalance == null
      && raw?.auditedBalance == null
      ? calcAdjustedAmount(closing, aje, rje)
      : parseNum(raw?.closingAdjusted ?? raw?.adjustedBalance ?? raw?.auditedBalance)

    openingAdjusted += opening
    closingAdjusted += audited
    addAggregate(nature[classifyNature(raw?.paymentNature ?? raw?.nature)], closing, aje, rje)

    // 账龄按生效段读取：nested 优先，缺该段键回退迁移前扁平字段/更早别名
    const legacyRaw = {
      ...raw,
      unadjustedAgingLt1: raw?.unadjustedAgingLt1 ?? raw?.aging1Year ?? raw?.agingLt1,
      unadjustedAging1to2: raw?.unadjustedAging1to2 ?? raw?.aging1to2Year ?? raw?.aging1to2,
      unadjustedAging2to3: raw?.unadjustedAging2to3 ?? raw?.aging2to3Year ?? raw?.aging2to3,
      unadjustedAgingGt3: raw?.unadjustedAgingGt3 ?? raw?.aging3YearPlus ?? raw?.agingGt3,
      auditedAgingLt1: raw?.auditedAgingLt1 ?? raw?.adjustedAging1,
      auditedAging1to2: raw?.auditedAging1to2 ?? raw?.adjustedAging2,
      auditedAging2to3: raw?.auditedAging2to3 ?? raw?.adjustedAging3,
      auditedAgingGt3: raw?.auditedAgingGt3 ?? raw?.adjustedAging4,
    }
    const unadjustedBuckets = segKeys.map((key) => f4AgingValue(legacyRaw, 'current', key))
    const auditedBuckets = segKeys.map((key) => f4AgingValue(legacyRaw, 'audited', key))
    const bucketKeys = agingRowKeys
    const unadjustedTotal = calcSubtotal(unadjustedBuckets)
    const auditedTotal = calcSubtotal(auditedBuckets)
    const hasAuditedBuckets = auditedBuckets.some((amount) => Math.abs(amount) >= BALANCE_TOLERANCE)
    const rowRjeTotal = rje

    bucketKeys.forEach((key, index) => {
      const unadjusted = unadjustedBuckets[index]
      const auditedBucket = hasAuditedBuckets ? auditedBuckets[index] : unadjusted
      // 明细表未提供按账龄拆分的 RJE，保守地将其归入“其他/未分类”，避免臆测分配。
      addAggregate(aging[key], unadjusted, auditedBucket - unadjusted, 0)
    })
    const closingResidual = closing - unadjustedTotal
    const auditedResidual = audited - (hasAuditedBuckets ? auditedTotal : unadjustedTotal)
    addAggregate(
      aging[F4_RESIDUAL_ROW_KEY],
      closingResidual,
      auditedResidual - closingResidual - rowRjeTotal,
      rowRjeTotal,
    )
  }

  return {
    hasData: meaningful.length > 0,
    nature,
    aging,
    openingAdjusted,
    closingAdjusted,
  }
}

export function parseF4TrialBalance(value: string | null | undefined): F4TrialBalance {
  if (!value) return { opening: 0, closing: 0 }
  try {
    const parsed = JSON.parse(value)
    if (parsed && typeof parsed === 'object') {
      return {
        opening: parseNum(parsed.opening),
        closing: parseNum(parsed.closing),
      }
    }
  } catch {
    // 兼容旧存储：单个数字代表期末试算表数。
  }
  return { opening: 0, closing: parseNum(value) }
}

export function useF4Adjudication(options: UseF4AdjudicationOptions) {
  const { allResponses, isReadonly, projectId, tbAmountSeed } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const natureStored = ref<StoredF4AdjRow[]>([])
  const agingStored = ref<StoredF4AdjRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── 账龄段（主入口 provide 优先，其次自加载，最后 F4 默认预设） ────────────
  const injectedSegments = inject<Ref<AgingSegment[]> | null>('f4AgingSegments', null)
  const ownConfig = injectedSegments ? null : useAgingConfig(projectId, 'F4')
  const segments: ComputedRef<AgingSegment[]> = computed(() => {
    const raw = injectedSegments?.value ?? ownConfig?.segments.value ?? []
    return raw.length
      ? raw
      : (PRESET_SEGMENTS[DEFAULT_SUBJECT_PRESETS.F4 ?? 'THREE_YEAR'] as AgingSegment[])
  })
  const agingDefaults = computed(() => buildF4AgingDefaults(segments.value))

  function loadRows(): void {
    natureStored.value = migrateF4AdjRows(
      allResponses.value.get(NATURE_STORAGE_KEY)?.remark,
      F4_NATURE_DEFAULTS,
    )
    agingStored.value = migrateF4AdjRows(
      allResponses.value.get(AGING_STORAGE_KEY)?.remark,
      agingDefaults.value,
    )
  }

  watch(
    () => [
      allResponses.value.get(NATURE_STORAGE_KEY)?.remark,
      allResponses.value.get(AGING_STORAGE_KEY)?.remark,
    ],
    () => {
      if (!natureStored.value.length || !agingStored.value.length) loadRows()
    },
    { immediate: true },
  )

  // 账龄段变化：同 rowKey 保金额 / 新段补 0 / 废弃段丢弃，并持久化一次（Property 3）
  watch(
    () => agingDefaults.value.map((row) => row.rowKey).join('|'),
    (next, prev) => {
      if (!prev || next === prev) return
      if (!agingStored.value.length) return
      const byKey = new Map(agingStored.value.map((row) => [row.rowKey, row]))
      agingStored.value = agingDefaults.value.map((item) => ({
        ...item,
        ...(byKey.get(item.rowKey) ?? {}),
        label: item.label,
      }))
      if (!readonly.value) persistRows('aging')
    },
  )

  const detailAggregation = computed(() =>
    aggregateF4Detail(allResponses.value.get(DETAIL_STORAGE_KEY)?.remark, segments.value),
  )
  const natureDataRows: ComputedRef<F4AdjudicationRow[]> = computed(() =>
    natureStored.value.map((row) => computeF4AdjudicationRow(
      row,
      detailAggregation.value.hasData ? detailAggregation.value.nature[row.rowKey] : undefined,
    )),
  )
  const agingDataRows: ComputedRef<F4AdjudicationRow[]> = computed(() =>
    agingStored.value.map((row) => computeF4AdjudicationRow(
      row,
      detailAggregation.value.hasData ? detailAggregation.value.aging[row.rowKey] : undefined,
    )),
  )
  const natureSubtotalRow = computed(() => subtotal(natureDataRows.value, 'nature-subtotal'))
  const agingSubtotalRow = computed(() => subtotal(agingDataRows.value, 'aging-subtotal'))
  const totalRow = computed(() => ({ ...natureSubtotalRow.value, rowKey: 'total' }))

  const openingCrossCheckPassed = computed(() =>
    Math.abs(natureSubtotalRow.value.openingAdjusted - agingSubtotalRow.value.openingAdjusted)
      < BALANCE_TOLERANCE,
  )
  const closingCrossCheckPassed = computed(() =>
    Math.abs(natureSubtotalRow.value.closingAdjusted - agingSubtotalRow.value.closingAdjusted)
      < BALANCE_TOLERANCE,
  )
  const crossCheckPassed = computed(() =>
    openingCrossCheckPassed.value && closingCrossCheckPassed.value,
  )

  const trialBalance = computed(() => {
    // 手工优先：有持久化 F4-1-adj-tb-2202 用之；否则回退后端 render 的 2202 期末 TB 核对标量
    const remark = allResponses.value.get(TB_STORAGE_KEY)?.remark
    if (remark != null && String(remark).trim() !== '') {
      return parseF4TrialBalance(remark)
    }
    return { opening: 0, closing: parseNum(tbAmountSeed?.value ?? 0) }
  })
  const openingVariance = computed(() =>
    natureSubtotalRow.value.openingAdjusted - trialBalance.value.opening,
  )
  const closingVariance = computed(() =>
    natureSubtotalRow.value.closingAdjusted - trialBalance.value.closing,
  )
  // 兼容旧调用方：原 trialBalanceAmount/variance 均表示期末。
  const trialBalanceAmount = computed(() => trialBalance.value.closing)
  const variance = closingVariance

  const significantChanges = computed(() =>
    natureDataRows.value
      .filter((row) => Math.abs(row.changeRate) > 0.3)
      .map((row) => ({
        rowKey: row.rowKey,
        label: row.label,
        changeAmount: row.changeAmount,
        changeRate: row.changeRate,
        reasonAnalysis: row.reasonAnalysis,
      })),
  )

  watch(
    () => allResponses.value.get(NOTE_STORAGE_KEY)?.remark,
    (value) => { auditNote.value = value || '' },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get(CONCLUSION_STORAGE_KEY)?.remark,
    (value) => { auditConclusion.value = value || '' },
    { immediate: true },
  )

  function updateCell(
    section: F4AdjudicationSection,
    rowKey: string,
    field: keyof StoredF4AdjRow,
    value: unknown,
  ): void {
    if (readonly.value) return
    const target = section === 'nature' ? natureStored : agingStored
    const row = target.value.find((item) => item.rowKey === rowKey)
    if (!row) return
    if (field === 'reasonAnalysis' || field === 'label') {
      ;(row as any)[field] = String(value ?? '')
    } else if (!['rowKey', 'isFixed'].includes(field)) {
      ;(row as any)[field] = parseNum(value as string | number | null | undefined)
    }
    persistRows(section)
  }

  function persistRows(section: F4AdjudicationSection): void {
    const key = section === 'nature' ? NATURE_STORAGE_KEY : AGING_STORAGE_KEY
    const rows = section === 'nature' ? natureStored.value : agingStored.value
    allResponses.value.set(key, {
      item_id: key,
      conclusion: null,
      remark: JSON.stringify(rows),
    })
    debounceSave()
  }

  function updateTrialBalance(period: keyof F4TrialBalance, value: unknown): void {
    if (readonly.value) return
    const next = {
      ...trialBalance.value,
      [period]: parseNum(value as string | number | null | undefined),
    }
    allResponses.value.set(TB_STORAGE_KEY, {
      item_id: TB_STORAGE_KEY,
      conclusion: null,
      remark: JSON.stringify(next),
    })
    debounceSave()
  }

  function updateNatureCell(rowKey: string, field: string, value: unknown): void {
    updateCell('nature', rowKey, field as keyof StoredF4AdjRow, value)
  }

  function updateAgingCell(rowKey: string, field: string, value: unknown): void {
    updateCell('aging', rowKey, field as keyof StoredF4AdjRow, value)
  }

  function updateLegacyTrialBalance(value: unknown): void {
    updateTrialBalance('closing', value)
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 1500)
  }

  function flushSave(): void {
    const items = [
      allResponses.value.get(NATURE_STORAGE_KEY),
      allResponses.value.get(AGING_STORAGE_KEY),
      allResponses.value.get(TB_STORAGE_KEY),
      allResponses.value.get(NOTE_STORAGE_KEY),
      allResponses.value.get(CONCLUSION_STORAGE_KEY),
    ].filter(Boolean)
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items } }))
    }
  }

  function publishAdjudicated(): void {
    const auditedAmount = totalRow.value.closingAdjusted
    // 统一走 eventBus（crossWpEventBridge 带再入守卫转发到 window，旧 window 监听者不受影响）
    try {
      eventBus.emit('substantive:adjudicated', {
        wpCode: 'F4',
        accountCode: '2202',
        auditedAmount,
        adjudicatedAmount: auditedAmount,
        timestamp: Date.now(),
      } as any)
    } catch {
      console.warn('[useF4Adjudication] EventBus publish substantive:adjudicated failed')
    }
    if (projectId.value) {
      window.dispatchEvent(new CustomEvent('f4:writeback-trial-balance', {
        detail: { projectId: projectId.value, accountCode: '2202', auditedAmount },
      }))
    }
  }

  watch(auditNote, (value) => {
    allResponses.value.set(NOTE_STORAGE_KEY, {
      item_id: NOTE_STORAGE_KEY,
      conclusion: null,
      remark: value,
    })
    debounceSave()
  })
  watch(auditConclusion, (value) => {
    allResponses.value.set(CONCLUSION_STORAGE_KEY, {
      item_id: CONCLUSION_STORAGE_KEY,
      conclusion: null,
      remark: value,
    })
    debounceSave()
  })

  function serialize(): Record<string, string> {
    return {
      [NATURE_STORAGE_KEY]: JSON.stringify(natureStored.value),
      [AGING_STORAGE_KEY]: JSON.stringify(agingStored.value),
      [TB_STORAGE_KEY]: JSON.stringify(trialBalance.value),
      [NOTE_STORAGE_KEY]: auditNote.value,
      [CONCLUSION_STORAGE_KEY]: auditConclusion.value,
    }
  }

  function deserialize(data: Record<string, string>): void {
    for (const key of [NATURE_STORAGE_KEY, AGING_STORAGE_KEY, TB_STORAGE_KEY]) {
      if (data[key]) {
        allResponses.value.set(key, { item_id: key, conclusion: null, remark: data[key] })
      }
    }
    if (data[NOTE_STORAGE_KEY] != null) auditNote.value = data[NOTE_STORAGE_KEY]
    if (data[CONCLUSION_STORAGE_KEY] != null) auditConclusion.value = data[CONCLUSION_STORAGE_KEY]
    loadRows()
  }

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    segments,
    natureDataRows,
    natureSubtotalRow,
    agingDataRows,
    agingSubtotalRow,
    totalRow,
    detailAggregation,
    openingCrossCheckPassed,
    closingCrossCheckPassed,
    crossCheckPassed,
    trialBalance,
    trialBalanceAmount,
    openingVariance,
    closingVariance,
    variance,
    significantChanges,
    updateCell,
    updateNatureCell,
    updateAgingCell,
    updateTrialBalance,
    updateLegacyTrialBalance,
    auditNote,
    auditConclusion,
    publishAdjudicated,
    serialize,
    deserialize,
  }
}

export default useF4Adjudication
