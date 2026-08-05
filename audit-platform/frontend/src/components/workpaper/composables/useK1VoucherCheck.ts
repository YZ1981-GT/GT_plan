/**
 * useK1VoucherCheck.ts — K1-12 其他应收款检查表（凭证级测试）状态与计算
 *
 * 忠实反映致同源模板 K1-12 结构：
 *   一、审计目标（存在/权利义务/计价分摊 三认定）
 *   二、样本选取标准与规模（测试总体/特定样本/抽样总体/样本量/抽样方法/抽样过程）
 *   三、测试（1.本期发生额检查 2.期后收款检查，凭证级明细 + 五项核对）
 *   四、审计说明（检查比例表：本期借方/本期贷方/期末余额 → 账面/检查/比例）
 *   五、审计结论
 *
 * 纯函数 + ref 状态，持久化由组件层 emit('save') 负责。
 * 数据打包为单一 JSON 存 checklist_responses（item_id: K1-12-voucher-check）。
 */
import { ref, computed, type Ref } from 'vue'
import { isK1RelatedPartyMarked } from './useK1RelatedParty'
import { partyNameForColumn } from './shared/samplingPartyTarget'

// ─── 源模板五项核对（对齐 K1-12 Excel R13 测试内容说明）────────────────────────
export const K1_VOUCHER_CHECK_LABELS = [
  '原始凭证内容完整',
  '账务记录与原始凭证相符',
  '会计处理正确',
  '会计期间正确',
  '债务人与交易对手核对一致',
] as const

// ─── 凭证检查行 ───────────────────────────────────────────────────────────────
export interface K1VoucherRow {
  id: string
  debtorName: string        // 债务人名称
  date: string              // 日期
  voucherNo: string         // 凭证编号
  businessContent: string   // 业务内容
  offsetAccount: string     // 对方科目
  offsetSubAccount: string  // 对方明细科目
  debitAmount: number       // 借方金额
  creditAmount: number       // 贷方金额
  supportingDoc: string     // 支持性文件
  checks: boolean[]         // 核对内容 1-5
  indexNo: string           // 索引号
  abnormal: boolean         // 是否异常
  remark: string            // 备注说明
  /** OCR 附件文件名（可选） */
  ocrAttachment?: string
}

// ─── 样本选取标准与规模 ───────────────────────────────────────────────────────
export interface K1SampleCriteria {
  populationDebitCount: number    // 借方发生额凭证笔数
  populationDebitAmount: number   // 借方发生额金额
  populationCreditCount: number   // 贷方发生额凭证笔数
  populationCreditAmount: number  // 贷方发生额金额
  specificSample: string          // 特定样本说明（大额/关联方/异常）
  samplingPopulationCount: number // 抽样总体笔数
  samplingPopulationAmount: number// 抽样总体金额
  sampleSize: number              // 确定的抽样样本量
  samplingMethod: string          // 抽样方法
  samplingProcess: string         // 抽样过程
  endBalance: number              // 期末余额（用于检查比例）
  /** 特定样本笔数（用于计算抽样总体） */
  specificSampleCount: number
  /** 特定样本金额（用于计算抽样总体） */
  specificSampleAmount: number
  /** 账面本期借方（检查比例分母，可勾 K1-1/K1-2） */
  bookDebitOccurrence: number
  /** 账面本期贷方（检查比例分母，可勾 K1-1/K1-2） */
  bookCreditOccurrence: number
}

export interface K1CheckRatioRow {
  direction: string     // 方向
  bookAmount: number    // 账面金额
  checkedAmount: number // 检查金额
  ratio: number | null  // 检查比例
}

export interface K1SampleSizeDeviation {
  planned: number
  actual: number
  diff: number
  needsExpansion: boolean
}

export interface K1LargeAmountSpecifics {
  counterparties: Array<{ name: string; amount: number; proportion: number | null }>
  totalAmount: number
  count: number
}

export interface K1AbnormalAdjDraft {
  summary: string
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
}

