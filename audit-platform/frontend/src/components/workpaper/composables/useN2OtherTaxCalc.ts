/**
 * useN2OtherTaxCalc — N2-8 其他税费测算表 composable
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 3.4
 * Requirements: 5.1-5.5
 *
 * 职责：
 * - 城建税/教育费附加/地方教育附加 3行
 * - Uses calcSurtax from useN2MultiTaxEngine
 * - 计税依据从vatToSurtax获取(N2-6→N2-8)
 * - 城建税税率地区选择(市区7%/县城5%/其他1%)
 *
 * 公式：附加税费 = (增值税 + 消费税) × 适用税率
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { calcSurtax } from './useN2MultiTaxEngine'
import { calcSubtotal } from './useN2FormulaEngine'
import type { ChecklistResponse } from './useN2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 城建税地区类型 */
export type UrbanAreaType = '市区' | '县城' | '其他'

/** 城建税地区→税率映射 */
export const URBAN_RATE_MAP: Record<UrbanAreaType, number> = {
  '市区': 0.07,
  '县城': 0.05,
  '其他': 0.01,
}

/** 附加税种类型 */
export type SurtaxType = '城建税' | '教育费附加' | '地方教育附加'

/** 附加税测算行 */
export interface N2OtherTaxRow {
  /** 税种 */
  taxType: SurtaxType
  /** 计税依据（增值税+消费税） */
  taxBase: number
  /** 适用税率 */
  rate: number
  /** 应交税额（公式：计税依据×税率） */
  amount: number
}

/** 其他税费测算汇总 */
export interface N2OtherTaxSummary {
  /** 计税依据合计（相同，取一次） */
  taxBase: number
  /** 城建税应交 */
  urbanMaintenance: number
  /** 教育费附加应交 */
  educationSurcharge: number
  /** 地方教育附加应交 */
  localEducation: number
  /** 合计应交 */
  total: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 教育费附加税率固定 3% */
const EDUCATION_RATE = 0.03
/** 地方教育附加税率固定 2% */
const LOCAL_EDUCATION_RATE = 0.02

// ─── Helpers ─────────────────────────────────────────────────────────────────

function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseN2OtherTaxCalcOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveField: (sheet: string, field: string, value: any) => Promise<void>
  getField: (sheet: string, field: string) => any
}

export function useN2OtherTaxCalc(options: UseN2OtherTaxCalcOptions) {
  const { allResponses, saveField, getField } = options

  // ─── 1. 城建税地区选择 ────────────────────────────────────────────────────

  /** 当前城建税适用地区 */
  const urbanAreaType: ComputedRef<UrbanAreaType> = computed(() => {
    const stored = getField('8', 'urban-area-type')
    if (stored === '县城' || stored === '其他') return stored
    return '市区' // 默认市区
  })

  /** 城建税适用税率（根据地区） */
  const urbanRate: ComputedRef<number> = computed(() => {
    return URBAN_RATE_MAP[urbanAreaType.value]
  })

  // ─── 2. 计税依据（从N2-6获取应交增值税） ──────────────────────────────────

  /**
   * 计税依据 = 应交增值税 + 消费税
   * 增值税取自 N2-6-vat-payable（vatToSurtax联动）
   * 消费税独立填写
   */
  const taxBase: ComputedRef<number> = computed(() => {
    const vatPayable = parseNum(
      (() => {
        const resp = allResponses.value.get('N2-6-vat-payable')
        if (!resp?.conclusion) return 0
        try { return JSON.parse(resp.conclusion) } catch { return parseNum(resp.conclusion) }
      })(),
    )
    const consumptionTax = parseNum(getField('8', 'consumption-tax'))
    return vatPayable + consumptionTax
  })

  // ─── 3. 三行测算（公式列自动计算） ────────────────────────────────────────

  const rows: ComputedRef<N2OtherTaxRow[]> = computed(() => {
    const base = taxBase.value
    return [
      {
        taxType: '城建税' as SurtaxType,
        taxBase: base,
        rate: urbanRate.value,
        amount: calcSurtax(base, 0, urbanRate.value), // base已含增值税+消费税
      },
      {
        taxType: '教育费附加' as SurtaxType,
        taxBase: base,
        rate: EDUCATION_RATE,
        amount: calcSurtax(base, 0, EDUCATION_RATE),
      },
      {
        taxType: '地方教育附加' as SurtaxType,
        taxBase: base,
        rate: LOCAL_EDUCATION_RATE,
        amount: calcSurtax(base, 0, LOCAL_EDUCATION_RATE),
      },
    ]
  })

  // ─── 4. 汇总 ──────────────────────────────────────────────────────────────

  const summary: ComputedRef<N2OtherTaxSummary> = computed(() => {
    const r = rows.value
    const urbanMaintenance = r[0].amount
    const educationSurcharge = r[1].amount
    const localEducation = r[2].amount
    return {
      taxBase: taxBase.value,
      urbanMaintenance,
      educationSurcharge,
      localEducation,
      total: calcSubtotal([urbanMaintenance, educationSurcharge, localEducation]),
    }
  })

  // ─── 5. 操作 ──────────────────────────────────────────────────────────────

  /**
   * 设置城建税地区类型
   */
  async function setUrbanAreaType(area: UrbanAreaType): Promise<void> {
    await saveField('8', 'urban-area-type', area)
  }

  /**
   * 设置消费税金额（手工录入）
   */
  async function setConsumptionTax(amount: number): Promise<void> {
    await saveField('8', 'consumption-tax', amount)
  }

  /**
   * 同步各附加税测算结果到独立字段（供N2-1回填 + N4联动）
   */
  async function syncResults(): Promise<void> {
    const s = summary.value
    await saveField('8', 'surtax-urban', s.urbanMaintenance)
    await saveField('8', 'surtax-education', s.educationSurcharge)
    await saveField('8', 'surtax-local-education', s.localEducation)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    urbanAreaType,
    urbanRate,
    taxBase,
    rows,
    summary,
    setUrbanAreaType,
    setConsumptionTax,
    syncResults,
  }
}

export default useN2OtherTaxCalc
