/**
 * useG1VoucherCheck — G1-13 交易性金融资产检查表
 *
 * 对齐 Excel《交易性金融资产检查表 G1-13》：
 * 目标 → 抽样计划 → 本期发生额检查 / 期后处置新售 → 六项核对 → 检查比例 → 说明/结论
 *
 * 保留：抽凭引擎填入、OCR 附件、旧行字段迁移
 * 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读走共享回填函数 `useVoucherCheckFill`：本期 / 期后两个区段各算
 * 一张表（「替换本阶段抽凭行」只动当前区段），一个对方科目一行（后端配对），按分录指纹去重，行元数据 `_gt` 随行
 * JSON 落库（spec voucher-identity-writeback-and-audit-phase 任务 11）。
 */
import { ref, computed, watch, type ComputedRef, type Ref } from 'vue'
import { parseNum, calcSubtotal } from './useG1TraFinFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import type { SampledVoucher } from './useSamplingAlgorithms'
import {
  counterpartText, metaOf, useVoucherCheckFill, withRowMeta,
  type EngineFilledPayload, type FillSample, type PreparedItem,
} from './shared/voucherCheckFill'

export type G1VoucherPeriod = 'current' | 'subsequent'
export type G1VoucherTab = 'basic' | 'check' | 'result'

/** 六项核对说明（Excel 红色提示 1–6） */
export const G1_VOUCHER_CHECK_ITEMS = [
  { key: 'check1DocsComplete', label: '①原始单据齐全', hint: '合同、交割单、银行回单、审批单等' },
  { key: 'check2VoucherMatch', label: '②凭证与单据相符', hint: '记账凭证与原始单据金额、内容一致' },
  { key: 'check3Accounting', label: '③账务处理正确', hint: '科目、方向、金额符合准则' },
  { key: 'check4Period', label: '④期间正确', hint: '记入正确会计期间（截止测试）' },
  { key: 'check5FairValue', label: '⑤公允价值计量正确', hint: '估值/市价取数与入账一致' },
  { key: 'check6Approval', label: '⑥授权审批恰当', hint: '投资决策与支付授权完整' },
] as const

export type G1CheckKey = (typeof G1_VOUCHER_CHECK_ITEMS)[number]['key']

export interface G1VoucherSamplingPlan {
  /** 测试总体 — 借方发生额 */
  populationDebit: number
  /** 测试总体 — 贷方发生额 */
  populationCredit: number
  /** 测试总体 — 笔数 */
  populationCount: number
  /** 金额门槛说明，如「单笔 50 万以上」 */
  amountThreshold: string
  /** 是否覆盖全部关联方 */
  includeRelatedParty: boolean
  /** 抽样方法 */
  method: 'random' | 'systematic' | 'judgmental' | 'mus' | ''
  methodNote: string
  criteriaNote: string
}

export interface G1VoucherCheckRow {
  id: string
  seq: number
  /** 本期发生额 / 期后处置新售 */
  period: G1VoucherPeriod
  voucherDate: string
  voucherNo: string
  businessContent: string
  debitAccount: string
  creditAccount: string
  debitAmount: number
  creditAmount: number
  /** 兼容旧「金额」列 = max(借,贷) */
  amount: number
  supportingDocs: string
  check1DocsComplete: boolean | null
  check2VoucherMatch: boolean | null
  check3Accounting: boolean | null
  check4Period: boolean | null
  check5FairValue: boolean | null
  check6Approval: boolean | null
  indexRef: string
  isAbnormal: boolean
  abnormalDesc: string
  remark: string
  attachment: string
  sampleSource: string
  // 旧字段兼容（导入/测试）
  summary: string
  securityName: string
  investType: string
  counterAccount: string
  contractCheck: string
  settlementCheck: string
  quoteCheck: string
  approvalCheck: string
  bookkeepingCheck: string
  auditConclusion: string
}

export interface G1VoucherCheckColumn {
  prop: keyof G1VoucherCheckRow
  label: string
  width: number
  type: 'text' | 'number'
}

