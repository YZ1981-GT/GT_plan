/**
 * useG1ContractCashflow — G1-10 合同现金流量特征分析（SPPI）
 *
 * 对齐 Excel《合同现金流量特征分析 G1-10》六大分区：
 * (一)债券 (二)理财两步 (三)优先股/永续债 (四)可转债 (五)项目收益/信托 (六)ABS
 *
 * 判定规则（CAS 22 / IFRS 9）：
 * - 权益转换、杠杆 → 不通过
 * - 仅提前赎回/展期 → 需进一步分析
 * - 不保本理财 → 不通过（FVTPL）
 * - 可转债含转股条款 → 通常不通过（嵌入权益衍生）
 * - ABS 次级/首次损失 → 不通过；优先档需穿透
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { determineSPPIConclusion, type SPPIResult } from '@/composables/useG4SppiFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export type G1SppiConclusion = SPPIResult | ''

export const G1_SPPI_CONCLUSION_OPTIONS: { value: G1SppiConclusion; label: string }[] = [
  { value: 'PASS', label: '通过 SPPI' },
  { value: 'FAIL', label: '不通过（FVTPL）' },
  { value: 'FURTHER_ANALYSIS', label: '需进一步分析' },
  { value: '', label: '未判定' },
]

export type G1SppiSectionKey =
  | 'bond'
  | 'wealth1'
  | 'wealth2'
  | 'perpetual'
  | 'convertible'
  | 'project'
  | 'abs'

export const G1_SPPI_SECTIONS: { key: G1SppiSectionKey; label: string }[] = [
  { key: 'bond', label: '（一）债券投资' },
  { key: 'wealth1', label: '（二）理财·保本保收益' },
  { key: 'wealth2', label: '（二）理财·浮动不现实' },
  { key: 'perpetual', label: '（三）优先股/永续债' },
  { key: 'convertible', label: '（四）可转换债券' },
  { key: 'project', label: '（五）项目收益/信托' },
  { key: 'abs', label: '（六）资产支持证券' },
]

/** （一）债券投资 */
export interface G1BondSppiRow {
  id: string
  seq: number
  investItem: string
  bookOrFaceValue: number
  couponRate: string
  hasEarlyRedemption: 'yes' | 'no' | ''
  hasExtension: 'yes' | 'no' | ''
  hasEquityConversion: 'yes' | 'no' | ''
  hasLeverage: 'yes' | 'no' | ''
  /** 自动建议结论（只读展示） */
  suggested: G1SppiConclusion
  conclusion: G1SppiConclusion
  analysisNote: string
  /** 用户是否手动覆盖自动结论 */
  conclusionOverridden: boolean
}

/** （二）第一步：保本保收益 */
export interface G1WealthStep1Row {
  id: string
  seq: number
  investItem: string
  totalAmount: number
  guaranteesPrincipal: 'yes' | 'no' | ''
  fixedGuaranteed: 'yes' | 'no' | ''
  fixedRate: string
  floatingGuaranteed: 'yes' | 'no' | ''
  floatingRate: string
  suggested: G1SppiConclusion
  conclusion: G1SppiConclusion
  conclusionOverridden: boolean
  remark: string
}

/** （二）第二步：浮动收益是否不现实 */
export interface G1WealthStep2Row {
  id: string
  seq: number
  investItem: string
  fixedRate: string
  floatingMethod: string
  baseVariableHistory: string
  isUnrealistic: 'yes' | 'no' | ''
  suggested: G1SppiConclusion
  conclusion: G1SppiConclusion
  conclusionOverridden: boolean
  remark: string
}

/** （三）优先股、永续债 */
export interface G1PerpetualRow {
  id: string
  seq: number
  investItem: string
  bookValue: number
  term: string
  initialRate: string
  hasDeferredDividend: 'yes' | 'no' | ''
  deferredCompounds: 'yes' | 'no' | ''
  convertibleToFixedEquity: 'yes' | 'no' | ''
  suggested: G1SppiConclusion
  conclusion: G1SppiConclusion
  conclusionOverridden: boolean
  analysisNote: string
}

/** （四）可转换债券 */
export interface G1ConvertibleRow {
  id: string
  seq: number
  investItem: string
  totalAmount: number
  term: string
  couponRate: string
  initialConversionPrice: string
  hasConversionFeature: 'yes' | 'no' | ''
  featureDesc: string
  suggested: G1SppiConclusion
  conclusion: G1SppiConclusion
  conclusionOverridden: boolean
  analysisNote: string
}

