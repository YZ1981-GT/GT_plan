/**
 * useI1TitleCheck — I1-8 无形资产权属检查
 *
 * 对齐致同 Excel「无形资产权属检查表I1-8」：
 *   权证记载（编号/权利人/登记日/权利起止/复印件索引）
 *   财务账面（原值/累计摊销/减值准备/净值=原值−摊销−减值）  ← 源表误写「累计折旧」，按 CAS6 用摊销
 *   抵押情况（是否抵押受限/抵押价值/抵押性质）
 *
 * 增强：从 I1-2 带入账面；到期预警；权利人一致性；编制校验；结论草稿
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { calcNetValue } from './useI1FormulaEngine'

export const I1_TITLE_TYPE_OPTIONS = [
  '专利权',
  '商标权',
  '著作权',
  '土地使用权',
  '软件著作权',
  '特许经营权',
  '探矿权/采矿权',
  '数据资源',
  '其他',
] as const

const ITEM_ID_ROWS = 'I1-8-rows'
const ITEM_ID_NOTE = 'I1-8-audit-note'
const ITEM_ID_CONCLUSION = 'I1-8-conclusion'
const ITEM_ID_DETAIL = 'I1-2-rows'

const EXPIRY_WARN_DAYS = 365
const SYNC_TOLERANCE = 0.01

export interface I1TitleCheckRow {
  rowId: string
  /** 资产名称 */
  name: string
  /** 类型（筛选用，Excel 未强制） */
  type: string
  /** 权证编号 */
  certNo: string
  /** 权利人名称 */
  rightHolder: string
  /** 登记日期 */
  registrationDate: string
  /** 权利起日 */
  rightStartDate: string
  /** 权利止日（有效期） */
  rightEndDate: string
  /** 权证复印件索引 */
  copyIndex: string
  /** 账面原值 G */
  cost: number
  /** 累计摊销 H（源表写折旧，按准则用摊销） */
  accAmort: number
  /** 减值准备 I */
  impairment: number
  /** 净值 J = G−H−I（公式） */
  netBookValue: number
  /** 是否抵押受限 */
  mortgageRestricted: 'Y' | 'N' | ''
  /** 抵押价值 */
  mortgageValue: number
  /** 抵押性质 */
  mortgageNature: string
  /** 权利人是否与被审计单位一致 */
  holderConsistent: 'Y' | 'N' | ''
  /** 核验方式 */
  verifyMethod: string
  /** 核验日期 */
  verifyDate: string
  /** 行结论 */
  conclusion: string
  /** 备注 */
  remark: string
  /** 来源 I1-2 */
  sourceDetailRowId?: string
  /** 兼容旧字段 */
  bookValue?: number
  certValue?: number
  validUntil?: string
  pledgeStatus?: string
  registrationStatus?: string
  isConsistent?: string
  diffDescription?: string
  renewalStatus?: string
  registrationAuthority?: string
}

export interface I1TitlePrepValidation {
  ok: boolean
  messages: string[]
}

export type I1TitleExpiryFlag = 'ok' | 'near' | 'expired' | 'none'