/** K1-12 → K1-4 推送标记，用于去重 */
export const K1_VOUCHER_PUSH_MARK = '【K1-12推送】'

const CHECK_LABELS = [...K1_VOUCHER_CHECK_LABELS]

function emptyRow(seq: number): K1VoucherRow {
  return {
    id: `k1vc-${Date.now()}-${seq}-${Math.random().toString(36).slice(2, 6)}`,
    debtorName: '', date: '', voucherNo: '', businessContent: '',
    offsetAccount: '', offsetSubAccount: '', debitAmount: 0, creditAmount: 0,
    supportingDoc: '', checks: [false, false, false, false, false],
    indexNo: '', abnormal: false, remark: '',
  }
}

function emptyCriteria(): K1SampleCriteria {
  return {
    populationDebitCount: 0, populationDebitAmount: 0,
    populationCreditCount: 0, populationCreditAmount: 0,
    specificSample: '大额（XX金额以上）、关联方/关联交易形成的款项、异常款项全部测试',
    samplingPopulationCount: 0, samplingPopulationAmount: 0,
    sampleSize: 0, samplingMethod: '货币单元抽样', samplingProcess: '', endBalance: 0,
    specificSampleCount: 0, specificSampleAmount: 0,
    bookDebitOccurrence: 0, bookCreditOccurrence: 0,
  }
}

function getNumFromMap(map: Map<string, any>, key: string): number {
  const raw = map.get(key)?.remark ?? map.get(key)?.conclusion
  const n = Number(raw)
  return Number.isFinite(n) ? n : 0
}

/** 从 K1-1 审定表其他应收款区块汇总借/贷发生额，期末余额优先取 K1-2 合计 */
export function pullK1BookAmounts(map: Map<string, any>): {
  debit: number
  credit: number
  endBalance: number
  relatedParties: string[]
} {
  let debit = 0
  let credit = 0
  const count = getNumFromMap(map, 'K1-1-receivable-count') || 5
  for (let i = 0; i < count; i++) {
    debit += getNumFromMap(map, `K1-1-receivable-r${i}-debit`)
    credit += getNumFromMap(map, `K1-1-receivable-r${i}-credit`)
  }
  const endBalance = getNumFromMap(map, 'K1-2-end-subtotal')
    || getNumFromMap(map, 'K1-1-audited-receivable')

  const relatedParties: string[] = []
  try {
    const raw = map.get('K1-2-detail-rows')?.remark
    if (raw) {
      const rows = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (Array.isArray(rows)) {
        for (const r of rows) {
          if (isK1RelatedPartyMarked(r?.relatedParty) && r?.counterparty) {
            relatedParties.push(String(r.counterparty))
          }
        }
      }
    }
  } catch { /* ignore */ }

  return { debit, credit, endBalance, relatedParties }
}

/** 抽样总体 = 测试总体 − 特定样本（对齐 Excel 二、样本选取逻辑） */
export function computeK1SamplingPopulation(criteria: Pick<
  K1SampleCriteria,
  | 'populationDebitCount' | 'populationCreditCount'
  | 'populationDebitAmount' | 'populationCreditAmount'
  | 'specificSampleCount' | 'specificSampleAmount'
>): { count: number; amount: number } {
  const totalCount = (criteria.populationDebitCount || 0) + (criteria.populationCreditCount || 0)
  const totalAmount = (criteria.populationDebitAmount || 0) + (criteria.populationCreditAmount || 0)
  return {
    count: Math.max(0, totalCount - (criteria.specificSampleCount || 0)),
    amount: Math.max(0, totalAmount - (criteria.specificSampleAmount || 0)),
  }
}

