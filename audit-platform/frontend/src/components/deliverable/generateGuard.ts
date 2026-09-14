/**
 * 三类核心交付物「生成入口」前置守卫纯逻辑
 *
 * 对应需求 21（生成入口一致性）：报表 / 附注 / 报告正文三处入口统一的前置检查、
 * 进度反馈、结果提示语义。本模块抽离可测纯逻辑（前置数据就绪判定），
 * 供 view 集成与 fast-check 属性测试共用。
 *
 * 对应需求：21.1/21.2/21.3（三入口存在）、21.4 + Property 37（前置数据就绪守卫）。
 *
 * 需求 14（生成前置守卫与数据依赖链）：
 * - 四个生成入口（交付件中心 报表/附注/报告正文 + AuditReportEditor 报告正文）
 *   SHALL 统一调用 `checkGenerateReady`，文案以本模块返回的 `message` 为唯一来源。
 * - 数据依赖链：试算表就绪(trialBalanceReady) → 财务报表(reportsReady) → 附注/报告正文。
 * - 一键全套（full_deliverables）额外生成未审财务报表（financial_report_unadjusted），仍依赖试算表就绪。
 * - 服务端「一键生成全套」job（job_type='full_deliverables'，task 15 待实现）
 *   SHALL 复用同一依赖链（trialBalanceReady → reportsReady）做 job 级前置校验，
 *   并对齐此处的错误文案语义（无法生成「X」：…尚未就绪，请先完成前置数据准备），
 *   单项失败不阻断其他已完成项的重试（需求 14.3）。
 */

/** 三类生成入口键（与 DeliverableToolbar 事件一致） */
export type GenerateEntryKey = 'reports' | 'notes' | 'report_body'

export interface GenerateEntry {
  key: GenerateEntryKey
  /** 中文按钮文案 */
  label: string
  /** 该入口生成所需就绪的底层数据键 */
  requires: ReadonlyArray<keyof DataReadiness>
}

/** 底层数据就绪状态（true = 已就绪） */
export interface DataReadiness {
  /** 试算表/序时账已导入 */
  trialBalanceReady: boolean
  /** 财务报表已生成 */
  reportsReady: boolean
}

/**
 * 三类核心交付物生成入口定义（需求 21.1/21.2/21.3）。
 * - 生成报表：依赖试算表已就绪
 * - 生成附注：依赖财务报表已就绪
 * - 生成报告正文：依赖财务报表已就绪
 */
export const GENERATE_ENTRIES: readonly GenerateEntry[] = [
  { key: 'reports', label: '生成报表', requires: ['trialBalanceReady'] },
  { key: 'notes', label: '生成附注', requires: ['reportsReady'] },
  { key: 'report_body', label: '生成报告', requires: ['reportsReady'] },
] as const

const READINESS_LABEL: Record<keyof DataReadiness, string> = {
  trialBalanceReady: '试算表/序时账数据',
  reportsReady: '财务报表数据',
}

export interface GuardResult {
  /** 是否允许继续生成 */
  allowed: boolean
  /** 被阻止时的前置检查提示（allowed=false 时非空） */
  message: string
  /** 缺失的就绪项 */
  missing: Array<keyof DataReadiness>
}

/**
 * 生成前置数据就绪守卫（需求 21.4 / Property 37）。
 *
 * *For any* 生成入口与就绪状态：当该入口所需的任一底层数据未就绪时，
 * 返回 allowed=false 并给出非空的前置检查提示；全部就绪时 allowed=true。
 */
export function checkGenerateReady(
  entryKey: GenerateEntryKey,
  readiness: DataReadiness,
): GuardResult {
  const entry = GENERATE_ENTRIES.find((e) => e.key === entryKey)
  if (!entry) {
    return { allowed: false, message: '未知的生成入口', missing: [] }
  }
  const missing = entry.requires.filter((flag) => !readiness[flag])
  if (missing.length) {
    const names = missing.map((f) => READINESS_LABEL[f]).join('、')
    return {
      allowed: false,
      message: `无法生成「${entry.label.replace('生成', '')}」：${names}尚未就绪，请先完成前置数据准备`,
      missing,
    }
  }
  return { allowed: true, message: '', missing: [] }
}
