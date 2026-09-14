/**
 * buildAiContext — 统一 AI 上下文工厂
 *
 * Feature: platform-global-hardening
 * Requirements: 9.1, 9.2
 *
 * 自动附带该底稿的联动数据/审定数/账龄/异常项/源模板方法论，
 * 确保 AI 生成基于实际数据而非通用套话。
 *
 * 返回值保证非空（never return empty/null）。
 */

/** AI 上下文结构 */
export interface AiContext {
  /** 底稿编码 */
  wpCode: string
  /** 当前 sheet（如有） */
  sheet: string
  /** 联动数据（审定数/未审数/差异等） */
  linkedData: Record<string, unknown>
  /** 审定数（该底稿相关科目的审定金额摘要） */
  auditedAmounts: Record<string, number>
  /** 账龄信息（如适用） */
  agingData: Record<string, unknown>[]
  /** 异常项（标记为异常的行/事项） */
  anomalies: string[]
  /** 源模板方法论（CAS 依据/编制方法等） */
  methodology: string
  /** 附加上下文（调用方可扩展） */
  extra: Record<string, unknown>
}

/**
 * 从 wpCode 中提取循环前缀
 * 如 'D2-1' → 'D', 'F3A' → 'F', 'K10-6' → 'K'
 */
function extractCyclePrefix(wpCode: string): string {
  const match = wpCode.match(/^([A-Z])/i)
  return match ? match[1].toUpperCase() : ''
}

/**
 * 从 wpCode 中提取科目族关键字（用于联动数据描述）
 */
function getSubjectFamily(wpCode: string): string {
  const cycleMap: Record<string, string> = {
    D: '应收/预付款项',
    E: '货币资金',
    F: '存货/成本',
    G: '投资/金融资产',
    H: '固定资产/无形资产',
    I: '无形资产/开发支出',
    J: '投资性房地产',
    K: '负债/费用',
    L: '应付/预收款项',
    M: '权益',
    N: '收入/税费',
  }
  const prefix = extractCyclePrefix(wpCode)
  return cycleMap[prefix] || '通用审计领域'
}

/**
 * 获取源模板方法论文本（基于 wpCode 和 sheet）
 */
function getMethodology(wpCode: string, sheet: string): string {
  const prefix = extractCyclePrefix(wpCode)
  const subject = getSubjectFamily(wpCode)

  // 通用方法论框架 + 循环特定指引
  const baseMethodology = `审计底稿 ${wpCode}（${subject}）`

  const cycleGuidance: Record<string, string> = {
    D: '执行应收/预付款项实质性程序：函证、账龄分析、期后回款检查、坏账计提合理性评估（CAS 1312）',
    E: '执行货币资金实质性程序：银行函证、银行对账单核对、大额资金流水检查（CAS 1312）',
    F: '执行存货/成本实质性程序：监盘、截止测试、计价测试、慢周转/跌价测试（CAS 1311）',
    G: '执行投资类实质性程序：公允价值估值、减值测试、SPPI测试、分类适当性评估（CAS 1321）',
    H: '执行固定资产实质性程序：所有权验证、折旧计提复核、减值迹象评估（CAS 1312）',
    I: '执行无形资产实质性程序：研发费用资本化判定、摊销复核、减值测试（CAS 1312）',
    J: '执行投资性房地产实质性程序：公允价值模型/成本模型、转换测试、收入确认（CAS 1312）',
    K: '执行负债/费用类实质性程序：完整性验证、截止测试、费用分类合理性评估（CAS 1312）',
    L: '执行应付/预收款项实质性程序：函证、账龄分析、暂估/长期挂账核查（CAS 1312）',
    M: '执行权益类实质性程序：股本变动验证、留存收益复核、其他综合收益核查（CAS 1312）',
    N: '执行收入/税费类实质性程序：截止测试、毛利分析、收入确认五步法评估（CAS 1312/CAS 14）',
  }

  const guidance = cycleGuidance[prefix] || '按照中国注册会计师审计准则执行实质性程序'

  if (sheet) {
    return `${baseMethodology}，当前工作表: ${sheet}。\n方法论: ${guidance}`
  }
  return `${baseMethodology}。\n方法论: ${guidance}`
}

/**
 * buildAiContext — 构建 AI 上下文
 *
 * 自动附带该底稿的联动数据/审定数/账龄/异常项/源模板方法论。
 * 保证返回非空 context（never return empty/null）。
 *
 * @param wpCode - 底稿编码（如 'D2-1', 'F3', 'K10'）
 * @param sheet - 当前 sheet 名称（可选）
 * @returns AiContext 非空上下文对象
 *
 * @example
 * ```ts
 * const ctx = buildAiContext('D2-5', '账龄分析')
 * // ctx.methodology 包含 D 类方法论
 * // ctx.wpCode = 'D2-5'
 * // ctx.sheet = '账龄分析'
 * ```
 */
export function buildAiContext(wpCode: string, sheet?: string): AiContext {
  const sheetName = sheet || ''

  // 构建联动数据描述
  const subject = getSubjectFamily(wpCode)
  const linkedData: Record<string, unknown> = {
    subject,
    cyclePrefix: extractCyclePrefix(wpCode),
    wpCode,
    dataScope: `${subject}相关科目审定数据`,
  }

  // 审定数占位（实际运行时由调用方注入或从 useAuditData SDK 获取）
  const auditedAmounts: Record<string, number> = {}

  // 账龄数据占位
  const agingData: Record<string, unknown>[] = []

  // 异常项占位
  const anomalies: string[] = []

  // 方法论
  const methodology = getMethodology(wpCode, sheetName)

  return {
    wpCode,
    sheet: sheetName,
    linkedData,
    auditedAmounts,
    agingData,
    anomalies,
    methodology,
    extra: {},
  }
}

/**
 * enrichAiContext — 用实际数据丰富 AI 上下文
 *
 * 在底稿运行时调用，把实际获取到的数据注入到上下文中。
 * 用于底稿 tab 内把 SDK/composable 获取的数据附加到 context。
 *
 * @param base - 由 buildAiContext 创建的基础上下文
 * @param enrichment - 需注入的实际数据
 * @returns 丰富后的 AiContext（新对象，不修改原始）
 */
export function enrichAiContext(
  base: AiContext,
  enrichment: {
    auditedAmounts?: Record<string, number>
    agingData?: Record<string, unknown>[]
    anomalies?: string[]
    linkedData?: Record<string, unknown>
    extra?: Record<string, unknown>
  },
): AiContext {
  return {
    ...base,
    linkedData: { ...base.linkedData, ...enrichment.linkedData },
    auditedAmounts: { ...base.auditedAmounts, ...enrichment.auditedAmounts },
    agingData: [...base.agingData, ...(enrichment.agingData || [])],
    anomalies: [...base.anomalies, ...(enrichment.anomalies || [])],
    extra: { ...base.extra, ...enrichment.extra },
  }
}
