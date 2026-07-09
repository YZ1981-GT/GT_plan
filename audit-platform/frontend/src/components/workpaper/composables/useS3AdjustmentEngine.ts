/**
 * useS3AdjustmentEngine — S3 首次执行新准则调整 + 简化追溯调整法公式引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 *
 * 本引擎覆盖：
 * - S3-4 首次执行新金融工具准则（41个公式）：调整差异 = 新准则账面 - 原准则账面
 * - S3-8 首次执行新租赁准则（6个公式）：使用权资产 = total - deduction; 租赁负债 = SUM(components)
 * - S3-9/10 简化追溯调整法（137+132公式）：折现计算 pvFactor = 1/(1+rate)^years; pv = amount * pvFactor
 *
 * Spec: .kiro/specs/s-estimate-calculation-workpapers/ Task 3.4
 * Requirements: 6.1
 */

import { computed, type Ref } from 'vue'

// ─── helpers ────────────────────────────────────────────────

/** 安全数值解析：null/undefined/NaN/空→0 */
export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}

// ─── interfaces ─────────────────────────────────────────────

/**
 * S3-4/6 首次执行新准则调整差异输入
 * 每一项包含原准则账面和新准则账面
 */
export interface AdjustmentDiffInput {
  items: Array<{
    oldStandard: number  // 原准则账面
    newStandard: number  // 新准则账面
  }>
}

/**
 * S3-8 首次执行新租赁准则调整输入
 * 使用权资产 = total - deduction
 * 租赁负债 = SUM(components)（正加负减）
 */
export interface LeaseAdjustInput {
  total: number        // 总额
  deduction: number    // 扣除项
  components: number[] // 加减项（正加负减）
}

/**
 * S3-9/10 简化追溯调整法输入
 * 每一项包含原始金额、折现年份、是否到期
 */
export interface SimplifiedRetroInput {
  items: Array<{
    amount: number     // 原始金额
    years: number      // 折现年份
    expired: boolean   // 是否到期
  }>
  discountRate: number // 折现率（小数，如 0.05 表示 5%）
}

// ─── 1. 首次执行新准则调整差异（S3-4/6） ───────────────────

/**
 * 计算首次执行新准则的调整差异
 *
 * 公式：diff = newStandard - oldStandard（新准则账面 - 原准则账面）
 *
 * 来源：S3-4 首次执行新金融工具准则的调整（41个公式）
 *       S3-6 首次执行新收入准则的调整
 *
 * @param i - AdjustmentDiffInput
 * @returns { diffs: 各项差异, totalDiff: 差异合计 }
 */
export function calcAdjustmentDiff(i: AdjustmentDiffInput): {
  diffs: number[]
  totalDiff: number
} {
  if (!i.items || i.items.length === 0) {
    return { diffs: [], totalDiff: 0 }
  }

  const diffs = i.items.map(item => {
    const newVal = parseNum(item.newStandard)
    const oldVal = parseNum(item.oldStandard)
    return newVal - oldVal
  })

  const totalDiff = diffs.reduce((sum, d) => sum + d, 0)

  return { diffs, totalDiff }
}

// ─── 2. 首次执行新租赁准则调整（S3-8） ─────────────────────

/**
 * 计算首次执行新租赁准则的调整
 *
 * 公式：
 * - 使用权资产初始确认 = total - deduction
 * - 租赁负债初始确认 = SUM(components)（正加负减，如 a+b+c-d-e-f-g）
 *
 * 来源：S3-8 首次执行新租赁准则的调整（6个公式）
 *       F55 = F53 - F54（使用权资产）
 *       F63 = F56+F57+F58-F59-F60-F61-F62（租赁负债）
 *
 * @param i - LeaseAdjustInput
 * @returns { rouAsset: 使用权资产, leaseLiability: 租赁负债 }
 */
export function calcLeaseAdjust(i: LeaseAdjustInput): {
  rouAsset: number
  leaseLiability: number
} {
  const total = parseNum(i.total)
  const deduction = parseNum(i.deduction)

  const rouAsset = total - deduction

  const components = i.components || []
  const leaseLiability = components.reduce((sum, c) => sum + parseNum(c), 0)

  return { rouAsset, leaseLiability }
}

// ─── 3. 简化追溯调整法折现计算（S3-9/10） ──────────────────

