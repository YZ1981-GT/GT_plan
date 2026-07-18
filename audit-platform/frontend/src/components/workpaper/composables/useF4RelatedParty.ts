/**
 * useF4RelatedParty — F4-6 应付账款关联方及交易检查表
 *
 * 源表逻辑：识别关联方 → 核对期初与借贷发生额 → 计算期末余额 →
 * 检查账龄、定价政策、交易性质和期后付款 → 评价披露与未识别关联方风险。
 */
import { computed, onBeforeUnmount, ref, watch, type ComputedRef, type Ref } from 'vue'
import { calcConcentration, calcCreditBalance, calcSubtotal, parseNum } from './useF4AccPayFormulaEngine'
import { computeF4DetailRow, migrateF4DetailRows } from './useF4Detail'
import { readRowJson, type ChecklistResponse } from './useF4FormData'

export const F4_RELATED_RELATIONSHIPS = [
  '实际控制人',
  '控股股东',
  '控股股东、实际控制人的附属企业',
  '持有5%以上股份的法人或其他组织',
  '联营企业',
  '合营企业',
  '董高监等关键管理人员',
  '其他关联方',
] as const

export const F4_RELATED_AGING_OPTIONS = ['1年以内', '1～2年', '2～3年', '3年以上'] as const
export const F4_RELATED_PRICING_OPTIONS = ['市场定价', '协议定价', '成本加成', '参考第三方价格', '政府定价', '其他'] as const

export interface RelatedPartyAPRow {
  rowId: string
  seq: number
  sourceRowId: string
  partyName: string
  relationship: string
  openingBalance: number
  currentDebit: number
  currentCredit: number
  closingBalance: number
  aging: string
  pricingPolicy: string
  transactionNature: string
  postPaymentAmount: number
  indexNo: string
  remark: string
  linked: boolean
  sourceClosingBalance: number
  reconciliationDifference: number
  concentration: number
  riskFlags: string[]
  riskLevel: 'none' | 'warning' | 'danger'
}

interface StoredRelatedPartyRow {
  rowId: string
  seq: number
  sourceRowId: string
  partyName: string
  relationship: string
  openingBalance: number
  currentDebit: number
  currentCredit: number
  aging: string
  pricingPolicy: string
  transactionNature: string
  postPaymentAmount: number
  indexNo: string
  remark: string
  sourceClosingBalance: number
}

export interface F4RelatedPartyCandidate {
  sourceRowId: string
  partyName: string
  relationship: string
  openingBalance: number
  currentDebit: number
  currentCredit: number
  sourceClosingBalance: number
  aging: string
  transactionNature: string
  postPaymentAmount: number
}

export interface UseF4RelatedPartyOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

const STORAGE_KEY = 'F4-6-rows'
const DETAIL_KEY = 'F4-2-rows'
const NOTE_KEY = 'F4-6-audit-note'
const CONCLUSION_KEY = 'F4-6-audit-conclusion'
const LEGACY_NOTE_KEY = 'F4-6-note'
const TOLERANCE = 0.005
const CONCENTRATION_THRESHOLD = 30

