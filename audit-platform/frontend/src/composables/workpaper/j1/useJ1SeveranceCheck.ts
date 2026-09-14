/**
 * useJ1SeveranceCheck — J1-10 辞退福利检查表 composable
 *
 * 核心：CAS9辞退福利确认条件（正式计划+不能撤回）+ 精算/抽查
 * Source: J1-10 辞退福利检查表 48行×10列
 *
 * Spec: .kiro/specs/j1-employee-compensation/
 */
import { ref, computed, type Ref } from 'vue'
import { calcSubtotal, parseNum } from './useJ1FormulaEngine'

export interface SeveranceCheckRow {
  id: string
  department: string        // 部门
  employeeCount: number     // 涉及人数
  estimatedAmount: number   // 预计金额
  actualAccrual: number     // 实际计提
  hasFormalPlan: boolean    // 是否有正式计划
  isIrrevocable: boolean   // 是否不可撤回
  actuaryUsed: boolean     // 是否使用精算师
  paymentPeriod: string    // 预计支付期间
  checkResult: string      // 检查结论
}

export interface CAS9Condition {
  label: string
  isMet: boolean
  evidence: string
}

export function useJ1SeveranceCheck(htmlData: Ref<Record<string, unknown>>) {
  const rows: Ref<SeveranceCheckRow[]> = ref([])
  const cas9Conditions: Ref<CAS9Condition[]> = ref([
    { label: '企业已正式制定辞退计划或提出自愿裁减建议', isMet: false, evidence: '' },
    { label: '辞退计划已交沟通并经工会/职代会讨论', isMet: false, evidence: '' },
    { label: '辞退计划具有可操作性(含具体部门/职位/人数/补偿标准/时间)', isMet: false, evidence: '' },
    { label: '企业不能单方面撤回辞退计划', isMet: false, evidence: '' },
  ])

  function initFromHtmlData(data: Record<string, unknown>) {
    const rawRows = (data.severance_check_rows || []) as Array<Record<string, unknown>>
    rows.value = rawRows.map(r => ({
      id: String(r.id || ''),
      department: String(r.department || ''),
      employeeCount: parseNum(r.employee_count as number),
      estimatedAmount: parseNum(r.estimated_amount as number),
      actualAccrual: parseNum(r.actual_accrual as number),
      hasFormalPlan: Boolean(r.has_formal_plan),
      isIrrevocable: Boolean(r.is_irrevocable),
      actuaryUsed: Boolean(r.actuary_used),
      paymentPeriod: String(r.payment_period || ''),
      checkResult: String(r.check_result || ''),
    }))

    if (data.cas9_conditions && Array.isArray(data.cas9_conditions)) {
      cas9Conditions.value = (data.cas9_conditions as Array<Record<string, unknown>>).map(c => ({
        label: String(c.label || ''),
        isMet: Boolean(c.is_met),
        evidence: String(c.evidence || ''),
      }))
    }
  }

  const totalEstimated = computed(() => calcSubtotal(rows.value.map(r => r.estimatedAmount)))
  const totalActual = computed(() => calcSubtotal(rows.value.map(r => r.actualAccrual)))
  const totalEmployees = computed(() => calcSubtotal(rows.value.map(r => r.employeeCount)))
  const allConditionsMet = computed(() => cas9Conditions.value.every(c => c.isMet))

  return {
    rows,
    cas9Conditions,
    totalEstimated,
    totalActual,
    totalEmployees,
    allConditionsMet,
    initFromHtmlData,
  }
}
