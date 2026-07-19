/**
 * useG4MainInterestCalc — G4-4 利息测算表（实际利率法双section分组）
 *
 * Spec: .kiro/specs/g4-bond-investment-main/ Task 6.3
 * Requirements: 7.1~7.11
 *
 * 功能：
 * - InterestCalcGroup分组管理（每投资项目独立成组）
 * - (一)初始入账价值：initialCarryingAmount = purchasePrice + transactionCost
 * - (二)利息计算多行：amortizedCost/effectiveInterest/cashInflow/closingBalance
 * - Stage1/2/3条件：公式相同但Stage3减值更大→摊余成本基数更低
 * - 各项目实际利息收入合计 vs G4-1审定利息收入比对
 * - 差异>0.01元红色高亮
 *
 * 比照 useG2InterestCalc / useG4MainAdjustment
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  parseNum,
  calcInitialCarryingAmount,
  calcAmortizedCost,
  calcEffectiveInterest,
  calcCashInflow,
  calcEndingBalance,
} from '@/composables/useG4MainFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import {
  G4_ITEM_IDS,
  buildCanonicalPayload,
  parseCanonicalJson,
} from './g4StorageContract'
import {
  applyG44InterestToDetailRows,
  fetchCanonicalRowsFromWorkpaper,
  resolveG4MainWorkpaperId,
  saveCanonicalRowsToWorkpaper,
  type G4CrossApplyResult,
} from './g4CrossHelpers'
import {
  buildG44InterestVarianceDraft,
  dispatchG4ExceptionDrafts,
} from './g4ExceptionRouting'

// ═══ 数据模型 ═══

export interface InitialCarryingData {
  faceValueTotal: number        // 面值总额
  initialDate: string           // 初始计量日
  maturityDate: string          // 到期日
  purchasePrice: number         // 购买对价
  transactionCost: number       // 交易费用
  initialCarryingAmount: number // 公式: purchasePrice + transactionCost
  couponRate: number            // 票面利率(小数，至少4位)
  effectiveRate: number         // 实际利率(小数，至少4位)
}

export interface InterestPeriodRow {
  id: string
  cutoffDate: string            // 截止日
  openingBalance: number        // 期初账面总额
  openingImpairment: number     // 期初减值准备余额
  openingAmortizedCost: number  // 公式: 期初账面 - 减值准备
  effectiveInterest: number     // 公式: 摊余成本 × 实际利率 × days/365
  cashInflow: number            // 公式: 面值 × 票面利率 [× days/365]
  principalRepaid: number       // 已收回的本金
  closingBalance: number        // 公式: 期初 + 利息 - 现金流入 - 已收回本金
  days: number                  // 计息天数(1~366)
  stage: 'Stage1' | 'Stage2' | 'Stage3'  // 减值阶段(下拉)
}

export interface InterestCalcGroup {
  id: string
  projectName: string           // 投资项目名称
  initial: InitialCarryingData
  periods: InterestPeriodRow[]
}

export interface InterestCalcSummary {
  totalEffectiveInterest: number   // 各项目实际利息收入合计
  g4_1InterestAdjusted: number     // G4-1审定表利息收入审定数
  variance: number                 // 差异
  isVarianceAcceptable: boolean    // |差异| <= 0.01
}

// ═══ 常量 ═══

const STORAGE_KEY = G4_ITEM_IDS.G4_4_INTEREST
const IE_COMPAT_STORAGE_KEY = G4_ITEM_IDS.G4_4_ROWS
const INTEREST_BENCHMARK_KEY = G4_ITEM_IDS.G4_4_BENCHMARK
const VARIANCE_THRESHOLD = 0.01
const MAX_GROUPS = 50
const MAX_PERIODS_PER_GROUP = 36  // 最多36个计息期间(3年月度)

// ═══ 工具函数 ═══

function generateId(prefix = 'g4ic'): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function createEmptyInitial(): InitialCarryingData {
  return {
    faceValueTotal: 0,
    initialDate: '',
    maturityDate: '',
    purchasePrice: 0,
    transactionCost: 0,
    initialCarryingAmount: 0,
    couponRate: 0,
    effectiveRate: 0,
  }
}

function createEmptyPeriod(): InterestPeriodRow {
  return {
    id: generateId('period'),
    cutoffDate: '',
    openingBalance: 0,
    openingImpairment: 0,
    openingAmortizedCost: 0,
    effectiveInterest: 0,
    cashInflow: 0,
    principalRepaid: 0,
    closingBalance: 0,
    days: 365,
    stage: 'Stage1',
  }
}

function createEmptyGroup(projectName: string): InterestCalcGroup {
  return {
    id: generateId('group'),
    projectName,
    initial: createEmptyInitial(),
    periods: [createEmptyPeriod()],
  }
}

/** 对单行进行公式计算（返回新行，不修改原行） */
function computePeriodRow(
  row: InterestPeriodRow,
  initial: InitialCarryingData,
): InterestPeriodRow {
  // Stage1/2/3 公式完全相同，区别在于 openingImpairment 数值不同
  // Stage3 的减值准备通常更大，导致 amortizedCost 基数更低
  const openingAmortizedCost = calcAmortizedCost(
    parseNum(row.openingBalance),
    parseNum(row.openingImpairment),
  )

  const days = parseNum(row.days)
  const effectiveInterest = calcEffectiveInterest(
    openingAmortizedCost,
    parseNum(initial.effectiveRate),
    days,
  )

  const cashInflow = calcCashInflow(
    parseNum(initial.faceValueTotal),
    parseNum(initial.couponRate),
    days,
  )

  const closingBalance = calcEndingBalance(
    parseNum(row.openingBalance),
    effectiveInterest,
    cashInflow,
    parseNum(row.principalRepaid),
  )

  return {
    ...row,
    openingAmortizedCost: Math.round(openingAmortizedCost * 100) / 100,
    effectiveInterest: Math.round(effectiveInterest * 100) / 100,
    cashInflow: Math.round(cashInflow * 100) / 100,
    closingBalance: Math.round(closingBalance * 100) / 100,
  }
}

