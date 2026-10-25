/**
 * d4OtherGroupPushPredicates — D4-33~36 其他业务收入组「可推送 A13」判据单一真源
 *
 * spec: d4-33-36-writeback-formula-and-io-closure（Requirement 3.12 / Property 10）
 *
 * 四张表的「哪些行/项可推送到 A13 未更正错报」判据集中在此，四表共同引用，
 * 禁止在四个组件各写一份过滤条件（防口径漂移）。
 *
 * 🔴 科目口径（DEC-5）：四表统一 accountCode='6051' / accountName='其他业务收入'，
 *    不得照抄姊妹 spec D4-13~20 的 '6001'/'营业收入'。
 *
 * 🔴 A13 金额与方向纪律（Governance / Property 15）：
 *    - D4-33 是分析表（定性风险），命中项不携带 amount，必须由人工在推送前认定金额与方向，
 *      不得以 amount:0 自动进入错报汇总。故 D4-33 判据产出 `requiresManualAmount: true`。
 *    - D4-34 差异保留符号（不 abs），由人工认定方向。
 *    - D4-35 抽凭金额不直接等同错报金额（作为参考金额，人工认定）。
 *    - D4-36 跨期金额是取证金额（forward 取 docAmount / backward 取 voucherAmount），人工认定。
 */
import { parseNum } from './useD4FormulaEngine'

// ─── 科目口径常量（单一真源，守卫锁死防照抄 6001）───────────────────────────
export const D4_OTHER_ACCOUNT_CODE = '6051' as const
export const D4_OTHER_ACCOUNT_NAME = '其他业务收入' as const

/** 待推送候选项（未认定金额前的中间形态） */
export interface D4OtherPushCandidate {
  /** 来源表 */
  wpCode: 'D4-33' | 'D4-34' | 'D4-35' | 'D4-36'
  /** 凭证号/标识（入描述与溯源） */
  voucherNo?: string
  /** 参考金额（D4-34 差异 / D4-35 抽凭额 / D4-36 取证额）；D4-33 无金额 */
  refAmount?: number
  /** 描述（含定性标记/方向/差异等） */
  description: string
  /** 溯源索引 */
  indexRef: string
  /** 是否需人工认定金额（D4-33 定性项为 true，不得以 0 自动入汇总） */
  requiresManualAmount: boolean
}

// ─── D4-33 毛利率异常判据 ───────────────────────────────────────────────────
// 判据：某业务类型合计毛利率超阈值(默认 ±20 个百分点) 或 毛利率同比变动率绝对值超阈值(默认 30%)

export interface D4_33BizStat {
  name: string
  /** 合计毛利率（百分比，如 40 代表 40%） */
  marginPct: number
  /** 同比变动率（百分比，如 35 代表 35%）；无上年数时为 null */
  changeRatePct: number | null
}

export function d4_33Candidates(
  stats: D4_33BizStat[],
  opts: { marginThresholdPct?: number; changeRateThresholdPct?: number } = {},
): D4OtherPushCandidate[] {
  const marginTh = opts.marginThresholdPct ?? 20
  const changeTh = opts.changeRateThresholdPct ?? 30
  const out: D4OtherPushCandidate[] = []
  for (const s of stats) {
    const marginExceeds = Math.abs(s.marginPct) > marginTh
    const changeExceeds = s.changeRatePct !== null && Math.abs(s.changeRatePct) > changeTh
    if (marginExceeds || changeExceeds) {
      const changeText = s.changeRatePct !== null ? `，同比变动 ${s.changeRatePct.toFixed(2)}%` : ''
      out.push({
        wpCode: 'D4-33',
        description: `其他业务毛利率分析：${s.name} 毛利率 ${s.marginPct.toFixed(2)}%${changeText}，超阈值`,
        indexRef: 'wp:D4-33',
        requiresManualAmount: true, // 定性项：金额与方向由人工认定，不预填 0
      })
    }
  }
  return out
}

// ─── D4-34 合同测算差异判据 ─────────────────────────────────────────────────
// 判据：diff !== 0（保留符号，租赁区与咨询区各自独立成条）

export interface D4_34RentalLike {
  tenant: string
  expectedRevenue: number | string
  actualRevenue: number | string
  diff: number
  indexRef?: string
}
export interface D4_34ConsultLike {
  client: string
  expectedRevenue: number | string
  actualRevenue: number | string
  diff: number
  indexRef?: string
}

