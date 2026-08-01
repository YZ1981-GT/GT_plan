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
 *           N2-2各税种本期应交 → N4税金及附加（'tax-accrual:updated'）
 *           N2-1审定期末合计 ↔ N2-2审定期末合计（源模板 I22 ↔ P25 交叉验证）
 *
 * 🔴 读取的 item_id 与字段必须与 useN2Adjudication14 / useN2Detail16 的持久化契约一致，
 *    键集收敛在 N2_CROSS_SHEET_ITEM_IDS，守卫见 __tests__/n2CrossSheetContract.spec.ts。
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

/**
 * 🔴 联动读取的 item_id 单一真源 —— 必须与持久化方保持一致，禁写散落字面量。
 *
 * 写入方（唯一权威）：
 * - `N2-1-adjudication-rows`   ← useN2Adjudication14 的 saveField('1', 'adjudication-rows')
 * - `N2-1-end-audited-total`   ← useN2Adjudication14.saveAndSync 的 saveField('1', 'end-audited-total')
 * - `N2-2-detail-rows`         ← useN2Detail16 的 saveField('2', 'detail-rows')
 *
 * 历史坑：本文件曾读旧模型键 `N2-2-rows` 与 `N2-1-end-balance-total`（全库无人写），
 * 且按旧字段名 beginning/accrual/payment/creditAmount 取值 → 两侧恒 0 → diff=0
 * → 勾稽恒报「通过」的**假绿**，比失配更危险。改键时必须同步 crossSheetContract 守卫。
 */
export const N2_CROSS_SHEET_ITEM_IDS = {
  /** N2-1 审定表整行数组（14 列模型 N2Adj14Row 的原始录入字段） */
  adjudicationRows: 'N2-1-adjudication-rows',
  /** N2-1 审定期末合计（saveAndSync 回写，仅作无行数据时的回退） */
  adjudicationEndAuditedTotal: 'N2-1-end-audited-total',
  /** N2-2 明细表整行数组（16 列模型 N2Detail16Row 的原始录入字段） */
  detailRows: 'N2-2-detail-rows',
} as const

/**
 * 税种 → 测算表结果 item_id 映射。
 *
 * 🔴 键必须是 `_normalizeTaxNameForN4` 的**输出名**（规范名），
 *    因为审定侧是把 N2-1 行的 taxType 归一后再按此表逐税种比对（见 adjudicationVsCalcTables）。
 */
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
 * N2-1 审定表单行「期末·审定」派生（源模板 N2-1!I = F+G+H，即 未审+账项调整+重分类）。
 *
 * 派生列不持久化（平台铁律），故此处按原始录入字段现算，使勾稽始终实时。
 * 兼容旧字段名 unadjusted/aje/rje（与 useN2Adjudication14._map14 的兼容口径一致）。
 */
function _adjRowEndAudited(r: any): number {
  return (
    parseNum(r.endUnadj ?? r.unadjusted)
    + parseNum(r.endAje ?? r.aje)
    + parseNum(r.endRje ?? r.rje)
  )
}

/**
 * N2-2 明细表单行「审定·期末」派生（源模板 N2-2!P = M+N−O）：
 * - M 审定期初 = C 未审期初 + G 期初调整
 * - N 审定应交 = D 未审应交 + I 账项调整应交 + K 重分类应交
 * - O 审定已交 = E 未审已交 + J 账项调整已交 + L 重分类已交
 */
function _detailRowAudEnd(r: any): number {
  const m = parseNum(r.unadjBegin) + parseNum(r.beginAdjust)
  const n = parseNum(r.unadjPayable) + parseNum(r.ajePayable) + parseNum(r.rjePayable)
  const o = parseNum(r.unadjPaid) + parseNum(r.ajePaid) + parseNum(r.rjePaid)
  return m + n - o
}

/**
 * N2-2 明细表单行「审定·本期应交」派生（源模板 N2-2!N = D+I+K）。
 * 这是源模板中唯一的「本期应交」口径，供 N4 税金及附加计提核对。
 */
