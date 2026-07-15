/**
 * cycleConfirmationMeta — 各循环（D0/E0/F0/G0/H0/K0/L0）函证底稿编码与跨表文案
 *
 * 共享 HTML 组件（summary / diff / reliability / alternative master）挂在不同循环时，
 * 须按 wpCode 前缀解析 sheet 名，避免文案写死 D0-*。
 */

export type ConfirmationCycle =
  | 'D0'
  | 'E0'
  | 'F0'
  | 'G0'
  | 'H0'
  | 'K0'
  | 'L0'

export interface CycleConfirmationMeta {
  cycle: ConfirmationCycle
  /** 汇总表，如 F0-1 */
  summaryCode: string
  /** 差异调节，如 F0-4（E0 无独立差异表 → null） */
  diffCode: string | null
  /** 差异检查表（D0/F0/K0 有 4b；其余可能无） */
  diffChecklistCode: string | null
  /** 差异证券专表（仅 G0-3S；其余 null） */
  diffSecuritiesCode: string | null
  /** 替代程序主表（部分循环仅一张；E0 货币资金无替代程序 → null） */
  altPrimaryCode: string | null
  /** 第二张替代（无则 null） */
  altSecondaryCode: string | null
  /** 回函可靠性（E0 无可靠性验证 sheet → null） */
  reliabilityCode: string | null
  /** 舞弊风险 */
  fraudCode: string
  /** 主体核查 */
  entityVerifyCode: string
  /** 跟函 */
  followupCode: string
}

const CYCLE_SHEETS: Record<ConfirmationCycle, Omit<CycleConfirmationMeta, 'cycle'>> = {
  D0: {
    summaryCode: 'D0-1',
    entityVerifyCode: 'D0-2',
    followupCode: 'D0-3',
    diffCode: 'D0-4',
    diffChecklistCode: 'D0-4b',
    diffSecuritiesCode: null,
    altPrimaryCode: 'D0-5',
    altSecondaryCode: 'D0-6',
    reliabilityCode: 'D0-7',
    fraudCode: 'D0-8',
  },
  E0: {
    // E0（货币资金）真实模板：E0-1 汇总 / E0-2 核实单位 / E0-3~6 发函记录(d-form) /
    // E0-7 跟函 / E0-8 舞弊。勿按 D0 序号镜像；无独立差异调节表与回函可靠性表。
    summaryCode: 'E0-1',
    entityVerifyCode: 'E0-2',
    followupCode: 'E0-7',
    diffCode: null, // E0 无独立差异调节表
    diffChecklistCode: null,
    diffSecuritiesCode: null,
    altPrimaryCode: null, // E0 无替代程序 sheet（发函记录 E0-3~6 为 d-form 直接编制，非替代确认）
    altSecondaryCode: null,
    reliabilityCode: null, // E0 无回函可靠性验证 sheet
    fraudCode: 'E0-8',
  },
  F0: {
    summaryCode: 'F0-1',
    entityVerifyCode: 'F0-2',
    followupCode: 'F0-3',
    diffCode: 'F0-4',
    diffChecklistCode: 'F0-4b',
    diffSecuritiesCode: null,
    altPrimaryCode: 'F0-5',
    altSecondaryCode: 'F0-6',
    reliabilityCode: 'F0-7',
    fraudCode: 'F0-8',
  },
  G0: {
    summaryCode: 'G0-1',
    entityVerifyCode: 'G0-2',
    followupCode: 'G0-3',
    diffCode: 'G0-4',
    diffChecklistCode: null,
    diffSecuritiesCode: 'G0-3S', // 证券差异专表（G0 特有）
    altPrimaryCode: 'G0-6',
    altSecondaryCode: null,
    reliabilityCode: 'G0-7',
    fraudCode: 'G0-8',
  },
  H0: {
    summaryCode: 'H0-1',
    entityVerifyCode: 'H0-2',
    followupCode: 'H0-3',
    diffCode: 'H0-4',
    diffChecklistCode: null,
    diffSecuritiesCode: null,
    altPrimaryCode: 'H0-5',
    altSecondaryCode: null,
    reliabilityCode: 'H0-6',
    fraudCode: 'H0-7',
  },
  K0: {
    summaryCode: 'K0-1',
    entityVerifyCode: 'K0-2',
    followupCode: 'K0-3',
    diffCode: 'K0-4',
    diffChecklistCode: null,
    diffSecuritiesCode: null,
    altPrimaryCode: 'K0-5',
    altSecondaryCode: 'K0-6',
    reliabilityCode: 'K0-7',
    fraudCode: 'K0-8',
  },
  L0: {
    summaryCode: 'L0-1',
    entityVerifyCode: 'L0-2',
    followupCode: 'L0-3',
    diffCode: 'L0-4',
    diffChecklistCode: null,
    diffSecuritiesCode: null,
    altPrimaryCode: 'L0-5',
    altSecondaryCode: null,
    reliabilityCode: 'L0-6',
    fraudCode: 'L0-7',
  },
}