function _getNum(v: any): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _genId(): string {
  return `i1t8-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function _safeParse(raw: unknown): any[] {
  if (raw == null) return []
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string') {
    try {
      const p = JSON.parse(raw)
      return Array.isArray(p) ? p : []
    } catch {
      return []
    }
  }
  return []
}

function _yn(v: any): 'Y' | 'N' | '' {
  const s = String(v ?? '').trim().toUpperCase()
  if (['Y', '是', '√', 'TRUE', '1', '已抵押', '受限'].includes(s)) return 'Y'
  if (['N', '否', '×', 'FALSE', '0', '无'].includes(s)) return 'N'
  return ''
}

/** 净值公式（Excel J=G−H−I） */
export function calcI1TitleNetBook(cost: number, accAmort: number, impairment: number): number {
  return calcNetValue(_getNum(cost), _getNum(accAmort), _getNum(impairment))
}

/** 到期预警：无日期 none；已过期 expired；一年内 near；否则 ok */
export function classifyI1TitleExpiry(rightEndDate: string, asOf = new Date()): I1TitleExpiryFlag {
  if (!rightEndDate?.trim()) return 'none'
  const end = new Date(rightEndDate)
  if (Number.isNaN(end.getTime())) return 'none'
  const ms = end.getTime() - asOf.getTime()
  if (ms < 0) return 'expired'
  if (ms <= EXPIRY_WARN_DAYS * 86400000) return 'near'
  return 'ok'
}

export function recomputeI1TitleRow(row: I1TitleCheckRow): I1TitleCheckRow {
  const cost = _getNum(row.cost)
  const accAmort = _getNum(row.accAmort)
  const impairment = _getNum(row.impairment)
  const netBookValue = calcI1TitleNetBook(cost, accAmort, impairment)
  const mortgageRestricted = _yn(row.mortgageRestricted) || (
    row.pledgeStatus && row.pledgeStatus !== '无' ? 'Y' : row.mortgageRestricted
  )
  return {
    ...row,
    cost,
    accAmort,
    impairment,
    netBookValue,
    mortgageRestricted: _yn(mortgageRestricted) as 'Y' | 'N' | '',
    mortgageValue: _getNum(row.mortgageValue),
    holderConsistent: _yn(row.holderConsistent) as 'Y' | 'N' | '',
  }
}

export function emptyI1TitleRow(partial?: Partial<I1TitleCheckRow>): I1TitleCheckRow {
  return recomputeI1TitleRow({
    rowId: partial?.rowId ?? _genId(),
    name: '',
    type: '',
    certNo: '',
    rightHolder: '',
    registrationDate: '',
    rightStartDate: '',
    rightEndDate: '',
    copyIndex: '',
    cost: 0,
    accAmort: 0,
    impairment: 0,
    netBookValue: 0,
    mortgageRestricted: '',
    mortgageValue: 0,
    mortgageNature: '',
    holderConsistent: '',
    verifyMethod: '',
    verifyDate: '',
    conclusion: '',
    remark: '',
    ...partial,
  })
}

/** 旧数据兼容归一化 */
export function normalizeI1TitleRow(raw: any): I1TitleCheckRow {
  const cost = _getNum(raw.cost) || _getNum(raw.bookValue) || 0
  const accAmort = _getNum(raw.accAmort)
  const impairment = _getNum(raw.impairment) || _getNum(raw.impairmentProvision)
  const rightEndDate = String(raw.rightEndDate || raw.validUntil || '')
  let mortgageRestricted = _yn(raw.mortgageRestricted)
  if (!mortgageRestricted && raw.pledgeStatus) {
    mortgageRestricted = raw.pledgeStatus === '无' || raw.pledgeStatus === '' ? 'N' : 'Y'
  }
  const mortgageValue = _getNum(raw.mortgageValue) || _getNum(raw.pledgeAmount)
  let mortgageNature = String(raw.mortgageNature || '')
  if (!mortgageNature && raw.pledgeStatus && raw.pledgeStatus !== '无') {
    mortgageNature = String(raw.pledgeStatus)
  }

  return recomputeI1TitleRow({
    rowId: raw.rowId ?? _genId(),
    name: String(raw.name ?? ''),
    type: String(raw.type ?? ''),
    certNo: String(raw.certNo ?? ''),
    rightHolder: String(raw.rightHolder ?? ''),
    registrationDate: String(raw.registrationDate ?? ''),
    rightStartDate: String(raw.rightStartDate ?? ''),
    rightEndDate,
    copyIndex: String(raw.copyIndex ?? ''),
    cost,
    accAmort,
    impairment,
    netBookValue: 0,
    mortgageRestricted,
    mortgageValue,
    mortgageNature,
    holderConsistent: _yn(raw.holderConsistent) || _yn(raw.isConsistent === '是' ? 'Y' : raw.isConsistent === '否' ? 'N' : ''),
    verifyMethod: String(raw.verifyMethod ?? ''),
    verifyDate: String(raw.verifyDate ?? ''),
    conclusion: String(raw.conclusion ?? ''),
    remark: String(raw.remark || raw.diffDescription || ''),
    sourceDetailRowId: raw.sourceDetailRowId ? String(raw.sourceDetailRowId) : undefined,
  })
}

export function validateI1TitlePrep(rows: I1TitleCheckRow[]): I1TitlePrepValidation {
  const messages: string[] = []
  for (const r of rows) {
    if (!r.name?.trim() && r.cost <= 0) continue
    const label = r.name || r.rowId
    if (!r.certNo?.trim()) {
      messages.push(`「${label}」未填写权证编号`)
    }
    if (!r.rightHolder?.trim()) {
      messages.push(`「${label}」未填写权利人`)
    }
    if (r.holderConsistent === 'N' && !r.remark?.trim()) {
      messages.push(`「${label}」权利人与被审计单位不一致，请在备注说明`)
    }
    const exp = classifyI1TitleExpiry(r.rightEndDate)
    if (exp === 'expired' && !['需补办', '有差异', '已注销'].includes(r.conclusion)) {
      messages.push(`「${label}」权利已到期，请关注续展并更新结论`)
    }
    if (r.mortgageRestricted === 'Y') {
      if (r.mortgageValue <= 0) messages.push(`「${label}」已抵押受限但未填抵押价值`)
      if (!r.mortgageNature?.trim()) messages.push(`「${label}」已抵押受限但未填抵押性质`)
    }
    if (r.cost > 0 && Math.abs(r.netBookValue - calcI1TitleNetBook(r.cost, r.accAmort, r.impairment)) > SYNC_TOLERANCE) {
      messages.push(`「${label}」净值勾稽异常`)
    }
  }
  return { ok: messages.length === 0, messages }
}

export function seedI1TitleFromDetail(detailRows: any[]): I1TitleCheckRow[] {
  const out: I1TitleCheckRow[] = []
  for (const r of detailRows ?? []) {
    const name = String(r?.name || '').trim()
    if (!name) continue
    const cost = _getNum(r.costEnd ?? r.cost)
    const accAmort = _getNum(r.accAmortEnd ?? r.accAmort)
    const impairment = _getNum(r.impairmentEnd ?? r.impairmentProvision ?? r.impairment)
    out.push(emptyI1TitleRow({
      name,
      type: String(r.category || r.type || '').trim(),
      cost,
      accAmort,
      impairment,
      sourceDetailRowId: String(r.rowId ?? ''),
      remark: '自I1-2带入账面',
    }))
  }
  return out
}

export function buildI1TitleConclusionDraft(rows: I1TitleCheckRow[]): string {
  const total = rows.length
  const checked = rows.filter((r) => r.certNo || r.verifyMethod).length
  const holderDiff = rows.filter((r) => r.holderConsistent === 'N').length
  const mortgaged = rows.filter((r) => r.mortgageRestricted === 'Y').length
  const expired = rows.filter((r) => classifyI1TitleExpiry(r.rightEndDate) === 'expired').length
  const near = rows.filter((r) => classifyI1TitleExpiry(r.rightEndDate) === 'near').length
  const mortgageAmt = rows
    .filter((r) => r.mortgageRestricted === 'Y')
    .reduce((s, r) => s + r.mortgageValue, 0)

  return [
    `经抽查/逐项核查无形资产权属证书（共 ${total} 项，已填权证 ${checked} 项）：`,
    `（1）权利人与被审计单位不一致 ${holderDiff} 项${holderDiff ? '（详见备注）' : ''}；`,
    `（2）抵押/受限 ${mortgaged} 项，抵押价值合计 ${mortgageAmt.toFixed(2)} 元；`,
    `（3）权利到期 ${expired} 项、一年到期（≤1年） ${near} 项；`,
    `（4）账面净值按原值−累计摊销−减值准备勾稽；`,
    `（5）权属在重大方面${holderDiff || expired ? '尚需关注上述事项' : '未见异常'}。`,
  ].join('')
}

export function useI1TitleCheck(options: {
  allResponses: Ref<Map<string, any>>
  onSave?: (itemId: string, value: any) => void
}) {
  const rows = ref<I1TitleCheckRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  const filterType = ref('')
  const entityName = ref('')

  function _load() {
    const map = options.allResponses.value
    const raw = map.get(ITEM_ID_ROWS)
    const parsed = _safeParse(raw?.remark ?? raw?.conclusion ?? raw)
    rows.value = parsed.map(normalizeI1TitleRow)

    const n = map.get(ITEM_ID_NOTE)
    auditNote.value = String(n?.remark ?? n?.conclusion ?? '')
    const c = map.get(ITEM_ID_CONCLUSION)
    auditConclusion.value = String(c?.remark ?? c?.conclusion ?? '')
  }

  function _persistRows() {
    options.onSave?.(ITEM_ID_ROWS, rows.value)
  }

  watch(options.allResponses, () => _load(), { immediate: true, deep: true })

  const filteredRows: ComputedRef<I1TitleCheckRow[]> = computed(() => {
    if (!filterType.value) return rows.value
    return rows.value.filter((r) => r.type === filterType.value)
  })

  const totalCost = computed(() => rows.value.reduce((s, r) => s + r.cost, 0))
  const totalAccAmort = computed(() => rows.value.reduce((s, r) => s + r.accAmort, 0))
  const totalImpairment = computed(() => rows.value.reduce((s, r) => s + r.impairment, 0))
  const totalNet = computed(() => rows.value.reduce((s, r) => s + r.netBookValue, 0))
  const totalMortgage = computed(() =>
    rows.value.filter((r) => r.mortgageRestricted === 'Y').reduce((s, r) => s + r.mortgageValue, 0),
  )
  const mortgagedCount = computed(() => rows.value.filter((r) => r.mortgageRestricted === 'Y').length)
  const expiredCount = computed(() =>
    rows.value.filter((r) => classifyI1TitleExpiry(r.rightEndDate) === 'expired').length,
  )
  const nearExpiryCount = computed(() =>
    rows.value.filter((r) => classifyI1TitleExpiry(r.rightEndDate) === 'near').length,
  )
  const holderMismatchCount = computed(() =>
    rows.value.filter((r) => r.holderConsistent === 'N').length,
  )

  const prepValidation = computed(() => validateI1TitlePrep(rows.value))

  const groupStats = computed(() => {
    const map = new Map<string, { count: number; netTotal: number }>()
    for (const r of rows.value) {
      const t = r.type || '未分类'
      const cur = map.get(t) || { count: 0, netTotal: 0 }
      cur.count++
      cur.netTotal += r.netBookValue
      map.set(t, cur)
    }
    return [...map.entries()].map(([type, s]) => ({ type, ...s }))
  })

  function addRow(name: string): I1TitleCheckRow {
    const row = emptyI1TitleRow({ name: name.trim() })
    rows.value.push(row)
    _persistRows()
    return row
  }

  function removeRow(rowId: string): void {
    const i = rows.value.findIndex((r) => r.rowId === rowId)
    if (i < 0) return
    rows.value.splice(i, 1)
    _persistRows()
  }

  function updateField(rowId: string, field: keyof I1TitleCheckRow, value: any): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row) return
    ;(row as any)[field] = value
    Object.assign(row, recomputeI1TitleRow(row))
    // 权利人与实体名自动勾稽提示
    if (field === 'rightHolder' && entityName.value) {
      const holder = String(value || '').trim()
      const ent = entityName.value.trim()
      if (holder && ent) {
        row.holderConsistent = holder === ent || holder.includes(ent) || ent.includes(holder) ? 'Y' : 'N'
      }
    }
    _persistRows()
  }

  function persist(): void {
    _persistRows()
  }

  function saveNote(text: string): void {
    auditNote.value = text
    options.onSave?.(ITEM_ID_NOTE, text)
  }

  function saveConclusion(text: string): void {
    auditConclusion.value = text
    options.onSave?.(ITEM_ID_CONCLUSION, text)
  }

  function fillConclusionDraft(): string {
    const draft = buildI1TitleConclusionDraft(rows.value)
    auditConclusion.value = draft
    saveConclusion(draft)
    return draft
  }

  function seedFromDetail(): { ok: boolean; message: string; count: number } {
    const raw = options.allResponses.value.get(ITEM_ID_DETAIL)
    const detail = _safeParse(raw?.remark ?? raw?.conclusion ?? raw)
    const seeded = seedI1TitleFromDetail(detail)
    if (!seeded.length) {
      return { ok: false, count: 0, message: 'I1-2 无明细可带入' }
    }
    const byName = new Map(rows.value.map((r) => [r.name.trim(), r]))
    let count = 0
    for (const s of seeded) {
      const prev = byName.get(s.name.trim())
      if (prev) {
        prev.cost = s.cost
        prev.accAmort = s.accAmort
        prev.impairment = s.impairment
        prev.type = s.type || prev.type
        prev.sourceDetailRowId = s.sourceDetailRowId
        Object.assign(prev, recomputeI1TitleRow(prev))
        count++
      } else {
        rows.value.push(s)
        byName.set(s.name.trim(), s)
        count++
      }
    }
    if (count) _persistRows()
    return { ok: count > 0, count, message: `已从 I1-2 带入/更新 ${count} 行账面` }
  }

  function applyEntityNameCheck(name: string): number {
    entityName.value = name.trim()
    if (!entityName.value) return 0
    let n = 0
    for (const row of rows.value) {
      if (!row.rightHolder?.trim()) continue
      const holder = row.rightHolder.trim()
      const ent = entityName.value
      const ok = holder === ent || holder.includes(ent) || ent.includes(holder)
      const next: 'Y' | 'N' = ok ? 'Y' : 'N'
      if (row.holderConsistent !== next) {
        row.holderConsistent = next
        n++
      }
    }
    if (n) _persistRows()
    return n
  }

  return {
    rows,
    filteredRows,
    filterType,
    entityName,
    auditNote,
    auditConclusion,
    totalCost,
    totalAccAmort,
    totalImpairment,
    totalNet,
    totalMortgage,
    mortgagedCount,
    expiredCount,
    nearExpiryCount,
    holderMismatchCount,
    prepValidation,
    groupStats,
    addRow,
    removeRow,
    updateField,
    persist,
    saveNote,
    saveConclusion,
    fillConclusionDraft,
    seedFromDetail,
    applyEntityNameCheck,
    classifyExpiry: classifyI1TitleExpiry,
  }
}

export default useI1TitleCheck
