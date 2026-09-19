/**
 * useG5VoucherCheck.ts — G5-12 长期应收款凭证检查表
 *
 * 对齐致同源模板「凭证检查表G5-12」：
 *   一、测试目标（存在 / 权利与义务 / 计价和分摊）
 *   二、样本选取方法与规模（测试总体/特定样本/抽样总体/样本量/方法/过程）
 *   三、测试（1.本期发生额 2.期后处置、新增；五项核对）
 *   四、审计说明（检查比例：本期借方/本期贷方/期后合计）
 *   五、审计结论（A/B/C）
 *
 * 持久化：单一 JSON → checklist_responses item_id=G5-12-voucher-check
 * 兼容迁移：旧版扁平 G5-12-rows / 独立 note·conclusion keys
 */
import { ref, computed, type Ref } from 'vue'
import { readCanonicalRaw } from './g5StorageContract'

// ─── 源模板五项核对（R13）────────────────────────────────────────────────────
export const G5_VOUCHER_CHECK_LABELS = [
  '原始凭证内容完整',
  '有授权批准',
  '账务处理正确',
  '初始成本计算正确',
  '还款人与交易对手核对一致',
] as const

export interface G5VoucherRow {
  id: string
  date: string
  voucherNo: string
  businessContent: string
  offsetAccount: string
  offsetSubAccount: string
  debitAmount: number
  creditAmount: number
  supportingDoc: string
  checks: boolean[]
  indexNo: string
  abnormal: boolean
  remark: string
  source?: string
}

export interface G5SampleCriteria {
  populationDebitCount: number
  populationDebitAmount: number
  populationCreditCount: number
  populationCreditAmount: number
  specificSample: string
  samplingPopulationCount: number
  samplingPopulationAmount: number
  sampleSize: number
  samplingMethod: string
  samplingProcess: string
  /** 本期发生额账面借方（检查比例分母，可与 G5-2 勾稽） */
  bookDebitOccurrence: number
  /** 本期发生额账面贷方 */
  bookCreditOccurrence: number
}

export interface G5CheckRatioRow {
  direction: string
  bookAmount: number
  checkedAmount: number
  ratio: number | null
}

export const G5_CONCLUSION_TEMPLATES: Record<string, string> = {
  A: '未见异常。',
  B: '除以下重大不符事项应当作为调整事项予以调整外，其余未见异常。',
  C: '由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。',
}

const ITEM_ID = 'G5-12-voucher-check'
const LEGACY_ROWS_KEY = 'G5-12-rows'
const LEGACY_NOTE_KEY = 'G5-12-audit-note'
const LEGACY_CONCLUSION_KEY = 'G5-12-audit-conclusion'

function emptyRow(seq = 0): G5VoucherRow {
  return {
    id: `g5vc-${Date.now()}-${seq}-${Math.random().toString(36).slice(2, 6)}`,
    date: '',
    voucherNo: '',
    businessContent: '',
    offsetAccount: '',
    offsetSubAccount: '',
    debitAmount: 0,
    creditAmount: 0,
    supportingDoc: '',
    checks: [false, false, false, false, false],
    indexNo: '',
    abnormal: false,
    remark: '',
  }
}

function emptyCriteria(): G5SampleCriteria {
  return {
    populationDebitCount: 0,
    populationDebitAmount: 0,
    populationCreditCount: 0,
    populationCreditAmount: 0,
    specificSample: '大额（XX金额以上）、关联方/关联交易形成的款项、异常款项全部测试',
    samplingPopulationCount: 0,
    samplingPopulationAmount: 0,
    sampleSize: 0,
    samplingMethod: '货币单元抽样',
    samplingProcess: '',
    bookDebitOccurrence: 0,
    bookCreditOccurrence: 0,
  }
}

