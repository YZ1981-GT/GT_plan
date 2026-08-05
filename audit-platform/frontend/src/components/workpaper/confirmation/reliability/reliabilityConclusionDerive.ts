/**
 * reliabilityConclusionDerive.ts — 回函可靠性结论自动推导（七枢纽共享）
 *
 * 🔴 立项依据（f0-confirmation-linkage-and-structural-enhancement R6.4，
 *    2026-08-03 浏览器实测发现该需求未实现）：
 * `conclusion_status` 原先**只有手工 el-select**，行级从不根据
 * 身份确认 / 邮箱域名 / 致电确认 推导；自动推导只存在于**总体结论**层
 * （`ReliabilityConclusion.vue` 按已填行的状态计数反推 `conclusion_type`）
 * → 审计师必须逐行自己判断，而判据（私人邮箱不可靠等）就写在同一行的旁边列里。
 *
 * 源模板依据（`邮件传真回函可靠性验证F0-7` 注1~注3，openpyxl 直读）：
 * - 注1（A24~A27）身份确认：需确定回函者属于被询证者或经其授权、对所函证信息知情
 * - 注2（A28~A30）邮箱：**「从私人电子信箱发送的回函不可靠」**（源模板原话）
 * - 注3（A34~A37）信息可靠性：不列明余额 / 水印防篡改等降低「不看就确认」风险
 *
 * 设计约束：
 * - **只产出建议，不自动写入**（memory 铁律「手工优先」）。调用方在结论为空时
 *   才提供一键采纳；已填值一律不覆盖。
 * - **寄回原件=是 → 免验证**，不产出建议（与 `isVerificationDisabled` 同口径）。
 * - 判据不足（三项验证列全空）时返回 `null` —— 「还没填」与「填了但不可靠」是两种状态，
 *   不得把空白推成「不可靠」。
 */
import { isCorpEmailDomain } from '@/utils/emailDomainCheck'
import type { ReliabilityRow } from './reliabilityTypes'

export type ReliabilityConclusionStatus = '可靠' | '部分可靠需补充' | '不可靠'

export interface ReliabilityConclusionSuggestion {
  /** 建议结论 */
  status: ReliabilityConclusionStatus
  /** 一句话理由（展示在 tooltip / 采纳确认里） */
  reason: string
  /** 触发降级的具体判据（可能多条） */
  blockers: string[]
}

/** 三项验证列是否都还没填（判据不足） */
function hasNoEvidence(row: ReliabilityRow): boolean {
  return (
    row.identity_verified == null
    && row.email_verified == null
    && row.phone_called == null
    && !String(row.email_domain || '').trim()
    && !String(row.reply_email || '').trim()
  )
}

/**
 * 推导某行的可靠性结论建议。
 *
 * 规则（design.md「F0-7 可靠性自动推导逻辑」）：
 * 1. 寄回原件=是 → null（免验证）
 * 2. 判据全空 → null（不把空白推成不可靠）
 * 3. 身份确认=否 **或** 邮箱域名/回函邮箱为私人域名 → 不可靠
 * 4. 未致电确认 **且** 未寄回原件 → 部分可靠需补充
 * 5. 其余 → 可靠
 */
export function deriveReliabilityConclusion(
  row: ReliabilityRow,
): ReliabilityConclusionSuggestion | null {
  if (row.original_returned === '是') return null
  if (hasNoEvidence(row)) return null

  const blockers: string[] = []

  // ── 硬性不可靠 ──
  if (row.identity_verified === false) {
    blockers.push('回函者身份未确认（注1）')
  }
  // 邮箱域名列与回函邮箱列任一判为私人域名即不可靠（源模板注2 原话）
  const personal = [row.email_domain, row.reply_email]
    .map(v => String(v || '').trim())
    .filter(Boolean)
    .some(v => isCorpEmailDomain(v) === 'personal')
  if (personal) {
    blockers.push('回函来自私人电子信箱（注2：私人信箱发送的回函不可靠）')
  }
  if (row.email_verified === false) {
    blockers.push('回函邮箱未通过域名核对（注2）')
  }

  if (blockers.length) {
    return {
      status: '不可靠',
      reason: '存在硬性不可靠情形，建议执行替代程序或追加审计证据',
      blockers,
    }
  }

  // ── 待补充 ──
  if (row.phone_called === false || row.phone_called == null) {
    return {
      status: '部分可靠需补充',
      reason: '未致电向被询证者核实且未取得回函原件，建议补充验证程序',
      blockers: ['未致电确认（注1）'],
    }
  }

  return {
    status: '可靠',
    reason: '身份、邮箱域名、致电确认三项均已通过，可作为审计证据',
    blockers: [],
  }
}

/** 建议结论对应的 el-tag type（与 `conclusionTagType` 同口径） */
export function suggestionTagType(
  status: ReliabilityConclusionStatus,
): 'success' | 'warning' | 'danger' {
  if (status === '可靠') return 'success'
  if (status === '部分可靠需补充') return 'warning'
  return 'danger'
}

/**
 * 是否应向用户提示建议：仅当该行**尚未填结论**且有建议时。
 *
 * 🔴 已填值一律不提示、不覆盖 —— 审计判断优先于系统初判
 * （源模板注2 第 3 条：「系统按域名自动初判，最终判断仍需审计师复核」）。
 */
export function shouldOfferSuggestion(row: ReliabilityRow): boolean {
  if (row.conclusion_status) return false
  return deriveReliabilityConclusion(row) !== null
}