/** 兼容集成测试：仍导出「核对列」名（映射到新六项 + 结论） */
export const G1_VOUCHER_CHECK_COLUMNS: G1VoucherCheckColumn[] = [
  { prop: 'seq', label: '序号', width: 60, type: 'number' },
  { prop: 'voucherDate', label: '凭证日期', width: 120, type: 'text' },
  { prop: 'voucherNo', label: '凭证号', width: 110, type: 'text' },
  { prop: 'amount', label: '金额', width: 120, type: 'number' },
  { prop: 'contractCheck', label: '合同核对', width: 110, type: 'text' },
  { prop: 'settlementCheck', label: '结算单核对', width: 120, type: 'text' },
  { prop: 'quoteCheck', label: '报价/估值核对', width: 130, type: 'text' },
  { prop: 'approvalCheck', label: '授权审批核对', width: 130, type: 'text' },
  { prop: 'bookkeepingCheck', label: '账务处理核对', width: 130, type: 'text' },
  { prop: 'auditConclusion', label: '审计结论', width: 140, type: 'text' },
]

const DATA_KEY = 'G1-13-rows'
const PLAN_KEY = 'G1-13-sampling-plan'
const CONCLUSION_KEY = 'G1-13-conclusion'

export const DEFAULT_SAMPLING_PLAN: G1VoucherSamplingPlan = {
  populationDebit: 0,
  populationCredit: 0,
  populationCount: 0,
  amountThreshold: '',
  includeRelatedParty: true,
  method: 'random',
  methodNote: '',
  criteriaNote: '',
}

export const G1_SAMPLING_METHOD_OPTIONS = [
  { value: 'random', label: '随机抽样' },
  { value: 'systematic', label: '系统抽样' },
  { value: 'judgmental', label: '判断抽样' },
  { value: 'mus', label: '货币单位抽样(MUS)' },
] as const

