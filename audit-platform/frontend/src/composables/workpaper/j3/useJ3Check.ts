/**
 * useJ3Check — J3-2 股份支付检查表 composable
 *
 * 管理 19列检查表段落型数据：
 * - 授予条件核验 / 公允价值确定 / 等待期费用 / 行权 / 修改 / 取消
 * - Black-Scholes 参数逐项验证
 * - CAS11 合规检查
 *
 * Spec: .kiro/specs/j3-share-based-payment/
 * Requirements: 5.1-5.5
 */
import { ref, computed, type Ref } from 'vue'
import { validateBSParams, type BSParams } from './useJ3OptionPricingEngine'

export interface J3CheckSection {
  id: string
  title: string
  description: string
  items: J3CheckItem[]
}

export interface J3CheckItem {
  id: string
  label: string
  value: string
  conclusion: '符合' | '不符合' | '不适用' | ''
  note: string
  aiGenerated?: boolean
}

export interface J3BSParamCheck {
  param: string
  label: string
  value: number
  isReasonable: boolean
  warning: string
}

export function useJ3Check(plans: Ref<Array<{ type: string; name: string }>>) {
  const sections = ref<J3CheckSection[]>([
    {
      id: 'grant-conditions',
      title: '一、授予条件核验',
      description: '检查股份支付方案授予条件是否满足CAS11要求',
      items: [
        { id: 'gc-1', label: '是否为雇员或提供类似服务的人员', value: '', conclusion: '', note: '' },
        { id: 'gc-2', label: '授权日与行权日之间是否存在重大时间间隔', value: '', conclusion: '', note: '' },
        { id: 'gc-3', label: '主要条款及条件与股份支付工具是否一致', value: '', conclusion: '', note: '' },
      ],
    },
    {
      id: 'fair-value',
      title: '二、公允价值确定',
      description: '检查权益工具公允价值的确定方法和参数',
      items: [
        { id: 'fv-1', label: '公允价值确定方法（BS模型/二叉树/其他）', value: '', conclusion: '', note: '' },
        { id: 'fv-2', label: '标的价格来源及合理性', value: '', conclusion: '', note: '' },
        { id: 'fv-3', label: '行权价格确定依据', value: '', conclusion: '', note: '' },
        { id: 'fv-4', label: '波动率计算方法及期间选取', value: '', conclusion: '', note: '' },
        { id: 'fv-5', label: '无风险利率选取依据', value: '', conclusion: '', note: '' },
        { id: 'fv-6', label: '预期期限确定', value: '', conclusion: '', note: '' },
        { id: 'fv-7', label: '预期股息率', value: '', conclusion: '', note: '' },
      ],
    },
    {
      id: 'vesting-expense',
      title: '三、等待期费用确认',
      description: '检查各期费用确认金额的准确性',
      items: [
        { id: 've-1', label: '等待期内每期确认费用计算', value: '', conclusion: '', note: '' },
        { id: 've-2', label: '费用分配对象（管理费用/销售费用/生产成本）', value: '', conclusion: '', note: '' },
        { id: 've-3', label: '在可行权日调整至实际可行权水平', value: '', conclusion: '', note: '' },
      ],
    },
    {
      id: 'exercise',
      title: '四、行权/修改/取消',
      description: '检查行权、修改及取消的会计处理',
      items: [
        { id: 'ex-1', label: '行权时的会计处理', value: '', conclusion: '', note: '' },
        { id: 'ex-2', label: '协议变更处理（增减公允价值）', value: '', conclusion: '', note: '' },
        { id: 'ex-3', label: '取消/失效处理', value: '', conclusion: '', note: '' },
      ],
    },
    {
      id: 'settlement-type',
      title: '五、结算方式分类',
      description: '检查权益结算与现金结算的分类正确性',
      items: [
        { id: 'st-1', label: '结算方式分类（权益/现金/组合）', value: '', conclusion: '', note: '' },
        { id: 'st-2', label: '现金结算每个资产负债表日重新计量', value: '', conclusion: '', note: '' },
        { id: 'st-3', label: '权益结算锁定授予日公允价值', value: '', conclusion: '', note: '' },
      ],
    },
  ])

  // ── BS参数验证 ─────────────────────────────────────────────────────────────

  const bsParams = ref<BSParams>({ S: 0, K: 0, T: 0, r: 0, sigma: 0 })

  const bsValidation = computed(() => validateBSParams(bsParams.value))

  const bsParamChecks = computed<J3BSParamCheck[]>(() => {
    const p = bsParams.value
    const checks: J3BSParamCheck[] = [
      { param: 'S', label: '标的价格', value: p.S, isReasonable: p.S > 0, warning: p.S <= 0 ? '必须>0' : '' },
      { param: 'K', label: '行权价格', value: p.K, isReasonable: p.K > 0, warning: p.K <= 0 ? '必须>0' : '' },
      { param: 'T', label: '预期期限(年)', value: p.T, isReasonable: p.T > 0, warning: p.T <= 0 ? '必须>0' : '' },
      { param: 'r', label: '无风险利率', value: p.r, isReasonable: p.r >= 0.01 && p.r <= 0.10, warning: p.r < 0.01 ? '偏低' : p.r > 0.10 ? '偏高' : '' },
      { param: 'sigma', label: '波动率', value: p.sigma, isReasonable: p.sigma >= 0.10 && p.sigma <= 1.0, warning: p.sigma < 0.10 ? '偏低' : p.sigma > 1.0 ? '偏高' : '' },
    ]
    return checks
  })

  // ── 检查项更新 ─────────────────────────────────────────────────────────────

  function updateCheckItem(sectionId: string, itemId: string, updates: Partial<J3CheckItem>) {
    const section = sections.value.find(s => s.id === sectionId)
    if (!section) return
    const item = section.items.find(i => i.id === itemId)
    if (item) Object.assign(item, updates)
  }

  // ── 整体结论 ──────────────────────────────────────────────────────────────

  const overallConclusion = computed(() => {
    const allItems = sections.value.flatMap(s => s.items)
    const hasNonCompliance = allItems.some(i => i.conclusion === '不符合')
    const allChecked = allItems.every(i => i.conclusion !== '')
    if (hasNonCompliance) return '存在不符合事项'
    if (allChecked) return '全部符合'
    return '检查进行中'
  })

  return {
    sections,
    bsParams,
    bsValidation,
    bsParamChecks,
    overallConclusion,
    updateCheckItem,
  }
}