/**
 * 计算简化追溯调整法的折现现值
 *
 * 公式：
 * - 现值折现因子 pvFactor = 1 / (1 + rate) ^ years
 * - 现值 pv = amount * pvFactor
 * - 条件公式 conditional = expired ? 0 : amount（到期则现值=0）
 *
 * 特殊规则：
 * - discountRate = 0 → pvFactor = 1（无折现，不是错误）
 * - expired = true → pv = 0
 * - 空数组 → totalPV = 0
 * - 不抛异常，不返回 NaN/Infinity
 *
 * 来源：S3-9 简化追溯调整法（137个公式）
 *       S3-10 简化追溯调整法-变体（132个公式）
 *       H{r} = 1/(1+$H$10)^G{r}
 *       I{r} = B{r} * H{r}
 *       C{r} = IF(E{r}=1, 0, B{r})
 *
 * @param i - SimplifiedRetroInput
 * @returns { pvFactors: 各项折现因子, pvAmounts: 各项现值, totalPV: 现值合计 }
 */
export function calcSimplifiedRetro(i: SimplifiedRetroInput): {
  pvFactors: number[]
  pvAmounts: number[]
  totalPV: number
} {
  if (!i.items || i.items.length === 0) {
    return { pvFactors: [], pvAmounts: [], totalPV: 0 }
  }

  const rate = parseNum(i.discountRate)

  const pvFactors: number[] = []
  const pvAmounts: number[] = []

  for (const item of i.items) {
    const amount = parseNum(item.amount)
    const years = parseNum(item.years)
    const expired = item.expired === true

    // 到期项：现值为 0
    if (expired) {
      pvFactors.push(0)
      pvAmounts.push(0)
      continue
    }

    // 计算折现因子：pvFactor = 1 / (1 + rate) ^ years
    // rate = 0 时 pvFactor = 1（不折现）
    let pvFactor: number
    if (rate === 0) {
      pvFactor = 1
    } else {
      const base = 1 + rate
      const power = Math.pow(base, years)
      // 防御 Infinity（极端 years 值时）
      if (!Number.isFinite(power) || power === 0) {
        pvFactor = 0
      } else {
        pvFactor = 1 / power
      }
    }

    // 确保 pvFactor 有限
    if (!Number.isFinite(pvFactor)) {
      pvFactor = 0
    }

    const pv = amount * pvFactor

    // 确保 pv 有限
    pvFactors.push(Number.isFinite(pv) ? pvFactor : 0)
    pvAmounts.push(Number.isFinite(pv) ? pv : 0)
  }

  const totalPV = pvAmounts.reduce((sum, pv) => sum + pv, 0)

  return { pvFactors, pvAmounts, totalPV }
}

// ─── composable wrapper ─────────────────────────────────────

/**
 * Vue composable wrapper — 将纯函数以 reactive 方式暴露给组件
 *
 * 使用方式：
 * ```ts
 * const { adjustmentDiff, leaseAdjust, simplifiedRetro } = useS3AdjustmentEngine(
 *   adjDiffInputRef, leaseInputRef, retroInputRef
 * )
 * ```
 */
export function useS3AdjustmentEngine(
  adjDiffInput?: Ref<AdjustmentDiffInput>,
  leaseInput?: Ref<LeaseAdjustInput>,
  retroInput?: Ref<SimplifiedRetroInput>,
) {
  const adjustmentDiff = computed(() => {
    if (!adjDiffInput?.value) return { diffs: [], totalDiff: 0 }
    return calcAdjustmentDiff(adjDiffInput.value)
  })

  const leaseAdjust = computed(() => {
    if (!leaseInput?.value) return { rouAsset: 0, leaseLiability: 0 }
    return calcLeaseAdjust(leaseInput.value)
  })

  const simplifiedRetro = computed(() => {
    if (!retroInput?.value) return { pvFactors: [], pvAmounts: [], totalPV: 0 }
    return calcSimplifiedRetro(retroInput.value)
  })

  return {
    // 纯函数（直接导出供独立调用）
    calcAdjustmentDiff,
    calcLeaseAdjust,
    calcSimplifiedRetro,
    parseNum,
    // reactive computeds
    adjustmentDiff,
    leaseAdjust,
    simplifiedRetro,
  }
}
