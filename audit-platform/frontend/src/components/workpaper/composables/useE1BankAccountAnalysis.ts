/**
 * useE1BankAccountAnalysis — E1-29 银行账户分析（IPO 加深）
 *
 * - Part(一)：账户清单 + 开户地三列（相对 E1-10）
 * - Part(二)：多年账户指标与异常判断
 * - 红旗提示勾选 + 说明/结论
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { UseE1BaseOptions, ChecklistItem } from './useE1Adjudication'
import { parseNum } from './useE1FormulaEngine'
import { E1_ACCOUNT_LIST_STORAGE_KEY } from './useE1AccountList'

export const E1_BANK_ANALYSIS_PACK_KEY = 'E1-bank-analysis-pack'
export const E1_BANK_ANALYSIS_NOTE_KEY = 'E1-bank-analysis-audit-note'
export const E1_BANK_ANALYSIS_CONCLUSION_KEY = 'E1-bank-analysis-audit-conclusion'
export const E1_IPO_APPLICABLE_KEY = 'E1-ipo-applicable'

export type YesNo = '是' | '否' | ''
export type Consistent = '一致' | '不一致' | ''

export interface BankAnalysisRow {
  id: string
  bank: string
  accountNo: string
  accountType: string
  accountStatus: string
  openDate: string
  closeDate: string
  openReason: string
  closeReason: string
  companyInfoConsistent: Consistent
  inconsistencyReason: string
  location: string
  hasBusiness: YesNo
  remoteReason: string
  remark: string
  hasBookRecord: YesNo
  checkResult: Consistent
  /** 是否零余额（分析汇总用） */
  isZeroBalance: YesNo
}

export interface AnalysisYearCols {
  year: number
  accountCount: number
  openedCount: number
  closedCount: number
  zeroBalanceCount: number
}

export interface AnalysisJudgment {
  remoteNoBusinessCount: number
  matchBusinessScale: YesNo
  frequentOpen: YesNo
  frequentClose: YesNo
  anomalyNote: string
  otherRemark: string
}

export interface TipFlag {
  key: string
  label: string
  checked: boolean
  note: string
}

export interface BankAnalysisPack {
  rows: BankAnalysisRow[]
  years: AnalysisYearCols[]
  judgment: AnalysisJudgment
  tips: TipFlag[]
}

export const TIP_DEFS: Array<{ key: string; label: string }> = [
  { key: 'refuseConfirm', label: '不配合银行函证或不配合打印已开立账户清单' },
  { key: 'scaleMismatch', label: '开户数量与业务规模不匹配，或多个零余额账户长期不销户' },
  { key: 'remoteNoBiz', label: '在无经营业务地区开立账户，或异地高额存放资金' },
  { key: 'frequentOpenClose', label: '频繁开销户，或本期突然注销活跃账户' },
  { key: 'personalAccounts', label: '资金进入管理层/员工个人账户，或与个人大额频繁往来' },
  { key: 'raiseFundMisuse', label: '募集资金违规质押、转户或挪用等' },
  { key: 'cashPooling', label: '与实控人/集团签订现金管理账户（资金归集）协议' },
]

function uid(prefix: string): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `${prefix}-${crypto.randomUUID()}`
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

export function createEmptyRow(): BankAnalysisRow {
  return {
    id: uid('ba'),
    bank: '',
    accountNo: '',
    accountType: '',
    accountStatus: '正常',
    openDate: '',
    closeDate: '',
    openReason: '',
    closeReason: '',
    companyInfoConsistent: '',
    inconsistencyReason: '',
    location: '',
    hasBusiness: '',
    remoteReason: '',
    remark: '',
    hasBookRecord: '',
    checkResult: '',
    isZeroBalance: '',
  }
}

function defaultYears(bsYear: number): AnalysisYearCols[] {
  const y = bsYear > 1900 ? bsYear : new Date().getFullYear() - 1
  return [
    { year: y, accountCount: 0, openedCount: 0, closedCount: 0, zeroBalanceCount: 0 },
    { year: y - 1, accountCount: 0, openedCount: 0, closedCount: 0, zeroBalanceCount: 0 },
    { year: y - 2, accountCount: 0, openedCount: 0, closedCount: 0, zeroBalanceCount: 0 },
  ]
}

function defaultJudgment(): AnalysisJudgment {
  return {
    remoteNoBusinessCount: 0,
    matchBusinessScale: '',
    frequentOpen: '',
    frequentClose: '',
    anomalyNote: '',
    otherRemark: '',
  }
}

