/**
 * useC24AnalyticsEngine — C24 会计分录细节测试分析引擎
 *
 * 纯函数，无副作用、无 API 调用、确定性输出。
 * 供 GtC24JournalDetail 组件直接调用，公式列只读。
 */

// ─── 类型定义 ───────────────────────────────────────────────

export interface JournalEntry {
  voucherDate: string       // YYYY-MM-DD
  voucherMonth: number      // 1-12
  voucherType: string       // 付/收/转
  voucherNo: string         // 如 付-001
  summary: string
  accountCode: string
  accountName: string
  debit: number
  credit: number
  voucherSheets: string
  preparer: string
  reviewer: string
  poster: string
}

export interface AnomalyRules {
  holidays: string[]            // 假期日期列表 (YYYY-MM-DD)
  nightStartHour: number        // 夜间起始（默认22）
  nightEndHour: number          // 夜间结束（默认6）
  largeAmountThreshold: number  // 大额阈值
  approvalLimit: number         // 审批限额
  roundAmountDigits: number     // 约整数判断位数（末尾N个0）
  vagueKeywords: string[]       // 模糊关键词（调整/暂估/其他等）
  checkEmptySummary: boolean    // 检查空摘要
  duplicateCheck: boolean       // 重复检测
}

export interface TrialBalanceRow {
  accountCode: string
  debitAmount: number
  creditAmount: number
}

export interface BalanceIntegrityResult {
  debitTotal: number
  creditTotal: number
  balanced: boolean
}

export interface TrialBalanceComparison {
  account: string
  accountName: string
  jeDebitSum: number
  jeCreditSum: number
  jeNet: number
  tbDebit: number
  tbCredit: number
  tbNet: number
  diff: number
}

export interface GapResult {
  type: string   // 凭证类型
  month: number  // 月份
  start: string  // 缺号起始
  end: string    // 缺号终止
  count: number  // 缺号数量
}

export interface AnomalyResult {
  entry: JournalEntry
  reasons: string[]
}

export interface BenfordDigitResult {
  digit: number             // 1-9
  expected: number          // log10(1+1/digit)
  count: number             // 实际首位数为该数字的条数
  actual: number            // count / total
  deviation: number         // actual - expected
  chi2Contribution: number  // (count - expected*N)² / (expected*N)
}

export interface BenfordTestResult {
  chi2Total: number
  criticalValue: number
  significant: boolean      // chi2Total > criticalValue
}

// ─── 1. 借贷平衡完整性 ─────────────────────────────────────

export function calcBalanceIntegrity(entries: JournalEntry[]): BalanceIntegrityResult {
  let debitTotal = 0
  let creditTotal = 0
  for (const e of entries) {
    debitTotal += e.debit || 0
    creditTotal += e.credit || 0
  }
  // 浮点修正：保留2位
  debitTotal = Math.round(debitTotal * 100) / 100
  creditTotal = Math.round(creditTotal * 100) / 100
  const balanced = Math.abs(debitTotal - creditTotal) < 0.01
  return { debitTotal, creditTotal, balanced }
}

// ─── 2. 科目余额对比 ────────────────────────────────────────

