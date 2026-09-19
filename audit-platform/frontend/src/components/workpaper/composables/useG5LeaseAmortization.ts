/**
 * useG5LeaseAmortization — G5-5 融资租赁未实现收益测算（内含利率法）
 *
 * 核心公式（分期摊销）：
 * - 净投资额 = 应收融资租赁款 - 未实现融资收益
 * - 融资收益 = 净投资额 × 内含利率
 * - 期末应收 = 期初应收 - 本期收款
 * - 期末未实现 = 期初未实现 - 本期收益
 * - 期间连续性：第N期期初 = 第N-1期期末
 *
 * 期末汇总勾稽（对齐 Excel 模板 G5-5 列）：
 * - 最低租赁收款额 ≈ 各期租金 + 承租人担保余值 + 第三方担保余值
 * - 未实现期末 = 期初 + 本期增加 − 本期确认收益
 * - 租赁投资净额期末 = 应收期末 − 未实现期末
 * - 账面净值 = 净投资期末 − 减值准备 − 已核销
 */
import { ref, computed } from 'vue'
import {
  parseNum,
  calcNetInvestment,
  calcLeaseFinancingIncome,
  calcEndingReceivable,
  calcEndingUnrealizedIncome,
} from '@/composables/useG5FormulaEngine'
import { ElMessage, ElMessageBox } from 'element-plus'

// ═══ 类型定义 ═══

export interface LeaseBasicData {
  lessee: string
  leaseStartDate: string
  leaseEndDate: string
  /** 各期租金合计（模板列：最低租赁收款额中的各期租金） */
  rentalInstallments: number
  /** 承租人担保余值 */
  residualLessee: number
  /** 第三方担保余值 */
  residualThirdParty: number
  /** 最低租赁收款额合计（=租金+承租人担保+第三方担保；可手改） */
  minimumLeasePayment: number
  /** 初始直接费用 */
  initialDirectCosts: number
  /** 未担保余值 — 期初 */
  unguaranteedOpening: number
  /** 未担保余值 — 本期增加 */
  unguaranteedIncrease: number
  /** 未担保余值 — 本期减少 */
  unguaranteedDecrease: number
  /** 未担保余值 — 期末（亦用于初始化） */
  unguaranteedResidual: number
  fairValue: number
  implicitRate: number
  /** 账面：未实现融资收益期末 */
  bookClosingUnrealized: number
  /** 账面：租赁投资净额期末 / 长期应收净额 */
  bookClosingNetInvestment: number
  /** 预计可收回金额 */
  estimatedRecoverable: number
  /** 减值准备期末余额 */
  impairmentEnding: number
  /** 已核销金额 */
  writtenOffAmount: number
}

export interface LeaseAmortizationPeriod {
  id: string
  periodNo: number
  openingReceivable: number
  openingUnrealized: number
  openingNetInvestment: number
  periodIncome: number
  periodCollection: number
  closingReceivable: number
  closingUnrealized: number
  closingNetInvestment: number
  companyBookIncome: number
  variance: number
}

export interface LeaseAmortizationGroup {
  id: string
  projectName: string
  basic: LeaseBasicData
  periods: LeaseAmortizationPeriod[]
}

/** 对齐 Excel 模板的项目级汇总勾稽行 */
export interface LeaseReconcileRow {
  groupId: string
  projectName: string
  lessee: string
  /** (1) 最低租赁收款额 */
  minimumLeasePayment: number
  rentalInstallments: number
  residualLessee: number
  residualThirdParty: number
  /** (5) 初始直接费用 */
  initialDirectCosts: number
  unguaranteedOpening: number
  unguaranteedIncrease: number
  unguaranteedDecrease: number
  /** 未担保余值期末 */
  unguaranteedEnding: number
  /** 毛投资额 ≈ 最低租赁收款额 + 未担保余值 + 初始直接费用 */
  grossInvestment: number
  /** 未实现融资收益期初（取首期期初） */
  unrealizedOpening: number
  /** 本期增加（勾稽恒等式：期末−期初+本期确认） */
  unrealizedAddition: number
  /** 本期确认融资收益（摊销合计） */
  unrealizedRecognized: number
  /** 未实现融资收益期末（取末期期末） */
  unrealizedEnding: number
  /** 净投资期初 */
  netOpening: number
  /** 净投资本期减少（期初−期末，收款大于收益时为正） */
  netDecrease: number
  /** 净投资期末 */
  netEnding: number
  estimatedRecoverable: number
  impairmentEnding: number
  writtenOffAmount: number
  /** 账面净值 = 净投资期末 − 减值 − 已核销 */
  carryingAmount: number
  bookClosingUnrealized: number
  bookClosingNetInvestment: number
  /** 未实现差异 = 审计期末 − 账面期末 */
  unrealizedVariance: number
  /** 净投资差异 = 审计期末 − 账面期末 */
  netVariance: number
  continuityOk: boolean
}

