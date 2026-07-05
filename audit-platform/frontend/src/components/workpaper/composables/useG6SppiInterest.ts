/**
 * useG6SppiInterest — G6-6 利息测算表（实际利率法分组结构）
 *
 * Spec: .kiro/specs/g6-other-bond-investment-sppi/ Task 5.1
 * Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 7.1
 *
 * 职责：
 * - 投资项目分组结构（每项目多期）
 * - calcEffectiveInterest / calcCashInflow / calcEndingAmortized per period
 * - 链式计算（上期末 = 下期初）
 * - 合计汇总 + 交叉验证（利息合计 vs G6-1审定数）
 * - 动态行管理（新增项目ElMessageBox.prompt / 新增期间 / 删除）
 */
import { ref, computed, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import {
  calcEffectiveInterest,
  calcCashInflow,
  calcEndingAmortized,
  parseNum,
} from '@/composables/useG6SppiFormulaEngine'

// ─── 数据模型 ────────────────────────────────────────────────────────────────

/** 单期利息计算 */
export interface InterestPeriod {
  id: string
  periodEnd: string          // 截止日（如 "2024-06-30"）
  openingAmortized: number   // 期初摊余成本
  effectiveInterest: number  // 实际利息收入（公式）
  cashInflow: number         // 现金流入（公式）
  endingAmortized: number    // 期末摊余成本（公式）
  days: number               // 计息天数
  remark: string             // 备注
}

/** 投资项目分组 */
export interface InterestGroup {
  id: string
  investProject: string      // 投资项目名称
  faceValue: number          // 面值
  couponRate: number         // 票面利率（如 0.04 = 4%）
  effectiveRate: number      // 实际利率（如 0.05 = 5%）
  periods: InterestPeriod[]  // 多期利息计算
}

/** 完整数据结构 */
export interface InterestCalculationData {
  groups: InterestGroup[]
  conclusion: string
  crossValidation: {
    totalInterest: number       // 利息合计（本表计算）
    auditedInterest: number     // G6-1审定数（外部输入）
    difference: number          // 差异
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useG6SppiInterest() {
  const groups = ref<InterestGroup[]>([])
  const conclusion = ref('')
  const auditedInterest = ref(0) // G6-1利息审定数（外部数据）

  // ─── 公式计算 ──────────────────────────────────────────────────────────────

  /** 重算单期公式列 */
  function recalcPeriod(period: InterestPeriod, group: InterestGroup): void {
    period.effectiveInterest = calcEffectiveInterest(
      parseNum(period.openingAmortized),
      parseNum(group.effectiveRate),
      parseNum(period.days),
    )
    period.cashInflow = calcCashInflow(
      parseNum(group.faceValue),
      parseNum(group.couponRate),
      parseNum(period.days),
    )
    period.endingAmortized = calcEndingAmortized(
      parseNum(period.openingAmortized),
      period.effectiveInterest,
      period.cashInflow,
    )
  }

  /** 重算整组（链式：上期末 = 下期初） */
  function recalcGroup(group: InterestGroup): void {
    for (let i = 0; i < group.periods.length; i++) {
      const period = group.periods[i]
      // 第一期之后，上期末摊余 = 本期初摊余
      if (i > 0) {
        period.openingAmortized = group.periods[i - 1].endingAmortized
      }
      recalcPeriod(period, group)
    }
  }

  /** 重算所有组 */
  function recalcAll(): void {
    for (const group of groups.value) {
      recalcGroup(group)
    }
  }

  // watch groups 变化时自动重算
  watch(groups, () => {
    recalcAll()
  }, { deep: true })

  // ─── 合计计算 ──────────────────────────────────────────────────────────────

  /** 全部利息合计 */
  const totalInterest = computed(() => {
    let sum = 0
    for (const group of groups.value) {
      for (const period of group.periods) {
        sum += parseNum(period.effectiveInterest)
      }
    }
    return Math.round(sum * 100) / 100
  })

  /** 交叉验证差异 */
  const crossValidationDiff = computed(() => {
    return Math.round((totalInterest.value - parseNum(auditedInterest.value)) * 100) / 100
  })

  /** 交叉验证是否通过（差异=0） */
  const crossValidationPassed = computed(() => {
    return Math.abs(crossValidationDiff.value) < 0.01
  })

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

      const newGroup: InterestGroup = {
        id: `ig-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        investProject: value.trim(),
        faceValue: 0,
        couponRate: 0,
        effectiveRate: 0,
        periods: [],
      }
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

    // 默认继承上一期的期末摊余作为本期期初
    const lastPeriod = group.periods[group.periods.length - 1]
    const openingAmortized = lastPeriod ? lastPeriod.endingAmortized : parseNum(group.faceValue)

    const newPeriod: InterestPeriod = {
      id: `ip-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      periodEnd: '',
      openingAmortized,
      effectiveInterest: 0,
      cashInflow: 0,
      endingAmortized: 0,
      days: 180,
      remark: '',
    }
    group.periods.push(newPeriod)
    recalcGroup(group)
  }

  /** 删除期间 */
  function removePeriod(groupId: string, periodId: string): void {
    const group = groups.value.find(g => g.id === groupId)
    if (!group) return
    group.periods = group.periods.filter(p => p.id !== periodId)
    // 重算链式
    recalcGroup(group)
  }

  /** 更新组头信息 */
  function updateGroupHeader(groupId: string, field: keyof InterestGroup, value: any): void {
    const group = groups.value.find(g => g.id === groupId)
    if (!group) return
    ;(group as any)[field] = value
    recalcGroup(group)
  }

  /** 更新期间字段 */
  function updatePeriod(groupId: string, periodId: string, field: keyof InterestPeriod, value: any): void {
    const group = groups.value.find(g => g.id === groupId)
    if (!group) return
    const period = group.periods.find(p => p.id === periodId)
    if (!period) return
    ;(period as any)[field] = value
    recalcGroup(group)
  }

  // ─── 数据加载/导出 ─────────────────────────────────────────────────────────

  function loadData(data: InterestCalculationData | null): void {
    if (!data?.groups?.length) {
      groups.value = []
      conclusion.value = data?.conclusion || ''
      auditedInterest.value = data?.crossValidation?.auditedInterest || 0
      return
    }

    groups.value = data.groups.map(g => ({
      id: g.id || `ig-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      investProject: g.investProject || '',
      faceValue: parseNum(g.faceValue),
      couponRate: parseNum(g.couponRate),
      effectiveRate: parseNum(g.effectiveRate),
      periods: (g.periods || []).map(p => ({
        id: p.id || `ip-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        periodEnd: p.periodEnd || '',
        openingAmortized: parseNum(p.openingAmortized),
        effectiveInterest: 0,
        cashInflow: 0,
        endingAmortized: 0,
        days: parseNum(p.days) || 180,
        remark: p.remark || '',
      })),
    }))
    conclusion.value = data.conclusion || ''
    auditedInterest.value = data.crossValidation?.auditedInterest || 0
    recalcAll()
  }

  function toJSON(): InterestCalculationData {
    return {
      groups: groups.value.map(g => ({ ...g, periods: g.periods.map(p => ({ ...p })) })),
      conclusion: conclusion.value,
      crossValidation: {
        totalInterest: totalInterest.value,
        auditedInterest: auditedInterest.value,
        difference: crossValidationDiff.value,
      },
    }
  }

  // ─── 单组利息小计 ──────────────────────────────────────────────────────────

  /** 单个投资项目利息合计 */
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
    // State
    groups,
    conclusion,
    auditedInterest,
    // Computed
    totalInterest,
    crossValidationDiff,
    crossValidationPassed,
    // Methods
    recalcPeriod,
    recalcGroup,
    recalcAll,
    addGroup,
    removeGroup,
    addPeriod,
    removePeriod,
    updateGroupHeader,
    updatePeriod,
    getGroupInterestTotal,
    loadData,
    toJSON,
  }
}

export default useG6SppiInterest
