/**
 * useH6Check — H6-4 固定资产清理检查表 composable
 *
 * 对齐致同源模板「固定资产清理检查表」编制逻辑：
 * 一、审计目标（存在/发生、完整性、权利义务、计价分摊）
 * 二、测试原因 + 测试内容说明
 * 三、凭证级样本明细（日期/凭证号/类别/名称 + 被清理固定资产情况
 *     + 清理费用/收入/净损益 + 转营业外/转处置收益 + 期末余额 + 原因/批准/索引）
 * 四、合计 + 检查比例（样本净值合计 ÷ H6-2 本期减少净值）
 * 五、审计说明 / 结论
 *
 * 公式（源模板）：
 *   净值 = 原值 − 累计折旧 − 减值准备
 *   清理净损益 = 清理收入 − 清理费用 − 净值
 *   检查比例 = 样本净值合计 / H6-2 本期减少合计
 *
 * Saves: H6-4-rows / H6-4-test-reasons / H6-4-sampling / H6-4-note / H6-4-conclusion
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcNetBookValue,
  calcDisposalGainLoss,
  calcSubtotal,
  isClearingOverOneYear,
  defaultH6PeriodEnd,
} from './useH6FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 测试原因（源模板勾选） */
export type H6CheckTestReason =
  | 'largeAmount'
  | 'relatedParty'
  | 'frequentLarge'
  | 'abnormal'
  | 'other'

/** H6-4 检查表行（对齐源模板 18 列 + 联动增强） */
export interface H6CheckRow {
  rowId: string
  /** 关联 H6-2 明细行 */
  linkedDetailRowId: string
  /** 日期 */
  date: string
  /** 凭证编号 */
  voucherNo: string
  /** 固定资产类别 */
  category: string
  /** 固定资产名称 */
  assetName: string
  /** 对方科目 */
  counterpartAccount: string
  /** 原值 */
  originalCost: number
  /** 累计折旧 */
  accumulatedDepreciation: number
  /** 减值准备 */
  impairment: number
  /** 净值（公式） */
  netValue: number
  /** 清理费用 */
  clearingExpense: number
  /** 清理收入 */
  clearingIncome: number
  /** 清理净损益（公式） */
  clearingGainLoss: number
  /** 转营业外收入/支出 */
  toNonOperating: number
  /** 转资产处置收益 */
  toDisposalGain: number
  /** 期末余额 */
  endingBalance: number
  /** 清理原因 */
  clearingReason: string
  /** 批准人 */
  approvedBy: string
  /** 相关资料索引号 */
  indexRef: string
  /** 联动 H1-8 索引 */
  refH1Code: string
  /** 联动 H10 索引 */
  refH10Code: string
  /** 核对内容勾选：0原始凭证齐全 1记账相符 2账务正确 3期间恰当 4其他 */
  checks: boolean[]
  /** 是否异常 */
  isAbnormal: boolean
  /** 附件 URL / 文件名 */
  attachmentUrl: string
  /** 备注 */
  remark: string
}

export interface H6CheckSampling {
  /** 本期固定资产清理减少合计（总体，优先自 H6-2 带入） */
  totalPopulation: number
  samplingMethod: string
  /** 总体是否手工覆盖 */
  populationManual: boolean
  /** 特定样本说明 */
  specificSample: string
  /** 抽样过程叙述 */
  samplingProcess: string
}

export interface H6CheckSummary {
  checkedCount: number
  originalCostTotal: number
  netValueTotal: number
  expenseTotal: number
  incomeTotal: number
  gainLossTotal: number
  toNonOperatingTotal: number
  toDisposalGainTotal: number
  endingBalanceTotal: number
  /** 检查比例(%) = 样本净值 / 总体 */
  coverageRate: number
  anomalyCount: number
  /** 期末余额非零笔数（过渡科目应清零） */
  nonZeroEndingCount: number
  /** 结转分摊与净损益勾稽异常笔数 */
  transferMismatchCount: number
  /** 挂账超 1 年笔数 */
  overOneYearCount: number
  /** 与 H10 净损益勾稽差额（检查表转处置收益合计 − H10 可取数） */
  h10GainLossDiff: number | null
  hasLowCoverage: boolean
  warning: string
}

/**
 * 测试内容说明（核对内容 1–5）
 * 第5项补全致同模板空白：结转分摊 + 1606 清零 + H10 勾稽
 */