export function compareToTrialBalance(
  entries: JournalEntry[],
  trialBalance: TrialBalanceRow[],
): TrialBalanceComparison[] {
  // 按科目编码汇总分录
  const jeMap = new Map<string, { debit: number; credit: number; name: string }>()
  for (const e of entries) {
    const code = e.accountCode
    if (!jeMap.has(code)) {
      jeMap.set(code, { debit: 0, credit: 0, name: e.accountName })
    }
    const acc = jeMap.get(code)!
    acc.debit += e.debit || 0
    acc.credit += e.credit || 0
  }

  // 合并试算表
  const tbMap = new Map<string, { debit: number; credit: number }>()
  for (const tb of trialBalance) {
    tbMap.set(tb.accountCode, { debit: tb.debitAmount, credit: tb.creditAmount })
  }

  // 取所有科目合集
  const allAccounts = new Set([...Array.from(jeMap.keys()), ...Array.from(tbMap.keys())])
  const results: TrialBalanceComparison[] = []

  for (const account of Array.from(allAccounts)) {
    const je = jeMap.get(account) || { debit: 0, credit: 0, name: '' }
    const tb = tbMap.get(account) || { debit: 0, credit: 0 }

    const jeDebitSum = Math.round(je.debit * 100) / 100
    const jeCreditSum = Math.round(je.credit * 100) / 100
    const jeNet = Math.round((jeDebitSum - jeCreditSum) * 100) / 100
    const tbDebit = tb.debit
    const tbCredit = tb.credit
    const tbNet = Math.round((tbDebit - tbCredit) * 100) / 100
    const diff = Math.round((jeNet - tbNet) * 100) / 100

    results.push({
      account,
      accountName: je.name || account,
      jeDebitSum,
      jeCreditSum,
      jeNet,
      tbDebit,
      tbCredit,
      tbNet,
      diff,
    })
  }

  return results.sort((a, b) => a.account.localeCompare(b.account))
}

// ─── 3. 跳号测试 ───────────────────────────────────────────

/**
 * 解析凭证号（如"付-001"）为 { type, num }
 * 支持格式：类型-数字编号 或 纯数字
 */
function parseVoucherNo(vno: string): { type: string; num: number } | null {
  if (!vno || typeof vno !== 'string') return null
  const trimmed = vno.trim()
  // 格式1: 类型-数字 (如 付-001, 收-12, 转-003)
  const match = trimmed.match(/^(.+?)-(\d+)$/)
  if (match) {
    return { type: match[1], num: parseInt(match[2], 10) }
  }
  // 格式2: 纯数字
  const numMatch = trimmed.match(/^(\d+)$/)
  if (numMatch) {
    return { type: '', num: parseInt(numMatch[1], 10) }
  }
  return null
}

export function detectGaps(voucherNos: string[]): GapResult[] {
  // 解析所有凭证号
  const parsed: { type: string; num: number; original: string }[] = []
  for (const vno of voucherNos) {
    const p = parseVoucherNo(vno)
    if (p) parsed.push({ ...p, original: vno })
  }

  if (parsed.length === 0) return []

  // 按类型分组（同类型内找跳号）
  const byType = new Map<string, number[]>()
  for (const p of parsed) {
    if (!byType.has(p.type)) byType.set(p.type, [])
    byType.get(p.type)!.push(p.num)
  }

  const gaps: GapResult[] = []

  for (const [type, nums] of Array.from(byType)) {
    // 去重排序
    const sorted = Array.from(new Set(nums)).sort((a, b) => a - b)
    if (sorted.length < 2) continue

    // 在连续区间内检测缺号
    let gapStart: number | null = null
    let gapCount = 0

    for (let i = 0; i < sorted.length - 1; i++) {
      const current = sorted[i]
      const next = sorted[i + 1]
      if (next - current > 1) {
        // 有缺口
        gapStart = current + 1
        const gapEnd = next - 1
        gapCount = gapEnd - gapStart + 1
        const prefix = type ? `${type}-` : ''
        gaps.push({
          type,
          month: 0, // 月份信息需从 entries 上下文获取，此处简化
          start: `${prefix}${String(gapStart).padStart(3, '0')}`,
          end: `${prefix}${String(gapEnd).padStart(3, '0')}`,
          count: gapCount,
        })
      }
    }
  }

  return gaps
}

// ─── 4. 异常分录筛选（13 条规则） ─────────────────────────────