/** 对整个 group 进行公式计算（期间自动倒轧：首期开口=初始入账价值，其后期=上期期末） */
function computeGroup(group: InterestCalcGroup): InterestCalcGroup {
  const initialCarryingAmount = calcInitialCarryingAmount(
    parseNum(group.initial.purchasePrice),
    parseNum(group.initial.transactionCost),
  )

  const computedInitial: InitialCarryingData = {
    ...group.initial,
    initialCarryingAmount: Math.round(initialCarryingAmount * 100) / 100,
  }

  const computedPeriods: InterestPeriodRow[] = []
  let prevClosing = computedInitial.initialCarryingAmount
  for (let i = 0; i < group.periods.length; i++) {
    const p = { ...group.periods[i] }
    // 首期默认用初始入账价值；后续期自动从上期期末倒轧（用户填了非零 opening 则保留）
    if (i === 0) {
      if (!parseNum(p.openingBalance)) p.openingBalance = prevClosing
    } else if (!parseNum(p.openingBalance)) {
      p.openingBalance = prevClosing
    }
    const computed = computePeriodRow(p, computedInitial)
    computedPeriods.push(computed)
    prevClosing = computed.closingBalance
  }

  return {
    ...group,
    initial: computedInitial,
    periods: computedPeriods,
  }
}

