/**
 * useG5InstallmentSales — G5-6 分期销售未实现融资收益测算（实际利率法）
 *
 * 核心公式（分期摊销，对齐致同模板列口径）：
 * - 未实现融资收益初始 = 应收总额 − 公允价值
 * - 期初摊余成本(未收本金) = 期初应收 − 期初未实现
 * - 本期融资收益(3) = 期初摊余成本 × 实际利率(4)
 * - 已收本金(2) = 本期收款(5) − 本期融资收益(3)
 * - 期末应收 = 期初应收 − 本期收款
 * - 期末未实现 = 期初未实现 − 本期融资收益
 * - 期末摊余 = 期初摊余 + 本期收益 − 本期收款
 *
 * 期末汇总勾稽对齐 Excel「有融资性质的销售形成的长期应收款」模板。
 */
import { ref, computed } from 'vue'
import {
  parseNum,
  calcInstallmentFinancingIncome,
  calcSalesAmortizedCost,
  calcEndingReceivable,
  calcNetInvestment,
} from '@/composables/useG5FormulaEngine'
import { ElMessage, ElMessageBox } from 'element-plus'

// ═══ 类型 ═══

export interface InstallmentInitialData {
  /** 客户/债务人 */
  customer: string
  /** 合同/协议编号 */
  contractNo: string
  /** 应收总额（各期收款合计） */
  contractTotal: number
  /** 公允价值（初始确认收入金额） */
  fairValue: number
  /** 未实现融资收益初始 = 应收 − 公允 */
  unrealizedIncome: number
  /** 实际利率 */
  effectiveRate: number
  /** 收款期限说明 */
  collectionTerm: string
  /** 账面：未实现融资收益期末 */
  bookClosingUnrealized: number
  /** 账面：摊余成本/净额期末 */
  bookClosingAmortizedCost: number
  /** 预计可收回金额 */
  estimatedRecoverable: number
  /** 累计已收回款项（账面口径，可手改；默认取摊销收款合计） */
  totalCollectedBook: number
  /** 减值准备期末 */
  impairmentEnding: number
  /** 已核销 */
  writtenOffAmount: number
}

export interface InstallmentPeriod {
  id: string
  periodNo: number
  /** 各期收款时间（可选） */
  collectionDate: string
  openingReceivable: number
  openingUnrealized: number
  /** 未收本金 / 期初摊余成本 — 模板列(1) */
  openingAmortizedCost: number
  /** 本期确认融资收入 — 模板列(3) */
  periodIncome: number
  /** 各期收款金额 — 模板列(5) */
  periodCollection: number
  /** 已收本金 — 模板列(2)=(5)-(3) */
  principalCollected: number
  closingReceivable: number
  closingUnrealized: number
  closingAmortizedCost: number
  /** 账面本期确认融资收益 */
  companyBookIncome: number
  variance: number
}

export interface InstallmentSalesGroup {
  id: string
  projectName: string
  initial: InstallmentInitialData
  periods: InstallmentPeriod[]
}

/** 对齐 Excel 模板的项目级汇总勾稽行 */
export interface InstallmentReconcileRow {
  groupId: string
  projectName: string
  customer: string
  contractTotal: number
  fairValue: number
  /** 初始未实现 */
  initialUnrealized: number
  effectiveRate: number
  unrealizedOpening: number
  unrealizedAddition: number
  unrealizedRecognized: number
  unrealizedEnding: number
  amortizedOpening: number
  /** 已收本金合计 */
  principalCollectedTotal: number
  amortizedEnding: number
  collectionTotal: number
  estimatedRecoverable: number
  impairmentEnding: number
  writtenOffAmount: number
  /**
   * 模板列(8)启发：初始公允 − 预计可收回 − 已收回（若预计可收回未填则用减值字段路径）
   * 账面净值优先：摊余期末 − 减值 − 核销
   */
  impairmentImplied: number
  carryingAmount: number
  bookClosingUnrealized: number
  bookClosingAmortizedCost: number
  unrealizedVariance: number
  amortizedVariance: number
  continuityOk: boolean
}