function emptyBasic(): LeaseBasicData {
  return {
    lessee: '',
    leaseStartDate: '',
    leaseEndDate: '',
    rentalInstallments: 0,
    residualLessee: 0,
    residualThirdParty: 0,
    minimumLeasePayment: 0,
    initialDirectCosts: 0,
    unguaranteedOpening: 0,
    unguaranteedIncrease: 0,
    unguaranteedDecrease: 0,
    unguaranteedResidual: 0,
    fairValue: 0,
    implicitRate: 0,
    bookClosingUnrealized: 0,
    bookClosingNetInvestment: 0,
    estimatedRecoverable: 0,
    impairmentEnding: 0,
    writtenOffAmount: 0,
  }
}

function normalizeBasic(raw: any): LeaseBasicData {
  const b = emptyBasic()
  if (!raw || typeof raw !== 'object') return b
  b.lessee = String(raw.lessee ?? '')
  b.leaseStartDate = String(raw.leaseStartDate ?? '')
  b.leaseEndDate = String(raw.leaseEndDate ?? '')
  b.rentalInstallments = parseNum(raw.rentalInstallments ?? raw.minimumLeasePayment)
  b.residualLessee = parseNum(raw.residualLessee)
  b.residualThirdParty = parseNum(raw.residualThirdParty)
  const mlpParts = b.rentalInstallments + b.residualLessee + b.residualThirdParty
  b.minimumLeasePayment = parseNum(
    raw.minimumLeasePayment != null ? raw.minimumLeasePayment : mlpParts,
  )
  b.initialDirectCosts = parseNum(raw.initialDirectCosts)
  b.unguaranteedOpening = parseNum(raw.unguaranteedOpening)
  b.unguaranteedIncrease = parseNum(raw.unguaranteedIncrease)
  b.unguaranteedDecrease = parseNum(raw.unguaranteedDecrease)
  b.unguaranteedResidual = parseNum(raw.unguaranteedResidual)
  // 若仅有期末未担保余值、未填期初，默认期初=期末
  if (!b.unguaranteedOpening && b.unguaranteedResidual && !b.unguaranteedIncrease && !b.unguaranteedDecrease) {
    b.unguaranteedOpening = b.unguaranteedResidual
  }
  b.fairValue = parseNum(raw.fairValue)
  b.implicitRate = parseNum(raw.implicitRate)
  b.bookClosingUnrealized = parseNum(raw.bookClosingUnrealized)
  b.bookClosingNetInvestment = parseNum(raw.bookClosingNetInvestment)
  b.estimatedRecoverable = parseNum(raw.estimatedRecoverable)
  b.impairmentEnding = parseNum(raw.impairmentEnding)
  b.writtenOffAmount = parseNum(raw.writtenOffAmount)
  return b
}

// ═══ Composable ═══

