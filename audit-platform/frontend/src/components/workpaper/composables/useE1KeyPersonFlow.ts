/**
 * useE1KeyPersonFlow — E1-32 董监高关键岗位及其他关联方资金流水核查
 *
 * - 按人建表（姓名/职位）
 * - 18 列流水：客观列 OCR/导入 + 背景/三维判定/异常
 * - 收入支出合计 + 说明/结论
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { UseE1BaseOptions, ChecklistItem } from './useE1Adjudication'
import { parseNum } from './useE1FormulaEngine'

export const E1_KEYPERSON_FLOW_PACK_KEY = 'E1-keyperson-flow-pack'
export const E1_KEYPERSON_FLOW_NOTE_KEY = 'E1-keyperson-flow-audit-note'
export const E1_KEYPERSON_FLOW_CONCLUSION_KEY = 'E1-keyperson-flow-audit-conclusion'
export const E1_IPO_APPLICABLE_KEY = 'E1-ipo-applicable'
const LEGACY_ROWS_KEY = 'E1-ipo-E1-32-rows'
const E1_31_PACK_KEY = 'E1-bank-flow-pack'

export type YesNo = '是' | '否' | ''

export interface KeyPersonTxnRow {
  id: string
  accountNo: string
  bank: string
  cardNo: string
  cardType: string
  transDate: string
  currency: string
  summary: string
  income: number
  expense: number
  counterpartyName: string
  counterpartyAccount: string
  transBackground: string
  isAuditee: YesNo
  isCustomerOrSupplier: YesNo
  isCommonCounterparty: YesNo
  otherAnomaly: string
  remark: string
  source: string
}

export interface KeyPersonBlock {
  id: string
  name: string
  position: string
  rows: KeyPersonTxnRow[]
}

export interface KeyPersonFlowPack {
  persons: KeyPersonBlock[]
  activePersonId: string
  /** OCR 回填审计轨迹（最近若干次） */
  ocrJobs?: OcrJobMeta[]
}

export interface OcrJobMeta {
  id: string
  fileName: string
  attachmentId?: string
  at: string
  lineCount: number
  skippedCount: number
  confidence: number
  bank?: string
  accountNo?: string
  personName?: string
}

export type E31SeedMode = 'append' | 'replace'

/** 从 E1-31 pack 抽取可疑往来（纯函数） */
export function collectE31SuspectCandidates(pack31: any): {
  candidates: Array<Partial<KeyPersonTxnRow>>
  third: number
  inconsistent: number
  largeUnmatched: number
} {
  if (!pack31 || typeof pack31 !== 'object') {
    return { candidates: [], third: 0, inconsistent: 0, largeUnmatched: 0 }
  }
  const thr = Math.max(
    parseNum(pack31.largeThresholdBookToBank),
    parseNum(pack31.largeThresholdBankToBook),
    0,
  )
  const candidates: Array<Partial<KeyPersonTxnRow>> = []
  const seen = new Set<string>()
  let third = 0
  let inconsistent = 0
  let largeUnmatched = 0

  const push = (partial: Partial<KeyPersonTxnRow>) => {
    const key = [
      partial.transDate || '',
      partial.counterpartyName || '',
      partial.income || 0,
      partial.expense || 0,
    ].join('|')
    if (seen.has(key)) return
    seen.add(key)
    candidates.push(partial)
  }

  const scans = [
    ...(Array.isArray(pack31.bookToBank) ? pack31.bookToBank : []),
    ...(Array.isArray(pack31.bankToBook) ? pack31.bankToBook : []),
  ]
  for (const r of scans) {
    if (!r || typeof r !== 'object') continue
    const isThird = r.thirdParty === '是'
    const isInconsistent = r.infoConsistent === '否' || r.infoConsistent === ''
    const debit = parseNum(r.debit)
    const credit = parseNum(r.credit)
    const stmtAmt = parseNum(r.stmtAmount)
    const amt = Math.max(debit, credit, stmtAmt)
    const isLargeUnmatched = isInconsistent && thr > 0 && amt >= thr
    if (!isThird && !isLargeUnmatched && r.infoConsistent !== '否') continue
    if (isThird) third += 1
    if (r.infoConsistent === '否') inconsistent += 1
    if (isLargeUnmatched) largeUnmatched += 1

    let income = debit
    let expense = credit
    if (!income && !expense && stmtAmt) income = stmtAmt
    push({
      transDate: String(r.sDate || r.vDate || ''),
      summary: String(r.summary || r.businessContent || ''),
      counterpartyName: String(r.payerPayee || r.counterparty || ''),
      income,
      expense,
      transBackground: isThird
        ? '来自 E1-31：标注第三方回款/付款'
        : '来自 E1-31：信息不一致或大额未匹配',
      isAuditee: '',
      isCustomerOrSupplier: '',
      isCommonCounterparty: isThird ? '是' : '',
      otherAnomaly: isThird ? '第三方回款/付款' : (isInconsistent ? '双向核对未一致' : ''),
      remark: `E1-31种子${r.voucherNo ? ` 凭证${r.voucherNo}` : ''}`,
      source: 'e1-31',
      currency: 'CNY',
    })
  }
  return { candidates, third, inconsistent, largeUnmatched }
}