function emptyInitial(): InstallmentInitialData {
  return {
    customer: '',
    contractNo: '',
    contractTotal: 0,
    fairValue: 0,
    unrealizedIncome: 0,
    effectiveRate: 0,
    collectionTerm: '',
    bookClosingUnrealized: 0,
    bookClosingAmortizedCost: 0,
    estimatedRecoverable: 0,
    totalCollectedBook: 0,
    impairmentEnding: 0,
    writtenOffAmount: 0,
  }
}

function normalizeInitial(raw: any): InstallmentInitialData {
  const i = emptyInitial()
  if (!raw || typeof raw !== 'object') return i
  i.customer = String(raw.customer ?? '')
  i.contractNo = String(raw.contractNo ?? '')
  i.contractTotal = parseNum(raw.contractTotal)
  i.fairValue = parseNum(raw.fairValue)
  i.unrealizedIncome = parseNum(raw.unrealizedIncome)
  i.effectiveRate = parseNum(raw.effectiveRate)
  i.collectionTerm = String(raw.collectionTerm ?? '')
  i.bookClosingUnrealized = parseNum(raw.bookClosingUnrealized)
  i.bookClosingAmortizedCost = parseNum(raw.bookClosingAmortizedCost)
  i.estimatedRecoverable = parseNum(raw.estimatedRecoverable)
  i.totalCollectedBook = parseNum(raw.totalCollectedBook)
  i.impairmentEnding = parseNum(raw.impairmentEnding)
  i.writtenOffAmount = parseNum(raw.writtenOffAmount)
  return i
}

function createEmptyPeriod(periodNo: number): InstallmentPeriod {
  return {
    id: crypto.randomUUID(),
    periodNo,
    collectionDate: '',
    openingReceivable: 0,
    openingUnrealized: 0,
    openingAmortizedCost: 0,
    periodIncome: 0,
    periodCollection: 0,
    principalCollected: 0,
    closingReceivable: 0,
    closingUnrealized: 0,
    closingAmortizedCost: 0,
    companyBookIncome: 0,
    variance: 0,
  }
}

// ═══ Composable ═══

