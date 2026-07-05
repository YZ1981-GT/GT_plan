/**
 * useG5InstallmentSales — G5-6 分期销售测算(实际利率法)
 */
import { ref, computed } from 'vue'
import {
  parseNum, calcInstallmentFinancingIncome, calcSalesAmortizedCost,
  calcEndingReceivable, calcNetInvestment,
} from '@/composables/useG5FormulaEngine'
import { ElMessageBox } from 'element-plus'

export interface InstallmentInitialData {
  contractTotal: number
  fairValue: number
  unrealizedIncome: number
  effectiveRate: number
  collectionTerm: string
}

export interface InstallmentPeriod {
  id: string
  periodNo: number
  openingReceivable: number
  openingUnrealized: number
  openingAmortizedCost: number
  periodIncome: number
  periodCollection: number
  closingReceivable: number
  closingAmortizedCost: number
}

export interface InstallmentSalesGroup {
  id: string
  projectName: string
  initial: InstallmentInitialData
  periods: InstallmentPeriod[]
}

function createEmptyPeriod(periodNo: number): InstallmentPeriod {
  return {
    id: crypto.randomUUID(), periodNo,
    openingReceivable: 0, openingUnrealized: 0, openingAmortizedCost: 0,
    periodIncome: 0, periodCollection: 0, closingReceivable: 0, closingAmortizedCost: 0,
  }
}

export function useG5InstallmentSales() {
  const groups = ref<InstallmentSalesGroup[]>([])
  const activeTab = ref<'initial' | 'amortization'>('initial')
  const conclusion = ref('')

  function recalcInitial(group: InstallmentSalesGroup) {
    group.initial.unrealizedIncome = parseNum(group.initial.contractTotal) - parseNum(group.initial.fairValue)
  }

  function recalcPeriod(period: InstallmentPeriod, effectiveRate: number) {
    period.openingAmortizedCost = calcNetInvestment(period.openingReceivable, period.openingUnrealized)
    period.periodIncome = calcInstallmentFinancingIncome(period.openingAmortizedCost, effectiveRate)
    period.closingReceivable = calcEndingReceivable(period.openingReceivable, period.periodCollection)
    period.closingAmortizedCost = calcSalesAmortizedCost(
      period.openingAmortizedCost, period.periodIncome, period.periodCollection,
    )
  }

  function recalcGroup(group: InstallmentSalesGroup) {
    recalcInitial(group)
    for (const p of group.periods) recalcPeriod(p, group.initial.effectiveRate)
  }

  function validateContinuity(group: InstallmentSalesGroup): boolean {
    for (let i = 1; i < group.periods.length; i++) {
      const prev = group.periods[i - 1]
      const curr = group.periods[i]
      if (Math.abs(curr.openingReceivable - prev.closingReceivable) > 0.01) return false
    }
    return true
  }

  async function addGroup() {
    const { value } = await ElMessageBox.prompt('请输入销售项目名称', '新增项目', {
      confirmButtonText: '确定', cancelButtonText: '取消',
    })
    if (!value?.trim()) return
    groups.value.push({
      id: crypto.randomUUID(),
      projectName: value.trim(),
      initial: { contractTotal: 0, fairValue: 0, unrealizedIncome: 0, effectiveRate: 0, collectionTerm: '' },
      periods: [createEmptyPeriod(1)],
    })
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
      period.openingUnrealized = parseNum(group.initial.unrealizedIncome) - group.periods.reduce((s, p) => s + parseNum(p.periodIncome), 0)
    }
    group.periods.push(period)
    recalcPeriod(period, group.initial.effectiveRate)
  }

  const totalIncome = computed(() =>
    groups.value.reduce((s, g) => s + g.periods.reduce((ps, p) => ps + parseNum(p.periodIncome), 0), 0),
  )

  function loadData(data: any) {
    if (!data) return
    if (Array.isArray(data.groups)) {
      groups.value = data.groups.map((g: any) => ({
        id: g.id || crypto.randomUUID(),
        projectName: g.projectName || '',
        initial: {
          contractTotal: parseNum(g.initial?.contractTotal),
          fairValue: parseNum(g.initial?.fairValue),
          unrealizedIncome: parseNum(g.initial?.unrealizedIncome),
          effectiveRate: parseNum(g.initial?.effectiveRate),
          collectionTerm: g.initial?.collectionTerm || '',
        },
        periods: Array.isArray(g.periods) ? g.periods.map((p: any, idx: number) => ({
          id: p.id || crypto.randomUUID(),
          periodNo: p.periodNo ?? idx + 1,
          openingReceivable: parseNum(p.openingReceivable),
          openingUnrealized: parseNum(p.openingUnrealized),
          openingAmortizedCost: parseNum(p.openingAmortizedCost),
          periodIncome: parseNum(p.periodIncome),
          periodCollection: parseNum(p.periodCollection),
          closingReceivable: parseNum(p.closingReceivable),
          closingAmortizedCost: parseNum(p.closingAmortizedCost),
        })) : [createEmptyPeriod(1)],
      }))
      for (const g of groups.value) recalcGroup(g)
    }
    if (data.conclusion !== undefined) conclusion.value = data.conclusion
  }

  return {
    groups, activeTab, conclusion, totalIncome,
    recalcInitial, recalcPeriod, recalcGroup, validateContinuity,
    addGroup, removeGroup, addPeriod, loadData,
  }
}