/** 从 K1-5 大额分析读取特定样本候选（默认占比 ≥10%） */
export function pullK1LargeAmountSpecifics(
  map: Map<string, any>,
  threshold = 0.1,
): K1LargeAmountSpecifics {
  const empty: K1LargeAmountSpecifics = { counterparties: [], totalAmount: 0, count: 0 }
  try {
    const raw = map.get('K1-5-large-rows')?.remark
    if (!raw) return empty
    const rows = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (!Array.isArray(rows) || !rows.length) return empty

    const total = rows.reduce((s: number, r: any) => s + (Number(r?.endBalance) || 0), 0)
    const selected = rows.filter((r: any) => {
      const prop = Number(r?.proportion ?? (total > 0 ? (Number(r?.endBalance) || 0) / total : 0))
      return prop >= threshold || rows.length <= 5
    })
    const counterparties = selected
      .map((r: any) => ({
        name: String(r?.counterparty || ''),
        amount: Number(r?.endBalance) || 0,
        proportion: r?.proportion != null ? Number(r.proportion) : null,
      }))
      .filter(c => c.name)

    return {
      counterparties,
      totalAmount: counterparties.reduce((s, c) => s + c.amount, 0),
      count: counterparties.length,
    }
  } catch {
    return empty
  }
}

export function isK1VoucherRowChecksComplete(row: K1VoucherRow): boolean {
  return row.checks.length === 5 && row.checks.every(Boolean)
}

export type K1VoucherCheckStatus = 'ok' | 'missing' | 'pending' | 'warn'

export interface K1VoucherCheckItem {
  key: string
  label: string
  status: K1VoucherCheckStatus
  detail: string
}

/**
 * K1-12 逐笔核对实时状态（五项核对 + 关键字段完备性）。
 * 与表格勾选同源：checks[i]===true → ok。
 */
export function evaluateK1VoucherChecks(row: K1VoucherRow): K1VoucherCheckItem[] {
  const items: K1VoucherCheckItem[] = K1_VOUCHER_CHECK_LABELS.map((label, i) => {
    const checked = !!row.checks?.[i]
    return {
      key: `check-${i}`,
      label: `${i + 1}. ${label}`,
      status: checked ? 'ok' : 'pending',
      detail: checked ? '已勾选' : '待核对',
    }
  })

  if (!row.voucherNo?.trim() && !row.debitAmount && !row.creditAmount) {
    items.push({
      key: 'voucher-meta',
      label: '凭证要素',
      status: 'missing',
      detail: '缺凭证号与金额',
    })
  } else if (!row.supportingDoc?.trim()) {
    items.push({
      key: 'supporting',
      label: '支持性文件',
      status: 'warn',
      detail: '未填支持性文件说明',
    })
  } else {
    items.push({
      key: 'supporting',
      label: '支持性文件',
      status: 'ok',
      detail: row.supportingDoc.slice(0, 40),
    })
  }

  return items
}

/** 卡片状态签：完成 / 待核对 / 异常 */
export function k1VoucherCardStatus(row: K1VoucherRow): {
  label: string
  type: 'success' | 'warning' | 'danger' | 'info'
} {
  if (row.abnormal) return { label: '异常', type: 'danger' }
  if (isK1VoucherRowChecksComplete(row)) return { label: '核对通过', type: 'success' }
  const done = (row.checks || []).filter(Boolean).length
  if (done > 0) return { label: `待核对 ${5 - done}`, type: 'warning' }
  return { label: '未开始', type: 'info' }
}

