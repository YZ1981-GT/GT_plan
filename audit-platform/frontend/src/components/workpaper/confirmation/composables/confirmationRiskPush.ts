/**
 * confirmationRiskPush.ts — 函证枢纽两条风险推送通道的载荷构建（纯函数）
 *
 * 由 `f0FraudRiskPush.ts` 重写而来（f0-confirmation-linkage-and-structural-enhancement Task 32）。
 * 改名理由：消费方 `FraudRiskSummary.vue` / `DiffReconcileMaster.vue` 是
 * **七枢纽共享组件**（D0/E0/F0/G0/H0/K0/L0），挂 `f0` 前缀会误导下个会话以为是 F0 私有件。
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * 🔴🔴 重写背景（2026-08-04 实证，推翻 Task 11/12/13 的「待平台级共享件」结论）
 * ─────────────────────────────────────────────────────────────────────────────
 * 旧模块 `f0FraudRiskPush.ts` 是 Wave 7 漏掉的**第 4 个零孤儿模块**（零消费方 + 零测试），
 * 且两个载荷构建函数的契约都对不上平台真实通道：
 *
 * | 旧实现 | 实证问题 |
 * |--------|---------|
 * | `event_type: 'fraud-risk:push-to-b50'` | **发明的事件名**，全库 grep 零消费方（`eventBus.ts` 事件表与 `crossWpEventBridge` 白名单都没有它） |
 * | `FraudIndicator.exists: 'yes'\|'no'\|'na'` | 真实模型 `FraudRiskRow.is_exist` 是中文三态 `'是'\|'否'\|'NA'\|'待核实'` |
 * | A13 载荷 `{ source_wp_code, account_type, reason, ... }` | `normalizeMisstatementPushPayload` 读 `wpCode ?? wp_code`（**不读 `source_wp_code`**）→ 溯源列落空 |
 *
 * 平台**真实**通道（各有真消费者，非 stub）：
 * - B50：`eventBus.emit('b50:push-risk-factor', { factors: string[], source: string })`
 *   → 唯一消费者 `GtB50RiskAssessment.appendRiskFactorsFromB2`（既有生产者 B19-1 / B2-12 / B22A / B23）
 * - A13：`eventBus.emit('a13:push-misstatement', { wpCode, items: [...] })`
 *   → 唯一消费者 `useA13MisstatementBridge`（全平台 60+ 生产者）
 *
 * ─────────────────────────────────────────────────────────────────────────────
 * 🔴 `source` 必须落在 B50 的 `SOURCE_OPTIONS` 白名单内
 * ─────────────────────────────────────────────────────────────────────────────
 * `appendRiskFactorsFromB2` 对不在白名单的 source **静默改写成 `'b2_predecessor'`**
 * （显示「B2 前任沟通」）→ 溯源错到另一张底稿上。故本模块导出 `B50_SOURCE_CONFIRMATION`
 * 常量，并由守卫与 `GtB50RiskAssessment.vue` 的 `SOURCE_OPTIONS` 交叉锁死。
 *
 * 具体是哪一张 X0-8 由 factor 文案末尾的「（来自 F0-8）」承载（同 B19-1 范式），
 * 因为 `SOURCE_OPTIONS` 是固定枚举、不可能为七个循环各开一项。
 */

import type { FraudRiskRow } from '../fraudRisk/fraudRiskTypes'
import type { DiffReconcileRow } from '../diffReconcile/diffReconcileTypes'

// ─── B50 风险因素推送 ─────────────────────────────────────────────────────────

/**
 * B50 `SOURCE_OPTIONS` 里代表函证程序的取值。
 *
 * 🔴 改这个字符串必须同步 `GtB50RiskAssessment.vue` 的 `SOURCE_OPTIONS`，
 * 否则推送的溯源会被静默改写成「B2 前任沟通」。守卫 `confirmationRiskPush.spec.ts`
 * 直接读那个文件的源码做交叉断言。
 */
export const B50_SOURCE_CONFIRMATION = 'confirmation'

/** `b50:push-risk-factor` 的载荷（对齐 `appendRiskFactorsFromB2` 的读取形态） */
export interface B50RiskFactorPayload {
  /** 风险因素描述文本数组（B50 按文本去重，故推送幂等） */
  factors: string[]
  /** 溯源来源（必须 ∈ B50 SOURCE_OPTIONS） */
  source: string
}

/** 舞弊迹象「存在」的判定 —— 只有明确的「是」才算，`待核实`/`NA`/空 都不推 */
export function isFraudIndicatorPresent(row: Pick<FraudRiskRow, 'is_exist'>): boolean {
  return String(row?.is_exist ?? '').trim() === '是'
}

/**
 * 构建 B50 风险因素推送载荷。
 *
 * 文案范式对齐 B19-1 的 `collectExistFactors`：
 * `函证舞弊风险迹象：{描述}（应对措施：{措施}）（来源：{索引号}）（来自 {wpCode}）`
 *
 * - 只含 `is_exist === '是'` 的条目（Property 4）
 * - 应对措施/索引号为空时不产生空括号
 * - 描述为空的行跳过（B50 侧按文本去重，空文本会污染）
 */
