/**
 * useG1DerivativeCheck — G1-14 衍生金融工具核查表
 *
 * 对齐 Excel：
 *  (1) 确定衍生工具：工具名称 + B 变量问卷（8项）+ C 嵌入衍生问卷
 *  (2) 结论：无衍生 / 单独核算 / 嵌入衍生（含 CAS22 混合合同提示）
 *  (3) 抽查会计处理表
 *  (4) 专家资质及利用估值专家工作
 *
 * 逻辑修正：Excel 原文「B 任一为否即无衍生」有误 → 改为「B 全部为否才判定无衍生」。
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { parseNum } from './useG1TraFinFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import type { SampledVoucher } from './useSamplingAlgorithms'

export type G1DerivativeIdResult = 'NONE' | 'STANDALONE' | 'EMBEDDED' | 'INCOMPLETE'

export interface G1DerivativeVariableQ {
  id: string
  seq: number
  label: string
  answer: boolean | null
  remark: string
}

export interface G1DerivativeEmbeddedQ {
  id: string
  seq: string
  question: string
  answer: boolean | null
  explanation: string
}

export interface G1DerivativeVoucherRow {
  id: string
  seq: number
  date: string
  voucherNo: string
  businessContent: string
  detailAccount: string
  counterAccount: string
  debitAmount: number
  creditAmount: number
  conclusion: string
}

export interface G1DerivativeExpertRow {
  id: string
  seq: number
  item: string
  indexRef: string
  remark: string
}

/** 旧版清单行（兼容迁移） */
export interface G1DerivativeLegacyRow {
  id: string
  seq: number
  instrumentName: string
  instrumentType: string
  notionalAmount: number
  term: string
  counterparty: string
  margin: number
  isHedging: string
  accountingAppropriateness: string
  complianceConclusion: string
}

export interface G1DerivativeIdChip {
  color: string
  label: string
  type: 'success' | 'primary' | 'warning' | 'info'
}

export const G1_DERIVATIVE_ID_CHIP: Record<G1DerivativeIdResult, G1DerivativeIdChip> = {
  NONE: { color: '#909399', label: '未识别出衍生工具特征', type: 'info' },
  STANDALONE: { color: '#409EFF', label: '单独核算的衍生工具', type: 'primary' },
  EMBEDDED: { color: '#E6A23C', label: '嵌入衍生工具', type: 'warning' },
  INCOMPLETE: { color: '#909399', label: '请完成识别问卷', type: 'info' },
}

/** B：影响合同价值的变量（存在任一即可能构成衍生） */
export const G1_DERIVATIVE_B_VARIABLES: Array<{ id: string; seq: number; label: string }> = [
  { id: 'b1', seq: 1, label: '利率' },
  { id: 'b2', seq: 2, label: '金融工具价格' },
  { id: 'b3', seq: 3, label: '商品价格' },
  { id: 'b4', seq: 4, label: '汇率' },
  { id: 'b5', seq: 5, label: '价格或利率指数' },
  { id: 'b6', seq: 6, label: '信用等级 / 信用指数' },
  { id: 'b7', seq: 7, label: '其它金融变量' },
  { id: 'b8', seq: 8, label: '其它非金融变量（非合同一方特有）' },
]

/** C：嵌入衍生判断 */
export const G1_DERIVATIVE_C_QUESTIONS: Array<{ id: string; seq: string; question: string }> = [
  {
    id: 'c0',
    seq: 'C',
    question: '合同中包含的衍生工具是否属于嵌入衍生工具？',
  },
  {
    id: 'c1',
    seq: 'C.1',
    question: '嵌入衍生工具是否与主合同在经济特征上紧密相关、通常不可独立转让？',
  },
  {
    id: 'c2',
    seq: 'C.2',
    question: '嵌入衍生工具的对手方是否与主合同为同一方？',
  },
]