function defaultTips(): TipFlag[] {
  return TIP_DEFS.map(t => ({ key: t.key, label: t.label, checked: false, note: '' }))
}

function emptyPack(bsYear: number): BankAnalysisPack {
  return {
    rows: [createEmptyRow()],
    years: defaultYears(bsYear),
    judgment: defaultJudgment(),
    tips: defaultTips(),
  }
}

function normalizeRow(raw: Record<string, unknown>): BankAnalysisRow {
  const yn = (v: unknown): YesNo => (v === '是' || v === '否' ? v : '')
  const cs = (v: unknown): Consistent => (v === '一致' || v === '不一致' ? v : '')
  const hasBiz = raw.hasBusiness
  let hasBusiness: YesNo = ''
  if (hasBiz === true || hasBiz === 'Y' || hasBiz === '是') hasBusiness = '是'
  else if (hasBiz === false || hasBiz === 'N' || hasBiz === '否') hasBusiness = '否'

  return {
    id: String(raw.id || uid('ba')),
    bank: String(raw.bank || ''),
    accountNo: String(raw.accountNo || ''),
    accountType: String(raw.accountType || ''),
    accountStatus: String(raw.accountStatus || '正常'),
    openDate: String(raw.openDate || ''),
    closeDate: String(raw.closeDate || ''),
    openReason: String(raw.openReason || raw.openPurpose || ''),
    closeReason: String(raw.closeReason || ''),
    companyInfoConsistent: cs(raw.companyInfoConsistent),
    inconsistencyReason: String(raw.inconsistencyReason || ''),
    location: String(raw.location || ''),
    hasBusiness,
    remoteReason: String(raw.remoteReason || ''),
    remark: String(raw.remark || raw.reason || ''),
    hasBookRecord: yn(raw.hasBookRecord === 'Y' ? '是' : raw.hasBookRecord === 'N' ? '否' : raw.hasBookRecord),
    checkResult: cs(raw.checkResult),
    isZeroBalance: yn(raw.isZeroBalance),
  }
}

function yearFromBs(bs?: string): number {
  if (bs && bs.length >= 4) {
    const y = parseInt(bs.slice(0, 4), 10)
    if (Number.isFinite(y) && y > 1900) return y
  }
  return new Date().getFullYear() - 1
}