function normalizeGroup(raw: any): InterestCalcGroup | null {
  if (!raw || typeof raw !== 'object') return null
  // 兼容扁平 IE 行：initial.* 字段在顶层
  const initialSrc = raw.initial && typeof raw.initial === 'object' ? raw.initial : raw
  const hasFlatPeriod = raw.cutoffDate != null || raw.openingBalance != null || raw.effectiveInterest != null
  const periodsSrc = Array.isArray(raw.periods) && raw.periods.length > 0
    ? raw.periods
    : hasFlatPeriod
      ? [raw]
      : []
  return {
    id: raw.id || generateId('group'),
    projectName: raw.projectName || '未命名投资项目',
    initial: {
      faceValueTotal: parseNum(initialSrc.faceValueTotal),
      initialDate: initialSrc.initialDate || '',
      maturityDate: initialSrc.maturityDate || '',
      purchasePrice: parseNum(initialSrc.purchasePrice),
      transactionCost: parseNum(initialSrc.transactionCost),
      initialCarryingAmount: parseNum(initialSrc.initialCarryingAmount),
      couponRate: parseNum(initialSrc.couponRate),
      effectiveRate: parseNum(initialSrc.effectiveRate),
    },
    periods: periodsSrc.length > 0
      ? periodsSrc.map((p: any) => ({
          id: p.id || generateId('period'),
          cutoffDate: p.cutoffDate || '',
          openingBalance: parseNum(p.openingBalance),
          openingImpairment: parseNum(p.openingImpairment),
          openingAmortizedCost: parseNum(p.openingAmortizedCost),
          effectiveInterest: parseNum(p.effectiveInterest),
          cashInflow: parseNum(p.cashInflow),
          principalRepaid: parseNum(p.principalRepaid),
          closingBalance: parseNum(p.closingBalance),
          days: parseNum(p.days) || 365,
          stage: ['Stage1', 'Stage2', 'Stage3'].includes(p.stage) ? p.stage : 'Stage1',
        }))
      : [createEmptyPeriod()],
  }
}

/** 将扁平导入行（百分数利率）归并为嵌套 groups（小数利率） */
export function flattenInterestGroupsToRows(groups: InterestCalcGroup[]): Record<string, unknown>[] {
  const rows: Record<string, unknown>[] = []
  for (const group of groups) {
    const initial = group.initial || ({} as InitialCarryingData)
    const periods = group.periods?.length ? group.periods : [createEmptyPeriod()]
    periods.forEach((period, index) => {
      rows.push({
        id: index === 0 ? group.id : `${group.id}-${period.id}`,
        projectName: group.projectName,
        faceValueTotal: initial.faceValueTotal,
        initialDate: initial.initialDate,
        maturityDate: initial.maturityDate,
        purchasePrice: initial.purchasePrice,
        transactionCost: initial.transactionCost,
        initialCarryingAmount: initial.initialCarryingAmount,
        couponRate: Math.round(parseNum(initial.couponRate) * 10000) / 100, // 小数→百分数
        effectiveRate: Math.round(parseNum(initial.effectiveRate) * 10000) / 100,
        cutoffDate: period.cutoffDate,
        openingBalance: period.openingBalance,
        openingImpairment: period.openingImpairment,
        openingAmortizedCost: period.openingAmortizedCost,
        effectiveInterest: period.effectiveInterest,
        cashInflow: period.cashInflow,
        principalRepaid: period.principalRepaid,
        closingBalance: period.closingBalance,
        days: period.days,
        stage: period.stage,
      })
    })
  }
  return rows
}