export function d4_34Candidates(
  rentals: D4_34RentalLike[],
  consults: D4_34ConsultLike[],
  opts: { diffToleranceAbs?: number } = {},
): D4OtherPushCandidate[] {
  const tol = opts.diffToleranceAbs ?? 0
  const out: D4OtherPushCandidate[] = []
  for (const r of rentals) {
    if (Math.abs(r.diff) > tol) {
      out.push({
        wpCode: 'D4-34',
        voucherNo: r.tenant,
        refAmount: r.diff, // 保留符号，不 abs
        description: `合同测算差异（租赁）：承租方 ${r.tenant}，应计 ${parseNum(r.expectedRevenue)}、实计 ${parseNum(r.actualRevenue)}，差异 ${r.diff}`,
        indexRef: r.indexRef || 'wp:D4-34',
        requiresManualAmount: false,
      })
    }
  }
  for (const c of consults) {
    if (Math.abs(c.diff) > tol) {
      out.push({
        wpCode: 'D4-34',
        voucherNo: c.client,
        refAmount: c.diff, // 保留符号，不 abs
        description: `合同测算差异（咨询）：委托方 ${c.client}，应计 ${parseNum(c.expectedRevenue)}、实计 ${parseNum(c.actualRevenue)}，差异 ${c.diff}`,
        indexRef: c.indexRef || 'wp:D4-34',
        requiresManualAmount: false,
      })
    }
  }
  return out
}

// ─── D4-35 抽凭异常判据 ─────────────────────────────────────────────────────
// 判据：isAnomalous === '是'

export interface D4_35RowLike {
  voucherNo: string
  content: string
  amount: number | string
  isAnomalous: string
  check1: string; check2: string; check3: string; check4: string; check5: string; check6: string
  indexRef?: string
}

const D4_35_CHECK_LABELS = [
  '原始凭证是否齐全', '记账凭证与原始凭证是否相符', '账务处理是否正确',
  '是否记录于恰当的会计期间', '（自定义5）', '（自定义6）',
]

export function d4_35Candidates(rows: D4_35RowLike[]): D4OtherPushCandidate[] {
  const out: D4OtherPushCandidate[] = []
  for (const r of rows) {
    if (r.isAnomalous === '是') {
      const failed: string[] = []
      const checks = [r.check1, r.check2, r.check3, r.check4, r.check5, r.check6]
      checks.forEach((c, i) => { if (c !== '√') failed.push(`${i + 1}.${D4_35_CHECK_LABELS[i]}`) })
      const failText = failed.length ? `，未通过核对项：${failed.join('、')}` : ''
      out.push({
        wpCode: 'D4-35',
        voucherNo: r.voucherNo,
        refAmount: parseNum(r.amount), // 抽凭金额是参考，人工认定错报额
        description: `抽凭检查异常：凭证 ${r.voucherNo}，业务内容「${r.content}」${failText}`,
        indexRef: r.indexRef || 'wp:D4-35',
        requiresManualAmount: false,
      })
    }
  }
  return out
}

// ─── D4-36 跨期疑点判据 ─────────────────────────────────────────────────────
// 判据：isCrossing === '×'；forward 取 docAmount，backward 取 voucherAmount

export interface D4_36RowLike {
  voucherNo: string
  voucherAmount: number | string
  docNo: string
  docAmount: number | string
  isCrossing: string
  crossPeriodDays?: number
}

export function d4_36Candidates(
  forward: D4_36RowLike[],
  backward: D4_36RowLike[],
): D4OtherPushCandidate[] {
  const out: D4OtherPushCandidate[] = []
  for (const r of forward) {
    if (r.isCrossing === '×') {
      const days = r.crossPeriodDays != null ? `，跨期 ${r.crossPeriodDays} 天` : ''
      out.push({
        wpCode: 'D4-36',
        voucherNo: r.voucherNo,
        refAmount: parseNum(r.docAmount), // forward：已发/已验未记账，取单据金额
        description: `截止性测试跨期（账到单据）：凭证 ${r.voucherNo} / 单据 ${r.docNo}${days}，建议核实是否应调整期间`,
        indexRef: 'wp:D4-36',
        requiresManualAmount: false,
      })
    }
  }
  for (const r of backward) {
    if (r.isCrossing === '×') {
      const days = r.crossPeriodDays != null ? `，跨期 ${r.crossPeriodDays} 天` : ''
      out.push({
        wpCode: 'D4-36',
        voucherNo: r.docNo,
        refAmount: parseNum(r.voucherAmount), // backward：已记账未发/未验，取凭证金额
        description: `截止性测试跨期（单据到账）：单据 ${r.docNo} / 凭证 ${r.voucherNo}${days}，建议核实是否应调整期间`,
        indexRef: 'wp:D4-36',
        requiresManualAmount: false,
      })
    }
  }
  return out
}