export function useE1BankAccountAnalysis(options: UseE1BaseOptions) {
  const { allResponses, saveImmediate, isReadonly, bsDate } = options
  const bsYear = yearFromBs(bsDate?.value)

  const pack = ref<BankAnalysisPack>(emptyPack(bsYear))
  const auditNote = ref('')
  const auditConclusion = ref('')
  const isLoading = ref(false)

  const isApplicable = computed(() => {
    const v = allResponses.value.get(E1_IPO_APPLICABLE_KEY)?.conclusion
    return v !== 'N'
  })

  const rows = computed({
    get: () => pack.value.rows,
    set: (v) => { pack.value = { ...pack.value, rows: v } },
  })

  const inconsistencyCount = computed(() =>
    pack.value.rows.filter(r => r.checkResult === '不一致' || r.companyInfoConsistent === '不一致').length,
  )
  const remoteCount = computed(() =>
    pack.value.rows.filter(r => r.hasBusiness === '否' && String(r.location || '').trim()).length,
  )

  function load(): void {
    isLoading.value = true
    try {
      const y = yearFromBs(bsDate?.value)
      const raw = allResponses.value.get(E1_BANK_ANALYSIS_PACK_KEY)?.remark
      if (raw) {
        try {
          const parsed = JSON.parse(raw)
          if (Array.isArray(parsed)) {
            // 旧 IPO 扁平行
            pack.value = {
              ...emptyPack(y),
              rows: parsed.length ? parsed.map((r: any) => normalizeRow(r)) : [createEmptyRow()],
            }
          } else if (parsed && typeof parsed === 'object') {
            const tipsRaw = Array.isArray(parsed.tips) ? parsed.tips : []
            const tipMap = new Map(tipsRaw.map((t: any) => [String(t.key), t]))
            pack.value = {
              rows: Array.isArray(parsed.rows) && parsed.rows.length
                ? parsed.rows.map((r: any) => normalizeRow(r))
                : [createEmptyRow()],
              years: Array.isArray(parsed.years) && parsed.years.length
                ? parsed.years.map((yr: any) => ({
                    year: parseNum(yr.year) || y,
                    accountCount: parseNum(yr.accountCount),
                    openedCount: parseNum(yr.openedCount),
                    closedCount: parseNum(yr.closedCount),
                    zeroBalanceCount: parseNum(yr.zeroBalanceCount),
                  }))
                : defaultYears(y),
              judgment: { ...defaultJudgment(), ...(parsed.judgment || {}) },
              tips: TIP_DEFS.map(d => {
                const t = tipMap.get(d.key) as any
                return {
                  key: d.key,
                  label: d.label,
                  checked: !!(t && t.checked),
                  note: String(t?.note || ''),
                }
              }),
            }
          }
        } catch {
          pack.value = emptyPack(y)
        }
      } else {
        // 旧 IPO 扁平行 E1-ipo-E1-29-rows，或从 E1-10 预填
        const legacy = allResponses.value.get('E1-ipo-E1-29-rows')?.remark
        if (legacy) {
          try {
            const list = JSON.parse(legacy)
            if (Array.isArray(list) && list.length) {
              pack.value = {
                ...emptyPack(y),
                rows: list.map((r: any) => normalizeRow(r)),
              }
              recalcCurrentYearFromRows()
            } else {
              pack.value = emptyPack(y)
            }
          } catch {
            pack.value = emptyPack(y)
          }
        } else {
          const e10 = allResponses.value.get(E1_ACCOUNT_LIST_STORAGE_KEY)?.remark
          if (e10) {
            try {
              const list = JSON.parse(e10)
              if (Array.isArray(list) && list.length) {
                pack.value = {
                  ...emptyPack(y),
                  rows: list.map((r: any) => normalizeRow(r)),
                }
                recalcCurrentYearFromRows()
              } else {
                pack.value = emptyPack(y)
              }
            } catch {
              pack.value = emptyPack(y)
            }
          } else {
            pack.value = emptyPack(y)
          }
        }
      }
      auditNote.value = allResponses.value.get(E1_BANK_ANALYSIS_NOTE_KEY)?.remark
        || allResponses.value.get('E1-ipo-audit-note-E1-29')?.remark
        || ''
      auditConclusion.value = allResponses.value.get(E1_BANK_ANALYSIS_CONCLUSION_KEY)?.remark
        || allResponses.value.get('E1-ipo-audit-conclusion-E1-29')?.remark
        || ''
    } finally {
      isLoading.value = false
    }
  }

  load()

  watch(
    () => allResponses.value.get(E1_BANK_ANALYSIS_PACK_KEY)?.remark,
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
    const remark = JSON.stringify(pack.value)
    const item: ChecklistItem = {
      item_id: E1_BANK_ANALYSIS_PACK_KEY,
      conclusion: null,
      remark,
    }
    allResponses.value.set(E1_BANK_ANALYSIS_PACK_KEY, item)
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

  function addRow(): void {
    if (isReadonly.value) return
    pack.value = { ...pack.value, rows: [...pack.value.rows, createEmptyRow()] }
    scheduleSave()
  }

  function removeRow(id: string): void {
    if (isReadonly.value) return
    let next = pack.value.rows.filter(r => r.id !== id)
    if (!next.length) next = [createEmptyRow()]
    pack.value = { ...pack.value, rows: next }
    scheduleSave()
  }

  function updateCell(id: string, field: keyof BankAnalysisRow, value: unknown): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      rows: pack.value.rows.map(r => (r.id === id ? { ...r, [field]: value } : r)),
    }
    scheduleSave()
  }

  function updateYearCell(
    year: number,
    field: keyof Omit<AnalysisYearCols, 'year'>,
    value: number,
  ): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      years: pack.value.years.map(y =>
        y.year === year ? { ...y, [field]: parseNum(value) } : y,
      ),
    }
    scheduleSave()
  }

  function updateJudgment<K extends keyof AnalysisJudgment>(key: K, value: AnalysisJudgment[K]): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      judgment: { ...pack.value.judgment, [key]: value },
    }
    scheduleSave()
  }

  function updateTip(key: string, field: 'checked' | 'note', value: boolean | string): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      tips: pack.value.tips.map(t =>
        t.key === key ? { ...t, [field]: value } : t,
      ),
    }
    scheduleSave()
  }

  /** 用明细行回填当期年度指标（不覆盖历史两年） */
  function recalcCurrentYearFromRows(): void {
    const y = yearFromBs(bsDate?.value)
    const rs = pack.value.rows.filter(r => r.bank || r.accountNo)
    const accountCount = rs.length
    const openedCount = rs.filter(r => r.openDate && r.openDate.startsWith(String(y))).length
    const closedCount = rs.filter(r =>
      (r.closeDate && r.closeDate.startsWith(String(y)))
      || r.accountStatus.includes('销'),
    ).length
    const zeroBalanceCount = rs.filter(r => r.isZeroBalance === '是').length
    const remoteNoBusinessCount = rs.filter(r => r.hasBusiness === '否').length
    pack.value = {
      ...pack.value,
      years: pack.value.years.map(col =>
        col.year === y
          ? { ...col, accountCount, openedCount, closedCount, zeroBalanceCount }
          : col,
      ),
      judgment: {
        ...pack.value.judgment,
        remoteNoBusinessCount,
      },
    }
    scheduleSave()
  }

  function previewSyncFromE10(): { sourceCount: number; existingCount: number; newAccounts: number } | null {
    const e10 = allResponses.value.get(E1_ACCOUNT_LIST_STORAGE_KEY)?.remark
    if (!e10) return null
    try {
      const list = JSON.parse(e10)
      if (!Array.isArray(list) || !list.length) return null
      const existing = new Set(pack.value.rows.map(r => r.accountNo).filter(Boolean))
      let newAccounts = 0
      for (const r of list) {
        const no = String(r.accountNo || r.account || '').trim()
        if (no && !existing.has(no)) newAccounts += 1
      }
      return { sourceCount: list.length, existingCount: pack.value.rows.length, newAccounts }
    } catch {
      return null
    }
  }

  function syncFromE10(mode: 'replace' | 'merge' = 'replace'): number {
    if (isReadonly.value) return 0
    const e10 = allResponses.value.get(E1_ACCOUNT_LIST_STORAGE_KEY)?.remark
    if (!e10) return 0
    try {
      const list = JSON.parse(e10)
      if (!Array.isArray(list) || !list.length) return 0
      const byAcct = new Map(pack.value.rows.map(r => [r.accountNo, r]))

      if (mode === 'merge') {
        const rows = [...pack.value.rows]
        let added = 0
        for (const r of list) {
          const base = normalizeRow(r)
          if (!base.accountNo) continue
          if (byAcct.has(base.accountNo)) continue
          rows.push(base)
          byAcct.set(base.accountNo, base)
          added += 1
        }
        if (!added) return 0
        pack.value = { ...pack.value, rows }
        recalcCurrentYearFromRows()
        scheduleSave()
        return added
      }

      // replace：整表按 E1-10 重建，保留同账号加深字段
      const rows = list.map((r: any) => {
        const base = normalizeRow(r)
        const prev = byAcct.get(base.accountNo)
        if (!prev) return base
        return {
          ...base,
          location: prev.location || base.location,
          hasBusiness: prev.hasBusiness || base.hasBusiness,
          remoteReason: prev.remoteReason || base.remoteReason,
          remark: prev.remark || base.remark,
          isZeroBalance: prev.isZeroBalance || base.isZeroBalance,
        }
      })
      pack.value = { ...pack.value, rows }
      recalcCurrentYearFromRows()
      scheduleSave()
      return rows.length
    } catch {
      return 0
    }
  }

  function saveNote(val: string): void {
    if (isReadonly.value) return
    auditNote.value = val
    const item = { item_id: E1_BANK_ANALYSIS_NOTE_KEY, conclusion: null, remark: val }
    allResponses.value.set(E1_BANK_ANALYSIS_NOTE_KEY, item)
    saveImmediate([item]).catch(() => {})
  }

  function saveConclusion(val: string): void {
    if (isReadonly.value) return
    auditConclusion.value = val
    const item = { item_id: E1_BANK_ANALYSIS_CONCLUSION_KEY, conclusion: null, remark: val }
    allResponses.value.set(E1_BANK_ANALYSIS_CONCLUSION_KEY, item)
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
    rows,
    auditNote,
    auditConclusion,
    isLoading,
    isApplicable,
    inconsistencyCount,
    remoteCount,
    setApplicable,
    addRow,
    removeRow,
    updateCell,
    updateYearCell,
    updateJudgment,
    updateTip,
    recalcCurrentYearFromRows,
    syncFromE10,
    previewSyncFromE10,
    saveNote,
    saveConclusion,
    hydrate,
    scheduleSave,
  }
}