function normalizeRow(r: any): G5VoucherRow {
  const base = emptyRow(0)
  const checksRaw = r?.checks
  let checks: boolean[]
  if (Array.isArray(checksRaw) && checksRaw.length >= 5) {
    checks = checksRaw.slice(0, 5).map((x: any) => !!x)
  } else if (r && typeof r === 'object' && ('check1' in r || 'check2' in r)) {
    // 旧版 check1..check7（✓/✗）→ boolean[5]
    checks = [1, 2, 3, 4, 5].map((n) => r[`check${n}`] === '✓')
  } else {
    checks = [false, false, false, false, false]
  }
  const amount = Number(r?.amount ?? 0)
  const debit = Number(r?.debitAmount ?? (amount > 0 ? amount : 0))
  const credit = Number(r?.creditAmount ?? (amount < 0 ? Math.abs(amount) : 0))
  return {
    ...base,
    ...r,
    id: r?.id || base.id,
    businessContent: r?.businessContent ?? r?.summary ?? '',
    offsetAccount: r?.offsetAccount ?? r?.counterAccount ?? '',
    debitAmount: debit,
    creditAmount: credit,
    checks,
    abnormal: typeof r?.abnormal === 'boolean'
      ? r.abnormal
      : r?.isAbnormal === '是' || checks.some((c, i) => r?.[`check${i + 1}`] === '✗'),
    remark: r?.remark ?? r?.conclusion ?? '',
    date: r?.date ?? r?.voucherDate ?? '',
  }
}

/** 旧版扁平行数组 → 新结构（全部归入本期发生额） */
function migrateLegacyRows(raw: any): Partial<{
  criteria: G5SampleCriteria
  occurrenceRows: G5VoucherRow[]
  postPeriodRows: G5VoucherRow[]
  auditNote: string
  conclusion: string
  conclusionOption: string
}> | null {
  if (!raw) return null
  try {
    const data = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (Array.isArray(data)) {
      return { occurrenceRows: data.map(normalizeRow) }
    }
    if (data && typeof data === 'object' && (data.occurrenceRows || data.criteria)) {
      return data
    }
  } catch { /* ignore */ }
  return null
}