/** （五）项目收益权、信托 */
export interface G1ProjectRow {
  id: string
  seq: number
  investItem: string
  totalAmount: number
  term: string
  couponRate: string
  underlyingCashFlow: string
  deficiencyCompensation: string
  guarantee: string
  cfDependsOnProjectOps: 'yes' | 'no' | ''
  suggested: G1SppiConclusion
  conclusion: G1SppiConclusion
  conclusionOverridden: boolean
  analysisNote: string
}

/** （六）ABS */
export interface G1AbsRow {
  id: string
  seq: number
  investItem: string
  totalAmount: number
  term: string
  couponRate: string
  /** 优先 / 次级 / 其他 */
  tranche: 'senior' | 'mezzanine' | 'subordinated' | 'other' | ''
  underlyingCashFlow: string
  creditRiskCompare: string
  lookThroughOk: 'yes' | 'no' | ''
  suggested: G1SppiConclusion
  conclusion: G1SppiConclusion
  conclusionOverridden: boolean
  analysisNote: string
}

export interface G1SppiStore {
  version: 2
  bondRows: G1BondSppiRow[]
  wealthStep1: G1WealthStep1Row[]
  wealthStep2: G1WealthStep2Row[]
  perpetualRows: G1PerpetualRow[]
  convertibleRows: G1ConvertibleRow[]
  projectRows: G1ProjectRow[]
  absRows: G1AbsRow[]
}

const DATA_KEY = 'G1-10-rows'
const CONCLUSION_KEY = 'G1-10-conclusion'

function genId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

function yn(v: unknown): boolean {
  return v === true || v === 'yes' || v === '是' || v === 'Y' || v === 'y'
}

function asYn(v: unknown): 'yes' | 'no' | '' {
  if (v === true || v === 'yes' || v === '是') return 'yes'
  if (v === false || v === 'no' || v === '否') return 'no'
  return ''
}

// ─── 自动判定（导出供单测）────────────────────────────────────────────────

export function suggestBondSppi(row: Pick<
  G1BondSppiRow,
  'hasEarlyRedemption' | 'hasExtension' | 'hasEquityConversion' | 'hasLeverage'
>): G1SppiConclusion {
  return determineSPPIConclusion(
    yn(row.hasEarlyRedemption),
    yn(row.hasExtension),
    yn(row.hasEquityConversion),
    yn(row.hasLeverage),
  )
}

/** 理财第一步：不保本→FAIL；保本+浮动→需第二步；保本+固定→PASS */
export function suggestWealthStep1(row: Pick<
  G1WealthStep1Row,
  'guaranteesPrincipal' | 'fixedGuaranteed' | 'floatingGuaranteed'
>): G1SppiConclusion {
  if (row.guaranteesPrincipal === 'no') return 'FAIL'
  if (row.guaranteesPrincipal !== 'yes') return ''
  if (row.floatingGuaranteed === 'yes') return 'FURTHER_ANALYSIS'
  if (row.fixedGuaranteed === 'yes') return 'PASS'
  return 'FURTHER_ANALYSIS'
}

/** 浮动收益不现实（非真实/极小）→可仍通过；否则不通过 */
export function suggestWealthStep2(row: Pick<G1WealthStep2Row, 'isUnrealistic'>): G1SppiConclusion {
  if (row.isUnrealistic === 'yes') return 'PASS'
  if (row.isUnrealistic === 'no') return 'FAIL'
  return ''
}

/** 可按固定数量转股 → FAIL；递延股息不必然失败 */
export function suggestPerpetual(row: Pick<
  G1PerpetualRow,
  'convertibleToFixedEquity' | 'hasDeferredDividend'
>): G1SppiConclusion {
  if (row.convertibleToFixedEquity === 'yes') return 'FAIL'
  if (row.hasDeferredDividend === 'yes') return 'FURTHER_ANALYSIS'
  if (row.convertibleToFixedEquity === 'no') return 'PASS'
  return ''
}

/** 含转股条款 → 通常 FAIL（嵌入权益衍生，与基本借贷安排不一致） */
export function suggestConvertible(row: Pick<G1ConvertibleRow, 'hasConversionFeature'>): G1SppiConclusion {
  if (row.hasConversionFeature === 'yes') return 'FAIL'
  if (row.hasConversionFeature === 'no') return 'PASS'
  return ''
}

