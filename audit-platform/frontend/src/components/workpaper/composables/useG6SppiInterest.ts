/**
 * useG6SppiInterest — G6-6 利息测算表（实际利率法分组结构）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/ Task 5.1
 * Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 7.1
 *
 * 三层勾稽：
 * 1) 损益：Σ实际利息收入 ↔ 账面利息收入（手工/总账）
 * 2) 利息调整摊销：Σ(实际利息−票息) ↔ G6-1 利息调整本期变动
 * 3) 项目级期末摊余成本 ↔ G6-2 明细摊余成本（成本+利息调整）
 */
import { ref, computed, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import {
  calcEffectiveInterest,
  calcCashInflow,
  calcEndingAmortized,
  calcInterestDays,
  calcInitialCarryingAmount,
  calcInterestBasis,
  calcRemainingFace,
  normalizeDayCountBasis,
  parseNum,
  type G6DayCountBasis,
} from '@/composables/useG6SppiFormulaEngine'

// ─── 数据模型 ────────────────────────────────────────────────────────────────

export type G6InterestStage = 'Stage1' | 'Stage2' | 'Stage3'

/** 单期利息计算 */
export interface InterestPeriod {
  id: string
  periodStart: string        // 起息日（可自上一截止日继承）
  periodEnd: string          // 截止日（如 "2024-06-30"）
  openingAmortized: number   // 期初摊余成本（总额口径）
  openingImpairment: number  // 期初减值准备
  stage: G6InterestStage     // 减值阶段：Stage3 按净额计息
  effectiveInterest: number  // 实际利息收入（公式）
  cashInflow: number         // 现金流入（公式）
  principalRecovered: number // 已收回本金
  endingAmortized: number    // 期末摊余成本（公式）
  days: number               // 计息天数
  daysManualOverride: boolean // true=手工天数，不按日期覆盖
  openingManualOverride: boolean // true=手工期初摊余（含合法 0），不被初始入账覆盖
  remark: string             // 备注
  indexRef: string           // 期间级证据/索引
}

/** 投资项目分组 */
export interface InterestGroup {
  id: string
  crossSheetInvestmentId: string // 跨表稳定 ID（优先 G6-2）
  investProject: string      // 投资项目名称
  faceValue: number          // 面值
  couponRate: number         // 票面利率（如 0.04 = 4%）
  effectiveRate: number      // 实际利率（如 0.05 = 5%）
  /** 计息年天数基准：ACT/365（默认）、ACT/360 或 30/360 */
  dayCountBasis: G6DayCountBasis
  /** 初始确认 */
  purchasePrice: number
  transactionCost: number
  initialDate: string
  initialCarryingAmount: number // 公式：对价+交易费用
  periods: InterestPeriod[]  // 多期利息计算
}

/** 完整数据结构 */
export interface InterestCalculationData {
  groups: InterestGroup[]
  conclusion: string
  crossValidation: {
    totalInterest: number
    totalCashInflow: number
    totalAmortization: number
    bookInterestIncome: number
    bookInterestIncomeSet?: boolean
    interestAdjPeriodChange: number
    incomeDiff: number
    amortizationDiff: number
    /** 差异说明（超舍入阈值时建议填写） */
    varianceReason?: string
    /** 实际执行重要性（B15），用于升级提示 */
    performanceMateriality?: number
    auditedInterest?: number
    difference?: number
  }
}

export interface G6InterestRateWarning {
  groupId: string
  investProject: string
  message: string
}

export interface G6InterestDayWarning {
  groupId: string
  periodId: string
  investProject: string
  message: string
}

export interface G6InterestPrincipalWarning {
  groupId: string
  periodId?: string
  investProject: string
  message: string
}

/** 第三层：项目期末摊余 vs G6-2 */
export interface G6EndingAmortizedCompareRow {
  groupId: string
  investProject: string
  g66Ending: number
  g62Ending: number | null
  diff: number | null
  matched: boolean
}

const VARIANCE_THRESHOLD = 0.01
const RATE_DIFF_THRESHOLD = 0.02 // 200bp

function normalizeStage(raw: unknown): G6InterestStage {
  const s = String(raw || '')
  return s === 'Stage2' || s === 'Stage3' ? s : 'Stage1'
}

/** 截至 periodIndex 之前的已收回本金合计 */
function priorPrincipalRecovered(group: InterestGroup, periodIndex: number): number {
  let sum = 0
  for (let i = 0; i < periodIndex; i++) {
    sum += parseNum(group.periods[i]?.principalRecovered)
  }
  return Math.round(sum * 100) / 100
}

function emptyPeriod(partial: Partial<InterestPeriod> = {}): InterestPeriod {
  return {
    id: partial.id || `ip-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    periodStart: partial.periodStart || '',
    periodEnd: partial.periodEnd || '',
    openingAmortized: parseNum(partial.openingAmortized),
    openingImpairment: parseNum(partial.openingImpairment),
    stage: normalizeStage(partial.stage),
    effectiveInterest: 0,
    cashInflow: 0,
    principalRecovered: parseNum(partial.principalRecovered),
    endingAmortized: 0,
    days: parseNum(partial.days) || 180,
    daysManualOverride: Boolean(partial.daysManualOverride),
    openingManualOverride: Boolean(partial.openingManualOverride),
    remark: partial.remark || '',
    indexRef: partial.indexRef || '',
  }
}

function emptyGroup(partial: Partial<InterestGroup> = {}): InterestGroup {
  const purchasePrice = parseNum(partial.purchasePrice)
  const transactionCost = parseNum(partial.transactionCost)
  return {
    id: partial.id || `ig-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    crossSheetInvestmentId: String(partial.crossSheetInvestmentId || ''),
    investProject: partial.investProject || '',
    faceValue: parseNum(partial.faceValue),
    couponRate: parseNum(partial.couponRate),
    effectiveRate: parseNum(partial.effectiveRate),
    dayCountBasis: normalizeDayCountBasis(partial.dayCountBasis),
    purchasePrice,
    transactionCost,
    initialDate: partial.initialDate || '',
    initialCarryingAmount: calcInitialCarryingAmount(purchasePrice, transactionCost),
    periods: partial.periods || [],
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG6SppiInterest() {
  const groups = ref<InterestGroup[]>([])
  const conclusion = ref('')
  /** 账面利息收入基准（损益口径，手工/总账） */
  const bookInterestIncome = ref(0)
  /** 是否已明确填写账面利息（含合法 0） */
  const bookInterestIncomeSet = ref(false)
  /** G6-1 利息调整本期变动基准（摊销口径） */
  const interestAdjPeriodChange = ref(0)
  /** 差异说明 */
  const varianceReason = ref('')
  /** B15 实际执行重要性（0=未取到） */
  const performanceMateriality = ref(0)

  /** @deprecated 兼容旧名：实际指向利息调整本期变动 */
  const auditedInterest = interestAdjPeriodChange

  function setBookInterestIncome(value: number): void {
    bookInterestIncome.value = parseNum(value)
    bookInterestIncomeSet.value = true
  }

  function setPerformanceMateriality(value: number): void {
    performanceMateriality.value = Math.max(0, parseNum(value))
  }

  // ─── 公式计算 ──────────────────────────────────────────────────────────────

  /** 同步期间起息日与天数（非手工覆盖时按日期+计息基准推算） */
  function syncPeriodDates(
    period: InterestPeriod,
    prevEnd?: string,
    dayCountBasis: G6DayCountBasis | string = 'ACT/365',
  ): void {
    if (!period.periodStart && prevEnd) {
      period.periodStart = prevEnd
    }
    if (!period.daysManualOverride) {
      const derived = calcInterestDays(period.periodStart, period.periodEnd, dayCountBasis)
      if (derived != null) period.days = derived
    }
  }

  /** 重算单期公式列（票息按剩余面值 = 面值 − 此前收回本金） */
  function recalcPeriod(period: InterestPeriod, group: InterestGroup, periodIndex = 0): void {
    const basis = calcInterestBasis(
      period.openingAmortized,
      period.openingImpairment,
      period.stage,
    )
    period.effectiveInterest = calcEffectiveInterest(
      basis,
      parseNum(group.effectiveRate),
      parseNum(period.days),
      group.dayCountBasis,
    )
    const remainingFace = calcRemainingFace(
      group.faceValue,
      priorPrincipalRecovered(group, periodIndex),
    )
    period.cashInflow = calcCashInflow(
      remainingFace,
      parseNum(group.couponRate),
      parseNum(period.days),
      group.dayCountBasis,
    )
    period.endingAmortized = calcEndingAmortized(
      parseNum(period.openingAmortized),
      period.effectiveInterest,
      period.cashInflow,
      parseNum(period.principalRecovered),
    )
  }

  /** 重算整组（链式：上期末 = 下期初；首期空开口可用初始入账，除非手工覆盖） */
  function recalcGroup(group: InterestGroup): void {
    group.initialCarryingAmount = calcInitialCarryingAmount(
      group.purchasePrice,
      group.transactionCost,
    )
    for (let i = 0; i < group.periods.length; i++) {
      const period = group.periods[i]
      const prevEnd = i > 0 ? group.periods[i - 1].periodEnd : ''
      syncPeriodDates(period, prevEnd, group.dayCountBasis)
      if (i === 0) {
        if (
          !period.openingManualOverride
          && !parseNum(period.openingAmortized)
          && group.initialCarryingAmount
        ) {
          period.openingAmortized = group.initialCarryingAmount
        }
      } else {
        period.openingAmortized = group.periods[i - 1].endingAmortized
      }
      recalcPeriod(period, group, i)
    }
  }

  function recalcAll(): void {
    for (const group of groups.value) {
      recalcGroup(group)
    }
  }

  watch(groups, () => {
    recalcAll()
  }, { deep: true })

  // ─── 合计与三层勾稽 ────────────────────────────────────────────────────────

  const totalInterest = computed(() => {
    let sum = 0
    for (const group of groups.value) {
      for (const period of group.periods) {
        sum += parseNum(period.effectiveInterest)
      }
    }
    return Math.round(sum * 100) / 100
  })

  const totalCashInflow = computed(() => {
    let sum = 0
    for (const group of groups.value) {
      for (const period of group.periods) {
        sum += parseNum(period.cashInflow)
      }
    }
    return Math.round(sum * 100) / 100
  })

  /** 利息调整摊销额 = 实际利息 − 票息 */
  const totalAmortization = computed(() =>
    Math.round((totalInterest.value - totalCashInflow.value) * 100) / 100,
  )

  const incomeDiff = computed(() =>
    Math.round((totalInterest.value - parseNum(bookInterestIncome.value)) * 100) / 100,
  )

  const amortizationDiff = computed(() =>
    Math.round((totalAmortization.value - parseNum(interestAdjPeriodChange.value)) * 100) / 100,
  )

  /** 兼容旧：默认展示摊销层差异（若仅填了旧 auditedInterest） */
  const crossValidationDiff = computed(() => amortizationDiff.value)

  /** 账面利息未明确填写时不强制失败损益层（避免旧数据误报；0 可为合法账面） */
  const incomeLayerActive = computed(() => bookInterestIncomeSet.value)
  const incomePassed = computed(() =>
    !incomeLayerActive.value || Math.abs(incomeDiff.value) <= VARIANCE_THRESHOLD,
  )
  const amortizationPassed = computed(() => Math.abs(amortizationDiff.value) <= VARIANCE_THRESHOLD)
  /** 主勾稽：摊销层；损益层仅在已明确填写账面利息时一并要求 */
  const crossValidationPassed = computed(() => amortizationPassed.value && incomePassed.value)

  /** 超舍入阈值（需填差异说明） */
  const needsVarianceReason = computed(() => {
    const incomeOver = incomeLayerActive.value && Math.abs(incomeDiff.value) > VARIANCE_THRESHOLD
    const amortOver = Math.abs(amortizationDiff.value) > VARIANCE_THRESHOLD
    return incomeOver || amortOver
  })

  /** 超实际执行重要性（B15）→ 升级关注 */
  const materialVariance = computed(() => {
    const pm = parseNum(performanceMateriality.value)
    if (pm <= 0) return false
    const incomeOver = incomeLayerActive.value && Math.abs(incomeDiff.value) > pm
    const amortOver = Math.abs(amortizationDiff.value) > pm
    return incomeOver || amortOver
  })

  const varianceReasonMissing = computed(() =>
    needsVarianceReason.value && !String(varianceReason.value || '').trim(),
  )

  const rateWarnings = computed<G6InterestRateWarning[]>(() => {
    const warnings: G6InterestRateWarning[] = []
    for (const group of groups.value) {
      const er = parseNum(group.effectiveRate)
      const cr = parseNum(group.couponRate)
      if (er === 0 && cr === 0) continue
      if (er === 0 && parseNum(group.faceValue) > 0) {
        warnings.push({
          groupId: group.id,
          investProject: group.investProject,
          message: `"${group.investProject}"实际利率为 0 但已有面值，可能漏填实际利率`,
        })
      }
      const diff = Math.abs(er - cr)
      if (diff > RATE_DIFF_THRESHOLD) {
        warnings.push({
          groupId: group.id,
          investProject: group.investProject,
          message: `"${group.investProject}"实际利率(${(er * 100).toFixed(2)}%)与票面利率(${(cr * 100).toFixed(2)}%)差异${Math.round(diff * 10000)}bp，超过200bp，请确认利率来源`,
        })
      }
    }
    return warnings
  })

  const dayWarnings = computed<G6InterestDayWarning[]>(() => {
    const warnings: G6InterestDayWarning[] = []
    for (const group of groups.value) {
      for (let i = 0; i < group.periods.length; i++) {
        const p = group.periods[i]
        if (p.periodStart && p.periodEnd) {
          const a = new Date(`${p.periodStart}T00:00:00`)
          const b = new Date(`${p.periodEnd}T00:00:00`)
          if (!Number.isNaN(a.getTime()) && !Number.isNaN(b.getTime()) && b <= a) {
            warnings.push({
              groupId: group.id,
              periodId: p.id,
              investProject: group.investProject,
              message: `"${group.investProject}"期间截止日不晚于起息日`,
            })
          }
        }
        if (i > 0) {
          const prev = group.periods[i - 1]
          if (prev.periodEnd && p.periodStart && p.periodStart < prev.periodEnd) {
            warnings.push({
              groupId: group.id,
              periodId: p.id,
              investProject: group.investProject,
              message: `"${group.investProject}"期间与上期存在日期重叠/回退`,
            })
          }
        }
        if (p.days > 366) {
          warnings.push({
            groupId: group.id,
            periodId: p.id,
            investProject: group.investProject,
            message: `"${group.investProject}"计息天数 ${p.days} 超过 366`,
          })
        }
      }
    }
    return warnings
  })

  const hasRateWarnings = computed(() => rateWarnings.value.length > 0)
  const hasDayWarnings = computed(() => dayWarnings.value.length > 0)

  const principalWarnings = computed<G6InterestPrincipalWarning[]>(() => {
    const warnings: G6InterestPrincipalWarning[] = []
    for (const group of groups.value) {
      const face = parseNum(group.faceValue)
      let cumulative = 0
      for (const p of group.periods) {
        const recovered = parseNum(p.principalRecovered)
        if (recovered < 0) {
          warnings.push({
            groupId: group.id,
            periodId: p.id,
            investProject: group.investProject,
            message: `"${group.investProject}"收回本金为负数，请检查录入`,
          })
        }
        cumulative = Math.round((cumulative + recovered) * 100) / 100
        if (face > 0 && cumulative > face + 0.01) {
          warnings.push({
            groupId: group.id,
            periodId: p.id,
            investProject: group.investProject,
            message: `"${group.investProject}"累计收回本金 ${cumulative} 超过面值 ${face}`,
          })
          break
        }
        if (parseNum(p.endingAmortized) < -0.01) {
          warnings.push({
            groupId: group.id,
            periodId: p.id,
            investProject: group.investProject,
            message: `"${group.investProject}"期末摊余成本为负（${p.endingAmortized}），请核对收回本金/票息/利率`,
          })
        }
      }
    }
    return warnings
  })
  const hasPrincipalWarnings = computed(() => principalWarnings.value.length > 0)

  /** 第三层核对结果（由 runEndingAmortizedCompare 写入） */
  const endingAmortizedCompare = ref<G6EndingAmortizedCompareRow[]>([])
  const endingComparePassed = computed(() => {
    const rows = endingAmortizedCompare.value
    if (!rows.length) return true
    return rows.every((r) => r.matched && (r.diff == null || Math.abs(r.diff) < VARIANCE_THRESHOLD))
  })
  const endingCompareDiffTotal = computed(() => {
    let sum = 0
    for (const r of endingAmortizedCompare.value) {
      if (r.diff != null) sum += r.diff
    }
    return Math.round(sum * 100) / 100
  })

  function setEndingAmortizedCompare(rows: G6EndingAmortizedCompareRow[]): void {
    endingAmortizedCompare.value = rows
  }

  function applyCrossValidation(cv: InterestCalculationData['crossValidation'] | undefined): void {
    if (!cv) {
      bookInterestIncome.value = 0
      bookInterestIncomeSet.value = false
      interestAdjPeriodChange.value = 0
      varianceReason.value = ''
      return
    }
    bookInterestIncome.value = parseNum(cv.bookInterestIncome)
    if (typeof cv.bookInterestIncomeSet === 'boolean') {
      bookInterestIncomeSet.value = cv.bookInterestIncomeSet
    } else {
      bookInterestIncomeSet.value = Math.abs(bookInterestIncome.value) >= VARIANCE_THRESHOLD
    }
    interestAdjPeriodChange.value = parseNum(
      cv.interestAdjPeriodChange ?? cv.auditedInterest,
    )
    varianceReason.value = String(cv.varianceReason || '')
    if (cv.performanceMateriality != null) {
      performanceMateriality.value = parseNum(cv.performanceMateriality)
    }
  }

  // ─── 分组管理 ──────────────────────────────────────────────────────────────

  /** 新增投资项目 */
  async function addGroup(): Promise<void> {
    try {
      const { value } = await ElMessageBox.prompt(
        '请输入投资项目名称',
        '新增投资项目',
        {
          confirmButtonText: '确认',
          cancelButtonText: '取消',
          inputPattern: /\S+/,
          inputErrorMessage: '投资项目名称不能为空',
          inputPlaceholder: '例如：XX公司债券',
        },
      )
      if (!value?.trim()) return

      const newGroup = emptyGroup({
        investProject: value.trim(),
      })
      groups.value.push(newGroup)
      ElMessage.success(`已新增投资项目"${value.trim()}"`)
    } catch {
      // 用户取消
    }
  }

  /** 删除投资项目 */
  async function removeGroup(groupId: string): Promise<void> {
    const group = groups.value.find(g => g.id === groupId)
    if (!group) return
    try {
      await ElMessageBox.confirm(
        `确认删除投资项目"${group.investProject}"？将同时删除所有期间数据。`,
        '删除确认',
        { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' },
      )
      groups.value = groups.value.filter(g => g.id !== groupId)
      ElMessage.success(`已删除"${group.investProject}"`)
    } catch {
      // 用户取消
    }
  }

  // ─── 期间管理 ──────────────────────────────────────────────────────────────

  /** 新增期间 */
  function addPeriod(groupId: string): void {
    const group = groups.value.find(g => g.id === groupId)
    if (!group) return

    // 默认继承上一期的期末摊余；首期优先用初始入账价值
    const lastPeriod = group.periods[group.periods.length - 1]
    const openingAmortized = lastPeriod
      ? lastPeriod.endingAmortized
      : (group.initialCarryingAmount || 0)

    const newPeriod = emptyPeriod({
      periodStart: lastPeriod?.periodEnd || group.initialDate || '',
      openingAmortized,
      days: 180,
      daysManualOverride: false,
    })
    group.periods.push(newPeriod)
    recalcGroup(group)
  }

  /** 删除期间 */
  function removePeriod(groupId: string, periodId: string): void {
    const group = groups.value.find(g => g.id === groupId)
    if (!group) return
    group.periods = group.periods.filter(p => p.id !== periodId)
    recalcGroup(group)
  }

  /** 更新组头信息 */
  function updateGroupHeader(groupId: string, field: keyof InterestGroup, value: any): void {
    const group = groups.value.find(g => g.id === groupId)
    if (!group) return
    if (field === 'dayCountBasis') {
      group.dayCountBasis = normalizeDayCountBasis(value)
    } else {
      ;(group as any)[field] = value
    }
    recalcGroup(group)
  }

  /** 更新期间字段 */
  function updatePeriod(groupId: string, periodId: string, field: keyof InterestPeriod, value: any): void {
    const group = groups.value.find(g => g.id === groupId)
    if (!group) return
    const period = group.periods.find(p => p.id === periodId)
    if (!period) return
    ;(period as any)[field] = value
    if (field === 'days') {
      period.daysManualOverride = true
    }
    if (field === 'openingAmortized') {
      period.openingManualOverride = true
    }
    if (field === 'periodStart' || field === 'periodEnd') {
      // 改日期后若非手工天数，由 recalc 重推
      if (!period.daysManualOverride) {
        const derived = calcInterestDays(
          period.periodStart,
          period.periodEnd,
          group.dayCountBasis,
        )
        if (derived != null) period.days = derived
      }
    }
    recalcGroup(group)
  }

  // ─── 数据加载/导出 ─────────────────────────────────────────────────────────

  /** 扁平行（IE G6-6-rows）→ 分组结构 */
  function nestFlatRows(rows: any[]): InterestGroup[] {
    const order: string[] = []
    const map = new Map<string, InterestGroup>()
    for (const row of rows || []) {
      const name = String(row.investProject || row.projectName || '').trim() || '未命名投资项目'
      const key = name.replace(/\s+/g, '')
      if (!map.has(key)) {
        map.set(key, emptyGroup({
          id: String(row.id || `ig-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`),
          crossSheetInvestmentId: String(row.crossSheetInvestmentId || ''),
          investProject: name,
          faceValue: parseNum(row.faceValue),
          couponRate: parseNum(row.couponRate),
          effectiveRate: parseNum(row.effectiveRate),
          dayCountBasis: normalizeDayCountBasis(row.dayCountBasis),
          purchasePrice: parseNum(row.purchasePrice),
          transactionCost: parseNum(row.transactionCost),
          initialDate: String(row.initialDate || ''),
          periods: [],
        }))
        order.push(key)
      }
      const group = map.get(key)!
      if (!group.crossSheetInvestmentId && row.crossSheetInvestmentId) {
        group.crossSheetInvestmentId = String(row.crossSheetInvestmentId)
      }
      if (!group.faceValue && parseNum(row.faceValue)) group.faceValue = parseNum(row.faceValue)
      if (!group.couponRate && parseNum(row.couponRate)) group.couponRate = parseNum(row.couponRate)
      if (!group.effectiveRate && parseNum(row.effectiveRate)) group.effectiveRate = parseNum(row.effectiveRate)
      if (row.dayCountBasis) group.dayCountBasis = normalizeDayCountBasis(row.dayCountBasis)
      if (!group.purchasePrice && parseNum(row.purchasePrice)) group.purchasePrice = parseNum(row.purchasePrice)
      if (!group.transactionCost && parseNum(row.transactionCost)) group.transactionCost = parseNum(row.transactionCost)
      if (!group.initialDate && row.initialDate) group.initialDate = String(row.initialDate)

      const hasPeriod =
        row.periodEnd || row.cutoffDate || row.openingAmortized != null || row.days != null
      if (!hasPeriod && group.periods.length > 0) continue

      group.periods.push(emptyPeriod({
        id: String(row.periodId || `ip-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`),
        periodStart: String(row.periodStart || ''),
        periodEnd: String(row.periodEnd || row.cutoffDate || ''),
        openingAmortized: parseNum(row.openingAmortized),
        openingImpairment: parseNum(row.openingImpairment),
        stage: normalizeStage(row.stage),
        principalRecovered: parseNum(row.principalRecovered),
        days: parseNum(row.days) || 180,
        daysManualOverride: Boolean(row.daysManualOverride) || (!row.periodStart && !!row.days),
        openingManualOverride: Boolean(row.openingManualOverride)
          || (row.openingAmortized != null && parseNum(row.openingAmortized) === 0),
        remark: String(row.remark || ''),
        indexRef: String(row.indexRef || ''),
      }))
    }
    return order.map((k) => map.get(k)!).filter(Boolean)
  }

  /** 分组 → 扁平行（供 IE 双写） */
  function flattenGroups(source?: InterestGroup[]): any[] {
    const list = source ?? groups.value
    const flat: any[] = []
    for (const g of list) {
      const periods = g.periods?.length ? g.periods : [emptyPeriod({ id: '' })]
      periods.forEach((p, idx) => {
        flat.push({
          id: idx === 0 ? g.id : `${g.id}-${p.id || idx}`,
          periodId: p.id || '',
          crossSheetInvestmentId: g.crossSheetInvestmentId || g.id,
          investProject: g.investProject,
          faceValue: g.faceValue,
          couponRate: g.couponRate,
          effectiveRate: g.effectiveRate,
          dayCountBasis: g.dayCountBasis || 'ACT/365',
          purchasePrice: g.purchasePrice,
          transactionCost: g.transactionCost,
          initialDate: g.initialDate,
          initialCarryingAmount: g.initialCarryingAmount,
          cutoffDate: p.periodEnd,
          periodStart: p.periodStart,
          periodEnd: p.periodEnd,
          openingAmortized: p.openingAmortized,
          openingImpairment: p.openingImpairment,
          stage: p.stage,
          effectiveInterest: p.effectiveInterest,
          cashInflow: p.cashInflow,
          principalRecovered: p.principalRecovered,
          endingAmortized: p.endingAmortized,
          days: p.days,
          daysManualOverride: p.daysManualOverride,
          openingManualOverride: p.openingManualOverride,
          remark: p.remark,
          indexRef: p.indexRef,
        })
      })
    }
    return flat
  }

  function loadData(data: InterestCalculationData | any[] | null): void {
    if (Array.isArray(data)) {
      if (data.length && Array.isArray(data[0]?.periods)) {
        loadData({
          groups: data as InterestGroup[],
          conclusion: '',
          crossValidation: {
            totalInterest: 0,
            totalCashInflow: 0,
            totalAmortization: 0,
            bookInterestIncome: 0,
            bookInterestIncomeSet: false,
            interestAdjPeriodChange: 0,
            incomeDiff: 0,
            amortizationDiff: 0,
          },
        })
        return
      }
      groups.value = nestFlatRows(data)
      conclusion.value = ''
      recalcAll()
      return
    }

    if (!data?.groups?.length) {
      groups.value = []
      conclusion.value = data?.conclusion || ''
      applyCrossValidation(data?.crossValidation)
      return
    }

    groups.value = data.groups.map(g => emptyGroup({
      ...g,
      id: g.id || `ig-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      crossSheetInvestmentId: String(g.crossSheetInvestmentId || g.id || ''),
      periods: (g.periods || []).map(p => emptyPeriod({
        ...p,
        id: p.id || `ip-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        periodEnd: p.periodEnd || (p as any).cutoffDate || '',
      })),
    }))
    conclusion.value = data.conclusion || ''
    applyCrossValidation(data.crossValidation)
    recalcAll()
  }

  /**
   * 从 G6-2 明细种子合并：优先 crossSheetInvestmentId/id，其次名称；已有项目保留期间。
   */
  function mergeSeedsFromDetail(
    seeds: Array<{
      id: string
      investProject: string
      faceValue: number
      couponRate: number
      effectiveRate: number
      openingAmortized: number
    }>,
  ): { added: number; updated: number } {
    let added = 0
    let updated = 0
    const byId = new Map<string, InterestGroup>()
    for (const g of groups.value) {
      if (g.crossSheetInvestmentId) byId.set(g.crossSheetInvestmentId, g)
      if (g.id) byId.set(g.id, g)
    }
    const byName = new Map(
      groups.value.map((g) => [g.investProject.trim().replace(/\s+/g, ''), g]),
    )

    for (const seed of seeds) {
      const key = seed.investProject.trim().replace(/\s+/g, '')
      const existing =
        (seed.id && byId.get(seed.id)) ||
        byName.get(key) ||
        undefined
      if (existing) {
        if (seed.id) {
          existing.crossSheetInvestmentId = seed.id
          if (existing.id !== seed.id) {
            byId.delete(existing.id)
            existing.id = seed.id
            byId.set(seed.id, existing)
          }
        }
        if (!existing.faceValue && seed.faceValue) existing.faceValue = seed.faceValue
        if (seed.couponRate) {
          if (!existing.couponRate || Math.abs(existing.couponRate) > 1) {
            existing.couponRate = seed.couponRate
          }
        }
        if (seed.effectiveRate) {
          if (!existing.effectiveRate || Math.abs(existing.effectiveRate) > 1) {
            existing.effectiveRate = seed.effectiveRate
          }
        }
        if (existing.periods.length === 0 && seed.openingAmortized != null) {
          existing.periods.push(emptyPeriod({
            openingAmortized: seed.openingAmortized,
            openingManualOverride: true,
            days: 180,
            remark: '自G6-2带入',
          }))
        }
        updated += 1
        continue
      }

      const newGroup = emptyGroup({
        id: seed.id || `ig-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        crossSheetInvestmentId: seed.id || '',
        investProject: seed.investProject,
        faceValue: seed.faceValue,
        couponRate: seed.couponRate,
        effectiveRate: seed.effectiveRate,
        periods: seed.openingAmortized != null
          ? [emptyPeriod({
              openingAmortized: seed.openingAmortized,
              openingManualOverride: true,
              days: 180,
              remark: '自G6-2带入',
            })]
          : [],
      })
      groups.value.push(newGroup)
      byId.set(newGroup.id, newGroup)
      if (newGroup.crossSheetInvestmentId) byId.set(newGroup.crossSheetInvestmentId, newGroup)
      byName.set(key, newGroup)
      added += 1
    }
    recalcAll()
    return { added, updated }
  }

  /**
   * 从 G6-12 阶段/减值种子更新：匹配 id/名称后仅写入末期（报告期）stage 与减值。
   */
  function mergeEclStageSeeds(
    seeds: Array<{
      id: string
      investProject: string
      stage: G6InterestStage
      openingImpairment: number
    }>,
  ): { updated: number; unmatched: number } {
    let updated = 0
    let unmatched = 0
    const byId = new Map<string, InterestGroup>()
    for (const g of groups.value) {
      if (g.crossSheetInvestmentId) byId.set(g.crossSheetInvestmentId, g)
      if (g.id) byId.set(g.id, g)
    }
    const byName = new Map(
      groups.value.map((g) => [g.investProject.trim().replace(/\s+/g, ''), g]),
    )

    for (const seed of seeds) {
      const key = seed.investProject.trim().replace(/\s+/g, '')
      const existing =
        (seed.id && byId.get(seed.id)) ||
        byName.get(key) ||
        undefined
      if (!existing || !existing.periods.length) {
        unmatched += 1
        continue
      }
      const last = existing.periods[existing.periods.length - 1]
      last.stage = normalizeStage(seed.stage)
      last.openingImpairment = parseNum(seed.openingImpairment)
      updated += 1
    }
    recalcAll()
    return { updated, unmatched }
  }

  function toJSON(): InterestCalculationData {
    return {
      groups: groups.value.map(g => ({ ...g, periods: g.periods.map(p => ({ ...p })) })),
      conclusion: conclusion.value,
      crossValidation: {
        totalInterest: totalInterest.value,
        totalCashInflow: totalCashInflow.value,
        totalAmortization: totalAmortization.value,
        bookInterestIncome: bookInterestIncome.value,
        bookInterestIncomeSet: bookInterestIncomeSet.value,
        interestAdjPeriodChange: interestAdjPeriodChange.value,
        incomeDiff: incomeDiff.value,
        amortizationDiff: amortizationDiff.value,
        varianceReason: varianceReason.value,
        performanceMateriality: performanceMateriality.value,
        auditedInterest: interestAdjPeriodChange.value,
        difference: amortizationDiff.value,
      },
    }
  }

  function getGroupInterestTotal(groupId: string): number {
    const group = groups.value.find(g => g.id === groupId)
    if (!group) return 0
    let sum = 0
    for (const p of group.periods) {
      sum += parseNum(p.effectiveInterest)
    }
    return Math.round(sum * 100) / 100
  }

  return {
    groups,
    conclusion,
    bookInterestIncome,
    bookInterestIncomeSet,
    interestAdjPeriodChange,
    varianceReason,
    performanceMateriality,
    auditedInterest,
    totalInterest,
    totalCashInflow,
    totalAmortization,
    incomeDiff,
    amortizationDiff,
    incomePassed,
    amortizationPassed,
    incomeLayerActive,
    crossValidationDiff,
    crossValidationPassed,
    needsVarianceReason,
    materialVariance,
    varianceReasonMissing,
    rateWarnings,
    dayWarnings,
    principalWarnings,
    hasRateWarnings,
    hasDayWarnings,
    hasPrincipalWarnings,
    endingAmortizedCompare,
    endingComparePassed,
    endingCompareDiffTotal,
    setEndingAmortizedCompare,
    recalcPeriod,
    recalcGroup,
    recalcAll,
    addGroup,
    removeGroup,
    addPeriod,
    removePeriod,
    updateGroupHeader,
    updatePeriod,
    setBookInterestIncome,
    setPerformanceMateriality,
    getGroupInterestTotal,
    loadData,
    nestFlatRows,
    flattenGroups,
    mergeSeedsFromDetail,
    mergeEclStageSeeds,
    toJSON,
    VARIANCE_THRESHOLD,
  }
}

export default useG6SppiInterest