export function screenAnomalies(entries: JournalEntry[], rules: AnomalyRules): AnomalyResult[] {
  const results: AnomalyResult[] = []

  // 预计算：用于规则3（频繁调整）、规则9、规则10
  const accountEntryCount = new Map<string, number>()
  const accountAdjustCount = new Map<string, number>()
  for (const e of entries) {
    const code = e.accountCode
    accountEntryCount.set(code, (accountEntryCount.get(code) || 0) + 1)
    // 调整分录：摘要包含"调整"
    if (e.summary && e.summary.includes('调整')) {
      accountAdjustCount.set(code, (accountAdjustCount.get(code) || 0) + 1)
    }
  }

  // 预计算：用于规则7（尾数一致）
  const tailDigitsMap = new Map<string, number>()  // 尾数→出现次数
  for (const e of entries) {
    const amount = Math.max(e.debit, e.credit)
    if (amount > 0) {
      const tail = String(Math.round(amount * 100)).slice(-2)
      tailDigitsMap.set(tail, (tailDigitsMap.get(tail) || 0) + 1)
    }
  }

  // 预计算：用于规则8（重复检测）
  const duplicateKeys = new Map<string, number>()  // key→出现次数
  if (rules.duplicateCheck) {
    for (const e of entries) {
      // 同金额+同摘要
      const key = `${e.debit}|${e.credit}|${e.summary || ''}`
      duplicateKeys.set(key, (duplicateKeys.get(key) || 0) + 1)
    }
  }

  // 异常账户体量阈值（规则10）：平均分录数的3倍
  const avgEntryCount = entries.length > 0
    ? entries.length / Math.max(accountEntryCount.size, 1)
    : 0
  const unusualVolumeThreshold = avgEntryCount * 3

  for (const entry of entries) {
    const reasons: string[] = []
    const amount = Math.max(entry.debit, entry.credit)

    // 规则1: 假期录入
    if (rules.holidays.length > 0 && rules.holidays.includes(entry.voucherDate)) {
      reasons.push('假期录入')
    }

    // 规则2: 夜间录入（需要时间信息，voucherDate 只有日期则跳过）
    // 如果 voucherDate 包含时间信息 (YYYY-MM-DD HH:mm) 才检测
    if (entry.voucherDate && entry.voucherDate.length > 10) {
      const timeMatch = entry.voucherDate.match(/(\d{2}):(\d{2})/)
      if (timeMatch) {
        const hour = parseInt(timeMatch[1], 10)
        if (hour >= rules.nightStartHour || hour < rules.nightEndHour) {
          reasons.push('夜间录入')
        }
      }
    }

    // 规则3: 频繁调整分录（同账户多次调整）
    const adjustCount = accountAdjustCount.get(entry.accountCode) || 0
    if (adjustCount >= 3 && entry.summary && entry.summary.includes('调整')) {
      reasons.push('频繁调整')
    }

    // 规则4: 大额分录
    if (amount > rules.largeAmountThreshold) {
      reasons.push('大额分录')
    }

    // 规则5: 刚好低于审批限额（差额在5%以内）
    if (rules.approvalLimit > 0 && amount > 0) {
      const tolerance = rules.approvalLimit * 0.05
      if (amount < rules.approvalLimit && amount >= rules.approvalLimit - tolerance) {
        reasons.push('刚好低于审批限额')
      }
    }

    // 规则6: 约整数（末尾N个0）
    if (amount > 0 && rules.roundAmountDigits > 0) {
      const divisor = Math.pow(10, rules.roundAmountDigits)
      if (amount >= divisor && amount % divisor === 0) {
        reasons.push('约整数')
      }
    }

    // 规则7: 尾数一致（多条分录末两位相同，且该尾数出现≥5次）
    if (amount > 0) {
      const tail = String(Math.round(amount * 100)).slice(-2)
      const tailCount = tailDigitsMap.get(tail) || 0
      if (tailCount >= 5 && tail !== '00') {
        reasons.push('尾数一致')
      }
    }

    // 规则8: 同金额/同摘要重复
    if (rules.duplicateCheck) {
      const key = `${entry.debit}|${entry.credit}|${entry.summary || ''}`
      const dupCount = duplicateKeys.get(key) || 0
      if (dupCount >= 2) {
        reasons.push('同金额或同摘要重复')
      }
    }

    // 规则9: 借贷方不常见组合（借贷都有金额的分录行）
    if (entry.debit > 0 && entry.credit > 0) {
      reasons.push('借贷方不常见组合')
    }

    // 规则10: 大量分录的异常账户
    const entryCount = accountEntryCount.get(entry.accountCode) || 0
    if (entryCount > unusualVolumeThreshold && unusualVolumeThreshold > 0) {
      reasons.push('异常账户大量分录')
    }

    // 规则11: 与特殊事件有关（关键词匹配 — 使用 vagueKeywords 的超集）
    // 特殊事件关键词: 关联交易/收购/合并/重组/诉讼/处置
    const specialEventKeywords = ['关联交易', '收购', '合并', '重组', '诉讼', '处置', '清算', '破产']
    if (entry.summary) {
      for (const kw of specialEventKeywords) {
        if (entry.summary.includes(kw)) {
          reasons.push('与特殊事件有关')
          break
        }
      }
    }

    // 规则12: 含模糊词
    if (entry.summary && rules.vagueKeywords.length > 0) {
      for (const kw of rules.vagueKeywords) {
        if (entry.summary.includes(kw)) {
          reasons.push('含模糊词')
          break
        }
      }
    }

    // 规则13: 没有摘要
    if (rules.checkEmptySummary && (!entry.summary || entry.summary.trim() === '')) {
      reasons.push('没有摘要')
    }

    if (reasons.length > 0) {
      results.push({ entry, reasons })
    }
  }

  return results
}