/**
 * 现金流依赖项目运营且无差额补足/担保 → 倾向 FAIL；
 * 有补足或担保 → 需穿透进一步分析
 */
export function suggestProject(row: Pick<
  G1ProjectRow,
  'cfDependsOnProjectOps' | 'deficiencyCompensation' | 'guarantee'
>): G1SppiConclusion {
  const hasSupport =
    !!(row.deficiencyCompensation || '').trim() || !!(row.guarantee || '').trim()
  if (row.cfDependsOnProjectOps === 'yes' && !hasSupport) return 'FAIL'
  if (row.cfDependsOnProjectOps === 'yes' && hasSupport) return 'FURTHER_ANALYSIS'
  if (row.cfDependsOnProjectOps === 'no') return 'PASS'
  return ''
}

/** 次级/首次损失 → FAIL；优先档看穿透；穿透通过 → PASS */
export function suggestAbs(row: Pick<G1AbsRow, 'tranche' | 'lookThroughOk'>): G1SppiConclusion {
  if (row.tranche === 'subordinated') return 'FAIL'
  if (row.tranche === 'senior' || row.tranche === 'mezzanine') {
    if (row.lookThroughOk === 'yes') return 'PASS'
    if (row.lookThroughOk === 'no') return 'FAIL'
    return 'FURTHER_ANALYSIS'
  }
  return ''
}

export function applyConclusion<T extends { suggested: G1SppiConclusion; conclusion: G1SppiConclusion; conclusionOverridden: boolean }>(
  row: T,
  suggested: G1SppiConclusion,
): T {
  const next = { ...row, suggested }
  if (!row.conclusionOverridden) next.conclusion = suggested
  return next
}

// ─── Empty rows ─────────────────────────────────────────────────────────────

function emptyBond(seq = 1): G1BondSppiRow {
  return applyConclusion({
    id: genId('bond'),
    seq,
    investItem: '',
    bookOrFaceValue: 0,
    couponRate: '',
    hasEarlyRedemption: '',
    hasExtension: '',
    hasEquityConversion: 'no',
    hasLeverage: 'no',
    suggested: '' as G1SppiConclusion,
    conclusion: '' as G1SppiConclusion,
    analysisNote: '',
    conclusionOverridden: false,
  }, suggestBondSppi({ hasEarlyRedemption: '', hasExtension: '', hasEquityConversion: 'no', hasLeverage: 'no' }))
}

function emptyWealth1(seq = 1): G1WealthStep1Row {
  const base = {
    id: genId('w1'),
    seq,
    investItem: '',
    totalAmount: 0,
    guaranteesPrincipal: '' as const,
    fixedGuaranteed: '' as const,
    fixedRate: '',
    floatingGuaranteed: '' as const,
    floatingRate: '',
    suggested: '' as G1SppiConclusion,
    conclusion: '' as G1SppiConclusion,
    conclusionOverridden: false,
    remark: '',
  }
  return applyConclusion(base, suggestWealthStep1(base))
}

function emptyWealth2(seq = 1): G1WealthStep2Row {
  const base = {
    id: genId('w2'),
    seq,
    investItem: '',
    fixedRate: '',
    floatingMethod: '',
    baseVariableHistory: '',
    isUnrealistic: '' as const,
    suggested: '' as G1SppiConclusion,
    conclusion: '' as G1SppiConclusion,
    conclusionOverridden: false,
    remark: '',
  }
  return applyConclusion(base, suggestWealthStep2(base))
}

function emptyPerpetual(seq = 1): G1PerpetualRow {
  const base = {
    id: genId('perp'),
    seq,
    investItem: '',
    bookValue: 0,
    term: '',
    initialRate: '',
    hasDeferredDividend: '' as const,
    deferredCompounds: '' as const,
    convertibleToFixedEquity: 'no' as const,
    suggested: '' as G1SppiConclusion,
    conclusion: '' as G1SppiConclusion,
    conclusionOverridden: false,
    analysisNote: '',
  }
  return applyConclusion(base, suggestPerpetual(base))
}

function emptyConvertible(seq = 1): G1ConvertibleRow {
  const base = {
    id: genId('conv'),
    seq,
    investItem: '',
    totalAmount: 0,
    term: '',
    couponRate: '',
    initialConversionPrice: '',
    hasConversionFeature: 'yes' as const,
    featureDesc: '',
    suggested: '' as G1SppiConclusion,
    conclusion: '' as G1SppiConclusion,
    conclusionOverridden: false,
    analysisNote: '含转股条款通常引入权益价格风险，与基本借贷安排不一致，一般不通过 SPPI。',
  }
  return applyConclusion(base, suggestConvertible(base))
}

