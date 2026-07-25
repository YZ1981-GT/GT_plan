/**
 * useN2CrossSheet — N2 应交税费跨sheet引擎 + N4税金及附加联动
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 3.2
 * Requirements: 2.5, 2.6, 4.5, 5.3, 5.4, 6.3, 7.5, 8.4, 11.1-11.4
 *
 * 职责：
 * 1. adjudicationVsDetail — N2-1审定表合计 vs N2-2明细表合计 勾稽校验
 * 2. adjudicationVsCalcTables — N2-1各税种行 vs 对应测算表(N2-6/N2-8/N2-9/N2-10)交叉验证
 * 3. vatToSurtax — N2-6增值税测算结果 → N2-8城建税计税依据（应交增值税 feeds surtax）
 * 4. accrualToN4 — 各税种计提额 → N4税金及附加 EventBus publish
 *
 * 联动方向：N2-6增值税 → N2-8城建税及附加计税依据
 *           N2各税种计提 → N4税金及附加（'tax-accrual:updated'）
 *           N2-1审定 → N2-2明细（合计交叉验证）
 *
 * 科目：2221 应交税费（贷方/负债类！期末=期初+贷方-借方）
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistResponse } from './useN2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表 vs 明细表 勾稽结果 */
export interface AdjudicationVsDetailResult {
  /** 差额 = 审定表合计 - 明细表合计 */
  diff: number
  /** 差额绝对值 ≤ 阈值 视为匹配 */
  isMatch: boolean
}

/** 审定表 vs 测算表 逐税种交叉验证结果 */
export interface AdjudicationVsCalcResult {
  /** 税种名称 */
  tax: string
  /** 差额 = 审定表行金额 - 测算表结果金额 */
  diff: number
  /** 差额绝对值 ≤ 阈值 视为匹配 */
  isMatch: boolean
}

/** N2-6 → N2-8 增值税计税依据 */
export interface VatToSurtaxResult {
  /** N2-8城建税及附加的计税依据（=N2-6应交增值税） */
  base: number
}

/** 计提 → N4 联动载荷 */
export interface AccrualToN4Item {
  /** 税种名称 */
  tax: string
  /** 本期计提金额 */
  amount: number
}

/** EventBus 'tax-accrual:updated' 载荷 */
export interface TaxAccrualUpdatedPayload {
  wpCode: string
  accruals: AccrualToN4Item[]
  totalAccrual: number
  timestamp: number
}