export const CHECK_CONTENT_LABELS = [
  '原始凭证是否齐全（处置审批/评估/合同/发票/收款等）',
  '记账凭证与原始凭证是否相符',
  '账务处理是否正确（原值−累计折旧−减值=净值；清理净损益=收入−费用−净值）',
  '是否记录于恰当会计期间（截止测试）',
  '结转营业外与资产处置收益分摊正确；1606期末已清零；与H10勾稽一致',
] as const

export const H6_CONCLUSION_TEMPLATES = [
  { value: 'A', label: 'A、未见异常' },
  {
    value: 'B',
    label: 'B、除上述重大不符事项作为调整事项予以调整外，其余未见异常',
  },
  {
    value: 'C',
    label: 'C、由于存在重大未调整事项（或审计范围受限），不可确认',
  },
] as const

const ROWS_KEY = 'H6-4-rows'
const REASONS_KEY = 'H6-4-test-reasons'
const SAMPLING_KEY = 'H6-4-sampling'
const NOTE_KEY = 'H6-4-note'
const CONCLUSION_KEY = 'H6-4-conclusion'

function _num(v: any): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _boolLike(v: unknown): boolean {
  return v === true || v === 'Y' || v === 'y' || v === '是' || v === 1 || v === '1' || v === 'TRUE' || v === 'true'
}

function _boolAbnormal(v: unknown): boolean {
  if (v === false || v === '否' || v === 'N' || v === 'n' || v === 0 || v === '0' || v === '') return false
  return _boolLike(v)
}

/** 兼容 checks[] 数组与导入导出扁平 check1–check5 */
function _normChecks(raw: any): boolean[] {
  if (Array.isArray(raw?.checks)) {
    return [0, 1, 2, 3, 4].map((i) => Boolean(raw.checks[i]))
  }
  return [1, 2, 3, 4, 5].map((i) => _boolLike(raw?.[`check${i}`]))
}

function _safeParse(raw: any): any {
  if (raw == null) return null
  if (typeof raw !== 'string') return raw
  try {
    return JSON.parse(raw)
  } catch {
    return raw
  }
}

/** 行级公式重算 */
export function recalcH6CheckRow(row: H6CheckRow): void {
  row.netValue = calcNetBookValue(
    _num(row.originalCost),
    _num(row.accumulatedDepreciation),
    _num(row.impairment),
  )
  // 源模板：清理净损益 = 清理收入 − 清理费用 − 净值（税费并入清理费用或单独列；此处与 H6-2 一致可含税）
  row.clearingGainLoss = calcDisposalGainLoss(
    _num(row.clearingIncome),
    row.netValue,
    _num(row.clearingExpense),
    0,
  )
}

/** 结转分摊是否与净损益勾稽：|转营业外|+|转处置收益| ≈ |净损益|（允许 0.5 容差） */
export function isTransferMismatch(row: H6CheckRow): boolean {
  const gl = Math.abs(_num(row.clearingGainLoss))
  if (gl < 0.005 && Math.abs(_num(row.endingBalance)) < 0.005) return false
  const allocated =
    Math.abs(_num(row.toNonOperating)) + Math.abs(_num(row.toDisposalGain))
  // 已结转（期末≈0）时，分摊应覆盖净损益；挂账则允许差额≈期末余额
  const endAbs = Math.abs(_num(row.endingBalance))
  if (endAbs < 0.005) {
    return Math.abs(allocated - gl) > 0.5
  }
  return false
}

/** 挂账且转入清理超 1 年 */
export function isHangingOverOneYear(row: H6CheckRow, asOfDate?: string): boolean {
  if (Math.abs(_num(row.endingBalance)) < 0.005) return false
  return isClearingOverOneYear(row.date, asOfDate || defaultH6PeriodEnd())
}