export function nestFlatInterestRows(rows: Record<string, unknown>[]): InterestCalcGroup[] {
  const byProject = new Map<string, InterestCalcGroup>()
  for (const raw of rows || []) {
    const projectName = String(raw.projectName || '').trim() || '未命名投资项目'
    const key = projectName.replace(/\s+/g, '')
    let group = byProject.get(key)
    if (!group) {
      // 百分数→小数（>1 视为百分数）
      const toDecimal = (v: unknown) => {
        const n = parseNum(v)
        return n > 1 ? n / 100 : n
      }
      group = {
        id: String(raw.id || generateId('group')),
        projectName,
        initial: {
          faceValueTotal: parseNum(raw.faceValueTotal),
          initialDate: String(raw.initialDate || ''),
          maturityDate: String(raw.maturityDate || ''),
          purchasePrice: parseNum(raw.purchasePrice),
          transactionCost: parseNum(raw.transactionCost),
          initialCarryingAmount: parseNum(raw.initialCarryingAmount),
          couponRate: toDecimal(raw.couponRate),
          effectiveRate: toDecimal(raw.effectiveRate),
        },
        periods: [],
      }
      byProject.set(key, group)
    }
    group.periods.push({
      id: generateId('period'),
      cutoffDate: String(raw.cutoffDate || ''),
      openingBalance: parseNum(raw.openingBalance),
      openingImpairment: parseNum(raw.openingImpairment),
      openingAmortizedCost: parseNum(raw.openingAmortizedCost),
      effectiveInterest: parseNum(raw.effectiveInterest),
      cashInflow: parseNum(raw.cashInflow),
      principalRepaid: parseNum(raw.principalRepaid),
      closingBalance: parseNum(raw.closingBalance),
      days: parseNum(raw.days) || 365,
      stage: ['Stage1', 'Stage2', 'Stage3'].includes(String(raw.stage))
        ? (raw.stage as InterestPeriodRow['stage'])
        : 'Stage1',
    })
  }
  return Array.from(byProject.values())
}

function parseStoredGroups(resp: ChecklistResponse | undefined): InterestCalcGroup[] {
  let parsed = parseCanonicalJson<unknown>(resp)
  // Some pre-contract data used conclusion for audit text and remark for rows.
  if (!Array.isArray(parsed) && resp?.remark) {
    parsed = parseCanonicalJson<unknown>({ remark: resp.remark })
  }
  if (!Array.isArray(parsed)) return []
  const looksFlat = parsed.some(
    (row: any) => row && typeof row === 'object' && !row.initial && (
      row.faceValueTotal != null || row.cutoffDate != null || row.openingBalance != null
    ),
  )
  if (looksFlat) return nestFlatInterestRows(parsed as Record<string, unknown>[])
  return parsed.map(normalizeGroup).filter(Boolean) as InterestCalcGroup[]
}

// ═══ 接口定义 ═══

export interface UseG4MainInterestCalcOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean> | ComputedRef<boolean>
  /** G4-1 审定表中利息收入审定数（用于差异比对） */
  g4_1InterestAdjusted?: Ref<number> | ComputedRef<number>
  wpId?: Ref<string>
  projectId?: Ref<string>
}

// ═══ Composable 主体 ═══