// ─── 5. 本福特首位数分布 ─────────────────────────────────────

/**
 * 提取金额的首位非零数字
 */
function getFirstDigit(amount: number): number | null {
  const abs = Math.abs(amount)
  if (abs < 1e-10) return null  // 零或极小值排除
  const str = abs.toExponential()
  const firstChar = str[0]
  const digit = parseInt(firstChar, 10)
  return digit >= 1 && digit <= 9 ? digit : null
}

export function benfordDistribution(amounts: number[]): BenfordDigitResult[] {
  // 过滤有效金额（非零）
  const validAmounts = amounts.filter(a => Math.abs(a) >= 1e-10)
  const total = validAmounts.length

  if (total === 0) {
    // 返回全零分布
    return Array.from({ length: 9 }, (_, i) => ({
      digit: i + 1,
      expected: Math.log10(1 + 1 / (i + 1)),
      count: 0,
      actual: 0,
      deviation: 0 - Math.log10(1 + 1 / (i + 1)),
      chi2Contribution: 0,
    }))
  }

  // 统计首位数频率
  const counts = new Array(10).fill(0)  // index 0 unused, 1-9
  for (const a of validAmounts) {
    const d = getFirstDigit(a)
    if (d !== null) counts[d]++
  }

  const results: BenfordDigitResult[] = []
  for (let d = 1; d <= 9; d++) {
    const expected = Math.log10(1 + 1 / d)
    const count = counts[d]
    const actual = count / total
    const deviation = actual - expected
    // 卡方贡献: (observed - expected_count)² / expected_count
    const expectedCount = expected * total
    const chi2Contribution = expectedCount > 0
      ? Math.pow(count - expectedCount, 2) / expectedCount
      : 0
    results.push({ digit: d, expected, count, actual, deviation, chi2Contribution })
  }

  return results
}

// ─── 6. 卡方检验 ────────────────────────────────────────────

/**
 * 卡方分布右尾临界值表 (df=8)
 * 常用显著性水平对应的临界值
 */
const CHI2_CRITICAL_DF8: Record<number, number> = {
  0.10: 13.362,
  0.05: 15.507,
  0.025: 17.535,
  0.01: 20.090,
  0.005: 21.955,
  0.001: 26.125,
}

export function benfordChiSquareTest(
  distribution: BenfordDigitResult[],
  alpha: number = 0.05,
): BenfordTestResult {
  const chi2Total = distribution.reduce((sum, d) => sum + d.chi2Contribution, 0)

  // 查表获取临界值（df=8 for digits 1-9）
  const criticalValue = CHI2_CRITICAL_DF8[alpha] ?? CHI2_CRITICAL_DF8[0.05]
  const significant = chi2Total > criticalValue

  return { chi2Total, criticalValue, significant }
}