export function useG5InstallmentSales() {
  const groups = ref<InstallmentSalesGroup[]>([])
  const activeTab = ref<'initial' | 'amortization' | 'reconcile'>('initial')
  const conclusion = ref('')

  function recalcInitial(group: InstallmentSalesGroup) {
    group.initial.unrealizedIncome =
      parseNum(group.initial.contractTotal) - parseNum(group.initial.fairValue)
  }

  function recalcPeriod(period: InstallmentPeriod, effectiveRate: number) {
    const openRec = parseNum(period.openingReceivable)
    const openUnr = parseNum(period.openingUnrealized)
    const collection = parseNum(period.periodCollection)
    const rate = parseNum(effectiveRate)

    period.openingAmortizedCost = calcNetInvestment(openRec, openUnr)
    period.periodIncome = calcInstallmentFinancingIncome(period.openingAmortizedCost, rate)
    // 模板 (2) = (5) − (3)
    period.principalCollected = collection - period.periodIncome
    period.closingReceivable = calcEndingReceivable(openRec, collection)
    period.closingUnrealized = openUnr - period.periodIncome
    period.closingAmortizedCost = calcSalesAmortizedCost(
      period.openingAmortizedCost,
      period.periodIncome,
      collection,
    )
    period.variance = period.periodIncome - parseNum(period.companyBookIncome)
  }

  function recalcGroup(group: InstallmentSalesGroup) {
    recalcInitial(group)
    for (const p of group.periods) recalcPeriod(p, group.initial.effectiveRate)
  }

  /** 期间连续性：应收 + 未实现均需连贯 */
  function validateContinuity(group: InstallmentSalesGroup): boolean {
    for (let i = 1; i < group.periods.length; i++) {
      const prev = group.periods[i - 1]
      const curr = group.periods[i]
      if (Math.abs(parseNum(curr.openingReceivable) - parseNum(prev.closingReceivable)) > 0.01) {
        return false
      }
      if (Math.abs(parseNum(curr.openingUnrealized) - parseNum(prev.closingUnrealized)) > 0.01) {
        return false
      }
    }
    return true
  }

  function getContinuityErrors(group: InstallmentSalesGroup): number[] {
    const errors: number[] = []
    for (let i = 1; i < group.periods.length; i++) {
      const prev = group.periods[i - 1]
      const curr = group.periods[i]
      if (
        Math.abs(parseNum(curr.openingReceivable) - parseNum(prev.closingReceivable)) > 0.01 ||
        Math.abs(parseNum(curr.openingUnrealized) - parseNum(prev.closingUnrealized)) > 0.01
      ) {
        errors.push(curr.periodNo)
      }
    }
    return errors
  }

  function buildReconcileRow(group: InstallmentSalesGroup): InstallmentReconcileRow {
    const ini = group.initial
    const periods = group.periods
    const first = periods[0]
    const last = periods[periods.length - 1]

    const unrealizedRecognized = periods.reduce((s, p) => s + parseNum(p.periodIncome), 0)
    const unrealizedOpening = first ? parseNum(first.openingUnrealized) : parseNum(ini.unrealizedIncome)
    const unrealizedEnding = last
      ? parseNum(last.closingUnrealized)
      : parseNum(ini.unrealizedIncome)
    const unrealizedAddition = unrealizedEnding - unrealizedOpening + unrealizedRecognized

    const amortizedOpening = first ? parseNum(first.openingAmortizedCost) : parseNum(ini.fairValue)
    const amortizedEnding = last ? parseNum(last.closingAmortizedCost) : parseNum(ini.fairValue)
    const principalCollectedTotal = periods.reduce((s, p) => s + parseNum(p.principalCollected), 0)
    const collectionTotal = periods.reduce((s, p) => s + parseNum(p.periodCollection), 0)

    const estimated = parseNum(ini.estimatedRecoverable)
    const collectedBook = parseNum(ini.totalCollectedBook) || collectionTotal
    // 模板 (8) = 初始金额 − (6) − (7)；初始取公允价值
    const impairmentImplied =
      estimated > 0.01
        ? Math.max(0, parseNum(ini.fairValue) - estimated - collectedBook)
        : parseNum(ini.impairmentEnding)

    const impairment = parseNum(ini.impairmentEnding) || impairmentImplied
    const writtenOff = parseNum(ini.writtenOffAmount)
    const carryingAmount = amortizedEnding - impairment - writtenOff

    const bookUnr = parseNum(ini.bookClosingUnrealized)
    const bookAmort = parseNum(ini.bookClosingAmortizedCost)

    return {
      groupId: group.id,
      projectName: group.projectName,
      customer: ini.customer,
      contractTotal: parseNum(ini.contractTotal),
      fairValue: parseNum(ini.fairValue),
      initialUnrealized: parseNum(ini.unrealizedIncome),
      effectiveRate: parseNum(ini.effectiveRate),
      unrealizedOpening,
      unrealizedAddition,
      unrealizedRecognized,
      unrealizedEnding,
      amortizedOpening,
      principalCollectedTotal,
      amortizedEnding,
      collectionTotal,
      estimatedRecoverable: estimated,
      impairmentEnding: impairment,
      writtenOffAmount: writtenOff,
      impairmentImplied,
      carryingAmount,
      bookClosingUnrealized: bookUnr,
      bookClosingAmortizedCost: bookAmort,
      unrealizedVariance: unrealizedEnding - bookUnr,
      amortizedVariance: amortizedEnding - bookAmort,
      continuityOk: validateContinuity(group),
    }
  }

  const reconcileRows = computed(() => groups.value.map(buildReconcileRow))

  const reconcileTotals = computed(() => {
    const rows = reconcileRows.value
    const sum = (fn: (r: InstallmentReconcileRow) => number) =>
      rows.reduce((s, r) => s + fn(r), 0)
    return {
      contractTotal: sum(r => r.contractTotal),
      fairValue: sum(r => r.fairValue),
      initialUnrealized: sum(r => r.initialUnrealized),
      unrealizedOpening: sum(r => r.unrealizedOpening),
      unrealizedAddition: sum(r => r.unrealizedAddition),
      unrealizedRecognized: sum(r => r.unrealizedRecognized),
      unrealizedEnding: sum(r => r.unrealizedEnding),
      amortizedOpening: sum(r => r.amortizedOpening),
      principalCollectedTotal: sum(r => r.principalCollectedTotal),
      amortizedEnding: sum(r => r.amortizedEnding),
      collectionTotal: sum(r => r.collectionTotal),
      estimatedRecoverable: sum(r => r.estimatedRecoverable),
      impairmentEnding: sum(r => r.impairmentEnding),
      writtenOffAmount: sum(r => r.writtenOffAmount),
      carryingAmount: sum(r => r.carryingAmount),
      bookClosingUnrealized: sum(r => r.bookClosingUnrealized),
      bookClosingAmortizedCost: sum(r => r.bookClosingAmortizedCost),
      unrealizedVariance: sum(r => r.unrealizedVariance),
      amortizedVariance: sum(r => r.amortizedVariance),
    }
  })

  const totalIncome = computed(() =>
    groups.value.reduce(
      (s, g) => s + g.periods.reduce((ps, p) => ps + parseNum(p.periodIncome), 0),
      0,
    ),
  )

  const totalBookIncome = computed(() =>
    groups.value.reduce(
      (s, g) => s + g.periods.reduce((ps, p) => ps + parseNum(p.companyBookIncome), 0),
      0,
    ),
  )

  const totalVariance = computed(() =>
    groups.value.reduce(
      (s, g) => s + g.periods.reduce((ps, p) => ps + parseNum(p.variance), 0),
      0,
    ),
  )

  async function addGroup() {
    const { value } = await ElMessageBox.prompt('请输入销售项目名称', '新增项目', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    if (!value?.trim()) return
    const g: InstallmentSalesGroup = {
      id: crypto.randomUUID(),
      projectName: value.trim(),
      initial: emptyInitial(),
      periods: [createEmptyPeriod(1)],
    }
    groups.value.push(g)
  }

  function removeGroup(groupId: string) {
    groups.value = groups.value.filter(g => g.id !== groupId)
  }

  function addPeriod(groupId: string) {
    const group = groups.value.find(g => g.id === groupId)
    if (!group) return
    const period = createEmptyPeriod(group.periods.length + 1)
    if (group.periods.length > 0) {
      const prev = group.periods[group.periods.length - 1]
      period.openingReceivable = prev.closingReceivable
      period.openingUnrealized = prev.closingUnrealized
    } else {
      period.openingReceivable = parseNum(group.initial.contractTotal)
      period.openingUnrealized = parseNum(group.initial.unrealizedIncome)
    }
    group.periods.push(period)
    recalcPeriod(period, group.initial.effectiveRate)
  }

  function removePeriod(groupId: string, periodId: string) {
    const group = groups.value.find(g => g.id === groupId)
    if (!group || group.periods.length <= 1) return
    group.periods = group.periods.filter(p => p.id !== periodId)
    group.periods.forEach((p, i) => { p.periodNo = i + 1 })
  }

  /**
   * 用初始要素种子第一期：应收=合同总额，未实现=初始未实现，摊余=公允。
   */
  function seedFirstPeriodFromInitial(group: InstallmentSalesGroup) {
    recalcInitial(group)
    if (group.periods.length === 0) {
      group.periods.push(createEmptyPeriod(1))
    }
    const p0 = group.periods[0]
    p0.openingReceivable = parseNum(group.initial.contractTotal)
    p0.openingUnrealized = parseNum(group.initial.unrealizedIncome)
    recalcPeriod(p0, group.initial.effectiveRate)
  }

  /** 从 G5-2 带入 businessType=installment */
  function importFromG5BalanceRows(rawRows: unknown[]): number {
    if (!Array.isArray(rawRows) || rawRows.length === 0) return 0
    const existing = new Set(groups.value.map(g => g.projectName.trim()))
    let added = 0
    for (const raw of rawRows) {
      const r = raw as Record<string, any>
      if (String(r.businessType || '') !== 'installment') continue
      const name = String(r.debtorName || r.contractNo || '').trim() || `分期销售-${added + 1}`
      if (existing.has(name)) continue
      const g: InstallmentSalesGroup = {
        id: crypto.randomUUID(),
        projectName: name,
        initial: emptyInitial(),
        periods: [createEmptyPeriod(1)],
      }
      g.initial.customer = String(r.debtorName || '')
      g.initial.contractNo = String(r.contractNo || '')
      const contractAmt = parseNum(r.contractAmount)
      const closing = parseNum(r.closingBalance)
      const unrealized = parseNum(r.unrealizedIncome)
      g.initial.contractTotal = contractAmt || closing + unrealized
      g.initial.fairValue = Math.max(0, g.initial.contractTotal - unrealized)
      g.initial.unrealizedIncome = unrealized
      g.initial.bookClosingUnrealized = unrealized
      g.initial.bookClosingAmortizedCost = parseNum(r.netAmount) || (closing - unrealized)
      g.initial.collectionTerm = [r.startDate, r.maturityDate].filter(Boolean).join(' ~ ')
      seedFirstPeriodFromInitial(g)
      // 若余额明细是期末口径，覆盖第一期期初为当前未收回余额
      if (closing > 0) {
        g.periods[0].openingReceivable = closing
        g.periods[0].openingUnrealized = unrealized
        recalcPeriod(g.periods[0], g.initial.effectiveRate)
      }
      groups.value.push(g)
      existing.add(name)
      added += 1
    }
    if (added === 0) {
      ElMessage.info('G5-2 中无新增的分期销售行可带入（可能已全部存在）')
    } else {
      ElMessage.success(`已从 G5-2 带入 ${added} 个分期销售项目`)
    }
    return added
  }

  function loadData(data: any) {
    if (!data) return
    if (Array.isArray(data.groups)) {
      groups.value = data.groups.map((g: any) => ({
        id: g.id || crypto.randomUUID(),
        projectName: g.projectName || '',
        initial: normalizeInitial(g.initial),
        periods: Array.isArray(g.periods)
          ? g.periods.map((p: any, idx: number) => ({
              id: p.id || crypto.randomUUID(),
              periodNo: p.periodNo ?? idx + 1,
              collectionDate: String(p.collectionDate ?? ''),
              openingReceivable: parseNum(p.openingReceivable),
              openingUnrealized: parseNum(p.openingUnrealized),
              openingAmortizedCost: parseNum(p.openingAmortizedCost),
              periodIncome: parseNum(p.periodIncome),
              periodCollection: parseNum(p.periodCollection),
              principalCollected: parseNum(p.principalCollected),
              closingReceivable: parseNum(p.closingReceivable),
              closingUnrealized: parseNum(p.closingUnrealized),
              closingAmortizedCost: parseNum(p.closingAmortizedCost),
              companyBookIncome: parseNum(p.companyBookIncome),
              variance: parseNum(p.variance),
            }))
          : [createEmptyPeriod(1)],
      }))
      for (const g of groups.value) recalcGroup(g)
    }
    if (data.conclusion !== undefined) conclusion.value = data.conclusion
  }

  function toJSON() {
    return { groups: groups.value, conclusion: conclusion.value }
  }

  return {
    groups,
    activeTab,
    conclusion,
    totalIncome,
    totalBookIncome,
    totalVariance,
    reconcileRows,
    reconcileTotals,
    recalcInitial,
    recalcPeriod,
    recalcGroup,
    validateContinuity,
    getContinuityErrors,
    buildReconcileRow,
    seedFirstPeriodFromInitial,
    addGroup,
    removeGroup,
    addPeriod,
    removePeriod,
    importFromG5BalanceRows,
    loadData,
    toJSON,
  }
}