function generateRowId(): string {
  return `f4rp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

export function emptyF4RelatedPartyRow(seq: number): StoredRelatedPartyRow {
  return {
    rowId: generateRowId(),
    seq,
    sourceRowId: '',
    partyName: '',
    relationship: '',
    openingBalance: 0,
    currentDebit: 0,
    currentCredit: 0,
    aging: '',
    pricingPolicy: '',
    transactionNature: '',
    postPaymentAmount: 0,
    indexNo: '',
    remark: '',
    sourceClosingBalance: 0,
  }
}

function legacyRemark(raw: any): string {
  return [
    raw?.remark,
    raw?.settlementCycle ? `原结算周期：${raw.settlementCycle}` : '',
    raw?.isOverdue ? `原是否超期：${raw.isOverdue}` : '',
    raw?.fairness ? `原定价公允性：${raw.fairness}` : '',
    raw?.auditEvaluation ? `原审计评价：${raw.auditEvaluation}` : '',
  ].filter(Boolean).join('；')
}

function migrateRow(raw: any, index: number): StoredRelatedPartyRow {
  const base = emptyF4RelatedPartyRow(index + 1)
  const openingBalance = parseNum(raw?.openingBalance)
  const currentDebit = parseNum(raw?.currentDebit ?? raw?.currentDecrease ?? raw?.debit)
  const currentCredit = parseNum(raw?.currentCredit ?? raw?.currentIncrease ?? raw?.credit)
  return {
    ...base,
    rowId: String(raw?.rowId ?? raw?.id ?? generateRowId()),
    seq: Number(raw?.seq) || index + 1,
    sourceRowId: String(raw?.sourceRowId ?? ''),
    partyName: String(raw?.partyName ?? raw?.relatedPartyName ?? ''),
    relationship: String(raw?.relationship ?? ''),
    openingBalance,
    currentDebit,
    currentCredit,
    aging: String(raw?.aging ?? ''),
    pricingPolicy: String(raw?.pricingPolicy ?? ''),
    transactionNature: String(raw?.transactionNature ?? raw?.paymentNature ?? raw?.nature ?? ''),
    postPaymentAmount: parseNum(raw?.postPaymentAmount ?? raw?.subsequentPaymentAmount),
    indexNo: String(raw?.indexNo ?? raw?.indexRef ?? ''),
    remark: legacyRemark(raw),
    sourceClosingBalance: parseNum(
      raw?.sourceClosingBalance
      ?? raw?.closingBalance
      ?? calcCreditBalance(openingBalance, currentCredit, currentDebit),
    ),
  }
}

export function migrateF4RelatedPartyRows(
  value: string | null | undefined,
): StoredRelatedPartyRow[] {
  if (!value) return []
  try {
    const parsed = JSON.parse(value)
    if (!Array.isArray(parsed)) return []
    return parsed.map(migrateRow).map((row, index) => ({ ...row, seq: index + 1 }))
  } catch {
    return []
  }
}

function agingLabels(amounts: number[]): string {
  return F4_RELATED_AGING_OPTIONS
    .filter((_, index) => Math.abs(amounts[index]) >= TOLERANCE)
    .join('、')
}

/** 从F4-2提取已标识的关联方明细，并按实际债权人名称归集。 */
export function extractF4RelatedPartyCandidates(
  value: string | null | undefined,
): F4RelatedPartyCandidate[] {
  const grouped = new Map<string, {
    rowIds: string[]
    partyName: string
    relationships: Set<string>
    openingBalance: number
    currentDebit: number
    currentCredit: number
    sourceClosingBalance: number
    aging: number[]
    natures: Set<string>
    postPaymentAmount: number
  }>()

  for (const row of migrateF4DetailRows(value).map(computeF4DetailRow)) {
    const partyName = row.creditor.trim()
    const relationship = row.relatedPartyType.trim()
    if (!partyName || !relationship || relationship === '非关联方') continue
    const key = partyName.toLocaleLowerCase('zh-CN')
    const target = grouped.get(key) ?? {
      rowIds: [],
      partyName,
      relationships: new Set<string>(),
      openingBalance: 0,
      currentDebit: 0,
      currentCredit: 0,
      sourceClosingBalance: 0,
      aging: [0, 0, 0, 0],
      natures: new Set<string>(),
      postPaymentAmount: 0,
    }
    target.rowIds.push(row.rowId)
    target.relationships.add(relationship)
    target.openingBalance += row.openingAdjusted
    target.currentDebit += row.currentDebit
    target.currentCredit += row.currentCredit
    target.sourceClosingBalance += row.closingAdjusted
    target.aging[0] += row.auditedAgingLt1
    target.aging[1] += row.auditedAging1to2
    target.aging[2] += row.auditedAging2to3
    target.aging[3] += row.auditedAgingGt3
    if (row.paymentNature) target.natures.add(row.paymentNature)
    target.postPaymentAmount += row.subsequentPayment
    grouped.set(key, target)
  }

  return [...grouped.values()]
    .sort((a, b) =>
      Math.abs(b.sourceClosingBalance) - Math.abs(a.sourceClosingBalance)
      || a.partyName.localeCompare(b.partyName, 'zh-CN'),
    )
    .map((row) => ({
      sourceRowId: row.rowIds.sort().join('|'),
      partyName: row.partyName,
      relationship: [...row.relationships].join('、'),
      openingBalance: row.openingBalance,
      currentDebit: row.currentDebit,
      currentCredit: row.currentCredit,
      sourceClosingBalance: row.sourceClosingBalance,
      aging: agingLabels(row.aging),
      transactionNature: [...row.natures].join('、'),
      postPaymentAmount: row.postPaymentAmount,
    }))
}

function isBlankRow(row: StoredRelatedPartyRow): boolean {
  return !row.partyName && !row.relationship && !row.openingBalance && !row.currentDebit
    && !row.currentCredit && !row.aging && !row.pricingPolicy && !row.transactionNature
    && !row.postPaymentAmount && !row.indexNo && !row.remark && !row.sourceRowId
}

function computeRow(
  stored: StoredRelatedPartyRow,
  totalClosing: number,
  source?: F4RelatedPartyCandidate,
): RelatedPartyAPRow {
  const partyName = source?.partyName ?? stored.partyName
  const relationship = stored.relationship || source?.relationship || ''
  const openingBalance = source?.openingBalance ?? stored.openingBalance
  const currentDebit = source?.currentDebit ?? stored.currentDebit
  const currentCredit = source?.currentCredit ?? stored.currentCredit
  const aging = source?.aging ?? stored.aging
  const transactionNature = stored.transactionNature || source?.transactionNature || ''
  const postPaymentAmount = source?.postPaymentAmount ?? stored.postPaymentAmount
  // 联动行直接采用 F4-2 审定期末；勿用「期初审定+贷−借」去比审定数（AJE/RJE 会导致系统性误报）
  const rollForwardClosing = calcCreditBalance(openingBalance, currentCredit, currentDebit)
  const sourceClosingBalance = source?.sourceClosingBalance
    ?? (stored.sourceRowId ? stored.sourceClosingBalance : rollForwardClosing)
  const closingBalance = source ? sourceClosingBalance : rollForwardClosing
  const reconciliationDifference = closingBalance - sourceClosingBalance
  const concentration = calcConcentration(closingBalance, totalClosing)
  const riskFlags: string[] = []

  if (partyName) {
    if (!relationship) riskFlags.push('关联关系待核实')
    else if (relationship === '合并范围内关联方' || relationship === '合并范围外关联方') {
      riskFlags.push('关联关系需细化')
    }
    if (!stored.pricingPolicy) riskFlags.push('定价政策未说明')
    if (!transactionNature) riskFlags.push('交易性质未说明')
    if (!stored.indexNo) riskFlags.push('索引号待补')
  }
  if (Math.abs(reconciliationDifference) >= TOLERANCE && !source && stored.sourceRowId) {
    riskFlags.push('与F4-2审定数不一致')
  }
  if (closingBalance < -TOLERANCE) riskFlags.push('期末余额为负')
  if (postPaymentAmount > Math.max(0, closingBalance) + TOLERANCE) riskFlags.push('期后付款超过期末余额')
  if ((aging.includes('2～3年') || aging.includes('3年以上')) && postPaymentAmount < TOLERANCE) {
    riskFlags.push('长期账龄且无期后付款')
  }
  if (concentration > CONCENTRATION_THRESHOLD) riskFlags.push('关联方余额集中度较高')

  const riskLevel: RelatedPartyAPRow['riskLevel'] = riskFlags.some((flag) =>
    ['与F4-2审定数不一致', '期末余额为负', '期后付款超过期末余额'].includes(flag),
  ) ? 'danger' : riskFlags.length ? 'warning' : 'none'

  return {
    ...stored,
    partyName,
    relationship,
    openingBalance,
    currentDebit,
    currentCredit,
    closingBalance,
    aging,
    transactionNature,
    postPaymentAmount,
    linked: !!source,
    sourceClosingBalance,
    reconciliationDifference,
    concentration,
    riskFlags,
    riskLevel,
  }
}

export function useF4RelatedParty(options: UseF4RelatedPartyOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let lastPersistedJson = ''

  const storedData = ref<StoredRelatedPartyRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  function loadRows(): void {
    storedData.value = migrateF4RelatedPartyRows(readRowJson(allResponses.value.get(STORAGE_KEY)))
    if (!storedData.value.length) storedData.value = [emptyF4RelatedPartyRow(1)]
  }

  watch(
    () => readRowJson(allResponses.value.get(STORAGE_KEY)),
    (raw) => {
      if (raw && (raw === lastPersistedJson || raw === JSON.stringify(storedData.value))) return
      loadRows()
    },
    { immediate: true },
  )
  watch(
    () => [
      allResponses.value.get(NOTE_KEY)?.remark,
      allResponses.value.get(CONCLUSION_KEY)?.remark,
      allResponses.value.get(LEGACY_NOTE_KEY)?.remark,
    ],
    ([note, conclusion, legacy]) => {
      auditNote.value = note || ''
      auditConclusion.value = conclusion || legacy || ''
    },
    { immediate: true },
  )

  const detailCandidates = computed(() =>
    extractF4RelatedPartyCandidates(readRowJson(allResponses.value.get(DETAIL_KEY))),
  )
  watch(
    () => readRowJson(allResponses.value.get(DETAIL_KEY)),
    () => {
      if (!readonly.value && storedData.value.some((row) => row.sourceRowId)) persistRows()
    },
  )

  function sourceFor(row: StoredRelatedPartyRow): F4RelatedPartyCandidate | undefined {
    return row.sourceRowId
      ? detailCandidates.value.find((source) => source.sourceRowId === row.sourceRowId)
      : undefined
  }

  const totalClosing = computed(() => calcSubtotal(storedData.value.map((stored) => {
    const source = sourceFor(stored)
    return calcCreditBalance(
      source?.openingBalance ?? stored.openingBalance,
      source?.currentCredit ?? stored.currentCredit,
      source?.currentDebit ?? stored.currentDebit,
    )
  })))

  const rows: ComputedRef<RelatedPartyAPRow[]> = computed(() =>
    storedData.value.map((stored) => computeRow(stored, totalClosing.value, sourceFor(stored))),
  )
  const filledCount = computed(() => rows.value.filter((row) =>
    row.partyName || Math.abs(row.closingBalance) >= TOLERANCE,
  ).length)
  const pendingSyncCount = computed(() => {
    const linked = new Set(storedData.value.map((row) => row.sourceRowId).filter(Boolean))
    return detailCandidates.value.filter((source) => !linked.has(source.sourceRowId)).length
  })

  const summary = computed(() => ({
    count: filledCount.value,
    openingTotal: calcSubtotal(rows.value.map((row) => row.openingBalance)),
    debitTotal: calcSubtotal(rows.value.map((row) => row.currentDebit)),
    creditTotal: calcSubtotal(rows.value.map((row) => row.currentCredit)),
    closingTotal: totalClosing.value,
    postPaymentTotal: calcSubtotal(rows.value.map((row) => row.postPaymentAmount)),
    sourceClosingTotal: calcSubtotal(rows.value.map((row) => row.sourceClosingBalance)),
    reconciliationDifference: calcSubtotal(rows.value.map((row) => row.reconciliationDifference)),
    highRiskCount: rows.value.filter((row) => row.riskLevel === 'danger').length,
    missingPricingCount: rows.value.filter((row) => row.partyName && !row.pricingPolicy).length,
  }))

  function syncFromDetail(): number {
    if (readonly.value) return 0
    const linked = new Set(storedData.value.map((row) => row.sourceRowId).filter(Boolean))
    const pending = detailCandidates.value.filter((source) => !linked.has(source.sourceRowId))
    if (pending.length && storedData.value.length === 1 && isBlankRow(storedData.value[0])) {
      storedData.value = []
    }
    for (const source of pending) {
      storedData.value.push({
        ...emptyF4RelatedPartyRow(storedData.value.length + 1),
        sourceRowId: source.sourceRowId,
        partyName: source.partyName,
        relationship: source.relationship,
        openingBalance: source.openingBalance,
        currentDebit: source.currentDebit,
        currentCredit: source.currentCredit,
        aging: source.aging,
        transactionNature: source.transactionNature,
        postPaymentAmount: source.postPaymentAmount,
        sourceClosingBalance: source.sourceClosingBalance,
      })
    }
    if (pending.length) persistRows()
    return pending.length
  }

  function addRow(): void {
    if (readonly.value) return
    storedData.value.push(emptyF4RelatedPartyRow(storedData.value.length + 1))
    persistRows()
  }

  function removeRow(rowId: string): void {
    if (readonly.value) return
    const index = storedData.value.findIndex((row) => row.rowId === rowId)
    if (index === -1) return
    storedData.value.splice(index, 1)
    if (!storedData.value.length) storedData.value.push(emptyF4RelatedPartyRow(1))
    storedData.value.forEach((row, i) => { row.seq = i + 1 })
    persistRows()
  }

  function updateCell(rowId: string, field: string, value: unknown): void {
    if (readonly.value) return
    const row = storedData.value.find((item) => item.rowId === rowId)
    if (!row) return
    const numericFields = new Set([
      'openingBalance', 'currentDebit', 'currentCredit', 'postPaymentAmount', 'sourceClosingBalance',
    ])
    ;(row as any)[field] = numericFields.has(field)
      ? parseNum(value as string | number | null | undefined)
      : String(value ?? '')
    persistRows()
  }

  function setText(key: string, value: string): void {
    allResponses.value.set(key, { item_id: key, conclusion: null, remark: value })
    debounceSave()
  }

  function saveAuditNote(value: string): void {
    if (readonly.value) return
    auditNote.value = value
    setText(NOTE_KEY, value)
  }

  function saveAuditConclusion(value: string): void {
    if (readonly.value) return
    auditConclusion.value = value
    setText(CONCLUSION_KEY, value)
  }

  function persistRows(): void {
    // 导出接口读取持久化JSON，因此同步保存源表字段及公式期末余额快照。
    const serialized = storedData.value.map((stored) => {
      const source = sourceFor(stored)
      const openingBalance = source?.openingBalance ?? stored.openingBalance
      const currentDebit = source?.currentDebit ?? stored.currentDebit
      const currentCredit = source?.currentCredit ?? stored.currentCredit
      return {
        ...stored,
        partyName: source?.partyName ?? stored.partyName,
        relationship: stored.relationship || source?.relationship || '',
        openingBalance,
        currentDebit,
        currentCredit,
        closingBalance: calcCreditBalance(openingBalance, currentCredit, currentDebit),
        aging: source?.aging ?? stored.aging,
        transactionNature: stored.transactionNature || source?.transactionNature || '',
        postPaymentAmount: source?.postPaymentAmount ?? stored.postPaymentAmount,
        sourceClosingBalance: source?.sourceClosingBalance ?? stored.sourceClosingBalance,
      }
    })
    lastPersistedJson = JSON.stringify(serialized)
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: lastPersistedJson,
    })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 1200)
  }

  function flushSave(): void {
    const items = [STORAGE_KEY, NOTE_KEY, CONCLUSION_KEY]
      .map((key) => allResponses.value.get(key))
      .filter(Boolean)
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items } }))
    }
  }

  function rowClassName({ row }: { row: RelatedPartyAPRow }): string {
    if (row.riskLevel === 'danger') return 'related-risk-danger'
    if (row.riskLevel === 'warning') return 'related-risk-warning'
    return ''
  }

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    rows,
    summary,
    totalClosing,
    filledCount,
    pendingSyncCount,
    auditNote,
    auditConclusion,
    loadRows,
    syncFromDetail,
    addRow,
    removeRow,
    updateCell,
    saveAuditNote,
    saveAuditConclusion,
    rowClassName,
  }
}

export default useF4RelatedParty