/** 从任意函证 sheet 编码解析循环前缀 */
export function resolveConfirmationCycle(wpCode?: string | null): ConfirmationCycle {
  const code = String(wpCode || '').trim().toUpperCase()
  const m = code.match(/^([DEFGHKL])0\b/)
  if (m) return `${m[1]}0` as ConfirmationCycle
  // fallback: 前缀如 "F0-5"
  const prefix = code.split('-')[0]
  if (prefix && /^[DEFGHKL]0$/i.test(prefix)) return prefix.toUpperCase() as ConfirmationCycle
  return 'D0'
}

export function getCycleConfirmationMeta(wpCode?: string | null): CycleConfirmationMeta {
  const cycle = resolveConfirmationCycle(wpCode)
  return { cycle, ...CYCLE_SHEETS[cycle] }
}

/** 替代程序标签（主表/次表拼接；无替代程序 sheet 时返回 null，如 E0） */
export function altProcedureLabel(m: CycleConfirmationMeta): string | null {
  if (!m.altPrimaryCode) return null
  return m.altSecondaryCode
    ? `${m.altPrimaryCode}/${m.altSecondaryCode}`
    : m.altPrimaryCode
}

/** 汇总表 CrossRef 规则文案（挂在 confirmation-summary；null sheet 自动跳过） */
export function buildCrossRefRules(wpCode?: string | null) {
  const m = getCycleConfirmationMeta(wpCode)
  const altLabel = altProcedureLabel(m)
  const rules: Array<{ field: string; target: string; rule: string }> = [
    { field: '函证金额', target: 'TB 试算表', rule: '应与科目审定余额(audited_amount)核对一致' },
  ]
  if (m.diffCode) {
    rules.push({ field: '差异金额', target: `${m.diffCode} 差异调节`, rule: `不符项跳转到 ${m.diffCode} 差异调节表编制` })
  }
  if (m.diffSecuritiesCode) {
    rules.push({ field: '证券差异', target: `${m.diffSecuritiesCode} 证券差异专表`, rule: `证券类不符项跳转到 ${m.diffSecuritiesCode} 编制` })
  }
  if (altLabel) {
    rules.push({ field: '替代确认', target: altLabel, rule: `未回函项跳转到替代程序底稿（${altLabel}）确认` })
  }
  if (m.reliabilityCode) {
    rules.push({ field: '回函可靠性', target: m.reliabilityCode, rule: `电子回函需跳转 ${m.reliabilityCode} 验证可靠性` })
  }
  rules.push({ field: '舞弊风险', target: `${m.fraudCode}/B50`, rule: `异常迹象需记录到 ${m.fraudCode} 并汇总至 B50 风险评估` })
  return rules
}

/** CrossWorkpaperNav 导航项（按循环；null sheet 自动跳过，不生成跳错的入口） */
export function buildCrossWorkpaperNavDefs(wpCode?: string | null) {
  const m = getCycleConfirmationMeta(wpCode)
  const altLabel = altProcedureLabel(m)
  const items: Array<{ wpCode: string; label: string; tooltip: string }> = [
    { wpCode: m.entityVerifyCode, label: m.entityVerifyCode, tooltip: '核实被函证单位' },
    { wpCode: m.summaryCode, label: m.summaryCode, tooltip: '函证汇总表' },
    { wpCode: m.followupCode, label: m.followupCode, tooltip: '跟函过程控制' },
  ]
  if (m.reliabilityCode) {
    items.push({ wpCode: m.reliabilityCode, label: m.reliabilityCode, tooltip: '回函可靠性验证' })
  }
  if (m.diffCode) {
    items.push({ wpCode: m.diffCode, label: m.diffCode, tooltip: '差异调节表' })
  }
  if (m.diffSecuritiesCode) {
    items.push({ wpCode: m.diffSecuritiesCode, label: m.diffSecuritiesCode, tooltip: '证券差异专表' })
  }
  if (m.diffChecklistCode) {
    items.push({ wpCode: m.diffChecklistCode, label: m.diffChecklistCode, tooltip: '差异检查表' })
  }
  if (altLabel) {
    items.push({ wpCode: altLabel, label: altLabel, tooltip: '替代程序' })
  }
  items.push({ wpCode: m.fraudCode, label: m.fraudCode, tooltip: '舞弊风险评价' })
  return items
}

/** 示例索引号（导入模板说明） */
export function exampleConfirmIndex(wpCode?: string | null): string {
  const cycle = resolveConfirmationCycle(wpCode)
  return `${cycle}-001`
}