function uid(prefix: string): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `${prefix}-${crypto.randomUUID()}`
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

function yn(v: unknown): YesNo {
  if (v === true || v === 'Y' || v === '是') return '是'
  if (v === false || v === 'N' || v === '否') return '否'
  return ''
}

export function createEmptyTxn(): KeyPersonTxnRow {
  return {
    id: uid('kp'),
    accountNo: '',
    bank: '',
    cardNo: '',
    cardType: '',
    transDate: '',
    currency: 'CNY',
    summary: '',
    income: 0,
    expense: 0,
    counterpartyName: '',
    counterpartyAccount: '',
    transBackground: '',
    isAuditee: '',
    isCustomerOrSupplier: '',
    isCommonCounterparty: '',
    otherAnomaly: '',
    remark: '',
    source: 'manual',
  }
}

export function createEmptyPerson(partial?: Partial<KeyPersonBlock>): KeyPersonBlock {
  const id = partial?.id || uid('person')
  return {
    id,
    name: partial?.name || '',
    position: partial?.position || '',
    rows: partial?.rows?.length ? partial.rows : [],
  }
}

function emptyPack(): KeyPersonFlowPack {
  const p = createEmptyPerson({ name: '', position: '' })
  return { persons: [p], activePersonId: p.id, ocrJobs: [] }
}

function normalizeTxn(raw: Record<string, unknown>): KeyPersonTxnRow {
  let income = parseNum(raw.income)
  let expense = parseNum(raw.expense)
  const amount = Math.abs(parseNum(raw.amount))
  if (!income && !expense && amount) {
    const dir = String(raw.direction || '')
    if (dir.includes('支') || dir === '支出' || dir === 'D') expense = amount
    else income = amount
  }
  return {
    id: String(raw.id || uid('kp')),
    accountNo: String(raw.accountNo || ''),
    bank: String(raw.bank || ''),
    cardNo: String(raw.cardNo || raw.accountCardNo || ''),
    cardType: String(raw.cardType || ''),
    transDate: String(raw.transDate || raw.date || ''),
    currency: String(raw.currency || 'CNY'),
    summary: String(raw.summary || ''),
    income,
    expense,
    counterpartyName: String(raw.counterpartyName || raw.counterparty || ''),
    counterpartyAccount: String(raw.counterpartyAccount || ''),
    transBackground: String(raw.transBackground || ''),
    isAuditee: yn(raw.isAuditee),
    isCustomerOrSupplier: yn(raw.isCustomerOrSupplier),
    isCommonCounterparty: yn(raw.isCommonCounterparty),
    otherAnomaly: String(raw.otherAnomaly || raw.abnormalFlag || ''),
    remark: String(raw.remark || ''),
    source: String(raw.source || 'manual'),
  }
}

function normalizePerson(raw: Record<string, unknown>): KeyPersonBlock {
  const rowsRaw = Array.isArray(raw.rows) ? raw.rows : []
  return {
    id: String(raw.id || uid('person')),
    name: String(raw.name || ''),
    position: String(raw.position || ''),
    rows: rowsRaw.map((r: any) => normalizeTxn(r)),
  }
}

function isHit(r: KeyPersonTxnRow): boolean {
  return r.isAuditee === '是'
    || r.isCustomerOrSupplier === '是'
    || r.isCommonCounterparty === '是'
    || !!String(r.otherAnomaly || '').trim()
}

