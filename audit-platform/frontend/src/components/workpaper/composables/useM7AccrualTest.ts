/**
 * useM7AccrualTest — M7-4 计提测试表 composable
 *
 * Spec: .kiro/specs/m7-special-reserve/
 * Task: 3.4
 * Requirements: 4.1-4.6
 *
 * 职责：
 * - 安全生产费按产量/收入分档计提测试
 * - calcAccrualByOutput: 按产量分档计提 Σ(output×rate)
 * - calcAccrualByRevenue: 按营业收入计提 revenue×rate
 * - calcAccrualDiff: 计提差异=应计提-账面（正差=少提=风险）
 * - 9公式实时计算：
 *   G = E × F（应计金额=基数×比例）
 *   G_total = SUM(各档应计金额)
 *   H = estimated - booked（差异=应计-账面）
 * - 阈值高亮判断（|差异|>阈值→红色）
 * - 与M7-2明细表计提金额交叉核对
 *
 * 科目：4201 专项储备（**贷方/权益类！**）
 * 安全生产费计提（贷方增加）：借:生产成本/管理费用 贷:专项储备
 *
 * 37×19结构，9公式
 */
import { computed, ref, type ComputedRef } from 'vue'
import {
  calcAccrualByOutput,
  calcAccrualByRevenue,
  calcAccrualDiff,
} from './useM7AccrualEngine'
import { calcSubtotal } from './useM7FormulaEngine'
import type { useM7FormData } from './useM7FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 计提基础类型：按产量 / 按营业收入 */
export type AccrualBasis = 'output' | 'revenue'

/** 产量分档数据（煤矿/非煤矿山/危险品等） */
export interface M7AccrualTier {
  /** 档位描述（如"≤100万吨"、">100万吨~≤500万吨"） */
  label: string
  /** 该档产量/基数（E列） */
  output: number
  /** 该档计提标准/比例（F列） */
  rate: number
  /** 应计金额（G列，公式=E×F） */
  amount: number
}

/** 计提测试行数据 */
export interface M7AccrualTestData {
  /** 计提基础类型 */
  basis: AccrualBasis
  /** 企业名称/项目名称 */
  entityName: string
  /** 行业分类 */
  industryCategory: string

  // ─── 按产量模式 ───
  /** 产量分档 */
  tiers: M7AccrualTier[]
  /** 分档合计应计金额 */
  tieredTotal: number

  // ─── 按收入模式 ───
  /** 营业收入（基数） */
  revenue: number
  /** 计提比例 */
  revenueRate: number
  /** 按收入应计金额 */
  revenueAccrual: number

  // ─── 最终汇总 ───
  /** 应计提金额（根据basis取tieredTotal或revenueAccrual） */
  estimated: number
  /** 账面计提金额（企业实际计提） */
  booked: number
  /** 计提差异=应计-账面（正差=少提=风险） */
  diff: number
}