export function useK1VoucherCheck(opts: {
  allResponses: Ref<Map<string, any>>
  itemId?: string
  /** 可选：覆盖 5 项核对标签（如 K9 管理费用第⑤项应为「费用分类正确」而非 K1 的「债务人核对」） */
  checkLabels?: readonly string[]
}) {
  const itemId = opts.itemId ?? 'K1-12-voucher-check'

  // ─── 状态 ───────────────────────────────────────────────────────────────────
  const criteria = ref<K1SampleCriteria>(emptyCriteria())
  const occurrenceRows = ref<K1VoucherRow[]>([])   // 本期发生额检查
  const postCollectionRows = ref<K1VoucherRow[]>([]) // 期后收款检查
  const auditNote = ref('')
  const lowRatioExplanation = ref('')
  const conclusion = ref('')
  const conclusionOption = ref('')

  // 允许调用方覆盖核对标签（仅显示用；checks 数组仍固定 5 项）
  const checkLabels = (opts.checkLabels && opts.checkLabels.length === 5)
    ? [...opts.checkLabels]
    : CHECK_LABELS

  // ─── 加载 ────────────────────────────────────────────────────────────────────
  function load(): void {
    const stored = opts.allResponses.value.get(itemId)
    const raw = stored?.remark ?? stored?.value
    if (!raw) return
    try {
      const data = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (data.criteria) criteria.value = { ...emptyCriteria(), ...data.criteria }
      if (Array.isArray(data.occurrenceRows)) occurrenceRows.value = data.occurrenceRows.map(normalizeRow)
      if (Array.isArray(data.postCollectionRows)) postCollectionRows.value = data.postCollectionRows.map(normalizeRow)
      auditNote.value = data.auditNote ?? ''
      lowRatioExplanation.value = data.lowRatioExplanation ?? ''
      conclusion.value = data.conclusion ?? ''
      conclusionOption.value = data.conclusionOption ?? ''
    } catch {
      // 忽略损坏数据
    }
  }

  function normalizeRow(r: any): K1VoucherRow {
    const base = emptyRow(0)
    return {
      ...base,
      ...r,
      checks: Array.isArray(r?.checks) && r.checks.length === 5
        ? r.checks.map((x: any) => !!x)
        : [false, false, false, false, false],
      debitAmount: Number(r?.debitAmount ?? 0),
      creditAmount: Number(r?.creditAmount ?? 0),
    }
  }

  // ─── 行操作 ──────────────────────────────────────────────────────────────────
  function addOccurrenceRow(): void { occurrenceRows.value.push(emptyRow(occurrenceRows.value.length)) }
  function addPostCollectionRow(): void { postCollectionRows.value.push(emptyRow(postCollectionRows.value.length)) }
  function removeOccurrenceRow(id: string): void { occurrenceRows.value = occurrenceRows.value.filter(r => r.id !== id) }
  function removePostCollectionRow(id: string): void { postCollectionRows.value = postCollectionRows.value.filter(r => r.id !== id) }

  /** 弹窗/卡片回写：按 id 合并 patch */
  function updateVoucherRow(
    target: 'occurrence' | 'post',
    id: string,
    patch: Partial<K1VoucherRow>,
  ): boolean {
    const list = target === 'occurrence' ? occurrenceRows : postCollectionRows
    const idx = list.value.findIndex((r) => r.id === id)
    if (idx < 0) return false
    const prev = list.value[idx]
    const next: K1VoucherRow = {
      ...prev,
      ...patch,
      id: prev.id,
      checks: Array.isArray(patch.checks) && patch.checks.length === 5
        ? patch.checks.map(Boolean)
        : prev.checks,
    }
    list.value.splice(idx, 1, next)
    return true
  }

  /** 抽凭引擎回填：把样本映射为凭证检查行 */
  function fillFromSamples(target: 'occurrence' | 'post', samples: any[]): void {
    const mapped: K1VoucherRow[] = samples.map((s, i) => ({
      ...emptyRow(i),
      // 债务人名称走语义门控（K1 其他应收款，这一列语义是「债务人」）。
      // 原实现读 `s.counterpartName` —— 抽凭样本里**没有这个字段**（后端给的是
      // party_name/counterpart_account），故该列一直为空。
      debtorName: partyNameForColumn(s, 'debtor') || s.debtorName || '',
      date: s.voucherDate ?? s.date ?? '',
      voucherNo: s.voucherNo ?? '',
      businessContent: s.summary ?? s.businessContent ?? '',
      offsetAccount: s.counterpartAccount ?? s.offsetAccount ?? '',
      offsetSubAccount: s.counterpartSubAccount ?? s.offsetSubAccount ?? '',
      debitAmount: Number(s.debitAmount ?? 0),
      creditAmount: Number(s.creditAmount ?? 0),
      supportingDoc: s.supportingDoc ?? '',
      abnormal: !!s.abnormal,
      remark: s.selectionReason ?? s.remark ?? '',
    }))
    if (target === 'occurrence') {
      const existing = new Set(occurrenceRows.value.map(r => r.voucherNo).filter(Boolean))
      occurrenceRows.value.push(...mapped.filter(r => !r.voucherNo || !existing.has(r.voucherNo)))
    } else {
      const existing = new Set(postCollectionRows.value.map(r => r.voucherNo).filter(Boolean))
      postCollectionRows.value.push(...mapped.filter(r => !r.voucherNo || !existing.has(r.voucherNo)))
    }
  }

  /** 从 K1-1/K1-2 带入账面发生额与期末余额（对齐 Excel E61–E63 公式） */
  function applyFromK1Sheets(): { debit: number; credit: number; endBalance: number; filled: boolean } {
    const { debit, credit, endBalance, relatedParties } = pullK1BookAmounts(opts.allResponses.value)
    const filled = debit > 0 || credit > 0 || endBalance > 0
    if (filled) {
      criteria.value.bookDebitOccurrence = debit
      criteria.value.bookCreditOccurrence = credit
      if (!criteria.value.populationDebitAmount) criteria.value.populationDebitAmount = debit
      if (!criteria.value.populationCreditAmount) criteria.value.populationCreditAmount = credit
      if (!criteria.value.endBalance) criteria.value.endBalance = endBalance
      recalcSamplingPopulation()
    }
    if (relatedParties.length) {
      const hint = `关联方全部测试：${relatedParties.slice(0, 8).join('、')}${relatedParties.length > 8 ? '等' : ''}，共${relatedParties.length}户`
      if (!criteria.value.specificSample || criteria.value.specificSample.includes('XX')) {
        criteria.value.specificSample = hint
      }
      if (!criteria.value.specificSampleCount) {
        criteria.value.specificSampleCount = relatedParties.length
      }
    }
    return { debit, credit, endBalance, filled }
  }

  /** 从 K1-5 大额分析带入特定样本说明与数量/金额 */
  function applyFromK1LargeAmount(threshold = 0.1): K1LargeAmountSpecifics & { filled: boolean } {
    const data = pullK1LargeAmountSpecifics(opts.allResponses.value, threshold)
    if (data.count > 0) {
      const fmtWan = (n: number) => (n / 10000).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
      const parts = data.counterparties.slice(0, 8).map(c => `${c.name}(${fmtWan(c.amount)}万)`)
      criteria.value.specificSample = `大额全部测试（K1-5）：${parts.join('、')}${data.count > 8 ? '等' : ''}，共${data.count}户，合计${data.totalAmount.toLocaleString()}元`
      criteria.value.specificSampleCount = data.count
      criteria.value.specificSampleAmount = data.totalAmount
      recalcSamplingPopulation()
    }
    return { ...data, filled: data.count > 0 }
  }

  /** 重算抽样总体（测试总体 − 特定样本） */
  function recalcSamplingPopulation(): { count: number; amount: number } {
    const derived = computeK1SamplingPopulation(criteria.value)
    criteria.value.samplingPopulationCount = derived.count
    criteria.value.samplingPopulationAmount = derived.amount
    return derived
  }

  /** 异常凭证 → K1-4 调整备忘草稿（金额待补） */
  function buildAbnormalAdjDrafts(): K1AbnormalAdjDraft[] {
    return abnormalRows.value.map((r) => {
      const amt = Math.abs(Number(r.debitAmount || r.creditAmount || 0))
      const debtor = r.debtorName ? `${r.debtorName} ` : ''
      return {
        summary: `${K1_VOUCHER_PUSH_MARK}${debtor}凭证异常：${r.voucherNo || '无号'} ${r.businessContent || ''}`.trim(),
        accountCode: '1221',
        accountName: '其他应收款',
        debitAmount: 0,
        creditAmount: 0,
        indexRef: r.indexNo || 'K1-12',
        remark: `来自K1-12凭证检查；${r.remark || '金额待追查补录'}${amt ? `；检查涉及金额约${amt}` : ''}`,
      }
    })
  }

  // ─── 检查比例表（四、审计说明）────────────────────────────────────────────────
  const occurrenceDebitChecked = computed(() => occurrenceRows.value.reduce((s, r) => s + (r.debitAmount || 0), 0))
  const occurrenceCreditChecked = computed(() => occurrenceRows.value.reduce((s, r) => s + (r.creditAmount || 0), 0))
  const postCollectionChecked = computed(() => postCollectionRows.value.reduce((s, r) => s + (r.creditAmount || 0), 0))

  const checkRatios = computed<K1CheckRatioRow[]>(() => {
    const mk = (direction: string, book: number, checked: number): K1CheckRatioRow => ({
      direction, bookAmount: book, checkedAmount: checked,
      ratio: book > 0 ? checked / book : null,
    })
    return [
      mk('本期借方', criteria.value.bookDebitOccurrence || criteria.value.populationDebitAmount, occurrenceDebitChecked.value),
      mk('本期贷方', criteria.value.bookCreditOccurrence || criteria.value.populationCreditAmount, occurrenceCreditChecked.value),
      mk('期末余额', criteria.value.endBalance, postCollectionChecked.value),
    ]
  })

  /** 检查比例是否偏低（<30% 需扩样或说明）*/
  const lowRatioWarnings = computed(() =>
    checkRatios.value.filter(r => r.ratio != null && r.ratio < 0.3 && r.bookAmount > 0),
  )

  /** 计划样本量 vs 实际检查笔数 */
  const sampleSizeDeviation = computed<K1SampleSizeDeviation | null>(() => {
    const planned = criteria.value.sampleSize
    if (!planned) return null
    const actual = occurrenceRows.value.length
    return { planned, actual, diff: actual - planned, needsExpansion: actual < planned }
  })

  /** 有数据但五项核对未勾满的凭证 */
  const incompleteCheckRows = computed(() => {
    const hasData = (r: K1VoucherRow) => !!(r.voucherNo || r.debitAmount || r.creditAmount)
    return [
      ...occurrenceRows.value.filter(r => hasData(r) && !isK1VoucherRowChecksComplete(r)),
      ...postCollectionRows.value.filter(r => hasData(r) && !isK1VoucherRowChecksComplete(r)),
    ]
  })

  /** 抽样总体演算值（只读预览，与 criteria 中字段一致） */
  const derivedSamplingPopulation = computed(() => computeK1SamplingPopulation(criteria.value))

  /** 异常凭证汇总 */
  const abnormalRows = computed(() => [
    ...occurrenceRows.value.filter(r => r.abnormal),
    ...postCollectionRows.value.filter(r => r.abnormal),
  ])

  // ─── 序列化（持久化用）─────────────────────────────────────────────────────────
  function serialize(): string {
    return JSON.stringify({
      criteria: criteria.value,
      occurrenceRows: occurrenceRows.value,
      postCollectionRows: postCollectionRows.value,
      auditNote: auditNote.value,
      lowRatioExplanation: lowRatioExplanation.value,
      conclusion: conclusion.value,
      conclusionOption: conclusionOption.value,
    })
  }

  return {
    itemId, checkLabels,
    criteria, occurrenceRows, postCollectionRows, auditNote, lowRatioExplanation,
    conclusion, conclusionOption,
    checkRatios, lowRatioWarnings, sampleSizeDeviation, incompleteCheckRows, derivedSamplingPopulation, abnormalRows,
    occurrenceDebitChecked, occurrenceCreditChecked, postCollectionChecked,
    load, addOccurrenceRow, addPostCollectionRow, removeOccurrenceRow, removePostCollectionRow,
    updateVoucherRow,
    fillFromSamples, applyFromK1Sheets, applyFromK1LargeAmount, recalcSamplingPopulation,
    buildAbnormalAdjDrafts, serialize,
  }
}