/** 本地草拟审计说明 */
export function draftH6AuditNote(ctx: {
  summary: H6CheckSummary
  sampling: H6CheckSampling
  testReasons: H6CheckTestReason[]
  otherText?: string
}): string {
  const reasonMap: Record<string, string> = {
    largeAmount: '大额',
    relatedParty: '关联方',
    frequentLarge: '大额交易频繁',
    abnormal: '异常',
    other: ctx.otherText ? `其他（${ctx.otherText}）` : '其他',
  }
  const reasons = ctx.testReasons.map((r) => reasonMap[r] || r).join('、') || '未勾选'
  const lines = [
    `一、抽样：采用${ctx.sampling.samplingMethod || '判断抽样'}，测试原因：${reasons}。`,
    `本期减少总体净值 ${ctx.sampling.totalPopulation.toLocaleString('zh-CN', { maximumFractionDigits: 2 })} 元，检查样本 ${ctx.summary.checkedCount} 笔，样本净值合计 ${ctx.summary.netValueTotal.toLocaleString('zh-CN', { maximumFractionDigits: 2 })} 元，检查比例 ${ctx.summary.coverageRate.toFixed(2)}%。`,
  ]
  if (ctx.sampling.specificSample) lines.push(`特定样本：${ctx.sampling.specificSample}`)
  if (ctx.sampling.samplingProcess) lines.push(`抽样过程：${ctx.sampling.samplingProcess}`)
  lines.push(
    `二、结果：清理净损益合计 ${ctx.summary.gainLossTotal.toLocaleString('zh-CN', { maximumFractionDigits: 2 })} 元（转营业外 ${ctx.summary.toNonOperatingTotal.toLocaleString('zh-CN', { maximumFractionDigits: 2 })} / 转处置收益 ${ctx.summary.toDisposalGainTotal.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}）；异常 ${ctx.summary.anomalyCount} 笔，期末未清零 ${ctx.summary.nonZeroEndingCount} 笔，超1年挂账 ${ctx.summary.overOneYearCount} 笔，结转勾稽异常 ${ctx.summary.transferMismatchCount} 笔。`,
  )
  if (ctx.summary.hasLowCoverage) {
    lines.push('三、检查比例偏低，已/拟扩大样本量或说明原因：________。')
  } else {
    lines.push('三、检查比例尚可，未见需进一步扩样事项（如有例外见上）。')
  }
  if (ctx.summary.h10GainLossDiff != null && Math.abs(ctx.summary.h10GainLossDiff) > 0.5) {
    lines.push(`四、与 H10 处置损益勾稽差额 ${ctx.summary.h10GainLossDiff.toLocaleString('zh-CN', { maximumFractionDigits: 2 })} 元，需进一步核对。`)
  }
  return lines.join('\n')
}

/** 按摘要自动选结论草稿 */
export function draftH6Conclusion(summary: H6CheckSummary): string {
  if (
    summary.anomalyCount > 0 ||
    summary.transferMismatchCount > 0 ||
    (summary.h10GainLossDiff != null && Math.abs(summary.h10GainLossDiff) > 0.5)
  ) {
    return H6_CONCLUSION_TEMPLATES[1].label
  }
  if (summary.nonZeroEndingCount > 0 || summary.overOneYearCount > 0 || summary.hasLowCoverage) {
    return H6_CONCLUSION_TEMPLATES[1].label
  }
  return H6_CONCLUSION_TEMPLATES[0].label
}