export function useG5LeaseAmortization() {
  const groups = ref<LeaseAmortizationGroup[]>([])
  const activeTab = ref<'basic' | 'amortization' | 'reconcile'>('basic')
  const conclusion = ref('')

  // ─── 公式计算：单行 ───

  function recalcPeriod(period: LeaseAmortizationPeriod, implicitRate: number) {
    const rate = parseNum(implicitRate)
    const openRec = parseNum(period.openingReceivable)
    const openUnr = parseNum(period.openingUnrealized)
    const collection = parseNum(period.periodCollection)

    period.openingNetInvestment = calcNetInvestment(openRec, openUnr)
    period.periodIncome = calcLeaseFinancingIncome(period.openingNetInvestment, rate)
    period.closingReceivable = calcEndingReceivable(openRec, collection)
    period.closingUnrealized = calcEndingUnrealizedIncome(openUnr, period.periodIncome)
    period.closingNetInvestment = calcNetInvestment(period.closingReceivable, period.closingUnrealized)
    period.variance = period.periodIncome - parseNum(period.companyBookIncome)
  }

  function recalcGroup(group: LeaseAmortizationGroup) {
    const rate = parseNum(group.basic.implicitRate)
    for (const period of group.periods) {
      recalcPeriod(period, rate)
    }
  }

  /** 最低租赁收款额 = 租金 + 承租人担保 + 第三方担保 */
  function syncMinimumLeasePayment(basic: LeaseBasicData) {
    basic.minimumLeasePayment =
      parseNum(basic.rentalInstallments) +
      parseNum(basic.residualLessee) +
      parseNum(basic.residualThirdParty)
  }

  /** 未担保余值期末 = 期初 + 增加 − 减少 */
  function syncUnguaranteedEnding(basic: LeaseBasicData) {
    basic.unguaranteedResidual =
      parseNum(basic.unguaranteedOpening) +
      parseNum(basic.unguaranteedIncrease) -
      parseNum(basic.unguaranteedDecrease)
  }

  // ─── 期间连续性验证 ───

  function validateContinuity(group: LeaseAmortizationGroup): boolean {
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

  function getContinuityErrors(group: LeaseAmortizationGroup): number[] {
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

  // ─── 期末汇总勾稽（对齐 Excel） ───

  function buildReconcileRow(group: LeaseAmortizationGroup): LeaseReconcileRow {
    const b = group.basic
    const periods = group.periods
    const first = periods[0]
    const last = periods[periods.length - 1]

    const unrealizedRecognized = periods.reduce((s, p) => s + parseNum(p.periodIncome), 0)
    const unrealizedOpening = first ? parseNum(first.openingUnrealized) : 0
    const unrealizedEnding = last ? parseNum(last.closingUnrealized) : 0
    // 勾稽恒等式：期末 = 期初 + 增加 − 确认 → 增加 = 期末 − 期初 + 确认
    const unrealizedAddition = unrealizedEnding - unrealizedOpening + unrealizedRecognized

    const netOpening = first ? parseNum(first.openingNetInvestment) : 0
    const netEnding = last ? parseNum(last.closingNetInvestment) : 0
    const netDecrease = netOpening - netEnding

    const unguaranteedEnding =
      parseNum(b.unguaranteedOpening) +
      parseNum(b.unguaranteedIncrease) -
      parseNum(b.unguaranteedDecrease)
    // 若用户只填了 unguaranteedResidual，以其为准
    const ugEnd = Math.abs(unguaranteedEnding) > 0.01 ||
      parseNum(b.unguaranteedOpening) ||
      parseNum(b.unguaranteedIncrease) ||
      parseNum(b.unguaranteedDecrease)
      ? unguaranteedEnding
      : parseNum(b.unguaranteedResidual)

    const mlp = parseNum(b.minimumLeasePayment)
    const grossInvestment = mlp + ugEnd + parseNum(b.initialDirectCosts)
    const impairment = parseNum(b.impairmentEnding)
    const writtenOff = parseNum(b.writtenOffAmount)
    const carryingAmount = netEnding - impairment - writtenOff

    const bookUnr = parseNum(b.bookClosingUnrealized)
    const bookNet = parseNum(b.bookClosingNetInvestment)

    return {
      groupId: group.id,
      projectName: group.projectName,
      lessee: b.lessee,
      minimumLeasePayment: mlp,
      rentalInstallments: parseNum(b.rentalInstallments),
      residualLessee: parseNum(b.residualLessee),
      residualThirdParty: parseNum(b.residualThirdParty),
      initialDirectCosts: parseNum(b.initialDirectCosts),
      unguaranteedOpening: parseNum(b.unguaranteedOpening),
      unguaranteedIncrease: parseNum(b.unguaranteedIncrease),
      unguaranteedDecrease: parseNum(b.unguaranteedDecrease),
      unguaranteedEnding: ugEnd,
      grossInvestment,
      unrealizedOpening,
      unrealizedAddition,
      unrealizedRecognized,
      unrealizedEnding,
      netOpening,
      netDecrease,
      netEnding,
      estimatedRecoverable: parseNum(b.estimatedRecoverable),
      impairmentEnding: impairment,
      writtenOffAmount: writtenOff,
      carryingAmount,
      bookClosingUnrealized: bookUnr,
      bookClosingNetInvestment: bookNet,
      unrealizedVariance: unrealizedEnding - bookUnr,
      netVariance: netEnding - bookNet,
      continuityOk: validateContinuity(group),
    }
  }

  const reconcileRows = computed(() => groups.value.map(buildReconcileRow))

  const reconcileTotals = computed(() => {
    const rows = reconcileRows.value
    const sum = (fn: (r: LeaseReconcileRow) => number) =>
      rows.reduce((s, r) => s + fn(r), 0)
    return {
      minimumLeasePayment: sum(r => r.minimumLeasePayment),
      initialDirectCosts: sum(r => r.initialDirectCosts),
      unguaranteedEnding: sum(r => r.unguaranteedEnding),
      grossInvestment: sum(r => r.grossInvestment),
      unrealizedOpening: sum(r => r.unrealizedOpening),
      unrealizedAddition: sum(r => r.unrealizedAddition),
      unrealizedRecognized: sum(r => r.unrealizedRecognized),
      unrealizedEnding: sum(r => r.unrealizedEnding),
      netOpening: sum(r => r.netOpening),
      netDecrease: sum(r => r.netDecrease),
      netEnding: sum(r => r.netEnding),
      estimatedRecoverable: sum(r => r.estimatedRecoverable),
      impairmentEnding: sum(r => r.impairmentEnding),
      writtenOffAmount: sum(r => r.writtenOffAmount),
      carryingAmount: sum(r => r.carryingAmount),
      bookClosingUnrealized: sum(r => r.bookClosingUnrealized),
      bookClosingNetInvestment: sum(r => r.bookClosingNetInvestment),
      unrealizedVariance: sum(r => r.unrealizedVariance),
      netVariance: sum(r => r.netVariance),
    }
  })

  // ─── 合计 ───

  const totalIncome = computed(() =>
    groups.value.reduce(
      (sum, g) => sum + g.periods.reduce((s, p) => s + parseNum(p.periodIncome), 0),
      0,
    ),
  )

  const totalBookIncome = computed(() =>
    groups.value.reduce(
      (sum, g) => sum + g.periods.reduce((s, p) => s + parseNum(p.companyBookIncome), 0),
      0,
    ),
  )

  const totalVariance = computed(() =>
    groups.value.reduce(
      (sum, g) => sum + g.periods.reduce((s, p) => s + parseNum(p.variance), 0),
      0,
    ),
  )

  // ─── 动态行增删 ───

  function createEmptyPeriod(periodNo: number): LeaseAmortizationPeriod {
    return {
      id: crypto.randomUUID(),
      periodNo,
      openingReceivable: 0,
      openingUnrealized: 0,
      openingNetInvestment: 0,
      periodIncome: 0,
      periodCollection: 0,
      closingReceivable: 0,
      closingUnrealized: 0,
      closingNetInvestment: 0,
      companyBookIncome: 0,
      variance: 0,
    }
  }

  function createEmptyGroup(projectName: string): LeaseAmortizationGroup {
    return {
      id: crypto.randomUUID(),
      projectName,
      basic: emptyBasic(),
      periods: [createEmptyPeriod(1)],
    }
  }

  async function addGroup() {
    const { value } = await ElMessageBox.prompt('请输入租赁项目名称', '新增租赁项目', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    if (!value?.trim()) return
    groups.value.push(createEmptyGroup(value.trim()))
  }

  function removeGroup(groupId: string) {
    groups.value = groups.value.filter(g => g.id !== groupId)
  }

  function addPeriod(groupId: string) {
    const group = groups.value.find(g => g.id === groupId)
    if (!group) return
    const nextNo = group.periods.length + 1
    const newPeriod = createEmptyPeriod(nextNo)
    if (group.periods.length > 0) {
      const prev = group.periods[group.periods.length - 1]
      newPeriod.openingReceivable = prev.closingReceivable
      newPeriod.openingUnrealized = prev.closingUnrealized
    }
    group.periods.push(newPeriod)
    recalcPeriod(newPeriod, group.basic.implicitRate)
  }

  function removePeriod(groupId: string, periodId: string) {
    const group = groups.value.find(g => g.id === groupId)
    if (!group || group.periods.length <= 1) return
    group.periods = group.periods.filter(p => p.id !== periodId)
    group.periods.forEach((p, i) => { p.periodNo = i + 1 })
  }

  /**
   * 从 G5-2 余额明细中带入 businessType=lease 的债务人行。
   * 已存在同名项目则跳过（不覆盖）。
   */
  function importFromG5BalanceRows(rawRows: unknown[]): number {
    if (!Array.isArray(rawRows) || rawRows.length === 0) return 0
    const existingNames = new Set(groups.value.map(g => g.projectName.trim()))
    let added = 0
    for (const raw of rawRows) {
      const r = raw as Record<string, any>
      if (String(r.businessType || '') !== 'lease') continue
      const name = String(r.debtorName || r.contractNo || '').trim() || `租赁项目-${added + 1}`
      if (existingNames.has(name)) continue
      const g = createEmptyGroup(name)
      g.basic.lessee = String(r.debtorName || '')
      g.basic.leaseStartDate = String(r.startDate || '')
      g.basic.leaseEndDate = String(r.maturityDate || '')
      const contractAmt = parseNum(r.contractAmount)
      const closing = parseNum(r.closingBalance)
      const unrealized = parseNum(r.unrealizedIncome)
      g.basic.rentalInstallments = contractAmt || closing
      g.basic.minimumLeasePayment = g.basic.rentalInstallments
      g.basic.unguaranteedResidual = 0
      g.basic.bookClosingUnrealized = unrealized
      g.basic.bookClosingNetInvestment = parseNum(r.netAmount) || (closing - unrealized)
      if (g.periods[0]) {
        g.periods[0].openingReceivable = closing
        g.periods[0].openingUnrealized = unrealized
        recalcPeriod(g.periods[0], g.basic.implicitRate)
      }
      groups.value.push(g)
      existingNames.add(name)
      added += 1
    }
    if (added === 0) {
      ElMessage.info('G5-2 中无新增的融资租赁行可带入（可能已全部存在）')
    } else {
      ElMessage.success(`已从 G5-2 带入 ${added} 个融资租赁项目`)
    }
    return added
  }

  // ─── 数据序列化/反序列化 ───

  function loadData(data: any) {
    if (!data) return
    if (Array.isArray(data.groups)) {
      groups.value = data.groups.map((g: any) => ({
        id: g.id || crypto.randomUUID(),
        projectName: g.projectName || '',
        basic: normalizeBasic(g.basic),
        periods: Array.isArray(g.periods) ? g.periods.map((p: any, idx: number) => ({
          id: p.id || crypto.randomUUID(),
          periodNo: p.periodNo ?? idx + 1,
          openingReceivable: parseNum(p.openingReceivable),
          openingUnrealized: parseNum(p.openingUnrealized),
          openingNetInvestment: parseNum(p.openingNetInvestment),
          periodIncome: parseNum(p.periodIncome),
          periodCollection: parseNum(p.periodCollection),
          closingReceivable: parseNum(p.closingReceivable),
          closingUnrealized: parseNum(p.closingUnrealized),
          closingNetInvestment: parseNum(p.closingNetInvestment),
          companyBookIncome: parseNum(p.companyBookIncome),
          variance: parseNum(p.variance),
        })) : [createEmptyPeriod(1)],
      }))
      for (const g of groups.value) {
        recalcGroup(g)
      }
    }
    if (data.conclusion !== undefined) {
      conclusion.value = data.conclusion
    }
  }

  function toJSON() {
    return {
      groups: groups.value,
      conclusion: conclusion.value,
    }
  }

  return {
    groups,
    activeTab,
    conclusion,
    recalcPeriod,
    recalcGroup,
    syncMinimumLeasePayment,
    syncUnguaranteedEnding,
    validateContinuity,
    getContinuityErrors,
    buildReconcileRow,
    reconcileRows,
    reconcileTotals,
    totalIncome,
    totalBookIncome,
    totalVariance,
    addGroup,
    removeGroup,
    addPeriod,
    removePeriod,
    importFromG5BalanceRows,
    loadData,
    toJSON,
  }
}