const KEY_META = 'G1-14-meta'
const KEY_B = 'G1-14-b-variables'
const KEY_C = 'G1-14-c-embedded'
const KEY_VOUCHER = 'G1-14-vouchers'
const KEY_EXPERT = 'G1-14-experts'
const KEY_LEGACY = 'G1-14-rows'
const KEY_CONCLUSION = 'G1-14-conclusion'
const KEY_RESULT = 'G1-14-id-result'

function genId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

export function createDefaultBQuestions(): G1DerivativeVariableQ[] {
  return G1_DERIVATIVE_B_VARIABLES.map((v) => ({
    ...v,
    answer: null,
    remark: '',
  }))
}

export function createDefaultCQuestions(): G1DerivativeEmbeddedQ[] {
  return G1_DERIVATIVE_C_QUESTIONS.map((q) => ({
    ...q,
    answer: null,
    explanation: '',
  }))
}

export function createEmptyVoucherRow(seq = 1): G1DerivativeVoucherRow {
  return {
    id: genId('v'),
    seq,
    date: '',
    voucherNo: '',
    businessContent: '',
    detailAccount: '',
    counterAccount: '',
    debitAmount: 0,
    creditAmount: 0,
    conclusion: '',
  }
}

export function createDefaultExpertRows(): G1DerivativeExpertRow[] {
  return [
    { id: genId('e'), seq: 1, item: '了解专家资质（资格、经验、独立性）', indexRef: '', remark: '' },
    { id: genId('e'), seq: 2, item: '利用估值专家的工作（范围、结论、复核）', indexRef: '', remark: '' },
  ]
}

/**
 * 识别结论推导：
 * - B 未答完 → INCOMPLETE
 * - B 全部为否 → NONE（修正模板笔误）
 * - B 任一为是 → 进入 C；C 未答完 → INCOMPLETE
 * - C0=是（嵌入）→ EMBEDDED；否则 STANDALONE
 */
export function determineG1DerivativeId(
  bItems: Array<{ answer: boolean | null }>,
  cItems: Array<{ id: string; answer: boolean | null }>,
): G1DerivativeIdResult {
  if (!bItems.length || bItems.some((q) => q.answer === null || q.answer === undefined)) {
    return 'INCOMPLETE'
  }
  const anyYes = bItems.some((q) => q.answer === true)
  if (!anyYes) return 'NONE'

  const c0 = cItems.find((q) => q.id === 'c0')?.answer
  const c1 = cItems.find((q) => q.id === 'c1')?.answer
  const c2 = cItems.find((q) => q.id === 'c2')?.answer
  if (c0 === null || c0 === undefined || c1 === null || c1 === undefined || c2 === null || c2 === undefined) {
    return 'INCOMPLETE'
  }
  if (c0 === true) return 'EMBEDDED'
  return 'STANDALONE'
}