export function useG5VoucherCheck(opts?: {
  allResponses?: Ref<Map<string, any>>
  itemId?: string
}) {
  const itemId = opts?.itemId ?? ITEM_ID
  const criteria = ref<G5SampleCriteria>(emptyCriteria())
  const occurrenceRows = ref<G5VoucherRow[]>([])
  const postPeriodRows = ref<G5VoucherRow[]>([])
  const auditNote = ref('')
  const conclusion = ref('')
  const conclusionOption = ref('')
  const checkLabels = [...G5_VOUCHER_CHECK_LABELS]

  function loadFromMap(map?: Map<string, any>): void {
    if (!map) return
    const primary = map.get(itemId)
    const legacyRows = map.get(LEGACY_ROWS_KEY)
    const packed = migrateLegacyRows(readCanonicalRaw(primary) ?? primary?.value)
      ?? migrateLegacyRows(readCanonicalRaw(legacyRows) ?? legacyRows?.value)

    if (packed) {
      if (packed.criteria) criteria.value = { ...emptyCriteria(), ...packed.criteria }
      if (Array.isArray(packed.occurrenceRows)) {
        occurrenceRows.value = packed.occurrenceRows.map(normalizeRow)
      }
      if (Array.isArray(packed.postPeriodRows)) {
        postPeriodRows.value = packed.postPeriodRows.map(normalizeRow)
      }
      if (packed.auditNote != null) auditNote.value = packed.auditNote
      if (packed.conclusion != null) conclusion.value = packed.conclusion
      if (packed.conclusionOption != null) conclusionOption.value = packed.conclusionOption
    }

    // 独立 note/conclusion keys（旧组件）
    if (!auditNote.value) {
      const n = map.get(LEGACY_NOTE_KEY)
      if (n?.remark) auditNote.value = n.remark
    }
    if (!conclusion.value) {
      const c = map.get(LEGACY_CONCLUSION_KEY)
      if (c?.remark) conclusion.value = c.remark
    }
  }

  function load(): void {
    loadFromMap(opts?.allResponses?.value)
  }

  function addOccurrenceRow(): void {
    occurrenceRows.value.push(emptyRow(occurrenceRows.value.length))
  }
  function addPostPeriodRow(): void {
    postPeriodRows.value.push(emptyRow(postPeriodRows.value.length))
  }
  function removeOccurrenceRow(id: string): void {
    occurrenceRows.value = occurrenceRows.value.filter((r) => r.id !== id)
  }
  function removePostPeriodRow(id: string): void {
    postPeriodRows.value = postPeriodRows.value.filter((r) => r.id !== id)
  }

  /** 抽凭引擎回填 */
  function fillFromSamples(target: 'occurrence' | 'post', samples: any[]): void {
    const mapped: G5VoucherRow[] = samples.map((s, i) => ({
      ...emptyRow(i),
      date: s.voucherDate ?? s.date ?? '',
      voucherNo: s.voucherNo ?? '',
      businessContent: s.summary ?? s.businessContent ?? '',
      offsetAccount: s.counterpartAccount ?? s.offsetAccount ?? '',
      offsetSubAccount: s.counterpartSubAccount ?? '',
      debitAmount: Number(s.debitAmount ?? 0),
      creditAmount: Number(s.creditAmount ?? (s.amount != null && Number(s.amount) > 0 ? Number(s.amount) : 0)),
      remark: s.selectionReason ?? '',
      source: '抽凭',
      abnormal: !!s.abnormal,
    }))
    const bucket = target === 'occurrence' ? occurrenceRows : postPeriodRows
    const existing = new Set(bucket.value.map((r) => r.voucherNo).filter(Boolean))
    for (const r of mapped) {
      if (r.voucherNo && existing.has(r.voucherNo)) continue
      bucket.value.push(r)
      if (r.voucherNo) existing.add(r.voucherNo)
    }
  }

  const occurrenceDebitChecked = computed(() =>
    occurrenceRows.value.reduce((s, r) => s + (r.debitAmount || 0), 0),
  )
  const occurrenceCreditChecked = computed(() =>
    occurrenceRows.value.reduce((s, r) => s + (r.creditAmount || 0), 0),
  )
  const postDebitChecked = computed(() =>
    postPeriodRows.value.reduce((s, r) => s + (r.debitAmount || 0), 0),
  )
  const postCreditChecked = computed(() =>
    postPeriodRows.value.reduce((s, r) => s + (r.creditAmount || 0), 0),
  )

  const checkRatios = computed<G5CheckRatioRow[]>(() => {
    const mk = (direction: string, book: number, checked: number): G5CheckRatioRow => ({
      direction,
      bookAmount: book,
      checkedAmount: checked,
      ratio: book > 0 ? checked / book : null,
    })
    return [
      mk('本期借方', criteria.value.bookDebitOccurrence || criteria.value.populationDebitAmount, occurrenceDebitChecked.value),
      mk('本期贷方', criteria.value.bookCreditOccurrence || criteria.value.populationCreditAmount, occurrenceCreditChecked.value),
      mk('期后借方', 0, postDebitChecked.value), // 分母由说明填写时用 book*，期后通常无固定总体
      mk('期后贷方', 0, postCreditChecked.value),
    ].filter((r) => r.direction.startsWith('本期') || r.checkedAmount > 0)
  })

  /** 检查比例偏低告警（仅本期有账面分母时） */
  const lowRatioWarnings = computed(() =>
    checkRatios.value.filter(
      (r) => r.direction.startsWith('本期') && r.ratio != null && r.ratio < 0.3 && r.bookAmount > 0,
    ),
  )

  const abnormalRows = computed(() => [
    ...occurrenceRows.value.filter((r) => r.abnormal),
    ...postPeriodRows.value.filter((r) => r.abnormal),
  ])

  function applyConclusionTemplate(opt: string): void {
    conclusionOption.value = opt
    const text = G5_CONCLUSION_TEMPLATES[opt]
    if (text && !conclusion.value) conclusion.value = text
  }

  /** 从 G5-2 余额明细汇总账面借/贷发生额与特定样本提示 */
  function applyFromBalanceRows(rawRows: any[]): {
    debit: number
    credit: number
    relatedCount: number
    filled: boolean
  } {
    const list = Array.isArray(rawRows) ? rawRows : []
    let debit = 0
    let credit = 0
    let debitCount = 0
    let creditCount = 0
    const related: string[] = []
    for (const r of list) {
      const d = Number(r?.debitOccurrence ?? r?.debit ?? 0) || 0
      const c = Number(r?.creditOccurrence ?? r?.credit ?? 0) || 0
      debit += d
      credit += c
      if (d !== 0) debitCount += 1
      if (c !== 0) creditCount += 1
      if (r?.isRelatedParty && r?.debtorName) related.push(String(r.debtorName))
    }
    const filled = debit > 0 || credit > 0
    if (filled) {
      criteria.value.bookDebitOccurrence = debit
      criteria.value.bookCreditOccurrence = credit
      if (!criteria.value.populationDebitAmount) criteria.value.populationDebitAmount = debit
      if (!criteria.value.populationCreditAmount) criteria.value.populationCreditAmount = credit
      if (!criteria.value.populationDebitCount) criteria.value.populationDebitCount = debitCount
      if (!criteria.value.populationCreditCount) criteria.value.populationCreditCount = creditCount
    }
    if (related.length) {
      const hint = `关联方全部测试：${related.slice(0, 8).join('、')}${related.length > 8 ? '等' : ''}，共${related.length}户`
      if (!criteria.value.specificSample || criteria.value.specificSample.includes('XX')) {
        criteria.value.specificSample = hint
      }
    }
    return { debit, credit, relatedCount: related.length, filled }
  }

  /** 异常凭证 → G5-4 调整备忘草稿（金额待补） */
  function buildAbnormalAdjDrafts(): Array<{
    description: string
    accountCode: string
    accountName: string
    debitAmount: number
    creditAmount: number
    indexRef: string
    remark: string
  }> {
    return abnormalRows.value.map((r) => {
      const amt = Math.abs(Number(r.debitAmount || r.creditAmount || 0))
      return {
        description: `G5-12凭证异常：${r.voucherNo || '无号'} ${r.businessContent || ''}`.trim(),
        accountCode: '1531',
        accountName: '长期应收款',
        debitAmount: 0,
        creditAmount: 0,
        indexRef: r.indexNo || 'G5-12',
        remark: `来自G5-12凭证检查；${r.remark || '金额待追查补录'}${amt ? `；检查涉及金额约${amt}` : ''}`,
      }
    })
  }

  function serialize(): string {
    return JSON.stringify({
      criteria: criteria.value,
      occurrenceRows: occurrenceRows.value,
      postPeriodRows: postPeriodRows.value,
      auditNote: auditNote.value,
      conclusion: conclusion.value,
      conclusionOption: conclusionOption.value,
    })
  }

  /** 兼容旧调用方：合并单样本到本期表 */
  function mergeSample(sample: Partial<G5VoucherRow> & { summary?: string; amount?: number; voucherDate?: string }): void {
    fillFromSamples('occurrence', [sample])
  }

  function loadRows(data: any[]): void {
    occurrenceRows.value = data.map(normalizeRow)
  }

  return {
    itemId,
    checkLabels,
    criteria,
    occurrenceRows,
    postPeriodRows,
    auditNote,
    conclusion,
    conclusionOption,
    checkRatios,
    lowRatioWarnings,
    abnormalRows,
    occurrenceDebitChecked,
    occurrenceCreditChecked,
    postDebitChecked,
    postCreditChecked,
    load,
    loadFromMap,
    addOccurrenceRow,
    addPostPeriodRow,
    removeOccurrenceRow,
    removePostPeriodRow,
    fillFromSamples,
    applyConclusionTemplate,
    applyFromBalanceRows,
    buildAbnormalAdjDrafts,
    serialize,
    mergeSample,
    loadRows,
    // 兼容旧 API 名
    rows: occurrenceRows,
  }
}