/** 跨底稿引用定义 */
export interface CrossWpReference {
  /** 目标底稿编码 */
  targetWpCode: string
  /** 引用说明 */
  label: string
  /** 引用方向：from=从目标引入, to=输出到目标 */
  direction: 'from' | 'to'
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 勾稽匹配阈值（0.01元内视为匹配） */
const MATCH_THRESHOLD = 0.01

/** 税种 → 测算表 item_id 前缀映射 */
const TAX_CALC_TABLE_MAP: Record<string, string> = {
  '增值税': 'N2-6-vat-payable',
  '城建税': 'N2-8-surtax-urban',
  '教育费附加': 'N2-8-surtax-education',
  '地方教育附加': 'N2-8-surtax-local-education',
  '房产税': 'N2-9-property-tax-total',
  '土地增值税': 'N2-10-lvt-total',
}

/** N4联动的税种列表（计入税金及附加的税费） */
const N4_ACCRUAL_TAXES = [
  '城建税',
  '教育费附加',
  '地方教育附加',
  '房产税',
  '土地使用税',
  '印花税',
  '土地增值税',
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 安全解析数字，NaN/null/undefined → 0
 */
function parseNum(v: any): number {
  if (v == null) return 0
  if (typeof v === 'string') {
    try {
      v = JSON.parse(v)
    } catch {
      // not JSON, try direct parse
    }
  }
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/**
 * 从 allResponses 获取指定 item_id 的 conclusion 数值
 */
function getResponseNum(allResponses: Map<string, ChecklistResponse>, itemId: string): number {
  const resp = allResponses.get(itemId)
  return parseNum(resp?.conclusion)
}

/**
 * 安全解析 JSON 数组字符串，失败回退空数组
 */
function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/**
 * 税种名称归一化（供 N4 联动匹配）。消除 N2/N4 命名分歧：
 * 城市维护建设税/城建税 → 城建税；土地使用税/城镇土地使用税 → 土地使用税；
 * 车船牌照税/车船使用税/车船税 → 车船税；企业所得税/所得税 → 企业所得税；未交增值税/增值税 → 增值税。
 * 输出名与 useN4CrossSheet.TAX_TYPES / _normalizeTaxName 对齐（车船税/土地使用税/城建税作 N4 侧规范名）。
 */
function _normalizeTaxNameForN4(name: string): string {
  const s = String(name ?? '').trim()
  if (s === '城建税' || s === '城市维护建设税') return '城建税'
  if (s === '土地使用税' || s === '城镇土地使用税') return '土地使用税'
  if (s === '车船税' || s === '车船使用税' || s === '车船牌照税') return '车船税'
  if (s === '企业所得税' || s === '所得税') return '企业所得税'
  if (s === '增值税' || s === '未交增值税') return '增值税'
  return s
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * N2 跨sheet引擎 + N4税金及附加联动
 *
 * @param allResponses - 全部 checklist_responses（来自 useN2FormData）
 */
export function useN2CrossSheet(allResponses: Ref<Map<string, ChecklistResponse>>) {
  // ─── 上次发布的计提合计（用于变化检测，仅变化时发布） ─────────────────────
  const _lastPublishedTotal = ref<number | null>(null)

  // ─── 1. adjudicationVsDetail — N2-1审定表合计 vs N2-2明细表合计 ─────────

  /**
   * N2-1 审定表应交税费合计 应= N2-2 明细表各税种期末合计
   * 差额 = 审定表合计 - 明细表合计
   *
   * 数据来源：
   * - N2-1 审定表期末合计: item_id "N2-1-end-balance-total"
   * - N2-2 明细表行数据: item_id "N2-2-rows"（conclusion=JSON数组）
   */
  const adjudicationVsDetail: ComputedRef<AdjudicationVsDetailResult> = computed(() => {
    // 审定表期末合计。
    // 🔴 优先直接从 N2-1-adjudication-rows 现算（负债类 期末=期初+贷-借），使勾稽始终实时；
    //    仅当无行数据时回退已持久化的 N2-1-end-balance-total（saveAndSync 在回写时写入）。
    const adjResp = allResponses.value.get('N2-1-adjudication-rows')
    const adjRows = safeParseRows<{ beginning?: number; creditAmount?: number; debitAmount?: number; endBalance?: number }>(adjResp?.conclusion)
    let adjTotal = 0
    if (adjRows.length > 0) {
      for (const row of adjRows) {
        adjTotal += row.endBalance != null
          ? parseNum(row.endBalance)
          : parseNum(row.beginning) + parseNum(row.creditAmount) - parseNum(row.debitAmount)
      }
    } else {
      adjTotal = getResponseNum(allResponses.value, 'N2-1-end-balance-total')
    }

    // 明细表各行期末余额汇总。
    // 🔴 N2-2-rows 存储的是原始录入字段（beginning/accrual/payment），不含计算列 endBalance，
    //    故不能直接读 row.endBalance（恒 undefined→0），须按负债类公式 期末=期初+计提(贷)-缴纳(借) 现算。
    const detailResp = allResponses.value.get('N2-2-rows')
    const detailRows = safeParseRows<{ beginning?: number; accrual?: number; payment?: number; endBalance?: number }>(detailResp?.conclusion)
    let detailTotal = 0
    for (const row of detailRows) {
      const endBalance = row.endBalance != null
        ? parseNum(row.endBalance)
        : parseNum(row.beginning) + parseNum(row.accrual) - parseNum(row.payment)
      detailTotal += endBalance
    }

    const diff = parseFloat((adjTotal - detailTotal).toFixed(2))
    return {
      diff,
      isMatch: Math.abs(diff) <= MATCH_THRESHOLD,
    }
  })

  // ─── 2. adjudicationVsCalcTables — N2-1各税种行 vs 测算表结果 ──────────

  /**
   * N2-1 审定表各税种行的审定数 应= 对应测算表(N2-6/N2-8/N2-9/N2-10)的测算结果
   *
   * 映射关系：
   * - 增值税行 ↔ N2-6 增值税测算结果
   * - 城建税行 ↔ N2-8 城建税测算结果
   * - 教育费附加行 ↔ N2-8 教育费附加测算结果
   * - 地方教育附加行 ↔ N2-8 地方教育附加测算结果
   * - 房产税行 ↔ N2-9 房产税测算结果
   * - 土地增值税行 ↔ N2-10 土增税测算结果
   *
   * 数据来源：
   * - N2-1 审定表各税种行: item_id "N2-1-{税种英文}-audited"
   * - 各测算表结果: item_id 见 TAX_CALC_TABLE_MAP
   */
  const adjudicationVsCalcTables: ComputedRef<AdjudicationVsCalcResult[]> = computed(() => {
    const results: AdjudicationVsCalcResult[] = []

    // 审定表税种行 item_id 映射
    const adjudicationKeys: Record<string, string> = {
      '增值税': 'N2-1-vat-audited',
      '城建税': 'N2-1-urban-maintenance-audited',
      '教育费附加': 'N2-1-education-surcharge-audited',
      '地方教育附加': 'N2-1-local-education-audited',
      '房产税': 'N2-1-property-tax-audited',
      '土地增值税': 'N2-1-lvt-audited',
    }

    for (const [tax, adjItemId] of Object.entries(adjudicationKeys)) {
      const calcItemId = TAX_CALC_TABLE_MAP[tax]
      if (!calcItemId) continue

      const adjAmount = getResponseNum(allResponses.value, adjItemId)
      const calcAmount = getResponseNum(allResponses.value, calcItemId)

      const diff = parseFloat((adjAmount - calcAmount).toFixed(2))
      results.push({
        tax,
        diff,
        isMatch: Math.abs(diff) <= MATCH_THRESHOLD,
      })
    }

    return results
  })

  // ─── 3. vatToSurtax — N2-6增值税 → N2-8城建税计税依据 ─────────────────

  /**
   * N2-6 增值税测算表的应交增值税 → N2-8 城建税及附加的计税依据
   * 城建税=(增值税+消费税)×税率，计税依据中增值税部分取自N2-6
   *
   * 数据来源：
   * - N2-6 应交增值税: item_id "N2-6-vat-payable"
   */
  const vatToSurtax: ComputedRef<VatToSurtaxResult> = computed(() => {
    const vatPayable = getResponseNum(allResponses.value, 'N2-6-vat-payable')
    return {
      base: vatPayable,
    }
  })

  // ─── 4. accrualToN4 — 各税种计提额 → N4税金及附加 ─────────────────────

  /**
   * 汇总N2各税种本期计提金额（本期贷方发生额 creditAmount），供N4税金及附加核对。
   * 只输出计入税金及附加的税费（不含增值税/所得税等不进 6403 的税种），并归一化税种名。
   *
   * 🔴 数据来源修正：useN2Adjudication 存储整行数组于 "N2-1-adjudication-rows"（不写 per-tax
   *    "N2-1-{税种}-accrual"），故须从行数组现算，否则读 per-tax 键恒 0 → N4↔N2 勾稽全断。
   */
  const accrualToN4: ComputedRef<AccrualToN4Item[]> = computed(() => {
    // 不进入税金及附加(6403)的税种（增值税/所得税等），排除
    const EXCLUDED = new Set(['增值税', '企业所得税', '代扣代缴外国企业所得税', '代扣代缴个人所得税', '其他'])
    const resp = allResponses.value.get('N2-1-adjudication-rows')
    const rows = safeParseRows<{ taxType?: string; creditAmount?: number }>(resp?.conclusion)
    const items: AccrualToN4Item[] = []
    for (const row of rows) {
      const tax = _normalizeTaxNameForN4(String(row.taxType ?? ''))
      if (!tax || EXCLUDED.has(tax)) continue
      items.push({ tax, amount: parseNum(row.creditAmount) })
    }
    return items
  })

  // ─── 5. publishTaxAccrualUpdated — EventBus 发布 ───────────────────────

  /**
   * 发布 'tax-accrual:updated' 事件到 EventBus。
   * 仅在值变化时发布（避免重复广播）。
   *
   * 载荷：wpCode / 各税种计提明细 / 计提合计 / 时间戳
   * N4税金及附加 订阅用于费用确认核对。
   */
  function publishTaxAccrualUpdated(): void {
    const accruals = accrualToN4.value
    const totalAccrual = accruals.reduce((sum, item) => sum + item.amount, 0)
    const roundedTotal = parseFloat(totalAccrual.toFixed(2))

    // 仅在值变化时发布
    if (_lastPublishedTotal.value === roundedTotal) return
    _lastPublishedTotal.value = roundedTotal

    const payload: TaxAccrualUpdatedPayload = {
      wpCode: 'N2',
      accruals: accruals.filter(a => a.amount !== 0),
      totalAccrual: roundedTotal,
      timestamp: Date.now(),
    }

    eventBus.emit('tax-accrual:updated', payload)
  }

  // ─── 6. 跨底稿引用定义 ────────────────────────────────────────────────

  /** N2 应交税费 cross_wp_references（关联 N4） */
  const cross_wp_references: CrossWpReference[] = [
    {
      targetWpCode: 'N4',
      label: 'N4税金及附加-计提核对',
      direction: 'to',
    },
  ]

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // 核心勾稽
    adjudicationVsDetail,
    adjudicationVsCalcTables,
    // N2-6 → N2-8 联动
    vatToSurtax,
    // N4计提联动
    accrualToN4,
    publishTaxAccrualUpdated,
    // 跨底稿引用
    cross_wp_references,
  }
}

export default useN2CrossSheet