/** 差异阈值配置 */
export interface M7AccrualThreshold {
  /** 绝对值阈值（默认1000元） */
  absolute: number
  /** 相对值阈值（默认5%） */
  relative: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEFAULT_THRESHOLD: M7AccrualThreshold = {
  absolute: 1000,
  relative: 0.05,
}

/** 行业分类选项 */
export const INDUSTRY_CATEGORIES = [
  '煤矿',
  '非煤矿山',
  '危险品生产',
  '危险品储存',
  '烟花爆竹',
  '建筑施工',
  '交通运输—铁路/公路',
  '交通运输—水运',
  '交通运输—民航',
  '冶金',
  '机械制造',
  '武器装备研制',
  '其他',
] as const

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * M7-4 计提测试表业务逻辑（安全生产费按产量/收入分档计提+9公式+阈值高亮）
 *
 * @param formData 由调用方传入的 useM7FormData 实例
 * @param options 配置项
 */
export function useM7AccrualTest(
  formData: ReturnType<typeof useM7FormData>,
  options?: {
    threshold?: M7AccrualThreshold
  },
) {
  const { debouncedSave, saveField } = formData
  const threshold = options?.threshold || DEFAULT_THRESHOLD

  // ─── 1. 响应式状态 ────────────────────────────────────────────────────

  /** 计提基础类型 */
  const basis = ref<AccrualBasis>('output')
  /** 企业/项目名称 */
  const entityName = ref('')
  /** 行业分类 */
  const industryCategory = ref('')

  // ─── 按产量模式 ───
  /** 产量分档 */
  const tiers = ref<M7AccrualTier[]>([
    { label: '第一档', output: 0, rate: 0, amount: 0 },
  ])

  // ─── 按收入模式 ───
  /** 营业收入 */
  const revenue = ref(0)
  /** 计提比例 */
  const revenueRate = ref(0)

  // ─── 账面数据 ───
  /** 账面计提金额（企业实际计提数） */
  const booked = ref(0)

  // ─── 2. 计算属性：9公式全部前端实时计算 ────────────────────────────────

  /** 各档应计金额实时计算：G=E×F */
  const computedTiers: ComputedRef<M7AccrualTier[]> = computed(() => {
    return tiers.value.map(tier => ({
      ...tier,
      amount: tier.output * tier.rate,  // G = E × F
    }))
  })

  /** 分档合计应计金额：G_total = SUM(G) */
  const tieredTotal: ComputedRef<number> = computed(() => {
    return calcAccrualByOutput(
      computedTiers.value.map(t => ({ output: t.output, rate: t.rate })),
    )
  })

  /** 按收入应计金额：revenue × rate */
  const revenueAccrual: ComputedRef<number> = computed(() => {
    return calcAccrualByRevenue(revenue.value, revenueRate.value)
  })

  /** 应计提金额（根据basis取值） */
  const estimated: ComputedRef<number> = computed(() => {
    return basis.value === 'output' ? tieredTotal.value : revenueAccrual.value
  })

  /** 计提差异=应计-账面（正差=少提=风险） */
  const diff: ComputedRef<number> = computed(() => {
    return calcAccrualDiff(estimated.value, booked.value)
  })

  // ─── 3. 聚合数据（供Vue组件渲染） ────────────────────────────────────

  /** 完整计提测试数据 */
  const testData: ComputedRef<M7AccrualTestData> = computed(() => ({
    basis: basis.value,
    entityName: entityName.value,
    industryCategory: industryCategory.value,
    tiers: computedTiers.value,
    tieredTotal: tieredTotal.value,
    revenue: revenue.value,
    revenueRate: revenueRate.value,
    revenueAccrual: revenueAccrual.value,
    estimated: estimated.value,
    booked: booked.value,
    diff: diff.value,
  }))

  // ─── 4. 阈值高亮判断 ──────────────────────────────────────────────────

  /**
   * 判断计提差异是否超阈值（红色高亮）
   * |差异| > absolute 且 相对差异 > relative
   */
  function isDiffExceedThreshold(diffValue: number, estimatedValue: number): boolean {
    if (Math.abs(diffValue) <= threshold.absolute) return false
    if (estimatedValue === 0) return Math.abs(diffValue) > threshold.absolute
    return Math.abs(diffValue / estimatedValue) > threshold.relative
  }

  /** 计提差异是否超阈值（红色高亮） */
  const diffHighlight: ComputedRef<boolean> = computed(() => {
    return isDiffExceedThreshold(diff.value, estimated.value)
  })

  /** 各档差异高亮（用于分档行级高亮） */
  const tierHighlights: ComputedRef<boolean[]> = computed(() => {
    return computedTiers.value.map(tier => {
      // 单档无法独立计算差异，仅在合计层判断
      return false
    })
  })

  // ─── 5. 档位操作 ──────────────────────────────────────────────────────

  /** 新增档位 */
  function addTier(label?: string): void {
    const n = tiers.value.length + 1
    tiers.value.push({
      label: label || `第${n}档`,
      output: 0,
      rate: 0,
      amount: 0,
    })
    _persistAll()
  }

  /** 删除档位 */
  function removeTier(index: number): void {
    if (index < 0 || index >= tiers.value.length) return
    tiers.value.splice(index, 1)
    _persistAll()
  }

  /** 更新档位字段 */
  function updateTier(index: number, field: 'label' | 'output' | 'rate', value: string | number): void {
    if (index < 0 || index >= tiers.value.length) return
    const tier = tiers.value[index] as any
    tier[field] = value
    _persistAll()
  }

  // ─── 6. 字段更新 ──────────────────────────────────────────────────────

  function setBasis(val: AccrualBasis): void {
    basis.value = val
    _persistField('basis', val)
  }

  function setEntityName(val: string): void {
    entityName.value = val
    _persistField('entity-name', val)
  }

  function setIndustryCategory(val: string): void {
    industryCategory.value = val
    _persistField('industry-category', val)
  }

  function setRevenue(val: number): void {
    revenue.value = val
    _persistField('revenue', val)
  }

  function setRevenueRate(val: number): void {
    revenueRate.value = val
    _persistField('revenue-rate', val)
  }

  function setBooked(val: number): void {
    booked.value = val
    _persistField('booked', val)
  }

  // ─── 7. 保存计提测试结果 ──────────────────────────────────────────────

  /** 保存完整计提测试结果 */
  async function saveTestResult(): Promise<void> {
    await saveField('M7-4-test-result', {
      remark: JSON.stringify(testData.value),
    })
  }

  // ─── 8. 内部持久化 ────────────────────────────────────────────────────

  function _persistField(field: string, value: any): void {
    const strVal = typeof value === 'string' ? value : String(value)
    debouncedSave(`M7-4-${field}`, { remark: strVal })
  }

  function _persistAll(): void {
    debouncedSave('M7-4-tiers', {
      remark: JSON.stringify(tiers.value),
    })
    debouncedSave('M7-4-estimated', {
      remark: String(estimated.value),
    })
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 状态
    basis,
    entityName,
    industryCategory,
    tiers,
    revenue,
    revenueRate,
    booked,

    // 计算属性（9公式）
    computedTiers,
    tieredTotal,
    revenueAccrual,
    estimated,
    diff,

    // 聚合数据
    testData,

    // 阈值高亮
    diffHighlight,
    tierHighlights,
    isDiffExceedThreshold,

    // 档位操作
    addTier,
    removeTier,
    updateTier,

    // 字段更新
    setBasis,
    setEntityName,
    setIndustryCategory,
    setRevenue,
    setRevenueRate,
    setBooked,

    // 保存
    saveTestResult,
  }
}

export default useM7AccrualTest