export function useE1KeyPersonFlow(options: UseE1BaseOptions) {
  const { allResponses, saveImmediate, isReadonly } = options

  const pack = ref<KeyPersonFlowPack>(emptyPack())
  const auditNote = ref('')
  const auditConclusion = ref('')
  const isLoading = ref(false)

  const isApplicable = computed(() => {
    const v = allResponses.value.get(E1_IPO_APPLICABLE_KEY)?.conclusion
    return v !== 'N'
  })

  const activePerson = computed(() => {
    const id = pack.value.activePersonId
    return pack.value.persons.find(p => p.id === id) || pack.value.persons[0] || null
  })

  const activeRows = computed(() => activePerson.value?.rows || [])

  const totals = computed(() => {
    const rows = activeRows.value
    return {
      income: rows.reduce((s, r) => s + parseNum(r.income), 0),
      expense: rows.reduce((s, r) => s + parseNum(r.expense), 0),
      hitCount: rows.filter(isHit).length,
      rowCount: rows.length,
    }
  })

  const allHitCount = computed(() =>
    pack.value.persons.reduce((s, p) => s + p.rows.filter(isHit).length, 0),
  )

  function load(): void {
    isLoading.value = true
    try {
      const raw = allResponses.value.get(E1_KEYPERSON_FLOW_PACK_KEY)?.remark
      if (raw) {
        try {
          const parsed = JSON.parse(raw)
          if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
            const persons = Array.isArray(parsed.persons) && parsed.persons.length
              ? parsed.persons.map((p: any) => normalizePerson(p))
              : [createEmptyPerson()]
            const activeId = String(parsed.activePersonId || persons[0].id)
            pack.value = {
              persons,
              activePersonId: persons.some(p => p.id === activeId) ? activeId : persons[0].id,
              ocrJobs: Array.isArray(parsed.ocrJobs)
                ? parsed.ocrJobs.slice(-20).map((j: any) => ({
                    id: String(j.id || uid('ocr')),
                    fileName: String(j.fileName || ''),
                    attachmentId: j.attachmentId ? String(j.attachmentId) : undefined,
                    at: String(j.at || ''),
                    lineCount: parseNum(j.lineCount),
                    skippedCount: parseNum(j.skippedCount),
                    confidence: parseNum(j.confidence),
                    bank: j.bank ? String(j.bank) : undefined,
                    accountNo: j.accountNo ? String(j.accountNo) : undefined,
                    personName: j.personName ? String(j.personName) : undefined,
                  }))
                : [],
            }
          }
        } catch {
          pack.value = emptyPack()
        }
      } else {
        // 旧扁平行：姓名/职位/账号… → 按姓名分组
        const legacy = allResponses.value.get(LEGACY_ROWS_KEY)?.remark
        if (legacy) {
          try {
            const list = JSON.parse(legacy)
            if (Array.isArray(list) && list.length) {
              const byName = new Map<string, KeyPersonBlock>()
              for (const r of list) {
                const name = String(r.name || '未命名')
                if (!byName.has(name)) {
                  byName.set(name, createEmptyPerson({
                    name,
                    position: String(r.position || ''),
                    rows: [],
                  }))
                }
                const block = byName.get(name)!
                if (!block.position && r.position) block.position = String(r.position)
                block.rows.push(normalizeTxn({
                  ...r,
                  income: r.income ?? (parseNum(r.amount) > 0 ? parseNum(r.amount) : 0),
                  expense: r.expense ?? 0,
                  isAuditee: r.isRelatedParty === true || r.isRelatedParty === '是' ? '是' : '',
                  otherAnomaly: r.abnormalFlag || r.otherAnomaly || '',
                }))
              }
              const persons = Array.from(byName.values())
              pack.value = { persons, activePersonId: persons[0].id }
            } else {
              pack.value = emptyPack()
            }
          } catch {
            pack.value = emptyPack()
          }
        } else {
          pack.value = emptyPack()
        }
      }
      auditNote.value = allResponses.value.get(E1_KEYPERSON_FLOW_NOTE_KEY)?.remark
        || allResponses.value.get('E1-ipo-audit-note-E1-32')?.remark
        || ''
      auditConclusion.value = allResponses.value.get(E1_KEYPERSON_FLOW_CONCLUSION_KEY)?.remark
        || allResponses.value.get('E1-ipo-audit-conclusion-E1-32')?.remark
        || ''
    } finally {
      isLoading.value = false
    }
  }

  load()

  watch(
    () => allResponses.value.get(E1_KEYPERSON_FLOW_PACK_KEY)?.remark,
    (n, o) => { if (n !== o) load() },
  )

  let saveTimer: ReturnType<typeof setTimeout> | null = null
  function scheduleSave(): void {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      persist()
    }, 2000)
  }

  function persist(): void {
    const item: ChecklistItem = {
      item_id: E1_KEYPERSON_FLOW_PACK_KEY,
      conclusion: null,
      remark: JSON.stringify(pack.value),
    }
    allResponses.value.set(E1_KEYPERSON_FLOW_PACK_KEY, item)
    saveImmediate([item]).catch(() => {})
  }

  function setApplicable(val: boolean): void {
    if (isReadonly.value) return
    const item = {
      item_id: E1_IPO_APPLICABLE_KEY,
      conclusion: val ? 'Y' : 'N',
      remark: null,
    }
    allResponses.value.set(E1_IPO_APPLICABLE_KEY, item)
    saveImmediate([item]).catch(() => {})
  }

  function setActivePerson(id: string): void {
    if (!pack.value.persons.some(p => p.id === id)) return
    pack.value = { ...pack.value, activePersonId: id }
    scheduleSave()
  }

  function addPerson(name = '', position = ''): string {
    if (isReadonly.value) return ''
    const p = createEmptyPerson({ name, position })
    pack.value = {
      persons: [...pack.value.persons, p],
      activePersonId: p.id,
    }
    scheduleSave()
    return p.id
  }

  function removePerson(id: string): void {
    if (isReadonly.value) return
    let next = pack.value.persons.filter(p => p.id !== id)
    if (!next.length) next = [createEmptyPerson()]
    pack.value = {
      persons: next,
      activePersonId: next.some(p => p.id === pack.value.activePersonId)
        ? pack.value.activePersonId
        : next[0].id,
    }
    scheduleSave()
  }

  function updatePersonMeta(field: 'name' | 'position', value: string): void {
    if (isReadonly.value) return
    const id = pack.value.activePersonId
    pack.value = {
      ...pack.value,
      persons: pack.value.persons.map(p =>
        p.id === id ? { ...p, [field]: value } : p,
      ),
    }
    scheduleSave()
  }

  function mapPersons(
    mapper: (p: KeyPersonBlock) => KeyPersonBlock,
  ): void {
    pack.value = {
      ...pack.value,
      persons: pack.value.persons.map(p =>
        p.id === pack.value.activePersonId ? mapper(p) : p,
      ),
    }
  }

  function addRow(partial?: Partial<KeyPersonTxnRow>): void {
    if (isReadonly.value) return
    mapPersons(p => ({
      ...p,
      rows: [...p.rows, { ...createEmptyTxn(), ...partial }],
    }))
    scheduleSave()
  }

  function removeRow(id: string): void {
    if (isReadonly.value) return
    mapPersons(p => ({ ...p, rows: p.rows.filter(r => r.id !== id) }))
    scheduleSave()
  }

  function updateRow(id: string, field: keyof KeyPersonTxnRow, value: unknown): void {
    if (isReadonly.value) return
    mapPersons(p => ({
      ...p,
      rows: p.rows.map(r => (r.id === id ? { ...r, [field]: value } : r)),
    }))
    scheduleSave()
  }

  /** OCR/导入流水并入当前人员 */
  function mergeOcrLines(
    lines: Array<Partial<KeyPersonTxnRow> & { direction?: string; amount?: number; date?: string; counterparty?: string }>,
    meta?: {
      bank?: string
      accountNo?: string
      name?: string
      position?: string
      ocrJob?: Omit<OcrJobMeta, 'id' | 'at'> & { id?: string; at?: string }
    },
  ): number {
    if (isReadonly.value) return 0
    const mapped = lines.map(r => normalizeTxn({
      ...r,
      bank: r.bank || meta?.bank || '',
      accountNo: r.accountNo || meta?.accountNo || '',
      transDate: r.transDate || r.date || '',
      counterpartyName: r.counterpartyName || r.counterparty || '',
      source: r.source || 'ocr',
    })).filter(r => r.transDate || r.income || r.expense || r.counterpartyName)

    if (!mapped.length) return 0

    const id = pack.value.activePersonId
    let personName = ''
    pack.value = {
      ...pack.value,
      persons: pack.value.persons.map(p => {
        if (p.id !== id) return p
        personName = p.name || meta?.name || ''
        return {
          ...p,
          name: p.name || meta?.name || '',
          position: p.position || meta?.position || '',
          rows: [...p.rows, ...mapped],
        }
      }),
    }
    if (meta?.ocrJob) {
      recordOcrJob({
        ...meta.ocrJob,
        lineCount: meta.ocrJob.lineCount ?? mapped.length,
        personName: meta.ocrJob.personName || personName,
        bank: meta.ocrJob.bank || meta.bank,
        accountNo: meta.ocrJob.accountNo || meta.accountNo,
      })
    } else {
      scheduleSave()
    }
    return mapped.length
  }

  function recordOcrJob(partial: Omit<OcrJobMeta, 'id' | 'at'> & { id?: string; at?: string }): void {
    if (isReadonly.value) return
    const job: OcrJobMeta = {
      id: partial.id || uid('ocr'),
      fileName: partial.fileName || '',
      attachmentId: partial.attachmentId,
      at: partial.at || new Date().toISOString(),
      lineCount: partial.lineCount || 0,
      skippedCount: partial.skippedCount || 0,
      confidence: partial.confidence || 0,
      bank: partial.bank,
      accountNo: partial.accountNo,
      personName: partial.personName,
    }
    const prev = Array.isArray(pack.value.ocrJobs) ? pack.value.ocrJobs : []
    pack.value = { ...pack.value, ocrJobs: [...prev, job].slice(-20) }
    scheduleSave()
  }

  function previewSeedFromE31(): {
    count: number
    third: number
    inconsistent: number
    largeUnmatched: number
  } | null {
    const raw = allResponses.value.get(E1_31_PACK_KEY)?.remark
    if (!raw) return null
    try {
      const pack31 = JSON.parse(raw)
      const r = collectE31SuspectCandidates(pack31)
      if (!r.candidates.length) return { count: 0, third: 0, inconsistent: 0, largeUnmatched: 0 }
      return {
        count: r.candidates.length,
        third: r.third,
        inconsistent: r.inconsistent,
        largeUnmatched: r.largeUnmatched,
      }
    } catch {
      return null
    }
  }

  /**
   * 从 E1-31 可疑抽样行种子。
   * append：追加；replace：先清除当前人 source=e1-31 行再写入。
   */
  function seedFromE31(mode: E31SeedMode = 'append'): number {
    if (isReadonly.value) return 0
    const raw = allResponses.value.get(E1_31_PACK_KEY)?.remark
    if (!raw) return 0
    let pack31: any
    try {
      pack31 = JSON.parse(raw)
    } catch {
      return 0
    }
    const { candidates } = collectE31SuspectCandidates(pack31)
    if (!candidates.length) return 0

    if (mode === 'replace') {
      const id = pack.value.activePersonId
      pack.value = {
        ...pack.value,
        persons: pack.value.persons.map(p =>
          p.id === id
            ? { ...p, rows: p.rows.filter(r => r.source !== 'e1-31') }
            : p,
        ),
      }
    }
    return mergeOcrLines(candidates as any)
  }

  function saveNote(val: string): void {
    if (isReadonly.value) return
    auditNote.value = val
    const item = { item_id: E1_KEYPERSON_FLOW_NOTE_KEY, conclusion: null, remark: val }
    allResponses.value.set(E1_KEYPERSON_FLOW_NOTE_KEY, item)
    saveImmediate([item]).catch(() => {})
  }

  function saveConclusion(val: string): void {
    if (isReadonly.value) return
    auditConclusion.value = val
    const item = { item_id: E1_KEYPERSON_FLOW_CONCLUSION_KEY, conclusion: null, remark: val }
    allResponses.value.set(E1_KEYPERSON_FLOW_CONCLUSION_KEY, item)
    saveImmediate([item]).catch(() => {})
  }

  function hydrate(): void {
    load()
  }

  onBeforeUnmount(() => {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
      persist()
    }
  })

  return {
    pack,
    activePerson,
    activeRows,
    auditNote,
    auditConclusion,
    isLoading,
    isApplicable,
    totals,
    allHitCount,
    setApplicable,
    setActivePerson,
    addPerson,
    removePerson,
    updatePersonMeta,
    addRow,
    removeRow,
    updateRow,
    mergeOcrLines,
    seedFromE31,
    previewSeedFromE31,
    recordOcrJob,
    saveNote,
    saveConclusion,
    hydrate,
    scheduleSave,
  }
}
