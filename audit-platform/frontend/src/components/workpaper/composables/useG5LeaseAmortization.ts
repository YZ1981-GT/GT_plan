/**
 * useG5LeaseAmortization — G5-5 融资租赁未实现收益测算（内含利率法）
 *
 * 核心公式：
 * - 净投资额 = 应收融资租赁款 - 未实现融资收益
 * - 融资收益 = 净投资额 × 内含利率（核心）
 * - 期末应收 = 期初应收 - 本期收款
 * - 期末未实现 = 期初未实现 - 本期收益
 *
 * 期间连续性：第N期期初 = 第N-1期期末
 * 差异 = 审计测算 - 企业账面（>重要性水平红色高亮）
 */
import { ref, computed } from 'vue'
import {
  parseNum,
  calcNetInvestment,
  calcLeaseFinancingIncome,
  calcEndingReceivable,
  calcEndingUnrealizedIncome,
} from '@/composables/useG5FormulaEngine'
import { ElMessageBox } from 'element-plus'

// ═══ 类型定义 ═══

export interface LeaseBasicData {
  lessee: string
  leaseStartDate: string
  leaseEndDate: string
  minimumLeasePayment: number
  unguaranteedResidual: number
  fairValue: number
  implicitRate: number
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

// ═══ Composable ═══

export function useG5LeaseAmortization() {
  const groups = ref<LeaseAmortizationGroup[]>([])
  const activeTab = ref<'basic' | 'amortization'>('basic')
  const conclusion = ref('')

  // ─── 公式计算：单行 ───

  function recalcPeriod(period: LeaseAmortizationPeriod, implicitRate: number) {
    const rate = parseNum(implicitRate)
    const openRec = parseNum(period.openingReceivable)
    const openUnr = parseNum(period.openingUnrealized)
    const collection = parseNum(period.periodCollection)

    // 净投资额 = 应收 - 未实现
    period.openingNetInvestment = calcNetInvestment(openRec, openUnr)
    // 融资收益 = 净投资额 × 内含利率
    period.periodIncome = calcLeaseFinancingIncome(period.openingNetInvestment, rate)
    // 期末应收 = 期初 - 收款
    period.closingReceivable = calcEndingReceivable(openRec, collection)
    // 期末未实现 = 期初 - 收益
    period.closingUnrealized = calcEndingUnrealizedIncome(openUnr, period.periodIncome)
    // 期末净投资 = 期末应收 - 期末未实现
    period.closingNetInvestment = calcNetInvestment(period.closingReceivable, period.closingUnrealized)
    // 差异 = 审计测算收益 - 企业账面收益
    period.variance = period.periodIncome - parseNum(period.companyBookIncome)
  }

  // ─── 公式计算：整组 ───

  function recalcGroup(group: LeaseAmortizationGroup) {
    const rate = parseNum(group.basic.implicitRate)
    for (const period of group.periods) {
      recalcPeriod(period, rate)
    }
  }

  // ─── 期间连续性验证 ───

  function validateContinuity(group: LeaseAmortizationGroup): boolean {
    for (let i = 1; i < group.periods.length; i++) {
      const prev = group.periods[i - 1]
      const curr = group.periods[i]
      // 第N期期初应收 = 第N-1期期末应收
      if (Math.abs(parseNum(curr.openingReceivable) - parseNum(prev.closingReceivable)) > 0.01) {
        return false
      }
      // 第N期期初未实现 = 第N-1期期末未实现
      if (Math.abs(parseNum(curr.openingUnrealized) - parseNum(prev.closingUnrealized)) > 0.01) {
        return false
      }
    }
    return true
  }

  /** 获取连续性断裂的期间编号列表 */
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

  // ─── 合计 ───

  /** 各项目融资收益合计 */
  const totalIncome = computed(() =>
    groups.value.reduce(
      (sum, g) => sum + g.periods.reduce((s, p) => s + parseNum(p.periodIncome), 0),
      0,
    ),
  )

  /** 各项目差异合计 */
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
      basic: {
        lessee: '',
        leaseStartDate: '',
        leaseEndDate: '',
        minimumLeasePayment: 0,
        unguaranteedResidual: 0,
        fairValue: 0,
        implicitRate: 0,
      },
      periods: [createEmptyPeriod(1)],
    }
  }

  /** 新增租赁项目（ElMessageBox.prompt 输入项目名称） */
  async function addGroup() {
    const { value } = await ElMessageBox.prompt('请输入租赁项目名称', '新增租赁项目', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    if (!value?.trim()) return
    groups.value.push(createEmptyGroup(value.trim()))
  }

  /** 删除租赁项目 */
  function removeGroup(groupId: string) {
    groups.value = groups.value.filter(g => g.id !== groupId)
  }

  /** 新增期间行（追加到指定项目） */
  function addPeriod(groupId: string) {
    const group = groups.value.find(g => g.id === groupId)
    if (!group) return
    const nextNo = group.periods.length + 1
    const newPeriod = createEmptyPeriod(nextNo)
    // 自动填充期初值 = 上期期末值（期间连续性）
    if (group.periods.length > 0) {
      const prev = group.periods[group.periods.length - 1]
      newPeriod.openingReceivable = prev.closingReceivable
      newPeriod.openingUnrealized = prev.closingUnrealized
    }
    group.periods.push(newPeriod)
    // 自动计算新期间
    recalcPeriod(newPeriod, group.basic.implicitRate)
  }

  /** 删除指定期间行 */
  function removePeriod(groupId: string, periodId: string) {
    const group = groups.value.find(g => g.id === groupId)
    if (!group) return
    group.periods = group.periods.filter(p => p.id !== periodId)
    // 重新编号
    group.periods.forEach((p, i) => { p.periodNo = i + 1 })
  }

  // ─── 数据序列化/反序列化 ───

  function loadData(data: any) {
    if (!data) return
    if (Array.isArray(data.groups)) {
      groups.value = data.groups.map((g: any) => ({
        id: g.id || crypto.randomUUID(),
        projectName: g.projectName || '',
        basic: {
          lessee: g.basic?.lessee || '',
          leaseStartDate: g.basic?.leaseStartDate || '',
          leaseEndDate: g.basic?.leaseEndDate || '',
          minimumLeasePayment: parseNum(g.basic?.minimumLeasePayment),
          unguaranteedResidual: parseNum(g.basic?.unguaranteedResidual),
          fairValue: parseNum(g.basic?.fairValue),
          implicitRate: parseNum(g.basic?.implicitRate),
        },
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
      // 重算公式确保数据一致
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
    validateContinuity,
    getContinuityErrors,
    totalIncome,
    totalVariance,
    addGroup,
    removeGroup,
    addPeriod,
    removePeriod,
    loadData,
    toJSON,
  }
}