export function buildB50RiskFactorPayload(
  rows: readonly FraudRiskRow[],
  wpCode: string,
): B50RiskFactorPayload {
  const factors: string[] = []
  for (const row of rows ?? []) {
    if (!isFraudIndicatorPresent(row)) continue
    const desc = String(row.description ?? '').trim()
    if (!desc) continue

    let text = `函证舞弊风险迹象：${desc}`
    const measure = String(row.countermeasure ?? '').trim()
    if (measure) text += `（应对措施：${measure}）`
    const ref = String(row.source_ref ?? '').trim()
    if (ref) text += `（来源：${ref}）`
    text += `（来自 ${String(wpCode ?? '').trim() || '函证程序'}）`
    factors.push(text)
  }
  return { factors, source: B50_SOURCE_CONFIRMATION }
}

/** 是否有值得推送的迹象（推送按钮 disabled 判定） */
export function hasPresentFraudIndicators(rows: readonly FraudRiskRow[]): boolean {
  return (rows ?? []).some(
    (r) => isFraudIndicatorPresent(r) && String(r.description ?? '').trim() !== '',
  )
}

// ─── A13 错报推送 ─────────────────────────────────────────────────────────────

/** `a13:push-misstatement` 形态 A 的单行（字段名对齐 `normalizeMisstatementPushPayload`） */
export interface A13MisstatementItem {
  /** 错报描述（已内联单位/科目/原因，便于溯源） */
  description: string
  /** 受影响科目名称（函证字典只给中文名，无科目码 → `accountCode` 一律不发） */
  accountName: string | null
  /** 错报金额（**正数**，见 `pickMisstatementAmount` 注释） */
  amount: number
  /** 原始索引号（写入 description 尾部的「（索引:xxx）」） */
  indexRef: string
}

/** `a13:push-misstatement` 载荷（形态 A） */
export interface A13MisstatementPayload {
  /** 来源底稿编码 —— 🔴 键名必须是 `wpCode`（bridge 不认 `source_wp_code`） */
  wpCode: string
  items: A13MisstatementItem[]
}

/** 差异类型 code → 中文（与 `DiffReconcileMaster.DIFF_TYPE_MAP` 同源，仅用于文案） */
const DIFF_TYPE_TEXT: Readonly<Record<string, string>> = Object.freeze({
  time: '时间性差异',
  accounting: '记账差异',
  unrecorded: '未达账项',
  other: '其他差异',
})

/**
 * 错报金额取绝对值。
 *
 * 两个理由（都不是「随手 abs」）：
 * 1. `useA13MisstatementBridge` 对 `amount <= 0` 的行**直接 continue**（错报必须有金额），
 *    负差异原样推送会被静默丢弃；
 * 2. **源模板自身在差异方向上不一致** —— openpyxl 直读实证：
 *    D0-4 / F0-4 / L0-4 是 `F6 = E6 - D6`（回函 − 发函），
 *    K0-4 是 `F6 = D6 - E6`（发函 − 回函），
 *    而平台 `computeDifference` 统一取 `sent - reply`。
 *    错报金额只关心「差多少」，取绝对值可绕开这处未收敛的方向分歧
 *    （方向本身属七枢纽平台级议题，见 tasks.md Notes，本模块不擅自改）。
 */
export function pickMisstatementAmount(row: Pick<DiffReconcileRow, 'difference'>): number {
  const raw = Number(row?.difference)
  if (!Number.isFinite(raw)) return 0
  return Math.round(Math.abs(raw) * 100) / 100
}

/** 单行 → 错报描述 */
export function buildMisstatementDescription(row: DiffReconcileRow): string {
  const entity = String(row.entity_name ?? '').trim() || '未填被询证单位'
  const subject = String(row.subject ?? '').trim()
  const typeText = DIFF_TYPE_TEXT[String(row.diff_type ?? '')] ?? String(row.diff_type ?? '').trim()
  const note = String(row.diff_note ?? '').trim()

  let text = `函证差异：${entity}`
  if (subject) text += `（${subject}）`
  const reason = [typeText, note].filter(Boolean).join('，')
  text += reason ? `，差异原因：${reason}` : '，差异原因待查明'
  return text
}

/**
 * 构建 A13 错报推送载荷（形态 A）。
 *
 * 调用方负责挑行（通常是 `isOverMateriality` 的行或用户勾选行）；
 * 本函数只做「金额 ≤ 0 的行剔除 + 描述拼装」，不做重要性判断
 * （重要性阈值在 `useDiffReconcileData.materialityConfig`，属组件状态不是纯函数入参）。
 */
export function buildDiffMisstatementPayload(
  rows: readonly DiffReconcileRow[],
  wpCode: string,
): A13MisstatementPayload {
  const items: A13MisstatementItem[] = []
  for (const row of rows ?? []) {
    const amount = pickMisstatementAmount(row)
    if (amount <= 0) continue
    items.push({
      description: buildMisstatementDescription(row),
      accountName: String(row.subject ?? '').trim() || null,
      amount,
      indexRef: String(row.confirm_index ?? '').trim(),
    })
  }
  return { wpCode: String(wpCode ?? '').trim(), items }
}

/**
 * 🔴 **不导出「差异原因枚举」** —— 旧模块的 `F0_DIFF_REASONS`
 * （在途款项/未达账项/退货退款/跨期记账/尾差/其他）是自造的双真源，已删：
 * - 源模板 F0-4 第 7 列「差异原因」**无任何数据有效性**（openpyxl 实证 `data_validations` 为空），
 *   那 6 项取值没有源模板依据；
 * - 平台既有真源是后端字典 `confirmation_diff_type`（时间性差异/记账差异/未达账项/其他差异），
 *   已由 `DiffReconcileMaster` 的「差异类型」el-select 消费，配「差异说明」自由文本兜底
 *   → R7.1「下拉枚举 + 自由文本」由这两列共同满足，无需第二套枚举。
 */