function _detailRowAudPayable(r: any): number {
  return parseNum(r.unadjPayable) + parseNum(r.ajePayable) + parseNum(r.rjePayable)
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
   * 对应源模板勾稽：N2-1!I22（审定期末合计） ↔ N2-2!P25（审定期末合计）
   *
   * 数据来源（键见 N2_CROSS_SHEET_ITEM_IDS）：
   * - N2-1 审定表行数据: "N2-1-adjudication-rows"（conclusion=JSON数组）
   *   回退: "N2-1-end-audited-total"
   * - N2-2 明细表行数据: "N2-2-detail-rows"（conclusion=JSON数组）
   */
  const adjudicationVsDetail: ComputedRef<AdjudicationVsDetailResult> = computed(() => {
    // 审定表期末审定合计。
    // 🔴 优先从行数组现算（源模板 I=F+G+H），使勾稽始终实时；派生列不持久化故必须现算。
    //    仅当无行数据时回退已持久化的 N2-1-end-audited-total（saveAndSync 回写）。
    const adjResp = allResponses.value.get(N2_CROSS_SHEET_ITEM_IDS.adjudicationRows)
    const adjRows = safeParseRows<Record<string, unknown>>(adjResp?.conclusion)
    let adjTotal = 0
    if (adjRows.length > 0) {
      for (const row of adjRows) {
        adjTotal += _adjRowEndAudited(row)
      }
    } else {
      adjTotal = getResponseNum(allResponses.value, N2_CROSS_SHEET_ITEM_IDS.adjudicationEndAuditedTotal)
    }

    // 明细表各行审定期末汇总。
    // 🔴 N2-2-detail-rows 只存原始录入列（unadjBegin/beginAdjust/unadj|aje|rje Payable/Paid），
    //    审定列 M/N/O/P 全是派生列不落库，故必须按源模板 P=M+N−O 现算，不能读 row.audEnd。
    const detailResp = allResponses.value.get(N2_CROSS_SHEET_ITEM_IDS.detailRows)
    const detailRows = safeParseRows<Record<string, unknown>>(detailResp?.conclusion)
    let detailTotal = 0
    for (const row of detailRows) {
      detailTotal += _detailRowAudEnd(row)
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
   * - 审定侧：`N2-1-adjudication-rows` 整行数组 → 按 taxType 归一 → **现算**期末审定数
   *   （源模板 N2-1!I = F+G+H，即 未审+账项调整+重分类；派生列不持久化故必须现算）
   * - 测算侧：各测算表结果 item_id，见 TAX_CALC_TABLE_MAP
   *
   * 🔴 不再读 per-tax 键 `N2-1-{税种}-audited`（本 spec R7.1）：那 6 个键里 5 个**全库无写入方**
   *    → 审定侧恒 0 → 长期假绿。且**不补 per-tax 写入点**（R7.5）—— 审定数的唯一真源是
   *    `N2-1-adjudication-rows` 整行数组，再拆一份单税种标量即构成双真源，两者必然漂移。
   *    故一律按 taxType 现算，与 adjudicationVsDetail / accrualToN4 同口径。
   */
  const adjudicationVsCalcTables: ComputedRef<AdjudicationVsCalcResult[]> = computed(() => {
    // 审定侧：按归一化税种名累计期末审定数（同一税种可能拆多行，须累加）
    const resp = allResponses.value.get(N2_CROSS_SHEET_ITEM_IDS.adjudicationRows)
    const rows = safeParseRows<Record<string, unknown>>(resp?.conclusion)
    const auditedByTax = new Map<string, number>()
    for (const row of rows) {
      const tax = _normalizeTaxNameForN4(String(row.taxType ?? ''))
      if (!tax) continue
      auditedByTax.set(tax, (auditedByTax.get(tax) ?? 0) + _adjRowEndAudited(row))
    }

    const results: AdjudicationVsCalcResult[] = []
    for (const [tax, calcItemId] of Object.entries(TAX_CALC_TABLE_MAP)) {
      const adjAmount = auditedByTax.get(tax) ?? 0
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
   * 汇总N2各税种「本期应交」金额，供N4税金及附加核对。
   * 只输出计入税金及附加的税费（不含增值税/所得税等不进 6403 的税种），并归一化税种名。
   *
   * 🔴 数据源 = N2-2 明细表（源模板 N2-2!N「审定·本期应交」= D+I+K），不是 N2-1 审定表：
   *    源模板 N2-1 是 14 列**双期余额表**（期初/期末各 未审·账项调整·重分类·审定），
   *    压根没有「本期计提/本期应交」列 —— 本期发生额只存在于 N2-2。
   *    旧实现读 N2-1 行的 `creditAmount`（自造模型遗留字段，新模型无此列）→ 恒 0 → N2→N4 联动全断。
   */
  const accrualToN4: ComputedRef<AccrualToN4Item[]> = computed(() => {
    // 不进入税金及附加(6403)的税种（增值税/所得税等），排除
    const EXCLUDED = new Set(['增值税', '企业所得税', '代扣代缴外国企业所得税', '代扣代缴个人所得税', '其他'])
    const resp = allResponses.value.get(N2_CROSS_SHEET_ITEM_IDS.detailRows)
    const rows = safeParseRows<Record<string, unknown>>(resp?.conclusion)
    const items: AccrualToN4Item[] = []
    for (const row of rows) {
      const tax = _normalizeTaxNameForN4(String(row.taxType ?? ''))
      if (!tax || EXCLUDED.has(tax)) continue
      items.push({ tax, amount: _detailRowAudPayable(row) })
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