export function useG4MainInterestCalc(options: UseG4MainInterestCalcOptions) {
  const { allResponses, isReadonly, g4_1InterestAdjusted } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── 响应式数据 ───
  const groups = ref<InterestCalcGroup[]>([])
  const writebackPreview = ref<G4CrossApplyResult | null>(null)

  /** G4-1 利息审定比对基准：优先外部传入，否则读 checklist / G4-3·6011 净额 */
  const interestBenchmark = computed(() => {
    if (g4_1InterestAdjusted) return parseNum(g4_1InterestAdjusted.value)
    const stored = parseNum(allResponses.value.get(INTEREST_BENCHMARK_KEY)?.remark)
    if (stored !== 0) return stored
    // 从 G4-3 汇总 6011（利息收入）账项调整净额作参照（贷方增加收入为正）
    try {
      const raw = allResponses.value.get('G4-3-rows')?.remark
      if (!raw) return 0
      const entries = JSON.parse(raw) as Array<{
        accountCode?: string
        category?: string
        entryType?: string
        debitAmount?: number
        creditAmount?: number
      }>
      if (!Array.isArray(entries)) return 0
      let net = 0
      for (const e of entries) {
        if (String(e.accountCode || '') !== '6011') continue
        if (e.category === '报表调整' || e.entryType === 'RJE') continue
        // 收入类：贷−借 为审定调增利息收入
        net += parseNum(e.creditAmount) - parseNum(e.debitAmount)
      }
      return net
    } catch {
      return 0
    }
  })

  // ─── 从存储加载 ───
  function loadGroups(): void {
    const stored = parseStoredGroups(
      allResponses.value.get(STORAGE_KEY) ?? allResponses.value.get(IE_COMPAT_STORAGE_KEY),
    )
    groups.value = stored.length > 0 ? stored : []
  }

  watch(
    () => {
      const primary = allResponses.value.get(STORAGE_KEY)
      const compat = allResponses.value.get(IE_COMPAT_STORAGE_KEY)
      return [primary?.conclusion, primary?.remark, compat?.conclusion, compat?.remark].join('|')
    },
    (fingerprint, previous) => {
      // 初次或外部导入/结转导致存储指纹变化时重载；避免空表永久不刷新
      if (groups.value.length === 0 || (previous != null && fingerprint !== previous)) {
        loadGroups()
      }
    },
    { immediate: true },
  )

  // ─── 带公式的计算后分组（只读，每次 groups 变更自动重算） ───
  const computedGroups: ComputedRef<InterestCalcGroup[]> = computed(() =>
    groups.value.map(computeGroup),
  )

  // ─── 汇总 ───
  const totalEffectiveInterest: ComputedRef<number> = computed(() =>
    computedGroups.value.reduce(
      (sum, g) => sum + g.periods.reduce((s, p) => s + parseNum(p.effectiveInterest), 0),
      0,
    ),
  )

  /** 与 G4-1 / 基准利息收入比对 */
  const summary: ComputedRef<InterestCalcSummary> = computed(() => {
    const total = totalEffectiveInterest.value
    const adjusted = interestBenchmark.value
    const variance = Math.round((total - adjusted) * 100) / 100
    return {
      totalEffectiveInterest: Math.round(total * 100) / 100,
      g4_1InterestAdjusted: adjusted,
      variance,
      isVarianceAcceptable: Math.abs(variance) <= VARIANCE_THRESHOLD,
    }
  })

  function setInterestBenchmark(amount: number): void {
    if (readonly.value) return
    allResponses.value.set(INTEREST_BENCHMARK_KEY, {
      item_id: INTEREST_BENCHMARK_KEY,
      conclusion: null,
      remark: String(amount),
    })
    window.dispatchEvent(
      new CustomEvent('g4:save-items', {
        detail: { items: [allResponses.value.get(INTEREST_BENCHMARK_KEY)] },
      }),
    )
  }

  // ─── 差异高亮判断 ───

  /** |差异| > 0.01 → 红色高亮 */
  function isVarianceHighlight(): boolean {
    return !summary.value.isVarianceAcceptable
  }

  // ─── 利率合理性校验 ───

  /** 利率差异阈值：实际利率与票面利率差异超过200bp(2%)视为异常 */
  const RATE_DIFF_THRESHOLD = 0.02

  interface RateWarning {
    groupId: string
    projectName: string
    effectiveRate: number
    couponRate: number
    diffBps: number  // 差异(基点)
    message: string
  }

  /** 检测所有投资项目的利率合理性，返回异常列表 */
  const rateWarnings: ComputedRef<RateWarning[]> = computed(() => {
    const warnings: RateWarning[] = []
    for (const group of groups.value) {
      const er = parseNum(group.initial.effectiveRate)
      const cr = parseNum(group.initial.couponRate)
      // 跳过未填利率的空行
      if (er === 0 && cr === 0) continue
      const diff = Math.abs(er - cr)
      if (diff > RATE_DIFF_THRESHOLD) {
        warnings.push({
          groupId: group.id,
          projectName: group.projectName,
          effectiveRate: er,
          couponRate: cr,
          diffBps: Math.round(diff * 10000),
          message: `"${group.projectName}"实际利率(${(er * 100).toFixed(2)}%)与票面利率(${(cr * 100).toFixed(2)}%)差异${Math.round(diff * 10000)}bp，超过200bp阈值，请确认利率来源`,
        })
      }
      // 利率为0但有面值/对价的场景（可能漏填）
      if (er === 0 && parseNum(group.initial.purchasePrice) > 0) {
        warnings.push({
          groupId: group.id,
          projectName: group.projectName,
          effectiveRate: 0,
          couponRate: cr,
          diffBps: 0,
          message: `"${group.projectName}"实际利率为0但已填入购买对价，可能漏填实际利率`,
        })
      }
    }
    return warnings
  })

  /** 是否存在利率异常 */
  const hasRateWarnings: ComputedRef<boolean> = computed(() => rateWarnings.value.length > 0)

  // ─── 持久化 ───

  function persist(): void {
    const primary = buildCanonicalPayload(STORAGE_KEY, groups.value)
    const ieCompat = buildCanonicalPayload(
      IE_COMPAT_STORAGE_KEY,
      flattenInterestGroupsToRows(computedGroups.value),
    )
    allResponses.value.set(STORAGE_KEY, primary)
    allResponses.value.set(IE_COMPAT_STORAGE_KEY, ieCompat)
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function flushSave(): void {
    const items = [
      allResponses.value.get(STORAGE_KEY),
      allResponses.value.get(IE_COMPAT_STORAGE_KEY),
    ].filter((item): item is ChecklistResponse => Boolean(item))
    if (items.length) {
      window.dispatchEvent(new CustomEvent('g4:save-items', { detail: { items } }))
    }
  }

  // ─── 分组管理 ───

  /**
   * 新增投资项目 — ElMessageBox.prompt 输入名称确认后创建新组
   */
  async function addGroup(): Promise<void> {
    if (readonly.value) return
    if (groups.value.length >= MAX_GROUPS) return

    try {
      const { value: projectName } = await ElMessageBox.prompt(
        '请输入投资项目名称',
        '新增投资项目',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '例如：XX公司2024年企业债',
          inputValidator: (val: string) => {
            if (!val || !val.trim()) return '投资项目名称不能为空'
            return true
          },
          inputErrorMessage: '请输入有效的投资项目名称',
        },
      )
      if (!projectName || !projectName.trim()) return

      const newGroup = createEmptyGroup(projectName.trim())
      groups.value = [...groups.value, newGroup]
      persist()
    } catch {
      // 用户取消
    }
  }

  /**
   * 删除分组
   */
  function removeGroup(groupId: string): void {
    if (readonly.value) return
    const idx = groups.value.findIndex((g) => g.id === groupId)
    if (idx === -1) return

    groups.value = groups.value.filter((g) => g.id !== groupId)
    persist()
  }

  // ─── 计息期间行管理 ───

  /**
   * 新增计息期间行
   */
  function addPeriod(groupId: string): void {
    if (readonly.value) return
    const idx = groups.value.findIndex((g) => g.id === groupId)
    if (idx === -1) return
    if (groups.value[idx].periods.length >= MAX_PERIODS_PER_GROUP) return

    const newPeriod = createEmptyPeriod()
    const updatedGroup = {
      ...groups.value[idx],
      periods: [...groups.value[idx].periods, newPeriod],
    }
    const next = [...groups.value]
    next[idx] = updatedGroup
    groups.value = next
    persist()
  }

  /**
   * 删除计息期间行（至少保留1行）
   */
  function removePeriod(groupId: string, periodId: string): void {
    if (readonly.value) return
    const idx = groups.value.findIndex((g) => g.id === groupId)
    if (idx === -1) return
    if (groups.value[idx].periods.length <= 1) return

    const updatedGroup = {
      ...groups.value[idx],
      periods: groups.value[idx].periods.filter((p) => p.id !== periodId),
    }
    const next = [...groups.value]
    next[idx] = updatedGroup
    groups.value = next
    persist()
  }

  // ─── 单元格编辑 ───

  /**
   * 更新 section(一) 初始入账价值字段
   */
  function updateInitialField(
    groupId: string,
    field: keyof InitialCarryingData,
    value: string | number,
  ): void {
    if (readonly.value) return
    const idx = groups.value.findIndex((g) => g.id === groupId)
    if (idx === -1) return

    const numericFields: (keyof InitialCarryingData)[] = [
      'faceValueTotal', 'purchasePrice', 'transactionCost', 'couponRate', 'effectiveRate',
    ]
    const dateFields: (keyof InitialCarryingData)[] = ['initialDate', 'maturityDate']
    const formulaFields: (keyof InitialCarryingData)[] = ['initialCarryingAmount']

    // 公式字段不可手动修改
    if (formulaFields.includes(field)) return

    const updatedInitial = { ...groups.value[idx].initial }
    if (numericFields.includes(field)) {
      ;(updatedInitial as any)[field] = typeof value === 'number' ? value : parseNum(value)
    } else if (dateFields.includes(field)) {
      ;(updatedInitial as any)[field] = String(value ?? '')
    }

    const next = [...groups.value]
    next[idx] = { ...next[idx], initial: updatedInitial }
    groups.value = next
    persist()
  }

  /**
   * 更新 section(二) 计息期间行字段
   */
  function updatePeriodField(
    groupId: string,
    periodId: string,
    field: keyof InterestPeriodRow,
    value: string | number,
  ): void {
    if (readonly.value) return
    const gIdx = groups.value.findIndex((g) => g.id === groupId)
    if (gIdx === -1) return
    const pIdx = groups.value[gIdx].periods.findIndex((p) => p.id === periodId)
    if (pIdx === -1) return

    const formulaFields: (keyof InterestPeriodRow)[] = [
      'openingAmortizedCost', 'effectiveInterest', 'cashInflow', 'closingBalance',
    ]
    // 公式字段不可手动修改
    if (formulaFields.includes(field)) return

    const numericFields: (keyof InterestPeriodRow)[] = [
      'openingBalance', 'openingImpairment', 'principalRepaid', 'days',
    ]

    const updatedPeriod = { ...groups.value[gIdx].periods[pIdx] }

    if (field === 'stage') {
      const stageVal = String(value)
      updatedPeriod.stage = (['Stage1', 'Stage2', 'Stage3'].includes(stageVal)
        ? stageVal
        : 'Stage1') as 'Stage1' | 'Stage2' | 'Stage3'
    } else if (field === 'cutoffDate') {
      updatedPeriod.cutoffDate = String(value ?? '')
    } else if (numericFields.includes(field)) {
      ;(updatedPeriod as any)[field] = typeof value === 'number' ? value : parseNum(value)
    } else if (field === 'id') {
      // id 不可手动修改
      return
    }

    const updatedPeriods = [...groups.value[gIdx].periods]
    updatedPeriods[pIdx] = updatedPeriod

    const next = [...groups.value]
    next[gIdx] = { ...next[gIdx], periods: updatedPeriods }
    groups.value = next
    persist()
  }

  // ─── 批量设置（用于导入/seed） ───

  function setGroups(newGroups: InterestCalcGroup[]): void {
    groups.value = newGroups.map(normalizeGroup).filter(Boolean) as InterestCalcGroup[]
    persist()
  }

  async function previewWriteback(): Promise<G4CrossApplyResult | null> {
    const targetWpId = await resolveG4MainWorkpaperId(
      options.projectId?.value || '',
      options.wpId?.value,
    )
    if (!targetWpId) {
      ElMessage.error('未找到 G4 主底稿')
      return null
    }
    try {
      const existing = await fetchCanonicalRowsFromWorkpaper(targetWpId, G4_ITEM_IDS.G4_2_ROWS)
      writebackPreview.value = applyG44InterestToDetailRows(existing, computedGroups.value)
      return writebackPreview.value
    } catch {
      ElMessage.error('读取 G4-2 明细失败')
      return null
    }
  }

  async function confirmInterestWriteback(): Promise<void> {
    if (readonly.value) return
    const preview = await previewWriteback()
    if (!preview) return
    const componentLines = computedGroups.value.map((group) => {
      const actualInterest = group.periods.reduce((s, p) => s + parseNum(p.effectiveInterest), 0)
      const coupon = group.periods.reduce((s, p) => s + parseNum(p.cashInflow), 0)
      const amortization = Math.round((actualInterest - coupon) * 100) / 100
      return `${group.projectName || group.id || '未命名'}: 实际利息 ${actualInterest.toFixed(2)} / 票息 ${coupon.toFixed(2)} / 利息调整(摊销) ${amortization.toFixed(2)}`
    })
    const adjustmentTotal = preview.rows.reduce(
      (sum, row: any) => sum + parseNum(row.periodInterestAdjChange),
      0,
    )
    const hasVarianceDraft = Math.abs(summary.value.variance) >= VARIANCE_THRESHOLD
    const breakdown = componentLines.length
      ? `\n\n分项预览：\n${componentLines.slice(0, 8).join('\n')}${componentLines.length > 8 ? `\n…另有 ${componentLines.length - 8} 项` : ''}`
      : ''
    try {
      await ElMessageBox.confirm(
        `将实际利息－票息净额回写至 G4-2 的“本期利息调整变动”：匹配 ${preview.matched.length} 条，未匹配 ${preview.unmatched.length} 条，回写合计 ${adjustmentTotal.toFixed(2)}。${
          hasVarianceDraft ? `另将审计差额 ${summary.value.variance.toFixed(2)} 作为 G4-3 例外草稿。` : ''
        }不会将利息测算总额直接写入 G4-3。${breakdown}`,
        'G4-4 回写预览',
        { confirmButtonText: '确认回写', cancelButtonText: '取消', type: 'warning', customClass: 'g4-interest-writeback-preview' },
      )
    } catch {
      return
    }
    const targetWpId = await resolveG4MainWorkpaperId(
      options.projectId?.value || '',
      options.wpId?.value,
    )
    if (!targetWpId) return
    try {
      await saveCanonicalRowsToWorkpaper(
        targetWpId,
        options.projectId?.value || '',
        G4_ITEM_IDS.G4_2_ROWS,
        preview.rows,
      )
      // 同步当前 Main 内存，避免同实例切回 G4-2 时用旧行覆盖写回结果
      const detailPayload = buildCanonicalPayload(G4_ITEM_IDS.G4_2_ROWS, preview.rows)
      allResponses.value.set(G4_ITEM_IDS.G4_2_ROWS, detailPayload)
      try {
        window.dispatchEvent(new CustomEvent('g4:save-items', {
          detail: { items: [detailPayload] },
        }))
      } catch { /* silent */ }
      const drafts = buildG44InterestVarianceDraft(summary.value.variance, {
        description: 'G4-4 实际利率测算与审定利息收入差异',
      })
      dispatchG4ExceptionDrafts(drafts, allResponses.value)
      ElMessage.success(`已回写 ${preview.matched.length} 条 G4-2 利息调整${
        drafts.length ? '，并生成 G4-3 差异草稿' : ''
      }`)
    } catch {
      ElMessage.error('G4-4 回写失败')
    }
  }

  // ─── 生命周期清理 ───
  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    // 数据
    groups,
    computedGroups,
    // 汇总 & 比对
    totalEffectiveInterest,
    summary,
    isVarianceHighlight,
    // 利率合理性校验
    rateWarnings,
    hasRateWarnings,
    RATE_DIFF_THRESHOLD,
    // 分组管理
    addGroup,
    removeGroup,
    // 计息期间管理
    addPeriod,
    removePeriod,
    // 单元格编辑
    updateInitialField,
    updatePeriodField,
    setInterestBenchmark,
    // 批量设置
    setGroups,
    loadGroups,
    writebackPreview,
    previewWriteback,
    confirmInterestWriteback,
    // 常量
    STORAGE_KEY,
    INTEREST_BENCHMARK_KEY,
    VARIANCE_THRESHOLD,
  }
}

export default useG4MainInterestCalc