function emptyProject(seq = 1): G1ProjectRow {
  const base = {
    id: genId('proj'),
    seq,
    investItem: '',
    totalAmount: 0,
    term: '',
    couponRate: '',
    underlyingCashFlow: '',
    deficiencyCompensation: '',
    guarantee: '',
    cfDependsOnProjectOps: '' as const,
    suggested: '' as G1SppiConclusion,
    conclusion: '' as G1SppiConclusion,
    conclusionOverridden: false,
    analysisNote: '',
  }
  return applyConclusion(base, suggestProject(base))
}

function emptyAbs(seq = 1): G1AbsRow {
  const base = {
    id: genId('abs'),
    seq,
    investItem: '',
    totalAmount: 0,
    term: '',
    couponRate: '',
    tranche: '' as const,
    underlyingCashFlow: '',
    creditRiskCompare: '',
    lookThroughOk: '' as const,
    suggested: '' as G1SppiConclusion,
    conclusion: '' as G1SppiConclusion,
    conclusionOverridden: false,
    analysisNote: '',
  }
  return applyConclusion(base, suggestAbs(base))
}

function emptyStore(): G1SppiStore {
  return {
    version: 2,
    bondRows: [emptyBond(1)],
    wealthStep1: [emptyWealth1(1)],
    wealthStep2: [emptyWealth2(1)],
    perpetualRows: [emptyPerpetual(1)],
    convertibleRows: [emptyConvertible(1)],
    projectRows: [emptyProject(1)],
    absRows: [emptyAbs(1)],
  }
}

/** 旧版单表行 → 迁入债券分区 */
function migrateLegacyFlat(rows: Record<string, unknown>[]): G1SppiStore {
  const store = emptyStore()
  if (!rows.length) return store
  store.bondRows = rows.map((r, i) => {
    const base: G1BondSppiRow = {
      id: String(r.id || genId('bond')),
      seq: i + 1,
      investItem: String(r.investItem || r.securityName || ''),
      bookOrFaceValue: Number(r.bookOrFaceValue || r.bookValue || 0) || 0,
      couponRate: String(r.couponRate || ''),
      hasEarlyRedemption: asYn(r.hasEarlyRedemption ?? r.prepaymentExtension),
      hasExtension: asYn(r.hasExtension),
      hasEquityConversion: asYn(r.hasEquityConversion),
      hasLeverage: asYn(r.hasLeverage),
      suggested: '',
      conclusion: r.sppiConclusion === 'pass' || r.sppiConclusion === 'PASS'
        ? 'PASS'
        : r.sppiConclusion === 'fail' || r.sppiConclusion === 'FAIL'
          ? 'FAIL'
          : '',
      analysisNote: String(r.auditEval || r.contractTermDesc || r.analysisNote || ''),
      conclusionOverridden: true,
    }
    return applyConclusion(base, suggestBondSppi(base))
  })
  return store
}

function normalizeStore(raw: unknown): G1SppiStore {
  if (!raw) return emptyStore()
  if (Array.isArray(raw)) return migrateLegacyFlat(raw as Record<string, unknown>[])
  const o = raw as Partial<G1SppiStore>
  if (o.version === 2 || o.bondRows) {
    return {
      version: 2,
      bondRows: (o.bondRows?.length ? o.bondRows : [emptyBond(1)]).map((r, i) =>
        applyConclusion({ ...emptyBond(i + 1), ...r, seq: i + 1 }, suggestBondSppi(r)),
      ),
      wealthStep1: (o.wealthStep1?.length ? o.wealthStep1 : [emptyWealth1(1)]).map((r, i) =>
        applyConclusion({ ...emptyWealth1(i + 1), ...r, seq: i + 1 }, suggestWealthStep1(r)),
      ),
      wealthStep2: (o.wealthStep2?.length ? o.wealthStep2 : [emptyWealth2(1)]).map((r, i) =>
        applyConclusion({ ...emptyWealth2(i + 1), ...r, seq: i + 1 }, suggestWealthStep2(r)),
      ),
      perpetualRows: (o.perpetualRows?.length ? o.perpetualRows : [emptyPerpetual(1)]).map((r, i) =>
        applyConclusion({ ...emptyPerpetual(i + 1), ...r, seq: i + 1 }, suggestPerpetual(r)),
      ),
      convertibleRows: (o.convertibleRows?.length ? o.convertibleRows : [emptyConvertible(1)]).map((r, i) =>
        applyConclusion({ ...emptyConvertible(i + 1), ...r, seq: i + 1 }, suggestConvertible(r)),
      ),
      projectRows: (o.projectRows?.length ? o.projectRows : [emptyProject(1)]).map((r, i) =>
        applyConclusion({ ...emptyProject(i + 1), ...r, seq: i + 1 }, suggestProject(r)),
      ),
      absRows: (o.absRows?.length ? o.absRows : [emptyAbs(1)]).map((r, i) =>
        applyConclusion({ ...emptyAbs(i + 1), ...r, seq: i + 1 }, suggestAbs(r)),
      ),
    }
  }
  return emptyStore()
}