/** OCR 字段映射 */
export function mapOcrToH6CheckFields(fields: Record<string, any>): Partial<H6CheckRow> {
  const pick = (...keys: string[]) => {
    for (const k of keys) {
      if (fields[k] != null && String(fields[k]).trim() !== '') return String(fields[k]).trim()
    }
    return ''
  }
  const numPick = (...keys: string[]) => {
    for (const k of keys) {
      if (fields[k] != null && fields[k] !== '') {
        const n = Number(String(fields[k]).replace(/,/g, ''))
        if (Number.isFinite(n)) return n
      }
    }
    return undefined
  }
  const patch: Partial<H6CheckRow> = {}
  const name = pick('assetName', 'asset_name', 'name', '合同标的', '设备名称', '固定资产名称')
  if (name) patch.assetName = name
  const voucherNo = pick('voucherNo', 'voucher_no', '凭证号', '凭证编号')
  if (voucherNo) patch.voucherNo = voucherNo
  const date = pick('date', 'voucherDate', '日期', '合同日期', '签约日期')
  if (date) patch.date = date
  const approvedBy = pick('approvedBy', 'approver', '批准人', '审批人')
  if (approvedBy) patch.approvedBy = approvedBy
  const party = pick('contractParty', '对方', '合同对方', '买方')
  if (party) patch.remark = (patch.remark ? patch.remark + '；' : '') + `对方:${party}`
  const income = numPick('clearingIncome', 'disposalIncome', 'amount', '合同金额', '价款', '清理收入')
  if (income != null) patch.clearingIncome = income
  const cost = numPick('originalCost', '原值')
  if (cost != null) patch.originalCost = cost
  const indexRef = pick('indexRef', '合同编号', 'contractNo', 'invoiceNo', '发票号')
  if (indexRef) patch.indexRef = indexRef
  return patch
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH6Check(params: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const { allResponses, onSave } = params

  const rows = ref<H6CheckRow[]>([])
  const testReasons = ref<H6CheckTestReason[]>([])
  const testReasonOther = ref('')
  const sampling = ref<H6CheckSampling>({
    totalPopulation: 0,
    samplingMethod: '货币单元抽样',
    populationManual: false,
    specificSample: '大额清理、关联方处置、异常挂账全部测试',
    samplingProcess: '',
  })
  const auditNote = ref('')
  const auditConclusion = ref('')

  function _getItemRaw(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    return _safeParse(item.remark ?? item.conclusion ?? item)
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    if (!item) return ''
    const v = item.remark ?? item.conclusion ?? ''
    return typeof v === 'string' ? v : ''
  }

  /** 识别旧版合规矩阵行（disposalApproval 等字段）→ 降级为名称+备注 */
  function _isLegacyComplianceRow(raw: any): boolean {
    return (
      raw != null &&
      typeof raw === 'object' &&
      ('disposalApproval' in raw || 'assetValuation' in raw) &&
      !('originalCost' in raw) &&
      !('clearingIncome' in raw)
    )
  }

  function _normalizeRow(raw: any): H6CheckRow {
    if (_isLegacyComplianceRow(raw)) {
      const legacyDims = [
        raw.disposalApproval,
        raw.assetValuation,
        raw.taxTreatment,
        raw.accountingTreatment,
        raw.incomeRecognition,
        raw.expenseAllocation,
        raw.transferTiming,
        raw.conclusion,
      ]
        .filter(Boolean)
        .join('/')
      const row: H6CheckRow = {
        rowId: raw.rowId ?? `chk-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
        linkedDetailRowId: raw.linkedDetailRowId ?? '',
        date: '',
        voucherNo: '',
        category: '',
        assetName: raw.projectName ?? raw.assetName ?? '',
        counterpartAccount: '',
        originalCost: 0,
        accumulatedDepreciation: 0,
        impairment: 0,
        netValue: 0,
        clearingExpense: 0,
        clearingIncome: 0,
        clearingGainLoss: 0,
        toNonOperating: 0,
        toDisposalGain: 0,
        endingBalance: 0,
        clearingReason: '',
        approvedBy: '',
        indexRef: '',
        refH1Code: '',
        refH10Code: '',
        checks: [false, false, false, false, false],
        isAbnormal: legacyDims.includes('不合规'),
        attachmentUrl: '',
        remark:
          raw.remark ||
          (legacyDims ? `【旧版合规结论已迁移】${legacyDims}` : ''),
      }
      return row
    }

    const checks = _normChecks(raw)

    const row: H6CheckRow = {
      rowId: raw.rowId ?? `chk-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      linkedDetailRowId: raw.linkedDetailRowId ?? '',
      date: raw.date ?? '',
      voucherNo: raw.voucherNo ?? '',
      category: raw.category ?? '',
      assetName: raw.assetName ?? raw.projectName ?? '',
      counterpartAccount: raw.counterpartAccount ?? '',
      originalCost: _num(raw.originalCost),
      accumulatedDepreciation: _num(
        raw.accumulatedDepreciation ?? raw.accDepreciation ?? raw.accDep,
      ),
      impairment: _num(raw.impairment),
      netValue: 0,
      clearingExpense: _num(raw.clearingExpense ?? raw.disposalExpenses ?? raw.disposalCost),
      clearingIncome: _num(raw.clearingIncome ?? raw.disposalIncome),
      clearingGainLoss: 0,
      toNonOperating: _num(raw.toNonOperating),
      toDisposalGain: _num(raw.toDisposalGain),
      endingBalance: _num(raw.endingBalance),
      clearingReason: raw.clearingReason ?? raw.disposalReason ?? '',
      approvedBy: raw.approvedBy ?? '',
      indexRef: raw.indexRef ?? '',
      refH1Code: raw.refH1Code ?? raw.refH1 ?? '',
      refH10Code: raw.refH10Code ?? raw.refH10 ?? '',
      checks,
      isAbnormal: _boolAbnormal(raw.isAbnormal),
      attachmentUrl: raw.attachmentUrl ?? '',
      remark: raw.remark ?? '',
    }
    recalcH6CheckRow(row)
    return row
  }

  /** 从 H6-2 取本期减少净值合计（检查比例分母） */
  function _calcLinkedPopulation(): { amount: number; source: 'H6-2' | '' } {
    const data = _getItemRaw('H6-2-rows')
    if (!Array.isArray(data) || data.length === 0) return { amount: 0, source: '' }
    let total = 0
    for (const r of data) {
      const cost = _num(r.originalCost)
      const dep = _num(r.accumulatedDepreciation)
      const imp = _num(r.impairment)
      // H6-2 当前无减值列时 imp=0；净值优先用已存字段
      const nv =
        r.netBookValue != null && r.netBookValue !== ''
          ? _num(r.netBookValue)
          : calcNetBookValue(cost, dep, imp)
      total += nv
    }
    return { amount: total, source: total > 0 ? 'H6-2' : '' }
  }

  const linkedPopulation = computed(() => _calcLinkedPopulation())

  function load(): void {
    const data = _getItemRaw(ROWS_KEY)
    rows.value = Array.isArray(data) ? data.map(_normalizeRow) : []

    const reasons = _getItemRaw(REASONS_KEY)
    if (reasons && typeof reasons === 'object') {
      testReasons.value = Array.isArray(reasons.reasons) ? reasons.reasons : []
      testReasonOther.value = reasons.otherText ?? ''
    } else {
      testReasons.value = []
      testReasonOther.value = ''
    }

    const samp = _getItemRaw(SAMPLING_KEY)
    if (samp && typeof samp === 'object') {
      sampling.value = {
        totalPopulation: _num(samp.totalPopulation),
        samplingMethod: samp.samplingMethod ?? '货币单元抽样',
        populationManual: Boolean(samp.populationManual),
        specificSample: samp.specificSample ?? '大额清理、关联方处置、异常挂账全部测试',
        samplingProcess: samp.samplingProcess ?? '',
      }
    }

    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)

    // 总体为空且非手工锁定时，自动从 H6-2 带入（仅内存）
    if (!sampling.value.populationManual && !(sampling.value.totalPopulation > 0)) {
      const linked = _calcLinkedPopulation()
      if (linked.amount > 0) {
        sampling.value.totalPopulation = linked.amount
      }
    }
  }

  watch(allResponses, () => load(), { immediate: true })

  // ─── Summary ───────────────────────────────────────────────────────────────

  /** 尝试从 H10 相关 checklist 取处置损益合计 */
  function _calcH10GainLoss(): number | null {
    const keys = ['H10-2-rows', 'H10-rows', 'H10-1-gain-loss-total', 'H10-detail-rows']
    for (const key of keys) {
      const raw = _getItemRaw(key)
      if (raw == null) continue
      if (typeof raw === 'number') return raw
      if (typeof raw === 'string' && raw && !Number.isNaN(Number(raw))) return Number(raw)
      if (Array.isArray(raw)) {
        let sum = 0
        let hit = false
        for (const r of raw) {
          const v = r.gainLoss ?? r.disposalGainLoss ?? r.netGainLoss ?? r.amount
          if (v != null && v !== '') {
            sum += _num(v)
            hit = true
          }
        }
        if (hit) return sum
      }
      if (typeof raw === 'object' && raw.totalGainLoss != null) return _num(raw.totalGainLoss)
    }
    return null
  }

  const summary: ComputedRef<H6CheckSummary> = computed(() => {
    const checkedCount = rows.value.length
    const originalCostTotal = calcSubtotal(rows.value.map((r) => r.originalCost))
    const netValueTotal = calcSubtotal(rows.value.map((r) => r.netValue))
    const expenseTotal = calcSubtotal(rows.value.map((r) => r.clearingExpense))
    const incomeTotal = calcSubtotal(rows.value.map((r) => r.clearingIncome))
    const gainLossTotal = calcSubtotal(rows.value.map((r) => r.clearingGainLoss))
    const toNonOperatingTotal = calcSubtotal(rows.value.map((r) => r.toNonOperating))
    const toDisposalGainTotal = calcSubtotal(rows.value.map((r) => r.toDisposalGain))
    const endingBalanceTotal = calcSubtotal(rows.value.map((r) => r.endingBalance))
    const anomalyCount = rows.value.filter((r) => r.isAbnormal).length
    const nonZeroEndingCount = rows.value.filter(
      (r) => Math.abs(_num(r.endingBalance)) > 0.005,
    ).length
    const transferMismatchCount = rows.value.filter((r) => isTransferMismatch(r)).length
    const overOneYearCount = rows.value.filter((r) => isHangingOverOneYear(r)).length

    const h10 = _calcH10GainLoss()
    const h10GainLossDiff =
      h10 == null ? null : toDisposalGainTotal - h10

    const pop = sampling.value.totalPopulation
    const coverageRate = pop > 0 ? (netValueTotal / pop) * 100 : 0
    const hasLowCoverage = pop > 0 && coverageRate < 20

    const warnings: string[] = []
    if (anomalyCount > 0) warnings.push(`发现${anomalyCount}笔异常样本`)
    if (nonZeroEndingCount > 0) {
      warnings.push(`${nonZeroEndingCount}笔期末余额未清零（1606过渡科目应结转完毕）`)
    }
    if (overOneYearCount > 0) {
      warnings.push(`${overOneYearCount}笔挂账超1年，请说明进展并关注附注披露`)
    }
    if (transferMismatchCount > 0) {
      warnings.push(`${transferMismatchCount}笔结转分摊与清理净损益勾稽异常`)
    }
    if (h10GainLossDiff != null && Math.abs(h10GainLossDiff) > 0.5) {
      warnings.push(`转处置收益与 H10 勾稽差额 ${h10GainLossDiff.toFixed(2)} 元`)
    }
    if (hasLowCoverage) {
      warnings.push(`检查比例偏低（${coverageRate.toFixed(1)}%），请扩样或说明原因`)
    }

    return {
      checkedCount,
      originalCostTotal,
      netValueTotal,
      expenseTotal,
      incomeTotal,
      gainLossTotal,
      toNonOperatingTotal,
      toDisposalGainTotal,
      endingBalanceTotal,
      coverageRate,
      anomalyCount,
      nonZeroEndingCount,
      transferMismatchCount,
      overOneYearCount,
      h10GainLossDiff,
      hasLowCoverage,
      warning: warnings.join('；'),
    }
  })

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persistRows(): void {
    if (!onSave) return
    onSave(
      ROWS_KEY,
      rows.value.map((r) => ({
        rowId: r.rowId,
        linkedDetailRowId: r.linkedDetailRowId,
        date: r.date,
        voucherNo: r.voucherNo,
        category: r.category,
        assetName: r.assetName,
        counterpartAccount: r.counterpartAccount,
        originalCost: r.originalCost,
        accumulatedDepreciation: r.accumulatedDepreciation,
        impairment: r.impairment,
        netValue: r.netValue,
        clearingExpense: r.clearingExpense,
        clearingIncome: r.clearingIncome,
        clearingGainLoss: r.clearingGainLoss,
        toNonOperating: r.toNonOperating,
        toDisposalGain: r.toDisposalGain,
        endingBalance: r.endingBalance,
        clearingReason: r.clearingReason,
        approvedBy: r.approvedBy,
        indexRef: r.indexRef,
        refH1Code: r.refH1Code,
        refH10Code: r.refH10Code,
        checks: [...r.checks],
        // 扁平字段供导入导出 round-trip（与后端 _H6_4_KEYS 对齐）
        check1: Boolean(r.checks[0]),
        check2: Boolean(r.checks[1]),
        check3: Boolean(r.checks[2]),
        check4: Boolean(r.checks[3]),
        check5: Boolean(r.checks[4]),
        isAbnormal: r.isAbnormal,
        attachmentUrl: r.attachmentUrl,
        remark: r.remark,
      })),
    )
  }

  function _persistReasons(): void {
    onSave?.(REASONS_KEY, {
      reasons: [...testReasons.value],
      otherText: testReasonOther.value,
    })
  }

  function _persistSampling(): void {
    onSave?.(SAMPLING_KEY, { ...sampling.value })
  }

  // ─── Actions ───────────────────────────────────────────────────────────────

  function updateTestReasons(reasons: H6CheckTestReason[], otherText = ''): void {
    testReasons.value = [...reasons]
    testReasonOther.value = otherText
    _persistReasons()
  }

  function updateSampling(patch: Partial<H6CheckSampling>): void {
    Object.assign(sampling.value, patch)
    if ('totalPopulation' in patch) sampling.value.populationManual = true
    _persistSampling()
  }

  function syncPopulationFromH62(force = false): {
    ok: boolean
    amount: number
    source: string
  } {
    const linked = _calcLinkedPopulation()
    if (!(linked.amount > 0)) return { ok: false, amount: 0, source: '' }
    if (force || !sampling.value.populationManual) {
      sampling.value.totalPopulation = linked.amount
      sampling.value.populationManual = false
      _persistSampling()
    }
    return { ok: true, amount: linked.amount, source: linked.source }
  }

  function addRow(assetName = ''): void {
    const row = _normalizeRow({ assetName: assetName.trim() })
    rows.value.push(row)
    _persistRows()
  }

  function deleteRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    rows.value.splice(idx, 1)
    _persistRows()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return

    if (field === 'checks' && Array.isArray(value)) {
      row.checks = [0, 1, 2, 3, 4].map((i) => Boolean(value[i]))
      _persistRows()
      return
    }

    if (field === 'isAbnormal') {
      row.isAbnormal = Boolean(value)
      _persistRows()
      return
    }

    const strFields = [
      'date',
      'voucherNo',
      'category',
      'assetName',
      'counterpartAccount',
      'clearingReason',
      'approvedBy',
      'indexRef',
      'refH1Code',
      'refH10Code',
      'attachmentUrl',
      'remark',
      'linkedDetailRowId',
    ]
    if (strFields.includes(field)) {
      ;(row as any)[field] = String(value ?? '')
      _persistRows()
      return
    }

    const numFields = [
      'originalCost',
      'accumulatedDepreciation',
      'impairment',
      'clearingExpense',
      'clearingIncome',
      'toNonOperating',
      'toDisposalGain',
      'endingBalance',
    ]
    if (numFields.includes(field)) {
      ;(row as any)[field] = _num(value)
      recalcH6CheckRow(row)
      _persistRows()
      return
    }
  }

  /** 从 H6-2 同步样本行（增量，不覆盖已有 linked 行的手工字段） */
  function syncFromDetailRows(
    detailRows: Array<{
      rowId: string
      assetName: string
      originalCost?: number
      accumulatedDepreciation?: number
      impairment?: number
      disposalIncome?: number
      disposalExpenses?: number
      taxAmount?: number
      disposalReason?: string
      startDate?: string
      transferAccount?: string
      gainLoss?: number
      netBookValue?: number
      status?: string
      refH1Code?: string
      refH10Code?: string
    }>,
  ): number {
    let added = 0
    for (const d of detailRows) {
      const existing = rows.value.find((r) => r.linkedDetailRowId === d.rowId)
      if (existing) {
        existing.assetName = d.assetName || existing.assetName
        if (d.originalCost != null) existing.originalCost = _num(d.originalCost)
        if (d.accumulatedDepreciation != null) {
          existing.accumulatedDepreciation = _num(d.accumulatedDepreciation)
        }
        if (d.impairment != null) existing.impairment = _num(d.impairment)
        if (d.disposalIncome != null) existing.clearingIncome = _num(d.disposalIncome)
        if (d.disposalExpenses != null || d.taxAmount != null) {
          existing.clearingExpense =
            _num(d.disposalExpenses) + _num(d.taxAmount)
        }
        if (d.disposalReason) existing.clearingReason = d.disposalReason
        if (d.startDate) existing.date = d.startDate
        if (d.refH1Code) existing.refH1Code = d.refH1Code
        if (d.refH10Code) existing.refH10Code = d.refH10Code
        if (d.transferAccount) existing.counterpartAccount = d.transferAccount
        if (d.status === '已结转') {
          existing.endingBalance = 0
          const gl = _num(d.gainLoss)
          const acct = (d.transferAccount || '').toLowerCase()
          if (acct.includes('营业外') || acct.includes('6301') || acct.includes('6711')) {
            existing.toNonOperating = gl
            existing.toDisposalGain = 0
          } else if (
            acct.includes('处置') ||
            acct.includes('6115') ||
            acct.includes('资产处置')
          ) {
            existing.toDisposalGain = gl
            existing.toNonOperating = 0
          }
        }
        recalcH6CheckRow(existing)
        continue
      }

      const expense = _num(d.disposalExpenses) + _num(d.taxAmount)
      const row = _normalizeRow({
        linkedDetailRowId: d.rowId,
        assetName: d.assetName,
        date: d.startDate ?? '',
        originalCost: d.originalCost,
        accumulatedDepreciation: d.accumulatedDepreciation,
        impairment: d.impairment,
        clearingIncome: d.disposalIncome,
        clearingExpense: expense,
        clearingReason: d.disposalReason,
        endingBalance: d.status === '已结转' ? 0 : _num(d.netBookValue),
        counterpartAccount: d.transferAccount ?? '',
        refH1Code: d.refH1Code ?? '',
        refH10Code: d.refH10Code ?? '',
      })
      if (d.status === '已结转') {
        const gl = row.clearingGainLoss
        const acct = (d.transferAccount || '').toLowerCase()
        if (acct.includes('营业外') || acct.includes('6301') || acct.includes('6711')) {
          row.toNonOperating = gl
        } else {
          row.toDisposalGain = gl
        }
      }
      rows.value.push(row)
      added++
    }
    _persistRows()
    syncPopulationFromH62(false)
    return added
  }

  /** 抽凭引擎回填（增强：借贷方向、对方科目、摘要） */
  function fillFromSampledVouchers(samples: any[]): number {
    let n = 0
    for (const s of samples) {
      const name =
        s.summary || s.assetName || s.debtorName || s.businessContent || s.accountName || '抽凭样本'
      addRow(String(name).slice(0, 80))
      const last = rows.value[rows.value.length - 1]
      if (!last) continue
      if (s.voucherNo || s.voucher_no) last.voucherNo = s.voucherNo || s.voucher_no
      if (s.date || s.voucherDate) last.date = s.date || s.voucherDate
      if (s.counterpartAccount) last.counterpartAccount = s.counterpartAccount
      const debit = _num(s.debitAmount ?? s.debit)
      const credit = _num(s.creditAmount ?? s.credit)
      // 1606 借方多为转入清理（近似原值/净值），贷方多为结转损益
      if (debit > 0 && credit <= 0) {
        last.originalCost = debit
        last.endingBalance = debit
      } else if (credit > 0) {
        last.clearingIncome = last.clearingIncome || credit
        last.toDisposalGain = credit
        last.endingBalance = 0
      } else if (_num(s.amount) > 0) {
        last.originalCost = _num(s.amount)
      }
      if (s.abnormal || s.checkResult === 'ERR') last.isAbnormal = true
      recalcH6CheckRow(last)
      n++
    }
    if (n > 0) _persistRows()
    return n
  }

  function applyOcrFields(rowId: string, fields: Record<string, any>): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    const patch = mapOcrToH6CheckFields(fields)
    Object.assign(row, patch)
    recalcH6CheckRow(row)
    _persistRows()
  }

  function applyLocalDraftNote(): string {
    const text = draftH6AuditNote({
      summary: summary.value,
      sampling: sampling.value,
      testReasons: testReasons.value,
      otherText: testReasonOther.value,
    })
    saveAuditNote(text)
    return text
  }

  function applyLocalDraftConclusion(): string {
    const text = draftH6Conclusion(summary.value)
    saveAuditConclusion(text)
    return text
  }

  function saveAuditNote(text: string): void {
    auditNote.value = text
    onSave?.(NOTE_KEY, text)
  }

  function saveAuditConclusion(text: string): void {
    auditConclusion.value = text
    onSave?.(CONCLUSION_KEY, text)
  }

  function applyConclusionTemplate(code: string): void {
    const t = H6_CONCLUSION_TEMPLATES.find((x) => x.value === code)
    if (!t) return
    auditConclusion.value = t.label
    onSave?.(CONCLUSION_KEY, t.label)
  }

  function save(): void {
    _persistRows()
    _persistReasons()
    _persistSampling()
  }

  return {
    rows,
    testReasons,
    testReasonOther,
    sampling,
    auditNote,
    auditConclusion,
    summary,
    linkedPopulation,
    CHECK_CONTENT_LABELS,
    H6_CONCLUSION_TEMPLATES,
    updateTestReasons,
    updateSampling,
    syncPopulationFromH62,
    addRow,
    deleteRow,
    updateCell,
    syncFromDetailRows,
    fillFromSampledVouchers,
    applyOcrFields,
    applyLocalDraftNote,
    applyLocalDraftConclusion,
    saveAuditNote,
    saveAuditConclusion,
    applyConclusionTemplate,
    save,
    load,
    recalcH6CheckRow,
    isTransferMismatch,
    isHangingOverOneYear,
  }
}

export default useH6Check