function genId(): string {
  return `g1v-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

function toTriBool(v: unknown): boolean | null {
  if (v === true || v === '✓' || v === '是' || v === 'yes' || v === 'Y' || v === '1' || v === 'true') return true
  if (v === false || v === '✗' || v === '否' || v === 'no' || v === 'N' || v === '0' || v === 'false') return false
  if (v === null || v === undefined || v === '') return null
  // 旧文本「相符/无异常」视为通过
  const s = String(v).trim()
  if (!s) return null
  if (/不符|异常|错误|失败|否/.test(s)) return false
  return true
}

function checkToLegacy(v: boolean | null): string {
  if (v === true) return '相符'
  if (v === false) return '不符'
  return ''
}

/** 检查比例 = 样本金额 / 总体金额；总体为 0 时返回 null（避免 DIV/0） */
export function calcInspectionRatio(sampleAmount: number, populationAmount: number): number | null {
  const pop = parseNum(populationAmount)
  if (pop === 0) return null
  return parseNum(sampleAmount) / pop
}

export function enrichVoucherRow(raw: Partial<G1VoucherCheckRow> & { id?: string }, seq: number): G1VoucherCheckRow {
  const debit = parseNum(raw.debitAmount)
  const credit = parseNum(raw.creditAmount ?? (debit ? 0 : raw.amount))
  const amount = Math.max(debit, credit, parseNum(raw.amount))

  // 旧五列文本 → 六项布尔
  let c1 = toTriBool(raw.check1DocsComplete)
  let c2 = toTriBool(raw.check2VoucherMatch)
  let c3 = toTriBool(raw.check3Accounting ?? raw.bookkeepingCheck)
  let c4 = toTriBool(raw.check4Period)
  let c5 = toTriBool(raw.check5FairValue ?? raw.quoteCheck)
  let c6 = toTriBool(raw.check6Approval ?? raw.approvalCheck)
  if (c1 === null && raw.contractCheck != null && raw.contractCheck !== '') c1 = toTriBool(raw.contractCheck)
  if (c2 === null && raw.settlementCheck != null && raw.settlementCheck !== '') c2 = toTriBool(raw.settlementCheck)

  const checks = [c1, c2, c3, c4, c5, c6]
  const hasFail = checks.some((c) => c === false)
  let isAbnormal = raw.isAbnormal === true || raw.isAbnormal === ('是' as unknown)
  if (raw.isAbnormal === false || raw.isAbnormal === ('否' as unknown)) isAbnormal = false
  else if (hasFail) isAbnormal = true

  const businessContent = raw.businessContent || raw.summary || ''
  const counterAccount = raw.counterAccount || raw.creditAccount || raw.debitAccount || ''

  return {
    id: raw.id || genId(),
    seq,
    period: raw.period === 'subsequent' ? 'subsequent' : 'current',
    voucherDate: raw.voucherDate || '',
    voucherNo: raw.voucherNo || '',
    businessContent,
    debitAccount: raw.debitAccount || '',
    creditAccount: raw.creditAccount || '',
    debitAmount: debit,
    creditAmount: credit || (debit === 0 ? amount : 0),
    amount,
    supportingDocs: raw.supportingDocs || '',
    check1DocsComplete: c1,
    check2VoucherMatch: c2,
    check3Accounting: c3,
    check4Period: c4,
    check5FairValue: c5,
    check6Approval: c6,
    indexRef: raw.indexRef || '',
    isAbnormal,
    abnormalDesc: raw.abnormalDesc || '',
    remark: raw.remark || '',
    attachment: raw.attachment || '',
    sampleSource: raw.sampleSource || '',
    summary: businessContent,
    securityName: raw.securityName || '',
    investType: raw.investType || '',
    counterAccount,
    contractCheck: checkToLegacy(c1),
    settlementCheck: checkToLegacy(c2),
    quoteCheck: checkToLegacy(c5),
    approvalCheck: checkToLegacy(c6),
    bookkeepingCheck: checkToLegacy(c3),
    auditConclusion: raw.auditConclusion || (isAbnormal ? '异常' : hasFail ? '异常' : checks.every((c) => c === true) ? '无异常' : ''),
  }
}

function emptyRow(seq: number, period: G1VoucherPeriod = 'current'): G1VoucherCheckRow {
  return enrichVoucherRow({ period }, seq)
}

function loadRows(map: Map<string, ChecklistResponse>): G1VoucherCheckRow[] {
  const raw = map.get(DATA_KEY)?.conclusion || map.get(DATA_KEY)?.remark
  if (!raw) return [emptyRow(1, 'current'), emptyRow(1, 'subsequent')]
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed) || !parsed.length) return [emptyRow(1, 'current'), emptyRow(1, 'subsequent')]
    return parsed.map((p: Partial<G1VoucherCheckRow>, i: number) => withRowMeta(enrichVoucherRow(p, i + 1), p))
  } catch {
    return [emptyRow(1, 'current'), emptyRow(1, 'subsequent')]
  }
}

function loadPlan(map: Map<string, ChecklistResponse>): G1VoucherSamplingPlan {
  const raw = map.get(PLAN_KEY)?.conclusion || map.get(PLAN_KEY)?.remark
  if (!raw) return { ...DEFAULT_SAMPLING_PLAN }
  try {
    return { ...DEFAULT_SAMPLING_PLAN, ...JSON.parse(raw) }
  } catch {
    return { ...DEFAULT_SAMPLING_PLAN }
  }
}

/**
 * 共享回填函数的待写入项 → G1-13 检查行（区段由所进的表定）：金额在样本自己的借贷栏；样本在借方则对方科目
 * 进贷方科目、本科目进借方科目，反之亦然（原实现一律写进贷方科目）
 */
export function mapPreparedToG1VoucherRow(item: PreparedItem, period: G1VoucherPeriod, seq: number): G1VoucherCheckRow {
  const s = item.sample as PreparedItem['sample'] & { summary?: string | null; accountCode?: string; accountName?: string }
  const debit = parseNum(item.debitAmount)
  const credit = parseNum(item.creditAmount)
  const own = [s.accountCode, s.accountName].filter(Boolean).join(' ')
  const counter = counterpartText(item)
  const onDebit = item.debitAmount !== null
  return enrichVoucherRow({
    period,
    voucherDate: s.voucherDate || '',
    voucherNo: s.voucherNo || '',
    businessContent: s.summary || '',
    debitAmount: debit,
    creditAmount: credit,
    amount: Math.max(debit, credit),
    debitAccount: onDebit ? own : counter,
    creditAccount: onDebit ? counter : own,
    counterAccount: counter,
    sampleSource: '抽凭引擎',
  }, seq)
}

/** 行上已填核对结果、支持性文件、索引、异常说明、备注或附件（替换与撤销抽凭时据此先确认） */
export function hasG1VoucherContent(r: G1VoucherCheckRow): boolean {
  return [r.check1DocsComplete, r.check2VoucherMatch, r.check3Accounting, r.check4Period, r.check5FairValue, r.check6Approval]
    .some((c) => c !== null)
    || [r.supportingDocs, r.indexRef, r.abnormalDesc, r.remark, r.attachment].some((v) => String(v ?? '').trim() !== '')
}

export function useG1VoucherCheck(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
  /** 项目 id（抽凭回填按项目当前审计阶段标行阶段，年审阶段预审行只读） */
  projectId?: Ref<string | undefined> | ComputedRef<string | undefined>
}) {
  const rows = ref<G1VoucherCheckRow[]>(loadRows(opts.allResponses.value))
  const samplingPlan = ref<G1VoucherSamplingPlan>(loadPlan(opts.allResponses.value))
  const auditConclusion = ref(opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? '')
  const activePeriod = ref<G1VoucherPeriod>('current')
  const activeTab = ref<G1VoucherTab>('basic')

  /** 已在某个区段的分录（按指纹）：再次回填 / 挂凭导入仍进那个区段 */
  function periodHolding(lfp: string | null): G1VoucherPeriod | null {
    if (!lfp) return null
    return rows.value.find((r) => metaOf(r)?.lfp === lfp)?.period ?? null
  }
  /** 两个区段各算一张表：共享回填函数按表替换，「替换本阶段抽凭行」只动当前区段 */
  const periodTable = (period: G1VoucherPeriod) => computed<G1VoucherCheckRow[]>({
    get: () => rows.value.filter((r) => r.period === period),
    set: (list) => {
      const cur = period === 'current' ? list : rows.value.filter((r) => r.period === 'current')
      const sub = period === 'subsequent' ? list : rows.value.filter((r) => r.period === 'subsequent')
      rows.value = [...cur, ...sub]
    },
  })
  const periodTables = { current: periodTable('current'), subsequent: periodTable('subsequent') }
  // 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读：共享回填函数
  const voucherFill = useVoucherCheckFill<G1VoucherCheckRow>({
    projectId: () => opts.projectId?.value,
    tables: periodTables,
    tableOf: (item) => periodHolding(item.meta.lfp),
    mapSampleToRow: (item, key) => mapPreparedToG1VoucherRow(item, key as G1VoucherPeriod, rows.value.length + 1),
    persist: () => persistAll(),
    hasUserContent: hasG1VoucherContent,
    afterChange: () => { rows.value.forEach((r, i) => { r.seq = i + 1 }) },
    readonly: () => opts.isReadonly.value,
  })
  voucherFill.markLoaded()

  /** 年审阶段的预审行只读（不可改、不可删） */
  function lockedRow(id: string): boolean {
    const row = rows.value.find((r) => r.id === id)
    return !!row && voucherFill.isRowLocked(row)
  }

  function loadAll() {
    rows.value = loadRows(opts.allResponses.value)
    voucherFill.markLoaded()
    samplingPlan.value = loadPlan(opts.allResponses.value)
    auditConclusion.value = opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? ''
  }

  watch(
    () => opts.allResponses.value.get(DATA_KEY)?.conclusion,
    (raw) => {
      if (!raw) return
      rows.value = loadRows(opts.allResponses.value)
      voucherFill.markLoaded()
    },
  )

  const periodRows = computed(() =>
    rows.value.filter((r) => r.period === activePeriod.value),
  )

  const currentRows = computed(() => rows.value.filter((r) => r.period === 'current'))
  const subsequentRows = computed(() => rows.value.filter((r) => r.period === 'subsequent'))

  const sampleDebit = computed(() =>
    calcSubtotal(periodRows.value.map((r) => parseNum(r.debitAmount))),
  )
  const sampleCredit = computed(() =>
    calcSubtotal(periodRows.value.map((r) => parseNum(r.creditAmount))),
  )
  const sampleAmount = computed(() =>
    calcSubtotal(periodRows.value.map((r) => parseNum(r.amount))),
  )

  const populationAmount = computed(() => {
    const d = parseNum(samplingPlan.value.populationDebit)
    const c = parseNum(samplingPlan.value.populationCredit)
    return Math.max(d + c, d, c)
  })

  /** 检查比例；无总体时为 null */
  const inspectionRatio = computed(() =>
    calcInspectionRatio(sampleAmount.value, populationAmount.value),
  )

  const total = computed(() => calcSubtotal(rows.value.map((r) => parseNum(r.amount))))
  const abnormalCount = computed(() => rows.value.filter((r) => r.isAbnormal).length)
  const sampledCount = computed(() => rows.value.filter((r) => !!r.sampleSource).length)
  const pendingCheckCount = computed(() =>
    rows.value.filter((r) => {
      const checks = [
        r.check1DocsComplete, r.check2VoucherMatch, r.check3Accounting,
        r.check4Period, r.check5FairValue, r.check6Approval,
      ]
      return checks.some((c) => c === null) && (r.voucherNo || r.amount)
    }).length,
  )

  function persistAll() {
    if (opts.isReadonly.value) return
    // 年审阶段预审行按读入版本写回（两个区段各一张表）
    const payload = JSON.stringify([
      ...voucherFill.guardPersist(periodTables.current.value, 'current'),
      ...voucherFill.guardPersist(periodTables.subsequent.value, 'subsequent'),
    ])
    opts.debouncedSave(DATA_KEY, { conclusion: payload, remark: payload })
  }

  function persistPlan() {
    if (opts.isReadonly.value) return
    const payload = JSON.stringify(samplingPlan.value)
    opts.debouncedSave(PLAN_KEY, { conclusion: payload, remark: payload })
  }

  watch(auditConclusion, (v) => {
    if (!opts.isReadonly.value) opts.debouncedSave(CONCLUSION_KEY, { conclusion: v })
  })

  function updateSamplingPlan(patch: Partial<G1VoucherSamplingPlan>) {
    if (opts.isReadonly.value) return
    samplingPlan.value = { ...samplingPlan.value, ...patch }
    persistPlan()
  }

  function updateRow(id: string, patch: Partial<G1VoucherCheckRow>) {
    if (opts.isReadonly.value || lockedRow(id)) return
    rows.value = rows.value.map((r) => {
      if (r.id !== id) return r
      return withRowMeta(enrichVoucherRow({ ...r, ...patch, id: r.id }, r.seq), r)
    })
    persistAll()
  }

  function setCheck(id: string, key: G1CheckKey, value: boolean | null) {
    updateRow(id, { [key]: value } as Partial<G1VoucherCheckRow>)
  }

  function addRow(period?: G1VoucherPeriod) {
    if (opts.isReadonly.value) return
    const p = period || activePeriod.value
    const seq = rows.value.filter((r) => r.period === p).length + 1
    rows.value = [...rows.value, emptyRow(seq, p)].map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
  }

  function removeRow(id: string) {
    if (opts.isReadonly.value || lockedRow(id)) return
    const next = rows.value.filter((r) => r.id !== id)
    const cur = next.filter((r) => r.period === 'current')
    const sub = next.filter((r) => r.period === 'subsequent')
    if (!cur.length) cur.push(emptyRow(1, 'current'))
    if (!sub.length) sub.push(emptyRow(1, 'subsequent'))
    rows.value = [...cur, ...sub].map((r, i) => ({ ...r, seq: i + 1 }))
    persistAll()
  }

  function mapVoucherToRow(v: SampledVoucher, seq: number, period: G1VoucherPeriod = 'current'): G1VoucherCheckRow {
    const debit = v.debitAmount ? parseNum(v.debitAmount) : 0
    const credit = v.creditAmount ? parseNum(v.creditAmount) : 0
    return enrichVoucherRow(
      {
        period,
        voucherDate: v.voucherDate || '',
        voucherNo: v.voucherNo || '',
        businessContent: v.summary || '',
        debitAmount: debit,
        creditAmount: credit,
        amount: Math.max(debit, credit),
        counterAccount: v.counterpartAccount || '',
        creditAccount: v.counterpartAccount || '',
        sampleSource: '抽凭引擎',
      },
      seq,
    )
  }

  /** 抽凭引擎回填进当前区段：一个对方科目一行，按分录指纹去重；「替换本阶段抽凭行」只删当前区段本阶段抽凭填入的行 */
  function onEngineFilled(payload: EngineFilledPayload) {
    return voucherFill.onEngineFilled(payload, { tables: [activePeriod.value] })
  }

  /** 从序时账挂入导入当前区段：幂等追加（已在另一区段的分录留在原处） */
  function onAttachImported(samples: FillSample[]) {
    return voucherFill.onAttachImported(samples, { tables: [activePeriod.value] })
  }

  return {
    columns: G1_VOUCHER_CHECK_COLUMNS,
    rows,
    periodRows,
    currentRows,
    subsequentRows,
    samplingPlan,
    auditConclusion,
    activePeriod,
    activeTab,
    total,
    sampleDebit,
    sampleCredit,
    sampleAmount,
    populationAmount,
    inspectionRatio,
    abnormalCount,
    sampledCount,
    pendingCheckCount,
    loadAll,
    persistAll,
    updateSamplingPlan,
    updateRow,
    setCheck,
    addRow,
    removeRow,
    mapVoucherToRow,
    // 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读（共享回填函数）
    onEngineFilled,
    onAttachImported,
    onUndoRequest: voucherFill.onUndoRequest,
    voucherRowClass: voucherFill.rowClass,
    isVoucherRowLocked: voucherFill.isRowLocked,
    voucherFillReady: voucherFill.ready,
    CHECK_ITEMS: G1_VOUCHER_CHECK_ITEMS,
  }
}

export default useG1VoucherCheck