function loadStore(map: Map<string, ChecklistResponse>): G1SppiStore {
  const raw = map.get(DATA_KEY)?.conclusion || map.get(DATA_KEY)?.remark
  if (!raw) return emptyStore()
  try {
    return normalizeStore(JSON.parse(raw))
  } catch {
    return emptyStore()
  }
}

export const G1_SPPI_GUIDANCE = {
  bond: '利息应为货币时间价值、信用风险、其他基本借贷风险与成本及利润率的对价。含权益转换或杠杆通常不通过 SPPI。',
  wealth: '不保本 → 分类为 FVTPL。保本且含浮动收益时，评估浮动条件是否「不现实/极小」；若不现实仍可通过。',
  perpetual: '可递延利息不必然导致失败；若可按固定数量转换为权益工具，则通常不通过。',
  convertible: '转股条款引入权益价格风险，一般不通过 SPPI（模板示例写「通过」时应复核修正）。',
  project: '若现金流取决于特定项目运营表现，需穿透评估；无差额补足/担保时倾向不通过。',
  abs: '穿透三条件：①底层含符合 SPPI 的工具；②本档信用风险 ≤ 底层池平均；③无其他改变现金流的特征。次级档通常不通过。',
}

export function useG1ContractCashflow(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}) {
  const store = ref<G1SppiStore>(loadStore(opts.allResponses.value))
  const activeSection = ref<G1SppiSectionKey>('bond')
  const auditConclusion = ref(opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? '')

  function loadAll() {
    store.value = loadStore(opts.allResponses.value)
    auditConclusion.value = opts.allResponses.value.get(CONCLUSION_KEY)?.conclusion ?? ''
  }

  watch(
    () => opts.allResponses.value.get(DATA_KEY)?.conclusion,
    (raw) => {
      if (raw) store.value = loadStore(opts.allResponses.value)
    },
  )

  const stats = computed(() => {
    const all = [
      ...store.value.bondRows,
      ...store.value.wealthStep1,
      ...store.value.wealthStep2,
      ...store.value.perpetualRows,
      ...store.value.convertibleRows,
      ...store.value.projectRows,
      ...store.value.absRows,
    ]
    const pass = all.filter((r) => r.conclusion === 'PASS').length
    const fail = all.filter((r) => r.conclusion === 'FAIL').length
    const further = all.filter((r) => r.conclusion === 'FURTHER_ANALYSIS').length
    const pending = all.filter((r) => !r.conclusion).length
    const mismatches = all.filter(
      (r) => r.suggested && r.conclusion && r.suggested !== r.conclusion,
    ).length
    return { total: all.length, pass, fail, further, pending, mismatches }
  })

  function persist() {
    if (opts.isReadonly.value) return
    const payload = JSON.stringify(store.value)
    opts.debouncedSave(DATA_KEY, { conclusion: payload, remark: payload })
  }

  watch(auditConclusion, (v) => {
    if (!opts.isReadonly.value) opts.debouncedSave(CONCLUSION_KEY, { conclusion: v })
  })

  function reseq<T extends { seq: number }>(list: T[]): T[] {
    return list.map((r, i) => ({ ...r, seq: i + 1 }))
  }

  // ── bond ──
  function updateBond(id: string, patch: Partial<G1BondSppiRow>) {
    if (opts.isReadonly.value) return
    store.value = {
      ...store.value,
      bondRows: store.value.bondRows.map((r) => {
        if (r.id !== id) return r
        let next = { ...r, ...patch }
        if ('conclusion' in patch && patch.conclusion !== undefined) {
          next.conclusionOverridden = true
        }
        const suggested = suggestBondSppi(next)
        next = applyConclusion(next, suggested)
        if (next.hasEquityConversion === 'yes' && next.conclusion === 'PASS') {
          ElMessage.warning('含权益转换条款却判定「通过」：与 CAS22 基本借贷安排通常不符，请复核')
        }
        return next
      }),
    }
    persist()
  }

  function addBond() {
    if (opts.isReadonly.value) return
    store.value = {
      ...store.value,
      bondRows: reseq([...store.value.bondRows, emptyBond(store.value.bondRows.length + 1)]),
    }
    persist()
  }

  function removeBond(id: string) {
    if (opts.isReadonly.value || store.value.bondRows.length <= 1) return
    store.value = { ...store.value, bondRows: reseq(store.value.bondRows.filter((r) => r.id !== id)) }
    persist()
  }

  // ── wealth1 ──
  function updateWealth1(id: string, patch: Partial<G1WealthStep1Row>) {
    if (opts.isReadonly.value) return
    store.value = {
      ...store.value,
      wealthStep1: store.value.wealthStep1.map((r) => {
        if (r.id !== id) return r
        let next = { ...r, ...patch }
        if ('conclusion' in patch) next.conclusionOverridden = true
        return applyConclusion(next, suggestWealthStep1(next))
      }),
    }
    persist()
  }

  function addWealth1() {
    if (opts.isReadonly.value) return
    store.value = {
      ...store.value,
      wealthStep1: reseq([...store.value.wealthStep1, emptyWealth1()]),
    }
    persist()
  }

  function removeWealth1(id: string) {
    if (opts.isReadonly.value || store.value.wealthStep1.length <= 1) return
    store.value = {
      ...store.value,
      wealthStep1: reseq(store.value.wealthStep1.filter((r) => r.id !== id)),
    }
    persist()
  }

  // ── wealth2 ──
  function updateWealth2(id: string, patch: Partial<G1WealthStep2Row>) {
    if (opts.isReadonly.value) return
    store.value = {
      ...store.value,
      wealthStep2: store.value.wealthStep2.map((r) => {
        if (r.id !== id) return r
        let next = { ...r, ...patch }
        if ('conclusion' in patch) next.conclusionOverridden = true
        return applyConclusion(next, suggestWealthStep2(next))
      }),
    }
    persist()
  }

  function addWealth2() {
    if (opts.isReadonly.value) return
    store.value = {
      ...store.value,
      wealthStep2: reseq([...store.value.wealthStep2, emptyWealth2()]),
    }
    persist()
  }

  function removeWealth2(id: string) {
    if (opts.isReadonly.value || store.value.wealthStep2.length <= 1) return
    store.value = {
      ...store.value,
      wealthStep2: reseq(store.value.wealthStep2.filter((r) => r.id !== id)),
    }
    persist()
  }

  /** 将理财第一步中「需进一步分析」的浮动产品带入第二步 */
  function pullFloatingToStep2(): number {
    if (opts.isReadonly.value) return 0
    const need = store.value.wealthStep1.filter(
      (r) => r.floatingGuaranteed === 'yes' && r.investItem.trim(),
    )
    if (!need.length) {
      ElMessage.info('第一步中无「约定浮动收益」的项目')
      return 0
    }
    const existing = new Set(store.value.wealthStep2.map((r) => r.investItem.trim().toLowerCase()))
    const added: G1WealthStep2Row[] = []
    for (const r of need) {
      const key = r.investItem.trim().toLowerCase()
      if (existing.has(key)) continue
      added.push(
        applyConclusion(
          {
            ...emptyWealth2(),
            investItem: r.investItem,
            fixedRate: r.fixedRate,
          },
          '',
        ),
      )
      existing.add(key)
    }
    if (!added.length) {
      ElMessage.info('浮动项目已在第二步中')
      return 0
    }
    const keep = store.value.wealthStep2.filter((r) => r.investItem.trim())
    store.value = {
      ...store.value,
      wealthStep2: reseq([...keep, ...added]),
    }
    persist()
    ElMessage.success(`已带入 ${added.length} 项至浮动不现实分析`)
    return added.length
  }

  // ── perpetual / convertible / project / abs（通用模式）──
  function updatePerpetual(id: string, patch: Partial<G1PerpetualRow>) {
    if (opts.isReadonly.value) return
    store.value = {
      ...store.value,
      perpetualRows: store.value.perpetualRows.map((r) => {
        if (r.id !== id) return r
        let next = { ...r, ...patch }
        if ('conclusion' in patch) next.conclusionOverridden = true
        return applyConclusion(next, suggestPerpetual(next))
      }),
    }
    persist()
  }
  function addPerpetual() {
    if (opts.isReadonly.value) return
    store.value = { ...store.value, perpetualRows: reseq([...store.value.perpetualRows, emptyPerpetual()]) }
    persist()
  }
  function removePerpetual(id: string) {
    if (opts.isReadonly.value || store.value.perpetualRows.length <= 1) return
    store.value = { ...store.value, perpetualRows: reseq(store.value.perpetualRows.filter((r) => r.id !== id)) }
    persist()
  }

  function updateConvertible(id: string, patch: Partial<G1ConvertibleRow>) {
    if (opts.isReadonly.value) return
    store.value = {
      ...store.value,
      convertibleRows: store.value.convertibleRows.map((r) => {
        if (r.id !== id) return r
        let next = { ...r, ...patch }
        if ('conclusion' in patch) next.conclusionOverridden = true
        const suggested = suggestConvertible(next)
        next = applyConclusion(next, suggested)
        if (next.hasConversionFeature === 'yes' && next.conclusion === 'PASS') {
          ElMessage.warning('可转债含转股却判定「通过」：请按 CAS22 复核（通常应不通过）')
        }
        return next
      }),
    }
    persist()
  }
  function addConvertible() {
    if (opts.isReadonly.value) return
    store.value = { ...store.value, convertibleRows: reseq([...store.value.convertibleRows, emptyConvertible()]) }
    persist()
  }
  function removeConvertible(id: string) {
    if (opts.isReadonly.value || store.value.convertibleRows.length <= 1) return
    store.value = {
      ...store.value,
      convertibleRows: reseq(store.value.convertibleRows.filter((r) => r.id !== id)),
    }
    persist()
  }

  function updateProject(id: string, patch: Partial<G1ProjectRow>) {
    if (opts.isReadonly.value) return
    store.value = {
      ...store.value,
      projectRows: store.value.projectRows.map((r) => {
        if (r.id !== id) return r
        let next = { ...r, ...patch }
        if ('conclusion' in patch) next.conclusionOverridden = true
        return applyConclusion(next, suggestProject(next))
      }),
    }
    persist()
  }
  function addProject() {
    if (opts.isReadonly.value) return
    store.value = { ...store.value, projectRows: reseq([...store.value.projectRows, emptyProject()]) }
    persist()
  }
  function removeProject(id: string) {
    if (opts.isReadonly.value || store.value.projectRows.length <= 1) return
    store.value = { ...store.value, projectRows: reseq(store.value.projectRows.filter((r) => r.id !== id)) }
    persist()
  }

  function updateAbs(id: string, patch: Partial<G1AbsRow>) {
    if (opts.isReadonly.value) return
    store.value = {
      ...store.value,
      absRows: store.value.absRows.map((r) => {
        if (r.id !== id) return r
        let next = { ...r, ...patch }
        if ('conclusion' in patch) next.conclusionOverridden = true
        return applyConclusion(next, suggestAbs(next))
      }),
    }
    persist()
  }
  function addAbs() {
    if (opts.isReadonly.value) return
    store.value = { ...store.value, absRows: reseq([...store.value.absRows, emptyAbs()]) }
    persist()
  }
  function removeAbs(id: string) {
    if (opts.isReadonly.value || store.value.absRows.length <= 1) return
    store.value = { ...store.value, absRows: reseq(store.value.absRows.filter((r) => r.id !== id)) }
    persist()
  }

  return {
    store,
    activeSection,
    auditConclusion,
    stats,
    loadAll,
    persist,
    updateBond,
    addBond,
    removeBond,
    updateWealth1,
    addWealth1,
    removeWealth1,
    updateWealth2,
    addWealth2,
    removeWealth2,
    pullFloatingToStep2,
    updatePerpetual,
    addPerpetual,
    removePerpetual,
    updateConvertible,
    addConvertible,
    removeConvertible,
    updateProject,
    addProject,
    removeProject,
    updateAbs,
    addAbs,
    removeAbs,
    DATA_KEY,
  }
}