function safeParse<T>(raw: string | null | undefined): T | null {
  if (!raw) return null
  try {
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

function mergeB(stored: G1DerivativeVariableQ[] | null): G1DerivativeVariableQ[] {
  const base = createDefaultBQuestions()
  if (!stored?.length) return base
  const map = new Map(stored.map((q) => [q.id, q]))
  return base.map((q) => {
    const hit = map.get(q.id)
    return hit ? { ...q, answer: hit.answer ?? null, remark: hit.remark || '' } : q
  })
}

function mergeC(stored: G1DerivativeEmbeddedQ[] | null): G1DerivativeEmbeddedQ[] {
  const base = createDefaultCQuestions()
  if (!stored?.length) return base
  const map = new Map(stored.map((q) => [q.id, q]))
  return base.map((q) => {
    const hit = map.get(q.id)
    return hit
      ? { ...q, answer: hit.answer ?? null, explanation: hit.explanation || '' }
      : q
  })
}

function isLegacyInventory(raw: unknown): boolean {
  if (!Array.isArray(raw) || !raw.length) return false
  const first = raw[0] as Record<string, unknown>
  return 'instrumentName' in first || 'notionalAmount' in first || 'instrumentType' in first
}

export function useG1DerivativeCheck(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const instrumentName = ref('')
  const natureDesc = ref('')
  const accountCode = ref('')
  const accountingPolicy = ref('')
  const cas22HybridNoted = ref(false)

  const bQuestions = ref<G1DerivativeVariableQ[]>(createDefaultBQuestions())
  const cQuestions = ref<G1DerivativeEmbeddedQ[]>(createDefaultCQuestions())
  const vouchers = ref<G1DerivativeVoucherRow[]>([createEmptyVoucherRow(1)])
  const experts = ref<G1DerivativeExpertRow[]>(createDefaultExpertRows())
  const legacyRows = ref<G1DerivativeLegacyRow[]>([])
  const auditConclusion = ref('')

  const idResult = computed(() =>
    determineG1DerivativeId(bQuestions.value, cQuestions.value),
  )
  const idChip = computed(() => G1_DERIVATIVE_ID_CHIP[idResult.value])
  const hasUnderlyingVariable = computed(() =>
    bQuestions.value.some((q) => q.answer === true),
  )
  const showEmbeddedSection = computed(() => hasUnderlyingVariable.value)
  const skipFurther = computed(() => idResult.value === 'NONE')

  const cas22Hint = computed(() => {
    if (idResult.value !== 'EMBEDDED') return null
    return '提示（CAS22）：若混合合同主合同属于金融资产范畴，嵌入衍生工具通常不单独分拆，而将混合合同整体按准则分类计量（交易性金融资产常见为 FVTPL）。'
  })

  function loadAll() {
    const meta = safeParse<{
      instrumentName?: string
      natureDesc?: string
      accountCode?: string
      accountingPolicy?: string
      cas22HybridNoted?: boolean
    }>(opts.allResponses.value.get(KEY_META)?.remark)
    if (meta) {
      instrumentName.value = meta.instrumentName || ''
      natureDesc.value = meta.natureDesc || ''
      accountCode.value = meta.accountCode || ''
      accountingPolicy.value = meta.accountingPolicy || ''
      cas22HybridNoted.value = !!meta.cas22HybridNoted
    }

    bQuestions.value = mergeB(safeParse(opts.allResponses.value.get(KEY_B)?.remark))
    cQuestions.value = mergeC(safeParse(opts.allResponses.value.get(KEY_C)?.remark))

    const v = safeParse<G1DerivativeVoucherRow[]>(opts.allResponses.value.get(KEY_VOUCHER)?.remark)
    vouchers.value = Array.isArray(v) && v.length ? v : [createEmptyVoucherRow(1)]

    const e = safeParse<G1DerivativeExpertRow[]>(opts.allResponses.value.get(KEY_EXPERT)?.remark)
    experts.value = Array.isArray(e) && e.length ? e : createDefaultExpertRows()

    const legacyRaw = opts.allResponses.value.get(KEY_LEGACY)?.conclusion
      || opts.allResponses.value.get(KEY_LEGACY)?.remark
    const legacyParsed = safeParse<any[]>(legacyRaw)
    if (legacyParsed && isLegacyInventory(legacyParsed)) {
      legacyRows.value = legacyParsed.map((p, i) => ({
        id: String(p.id || `L${i + 1}`),
        seq: Number(p.seq) || i + 1,
        instrumentName: String(p.instrumentName || ''),
        instrumentType: String(p.instrumentType || ''),
        notionalAmount: parseNum(p.notionalAmount),
        term: String(p.term || ''),
        counterparty: String(p.counterparty || ''),
        margin: parseNum(p.margin),
        isHedging: String(p.isHedging || ''),
        accountingAppropriateness: String(p.accountingAppropriateness || ''),
        complianceConclusion: String(p.complianceConclusion || ''),
      }))
      if (!instrumentName.value) {
        const first = legacyRows.value.find((r) => r.instrumentName)
        if (first) instrumentName.value = first.instrumentName
      }
    }

    auditConclusion.value =
      opts.allResponses.value.get(KEY_CONCLUSION)?.conclusion
      || opts.allResponses.value.get(KEY_CONCLUSION)?.remark
      || ''
  }

  // 初次加载；之后仅在本地尚未作答时接受外部回填，避免 persist 自触发互相覆盖
  loadAll()
  watch(
    () => opts.allResponses.value.get(KEY_B)?.remark
      ?? opts.allResponses.value.get(KEY_META)?.remark
      ?? opts.allResponses.value.get(KEY_LEGACY)?.conclusion,
    (raw, prev) => {
      if (!raw || raw === prev) return
      const localAnswered = bQuestions.value.some((q) => q.answer !== null)
        || cQuestions.value.some((q) => q.answer !== null)
        || !!instrumentName.value
      if (!localAnswered) loadAll()
    },
  )

  function persistResult() {
    if (opts.isReadonly.value) return
    const chip = G1_DERIVATIVE_ID_CHIP[idResult.value]
    opts.debouncedSave(KEY_RESULT, {
      remark: idResult.value,
      conclusion: chip.label,
    })
  }

  watch(idResult, () => persistResult(), { immediate: true })

  function persistMeta() {
    if (opts.isReadonly.value) return
    opts.debouncedSave(KEY_META, {
      remark: JSON.stringify({
        instrumentName: instrumentName.value,
        natureDesc: natureDesc.value,
        accountCode: accountCode.value,
        accountingPolicy: accountingPolicy.value,
        cas22HybridNoted: cas22HybridNoted.value,
      }),
    })
  }

  function setInstrumentName(v: string) {
    if (opts.isReadonly.value) return
    instrumentName.value = v
    persistMeta()
  }

  function setMetaField(
    field: 'natureDesc' | 'accountCode' | 'accountingPolicy',
    value: string,
  ) {
    if (opts.isReadonly.value) return
    if (field === 'natureDesc') natureDesc.value = value
    else if (field === 'accountCode') accountCode.value = value
    else accountingPolicy.value = value
    persistMeta()
  }

  function setCas22HybridNoted(v: boolean) {
    if (opts.isReadonly.value) return
    cas22HybridNoted.value = v
    persistMeta()
  }

  function setBAnswer(id: string, value: boolean | null) {
    if (opts.isReadonly.value) return
    bQuestions.value = bQuestions.value.map((q) =>
      q.id === id ? { ...q, answer: value } : q,
    )
    opts.debouncedSave(KEY_B, { remark: JSON.stringify(bQuestions.value) })
  }

  function setBRemark(id: string, value: string) {
    if (opts.isReadonly.value) return
    bQuestions.value = bQuestions.value.map((q) =>
      q.id === id ? { ...q, remark: value } : q,
    )
    opts.debouncedSave(KEY_B, { remark: JSON.stringify(bQuestions.value) })
  }

  /**
   * 从合同 OCR 结果自动勾选 B 问卷。
   * ocrFields 的键对齐后端 _g1_contract_ocr.py 的 _B_VARIABLE_FIELDS。
   * 仅将识别为 true 的变量置「是」（不覆盖已答项为否，避免误清人工判断），
   * 返回本次自动置「是」的数量。
   */
  function applyContractOcrToB(ocrFields: Record<string, unknown>): number {
    if (opts.isReadonly.value) return 0
    const map: Record<string, string> = {
      b1_interestRate: 'b1',
      b2_financialPrice: 'b2',
      b3_commodityPrice: 'b3',
      b4_exchangeRate: 'b4',
      b5_priceIndex: 'b5',
      b6_creditRating: 'b6',
      b7_otherFinancial: 'b7',
      b8_otherNonFinancial: 'b8',
    }
    let applied = 0
    const next = bQuestions.value.map((q) => ({ ...q }))
    for (const [ocrKey, bId] of Object.entries(map)) {
      if (ocrFields[ocrKey] === true) {
        const row = next.find((q) => q.id === bId)
        if (row && row.answer !== true) {
          row.answer = true
          if (!row.remark) row.remark = '合同OCR识别'
          applied += 1
        }
      }
    }
    if (applied > 0) {
      bQuestions.value = next
      opts.debouncedSave(KEY_B, { remark: JSON.stringify(bQuestions.value) })
    }
    // OCR 识别的工具名称回填（仅当本地为空）
    const nm = ocrFields.instrumentName
    if (typeof nm === 'string' && nm.trim() && !instrumentName.value) {
      setInstrumentName(nm.trim())
    }
    return applied
  }

  function setCAnswer(id: string, value: boolean | null) {
    if (opts.isReadonly.value) return
    cQuestions.value = cQuestions.value.map((q) =>
      q.id === id ? { ...q, answer: value } : q,
    )
    opts.debouncedSave(KEY_C, { remark: JSON.stringify(cQuestions.value) })
  }

  function setCExplanation(id: string, value: string) {
    if (opts.isReadonly.value) return
    cQuestions.value = cQuestions.value.map((q) =>
      q.id === id ? { ...q, explanation: value } : q,
    )
    opts.debouncedSave(KEY_C, { remark: JSON.stringify(cQuestions.value) })
  }

  function persistVouchers() {
    if (opts.isReadonly.value) return
    opts.debouncedSave(KEY_VOUCHER, { remark: JSON.stringify(vouchers.value) })
  }

  function addVoucher() {
    if (opts.isReadonly.value) return
    vouchers.value = [
      ...vouchers.value,
      createEmptyVoucherRow(vouchers.value.length + 1),
    ]
    persistVouchers()
  }

  function updateVoucher(id: string, patch: Partial<G1DerivativeVoucherRow>) {
    if (opts.isReadonly.value) return
    vouchers.value = vouchers.value.map((r) => {
      if (r.id !== id) return r
      const next = { ...r, ...patch }
      if ('debitAmount' in patch) next.debitAmount = parseNum(patch.debitAmount)
      if ('creditAmount' in patch) next.creditAmount = parseNum(patch.creditAmount)
      return next
    })
    persistVouchers()
  }

  function removeVoucher(id: string) {
    if (opts.isReadonly.value || vouchers.value.length <= 1) return
    vouchers.value = vouchers.value
      .filter((r) => r.id !== id)
      .map((r, i) => ({ ...r, seq: i + 1 }))
    persistVouchers()
  }

  /** 抽凭引擎回填（对齐 G1-13） */
  function applySamplingResults(samples: SampledVoucher[], mode: 'append' | 'replace' = 'append') {
    if (opts.isReadonly.value || !samples?.length) return 0
    const mapped = samples.map((v, i) => ({
      ...createEmptyVoucherRow(i + 1),
      date: v.voucherDate || '',
      voucherNo: v.voucherNo || '',
      businessContent: v.summary || '',
      detailAccount: [v.accountCode, v.accountName].filter(Boolean).join(' '),
      counterAccount: v.counterpartAccount || '',
      debitAmount: parseNum(v.debitAmount),
      creditAmount: parseNum(v.creditAmount),
      conclusion: v.abnormal ? '异常待查' : (v.checkResult === 'pass' ? '未见异常' : ''),
    }))
    if (mode === 'replace') {
      vouchers.value = mapped
    } else {
      const existing = new Set(vouchers.value.map((r) => r.voucherNo).filter(Boolean))
      const blankOnly = vouchers.value.length === 1
        && !vouchers.value[0].voucherNo
        && !vouchers.value[0].businessContent
      const base = blankOnly ? [] : vouchers.value
      const add = mapped.filter((r) => !r.voucherNo || !existing.has(r.voucherNo))
      vouchers.value = [...base, ...add].map((r, i) => ({ ...r, seq: i + 1 }))
    }
    persistVouchers()
    return mapped.length
  }

  /** 从 G1-13 检查表带入抽查凭证 */
  function syncVouchersFromG113(): number {
    if (opts.isReadonly.value) return 0
    const raw = opts.allResponses.value.get('G1-13-rows')?.conclusion
      || opts.allResponses.value.get('G1-13-rows')?.remark
    if (!raw) return 0
    let parsed: any[] = []
    try {
      parsed = JSON.parse(raw)
    } catch {
      return 0
    }
    if (!Array.isArray(parsed) || !parsed.length) return 0
    const mapped = parsed
      .filter((r) => r.voucherNo || r.businessContent || r.voucherDate)
      .map((r, i) => ({
        ...createEmptyVoucherRow(i + 1),
        date: String(r.voucherDate || r.date || ''),
        voucherNo: String(r.voucherNo || ''),
        businessContent: String(r.businessContent || r.summary || ''),
        detailAccount: String(r.debitAccount || r.detailAccount || ''),
        counterAccount: String(r.counterAccount || r.creditAccount || ''),
        debitAmount: parseNum(r.debitAmount),
        creditAmount: parseNum(r.creditAmount),
        conclusion: String(r.conclusion || r.checkConclusion || ''),
      }))
    if (!mapped.length) return 0
    const existing = new Set(vouchers.value.map((r) => r.voucherNo).filter(Boolean))
    const blankOnly = vouchers.value.length === 1
      && !vouchers.value[0].voucherNo
      && !vouchers.value[0].businessContent
    const base = blankOnly ? [] : vouchers.value
    const add = mapped.filter((r) => !r.voucherNo || !existing.has(r.voucherNo))
    vouchers.value = [...base, ...add].map((r, i) => ({ ...r, seq: i + 1 }))
    persistVouchers()
    return add.length
  }

  function persistExperts() {
    if (opts.isReadonly.value) return
    opts.debouncedSave(KEY_EXPERT, { remark: JSON.stringify(experts.value) })
  }

  function updateExpert(id: string, patch: Partial<G1DerivativeExpertRow>) {
    if (opts.isReadonly.value) return
    experts.value = experts.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
    persistExperts()
  }

  function setAuditConclusion(v: string) {
    if (opts.isReadonly.value) return
    auditConclusion.value = v
    opts.debouncedSave(KEY_CONCLUSION, { conclusion: v, remark: v })
  }

  /** 演示路径：存在汇率变量 + 嵌入衍生 */
  function applyEmbeddedDemo() {
    if (opts.isReadonly.value) return
    if (!instrumentName.value) instrumentName.value = '示例：含汇率挂钩条款的理财合同'
    bQuestions.value = bQuestions.value.map((q) => ({
      ...q,
      answer: q.id === 'b4',
    }))
    cQuestions.value = cQuestions.value.map((q) => ({
      ...q,
      answer: q.id === 'c0' ? true : q.id === 'c1' ? true : q.id === 'c2' ? true : null,
    }))
    opts.debouncedSave(KEY_B, { remark: JSON.stringify(bQuestions.value) })
    opts.debouncedSave(KEY_C, { remark: JSON.stringify(cQuestions.value) })
    persistMeta()
    persistResult()
  }

  return {
    instrumentName,
    natureDesc,
    accountCode,
    accountingPolicy,
    cas22HybridNoted,
    bQuestions,
    cQuestions,
    vouchers,
    experts,
    legacyRows,
    auditConclusion,
    idResult,
    idChip,
    hasUnderlyingVariable,
    showEmbeddedSection,
    skipFurther,
    cas22Hint,
    setInstrumentName,
    setMetaField,
    setCas22HybridNoted,
    setBAnswer,
    setBRemark,
    applyContractOcrToB,
    setCAnswer,
    setCExplanation,
    addVoucher,
    updateVoucher,
    removeVoucher,
    applySamplingResults,
    syncVouchersFromG113,
    updateExpert,
    setAuditConclusion,
    applyEmbeddedDemo,
    loadAll,
  }
}

export default useG1DerivativeCheck
